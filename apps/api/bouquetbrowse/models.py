from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base, Identity, utcnow


class Seller(Identity, Base):
    __tablename__ = "sellers"
    name: Mapped[str] = mapped_column(String(160))
    slug: Mapped[str] = mapped_column(String(160), unique=True)
    district: Mapped[str] = mapped_column(String(80))
    city: Mapped[str] = mapped_column(String(80), default="Hanoi")
    bio: Mapped[str] = mapped_column(Text, default="")
    profile_url: Mapped[str | None] = mapped_column(Text)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)


class SourceAccount(Identity, Base):
    __tablename__ = "source_accounts"
    __table_args__ = (
        UniqueConstraint("platform", "username"),
        UniqueConstraint("platform", "platform_account_id", name="uq_platform_account_id"),
    )
    seller_id: Mapped[str | None] = mapped_column(ForeignKey("sellers.id"), index=True)
    platform_account_id: Mapped[str | None] = mapped_column(String(160))
    role: Mapped[str] = mapped_column(String(24), default="unresolved")
    platform: Mapped[str] = mapped_column(String(20))
    username: Mapped[str] = mapped_column(String(100))
    profile_url: Mapped[str | None] = mapped_column(Text)
    capabilities: Mapped[dict] = mapped_column(JSON, default=dict)


class SourcePost(Identity, Base):
    __tablename__ = "source_posts"
    __table_args__ = (UniqueConstraint("platform", "platform_post_id"),)
    account_id: Mapped[str] = mapped_column(ForeignKey("source_accounts.id"), index=True)
    platform: Mapped[str] = mapped_column(String(20))
    platform_post_id: Mapped[str] = mapped_column(String(160))
    url: Mapped[str | None] = mapped_column(Text)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    access_state: Mapped[str] = mapped_column(String(20), default="accessible")
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)


class PostVersion(Identity, Base):
    __tablename__ = "source_post_versions"
    __table_args__ = (UniqueConstraint("post_id", "content_hash"),)
    post_id: Mapped[str] = mapped_column(ForeignKey("source_posts.id"), index=True)
    content_hash: Mapped[str] = mapped_column(String(64))
    caption: Mapped[str] = mapped_column(Text)
    payload: Mapped[dict] = mapped_column(JSON)
    retention_until: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class MediaAsset(Identity, Base):
    __tablename__ = "media_assets"
    checksum: Mapped[str | None] = mapped_column(String(64), index=True)
    perceptual_hash: Mapped[str | None] = mapped_column(String(32), index=True)
    storage_key: Mapped[str | None] = mapped_column(Text)
    source_url: Mapped[str | None] = mapped_column(Text)
    mime: Mapped[str | None] = mapped_column(String(40))
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    state: Mapped[str] = mapped_column(String(24), default="pending")
    rights: Mapped[dict] = mapped_column(JSON, default=dict)
    retention_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PostMedia(Identity, Base):
    __tablename__ = "source_post_media"
    __table_args__ = (UniqueConstraint("version_id", "position"),)
    version_id: Mapped[str] = mapped_column(ForeignKey("source_post_versions.id"), index=True)
    media_id: Mapped[str] = mapped_column(ForeignKey("media_assets.id"), index=True)
    position: Mapped[int] = mapped_column(Integer)


class Listing(Identity, Base):
    __tablename__ = "listings"
    __table_args__ = (
        UniqueConstraint("seller_id", "configuration_key"),
        Index("ix_catalog_facets", "state", "primary_flower", "arrangement", "color"),
    )
    seller_id: Mapped[str] = mapped_column(ForeignKey("sellers.id"), index=True)
    configuration_key: Mapped[str] = mapped_column(String(64))
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    primary_flower: Mapped[str | None] = mapped_column(String(40))
    color: Mapped[str | None] = mapped_column(String(40))
    arrangement: Mapped[str | None] = mapped_column(String(40))
    stem_count: Mapped[int | None] = mapped_column(Integer)
    image_path: Mapped[str | None] = mapped_column(Text)
    style: Mapped[str | None] = mapped_column(String(40))
    occasion: Mapped[str | None] = mapped_column(String(40))
    attributes: Mapped[dict] = mapped_column(JSON, default=dict)
    state: Mapped[str] = mapped_column(String(24), default="review")
    current_revision_id: Mapped[str | None] = mapped_column(String(36))
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    search_text: Mapped[str] = mapped_column(Text, default="")


