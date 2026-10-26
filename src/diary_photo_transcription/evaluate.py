from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
from itertools import zip_longest

from diary_photo_transcription.schemas import (
    FieldLabel,
    FormField,
    PhotoObservation,
    ScoreObservation,
)


def _levenshtein_distance(seq1: str, seq2: str) -> int:
    """Calculate the Levenshtein edit distance between two character sequences."""
    if len(seq1) < len(seq2):
        seq1, seq2 = seq2, seq1
    if not seq2:
        return len(seq1)
    previous = list(range(len(seq2) + 1))
    for x, left in enumerate(seq1, start=1):
        current = [x]
        for y, right in enumerate(seq2, start=1):
            current.append(
                min(previous[y] + 1, current[y - 1] + 1, previous[y - 1] + (left != right))
            )
        previous = current
    return previous[-1]


def _ratio(part: int, total: int, empty: float = 1.0) -> float:
    return part / total if total else empty


def calculate_cer(reference: str, hypothesis: str) -> float:
    """Calculate Character Error Rate (CER) = Levenshtein Distance / len(reference)."""
    return _ratio(
        _levenshtein_distance(reference, hypothesis), len(reference), float(bool(hypothesis))
    )


@dataclass(frozen=True, slots=True)
class ScoreMismatch:
    position: int
    gold_state: str
    pred_state: str
    gold_raw: str | None
    pred_raw: str | None


@dataclass(frozen=True, slots=True)
class ScoreEvaluationResult:
    total_positions: int
    state_matches: int
    value_matches: int
    exact_matches: int
    mismatches: tuple[ScoreMismatch, ...] = ()

    @property
    def state_accuracy(self) -> float:
        return _ratio(self.state_matches, self.total_positions)

    @property
    def value_accuracy(self) -> float:
        return _ratio(self.value_matches, self.total_positions)

    @property
    def position_accuracy(self) -> float:
        return _ratio(self.exact_matches, self.total_positions)


def evaluate_scores(
    gold_scores: tuple[ScoreObservation, ...],
    pred_scores: tuple[ScoreObservation, ...],
) -> ScoreEvaluationResult:
    """Evaluate predicted score observations against gold standard positions."""
    gold_by_pos = {s.position: s for s in gold_scores}
    pred_by_pos = {s.position: s for s in pred_scores}
    positions = sorted(set(gold_by_pos) | set(pred_by_pos))
    state_matches = value_matches = exact_matches = 0
    mismatches: list[ScoreMismatch] = []
    for pos in positions:
        gold = gold_by_pos.get(pos)
        pred = pred_by_pos.get(pos)
        state_ok = gold is not None and pred is not None and gold.state == pred.state
        value_ok = (
            gold is not None
            and pred is not None
            and (gold.value, gold.raw_value) == (pred.value, pred.raw_value)
        )
        state_matches += state_ok
        value_matches += value_ok
        exact_matches += state_ok and value_ok
        if not (state_ok and value_ok):
            mismatches.append(
                ScoreMismatch(
                    position=pos,
                    gold_state=gold.state.value if gold else "missing",
                    pred_state=pred.state.value if pred else "missing",
                    gold_raw=gold.raw_value if gold else None,
                    pred_raw=pred.raw_value if pred else None,
                )
            )
    return ScoreEvaluationResult(
        len(positions), state_matches, value_matches, exact_matches, tuple(mismatches)
    )


@dataclass(frozen=True, slots=True)
class FieldEvaluationResult:
    present_precision: float
    present_recall: float
    item_cer: float
    mismatches: tuple[str, ...] = ()


def _precision_recall(gold: set[FieldLabel], pred: set[FieldLabel]) -> tuple[float, float]:
    hits = len(gold & pred)
    return _ratio(hits, len(pred)), _ratio(hits, len(gold))


def _field_text(fields: tuple[FormField, ...]) -> str:
    return "\n".join(f"{f.label}: {' | '.join(i.text for i in f.items)}" for f in fields)


def evaluate_fields(
    gold_fields: tuple[FormField, ...],
    pred_fields: tuple[FormField, ...],
) -> FieldEvaluationResult:
    """Evaluate form fields: precision/recall on labels and item content similarity.

    Absent labels need no metric: the schema makes them the complement of the present ones.
    """
    gold_by_label = {f.label: f for f in gold_fields}
    pred_by_label = {f.label: f for f in pred_fields}
    gold_present, pred_present = set(gold_by_label), set(pred_by_label)
    present_precision, present_recall = _precision_recall(gold_present, pred_present)

    mismatches = [f"Missing present label: {m.value}" for m in sorted(gold_present - pred_present)]
    mismatches += [
        f"Unexpected extra label: {e.value}" for e in sorted(pred_present - gold_present)
    ]
    mismatches += [
        f"Field content/state differs: {label.value}"
        for label in sorted(gold_present & pred_present)
        if gold_by_label[label] != pred_by_label[label]
    ]
    return FieldEvaluationResult(
        present_precision=present_precision,
        present_recall=present_recall,
        item_cer=calculate_cer(_field_text(gold_fields), _field_text(pred_fields)),
        mismatches=tuple(mismatches),
    )


