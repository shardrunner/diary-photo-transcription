"""Argument-Parser für die Tagebuch-CLI."""

from __future__ import annotations

import argparse
from datetime import date
from importlib.metadata import version
from pathlib import Path

OUTPUT_DIR = Path("private/output")
SOURCE_DIR = Path("private/source")


def _positive_int(value: str) -> int:
    number = int(value)
    if number <= 0:
        raise argparse.ArgumentTypeError("must be positive")
    return number


def _iso_date(value: str) -> str:
    try:
        if date.fromisoformat(value).isoformat() != value:
            raise ValueError
    except ValueError:
        raise argparse.ArgumentTypeError("expected a valid YYYY-MM-DD calendar date") from None
    return value


def _add_request_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    parser.add_argument(
        "--media-resolution",
        choices=("high", "ultra_high"),
        default="high",
        help="Gemini image processing resolution",
    )
    parser.add_argument(
        "--thinking-level",
        choices=("low", "medium", "high"),
        help="explicit Gemini thinking level; the model default is used when omitted",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="diary-photo-transcription", description="Source-faithful diary extraction"
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {version('diary-photo-transcription')}"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    batch = subparsers.add_parser("batch", help="extract JPEGs in parallel (paid)")
    source = batch.add_mutually_exclusive_group()
    source.add_argument("--photos", nargs="+", type=Path, help="list of photo paths")
    source.add_argument("--source-dir", type=Path, default=SOURCE_DIR)
    batch.add_argument("--concurrency", type=_positive_int, default=4)
    batch.add_argument("--force", action="store_true", help="new paid runs even if they exist")
    _add_request_args(batch)

    review = subparsers.add_parser("review", help="list runs with review issues")
    review.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    review.add_argument("--source-dir", type=Path, default=SOURCE_DIR)
    review.add_argument("--date", type=_iso_date, help="only runs containing this date")
    review.add_argument(
        "--refine",
        action="store_true",
        help="paid second pass on flagged runs; creates revisions to approve or reject",
    )

    for action in ("approve", "reject"):
        decision = subparsers.add_parser(action, help=f"{action} a refinement revision")
        decision.add_argument("--run-dir", type=Path, required=True)
        decision.add_argument("--revision", required=True)

    select = subparsers.add_parser("select", help="choose the run for a date with competitors")
    select.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    select.add_argument("--date", type=_iso_date, required=True)
    selection = select.add_mutually_exclusive_group(required=True)
    selection.add_argument("--run", help="run directory name")
    selection.add_argument("--clear", action="store_true", help="forget this date's selection")

    export = subparsers.add_parser("export", help="write daily notes to the Obsidian vault")
    export.add_argument("--vault-dir", type=Path, help="defaults to vault_dir in local config")
    export.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    export.add_argument("--date", type=_iso_date, help="export only this date")
    export.add_argument("--force", action="store_true", help="overwrite differing vault notes")

    evaluate = subparsers.add_parser("eval", help="compare a prediction with a gold observation")
    evaluate.add_argument("--gold", type=Path, required=True, help="gold observation JSON")
    evaluate.add_argument("--pred", type=Path, required=True, help="prediction JSON or run dir")
    return parser
