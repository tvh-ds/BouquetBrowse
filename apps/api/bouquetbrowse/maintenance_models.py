"""Content-free operational alerts; application jobs are their delivery outbox."""

from datetime import datetime

from sqlalchemy import JSON, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base, Identity


class OperationAlert(Identity, Base):
    __tablename__ = "operation_alerts"
    code: Mapped[str] = mapped_column(String(60), unique=True)
    severity: Mapped[str] = mapped_column(String(20))
    state: Mapped[str] = mapped_column(String(20), default="open")
    version: Mapped[int] = mapped_column(Integer, default=1)
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    acknowledged_by: Mapped[str | None] = mapped_column(String(160))
