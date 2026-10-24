import json
import socket

import httpx
import pytest

from bouquetbrowse import public_pages as pages
from bouquetbrowse.providers import CapabilityError

HTTPX_CLIENT = httpx.Client
URL = "https://www.threads.com/@fixture.florist/post/ABC123"


def document(**changes):
    post = {
        "@type": "SocialMediaPosting",
        "url": URL,
        "articleBody": "Bó hoa hồng, 20 cành. Giá 650k. Phí ship 30k.",
        "datePublished": "2026-10-01T10:00:00+07:00",
        "image": ["https://img.cdninstagram.com/flower.jpg", "https://127.0.0.1/private"],
    }
    post.update(changes)
    return '<script type="application/ld+json">' + json.dumps(post) + "</script>"


def test_source_identity_and_unknowns():
    result = pages.parse_page(document(), URL + "?tracking=removed")
    draft = result["draft"]
    assert draft["caption"].endswith("Phí ship 30k.")
    assert draft["username"] == "fixture.florist"
    assert draft["source_url"] == URL
    assert draft["published_at"] == "2026-10-01T10:00:00+07:00"
    assert draft["media_urls"] == ["https://img.cdninstagram.com/flower.jpg"]
    assert draft["rights_confirmed"] is False
    assert draft["district"] == draft["seller_name"] == ""


@pytest.mark.parametrize(
    "url",
    [
        "http://www.threads.com/@x/post/ABC",
        "https://threads.com.evil.test/@x/post/ABC",
        "https://user:pass@threads.com/@x/post/ABC",
        "https://threads.com:444/@x/post/ABC",
        "https://127.0.0.1/p/ABC/",
        "https://www.instagram.com/accounts/login/",
        "https://threads.com/@fixture.florist",
    ],
)
def test_rejects_unsafe_or_nonpost_urls(url):
    with pytest.raises(CapabilityError):
        pages.post_identity(url)


def test_metadata_fallback_never_invents_date_or_author():
    result = pages.parse_page(
        '<meta property="og:description" content="Hoa hồng &amp; giấy gói. Giá 650k">',
        "https://www.instagram.com/p/ABC/",
    )
    assert result["draft"]["caption"] == "Hoa hồng & giấy gói. Giá 650k"
    assert result["draft"]["published_at"] is None
    assert result["draft"]["username"] == ""
    assert len(result["warnings"]) == 3
    assert pages.parse_page(document(datePublished="2026-10-01"), URL)["draft"]["published_at"] is None


def test_conflicting_identity_and_multipost_metadata_abstain():
    with pytest.raises(CapabilityError, match="different post"):
        pages.parse_page(document(url="https://www.threads.com/@other/post/OTHER"), URL)
    with pytest.raises(CapabilityError, match="Multiple"):
        pages.parse_page(document() + document(), URL)


def test_login_or_empty_html_does_not_become_listing():
    for html in [
        "<title>Log in</title>",
        '<meta property="og:description" content="Instagram">',
        '<script type="application/ld+json">invalid</script>',
    ]:
        with pytest.raises(CapabilityError, match="No usable"):
            pages.parse_page(html, URL)


def network(monkeypatch, handler):
    monkeypatch.setattr(pages, "consume_quota", lambda *args: None)
    monkeypatch.setattr(
        pages.socket,
        "getaddrinfo",
        lambda *args, **kwargs: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("1.1.1.1", 443))],
    )
    monkeypatch.setattr(
        pages.httpx, "Client", lambda **kwargs: HTTPX_CLIENT(transport=httpx.MockTransport(handler), **kwargs)
    )


def test_public_fetch_is_pinned_anonymous_and_bounded(monkeypatch):
    def handler(request):
        assert request.url.host == "1.1.1.1"
        assert request.headers["host"] == "www.threads.com"
        assert "authorization" not in request.headers and "cookie" not in request.headers
        assert request.extensions["sni_hostname"] == "www.threads.com"
        return httpx.Response(200, headers={"content-type": "text/html; charset=utf-8"}, text=document())

    network(monkeypatch, handler)
    assert pages.collect_page(URL)["draft"]["platform_post_id"] == "ABC123"


def test_threads_share_link_resolves_to_same_platform_post(monkeypatch):
    calls = []

    def handler(request):
        calls.append(str(request.url.path))
        if request.url.path.startswith("/share/"):
            return httpx.Response(302, headers={"location": URL + "?tracking=discarded"})
        return httpx.Response(200, headers={"content-type": "text/html"}, text=document())

    network(monkeypatch, handler)
    result = pages.collect_page("https://www.threads.com/share/SYNTHETIC/")
    assert result["draft"]["source_url"] == URL
    assert len(calls) == 2


