"""Claude adapter via the local Claude Code CLI in print mode (`claude -p`).

Used for model comparison. The CLI is an agent harness, not a bare model call:
the photo is read through its Read tool (which decides the image resolution)
and the reported cost includes the harness's own prompt tokens.
"""

from __future__ import annotations

import functools
import json
import shutil
import subprocess
import tempfile
import time
from collections.abc import Callable
from decimal import Decimal
from pathlib import Path
from typing import Any

from diary_photo_transcription.config import MediaResolution
from diary_photo_transcription.provider import ModelResult, PhotoSnapshot, TokenUsage
from diary_photo_transcription.schemas import model_response_json_schema

# Whole agent session including tool turns, matching the other adapters' budget.
REQUEST_TIMEOUT_SECONDS = 300
_SYSTEM_PROMPT = (
    "Du bist eine Transkriptions-Engine. Lies das Foto mit dem Read-Tool und "
    "antworte ausschließlich mit der geforderten strukturierten Ausgabe."
)
_PHOTO_NAME = "photo.jpg"


@functools.cache
def cli_version() -> str:
    completed = subprocess.run(
        ["claude", "--version"], capture_output=True, text=True, check=True, timeout=30
    )
    return completed.stdout.strip()


def create_client() -> str:
    """Return the CLI path; authentication is the CLI's own login or API key."""
    path = shutil.which("claude")
    if path is None:
        raise ValueError("The claude CLI is required for Claude models")
    return path


def request_observation(
    client: str,
    *,
    model: str,
    photo: PhotoSnapshot,
    prompt: str,
    thinking_level: str | None = None,
    media_resolution: MediaResolution = "high",
    on_interaction: Callable[[dict[str, Any]], object] | None = None,
) -> ModelResult:
    """Run one isolated print-mode session that may only read the prepared photo."""
    if media_resolution != "high":
        raise ValueError("The claude CLI has no image resolution setting; use high")
    command = [
        client,
        "-p",
        f"{prompt}\n\nDas Foto liegt unter ./{_PHOTO_NAME}.",
        "--model",
        model,
        "--system-prompt",
        _SYSTEM_PROMPT,
        "--tools",
        "Read",
        "--allowedTools",
        "Read",
        "--output-format",
        "json",
        "--json-schema",
        json.dumps(model_response_json_schema(), ensure_ascii=False),
        "--setting-sources",
        "",
        "--no-session-persistence",
    ]
    if thinking_level is not None:
        command += ["--effort", thinking_level]

    with tempfile.TemporaryDirectory(prefix="diary-claude-") as workdir:
        (Path(workdir) / _PHOTO_NAME).write_bytes(photo.upload_bytes)
        started = time.monotonic()
        completed = subprocess.run(
            command,
            cwd=workdir,
            capture_output=True,
            text=True,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        duration = time.monotonic() - started
    if completed.returncode != 0 and not completed.stdout.strip():
        raise ValueError(f"claude CLI failed ({completed.returncode}): {completed.stderr.strip()}")
    result: dict[str, Any] = json.loads(completed.stdout)

    if on_interaction is not None:
        on_interaction(
            {
                "interaction": result,
                "requestDurationSeconds": duration,
                "model": model,
                "mediaResolution": media_resolution,
                "thinkingLevel": thinking_level,
            }
        )

    if result.get("is_error") or result.get("subtype") != "success":
        raise ValueError(f"claude CLI reported an error: {result.get('subtype')}")
    output = result.get("structured_output")
    if not isinstance(output, dict):
        raise ValueError("claude CLI returned no structured output")
    usage = result.get("usage")
    if not isinstance(usage, dict):
        raise ValueError("claude CLI returned no usage metadata")
    input_tokens = (
        usage["input_tokens"]
        + usage["cache_creation_input_tokens"]
        + usage["cache_read_input_tokens"]
    )
    thinking = usage["output_tokens_details"]["thinking_tokens"]
    return ModelResult(
        raw_text=json.dumps(output, ensure_ascii=False),
        usage=TokenUsage(
            input_tokens=input_tokens,
            output_tokens=usage["output_tokens"] - thinking,
            thinking_tokens=thinking,
            total_tokens=input_tokens + usage["output_tokens"],
        ),
        interaction_id=result.get("session_id"),
        request_duration_seconds=duration,
        cost_usd=Decimal(str(result["total_cost_usd"])),
    )
