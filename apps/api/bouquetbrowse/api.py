import hashlib
import hmac
import logging
from contextlib import asynccontextmanager
from uuid import uuid4

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from sqlalchemy import func, or_, select, text
from sqlalchemy.orm import Session

from .adapters import capability_status, consume_quota
from .auth import User, demo_token, require_admin, require_proxy, require_reviewer, require_user, supabase_password
from .catalog import all_listings, card, catalog, commercial_issues, comparison, price_json, similar
from .config import get_settings
from .db import Base, SessionLocal, aware, engine, get_db, utcnow
from .models import (
    CostEntry,
    FieldAssertion,
    IngestionCursor,
    Job,
    Listing,
    ListingSource,
    MediaAsset,
    PostMedia,
    PostVersion,
    PriceObservation,
    ReviewAction,
    Seller,
    SourcePost,
    TakedownRequest,
)
from .pipeline import digest, enqueue, ingest, review_listing
from .providers import CapabilityError
from .responses import CatalogView, ComparisonView, DetailView, FacetsView, SessionView, SimilarView
from .schemas import (
    ImportBatch,
    LoginBody,
    PublicPagePreview,
    PublicPageRequest,
    ReviewDecision,
    SyncBody,
    TakedownBody,
)
from .seed import seed_demo

logger = logging.getLogger("bouquetbrowse")


@asynccontextmanager
async def lifespan(app):
    if get_settings().app_mode == "demo":
        Base.metadata.create_all(engine)
        with SessionLocal() as db:
            seed_demo(db)
    yield


app = FastAPI(
    title="BouquetBrowse API",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs" if get_settings().app_mode == "demo" else None,
    openapi_url="/openapi.json" if get_settings().app_mode == "demo" else None,
    redoc_url=None,
)

from .discovery_api import router as discovery_router  # noqa: E402

app.include_router(discovery_router)


@app.middleware("http")
async def request_context(request, call_next):
    request.state.request_id = str(uuid4())
    try:
        content_length = int(request.headers.get("content-length", "0") or 0)
    except ValueError:
        return JSONResponse(
            {"error": {"code": "invalid_length", "message": "Invalid Content-Length."}}, status_code=400
        )
    if content_length > 5 * 1024 * 1024:
        return JSONResponse(
            {"error": {"code": "payload_too_large", "message": "Request exceeds 5 MB."}}, status_code=413
        )
    try:
        response = await call_next(request)
    except Exception:
        logger.error("request_failed request_id=%s", request.state.request_id)
        response = JSONResponse(
            {
                "error": {
                    "code": "internal_error",
                    "message": "Unable to complete this request. Use the request ID when reporting the problem.",
                }
            },
            status_code=500,
        )
    response.headers["X-Request-ID"] = request.state.request_id
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


@app.exception_handler(HTTPException)
async def http_error(request, exc):
    detail = exc.detail if isinstance(exc.detail, dict) else {"code": "request_failed", "message": exc.detail}
    return JSONResponse(
        {"error": {**detail, "request_id": getattr(request.state, "request_id", None)}}, status_code=exc.status_code
    )


@app.exception_handler(RequestValidationError)
async def validation_error(request, exc):
    # Never echo submitted passwords, tokens, captions or raw request bodies.
    fields = [".".join(str(part) for part in error["loc"]) for error in exc.errors()]
    return JSONResponse(
        {
            "error": {
                "code": "validation_error",
                "message": "Check the required fields and their formats.",
                "fields": fields,
                "request_id": request.state.request_id,
            }
        },
        status_code=422,
    )


@app.exception_handler(CapabilityError)
async def capability_error(request, exc):
    return JSONResponse(
        {"error": {"code": exc.code, "message": str(exc), "request_id": request.state.request_id}},
        status_code=409 if not exc.retryable else 429,
    )


@app.exception_handler(ValueError)
async def value_error(request, exc):
    return JSONResponse(
        {"error": {"code": "invalid_operation", "message": str(exc), "request_id": request.state.request_id}},
        status_code=422,
    )


@app.get("/health/live")
def health_live():
    return {"status": "ok"}