class ListingSource(Identity, Base):
    __tablename__ = "listing_sources"
    __table_args__ = (UniqueConstraint("listing_id", "version_id", "item_key"),)
    listing_id: Mapped[str] = mapped_column(ForeignKey("listings.id"), index=True)
    version_id: Mapped[str] = mapped_column(ForeignKey("source_post_versions.id"), index=True)
    item_key: Mapped[str] = mapped_column(String(80), default="0")


class ListingRevision(Identity, Base):
    __tablename__ = "listing_revisions"
    listing_id: Mapped[str] = mapped_column(ForeignKey("listings.id"), index=True)
    snapshot: Mapped[dict] = mapped_column(JSON)
    taxonomy_version: Mapped[str] = mapped_column(String(40), default="flowers-v1")
    pipeline_version: Mapped[str] = mapped_column(String(40), default="hybrid-v1")


class ModelVersion(Identity, Base):
    __tablename__ = "model_versions"
    name: Mapped[str] = mapped_column(String(160), unique=True)
    revision: Mapped[str] = mapped_column(String(160))
    dimensions: Mapped[int | None] = mapped_column(Integer)
    configuration: Mapped[dict] = mapped_column(JSON, default=dict)


class ExtractionRun(Identity, Base):
    __tablename__ = "extraction_runs"
    __table_args__ = (UniqueConstraint("input_hash", "pipeline_version", "stage"),)
    version_id: Mapped[str] = mapped_column(ForeignKey("source_post_versions.id"), index=True)
    input_hash: Mapped[str] = mapped_column(String(64))
    pipeline_version: Mapped[str] = mapped_column(String(80))
    stage: Mapped[str] = mapped_column(String(30), default="extraction")
    provider: Mapped[str] = mapped_column(String(40))
    output: Mapped[dict] = mapped_column(JSON)
    errors: Mapped[list] = mapped_column(JSON, default=list)
    cost_usd: Mapped[float] = mapped_column(Float, default=0)


class FieldAssertion(Identity, Base):
    __tablename__ = "field_assertions"
    listing_id: Mapped[str] = mapped_column(ForeignKey("listings.id"), index=True)
    run_id: Mapped[str | None] = mapped_column(ForeignKey("extraction_runs.id"), index=True)
    field: Mapped[str] = mapped_column(String(80))
    value: Mapped[dict] = mapped_column(JSON)
    evidence: Mapped[list] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(30))
    calibrated_confidence: Mapped[float | None] = mapped_column(Float)
    review_state: Mapped[str] = mapped_column(String(24), default="pending")


class PriceObservation(Identity, Base):
    __tablename__ = "price_observations"
    __table_args__ = (
        CheckConstraint("amount_min >= 0"),
        CheckConstraint("amount_max IS NULL OR amount_max >= amount_min"),
    )
    listing_id: Mapped[str] = mapped_column(ForeignKey("listings.id"), index=True)
    version_id: Mapped[str] = mapped_column(ForeignKey("source_post_versions.id"), index=True)
    amount_min: Mapped[int] = mapped_column(BigInteger)
    amount_max: Mapped[int | None] = mapped_column(BigInteger)
    currency: Mapped[str] = mapped_column(String(3), default="VND")
    kind: Mapped[str] = mapped_column(String(24), default="exact")
    component: Mapped[str] = mapped_column(String(24), default="bouquet")
    evidence: Mapped[dict] = mapped_column(JSON)
    reviewed: Mapped[bool] = mapped_column(Boolean, default=False)
    advertised_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    valid_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    superseded: Mapped[bool] = mapped_column(Boolean, default=False)


class AvailabilityObservation(Identity, Base):
    __tablename__ = "availability_observations"
    listing_id: Mapped[str] = mapped_column(ForeignKey("listings.id"), index=True)
    version_id: Mapped[str] = mapped_column(ForeignKey("source_post_versions.id"), index=True)
    status: Mapped[str] = mapped_column(String(30), default="unknown")
    lead_days: Mapped[int | None] = mapped_column(Integer)
    delivery: Mapped[bool | None] = mapped_column(Boolean)
    explicit_delivery_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    evidence: Mapped[dict] = mapped_column(JSON, default=dict)


class TextEmbedding(Identity, Base):
    __tablename__ = "text_embeddings"
    __table_args__ = (UniqueConstraint("revision_id", "model_version"),)
    revision_id: Mapped[str] = mapped_column(ForeignKey("listing_revisions.id"), index=True)
    model_version: Mapped[str] = mapped_column(String(160))
    vector: Mapped[list] = mapped_column(JSON().with_variant(Vector(1536), "postgresql"))


