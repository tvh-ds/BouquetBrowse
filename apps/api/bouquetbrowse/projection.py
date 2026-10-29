"""Project complete, validated offer revisions into the attributable catalog."""

from datetime import timedelta

from sqlalchemy import select

from .catalog_event_models import CatalogChange, SellerFact
from .conversation_models import ConversationCapture, OfferClaim
from .db import aware, utcnow
from .extraction import fold
from .models import Listing, ListingRevision, MediaAsset, PostVersion, PriceObservation, SourcePost
from .offers import current_associations, evidence_bundle, offer_fingerprint
from .pipeline import digest, title_for
from .publication_gates import publication_ready


def change(db, key, kind, listing_id=None, seller_id=None, source_url=None, advertised_at=None, details=None):
    from .discovery import dialect_insert

    db.execute(
        dialect_insert(db)(CatalogChange)
        .values(
            event_key=key,
            kind=kind,
            listing_id=listing_id,
            seller_id=seller_id,
            source_url=source_url,
            advertised_at=advertised_at,
            details=details or {},
        )
        .on_conflict_do_nothing(index_elements=["event_key"])
    )
    return db.scalar(select(CatalogChange).where(CatalogChange.event_key == key))


def seller_fact(db, offer, field, value, evidence):
    key = digest(evidence)
    existing = db.scalar(
        select(SellerFact.id).where(
            SellerFact.seller_id == offer.seller_id, SellerFact.field == field, SellerFact.evidence_key == key
        )
    )
    if existing:
        return
    version = db.get(PostVersion, evidence["version_id"])
    db.add(
        SellerFact(
            seller_id=offer.seller_id,
            field=field,
            value={"value": value},
            evidence_key=key,
            evidence=evidence,
            retention_until=version.retention_until,
        )
    )
    source = db.get(SourcePost, version.post_id)
    change(
        db,
        f"seller:{offer.seller_id}:{field}:{key}",
        "seller_update",
        seller_id=offer.seller_id,
        source_url=source.url,
        advertised_at=source.published_at,
        details={"field": field, "value": value},
    )


