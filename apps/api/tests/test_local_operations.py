import json
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import select
from test_catalog_digests import completed_offer

from bouquetbrowse.catalog_event_models import CatalogChange, DailyDigest
from bouquetbrowse.db import utcnow
from bouquetbrowse.digests import HANOI
from bouquetbrowse.discovery import settings_row
from bouquetbrowse.local_schedule import next_check, tick
from bouquetbrowse.models import Job, Listing, MediaAsset, PostVersion
from bouquetbrowse.offer_models import OfferAnalysis
from bouquetbrowse.operations_models import DeletionRecord, ScheduleSlot
from bouquetbrowse.recovery import checksum, private_directory, replay_deletions, verify_manifest
from bouquetbrowse.retention import expire
from bouquetbrowse.runtime_models import GraphExecution
from bouquetbrowse.worker import purge_listing


def test_placeholder_runtime_never_schedules_or_creates_fake_digests(db):
    assert tick(db)["scheduled"] == 0
    assert not list(db.scalars(select(ScheduleSlot)))
    assert not list(db.scalars(select(DailyDigest)))


def test_hanoi_slots_are_idempotent_and_sleep_never_bursts(db, monkeypatch):
    from bouquetbrowse import local_schedule

    monkeypatch.setattr(local_schedule, "collection_ready", lambda *args: True)
    now = datetime(2026, 10, 29, 10, 0, 30, tzinfo=HANOI)
    settings_row(db).paused = False
    assert tick(db, now)["scheduled"] == 1
    assert tick(db, now)["scheduled"] == 0
    first = db.scalar(select(ScheduleSlot).where(ScheduleSlot.state == "queued"))
    assert first.slot_key.endswith("T10:00+07:00")
    # Wake the following morning after all windows have elapsed.
    later = now + timedelta(days=1, minutes=35)
    assert tick(db, later)["scheduled"] == 0
    digest_row = db.scalar(select(DailyDigest))
    assert digest_row.partial and digest_row.coverage["missed"] == 5
    assert all(s.state == "missed" for s in db.scalars(select(ScheduleSlot)))


def test_final_run_closes_digest_and_refresh_cadences(db, monkeypatch):
    from bouquetbrowse import local_schedule

    monkeypatch.setattr(local_schedule, "collection_ready", lambda *args: True)
    now = datetime(2026, 10, 29, 22, 0, 10, tzinfo=HANOI)
    assert tick(db, now)["scheduled"] == 1
    assert not list(db.scalars(select(DailyDigest)))
    execution = db.scalar(select(GraphExecution))
    execution.state = "completed"
    assert tick(db, now + timedelta(minutes=1))["scheduled"] == 0
    assert db.scalar(select(DailyDigest)).partial
    profile = SimpleNamespace(kind="profile", evidence_gaps=[])
    assert next_check(profile, now) == now + timedelta(days=7)
    profile.evidence_gaps = ["unresolved"]
    assert next_check(profile, now).hour == 6


def test_takedown_scrubs_new_graph_evidence_and_queues_checkpoint_deletion(db):
    offer, execution, analysis = completed_offer(db)
    listing_id = offer.listing_id
    purge_listing(db, listing_id)
    db.flush()
    assert db.get(Listing, listing_id).state == "withdrawn"
    assert db.get(OfferAnalysis, analysis.id).output == {}
    assert not any(v.caption for v in db.scalars(select(PostVersion)))
    assert db.get(GraphExecution, execution.id).state == "withdrawn"
    assert list(db.scalars(select(DeletionRecord)))
    assert db.scalar(select(Job).where(Job.kind == "delete-checkpoints"))
    assert all(not e.details or e.suppressed for e in db.scalars(select(CatalogChange)))
    assert all(a.state == "removed" for a in db.scalars(select(MediaAsset)))


def test_expiry_and_deletion_replay_are_idempotent(db):
    offer, execution, analysis = completed_offer(db)
    for version in db.scalars(select(PostVersion)):
        version.retention_until = utcnow() - timedelta(seconds=1)
    assert expire(db)["expired_versions"] > 0
    assert expire(db)["expired_versions"] == 0
    values = [{"subject_kind": "listing", "subject_id": offer.listing_id, "reason": "takedown"}]
    assert replay_deletions(db, values) == 1
    assert replay_deletions(db, values) == 1
    assert db.get(OfferAnalysis, analysis.id).output == {}


