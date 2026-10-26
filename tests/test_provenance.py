from __future__ import annotations

import pytest

from diary_photo_transcription.config import LocalConfig, ProjectConfig
from diary_photo_transcription.prompts import EXTRACTION_PROMPT, PROMPT_VERSION
from diary_photo_transcription.provenance import (
    config_fingerprint,
    extraction_run_id,
)


@pytest.mark.parametrize(
    "changed",
    [
        ProjectConfig(model="different-model"),
        ProjectConfig(thinking_level="low"),
        ProjectConfig(media_resolution="ultra_high"),
    ],
)
def test_output_relevant_settings_change_the_run_identity(changed: ProjectConfig) -> None:
    base = ProjectConfig()
    photo = "a" * 64
    assert config_fingerprint(base) == config_fingerprint(ProjectConfig())
    assert config_fingerprint(changed) != config_fingerprint(base)
    assert extraction_run_id(photo, changed) != extraction_run_id(photo, base)
    assert extraction_run_id("b" * 64, base) != extraction_run_id(photo, base)


def test_fingerprint_ignores_vault_destination_and_sdk_version(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    base = config_fingerprint(ProjectConfig())
    monkeypatch.setattr("diary_photo_transcription.config.version", lambda _: "synthetic-sdk")
    assert ProjectConfig().sdk_version == "synthetic-sdk"
    assert config_fingerprint(ProjectConfig()) == base
    assert config_fingerprint(ProjectConfig(local=LocalConfig(vault_dir="elsewhere"))) == base
    assert config_fingerprint(ProjectConfig(local=LocalConfig(context="vocabulary"))) != base
    assert config_fingerprint(ProjectConfig(local=LocalConfig(default_corpus_year=2025))) != base


def test_changed_prompt_changes_run_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    base = config_fingerprint(ProjectConfig())
    monkeypatch.setattr(
        "diary_photo_transcription.config.EXTRACTION_PROMPT",
        EXTRACTION_PROMPT + "\nSynthetic change.",
    )
    assert config_fingerprint(ProjectConfig()) != base


def test_absent_score_row_prompt() -> None:
    assert PROMPT_VERSION >= 10
    assert "nur einzelne Symbole" in EXTRACTION_PROMPT
    assert "scores=[]" in EXTRACTION_PROMPT
    assert 'state="empty" und rawValue=null' not in EXTRACTION_PROMPT
    assert "Habittrackerzahl als ganze Zahl" in EXTRACTION_PROMPT
    assert "./." in EXTRACTION_PROMPT
