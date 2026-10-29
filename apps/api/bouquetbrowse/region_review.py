"""An operator may split an immutable collage into explicitly bound region offers."""

from sqlalchemy import select

from .conversation_contracts import QuoteReference
from .conversation_models import OfferAssociation
from .conversations import anchor_quote, ensure_occurrence
from .db import aware, utcnow
from .executions import create_execution
from .models import Listing, MediaAsset, PostVersion, SourcePost
from .offers import current_associations, offer_fingerprint
from .recognition_models import ImageRegion
from .runtime_models import GraphExecution
from .schemas import StrictModel


class RegionDecision(StrictModel):
    expected_fingerprint: str
    price_target: QuoteReference | None = None


def split_region(db, original, region_id, body, actor, command_key):
    if original.input_fingerprint != body.expected_fingerprint or original.state in {"withdrawn", "rejected"}:
        raise ValueError("Offer evidence changed or was suppressed")
    region = db.get(ImageRegion, region_id)
    refs = current_associations(db, original)
    source_ref = next(
        (a for a in refs if a.media_id == (region.media_id if region else None) and a.role == "seller_image"), None
    )
    asset = db.get(MediaAsset, region.media_id) if region else None
    if (
        not region
        or region.kind != "product"
        or aware(region.retention_until) <= utcnow()
        or not source_ref
        or not asset
        or asset.checksum != region.checksum
    ):
        raise ValueError("Select a current seller-owned product region")
    source = db.get(SourcePost, db.get(PostVersion, source_ref.version_id).post_id)
    if source.account_id != original.account_id:
        raise ValueError("Reference images cannot establish completed seller work")
    target = anchor_quote(db, body.price_target) if body.price_target else None
    if target and target["version_id"] not in {
        a.version_id
        for a in refs
        if db.get(SourcePost, db.get(PostVersion, a.version_id).post_id).account_id == original.account_id
    }:
        raise ValueError("Commercial binding must cite this seller's messages")
    offer = ensure_occurrence(db, original.account_id, original.anchor_id, f"region:{region.id}")
    existing = current_associations(db, offer)
    if existing:
        previous_target = next((a.evidence.get("target") for a in existing if a.role == "commercial_target"), None)
        if previous_target != target:
            raise ValueError("A changed region decision needs a new association revision")
    else:
        for ref in refs:
            if not ref.media_id:
                db.add(
                    OfferAssociation(
                        offer_id=offer.id,
                        revision=offer.association_revision,
                        version_id=ref.version_id,
                        item_key=ref.item_key,
                        role=ref.role,
                        basis=ref.basis,
                        state=ref.state,
                        evidence=ref.evidence,
                    )
                )
        db.add(
            OfferAssociation(
                offer_id=offer.id,
                revision=offer.association_revision,
                version_id=source_ref.version_id,
                media_id=asset.id,
                region=region.bounds,
                item_key=f"region:{region.id}",
                role="seller_image",
                basis="reviewed_region",
                state="accepted",
                evidence={**source_ref.evidence, "region_id": region.id, "actor": actor},
            )
        )
        if target:
            db.add(
                OfferAssociation(
                    offer_id=offer.id,
                    revision=offer.association_revision,
                    version_id=target["version_id"],
                    item_key=f"price:{region.id}",
                    role="commercial_target",
                    basis="reviewed_region",
                    state="accepted",
                    evidence={"target": target, "region_id": region.id, "actor": actor},
                )
            )
        db.flush()
        offer.input_fingerprint = offer_fingerprint(db, offer)
    region.state = "accepted"
    original.state = "split"
    if original.listing_id:
        db.get(Listing, original.listing_id).state = "review"
    previous = db.scalar(
        select(GraphExecution)
        .where(GraphExecution.offer_id == original.id)
        .order_by(GraphExecution.created_at.desc())
        .limit(1)
    )
    if not previous:
        raise ValueError("Original execution configuration is missing")
    execution = create_execution(
        db, "offer", f"region:{command_key}"[:160], previous.configuration, offer.input_fingerprint, offer.id
    )
    return {"offer_id": offer.id, "execution_id": execution.id, "job_id": execution.job_id}
