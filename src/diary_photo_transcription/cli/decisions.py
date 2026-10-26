"""Entscheidungen über Refinement-Revisionen und manuelle Tages-Auswahl."""

from __future__ import annotations

import argparse

from diary_photo_transcription.runs import clear_selection, decide_revision, select_day


def run_decision(args: argparse.Namespace) -> int:
    approve = args.command == "approve"
    decide_revision(args.run_dir.resolve(strict=True), args.revision, approve=approve)
    print(f"Revision {args.revision}: {'approved' if approve else 'rejected'}")
    return 0


def run_select(args: argparse.Namespace) -> int:
    output_dir = args.output_dir.resolve(strict=True)
    if args.clear:
        clear_selection(output_dir, args.date)
        print(f"Cleared selection for {args.date}; vault notes unchanged.")
    else:
        select_day(output_dir, args.date, args.run)
        print(f"Selected {args.run} for {args.date}")
    return 0
