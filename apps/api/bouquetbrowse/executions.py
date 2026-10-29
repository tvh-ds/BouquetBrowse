"""Execution creation is a domain command, not a LangGraph checkpoint edit."""

from datetime import timedelta
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import select

from .db import utcnow
from .graphs import BEHAVIOR_VERSION
from .model_calls import microusd
from .pipeline import digest, enqueue
from .runtime_models import GraphExecution


def create_execution(db, kind, command_key, configuration, input_fingerprint, offer_id=None):
    from .config import get_settings

    configuration = dict(configuration)
    if kind in {"offer", "evaluation"}:
        settings = get_settings()
        for key, value in {
            "recognition_version": "mixed-flowers-v1",
            "preprocessing_version": "jpeg-1200-v1",
            "image_embedding_provider": settings.image_embedding_provider,
            "siglip_revision": settings.siglip_revision,
        }.items():
            configuration.setdefault(key, value)
    if kind not in {"discovery", "offer", "evaluation"}:
        raise ValueError("Unknown graph execution kind")
    if not command_key or len(command_key) > 160:
        raise ValueError("A bounded idempotency key is required")
    allowed = {
        "planner_model",
        "extraction_model",
        "escalation_model",
        "taxonomy_version",
        "prompt_version",
        "schema_version",
        "policy_ref",
        "budget_usd",
        "slot",
        "manual",
        "source_capture_id",
        "recognition_version",
        "preprocessing_version",
        "image_embedding_provider",
        "siglip_revision",
    }
    if set(configuration) - allowed:
        raise ValueError("Execution configuration cannot contain credentials or arbitrary source data")
    fingerprint = digest(
        {
            "kind": kind,
            "configuration": configuration,
            "input": input_fingerprint,
            "offer_id": offer_id,
            "behavior": BEHAVIOR_VERSION,
        }
    )
    execution_id = str(uuid5(NAMESPACE_URL, f"bouquetbrowse:graph:{kind}:{command_key}"))
    existing = db.get(GraphExecution, execution_id)
    if existing:
        if existing.input_fingerprint != fingerprint:
            raise ValueError("Execution key was reused for different inputs")
        return existing
    limit = 0.35 if kind == "discovery" else 0.10
    budget = configuration.get("budget_usd", limit)
    if microusd(budget) <= 0 or microusd(budget) > microusd(limit):
        raise ValueError("Execution allowance exceeds the configured per-work ceiling")
    job = enqueue(db, f"{kind}-graph", {"execution_id": execution_id}, f"graph:{kind}:{command_key}")
    # Concurrent callers serialize on the job's unique key before reaching here.
    existing = db.get(GraphExecution, execution_id)
    if existing:
        if existing.input_fingerprint != fingerprint:
            raise ValueError("Execution key was reused for different inputs")
        return existing
    execution = GraphExecution(
        id=execution_id,
        job_id=job.id,
        kind=kind,
        behavior_version=BEHAVIOR_VERSION,
        configuration=configuration,
        input_fingerprint=fingerprint,
        offer_id=offer_id,
        deadline=utcnow() + timedelta(minutes=20) if kind == "discovery" else None,
        budget_microusd=microusd(budget),
        progress={"offer_fingerprint": input_fingerprint} if kind == "offer" else {},
    )
    db.add(execution)
    db.flush()
    return execution


def pinned_execution(db, execution_id):
    execution = db.scalar(select(GraphExecution).where(GraphExecution.id == execution_id))
    if not execution or execution.behavior_version != BEHAVIOR_VERSION:
        raise ValueError("This execution needs its compatible pinned graph or an explicit migration")
    return execution
