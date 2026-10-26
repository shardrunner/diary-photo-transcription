# Diary Photo Transcription

> **Disclaimer:** This project is vibe coded for personal use. Use at your own risk.

[![CI](https://github.com/shardrunner/diary-photo-transcription/actions/workflows/ci.yml/badge.svg)](https://github.com/shardrunner/diary-photo-transcription/actions/workflows/ci.yml)
[![Python >=3.12](https://img.shields.io/badge/python-%3E%3D3.12-blue.svg)](pyproject.toml)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

A Python CLI that transcribes photos of my handwritten German diary into
Obsidian daily notes using multimodal LLMs (Gemini or OpenAI; a Claude Code
adapter is used for comparisons). The pipeline aims to preserve the page
faithfully: text the model considers illegible is marked `⟦unleserlich⟧`, every
run records its provenance, and refinements need explicit approval.

**Tech stack:** Python · Pydantic · Gemini and OpenAI APIs · pytest · Ruff ·
Pyrefly · uv · GitHub Actions

## Highlights

- **Human in the loop:** uncertain text is marked instead of guessed, refinements
  apply only after approval, and conflicting runs for a date are resolved manually.
- **Evaluated model choice:** Gemini, OpenAI and Claude models compared through the
  same pipeline on text accuracy, dates, cost and latency.
- **Gold-set scoring:** `eval` compares any run with a hand-verified page (CER,
  omissions, form labels, score positions).
- **Traceable and private:** every run keeps the raw response, prompt and
  provenance hashes; photos are uploaded without EXIF metadata.
- **Tested offline:** tests need no credentials or network; CI also runs the demo
  and a wheel smoke test.

## Model evaluation

Three models ran through the same pipeline (same prompt, schema and validation)
in October 2026. The sample is small (2 hand-verified pages × 3 runs for text,
15 pages for dates), so treat the numbers as a rough guide. CER is the character
error rate of the transcribed text.

| Model (setting) | Text CER ↓ | Dates correct ↑ | Confident date errors ↓ | USD/page ↓ | Median latency ↓ |
|---|---|---|---|---|---|
| Gemini 3.8 Flash (medium) | **2.2%** | 11/15 | 3 | 0.063 | 140 s |
| GPT-6.1 Terra (medium, original detail) | 3.4% | **14/15** | **1** | 0.029 | 69 s |
| GPT-6.1 Terra (medium) | 4.1% | **14/15** | **1** | **0.020** | 59 s |
| Claude Sonnet 5.5 (medium, via Claude Code) | 2.5% | 12/14 | **1** | 0.067 | **23 s** |

Dates are counted over successful requests only (one Claude request failed).

- On this small sample, Gemini medium had the lowest text and form error and no
  measured omissions; Terra got more dates right at about a third of the cost.
- The worst errors were schema-valid: wrong years marked `certain`. Replaying the
  runs, a disagreement check against Terra flagged 3 of Gemini's 4 date errors
  with no false flags. This check is planned, not yet implemented.
- Higher thinking levels did not consistently help; Gemini at `high` mostly timed
  out.

Details, all 8 configurations and failure analysis:
[model evaluation](docs/ai/model-evaluation.md).

## How it works

1. Strip EXIF from the diary photo and hash it.
2. Extract the page with an LLM into strict-schema JSON.
3. Validate with Pydantic and domain rules.
4. Render Markdown notes and review issues.
5. Export to the Obsidian vault.

The raw model response is saved before validation. An optional second pass
refines uncertain passages and only takes effect once approved. If several runs
cover the same date, I choose the source manually; export does not overwrite
differing notes without `--force`. First extractions are not approved one by one,
so exported notes still need a human read.

## Design decisions

- **Three observation classes:** closed form labels, positional scores and ordered
  paragraphs. Absent, visibly empty, illegible and struck-through are distinct
  states; a present score row reports all 17 positions so gaps cannot shift values.
- **Deterministic domain logic:** the model reports position and visible value;
  code assigns score meaning and validates notation.
- **Source-faithful rendering:** entries keep source order, item boundaries,
  completion and strike-through state and raw score notation. Text is escaped for
  literal Markdown/Obsidian display. Frontmatter summaries are marked
  non-authoritative and become `null` on conflicting sources.

See the [data model](docs/ai/data-model.md) and the
[paper contract](docs/ai/papierlegende.md).

## Quick start (offline demo, no credentials)

Requires Python 3.12+ on Linux/Unix and [uv](https://docs.astral.sh/uv/).

```bash
uv sync --locked
uv run python examples/demo/run.py
uv run diary-photo-transcription eval \
  --gold examples/demo/expected.json --pred examples/demo/expected.json
```

The demo validates and re-renders a synthetic fixture (no real diary content)
without inference. Comparing the expected output with itself is a software check,
**not a handwriting benchmark**.

## Usage

The CLI and prompts are in German because the diary is German.

<details>
<summary><b>Setup and daily workflow</b></summary>

```bash
mkdir -p private/source
cp examples/local-config.json private/local-config.json   # new installs only
cp .env.example .env                                      # GEMINI_API_KEY and/or OPENAI_API_KEY
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

`--model`, `--thinking-level` and `--media-resolution` on `batch` are for paid
comparisons; they change the run identity. `--thinking-level` maps to OpenAI
reasoning effort, `--media-resolution high|ultra_high` to OpenAI image detail
`high|original`. Prompt and strict JSON schema are identical for both providers.
Ctrl-C during `batch` drops queued photos; requests already sent finish and are
saved.

</details>

<details>
<summary><b>Runs and artifacts</b></summary>

A run is identified by photo content hash + configuration fingerprint, so an
unchanged photo with the same configuration is skipped (`--force` makes a new run).
The Gemini SDK version is recorded in `run.json` but not part of the fingerprint,
so an SDK upgrade does not resubmit extracted photos; use `--force` to compare an
upgrade on selected `--photos`. Each run is built in a hidden staging directory and
renamed into `private/output/RUN/` only when complete:

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
and a new refinement waits until the open one is decided. A date found in several
runs needs a `select`; export never picks a winner and refuses to overwrite
differing vault notes without `--force`.

</details>

## Privacy, costs and limitations

**Local orchestration is not local inference.** Photos and any configured context
go to Google's or OpenAI's cloud API with `store=false`, which is not a universal
retention guarantee; check the provider's API data terms first. The Claude Code
adapter uses the local `claude` CLI with its own authentication and data handling. Uploads are
EXIF-oriented and re-encoded without metadata. Run artifacts and error messages can
contain diary text. Keys are read from `GEMINI_API_KEY` or `OPENAI_API_KEY` only,
and a nonempty `GOOGLE_GENAI_DEBUG` is refused because SDK wire logging would
record credentials and photos.

Each HTTP attempt times out after 300 s (dense pages exceeded 120 s); both SDKs
retry 408/409/429/5xx up to twice. Logged costs estimate reported usage at the
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
a heuristic secret check, not proof that prose or images are free of private
material.

Developed with AI coding assistants.

## License

[MIT](LICENSE).
