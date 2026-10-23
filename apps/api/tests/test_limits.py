import pytest
from pydantic import ValidationError

from bouquetbrowse import providers
from bouquetbrowse.catalog import comparison
from bouquetbrowse.config import Settings
from bouquetbrowse.models import Listing
from bouquetbrowse.providers import CapabilityError
from bouquetbrowse.seed import stable


def test_cohort_snapshot_reused_until_members_change(seeded):
    target = seeded.get(Listing, stable("listing-0-0"))
    first = comparison(seeded, target)["summary"]["run_id"]
    assert comparison(seeded, target)["summary"]["run_id"] == first
    seeded.get(Listing, stable("listing-1-0")).state = "withdrawn"
    seeded.commit()
    seeded.info.clear()
    assert comparison(seeded, target)["summary"]["run_id"] != first


def test_mixed_composition_not_automatically_equivalent(seeded):
    target = seeded.get(Listing, stable("listing-0-0"))
    target.attributes = {**target.attributes, "flower_composition": ["rose", "lily", "tulip"]}
    seeded.commit()
    assert comparison(seeded, target)["summary"]["seller_count"] == 0


def test_pilot_cannot_use_demo_configuration():
    with pytest.raises(ValidationError):
        Settings(app_mode="pilot", _env_file=None)
    with pytest.raises(ValidationError):
        Settings(monthly_model_budget_usd=0, _env_file=None)


def test_cost_reservations_enforce_monthly_ceiling(db, monkeypatch):
    monkeypatch.setattr(providers, "get_settings", lambda: Settings(monthly_model_budget_usd=0.01, _env_file=None))
    first = providers.reserve_cost("test-model", 0.006)
    with pytest.raises(CapabilityError, match="budget reached"):
        providers.reserve_cost("test-model", 0.006)
    providers.settle_cost(first, 0.001, {"test": True})
    assert providers.reserve_cost("test-model", 0.007)
