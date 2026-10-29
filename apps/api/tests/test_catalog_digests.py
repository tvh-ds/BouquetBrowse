from datetime import timedelta

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from sqlalchemy import select
from test_conversation_offers import capture, interpretation, message, offer_for

from bouquetbrowse.catalog import commercial_issues
from bouquetbrowse.catalog_event_models import CatalogChange, DigestMember
from bouquetbrowse.db import utcnow
from bouquetbrowse.digests import HANOI, build_digest, digest_view
from bouquetbrowse.graphs import invoke_graph, offer_graph
from bouquetbrowse.leases import claim
from bouquetbrowse.models import Job, Listing, MediaAsset, PostVersion, PriceObservation
from bouquetbrowse.offer_models import OfferAnalysis
from bouquetbrowse.offer_runtime import OfferServices
from bouquetbrowse.projection import change, project_offer
from bouquetbrowse.runtime_models import GraphExecution
from bouquetbrowse.visibility import visible


def completed_offer(db):
    capture(
        db,
        [
            message("offer", "fictional_seller", "Bên em nhận đặt bó hoa, giao Hà Nội. 650k", image=True),
            message("buyer", "fictional_buyer", "PRIVATE BUYER CONTEXT", "offer"),
        ],
    )
    offer = offer_for(db, "offer")
    for media in db.scalars(select(MediaAsset)):
        media.state, media.storage_key = "ready", "synthetic.jpg"
    execution = db.scalar(select(GraphExecution).where(GraphExecution.offer_id == offer.id))
    db.commit()
    lease = claim(kinds=["offer-graph"])
    invoke_graph(
        offer_graph(OfferServices(execution.id, lease, lambda *args: interpretation(db, "offer")), InMemorySaver()),
        execution.id,
    )
    db.expire_all()
    analysis = db.scalar(select(OfferAnalysis).where(OfferAnalysis.execution_id == execution.id))
    analysis.output = {
        **analysis.output,
        "recognition_completed": True,
        "visual_arrangement": "bouquet",
        "visual_colors": ["pink"],
        "composition": [
            {
                "flower": f,
                "status": "stated",
                "evidence_refs": [],
                "media_refs": [],
                "stated_count": None,
                "alternatives": [],
                "review_state": "pending",
                "supported": True,
            }
            for f in ["rose", "peony"]
        ],
    }
    db.flush()
    return db.get(type(offer), offer.id), db.get(GraphExecution, execution.id), analysis


def test_closed_gate_does_not_publish_validated_fixture(db):
    offer, execution, analysis = completed_offer(db)
    assert not project_offer(db, offer, execution, analysis)
    assert not visible(db, db.get(Listing, offer.listing_id))
    assert not list(db.scalars(select(CatalogChange)))


def test_published_provisional_revision_queues_semantic_index_once(db, monkeypatch):
    from bouquetbrowse.config import Settings
    from bouquetbrowse.models import Job

    offer, execution, analysis = completed_offer(db)
    monkeypatch.setattr("bouquetbrowse.projection.publication_ready", lambda *args: True)
    monkeypatch.setattr(
        "bouquetbrowse.config.get_settings", lambda: Settings(openai_api_key="fictional-test-only", _env_file=None)
    )
    assert project_offer(db, offer, execution, analysis)
    assert project_offer(db, offer, execution, analysis)
    db.flush()
    jobs = list(db.scalars(select(Job).where(Job.kind == "embed-text")))
    assert len(jobs) == 1 and jobs[0].payload["revision_id"] == analysis.revision_id


def test_similarity_uses_selected_offer_media_and_never_a_whole_collage_for_a_crop(db, monkeypatch):
    from bouquetbrowse.catalog import selected_image_vectors
    from bouquetbrowse.models import ImageEmbedding, ListingRevision, PostMedia, SourcePost

    offer, execution, analysis = completed_offer(db)
    monkeypatch.setattr("bouquetbrowse.projection.publication_ready", lambda *args: True)
    project_offer(db, offer, execution, analysis)
    listing = db.get(Listing, offer.listing_id)
    revision = db.get(ListingRevision, listing.current_revision_id)
    own_id = revision.snapshot["media_ids"][0]
    buyer_version = db.scalar(select(PostVersion).join(SourcePost).where(SourcePost.platform_post_id == "buyer"))
    buyer_asset = MediaAsset(state="ready", checksum="b" * 64)
    db.add(buyer_asset)
    db.flush()
    db.add(PostMedia(version_id=buyer_version.id, media_id=buyer_asset.id, position=0))
    for media_id in [own_id, buyer_asset.id]:
        db.add(ImageEmbedding(media_id=media_id, model_version="fictional", vector=[0.1] * 768))
    db.flush()
    assert {v.media_id for v in selected_image_vectors(db, [listing])[listing.id]} == {own_id}
    revision.snapshot = {**revision.snapshot, "media_regions": {own_id: [0, 0, 0.5, 1]}}
    assert listing.id not in selected_image_vectors(db, [listing])


