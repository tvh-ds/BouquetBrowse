import re

from sqlalchemy import select
from test_conversation_offers import capture, interpretation, message, offer_for, reference

from bouquetbrowse.conversation_models import CanonicalLink, TaxonomyTerm
from bouquetbrowse.curation_api import fingerprint, links_hash
from bouquetbrowse.discovery import settings_row
from bouquetbrowse.models import Seller
from bouquetbrowse.offer_contracts import OfferField
from bouquetbrowse.offers import validate_interpretation
from bouquetbrowse.runtime_models import GraphExecution
from bouquetbrowse.taxonomy import flower_patterns, normalize, promote, vocabulary


def test_taxonomy_promotes_literal_aliases_into_immutable_version(client, db, admin_headers, tester_headers):
    row = TaxonomyTerm(key="garden rose", taxonomy_version="flowers-v2", aliases=[], evaluation={})
    db.add(row)
    db.commit()
    body = {
        "expected_fingerprint": fingerprint(row),
        "decision": "promote",
        "canonical_key": "rose",
        "new_version": "flowers-v3",
        "aliases": ["hồng vườn", "rose (garden)"],
        "reason": "Reviewed florist synonym mapping",
    }
    path = f"/v1/admin/curation/taxonomy/{row.id}/decision"
    assert client.post(path, json=body, headers={**tester_headers, "Idempotency-Key": "taxonomy"}).status_code == 403
    response = client.post(path, json=body, headers={**admin_headers, "Idempotency-Key": "taxonomy"})
    assert response.status_code == 200, response.text
    assert (
        client.post(path, json=body, headers={**admin_headers, "Idempotency-Key": "taxonomy"}).json() == response.json()
    )
    db.expire_all()
    assert normalize(db, "garden rose", "flowers-v3") == "rose"
    assert normalize(db, "garden rose", "flowers-v2") is None
    assert settings_row(db).configuration["taxonomy_version"] == "flowers-v3"
    pattern = flower_patterns(db, "flowers-v3")["rose"]
    assert re.search(pattern, "rose (garden)", re.I)
    assert not re.fullmatch(pattern, "rose garden", re.I)
    assert vocabulary(db, "flowers-v3")["rose"]
    assert client.post(path, json=body, headers={**admin_headers, "Idempotency-Key": "different"}).status_code == 409


def test_taxonomy_collision_is_rejected(client, db, admin_headers):
    row = TaxonomyTerm(key="new-flower", taxonomy_version="flowers-v2", aliases=[], evaluation={})
    db.add(row)
    db.commit()
    body = {
        "expected_fingerprint": fingerprint(row),
        "decision": "promote",
        "new_version": "flowers-v3",
        "aliases": ["rose"],
        "reason": "Must not steal another category name",
    }
    response = client.post(
        f"/v1/admin/curation/taxonomy/{row.id}/decision",
        json=body,
        headers={**admin_headers, "Idempotency-Key": "collision"},
    )
    assert response.status_code == 409
    assert "two flower types" in response.text


def test_canonical_links_are_audited_reversible_and_seller_bounded(client, db, admin_headers):
    capture(
        db,
        [
            message("canonical-a", "fictional_a", "Bên em nhận đặt bó hoa giao Hà Nội", image=True),
            message("canonical-b", "fictional_b", "Bên em nhận đặt bó hoa giao Hà Nội", image=True),
        ],
    )
    a, b = offer_for(db, "canonical-a"), offer_for(db, "canonical-b")
    for index, offer in enumerate([a, b]):
        seller = Seller(name=f"Fictional {index}", slug=f"canonical-{index}", city="Hanoi", district="Unknown")
        db.add(seller)
        db.flush()
        offer.seller_id = seller.id
    db.commit()
    body = {
        "offer_id": a.id,
        "expected_fingerprint": a.input_fingerprint,
        "expected_links_hash": links_hash(db, a.id),
        "reason": "Operator reviewed the same configuration",
    }
    result = client.post(
        "/v1/admin/curation/canonical/link", json=body, headers={**admin_headers, "Idempotency-Key": "canonical"}
    )
    assert result.status_code == 200, result.text
    assert (
        client.post(
            "/v1/admin/curation/canonical/link", json=body, headers={**admin_headers, "Idempotency-Key": "canonical"}
        ).json()
        == result.json()
    )
    assert (
        client.post(
            "/v1/admin/curation/canonical/link", json=body, headers={**admin_headers, "Idempotency-Key": "stale-link"}
        ).status_code
        == 409
    )
    foreign = {
        **body,
        "offer_id": b.id,
        "expected_fingerprint": b.input_fingerprint,
        "configuration_id": result.json()["configuration_id"],
    }
    assert (
        client.post(
            "/v1/admin/curation/canonical/link", json=foreign, headers={**admin_headers, "Idempotency-Key": "foreign"}
        ).status_code
        == 409
    )
    db.expire_all()
    link = db.get(CanonicalLink, result.json()["link_id"])
    assert link.state == "accepted"
    response = client.post(
        f"/v1/admin/curation/canonical/{link.id}/unlink",
        json={"expected_fingerprint": fingerprint(link), "reason": "Reviewed association was incorrect"},
        headers={**admin_headers, "Idempotency-Key": "unlink"},
    )
    assert response.status_code == 200
    db.expire_all()
    assert db.get(CanonicalLink, link.id).state == "revoked"
    assert len(list(db.scalars(select(CanonicalLink)))) == 1
    assert a.id == offer_for(db, "canonical-a").id


