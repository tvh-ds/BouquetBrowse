"""Durable paid-call receipts. A timeout is not permission to bill again."""

import time
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import timedelta
from decimal import ROUND_CEILING, Decimal

from sqlalchemy import func, select, text

from . import db as database
from .config import get_settings
from .db import aware, utcnow
from .models import CostEntry
from .pipeline import digest
from .runtime_models import GraphExecution, ModelCall


@dataclass(frozen=True)
class CallScope:
    key: str
    limit_microusd: int
    execution_id: str | None = None
    lease: object | None = None


CURRENT_SCOPE = ContextVar("model_call_scope", default=None)


@contextmanager
def call_scope(scope):
    token = CURRENT_SCOPE.set(scope)
    try:
        yield
    finally:
        CURRENT_SCOPE.reset(token)


def microusd(amount):
    value = Decimal(str(amount))
    if not value.is_finite() or value < 0:
        raise ValueError("Spending amounts must be finite and nonnegative")
    return int((value * 1_000_000).to_integral_value(rounding=ROUND_CEILING))


def verify_scope(db, scope):
    from .providers import CapabilityError

    if scope.lease:
        from .leases import guard

        guard(db, scope.lease)
    if scope.execution_id:
        execution = db.get(GraphExecution, scope.execution_id)
        if not execution or execution.state in {"cancelled", "superseded", "withdrawn"}:
            raise CapabilityError("Execution is no longer active.", "execution_cancelled")
        if scope.lease and execution.job_id != scope.lease.job_id:
            raise CapabilityError("Lease does not own this model execution.", "lease_lost")
        if execution.deadline and aware(execution.deadline) <= utcnow():
            raise CapabilityError("Execution deadline reached.", "run_deadline")


def lock_spending(db):
    if db.bind.dialect.name == "postgresql":
        db.execute(text("SELECT pg_advisory_xact_lock(73402911)"))


def amount_expression():
    # Historical rows written before the integer ledger migration remain countable.
    return func.coalesce(func.nullif(CostEntry.amount_microusd, 0), func.round(CostEntry.amount_usd * 1_000_000))


def reserve_entry(db, model, amount):
    from .providers import CapabilityError

    reserved = microusd(amount)
    if reserved <= 0:
        raise ValueError("A positive reservation is required")
    lock_spending(db)
    first = utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    spent = db.scalar(
        select(func.coalesce(func.sum(amount_expression()), 0)).where(
            CostEntry.created_at >= first,
            CostEntry.state.in_(["reserved", "settled", "uncertain"]),
        )
    )
    if spent + reserved > microusd(get_settings().monthly_model_budget_usd):
        raise CapabilityError("Monthly model budget reached. Review spending before retrying.", "budget_exhausted")
    entry = CostEntry(
        provider="openai", model=model, amount_usd=reserved / 1_000_000, amount_microusd=reserved, state="reserved"
    )
    db.add(entry)
    db.flush()
    return entry


