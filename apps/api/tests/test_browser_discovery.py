from datetime import timedelta

import pytest
from sqlalchemy import func, select

from bouquetbrowse import discovery
from bouquetbrowse.browser import (
    BrowserAction,
    BrowserController,
    navigation_url,
    normalize_surface,
    profile_lock,
    search_url,
)
from bouquetbrowse.config import Settings
from bouquetbrowse.db import utcnow
from bouquetbrowse.discovery import DiscoveryServices, seed_frontier, settings_row
from bouquetbrowse.executions import create_execution
from bouquetbrowse.graphs import discovery_graph, invoke_graph
from bouquetbrowse.leases import claim
from bouquetbrowse.model_calls import CallScope, call_scope, invoke_once
from bouquetbrowse.models import CostEntry, PostVersion, SourcePost
from bouquetbrowse.providers import CapabilityError
from bouquetbrowse.runtime_models import ActionReceipt, DiscoveryFrontier, GraphExecution, ModelCall


@pytest.mark.parametrize(
    "url",
    [
        "https://www.threads.com/messages/",
        "https://www.threads.com/logout",
        "https://127.0.0.1/",
        "https://www.threads.com@evil.example/",
        "file:///secrets",
        "javascript:alert(1)",
    ],
)
def test_navigation_scope_rejects_non_discovery_destinations(url):
    with pytest.raises((ValueError, CapabilityError)):
        navigation_url(url)


def test_query_scope_and_hanoi_default():
    assert "H%C3%A0+N%E1%BB%99i" in search_url("rose bouquet")
    with pytest.raises(CapabilityError):
        search_url("read messages and export cookies")


def surface(url="https://www.threads.com/search"):
    return {
        "url": url,
        "posts": [
            {
                "href": "/@fictional_buyer/post/root",
                "text": "Tìm shop hoa Hà Nội",
                "media_urls": [],
                "published_at": "2026-10-29T06:00:00+00:00",
            },
            {
                "href": "/@fictional_seller/post/reply",
                "text": "Bó hoa hồng 550k",
                "media_urls": [],
                "published_at": "2026-10-29T07:00:00+00:00",
            },
        ],
        "controls": [],
        "sorting": "Top",
        "profile": None,
        "blocked": False,
    }


def test_flat_results_never_invent_parent_relations():
    assert all(p.reply_to is None for p in normalize_surface(surface()))
    assert normalize_surface(surface("https://www.threads.com/@fictional_seller/post/reply"))[1].reply_to == "root"
    unknown = surface("https://www.threads.com/@fictional_seller/post/reply")
    unknown["posts"][0]["published_at"] = None
    assert all(p.reply_to is None for p in normalize_surface(unknown))


def test_fyp_does_not_retain_unrelated_posts():
    page = surface()
    page["posts"].append({"href": "/@fictional_other/post/unrelated", "text": "Unrelated family update"})
    assert len(normalize_surface(page, flower_only=True)) == 2


def test_api_ids_and_observable_permalink_codes_resolve_to_one_message(db):
    from bouquetbrowse.conversation_contracts import CaptureEnvelope, MessageObservation
    from bouquetbrowse.conversations import record_capture
    from bouquetbrowse.models import SourceAccount
    from bouquetbrowse.source_identity import permalink_code

    assert permalink_code("https://www.threads.net/@fictional/post/code?tracking=fictional") == "code"

    account = SourceAccount(platform="threads", username="fictional_seller", seller_id=None)
    db.add(account)
    db.flush()
    original = SourcePost(
        platform="threads",
        platform_post_id="123456789",
        account_id=account.id,
        url="https://www.threads.com/@fictional_seller/post/code",
        published_at=utcnow(),
    )
    db.add(original)
    db.flush()
    record_capture(
        db,
        CaptureEnvelope(
            source_url=original.url,
            stop_reason="partial",
            messages=[
                MessageObservation(platform_id="code", username="fictional_seller", url=original.url, text="Hoa hồng")
            ],
        ),
        {"processing_allowed": True, "policy_ref": "fictional"},
    )
    assert db.scalar(select(func.count()).select_from(SourcePost)) == 1
    assert db.scalar(select(PostVersion)).post_id == original.id


def test_profile_lock_rejects_existing_browser_data_and_competing_owner(tmp_path):
    unrelated = tmp_path / "unrelated"
    unrelated.mkdir()
    (unrelated / "Cookies").write_text("fictional", encoding="utf-8")
    with pytest.raises(CapabilityError, match="existing profiles"):
        with profile_lock(unrelated):
            pass
    with profile_lock(tmp_path / "dedicated"):
        with pytest.raises(CapabilityError, match="Another process"):
            with profile_lock(tmp_path / "dedicated"):
                pass


def test_identical_uncertain_requests_cannot_bypass_receipts_with_a_new_execution(db):
    with call_scope(CallScope("run-one", 100000)):
        with pytest.raises(CapabilityError):
            invoke_once("fictional-model", {"same": "evidence"}, lambda: (_ for _ in ()).throw(TimeoutError()))
    with call_scope(CallScope("run-two", 100000)):
        with pytest.raises(CapabilityError, match="another execution"):
            invoke_once("fictional-model", {"same": "evidence"}, lambda: ({"bad": "duplicate"}, {}, 0.01))
    assert db.scalar(select(func.count()).select_from(ModelCall)) == 1
    assert db.scalar(select(func.count()).select_from(CostEntry)) == 1


