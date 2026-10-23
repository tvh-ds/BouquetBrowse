from datetime import timedelta

import pytest
from sqlalchemy import func, select

from bouquetbrowse.db import utcnow
from bouquetbrowse.models import FieldAssertion, Listing, PriceObservation, SourcePost
from bouquetbrowse.pipeline import ingest, process_extraction, review_listing
from bouquetbrowse.schemas import ImportPost, ReviewDecision


def imported(post_id="test-1", username="test.florist", slug="test-florist", caption=None):
    return ImportPost(
        platform="operator",
        platform_post_id=post_id,
        username=username,
        seller_name="Fictional test seller",
        seller_slug=slug,
        district="Ba Đình",
        published_at=utcnow() - timedelta(days=1),
        caption=caption or "Bó hoa hồng màu hồng, 20 cành. Giá 650k. Đặt trước 2 ngày. Có giao hàng. Phí ship 30k.",
        rights_confirmed=True,
    )


def test_ingestion_is_idempotent(db):
    a = ingest(db, imported())
    b = ingest(db, imported())
    db.commit()
    assert a["version_id"] == b["version_id"]
    assert b["duplicate"]
    assert db.scalar(select(func.count()).select_from(SourcePost)) == 1


def test_complete_review_and_publication(db):
    source = ingest(db, imported())
    db.commit()
    result = process_extraction(db, source["version_id"])
    listing = db.get(Listing, result["listing_id"])
    assert listing.state == "review"
    assert listing.image_path is None
    assert (
        db.scalars(select(PriceObservation).where(PriceObservation.listing_id == listing.id)).first().reviewed is False
    )
    review_listing(
        db,
        listing,
        ReviewDecision(decision="accept", reason="Matched caption price, count and configuration."),
        "reviewer",
    )
    db.commit()
    assert listing.state == "published"
    assert listing.current_revision_id
    assert listing.attributes["size_reviewed"] is True
    assert (
        db.scalar(
            select(func.count())
            .select_from(FieldAssertion)
            .where(FieldAssertion.listing_id == listing.id, FieldAssertion.review_state == "pending")
        )
        == 0
    )


def test_identical_captions_from_different_sellers_never_merge(db):
    a = ingest(db, imported())
    b = ingest(db, imported("test-2", "other.florist", "other-florist"))
    db.commit()
    first = process_extraction(db, a["version_id"])
    second = process_extraction(db, b["version_id"])
    db.commit()
    assert first["listing_id"] != second["listing_id"]


def test_multiple_prices_cannot_publish_without_association(db):
    source = ingest(db, imported(caption="Bó hoa hồng màu hồng, 20 cành. Bó A 650k; bó B 850k."))
    result = process_extraction(db, source["version_id"])
    with pytest.raises(ValueError, match="multiple prices"):
        review_listing(
            db,
            db.get(Listing, result["listing_id"]),
            ReviewDecision(decision="accept", reason="Manual review"),
            "reviewer",
        )


def test_corrected_price_requires_source_evidence(db):
    source = ingest(db, imported())
    result = process_extraction(db, source["version_id"])
    listing = db.get(Listing, result["listing_id"])
    with pytest.raises(ValueError, match="matching monetary quote"):
        review_listing(
            db,
            listing,
            ReviewDecision(
                decision="correct", reason="Manual correction", price_minor=900000, price_evidence_quote="650k"
            ),
            "reviewer",
        )


def test_post_cannot_change_seller(db):
    ingest(db, imported())
    with pytest.raises(ValueError, match="reassigned"):
        ingest(db, imported("test-1", "other.seller", "other-seller"))


def test_rights_confirmation_is_explicit(db):
    post = imported()
    post.rights_confirmed = False
    with pytest.raises(ValueError, match="permission"):
        ingest(db, post)
