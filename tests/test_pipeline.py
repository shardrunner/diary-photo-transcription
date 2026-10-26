"""Paid-work orchestration, fully offline via the FakeGemini fixture."""

import json
from concurrent.futures import CancelledError
from pathlib import Path
from threading import Event
from unittest.mock import Mock

import pytest

from diary_photo_transcription.config import ProjectConfig
from diary_photo_transcription.pipeline import extract_photo, refine_run
from diary_photo_transcription.provenance import sha256
from diary_photo_transcription.runs import (
    active_dir,
    decide_revision,
    discover_runs,
    pending_revisions,
    read_meta,
)


@pytest.fixture
def photo(tmp_path: Path, make_photo) -> Path:
    return make_photo(tmp_path / "source" / "photo.jpg")


def test_extraction_publishes_one_complete_run(tmp_path, photo, fake_gemini):
    output = tmp_path / "output"
    result = extract_photo(photo, ProjectConfig(), output)

    assert discover_runs(output) == [result.run_dir]
    assert {p.name for p in result.run_dir.iterdir()} == {
        "interaction.json",
        "raw.json",
        "run.json",
        "prompt.txt",
        "review.json",
        "2040-01-02.md",
    }
    meta = read_meta(result.run_dir)
    assert meta["provenance"]["photoSha256"] == sha256(photo)
    assert meta["rawSha256"] == sha256(result.run_dir / "raw.json")
    assert meta["usage"]["totalTokens"] == 150
    assert meta["provenance"]["schemaVersion"] == result.observation.schema_version == 2
    assert not [p for p in output.iterdir() if p.name.startswith(".")]


def test_existing_run_is_skipped_without_request(tmp_path, photo, fake_gemini):
    first = extract_photo(photo, ProjectConfig(), tmp_path / "output")
    again = extract_photo(photo, ProjectConfig(), tmp_path / "output")

    assert again.skipped
    assert again.run_dir == first.run_dir
    assert len(fake_gemini.prompts) == 1


def test_force_and_changed_settings_create_separate_runs(tmp_path, photo, fake_gemini):
    output = tmp_path / "output"
    first = extract_photo(photo, ProjectConfig(), output)
    forced = extract_photo(photo, ProjectConfig(), output, force=True)
    thinking = extract_photo(photo, ProjectConfig(thinking_level="low"), output)

    assert len({first.run_dir, forced.run_dir, thinking.run_dir}) == 3
    assert forced.run_dir.name.startswith(f"{first.run_dir.name}-rerun-")
    assert len(fake_gemini.prompts) == 3


@pytest.mark.parametrize("unsupported_version", [False, True])
def test_invalid_response_keeps_evidence_but_publishes_nothing(
    tmp_path, photo, fake_gemini, unsupported_version
):
    output = tmp_path / "output"
    fake_gemini.raw_text = (
        json.dumps({**json.loads(fake_gemini.raw_text), "schemaVersion": 3})
        if unsupported_version
        else '{"schemaVersion": 2}'
    )

    with pytest.raises(ValueError) as raised:
        extract_photo(photo, ProjectConfig(), output)

    assert discover_runs(output) == []
    [failed] = output.iterdir()
    assert failed.name.startswith(".failed-")
    assert json.loads((failed / "interaction.json").read_text())["interaction"]
    assert str(failed) in "".join(raised.value.__notes__)

    fake_gemini.raw_text = fake_gemini.clean_raw()
    assert not extract_photo(photo, ProjectConfig(), output).skipped


def test_transport_failure_leaves_no_directory(tmp_path, photo, fake_gemini, monkeypatch):
    output = tmp_path / "output"
    monkeypatch.setattr(
        "diary_photo_transcription.gemini.request_observation",
        Mock(side_effect=RuntimeError("HTTP 503")),
    )
    with pytest.raises(RuntimeError):
        extract_photo(photo, ProjectConfig(), output)
    assert list(output.iterdir()) == []


def test_cancelled_extraction_sends_nothing(tmp_path, photo, fake_gemini):
    cancel = Event()
    cancel.set()
    with pytest.raises(CancelledError):
        extract_photo(photo, ProjectConfig(), tmp_path / "output", cancel_event=cancel)
    assert fake_gemini.prompts == []


def test_refinement_waits_for_approval(tmp_path, photo, fake_gemini):
    run = extract_photo(photo, ProjectConfig(), tmp_path / "output").run_dir
    fake_gemini.raw_text = fake_gemini.clean_raw()

    revision = refine_run(run, photo.parent)

    assert revision is not None
    assert "Morgen folgt ein ⟦unleserlich⟧" in fake_gemini.prompts[-1]
    assert "ohne Beleg im Datum-Feld" in fake_gemini.prompts[-1]
    assert read_meta(revision.run_dir)["parentRawSha256"] == sha256(run / "raw.json")
    assert active_dir(run) == run
    assert pending_revisions(run) == [revision.run_dir.name]
    with pytest.raises(ValueError, match="undecided revision"):
        refine_run(run, photo.parent)

    decide_revision(run, revision.run_dir.name, approve=True)
    assert active_dir(run) == revision.run_dir
    assert refine_run(run, photo.parent) is None
    assert len(fake_gemini.prompts) == 2


def test_refinement_reuses_the_run_request_settings(tmp_path, photo, fake_gemini):
    config = ProjectConfig(thinking_level="low", media_resolution="ultra_high")
    run = extract_photo(photo, config, tmp_path / "output").run_dir
    revision = refine_run(run, photo.parent)
    assert revision is not None
    usage = read_meta(revision.run_dir)["usage"]
    assert (usage["thinkingLevel"], usage["mediaResolution"]) == ("low", "ultra_high")


def test_refinement_finds_moved_photo_by_content(tmp_path, photo, fake_gemini):
    run = extract_photo(photo, ProjectConfig(), tmp_path / "output").run_dir
    moved = photo.rename(photo.with_name("renamed.JPG"))
    assert refine_run(run, moved.parent) is not None


def test_refinement_without_source_photo_fails(tmp_path, photo, fake_gemini, make_photo):
    run = extract_photo(photo, ProjectConfig(), tmp_path / "output").run_dir
    make_photo(photo, color=(200, 0, 0))
    with pytest.raises(FileNotFoundError):
        refine_run(run, photo.parent)
    assert len(fake_gemini.prompts) == 1
