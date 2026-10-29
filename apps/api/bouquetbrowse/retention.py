"""Remove evidence copies before retention/deletion can leave unsupported projections."""

from datetime import timedelta

from sqlalchemy import delete, select, text

from .browser_models import BrowserObservation, ProfileSnapshot
from .catalog_event_models import CatalogChange, SellerFact
from .conversation_models import (
    CanonicalConfiguration,
    CanonicalLink,
    CaptureMember,
    ConversationCapture,
    OfferAssociation,
    OfferClaim,
    OfferOccurrence,
)
from .db import aware, utcnow
from .leases import cancel
from .models import (
    ExtractionRun,
    FieldAssertion,
    ImageEmbedding,
    Job,
    Listing,
    ListingSource,
    MediaAsset,
    PostMedia,
    PostVersion,
    ReviewAction,
    SourcePost,
)
from .offer_models import AssociationReview, OfferAnalysis
from .operations_models import CallDependency, DeletionRecord
from .pipeline import enqueue
from .recognition_models import ImageRegion, RecognitionRecord
from .runtime_models import ActionReceipt, ExecutionEvent, GraphExecution, ModelCall


def ledger(db, kind, subject_id, reason):
    from .discovery import dialect_insert

    db.execute(
        dialect_insert(db)(DeletionRecord)
        .values(deletion_key=f"{kind}:{subject_id}", subject_kind=kind, subject_id=subject_id, reason=reason)
        .on_conflict_do_nothing(index_elements=["deletion_key"])
    )


def remove_media(db, asset):
    if asset.storage_key:
        enqueue(db, "delete-media", {"storage_key": asset.storage_key}, f"delete-media:{asset.id}:{asset.storage_key}")
    asset.storage_key, asset.source_url, asset.state = None, None, "removed"
    db.execute(delete(ImageEmbedding).where(ImageEmbedding.media_id == asset.id))
    for region in db.scalars(select(ImageRegion).where(ImageRegion.media_id == asset.id)):
        region.evidence, region.bounds, region.state = {}, [], "removed"


