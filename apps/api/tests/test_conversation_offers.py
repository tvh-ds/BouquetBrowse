"""Synthetic conversations exercise ownership, target binding and durable offer commits."""

from datetime import timedelta

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from sqlalchemy import func, select

from bouquetbrowse.conversation_contracts import CaptureEnvelope, MessageObservation, QuoteReference
from bouquetbrowse.conversation_models import OfferClaim, OfferOccurrence
from bouquetbrowse.conversations import record_capture
from bouquetbrowse.db import utcnow
from bouquetbrowse.graphs import invoke_graph, offer_graph
from bouquetbrowse.leases import claim
from bouquetbrowse.models import Listing, MediaAsset, PostVersion, PriceObservation, SourceAccount, SourcePost
from bouquetbrowse.offer_contracts import OfferField, OfferInterpretation
from bouquetbrowse.offer_models import OfferAnalysis
from bouquetbrowse.offer_runtime import OfferServices
from bouquetbrowse.offers import evidence_bundle, segment_capture, validate_interpretation
from bouquetbrowse.providers import CapabilityError
from bouquetbrowse.runtime_models import GraphExecution

POLICY = {"processing_allowed": True, "display_allowed": True, "policy_ref": "fictional-tests"}
CONFIG = {"extraction_model": "fictional-model", "taxonomy_version": "flowers-v2"}


def message(key, username, text, parent=None, image=False, date=True):
    return MessageObservation(
        platform_id=key,
        username=username,
        text=text,
        url=f"https://www.threads.com/@{username}/post/{key}",
        reply_to=parent,
        media_urls=[f"https://scontent.cdninstagram.com/{key}.jpg"] if image else [],
        published_at=utcnow() - timedelta(days=1) if date else None,
    )


def capture(db, messages):
    result = record_capture(
        db,
        CaptureEnvelope(source_url=messages[0].url, messages=messages, stop_reason="partial", remaining_expansions=3),
        POLICY,
    )
    db.flush()
    segment_capture(db, result.id, CONFIG)
    db.flush()
    return result


def offer_for(db, key):
    return db.scalar(
        select(OfferOccurrence)
        .join(SourcePost, SourcePost.id == OfferOccurrence.anchor_id)
        .where(SourcePost.platform_post_id == key)
    )


def reference(db, key, quote):
    version = db.scalar(
        select(PostVersion)
        .join(SourcePost, SourcePost.id == PostVersion.post_id)
        .where(SourcePost.platform_post_id == key)
        .order_by(PostVersion.created_at.desc())
        .limit(1)
    )
    return QuoteReference(version_id=version.id, quote=quote)


def interpretation(db, key, quote="Bên em nhận đặt bó hoa, giao Hà Nội"):
    ref = reference(db, key, quote)
    return OfferInterpretation(seller_offer=True, ownership=ref, location=ref, multi_product=False)


def test_buyer_request_separate_seller_offers_and_prices(db):
    capture(
        db,
        [
            message("buyer", "fictional_buyer", "Tìm shop bó hoa Hà Nội ngân sách 500k", image=True),
            message("offerA", "fictional_a", "Bên em nhận đặt bó hoa, giao Hà Nội. 550k", "buyer", True),
            message("offerB", "fictional_b", "Bên em nhận đặt bó hoa, giao Hà Nội. 650k", "buyer", True),
        ],
    )
    a, b, buyer = [offer_for(db, key) for key in ["offerA", "offerB", "buyer"]]
    assert a.id != b.id
    assert validate_interpretation(db, a, interpretation(db, "offerA"))["prices"][0]["amount_min"] == 550000
    assert validate_interpretation(db, b, interpretation(db, "offerB"))["prices"][0]["amount_min"] == 650000
    proposed = OfferInterpretation(
        seller_offer=True,
        ownership=reference(db, "buyer", "shop"),
        location=reference(db, "buyer", "shop bó hoa Hà Nội"),
        multi_product=False,
    )
    assert "seller_ownership_unresolved" in validate_interpretation(db, buyer, proposed)["errors"]
    assert db.scalar(select(func.count()).select_from(Listing)) == 0
    assert not any(account.seller_id for account in db.scalars(select(SourceAccount)))


def test_seller_price_reply_binds_to_ancestor_not_other_seller(db):
    capture(
        db,
        [
            message("root", "fictional_a", "Bên em nhận đặt bó hoa, giao Hà Nội", image=True),
            message("q", "fictional_buyer", "Giá bao nhiêu?", "root"),
            message("answer", "fictional_a", "650k", "q"),
            message("competitor", "fictional_b", "450k", "q"),
        ],
    )
    result = validate_interpretation(db, offer_for(db, "root"), interpretation(db, "root"))
    assert [p["amount_min"] for p in result["prices"]] == [650000]
    assert not result["errors"]


