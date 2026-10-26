import base64
import json
from datetime import UTC, datetime
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import httpx
import pytest
from google import genai
from google.genai import types
from google.genai.interactions import Error, Interaction, Usage
from PIL import Image

from diary_photo_transcription import gemini
from diary_photo_transcription.gemini import (
    build_interaction_input,
    build_response_format,
    estimate_standard_cost_usd,
    request_observation,
)
from diary_photo_transcription.provider import PhotoSnapshot, TokenUsage

_USAGE = Usage(
    total_input_tokens=100, total_output_tokens=20, total_thought_tokens=30, total_tokens=150
)


def _photo(tmp_path: Path) -> PhotoSnapshot:
    path = tmp_path / "photo.jpg"
    Image.new("RGB", (8, 8)).save(path)
    return PhotoSnapshot.capture(path)


def jpeg(path: Path) -> Path:
    exif = Image.Exif()
    exif[274] = 6
    exif[315] = "private author"
    Image.new("RGB", (12, 8), "red").save(path, exif=exif)
    return path


def _interaction(**changes: Any) -> Interaction:
    interaction = Interaction.model_validate(
        {
            "id": "interaction-123",
            "status": "completed",
            "steps": [
                {
                    "type": "model_output",
                    "content": [{"type": "text", "text": '{"schemaVersion":2}'}],
                }
            ],
            "usage": _USAGE,
        }
    )
    # Deliberately bypass validation for malformed SDK responses such as missing status.
    return interaction.model_copy(update=changes)


class _Recording:
    def __init__(self, interaction: Interaction) -> None:
        self.interaction = interaction
        self.kwargs: dict[str, Any] = {}

    def create(self, **kwargs: Any) -> Interaction:
        self.kwargs = kwargs
        return self.interaction


def _request(tmp_path: Path, interaction: Interaction, **kwargs: Any) -> Any:
    recording = _Recording(interaction)
    client = cast(genai.Client, SimpleNamespace(interactions=recording))
    result = request_observation(
        client, model="test-model", photo=_photo(tmp_path), prompt="PROMPT", **kwargs
    )
    return result, recording.kwargs


def test_client_leaves_retries_to_the_sdk(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(gemini, "load_dotenv", lambda: None)
    monkeypatch.setenv("GEMINI_API_KEY", "explicit")
    monkeypatch.setattr(gemini.genai, "Client", lambda **kwargs: kwargs)
    options = cast(dict[str, Any], gemini.create_client())["http_options"]
    assert options.timeout == gemini.REQUEST_TIMEOUT_MS
    assert options.retry_options.attempts == gemini.SDK_RETRIES


def test_sdk_transport_preserves_request_contract_and_retries(tmp_path: Path) -> None:
    requests: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) < 3:
            return httpx.Response(503, json={"error": {"message": "synthetic unavailable"}})
        return httpx.Response(200, json=_interaction().model_dump(mode="json"))

    with (
        httpx.Client(transport=httpx.MockTransport(respond)) as transport,
        genai.Client(
            api_key="placeholder",
            vertexai=False,
            http_options=types.HttpOptions(
                httpx_client=transport,
                timeout=gemini.REQUEST_TIMEOUT_MS,
                retry_options=types.HttpRetryOptions(
                    attempts=gemini.SDK_RETRIES, initial_delay=0.001, max_delay=0.002
                ),
            ),
        ) as client,
    ):
        result = request_observation(
            client,
            model="gemini-3.8-flash",
            photo=_photo(tmp_path),
            prompt="Synthetic prompt",
            thinking_level="low",
        )

    assert len(requests) == 3
    request = requests[-1]
    body = json.loads(request.content)
    assert body["store"] is False and body["stream"] is False
    assert body["response_format"] == build_response_format()
    assert body["generation_config"] == {"thinking_level": "low"}
    content = body["input"][0]["content"]
    assert content[0] == {"type": "text", "text": "Synthetic prompt"}
    assert content[1]["mime_type"] == "image/jpeg"
    assert content[1]["resolution"] == "high"
    with Image.open(BytesIO(base64.b64decode(content[1]["data"]))) as image:
        assert image.size == (8, 8)
    assert request.extensions["timeout"]["read"] == 300.0
    assert result.raw_text == '{"schemaVersion":2}'
    assert result.usage == TokenUsage(100, 20, 30, 150)


def test_interaction_input_is_text_first_inline_jpeg(tmp_path: Path) -> None:
    photo = _photo(tmp_path)
    content = build_interaction_input(photo, prompt="P", media_resolution="ultra_high")
    assert content[0] == {"type": "text", "text": "P"}
    assert content[1]["mime_type"] == "image/jpeg"
    assert content[1]["resolution"] == "ultra_high"
    assert build_response_format()["schema"]


def test_request_is_stateless_structured_and_maps_usage(tmp_path: Path) -> None:
    result, sent = _request(
        tmp_path, _interaction(), thinking_level="low", media_resolution="ultra_high"
    )
    assert sent["model"] == "test-model"
    assert sent["store"] is False
    assert sent["stream"] is False
    assert sent["response_format"] == build_response_format()
    assert sent["generation_config"] == {"thinking_level": "low"}
    assert sent["input"][0]["text"] == "PROMPT"
    assert result.raw_text == '{"schemaVersion":2}'
    assert result.interaction_id == "interaction-123"
    assert result.usage == TokenUsage(100, 20, 30, 150)


