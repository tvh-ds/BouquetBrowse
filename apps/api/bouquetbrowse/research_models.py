"""Private evaluation work and immutable, association-bound crop features."""

from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base, Identity


class CropEmbedding(Identity, Base):
    __tablename__ = "crop_embeddings"
    __table_args__ = (UniqueConstraint("association_id", "checksum", "region_hash", "model_version"),)
    association_id: Mapped[str] = mapped_column(ForeignKey("offer_associations.id"), index=True)
    media_id: Mapped[str] = mapped_column(ForeignKey("media_assets.id"), index=True)
    checksum: Mapped[str] = mapped_column(String(64))
    region_hash: Mapped[str] = mapped_column(String(64))
    model_version: Mapped[str] = mapped_column(String(160))
    vector: Mapped[list] = mapped_column(JSON().with_variant(Vector(768), "postgresql"))
    retention_until: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class EvaluationDataset(Identity, Base):
    __tablename__ = "evaluation_datasets"
    name: Mapped[str] = mapped_column(String(80))
    dataset_kind: Mapped[str] = mapped_column(String(24))
    configuration: Mapped[dict] = mapped_column(JSON)
    version: Mapped[int] = mapped_column(Integer, default=1)
    actor: Mapped[str] = mapped_column(String(160))
    proof_id: Mapped[str | None] = mapped_column(ForeignKey("pilot_proofs.id"))
    export_keys: Mapped[list] = mapped_column(JSON, default=list)
    retention_until: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class EvaluationItem(Identity, Base):
    __tablename__ = "evaluation_items"
    __table_args__ = (UniqueConstraint("dataset_id", "media_id"),)
    dataset_id: Mapped[str] = mapped_column(ForeignKey("evaluation_datasets.id"), index=True)
    offer_id: Mapped[str] = mapped_column(ForeignKey("offer_occurrences.id"), index=True)
    media_id: Mapped[str] = mapped_column(ForeignKey("media_assets.id"), index=True)
    offer_fingerprint: Mapped[str] = mapped_column(String(64))
    checksum: Mapped[str] = mapped_column(String(64))
    seller_group: Mapped[str] = mapped_column(String(160))
    image_family: Mapped[str] = mapped_column(String(160))
    split: Mapped[str] = mapped_column(String(24))
    labels: Mapped[list | None] = mapped_column(JSON)
    assessable: Mapped[list] = mapped_column(JSON, default=list)
    reviewers: Mapped[list] = mapped_column(JSON, default=list)
    history: Mapped[list] = mapped_column(JSON, default=list)
    version: Mapped[int] = mapped_column(Integer, default=1)
    execution_id: Mapped[str | None] = mapped_column(ForeignKey("graph_executions.id"), index=True)
    joint_record_id: Mapped[str | None] = mapped_column(ForeignKey("recognition_records.id"))
    image_only_record_id: Mapped[str | None] = mapped_column(ForeignKey("recognition_records.id"))
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    cost_microusd: Mapped[int] = mapped_column(Integer, default=0)
    state: Mapped[str] = mapped_column(String(24), default="unannotated")
    retention_until: Mapped[datetime] = mapped_column(DateTime(timezone=True))