def test_backup_manifest_rejects_changes_and_path_escape(tmp_path):
    artifact = tmp_path / "database.dump"
    artifact.write_bytes(b"fictional backup")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "version": "bouquet-backup-v1",
                "files": [{"name": artifact.name, "sha256": checksum(artifact), "bytes": artifact.stat().st_size}],
            }
        )
    )
    assert verify_manifest(manifest)["version"] == "bouquet-backup-v1"
    artifact.write_bytes(b"changed")
    with pytest.raises(ValueError, match="checksum"):
        verify_manifest(manifest)
    from bouquetbrowse.config import ROOT

    with pytest.raises(ValueError, match="ignored"):
        private_directory(ROOT / "docs" / "private-backup")


def test_operations_status_restricts_access_and_reports_zero_real_coverage(client, admin_headers, tester_headers):
    assert client.get("/v1/admin/operations/status", headers=tester_headers).status_code == 403
    body = client.get("/v1/admin/operations/status", headers=admin_headers).json()
    assert body["coverage"]["visible_real_listings"] == 0
    assert body["readiness"]["ready"] is False


def test_paid_response_after_takedown_settles_cost_without_restoring_content(db):
    from bouquetbrowse.model_calls import CallScope, call_scope, invoke_once
    from bouquetbrowse.models import CostEntry
    from bouquetbrowse.providers import CapabilityError
    from bouquetbrowse.runtime_models import ModelCall

    offer, execution, analysis = completed_offer(db)
    db.commit()

    def fake_in_flight():
        purge_listing(db, offer.listing_id)
        db.commit()
        return {"private": "must not return"}, {}, 0.001

    with call_scope(CallScope("deletion-race", 100000, execution.id)):
        with pytest.raises(CapabilityError, match="deleted"):
            invoke_once("fictional", {"test": "deletion-race"}, fake_in_flight, 0.01)
    db.expire_all()
    assert db.scalar(select(ModelCall)).result is None
    assert db.scalar(select(ModelCall)).state == "removed"
    assert db.scalar(select(CostEntry)).state == "settled"


def test_image_only_call_without_offer_is_scrubbed_through_media_dependency(db):
    from bouquetbrowse.model_calls import invoke_once
    from bouquetbrowse.providers import CapabilityError
    from bouquetbrowse.retention import remove_media
    from bouquetbrowse.runtime_models import ModelCall

    asset = MediaAsset(state="ready", checksum="a" * 64, retention_until=utcnow() + timedelta(days=30))
    db.add(asset)
    db.commit()

    def fake_in_flight():
        remove_media(db, asset)
        db.commit()
        return {"flowers": []}, {}, 0.001

    with pytest.raises(CapabilityError, match="deleted"):
        invoke_once("fictional", {"views": [{"media_id": asset.id}]}, fake_in_flight, 0.01)
    db.expire_all()
    assert db.scalar(select(ModelCall)).result is None


def test_sqlite_backup_restore_replays_later_deletion_before_reading(db, tmp_path):
    # A content recovery exercise uses a private fictional snapshot, never the user's DB.
    import sqlite3

    from sqlalchemy.orm import Session

    from bouquetbrowse.db import make_engine
    from bouquetbrowse.recovery import export_deletions

    if db.bind.dialect.name != "sqlite":
        pytest.skip("SQLite artifact rehearsal; PostgreSQL migrations/checkpoints are exercised separately")
    offer, execution, analysis = completed_offer(db)
    listing_id, analysis_id = offer.listing_id, analysis.id
    db.commit()
    saved = tmp_path / "fictional-snapshot.db"
    with sqlite3.connect(db.bind.url.database) as source, sqlite3.connect(saved) as target:
        source.backup(target)
    purge_listing(db, listing_id)
    db.commit()
    ledger_path = tmp_path / "current-deletions.jsonl"
    export_deletions(db, ledger_path)
    restored = make_engine(f"sqlite:///{saved}")
    with Session(restored) as target:
        assert target.get(OfferAnalysis, analysis_id).output
        replay_deletions(target, [json.loads(line) for line in ledger_path.read_text().splitlines()])
        target.commit()
        assert target.get(Listing, listing_id).state == "withdrawn"
        assert target.get(OfferAnalysis, analysis_id).output == {}
    restored.dispose()
