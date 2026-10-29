"""One evidence visibility policy for catalog, detail, media, analytics and digest reads."""

from sqlalchemy import select

from .conversation_models import OfferOccurrence
from .db import aware, utcnow
from .models import Listing, ListingRevision, MediaAsset, PostVersion, SourcePost

VISIBLE_STATES = {"published", "provisional"}


def visible(db, listing):
    if not listing or listing.state not in VISIBLE_STATES:
        return False
    if listing.is_demo:
        return True
    offer = db.scalar(select(OfferOccurrence).where(OfferOccurrence.listing_id == listing.id))
    if not offer:
        return True  # Existing operator-reviewed catalog keeps its original contract.
    revision = db.get(ListingRevision, listing.current_revision_id) if listing.current_revision_id else None
    if not revision or not revision.snapshot.get("evidence_versions"):
        from .conversation_models import OfferAssociation
        from .models import ListingSource

        legacy = db.scalar(
            select(OfferAssociation.id).where(
                OfferAssociation.offer_id == offer.id,
                OfferAssociation.role == "legacy_source",
                OfferAssociation.basis == "operator_import",
            )
        )
        if not legacy:
            return False
        versions = list(
            db.scalars(
                select(PostVersion)
                .join(ListingSource, ListingSource.version_id == PostVersion.id)
                .where(ListingSource.listing_id == listing.id)
            )
        )
        return bool(versions) and all(
            aware(v.retention_until) > utcnow() and db.get(SourcePost, v.post_id).access_state != "removed"
            for v in versions
        )
    for version_id in revision.snapshot["evidence_versions"]:
        version = db.get(PostVersion, version_id)
        post = db.get(SourcePost, version.post_id) if version else None
        if not version or aware(version.retention_until) <= utcnow() or not post or post.access_state == "removed":
            return False
    return True


def visible_listings(db):
    return [
        listing
        for listing in db.scalars(select(Listing).where(Listing.state.in_(VISIBLE_STATES)))
        if visible(db, listing)
    ]


def visible_media(db, media_id):
    asset = db.get(MediaAsset, media_id)
    if (
        not asset
        or asset.state != "ready"
        or not asset.storage_key
        or asset.retention_until
        and aware(asset.retention_until) <= utcnow()
    ):
        return False
    for listing in visible_listings(db):
        revision = db.get(ListingRevision, listing.current_revision_id) if listing.current_revision_id else None
        media_ids = revision.snapshot.get("media_ids", []) if revision else []
        cropped = bool(revision and revision.snapshot.get("media_regions", {}).get(media_id))
        if not cropped and (media_id in media_ids or listing.image_path == f"/api/v1/media/{media_id}"):
            return True
    return False


def public_composition(listing):
    return [
        {
            key: component.get(key)
            for key in ["flower", "status", "stated_count", "alternatives", "review_state", "supported", "visual_state"]
        }
        for component in listing.attributes.get("composition", [])
    ]


def flower_types(listing):
    components = listing.attributes.get("composition", [])
    if components:
        return {
            c["flower"]
            for c in components
            if c.get("status") not in {"unknown", "conflict"}
            and c.get("review_state") != "rejected"
            and not c.get("alternatives")
            and (
                c.get("status") == "stated" or c.get("supported") or c.get("review_state") in {"accepted", "corrected"}
            )
        }
    return set(
        listing.attributes.get("flower_composition") or ([listing.primary_flower] if listing.primary_flower else [])
    )


def public_attributes(listing):
    allowed = {
        "title_en",
        "flower_composition",
        "warnings",
        "size_reviewed",
        "extraction_reviewed",
        "accepted_availability",
        "updating",
        "composition_reviewed",
        "offer_type",
        "capture_complete",
        "evidence_at",
        "reference_image",
        "image_analysis_complete",
    }
    return {key: value for key, value in listing.attributes.items() if key in allowed}
