import json
from datetime import timedelta

import httpx
import openai
import pytest
from pydantic import BaseModel, ValidationError
from sqlalchemy import select

from bouquetbrowse.db import utcnow
from bouquetbrowse.model_calls import invoke_once
from bouquetbrowse.models import CostEntry
from bouquetbrowse.provider_diagnostics import failure_diagnostics, public_diagnostics
from bouquetbrowse.providers import CapabilityError
from bouquetbrowse.retention import expire
from bouquetbrowse.runtime_models import ModelCall

SECRET = "fictional-secret-token-private-caption"


def status_error(status, code=None, retry_after="3.2"):
    request = httpx.Request(
        "POST", f"https://api.example.test/private?token={SECRET}", headers={"Authorization": SECRET}, content=SECRET
    )
    response = httpx.Response(status, request=request, headers={"retry-after": retry_after, "x-request-id": SECRET})
    return openai.APIStatusError(
        SECRET, response=response, body={"code": code, "message": SECRET, "failed_generation": SECRET}
    )


@pytest.mark.parametrize(
    "status,code,category",
    [
        (429, "rate_limit_exceeded", "rate_limit"),
        (429, "insufficient_quota", "quota_exhausted"),
        (401, "invalid_api_key", "authentication"),
        (403, None, "permission"),
        (404, "model_not_found", "model_unavailable"),
        (500, None, "provider_server"),
        (400, "json_validate_failed", "response_validation"),
        (422, SECRET, "invalid_request"),
    ],
)
def test_http_metadata_is_allowlisted(status, code, category):
    metadata = failure_diagnostics(status_error(status, code), 15)
    assert metadata["category"] == category
    assert metadata["http_status"] == status
    assert metadata["retry_after_seconds"] == 4
    assert SECRET not in json.dumps(metadata)


@pytest.mark.parametrize(
    "header,expected", [("nan", None), ("inf", None), (SECRET, None), ("-1", None), ("900000", 86400)]
)
def test_retry_after_is_bounded_numeric_metadata(header, expected):
    assert failure_diagnostics(status_error(429, retry_after=header), 0)["retry_after_seconds"] == expected


@pytest.mark.parametrize(
    "error,category",
    [
        (TimeoutError(SECRET), "timeout"),
        (openai.APITimeoutError(httpx.Request("POST", "https://api.example.test")), "timeout"),
        (
            openai.APIConnectionError(message=SECRET, request=httpx.Request("POST", "https://api.example.test")),
            "connection",
        ),
        (json.JSONDecodeError(SECRET, SECRET, 0), "response_decode"),
        (openai.ContentFilterFinishReasonError(), "response_refused"),
        (CapabilityError(SECRET, "model_response_truncated"), "response_truncated"),
        (ValueError(SECRET), "application_error"),
    ],
)
def test_non_http_exceptions_do_not_expose_messages(error, category):
    metadata = failure_diagnostics(error, 10)
    assert metadata["category"] == category
    assert SECRET not in json.dumps(metadata)


def test_validation_input_and_invalid_stored_json_are_not_exposed():
    class Schema(BaseModel):
        number: int

    with pytest.raises(ValidationError) as error:
        Schema(number=SECRET)
    assert failure_diagnostics(error.value, 1)["category"] == "response_validation"
    assert SECRET not in json.dumps(failure_diagnostics(error.value, 1))
    assert public_diagnostics({"failure": {"category": [SECRET]}}) is None
    assert public_diagnostics(
        {"failure": {"category": "timeout", "http_status": True, "provider_code": SECRET, "raw": SECRET}}
    ) == {
        "category": "timeout",
        "http_status": None,
        "provider_code": None,
        "retry_after_seconds": None,
        "latency_ms": None,
    }


@pytest.mark.parametrize(
    "options,category",
    [
        ({"status": 429}, "rate_limit"),
        ({"invalid": True}, "response_validation"),
        ({"finish_reason": "length"}, "response_truncated"),
    ],
)
def test_actual_sdk_failures_are_recorded_without_retries(db, monkeypatch, options, category):
    from test_groq_provider import fake_provider, generate, groq_settings

    from bouquetbrowse import model_calls

    requests = fake_provider(monkeypatch, **options)
    settings = groq_settings()
    monkeypatch.setattr(model_calls, "get_settings", lambda: settings)
    for _ in range(2):
        with pytest.raises(CapabilityError):
            invoke_once(settings.active_planner_model, {"fictional": True}, lambda: (generate(settings), {}, 0.001))
    db.expire_all()
    assert len(requests) == 1
    assert db.scalar(select(ModelCall)).usage["failure"]["category"] == category


def test_receipt_api_logs_replay_and_expiry(db, client, admin_headers, tester_headers, caplog):
    attempts = []

    def fail():
        attempts.append(True)
        raise status_error(429, "rate_limit_exceeded")

    for _ in range(2):
        with pytest.raises(CapabilityError) as error:
            invoke_once("fictional-model", {"input": "fictional"}, fail)
        assert SECRET not in str(error.value)
        assert error.value.code == "call_replay_required"
    db.expire_all()
    call = db.scalar(select(ModelCall))
    assert len(attempts) == 1 and call.state == "uncertain"
    assert call.usage["failure"]["category"] == "rate_limit"
    assert db.get(CostEntry, call.cost_id).amount_microusd == 100000
    assert SECRET not in caplog.text and "category=rate_limit" in caplog.text
    assert client.get("/v1/admin/model-calls", headers=tester_headers).status_code == 403
    response = client.get("/v1/admin/model-calls", headers=admin_headers)
    assert response.json()["items"][0]["diagnostics"]["http_status"] == 429
    assert SECRET not in response.text
    call.retention_until = utcnow() - timedelta(days=1)
    db.commit()
    expire(db)
    db.commit()
    assert "failure" not in call.usage
    assert db.get(CostEntry, call.cost_id).amount_microusd == 100000


def test_in_flight_deletion_does_not_restore_diagnostics(db):
    def fail_after_deletion():
        call = db.scalar(select(ModelCall))
        call.state, call.usage = "removed", {}
        db.commit()
        raise TimeoutError(SECRET)

    with pytest.raises(CapabilityError):
        invoke_once("fictional-model", {}, fail_after_deletion)
    db.expire_all()
    call = db.scalar(select(ModelCall))
    assert call.state == "removed" and call.usage == {}