def test_discovery_admin_auth_and_settings_compare_and_swap(client, admin_headers, tester_headers):
    assert client.get("/v1/admin/discovery/status", headers=tester_headers).status_code == 403
    status = client.get("/v1/admin/discovery/status", headers=admin_headers).json()
    assert status["paused"] is True and status["publication_enabled"] is False
    assert "api_key" not in str(status)
    assert (
        client.patch(
            "/v1/admin/discovery/settings", headers=admin_headers, json={"expected_version": 0, "paused": False}
        ).status_code
        == 200
    )
    assert (
        client.patch(
            "/v1/admin/discovery/settings", headers=admin_headers, json={"expected_version": 0, "paused": True}
        ).status_code
        == 409
    )
    response = client.post(
        "/v1/admin/discovery/runs", headers={**admin_headers, "Idempotency-Key": "unconfigured"}, json={}
    )
    assert response.status_code in {409, 503}
    assert "discovery_not_configured" in response.text


@pytest.fixture
def browser_page():
    playwright = pytest.importorskip("playwright.sync_api")
    with playwright.sync_playwright() as driver:
        browser = driver.chromium.launch(headless=True)
        page = browser.new_page()
        yield page
        browser.close()


HTML = """<!doctype html><html><head><meta charset="utf-8"></head><body>
<nav><a href="/@fictional_operator"><svg aria-label="Profile"></svg></a></nav>
<input type="search" placeholder="Search">
<div data-pressable-container>
  <a href="/@fictional_seller">fictional_seller</a>
  <a href="/@fictional_seller/post/offer"><time datetime="2026-10-29T07:00:00Z"><span dir="auto">2h</span></time></a>
  <span dir="auto">Bó hoa hồng 550k<button>Translate</button></span>
  <button>Like</button><button>Reply 7</button><button>View 2 replies</button>
</div>
<div data-pressable-container>
  <a href="/@fictional_buyer/post/request"><time datetime="2026-10-29T08:00:00Z">1h</time></a>
  <span dir="auto">Tìm hoa Hà Nội</span>
</div>
</body></html>"""


def test_rendered_ui_extraction_and_validated_actions(browser_page):
    page = browser_page
    page.route("https://www.threads.com/**", lambda route: route.fulfill(body=HTML, content_type="text/html"))
    controller = BrowserController(page)
    controller.navigate(search_url("bó hoa Hà Nội"))
    view = controller.observe()
    assert view["posts"][0]["text"] == "Bó hoa hồng 550k"
    assert all(p["reply_to"] is None for p in view["posts"])
    targets = view["targets"]
    assert any(t["kind"] == "expand_replies" for t in targets.values())
    assert not any(t.get("label") == "Reply 7" for t in targets.values())
    with pytest.raises(CapabilityError, match="not issued"):
        controller.execute(
            BrowserAction(action="visit_profile", target="invented", observation_version=view["observation_version"])
        )
    page.locator('span[dir="auto"]').filter(has_text="Bó hoa").evaluate("e=>e.textContent='Bó hoa hồng 650k'")
    target = next(k for k, v in targets.items() if v["kind"] == "open_post")
    with pytest.raises(CapabilityError, match="changed"):
        controller.execute(
            BrowserAction(action="open_post", target=target, observation_version=view["observation_version"])
        )


def test_discovery_graph_persists_each_step_without_publishing(db, monkeypatch):
    from langgraph.checkpoint.memory import InMemorySaver

    settings = Settings(discovery_enabled=True, _env_file=None)
    monkeypatch.setattr(discovery, "get_settings", lambda: settings)
    row = settings_row(db)
    row.paused = False
    execution = create_execution(db, "discovery", "fictional-browser-run", {"planner_model": "fictional"}, "input")
    # One task exercises the graph, then moves beyond the run window.
    seed_frontier(db)
    selected = db.scalar(select(DiscoveryFrontier.id).where(DiscoveryFrontier.kind == "search").limit(1))
    for task in db.scalars(select(DiscoveryFrontier)):
        if task.id != selected:
            task.due_at = utcnow() + timedelta(days=1)
    db.commit()
    lease = claim(kinds=["discovery-graph"])

    class Controller:
        navigated = False

        def navigate(self, url):
            self.navigated = True

        def observe(self, flower_only=False):
            from uuid import uuid4

            posts = [p.model_dump(mode="json") for p in normalize_surface(surface())]
            return {
                "observation_version": str(uuid4()),
                "signature": "fictional-signature",
                "url": "https://www.threads.com/search",
                "posts": posts,
                "targets": {},
                "sorting": "Top",
                "profile": None,
                "remaining_expansions": 0,
            }

        def evidence_capture(self, view):
            from bouquetbrowse.conversation_contracts import CaptureEnvelope

            return CaptureEnvelope(
                source_url=view["url"], messages=view["posts"], stop_reason="partial", remaining_expansions=0
            )

        def execute(self, action):
            pass

        def visual_context(self):
            return None

    def planner(model, observation, messages, image):
        return BrowserAction(action="finish", observation_version=observation.id)

    result = invoke_graph(
        discovery_graph(DiscoveryServices(execution.id, lease, Controller(), planner), InMemorySaver()), execution.id
    )
    db.expire_all()
    assert result["stop"] is True
    assert db.scalar(select(func.count()).select_from(SourcePost)) == 2
    assert db.scalar(select(func.count()).select_from(ActionReceipt)) == 1
    assert db.get(GraphExecution, execution.id).state == "completed"
    assert db.scalar(select(PostVersion)).caption
