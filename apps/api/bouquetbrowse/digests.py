"""Digest membership freezes once; late enrichment belongs to the next snapshot."""

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select, text

from .catalog_event_models import CatalogChange, DailyDigest, DigestMember
from .db import aware, utcnow
from .models import Listing
from .visibility import visible

HANOI = ZoneInfo("Asia/Ho_Chi_Minh")


def build_digest(db, day: date, coverage=None, now=None):
    now = now or utcnow()
    if day > now.astimezone(HANOI).date():
        raise ValueError("Cannot publish a future digest")
    if db.bind.dialect.name == "postgresql":
        db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": 80000000 + day.toordinal()})
    existing = db.scalar(select(DailyDigest).where(DailyDigest.day == day))
    if existing:
        return existing
    cutoff = min(now, datetime.combine(day + timedelta(days=1), time.min, HANOI))
    coverage = coverage or {"scheduled": 5, "completed": 0, "missed": 5}
    partial = coverage.get("completed", 0) < coverage.get("scheduled", 5) or coverage.get("missed", 0) > 0
    digest = DailyDigest(
        day=day,
        cutoff=cutoff,
        partial=partial,
        coverage=coverage,
        note="Partial collection: missed or unavailable runs are not represented as collected data."
        if partial
        else "Observed catalog changes; advertised facts are not inventory confirmations.",
    )
    db.add(digest)
    db.flush()
    assigned = select(DigestMember.event_id)
    events = db.scalars(
        select(CatalogChange)
        .where(
            CatalogChange.created_at <= cutoff, CatalogChange.suppressed.is_(False), CatalogChange.id.not_in(assigned)
        )
        .order_by(CatalogChange.created_at, CatalogChange.id)
    )
    for event in events:
        db.add(DigestMember(digest_id=digest.id, event_id=event.id))
    return digest


def event_view(db, event):
    if event.suppressed or event.listing_id and not visible(db, db.get(Listing, event.listing_id)):
        return None
    return {
        "id": event.id,
        "kind": event.kind,
        "listing_id": event.listing_id,
        "seller_id": event.seller_id,
        "source_url": event.source_url,
        "advertised_at": aware(event.advertised_at).isoformat() if event.advertised_at else None,
        "observed_at": aware(event.created_at).isoformat(),
        "details": event.details,
    }


def recent_changes(db, listing_id=None, seller_id=None, limit=10):
    query = select(CatalogChange).where(CatalogChange.suppressed.is_(False))
    query = (
        query.where(CatalogChange.listing_id == listing_id)
        if listing_id
        else query.where(CatalogChange.seller_id == seller_id)
    )
    return [
        view
        for event in db.scalars(query.order_by(CatalogChange.created_at.desc()).limit(limit))
        if (view := event_view(db, event))
    ]


def digest_view(db, digest):
    events = db.scalars(
        select(CatalogChange)
        .join(DigestMember, DigestMember.event_id == CatalogChange.id)
        .where(DigestMember.digest_id == digest.id)
        .order_by(CatalogChange.created_at, CatalogChange.id)
    )
    return {
        "date": digest.day.isoformat(),
        "partial": digest.partial,
        "coverage": digest.coverage,
        "published_at": aware(digest.created_at).isoformat(),
        "note": digest.note,
        "items": [view for event in events if (view := event_view(db, event))],
    }