def test_default_thinking_level_is_not_sent(tmp_path: Path) -> None:
    _, sent = _request(tmp_path, _interaction())
    assert "generation_config" not in sent


@pytest.mark.parametrize(
    "changes, message",
    [
        ({"status": None}, "status"),
        ({"status": "incomplete"}, "status"),
        ({"errors": [Error(code="blocked", message="No result")]}, "blocked: No result"),
        ({"output_text": " "}, "response text"),
        ({"usage": None}, "usage"),
        ({"usage": Usage(total_input_tokens=1)}, "usage field"),
    ],
)
def test_unusable_response_fails_after_its_evidence_is_saved(
    tmp_path: Path, changes: dict[str, Any], message: str
) -> None:
    interaction = _interaction(provider_metadata={"trace": "synthetic evidence"}, **changes)
    evidence: list[dict[str, Any]] = []
    with pytest.raises(ValueError, match=message):
        _request(tmp_path, interaction, on_interaction=evidence.append)
    [saved] = evidence
    usage = interaction.usage
    assert saved["interaction"].get("usage") == (
        None if usage is None else usage.model_dump(mode="json")
    )
    assert saved["interaction"]["output_text"] == interaction.output_text
    assert saved["interaction"]["steps"][0]["content"][0]["text"] == '{"schemaVersion":2}'
    assert saved["interaction"]["provider_metadata"] == {"trace": "synthetic evidence"}


@pytest.mark.parametrize(
    "timestamp, expected",
    [
        ("2026-12-31T23:59:59+00:00", "1.50"),
        ("2027-01-01T00:00:00+00:00", "3.00"),
    ],
)
def test_standard_cost_uses_current_utc_rates_and_includes_thinking(
    monkeypatch: pytest.MonkeyPatch, timestamp: str, expected: str
) -> None:
    class Clock:
        @staticmethod
        def now(tz):
            assert tz is UTC
            return datetime.fromisoformat(timestamp)

    monkeypatch.setattr(gemini, "datetime", Clock)
    usage = TokenUsage(1_000_000, 100_000, 100_000, 1_200_000)
    assert estimate_standard_cost_usd(usage) == Decimal(expected)


def test_snapshot_survives_source_replacement_and_strips_metadata(tmp_path: Path) -> None:
    path = jpeg(tmp_path / "photo.jpg")
    snapshot = PhotoSnapshot.capture(path)
    path.write_bytes(b"not an image")
    payload = cast(str, gemini.build_interaction_input(snapshot)[1]["data"])
    with Image.open(BytesIO(base64.b64decode(payload))) as image:
        assert image.size == (8, 12)
        assert not image.getexif()


@pytest.mark.parametrize("orientation", [None, 1, 6])
def test_all_jpegs_strip_metadata(tmp_path: Path, orientation: int | None) -> None:
    path = tmp_path / "photo.jpg"
    exif = Image.Exif()
    exif[315] = "private author"
    if orientation is not None:
        exif[274] = orientation
    Image.new("RGB", (12, 8)).save(path, exif=exif)
    payload = cast(str, gemini.build_interaction_input(PhotoSnapshot.capture(path))[1]["data"])
    with Image.open(BytesIO(base64.b64decode(payload))) as image:
        assert not image.getexif()


def test_invalid_image_fails_locally(tmp_path: Path) -> None:
    path = tmp_path / "bad.jpg"
    path.write_bytes(b"bad")
    with pytest.raises(ValueError, match="JPEG"):
        gemini.build_interaction_input(PhotoSnapshot.capture(path))


@pytest.mark.parametrize("debug", ["1", "0"])
def test_debug_rejected(monkeypatch: pytest.MonkeyPatch, debug: str) -> None:
    monkeypatch.setattr(gemini, "load_dotenv", lambda: None)
    monkeypatch.setenv("GEMINI_API_KEY", "explicit")
    monkeypatch.setenv("GOOGLE_GENAI_DEBUG", debug)
    with pytest.raises(ValueError, match="GOOGLE_GENAI_DEBUG"):
        gemini.create_client()


def test_explicit_key_and_conflict(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(gemini, "load_dotenv", lambda: None)
    monkeypatch.delenv("GOOGLE_GENAI_DEBUG", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    with pytest.raises(ValueError, match="GEMINI_API_KEY"):
        gemini.create_client()
    monkeypatch.setenv("GEMINI_API_KEY", "explicit")
    monkeypatch.setenv("GOOGLE_API_KEY", "different")
    with pytest.raises(ValueError, match="GOOGLE_API_KEY"):
        gemini.create_client()
    monkeypatch.setenv("GOOGLE_API_KEY", "explicit")
    monkeypatch.setattr(gemini.genai, "Client", lambda **kw: kw)
    assert (
        cast(dict[str, object], gemini.create_client())["api_key"]
        == gemini.os.environ["GEMINI_API_KEY"]
    )