def test_conversation_explorer_reports_edges_and_partial_coverage(client, db, admin_headers):
    record = capture(
        db,
        [
            message("explorer-root", "fictional_seller", "Bên em nhận đặt bó hoa giao Hà Nội", image=True),
            message("explorer-reply", "fictional_buyer", "Giá bao nhiêu?", "explorer-root"),
        ],
    )
    db.commit()
    response = client.get(f"/v1/admin/conversations/{record.id}", headers=admin_headers)
    assert response.status_code == 200, response.text
    data = response.json()
    assert len(data["messages"]) == 2
    assert data["edges"][0]["kind"] == "reply_to"
    assert "remaining_expansions" in data


def test_alias_change_reprocesses_only_affected_offers_and_pins_validation(db):
    capture(
        db,
        [
            message("alias-a", "fictional_alias_a", "Bên em nhận đặt bó hoa, giao Hà Nội. rosita", image=True),
            message("alias-b", "fictional_alias_b", "Bên em nhận đặt bó hoa, giao Hà Nội. hoa ly", image=True),
        ],
    )
    a, b = offer_for(db, "alias-a"), offer_for(db, "alias-b")
    row = TaxonomyTerm(key="rosita", taxonomy_version="flowers-v2", aliases=[], evaluation={})
    db.add(row)
    db.flush()
    promote(db, row, "flowers-v3", [], "fictional-admin", "Reviewed florist alias", "rose")
    db.flush()
    assert row.evaluation["affected_offers"] == [a.id]
    assert len(list(db.scalars(select(GraphExecution).where(GraphExecution.offer_id == b.id)))) == 1
    result = interpretation(db, "alias-a")
    result.fields = [OfferField(field="flower", value="rose", evidence=[reference(db, "alias-a", "rosita")])]
    assert (
        validate_interpretation(db, a, result, {"taxonomy_version": "flowers-v3"})["composition"][0]["flower"] == "rose"
    )
    import pytest

    with pytest.raises(ValueError, match="unsupported"):
        validate_interpretation(db, a, result, {"taxonomy_version": "flowers-v2"})


def test_profile_takedown_replays_without_reviving_business_facts(db, monkeypatch):
    from datetime import timedelta

    from bouquetbrowse.browser_models import ProfileSnapshot
    from bouquetbrowse.catalog_event_models import SellerFact
    from bouquetbrowse.db import utcnow
    from bouquetbrowse.models import SourceAccount
    from bouquetbrowse.recovery import replay_deletions
    from bouquetbrowse.seller_profiles import project_profile_snapshot

    monkeypatch.setattr("bouquetbrowse.seller_profiles.publication_ready", lambda *args: True)
    account = SourceAccount(platform="threads", username="fictional_removed_profile")
    db.add(account)
    db.flush()
    profile = ProfileSnapshot(
        account_id=account.id,
        content_hash="fictional-profile",
        source_url="https://www.threads.com/@fictional_removed_profile",
        text="Tiệm hoa Hà Nội",
        policy={"display_allowed": True},
        retention_until=utcnow() + timedelta(days=1),
    )
    db.add(profile)
    db.flush()
    assert project_profile_snapshot(db, profile.id, {})
    db.flush()
    assert list(db.scalars(select(SellerFact)))
    replay_deletions(db, [{"subject_kind": "profile", "subject_id": account.id, "reason": "takedown"}])
    db.flush()
    assert not list(db.scalars(select(SellerFact)))
    assert profile.text == ""
    assert account.capabilities["profile_suppressed"]
    assert project_profile_snapshot(db, profile.id, {}) == 0
