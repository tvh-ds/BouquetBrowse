from datetime import datetime
from typing import Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator

T = TypeVar("T")


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Evidence(StrictModel):
    quote: str = Field(max_length=1000)
    start: int = Field(ge=0)
    end: int = Field(ge=0)
    media_id: str | None = None


class ExtractedField(StrictModel, Generic[T]):
    value: T | None
    status: Literal["stated", "visual_inference", "context_inference", "unknown", "conflict"]
    evidence_refs: list[Evidence]
    raw_confidence: float | None = Field(default=None, ge=0, le=1)
    calibrated_confidence: float | None = Field(default=None, ge=0, le=1)
    review_state: Literal["pending", "accepted", "corrected", "rejected"] = "pending"
    method_version: str = "rules-v1"


class PriceClaim(StrictModel):
    amount_min: int = Field(ge=0, le=10**12)
    amount_max: int | None = Field(default=None, ge=0, le=10**12)
    currency: Literal["VND", "USD"]
    currency_basis: Literal["explicit", "seller_market"]
    kind: Literal["exact", "range", "from", "promotion", "previous"]
    component: Literal["bouquet", "delivery", "deposit"]
    evidence: Evidence


class ProductExtraction(StrictModel):
    arrangement: ExtractedField[str]
    primary_flower: ExtractedField[str]
    flower_composition: ExtractedField[list[str]]
    color: ExtractedField[str]
    stem_count: ExtractedField[int]
    lead_days: ExtractedField[int]
    delivery: ExtractedField[bool]
    wrapping: ExtractedField[str]
    style: ExtractedField[str]
    occasion: ExtractedField[str]
    prices: list[PriceClaim] = Field(max_length=30)
    warnings: list[str] = Field(max_length=30)


class ImportPost(StrictModel):
    platform: Literal["instagram", "threads", "operator"]
    platform_post_id: str = Field(min_length=1, max_length=160, pattern=r"^[\w.:-]+$")
    username: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9_.-]+$")
    seller_name: str = Field(min_length=1, max_length=160)
    seller_slug: str = Field(min_length=1, max_length=160, pattern=r"^[a-z0-9-]+$")
    district: str = Field(min_length=1, max_length=80)
    city: Literal["Hanoi"] = "Hanoi"
    source_url: HttpUrl | None = None
    published_at: datetime
    caption: str = Field(min_length=1, max_length=20000)
    media_urls: list[HttpUrl] = Field(default_factory=list, max_length=10)
    rights_confirmed: bool = False
    product_key: str | None = Field(default=None, max_length=80, pattern=r"^[A-Za-z0-9_.-]+$")

    @field_validator("published_at")
    @classmethod
    def timezone_required(cls, value):
        if value.tzinfo is None:
            raise ValueError("Publication time must include a timezone")
        return value

    @field_validator("source_url", "media_urls")
    @classmethod
    def https_only(cls, value):
        urls = value if isinstance(value, list) else [value]
        if any(url is not None and url.scheme != "https" for url in urls):
            raise ValueError("Source and media URLs must use HTTPS")
        return value


class ImportBatch(StrictModel):
    posts: list[ImportPost] = Field(min_length=1, max_length=100)


class PublicPageRequest(StrictModel):
    url: str = Field(min_length=1, max_length=2048)


class PublicPagePreview(StrictModel):
    parser_version: str
    warnings: list[str]
    draft: dict


class ReviewDecision(StrictModel):
    expected_fingerprint: str | None = None
    composition: list[str] | None = Field(default=None, max_length=20)
    decision: Literal["accept", "correct", "reject"]
    reason: str = Field(min_length=3, max_length=1000)
    primary_flower: str | None = Field(default=None, max_length=40)
    color: str | None = Field(default=None, max_length=40)
    arrangement: str | None = Field(default=None, max_length=40)
    stem_count: int | None = Field(default=None, ge=1, le=10000)
    price_minor: int | None = Field(default=None, ge=0, le=10**10)
    price_evidence_quote: str | None = Field(default=None, max_length=1000)
    configuration_evidence_quote: str | None = Field(default=None, max_length=1000)


class TakedownBody(StrictModel):
    listing_id: str
    reason: str = Field(min_length=3, max_length=1000)


class SyncBody(StrictModel):
    query: str = Field(default="bó hoa Hà Nội", min_length=1, max_length=200)
    username: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_.]{1,100}$")


class LoginBody(StrictModel):
    email: str = Field(max_length=254)
    password: str = Field(max_length=200)
