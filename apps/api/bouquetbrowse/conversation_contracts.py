"""Validated inputs contain observations, never executable browser instructions."""

from datetime import datetime
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, field_validator

from .schemas import StrictModel


class MessageObservation(StrictModel):
    platform_id: str = Field(min_length=1, max_length=160, pattern=r"^[A-Za-z0-9_.:-]+$")
    username: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9_.]+$")
    platform_account_id: str | None = Field(default=None, max_length=160)
    url: str = Field(max_length=2048)
    text: str = Field(max_length=20000)
    published_at: datetime | None = None
    reply_to: str | None = Field(default=None, max_length=160)
    quote_of: str | None = Field(default=None, max_length=160)
    media_urls: list[str] = Field(default_factory=list, max_length=10)

    @field_validator("published_at")
    @classmethod
    def aware_time(cls, value):
        if value and value.tzinfo is None:
            raise ValueError("Publication time must be timezone-aware")
        return value

    @field_validator("url")
    @classmethod
    def threads_url(cls, value):
        return validate_threads_url(value)


def validate_threads_url(value):
    url = urlsplit(value)
    if url.scheme != "https" or url.hostname not in {"www.threads.com", "threads.com"}:
        raise ValueError("Only HTTPS Threads navigation is supported")
    if url.username or url.password or url.port not in {None, 443} or url.fragment:
        raise ValueError("Invalid Threads URL")
    return value


class CaptureEnvelope(StrictModel):
    source_url: str = Field(max_length=2048)
    messages: list[MessageObservation] = Field(max_length=100)
    sorting: str = Field(default="unknown", max_length=40)
    stop_reason: str = Field(max_length=80)
    remaining_expansions: int | None = Field(default=None, ge=0, le=10000)
    observed_branches: list[str] = Field(default_factory=list, max_length=100)

    @field_validator("source_url")
    @classmethod
    def threads_url(cls, value):
        return validate_threads_url(value)


class QuoteReference(StrictModel):
    version_id: str
    quote: str = Field(min_length=1, max_length=1000)
    before: str | None = Field(default=None, max_length=200)
    after: str | None = Field(default=None, max_length=200)


class CompositionComponent(StrictModel):
    flower: str = Field(max_length=80)
    status: Literal["stated", "visual_inference", "context_inference", "unknown", "conflict"]
    evidence_refs: list[QuoteReference] = Field(default_factory=list, max_length=20)
    media_refs: list[str] = Field(default_factory=list, max_length=12)
    stated_count: int | None = Field(default=None, ge=1, le=10000)
    alternatives: list[str] = Field(default_factory=list, max_length=10)
    review_state: Literal["pending", "accepted", "corrected", "rejected"] = "pending"
