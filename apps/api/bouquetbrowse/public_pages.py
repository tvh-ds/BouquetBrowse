"""Bounded anonymous post-page collection. Never uses account sessions or private APIs."""

import ipaddress
import json
import re
import socket
from datetime import datetime
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit, urlunsplit

import httpx

from .adapters import consume_quota
from .providers import CapabilityError

MAX_BYTES = 2 * 1024 * 1024
HOSTS = {"threads.com", "www.threads.com", "threads.net", "www.threads.net", "instagram.com", "www.instagram.com"}
VERSION = "public-html-v1"


def post_identity(url: str, allow_share=False):
    try:
        p = urlsplit(url)
        if p.scheme != "https" or p.hostname not in HOSTS or p.username or p.password or p.port not in {None, 443}:
            raise ValueError
    except ValueError:
        raise CapabilityError(
            "Use an HTTPS Threads or Instagram post URL without credentials.", "unsafe_page_url"
        ) from None
    platform = "instagram" if "instagram" in p.hostname else "threads"
    if allow_share and platform == "threads" and re.fullmatch(r"/share/[A-Za-z0-9_-]{1,100}/?", p.path):
        return platform, None, None, urlunsplit(("https", p.hostname, p.path, "", ""))
    pattern = (
        r"/(?:p|reel)/([A-Za-z0-9_-]{1,100})/?"
        if platform == "instagram"
        else r"/@([A-Za-z0-9_.]{1,100})/post/([A-Za-z0-9_-]{1,100})/?"
    )
    match = re.fullmatch(pattern, p.path)
    if not match:
        raise CapabilityError(
            "Open an individual post and copy its URL. Profiles and search pages are not supported.",
            "post_url_required",
        )
    return (
        platform,
        match[len(match.groups())],
        match[1] if platform == "threads" else None,
        urlunsplit(("https", p.hostname, p.path, "", "")),
    )


def public_destination(host):
    try:
        addresses = {r[4][0] for r in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)}
    except OSError:
        raise CapabilityError("Public page hostname could not be resolved.", "page_unavailable") from None
    if not addresses or any(not ipaddress.ip_address(a).is_global for a in addresses):
        raise CapabilityError("Public page destination is not a public network address.", "unsafe_page_url")
    return sorted(addresses)[0]


def fetch_html(url: str):
    platform, post_id, _, url = post_identity(url, allow_share=True)
    try:
        with httpx.Client(timeout=15, follow_redirects=False, trust_env=False) as client:
            for _ in range(3):
                consume_quota("public-pages", 100)
                host = urlsplit(url).hostname
                address = public_destination(host)
                request = httpx.Request(
                    "GET",
                    httpx.URL(url).copy_with(host=address),
                    headers={
                        "Host": host,
                        "User-Agent": "BouquetBrowse/0.1 (public post preview)",
                        "Accept": "text/html",
                    },
                    extensions={"sni_hostname": host},
                )
                response = client.send(request, stream=True)
                try:
                    if response.status_code in {301, 302, 303, 307, 308}:
                        target = urljoin(url, response.headers.get("location", ""))
                        try:
                            target_platform, target_id, _, target = post_identity(target)
                        except CapabilityError:
                            raise CapabilityError(
                                "The post redirects to login or an unsupported page. Supply a permitted caption through operator import.",
                                "page_access_required",
                            ) from None
                        if target_platform != platform or post_id is not None and target_id != post_id:
                            raise CapabilityError(
                                "The source redirected to a different post.", "page_identity_mismatch"
                            )
                        post_id, url = target_id, target
                        continue
                    if response.status_code in {401, 403, 429}:
                        raise CapabilityError(
                            "The source restricted anonymous access or rate-limited this request. No session or bypass was attempted.",
                            "page_access_required",
                        )
                    if response.status_code != 200:
                        raise CapabilityError("The public post could not be retrieved.", "page_unavailable")
                    if response.headers.get("content-type", "").split(";")[0].strip().lower() not in {
                        "text/html",
                        "application/xhtml+xml",
                    }:
                        raise CapabilityError("The source did not return an HTML post page.", "page_format_unsupported")
                    parts, size = [], 0
                    for chunk in response.iter_bytes():
                        size += len(chunk)
                        if size > MAX_BYTES:
                            raise CapabilityError("The page exceeds the 2 MB parsing limit.", "page_too_large")
                        parts.append(chunk)
                    return b"".join(parts).decode("utf-8", errors="replace"), url
                finally:
                    response.close()
    except httpx.HTTPError:
        raise CapabilityError(
            "The anonymous public-page request failed. Retry later or use operator import.", "page_unavailable"
        ) from None
    raise CapabilityError("The source redirected too many times.", "page_redirect_limit")