@dataclass(frozen=True, slots=True)
class TextEvaluationResult:
    edit_distance: int
    reference_length: int
    paragraph_count_gold: int
    paragraph_count_pred: int
    missing_passages: tuple[str, ...] = ()
    inserted_passages: tuple[str, ...] = ()

    @property
    def cer(self) -> float:
        return _ratio(self.edit_distance, self.reference_length, float(bool(self.edit_distance)))


def evaluate_paragraphs(
    gold_paragraphs: tuple[str, ...],
    pred_paragraphs: tuple[str, ...],
) -> TextEvaluationResult:
    """Evaluate free text paragraphs with CER and passage alignment."""
    gold_full = "\n\n".join(gold_paragraphs)
    pred_full = "\n\n".join(pred_paragraphs)
    missing: list[str] = []
    inserted: list[str] = []
    for tag, i1, i2, j1, j2 in SequenceMatcher(None, gold_full, pred_full).get_opcodes():
        if tag in ("delete", "replace") and len(deleted := gold_full[i1:i2].strip()) > 10:
            missing.append(deleted)
        if tag in ("insert", "replace") and len(added := pred_full[j1:j2].strip()) > 10:
            inserted.append(added)
    return TextEvaluationResult(
        edit_distance=_levenshtein_distance(gold_full, pred_full),
        reference_length=len(gold_full),
        paragraph_count_gold=len(gold_paragraphs),
        paragraph_count_pred=len(pred_paragraphs),
        missing_passages=tuple(missing),
        inserted_passages=tuple(inserted),
    )


@dataclass(frozen=True, slots=True)
class OverallEvaluationReport:
    is_exact_match: bool
    date_match: bool
    text_report: TextEvaluationResult
    score_report: ScoreEvaluationResult
    field_report: FieldEvaluationResult
    notes: tuple[str, ...] = ()


def evaluate_observation(
    gold: PhotoObservation,
    pred: PhotoObservation,
) -> OverallEvaluationReport:
    """Compare every entry in source order; no automatic date alignment or merging.

    Text CER sums edit distances per entry / total reference characters.
    Field ratios/CER are macro averages over entry slots.
    Exact match covers the entire structured observation, including all states.
    """
    notes = []
    if len(gold.entries) != len(pred.entries):
        notes.append(f"Entry count mismatch: gold={len(gold.entries)}, pred={len(pred.entries)}")
    dates_match = True
    texts: list[TextEvaluationResult] = []
    scores: list[ScoreEvaluationResult] = []
    fields: list[FieldEvaluationResult] = []
    field_mismatches: list[str] = []
    for index, (g, p) in enumerate(zip_longest(gold.entries, pred.entries), start=1):
        if g is None or p is None or (g.date, g.date_certainty) != (p.date, p.date_certainty):
            dates_match = False
            notes.append(f"Entry {index}: date mismatch or missing/extra entry")
        if g is not None and p is not None and g != p:
            notes.append(f"Entry {index}: structured content/state differs")
        texts.append(evaluate_paragraphs(g.paragraphs if g else (), p.paragraphs if p else ()))
        scores.append(evaluate_scores(g.scores if g else (), p.scores if p else ()))
        report = evaluate_fields(
            g.fields if g else (),
            p.fields if p else (),
        )
        fields.append(report)
        field_mismatches.extend(f"Entry {index}: {m}" for m in report.mismatches)

    def mean(attribute: str, empty: float = 1.0) -> float:
        return _ratio(sum(getattr(r, attribute) for r in fields), len(fields), empty)

    return OverallEvaluationReport(
        is_exact_match=gold == pred,
        date_match=dates_match,
        text_report=TextEvaluationResult(
            sum(t.edit_distance for t in texts),
            sum(t.reference_length for t in texts),
            sum(t.paragraph_count_gold for t in texts),
            sum(t.paragraph_count_pred for t in texts),
            tuple(passage for t in texts for passage in t.missing_passages),
            tuple(passage for t in texts for passage in t.inserted_passages),
        ),
        score_report=ScoreEvaluationResult(
            sum(s.total_positions for s in scores),
            sum(s.state_matches for s in scores),
            sum(s.value_matches for s in scores),
            sum(s.exact_matches for s in scores),
            tuple(m for s in scores for m in s.mismatches),
        ),
        field_report=FieldEvaluationResult(
            mean("present_precision"),
            mean("present_recall"),
            mean("item_cer", 0.0),
            tuple(field_mismatches),
        ),
        notes=tuple(notes),
    )
