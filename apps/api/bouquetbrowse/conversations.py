"""Transactional conversation commands; callers own short transactions."""

from datetime import timedelta

from sqlalchemy import select, text

from .conversation_contracts import CaptureEnvelope, QuoteReference
from .conversation_models import (
    AccountAlias,
    CanonicalConfiguration,
    CanonicalLink,
    CaptureMember,
    ConversationCapture,
    MessageEdge,
    OfferAssociation,
    OfferOccurrence,
)
from .db import aware, utcnow
from .models import Listing, ListingSource, PostVersion, SourceAccount, SourcePost
from .pipeline import digest
from .source_identity import find_parent, find_source


def anchor_quote(db, reference: QuoteReference):
    version = db.get(PostVersion, reference.version_id)
    if not version or aware(version.retention_until) <= utcnow() or not version.caption:
        raise ValueError("Evidence version is unavailable")
    text, matches, offset = version.caption, [], 0
    while (position := text.find(reference.quote, offset)) >= 0:
        end = position + len(reference.quote)
        if (reference.before is None or text[:position].endswith(reference.before)) and (
            reference.after is None or text[end:].startswith(reference.after)
        ):
            matches.append((position, end))
        offset = position + 1
    if len(matches) != 1:
        raise ValueError("Evidence quote must match one unambiguous span")
    start, end = matches[0]
    return {"version_id": version.id, "quote": reference.quote, "start": start, "end": end}


def record_capture(db, envelope: CaptureEnvelope, acquisition: dict):
    if not acquisition.get("processing_allowed") or not acquisition.get("policy_ref"):
        raise ValueError("An explicit processing policy is required")
    if db.bind.dialect.name == "postgresql":
        identities = {f"account:{m.username}" for m in envelope.messages}
        identities |= {f"message:{m.platform_id}" for m in envelope.messages}
        identities |= {f"account-id:{m.platform_account_id}" for m in envelope.messages if m.platform_account_id}
        for identity in sorted(identities):
            db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": int(digest(identity)[:15], 16)})
    capture = ConversationCapture(
        source_url=envelope.source_url,
        acquisition=acquisition,
        sorting=envelope.sorting,
        stop_reason=envelope.stop_reason,
        remaining_expansions=envelope.remaining_expansions,
        coverage={"branches": envelope.observed_branches, "complete": envelope.stop_reason == "exhausted"},
        retention_until=utcnow() + timedelta(days=30),
    )
    db.add(capture)
    db.flush()
    for observation in envelope.messages:
        account = db.scalar(
            select(SourceAccount).where(
                SourceAccount.platform == "threads", SourceAccount.username == observation.username
            )
        )
        if observation.platform_account_id:
            stable = db.scalar(
                select(SourceAccount).where(
                    SourceAccount.platform == "threads",
                    SourceAccount.platform_account_id == observation.platform_account_id,
                )
            )
            if stable and account and stable.id != account.id:
                raise ValueError("Conflicting account identities require review")
            account = stable or account
        if not account:
            account = SourceAccount(platform="threads", username=observation.username, seller_id=None)
            db.add(account)
            db.flush()
        if observation.platform_account_id:
            if account.platform_account_id not in {None, observation.platform_account_id}:
                raise ValueError("Account identity cannot be reassigned")
            account.platform_account_id = observation.platform_account_id
        if not db.scalar(
            select(AccountAlias.id).where(
                AccountAlias.account_id == account.id, AccountAlias.username == observation.username
            )
        ):
            db.add(
                AccountAlias(account_id=account.id, username=observation.username, evidence={"capture_id": capture.id})
            )
        post = find_source(db, "threads", observation.platform_id, observation.url)
        if post and (post.account_id != account.id or post.access_state == "removed"):
            raise ValueError("Source identity is conflicting or suppressed")
        if not post:
            post = SourcePost(
                platform="threads",
                platform_post_id=observation.platform_id,
                account_id=account.id,
                url=observation.url,
                published_at=observation.published_at,
            )
            db.add(post)
            db.flush()
        post.last_seen_at = utcnow()
        if post.published_at is None:
            post.published_at = observation.published_at
        content_hash = digest(
            {
                "text": observation.text,
                "media": observation.media_urls,
                "published_at": observation.published_at,
                "reply_to": observation.reply_to,
                "quote_of": observation.quote_of,
            }
        )
        version = db.scalar(
            select(PostVersion).where(PostVersion.post_id == post.id, PostVersion.content_hash == content_hash)
        )
        if not version:
            version = PostVersion(
                post_id=post.id,
                content_hash=content_hash,
                caption=observation.text,
                payload={
                    "media_urls": observation.media_urls,
                    "acquisition": acquisition,
                    "published_at": observation.published_at.isoformat() if observation.published_at else None,
                    "observed_platform_id": observation.platform_id,
                    "source_url": observation.url,
                },
                retention_until=capture.retention_until,
            )
            db.add(version)
            db.flush()
        if not db.scalar(
            select(CaptureMember.id).where(
                CaptureMember.capture_id == capture.id, CaptureMember.version_id == version.id
            )
        ):
            db.add(CaptureMember(capture_id=capture.id, version_id=version.id))
        for kind, target in [("reply_to", observation.reply_to), ("quote_of", observation.quote_of)]:
            if target and not db.scalar(
                select(MessageEdge.id).where(
                    MessageEdge.source_id == post.id, MessageEdge.kind == kind, MessageEdge.target_platform_id == target
                )
            ):
                db.add(MessageEdge(source_id=post.id, kind=kind, target_platform_id=target))
    db.flush()
    # Ancestors can arrive through a different discovery path or a later capture.
    for edge in db.scalars(select(MessageEdge).where(MessageEdge.target_id.is_(None))):
        edge.target_id = find_parent(db, edge.target_platform_id)
    return capture


