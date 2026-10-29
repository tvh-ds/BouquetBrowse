"""Untrusted interpretation proposals must survive server-side evidence checks."""

from typing import Literal

from pydantic import Field

from .conversation_contracts import QuoteReference
from .schemas import StrictModel


class OfferField(StrictModel):
    field: Literal["arrangement", "color", "stem_count", "lead_days", "delivery", "flower", "location", "ownership"]
    value: str | int | bool
    evidence: list[QuoteReference] = Field(min_length=1, max_length=4)
    derivation: Literal["direct", "seller_confirmation"] = "direct"


class OfferInterpretation(StrictModel):
    seller_offer: bool
    ownership: QuoteReference | None
    location: QuoteReference | None
    multi_product: bool
    fields: list[OfferField] = Field(default_factory=list, max_length=30)
    warnings: list[str] = Field(default_factory=list, max_length=10)
