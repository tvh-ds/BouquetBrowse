"""Offer processing artifacts are authoritative domain receipts, not graph state."""

from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base, Identity


class OfferAnalysis(Identity, Base):
    __tablename__ = "offer_analyses"
    __table_args__ = (UniqueConstraint("execution_id"),)
    execution_id: Mapped[str] = mapped_column(ForeignKey("graph_executions.id"), index=True)
    offer_id: Mapped[str] = mapped_column(ForeignKey("offer_occurrences.id"), index=True)
    fingerprint: Mapped[str] = mapped_column(String(64))
    state: Mapped[str] = mapped_column(String(30), default="pending")
    output: Mapped[dict] = mapped_column(JSON, default=dict)
    errors: Mapped[list] = mapped_column(JSON, default=list)
    revision_id: Mapped[str | None] = mapped_column(ForeignKey("listing_revisions.id"))
    retention_until: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class AssociationReview(Identity, Base):
    __tablename__ = "association_reviews"
    __table_args__ = (UniqueConstraint("offer_id", "fingerprint", "kind"),)
    offer_id: Mapped[str] = mapped_column(ForeignKey("offer_occurrences.id"), index=True)
    fingerprint: Mapped[str] = mapped_column(String(64))
    kind: Mapped[str] = mapped_column(String(50))
    state: Mapped[str] = mapped_column(String(24), default="pending")
    proposal: Mapped[dict] = mapped_column(JSON, default=dict)
    decision: Mapped[dict] = mapped_column(JSON, default=dict)
    actor: Mapped[str | None] = mapped_column(String(160))
