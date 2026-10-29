"""Operational conversation views are restricted to administrators."""

from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .auth import User, require_admin
from .conversation_models import CaptureMember, ConversationCapture, OfferOccurrence
from .db import get_db, utcnow
from .models import Job, PostVersion
from .offer_contracts import OfferInterpretation
from .offer_models import AssociationReview, OfferAnalysis
from .offers import evidence_bundle, validate_interpretation
from .runtime_models import GraphExecution
from .schemas import StrictModel

router = APIRouter(prefix="/v1/admin/conversations", dependencies=[Depends(require_admin)])
Database = Annotated[Session, Depends(get_db)]


class InterpretationDecision(StrictModel):
    expected_fingerprint: str
    interpretation: OfferInterpretation


from .region_review import RegionDecision  # noqa: E402


@router.post("/offers/{offer_id}/regions/{region_id}/split")
def split(
    offer_id: str,
    region_id: str,
    body: RegionDecision,
    db: Database,
    user: Annotated[User, Depends(require_admin)],
    idempotency_key: Annotated[str | None, Header()] = None,
):
    from .region_review import split_region

    if not idempotency_key or len(idempotency_key) > 100:
        raise HTTPException(400, detail="Provide an Idempotency-Key of at most 100 characters.")
    offer = db.scalar(select(OfferOccurrence).where(OfferOccurrence.id == offer_id).with_for_update())
    if not offer:
        raise HTTPException(404, detail="Offer not found.")
    result = split_region(db, offer, region_id, body, user.id, idempotency_key)
    db.commit()
    return result


@router.get("")
def captures(db: Database):
    rows = db.scalars(select(ConversationCapture).order_by(ConversationCapture.created_at.desc()).limit(50))
    return {
        "items": [
            {
                "id": r.id,
                "url": r.source_url,
                "at": r.created_at,
                "sorting": r.sorting,
                "coverage": r.coverage,
                "remaining_expansions": r.remaining_expansions,
                "stop_reason": r.stop_reason,
            }
            for r in rows
        ]
    }


@router.get("/exceptions")
def exceptions(db: Database):
    rows = db.scalars(
        select(AssociationReview)
        .where(AssociationReview.state == "pending")
        .order_by(AssociationReview.created_at)
        .limit(100)
    )
    return {
        "items": [
            {"id": r.id, "offer_id": r.offer_id, "fingerprint": r.fingerprint, "kind": r.kind, "proposal": r.proposal}
            for r in rows
        ]
    }


@router.get("/offers/{offer_id}")
def detail(offer_id: str, db: Database):
    offer = db.get(OfferOccurrence, offer_id)
    if not offer:
        raise HTTPException(404, detail="Offer not found.")
    from .models import MediaAsset
    from .recognition_models import ImageRegion

    bundle = evidence_bundle(db, offer)
    media_ids = {m["media_id"] for m in bundle["media"]}
    regions = list(db.scalars(select(ImageRegion).where(ImageRegion.media_id.in_(media_ids))))
    return {
        "id": offer.id,
        "state": offer.state,
        "fingerprint": offer.input_fingerprint,
        "evidence": bundle,
        "regions": [
            {"id": r.id, "media_id": r.media_id, "bounds": r.bounds, "kind": r.kind, "state": r.state}
            for r in regions
            if db.get(MediaAsset, r.media_id).checksum == r.checksum
        ],
    }


