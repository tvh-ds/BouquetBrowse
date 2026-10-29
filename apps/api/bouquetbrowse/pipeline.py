import hashlib
import json
from datetime import timedelta

from sqlalchemy import select, text

from .config import get_settings
from .db import aware, utcnow
from .extraction import extract_caption, extract_prices, fold, validate_grounding
from .models import (
    AvailabilityObservation,
    ExtractionRun,
    FieldAssertion,
    Job,
    Listing,
    ListingRevision,
    ListingSource,
    MediaAsset,
    PostMedia,
    PostVersion,
    PriceObservation,
    ReviewAction,
    Seller,
    SourceAccount,
    SourcePost,
    TextEmbedding,
)
from .providers import CapabilityError, structured_extract
from .schemas import ImportPost, ReviewDecision
from .source_identity import find_source


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()


def enqueue(db, kind, payload, key):
    if db.bind.dialect.name == "postgresql":
        from sqlalchemy.dialects.postgresql import insert
    else:
        from sqlalchemy.dialects.sqlite import insert

    db.execute(
        insert(Job)
        .values(kind=kind, payload=payload, idempotency_key=key)
        .on_conflict_do_nothing(index_elements=["idempotency_key"])
    )
    job = db.scalar(select(Job).where(Job.idempotency_key == key))
    if job.kind != kind or job.payload != payload:
        raise ValueError("Idempotency key was already used for different work")
    return job


def ingest(db, post: ImportPost):
    if not post.rights_confirmed:
        raise ValueError("Confirm permission to process and display the imported content.")
    if db.bind.dialect.name == "postgresql":
        lock = int(digest([post.platform, post.platform_post_id])[:15], 16)
        db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": lock})
    seller = db.scalar(select(Seller).where(Seller.slug == post.seller_slug))
    if not seller:
        seller = Seller(name=post.seller_name, slug=post.seller_slug, district=post.district, city=post.city)
        db.add(seller)
        db.flush()
    account = db.scalar(
        select(SourceAccount).where(SourceAccount.platform == post.platform, SourceAccount.username == post.username)
    )
    if account and account.seller_id != seller.id:
        raise ValueError("This source account is already associated with another seller.")
    if not account:
        account = SourceAccount(seller_id=seller.id, platform=post.platform, username=post.username)
        db.add(account)
        db.flush()
    source = find_source(db, post.platform, post.platform_post_id, post.source_url)
    if source and source.account_id != account.id:
        raise ValueError("Post identity cannot be reassigned to another seller.")
    if source and source.access_state == "removed":
        raise ValueError("This source was removed. A takedown cannot be reversed by ingestion.")
    if not source:
        source = SourcePost(
            account_id=account.id,
            platform=post.platform,
            platform_post_id=post.platform_post_id,
            url=str(post.source_url) if post.source_url else None,
            published_at=post.published_at,
        )
        db.add(source)
        db.flush()
    account.capabilities = {**account.capabilities, "rights_confirmed": True, "location_reviewed": True}
    source.last_seen_at = utcnow()
    payload = post.model_dump(mode="json")
    content_hash = digest({"caption": post.caption, "media": payload["media_urls"], "product_key": post.product_key})
    version = db.scalar(
        select(PostVersion).where(PostVersion.post_id == source.id, PostVersion.content_hash == content_hash)
    )
    if version:
        return {"post_id": source.id, "version_id": version.id, "duplicate": True}
    version = PostVersion(
        post_id=source.id,
        content_hash=content_hash,
        caption=post.caption,
        payload=payload,
        retention_until=utcnow() + timedelta(days=30),
    )
    db.add(version)
    db.flush()
    for position, url in enumerate(post.media_urls):
        asset = MediaAsset(
            source_url=str(url),
            rights={"operator_confirmed": True, "source_post_id": source.id},
            retention_until=utcnow() + timedelta(days=90),
        )
        db.add(asset)
        db.flush()
        db.add(PostMedia(version_id=version.id, media_id=asset.id, position=position))
        enqueue(db, "prepare-media", {"media_id": asset.id}, f"media:{asset.id}")
    job = enqueue(
        db, "extract", {"version_id": version.id, "pipeline_version": "hybrid-v1"}, f"extract:{version.id}:hybrid-v1"
    )
    return {"post_id": source.id, "version_id": version.id, "job_id": job.id, "duplicate": False}