def invoke_once(model, request, invoke, reservation_usd=0.10):
    """invoke returns (validated JSON result, usage JSON, actual USD). No network transaction."""
    from .providers import CapabilityError

    request_hash = digest({"model": model, "request": request})
    scope = CURRENT_SCOPE.get() or CallScope(f"request:{request_hash}", microusd(reservation_usd))
    blocked = None
    with database.SessionLocal() as db:
        lock_spending(db)
        verify_scope(db, scope)
        previous = db.scalar(
            select(ModelCall)
            .where(
                ModelCall.scope_key == scope.key,
                ModelCall.request_hash == request_hash,
            )
            .order_by(ModelCall.attempt.desc())
            .limit(1)
        )
        if previous and previous.state == "succeeded":
            from .retention import receipt_permitted

            if not receipt_permitted(db, previous):
                raise CapabilityError("Cached source evidence is no longer usable.", "source_removed")
            if previous.result is None or aware(previous.retention_until) <= utcnow():
                raise CapabilityError("Cached model evidence expired; request explicit reprocessing.", "call_expired")
            return previous.result, previous.usage
        shared = db.scalar(
            select(ModelCall)
            .where(ModelCall.request_hash == request_hash)
            .order_by(ModelCall.created_at.desc(), ModelCall.attempt.desc())
            .limit(1)
        )
        if shared and shared.scope_key != scope.key:
            if shared.state == "succeeded" and shared.result is not None and aware(shared.retention_until) > utcnow():
                from .retention import receipt_permitted

                if not receipt_permitted(db, shared):
                    raise CapabilityError("Cached source evidence is no longer usable.", "source_removed")
                return shared.result, shared.usage
            if shared.state in {"dispatched", "uncertain", "failed"} and not shared.replay_authorized:
                raise CapabilityError(
                    "Identical paid work is in flight or uncertain in another execution.", "call_replay_required"
                )
        if previous and previous.state in {"dispatched", "uncertain", "failed"} and not previous.replay_authorized:
            previous.state = "uncertain" if previous.state == "dispatched" else previous.state
            db.get(CostEntry, previous.cost_id).state = "uncertain"
            db.commit()
            blocked = previous.id
        if blocked is None:
            if previous and previous.state == "prepared":
                call = previous
            else:
                spent = db.scalar(
                    select(func.coalesce(func.sum(amount_expression()), 0))
                    .join(ModelCall, ModelCall.cost_id == CostEntry.id)
                    .where(ModelCall.scope_key == scope.key)
                )
                if spent + microusd(reservation_usd) > scope.limit_microusd:
                    raise CapabilityError("Execution model allowance reached.", "scope_budget_exhausted")
                cost = reserve_entry(db, model, reservation_usd)
                call = ModelCall(
                    scope_key=scope.key,
                    request_hash=request_hash,
                    attempt=previous.attempt + 1 if previous else 1,
                    execution_id=scope.execution_id,
                    job_id=scope.lease.job_id if scope.lease else None,
                    cost_id=cost.id,
                    model=model,
                    state="prepared",
                    retention_until=utcnow() + timedelta(days=30),
                )
                db.add(call)
                db.flush()
                from .operations_models import CallDependency

                for media_id in sorted({v["media_id"] for v in request.get("views", []) if v.get("media_id")})[:12]:
                    db.add(CallDependency(call_id=call.id, kind="media", reference_id=media_id))
            call_id = call.id
            from .retention import receipt_permitted

            if not receipt_permitted(db, call):
                raise CapabilityError("Source evidence is no longer usable.", "source_removed")
            # Commit dispatch before the request. A crash here must not repeat it automatically.
            call.state = "dispatched"
            db.commit()
    if blocked:
        raise CapabilityError("An uncertain paid call requires explicit replay in admin.", "call_replay_required")
    started = time.monotonic()
    try:
        result, usage, actual_usd = invoke()
        usage = {**usage, "latency_ms": round((time.monotonic() - started) * 1000)}
    except Exception as exc:
        with database.SessionLocal() as db:
            call = db.get(ModelCall, call_id)
            call.state = "removed" if call.state == "removed" else "uncertain"
            db.get(CostEntry, call.cost_id).state = "uncertain"
            db.commit()
        raise CapabilityError(
            "Paid request outcome is uncertain; reservation retained. Explicit replay required.", "call_replay_required"
        ) from exc
    with database.SessionLocal() as db:
        call = db.get(ModelCall, call_id)
        from .retention import receipt_permitted

        permitted = receipt_permitted(db, call)
        # Cancellation can retain an audit receipt; deletion must not resurrect content.
        call.result, call.usage, call.state = (result, usage, "succeeded") if permitted else (None, {}, "removed")
        cost = db.get(CostEntry, call.cost_id)
        cost.amount_microusd = microusd(actual_usd)
        cost.amount_usd, cost.usage, cost.state = cost.amount_microusd / 1_000_000, usage, "settled"
        db.commit()
    if not permitted:
        raise CapabilityError("Source evidence was deleted while the call was in flight.", "source_removed")
    return result, usage


def authorize_replay(db, call_id, actor):
    from .providers import CapabilityError

    call = db.get(ModelCall, call_id)
    if not call or call.state not in {"uncertain", "failed"}:
        raise CapabilityError("Only uncertain/failed calls can be explicitly replayed.", "invalid_replay")
    call.replay_authorized = True
    call.replay_actor = actor
    return call
