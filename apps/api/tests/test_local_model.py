import sys
from types import SimpleNamespace

import pytest
from pydantic import ValidationError
from sqlalchemy import select

from bouquetbrowse import local_model, model_calls
from bouquetbrowse.browser import BrowserAction
from bouquetbrowse.config import Settings
from bouquetbrowse.model_transport import structured_response
from bouquetbrowse.models import CostEntry
from bouquetbrowse.providers import CapabilityError


def test_local_generation_bounds_and_validates_without_cloud(tmp_path, monkeypatch):
    for suffix in ("xml", "bin"):
        (tmp_path / f"openvino_language_model.{suffix}").touch()
    settings = Settings(_env_file=None, model_provider="openvino", openvino_model_dir=tmp_path)
    ov = SimpleNamespace(ChatHistory=list, GenerationConfig=SimpleNamespace, StructuredOutputConfig=SimpleNamespace)
    monkeypatch.setitem(sys.modules, "openvino_genai", ov)
    monkeypatch.setattr(local_model, "prepared_image", lambda url: "fictional-tensor")
    output = '{"action":"finish","observation_version":"","target":null,"query":null}'

    def run(history, images, generation_config, streamer):
        assert images == ["fictional-tensor"]
        assert history[1]["content"].count("<ov_genai_image_0>") == 1
        assert generation_config.max_new_tokens == local_model.MAX_NEW_TOKENS
        metrics = SimpleNamespace(get_num_input_tokens=lambda: 10, get_num_generated_tokens=lambda: 5)
        return SimpleNamespace(texts=[output], perf_metrics=metrics)

    monkeypatch.setattr(local_model, "pipeline", lambda path, device: SimpleNamespace(generate=run))
    image = {"type": "input_image", "image_url": "data:image/jpeg;base64,ZmljdGlvbmFs"}
    parts = [{"type": "input_text", "text": "<ov_genai_image_0>"}, image]

    def generate():
        return structured_response(
            settings,
            model=settings.active_planner_model,
            text_format=BrowserAction,
            max_output_tokens=3000,
            input=[{"role": "system", "content": "Choose an action."}, {"role": "user", "content": parts}],
        )

    assert generate().output_parsed.action == "finish"
    output = '{"action":"execute_shell"}'
    with pytest.raises(ValidationError):
        generate()
    parts.append(image)
    with pytest.raises(CapabilityError, match="image limit"):
        generate()


def test_local_failure_keeps_a_receipt_without_reserving_api_spend(db):
    def invalid_output():
        raise ValueError("fictional failure")

    with pytest.raises(CapabilityError, match="Local inference outcome"):
        model_calls.invoke_once("local-test", {"fixture": True}, invalid_output, provider="openvino")
    cost = db.scalar(select(CostEntry))
    assert (cost.provider, cost.state, cost.amount_microusd) == ("openvino", "uncertain", 0)
