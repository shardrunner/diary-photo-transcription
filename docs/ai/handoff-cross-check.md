---
summary: Handoff (2026-10-26) for the Gemini + GPT-6.1 Terra cross-check, date plausibility checks and follow-ups after the model evaluation.
read_when:
  - Implementing the cross-check, date plausibility flags or the default thinking level
  - Picking up work after the 2026-10-26 model evaluation
---

# Handoff: cross-check and date plausibility (2026-10-26)

Private, page-specific details (photo IDs, verified dates, run folders) are in
the ignored `private/handoff-notes.md`. Do not copy them into tracked files.

## Goal

Make wrong dates visible before export, without automatic corrections:

1. **Cross-check:** GPT-6.1 Terra extracts every page in addition to Gemini 3.8
   Flash. Date disagreements become review issues.
2. **Deterministic plausibility flags:** a year outside the corpus year, and a
   date that breaks the photo sequence.
3. **Explicit default thinking level:** `medium`.

The rationale is in [model-evaluation.md](model-evaluation.md), sections
"Cross-check simulation" and "Decision". In short: Gemini is the most faithful
transcriber but reads some years confidently wrong (e.g. 2020 instead of 2026);
Terra reads dates best. Disagreement flagged 3 of 4 Gemini date errors with no
false flags, at +0.020 USD/page.

## Current state

- Branch `main`, 9 commits ahead of `origin/main` (not pushed). From `35f0673`
  to `d1efe77`:
  - SDK version removed from run identity
  - CLI errors print without a traceback
  - Prompt v10 handles partial score rows
  - `provider.py` refactor
  - OpenAI adapter
  - Claude CLI adapter
  - Model evaluation document and README table
- Checks are green: `uv run pytest -x` (906 tests, offline),
  `uv run ruff check . && uv run ruff format --check .`, `uv run pyrefly check`,
  `uv run python scripts/scan-secrets.py`. The scan checks the staged index; only
  exact placeholders such as `placeholder` or `replace-me` are allowed as fake
  keys in tests.
- **Providers**, chosen by `batch --model`:

  | Model | Provider (`config.MODELS`) | Adapter | Credentials |
  |---|---|---|---|
  | `gemini-3.8-flash` (default) | `gemini` | `gemini.py` | `GEMINI_API_KEY` |
  | `gpt-6.1-terra` | `openai` | `openai_api.py` | `OPENAI_API_KEY` |
  | `claude-sonnet-5-5` | `claude-cli` | `claude_cli.py` | `claude` CLI login |

  - The pipeline picks the adapter at call time (`pipeline._adapter`), so tests
    can monkeypatch the modules.
  - Shared types are in `provider.py`. `ModelResult.cost_usd` overrides the usage
    estimate; only the Claude adapter sets it.
- **Prompt and schema:** prompt v10 (`prompts.py`), schema v2 (`schemas.py`).
  OpenAI gets `openai_api.strict_json_schema()`: every property required and no
  defaults.
- **Run identity:** photo hash plus config fingerprint
  (`provenance.config_fingerprint`). The fingerprint covers prompt, local config
  (without `vault_dir`), model, thinking level, resolution, prompt and schema
  version. The SDK version is recorded in `run.json` but not in the fingerprint.
- **Benchmark:** `scripts/model_benchmark.py BENCH_DIR` aggregates content-free
  metrics. It counts failed requests from `✗` lines in each config's `*.log`,
  because timeouts leave no run folder.

## Known problems

- **Prompt v10 changed the fingerprint of every run.** The next plain `batch`
  re-sends all 33 source photos: about 2.1 USD with Gemini medium, about 2.75 USD
  with the cross-check. Do the steps below first, then run one consented batch.
- **Every model misreads the same ambiguous date.** One page's date is barely
  legible, and every model reads it the same wrong way, so it collides with
  another page's date. `select` can only pick one of the two runs, and there is
  no manual date correction. Only the sequence check (step 2) or a human
  catches this.
- **No uncertain-score state.** At high image resolution, models write
  `⟦unsicher: N⟧` into score `rawValue`. Validation rejects it, as designed, but
  the paid response is lost (kept only in `.failed-*`).
- **Gemini at `thinking_level=high`** usually exceeds the 300 s per-attempt
  timeout (`gemini.REQUEST_TIMEOUT_MS`). Do not use it.
- **Timeouts leave no trace** in the output folder (no `.failed-*`, since there
  is no response); they appear only in the `batch` output.
- **Claude cost precision:** `run.json` stores the Claude cost as a long float
  string (`Decimal(str(float))`). Harmless, but untidy.

