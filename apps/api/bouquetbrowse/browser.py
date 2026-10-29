"""Bounded browser actions. Model output never becomes a selector or script."""

import json
import re
from contextlib import contextmanager
from pathlib import Path
from typing import Literal
from urllib.parse import urlencode, urljoin, urlsplit
from uuid import uuid4

from pydantic import Field

from .conversation_contracts import CaptureEnvelope, MessageObservation, validate_threads_url
from .extraction import fold
from .pipeline import digest
from .providers import CapabilityError
from .schemas import StrictModel
from .threads_dom import READ_SURFACE

FLOWERS = re.compile(r"\b(?:hoa|flowers?|florist|bouquet|rose|peony|lily|tulip|sunflower|cam chuong|cat tuong)\b")
POST = re.compile(r"^/@([A-Za-z0-9_.]{1,100})/post/([A-Za-z0-9_-]{1,100})/?$")
PROFILE = re.compile(r"^/@[A-Za-z0-9_.]{1,100}/?$")


def navigation_url(value):
    value = validate_threads_url(value)
    parsed = urlsplit(value)
    if not (POST.fullmatch(parsed.path) or PROFILE.fullmatch(parsed.path) or parsed.path in {"/", "/search"}):
        raise CapabilityError("This browser action is outside flower discovery.", "navigation_out_of_scope")
    if parsed.path != "/search" and parsed.query:
        raise CapabilityError("Unexpected navigation parameters.", "navigation_out_of_scope")
    return value


def search_url(query):
    if len(query) > 120 or not FLOWERS.search(fold(query)):
        raise CapabilityError("Search must stay within the flower taxonomy.", "query_out_of_scope")
    if not re.search(r"\b(?:ha noi|hanoi|hn)\b", fold(query)):
        query += " Hà Nội"
    return "https://www.threads.com/search?" + urlencode({"q": query, "serp_type": "default", "filter": "recent"})


@contextmanager
def profile_lock(directory):
    directory = Path(directory).resolve()
    marker = directory / "bouquetbrowse-profile.json"
    if directory.exists() and any(directory.iterdir()) and not marker.is_file():
        raise CapabilityError(
            "Choose an empty dedicated profile directory; existing profiles are not adopted.", "profile_not_owned"
        )
    directory.mkdir(parents=True, exist_ok=True)
    if marker.exists():
        if json.loads(marker.read_text(encoding="utf-8")).get("application") != "BouquetBrowse":
            raise CapabilityError("Profile ownership marker is invalid.", "profile_not_owned")
    else:
        marker.write_text(json.dumps({"application": "BouquetBrowse", "version": 1}), encoding="utf-8")
    with (directory / "session.lock").open("a+b") as stream:
        try:
            stream.seek(0)
            if stream.read(1) == b"":
                stream.write(b"1")
                stream.flush()
            stream.seek(0)
            import os

            if os.name == "nt":
                import msvcrt

                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise CapabilityError("Another process owns the dedicated browser.", "browser_busy") from None
        try:
            yield directory
        finally:
            stream.seek(0)
            if os.name == "nt":
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def normalize_surface(surface, flower_only=False):
    posts = []
    focal = POST.fullmatch(urlsplit(surface["url"]).path)
    for raw in surface.get("posts", [])[:100]:
        if raw.get("private"):
            continue
        match = POST.fullmatch(urlsplit(urljoin(surface["url"], raw.get("href", ""))).path)
        if not match:
            continue
        if flower_only and not FLOWERS.search(fold(raw.get("text", "") + " " + " ".join(raw.get("topics", [])))):
            continue  # Unrelated FYP content never enters evidence tables or model context.
        try:
            post = MessageObservation(
                platform_id=match[2],
                username=match[1],
                url=f"https://www.threads.com/@{match[1]}/post/{match[2]}",
                text=raw.get("text", ""),
                published_at=raw.get("published_at"),
                media_urls=raw.get("media_urls", [])[:10],
            )
        except ValueError:
            continue
        quote = POST.fullmatch(urlsplit(urljoin(surface["url"], raw.get("quoted") or "")).path)
        if raw.get("quoted") and quote:
            post.quote_of = quote[2]
        posts.append(post)
    # A reply permalink renders its ancestor chain before the focal message. Flat
    # search results and the replies below a root never establish immediate parents.
    if focal:
        positions = [i for i, p in enumerate(posts) if p.platform_id == focal[2]]
        if len(positions) == 1 and positions[0] > 0:
            chain = posts[: positions[0] + 1]
            if all(p.published_at for p in chain) and all(
                a.published_at <= b.published_at for a, b in zip(chain, chain[1:], strict=False)
            ):
                for parent, child in zip(chain, chain[1:], strict=False):
                    child.reply_to = parent.platform_id
    return posts


