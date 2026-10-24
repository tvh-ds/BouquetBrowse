from datetime import timedelta
from urllib.parse import urlparse

import httpx
from sqlalchemy import select, text

from .config import get_settings
from .db import SessionLocal, utcnow
from .models import RateBucket
from .providers import CapabilityError


def consume_quota(key: str, maximum: int, seconds=86400):
    slot = int(utcnow().timestamp()) // seconds
    bucket_key = f"{key}:{slot}"
    with SessionLocal() as db:
        if db.bind.dialect.name == "postgresql":
            db.execute(text("SELECT pg_advisory_xact_lock(73402912)"))
        bucket = db.scalar(select(RateBucket).where(RateBucket.key == bucket_key).with_for_update())
        if bucket is None:
            bucket = RateBucket(key=bucket_key, count=0, expires_at=utcnow() + timedelta(seconds=seconds))
            db.add(bucket)
        if bucket.count >= maximum:
            raise CapabilityError(
                "Application request allowance reached. Retry after the current window.",
                "rate_limited",
                retryable=True,
                retry_after=seconds,
            )
        bucket.count += 1
        db.commit()


def capability_status():
    s = get_settings()
    return [
        {
            "id": "operator",
            "name": "Operator imports",
            "enabled": True,
            "state": "ready",
            "detail": "Paste attributable captions and explicit seller/location information. Commercial fields enter review.",
        },
        {
            "id": "public-pages",
            "name": "Public post HTML preview",
            "enabled": True,
            "state": "manual_preview",
            "detail": "Collect individual public Threads/Instagram post URLs in Import. Anonymous HTML only; source restrictions may prevent collection. Complete missing facts and review before publication.",
        },
        {
            "id": "threads",
            "name": "Threads keyword discovery",
            "enabled": bool(s.threads_access_token and s.threads_search_approved),
            "state": "ready" if s.threads_access_token and s.threads_search_approved else "needs_configuration",
            "detail": "Requires a token and confirmed threads_keyword_search approval. Coverage, returned fields and quotas remain account-specific.",
        },
        {
            "id": "instagram",
            "name": "Instagram business discovery",
            "enabled": bool(
                s.instagram_access_token
                and s.instagram_user_id
                and s.instagram_graph_version
                and s.instagram_discovery_approved
            ),
            "state": "ready"
            if s.instagram_access_token
            and s.instagram_user_id
            and s.instagram_graph_version
            and s.instagram_discovery_approved
            else "needs_configuration",
            "detail": "Requires a supported professional account, approved read access, and a pinned Graph version. Consumer accounts are unsupported.",
        },
    ]


def request_json(url, token, params):
    consume_quota("source-discovery", 100)
    with httpx.Client(timeout=20, follow_redirects=False) as client:
        response = client.get(url, headers={"Authorization": f"Bearer {token}"}, params=params)
    if response.status_code == 429:
        retry_after = response.headers.get("retry-after", "300")
        raise CapabilityError(
            "Source rate limit reached. The worker will respect Retry-After.",
            "source_rate_limited",
            True,
            int(retry_after) if retry_after.isdigit() else 300,
        )
    if response.status_code in {401, 403}:
        raise CapabilityError(
            "Source authorization failed. Verify the token and approved read permissions.",
            "source_authorization_required",
        )
    if response.status_code >= 500:
        raise CapabilityError("Source service is temporarily unavailable.", "source_unavailable", True)
    if response.status_code != 200:
        raise CapabilityError(
            "Source rejected this documented read request. Verify API version, fields and account capabilities.",
            "source_contract_error",
        )
    result = response.json()
    if not isinstance(result, dict) or result.get("error"):
        raise CapabilityError("Source returned an invalid or error response.", "source_contract_error")
    return result


def discover(source: str, query: str, username: str | None = None):
    s = get_settings()
    capability = next((c for c in capability_status() if c["id"] == source), None)
    if not capability or not capability["enabled"]:
        raise CapabilityError(capability["detail"] if capability else "Unknown source adapter.")
    if source == "threads":
        parsed = urlparse(s.threads_api_base)
        if parsed.scheme != "https" or parsed.hostname not in {"graph.threads.net", "graph.threads.com"}:
            raise CapabilityError("Threads API base must use the official HTTPS Graph host.")
        payload = request_json(
            f"{s.threads_api_base.rstrip('/')}/keyword_search",
            s.threads_access_token,
            {
                "q": query,
                "search_type": "RECENT",
                "limit": 25,
                "fields": "id,text,timestamp,permalink,username,media_type,media_url",
            },
        )
        return payload.get("data", []), {
            "coverage": "bounded_search_sample",
            "next_page_available": bool(payload.get("paging", {}).get("next")),
        }
    if source == "instagram":
        if not username:
            raise CapabilityError("Choose a registered professional seller username.", "seller_required")
        if (
            not s.instagram_graph_version.startswith("v")
            or not s.instagram_graph_version[1:].replace(".", "").isdigit()
        ):
            raise CapabilityError("Pin a valid Graph API version from the app dashboard.")
        fields = f"business_discovery.username({username}){{username,media.limit(25){{id,caption,media_type,media_url,permalink,timestamp}}}}"
        payload = request_json(
            f"https://graph.facebook.com/{s.instagram_graph_version}/{s.instagram_user_id}",
            s.instagram_access_token,
            {"fields": fields},
        )
        media = payload.get("business_discovery", {}).get("media", {})
        return [{**row, "username": username} for row in media.get("data", [])], {
            "coverage": "known_professional_account",
            "next_page_available": bool(media.get("paging", {}).get("next")),
        }
    raise CapabilityError("Operator records are imported through the import endpoint.")
