"""Short-lived browser observations and attributable profile versions."""

from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base, Identity


class BrowserObservation(Identity, Base):
    __tablename__ = "browser_observations"
    execution_id: Mapped[str] = mapped_column(ForeignKey("graph_executions.id"), index=True)
    capture_id: Mapped[str | None] = mapped_column(ForeignKey("conversation_captures.id"), index=True)
    signature: Mapped[str] = mapped_column(String(64))
    snapshot: Mapped[dict] = mapped_column(JSON)
    retention_until: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ProfileSnapshot(Identity, Base):
    __tablename__ = "profile_snapshots"
    __table_args__ = (UniqueConstraint("account_id", "content_hash"),)
    account_id: Mapped[str] = mapped_column(ForeignKey("source_accounts.id"), index=True)
    content_hash: Mapped[str] = mapped_column(String(64))
    source_url: Mapped[str] = mapped_column(Text)
    text: Mapped[str] = mapped_column(Text)
    policy: Mapped[dict] = mapped_column(JSON)
    retention_until: Mapped[datetime] = mapped_column(DateTime(timezone=True))