def test_cookie_received_during_redirect_is_not_forwarded(monkeypatch):
    calls = []

    def handler(request):
        assert "cookie" not in request.headers
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(302, headers={"location": URL, "set-cookie": "session=untrusted; Path=/"})
        return httpx.Response(200, headers={"content-type": "text/html"}, text=document())

    network(monkeypatch, handler)
    pages.collect_page("https://www.threads.com/share/SYNTHETIC/")
    assert len(calls) == 2


@pytest.mark.parametrize("status", [401, 403, 429])
def test_access_restrictions_fail_without_retry(monkeypatch, status):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(status)

    network(monkeypatch, handler)
    with pytest.raises(CapabilityError) as error:
        pages.collect_page(URL)
    assert error.value.code == "page_access_required"
    assert len(calls) == 1


def test_redirect_to_private_or_login_destination_is_not_followed(monkeypatch):
    for location in ["https://127.0.0.1/private", "https://www.instagram.com/accounts/login/"]:
        calls = []

        def handler(request, calls=calls, location=location):
            calls.append(request)
            return httpx.Response(302, headers={"location": location})

        network(monkeypatch, handler)
        with pytest.raises(CapabilityError):
            pages.collect_page(URL)
        assert len(calls) == 1


def test_private_dns_is_rejected_before_network(monkeypatch):
    monkeypatch.setattr(pages.socket, "getaddrinfo", lambda *args, **kwargs: [(2, 1, 6, "", ("127.0.0.1", 443))])
    with pytest.raises(CapabilityError, match="public network"):
        pages.public_destination("www.threads.com")


def test_oversized_pages_and_non_html_fail(monkeypatch):
    for headers, body, code in [
        ({"content-type": "application/json"}, "{}", "page_format_unsupported"),
        ({"content-type": "text/html"}, "x" * (pages.MAX_BYTES + 1), "page_too_large"),
    ]:
        network(
            monkeypatch, lambda request, headers=headers, body=body: httpx.Response(200, headers=headers, text=body)
        )
        with pytest.raises(CapabilityError) as error:
            pages.collect_page(URL)
        assert error.value.code == code


def test_preview_requires_admin_and_can_feed_existing_review_pipeline(
    client, monkeypatch, tester_headers, admin_headers
):
    monkeypatch.setattr(pages, "fetch_html", lambda url: (document(), URL))
    response = client.post("/v1/admin/pages/preview", headers=tester_headers, json={"url": URL})
    assert response.status_code == 403
    response = client.post("/v1/admin/pages/preview", headers=admin_headers, json={"url": URL})
    assert response.status_code == 200
    draft = response.json()["draft"]
    draft.update(
        seller_name="Fixture Florist",
        seller_slug="fixture-florist",
        district="Ba Đình",
        rights_confirmed=True,
        media_urls=[],
    )
    response = client.post(
        "/v1/admin/imports", headers={**admin_headers, "Idempotency-Key": "parsed-page"}, json={"posts": [draft]}
    )
    assert response.status_code == 200
    from bouquetbrowse.worker import run_once

    assert run_once()
    reviews = client.get("/v1/admin/reviews", headers=admin_headers).json()["items"]
    assert len(reviews) == 1
    assert client.get("/v1/listings/" + reviews[0]["id"], headers=admin_headers).status_code == 404


def test_untrusted_metadata_shapes_and_login_identity():
    with pytest.raises(CapabilityError):
        pages.parse_page(document(url=["not a URL"]), URL)
    with pytest.raises(CapabilityError):
        pages.parse_page(
            '<meta property="og:url" content="https://www.instagram.com/accounts/login/"><meta property="og:description" content="Sign in to see more">',
            URL,
        )
    with pytest.raises(CapabilityError):
        pages.parse_page('<script type="application/ld+json">{"@type":42}</script>', URL)


def test_manual_page_collection_cannot_queue_discovery(client, admin_headers):
    response = client.post(
        "/v1/admin/sources/public-pages/sync",
        headers={**admin_headers, "Idempotency-Key": "manual-cannot-sync"},
        json={"query": "hoa"},
    )
    assert response.status_code == 409
    assert "individual public" in response.json()["error"]["message"]
