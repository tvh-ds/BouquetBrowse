"""Bounded, in-process OpenVINO generation over trusted local weights."""

import base64
import binascii
import io
import json
import time
from functools import lru_cache
from threading import Lock
from types import SimpleNamespace

from PIL import Image

from .providers import CapabilityError

MAX_IMAGE_BYTES = 4 * 1024 * 1024
MAX_IMAGE_PIXELS = 4_000_000
MAX_PROMPT_BYTES = 32_000
MAX_NEW_TOKENS = 1024
JPEG_PREFIX = "data:image/jpeg;base64,"
PIPELINE_LOCK = Lock()


@lru_cache(maxsize=1)
def pipeline(model_dir, device):
    import openvino_genai

    return openvino_genai.VLMPipeline(model_dir, device)


def prepared_image(url):
    import numpy
    import openvino

    if not url.startswith(JPEG_PREFIX) or len(url) > len(JPEG_PREFIX) + 4 * ((MAX_IMAGE_BYTES + 2) // 3):
        raise CapabilityError("Local inference requires a bounded JPEG data URL.", "local_input_invalid")
    try:
        data = base64.b64decode(url[len(JPEG_PREFIX) :], validate=True)
        if len(data) > MAX_IMAGE_BYTES:
            raise ValueError("JPEG exceeds size limit")
        with Image.open(io.BytesIO(data), formats=["JPEG"]) as source:
            if source.width * source.height > MAX_IMAGE_PIXELS:
                raise ValueError("JPEG exceeds pixel limit")
            source.thumbnail((672, 672))
            return openvino.Tensor(numpy.array(source.convert("RGB"))[None])
    except (binascii.Error, ValueError, OSError, Image.DecompressionBombError):
        raise CapabilityError("Local inference could not decode a bounded JPEG.", "local_input_invalid") from None


def generate(settings, messages, schema, max_output_tokens):
    try:
        import openvino_genai as ov
    except ImportError:
        raise CapabilityError("Install the local-model extra to run OpenVINO.", "local_runtime_unavailable") from None

    schema_json = json.dumps(schema.model_json_schema(), ensure_ascii=False, separators=(",", ":"))
    history, images = ov.ChatHistory(), []
    prompt_bytes = len(schema_json.encode())
    for message in messages:
        parts = message["content"]
        if isinstance(parts, str):
            parts = [{"type": "input_text", "text": parts}]
        content = []
        for part in parts:
            if part["type"] == "input_text":
                # Keep captured control tokens from becoming chat or image delimiters.
                text = part["text"].replace("<", "\\u003c")
                prompt_bytes += len(text.encode())
                if prompt_bytes > MAX_PROMPT_BYTES:
                    raise CapabilityError("Local inference prompt exceeds the supported size.", "local_input_invalid")
                content.append(text)
            elif part["type"] == "input_image" and not images:
                content.append("<ov_genai_image_0>")
                images.append(prepared_image(part["image_url"]))
            else:
                raise CapabilityError("Unsupported local inference input.", "local_input_invalid")
        if message["role"] == "system":
            content.append("Return only the requested JSON object. JSON schema: " + schema_json)
        history.append({"role": message["role"], "content": "\n".join(content)})

    try:
        config = ov.GenerationConfig()
        config.max_new_tokens = min(max_output_tokens, MAX_NEW_TOKENS)
        config.do_sample = False
        config.structured_output_config = ov.StructuredOutputConfig(json_schema=schema_json)
        # One pipeline per process, with no shared chat state or simultaneous decoding.
        with PIPELINE_LOCK:
            model = pipeline(str(settings.openvino_model_dir.resolve()), settings.openvino_device)
            deadline = time.monotonic() + 90
            result = model.generate(
                history, images=images, generation_config=config, streamer=lambda _: time.monotonic() >= deadline
            )
            if time.monotonic() >= deadline:
                raise TimeoutError("Local model generation timed out")
    except RuntimeError:
        raise CapabilityError(
            "OpenVINO could not load or run the configured model.", "local_runtime_unavailable"
        ) from None

    parsed = schema.model_validate_json(result.texts[0])
    metrics = result.perf_metrics
    usage = {
        "provider": "openvino",
        "pricing_basis": "local_no_api_charge",
        "resolved_model": settings.openvino_model,
        "input_tokens": metrics.get_num_input_tokens(),
        "output_tokens": metrics.get_num_generated_tokens(),
    }
    return SimpleNamespace(
        output_parsed=parsed, usage=SimpleNamespace(model_dump=lambda: usage), model=settings.openvino_model
    )