@router.post("/offers/{offer_id}/interpretation")
def decide(
    offer_id: str,
    body: InterpretationDecision,
    db: Database,
    user: Annotated[User, Depends(require_admin)],
    idempotency_key: Annotated[str | None, Header()] = None,
):
    if not idempotency_key or len(idempotency_key) > 160:
        raise HTTPException(400, detail="Provide a bounded Idempotency-Key.")
    offer = db.scalar(select(OfferOccurrence).where(OfferOccurrence.id == offer_id).with_for_update())
    if not offer:
        raise HTTPException(404, detail="Offer not found.")
    if offer.input_fingerprint != body.expected_fingerprint or offer.state in {"withdrawn", "rejected"}:
        raise HTTPException(409, detail="Offer changed or is suppressed; reload evidence.")
    analysis = db.scalar(
        select(OfferAnalysis)
        .where(OfferAnalysis.offer_id == offer.id, OfferAnalysis.fingerprint == offer.input_fingerprint)
        .order_by(OfferAnalysis.created_at.desc())
        .limit(1)
    )
    if not analysis:
        raise HTTPException(409, detail="Wait for the current interpretation attempt.")
    if analysis.state == "completed":
        raise HTTPException(409, detail="Completed revisions are immutable; request reprocessing.")
    validated = validate_interpretation(
        db, offer, body.interpretation, db.get(GraphExecution, analysis.execution_id).configuration
    )
    if validated["errors"]:
        raise HTTPException(422, detail={"code": "evidence_unresolved", "errors": validated["errors"]})
    reviews = list(
        db.scalars(
            select(AssociationReview).where(
                AssociationReview.offer_id == offer.id, AssociationReview.fingerprint == offer.input_fingerprint
            )
        )
    )
    submitted = body.model_dump(mode="json")
    existing = next((r for r in reviews if r.decision.get("command_key") == idempotency_key), None)
    if existing and existing.decision.get("submitted") != submitted:
        raise HTTPException(409, detail="Decision key was used for different inputs.")
    for review in reviews:
        review.state, review.actor = "accepted", user.id
        review.decision = {"command_key": idempotency_key, "submitted": submitted, "at": utcnow().isoformat()}
    analysis.output = {
        **analysis.output,
        **validated,
        "composition": validated["composition"]
        + [c for c in analysis.output.get("composition", []) if c.get("status") == "visual_inference"],
    }
    analysis.errors = []
    execution = db.get(GraphExecution, analysis.execution_id)
    job = db.get(Job, execution.job_id)
    if job.state == "processing" or job.cancelled_at:
        raise HTTPException(409, detail="Wait for active work or create a new execution after cancellation.")
    job.state, job.run_after, execution.state = "queued", utcnow(), "queued"
    db.commit()
    return {"offer_id": offer.id, "execution_id": execution.id, "state": "queued"}


@router.get("/{capture_id}")
def capture_detail(capture_id: str, db: Database):
    capture = db.get(ConversationCapture, capture_id)
    if not capture:
        raise HTTPException(404, detail="Capture not found.")
    rows = list(
        db.scalars(
            select(PostVersion)
            .join(CaptureMember, CaptureMember.version_id == PostVersion.id)
            .where(CaptureMember.capture_id == capture.id)
            .limit(100)
        )
    )
    from .conversation_models import MessageEdge
    from .db import aware
    from .models import SourceAccount, SourcePost

    post_ids = {v.post_id for v in rows}
    return {
        "id": capture.id,
        "coverage": capture.coverage,
        "stop_reason": capture.stop_reason,
        "sorting": capture.sorting,
        "remaining_expansions": capture.remaining_expansions,
        "edges": [
            {
                "source_id": e.source_id,
                "target_id": e.target_id,
                "unresolved_platform_id": e.target_platform_id if not e.target_id else None,
                "kind": e.kind,
            }
            for e in db.scalars(select(MessageEdge).where(MessageEdge.source_id.in_(post_ids)))
        ],
        "offers": [
            {"id": o.id, "state": o.state, "seller_id": o.seller_id, "listing_id": o.listing_id}
            for o in db.scalars(select(OfferOccurrence).where(OfferOccurrence.anchor_id.in_(post_ids)))
        ],
        "messages": [
            {
                "version_id": v.id,
                "post_id": v.post_id,
                "text": v.caption if aware(v.retention_until) > utcnow() else "",
                "author": db.get(SourceAccount, db.get(SourcePost, v.post_id).account_id).username,
                "published_at": db.get(SourcePost, v.post_id).published_at,
                "retention_until": v.retention_until,
            }
            for v in rows
        ],
    }
