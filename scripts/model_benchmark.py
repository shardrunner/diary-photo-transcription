#!/usr/bin/env python3
"""Aggregate a model benchmark into content-free metrics.

Layout: BENCH/<config>/<rep>/<run>/ as written by `batch --output-dir`. Gold
observations are matched by photo name (GOLD/<photo stem>.json); page dates by
DATES (photo name -> list of ISO dates, [] for an undated page). Only rep1 is
expected to contain the full date subset; further reps repeat the gold photos.
Failed requests (timeouts leave no run) are counted from `✗` lines in
BENCH/<config>/*.log, the saved `batch` output. Prints a Markdown table and
optionally writes the metrics as JSON. No diary
text leaves this script.
"""

from __future__ import annotations

import argparse
import json
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any

from diary_photo_transcription.evaluate import evaluate_observation
from diary_photo_transcription.runs import active_dir, discover_runs, read_issues, read_observation
from diary_photo_transcription.schemas import PhotoObservation


def _photo_name(run: Path) -> str:
    meta = json.loads((run / "run.json").read_text(encoding="utf-8"))
    return Path(meta["provenance"]["photoPath"]).name


def _mean(values: list[float]) -> float | None:
    return statistics.mean(values) if values else None


def _pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.1%}"


def _num(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.1f}"


def _quantile(values: list[float], q: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, round(q * (len(ordered) - 1)))]


def evaluate_config(config_dir: Path, gold_dir: Path, dates: dict[str, list[str]]) -> dict:
    per_rep_text: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    item_cer: list[float] = []
    score = [0, 0]
    missing_passages = 0
    gold_samples = 0
    date_pages = date_correct = confident_wrong = 0
    usage: list[dict[str, Any]] = []
    issues: list[int] = []
    failed = sum(
        line.count("✗") for log in config_dir.glob("*.log") for line in log.open(encoding="utf-8")
    )
    for rep in sorted(p for p in config_dir.iterdir() if p.is_dir()):
        for run in discover_runs(rep):
            photo = _photo_name(run)
            meta = json.loads((run / "run.json").read_text(encoding="utf-8"))
            usage.append(meta["usage"])
            issues.append(len(read_issues(active_dir(run))))
            pred = read_observation(active_dir(run))
            gold_path = gold_dir / f"{Path(photo).stem}.json"
            if gold_path.exists():
                gold = PhotoObservation.model_validate_json(gold_path.read_text("utf-8"))
                report = evaluate_observation(gold, pred)
                per_rep_text[rep.name][0] += report.text_report.edit_distance
                per_rep_text[rep.name][1] += report.text_report.reference_length
                item_cer.append(report.field_report.item_cer)
                score[0] += report.score_report.exact_matches
                score[1] += report.score_report.total_positions
                missing_passages += len(report.text_report.missing_passages)
                gold_samples += 1
            if rep.name == "rep1" and photo in dates:
                expected = sorted(dates[photo])
                found = sorted(str(e.date) for e in pred.entries if e.date is not None)
                date_pages += 1
                date_correct += found == expected
                confident_wrong += any(
                    e.date is not None
                    and str(e.date) not in expected
                    and e.date_certainty == "certain"
                    for e in pred.entries
                )
    rep_cer = [edits / length for edits, length in per_rep_text.values() if length]
    seconds = [u["requestDurationSeconds"] for u in usage]
    return {
        "requests": len(usage) + failed,
        "failedRequests": failed,
        "goldSamples": gold_samples,
        "textCer": _mean(rep_cer),
        "textCerRange": [min(rep_cer), max(rep_cer)] if rep_cer else None,
        "formItemCer": _mean(item_cer),
        "scoreAccuracy": score[0] / score[1] if score[1] else None,
        "missingPassagesPerGoldPage": missing_passages / gold_samples if gold_samples else None,
        "datePages": date_pages,
        "datesCorrect": date_correct,
        "confidentWrongDatePages": confident_wrong,
        "reviewIssuesPerPage": statistics.mean(issues),
        "costUsdPerPage": statistics.mean(float(u["estimatedStandardCostUsd"]) for u in usage),
        "latencyMedianSeconds": statistics.median(seconds),
        "latencyP90Seconds": _quantile(seconds, 0.9),
        "thinkingTokensMean": statistics.mean(u["thinkingTokens"] for u in usage),
    }


def markdown(results: dict[str, dict]) -> str:
    rows = [
        "| Configuration | Text CER ↓ (range over reps) | Form item CER ↓ | Score acc. ↑ "
        "| Omitted passages/page ↓ | Dates correct ↑ | Confident wrong dates ↓ | Failed ↓ "
        "| Review issues/page | USD/page ↓ | Latency median / p90 ↓ | Thinking tokens |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for name, r in results.items():
        spread = r["textCerRange"]
        text = _pct(r["textCer"]) + (f" ({spread[0]:.1%}-{spread[1]:.1%})" if spread else "")
        rows.append(
            f"| {name} | {text} | {_pct(r['formItemCer'])} "
            f"| {_pct(r['scoreAccuracy'])} | {_num(r['missingPassagesPerGoldPage'])} "
            f"| {r['datesCorrect']}/{r['datePages']} "
            f"| {r['confidentWrongDatePages']} | {r['failedRequests']}/{r['requests']} "
            f"| {r['reviewIssuesPerPage']:.1f} | {r['costUsdPerPage']:.3f} "
            f"| {r['latencyMedianSeconds']:.0f} s / {r['latencyP90Seconds']:.0f} s "
            f"| {r['thinkingTokensMean']:,.0f} |"
        )
    return "\n".join(rows)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Aggregate a model benchmark into content-free metrics."
    )
    parser.add_argument("bench", type=Path)
    parser.add_argument("--gold-dir", type=Path, default=Path("private/gold"))
    parser.add_argument("--dates", type=Path, default=Path("private/gold/dates.json"))
    parser.add_argument("--json-out", type=Path)
    args = parser.parse_args()
    dates = {
        k: v
        for k, v in json.loads(args.dates.read_text(encoding="utf-8")).items()
        if not k.startswith("_")
    }
    results = {
        config.name: evaluate_config(config, args.gold_dir, dates)
        for config in sorted(p for p in args.bench.iterdir() if p.is_dir())
    }
    print(markdown(results))
    if args.json_out:
        args.json_out.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
