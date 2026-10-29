"""Durable schedule/health and content-free deletion replay ledger."""

from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base, Identity, utcnow


class ScheduleSlot(Identity, Base):
    __tablename__ = "schedule_slots"
    slot_key: Mapped[str] = mapped_column(String(40), unique=True)
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    state: Mapped[str] = mapped_column(String(24))
    reason: Mapped[str | None] = mapped_column(String(80))
    execution_id: Mapped[str | None] = mapped_column(ForeignKey("graph_executions.id"))


class RuntimeStatus(Identity, Base):
    __tablename__ = "runtime_status"
    role: Mapped[str] = mapped_column(String(40), unique=True)
    seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    state: Mapped[str] = mapped_column(String(40))
    details: Mapped[dict] = mapped_column(JSON, default=dict)


class DeletionRecord(Identity, Base):
    __tablename__ = "deletion_records"
    deletion_key: Mapped[str] = mapped_column(String(100), unique=True)
    subject_kind: Mapped[str] = mapped_column(String(30))
    subject_id: Mapped[str] = mapped_column(String(36))
    reason: Mapped[str] = mapped_column(String(30))


class CallDependency(Identity, Base):
    __tablename__ = "call_dependencies"
    __table_args__ = (UniqueConstraint("call_id", "kind", "reference_id"),)
    call_id: Mapped[str] = mapped_column(ForeignKey("model_calls.id"), index=True)
    kind: Mapped[str] = mapped_column(String(24))
    reference_id: Mapped[str] = mapped_column(String(36), index=True)
