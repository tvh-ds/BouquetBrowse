import argparse
import logging
import random
import time
from datetime import timedelta

from sqlalchemy import delete, or_, select

from .adapters import discover
from .config import get_settings
from .db import SessionLocal, aware, utcnow
from .models import (
    AvailabilityObservation,
    CohortMember,
    CohortRun,
    ExtractionRun,
    FieldAssertion,
    ImageEmbedding,
    IngestionCursor,
    Listing,
    ListingSimilarity,
    ListingSource,
    MediaAsset,
    PostMedia,
    PostVersion,
    PriceObservation,
    RateBucket,
    Seller,
    SourceAccount,
    SourcePost,
    TakedownRequest,
    TextEmbedding,
)
from .pipeline import enqueue, ingest, process_extraction
from .providers import CapabilityError, _live_text_vector
from .schemas import ImportPost

logger = logging.getLogger("bouquetbrowse.worker")


def claim_job():
    from .leases import claim

    lease = claim(SessionLocal)
    return lease.job_id if lease else None


def purge_listing(db, listing_id, extended=True):
    listing = db.get(Listing, listing_id)
    if not listing:
        return
    if extended:
        from .retention import scrub_versions

        versions = list(db.scalars(select(ListingSource.version_id).where(ListingSource.listing_id == listing_id)))
        scrub_versions(db, versions, reason="takedown", listing_ids=[listing_id])
        return
    run_ids = set(db.scalars(select(CohortMember.run_id).where(CohortMember.listing_id == listing_id)).all()) | set(
        db.scalars(select(CohortRun.id).where(CohortRun.listing_id == listing_id)).all()
    )
    if run_ids:
        db.execute(delete(CohortMember).where(CohortMember.run_id.in_(run_ids)))
        db.execute(delete(CohortRun).where(CohortRun.id.in_(run_ids)))
    db.execute(
        delete(ListingSimilarity).where(
            or_(ListingSimilarity.listing_id == listing_id, ListingSimilarity.neighbor_id == listing_id)
        )
    )
    for model in [PriceObservation, AvailabilityObservation, FieldAssertion]:
        db.execute(delete(model).where(model.listing_id == listing_id))
    from .models import ListingRevision

    revisions = db.scalars(select(ListingRevision.id).where(ListingRevision.listing_id == listing_id)).all()
    db.execute(delete(TextEmbedding).where(TextEmbedding.revision_id.in_(revisions)))
    links = db.scalars(select(ListingSource).where(ListingSource.listing_id == listing_id)).all()
    for link in links:
        other_active = db.scalar(
            select(ListingSource.id)
            .join(Listing, Listing.id == ListingSource.listing_id)
            .where(
                ListingSource.version_id == link.version_id,
                ListingSource.listing_id != listing_id,
                Listing.state == "published",
            )
            .limit(1)
        )
        if other_active:
            continue
        version = db.get(PostVersion, link.version_id)
        version.caption, version.payload = "", {"removed": True}
        post = db.get(SourcePost, version.post_id)
        post.access_state, post.url = "removed", None
        for run in db.scalars(select(ExtractionRun).where(ExtractionRun.version_id == version.id)).all():
            run.output, run.errors = {}, ["Removed through takedown"]
        for asset in db.scalars(
            select(MediaAsset)
            .join(PostMedia, PostMedia.media_id == MediaAsset.id)
            .where(PostMedia.version_id == version.id)
        ).all():
            other_use = db.scalar(
                select(ListingSource.id)
                .join(PostMedia, PostMedia.version_id == ListingSource.version_id)
                .join(Listing, Listing.id == ListingSource.listing_id)
                .where(PostMedia.media_id == asset.id, Listing.id != listing_id, Listing.state == "published")
                .limit(1)
            )
            if not other_use:
                if asset.storage_key:
                    enqueue(
                        db,
                        "delete-media",
                        {"storage_key": asset.storage_key},
                        f"delete-media:{asset.id}:{asset.storage_key}",
                    )
                asset.source_url, asset.storage_key, asset.state = None, None, "removed"
                db.execute(delete(ImageEmbedding).where(ImageEmbedding.media_id == asset.id))
    listing.state, listing.title, listing.description, listing.image_path, listing.search_text = (
        "withdrawn",
        "Removed listing",
        "",
        None,
        "",
    )
    listing.attributes = {"removed": True}
    listing.primary_flower, listing.color, listing.arrangement, listing.stem_count = None, None, None, None
    listing.style, listing.occasion = None, None
    for revision in db.scalars(select(ListingRevision).where(ListingRevision.listing_id == listing_id)).all():
        revision.snapshot = {"removed": True}
    for request in db.scalars(select(TakedownRequest).where(TakedownRequest.listing_id == listing_id)).all():
        request.state = "purged"


