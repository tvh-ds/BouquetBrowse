"""Hanoi wall-clock slots, no sleep wake-up and no catch-up collection bursts."""

from datetime import datetime, time, timedelta

from sqlalchemy import select, text

from .config import get_settings
from .db import aware, utcnow
from .digests import HANOI, build_digest
from .discovery import settings_row
from .executions import create_execution
from .leases import cancel
from .models import Job
from .operations_models import RuntimeStatus, ScheduleSlot
from .pilot import readiness
from .runtime_models import GraphExecution

HOURS = (6, 10, 14, 18, 22)


def next_check(frontier, now=None):
    now = aware(now or utcnow())
    if frontier.evidence_gaps:
        local = now.astimezone(HANOI)
        return next(
            datetime.combine(local.date() + timedelta(days=offset), time(hour), HANOI)
            for offset in range(2)
            for hour in HOURS
            if datetime.combine(local.date() + timedelta(days=offset), time(hour), HANOI) > now
        )
    return (
        now + timedelta(days=7 if frontier.kind == "profile" else 1)
        if frontier.kind in {"profile", "post"}
        else now + timedelta(hours=4)
    )


def collection_ready(db, settings, control):
    return (
        settings.recurring_enabled
        and settings.discovery_enabled
        and not control.paused
        and readiness(db)["ready"]
        and bool(settings.openai_api_key)
        and db.bind.dialect.name == "postgresql"
    )


def heartbeat(db, role, state="awake", details=None, now=None):
    from .discovery import dialect_insert

    now = now or utcnow()
    db.execute(
        dialect_insert(db)(RuntimeStatus)
        .values(role=role, seen_at=now, state=state, details=details or {})
        .on_conflict_do_nothing(index_elements=["role"])
    )
    row = db.scalar(select(RuntimeStatus).where(RuntimeStatus.role == role))
    row.seen_at, row.state = now, state
    if details is not None:
        row.details = details
    return row


def tick(db, now=None):
    now = aware(now or utcnow())
    today = now.astimezone(HANOI).date()
    if db.bind.dialect.name == "postgresql":
        db.execute(text("SELECT pg_advisory_xact_lock(73402917)"))
    settings = get_settings()
    status = heartbeat(db, "scheduler", now=now)
    control = settings_row(db)
    operational = collection_ready(db, settings, control)
    status.state = "ready" if operational else "paused" if control.paused else "setup_pending"
    start = status.details.get("started_day")
    if not start:
        if not operational:
            return {"scheduled": 0, "state": status.state}
        start = today.isoformat()
        status.details = {"started_day": start}
    first = max(datetime.fromisoformat(start).date(), today - timedelta(days=30))
    # Never reuse queued browser work after a sleep as a catch-up run.
    for slot in db.scalars(select(ScheduleSlot).where(ScheduleSlot.state == "queued")):
        execution = db.get(GraphExecution, slot.execution_id)
        job = db.get(Job, execution.job_id) if execution else None
        if execution and execution.state == "completed":
            slot.state, slot.reason = "completed", execution.stop_reason
        elif not execution or not job or job.state in {"failed", "paused", "cancelled"}:
            slot.state, slot.reason = "failed", execution.stop_reason if execution else "missing_execution"
        elif now > aware(slot.scheduled_at) + timedelta(minutes=20):
            cancel(db, job.id)
            execution.state, execution.stop_reason = "cancelled", "missed_window"
            slot.state, slot.reason = "missed", "sleep_or_interrupted"
    count = 0
    day = first
    while day <= today:
        for hour in HOURS:
            scheduled = datetime.combine(day, time(hour), HANOI)
            if scheduled > now:
                continue
            key = f"{day.isoformat()}T{hour:02}:00+07:00"
            if db.scalar(select(ScheduleSlot.id).where(ScheduleSlot.slot_key == key)):
                continue
            slot = ScheduleSlot(slot_key=key, scheduled_at=scheduled, state="missed", reason="computer_not_running")
            db.add(slot)
            if operational and now <= scheduled + timedelta(seconds=90):
                active = db.scalar(
                    select(GraphExecution.id).where(
                        GraphExecution.kind == "discovery",
                        GraphExecution.state.in_(["queued", "processing", "running"]),
                        GraphExecution.deadline > now,
                    )
                )
                if not active:
                    config = {
                        "planner_model": settings.planner_model,
                        "extraction_model": settings.extraction_model,
                        "escalation_model": settings.escalation_model,
                        "taxonomy_version": control.configuration.get("taxonomy_version", "flowers-v2"),
                        "prompt_version": "discovery-v1",
                        "schema_version": "conversation-v1",
                        "policy_ref": control.policy["policy_ref"],
                        "budget_usd": settings.discovery_run_budget_usd,
                        "slot": key,
                    }
                    execution = create_execution(db, "discovery", f"slot:{key}", config, key)
                    execution.deadline = scheduled + timedelta(minutes=20)
                    slot.execution_id, slot.state, slot.reason = execution.id, "queued", None
                    count += 1
                else:
                    slot.reason = "browser_run_active"
            elif not operational:
                slot.reason = "paused_or_setup_pending"
        db.flush()
        slots = list(db.scalars(select(ScheduleSlot).where(ScheduleSlot.slot_key.like(f"{day.isoformat()}%"))))
        if len(slots) == 5 and all(s.state != "queued" for s in slots):
            build_digest(
                db,
                day,
                {
                    "scheduled": 5,
                    "completed": sum(s.state == "completed" for s in slots),
                    "missed": sum(s.state != "completed" for s in slots),
                },
                now=now,
            )
        day += timedelta(days=1)
    return {"scheduled": count, "state": status.state}