def test_provisional_browsing_history_composition_and_buyer_privacy(db, client, tester_headers, monkeypatch):
    offer, execution, analysis = completed_offer(db)
    monkeypatch.setattr("bouquetbrowse.projection.publication_ready", lambda *args: True)
    assert project_offer(db, offer, execution, analysis)
    db.commit()
    response = client.get(f"/v1/listings/{offer.listing_id}", headers=tester_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["state"] == "provisional" and body["price"]["amount_min"] == 650000
    assert body["price"]["reviewed"] is False and body["capture_complete"] is False
    assert "PRIVATE BUYER CONTEXT" not in response.text
    assert "offer_id" not in body["attributes"]
    matched = client.get("/v1/catalog?flower=rose,peony&flower_mode=all", headers=tester_headers).json()
    assert matched["total"] == 1
    assert offer.listing_id not in {
        item["id"] for item in client.get("/v1/catalog?reviewed_only=true", headers=tester_headers).json()["items"]
    }
    history = client.get(f"/v1/listings/{offer.listing_id}/price-history", headers=tester_headers).json()
    assert len(history["items"]) == 1 and history["items"][0]["reviewed"] is False
    assert commercial_issues(db, db.get(Listing, offer.listing_id))


def test_updating_keeps_accepted_price_and_expired_evidence_hides_every_view(db, client, tester_headers, monkeypatch):
    offer, execution, analysis = completed_offer(db)
    monkeypatch.setattr("bouquetbrowse.projection.publication_ready", lambda *args: True)
    project_offer(db, offer, execution, analysis)
    listing = db.get(Listing, offer.listing_id)
    listing.attributes = {**listing.attributes, "updating": True}
    price = db.scalar(select(PriceObservation).where(PriceObservation.listing_id == listing.id))
    db.add(
        PriceObservation(
            listing_id=listing.id,
            version_id=price.version_id,
            amount_min=999000,
            amount_max=999000,
            currency="VND",
            kind="exact",
            component="bouquet",
            evidence={},
            reviewed=False,
            advertised_at=utcnow(),
        )
    )
    db.commit()
    assert client.get(f"/v1/listings/{listing.id}", headers=tester_headers).json()["price"]["amount_min"] == 650000
    assert len(client.get(f"/v1/listings/{listing.id}/price-history", headers=tester_headers).json()["items"]) == 1
    assert "New evidence is being processed" in commercial_issues(db, listing)
    for version in db.scalars(select(PostVersion)):
        version.retention_until = utcnow() - timedelta(seconds=1)
    db.commit()
    assert client.get(f"/v1/listings/{listing.id}", headers=tester_headers).status_code == 404
    assert listing.id not in {item["id"] for item in client.get("/v1/catalog", headers=tester_headers).json()["items"]}
    assert client.get(f"/v1/listings/{listing.id}/price-history", headers=tester_headers).status_code == 404


def test_tentative_alternatives_never_become_definite_filter_matches(db, client, tester_headers, monkeypatch):
    offer, execution, analysis = completed_offer(db)
    monkeypatch.setattr("bouquetbrowse.projection.publication_ready", lambda *args: True)
    analysis.output = {
        **analysis.output,
        "composition": [
            {
                "flower": "peony",
                "status": "visual_inference",
                "alternatives": ["lisianthus"],
                "review_state": "pending",
                "supported": False,
                "stated_count": None,
            }
        ],
    }
    project_offer(db, offer, execution, analysis)
    db.commit()
    assert client.get("/v1/catalog?flower=peony", headers=tester_headers).json()["total"] == 0
    assert "peony" not in client.get("/v1/catalog/facets", headers=tester_headers).json()["flowers"]


def test_digest_is_idempotent_partial_and_late_events_wait(db):
    now = utcnow()
    day = now.astimezone(HANOI).date()
    first = change(db, "fictional-first", "source_access", details={"state": "unavailable"})
    db.flush()
    first.created_at = now - timedelta(seconds=1)
    digest = build_digest(db, day, {"scheduled": 5, "completed": 2, "missed": 3}, now=now)
    db.flush()
    assert digest.partial
    assert len(digest_view(db, digest)["items"]) == 1
    late = change(db, "fictional-late", "source_access", details={"state": "accessible"})
    db.flush()
    late.created_at = now + timedelta(seconds=1)
    assert build_digest(db, day, now=now + timedelta(seconds=2)).id == digest.id
    assert len(digest_view(db, digest)["items"]) == 1
    next_digest = build_digest(db, day + timedelta(days=1), now=now + timedelta(days=1, seconds=2))
    db.flush()
    assert [item["id"] for item in digest_view(db, next_digest)["items"]] == [late.id]
    assert len(list(db.scalars(select(DigestMember)))) == 2
    first.suppressed = True
    assert not digest_view(db, digest)["items"]


def test_digest_and_model_admin_routes_enforce_roles(client, tester_headers):
    assert client.get("/v1/digests", headers=tester_headers).status_code == 200
    assert client.get("/v1/admin/model-calls", headers=tester_headers).status_code == 403
    assert client.get("/v1/admin/media/unknown", headers=tester_headers).status_code == 403


def test_execution_cannot_borrow_another_job_lease(db):
    offer, execution, analysis = completed_offer(db)
    from bouquetbrowse.pipeline import enqueue
    from bouquetbrowse.providers import CapabilityError

    job = enqueue(db, "extract", {}, "other-lease")
    db.get(Job, execution.job_id).state = "succeeded"
    db.commit()
    lease = claim(kinds=["extract"])
    assert lease.job_id == job.id
    with pytest.raises(CapabilityError, match="own this execution"):
        OfferServices(execution.id, lease).stage("commit", {})


def test_reviewed_region_binds_price_and_serves_only_approved_crop(db, client, tester_headers, monkeypatch):
    import io

    from PIL import Image
    from test_conversation_offers import reference

    from bouquetbrowse.offers import validate_interpretation
    from bouquetbrowse.recognition_models import ImageRegion
    from bouquetbrowse.region_review import RegionDecision, split_region

    original, _, _ = completed_offer(db)
    from bouquetbrowse.offers import current_associations

    asset = db.get(MediaAsset, next(a.media_id for a in current_associations(db, original) if a.media_id))
    asset.checksum = "a" * 64
    region = ImageRegion(
        media_id=asset.id,
        checksum=asset.checksum,
        region_key="b" * 64,
        bounds=[0, 0, 0.5, 1],
        kind="product",
        state="proposed",
        evidence={},
        retention_until=utcnow() + timedelta(days=30),
    )
    db.add(region)
    db.flush()
    split = split_region(
        db,
        original,
        region.id,
        RegionDecision(expected_fingerprint=original.input_fingerprint, price_target=reference(db, "offer", "650k")),
        "fictional-reviewer",
        "fictional-region-command",
    )
    from bouquetbrowse.conversation_models import OfferOccurrence

    crop_offer = db.get(OfferOccurrence, split["offer_id"])
    proposal = interpretation(db, "offer")
    proposal.multi_product = True
    validated = validate_interpretation(db, crop_offer, proposal)
    assert not validated["errors"] and validated["prices"][0]["amount_min"] == 650000
    assert db.scalar(select(Listing).where(Listing.id == original.listing_id)).state == "review"
    db.commit()
    execution = db.get(GraphExecution, split["execution_id"])
    lease = claim(kinds=["offer-graph"])
    invoke_graph(offer_graph(OfferServices(execution.id, lease, lambda *args: proposal), InMemorySaver()), execution.id)
    db.expire_all()
    crop_offer = db.get(OfferOccurrence, crop_offer.id)
    analysis = db.scalar(select(OfferAnalysis).where(OfferAnalysis.execution_id == execution.id))
    analysis.output = {**analysis.output, "recognition_completed": True}
    monkeypatch.setattr("bouquetbrowse.projection.publication_ready", lambda *args: True)
    project_offer(db, crop_offer, execution, analysis)
    db.commit()
    output = io.BytesIO()
    Image.new("RGB", (800, 600), "pink").save(output, "JPEG")
    monkeypatch.setattr("bouquetbrowse.storage.get_media_bytes", lambda key: output.getvalue())
    assert client.get(f"/v1/media/{asset.id}", headers=tester_headers).status_code == 404
    response = client.get(f"/v1/listings/{crop_offer.listing_id}/image", headers=tester_headers)
    assert response.status_code == 200
    with Image.open(io.BytesIO(response.content)) as cropped:
        assert cropped.size == (400, 600)
