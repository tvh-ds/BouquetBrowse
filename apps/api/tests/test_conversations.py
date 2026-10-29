from datetime import timedelta

import pytest
from sqlalchemy import func, select

from bouquetbrowse.conversation_contracts import CaptureEnvelope, MessageObservation, QuoteReference
from bouquetbrowse.conversation_models import (
    CanonicalConfiguration,
    CaptureMember,
    MessageEdge,
    OfferOccurrence,
)
from bouquetbrowse.conversations import anchor_quote, backfill_legacy, ensure_occurrence, link_canonical, record_capture
from bouquetbrowse.db import utcnow
from bouquetbrowse.models import Listing, PostVersion, Seller, SourceAccount, SourcePost

POLICY = {"processing_allowed": True, "policy_ref": "fictional-test-policy"}


def capture(*messages):
    return CaptureEnvelope(
        source_url="https://www.threads.com/@fictional/post/root",
        messages=list(messages),
        stop_reason="time_budget",
        remaining_expansions=3,
    )


def message(key, username="fictional", **kwargs):
    return MessageObservation(
        platform_id=key,
        username=username,
        url=f"https://www.threads.com/@{username}/post/{key}",
        text="🌸 Giá 650k",
        **kwargs,
    )


def test_global_messages_versions_and_capture_subsets(db):
    first = record_capture(db, capture(message("reply", reply_to="root")), POLICY)
    db.commit()
    assert db.scalar(select(func.count()).select_from(Seller)) == 0
    assert db.scalar(select(MessageEdge)).target_id is None
    second = record_capture(db, capture(message("root"), message("reply", reply_to="root")), POLICY)
    db.commit()
    assert db.scalar(select(func.count()).select_from(SourcePost)) == 2
    assert db.scalar(select(func.count()).select_from(PostVersion)) == 2
    assert db.scalar(select(MessageEdge)).target_id is not None
    assert db.scalar(select(func.count()).select_from(CaptureMember).where(CaptureMember.capture_id == first.id)) == 1
    assert db.scalar(select(func.count()).select_from(CaptureMember).where(CaptureMember.capture_id == second.id)) == 2
    assert first.coverage["complete"] is False


def test_immutable_edit_versions_do_not_invent_publication_time(db):
    record_capture(db, capture(message("root")), POLICY)
    edited = message("root").model_copy(update={"text": "Giá 750k"})
    record_capture(db, capture(edited), POLICY)
    db.flush()
    assert db.scalar(select(func.count()).select_from(PostVersion)) == 2
    assert db.scalar(select(SourcePost)).published_at is None


def test_takedown_cannot_be_reversed_by_capture(db):
    record_capture(db, capture(message("root")), POLICY)
    db.scalar(select(SourcePost)).access_state = "removed"
    db.flush()
    with pytest.raises(ValueError, match="suppressed"):
        record_capture(db, capture(message("root")), POLICY)


def test_later_capture_can_supply_a_genuinely_observed_publication_date(db):
    record_capture(db, capture(message("root")), POLICY)
    published = utcnow() - timedelta(days=2)
    record_capture(db, capture(message("root", published_at=published)), POLICY)
    db.flush()
    from bouquetbrowse.db import aware

    assert aware(db.scalar(select(SourcePost)).published_at) == published
    assert db.scalar(select(func.count()).select_from(PostVersion)) == 2


def test_account_identity_conflict_requires_review(db):
    record_capture(db, capture(message("root", platform_account_id="111")), POLICY)
    with pytest.raises(ValueError, match="reassigned"):
        record_capture(db, capture(message("next", platform_account_id="222")), POLICY)


def test_quotes_use_unicode_codepoints_and_reject_repeated_match(db):
    record_capture(db, capture(message("root")), POLICY)
    version = db.scalar(select(PostVersion))
    evidence = anchor_quote(db, QuoteReference(version_id=version.id, quote="650k"))
    assert evidence["start"] == len("🌸 Giá ")
    version.caption = "650k hoặc 650k"
    with pytest.raises(ValueError, match="unambiguous"):
        anchor_quote(db, QuoteReference(version_id=version.id, quote="650k"))
    assert anchor_quote(db, QuoteReference(version_id=version.id, quote="650k", before="hoặc "))["start"] == 10
    version.retention_until = utcnow() - timedelta(seconds=1)
    with pytest.raises(ValueError, match="unavailable"):
        anchor_quote(db, QuoteReference(version_id=version.id, quote="650k"))


def test_offer_identity_does_not_depend_on_recognition_and_reposts_stay_distinct(db):
    record_capture(db, capture(message("root"), message("repost")), POLICY)
    account = db.scalar(select(SourceAccount))
    posts = list(db.scalars(select(SourcePost)))
    first = ensure_occurrence(db, account.id, posts[0].id)
    second = ensure_occurrence(db, account.id, posts[1].id)
    assert first.id != second.id
    assert ensure_occurrence(db, account.id, posts[0].id).id == first.id


def test_canonical_links_never_cross_sellers_or_use_similarity(db):
    record_capture(db, capture(message("root")), POLICY)
    seller = Seller(name="Fictional A", slug="fictional-a", district="Unknown")
    other = Seller(name="Fictional B", slug="fictional-b", district="Unknown")
    db.add_all([seller, other])
    db.flush()
    account, post = db.scalar(select(SourceAccount)), db.scalar(select(SourcePost))
    account.seller_id = seller.id
    offer = ensure_occurrence(db, account.id, post.id)
    configuration = CanonicalConfiguration(seller_id=other.id, evidence={"review": "test"})
    db.add(configuration)
    db.flush()
    with pytest.raises(ValueError, match="one seller"):
        link_canonical(db, offer.id, configuration.id, "reviewed_match", {"review": "test"})
    configuration.seller_id = seller.id
    with pytest.raises(ValueError, match="Similarity"):
        link_canonical(db, offer.id, configuration.id, "image_similarity", {"score": 0.99})


def test_legacy_backfill_keeps_listing_ids_and_is_idempotent(seeded):
    ids = set(seeded.scalars(select(Listing.id)))
    backfill_legacy(seeded)
    seeded.flush()
    count = seeded.scalar(select(func.count()).select_from(OfferOccurrence))
    backfill_legacy(seeded)
    seeded.flush()
    assert seeded.scalar(select(func.count()).select_from(OfferOccurrence)) == count
    assert ids == set(seeded.scalars(select(Listing.id)))
    assert count > 0


def test_capture_requires_processing_policy(db):
    with pytest.raises(ValueError, match="policy"):
        record_capture(db, capture(message("root")), {})
