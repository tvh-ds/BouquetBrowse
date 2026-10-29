from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from .auth import User, require_admin, require_user
from .catalog_event_models import DailyDigest
from .db import get_db, utcnow
from .digests import digest_view
from .model_calls import authorize_replay
from .models import CostEntry, Job
from .pipeline import enqueue
from .responses import DigestListView, DigestView
from .runtime_models import GraphExecution, ModelCall
from .schemas import StrictModel

router = APIRouter()
Database = Annotated[Session, Depends(get_db)]


@router.get("/v1/admin/media/{media_id}", dependencies=[Depends(require_admin)])
def operational_media(media_id: str, db: Database):
    from .db import aware
    from .models import MediaAsset
    from .storage import get_media_bytes

    asset = db.get(MediaAsset, media_id)
    if (
        not asset
        or asset.state != "ready"
        or not asset.storage_key
        or asset.retention_until
        and aware(asset.retention_until) <= utcnow()
    ):
        raise HTTPException(404, detail="Media is unavailable or expired.")
    try:
        return Response(
            get_media_bytes(asset.storage_key), media_type="image/jpeg", headers={"Cache-Control": "private, no-store"}
        )
    except FileNotFoundError as exc:
        raise HTTPException(404, detail="Media is unavailable.") from exc


@router.get("/v1/listings/{listing_id}/image", dependencies=[Depends(require_user)])
def listing_image(listing_id: str, db: Database):
    from .models import Listing, ListingRevision, MediaAsset
    from .recognition import crop_image
    from .recognition_contracts import RegionBounds
    from .storage import get_media_bytes
    from .visibility import visible

    listing = db.get(Listing, listing_id)
    if not visible(db, listing):
        raise HTTPException(404, detail="Image is unavailable.")
    revision = db.get(ListingRevision, listing.current_revision_id)
    media_ids = revision.snapshot.get("media_ids", []) if revision else []
    if not media_ids:
        raise HTTPException(404, detail="Image is unavailable.")
    asset = db.get(MediaAsset, media_ids[0])
    from .db import aware

    if (
        not asset
        or not asset.storage_key
        or asset.state != "ready"
        or asset.retention_until
        and aware(asset.retention_until) <= utcnow()
    ):
        raise HTTPException(404, detail="Image is unavailable.")
    try:
        content = get_media_bytes(asset.storage_key)
        region = revision.snapshot.get("media_regions", {}).get(asset.id)
        if region:
            content = crop_image(
                content, RegionBounds(left=region[0], top=region[1], right=region[2], bottom=region[3])
            )
        return Response(content, media_type="image/jpeg", headers={"Cache-Control": "private, no-store"})
    except FileNotFoundError as exc:
        raise HTTPException(404, detail="Image is unavailable.") from exc


class ReplayBody(StrictModel):
    expected_state: str


@router.get("/v1/digests", dependencies=[Depends(require_user)], response_model=DigestListView)
def digests(db: Database):
    rows = db.scalars(select(DailyDigest).order_by(DailyDigest.day.desc()).limit(60))
    return {
        "items": [
            {
                "date": row.day.isoformat(),
                "partial": row.partial,
                "coverage": row.coverage,
                "published_at": row.created_at.isoformat(),
                "note": row.note,
            }
            for row in rows
        ]
    }


@router.get("/v1/digests/{day}", dependencies=[Depends(require_user)], response_model=DigestView)
def digest(day: date, db: Database):
    row = db.scalar(select(DailyDigest).where(DailyDigest.day == day))
    if not row:
        raise HTTPException(404, detail="No digest was published for this day.")
    return digest_view(db, row)


@router.get("/v1/admin/model-calls", dependencies=[Depends(require_admin)])
def calls(db: Database):
    rows = db.scalars(select(ModelCall).order_by(ModelCall.created_at.desc()).limit(100))
    return {
        "items": [
            {
                "id": row.id,
                "model": row.model,
                "state": row.state,
                "attempt": row.attempt,
                "execution_id": row.execution_id,
                "job_id": row.job_id,
                "replay_authorized": row.replay_authorized,
                "amount_microusd": db.get(CostEntry, row.cost_id).amount_microusd,
                "created_at": row.created_at,
            }
            for row in rows
        ]
    }


@router.post("/v1/admin/model-calls/{call_id}/replay")
def replay(
    call_id: str,
    body: ReplayBody,
    db: Database,
    user: Annotated[User, Depends(require_admin)],
    idempotency_key: Annotated[str | None, Header()] = None,
):
    if not idempotency_key or len(idempotency_key) > 160:
        raise HTTPException(400, detail="Provide a bounded Idempotency-Key.")
    prior = db.scalar(select(Job).where(Job.idempotency_key == f"replay:{idempotency_key}"))
    if prior:
        if prior.payload != {"call_id": call_id, "expected_state": body.expected_state}:
            raise HTTPException(409, detail="Replay key was used for different inputs.")
        return prior.result
    row = db.scalar(select(ModelCall).where(ModelCall.id == call_id).with_for_update())
    if not row or row.state != body.expected_state or row.state not in {"uncertain", "failed"}:
        raise HTTPException(409, detail="Paid-call state changed or is not replayable.")
    job = db.get(Job, row.job_id) if row.job_id else None
    execution = db.get(GraphExecution, row.execution_id) if row.execution_id else None
    if (
        not job
        or job.cancelled_at
        or job.state == "processing"
        or execution
        and execution.state in {"superseded", "cancelled", "withdrawn"}
    ):
        raise HTTPException(409, detail="This execution cannot resume; inspect its current evidence and job state.")
    receipt = enqueue(
        db, "replay-receipt", {"call_id": row.id, "expected_state": body.expected_state}, f"replay:{idempotency_key}"
    )
    if receipt.state == "succeeded":
        return receipt.result
    authorize_replay(db, row.id, user.id)
    # A new reservation is made by invoke_once before redispatch, under all original limits.
    job.state, job.run_after, job.last_error = "queued", utcnow(), None
    if execution:
        execution.state = "queued"
    receipt.state, receipt.result = "succeeded", {"call_id": row.id, "job_id": job.id, "state": "queued"}
    db.commit()
    return receipt.result
