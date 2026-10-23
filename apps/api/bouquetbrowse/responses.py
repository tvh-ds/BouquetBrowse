"""Public catalog response contracts; OpenAPI is the client type authority."""

from typing import Any

from pydantic import BaseModel, ConfigDict


class Contract(BaseModel):
    model_config = ConfigDict(extra="allow")


class PriceView(Contract):
    id: str
    amount_min: int
    amount_max: int | None
    currency: str
    kind: str
    component: str
    reviewed: bool
    advertised_at: str
    observed_at: str
    valid_until: str | None
    evidence: dict[str, Any]


class SellerView(Contract):
    id: str
    name: str
    slug: str
    district: str
    city: str


class AvailabilityView(Contract):
    status: str
    lead_days: int | None
    delivery: bool | None


class ListingView(Contract):
    id: str
    title: str
    description: str
    primary_flower: str | None
    color: str | None
    arrangement: str | None
    stem_count: int | None
    image_path: str | None
    style: str | None
    occasion: str | None
    state: str
    attributes: dict[str, Any]
    is_demo: bool
    seller: SellerView
    price: PriceView | None
    availability: AvailabilityView
    published_at: str | None
    last_checked_at: str | None
    source_url: str | None
    source_platform: str | None
    similarity: float | None = None
    match_reasons: list[str] | None = None
    qualified: bool | None = None


class CatalogView(Contract):
    items: list[ListingView]
    total: int
    next_cursor: str | None
    search_mode: str


class SimilarView(Contract):
    items: list[ListingView]


class SummaryView(Contract):
    status: str
    seller_count: int
    listing_count: int
    median: float | None
    min: int | None
    max: int | None
    q1: float | None
    q3: float | None
    percentile: float | None
    relative_difference: float | None
    window_days: int
    target_issues: list[str]
    is_demo: bool
    caveat: str
    run_id: str | None = None


class ExcludedView(Contract):
    listing_id: str
    reasons: list[str]


class ComparisonView(Contract):
    summary: SummaryView
    items: list[ListingView]
    excluded: list[ExcludedView]


class SourceView(Contract):
    id: str
    url: str | None
    platform: str
    published_at: str
    last_seen_at: str
    caption: str
    version_id: str


class AssertionView(Contract):
    id: str
    field: str
    value: dict[str, Any]
    status: str
    review_state: str
    evidence: list[Any]
    calibrated_confidence: float | None


class DetailView(ListingView):
    sources: list[SourceView]
    assertions: list[AssertionView]
    warnings: list[str]


class FacetsView(Contract):
    flowers: list[str]
    colors: list[str]
    districts: list[str]
    arrangements: list[str]
    occasions: list[str]


class SessionView(Contract):
    id: str
    role: str
    mode: str
