"""Audited summaries only. Real annotations stay in private operator storage."""

from sqlalchemy import JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base, Identity


class PilotProof(Identity, Base):
    __tablename__ = "pilot_proofs"
    __table_args__ = (UniqueConstraint("kind", "configuration_hash", "dataset_hash"),)
    kind: Mapped[str] = mapped_column(String(24))
    configuration_hash: Mapped[str] = mapped_column(String(64), index=True)
    behavior_version: Mapped[str] = mapped_column(String(80))
    dataset_hash: Mapped[str] = mapped_column(String(64))
    report_hash: Mapped[str] = mapped_column(String(64))
    report: Mapped[dict] = mapped_column(JSON)
    dependencies: Mapped[dict] = mapped_column(JSON)
    state: Mapped[str] = mapped_column(String(24), default="pending")
    actor: Mapped[str | None] = mapped_column(String(160))
    attestation: Mapped[dict] = mapped_column(JSON, default=dict)
