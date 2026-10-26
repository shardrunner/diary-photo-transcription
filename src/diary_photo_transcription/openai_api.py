"""OpenAI Responses API adapter with the same contract as the Gemini adapter."""

from __future__ import annotations

import base64
import copy
import os
import time
from collections.abc import Callable
from decimal import Decimal
from typing import Any

from dotenv import load_dotenv
from openai import OpenAI

from diary_photo_transcription.config import MediaResolution
from diary_photo_transcription.provider import ModelResult, PhotoSnapshot, TokenUsage
from diary_photo_transcription.schemas import model_response_json_schema

# The SDK retries connection errors, 408/409/429 and 5xx with backoff.
SDK_RETRIES = 2
# Per HTTP attempt, matching the Gemini adapter.
REQUEST_TIMEOUT_SECONDS = 300.0

# Standard rates for gpt-6.1-terra; reasoning tokens bill as output
# (https://developers.openai.com/api/docs/models/gpt-6.1-terra).
_INPUT_USD_PER_MILLION = Decimal("1.00")
_OUTPUT_USD_PER_MILLION = Decimal("5.00")
_MILLION = Decimal(1_000_000)

# "high" fits the image into 2048 px / 2,500 patches; "original" keeps full resolution.
_DETAIL: dict[MediaResolution, str] = {"high": "high", "ultra_high": "original"}


def strict_json_schema() -> dict[str, Any]:
    """The response schema in OpenAI strict mode: every property required, no defaults.

    Optional fields stay optional in value (nullable or empty), so Pydantic
    validation of the response is unchanged.
    """

    def visit(node: Any) -> None:
        if isinstance(node, dict):
            node.pop("default", None)
            if "properties" in node:
                node["required"] = list(node["properties"])
                node["additionalProperties"] = False
            for value in node.values():
                visit(value)
        elif isinstance(node, list):
            for value in node:
                visit(value)

    schema = copy.deepcopy(model_response_json_schema())
    visit(schema)
    return schema


def create_client() -> OpenAI:
    load_dotenv()
    key = os.environ.get("OPENAI_API_KEY", "")
    if not key.strip():
        raise ValueError("OPENAI_API_KEY is required")
    return OpenAI(api_key=key, timeout=REQUEST_TIMEOUT_SECONDS, max_retries=SDK_RETRIES)


def estimate_standard_cost_usd(usage: TokenUsage) -> Decimal:
    """Standard (uncached) cost including reasoning tokens."""
    output_tokens = usage.output_tokens + usage.thinking_tokens
    return (
        Decimal(usage.input_tokens) * _INPUT_USD_PER_MILLION
        + Decimal(output_tokens) * _OUTPUT_USD_PER_MILLION
    ) / _MILLION


def request_observation(
    client: Any,
    *,
    model: str,
    photo: PhotoSnapshot,
    prompt: str,
    thinking_level: str | None = None,
    media_resolution: MediaResolution = "high",
    on_interaction: Callable[[dict[str, Any]], object] | None = None,
) -> ModelResult:
    """One stateless strict-JSON response; evidence is handed out before validation."""
    image = base64.b64encode(photo.upload_bytes).decode("ascii")
    request: dict[str, Any] = {
        "model": model,
        "input": [
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": prompt},
                    {
                        "type": "input_image",
                        "image_url": f"data:image/jpeg;base64,{image}",
                        "detail": _DETAIL[media_resolution],
                    },
                ],
            }
        ],
        "text": {
            "format": {
                "type": "json_schema",
                "name": "photo_observation",
                "schema": strict_json_schema(),
                "strict": True,
            }
        },
        "store": False,
    }
    if thinking_level is not None:
        request["reasoning"] = {"effort": thinking_level}

    started = time.monotonic()
    response: Any = client.responses.create(**request)
    duration = time.monotonic() - started

    if on_interaction is not None:
        on_interaction(
            {
                "interaction": response.model_dump(mode="json"),
                "requestDurationSeconds": duration,
                "model": model,
                "mediaResolution": media_resolution,
                "thinkingLevel": thinking_level,
            }
        )

    if response.error is not None:
        raise ValueError(f"OpenAI response reported an error: {response.error.message}")
    if response.status != "completed":
        details = response.incomplete_details
        reason = f" ({details.reason})" if details is not None and details.reason else ""
        raise ValueError(f"OpenAI response status is not completed: {response.status}{reason}")
    output_text = response.output_text
    if not output_text.strip():
        raise ValueError("OpenAI returned no structured response text")
    usage = response.usage
    if usage is None:
        raise ValueError("OpenAI returned no usage metadata")
    reasoning = usage.output_tokens_details.reasoning_tokens
    return ModelResult(
        raw_text=output_text,
        usage=TokenUsage(
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens - reasoning,
            thinking_tokens=reasoning,
            total_tokens=usage.total_tokens,
        ),
        interaction_id=response.id or None,
        request_duration_seconds=duration,
    )
