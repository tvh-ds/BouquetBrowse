import hashlib
from types import SimpleNamespace

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from sqlalchemy import select
from test_catalog_digests import completed_offer
from test_mixed_recognition import image_bytes, result

from bouquetbrowse import config, model_calls, recognition
from bouquetbrowse.catalog import selected_image_vectors
from bouquetbrowse.config import Settings
from bouquetbrowse.conversation_models import OfferAssociation
from bouquetbrowse.crop_vectors import commit, enqueue_crop, prepare
from bouquetbrowse.db import utcnow
from bouquetbrowse.evaluation import EvaluationServices, checked_item, judgments
from bouquetbrowse.graphs import evaluation_graph, invoke_graph
from bouquetbrowse.leases import claim
from bouquetbrowse.models import CostEntry, Listing, MediaAsset
from bouquetbrowse.recognition_contracts import FlowerVisual
from bouquetbrowse.research_models import CropEmbedding, EvaluationDataset, EvaluationItem
from bouquetbrowse.runtime_models import GraphExecution
from bouquetbrowse.vision import MODEL


def source(db, monkeypatch):
    offer, _, _ = completed_offer(db)
    asset = db.scalar(
        select(MediaAsset)
        .join(OfferAssociation, OfferAssociation.media_id == MediaAsset.id)
        .where(OfferAssociation.offer_id == offer.id)
    )
    content = image_bytes()
    asset.checksum, asset.storage_key = (
        hashlib.sha256(content).hexdigest(),
        hashlib.sha256(content).hexdigest() + ".jpg",
    )
    db.commit()
    monkeypatch.setattr("bouquetbrowse.storage.get_media_bytes", lambda key: content)
    return offer, asset


def fake_models(monkeypatch):
    import openai

    settings = Settings(_env_file=None, openai_api_key="fictional-test-key")
    for module in [config, recognition, model_calls]:
        monkeypatch.setattr(module, "get_settings", lambda: settings)
    calls = []

    def parse(**kwargs):
        import json

        content = kwargs["input"][1]["content"]
        purpose = json.loads(content[0]["text"])["purpose"]
        view_id = json.loads(content[1]["text"])["view_id"]
        calls.append(purpose)
        return SimpleNamespace(
            output_parsed=result(
                [FlowerVisual(flower="rose", state="present", view_ids=[view_id])], interpretation=purpose == "joint"
            ),
            usage=SimpleNamespace(model_dump=lambda: {"input_tokens": 100, "output_tokens": 100}),
            model="gpt-6-luna",
        )

    monkeypatch.setattr(openai, "OpenAI", lambda **kwargs: SimpleNamespace(responses=SimpleNamespace(parse=parse)))
    return calls


def dataset(client, db, monkeypatch, headers):
    offer, asset = source(db, monkeypatch)
    response = client.post(
        "/v1/admin/evaluations",
        json={
            "name": "Fictional evaluation",
            "items": [
                {"offer_id": offer.id, "media_id": asset.id, "split": "development", "image_family": "fictional-family"}
            ],
        },
        headers={**headers, "Idempotency-Key": "dataset"},
    )
    assert response.status_code == 200, response.text
    dataset_id = response.json()["id"]
    item = db.scalar(select(EvaluationItem).where(EvaluationItem.dataset_id == dataset_id))
    annotation = {
        "expected_version": item.version,
        "labels": ["rose"],
        "assessable": ["rose", "peony"],
        "reviewers": ["fictional-reviewer"],
        "split": "development",
        "image_family": "fictional-family",
    }
    saved = client.post(
        f"/v1/admin/evaluations/{dataset_id}/items/{item.id}/annotation", json=annotation, headers=headers
    )
    assert saved.status_code == 200, saved.text
    db.expire_all()
    return db.get(EvaluationDataset, dataset_id), item, offer