def scrub_versions(db, version_ids, reason="expired", listing_ids=None):
    versions = set(version_ids)
    if not versions and not listing_ids:
        return
    associations = list(db.scalars(select(OfferAssociation).where(OfferAssociation.version_id.in_(versions))))
    offers = set(a.offer_id for a in associations)
    listings = set(listing_ids or []) | set(
        db.scalars(select(ListingSource.listing_id).where(ListingSource.version_id.in_(versions)))
    )
    offers.update(db.scalars(select(OfferOccurrence.id).where(OfferOccurrence.listing_id.in_(listings))))
    captures = set(db.scalars(select(CaptureMember.capture_id).where(CaptureMember.version_id.in_(versions))))
    executions = set(db.scalars(select(GraphExecution.id).where(GraphExecution.offer_id.in_(offers))))
    executions.update(
        db.scalars(select(BrowserObservation.execution_id).where(BrowserObservation.capture_id.in_(captures)))
    )
    executions.update(db.scalars(select(ActionReceipt.execution_id).where(ActionReceipt.capture_id.in_(captures))))
    media = set(db.scalars(select(PostMedia.media_id).where(PostMedia.version_id.in_(versions))))
    media.update(a.media_id for a in associations if a.media_id)
    urls = set()
    for version_id in versions:
        version = db.get(PostVersion, version_id)
        if not version:
            continue
        version.caption, version.payload, version.retention_until = "", {"removed": reason}, utcnow()
        post = db.get(SourcePost, version.post_id)
        if post.url:
            urls.add(post.url)
        if reason == "takedown":
            ledger(db, "post", post.id, reason)
            post.access_state, post.url = "removed", None
        for run in db.scalars(select(ExtractionRun).where(ExtractionRun.version_id == version_id)):
            run.output, run.errors = {}, [reason]
    for offer in db.scalars(select(OfferOccurrence).where(OfferOccurrence.id.in_(offers))):
        offer.state = "withdrawn" if reason == "takedown" else "expired"
        if offer.listing_id:
            listings.add(offer.listing_id)
    for association in db.scalars(select(OfferAssociation).where(OfferAssociation.offer_id.in_(offers))):
        association.evidence, association.region, association.state = {}, None, "removed"
    for claim in db.scalars(select(OfferClaim).where(OfferClaim.offer_id.in_(offers))):
        claim.evidence, claim.value, claim.status = [], {}, "unknown"
    for analysis in db.scalars(select(OfferAnalysis).where(OfferAnalysis.offer_id.in_(offers))):
        analysis.output, analysis.errors, analysis.state = {}, [reason], "removed"
    for review in db.scalars(select(AssociationReview).where(AssociationReview.offer_id.in_(offers))):
        review.proposal, review.decision, review.state = {}, {}, "removed"
    for link in db.scalars(select(CanonicalLink).where(CanonicalLink.offer_id.in_(offers))):
        link.evidence, link.state = {}, "removed"
        db.get(CanonicalConfiguration, link.configuration_id).evidence = {}
    for record in db.scalars(select(RecognitionRecord)):
        views = record.dependencies.get("views", [])
        if record.offer_id in offers or any(v.get("media_id") in media for v in views):
            record.result, record.dependencies, record.retention_until = {}, {}, utcnow()
    for observation in db.scalars(select(BrowserObservation).where(BrowserObservation.capture_id.in_(captures))):
        observation.snapshot = {}
    for capture_id in captures:
        capture = db.get(ConversationCapture, capture_id)
        capture.source_url, capture.coverage = "", {"removed": reason}
    for receipt in db.scalars(select(ActionReceipt).where(ActionReceipt.execution_id.in_(executions))):
        receipt.continuation, receipt.state = {}, "removed"
    for execution_id in executions:
        execution = db.get(GraphExecution, execution_id)
        cancel(db, execution.job_id)
        execution.state, execution.stop_reason, execution.progress = "withdrawn", reason, {}
        # Checkpointer deletion is an idempotent downstream command, outside this transaction.
        enqueue(db, "delete-checkpoints", {"execution_id": execution_id}, f"delete-checkpoints:{execution_id}")
    for call in db.scalars(select(ModelCall).where(ModelCall.execution_id.in_(executions))):
        call.result, call.usage, call.replay_authorized = None, {}, False
        # Keep uncertain reservations in the financial ledger; never authorize replay.
        call.state = "removed"
    calls = select(CallDependency.call_id).where(CallDependency.kind == "media", CallDependency.reference_id.in_(media))
    for call in db.scalars(select(ModelCall).where(ModelCall.id.in_(calls))):
        call.result, call.usage, call.state, call.replay_authorized = None, {}, "removed", False
    for event in db.scalars(select(ExecutionEvent).where(ExecutionEvent.execution_id.in_(executions))):
        event.details = {}
    for fact in db.scalars(select(SellerFact)):
        if fact.evidence.get("version_id") in versions:
            db.delete(fact)
    for listing_id in listings:
        listing = db.get(Listing, listing_id)
        if not listing:
            continue
        ledger(db, "listing", listing_id, reason)
        # Reuse the legacy purge for observations/vectors/cohorts and immutable revision copies.
        from .worker import purge_listing

        purge_listing(db, listing_id, extended=False)
    for event in db.scalars(select(CatalogChange)):
        if event.listing_id in listings or event.source_url in urls:
            event.suppressed, event.details, event.source_url = True, {}, None
    for asset in db.scalars(select(MediaAsset).where(MediaAsset.id.in_(media))):
        remove_media(db, asset)
    for review in db.scalars(select(ReviewAction).where(ReviewAction.listing_id.in_(listings))):
        review.reason, review.changes = "Evidence removed", {}
    # Operator imports/reviews may retain exact quotes independently of new offer claims.
    for assertion in db.scalars(select(FieldAssertion).where(FieldAssertion.listing_id.in_(listings))):
        assertion.evidence = []
    # Raw import command copies are private too; preserve only content-free receipts.
    for job in db.scalars(select(Job)):
        if job.kind not in {"delete-media", "delete-checkpoints"} and (
            job.payload.get("version_id") in versions
            or job.payload.get("listing_id") in listings
            or job.payload.get("execution_id") in executions
        ):
            for call in db.scalars(select(ModelCall).where(ModelCall.job_id == job.id)):
                call.result, call.usage, call.state, call.replay_authorized = None, {}, "removed", False
            if job.kind not in {"purge", "retention"}:
                cancel(db, job.id)
            job.payload, job.result, job.last_error = {}, {"removed": True}, None


