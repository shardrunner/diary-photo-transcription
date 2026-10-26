# Diary Photo Transcription

> **Disclaimer:** This project is vibe coded for personal use. Use at your own risk.

[![CI](https://github.com/shardrunner/diary-photo-transcription/actions/workflows/ci.yml/badge.svg)](https://github.com/shardrunner/diary-photo-transcription/actions/workflows/ci.yml)
[![Python >=3.12](https://img.shields.io/badge/python-%3E%3D3.12-blue.svg)](pyproject.toml)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

An applied multimodal AI pipeline for source-faithful transcription of German diary
photos into Obsidian daily notes. It combines Gemini structured output with strict
domain validation, content-based provenance, deterministic Markdown rendering and
human approval. It demonstrates the engineering around a model—not a claim that
valid JSON is a correct transcription.

**Tech stack:** Python ≥3.12 · Pydantic · google-genai (`gemini-3.8-flash`) · CLI ·
filesystem artifacts. CLI and prompts are German because the diary is German.

**Workflow:**

1. Send a local JPEG and configured private context to the Gemini cloud API.
2. Save the raw model observation, validate it, and render Markdown plus review issues.
3. Review uncertainties; optional refinements require explicit approval or rejection.
4. Manually choose a source when runs compete for the same date, then export to the
   vault with overwrite protection.

## Offline demo — no credentials

Requires Python 3.12+ on Linux/Unix and [uv](https://docs.astral.sh/uv/).

```bash
uv sync --locked
uv run python examples/demo/run.py
uv run diary-photo-transcription eval \
  --gold examples/demo/expected.json --pred examples/demo/expected.json
```

See the [synthetic source image](examples/demo/source.jpg), its
[expected structured output](examples/demo/expected.json) and the
[rendered note](examples/demo/2040-01-02.md). The obscured word becomes
`⟦unleserlich⟧` and a review issue. The demo validates and re-renders without
inference; self-comparison is a software check, **not a handwriting benchmark**.

## Daily use

```bash
mkdir -p private/source
cp examples/local-config.json private/local-config.json   # new installs only
cp .env.example .env                                      # add a Paid-project GEMINI_API_KEY
```

`private/local-config.json` holds `context` (reading-aid vocabulary),
`default_corpus_year` and `vault_dir`; unknown keys or wrong types fail. Personal
names and abbreviations belong only there, never in tracked prompts or docs; the
example is fictional, and vocabulary is a reading aid, not evidence of visible text.
`TAGEBUCH_CONFIG=/path.json` selects another file, `TAGEBUCH_CONFIG=''` disables it.

```bash
uv run diary-photo-transcription batch                      # paid; skips photos already extracted
uv run diary-photo-transcription batch --photos private/source/x.jpg [--force]
uv run diary-photo-transcription review                     # runs with review issues
uv run diary-photo-transcription review --refine            # paid second pass → pending revision
uv run diary-photo-transcription approve --run-dir private/output/RUN --revision ID   # or reject
uv run diary-photo-transcription select --date 2040-01-02 --run RUN                  # or --clear
uv run diary-photo-transcription export [--vault-dir DIR] [--force]
```

`--thinking-level` and `--media-resolution` on `batch` are for paid
comparisons; they change the run identity. Ctrl-C during `batch` drops queued photos;
requests already sent finish and are saved.

### Runs

A run is identified by photo content hash + configuration fingerprint, so an
unchanged photo with the same configuration is skipped (`--force` makes a new run).
The fingerprint includes the Gemini SDK version: after an SDK upgrade, `batch`
can submit previously extracted photos again. Use `--photos` to limit the first
paid batch after upgrading to the intended inputs. Each run is
built in a hidden staging directory and renamed into `private/output/RUN/` only
when complete:

| File | Content |
| --- | --- |
| `interaction.json` | full provider response, saved before it is validated |
| `raw.json` | model observation (not ground truth) |
| `run.json` | provenance, hashes, token usage and cost estimate |
| `prompt.txt`, `review.json`, `YYYY-MM-DD.md` | exact prompt, review issues, rendered notes |

A response that fails validation is kept in `private/output/.failed-*` for
inspection and does not block a new attempt. Refinements reuse the run's model,
thinking level and resolution and are written to `RUN/revisions/ID/`; only an
explicitly approved revision replaces the run's notes for review, eval and export,
and a new refinement waits until the open one is decided. A date found in several runs needs a `select`; export never picks a
winner and refuses to overwrite differing vault notes without `--force`.

## Design decisions

- **Three observation classes:** closed form labels, positional scores and ordered
  paragraphs. Absent, visibly empty, illegible and struck-through are distinct states;
  a present score row reports all 17 positions so gaps cannot shift values.
- **Deterministic domain logic:** the model reports position and visible value;
  code assigns score meaning and validates notation.
- **Source-faithful rendering:** entries keep source order, item boundaries,
  completion and strike-through state and raw score notation. Text is escaped for
  literal Markdown/Obsidian display. Frontmatter summaries are marked
  non-authoritative and become `null` on conflicting sources.
- **Human authority:** fewer uncertainty markers do not establish correctness.
  Refinements need approval; competing sources need a manual choice.
- **Small local architecture:** Pydantic, filesystem artifacts and a CLI; no
  database, GUI or provider framework. See the [data model](docs/ai/data-model.md)
  and the [paper contract](docs/ai/papierlegende.md).

Evaluation compares all entries in source order. Text CER sums per-entry edit
distances over total reference characters; listed inserted passages are
differences, not verified hallucinations. Meaningful quality numbers need
independently verified gold data ([notes](docs/ai/extraktionsoptimierung.md)).

## Privacy, costs and limitations

**Local orchestration is not local inference.** Photos and configured context go
to Google's cloud API with `store=false`, which is not a universal retention
guarantee; check the Paid API data terms first. Uploads are EXIF-oriented and
re-encoded without metadata. Run artifacts and error messages can contain
diary text. The key is read from `GEMINI_API_KEY`
only, and a nonempty `GOOGLE_GENAI_DEBUG` is refused because SDK wire logging
would record credentials and photos.

Each HTTP attempt times out after 300 s (dense pages exceeded 120 s); the SDK
retries 408/409/429/5xx up to twice. Logged costs estimate reported usage at the
configured rates, not billed cost; failed or timed-out requests may cost tokens
without reporting usage. With `gemini-3.8-flash` and its default thinking, a page
costs about $0.055 (thinking is ~70 % of that); `--thinking-level low` is the main
cost lever. Rates double from 2027-01-01; new estimates use the rates for the
current UTC date. Stored run estimates remain unchanged.

## Development

Tests need no credentials; the pytest process blocks Internet sockets.

```bash
uv run pytest -x
uv run ruff check . && uv run ruff format --check .
uv run pyrefly check
uv build --no-sources
```

CI runs these on Python 3.12, 3.14 and 3.15, plus the demo, a wheel smoke test and
`scripts/scan-secrets.py`, a `detect-secrets` scan of the staged Git index. It is
a heuristic secret check, not proof that prose or images are free of private material.

## License

[MIT](LICENSE).
