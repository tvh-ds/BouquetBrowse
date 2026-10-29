"""Durable change events and Hanoi-day digest projections."""

from datetime import date, datetime

from sqlalchemy import JSON, Boolean, Date, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base, Identity


class CatalogChange(Identity, Base):
    __tablename__ = "catalog_changes"
    event_key: Mapped[str] = mapped_column(String(160), unique=True)
    kind: Mapped[str] = mapped_column(String(40))
    listing_id: Mapped[str | None] = mapped_column(ForeignKey("listings.id"), index=True)
    seller_id: Mapped[str | None] = mapped_column(ForeignKey("sellers.id"), index=True)
    source_url: Mapped[str | None] = mapped_column(String(2048))
    advertised_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    suppressed: Mapped[bool] = mapped_column(Boolean, default=False)


class DailyDigest(Identity, Base):
    __tablename__ = "daily_digests"
    day: Mapped[date] = mapped_column(Date, unique=True)
    partial: Mapped[bool] = mapped_column(Boolean)
    coverage: Mapped[dict] = mapped_column(JSON)
    cutoff: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    note: Mapped[str] = mapped_column(String(300))


class DigestMember(Identity, Base):
    __tablename__ = "digest_members"
    __table_args__ = (UniqueConstraint("event_id"),)
    digest_id: Mapped[str] = mapped_column(ForeignKey("daily_digests.id"), index=True)
    event_id: Mapped[str] = mapped_column(ForeignKey("catalog_changes.id"), index=True)


class SellerFact(Identity, Base):
    __tablename__ = "seller_facts"
    __table_args__ = (UniqueConstraint("seller_id", "field", "evidence_key"),)
    seller_id: Mapped[str] = mapped_column(ForeignKey("sellers.id"), index=True)
    field: Mapped[str] = mapped_column(String(40))
    value: Mapped[dict] = mapped_column(JSON)
    evidence_key: Mapped[str] = mapped_column(String(64))
    evidence: Mapped[dict] = mapped_column(JSON)
    retention_until: Mapped[datetime] = mapped_column(DateTime(timezone=True))
