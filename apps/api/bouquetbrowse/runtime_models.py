"""Application-owned execution facts; graph checkpoints only reference these rows."""

from datetime import datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base, Identity, utcnow


class DiscoverySettings(Identity, Base):
    __tablename__ = "discovery_settings"
    name: Mapped[str] = mapped_column(String(40), unique=True, default="threads")
    version: Mapped[int] = mapped_column(Integer, default=1)
    paused: Mapped[bool] = mapped_column(Boolean, default=True)
    policy: Mapped[dict] = mapped_column(JSON, default=dict)
    configuration: Mapped[dict] = mapped_column(JSON, default=dict)
    release_gates: Mapped[dict] = mapped_column(JSON, default=dict)


class GraphExecution(Identity, Base):
    __tablename__ = "graph_executions"
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id"), unique=True)
    kind: Mapped[str] = mapped_column(String(24))
    behavior_version: Mapped[str] = mapped_column(String(80))
    configuration: Mapped[dict] = mapped_column(JSON)
    state: Mapped[str] = mapped_column(String(30), default="queued")
    input_fingerprint: Mapped[str] = mapped_column(String(64))
    offer_id: Mapped[str | None] = mapped_column(ForeignKey("offer_occurrences.id"), index=True)
    deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    budget_microusd: Mapped[int] = mapped_column(BigInteger)
    progress: Mapped[dict] = mapped_column(JSON, default=dict)
    stop_reason: Mapped[str | None] = mapped_column(String(80))


class DiscoveryFrontier(Identity, Base):
    __tablename__ = "discovery_frontier"
    key: Mapped[str] = mapped_column(String(64), unique=True)
    queue: Mapped[str] = mapped_column(String(24))
    kind: Mapped[str] = mapped_column(String(24))
    target: Mapped[str] = mapped_column(Text)
    origin: Mapped[str] = mapped_column(String(80))
    state: Mapped[str] = mapped_column(String(24), default="due")
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    continuation: Mapped[dict] = mapped_column(JSON, default=dict)
    evidence_gaps: Mapped[list] = mapped_column(JSON, default=list)
    recent_yield: Mapped[int] = mapped_column(Integer, default=0)


class ActionReceipt(Identity, Base):
    __tablename__ = "action_receipts"
    __table_args__ = (UniqueConstraint("execution_id", "action_key"),)
    execution_id: Mapped[str] = mapped_column(ForeignKey("graph_executions.id"), index=True)
    action_key: Mapped[str] = mapped_column(String(80))
    action: Mapped[str] = mapped_column(String(40))
    observation_version: Mapped[str | None] = mapped_column(String(80))
    state: Mapped[str] = mapped_column(String(24))
    capture_id: Mapped[str | None] = mapped_column(ForeignKey("conversation_captures.id"), index=True)
    continuation: Mapped[dict] = mapped_column(JSON, default=dict)


class ModelCall(Identity, Base):
    __tablename__ = "model_calls"
    __table_args__ = (
        UniqueConstraint("scope_key", "request_hash", "attempt"),
        CheckConstraint("attempt >= 1"),
    )
    scope_key: Mapped[str] = mapped_column(String(100), index=True)
    request_hash: Mapped[str] = mapped_column(String(64))
    attempt: Mapped[int] = mapped_column(Integer, default=1)
    execution_id: Mapped[str | None] = mapped_column(ForeignKey("graph_executions.id"), index=True)
    job_id: Mapped[str | None] = mapped_column(ForeignKey("jobs.id"), index=True)
    cost_id: Mapped[str] = mapped_column(ForeignKey("cost_entries.id"), unique=True)
    model: Mapped[str] = mapped_column(String(160))
    state: Mapped[str] = mapped_column(String(24), default="prepared")
    result: Mapped[dict | None] = mapped_column(JSON)
    usage: Mapped[dict] = mapped_column(JSON, default=dict)
    replay_authorized: Mapped[bool] = mapped_column(Boolean, default=False)
    replay_actor: Mapped[str | None] = mapped_column(String(160))
    retention_until: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ExecutionEvent(Identity, Base):
    __tablename__ = "execution_events"
    execution_id: Mapped[str] = mapped_column(ForeignKey("graph_executions.id"), index=True)
    kind: Mapped[str] = mapped_column(String(80))
    details: Mapped[dict] = mapped_column(JSON, default=dict)
