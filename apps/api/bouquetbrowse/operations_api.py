"""Private local-runtime health and measured catalog coverage; no source payloads."""

from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .auth import User, require_admin
from .config import get_settings
from .db import aware, get_db, utcnow
from .maintenance import MESSAGES, monthly_spending
from .maintenance_models import OperationAlert
from .models import Job, Listing, PriceObservation, SourcePost
from .operations_models import RuntimeStatus, ScheduleSlot
from .pilot import readiness
from .schemas import StrictModel
from .visibility import visible_listings

router = APIRouter(prefix="/v1/admin/operations", dependencies=[Depends(require_admin)])
Database = Annotated[Session, Depends(get_db)]


class AlertDecision(StrictModel):
    expected_version: int = Field(ge=1)


@router.post("/alerts/{alert_id}/acknowledge")
def acknowledge(alert_id: str, body: AlertDecision, db: Database, actor: Annotated[User, Depends(require_admin)]):
    alert = db.scalar(select(OperationAlert).where(OperationAlert.id == alert_id).with_for_update())
    if not alert or alert.version != body.expected_version or alert.state == "resolved":
        raise HTTPException(409, detail="Alert changed; reload before acknowledging")
    alert.state, alert.acknowledged_by = "acknowledged", actor.id
    db.commit()
    return {"id": alert.id, "state": alert.state}


@router.get("/status")
def status(db: Database):
    now = utcnow()
    listings = [listing for listing in visible_listings(db) if not listing.is_demo]
    prices = list(
        db.scalars(
            select(PriceObservation)
            .join(Listing, Listing.id == PriceObservation.listing_id)
            .where(Listing.is_demo.is_(False))
        )
    )
    active_leases = list(db.scalars(select(Job).where(Job.state == "processing", Job.lease_until > now)))

    def role_health(row):
        leases = [
            job
            for job in active_leases
            if (job.kind == "discovery-graph") == (row.role == "browser") and row.role != "scheduler"
        ]
        last = max([aware(row.seen_at), *[aware(job.lease_until) - timedelta(seconds=120) for job in leases]])
        return {
            "role": row.role,
            "state": "busy" if leases else row.state,
            "last_seen_at": last,
            "stale": (now - last).total_seconds() > 120,
        }

    return {
        "recurring_configured": get_settings().recurring_enabled,
        "backups_configured": get_settings().backups_enabled,
        "alerts": [
            {
                "id": a.id,
                "code": a.code,
                "state": a.state,
                "severity": a.severity,
                "version": a.version,
                "message": MESSAGES[a.code],
                "details": a.details,
                "last_seen_at": a.last_seen_at,
            }
            for a in db.scalars(select(OperationAlert).order_by(OperationAlert.last_seen_at.desc()).limit(100))
        ],
        "backups": [
            {"id": j.id, "state": j.state, "created_at": j.created_at, "result": j.result}
            for j in db.scalars(select(Job).where(Job.kind == "backup").order_by(Job.created_at.desc()).limit(10))
        ],
        "readiness": readiness(db),
        "roles": [role_health(row) for row in db.scalars(select(RuntimeStatus))],
        "slots": [
            {"key": r.slot_key, "state": r.state, "reason": r.reason, "execution_id": r.execution_id}
            for r in db.scalars(select(ScheduleSlot).order_by(ScheduleSlot.scheduled_at.desc()).limit(35))
        ],
        "coverage": {
            "visible_real_listings": len(listings),
            "visible_independent_sellers": len({listing.seller_id for listing in listings}),
            "observed_real_posts": db.scalar(
                select(func.count()).select_from(SourcePost).where(SourcePost.is_demo.is_(False))
            ),
            "advertised_prices_observed": len(prices),
            "reviewed_prices": sum(p.reviewed for p in prices),
            "supported_size_listings": sum(listing.stem_count is not None for listing in listings),
        },
        "model_cost_microusd": monthly_spending(db),
        "model_budget_microusd": round(get_settings().monthly_model_budget_usd * 1000000),
        "quality": "See audited pilot proofs; fixture success does not establish live quality.",
        "latency": "Not measured" if not prices else "Use private per-run evaluation measurements.",
    }
