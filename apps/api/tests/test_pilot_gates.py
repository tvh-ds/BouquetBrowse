from datetime import timedelta

import pytest
from sqlalchemy import select
from test_catalog_digests import completed_offer

from bouquetbrowse.conversation_models import CaptureMember
from bouquetbrowse.db import utcnow
from bouquetbrowse.models import AppUser
from bouquetbrowse.pilot import approve_proof, commercial_signature, offer_configuration, readiness, stage_proof
from bouquetbrowse.publication_gates import publication_ready


def reference(db, offer, analysis):
    from bouquetbrowse.runtime_models import GraphExecution

    execution = db.get(GraphExecution, analysis.execution_id)
    execution.configuration = offer_configuration(execution.configuration)
    db.flush()
    capture_id = db.scalar(select(CaptureMember.capture_id))
    return {
        "capture_id": capture_id,
        "pattern": "seller_root",
        "features": ["partial", "missing_price"],
        "reviewers": ["fictional-reviewer-a", "fictional-reviewer-b"],
        "offers": [
            {
                "offer_id": offer.id,
                "seller_account_id": offer.account_id,
                "abstain": False,
                "commercial_hash": commercial_signature(analysis.output),
            }
        ],
    }


def test_settings_cannot_open_a_release_gate(db):
    from bouquetbrowse.discovery import settings_row

    row = settings_row(db)
    row.release_gates = {"ready": True, "conversation_proof": True, "recognition_proof": True}
    db.flush()
    assert not publication_ready(db, offer_configuration())
    assert readiness(db)["live_results"] == "Not yet validated on real data"


def test_workflow_proof_uses_actual_analysis_and_is_idempotent(db):
    offer, execution, analysis = completed_offer(db)
    row = reference(db, offer, analysis)
    proof = stage_proof(db, "conversation", [row], execution.configuration)
    assert proof.report["failures"] == []
    assert not proof.report["dataset_ready"]
    assert stage_proof(db, "conversation", [row], execution.configuration).id == proof.id
    row["offers"][0]["commercial_hash"] = "f" * 64
    failed = stage_proof(db, "conversation", [row], execution.configuration)
    assert failed.report["failures"] == ["unsupported_or_missing_commercial_binding"]
    row["offers"][0]["seller_account_id"] = "another-seller"
    wrong = stage_proof(db, "conversation", [row], execution.configuration)
    assert "wrong_seller_or_unbound_offer" in wrong.report["failures"]


def test_synthetic_or_changed_proof_cannot_be_approved(db):
    offer, execution, analysis = completed_offer(db)
    proof = stage_proof(db, "conversation", [reference(db, offer, analysis)], execution.configuration)
    db.add(AppUser(id="operator", role="admin"))
    db.flush()
    with pytest.raises(ValueError, match="synthetic"):
        approve_proof(db, proof.id, proof.report_hash, "operator", "local-permission-ref", True)
    with pytest.raises(ValueError, match="admin"):
        approve_proof(db, proof.id, proof.report_hash, "unknown", "local-permission-ref", True)
    proof.report = {**proof.report, "dataset_ready": True}
    with pytest.raises(ValueError, match="changed"):
        approve_proof(db, proof.id, proof.report_hash, "operator", "local-permission-ref", True)


def test_expired_reference_and_duplicate_reviewers_rejected(db):
    offer, execution, analysis = completed_offer(db)
    row = reference(db, offer, analysis)
    row["reviewers"] = ["same", "same"]
    with pytest.raises(ValueError, match="distinct reviewers"):
        stage_proof(db, "conversation", [row], execution.configuration)
    row["reviewers"] = ["one", "two"]
    from bouquetbrowse.conversation_models import ConversationCapture

    db.get(ConversationCapture, row["capture_id"]).retention_until = utcnow() - timedelta(days=1)
    with pytest.raises(ValueError, match="expired"):
        stage_proof(db, "conversation", [row], execution.configuration)


def test_pilot_routes_are_admin_only_and_do_not_call_models(db, client, admin_headers, tester_headers):
    assert client.get("/v1/admin/pilot/readiness", headers=tester_headers).status_code == 403
    assert client.get("/v1/admin/pilot/readiness", headers=admin_headers).json()["ready"] is False
    assert client.get("/v1/admin/discovery/status", headers=admin_headers).json()["publication_enabled"] is False
    from bouquetbrowse.runtime_models import ModelCall

    assert not list(db.scalars(select(ModelCall)))


def test_approved_image_proof_support_is_configuration_and_evidence_bound(db):
    from test_mixed_recognition import judgments, result

    from bouquetbrowse.models import MediaAsset
    from bouquetbrowse.recognition import merge_components
    from bouquetbrowse.recognition_contracts import FlowerVisual

    rows = judgments()
    from bouquetbrowse.recognition import configuration_hash
    from bouquetbrowse.recognition_models import RecognitionRecord

    config = offer_configuration()
    for row in rows:
        db.add(
            MediaAsset(
                id=row["image_id"],
                checksum=row["checksum"],
                state="ready",
                retention_until=utcnow() + timedelta(days=30),
            )
        )
        for purpose, prediction_key, id_key in [
            ("joint", "joint_predictions", "joint_record_id"),
            ("image_only", "image_only_predictions", "image_only_record_id"),
        ]:
            record = RecognitionRecord(
                cache_key=f"{purpose}-{row['image_id']}",
                purpose=purpose,
                configuration_hash=configuration_hash(config),
                result={
                    "flowers": [
                        {"flower": f, "state": "present", "view_ids": [row["image_id"]], "alternatives": []}
                        for f in row[prediction_key]
                    ]
                },
                dependencies={
                    "views": [{"media_id": row["image_id"], "view_id": row["image_id"], "checksum": row["checksum"]}]
                },
                retention_until=utcnow() + timedelta(days=30),
            )
            db.add(record)
            db.flush()
            row[id_key] = record.id
    db.add(AppUser(id="operator", role="admin"))
    db.flush()
    # Fictional data deliberately exercises the real-data branch in an isolated test DB.
    # It is never installed as a production proof or reported as measured performance.
    proof = stage_proof(db, "recognition", rows, config, "permitted_real")
    approve_proof(db, proof.id, proof.report_hash, "operator", "fictional-test-only", True)
    db.flush()
    observed = result([FlowerVisual(flower="rose", state="present", view_ids=[rows[0]["image_id"]])])
    views = [{"view_id": rows[0]["image_id"], "media_id": rows[0]["image_id"], "checksum": rows[0]["checksum"]}]
    assert merge_components(db, [], [observed], config, views)[0]["supported"]
    assert not publication_ready(db, config)  # Conversation proof is independently required.
    changed = {**config, "recognition_version": "changed"}
    assert not merge_components(db, [], [observed], changed, views)[0]["supported"]
    db.get(MediaAsset, rows[0]["image_id"]).retention_until = utcnow() - timedelta(seconds=1)
    assert not merge_components(db, [], [observed], config, views)[0]["supported"]
