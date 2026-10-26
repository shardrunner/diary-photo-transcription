---
summary: Benchmark of Gemini 3.8 Flash, GPT-6.1 Terra and Claude Sonnet 5.5 on accuracy, reliability, cost and latency.
read_when:
  - Choosing or changing the model, thinking level or image resolution
  - Re-running the benchmark after a prompt, schema or SDK change
---

# Model evaluation (2026-10-26)

**Question:** Which model and setting should be the default for source-faithful
transcription of handwritten German diary pages? The criteria were accuracy, how
often the model is confidently wrong, reliability, cost and latency.

**Result:** No configuration wins on every axis. Gemini 3.8 Flash (medium) is
the most faithful transcriber. GPT-6.1 Terra is the most reliable at reading
dates and costs about a third as much. Gemini's main weakness, misread years,
can be caught with a free deterministic check, while weaker text fidelity
cannot be fixed afterwards. The recommendation is therefore **Gemini 3.8 Flash at
medium thinking, plus a year-plausibility review flag**. Terra medium with
`original` image detail is the strongest alternative.

## Setup

- **Identical pipeline for all models:** prompt v10, one strict JSON schema,
  Pydantic domain validation and the same artifacts. Adapters exist for the
  Gemini Interactions API (`google-genai` 2.31.0), the OpenAI Responses API
  (`openai` 3.39.0, `store=false`) and Claude Code print mode (`claude -p`
  2.1.310, read-only and without session persistence).
- **Configurations:** model × thinking level (Gemini `thinking_level`, OpenAI
  `reasoning.effort`, Claude `--effort`) × image resolution (Gemini
  `media_resolution` high/ultra_high, OpenAI `detail` high/original). Claude Code
  has no resolution flag; its Read tool decides how the image is sized.
- **Accuracy set:** 2 hand-verified gold pages, each run 3 times per
  configuration (n = 6), so run-to-run variance is visible.
- **Date set:** 15 pages, the same for every configuration, with verified page
  dates. The set is stratified: regular pages, multi-day pages with 2 and 4
  dates, an undated page, and pages with known hard handwriting.
- **Metrics** (`scripts/model_benchmark.py`; it outputs aggregates only and no
  diary text):
  - **Text CER:** character error rate of the free text, edits divided by
    reference characters.
  - **Form item CER:** the same measure for the left-page form items.
  - **Score accuracy:** state and value correct, per position.
  - **Omitted passages:** gold spans longer than 10 characters that the model
    dropped.
  - **Dates correct:** the exact set of dates per page.
  - **Confident wrong dates:** pages with a wrong date that the model marked
    `certain`.
  - **Failed:** timeouts plus schema-invalid responses.
  - **Cost:** estimated from reported usage at standard list prices; Claude
    reports its own cost.

## Results

| Configuration | Text CER ↓ (range of 3 runs) | Form CER ↓ | Scores ↑ | Omitted passages/page ↓ | Dates ↑ | Confident wrong dates ↓ | Failed ↓ | USD/page ↓ | Latency median ↓ |
|---|---|---|---|---|---|---|---|---|---|
| Gemini 3.8 Flash, medium | **2.2%** (1.8–2.6) | **9.2%** | **97.1%** | **0.0** | 11/15 | 3 | **0/19** | 0.063 | 140 s |
| Gemini 3.8 Flash, medium, ultra_high | 1.9% (1.0–3.1) | 6.9% | 85.9% | 0.2 | 7/11 | 4 | 4/19 | 0.046 | 101 s |
| Gemini 3.8 Flash, high ¹ | n/a | n/a | n/a | n/a | 5/5 | 0 | 7/12 | 0.109 | 259 s |
| GPT-6.1 Terra, medium | 4.1% (3.9–4.3) | 21.8% | **97.1%** | 1.0 | **14/15** | **1** | **0/19** | **0.020** | 59 s |
| GPT-6.1 Terra, medium, original | 3.4% (2.4–4.1) | 13.3% | 96.5% | 1.6 | **14/15** | **1** | 1/19 | 0.029 | 69 s |
| GPT-6.1 Terra, high | 5.0% (4.7–5.2) | 19.0% | 96.1% | 1.0 | **14/15** | **1** | **0/19** | 0.033 | 88 s |
| GPT-6.1 Terra, high, original | 2.9% (2.2–3.6) | 11.6% | 94.1% | 2.0 | 13/14 | **1** | 2/19 | 0.042 | 90 s |
| Claude Sonnet 5.5, medium ² | 2.5% (2.1–2.7) | 16.6% | 93.1% | 2.2 | 12/14 | **1** | 1/19 | 0.067 | **23 s** |