def handle_job(db, job, prepared=None):
    p = job.payload
    if job.kind == "extract":
        return process_extraction(db, p["version_id"], p.get("pipeline_version", "hybrid-v1"), prepared=prepared)
    if job.kind == "purge":
        purge_listing(db, p["listing_id"])
        return {"purged": True}
    if job.kind == "prepare-media":
        asset = db.get(MediaAsset, p["media_id"])
        if not asset or asset.state == "removed":
            if prepared:
                enqueue(db, "delete-media", {"storage_key": prepared[0]}, f"orphan-media:{prepared[0]}")
            return {"removed": True}
        key, metadata = prepared
        for name, value in metadata.items():
            setattr(asset, name, value)
        asset.storage_key, asset.state = key, "ready"
        if get_settings().image_embedding_provider == "siglip":
            enqueue(db, "embed-image", {"media_id": asset.id}, f"image:{asset.id}:{get_settings().siglip_revision}")
        # Publish an image only after source association; private delivery remains authenticated.
        for listing in db.scalars(
            select(Listing)
            .join(ListingSource, ListingSource.listing_id == Listing.id)
            .join(PostMedia, PostMedia.version_id == ListingSource.version_id)
            .where(PostMedia.media_id == asset.id)
        ).all():
            if listing.image_path is None:
                listing.image_path = f"/api/v1/media/{asset.id}"
        return {"media_id": asset.id}
    if job.kind == "embed-image":
        asset = db.get(MediaAsset, p["media_id"])
        if not asset or asset.state != "ready" or not asset.storage_key:
            return {"skipped": True}
        vector, model = prepared
        if not db.scalar(
            select(ImageEmbedding.id).where(ImageEmbedding.media_id == asset.id, ImageEmbedding.model_version == model)
        ):
            db.add(ImageEmbedding(media_id=asset.id, model_version=model, vector=vector))
        return {"embedded": True, "model": model}
    if job.kind == "embed-text":
        listing = db.get(Listing, p["listing_id"])
        if not listing or listing.state != "published" or listing.is_demo or prepared is None:
            return {"skipped": True}
        model = get_settings().embedding_model
        if not db.scalar(
            select(TextEmbedding.id).where(
                TextEmbedding.revision_id == p["revision_id"], TextEmbedding.model_version == model
            )
        ):
            db.add(
                TextEmbedding(
                    revision_id=p["revision_id"],
                    model_version=model,
                    vector=prepared,
                )
            )
        return {"embedded": True}
    if job.kind == "sync":
        rows, checkpoint = prepared
        imported, skipped = [], 0
        for row in rows:
            username = row.get("username")
            account = (
                db.scalar(
                    select(SourceAccount).where(
                        SourceAccount.platform == p["source"], SourceAccount.username == username
                    )
                )
                if username
                else None
            )
            if not account:
                skipped += 1
                continue
            seller = db.get(Seller, account.seller_id) if account.seller_id else None
            rights = account.capabilities.get("rights_confirmed", False)
            if not rights or not seller:
                skipped += 1
                continue
            caption = row.get("caption") or row.get("text")
            if not caption or not row.get("timestamp"):
                skipped += 1
                continue
            item = ImportPost(
                platform=p["source"],
                platform_post_id=str(row["id"]),
                username=username,
                seller_name=seller.name,
                seller_slug=seller.slug,
                district=seller.district,
                source_url=row.get("permalink"),
                published_at=row["timestamp"],
                caption=caption,
                media_urls=[row["media_url"]] if row.get("media_url") and row.get("media_type") == "IMAGE" else [],
                rights_confirmed=True,
            )
            imported.append(ingest(db, item))
        cursor = db.scalar(select(IngestionCursor).where(IngestionCursor.source == p["source"]))
        if not cursor:
            cursor = IngestionCursor(source=p["source"])
            db.add(cursor)
        cursor.checkpoint, cursor.last_success_at = {**checkpoint, "unregistered_or_unusable": skipped}, utcnow()
        return {"imported": len(imported), "skipped": skipped, "checkpoint": checkpoint}
    if job.kind == "retention":
        from .retention import expire

        expire(db)
        now = utcnow()
        for version in db.scalars(select(PostVersion).where(PostVersion.retention_until < now)).all():
            version.caption, version.payload = "", {"expired": True}
        for asset in db.scalars(
            select(MediaAsset).where(MediaAsset.retention_until < now, MediaAsset.state != "removed")
        ).all():
            if asset.storage_key:
                enqueue(
                    db,
                    "delete-media",
                    {"storage_key": asset.storage_key},
                    f"delete-media:{asset.id}:{asset.storage_key}",
                )
            asset.storage_key, asset.source_url, asset.state = None, None, "expired"
            db.execute(delete(ImageEmbedding).where(ImageEmbedding.media_id == asset.id))
        db.execute(delete(RateBucket).where(RateBucket.expires_at < now))
        old_cohorts = select(CohortRun.id).where(CohortRun.created_at < now - timedelta(days=7))
        db.execute(delete(CohortMember).where(CohortMember.run_id.in_(old_cohorts)))
        db.execute(delete(CohortRun).where(CohortRun.created_at < now - timedelta(days=7)))
        for listing in db.scalars(
            select(Listing).where(Listing.created_at < now - timedelta(days=365), Listing.state != "withdrawn")
        ).all():
            purge_listing(db, listing.id)
        return {"retention_checked": True}
    if job.kind == "delete-checkpoints":
        from .retention import delete_checkpoints

        delete_checkpoints(db, p["execution_id"])
        return {"deleted": True}
    raise CapabilityError("Unknown job type", "unsupported_job")


