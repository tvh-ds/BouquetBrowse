"""Daily backups and content-free, transition-driven local alert delivery."""

import json
from datetime import timedelta

from sqlalchemy import delete, func, or_, select, text

from .backups import owned_directory
from .config import get_settings
from .db import aware, utcnow
from .digests import HANOI
from .discovery import dialect_insert
from .maintenance_models import OperationAlert
from .models import CostEntry, Job
from .operations_models import DeletionRecord, RuntimeStatus
from .pipeline import enqueue
from .runtime_models import DiscoveryFrontier, ModelCall

MESSAGES = {
    "worker_missing": "A configured worker has stopped reporting. Inspect local startup and role health.",
    "jobs_failed": "Processing jobs failed. Inspect their errors before retrying.",
    "calls_uncertain": "Paid requests have uncertain outcomes. Inspect receipts before explicitly replaying.",
    "budget_near_limit": "At least 80% of the monthly model budget is reserved or spent.",
    "backlog_old": "Queued work has waited more than one day. Inspect workers and evidence expiry.",
    "backup_overdue": "No successful backup was recorded within 24 hours while backups are enabled.",
    "frontier_stale": "Discovery targets remain overdue by more than two days.",
}


def monthly_spending(db, now=None):
    now = now or utcnow()
    first = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return db.scalar(
        select(func.coalesce(func.sum(CostEntry.amount_microusd), 0)).where(
            CostEntry.created_at >= first, CostEntry.state.in_(["reserved", "settled", "uncertain"])
        )
    )


def set_alert(db, code, details, now):
    active = bool(details)
    row = db.scalar(select(OperationAlert).where(OperationAlert.code == code))
    if not row and not active:
        return
    if not row:
        db.execute(
            dialect_insert(db)(OperationAlert)
            .values(code=code, severity="warning", state="open", details=details, version=1, last_seen_at=now)
            .on_conflict_do_nothing(index_elements=["code"])
        )
        row = db.scalar(select(OperationAlert).where(OperationAlert.code == code))
        changed = True
    else:
        changed = (
            (active and row.state == "resolved") or (not active and row.state != "resolved") or row.details != details
        )
        if changed:
            row.version += 1
            row.state, row.acknowledged_by = "open" if active else "resolved", None
        row.details = details
        if active or changed:
            row.last_seen_at = now
    if changed:
        enqueue(
            db,
            "deliver-alert",
            {"alert_id": row.id, "version": row.version, "code": code, "state": row.state},
            f"alert:{row.id}:{row.version}",
        )


def tick(db, now=None):
    now = now or utcnow()
    settings = get_settings()
    if db.bind.dialect.name == "postgresql":
        db.execute(text("SELECT pg_advisory_xact_lock(73402921)"))
    if settings.backups_enabled and now.astimezone(HANOI).hour >= 6:
        from .leases import cancel

        current_key = f"backup:{now.astimezone(HANOI).date()}"
        for old in db.scalars(
            select(Job).where(Job.kind == "backup", Job.state == "queued", Job.idempotency_key != current_key)
        ):
            cancel(db, old.id)
        enqueue(db, "backup", {}, current_key)
    enqueue(db, "prune-alerts", {}, f"prune-alerts:{now.date()}")
    db.execute(
        delete(OperationAlert).where(
            OperationAlert.state == "resolved", OperationAlert.last_seen_at < now - timedelta(days=30)
        )
    )
    latest = db.scalar(select(DeletionRecord).order_by(DeletionRecord.created_at.desc(), DeletionRecord.id).limit(1))
    if latest:
        enqueue(db, "snapshot-deletions", {}, f"deletion-ledger:{latest.id}")
    roles = {r.role: r for r in db.scalars(select(RuntimeStatus))}
    missing = [
        role
        for role in ["browser", "offer"]
        if role not in roles or aware(roles[role].seen_at) < now - timedelta(minutes=3)
    ]
    # Long calls have a fenced heartbeat in the jobs table even between role heartbeats.
    active = list(db.scalars(select(Job).where(Job.state == "processing", Job.lease_until > now)))
    missing = [
        role for role in missing if not any((j.kind == "discovery-graph") == (role == "browser") for j in active)
    ]
    failed = db.scalar(
        select(func.count()).select_from(Job).where(Job.state == "failed", Job.created_at > now - timedelta(days=30))
    )
    uncertain = db.scalar(
        select(func.count())
        .select_from(ModelCall)
        .where(
            or_(
                ModelCall.state == "uncertain",
                (ModelCall.state == "dispatched") & (ModelCall.created_at < now - timedelta(minutes=2)),
            ),
            ModelCall.retention_until > now,
        )
    )
    backlog = db.scalar(
        select(func.count()).select_from(Job).where(Job.state == "queued", Job.run_after < now - timedelta(days=1))
    )
    spending = monthly_spending(db, now)
    backup = db.scalar(
        select(Job).where(Job.kind == "backup", Job.state == "succeeded").order_by(Job.created_at.desc()).limit(1)
    )
    stale = db.scalar(
        select(func.count())
        .select_from(DiscoveryFrontier)
        .where(DiscoveryFrontier.state == "due", DiscoveryFrontier.due_at < now - timedelta(days=2))
    )
    checks = {
        "worker_missing": {"roles": missing} if missing and settings.recurring_enabled else {},
        "jobs_failed": {"count": failed} if failed else {},
        "calls_uncertain": {"count": uncertain} if uncertain else {},
        "budget_near_limit": {"threshold_percent": 80}
        if spending >= settings.monthly_model_budget_usd * 800000
        else {},
        "backlog_old": {"count": backlog} if backlog else {},
        "backup_overdue": {"hours": 24}
        if settings.backups_enabled and (not backup or aware(backup.created_at) < now - timedelta(hours=24))
        else {},
        "frontier_stale": {"count": stale} if stale and settings.recurring_enabled else {},
    }
    for code, details in checks.items():
        set_alert(db, code, details, now)
    return {"active_alerts": sum(bool(v) for v in checks.values())}


def deliver(payload):
    from uuid import UUID

    if (
        set(payload) != {"alert_id", "version", "code", "state"}
        or payload.get("code") not in MESSAGES
        or payload.get("state") not in {"open", "resolved"}
    ):
        raise ValueError("Unknown operational alert")
    UUID(payload["alert_id"])
    if type(payload["version"]) is not int or payload["version"] <= 0:
        raise ValueError("Invalid alert version")
    folder = owned_directory(get_settings().alert_directory)
    # Structured local delivery only. No email, social message or webhook is sent.
    path = folder / f"alerts-{utcnow().date().isoformat()}.jsonl"
    if path.is_symlink():
        raise ValueError("Alert log must be a managed ordinary file")
    event = {
        **payload,
        "event_id": f"{payload['alert_id']}:{payload['version']}",
        "message": MESSAGES[payload["code"]],
        "at": utcnow().isoformat(),
    }
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(event) + "\n")
    prune_alert_logs()
    return {"delivered": True, "event_id": event["event_id"]}


def prune_alert_logs():
    folder = owned_directory(get_settings().alert_directory)
    for old in folder.glob("alerts-????-??-??.jsonl"):
        if old.is_symlink() or old.resolve().parent != folder:
            raise ValueError("Alert retention target is not managed")
        if old.name < f"alerts-{(utcnow() - timedelta(days=30)).date().isoformat()}.jsonl":
            old.unlink()
    return {"pruned": True}
