from datetime import timedelta

import pytest
from sqlalchemy import select

from bouquetbrowse.catalog import catalog, commercial_issues, comparison, eligibility
from bouquetbrowse.db import utcnow
from bouquetbrowse.models import Listing, PriceObservation
from bouquetbrowse.seed import stable


def test_seller_balanced_and_target_excluded(seeded):
    target = seeded.get(Listing, stable("listing-0-0"))
    result = comparison(seeded, target)
    assert result["summary"]["seller_count"] == 7
    assert result["summary"]["status"] == "limited"
    assert result["summary"]["median"] is not None
    assert result["summary"]["percentile"] is None
    assert len({item["seller"]["id"] for item in result["items"]}) == 7
    assert all(item["seller"]["id"] != target.seller_id for item in result["items"])


def test_small_cohorts_suppress_aggregates(seeded):
    target = seeded.get(Listing, stable("listing-0-0"))
    for i in range(4, 8):
        seeded.get(Listing, stable(f"listing-{i}-0")).state = "withdrawn"
    seeded.commit()
    summary = comparison(seeded, target)["summary"]
    assert summary["seller_count"] == 3
    assert summary["median"] is None
    assert summary["min"] is None
    assert summary["relative_difference"] is None


def test_unknown_size_and_stale_prices_do_not_qualify(seeded):
    assert any("size" in reason for reason in commercial_issues(seeded, seeded.get(Listing, stable("listing-3-3"))))
    assert any("older" in reason for reason in commercial_issues(seeded, seeded.get(Listing, stable("listing-2-3"))))
    assert any("range" in reason for reason in commercial_issues(seeded, seeded.get(Listing, stable("listing-1-3"))))


def test_price_filters_do_not_change_benchmark(seeded):
    target = seeded.get(Listing, stable("listing-0-0"))
    before = comparison(seeded, target, persist=False)["summary"]
    catalog(seeded, max_price=400000)
    after = comparison(seeded, target, persist=False)["summary"]
    assert before == after


def test_missing_fields_are_not_matches(seeded):
    target = seeded.get(Listing, stable("listing-0-0"))
    other = seeded.get(Listing, stable("listing-1-0"))
    other.color = None
    qualified, reasons = eligibility(seeded, target, other)
    assert not qualified
    assert "Different primary color" in reasons


def test_demo_and_live_are_never_mixed(seeded):
    target = seeded.get(Listing, stable("listing-0-0"))
    other = seeded.get(Listing, stable("listing-1-0"))
    other.is_demo = False
    assert not eligibility(seeded, target, other)[0]


def test_expired_offer_is_ineligible(seeded):
    target = seeded.get(Listing, stable("listing-0-0"))
    price = seeded.scalar(
        select(PriceObservation).where(PriceObservation.listing_id == target.id, PriceObservation.superseded.is_(False))
    )
    price.valid_until = utcnow() - timedelta(days=1)
    assert "Offer expired" in commercial_issues(seeded, target)


def test_cursor_and_filters(seeded):
    first = catalog(seeded, flower="rose", limit=5)
    second = catalog(seeded, flower="rose", cursor=first["next_cursor"], limit=5)
    assert len(first["items"]) == 5
    assert not {item["id"] for item in first["items"]} & {item["id"] for item in second["items"]}
    with pytest.raises(ValueError):
        catalog(seeded, color="pink", cursor=first["next_cursor"])


def test_bilingual_search(seeded):
    vi = catalog(seeded, q="hoa hồng")
    en = catalog(seeded, q="roses")
    assert vi["total"] > 0 and en["total"] > 0
    assert all(item["primary_flower"] == "rose" for item in vi["items"])
