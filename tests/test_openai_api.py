import base64
from decimal import Decimal
from importlib.metadata import version
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from openai.types.responses import Response
from PIL import Image

from diary_photo_transcription import openai_api
from diary_photo_transcription.config import ProjectConfig
from diary_photo_transcription.openai_api import (
    estimate_standard_cost_usd,
    request_observation,
    strict_json_schema,
)
from diary_photo_transcription.provider import PhotoSnapshot, TokenUsage

_USAGE = {
    "input_tokens": 100,
    "input_tokens_details": {"cached_tokens": 0, "cache_write_tokens": 0},
    "output_tokens": 50,
    "output_tokens_details": {"reasoning_tokens": 30},
    "total_tokens": 150,
}


def _response(**changes: Any) -> Response:
    response = Response.model_validate(
        {
            "id": "resp-123",
            "object": "response",
            "created_at": 0,
            "model": "gpt-6.1-terra",
            "status": "completed",
            "output": [
                {
                    "type": "message",
                    "id": "msg-1",
                    "role": "assistant",
                    "status": "completed",
                    "content": [
                        {"type": "output_text", "text": '{"schemaVersion":2}', "annotations": []}
                    ],
                }
            ],
            "parallel_tool_calls": False,
            "tool_choice": "auto",
            "tools": [],
            "usage": _USAGE,
        }
    )
    # Deliberately bypass validation for malformed responses such as missing usage.
    return response.model_copy(update=changes)


def _request(tmp_path: Path, response: Response, **kwargs: Any) -> tuple[Any, dict[str, Any]]:
    path = tmp_path / "photo.jpg"
    Image.new("RGB", (8, 8)).save(path)
    sent: dict[str, Any] = {}

    def create(**request: Any) -> Response:
        sent.update(request)
        return response

    client = SimpleNamespace(responses=SimpleNamespace(create=create))
    result = request_observation(
        client,
        model="gpt-6.1-terra",
        photo=PhotoSnapshot.capture(path),
        prompt="PROMPT",
        **kwargs,
    )
    return result, sent


def test_request_is_stateless_strict_structured_and_maps_usage(tmp_path: Path) -> None:
    result, sent = _request(tmp_path, _response(), thinking_level="high")
    assert sent["model"] == "gpt-6.1-terra"
    assert sent["store"] is False
    assert sent["reasoning"] == {"effort": "high"}
    assert sent["text"]["format"] == {
        "type": "json_schema",
        "name": "photo_observation",
        "schema": strict_json_schema(),
        "strict": True,
    }
    [message] = sent["input"]
    text, image = message["content"]
    assert text == {"type": "input_text", "text": "PROMPT"}
    assert image["type"] == "input_image" and image["detail"] == "high"
    prefix = "data:image/jpeg;base64,"
    assert image["image_url"].startswith(prefix)
    with Image.open(BytesIO(base64.b64decode(image["image_url"][len(prefix) :]))) as decoded:
        assert decoded.size == (8, 8)
    assert result.raw_text == '{"schemaVersion":2}'
    assert result.interaction_id == "resp-123"
    # Reasoning tokens are part of OpenAI's output count; keep them separate like Gemini.
    assert result.usage == TokenUsage(100, 20, 30, 150)


def test_default_reasoning_is_not_sent_and_ultra_high_means_original(tmp_path: Path) -> None:
    _, sent = _request(tmp_path, _response(), media_resolution="ultra_high")
    assert "reasoning" not in sent
    assert sent["input"][0]["content"][1]["detail"] == "original"


@pytest.mark.parametrize(
    "changes, message",
    [
        ({"status": "incomplete"}, "status"),
        ({"output": []}, "response text"),
        ({"usage": None}, "usage"),
    ],
)
def test_unusable_response_fails_after_its_evidence_is_saved(
    tmp_path: Path, changes: dict[str, Any], message: str
) -> None:
    evidence: list[dict[str, Any]] = []
    with pytest.raises(ValueError, match=message):
        _request(tmp_path, _response(**changes), on_interaction=evidence.append)
    [saved] = evidence
    assert saved["interaction"]["id"] == "resp-123"
    assert saved["model"] == "gpt-6.1-terra"


def test_strict_schema_requires_every_property_and_has_no_defaults() -> None:
    def visit(node: Any) -> None:
        if isinstance(node, dict):
            assert "default" not in node
            if "properties" in node:
                assert node["additionalProperties"] is False
                assert sorted(node["required"]) == sorted(node["properties"])
            for value in node.values():
                visit(value)
        elif isinstance(node, list):
            for value in node:
                visit(value)

    visit(strict_json_schema())


def test_standard_cost_includes_reasoning() -> None:
    usage = TokenUsage(1_000_000, 100_000, 100_000, 1_200_000)
    assert estimate_standard_cost_usd(usage) == Decimal("2.00")


def test_client_requires_openai_key(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(ValueError, match="OPENAI_API_KEY"):
        openai_api.create_client()
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-key")
    monkeypatch.setattr(openai_api, "OpenAI", lambda **kwargs: kwargs)
    client: Any = openai_api.create_client()
    assert client["api_key"] == "synthetic-key"
    assert client["timeout"] == openai_api.REQUEST_TIMEOUT_SECONDS
    assert client["max_retries"] == openai_api.SDK_RETRIES


def test_model_selects_provider_and_sdk_version() -> None:
    assert ProjectConfig().provider == "gemini"
    assert ProjectConfig().sdk_version == version("google-genai")
    terra = ProjectConfig(model="gpt-6.1-terra")
    assert terra.provider == "openai"
    assert terra.sdk_version == version("openai")