def expire(db, now=None):
    now = now or utcnow()
    versions = list(
        db.scalars(select(PostVersion.id).where(PostVersion.retention_until <= now, PostVersion.caption != ""))
    )
    scrub_versions(db, versions)
    for model, field, replacement in [
        (BrowserObservation, "snapshot", {}),
        (ProfileSnapshot, "text", ""),
        (RecognitionRecord, "result", {}),
        (OfferAnalysis, "output", {}),
        (ModelCall, "result", None),
    ]:
        for row in db.scalars(select(model).where(model.retention_until <= now)):
            setattr(row, field, replacement)
            if isinstance(row, RecognitionRecord):
                row.dependencies = {}
    for region in db.scalars(select(ImageRegion).where(ImageRegion.retention_until <= now)):
        region.bounds, region.evidence, region.state = [], {}, "expired"
    db.execute(delete(SellerFact).where(SellerFact.retention_until <= now))
    for event in db.scalars(select(ExecutionEvent).where(ExecutionEvent.created_at <= now - timedelta(days=30))):
        event.details = {}
    for event in db.scalars(select(CatalogChange).where(CatalogChange.created_at <= now - timedelta(days=365))):
        event.suppressed, event.details, event.source_url = True, {}, None
    # Compact checkpoints still carry source IDs; remove terminal histories at log retention.
    for execution in db.scalars(select(GraphExecution).where(GraphExecution.created_at <= now - timedelta(days=30))):
        cancel(db, execution.job_id)
        execution.state, execution.progress, execution.stop_reason = "withdrawn", {}, "retention"
        enqueue(db, "delete-checkpoints", {"execution_id": execution.id}, f"delete-checkpoints:{execution.id}")
    return {"expired_versions": len(versions)}


def delete_checkpoints(db, execution_id):
    if db.bind.dialect.name == "postgresql":
        for table in ["checkpoints", "checkpoint_blobs", "checkpoint_writes"]:
            if db.scalar(text("SELECT to_regclass(:name)"), {"name": f"graph_checkpoints.{table}"}):
                db.execute(text(f"DELETE FROM graph_checkpoints.{table} WHERE thread_id=:id"), {"id": execution_id})


def receipt_permitted(db, call):
    if call.state == "removed" or aware(call.retention_until) <= utcnow():
        return False
    for dependency in db.scalars(select(CallDependency).where(CallDependency.call_id == call.id)):
        asset = db.get(MediaAsset, dependency.reference_id)
        if not asset or asset.state != "ready" or asset.retention_until and aware(asset.retention_until) <= utcnow():
            return False
    if call.job_id:
        job = db.get(Job, call.job_id)
        listing = db.get(Listing, job.payload.get("listing_id")) if job and job.payload.get("listing_id") else None
        if listing and listing.state == "withdrawn":
            return False
        version = db.get(PostVersion, job.payload.get("version_id")) if job and job.payload.get("version_id") else None
        if version and (
            aware(version.retention_until) <= utcnow() or db.get(SourcePost, version.post_id).access_state == "removed"
        ):
            return False
    execution = db.get(GraphExecution, call.execution_id) if call.execution_id else None
    if execution and execution.state == "withdrawn":
        return False
    if execution and execution.offer_id:
        offer = db.get(OfferOccurrence, execution.offer_id)
        if not offer or offer.state in {"withdrawn", "expired"}:
            return False
        listing = db.get(Listing, offer.listing_id) if offer.listing_id else None
        if listing and listing.state == "withdrawn":
            return False
    return True
