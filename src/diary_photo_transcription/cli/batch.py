"""Parallele Extraktion mehrerer Fotos (`batch`)."""

from __future__ import annotations

import argparse
from concurrent.futures import CancelledError, ThreadPoolExecutor, as_completed
from decimal import Decimal
from pathlib import Path
from threading import Event

from diary_photo_transcription.config import load_project_config
from diary_photo_transcription.pipeline import (
    ExtractionResult,
    discover_source_photos,
    extract_photo,
)
from diary_photo_transcription.provenance import sha256


def _describe(result: ExtractionResult) -> str:
    entries = len(result.observation.entries)
    if result.skipped:
        return f"skipped (already extracted): {result.run_dir.name}; entries: {entries}"
    return (
        f"{result.run_dir.name}; entries: {entries}; tokens: {result.usage['totalTokens']}; "
        f"estimated cost USD: {result.estimated_cost:.4f}"
    )


def run_batch(args: argparse.Namespace) -> int:
    config = load_project_config(
        model=args.model,
        thinking_level=args.thinking_level,
        media_resolution=args.media_resolution,
    )
    output_dir = args.output_dir.resolve()
    if args.photos is not None:
        photos = [p.resolve(strict=True) for p in args.photos]
    else:
        photos = discover_source_photos(args.source_dir.resolve(strict=True))
    # Identical photo content under two names would otherwise be paid twice.
    unique: dict[str, Path] = {}
    for photo in photos:
        unique.setdefault(sha256(photo), photo)
    photos = list(unique.values())
    if not photos:
        print("No photos found to process.")
        return 0

    print(f"Batch extraction of {len(photos)} photos (concurrency={args.concurrency})...")
    cancel = Event()
    failures = 0
    cost = Decimal(0)
    executor = ThreadPoolExecutor(max_workers=args.concurrency)
    try:
        futures = {
            executor.submit(
                extract_photo, photo, config, output_dir, force=args.force, cancel_event=cancel
            ): photo
            for photo in photos
        }
        for done, future in enumerate(as_completed(futures), start=1):
            photo = futures[future]
            try:
                result = future.result()
            except CancelledError:
                failures += 1
                message = "✗ cancelled before request"
            except Exception as error:
                failures += 1
                details = [str(error), *getattr(error, "__notes__", ())]
                message = f"✗ {type(error).__name__}: {'; '.join(details)}"
            else:
                cost += 0 if result.skipped else result.estimated_cost
                message = f"✓ {_describe(result)}"
            print(f"[{done}/{len(photos)}] {photo.name}: {message}", flush=True)
    finally:
        # Ctrl-C: queued photos are dropped, started ones stop before their request;
        # requests already sent finish and keep their response.
        cancel.set()
        executor.shutdown(wait=True, cancel_futures=True)

    print(f"\nBatch complete: {len(photos) - failures} ok, {failures} failed; USD {cost:.4f}")
    return 0 if failures == 0 else 1