class ImageEmbedding(Identity, Base):
    __tablename__ = "image_embeddings"
    __table_args__ = (UniqueConstraint("media_id", "model_version"),)
    media_id: Mapped[str] = mapped_column(ForeignKey("media_assets.id"), index=True)
    model_version: Mapped[str] = mapped_column(String(160))
    vector: Mapped[list] = mapped_column(JSON().with_variant(Vector(768), "postgresql"))


class ListingSimilarity(Identity, Base):
    __tablename__ = "listing_similarity"
    listing_id: Mapped[str] = mapped_column(ForeignKey("listings.id"), index=True)
    neighbor_id: Mapped[str] = mapped_column(ForeignKey("listings.id"), index=True)
    score: Mapped[float] = mapped_column(Float)
    algorithm_version: Mapped[str] = mapped_column(String(80))
    components: Mapped[dict] = mapped_column(JSON)


class CohortRun(Identity, Base):
    __tablename__ = "cohort_runs"
    listing_id: Mapped[str] = mapped_column(ForeignKey("listings.id"), index=True)
    definition: Mapped[dict] = mapped_column(JSON)
    summary: Mapped[dict] = mapped_column(JSON)
    algorithm_version: Mapped[str] = mapped_column(String(80), default="cohort-v1")


class CohortMember(Identity, Base):
    __tablename__ = "cohort_members"
    run_id: Mapped[str] = mapped_column(ForeignKey("cohort_runs.id"), index=True)
    listing_id: Mapped[str] = mapped_column(ForeignKey("listings.id"), index=True)
    price_id: Mapped[str] = mapped_column(ForeignKey("price_observations.id"))


class Job(Identity, Base):
    __tablename__ = "jobs"
    __table_args__ = (Index("ix_runnable_jobs", "state", "run_after"),)
    kind: Mapped[str] = mapped_column(String(40))
    payload: Mapped[dict] = mapped_column(JSON)
    idempotency_key: Mapped[str] = mapped_column(String(200), unique=True)
    state: Mapped[str] = mapped_column(String(24), default="queued")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    run_after: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lease_token: Mapped[str | None] = mapped_column(String(36))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    result: Mapped[dict | None] = mapped_column(JSON)


class IngestionCursor(Identity, Base):
    __tablename__ = "ingestion_cursors"
    source: Mapped[str] = mapped_column(String(160), unique=True)
    checkpoint: Mapped[dict] = mapped_column(JSON, default=dict)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ReviewAction(Identity, Base):
    __tablename__ = "review_actions"
    listing_id: Mapped[str] = mapped_column(ForeignKey("listings.id"), index=True)
    actor: Mapped[str] = mapped_column(String(160))
    decision: Mapped[str] = mapped_column(String(30))
    reason: Mapped[str] = mapped_column(Text)
    changes: Mapped[dict] = mapped_column(JSON, default=dict)


class TakedownRequest(Identity, Base):
    __tablename__ = "takedown_requests"
    listing_id: Mapped[str] = mapped_column(ForeignKey("listings.id"), index=True)
    reason: Mapped[str] = mapped_column(Text)
    actor: Mapped[str] = mapped_column(String(160))
    state: Mapped[str] = mapped_column(String(30), default="pending")
    idempotency_key: Mapped[str] = mapped_column(String(160), unique=True)


class AppUser(Base):
    __tablename__ = "app_users"
    id: Mapped[str] = mapped_column(String(160), primary_key=True)
    role: Mapped[str] = mapped_column(String(20), default="tester")
    disabled: Mapped[bool] = mapped_column(Boolean, default=False)


class InteractionEvent(Identity, Base):
    __tablename__ = "interaction_events"
    event: Mapped[str] = mapped_column(String(30))
    listing_id: Mapped[str | None] = mapped_column(ForeignKey("listings.id"))


class CostEntry(Identity, Base):
    __tablename__ = "cost_entries"
    provider: Mapped[str] = mapped_column(String(40))
    model: Mapped[str] = mapped_column(String(160))
    amount_usd: Mapped[float] = mapped_column(Float)
    amount_microusd: Mapped[int] = mapped_column(BigInteger, default=0)
    state: Mapped[str] = mapped_column(String(24), default="reserved")
    usage: Mapped[dict] = mapped_column(JSON, default=dict)


class RateBucket(Base):
    __tablename__ = "rate_buckets"
    key: Mapped[str] = mapped_column(String(200), primary_key=True)
    count: Mapped[int] = mapped_column(Integer, default=0)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


# Register conversation tables in the shared metadata.
from . import (  # noqa: E402, F401
    browser_models,
    catalog_event_models,
    conversation_models,
    offer_models,
    operations_models,
    pilot_models,
    recognition_models,
    research_models,
    runtime_models,
)