def title_for(fields):
    flower = {
        "rose": "hoa hồng",
        "tulip": "tulip",
        "sunflower": "hướng dương",
        "lisianthus": "cát tường",
        "chrysanthemum": "hoa cúc",
    }.get(fields.get("primary_flower"), fields.get("primary_flower") or "hoa")
    color = {"pink": "hồng", "white": "trắng", "yellow": "vàng", "purple": "tím", "red": "đỏ"}.get(
        fields.get("color"), ""
    )
    kind = {"basket": "Giỏ", "box": "Hộp", "vase": "Bình"}.get(fields.get("arrangement"), "Bó")
    return f"{kind} {flower} {color}".strip()


def process_extraction(db, version_id, pipeline_version="hybrid-v1", prepared=None):
    version = db.get(PostVersion, version_id)
    if not version or not version.caption or aware(version.retention_until) <= utcnow():
        raise CapabilityError("Source content is missing or has expired.", "source_expired")
    post = db.get(SourcePost, version.post_id)
    if post.access_state == "removed":
        raise CapabilityError("Removed source cannot be reprocessed.", "source_removed")
    provider = get_settings().extraction_provider
    # Provider is part of version identity: rule and API runs never collide silently.
    full_version = f"{pipeline_version}:{provider}"
    run = db.scalar(
        select(ExtractionRun).where(
            ExtractionRun.input_hash == digest([version.id, version.content_hash]),
            ExtractionRun.pipeline_version == full_version,
            ExtractionRun.stage == "extraction",
        )
    )
    if run:
        linked = db.scalar(select(ListingSource).where(ListingSource.version_id == version.id))
        return {"listing_id": linked.listing_id if linked else None, "duplicate": True}
    cost = 0
    if prepared is not None:
        result, cost = prepared
    elif provider == "openai":
        images = []
        from .storage import get_media_bytes

        assets = db.scalars(
            select(MediaAsset)
            .join(PostMedia, PostMedia.media_id == MediaAsset.id)
            .where(PostMedia.version_id == version.id, MediaAsset.state == "ready")
            .order_by(PostMedia.position)
            .limit(4)
        ).all()
        for asset in assets:
            if asset.storage_key:
                images.append(get_media_bytes(asset.storage_key))
        result, cost = structured_extract(version.caption, images)
        total_media = len(db.scalars(select(PostMedia.id).where(PostMedia.version_id == version.id)).all())
        if total_media > len(images):
            result.warnings.append(
                f"Only {len(images)} of {total_media} media items analyzed; review image/product associations."
            )
    else:
        result = extract_caption(version.caption)
    validate_grounding(result, version.caption)
    run = ExtractionRun(
        version_id=version.id,
        input_hash=digest([version.id, version.content_hash]),
        pipeline_version=full_version,
        provider=provider,
        output=result.model_dump(mode="json"),
        cost_usd=cost,
    )
    db.add(run)
    db.flush()
    account = db.get(SourceAccount, post.account_id)
    fields = {
        name: getattr(result, name).value
        for name in ["primary_flower", "color", "arrangement", "stem_count", "style", "occasion"]
    }
    key = digest(
        {
            "seller": account.seller_id,
            "identity": version.payload.get("product_key") or f"{post.platform}:{post.platform_post_id}",
            "configuration": {key: fields[key] for key in ["primary_flower", "color", "arrangement", "stem_count"]},
        }
    )
    listing = db.scalar(select(Listing).where(Listing.seller_id == account.seller_id, Listing.configuration_key == key))
    if not listing:
        listing = Listing(
            seller_id=account.seller_id,
            configuration_key=key,
            title=title_for(fields),
            description="",
            **fields,
            attributes={"warnings": result.warnings},
            search_text=fold(version.caption),
            is_demo=False,
        )
        db.add(listing)
        db.flush()
    if not db.scalar(
        select(ListingSource).where(ListingSource.listing_id == listing.id, ListingSource.version_id == version.id)
    ):
        db.add(ListingSource(listing_id=listing.id, version_id=version.id))
    for name in type(result).model_fields:
        field = getattr(result, name)
        if hasattr(field, "evidence_refs"):
            db.add(
                FieldAssertion(
                    listing_id=listing.id,
                    run_id=run.id,
                    field=name,
                    value={"value": field.value},
                    evidence=[{**ref.model_dump(), "version_id": version.id} for ref in field.evidence_refs],
                    status=field.status,
                )
            )
    for claim in result.prices:
        db.add(
            PriceObservation(
                listing_id=listing.id,
                version_id=version.id,
                amount_min=claim.amount_min,
                amount_max=claim.amount_max,
                currency=claim.currency,
                kind=claim.kind,
                component=claim.component,
                evidence={**claim.evidence.model_dump(), "currency_basis": claim.currency_basis},
                advertised_at=post.published_at,
            )
        )
    db.add(
        AvailabilityObservation(
            listing_id=listing.id,
            version_id=version.id,
            status="preorder" if result.lead_days.value is not None else "unknown",
            lead_days=result.lead_days.value,
            delivery=result.delivery.value,
            evidence={"lead_days": result.lead_days.model_dump(), "delivery": result.delivery.model_dump()},
        )
    )
    db.flush()
    ready_media = db.scalar(
        select(MediaAsset)
        .join(PostMedia, PostMedia.media_id == MediaAsset.id)
        .where(PostMedia.version_id == version.id, MediaAsset.state == "ready")
        .order_by(PostMedia.position)
        .limit(1)
    )
    if ready_media and listing.image_path is None:
        listing.image_path = f"/api/v1/media/{ready_media.id}"
    return {"listing_id": listing.id, "run_id": run.id, "review_required": True}


