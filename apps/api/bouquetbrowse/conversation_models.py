"""Source conversation facts are independent of catalog and graph state."""

from datetime import datetime

from sqlalchemy import JSON, CheckConstraint, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base, Identity, utcnow


class AccountAlias(Identity, Base):
    __tablename__ = "account_aliases"
    __table_args__ = (UniqueConstraint("account_id", "username"),)
    account_id: Mapped[str] = mapped_column(ForeignKey("source_accounts.id"), index=True)
    username: Mapped[str] = mapped_column(String(100))
    evidence: Mapped[dict] = mapped_column(JSON, default=dict)


class MessageEdge(Identity, Base):
    __tablename__ = "message_edges"
    __table_args__ = (
        UniqueConstraint("source_id", "kind", "target_platform_id"),
        CheckConstraint("kind IN ('reply_to', 'quote_of')"),
    )
    source_id: Mapped[str] = mapped_column(ForeignKey("source_posts.id"), index=True)
    target_id: Mapped[str | None] = mapped_column(ForeignKey("source_posts.id"), index=True)
    target_platform_id: Mapped[str] = mapped_column(String(160))
    kind: Mapped[str] = mapped_column(String(24))


class ConversationCapture(Identity, Base):
    __tablename__ = "conversation_captures"
    source_url: Mapped[str] = mapped_column(Text)
    acquisition: Mapped[dict] = mapped_column(JSON)
    sorting: Mapped[str] = mapped_column(String(40), default="unknown")
    stop_reason: Mapped[str] = mapped_column(String(80))
    remaining_expansions: Mapped[int | None] = mapped_column(Integer)
    coverage: Mapped[dict] = mapped_column(JSON, default=dict)
    retention_until: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class CaptureMember(Identity, Base):
    __tablename__ = "capture_members"
    __table_args__ = (UniqueConstraint("capture_id", "version_id"),)
    capture_id: Mapped[str] = mapped_column(ForeignKey("conversation_captures.id"), index=True)
    version_id: Mapped[str] = mapped_column(ForeignKey("source_post_versions.id"), index=True)


class OfferOccurrence(Identity, Base):
    __tablename__ = "offer_occurrences"
    __table_args__ = (UniqueConstraint("account_id", "anchor_id", "slot_key"),)
    account_id: Mapped[str] = mapped_column(ForeignKey("source_accounts.id"), index=True)
    seller_id: Mapped[str | None] = mapped_column(ForeignKey("sellers.id"), index=True)
    anchor_id: Mapped[str] = mapped_column(ForeignKey("source_posts.id"), index=True)
    slot_key: Mapped[str] = mapped_column(String(100))
    kind: Mapped[str] = mapped_column(String(30), default="seller_work")
    listing_id: Mapped[str | None] = mapped_column(ForeignKey("listings.id"), unique=True)
    state: Mapped[str] = mapped_column(String(30), default="candidate")
    input_fingerprint: Mapped[str] = mapped_column(String(64), default="")
    association_revision: Mapped[int] = mapped_column(Integer, default=1)


class OfferAssociation(Identity, Base):
    __tablename__ = "offer_associations"
    __table_args__ = (UniqueConstraint("offer_id", "revision", "version_id", "item_key"),)
    offer_id: Mapped[str] = mapped_column(ForeignKey("offer_occurrences.id"), index=True)
    revision: Mapped[int] = mapped_column(Integer)
    version_id: Mapped[str] = mapped_column(ForeignKey("source_post_versions.id"), index=True)
    media_id: Mapped[str | None] = mapped_column(ForeignKey("media_assets.id"), index=True)
    item_key: Mapped[str] = mapped_column(String(100), default="message")
    role: Mapped[str] = mapped_column(String(30))
    basis: Mapped[str] = mapped_column(String(40))
    region: Mapped[list | None] = mapped_column(JSON)
    state: Mapped[str] = mapped_column(String(24), default="pending")
    evidence: Mapped[dict] = mapped_column(JSON, default=dict)


class CanonicalConfiguration(Identity, Base):
    __tablename__ = "canonical_configurations"
    seller_id: Mapped[str] = mapped_column(ForeignKey("sellers.id"), index=True)
    evidence: Mapped[dict] = mapped_column(JSON)


class CanonicalLink(Identity, Base):
    __tablename__ = "canonical_links"
    offer_id: Mapped[str] = mapped_column(ForeignKey("offer_occurrences.id"), index=True)
    configuration_id: Mapped[str] = mapped_column(ForeignKey("canonical_configurations.id"), index=True)
    state: Mapped[str] = mapped_column(String(24))
    basis: Mapped[str] = mapped_column(String(30))
    evidence: Mapped[dict] = mapped_column(JSON)


class OfferClaim(Identity, Base):
    __tablename__ = "offer_claims"
    offer_id: Mapped[str] = mapped_column(ForeignKey("offer_occurrences.id"), index=True)
    field: Mapped[str] = mapped_column(String(80))
    value: Mapped[dict] = mapped_column(JSON)
    evidence: Mapped[list] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(30))
    review_state: Mapped[str] = mapped_column(String(24), default="pending")
    valid_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    valid_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    supersedes_id: Mapped[str | None] = mapped_column(ForeignKey("offer_claims.id"), index=True)
    method_version: Mapped[str] = mapped_column(String(160))


class TaxonomyTerm(Identity, Base):
    __tablename__ = "taxonomy_terms"
    __table_args__ = (UniqueConstraint("taxonomy_version", "key"),)
    taxonomy_version: Mapped[str] = mapped_column(String(80))
    key: Mapped[str] = mapped_column(String(80))
    aliases: Mapped[list] = mapped_column(JSON)
    state: Mapped[str] = mapped_column(String(24), default="proposed")
    evaluation: Mapped[dict] = mapped_column(JSON, default=dict)
