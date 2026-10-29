import json
import subprocess
from datetime import timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from bouquetbrowse import backups, maintenance
from bouquetbrowse.config import Settings
from bouquetbrowse.db import utcnow
from bouquetbrowse.maintenance_models import OperationAlert
from bouquetbrowse.models import Job
from bouquetbrowse.pipeline import enqueue
from bouquetbrowse.recovery import verify_manifest


def test_daily_backup_is_idempotent_and_does_not_catch_up(db, monkeypatch):
    settings = Settings(_env_file=None, backups_enabled=True)
    monkeypatch.setattr(maintenance, "get_settings", lambda: settings)
    now = utcnow().replace(hour=12)
    old = enqueue(db, "backup", {}, "old-backup")
    old.created_at = now - timedelta(days=3)
    db.flush()
    maintenance.tick(db, now)
    maintenance.tick(db, now)
    jobs = list(db.scalars(select(Job).where(Job.kind == "backup")))
    assert len(jobs) == 2
    assert old.state == "cancelled"
    assert sum(j.state == "queued" for j in jobs) == 1


def test_alert_transitions_deliver_once_per_version_and_ack_is_fenced(client, db, monkeypatch, admin_headers, tmp_path):
    settings = Settings(_env_file=None, alert_directory=tmp_path / "alerts")
    monkeypatch.setattr(maintenance, "get_settings", lambda: settings)
    now = utcnow()
    maintenance.set_alert(db, "jobs_failed", {"count": 1}, now)
    maintenance.set_alert(db, "jobs_failed", {"count": 1}, now)
    db.commit()
    row = db.scalar(select(OperationAlert))
    jobs = list(db.scalars(select(Job).where(Job.kind == "deliver-alert")))
    assert len(jobs) == 1
    maintenance.deliver(jobs[0].payload)
    log = next(settings.alert_directory.glob("alerts-*.jsonl"))
    data = json.loads(log.read_text(encoding="utf-8"))
    assert data["event_id"] == f"{row.id}:1"
    assert "caption" not in data and "token" not in data
    response = client.post(
        f"/v1/admin/operations/alerts/{row.id}/acknowledge", json={"expected_version": 0}, headers=admin_headers
    )
    assert response.status_code == 422
    assert (
        client.post(
            f"/v1/admin/operations/alerts/{row.id}/acknowledge", json={"expected_version": 1}, headers=admin_headers
        ).status_code
        == 200
    )
    db.expire_all()
    maintenance.set_alert(db, "jobs_failed", {}, now)
    db.flush()
    assert row.state == "resolved" and row.version == 2
    maintenance.set_alert(db, "jobs_failed", {"count": 1}, now)
    db.flush()
    assert row.state == "open" and row.version == 3 and row.acknowledged_by is None


def test_native_backup_manifest_and_no_credential_in_arguments(db, tmp_path):
    from sqlalchemy.orm import sessionmaker

    factory = sessionmaker(db.bind, expire_on_commit=False)
    settings = Settings(
        _env_file=None,
        database_url="postgresql+psycopg://fictional:private-placeholder@localhost/fake_test",
        backup_directory=tmp_path / "backups",
    )
    observed = []

    def runner(command, **kwargs):
        assert "private-placeholder" not in " ".join(command)
        assert kwargs["env"]["PGPASSWORD"] == "private-placeholder"
        kwargs["stdout"].write(b"fictional custom database archive")
        observed.append(command)
        return SimpleNamespace(returncode=0)

    result = backups.create_backup(factory, settings, runner)
    manifest = settings.backup_directory / result["snapshot"] / "manifest.json"
    assert verify_manifest(manifest)["media"]["objects"] == 0
    assert len(observed) == 1
    assert (settings.backup_directory / "current-deletions" / "deletions-current.jsonl").is_file()


def test_failed_backup_never_publishes_manifest_and_retention_refuses_extra_files(db, tmp_path):
    from sqlalchemy.orm import sessionmaker

    factory = sessionmaker(db.bind, expire_on_commit=False)
    settings = Settings(
        _env_file=None,
        database_url="postgresql+psycopg://fictional:placeholder@localhost/fake_test",
        backup_directory=tmp_path / "backups",
    )

    def failure(command, **kwargs):
        raise subprocess.CalledProcessError(1, command)

    with pytest.raises(Exception, match="Backup failed"):
        backups.create_backup(factory, settings, failure)
    assert not list(settings.backup_directory.glob("snapshot-*/manifest.json"))

    def successful(command, **kwargs):
        kwargs["stdout"].write(b"fictional archive")

    result = backups.create_backup(factory, settings, successful)
    snapshot = settings.backup_directory / result["snapshot"]
    extra = snapshot / "user-notes.txt"
    extra.write_text("Unowned fixture file", encoding="utf-8")
    with pytest.raises(ValueError, match="unowned files"):
        backups.prune_backups(settings.backup_directory, utcnow() + timedelta(days=8))
    assert extra.is_file() and (snapshot / "database.dump").is_file()
    extra.unlink()
    assert backups.prune_backups(settings.backup_directory, utcnow() + timedelta(days=8)) == 1
    assert not snapshot.exists()
    assert (settings.backup_directory / "current-deletions" / "deletions-current.jsonl").exists()


def test_alert_rejects_arbitrary_payloads(monkeypatch, tmp_path):
    monkeypatch.setattr(
        maintenance, "get_settings", lambda: Settings(_env_file=None, alert_directory=tmp_path / "alerts")
    )
    with pytest.raises(ValueError):
        maintenance.deliver({"code": "jobs_failed", "state": "open", "token": "untrusted"})
    assert not (tmp_path / "alerts").exists()
