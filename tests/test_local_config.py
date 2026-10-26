import json
from pathlib import Path

import pytest

from diary_photo_transcription.config import load_project_config
from diary_photo_transcription.provenance import config_fingerprint


def test_local_config_changes_prompt_and_fingerprint(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"context": "Fictional: Alex", "default_corpus_year": 2040}))
    config = load_project_config(path)
    assert "Fictional: Alex" in config.effective_prompt
    assert "2040" in config.effective_prompt
    path.write_text("{}")
    assert config_fingerprint(config) != config_fingerprint(load_project_config(path))


@pytest.mark.parametrize(
    "text",
    [
        "{",
        '{"unknown": 1}',
        '{"default_corpus_year": true}',
        '{"context": 42}',
        '{"vault_dir": ""}',
    ],
)
def test_explicit_malformed_config_fails_without_echoing_values(tmp_path: Path, text: str) -> None:
    path = tmp_path / "config.json"
    path.write_text(text)
    with pytest.raises(ValueError, match="Invalid local configuration"):
        load_project_config(path)


def test_explicit_missing_config_fails(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Invalid local configuration"):
        load_project_config(tmp_path / "missing.json")