@app.get("/health/ready")
def health_ready(db: Session = Depends(get_db)):
    db.execute(text("SELECT 1"))
    db.execute(select(Listing.id).limit(1))
    return {"status": "ready"}


@app.get("/auth/config", dependencies=[Depends(require_proxy)])
def auth_config():
    return {
        "mode": get_settings().app_mode,
        "demo_accounts": ["admin", "tester"] if get_settings().app_mode == "demo" else [],
    }


@app.post("/auth/login", dependencies=[Depends(require_proxy)])
def login(body: LoginBody, request: Request):
    key = hashlib.sha256(body.email.lower().encode()).hexdigest()[:24]
    consume_quota(f"login:{key}", 10, 900)
    s = get_settings()
    if s.app_mode == "demo":
        accounts = {
            "admin@bouquetbrowse.local": ("demo-admin", "admin"),
            "tester@bouquetbrowse.local": ("demo-tester", "tester"),
        }
        account = accounts.get(body.email.lower())
        if not account or not hmac.compare_digest(body.password, account[0]):
            raise HTTPException(
                401,
                detail={"code": "invalid_credentials", "message": "Use a documented localhost demonstration account."},
            )
        return {"access_token": demo_token(account[1]), "expires_in": 8 * 3600}
    return supabase_password(body.email, body.password)


@app.post("/auth/refresh", dependencies=[Depends(require_proxy)])
def refresh(body: dict):
    s = get_settings()
    if s.app_mode != "pilot" or not isinstance(body.get("refresh_token"), str) or len(body["refresh_token"]) > 4096:
        raise HTTPException(401, detail="Sign in again.")
    response = httpx.post(
        f"{s.supabase_url}/auth/v1/token?grant_type=refresh_token",
        headers={"apikey": s.supabase_publishable_key},
        json={"refresh_token": body["refresh_token"]},
        timeout=15,
    )
    if response.status_code != 200:
        raise HTTPException(401, detail="Session expired. Sign in again.")
    data = response.json()
    return {key: data[key] for key in ["access_token", "refresh_token", "expires_in"]}


@app.get("/v1/session", response_model=SessionView)
def get_session(user: User = Depends(require_user)):
    return {"id": user.id, "role": user.role, "mode": get_settings().app_mode}


def published_listing(db, listing_id):
    listing = db.get(Listing, listing_id)
    if not listing or listing.state != "published":
        raise HTTPException(404, detail={"code": "listing_not_found", "message": "This bouquet is unavailable."})
    return listing


def detail(db, listing):
    source_rows = db.execute(
        select(SourcePost, PostVersion)
        .join(PostVersion, PostVersion.post_id == SourcePost.id)
        .join(ListingSource, ListingSource.version_id == PostVersion.id)
        .where(ListingSource.listing_id == listing.id)
        .order_by(SourcePost.published_at.desc())
    ).all()
    assertions = db.scalars(
        select(FieldAssertion).where(FieldAssertion.listing_id == listing.id).order_by(FieldAssertion.created_at.desc())
    ).all()
    return {
        **card(db, listing),
        "sources": [
            {
                "id": post.id,
                "url": post.url,
                "platform": post.platform,
                "published_at": aware(post.published_at).isoformat(),
                "last_seen_at": aware(post.last_seen_at).isoformat(),
                "caption": version.caption,
                "version_id": version.id,
            }
            for post, version in source_rows
        ],
        "assertions": [
            {
                "id": a.id,
                "field": a.field,
                "value": a.value,
                "status": a.status,
                "review_state": a.review_state,
                "evidence": a.evidence,
                "calibrated_confidence": a.calibrated_confidence,
            }
            for a in assertions
        ],
        "warnings": listing.attributes.get("warnings", []),
    }


@app.get("/v1/catalog", dependencies=[Depends(require_user)], response_model=CatalogView)
def get_catalog(
    q: str = Query("", max_length=200),
    flower: str = "",
    color: str = "",
    district: str = "",
    arrangement: str = "",
    occasion: str = "",
    delivery: bool | None = None,
    max_price: int | None = Query(None, ge=0),
    min_price: int | None = Query(None, ge=0),
    sort: str = Query("recommended", pattern="^(recommended|price-asc|price-desc|freshest)$"),
    cursor: str | None = Query(None, max_length=1000),
    limit: int = Query(24, ge=1, le=100),
    db: Session = Depends(get_db),
):
    return catalog(
        db, q, flower, color, district, arrangement, occasion, delivery, max_price, min_price, sort, cursor, limit
    )


