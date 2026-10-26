import runpy
import subprocess
import sys
from pathlib import Path

import pytest
from detect_secrets import settings

SCANNER = Path(__file__).resolve().parents[1] / "scripts/scan-secrets.py"


def google_credential():
    return "AIza" + "".join(["Ab3xY7qW9", "mN2pR5sT8", "uV0zC6dE1", "fG4hJkLQ"])


def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


@pytest.mark.parametrize("name", ["GEMINI_API_KEY", "GOOGLE_API_KEY"])
@pytest.mark.parametrize("json_style", [False, True])
def test_staged_secret_not_hidden_by_placeholder_comment(tmp_path, name, json_style):
    git(tmp_path, "init")
    secret = google_credential()
    line = f'{{"{name}": "{secret}"}}' if json_style else f'{name}="{secret}"'
    path = tmp_path / "config.txt"
    path.write_text(line + " # placeholder replace-me pragma: allowlist secret\n")
    git(tmp_path, "add", ".")
    path.write_text(f'{name}="replace-me"\n')
    result = subprocess.run([sys.executable, str(SCANNER)], cwd=tmp_path, capture_output=True)
    assert result.returncode == 1
    assert secret.encode() not in result.stdout + result.stderr
    git(tmp_path, "add", ".")
    path.write_text(line)
    result = subprocess.run([sys.executable, str(SCANNER)], cwd=tmp_path, capture_output=True)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    "value, expected",
    [
        ("replace-me", 0),
        ("placeholder", 0),
        ("", 0),
        ("replace-me-real", 1),
    ],
)
def test_allowlist_is_exact_value(tmp_path, value, expected):
    git(tmp_path, "init")
    (tmp_path / "config.json").write_text('{"GOOGLE_API_KEY": "' + value + '"}')
    git(tmp_path, "add", ".")
    result = subprocess.run([sys.executable, str(SCANNER)], cwd=tmp_path, capture_output=True)
    assert result.returncode == expected, result.stderr


@pytest.mark.parametrize("suffix, expected", [("", 0), ("0", 1)])
def test_hex_alphabet_exemption_is_exact(tmp_path, suffix, expected):
    git(tmp_path, "init")
    alphabet = "0123456789abcdef"
    (tmp_path / "source.py").write_text(f'characters = "{alphabet}{suffix}"\n')
    git(tmp_path, "add", "source.py")
    result = subprocess.run([sys.executable, str(SCANNER)], cwd=tmp_path, capture_output=True)
    assert result.returncode == expected, result.stderr


@pytest.mark.parametrize("name", ["GEMINI_API_KEY", "GOOGLE_API_KEY"])
@pytest.mark.parametrize("json_style", [False, True])
def test_hex_alphabet_does_not_hide_credentials(tmp_path, name, json_style):
    git(tmp_path, "init")
    alphabet = "0123456789abcdef"
    secret = google_credential()
    line = (
        f'{{"alphabet": "{alphabet}", "{name}": "{secret}"}}'
        if json_style
        else f'alphabet = "{alphabet}"; {name} = "{secret}"'
    )
    (tmp_path / "source.py").write_text(line + "\n")
    git(tmp_path, "add", "source.py")
    result = subprocess.run([sys.executable, str(SCANNER)], cwd=tmp_path, capture_output=True)
    assert result.returncode == 1
    assert b"'source.py':1" in result.stderr
    assert secret.encode() not in result.stdout + result.stderr


def test_scanner_error_is_redacted(tmp_path, monkeypatch, capsys):
    git(tmp_path, "init")
    monkeypatch.chdir(tmp_path)

    def broken():
        raise RuntimeError("synthetic-sensitive-value")

    monkeypatch.setattr(settings, "get_plugins", broken)
    module = runpy.run_path(str(SCANNER))
    import logging

    disabled = logging.root.manager.disable
    try:
        assert module["main"]() == 2
    finally:
        logging.disable(disabled)
    assert "synthetic-sensitive-value" not in capsys.readouterr().err


@pytest.mark.parametrize(
    "dependency, key, value, expected",
    [
        (True, None, None, 0),
        (False, "GEMINI_API_KEY", "1.5.0", 1),
        (True, "GOOGLE_API_KEY", "not-a-placeholder", 1),
    ],
)
def test_scanner_dependency_is_not_a_credential(tmp_path, dependency, key, value, expected):
    content = '  "detect-secrets==1.5.0", ' if dependency else ""
    if key:
        content += f'{key}="{value}"'
    git(tmp_path, "init")
    (tmp_path / "pyproject.toml").write_text(content)
    git(tmp_path, "add", ".")
    result = subprocess.run([sys.executable, str(SCANNER)], cwd=tmp_path, capture_output=True)
    assert result.returncode == expected, result.stderr


def test_git_or_dependency_error_fails_closed(tmp_path):
    result = subprocess.run([sys.executable, str(SCANNER)], cwd=tmp_path, capture_output=True)
    assert result.returncode != 0