def test_durable_evaluation_runs_both_paths_without_publication(client, db, monkeypatch, admin_headers):
    dataset_row, item, offer = dataset(client, db, monkeypatch, admin_headers)
    calls = fake_models(monkeypatch)
    response = client.post(
        f"/v1/admin/evaluations/{dataset_row.id}/run",
        json={"expected_version": dataset_row.version},
        headers={**admin_headers, "Idempotency-Key": "run"},
    )
    assert response.status_code == 200, response.text
    db.expire_all()
    execution = db.get(GraphExecution, response.json()["execution_ids"][0])
    lease = claim(kinds=["evaluation-graph"])
    saver = InMemorySaver()
    invoke_graph(evaluation_graph(EvaluationServices(execution.id, lease), saver), execution.id)
    db.expire_all()
    values = judgments(db, dataset_row)
    assert calls == ["joint", "image_only"]
    assert values[0]["joint_predictions"] == ["rose"]
    assert values[0]["image_only_predictions"] == ["rose"]
    assert values[0]["cost_microusd"] > 0
    before = len(list(db.scalars(select(CostEntry))))
    invoke_graph(evaluation_graph(EvaluationServices(execution.id, lease), saver), execution.id)
    assert len(list(db.scalars(select(CostEntry)))) == before
    assert db.get(Listing, offer.listing_id).state == "review"
    exported = client.get(f"/v1/admin/evaluations/{dataset_row.id}/export", headers=admin_headers)
    assert exported.status_code == 200
    assert "PRIVATE BUYER CONTEXT" not in exported.text
    staged = client.post(
        f"/v1/admin/evaluations/{dataset_row.id}/stage",
        json={"expected_version": dataset_row.version},
        headers=admin_headers,
    )
    assert staged.status_code == 200, staged.text
    assert not staged.json()["report"]["dataset_ready"]


def test_crash_after_receipt_reuses_paid_work(client, db, monkeypatch, admin_headers):
    dataset_row, _, _ = dataset(client, db, monkeypatch, admin_headers)
    calls = fake_models(monkeypatch)
    from bouquetbrowse.evaluation import queue_dataset

    ids = queue_dataset(db, dataset_row)
    db.commit()
    lease = claim(kinds=["evaluation-graph"])
    services = EvaluationServices(ids[0], lease)
    original = services.composite

    def crash(*args):
        original(*args)
        raise RuntimeError("synthetic crash after durable receipt")

    monkeypatch.setattr(services, "composite", crash)
    with pytest.raises(RuntimeError, match="synthetic crash"):
        services.stage("joint", {})
    assert calls == ["joint"]
    monkeypatch.setattr(services, "composite", original)
    invoke_graph(evaluation_graph(services, InMemorySaver()), ids[0])
    assert calls == ["joint", "image_only"]
    db.expire_all()
    assert len(judgments(db, dataset_row)) == 1


def test_uncertain_evaluation_requires_explicit_replay(client, db, monkeypatch, admin_headers):
    import openai

    from bouquetbrowse.evaluation import queue_dataset
    from bouquetbrowse.providers import CapabilityError
    from bouquetbrowse.runtime_models import ModelCall

    dataset_row, _, _ = dataset(client, db, monkeypatch, admin_headers)
    fake_models(monkeypatch)
    dispatched = []

    def timeout(**kwargs):
        dispatched.append(True)
        raise TimeoutError("fictional response lost after dispatch")

    monkeypatch.setattr(openai, "OpenAI", lambda **kwargs: SimpleNamespace(responses=SimpleNamespace(parse=timeout)))
    ids = queue_dataset(db, dataset_row)
    db.commit()
    services = EvaluationServices(ids[0], claim(kinds=["evaluation-graph"]))
    for _ in range(2):
        with pytest.raises(CapabilityError) as error:
            services.stage("joint", {})
        assert error.value.code == "call_replay_required"
    assert dispatched == [True]
    db.expire_all()
    assert db.scalar(select(ModelCall).where(ModelCall.execution_id == ids[0])).state == "uncertain"