def project_offer(db, offer, execution, analysis):
    if not publication_ready(db, execution.configuration):
        return False
    if (
        not analysis.revision_id
        or analysis.fingerprint != offer.input_fingerprint
        or offer_fingerprint(db, offer) != analysis.fingerprint
    ):
        return False
    evidence_bundle(db, offer)
    output = analysis.output
    if output.get("errors") or not output.get("recognition_completed"):
        return False
    listing = db.get(Listing, offer.listing_id)
    if not listing or listing.state in {"withdrawn", "rejected"}:
        return False
    anchor = db.get(SourcePost, offer.anchor_id)
    if (
        not anchor.published_at
        or aware(anchor.published_at) < utcnow() - timedelta(days=30)
        or aware(anchor.published_at) > utcnow() + timedelta(minutes=5)
    ):
        return False
    refs = current_associations(db, offer)
    captures = [db.get(ConversationCapture, a.evidence.get("capture_id")) for a in refs if a.evidence.get("capture_id")]
    if not captures or any(not c.acquisition.get("display_allowed") for c in captures):
        return False
    image_refs = [a for a in refs if a.media_id and a.role in {"seller_image", "reference_image"}]
    assets = [db.get(MediaAsset, a.media_id) for a in image_refs]
    if not assets or any(not a or a.state != "ready" or not a.storage_key for a in assets):
        return False
    revision = db.get(ListingRevision, analysis.revision_id)
    if listing.current_revision_id == revision.id:
        return True
    initial = listing.current_revision_id is None
    old_prices = list(listing.attributes.get("accepted_price_ids", []))
    fields = dict(revision.snapshot["fields"])
    composition = output.get("composition", [])
    supported = sorted(
        {
            c["flower"]
            for c in composition
            if c.get("status") not in {"unknown", "conflict"}
            and not c.get("alternatives")
            and (
                c.get("status") == "stated" or c.get("supported") or c.get("review_state") in {"accepted", "corrected"}
            )
        }
    )
    fields["primary_flower"] = "mixed" if len(supported) > 1 else next(iter(supported), None)
    fields.setdefault("arrangement", output.get("visual_arrangement"))
    fields.setdefault("color", next(iter(output.get("visual_colors", [])), None))
    for key in ["primary_flower", "color", "arrangement", "stem_count"]:
        setattr(listing, key, fields.get(key))
    listing.title = title_for(fields)
    listing.description = (
        listing.title
        + ". "
        + ("Thành phần: " + ", ".join(supported) + ". " if supported else "")
        + "Thông tin từ quảng cáo; liên hệ người bán để xác nhận."
    )
    listing.image_path = (
        f"/api/v1/listings/{listing.id}/image" if image_refs[0].region else f"/api/v1/media/{assets[0].id}"
    )
    prices = list(
        db.scalars(
            select(PriceObservation)
            .where(
                PriceObservation.listing_id == listing.id,
                PriceObservation.version_id.in_([a.version_id for a in refs]),
                PriceObservation.component == "bouquet",
                PriceObservation.superseded.is_(False),
            )
            .order_by(PriceObservation.advertised_at.desc(), PriceObservation.created_at.desc())
        )
    )
    valid_prices = [
        p
        for p in prices
        if any(
            p.version_id == claim["version_id"]
            and p.amount_min == claim["amount_min"]
            and p.amount_max == claim["amount_max"]
            for claim in output.get("prices", [])
        )
    ]
    price_ids = [p.id for p in valid_prices]
    reviewed = bool(output.get("commercial_reviewed"))
    if reviewed:
        for price in valid_prices:
            price.reviewed = True
    listing.state = "published" if reviewed else "provisional"
    listing.attributes = {
        **listing.attributes,
        "updating": False,
        "composition": composition,
        "flower_composition": supported,
        "extraction_reviewed": reviewed,
        "composition_reviewed": bool(output.get("composition_reviewed")),
        "offer_type": offer.kind,
        "capture_complete": all(c.coverage.get("complete") for c in captures),
        "evidence_at": utcnow().isoformat(),
        "reference_image": offer.kind == "recreation_quote",
        "image_analysis_complete": True,
        "accepted_price_ids": price_ids,
        "accepted_availability": {
            "status": "unknown",
            "lead_days": next((c["value"]["value"] for c in output["claims"] if c["field"] == "lead_days"), None),
            "delivery": next((c["value"]["value"] for c in output["claims"] if c["field"] == "delivery"), None),
        },
        "warnings": sorted(
            set(
                (["Partial conversation capture."] if not all(c.coverage.get("complete") for c in captures) else [])
                + (
                    [f"{len(output['unprocessed_media'])} media items were not analyzed."]
                    if output.get("unprocessed_media")
                    else []
                )
            )
        ),
    }
    listing.search_text = fold(
        " ".join([listing.title, listing.description, *supported, listing.arrangement or "", listing.color or ""])
    )
    revision.snapshot = {
        **revision.snapshot,
        "published": True,
        "evidence_versions": sorted({a.version_id for a in refs}),
        "media_ids": [a.id for a in assets],
        "media_regions": {a.media_id: a.region for a in image_refs if a.region},
        "price_ids": price_ids,
        "composition": composition,
        "fields": fields,
        "title": listing.title,
        "description": listing.description,
    }
    listing.current_revision_id, offer.state = revision.id, "published"
    if initial:
        change(db, f"new:{offer.id}", "new_offer", listing.id, offer.seller_id, anchor.url, anchor.published_at)
    elif price_ids != old_prices and valid_prices:
        previous = db.get(PriceObservation, old_prices[0]) if old_prices else None
        current = valid_prices[0]
        if not previous or (previous.amount_min, previous.amount_max, previous.currency) != (
            current.amount_min,
            current.amount_max,
            current.currency,
        ):
            change(
                db,
                f"price:{revision.id}:{current.id}",
                "advertised_price_update",
                listing.id,
                offer.seller_id,
                anchor.url,
                current.advertised_at,
                {"amount_min": current.amount_min, "currency": current.currency, "reviewed": current.reviewed},
            )
    if output.get("location"):
        seller_fact(db, offer, "service_area", "Hanoi", output["location"])
    for claim in db.scalars(select(OfferClaim).where(OfferClaim.offer_id == offer.id)):
        if claim.field in {"delivery", "lead_days", "flower"} and claim.evidence:
            seller_fact(db, offer, claim.field, claim.value.get("value"), claim.evidence[-1])
    return True
