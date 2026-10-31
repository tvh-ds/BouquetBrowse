"""Exercise real SDK serialization against a fake provider, never live credentials."""

import json

import httpx
import openai
import pytest
from pydantic import ValidationError
from sqlalchemy import select

from bouquetbrowse import config, model_calls, recognition
from bouquetbrowse.browser import BrowserAction
from bouquetbrowse.config import Settings
from bouquetbrowse.model_transport import GROQ_VISION_MODEL, require_model, structured_response
from bouquetbrowse.models import CostEntry
from bouquetbrowse.providers import CapabilityError, billed_amount


def groq_settings(**kwargs):
    return Settings(_env_file=None, model_provider="groq", groq_api_key="fictional-groq-key", **kwargs)


def fake_provider(monkeypatch, *, invalid=False, status=200):
    requests = []
    sdk = openai.OpenAI

    def handle(request):
        body = json.loads(request.content)
        requests.append((request, body))
        if status != 200:
            return httpx.Response(status, json={"error": {"message": "fictional provider error"}})
        value = {"action": "finish", "observation_version": "", "target": None, "query": None}
        if invalid:
            value["action"] = "execute_arbitrary_script"
        return httpx.Response(
            200,
            json={
                "id": "fictional-completion",
                "object": "chat.completion",
                "created": 0,
                "model": GROQ_VISION_MODEL,
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "stop",
                        "message": {"role": "assistant", "content": json.dumps(value)},
                    }
                ],
                "usage": {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120},
            },
        )

    monkeypatch.setattr(
        openai,
        "OpenAI",
        lambda **kwargs: sdk(
            http_client=httpx.Client(transport=httpx.MockTransport(handle)),
            **kwargs,
        ),
    )
    return requests


def generate(settings, images=0):
    return structured_response(
        settings,
        model=settings.active_planner_model,
        text_format=BrowserAction,
        max_output_tokens=450,
        input=[
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": "Fictional empty flower-search surface."},
                    *[
                        {"type": "input_image", "image_url": "data:image/jpeg;base64,ZmljdGlvbmFs"}
                        for _ in range(images)
                    ],
                ],
            }
        ],
    )


def test_groq_uses_own_key_endpoint_and_strict_schema(monkeypatch):
    requests = fake_provider(monkeypatch)
    response = generate(groq_settings(openai_api_key="fictional-other-provider"), images=3)
    request, body = requests[0]
    assert str(request.url) == "https://api.groq.com/openai/v1/chat/completions"
    assert request.headers["authorization"] == "Bearer fictional-groq-key"
    assert body["response_format"]["json_schema"]["strict"] is True
    assert body["max_completion_tokens"] == 450 and "tools" not in body and "store" not in body
    assert [p["type"] for p in body["messages"][0]["content"]] == ["text", "image_url", "image_url", "image_url"]
    assert response.output_parsed.action == "finish"
    assert response.usage.model_dump()["input_tokens"] == 100


def test_groq_does_not_fall_back_to_openai_key():
    settings = Settings(_env_file=None, model_provider="groq", groq_api_key="", openai_api_key="fictional-key")
    with pytest.raises(CapabilityError, match="GROQ_API_KEY"):
        generate(settings)


@pytest.mark.parametrize("images,model", [(4, GROQ_VISION_MODEL), (1, "openai/gpt-oss-20b")])
def test_unsupported_images_fail_before_network(monkeypatch, images, model):
    requests = fake_provider(monkeypatch)
    with pytest.raises(CapabilityError):
        generate(groq_settings(groq_planner_model=model), images)
    assert requests == []


def test_groq_schema_validation_and_uncertain_retry(db, monkeypatch):
    requests = fake_provider(monkeypatch, invalid=True)
    settings = groq_settings()
    monkeypatch.setattr(config, "get_settings", lambda: settings)
    monkeypatch.setattr(model_calls, "get_settings", lambda: settings)
    for _ in range(2):
        with pytest.raises(CapabilityError, match="uncertain"):
            model_calls.invoke_once(
                GROQ_VISION_MODEL,
                {"synthetic": True},
                lambda: (
                    generate(settings).output_parsed.model_dump(),
                    {},
                    0.001,
                ),
                0.025,
            )
    assert len(requests) == 1
    assert db.scalar(select(CostEntry)).provider == "groq"
    assert db.scalar(select(CostEntry)).state == "uncertain"