¹ Stopped after 12 of 19 requests. 7 of them hit the 300 s per-attempt timeout
(the SDK makes 3 attempts), including both gold pages, so there are no accuracy
numbers. ² Claude Code is run as an agent harness: cost and latency include its
system prompt and one Read tool turn.

Dates are counted over successful pages only. Failed requests appear only in
the "Failed" column.

## Findings

1. **Transcription fidelity:** Gemini medium has the lowest error on text and
   forms and the only zero-omission result. Terra at `high` detail has about
   twice Gemini's text CER. The full-resolution `original` detail closes much
   of that gap (5.0 → 2.9%), but Terra still drops more passages.
2. **Dates are where models are confidently wrong.** On 2–3 of 15 pages Gemini
   reads the year as 2020 or 2024 instead of 2026 and marks it `certain`. On one
   page it also merges two days into one. Every Terra configuration misses only
   the same single, barely legible date, which a human reader also misread. A
   wrong date silently files a note under the wrong day, which makes this the
   most consequential error type.
3. **More thinking did not mean more accuracy.** Gemini `high` mostly timed
   out and cost 1.7× as much as medium. Terra `high` was not better than
   `medium` and cost 1.6× as much. For Terra, image resolution mattered more
   than reasoning effort.
4. **Reliability:** At the higher settings (Gemini `ultra_high`, Terra
   `original`), models began writing uncertainty markers or out-of-range
   values into numeric score fields. Schema validation rejected these
   responses, which worked as designed. The failures also show that the
   schema has no way to mark an uncertain score.
5. **Cost and speed:** Terra medium costs a third of Gemini medium, and
   Gemini's introductory rates double on 2027-01-01. Sonnet is about 6× faster
   than Gemini. For a personal batch job of one page a day, every option costs
   under 50 USD a year, so cost and latency are secondary to correctness.
6. **Review burden:** Terra raises about 1.2 review issues per page, Gemini
   about 0.3. More flags mean more human review. On this data the extra flags
   did not come with better text.

## Decision

- **Default:** Gemini 3.8 Flash at medium thinking, set explicitly. Without an
  explicit level, the provider default varied from 0.7k to 18k thinking tokens
  between runs.
- **Mitigation:** add a deterministic review flag for page years outside the
  configured corpus year. That turns Gemini's confident date errors into
  visible review items at no API cost.
- **Revisit Terra** (medium, `original`) if the gold set grows and its text
  gap stays under about 1 percentage point, or if cost becomes relevant.

## Limitations

- **Small sample:** only 2 gold pages (n = 6 runs per configuration). Text CER
  ranges overlap between Gemini medium and Terra `original`, so that gap is
  indicative, not significant. The date set (15 pages) is the stronger
  signal.
- **Annotation:** a single annotator (the diary author) verified the gold data.
- **Prompt origin:** the prompt was developed on Gemini, which may favor it.
- **Load:** latency was measured under parallel load (up to 6 configurations ×
  4 concurrent requests) and is indicative only.
- **Snapshot:** model and price data are from 2026-10-26.

## Reproduce

```bash
B=private/benchmark/$(date +%F)/terra-medium-original && mkdir -p $B
uv run diary-photo-transcription batch --model gpt-6.1-terra --thinking-level medium \
  --media-resolution ultra_high --output-dir $B/rep1 --photos <date subset> | tee $B/batch.log
uv run python scripts/model_benchmark.py private/benchmark/$(date +%F)
```
