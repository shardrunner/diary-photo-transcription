"""Local run storage: discovery, refinement decisions and canonical days."""

from pathlib import Path

import pytest

from diary_photo_transcription.config import ProjectConfig
from diary_photo_transcription.pipeline import extract_photo, refine_run
from diary_photo_transcription.runs import (
    active_dir,
    clear_selection,
    decide_revision,
    discover_runs,
    resolve_days,
    select_day,
)


@pytest.fixture
def output(tmp_path: Path) -> Path:
    return tmp_path / "output"


@pytest.fixture
def new_run(output: Path, make_photo, fake_gemini):
    def create(name: str, color: tuple[int, int, int]) -> Path:
        photo = make_photo(output.parent / "source" / f"{name}.jpg", color)
        return extract_photo(photo, ProjectConfig(), output).run_dir

    return create


def _revision(run: Path, fake_gemini, raw: str) -> str:
    fake_gemini.raw_text = raw
    result = refine_run(run, run.parent.parent / "source")
    assert result is not None
    return result.run_dir.name


def test_discovery_ignores_hidden_and_rejects_foreign_directories(output, fake_gemini, new_run):
    run = new_run("a", (1, 1, 1))
    (output / ".failed-x").mkdir()
    assert discover_runs(output) == [run]
    (output / "poc").mkdir()
    with pytest.raises(ValueError, match="poc"):
        discover_runs(output)


def test_rejected_revision_never_becomes_active(output, fake_gemini, new_run):
    run = new_run("a", (1, 1, 1))
    revision = _revision(run, fake_gemini, fake_gemini.clean_raw())
    decide_revision(run, revision, approve=False)
    assert active_dir(run) == run
    with pytest.raises(ValueError, match="already rejected"):
        decide_revision(run, revision, approve=True)
    with pytest.raises(ValueError, match="Unknown revision"):
        decide_revision(run, "0" * 32, approve=True)


def test_approval_requires_the_revision_parent_to_be_active(output, fake_gemini, new_run):
    # Normal use cannot produce this: refinement refuses to run while a revision is open.
    run = new_run("a", (1, 1, 1))
    revision = _revision(run, fake_gemini, fake_gemini.clean_raw())
    meta = run / "revisions" / revision / "run.json"
    meta.write_text(meta.read_text().replace('"parentRawSha256": "', '"parentRawSha256": "0'))
    with pytest.raises(ValueError, match="no longer active parent"):
        decide_revision(run, revision, approve=True)


def test_single_candidate_per_date_needs_no_selection(output, fake_gemini, new_run):
    run = new_run("a", (1, 1, 1))
    assert resolve_days(output) == {"2040-01-02": run / "2040-01-02.md"}
    assert resolve_days(output, "2040-01-03") == {}


def test_competing_runs_require_an_explicit_selection(output, fake_gemini, new_run):
    first = new_run("a", (1, 1, 1))
    second = new_run("b", (200, 0, 0))
    with pytest.raises(ValueError, match="Ambiguous date 2040-01-02"):
        resolve_days(output)

    select_day(output, "2040-01-02", second.name)
    assert resolve_days(output) == {"2040-01-02": second / "2040-01-02.md"}
    clear_selection(output, "2040-01-02")
    clear_selection(output, "2040-01-02")
    with pytest.raises(ValueError, match="Ambiguous"):
        resolve_days(output)
    assert first != second


def test_selection_follows_the_approved_revision(output, fake_gemini, new_run):
    run = new_run("a", (1, 1, 1))
    select_day(output, "2040-01-02", run.name)
    revision = _revision(run, fake_gemini, fake_gemini.clean_raw())
    decide_revision(run, revision, approve=True)
    assert resolve_days(output) == {"2040-01-02": active_dir(run) / "2040-01-02.md"}


def test_selection_whose_date_vanished_fails_until_cleared(output, fake_gemini, new_run):
    run = new_run("a", (1, 1, 1))
    select_day(output, "2040-01-02", run.name)
    moved = fake_gemini.clean_raw().replace("2040-01-02", "2040-01-03")
    revision = _revision(run, fake_gemini, moved)
    decide_revision(run, revision, approve=True)
    with pytest.raises(ValueError, match="has no active note for 2040-01-02"):
        resolve_days(output)
    assert resolve_days(output, "2040-01-03") == {"2040-01-03": active_dir(run) / "2040-01-03.md"}
    clear_selection(output, "2040-01-02")
    assert set(resolve_days(output)) == {"2040-01-03"}


def test_selection_rejects_unknown_runs_and_dates(output, fake_gemini, new_run):
    run = new_run("a", (1, 1, 1))
    with pytest.raises(ValueError, match="Unknown run"):
        select_day(output, "2040-01-02", "missing")
    with pytest.raises(ValueError, match="Unknown run"):
        select_day(output, "2040-01-02", f"../{run.name}")
    with pytest.raises(ValueError, match="no active note"):
        select_day(output, "2040-01-05", run.name)
    assert not (output / "missing").exists()
