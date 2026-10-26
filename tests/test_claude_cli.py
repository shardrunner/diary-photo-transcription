import json
import subprocess
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from PIL import Image

from diary_photo_transcription import claude_cli
from diary_photo_transcription.config import ProjectConfig
from diary_photo_transcription.provider import PhotoSnapshot, TokenUsage

_RESULT = {
    "type": "result",
    "subtype": "success",
    "is_error": False,
    "session_id": "session-123",
    "total_cost_usd": 0.0204,
    "structured_output": {"schemaVersion": 2},
    "usage": {
        "input_tokens": 4,
        "cache_creation_input_tokens": 60,
        "cache_read_input_tokens": 36,
        "output_tokens": 50,
        "output_tokens_details": {"thinking_tokens": 30},
    },
}


def _request(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, result: dict[str, Any], **kwargs: Any
) -> tuple[Any, dict[str, Any]]:
    path = tmp_path / "photo.jpg"
    Image.new("RGB", (8, 8)).save(path)
    seen: dict[str, Any] = {}

    def run(command: list[str], **options: Any) -> subprocess.CompletedProcess[str]:
        seen["command"] = command
        seen.update(options)
        seen["files"] = sorted(p.name for p in Path(options["cwd"]).iterdir())
        return subprocess.CompletedProcess(command, 0, json.dumps(result), "")

    monkeypatch.setattr(claude_cli.subprocess, "run", run)
    response = claude_cli.request_observation(
        "claude",
        model="claude-sonnet-5-5",
        photo=PhotoSnapshot.capture(path),
        prompt="PROMPT",
        **kwargs,
    )
    return response, seen


def _flag(command: list[str], name: str) -> str:
    return command[command.index(name) + 1]


def test_request_runs_read_only_print_mode_with_schema(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    evidence: list[dict[str, Any]] = []
    result, seen = _request(
        tmp_path, monkeypatch, _RESULT, thinking_level="medium", on_interaction=evidence.append
    )
    command = seen["command"]
    assert command[:2] == ["claude", "-p"]
    assert _flag(command, "-p").startswith("PROMPT")
    assert _flag(command, "--model") == "claude-sonnet-5-5"
    assert _flag(command, "--effort") == "medium"
    assert _flag(command, "--tools") == _flag(command, "--allowedTools") == "Read"
    assert _flag(command, "--output-format") == "json"
    assert _flag(command, "--setting-sources") == ""
    assert "--no-session-persistence" in command
    assert json.loads(_flag(command, "--json-schema")) == claude_cli.model_response_json_schema()
    # Only the prepared photo is visible to the agent.
    assert seen["files"] == ["photo.jpg"]
    assert seen["timeout"] == claude_cli.REQUEST_TIMEOUT_SECONDS
    assert json.loads(result.raw_text) == {"schemaVersion": 2}
    assert result.interaction_id == "session-123"
    assert result.usage == TokenUsage(100, 20, 30, 150)
    assert result.cost_usd == Decimal("0.0204")
    assert evidence[0]["interaction"]["session_id"] == "session-123"


def test_default_effort_is_not_sent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _, seen = _request(tmp_path, monkeypatch, _RESULT)
    assert "--effort" not in seen["command"]


def test_ultra_high_resolution_is_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(ValueError, match="resolution"):
        _request(tmp_path, monkeypatch, _RESULT, media_resolution="ultra_high")


@pytest.mark.parametrize(
    "changes, message",
    [
        ({"is_error": True, "subtype": "error_max_turns"}, "error_max_turns"),
        ({"structured_output": None}, "structured output"),
        ({"usage": None}, "usage"),
    ],
)
def test_unusable_result_fails_after_its_evidence_is_saved(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, changes: dict[str, Any], message: str
) -> None:
    evidence: list[dict[str, Any]] = []
    with pytest.raises(ValueError, match=message):
        _request(tmp_path, monkeypatch, {**_RESULT, **changes}, on_interaction=evidence.append)
    assert evidence[0]["interaction"]["session_id"] == "session-123"


def test_model_selects_claude_cli_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    config = ProjectConfig(model="claude-sonnet-5-5")
    assert config.provider == "claude-cli"
    monkeypatch.setattr(claude_cli.shutil, "which", lambda name: None)
    with pytest.raises(ValueError, match="claude"):
        claude_cli.create_client()
