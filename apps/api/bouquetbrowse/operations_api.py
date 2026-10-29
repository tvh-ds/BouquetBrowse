"""Private local-runtime health and measured catalog coverage; no source payloads."""

from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .auth import require_admin
from .config import get_settings
from .db import aware, get_db, utcnow
from .models import CostEntry, Job, Listing, PriceObservation, SourcePost
from .operations_models import RuntimeStatus, ScheduleSlot
from .pilot import readiness
from .visibility import visible_listings

router = APIRouter(prefix="/v1/admin/operations", dependencies=[Depends(require_admin)])
Database = Annotated[Session, Depends(get_db)]


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
        "model_cost_microusd": db.scalar(
            select(func.coalesce(func.sum(CostEntry.amount_microusd), 0)).where(
                CostEntry.state.in_(["reserved", "settled", "uncertain"])
            )
        ),
        "quality": "See audited pilot proofs; fixture success does not establish live quality.",
        "latency": "Not measured" if not prices else "Use private per-run evaluation measurements.",
    }
