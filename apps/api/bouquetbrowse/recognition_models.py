"""Versioned visual observations and regions; evaluation never publishes catalog facts."""

from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base, Identity


class ImageRegion(Identity, Base):
    __tablename__ = "image_regions"
    __table_args__ = (UniqueConstraint("media_id", "checksum", "region_key", "kind"),)
    media_id: Mapped[str] = mapped_column(ForeignKey("media_assets.id"), index=True)
    checksum: Mapped[str] = mapped_column(String(64))
    region_key: Mapped[str] = mapped_column(String(64))
    bounds: Mapped[list] = mapped_column(JSON)
    kind: Mapped[str] = mapped_column(String(24), default="analysis")
    state: Mapped[str] = mapped_column(String(24), default="proposed")
    evidence: Mapped[dict] = mapped_column(JSON, default=dict)
    retention_until: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class RecognitionRecord(Identity, Base):
    __tablename__ = "recognition_records"
    cache_key: Mapped[str] = mapped_column(String(64), unique=True)
    offer_id: Mapped[str | None] = mapped_column(ForeignKey("offer_occurrences.id"), index=True)
    purpose: Mapped[str] = mapped_column(String(24))
    configuration_hash: Mapped[str] = mapped_column(String(64))
    result: Mapped[dict] = mapped_column(JSON)
    dependencies: Mapped[dict] = mapped_column(JSON)
    retention_until: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class RecognitionSupport(Identity, Base):
    __tablename__ = "recognition_support"
    __table_args__ = (UniqueConstraint("configuration_hash", "taxonomy_version", "flower"),)
    configuration_hash: Mapped[str] = mapped_column(String(64))
    taxonomy_version: Mapped[str] = mapped_column(String(80))
    flower: Mapped[str] = mapped_column(String(80))
    state: Mapped[str] = mapped_column(String(24), default="tentative")
    report: Mapped[dict] = mapped_column(JSON)