class BrowserAction(StrictModel):
    action: Literal[
        "search", "open_post", "visit_profile", "expand_replies", "open_sort", "set_sort", "scroll", "back", "finish"
    ]
    target: str | None = Field(default=None, max_length=80)
    observation_version: str = Field(max_length=80)
    query: str | None = Field(default=None, max_length=120)


class BrowserController:
    def __init__(self, page):
        self.page = page
        self.targets = {}
        self.version = None
        self.signature = None
        self.history = []
        self.navigated = False

    def read(self):
        if re.search(r"/(?:login|accounts|challenge|checkpoint)(?:/|$)", urlsplit(self.page.url).path):
            raise CapabilityError("The browser needs direct sign-in or access recovery.", "browser_auth_required")
        navigation_url(self.page.url)
        surface = self.page.evaluate(READ_SURFACE)
        if surface.get("authenticated") and surface.get("unavailable"):
            raise CapabilityError("Threads explicitly reports this source is unavailable.", "source_unavailable")
        if surface.get("blocked") or not surface.get("authenticated"):
            raise CapabilityError(
                "Sign in directly in the dedicated Threads profile; collection is paused.", "browser_auth_required"
            )
        return surface

    def observe(self, flower_only=False):
        surface = self.read()
        profile = surface.get("profile")
        business = profile and re.search(
            r"\b(?:florist|tiem hoa|shop hoa|flower.*(?:shop|studio)|nhan.*(?:order|dat hoa))\b",
            fold(profile.get("text", "")),
        )
        posts = [] if profile and not business else normalize_surface(surface, flower_only or bool(profile))
        self.version, self.signature = str(uuid4()), digest(surface)
        self.targets = {}

        def target(kind, **data):
            key = digest({"kind": kind, **data})[:24]
            self.targets[key] = {"kind": kind, **data}

        for post in posts[:20]:
            target("open_post", url=post.url)
            target("visit_profile", url=f"https://www.threads.com/@{post.username}")
        for control in surface.get("controls", []):
            label = control["label"]
            card_match = POST.fullmatch(urlsplit(urljoin(surface["url"], control.get("card") or "")).path)
            card = f"/@{card_match[1]}/post/{card_match[2]}" if card_match else None
            if re.match(r"^(?:view|show|load|see|xem|hiển thị|tải)", label, re.I):
                target("expand_replies", label=label, card=card)
            elif control["role"] == "menuitem":
                target("set_sort", label=label, card=None)
            else:
                target("open_sort", label=label, card=None)
        target("scroll")
        if self.history:
            target("back")
        return {
            "observation_version": self.version,
            "signature": self.signature,
            "url": surface["url"],
            "posts": [p.model_dump(mode="json") for p in posts],
            "targets": self.targets,
            "sorting": surface.get("sorting", "unknown"),
            "profile": profile if business else None,
            "partial": True,
            "remaining_expansions": sum(t["kind"] == "expand_replies" for t in self.targets.values()),
        }

    def navigate(self, url):
        self.page.goto(navigation_url(url), wait_until="domcontentloaded", timeout=20000)
        self.page.locator("body").wait_for(timeout=10000)
        try:
            self.page.locator(
                '[data-pressable-container] time,input[type="search"],input[type="password"],h1,[role="heading"],iframe[src*="captcha"]'
            ).first.wait_for(state="attached", timeout=10000)
        except Exception:
            raise CapabilityError(
                "The Threads page did not expose a supported readable layout.", "browser_layout_unavailable"
            ) from None
        self.navigated = True

    def execute(self, action: BrowserAction):
        if action.observation_version != self.version or digest(self.read()) != self.signature:
            raise CapabilityError("The page changed; observe again before acting.", "stale_observation")
        if action.action == "finish":
            return
        if action.action == "search":
            self.history.append(self.page.url)
            self.navigate(search_url(action.query or ""))
            return
        target = self.targets.get(action.target)
        if not target or target["kind"] != action.action:
            raise CapabilityError("Action target was not issued for this observation.", "invalid_action_target")
        if action.action in {"open_post", "visit_profile"}:
            self.history.append(self.page.url)
            self.navigate(target["url"])
        elif action.action == "scroll":
            self.page.mouse.wheel(0, 700)
        elif action.action == "back":
            self.navigate(self.history.pop())
        elif action.action in {"expand_replies", "open_sort", "set_sort"}:
            role = "menuitem" if action.action == "set_sort" else "button"
            locator = self.page.get_by_role(role, name=target["label"], exact=True)
            if action.action == "open_sort":
                locator = self.page.locator('button,[role="button"]').filter(
                    has=self.page.locator('[aria-label="Sort"]')
                )
            if target.get("card"):
                card = self.page.locator("[data-pressable-container]").filter(
                    has=self.page.locator(f'a[href="{target["card"]}"]')
                )
                locator = card.get_by_role(role, name=target["label"], exact=True)
            if locator.count() != 1:
                raise CapabilityError("Control is ambiguous; observe again.", "stale_observation")
            locator.click(timeout=10000)
        else:
            raise CapabilityError("This action is not supported.", "unsupported_browser_action")

    def evidence_capture(self, view, stop_reason="partial"):
        return CaptureEnvelope(
            source_url=view["url"],
            messages=view["posts"],
            sorting=view["sorting"],
            stop_reason=stop_reason,
            remaining_expansions=view["remaining_expansions"],
            observed_branches=[p["platform_id"] for p in view["posts"]],
        )

    def visual_context(self):
        # A bounded screenshot helps interpretation only; every action still needs
        # a validated semantic handle. No screenshots enter checkpoints or logs.
        surface = self.read()
        for post in normalize_surface(surface, flower_only=True):
            path = urlsplit(post.url).path
            card = self.page.locator("[data-pressable-container]").filter(has=self.page.locator(f'a[href="{path}"]'))
            if card.count() == 1:
                box = card.bounding_box()
                viewport = self.page.viewport_size or {"width": 1280, "height": 900}
                if box:
                    x, y = max(0, box["x"]), max(0, box["y"])
                    width = min(box["x"] + box["width"], viewport["width"]) - x
                    height = min(box["y"] + box["height"], viewport["height"]) - y
                    if width > 0 and height > 0:
                        return self.page.screenshot(
                            type="jpeg",
                            quality=45,
                            clip={"x": x, "y": y, "width": width, "height": height},
                            timeout=10000,
                        )
        return None


@contextmanager
def open_browser(directory, headless=True):
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise CapabilityError("Install the browser extra and Chromium first.", "browser_not_installed") from None
    with profile_lock(directory) as profile, sync_playwright() as driver:
        context = driver.chromium.launch_persistent_context(
            str(profile),
            headless=headless,
            accept_downloads=False,
            ignore_https_errors=False,
            permissions=[],
            service_workers="block",
            viewport={"width": 1280, "height": 900},
        )

        def restrict(route):
            parsed = urlsplit(route.request.url)
            host = parsed.hostname or ""
            vendors = (
                "threads.com",
                "threads.net",
                "instagram.com",
                "facebook.com",
                "facebook.net",
                "fbcdn.net",
                "cdninstagram.com",
                "fbsbx.com",
            )
            if parsed.scheme == "https" and any(host == v or host.endswith("." + v) for v in vendors):
                route.continue_()
            else:
                route.abort()

        context.route("**/*", restrict)
        page = context.pages[0] if context.pages else context.new_page()
        try:
            yield BrowserController(page)
        finally:
            context.close()
