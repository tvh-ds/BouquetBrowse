"""Resolve explicit permalink IDs alongside API IDs without changing ownership."""

import re
from urllib.parse import urlsplit

from sqlalchemy import select

from .models import SourcePost

THREAD = re.compile(r"^/@[A-Za-z0-9_.]{1,100}/post/([A-Za-z0-9_-]{1,100})/?$")
HOSTS = {"threads.com", "www.threads.com", "threads.net", "www.threads.net"}


def permalink_code(url):
    if not url:
        return None
    parsed = urlsplit(str(url))
    match = THREAD.fullmatch(parsed.path)
    return match[1] if parsed.scheme == "https" and parsed.hostname in HOSTS and match else None


def matching_permalinks(db, platform, code):
    candidates = db.scalars(
        select(SourcePost).where(
            SourcePost.platform == platform, SourcePost.url.contains("/post/" + code, autoescape=True)
        )
    )
    return [p for p in candidates if permalink_code(p.url) == code]


def find_source(db, platform, platform_id, url=None):
    direct = db.scalar(
        select(SourcePost).where(SourcePost.platform == platform, SourcePost.platform_post_id == platform_id)
    )
    code = permalink_code(url) if platform == "threads" else None
    if not code:
        return direct
    candidates = matching_permalinks(db, platform, code)
    if len(candidates) > 1 or direct and candidates and direct.id != candidates[0].id:
        raise ValueError("Conflicting source identifiers require review")
    return direct or (candidates[0] if candidates else None)


def find_parent(db, platform_id):
    direct = db.scalar(
        select(SourcePost.id).where(SourcePost.platform == "threads", SourcePost.platform_post_id == platform_id)
    )
    if direct:
        return direct
    matches = matching_permalinks(db, "threads", platform_id)
    return matches[0].id if len(matches) == 1 else None
