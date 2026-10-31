"""Explicit structured generation transports; never route a key to another provider."""

from types import SimpleNamespace

GROQ_BASE_URL = "https://api.groq.com/openai/v1"
GROQ_VISION_MODEL = "qwen/qwen3.8-27b"
RATES = {
    "openai": {"gpt-6-luna": (0.1, 0.5), "gpt-6.1-sol": (2, 10)},
    "groq": {
        "openai/gpt-oss-20b": (0.075, 0.30),
        "openai/gpt-oss-120b": (0.15, 0.60),
        GROQ_VISION_MODEL: (0.80, 4.00),
    },
}


def require_model(settings, model, *, vision=False, provider=None):
    from .providers import CapabilityError

    selected = provider or settings.model_provider
    if selected != settings.model_provider:
        raise CapabilityError(
            "Provider changed; explicitly reprocess with the current configuration.", "provider_changed"
        )
    if not settings.model_configured:
        field = "GROQ_API_KEY" if selected == "groq" else "OPENAI_API_KEY"
        raise CapabilityError(f"Configure {field} for the selected model provider.", "model_not_configured")
    if model not in RATES[selected]:
        raise CapabilityError("Model has no supported transport and spending contract.", "unsupported_model")
    if vision and selected == "groq" and model != GROQ_VISION_MODEL:
        raise CapabilityError("Choose the supported Groq vision model for image requests.", "vision_not_supported")
    return selected


def image_limit(settings=None, configuration=None):
    if settings is None:
        from .config import get_settings

        settings = get_settings()
    return 3 if (configuration or {}).get("model_provider", settings.model_provider) == "groq" else 4


def structured_response(settings, *, model, input, text_format, max_output_tokens, timeout=40, provider=None):
    """Preserve the existing Responses contract while adapting Groq's strict chat API."""
    from openai import OpenAI

    from .providers import CapabilityError

    images = sum(
        part.get("type") == "input_image"
        for message in input
        if isinstance(message.get("content"), list)
        for part in message["content"]
    )
    selected = require_model(settings, model, vision=bool(images), provider=provider)
    if images > image_limit(settings):
        raise CapabilityError("Request exceeds the selected provider's image limit.", "image_limit")
    if selected == "openai":
        return OpenAI(api_key=settings.openai_api_key, timeout=timeout, max_retries=0).responses.parse(
            model=model, input=input, text_format=text_format, store=False, max_output_tokens=max_output_tokens
        )
    messages = []
    for message in input:
        content = message["content"]
        if isinstance(content, list):
            converted = []
            for part in content:
                if part["type"] == "input_text":
                    converted.append({"type": "text", "text": part["text"]})
                elif part["type"] == "input_image":
                    converted.append({"type": "image_url", "image_url": {"url": part["image_url"]}})
                else:
                    raise ValueError("Unsupported model input part")
            content = converted
        messages.append({"role": message["role"], "content": content})
    response = OpenAI(
        api_key=settings.groq_api_key, base_url=GROQ_BASE_URL, timeout=timeout, max_retries=0
    ).chat.completions.parse(
        model=model,
        messages=messages,
        response_format=text_format,
        max_completion_tokens=max_output_tokens,
    )
    choice = response.choices[0]
    if choice.finish_reason != "stop" or choice.message.parsed is None or choice.message.refusal:
        raise CapabilityError("Groq returned a refused or incomplete structured response.", "extraction_incomplete")
    # Revalidate even SDK-parsed values; schemas alone never establish grounding.
    parsed = text_format.model_validate(choice.message.parsed)
    raw_usage = response.usage.model_dump() if response.usage else {}
    usage = {"provider": "groq", "pricing_basis": "published_paid_rate_estimate", "resolved_model": response.model}
    if "prompt_tokens" in raw_usage and "completion_tokens" in raw_usage:
        if any(type(raw_usage[k]) is not int or raw_usage[k] < 0 for k in ("prompt_tokens", "completion_tokens")):
            raise ValueError("Provider returned invalid token usage")
        usage.update(input_tokens=raw_usage["prompt_tokens"], output_tokens=raw_usage["completion_tokens"])
    return SimpleNamespace(output_parsed=parsed, usage=SimpleNamespace(model_dump=lambda: usage), model=response.model)
