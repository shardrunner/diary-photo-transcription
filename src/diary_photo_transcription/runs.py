"""Local run storage: publication, refinement decisions and canonical day selection.

A run directory is built under a dot-prefixed staging name and renamed into
place only after every artifact was written, so a visible run is always
complete. Failed attempts keep their evidence under `.failed-*` and are never
discovered. Refinements live in `RUN/revisions/ID/` and only count once
approved in `RUN/decisions.json`.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from diary_photo_transcription.atomic import atomic_write
from diary_photo_transcription.normalize import normalize_observation
from diary_photo_transcription.provenance import sha256
from diary_photo_transcription.render import render_markdown
from diary_photo_transcription.schemas import PhotoObservation, PhotoProvenance, ReviewIssue

META = "run.json"
DECISIONS = "decisions.json"
SELECTIONS = "selections.json"
_DATE_FILE = re.compile(r"\d{4}-\d{2}-\d{2}\.md")
_REVISION_ID = re.compile(r"[0-9a-f]{32}")


def _dump(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")


# --- artifacts -----------------------------------------------------------------


def write_artifacts(
    directory: Path, raw_text: str, meta: dict[str, Any], prompt: str
) -> PhotoObservation:
    """Validate the raw observation and write everything derived from it."""
    observation = PhotoObservation.model_validate_json(raw_text)
    result = normalize_observation(observation, PhotoProvenance.model_validate(meta["provenance"]))
    (directory / "raw.json").write_text(raw_text, encoding="utf-8")
    (directory / "prompt.txt").write_text(prompt, encoding="utf-8")
    (directory / META).write_bytes(_dump({**meta, "rawSha256": sha256(directory / "raw.json")}))
    issues = [issue.model_dump(mode="json", by_alias=True) for issue in result.review_issues]
    (directory / "review.json").write_bytes(_dump(issues))
    for day in result.days:
        (directory / f"{day.date.isoformat()}.md").write_bytes(render_markdown(day))
    return observation


def publish(staging: Path, final: Path) -> None:
    if final.exists():
        raise FileExistsError(f"Run already exists: {final}")
    staging.rename(final)


def keep_failed(staging: Path, error: BaseException) -> None:
    """Keep paid evidence of a failed attempt out of discovery, or drop an empty staging dir."""
    if not staging.exists():
        return
    if not any(staging.iterdir()):
        staging.rmdir()
        return
    failed = staging.with_name(".failed-" + staging.name.removeprefix(".staging-"))
    staging.rename(failed)
    error.add_note(f"Received response kept in {failed}")


def read_meta(directory: Path) -> dict[str, Any]:
    return json.loads((directory / META).read_text(encoding="utf-8"))


def read_observation(directory: Path) -> PhotoObservation:
    return PhotoObservation.model_validate_json((directory / "raw.json").read_text("utf-8"))


def read_issues(directory: Path) -> list[ReviewIssue]:
    data = json.loads((directory / "review.json").read_text(encoding="utf-8"))
    return [ReviewIssue.model_validate(issue) for issue in data]


def dated_notes(directory: Path) -> dict[str, Path]:
    return {
        path.stem: path
        for path in sorted(directory.glob("*.md"))
        if _DATE_FILE.fullmatch(path.name)
    }


def discover_runs(output_dir: Path) -> list[Path]:
    """Published runs; anything else visible in the output directory is an error."""
    if not output_dir.is_dir():
        return []
    runs = [p for p in sorted(output_dir.iterdir()) if p.is_dir() and not p.name.startswith(".")]
    if unexpected := [p.name for p in runs if not (p / META).is_file()]:
        raise ValueError(f"Not a published run (missing {META}): {', '.join(unexpected)}")
    return runs


# --- refinement decisions ------------------------------------------------------


def load_decisions(run: Path) -> dict[str, Any]:
    path = run / DECISIONS
    if not path.exists():
        return {"active": None, "decisions": {}}
    return json.loads(path.read_text(encoding="utf-8"))


def active_dir(run: Path) -> Path:
    """The approved revision if there is one, otherwise the initial run."""
    active = load_decisions(run)["active"]
    return run if active is None else run / "revisions" / active


def pending_revisions(run: Path) -> list[str]:
    revisions = run / "revisions"
    if not revisions.is_dir():
        return []
    decided = load_decisions(run)["decisions"]
    return [
        p.name
        for p in sorted(revisions.iterdir())
        if not p.name.startswith(".") and p.name not in decided
    ]


def decide_revision(run: Path, revision: str, *, approve: bool) -> None:
    """Record one decision; approval activates the revision unless its parent is stale."""
    if not _REVISION_ID.fullmatch(revision) or not (run / "revisions" / revision).is_dir():
        raise ValueError(f"Unknown revision {revision} in {run.name}")
    state = load_decisions(run)
    if revision in state["decisions"]:
        raise ValueError(f"Revision {revision} was already {state['decisions'][revision]}")
    if approve:
        parent_raw = read_meta(run / "revisions" / revision)["parentRawSha256"]
        if parent_raw != sha256(active_dir(run) / "raw.json"):
            raise ValueError("Revision was refined from a no longer active parent; reject it")
        state["active"] = revision
    state["decisions"][revision] = "approved" if approve else "rejected"
    atomic_write(run / DECISIONS, _dump(state))


# --- canonical days ------------------------------------------------------------


def load_selections(output_dir: Path) -> dict[str, str]:
    path = output_dir / SELECTIONS
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def select_day(output_dir: Path, date: str, run_name: str) -> None:
    run = output_dir / run_name
    if Path(run_name).name != run_name or run not in discover_runs(output_dir):
        raise ValueError(f"Unknown run: {run_name}")
    if date not in dated_notes(active_dir(run)):
        raise ValueError(f"Run {run_name} has no active note for {date}")
    atomic_write(output_dir / SELECTIONS, _dump({**load_selections(output_dir), date: run_name}))


def clear_selection(output_dir: Path, date: str) -> None:
    selections = load_selections(output_dir)
    if selections.pop(date, None) is not None:
        atomic_write(output_dir / SELECTIONS, _dump(selections))


def resolve_days(output_dir: Path, date_filter: str | None = None) -> dict[str, Path]:
    """Pick exactly one active note per date: the only candidate or the selected run."""
    candidates: dict[str, dict[str, Path]] = {}
    for run in discover_runs(output_dir):
        for date, path in dated_notes(active_dir(run)).items():
            candidates.setdefault(date, {})[run.name] = path
    selections = load_selections(output_dir)
    dates = set(candidates) | set(selections)
    if date_filter is not None:
        dates &= {date_filter}

    resolved: dict[str, Path] = {}
    for date in sorted(dates):
        by_run = candidates.get(date, {})
        if date in selections:
            if selections[date] not in by_run:
                raise ValueError(
                    f"Selected run {selections[date]} has no active note for {date}; "
                    f"use select --date {date} --clear or select another run"
                )
            resolved[date] = by_run[selections[date]]
        elif len(by_run) == 1:
            resolved[date] = next(iter(by_run.values()))
        else:
            raise ValueError(
                f"Ambiguous date {date}: {', '.join(by_run)}; use select --date {date} --run RUN"
            )
    return resolved
