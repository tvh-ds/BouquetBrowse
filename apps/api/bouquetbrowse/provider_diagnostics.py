"""Allowlisted failure metadata. Never stringify provider exceptions or bodies."""

import json
import math

import httpx
import openai
from pydantic import ValidationError

from .providers import CapabilityError

CATEGORIES = {
    "rate_limit",
    "quota_exhausted",
    "authentication",
    "permission",
    "model_unavailable",
    "invalid_request",
    "provider_server",
    "provider_http",
    "timeout",
    "connection",
    "response_validation",
    "response_decode",
    "response_truncated",
    "response_refused",
    "response_incomplete",
    "application_error",
}
CODES = {
    "rate_limit_exceeded",
    "insufficient_quota",
    "invalid_api_key",
    "model_not_found",
    "model_decommissioned",
    "json_validate_failed",
    "invalid_request_error",
    "context_length_exceeded",
    "extraction_incomplete",
    "planner_incomplete",
    "model_response_refused",
    "model_response_truncated",
    "model_response_invalid",
}


def failure_diagnostics(exc, elapsed_ms):
    category, status, code, retry_after = "application_error", None, None, None
    if isinstance(exc, openai.APIStatusError):
        value = exc.status_code
        status = value if type(value) is int and 100 <= value <= 599 else None
        value = exc.code
        code = value if isinstance(value, str) and value in CODES else None
        category = {
            400: "invalid_request",
            401: "authentication",
            403: "permission",
            404: "model_unavailable",
            408: "timeout",
            413: "invalid_request",
            422: "invalid_request",
            429: "rate_limit",
        }.get(status, "provider_server" if status and status >= 500 else "provider_http")
        if code == "insufficient_quota":
            category = "quota_exhausted"
        elif code == "json_validate_failed":
            category = "response_validation"
        try:
            value = float(exc.response.headers.get("retry-after", ""))
            if math.isfinite(value) and value >= 0:
                retry_after = min(86400, math.ceil(value))
        except (ValueError, OverflowError):
            pass
    elif isinstance(exc, (openai.APITimeoutError, httpx.TimeoutException, TimeoutError)):
        category = "timeout"
    elif isinstance(exc, (openai.APIConnectionError, httpx.NetworkError)):
        category = "connection"
    elif isinstance(exc, openai.LengthFinishReasonError):
        category = "response_truncated"
    elif isinstance(exc, openai.ContentFilterFinishReasonError):
        category = "response_refused"
    elif isinstance(exc, (openai.APIResponseValidationError, ValidationError)):
        category = "response_validation"
    elif isinstance(exc, json.JSONDecodeError):
        category = "response_decode"
    elif isinstance(exc, CapabilityError):
        code = exc.code if isinstance(exc.code, str) and exc.code in CODES else None
        category = {
            "extraction_incomplete": "response_incomplete",
            "planner_incomplete": "response_incomplete",
            "model_response_refused": "response_refused",
            "model_response_truncated": "response_truncated",
            "model_response_invalid": "response_validation",
        }.get(code, "application_error")
    return {
        "category": category,
        "http_status": status,
        "provider_code": code,
        "retry_after_seconds": retry_after,
        "latency_ms": max(0, min(int(elapsed_ms), 86400000)),
    }


def public_diagnostics(usage):
    """Revalidate stored JSON before exposing it through administration."""
    failure = usage.get("failure") if isinstance(usage, dict) else None
    if (
        not isinstance(failure, dict)
        or not isinstance(failure.get("category"), str)
        or failure["category"] not in CATEGORIES
    ):
        return None
    result = {"category": failure["category"]}
    for key, maximum in [("http_status", 599), ("retry_after_seconds", 86400), ("latency_ms", 86400000)]:
        value = failure.get(key)
        result[key] = value if type(value) is int and (100 if key == "http_status" else 0) <= value <= maximum else None
    code = failure.get("provider_code")
    result["provider_code"] = code if isinstance(code, str) and code in CODES else None
    return result


def failure_summary(diagnostics):
    safe = public_diagnostics({"failure": diagnostics})
    if safe is None:
        return "diagnostics unavailable"
    return "; ".join(
        str(value) for value in [safe["category"], safe["http_status"], safe["provider_code"]] if value is not None
    )
