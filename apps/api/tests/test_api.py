from test_pipeline import imported

from bouquetbrowse.models import Listing
from bouquetbrowse.seed import stable
from bouquetbrowse.worker import run_once


def test_private_api_and_health(client, tester_headers):
    assert client.get("/health/live").status_code == 200
    assert client.get("/v1/catalog").status_code == 401
    response = client.get("/v1/catalog", headers=tester_headers)
    assert response.status_code == 200
    assert response.json()["total"] == 30
    assert response.headers["x-request-id"]
    assert response.headers["cache-control"] == "private, no-store"


def test_role_checks(client, tester_headers):
    for path in ["/v1/admin/jobs", "/v1/admin/sources", "/v1/admin/reviews", "/v1/admin/overview"]:
        assert client.get(path, headers=tester_headers).status_code == 403


def test_disabled_adapter_is_explicit(client, admin_headers):
    response = client.post(
        "/v1/admin/sources/threads/sync",
        headers={**admin_headers, "Idempotency-Key": "sync-test"},
        json={"query": "hoa Hà Nội"},
    )
    assert response.status_code == 409
    assert "token" in response.json()["error"]["message"].lower()


def test_import_worker_review_roundtrip(client, db, admin_headers):
    headers = {**admin_headers, "Idempotency-Key": "import-1"}
    body = {"posts": [imported().model_dump(mode="json")]}
    response = client.post("/v1/admin/imports", headers=headers, json=body)
    assert response.status_code == 200, response.text
    assert client.post("/v1/admin/imports", headers=headers, json=body).json() == response.json()
    assert run_once()
    reviews = client.get("/v1/admin/reviews", headers=admin_headers).json()["items"]
    assert len(reviews) == 1
    listing_id = reviews[0]["id"]
    assert client.get(f"/v1/listings/{listing_id}", headers=admin_headers).status_code == 404
    response = client.post(
        f"/v1/admin/reviews/{listing_id}/decision",
        headers=admin_headers,
        json={"decision": "accept", "reason": "Source price and configuration checked."},
    )
    assert response.status_code == 200, response.text
    assert client.get(f"/v1/listings/{listing_id}", headers=admin_headers).status_code == 200


def test_takedown_hides_immediately_and_purges(client, db, admin_headers):
    target = stable("listing-0-0")
    response = client.post(
        "/v1/admin/takedowns",
        headers={**admin_headers, "Idempotency-Key": "remove-1"},
        json={"listing_id": target, "reason": "Test removal request."},
    )
    assert response.status_code == 200
    assert client.get(f"/v1/listings/{target}", headers=admin_headers).status_code == 404
    assert run_once()
    db.expire_all()
    listing = db.get(Listing, target)
    assert listing.state == "withdrawn"
    assert listing.title == "Removed listing"
    assert listing.image_path is None


def test_validation_does_not_echo_secrets(client, admin_headers):
    secret = "private-do-not-echo"
    response = client.post(
        "/auth/login", headers=admin_headers, json={"email": "a", "password": secret, "extra": secret}
    )
    assert response.status_code == 422
    assert secret not in response.text


def test_invalid_cursor_is_recoverable(client, tester_headers):
    response = client.get("/v1/catalog?cursor=invalid", headers=tester_headers)
    assert response.status_code == 422


def test_login_and_session(client):
    headers = {"X-Bouquet-Proxy": "localhost-proxy-demo-token"}
    response = client.post(
        "/auth/login", headers=headers, json={"email": "tester@bouquetbrowse.local", "password": "demo-tester"}
    )
    assert response.status_code == 200
    session = client.get(
        "/v1/session", headers={**headers, "Authorization": "Bearer " + response.json()["access_token"]}
    )
    assert session.json()["role"] == "tester"
