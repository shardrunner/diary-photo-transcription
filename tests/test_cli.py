"""Command-level behavior through `main`, offline via FakeGemini."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from diary_photo_transcription.cli import main
from diary_photo_transcription.cli.parser import build_parser
from diary_photo_transcription.runs import discover_runs, pending_revisions


@pytest.mark.parametrize(
    "argv",
    [
        ["batch", "--photos"],
        ["batch", "--photos", "a.jpg", "--source-dir", "."],
        ["batch", "--concurrency", "0"],
        ["batch", "--thinking-level", "minimal"],
        ["select", "--date", "2040-01-02"],
        ["select", "--date", "2040-01-02", "--run", "x", "--clear"],
        *[
            [command, "--date", value] + (["--run", "x"] if command == "select" else [])
            for command in ("export", "review", "select")
            for value in ("2025-02-29", "20250101", "2025-1-01")
        ],
    ],
)
def test_parser_rejects_invalid_arguments(argv: list[str]) -> None:
    with pytest.raises(SystemExit):
        build_parser().parse_args(argv)


@pytest.mark.parametrize(
    "command",
    [[sys.executable, "-m", "diary_photo_transcription"], ["diary-photo-transcription"]],
)
def test_module_help_and_version_name_the_command(command: list[str]) -> None:
    def run(flag: str) -> str:
        result = subprocess.run([*command, flag], capture_output=True, text=True)
        assert result.returncode == 0
        return result.stdout

    assert "Source-faithful diary extraction" in run("--help")
    assert run("--version").startswith("diary-photo-transcription ")


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_photo) -> Path:
    monkeypatch.chdir(tmp_path)
    make_photo(tmp_path / "private/source/a.jpg", (1, 1, 1))
    make_photo(tmp_path / "private/source/b.JPEG", (200, 0, 0))
    return tmp_path


def test_batch_deduplicates_content_and_reports_failures(workspace, fake_gemini, capsys):
    (workspace / "private/source/copy.jpg").write_bytes(
        (workspace / "private/source/a.jpg").read_bytes()
    )
    assert main(["batch"]) == 0
    assert len(fake_gemini.prompts) == 2
    assert "2 ok, 0 failed" in capsys.readouterr().out

    fake_gemini.raw_text = "{}"
    assert main(["batch", "--force", "--photos", "private/source/a.jpg"]) == 1
    out = capsys.readouterr().out
    assert "1 failed" in out
    assert "Received response kept in" in out


def test_review_refine_approve_and_export(workspace, fake_gemini, capsys):
    assert main(["batch", "--photos", "private/source/a.jpg"]) == 0
    [run] = discover_runs(workspace / "private/output")

    assert main(["review"]) == 0
    out = capsys.readouterr().out
    assert run.name in out
    assert "unreadable_text, unsupported_date" in out
    assert "Morgen folgt ein ⟦unleserlich⟧" in out
    assert str(workspace / "private/source/a.jpg") in out
    assert "Seite: sparse_page — Fictional typeset software fixture." in out
    assert "Layout: weicht ab — Text-only synthetic page; no score row or form." in out

    fake_gemini.raw_text = fake_gemini.clean_raw()
    assert main(["review", "--refine"]) == 0
    [revision] = pending_revisions(run)
    assert "approve or reject it explicitly" in capsys.readouterr().out

    assert main(["approve", "--run-dir", str(run), "--revision", revision]) == 0
    assert main(["review"]) == 0
    assert "No runs with review issues." in capsys.readouterr().out

    vault = workspace / "vault"
    assert main(["export", "--vault-dir", str(vault)]) == 0
    note = vault / "2040-01-02.md"
    assert "Morgen folgt ein Boot" in note.read_text()
    assert note.read_bytes() == (run / "revisions" / revision / "2040-01-02.md").read_bytes()


def test_review_aligns_multiline_notes(workspace, fake_gemini, capsys):
    raw = json.loads(fake_gemini.raw_text)
    raw["photoOverview"]["note"] = "first line\nsecond line"
    fake_gemini.raw_text = json.dumps(raw)
    main(["batch", "--photos", "private/source/a.jpg"])
    capsys.readouterr()
    assert main(["review"]) == 0
    assert "— first line\n           second line\n" in capsys.readouterr().out


def test_export_protects_differing_vault_notes(workspace, fake_gemini, capsys):
    main(["batch", "--photos", "private/source/a.jpg"])
    vault = workspace / "vault"
    vault.mkdir()
    (vault / "2040-01-02.md").write_text("hand-edited")

    assert main(["export", "--vault-dir", str(vault)]) == 1
    assert (vault / "2040-01-02.md").read_text() == "hand-edited"
    assert main(["export", "--vault-dir", str(vault), "--force"]) == 0
    assert main(["export", "--vault-dir", str(vault)]) == 0
    assert "0 written, 1 unchanged" in capsys.readouterr().out


def test_export_without_vault_fails(workspace, fake_gemini):
    main(["batch", "--photos", "private/source/a.jpg"])
    with pytest.raises(ValueError, match="vault_dir"):
        main(["export"])


def test_ambiguous_date_is_resolved_by_select(workspace, fake_gemini):
    main(["batch"])
    vault = workspace / "vault"
    with pytest.raises(ValueError, match="Ambiguous"):
        main(["export", "--vault-dir", str(vault)])
    assert not vault.exists()
    chosen = discover_runs(workspace / "private/output")[1]
    assert main(["select", "--date", "2040-01-02", "--run", chosen.name]) == 0
    assert main(["export", "--vault-dir", str(vault)]) == 0


def test_eval_accepts_json_or_run_directory(workspace, fake_gemini, capsys):
    main(["batch", "--photos", "private/source/a.jpg"])
    [run] = discover_runs(workspace / "private/output")
    gold = workspace / "gold.json"
    gold.write_text(fake_gemini.raw_text)
    for pred in (gold, run):
        assert main(["eval", "--gold", str(gold), "--pred", str(pred)]) == 0
        assert "Exakter Treffer: True" in capsys.readouterr().out
