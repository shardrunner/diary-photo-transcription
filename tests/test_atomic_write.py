from __future__ import annotations

import os
from pathlib import Path

import pytest

from diary_photo_transcription.atomic import atomic_write


def test_atomic_write_replaces_destination_after_complete_write(tmp_path: Path) -> None:
    destination = tmp_path / "manifest.yaml"
    destination.write_bytes(b"old-complete-content")

    atomic_write(destination, b"new-complete-content\n")

    assert destination.read_bytes() == b"new-complete-content\n"
    assert list(tmp_path.glob(f".{destination.name}.*.tmp")) == []


def test_atomic_write_failure_keeps_destination_and_cleans_temporary_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    destination = tmp_path / "manifest.yaml"
    destination.write_bytes(b"old-complete-content")

    def fail_replace(source: str | os.PathLike[str], target: str | os.PathLike[str]) -> None:
        assert Path(source).read_bytes() == b"new-complete-content\n"
        assert Path(target).read_bytes() == b"old-complete-content"
        raise OSError("synthetic replacement failure")

    monkeypatch.setattr(os, "replace", fail_replace)

    with pytest.raises(OSError, match="synthetic replacement failure"):
        atomic_write(destination, b"new-complete-content\n")

    assert destination.read_bytes() == b"old-complete-content"
    assert list(tmp_path.glob(f".{destination.name}.*.tmp")) == []