def test_confirmation_keeps_both_versions_and_rejects_compound_question(db):
    capture(
        db,
        [
            message("root", "fictional_a", "Bên em nhận đặt bó hoa, giao Hà Nội", image=True),
            message("q", "fictional_buyer", "Bó này 20 roses?", "root"),
            message("answer", "fictional_a", "Yes!", "q"),
        ],
    )
    result = interpretation(db, "root")
    result.fields = [
        OfferField(
            field="flower_count",
            flower="rose",
            value=20,
            derivation="seller_confirmation",
            evidence=[reference(db, "q", "20 roses?"), reference(db, "answer", "Yes!")],
        )
    ]
    validated = validate_interpretation(db, offer_for(db, "root"), result)
    assert len(validated["claims"][0]["evidence"]) == 2
    assert validated["claims"][0]["derivation"] == "seller_confirmation"
    capture(db, [message("q", "fictional_buyer", "20 roses và giao ngày mai?", "root")])
    # Segmentation from the root is required to incorporate a changed descendant.
    root = db.get(SourcePost, offer_for(db, "root").anchor_id)
    capture(db, [message("root", "fictional_a", "Bên em nhận đặt bó hoa, giao Hà Nội", image=True)])
    assert root
    result.ownership = interpretation(db, "root").ownership
    result.location = interpretation(db, "root").location
    result.fields[0].evidence[0] = reference(db, "q", "20 roses")
    with pytest.raises(ValueError, match="Ambiguous"):
        validate_interpretation(db, offer_for(db, "root"), result)


def test_wrong_author_quote_and_negated_claim_are_rejected(db):
    capture(
        db,
        [
            message("root", "fictional_a", "Bên em nhận đặt bó hoa, giao Hà Nội. Không có 20 roses", image=True),
            message("q", "fictional_buyer", "20 roses", "root"),
        ],
    )
    result = interpretation(db, "root")
    result.fields = [OfferField(field="stem_count", value=20, evidence=[reference(db, "q", "20 roses")])]
    with pytest.raises(ValueError, match="authored"):
        validate_interpretation(db, offer_for(db, "root"), result)
    result.fields[0].evidence = [reference(db, "root", "20 roses")]
    with pytest.raises(ValueError, match="Negated"):
        validate_interpretation(db, offer_for(db, "root"), result)


def test_missing_date_never_becomes_observation_time(db):
    capture(db, [message("root", "fictional_a", "Bên em nhận đặt bó hoa, giao Hà Nội. 650k", image=True, date=False)])
    output = validate_interpretation(db, offer_for(db, "root"), interpretation(db, "root"))
    assert output["prices"][0]["advertised_at"] is None


def test_independent_offer_graph_commit_replay_and_identity(db):
    capture(db, [message("root", "fictional_a", "Bên em nhận đặt bó hoa, giao Hà Nội. 650k", image=True)])
    offer = offer_for(db, "root")
    offer_id = offer.id
    for asset in db.scalars(select(MediaAsset)):
        asset.state, asset.storage_key = "ready", "fictional.jpg"
    execution = db.scalar(select(GraphExecution).where(GraphExecution.offer_id == offer.id))
    db.commit()
    lease = claim(kinds=["offer-graph"])
    calls = []

    def fake(bundle, config):
        calls.append(bundle["offer_id"])
        return interpretation(db, "root")

    graph = offer_graph(OfferServices(execution.id, lease, fake), InMemorySaver())
    invoke_graph(graph, execution.id)
    invoke_graph(graph, execution.id)
    db.expire_all()
    assert calls == [offer_id]
    listing_id = db.get(OfferOccurrence, offer_id).listing_id
    assert listing_id and db.get(Listing, listing_id).state == "review"
    assert db.scalar(select(func.count()).select_from(PriceObservation)) == 1
    assert db.scalar(select(OfferAnalysis)).revision_id
    assert db.scalar(select(func.count()).select_from(OfferClaim)) == 0
    # A later model correction cannot change this occurrence's identity or listing URL.
    capture(db, [message("root", "fictional_a", "Bên em nhận đặt bó hoa, giao Hà Nội. 750k", image=True)])
    assert offer_for(db, "root").id == offer_id
    assert offer_for(db, "root").listing_id == listing_id
    db.commit()
    with pytest.raises(CapabilityError, match="earlier|no longer active"):
        OfferServices(execution.id, lease, fake).stage("commit", {"execution_id": execution.id})


def test_collage_and_unresolved_location_require_review(db):
    capture(db, [message("root", "fictional_a", "Bên em nhận đặt bó hoa", image=True)])
    result = OfferInterpretation(
        seller_offer=True, ownership=reference(db, "root", "Bên em nhận đặt bó hoa"), location=None, multi_product=True
    )
    errors = validate_interpretation(db, offer_for(db, "root"), result)["errors"]
    assert "hanoi_service_unresolved" in errors and "multi_product_review" in errors
    assert evidence_bundle(db, offer_for(db, "root"))["media"][0]["role"] == "seller_image"


def test_conversation_admin_is_private(client, tester_headers, admin_headers):
    assert client.get("/v1/admin/conversations", headers=tester_headers).status_code == 403
    assert client.get("/v1/admin/conversations", headers=admin_headers).status_code == 200


def test_repeated_capture_reuses_offer_execution(db):
    observed = message("same", "fictional_a", "Bên em nhận đặt bó hoa, giao Hà Nội", image=True)
    capture(db, [observed])
    first = offer_for(db, "same")
    fingerprint = first.input_fingerprint
    capture(db, [observed])
    assert offer_for(db, "same").input_fingerprint == fingerprint
    assert len(list(db.scalars(select(GraphExecution).where(GraphExecution.offer_id == first.id)))) == 1


def test_reply_only_capture_invalidates_known_ancestor_offer(db):
    capture(db, [message("root", "fictional_a", "Bên em nhận đặt bó hoa, giao Hà Nội", image=True)])
    offer = offer_for(db, "root")
    previous = offer.input_fingerprint
    capture(db, [message("late-price", "fictional_a", "650k", "root")])
    assert offer_for(db, "root").input_fingerprint != previous
    assert validate_interpretation(db, offer, interpretation(db, "root"))["prices"][0]["amount_min"] == 650000
