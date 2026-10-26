from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Iterable
from datetime import date
from typing import Any

from diary_photo_transcription.schemas import (
    CalendarDay,
    DateCertainty,
    DayEntry,
    FieldLabel,
    NormalizationResult,
    PhotoObservation,
    PhotoProvenance,
    ReviewIssue,
    ScoreState,
)

_REASONS = (
    (re.compile(r"⟦unleserlich⟧"), "unreadable_text"),
    (re.compile(r"⟦unsicher: [^⟧\n]+⟧"), "uncertain_text"),
)


def _marked(value: str) -> bool:
    return any(pattern.search(value) for pattern, _ in _REASONS)


def uncertain_passages(value: Any, path: str = "photo") -> list[str]:
    """List every marked text with its location, e.g. `photo.entries[1].paragraphs[2]: …`."""
    if isinstance(value, str):
        return [f"{path}: {value}"] if _marked(value) else []
    if isinstance(value, dict):
        return [
            text
            for key, child in value.items()
            for text in uncertain_passages(child, f"{path}.{key}")
        ]
    if isinstance(value, (list, tuple)):
        return [
            text
            for index, child in enumerate(value, start=1)
            for text in uncertain_passages(child, f"{path}[{index}]")
        ]
    return []


def _uncertainty_reasons(*values: Any) -> tuple[str, ...]:
    """Return stable review codes for uncertainty markers anywhere in `values`."""
    passages = uncertain_passages(values)
    return tuple(reason for pattern, reason in _REASONS if any(pattern.search(p) for p in passages))


def normalize_observation(
    observation: PhotoObservation, provenance: PhotoProvenance
) -> NormalizationResult:
    """Group certain visible dates without changing model-produced text."""
    by_date: dict[date, list[DayEntry]] = defaultdict(list)
    review_issues: list[ReviewIssue] = []

    # Photo-level concerns apply to each existing entry, or to the photo itself.
    photo_text = observation.model_dump(exclude={"entries"})
    if not observation.entries and (photo_reasons := _uncertainty_reasons(photo_text)):
        review_issues.append(ReviewIssue(entry_index=None, reasons=photo_reasons))
    for index, entry in enumerate(observation.entries, start=1):
        reasons: list[str] = []
        if entry.date_certainty is DateCertainty.UNKNOWN:
            reasons.append("unknown_date")
        elif entry.date_certainty is DateCertainty.UNCERTAIN:
            reasons.append("uncertain_date")
        reasons.extend(_uncertainty_reasons(entry.model_dump(), photo_text))
        # Missing standard-form evidence is a review concern, not invalid data:
        # dates may legitimately occur elsewhere, or use the configured corpus year.
        if entry.date is not None and not any(
            field.label is FieldLabel.DATUM and field.items for field in entry.fields
        ):
            reasons.append("unsupported_date")

        if any(score.state is ScoreState.ILLEGIBLE for score in entry.scores):
            reasons.append("illegible_score")
        if reasons:
            review_issues.append(ReviewIssue(entry_index=index, reasons=tuple(reasons)))

        if entry.date_certainty is not DateCertainty.CERTAIN:
            continue
        assert entry.date is not None
        by_date[entry.date].append(
            DayEntry(
                source=provenance,
                source_entry_index=index,
                paragraphs=entry.paragraphs,
                fields=entry.fields,
                scores=entry.scores,
                crossed_out_corrections_omitted=entry.crossed_out_corrections_omitted,
                visual_notes=entry.visual_notes,
            )
        )

    days = tuple(
        CalendarDay(schema_version=observation.schema_version, date=day, entries=tuple(entries))
        for day, entries in sorted(by_date.items())
    )
    return NormalizationResult(days=days, review_issues=tuple(review_issues))


def review_targets(observation: PhotoObservation, issues: Iterable[ReviewIssue]) -> list[str]:
    """Human- and model-readable list of everything a reviewer should re-check."""
    targets = uncertain_passages(observation.model_dump(by_alias=True))
    for issue in issues:
        if issue.entry_index is None:
            continue
        entry = observation.entries[issue.entry_index - 1]
        label = f"Eintrag #{issue.entry_index}"
        if {"unknown_date", "uncertain_date"} & set(issue.reasons):
            targets.append(f"{label}: Datum ist unsicher oder unbekannt")
        if "unsupported_date" in issue.reasons:
            targets.append(f"{label}: Datum {entry.date} ohne Beleg im Datum-Feld")
        targets.extend(
            f"{label}: Score Position {score.position} ({score.symbol_description}) ist unleserlich"
            for score in entry.scores
            if score.state is ScoreState.ILLEGIBLE
        )
    return targets