## Next steps (priority order)

### 1. Cross-check with GPT-6.1 Terra

**Proposed design:**
- Add a `cross_check_model: str | None` setting: local config key and/or
  `batch --cross-check gpt-6.1-terra`. It is **not** part of the primary
  fingerprint, because it does not change the primary observation.
- In `pipeline._request_run`, after the primary response validates and before
  `publish`:
  - Request the second model into `staging/crosscheck/`, writing
    `interaction.json`, `raw.json` and a small `run.json` with usage, model and
    SDK version.
  - Write the cross-check issues into the same `review.json`, so the run is
    still published atomically.
- **Issue logic:**
  - Compare the sorted lists of non-null entry dates of both observations.
    This is exactly what the simulation measured.
  - A mismatch adds reason `date_disagreement` to each primary entry whose date
    is missing from the other list. If the primary has no dated entries, the
    issue is photo-level (`entry_index=None`).
  - Never auto-select or auto-correct a date (AGENTS.md: human authority).
- **Backfill:** for an existing run without `crosscheck/`, `batch` should
  request only the cross-check. That requires updating `review.json` in place,
  atomically via `atomic.py`. Alternatively, compute issues at review time;
  decide and document which.
- **Open decision, if the cross-check request fails:** recommended is to
  publish the primary run with reason `cross_check_failed`, so a provider
  outage does not discard a paid primary response. The alternative is to fail
  the whole run.
- **Approved refinements:** a revision can change dates. Re-run the
  comparison against the active observation, or flag the cross-check as stale.
- **Interfaces to update:** `review_targets` (`normalize.py:108`) for refine
  prompts, review output (`cli/review.py`) and README.
- **Tests (offline):** extend `FakeGemini` and `fake_openai` in
  `tests/conftest.py`; both fixtures can be active at once (see
  `test_batch_model_option_routes_to_openai` in `tests/test_cli.py`). Cover
  agreement, disagreement, multi-day pages, cross-check failure and backfill.

### 2. Deterministic date plausibility flags

- **`date_outside_corpus_year`:** in `normalize_observation`
  (`normalize.py:56`), when `local.default_corpus_year` is set and a dated
  entry's year differs. Purely local; needs config passed in. A review-time
  check also works.
- **`date_out_of_sequence`:** needs neighbor pages. Compute it at review time
  across runs ordered by photo capture time (from the file name) or by
  `run.json` photo path. Flag a page whose dates fall outside
  [previous page's maximum, next page's minimum].
  - Handle multi-day pages, undated pages and re-photographed duplicates.
  - The file name is only an ordering hint. AGENTS.md forbids taking dates
    from file names, so this check may only flag, never set a date.

### 3. Default thinking level `medium`

- Set `ProjectConfig.thinking_level = "medium"` (`config.py`) and update the
  `--thinking-level` help in `cli/parser.py`.
- Reason: without an explicit level, Gemini's thinking tokens varied from 0.7k
  to 17.8k between runs of the same page, and the output dropped text.
- This changes the fingerprint; the cost is already accounted for in "Known
  problems".

### Later

4. **Manual date correction:** for example a `correct-date --run R --entry N
   --date D` decision, recorded like approve/reject in `runs.py` and applied in
   `resolve_days`.
5. **Uncertain score state:** schema v3, e.g. state `uncertain` with `rawValue`
   allowed. Touches the prompt, `ScoreObservation` validation, render and eval.
6. **Gold set:** grow from 2 to about 6–8 verified pages. This is the biggest
   lever for evaluation confidence; the text-CER gap between Gemini and Terra
   `original` is not yet significant.
7. **Small fixes:**
   - Write a `.failed-*` marker with the error for timeouts.
   - Format the Claude cost as a clean decimal.
   - Commit a benchmark runner script (the one used lives in the ignored
     `.tmp/run-bench.sh`).

## Recommendations and constraints

- **Paid requests need explicit user consent.** Approximate cost per page:

  | Configuration | USD/page |
  |---|---|
  | Gemini medium | 0.063 (doubles from 2027-01-01) |
  | Terra medium | 0.020 |
  | Terra medium, `original` | 0.029 |
  | Sonnet via CLI | 0.067 |

  Use `--photos` to limit runs and `--output-dir private/...` for experiments,
  never the vault.
- **Never auto-apply corrections** or auto-select competing runs; flags only.
- **Keep diary content out of tracked files,** including tests (synthetic
  fixtures only), docs and issue text.
- **Use red-green TDD** for each step, and Conventional Commits.
- **Run docs-list** and keep front matter on new docs.