class Metadata(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.meta, self.documents, self.script = {}, [], None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "meta":
            key = (a.get("property") or a.get("name") or "").lower()
            self.meta.setdefault(key, []).append(a.get("content", ""))
        if tag == "script" and a.get("type", "").lower() == "application/ld+json":
            self.script = []

    def handle_data(self, data):
        if self.script is not None:
            self.script.append(data)

    def handle_endtag(self, tag):
        if tag == "script" and self.script is not None:
            try:
                self.documents.append(json.loads("".join(self.script)))
            except (ValueError, RecursionError):
                pass
            self.script = None


def parse_page(html: str, url: str):
    platform, post_id, username, canonical = post_identity(url)
    if len(html.encode("utf-8")) > MAX_BYTES:
        raise CapabilityError("The page exceeds the 2 MB parsing limit.", "page_too_large")
    parser = Metadata()
    parser.feed(html)

    def meta(key):
        return next(iter(parser.meta.get(key, [])), None)

    if meta("og:url"):
        try:
            if post_identity(meta("og:url"))[:2] != (platform, post_id):
                raise ValueError
        except (CapabilityError, ValueError):
            raise CapabilityError(
                "Page metadata does not identify the requested post; it may be a login page.", "page_identity_mismatch"
            ) from None
    # Walk only structured metadata; scripts, hidden hydration payloads and page instructions are never executed.
    pending, posts, visited = list(parser.documents), [], 0
    while pending and visited < 5000:
        node = pending.pop()
        visited += 1
        if isinstance(node, list):
            pending.extend(node)
        elif isinstance(node, dict):
            kinds = node.get("@type", [])
            if isinstance(kinds, str):
                kinds = [kinds]
            if not isinstance(kinds, list):
                kinds = []
            if any(isinstance(k, str) and k in {"SocialMediaPosting", "InstagramPosting"} for k in kinds):
                posts.append(node)
            else:
                pending.extend(v for v in node.values() if isinstance(v, (dict, list)))
    if len(posts) > 1:
        raise CapabilityError(
            "Multiple products or posts were found. Use operator import to associate the correct caption.",
            "page_ambiguous",
        )
    post = posts[0] if posts else {}
    if post.get("url"):
        try:
            if not isinstance(post["url"], str):
                raise ValueError
            other = post_identity(post["url"])
            if other[:2] != (platform, post_id):
                raise ValueError
        except (CapabilityError, ValueError, TypeError):
            raise CapabilityError("Page metadata refers to a different post.", "page_identity_mismatch") from None
    caption = post.get("articleBody") or meta("og:description") or meta("description")
    if (
        not isinstance(caption, str)
        or not caption.strip()
        or caption.strip().lower() in {"instagram", "threads", "log in to instagram", "log in to threads"}
    ):
        raise CapabilityError(
            "No usable public caption was found. The page may require login or client-side rendering; use operator import.",
            "page_content_unavailable",
        )
    if len(caption) > 20000:
        raise CapabilityError("The caption exceeds the import limit.", "page_too_large")
    author = post.get("author", {})
    if not username and isinstance(author, dict):
        handle = author.get("alternateName")
        if isinstance(handle, str) and re.fullmatch(r"@?[A-Za-z0-9_.]{1,100}", handle):
            username = handle.lstrip("@")
        elif isinstance(author.get("url"), str):
            p = urlsplit(author["url"])
            if p.hostname in HOSTS and "instagram" in p.hostname and re.fullmatch(r"/[A-Za-z0-9_.]{1,100}/?", p.path):
                username = p.path.strip("/")
    published = post.get("datePublished") or meta("article:published_time") or meta("og:published_time")
    try:
        published = datetime.fromisoformat(published.replace("Z", "+00:00"))
        if published.tzinfo is None:
            raise ValueError
        published = published.isoformat()
    except (ValueError, TypeError, AttributeError):
        published = None
    candidates = parser.meta.get("og:image", [])
    image = post.get("image")
    for item in image if isinstance(image, list) else [image]:
        candidates.append(item.get("url") if isinstance(item, dict) else item)
    images = []
    for image in candidates:
        if isinstance(image, str):
            p = urlsplit(image)
            if (
                p.scheme == "https"
                and not p.username
                and not p.password
                and ((p.hostname or "").endswith(".fbcdn.net") or (p.hostname or "").endswith(".cdninstagram.com"))
                and image not in images
            ):
                images.append(image)
    warnings = [
        "HTML metadata can be incomplete or truncated. Verify the caption and image association against the source before importing."
    ]
    if not published:
        warnings.append(
            "Publication time is missing or lacks a timezone. Supply the original publication time; collection time is not a substitute."
        )
    if not username:
        warnings.append("Seller username was not exposed. Supply it from the source.")
    return {
        "parser_version": VERSION,
        "warnings": warnings,
        "draft": {
            "platform": platform,
            "platform_post_id": post_id,
            "username": username or "",
            "seller_name": "",
            "seller_slug": "",
            "district": "",
            "city": "Hanoi",
            "source_url": canonical,
            "published_at": published,
            "caption": caption.strip(),
            "media_urls": images[:10],
            "rights_confirmed": False,
        },
    }


def collect_page(url: str):
    html, final_url = fetch_html(url)
    return parse_page(html, final_url)