@app.get("/v1/catalog/facets", dependencies=[Depends(require_user)], response_model=FacetsView)
def facets(db: Session = Depends(get_db)):
    listings = all_listings(db)
    return {
        "flowers": sorted({listing.primary_flower for listing in listings if listing.primary_flower}),
        "colors": sorted({listing.color for listing in listings if listing.color}),
        "arrangements": sorted({listing.arrangement for listing in listings if listing.arrangement}),
        "occasions": sorted({listing.occasion for listing in listings if listing.occasion}),
        "districts": sorted({db.get(Seller, listing.seller_id).district for listing in listings}),
    }


@app.get("/v1/listings/{listing_id}", dependencies=[Depends(require_user)], response_model=DetailView)
def get_listing(listing_id: str, db: Session = Depends(get_db)):
    return detail(db, published_listing(db, listing_id))


@app.get("/v1/listings/{listing_id}/similar", dependencies=[Depends(require_user)], response_model=SimilarView)
def get_similar(listing_id: str, limit: int = Query(12, ge=1, le=50), db: Session = Depends(get_db)):
    return {"items": similar(db, published_listing(db, listing_id), limit)}


@app.get("/v1/listings/{listing_id}/comparison", dependencies=[Depends(require_user)], response_model=ComparisonView)
def get_comparison(listing_id: str, db: Session = Depends(get_db)):
    return comparison(db, published_listing(db, listing_id))


@app.get("/v1/listings/{listing_id}/price-history", dependencies=[Depends(require_user)])
def get_history(listing_id: str, db: Session = Depends(get_db)):
    listing = published_listing(db, listing_id)
    prices = db.scalars(
        select(PriceObservation)
        .where(
            PriceObservation.listing_id == listing.id,
            PriceObservation.component == "bouquet",
            PriceObservation.reviewed.is_(True),
        )
        .order_by(PriceObservation.advertised_at, PriceObservation.id)
    ).all()
    return {
        "is_demo": listing.is_demo,
        "items": [price_json(p) for p in prices],
        "note": "Advertised observations, not confirmed transaction prices.",
    }


@app.get("/v1/sellers/{seller_id}", dependencies=[Depends(require_user)])
def get_seller(seller_id: str, db: Session = Depends(get_db)):
    seller = db.scalar(select(Seller).where(or_(Seller.id == seller_id, Seller.slug == seller_id)))
    if not seller:
        raise HTTPException(404, detail="Seller not found.")
    return {
        "seller": {
            "id": seller.id,
            "name": seller.name,
            "district": seller.district,
            "city": seller.city,
            "slug": seller.slug,
            "bio": seller.bio,
            "profile_url": seller.profile_url,
            "is_demo": seller.is_demo,
        },
        "items": [
            card(db, listing)
            for listing in db.scalars(
                select(Listing).where(Listing.seller_id == seller.id, Listing.state == "published")
            ).all()
        ],
    }


@app.get("/v1/analytics/cohorts", dependencies=[Depends(require_user)])
def analytics(listing_id: str | None = None, db: Session = Depends(get_db)):
    listings = all_listings(db)
    eligible = [listing for listing in listings if not commercial_issues(db, listing)]
    target = published_listing(db, listing_id) if listing_id else next(iter(eligible), None)
    compared = comparison(db, target, persist=False) if target else None
    return {
        "catalog_count": len(listings),
        "seller_count": len({listing.seller_id for listing in listings}),
        "eligible_count": len(eligible),
        "is_demo": get_settings().app_mode == "demo",
        "targets": [
            {"id": listing.id, "title": listing.title, "seller": db.get(Seller, listing.seller_id).name}
            for listing in eligible
        ],
        "selected": card(db, target) if target else None,
        "comparison": compared,
        "historical_note": "Cohort seasonality requires longitudinal real coverage. No inferred market trends are shown.",
    }