def review_listing(db, listing: Listing, decision: ReviewDecision, actor):
    before = {
        name: getattr(listing, name)
        for name in ["state", "primary_flower", "color", "arrangement", "stem_count", "title"]
    }
    if decision.decision == "reject":
        listing.state = "rejected"
    else:
        assertions = db.scalars(
            select(FieldAssertion)
            .where(FieldAssertion.listing_id == listing.id)
            .order_by(FieldAssertion.created_at, FieldAssertion.id)
        ).all()
        pending = [a for a in assertions if a.review_state == "pending"]
        for assertion in pending:
            if assertion.field == "flower_composition":
                listing.attributes = {**listing.attributes, "flower_composition": assertion.value.get("value") or []}
            if assertion.field in {"primary_flower", "color", "arrangement", "stem_count", "style", "occasion"}:
                setattr(listing, assertion.field, assertion.value.get("value"))
            assertion.review_state = "accepted"
        for name in ["primary_flower", "color", "arrangement", "stem_count"]:
            value = getattr(decision, name)
            if value is not None:
                if name == "stem_count" and value != before["stem_count"]:
                    quote = decision.configuration_evidence_quote or ""
                    captions = [
                        db.get(PostVersion, a.version_id).caption
                        for a in db.scalars(select(ListingSource).where(ListingSource.listing_id == listing.id)).all()
                    ]
                    if not quote or not any(
                        quote in caption and extract_caption(quote).stem_count.value == value for caption in captions
                    ):
                        raise ValueError("A corrected stem count requires a matching caption quote.")
                setattr(listing, name, value)
                db.add(
                    FieldAssertion(
                        listing_id=listing.id,
                        field=name,
                        value={"value": value},
                        evidence=[
                            {"actor": actor, "reason": decision.reason, "quote": decision.configuration_evidence_quote}
                        ],
                        status="stated" if name == "stem_count" else "visual_inference",
                        review_state="corrected",
                    )
                )
        candidates = db.scalars(
            select(PriceObservation)
            .where(
                PriceObservation.listing_id == listing.id,
                PriceObservation.component == "bouquet",
                PriceObservation.kind != "previous",
            )
            .order_by(PriceObservation.advertised_at.desc(), PriceObservation.created_at.desc())
        ).all()
        latest_version = candidates[0].version_id if candidates else None
        current = [p for p in candidates if p.version_id == latest_version]
        if len(current) > 1 and decision.price_minor is None:
            raise ValueError("Associate the correct product price before accepting multiple prices.")
        if decision.price_minor is not None:
            quote = decision.price_evidence_quote or ""
            sources = db.scalars(
                select(PostVersion)
                .join(ListingSource, ListingSource.version_id == PostVersion.id)
                .where(ListingSource.listing_id == listing.id)
            ).all()
            selected = next((v for v in sources if quote and quote in v.caption), None)
            parsed, _ = extract_prices(quote)
            exact = next(
                (
                    p
                    for p in parsed
                    if p.component == "bouquet"
                    and p.kind in {"exact", "promotion"}
                    and p.amount_min == decision.price_minor
                    and p.amount_max == decision.price_minor
                ),
                None,
            )
            if not selected or not exact:
                raise ValueError("Corrected prices require an exact matching monetary quote from a source caption.")
            post = db.get(SourcePost, selected.post_id)
            for price in candidates:
                price.superseded = True
            corrected = PriceObservation(
                listing_id=listing.id,
                version_id=selected.id,
                amount_min=exact.amount_min,
                amount_max=exact.amount_max,
                currency=exact.currency,
                kind=exact.kind,
                component="bouquet",
                reviewed=True,
                evidence={"quote": quote, "actor": actor, "currency_basis": exact.currency_basis},
                advertised_at=post.published_at,
            )
            db.add(corrected)
        else:
            for price in candidates:
                if price.version_id == latest_version:
                    price.reviewed = True
                else:
                    price.superseded = True
        listing.state = "published"
        listing.title = title_for({key: getattr(listing, key) for key in ["primary_flower", "color", "arrangement"]})
        listing.description = (
            f"{listing.title}. "
            + (f"{listing.stem_count} cành theo nội dung quảng cáo. " if listing.stem_count else "")
            + "Liên hệ người bán để xác nhận tình trạng hàng."
        )
        listing.attributes = {
            **listing.attributes,
            "size_reviewed": listing.stem_count is not None,
            "extraction_reviewed": True,
        }
        accepted_availability = db.scalar(
            select(AvailabilityObservation)
            .where(AvailabilityObservation.listing_id == listing.id)
            .order_by(AvailabilityObservation.created_at.desc())
            .limit(1)
        )
        if accepted_availability:
            listing.attributes = {
                **listing.attributes,
                "accepted_availability": {
                    "status": accepted_availability.status,
                    "lead_days": accepted_availability.lead_days,
                    "delivery": accepted_availability.delivery,
                },
            }
        listing.search_text = fold(
            " ".join(
                str(getattr(listing, name) or "")
                for name in ["title", "description", "primary_flower", "color", "style", "occasion", "arrangement"]
            )
        )
        snapshot = {
            key: getattr(listing, key)
            for key in [
                "title",
                "description",
                "primary_flower",
                "color",
                "arrangement",
                "stem_count",
                "style",
                "occasion",
            ]
        }
        revision = ListingRevision(listing_id=listing.id, snapshot=snapshot)
        db.add(revision)
        db.flush()
        listing.current_revision_id = revision.id
        from .catalog import demo_vector

        if listing.is_demo:
            db.add(
                TextEmbedding(
                    revision_id=revision.id, model_version="demo-lexical-v1", vector=demo_vector(listing.search_text)
                )
            )
        elif get_settings().openai_api_key:
            enqueue(
                db,
                "embed-text",
                {"listing_id": listing.id, "revision_id": revision.id},
                f"text:{revision.id}:{get_settings().embedding_model}",
            )
    db.add(
        ReviewAction(
            listing_id=listing.id,
            actor=actor,
            decision=decision.decision,
            reason=decision.reason,
            changes={"before": before, "submitted": decision.model_dump(exclude_none=True)},
        )
    )
    db.flush()
