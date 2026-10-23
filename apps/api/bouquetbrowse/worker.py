import argparse
import logging
import random
import time
from datetime import timedelta

from sqlalchemy import delete, or_, select, update

from .adapters import discover
from .config import get_settings
from .db import SessionLocal, utcnow
from .models import (
    AvailabilityObservation,
    CohortMember,
    CohortRun,
    ExtractionRun,
    FieldAssertion,
    ImageEmbedding,
    IngestionCursor,
    Job,
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
    with SessionLocal() as db:
        now = utcnow()
        job = db.scalar(
            select(Job)
            .where(
                or_(Job.state == "queued", (Job.state == "processing") & (Job.lease_until < now)), Job.run_after <= now
            )
            .order_by(Job.run_after, Job.id)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        if not job:
            return None
        claimed = db.execute(
            update(Job)
            .where(Job.id == job.id, Job.state == job.state, Job.attempts == job.attempts)
            .values(state="processing", attempts=job.attempts + 1, lease_until=now + timedelta(minutes=10))
        )
        if claimed.rowcount != 1:
            db.rollback()
            return None
        db.commit()
        return job.id


def purge_listing(db, listing_id):
    listing = db.get(Listing, listing_id)
    if not listing:
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
                    from .storage import delete_media

                    delete_media(asset.storage_key)
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


def handle_job(db, job):
    p = job.payload
    if job.kind == "extract":
        return process_extraction(db, p["version_id"], p.get("pipeline_version", "hybrid-v1"))
    if job.kind == "purge":
        purge_listing(db, p["listing_id"])
        return {"purged": True}
    if job.kind == "prepare-media":
        from .media import download_media, save_media

        asset = db.get(MediaAsset, p["media_id"])
        if asset.state == "removed":
            return {"removed": True}
        key, _, metadata = save_media(download_media(asset.source_url))
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
        from .storage import get_media_bytes
        from .vision import image_embedding

        asset = db.get(MediaAsset, p["media_id"])
        if not asset or asset.state != "ready" or not asset.storage_key:
            return {"skipped": True}
        vector, model = image_embedding(get_media_bytes(asset.storage_key))
        if not db.scalar(
            select(ImageEmbedding.id).where(ImageEmbedding.media_id == asset.id, ImageEmbedding.model_version == model)
        ):
            db.add(ImageEmbedding(media_id=asset.id, model_version=model, vector=vector))
        return {"embedded": True, "model": model}
    if job.kind == "embed-text":
        listing = db.get(Listing, p["listing_id"])
        if listing.state != "published" or listing.is_demo:
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
                    vector=list(_live_text_vector(listing.search_text, model)),
                )
            )
        return {"embedded": True}
    if job.kind == "sync":
        rows, checkpoint = discover(p["source"], p.get("query", "bó hoa Hà Nội"), p.get("username"))
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
            seller = db.get(Seller, account.seller_id)
            rights = account.capabilities.get("rights_confirmed", False)
            if not rights:
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
        now = utcnow()
        for version in db.scalars(select(PostVersion).where(PostVersion.retention_until < now)).all():
            version.caption, version.payload = "", {"expired": True}
        for asset in db.scalars(
            select(MediaAsset).where(MediaAsset.retention_until < now, MediaAsset.state != "removed")
        ).all():
            if asset.storage_key:
                from .storage import delete_media

                delete_media(asset.storage_key)
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
    raise CapabilityError("Unknown job type", "unsupported_job")


def run_once():
    job_id = claim_job()
    if not job_id:
        return False
    try:
        with SessionLocal() as db:
            job = db.get(Job, job_id)
            job.result = handle_job(db, job)
            job.state, job.lease_until, job.last_error = "succeeded", None, None
            db.commit()
    except Exception as exc:
        with SessionLocal() as db:
            job = db.get(Job, job_id)
            retryable = isinstance(exc, CapabilityError) and exc.retryable
            job.last_error = (
                str(exc)[:500]
                if isinstance(exc, (CapabilityError, ValueError))
                else "Processing failed. Inspect server logs using the job ID."
            )
            if retryable and job.attempts < 5:
                delay = exc.retry_after or [60, 300, 1800, 7200][min(job.attempts - 1, 3)]
                job.state = "queued"
                job.run_after = utcnow() + timedelta(seconds=delay + random.uniform(0, 10))
            else:
                job.state = "failed"
            job.lease_until = None
            db.commit()
        logger.error("job_failed job_id=%s type=%s", job_id, type(exc).__name__)
    return True


def schedule_due():
    from .adapters import capability_status

    with SessionLocal() as db:
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
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    while True:
        if args.schedule:
            schedule_due()
        processed = run_once()
        if args.once:
            break
        if not processed:
            time.sleep(2)


if __name__ == "__main__":
    main()
