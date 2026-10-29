from datetime import timedelta
from types import SimpleNamespace

from sqlalchemy import select

from bouquetbrowse.browser_models import ProfileSnapshot
from bouquetbrowse.catalog_event_models import CatalogChange, SellerFact
from bouquetbrowse.db import utcnow
from bouquetbrowse.discovery import add_frontier, select_frontier
from bouquetbrowse.models import Seller, SourceAccount, SourcePost
from bouquetbrowse.pipeline import enqueue
from bouquetbrowse.retention import expire
from bouquetbrowse.runtime_models import GraphExecution
from bouquetbrowse.seller_profiles import profile_summary, project_profile_snapshot


def test_profile_business_evidence_and_expiry(db, monkeypatch):
    monkeypatch.setattr("bouquetbrowse.seller_profiles.publication_ready", lambda *args: True)
    account = SourceAccount(platform="threads", username="fictional_florist", role="unresolved")
    db.add(account)
    db.flush()
    snapshot = ProfileSnapshot(
        account_id=account.id,
        content_hash="fictional",
        source_url="https://www.threads.com/@fictional_florist",
        text="Tiệm hoa Hà Nội\nHotline: 000-fictional\nGiao hoa Hà Nội",
        policy={"display_allowed": True},
        retention_until=utcnow() + timedelta(days=1),
    )
    db.add(snapshot)
    db.flush()
    assert project_profile_snapshot(db, snapshot.id, {}) >= 3
    db.flush()
    facts = list(db.scalars(select(SellerFact)))
    assert account.role == "seller"
    assert any(f.field == "business_contact" for f in facts)
    for fact in facts:
        ref = fact.evidence
        assert snapshot.text[ref["start"] : ref["end"]] == ref["quote"]
    count = len(facts)
    project_profile_snapshot(db, snapshot.id, {})
    db.flush()
    assert len(list(db.scalars(select(SellerFact)))) == count
    snapshot.retention_until = utcnow() - timedelta(seconds=1)
    expire(db)
    db.flush()
    assert not list(db.scalars(select(SellerFact)))
    assert all(e.suppressed for e in db.scalars(select(CatalogChange)))
    assert snapshot.text == ""


def test_buyer_profile_never_becomes_seller(db, monkeypatch):
    monkeypatch.setattr("bouquetbrowse.seller_profiles.publication_ready", lambda *args: True)
    account = SourceAccount(platform="threads", username="fictional_buyer")
    db.add(account)
    db.flush()
    snapshot = ProfileSnapshot(
        account_id=account.id,
        content_hash="buyer",
        source_url="https://www.threads.com/@fictional_buyer",
        text="Tìm shop hoa giao Hà Nội",
        policy={"display_allowed": True},
        retention_until=utcnow() + timedelta(days=1),
    )
    db.add(snapshot)
    db.flush()
    assert project_profile_snapshot(db, snapshot.id, {}) == 0
    assert account.seller_id is None


def test_frontier_balancing_and_independent_seller_priority(db):
    seller = Seller(name="Fictional", slug="fictional", city="Hanoi", district="Unknown")
    db.add(seller)
    db.flush()
    account = SourceAccount(platform="threads", username="covered", seller_id=seller.id)
    db.add(account)
    db.flush()
    db.add(
        SourcePost(
            platform="threads",
            platform_post_id="covered",
            account_id=account.id,
            url="https://www.threads.com/@covered/post/covered",
            last_seen_at=utcnow(),
        )
    )
    first = add_frontier(db, "profile", "https://www.threads.com/@covered")
    second = add_frontier(db, "profile", "https://www.threads.com/@new_seller")
    first.due_at = second.due_at = utcnow() - timedelta(hours=1)
    db.flush()
    assert select_frontier(db, SimpleNamespace(id="execution")).id == second.id
    first.evidence_gaps = ["missing_price"]
    assert select_frontier(db, SimpleNamespace(id="execution")).id == first.id
    # More than 100 old refresh records cannot hide a due FYP/search queue.
    for i in range(101):
        add_frontier(db, "post", f"https://www.threads.com/@covered/post/p{i}", queue="refresh")
    fyp = add_frontier(db, "fyp", "https://www.threads.com/", queue="fyp")
    db.flush()
    job = enqueue(db, "discovery-graph", {}, "fixture-effort")
    db.add(
        GraphExecution(
            job_id=job.id,
            kind="discovery",
            behavior_version="unused",
            configuration={},
            input_fingerprint="unused",
            budget_microusd=0,
            progress={"effort_seconds": {"refresh": 100, "discovery": 100}},
        )
    )
    db.flush()
    assert select_frontier(db, SimpleNamespace(id="execution")).id == fyp.id


def test_summary_omits_tentative_components():
    summary = profile_summary(
        [
            SimpleNamespace(
                attributes={
                    "composition": [
                        {"flower": "rose", "review_state": "accepted"},
                        {"flower": "peony", "review_state": "pending"},
                    ],
                    "style": "round",
                }
            )
        ],
        [],
    )
    assert summary["observed_flower_types"] == ["rose"]
    assert summary["observed_styles"] == ["round"]
