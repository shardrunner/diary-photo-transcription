"""Export der Tagesnotizen in den Obsidian-Vault (`export`)."""

from __future__ import annotations

import argparse
from pathlib import Path

from diary_photo_transcription.atomic import atomic_write
from diary_photo_transcription.config import load_project_config
from diary_photo_transcription.runs import resolve_days


def run_export(args: argparse.Namespace) -> int:
    """Copy one active note per date; differing vault notes need `--force`."""
    output_dir = args.output_dir.resolve(strict=True)
    vault = args.vault_dir or load_project_config().local.vault_dir
    if not vault:
        raise ValueError("Provide --vault-dir or configure vault_dir locally")
    vault_dir = Path(vault).expanduser().resolve()

    contents = {
        date: path.read_bytes() for date, path in resolve_days(output_dir, args.date).items()
    }
    if not contents:
        print("No matching daily notes to export.")
        return 0
    existing = {date: vault_dir / f"{date}.md" for date in contents}
    changed = {
        date: content
        for date, content in contents.items()
        if not existing[date].exists() or existing[date].read_bytes() != content
    }
    conflicts = sorted(date for date in changed if existing[date].exists())
    if conflicts and not args.force:
        print("Vault notes differ (use --force to overwrite): " + ", ".join(conflicts))
        return 1
    for date, content in sorted(changed.items()):
        atomic_write(existing[date], content)
    print(f"Export complete: {len(changed)} written, {len(contents) - len(changed)} unchanged.")
    return 0
