from html import escape

import pytest
from sqlalchemy import func, select

from bouquetbrowse.browser import BrowserAction, BrowserController, search_url
from bouquetbrowse.config import Settings
from bouquetbrowse.discovery import add_frontier, select_frontier
from bouquetbrowse.executions import create_execution
from bouquetbrowse.planner import action_menu
from bouquetbrowse.providers import CapabilityError
from bouquetbrowse.runtime_models import DiscoveryFrontier


def test_recent_mode_cannot_silently_resume_as_full(db, monkeypatch):
    from bouquetbrowse import discovery
    from bouquetbrowse.discovery import DiscoveryServices, seed_frontier, settings_row
    from bouquetbrowse.leases import claim

    recent = Settings(discovery_enabled=True, discovery_mode="recent_search", _env_file=None)
    monkeypatch.setattr(discovery, "get_settings", lambda: recent)
    seed_frontier(db)
    assert all(row.kind == "search" for row in db.scalars(select(DiscoveryFrontier)))
    settings_row(db).paused = False
    execution = create_execution(db, "discovery", "recent-pinned", {"discovery_mode": "recent_search"}, "fictional")
    db.commit()
    lease = claim(kinds=["discovery-graph"])
    service = DiscoveryServices(execution.id, lease, None)
    assert service.checked(db)[1] is False
    monkeypatch.setattr(discovery, "get_settings", lambda: Settings(discovery_enabled=True, _env_file=None))
    with pytest.raises(CapabilityError) as error:
        service.checked(db)
    assert error.value.code == "discovery_mode_changed"


def test_recent_frontier_does_not_visit_old_profiles_fyp_or_refresh(db):
    search = add_frontier(db, "search", "bó hoa Hà Nội")
    for kind, target, queue in [
        ("fyp", "https://www.threads.com/", "fyp"),
        ("profile", "https://www.threads.com/@fictional", "discovery"),
        ("post", "https://www.threads.com/@fictional/post/offer", "refresh"),
    ]:
        add_frontier(db, kind, target, queue)
    execution = create_execution(db, "discovery", "recent-only", {"discovery_mode": "recent_search"}, "fictional")
    assert select_frontier(db, execution).id == search.id
    assert db.scalar(select(func.count()).select_from(DiscoveryFrontier)) == 4
    assert execution.configuration["discovery_mode"] == "recent_search"


def test_recent_mode_config_menu_and_navigation_scope():
    with pytest.raises(ValueError):
        Settings(discovery_mode="unrestricted", _env_file=None)
    controller = BrowserController(None, mode="recent_search")
    for url in [
        "https://www.threads.com/",
        "https://www.threads.com/@fictional",
        "https://www.threads.com/search?q=hoa&filter=recent",
        "https://www.threads.com/search?q=hoa+Hanoi&filter=top",
        "https://www.threads.com/search?q=hoa+Hanoi&filter=recent&serp_type=profiles",
    ]:
        with pytest.raises(CapabilityError):
            controller.check_scope(url)
    controller.check_scope(search_url("hoa Hà Nội"))
    controller.check_scope("https://www.threads.com/@fictional/post/offer")
    snapshot = {
        "url": search_url("hoa Hà Nội"),
        "targets": {
            "profile": {"kind": "visit_profile"},
            "sort": {"kind": "set_sort"},
            "post": {"kind": "open_post", "url": "https://www.threads.com/@fictional/post/offer"},
        },
        "planning_context": {"discovery_mode": "recent_search"},
    }
    assert {a["action"] for a in action_menu(snapshot, []).values()} == {"open_post", "finish"}


@pytest.fixture
def page():
    playwright = pytest.importorskip("playwright.sync_api")
    with playwright.sync_playwright() as driver:
        browser = driver.chromium.launch(headless=True)
        yield browser.new_page()
        browser.close()


def search_html(tab):
    return f"""<nav><a href="/@fictional_operator"><svg aria-label="Profile"></svg></a></nav>
    {tab}<input type="search">
    <div data-pressable-container>
      <a href="/@fictional/post/offer"><time datetime="2026-11-02T06:00:00Z">1h</time></a>
      <span dir="auto">Bó hoa hồng Hà Nội</span><button>View 2 replies</button>
    </div>"""


def test_controller_requires_visible_recent_selection_and_removes_profile_targets(page):
    url = search_url("hoa Hà Nội")
    html = search_html(f'<a aria-current="page" href="{escape(url)}">Recent</a>')
    page.route("https://www.threads.com/**", lambda route: route.fulfill(body=html, content_type="text/html"))
    controller = BrowserController(page, mode="recent_search")
    controller.navigate(url)
    view = controller.observe()
    assert view["sorting"] == view["search_sort"] == "recent"
    assert {t["kind"] for t in view["targets"].values()} == {"open_post", "expand_replies", "scroll"}
    with pytest.raises(CapabilityError, match="disabled"):
        controller.execute(
            BrowserAction(action="visit_profile", target="forged", observation_version=view["observation_version"])
        )
    assert page.url == url


@pytest.mark.parametrize(
    "tab",
    [
        '<a aria-current="page" href="/search?q=hoa+Hanoi">Top</a>',
        '<a href="/search?q=hoa+Hanoi&filter=recent">Recent</a>',
        '<a aria-current="page" href="/search?q=other&filter=recent">Recent</a>',
    ],
)
def test_recent_url_alone_is_not_proof_of_selected_sort(page, tab):
    page.route(
        "https://www.threads.com/**", lambda route: route.fulfill(body=search_html(tab), content_type="text/html")
    )
    page.goto(search_url("hoa Hanoi"))
    with pytest.raises(CapabilityError) as error:
        BrowserController(page, mode="recent_search").observe()
    assert error.value.code == "search_sort_unverified"
