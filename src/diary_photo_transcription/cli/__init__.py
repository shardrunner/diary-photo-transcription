"""CLI-Einstieg (`main`) und Dispatch auf die Kommando-Module."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable, Sequence

from diary_photo_transcription.cli.batch import run_batch
from diary_photo_transcription.cli.decisions import run_decision, run_select
from diary_photo_transcription.cli.eval_cmd import run_eval
from diary_photo_transcription.cli.export import run_export
from diary_photo_transcription.cli.parser import build_parser
from diary_photo_transcription.cli.review import run_review

COMMANDS: dict[str, Callable[[argparse.Namespace], int]] = {
    "batch": run_batch,
    "review": run_review,
    "approve": run_decision,
    "reject": run_decision,
    "select": run_select,
    "export": run_export,
    "eval": run_eval,
}


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return COMMANDS[args.command](args)
    except ValueError as error:
        # Expected user/data errors (ambiguous date, unknown run, ...) are raised
        # as ValueError; print the message instead of a traceback.
        print(f"error: {error}", file=sys.stderr)
        return 1
