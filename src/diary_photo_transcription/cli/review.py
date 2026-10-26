"""Review-Liste und gezielter Refinement-Pass (`review`)."""

from __future__ import annotations

import argparse

from diary_photo_transcription.normalize import review_targets
from diary_photo_transcription.pipeline import find_source_photo, refine_run
from diary_photo_transcription.runs import (
    active_dir,
    dated_notes,
    discover_runs,
    pending_revisions,
    read_issues,
    read_meta,
    read_observation,
)

_LAYOUT = {True: "wie Vorlage", False: "weicht ab", None: "unklar"}


def _print_indented(prefix: str, text: str) -> None:
    """Print `text` after `prefix`, aligning continuation lines under its first line."""
    print(prefix + text.replace("\n", "\n" + " " * len(prefix)))


def run_review(args: argparse.Namespace) -> int:
    """List runs whose active observation has review issues; optionally refine them."""
    output_dir = args.output_dir.resolve(strict=True)
    source_dir = args.source_dir.resolve()
    flagged = []
    for run in discover_runs(output_dir):
        current = active_dir(run)
        issues = read_issues(current)
        pending = pending_revisions(run)
        if not issues and not pending:
            continue
        observation = read_observation(current)
        dates = [str(entry.date or "unbekannt") for entry in observation.entries]
        if args.date and args.date not in dates:
            continue
        flagged.append(run)

        source = find_source_photo(read_meta(current), source_dir)
        print(f"[{len(flagged)}] Run: {run.name} | Datum: {', '.join(dates) or 'keins'}")
        print(f"    Pfad: {current}")
        print(f"    Foto: {source or 'nicht gefunden'}")
        overview, layout = observation.photo_overview, observation.layout
        _print_indented(
            "    Seite: ", f"{', '.join(overview.tags) or 'keine Tags'} — {overview.note}"
        )
        layout_note = f" — {layout.deviation_note}" if layout.deviation_note else ""
        _print_indented("    Layout: ", f"{_LAYOUT[layout.follows_expected_layout]}{layout_note}")
        for revision in pending:
            notes = ", ".join(dated_notes(run / "revisions" / revision)) or "keine Tagesnotiz"
            print(f"    Offene Revision {revision} ({notes}): approve/reject --run-dir {run}")
        for issue in issues:
            label = f"Eintrag #{issue.entry_index}" if issue.entry_index else "Foto"
            print(f"    - {label}: {', '.join(issue.reasons)}")
        for index, target in enumerate(review_targets(observation, issues), start=1):
            _print_indented(f"        [{index}] ", target)
        print()

    if not flagged:
        print("No runs with review issues.")
        return 0
    if not args.refine:
        return 0

    print("Refinement (paid) with each run's model, thinking level and resolution:")
    for run in flagged:
        if pending_revisions(run):
            print(f"  {run.name}: skipped, decide the open revision first")
            continue
        result = refine_run(run, source_dir)
        if result is None:
            print(f"  {run.name}: nothing to refine")
            continue
        issues = len(read_issues(result.run_dir))
        usage = result.usage
        print(
            f"  {run.name}: revision {result.run_dir.name} ({issues} issue(s) left, "
            f"{usage['model']}, thinking={usage['thinkingLevel']}, "
            f"resolution={usage['mediaResolution']}, USD {result.estimated_cost:.4f}); "
            "approve or reject it explicitly"
        )
    return 0
