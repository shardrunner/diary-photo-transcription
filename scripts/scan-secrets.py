#!/usr/bin/env python3
"""Scan index blobs, never worktree files; report locations, never secret values.

CI's fresh checkout has the same index and tracked checkout content. All maintained
plugins run without heuristic/inline allowlists or online verification filters.
Only exact placeholder/alphabet values are exempted, never whole lines or paths.
No baseline hides existing findings.
"""

import logging
import re
import subprocess
import sys
from pathlib import PurePosixPath

PLACEHOLDERS = frozenset({"", "replace-me", "placeholder"})
NON_SECRET_ALPHABETS = frozenset({"0123456789abcdef"})
# KeywordDetector mistakes its own pinned package version for a secret assignment.
_SCANNER_DEPENDENCY = re.compile(r"""\s*["']detect-secrets==\d+\.\d+\.\d+["'],?\s*""")


def git(*args: str) -> bytes:
    return subprocess.run(["git", *args], check=True, capture_output=True).stdout


def main() -> int:
    # Scanner diagnostics can contain source text; emit only our own safe diagnostics.
    logging.disable(logging.CRITICAL)
    try:
        from detect_secrets.settings import default_settings, get_plugins

        entries = git("ls-files", "--stage", "-z").split(b"\0")
        failed = False
        with default_settings():
            plugins = get_plugins()
            if not plugins:
                raise RuntimeError("no scanner plugins")
            for entry in entries:
                if not entry:
                    continue
                metadata, raw_path = entry.split(b"\t", 1)
                mode, oid, stage = metadata.split()
                path = raw_path.decode("utf-8", errors="strict")
                parts = PurePosixPath(path).parts
                if stage != b"0" or mode not in (b"100644", b"100755", b"120000"):
                    raise ValueError("unsupported or unmerged index entry")
                if parts[0] in ("private", "tagebuch") or ".env" in parts:
                    print(f"Forbidden tracked path: {path!r}", file=sys.stderr)
                    failed = True
                    continue
                # Latin-1 is lossless, including ASCII credentials embedded in binary blobs.
                content = git("cat-file", "blob", oid.decode("ascii")).decode("latin-1")
                for number, line in enumerate(content.splitlines(), 1):
                    # analyze_line keeps plugin entropy thresholds (unlike adhoc scan_line).
                    if any(
                        secret.secret_value not in PLACEHOLDERS | NON_SECRET_ALPHABETS
                        and not (
                            type(plugin).__name__ == "KeywordDetector"
                            and _SCANNER_DEPENDENCY.fullmatch(line)
                        )
                        for plugin in plugins
                        for secret in plugin.analyze_line(
                            filename=path, line=line, line_number=number
                        )
                    ):
                        print(f"Potential secret: {path!r}:{number}", file=sys.stderr)
                        failed = True
        return 1 if failed else 0
    except Exception:
        print("Secret scan failed (Git/scanner error); publication blocked.", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