@app.get("/v1/media/{media_id}", dependencies=[Depends(require_user)])
def get_media(media_id: str, db: Session = Depends(get_db)):
    asset = db.get(MediaAsset, media_id)
    active = db.scalar(
        select(Listing.id)
        .join(ListingSource, ListingSource.listing_id == Listing.id)
        .join(PostMedia, PostMedia.version_id == ListingSource.version_id)
        .where(PostMedia.media_id == media_id, Listing.state == "published")
        .limit(1)
    )
    if not asset or asset.state != "ready" or not asset.storage_key or not active:
        raise HTTPException(404, detail="Media not found.")
    from .storage import get_media_bytes

    try:
        content = get_media_bytes(asset.storage_key)
    except FileNotFoundError as exc:
        raise HTTPException(404, detail="Media not found.") from exc
    return Response(content, media_type="image/jpeg", headers={"Cache-Control": "private, no-store"})


@app.get("/v1/admin/sources", dependencies=[Depends(require_admin)])
def admin_sources(db: Session = Depends(get_db)):
    cursors = {c.source: c for c in db.scalars(select(IngestionCursor)).all()}
    return {
        "items": [
            {
                **source,
                "last_success_at": aware(cursors[source["id"]].last_success_at).isoformat()
                if source["id"] in cursors and cursors[source["id"]].last_success_at
                else None,
                "checkpoint": cursors[source["id"]].checkpoint if source["id"] in cursors else None,
            }
            for source in capability_status()
        ],
        "coverage": "Live source coverage is not validated. Demo records are fictional.",
    }


def request_key(value):
    if not value or len(value) > 160 or not all(char.isalnum() or char in "-_.:" for char in value):
        raise HTTPException(422, detail="Supply an Idempotency-Key of 1–160 letters, digits or -_.: characters.")
    return value


@app.post("/v1/admin/pages/preview", dependencies=[Depends(require_admin)], response_model=PublicPagePreview)
def preview_public_page(body: PublicPageRequest):
    from .public_pages import collect_page

    return collect_page(body.url)


@app.post("/v1/admin/imports", dependencies=[Depends(require_admin)])
def import_posts(body: ImportBatch, idempotency_key: str | None = Header(None), db: Session = Depends(get_db)):
    key = request_key(idempotency_key)
    receipt = db.scalar(select(Job).where(Job.idempotency_key == f"import:{key}"))
    body_hash = digest(body.model_dump(mode="json"))
    if receipt:
        if receipt.payload["body_hash"] != body_hash:
            raise HTTPException(409, detail="This import key was used for different content.")
        return receipt.result
    result = {
        "items": [ingest(db, post) for post in sorted(body.posts, key=lambda p: (p.platform, p.platform_post_id))]
    }
    db.add(
        Job(
            kind="import-receipt",
            payload={"body_hash": body_hash},
            idempotency_key=f"import:{key}",
            state="succeeded",
            result=result,
        )
    )
    db.commit()
    return result


@app.post("/v1/admin/sources/{source_id}/sync", dependencies=[Depends(require_admin)])
def sync_source(
    source_id: str, body: SyncBody, idempotency_key: str | None = Header(None), db: Session = Depends(get_db)
):
    capability = next((c for c in capability_status() if c["id"] == source_id), None)
    if not capability or not capability["enabled"] or source_id in {"operator", "public-pages"}:
        raise CapabilityError(capability["detail"] if capability else "Unsupported source adapter.")
    key = request_key(idempotency_key)
    job = enqueue(db, "sync", {"source": source_id, **body.model_dump()}, f"sync:{key}")
    db.commit()
    return {"job_id": job.id, "state": job.state}


@app.get("/v1/admin/jobs", dependencies=[Depends(require_admin)])
def admin_jobs(db: Session = Depends(get_db)):
    jobs = db.scalars(select(Job).where(Job.kind != "import-receipt").order_by(Job.created_at.desc()).limit(100)).all()
    return {
        "items": [
            {
                "id": j.id,
                "kind": j.kind,
                "state": j.state,
                "attempts": j.attempts,
                "created_at": aware(j.created_at).isoformat(),
                "last_error": j.last_error,
                "result": j.result,
            }
            for j in jobs
        ]
    }