def test_export_expiry_scrubs_annotations_then_deletes_owned_files(client, db, monkeypatch, admin_headers, tmp_path):
    dataset_row, _, _ = dataset(client, db, monkeypatch, admin_headers)
    fake_models(monkeypatch)
    from bouquetbrowse import evaluation, worker
    from bouquetbrowse.evaluation import expire_research, export_dataset, queue_dataset

    ids = queue_dataset(db, dataset_row)
    db.commit()
    invoke_graph(
        evaluation_graph(EvaluationServices(ids[0], claim(kinds=["evaluation-graph"])), InMemorySaver()), ids[0]
    )
    db.expire_all()
    monkeypatch.setattr(evaluation, "ROOT", tmp_path)
    path = export_dataset(db, dataset_row)
    dataset_row.retention_until = utcnow()
    expire_research(db)
    db.commit()
    assert path.exists()  # File removal is a separately retryable command after evidence suppression.
    assert worker.run_once(kinds=["delete-evaluation-exports"])
    assert not path.exists()
    db.expire_all()
    item = db.scalar(select(EvaluationItem).where(EvaluationItem.dataset_id == dataset_row.id))
    assert item.labels is None and item.history == []


def test_missing_key_and_stale_annotations_are_explicit(client, db, monkeypatch, admin_headers, tester_headers):
    dataset_row, item, _ = dataset(client, db, monkeypatch, admin_headers)
    monkeypatch.setattr(config, "get_settings", lambda: Settings(_env_file=None, openai_api_key=""))
    response = client.post(
        f"/v1/admin/evaluations/{dataset_row.id}/run",
        json={"expected_version": dataset_row.version},
        headers={**admin_headers, "Idempotency-Key": "missing-key"},
    )
    assert response.status_code == 409
    assert "model_not_configured" in response.text
    assert client.get(f"/v1/admin/evaluations/{dataset_row.id}", headers=tester_headers).status_code == 403
    item.retention_until = utcnow()
    db.flush()
    with pytest.raises(Exception, match="expired"):
        checked_item(db, item)


def test_crop_vectors_use_region_bytes_and_reject_changed_association(db, monkeypatch):
    offer, asset = source(db, monkeypatch)
    association = db.scalar(
        select(OfferAssociation).where(OfferAssociation.offer_id == offer.id, OfferAssociation.media_id == asset.id)
    )
    association.region, association.basis, association.state = [0, 0, 0.5, 1], "reviewed_region", "accepted"
    revision = "a" * 40
    job = enqueue_crop(db, association, revision)
    db.commit()
    observed = []

    def encoder(content, pinned):
        import io

        from PIL import Image

        observed.append((Image.open(io.BytesIO(content)).size, pinned))
        return [1.0] + [0.0] * 767, f"{MODEL}@{pinned}"

    from bouquetbrowse.db import SessionLocal

    prepared = prepare(SessionLocal, job.payload, encoder)
    assert observed == [((400, 600), revision)]
    commit(db, job.payload, prepared)
    db.flush()
    assert db.scalar(select(CropEmbedding))
    listing = db.get(Listing, offer.listing_id)
    from bouquetbrowse.models import ListingRevision

    accepted = db.scalar(select(ListingRevision).where(ListingRevision.listing_id == listing.id))
    listing.current_revision_id = accepted.id
    accepted.snapshot = {**accepted.snapshot, "media_ids": [asset.id], "media_regions": {asset.id: association.region}}
    listing.attributes = {**listing.attributes, "offer_id": offer.id}
    assert selected_image_vectors(db, [listing])[listing.id][0].model_version == f"{MODEL}@{revision}"
    association.region = [0.5, 0, 1, 1]
    with pytest.raises(Exception, match="changed"):
        commit(db, job.payload, prepared)
    asset.state = "removed"
    assert selected_image_vectors(db, [listing]) == {}