def test_provider_isolation_in_receipts_and_spending(db):
    calls = []

    def invoke():
        calls.append(True)
        return {"synthetic": True}, {}, 0.001

    for provider in ["openai", "groq", "groq"]:
        model_calls.invoke_once("same-model-name", {"same": "input"}, invoke, provider=provider)
    assert len(calls) == 2
    assert {e.provider for e in db.scalars(select(CostEntry))} == {"openai", "groq"}


def test_upgrade_preserves_uncertain_legacy_openai_receipt(db):
    from datetime import timedelta

    from bouquetbrowse.db import utcnow
    from bouquetbrowse.pipeline import digest
    from bouquetbrowse.runtime_models import ModelCall

    request = {"text_hash": "fictional-retained-text", "dimensions": 1536}
    legacy_hash = digest({"model": "text-embedding-3-small", "request": request})
    cost = CostEntry(
        provider="openai", model="text-embedding-3-small", state="uncertain", amount_usd=0.001, amount_microusd=1000
    )
    db.add(cost)
    db.flush()
    db.add(
        ModelCall(
            scope_key=f"request:{legacy_hash}",
            request_hash=legacy_hash,
            attempt=1,
            model=cost.model,
            cost_id=cost.id,
            state="uncertain",
            retention_until=utcnow() + timedelta(days=30),
        )
    )
    db.commit()
    called = []
    with pytest.raises(CapabilityError, match="uncertain"):
        model_calls.invoke_once(cost.model, request, lambda: called.append(True), provider="openai")
    assert called == []


def test_groq_quota_failure_is_not_retried_automatically(db, monkeypatch):
    requests = fake_provider(monkeypatch, status=429)
    settings = groq_settings()
    monkeypatch.setattr(model_calls, "get_settings", lambda: settings)
    for _ in range(2):
        with pytest.raises(CapabilityError, match="uncertain"):
            model_calls.invoke_once(
                GROQ_VISION_MODEL,
                {"synthetic": "quota"},
                lambda: (
                    generate(settings).output_parsed.model_dump(),
                    {},
                    0.001,
                ),
                0.025,
            )
    assert len(requests) == 1


def test_explicit_provider_change_rejects_pinned_work():
    with pytest.raises(CapabilityError, match="Provider changed"):
        require_model(groq_settings(), GROQ_VISION_MODEL, provider="openai")
    with pytest.raises(CapabilityError, match="spending contract"):
        require_model(groq_settings(), "unbudgeted-model")


def test_groq_usage_uses_groq_rates_not_openai_model_prefix():
    usage = {"input_tokens": 1_000_000, "output_tokens": 1_000_000}
    assert billed_amount("openai/gpt-oss-20b", usage, 9, provider="groq") == 0.375
    assert billed_amount(GROQ_VISION_MODEL, usage, 9, provider="groq") == 4.8
    assert billed_amount(GROQ_VISION_MODEL, {}, 0.025, provider="groq") == 0.025


def test_legacy_extraction_provider_must_be_explicit():
    with pytest.raises(ValidationError):
        groq_settings(extraction_provider="openai")


def test_admin_status_recognizes_selected_groq_without_exposing_key(client, monkeypatch, admin_headers):
    from bouquetbrowse import discovery_api

    settings = groq_settings()
    monkeypatch.setattr(discovery_api, "get_settings", lambda: settings)
    response = client.get("/v1/admin/discovery/status", headers=admin_headers)
    assert response.status_code == 200
    assert response.json()["model_configured"] is True
    assert response.json()["model_provider"] == "groq"
    assert settings.groq_api_key not in response.text


def test_groq_two_image_chunks_preserve_truncation(db, monkeypatch):
    from test_mixed_recognition import result

    settings = groq_settings()
    monkeypatch.setattr(config, "get_settings", lambda: settings)
    prepared = []

    def prepare(bundle):
        prepared.extend(m["media_id"] for m in bundle["media"])
        return bundle["media"]

    monkeypatch.setattr(recognition, "prepare_views", prepare)
    calls = []

    def call(bundle, views, configuration):
        calls.append(len(views))
        return result([], interpretation=True)

    output = recognition.analyze_offer(
        {"media": [{"media_id": str(i)} for i in range(8)]}, {"model_provider": "groq"}, call=call
    )
    assert calls == [3, 3]
    assert prepared == [str(i) for i in range(6)]  # Unprocessed carousel media cannot block readiness.
    assert output["unprocessed_media"] == ["6", "7"]
