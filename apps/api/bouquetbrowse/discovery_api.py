"""Authenticated local discovery administration. No browser session material is exposed."""

from importlib.util import find_spec
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import Field
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from .auth import require_admin
from .config import get_settings
from .db import get_db
from .discovery import add_frontier, seed_frontier, settings_row
from .executions import create_execution
from .leases import cancel
from .pipeline import digest
from .providers import CapabilityError
from .runtime_models import DiscoveryFrontier, DiscoverySettings, ExecutionEvent, GraphExecution
from .schemas import StrictModel

Database = Annotated[Session, Depends(get_db)]

router = APIRouter(prefix="/v1/admin/discovery", dependencies=[Depends(require_admin)])


class RunBody(StrictModel):
    seed_queries: list[Annotated[str, Field(max_length=120)]] = Field(default_factory=list, max_length=10)


class SettingsBody(StrictModel):
    expected_version: int = Field(ge=0)
    paused: bool


class StatusView(StrictModel):
    enabled: bool
    paused: bool
    settings_version: int
    postgres: bool
    model_configured: bool
    browser_installed: bool
    release_gates: dict
    publication_enabled: bool


class SettingsView(StrictModel):
    paused: bool
    settings_version: int


class RunAcceptedView(StrictModel):
    execution_id: str
    job_id: str
    state: str


@router.get("/status", response_model=StatusView)
def status(db: Database):
    settings = get_settings()
    row = db.scalar(select(DiscoverySettings).where(DiscoverySettings.name == "threads"))
    return {
        "enabled": settings.discovery_enabled,
        "paused": row.paused if row else True,
        "settings_version": row.version if row else 0,
        "postgres": db.bind.dialect.name == "postgresql",
        "model_configured": bool(settings.openai_api_key),
        "browser_installed": find_spec("playwright") is not None,
        "release_gates": row.release_gates if row else {},
        "publication_enabled": False,
    }


@router.patch("/settings", response_model=SettingsView)
def configure(body: SettingsBody, db: Database):
    row = settings_row(db)
    changed = db.execute(
        update(DiscoverySettings)
        .where(DiscoverySettings.id == row.id, DiscoverySettings.version == body.expected_version)
        .values(paused=body.paused, version=body.expected_version + 1)
    )
    if changed.rowcount != 1:
        raise HTTPException(409, detail="Discovery settings changed; reload before updating.")
    db.commit()
    return {"paused": body.paused, "settings_version": body.expected_version + 1}


@router.post("/runs", status_code=202, response_model=RunAcceptedView)
def start_run(body: RunBody, db: Database, idempotency_key: Annotated[str | None, Header()] = None):
    settings = get_settings()
    if not idempotency_key or len(idempotency_key) > 160:
        raise HTTPException(400, detail="Provide an Idempotency-Key of at most 160 characters.")
    if not settings.discovery_enabled:
        raise CapabilityError("Enable DISCOVERY_ENABLED after local browser setup.", "discovery_not_configured")
    if db.bind.dialect.name != "postgresql":
        raise CapabilityError("Browser discovery requires PostgreSQL.", "postgres_required")
    if not settings.openai_api_key:
        raise CapabilityError("Configure OPENAI_API_KEY for the discovery planner.", "model_not_configured")
    if find_spec("playwright") is None:
        raise CapabilityError("Install the optional browser runtime and Chromium.", "browser_not_installed")
    row = settings_row(db)
    if row.paused:
        raise HTTPException(409, detail="Discovery is paused; resume it first.")
    seed_frontier(db)
    for query in body.seed_queries:
        add_frontier(db, "search", query, origin="operator")
    execution = create_execution(
        db,
        "discovery",
        idempotency_key,
        {
            "planner_model": settings.planner_model,
            "extraction_model": settings.extraction_model,
            "escalation_model": settings.escalation_model,
            "taxonomy_version": "flowers-v2",
            "prompt_version": "discovery-v1",
            "schema_version": "conversation-v1",
            "policy_ref": row.policy["policy_ref"],
            "manual": True,
            "budget_usd": settings.discovery_run_budget_usd,
        },
        digest(body.model_dump(mode="json")),
    )
    db.commit()
    return {"execution_id": execution.id, "job_id": execution.job_id, "state": execution.state}


@router.get("/runs")
def runs(db: Database):
    rows = db.scalars(
        select(GraphExecution)
        .where(GraphExecution.kind == "discovery")
        .order_by(GraphExecution.created_at.desc())
        .limit(50)
    )
    return {
        "items": [
            {
                "id": r.id,
                "job_id": r.job_id,
                "state": r.state,
                "stop_reason": r.stop_reason,
                "created_at": r.created_at,
                "deadline": r.deadline,
                "progress": r.progress,
            }
            for r in rows
        ]
    }


@router.get("/runs/{execution_id}")
def run_detail(execution_id: str, db: Database):
    execution = db.get(GraphExecution, execution_id)
    if not execution or execution.kind != "discovery":
        raise HTTPException(404, detail="Discovery run not found.")
    events = db.scalars(
        select(ExecutionEvent)
        .where(ExecutionEvent.execution_id == execution_id)
        .order_by(ExecutionEvent.created_at.desc())
        .limit(100)
    )
    return {
        "id": execution.id,
        "state": execution.state,
        "stop_reason": execution.stop_reason,
        "progress": execution.progress,
        "events": [{"kind": e.kind, "details": e.details, "at": e.created_at} for e in events],
    }


@router.post("/runs/{execution_id}/cancel")
def cancel_run(execution_id: str, db: Database):
    execution = db.get(GraphExecution, execution_id)
    if not execution or execution.kind != "discovery":
        raise HTTPException(404, detail="Discovery run not found.")
    cancel(db, execution.job_id)
    execution.state, execution.stop_reason = "cancelled", "operator_cancelled"
    db.commit()
    return {"id": execution.id, "state": execution.state}


@router.get("/frontier")
def frontier(db: Database):
    rows = db.scalars(select(DiscoveryFrontier).order_by(DiscoveryFrontier.due_at).limit(100))
    return {
        "items": [
            {
                "id": r.id,
                "kind": r.kind,
                "queue": r.queue,
                "target": r.target,
                "due_at": r.due_at,
                "last_checked_at": r.last_checked_at,
                "evidence_gaps": r.evidence_gaps,
            }
            for r in rows
        ]
    }