@app.post("/v1/admin/jobs/{job_id}/retry", dependencies=[Depends(require_admin)])
def retry_job(job_id: str, db: Session = Depends(get_db)):
    job = db.get(Job, job_id)
    if not job or job.state != "failed":
        raise HTTPException(409, detail="Only failed jobs can be retried.")
    job.state, job.attempts, job.run_after, job.last_error = "queued", 0, utcnow(), None
    db.commit()
    return {"job_id": job.id, "state": job.state}


@app.get("/v1/admin/reviews", dependencies=[Depends(require_reviewer)])
def admin_reviews(db: Session = Depends(get_db)):
    pending_ids = select(FieldAssertion.listing_id).where(FieldAssertion.review_state == "pending")
    listings = db.scalars(
        select(Listing)
        .where(or_(Listing.state == "review", Listing.id.in_(pending_ids)), Listing.state != "withdrawn")
        .order_by(Listing.created_at.desc())
        .limit(100)
    ).all()
    return {"items": [detail(db, listing) for listing in listings]}


@app.post("/v1/admin/reviews/{listing_id}/decision")
def decide(
    listing_id: str, body: ReviewDecision, user: User = Depends(require_reviewer), db: Session = Depends(get_db)
):
    listing = db.get(Listing, listing_id)
    if not listing or listing.state == "withdrawn":
        raise HTTPException(404, detail="Review not found.")
    review_listing(db, listing, body, user.id)
    db.commit()
    return {"listing_id": listing.id, "state": listing.state}


@app.post("/v1/admin/listings/{listing_id}/reprocess", dependencies=[Depends(require_admin)])
def reprocess(listing_id: str, idempotency_key: str | None = Header(None), db: Session = Depends(get_db)):
    listing = published_listing(db, listing_id)
    link = db.scalar(
        select(ListingSource)
        .where(ListingSource.listing_id == listing.id)
        .order_by(ListingSource.created_at.desc())
        .limit(1)
    )
    key = request_key(idempotency_key)
    job = enqueue(
        db,
        "extract",
        {"version_id": link.version_id, "pipeline_version": f"hybrid-v1:replay:{key[:16]}"},
        f"reprocess:{key}",
    )
    db.commit()
    return {"job_id": job.id}


@app.post("/v1/admin/takedowns")
def takedown(
    body: TakedownBody,
    idempotency_key: str | None = Header(None),
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    key = request_key(idempotency_key)
    existing = db.scalar(select(TakedownRequest).where(TakedownRequest.idempotency_key == key))
    if existing:
        if existing.listing_id != body.listing_id:
            raise HTTPException(409, detail="Takedown key belongs to another listing.")
        return {"id": existing.id, "state": existing.state}
    listing = db.get(Listing, body.listing_id)
    if not listing:
        raise HTTPException(404, detail="Listing not found.")
    listing.state = "withdrawn"
    record = TakedownRequest(listing_id=listing.id, reason=body.reason, actor=user.id, idempotency_key=key)
    db.add(record)
    enqueue(db, "purge", {"listing_id": listing.id}, f"purge:{listing.id}")
    db.commit()
    return {"id": record.id, "state": record.state}


@app.get("/v1/admin/overview", dependencies=[Depends(require_admin)])
def overview(db: Session = Depends(get_db)):
    month = utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    spend = db.scalar(
        select(func.coalesce(func.sum(CostEntry.amount_usd), 0)).where(
            CostEntry.created_at >= month, CostEntry.state.in_(["reserved", "settled"])
        )
    )
    return {
        "mode": get_settings().app_mode,
        "published": db.scalar(select(func.count()).select_from(Listing).where(Listing.state == "published")),
        "pending_reviews": db.scalar(select(func.count()).select_from(Listing).where(Listing.state == "review")),
        "failed_jobs": db.scalar(select(func.count()).select_from(Job).where(Job.state == "failed")),
        "model_spend_usd": spend,
        "model_budget_usd": get_settings().monthly_model_budget_usd,
        "recent_actions": [
            {"id": a.id, "decision": a.decision, "reason": a.reason, "created_at": aware(a.created_at).isoformat()}
            for a in db.scalars(select(ReviewAction).order_by(ReviewAction.created_at.desc()).limit(10)).all()
        ],
    }
