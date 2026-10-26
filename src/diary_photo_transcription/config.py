from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from importlib.metadata import version
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from diary_photo_transcription.prompts import EXTRACTION_PROMPT


class LocalConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    context: str = ""
    default_corpus_year: int | None = Field(default=None, ge=1, le=9999)
    vault_dir: str | None = Field(default=None, min_length=1)


def load_project_config(path: Path | None = None, **kwargs: Any) -> ProjectConfig:
    """Load ignored local settings; an empty environment override disables discovery."""
    explicit = path is not None
    if path is None:
        override = os.environ.get("TAGEBUCH_CONFIG")
        if override == "":
            return ProjectConfig(**kwargs)
        explicit = override is not None
        path = Path(override) if override is not None else Path("private/local-config.json")
    if not explicit and not path.exists():
        return ProjectConfig(**kwargs)
    try:
        local = LocalConfig.model_validate(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        raise ValueError("Invalid local configuration (check JSON, keys and value types)") from None
    return ProjectConfig(local=local, **kwargs)


ThinkingLevel = Literal["low", "medium", "high"]
MediaResolution = Literal["high", "ultra_high"]
Provider = Literal["gemini", "openai", "claude-cli"]
MODELS: dict[str, Provider] = {
    "gemini-3.8-flash": "gemini",
    "gpt-6.1-terra": "openai",
    "claude-sonnet-5-5": "claude-cli",
}
DEFAULT_MODEL = "gemini-3.8-flash"


@dataclass(frozen=True, slots=True)
class ProjectConfig:
    """Project configuration."""

    local: LocalConfig = field(default_factory=LocalConfig)
    model: str = DEFAULT_MODEL
    thinking_level: ThinkingLevel | None = None
    media_resolution: MediaResolution = "high"

    @property
    def provider(self) -> Provider:
        if self.model not in MODELS:
            raise ValueError(f"Unsupported model {self.model!r}; choose one of {', '.join(MODELS)}")
        return MODELS[self.model]

    @property
    def sdk_version(self) -> str:
        if self.provider == "claude-cli":
            from diary_photo_transcription.claude_cli import cli_version

            return cli_version()
        return version("openai" if self.provider == "openai" else "google-genai")

    @property
    def effective_prompt(self) -> str:
        year = self.local.default_corpus_year
        suffix = f"\nKonfiguriertes Korpusjahr: {year}." if year is not None else ""
        if self.local.context:
            suffix += (
                "\nLokales Vokabular (nur Lesehilfe, niemals als Bildbeleg):\n" + self.local.context
            )
        return EXTRACTION_PROMPT + suffix
