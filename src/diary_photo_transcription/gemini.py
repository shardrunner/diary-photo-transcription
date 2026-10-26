from __future__ import annotations

import base64
import os
import time
from collections.abc import Callable
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from dotenv import load_dotenv
from google import genai
from google.genai import types

from diary_photo_transcription.config import MediaResolution
from diary_photo_transcription.prompts import EXTRACTION_PROMPT
from diary_photo_transcription.provider import ModelResult, PhotoSnapshot, TokenUsage
from diary_photo_transcription.schemas import model_response_json_schema

# The SDK retries 408/409/429/5xx with capped exponential backoff; `attempts`
# is its retry count, so one request makes at most three HTTP attempts.
SDK_RETRIES = 2
# Per HTTP attempt. Dense pages with gemini-3.8-flash's default thinking
# (up to ~35k thinking tokens) exceeded 120 s repeatedly; 300 s leaves margin.
# Not part of the run fingerprint, so changing it never forces paid reruns.
REQUEST_TIMEOUT_MS = 300_000

# Introductory Standard rates for gemini-3.8-flash through 2026-12-31; both double on
# 2027-01-01 (https://ai.google.dev/gemini-api/docs/pricing).
_INPUT_USD_PER_MILLION = Decimal("0.75")
_OUTPUT_USD_PER_MILLION = Decimal("3.75")
_MILLION = Decimal(1_000_000)

InteractionContent = dict[str, object]
ResponseFormat = dict[str, object]


def build_interaction_input(
    photo: PhotoSnapshot,
    *,
    prompt: str = EXTRACTION_PROMPT,
    media_resolution: MediaResolution = "high",
) -> list[InteractionContent]:
    """Build text-first inline input with the configured prompt and JPEG resolution."""
    return [
        {"type": "text", "text": prompt},
        {
            "type": "image",
            "data": base64.b64encode(photo.upload_bytes).decode("ascii"),
            "mime_type": "image/jpeg",
            "resolution": media_resolution,
        },
    ]


def build_response_format() -> ResponseFormat:
    """Build the strict JSON response contract for an interaction."""
    return {
        "type": "text",
        "mime_type": "application/json",
        "schema": model_response_json_schema(),
    }


def create_client() -> genai.Client:
    """Use GEMINI_API_KEY explicitly; billing is not verified here."""
    load_dotenv()
    _reject_debug()
    key = os.environ.get("GEMINI_API_KEY", "")
    if not key.strip():
        raise ValueError("GEMINI_API_KEY is required")
    other = os.environ.get("GOOGLE_API_KEY")
    if other and other != key:
        raise ValueError("GOOGLE_API_KEY conflicts with GEMINI_API_KEY")
    return genai.Client(
        api_key=key,
        vertexai=False,
        http_options=types.HttpOptions(
            timeout=REQUEST_TIMEOUT_MS,
            retry_options=types.HttpRetryOptions(attempts=SDK_RETRIES),
        ),
    )


def _reject_debug() -> None:
    # SDK wire logging would write credentials and photos; even "0" enables it.
    if os.environ.get("GOOGLE_GENAI_DEBUG"):
        raise ValueError("GOOGLE_GENAI_DEBUG must be unset or empty for private requests")


def estimate_standard_cost_usd(usage: TokenUsage) -> Decimal:
    """Estimate Flash Standard cost at the current UTC date, including thinking."""
    output_tokens = usage.output_tokens + usage.thinking_tokens
    introductory_cost = (
        Decimal(usage.input_tokens) * _INPUT_USD_PER_MILLION
        + Decimal(output_tokens) * _OUTPUT_USD_PER_MILLION
    ) / _MILLION
    return introductory_cost * (2 if datetime.now(UTC).date() >= date(2027, 1, 1) else 1)


def _interaction_errors(interaction: Any) -> tuple[str, ...]:
    return tuple(
        ": ".join(part for part in (getattr(e, "code", None), getattr(e, "message", None)) if part)
        or "unspecified interaction error"
        for e in getattr(interaction, "errors", None) or ()
    )


def _required_token_count(metadata: Any, field: str) -> int:
    value = getattr(metadata, field, None)
    if type(value) is not int or value < 0:
        raise ValueError(f"Gemini returned invalid usage field {field}")
    return value


def request_observation(
    client: genai.Client,
    *,
    model: str,
    photo: PhotoSnapshot,
    prompt: str,
    thinking_level: str | None = None,
    media_resolution: MediaResolution = "high",
    on_interaction: Callable[[dict[str, Any]], object] | None = None,
) -> ModelResult:
    """Create one stateless structured interaction and return its text plus usage.

    ``on_interaction`` receives the full provider response before status, text
    or usage are accepted, so a paid but unusable response can still be saved.
    """
    request: dict[str, object] = {
        "model": model,
        "input": build_interaction_input(photo, prompt=prompt, media_resolution=media_resolution),
        "response_format": build_response_format(),
        "store": False,
        "stream": False,
    }
    if thinking_level is not None:
        request["generation_config"] = {"thinking_level": thinking_level}

    started = time.monotonic()
    interactions: Any = client.interactions
    interaction: Any = interactions.create(**request)
    duration = time.monotonic() - started

    if on_interaction is not None:
        on_interaction(
            {
                "interaction": interaction.model_dump(mode="json"),
                "requestDurationSeconds": duration,
                "model": model,
                "mediaResolution": media_resolution,
                "thinkingLevel": thinking_level,
            }
        )

    errors = _interaction_errors(interaction)
    if errors:
        raise ValueError(f"Gemini interaction reported errors: {'; '.join(errors)}")
    status = getattr(interaction, "status", None)
    if status != "completed":
        raise ValueError(f"Gemini interaction status is not completed: {status or 'missing'}")
    output_text = getattr(interaction, "output_text", None)
    if not isinstance(output_text, str) or not output_text.strip():
        raise ValueError("Gemini returned no structured response text")
    metadata = getattr(interaction, "usage", None)
    if metadata is None:
        raise ValueError("Gemini returned no usage metadata")
    usage = TokenUsage(
        input_tokens=_required_token_count(metadata, "total_input_tokens"),
        output_tokens=_required_token_count(metadata, "total_output_tokens"),
        thinking_tokens=_required_token_count(metadata, "total_thought_tokens"),
        total_tokens=_required_token_count(metadata, "total_tokens"),
    )
    interaction_id = getattr(interaction, "id", None)
    return ModelResult(
        raw_text=output_text,
        usage=usage,
        interaction_id=interaction_id
        if isinstance(interaction_id, str) and interaction_id
        else None,
        request_duration_seconds=duration,
    )