def ensure_occurrence(db, account_id, anchor_id, slot_key="whole", kind="seller_work"):
    account, anchor = db.get(SourceAccount, account_id), db.get(SourcePost, anchor_id)
    if not account or not anchor or anchor.account_id != account.id:
        raise ValueError("Offer anchor must belong to its advertising account")
    occurrence = db.scalar(
        select(OfferOccurrence).where(
            OfferOccurrence.account_id == account_id,
            OfferOccurrence.anchor_id == anchor_id,
            OfferOccurrence.slot_key == slot_key,
        )
    )
    if not occurrence:
        occurrence = OfferOccurrence(
            account_id=account_id, anchor_id=anchor_id, slot_key=slot_key, seller_id=account.seller_id, kind=kind
        )
        db.add(occurrence)
        db.flush()
    return occurrence


def link_canonical(db, offer_id, configuration_id, basis, evidence):
    offer, configuration = db.get(OfferOccurrence, offer_id), db.get(CanonicalConfiguration, configuration_id)
    if not offer or not configuration or not offer.seller_id or offer.seller_id != configuration.seller_id:
        raise ValueError("Canonical links must stay within one seller")
    if basis not in {"explicit_product", "reviewed_match"} or not evidence:
        raise ValueError("Similarity alone cannot establish product identity")
    link = CanonicalLink(
        offer_id=offer.id, configuration_id=configuration.id, state="accepted", basis=basis, evidence=evidence
    )
    db.add(link)
    return link


def backfill_legacy(db):
    """Preserve existing catalog URLs; mark associations as legacy evidence."""
    for link in db.scalars(select(ListingSource)):
        version = db.get(PostVersion, link.version_id)
        post = db.get(SourcePost, version.post_id)
        listing = db.get(Listing, link.listing_id)
        # A consolidated legacy listing may have multiple source occurrences.
        offer = ensure_occurrence(db, post.account_id, post.id, f"legacy:{link.item_key}")
        if not db.scalar(select(OfferOccurrence.id).where(OfferOccurrence.listing_id == listing.id)):
            offer.listing_id = listing.id
        if not db.scalar(
            select(OfferAssociation.id).where(
                OfferAssociation.offer_id == offer.id, OfferAssociation.version_id == version.id
            )
        ):
            db.add(
                OfferAssociation(
                    offer_id=offer.id,
                    revision=1,
                    version_id=version.id,
                    role="legacy_source",
                    basis="operator_import",
                    state="accepted",
                    evidence={"listing_source_id": link.id},
                )
            )
        db.flush()