def prepare_external(job, lease):
    """Read snapshots, close the transaction, then perform external work."""
    from .leases import guard

    p = job.payload
    if job.kind == "discovery-graph":
        from .discovery import run_discovery

        return run_discovery(p["execution_id"], lease)
    if job.kind == "offer-graph":
        from .offer_runtime import run_offer

        return run_offer(p["execution_id"], lease)
    if job.kind == "sync":
        return discover(p["source"], p.get("query", "bó hoa Hà Nội"), p.get("username"))
    if job.kind == "delete-media":
        with SessionLocal() as db:
            used = db.scalar(
                select(MediaAsset.id)
                .where(MediaAsset.storage_key == p["storage_key"], MediaAsset.state == "ready")
                .limit(1)
            )
            guard(db, lease)
            db.commit()
        if not used:
            from .storage import delete_media

            delete_media(p["storage_key"])
        return {"deleted": not bool(used)}
    if job.kind == "extract" and get_settings().extraction_provider == "openai":
        with SessionLocal() as db:
            version = db.get(PostVersion, p["version_id"])
            if not version or not version.caption or aware(version.retention_until) <= utcnow():
                raise CapabilityError("Source content expired.", "source_expired")
            if db.get(SourcePost, version.post_id).access_state == "removed":
                raise CapabilityError("Source was removed.", "source_removed")
            caption = version.caption
            keys = list(
                db.scalars(
                    select(MediaAsset.storage_key)
                    .join(PostMedia, PostMedia.media_id == MediaAsset.id)
                    .where(PostMedia.version_id == version.id, MediaAsset.state == "ready")
                    .order_by(PostMedia.position)
                    .limit(4)
                )
            )
            total = len(list(db.scalars(select(PostMedia.id).where(PostMedia.version_id == version.id))))
            pending = db.scalar(
                select(MediaAsset.id)
                .join(PostMedia, PostMedia.media_id == MediaAsset.id)
                .where(PostMedia.version_id == version.id, MediaAsset.state == "pending")
                .limit(1)
            )
        if pending:
            raise CapabilityError("Waiting for source images to finish preparation.", "media_pending", True, 30)
        from .providers import structured_extract
        from .storage import get_media_bytes

        result, cost = structured_extract(caption, [get_media_bytes(key) for key in keys if key])
        if total > len(keys):
            result.warnings.append(f"Only {len(keys)} of {total} media items analyzed.")
        return result, cost
    if job.kind == "prepare-media":
        with SessionLocal() as db:
            asset = db.get(MediaAsset, p["media_id"])
            if not asset or asset.state == "removed":
                return None
            url = asset.source_url
        from .media import download_media, save_media

        content = download_media(url)
        with SessionLocal() as db:
            guard(db, lease)
            db.commit()
        key, _, metadata = save_media(content)
        return key, metadata
    if job.kind == "embed-image":
        with SessionLocal() as db:
            asset = db.get(MediaAsset, p["media_id"])
            key = asset.storage_key if asset and asset.state == "ready" else None
        if not key:
            return None
        from .storage import get_media_bytes
        from .vision import image_embedding

        return image_embedding(get_media_bytes(key))
    if job.kind == "embed-text":
        with SessionLocal() as db:
            listing = db.get(Listing, p["listing_id"])
            text_input = (
                listing.search_text if listing and listing.state == "published" and not listing.is_demo else None
            )
        return list(_live_text_vector(text_input, get_settings().embedding_model)) if text_input else None
    return None


def run_once(kinds=None, exclude_kinds=None):
    from .leases import claim, guard, keep_alive
    from .model_calls import CallScope, call_scope, microusd

    lease = claim(SessionLocal, kinds, exclude_kinds)
    if not lease:
        return False
    prepared, job = None, None
    try:
        with (
            keep_alive(lease, SessionLocal),
            call_scope(CallScope(f"job:{lease.job_id}", microusd(get_settings().offer_budget_usd), lease=lease)),
        ):
            with SessionLocal() as db:
                job = guard(db, lease)
                db.expunge(job)
                db.commit()
            prepared = prepare_external(job, lease)
            with SessionLocal() as db:
                current = guard(db, lease)
                current.result = (
                    prepared
                    if current.kind in {"delete-media", "discovery-graph", "offer-graph"}
                    else handle_job(db, current, prepared)
                )
                current.state, current.lease_until, current.lease_token, current.last_error = (
                    "succeeded",
                    None,
                    None,
                    None,
                )
                db.commit()
    except Exception as exc:
        if job and job.kind == "prepare-media" and prepared:
            with SessionLocal() as db:
                enqueue(db, "delete-media", {"storage_key": prepared[0]}, f"orphan-media:{prepared[0]}")
                db.commit()
        try:
            with SessionLocal() as db:
                current = guard(db, lease)
                retryable = isinstance(exc, CapabilityError) and exc.retryable
                current.last_error = (
                    str(exc)[:500] if isinstance(exc, CapabilityError) else "Processing failed; inspect the job ID."
                )
                if isinstance(exc, CapabilityError) and exc.code in {
                    "call_replay_required",
                    "call_expired",
                    "browser_auth_required",
                    "discovery_paused",
                    "checkpoints_not_ready",
                    "discovery_not_configured",
                    "browser_busy",
                }:
                    current.state = "paused"
                elif retryable and current.attempts < 5:
                    delay = exc.retry_after or [60, 300, 1800, 7200][min(current.attempts - 1, 3)]
                    current.state = "queued"
                    current.run_after = utcnow() + timedelta(seconds=delay + random.uniform(0, 10))
                else:
                    current.state = "failed"
                current.lease_until, current.lease_token = None, None
                db.commit()
        except CapabilityError:
            pass  # A replacement or cancellation owns the result now.
        logger.error("job_failed job_id=%s type=%s", lease.job_id, type(exc).__name__)
    return True


def schedule_due():
    from .adapters import capability_status

    with SessionLocal() as db:
        from .local_schedule import tick

        tick(db)
        now = utcnow()
        enqueue(db, "retention", {}, f"retention:{now.date()}")
        for source in capability_status():
            if source["enabled"] and source["id"] == "threads":
                for query in ["bó hoa Hà Nội", "hoa hồng Hà Nội", "shop hoa Hà Nội"]:
                    enqueue(
                        db,
                        "sync",
                        {"source": "threads", "query": query},
                        f"scheduled:threads:{int(now.timestamp()) // 21600}:{query}",
                    )
        # Instagram refresh is restricted to registered, explicitly authorized professional handles.
        for account in db.scalars(select(SourceAccount).where(SourceAccount.platform == "instagram")).all():
            if account.capabilities.get("rights_confirmed") and get_settings().instagram_discovery_approved:
                enqueue(
                    db,
                    "sync",
                    {"source": "instagram", "username": account.username},
                    f"scheduled:instagram:{account.id}:{now.date()}",
                )
        db.commit()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--schedule", action="store_true")
    parser.add_argument("--role", choices=["general", "browser", "offer", "scheduler"], default="general")
    args = parser.parse_args()
    from logging.handlers import TimedRotatingFileHandler

    from .config import ROOT

    logs = ROOT / ".data" / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    handler = TimedRotatingFileHandler(
        logs / f"{args.role}.log", when="midnight", backupCount=30, utc=True, encoding="utf-8"
    )
    logging.basicConfig(
        level=logging.INFO,
        handlers=[logging.StreamHandler(), handler],
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    while True:
        from .local_schedule import heartbeat

        with SessionLocal() as db:
            heartbeat(db, args.role)
            db.commit()
        if args.schedule or args.role == "scheduler":
            schedule_due()
        if args.role == "scheduler":
            processed = False
        elif args.role == "browser":
            processed = run_once(kinds=["discovery-graph"])
        else:
            processed = run_once(exclude_kinds=["discovery-graph"])
        if args.once:
            break
        if not processed:
            time.sleep(30 if args.role == "scheduler" else 2)


if __name__ == "__main__":
    main()
