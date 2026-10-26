from __future__ import annotations

import itertools
from datetime import date

import pytest

from diary_photo_transcription.evaluate import (
    _levenshtein_distance,
    calculate_cer,
    evaluate_fields,
    evaluate_observation,
    evaluate_paragraphs,
    evaluate_scores,
)
from diary_photo_transcription.schemas import (
    Completion,
    DateCertainty,
    FieldItem,
    FieldLabel,
    FormField,
    LayoutObservation,
    ObservedEntry,
    OverviewTag,
    PhotoObservation,
    PhotoOverview,
    ScoreObservation,
    ScoreState,
)


def test_cer_exact_match() -> None:
    assert calculate_cer("Hallo Welt", "Hallo Welt") == 0.0


def test_cer_with_edits() -> None:
    # "Hallo" vs "Hello" -> 1 edit (substitution) / 5 chars = 0.2
    assert round(calculate_cer("Hallo", "Hello"), 2) == 0.2


def test_cer_empty_reference() -> None:
    assert calculate_cer("", "") == 0.0
    assert calculate_cer("", "Hallo") == 1.0


def test_evaluate_scores_exact_match() -> None:
    scores = (
        ScoreObservation(
            position=1, symbol_description="Stundenglas", state=ScoreState.STRUCK_THROUGH
        ),
        ScoreObservation(
            position=2,
            symbol_description="Schlaf",
            state=ScoreState.WRITTEN,
            raw_value="4",
            value=4,
        ),
    )
    result = evaluate_scores(scores, scores)
    assert result.position_accuracy == 1.0
    assert result.state_accuracy == 1.0
    assert result.value_accuracy == 1.0
    assert result.mismatches == ()


def test_evaluate_scores_with_shift() -> None:
    gold = (
        ScoreObservation(
            position=1, symbol_description="Stundenglas", state=ScoreState.STRUCK_THROUGH
        ),
        ScoreObservation(
            position=2,
            symbol_description="Schlaf",
            state=ScoreState.WRITTEN,
            raw_value="4",
            value=4,
        ),
    )
    shifted = (
        ScoreObservation(
            position=1,
            symbol_description="Stundenglas",
            state=ScoreState.WRITTEN,
            raw_value="4",
            value=4,
        ),
        ScoreObservation(
            position=2,
            symbol_description="Schlaf",
            state=ScoreState.WRITTEN,
            raw_value="0",
            value=0,
        ),
    )
    result = evaluate_scores(gold, shifted)
    assert result.state_accuracy == 0.5
    assert len(result.mismatches) == 2


def test_evaluate_fields_precision_recall() -> None:
    gold_fields = (
        FormField(
            label=FieldLabel.PRO,
            raw_label_text="Pro:",
            items=(FieldItem(text="früh ins Bett", completion=Completion.UNMARKED),),
        ),
    )
    pred_fields = (
        FormField(
            label=FieldLabel.PRO,
            raw_label_text="Pro:",
            items=(FieldItem(text="früh ins Bett", completion=Completion.UNMARKED),),
        ),
        FormField(
            label=FieldLabel.CONS,
            raw_label_text="Contra:",
            items=(FieldItem(text="kein Sport", completion=Completion.UNMARKED),),
        ),
    )
    result = evaluate_fields(gold_fields, pred_fields)
    assert result.present_precision == 0.5
    assert result.present_recall == 1.0


def test_evaluate_paragraphs() -> None:
    gold = ("Erster Absatz.", "Zweiter Absatz.")
    pred = ("Erster Absatz.", "Zweiter Absatz mit Tippfehler.")
    result = evaluate_paragraphs(gold, pred)
    assert result.cer > 0.0
    assert result.paragraph_count_gold == 2
    assert result.paragraph_count_pred == 2


def test_evaluate_full_observation() -> None:
    entry = ObservedEntry(
        date_certainty=DateCertainty.CERTAIN,
        date=date(2026, 7, 7),
        fields=(),
        absent_labels=tuple(FieldLabel),
        scores=(),
        paragraphs=("Text.",),
        crossed_out_corrections_omitted=False,
        visual_notes=(),
    )
    obs = PhotoObservation(
        schema_version=2,
        photo_overview=PhotoOverview(tags=(OverviewTag.SPARSE_PAGE,), note="Test"),
        layout=LayoutObservation(follows_expected_layout=True),
        entries=(entry,),
        visual_notes=(),
    )
    report = evaluate_observation(obs, obs)
    assert report.is_exact_match is True
    assert report.text_report.cer == 0.0


def test_distance_matches_matrix_reference() -> None:
    words = ["".join(chars) for n in range(4) for chars in itertools.product("aä", repeat=n)]
    for a, b in itertools.product(words, repeat=2):
        matrix = [[0] * (len(b) + 1) for _ in range(len(a) + 1)]
        for i in range(len(a) + 1):
            matrix[i][0] = i
        for j in range(len(b) + 1):
            matrix[0][j] = j
        for i in range(1, len(a) + 1):
            for j in range(1, len(b) + 1):
                matrix[i][j] = min(
                    matrix[i - 1][j] + 1,
                    matrix[i][j - 1] + 1,
                    matrix[i - 1][j - 1] + (a[i - 1] != b[j - 1]),
                )
        expected = matrix[-1][-1]
        assert _levenshtein_distance(a, b) == expected
        assert calculate_cer(a, b) == (expected / len(a) if a else float(bool(b)))


def test_paragraph_movement_costs_edits(make_observation):
    gold = make_observation(2)
    a = gold.entries[0].model_copy(update={"paragraphs": ("alpha", "beta")})
    b = gold.entries[1].model_copy(update={"paragraphs": ("gamma",)})
    gold = gold.model_copy(update={"entries": (a, b)})
    pred = gold.model_copy(
        update={
            "entries": (
                a.model_copy(update={"paragraphs": ("alpha",)}),
                b.model_copy(update={"paragraphs": ("beta", "gamma")}),
            )
        }
    )
    report = evaluate_observation(gold, pred)
    assert report.text_report.cer == 12 / 16
    assert not report.is_exact_match


@pytest.mark.parametrize(("gold_count", "pred_count"), [(2, 1), (1, 2), (2, 0), (0, 2)])
def test_all_entries_are_counted(make_observation, gold_count: int, pred_count: int) -> None:
    report = evaluate_observation(make_observation(gold_count), make_observation(pred_count))
    assert not report.is_exact_match
    assert not report.date_match
    assert report.text_report.cer > 0
    assert report.text_report.paragraph_count_gold == gold_count
    assert report.text_report.paragraph_count_pred == pred_count
    assert report.notes


@pytest.mark.parametrize("change", ["completion", "struck_through"])
def test_state_only_differences_are_not_exact(make_observation, change: str) -> None:
    gold = make_observation(2)
    item = FieldItem(text="Example", completion="unmarked")
    field = FormField(label="ToDos", items=(item,))
    entry = gold.entries[1].model_copy(
        update={
            "fields": (field,),
            "absent_labels": tuple(label for label in FieldLabel if label != field.label),
        }
    )
    gold = gold.model_copy(update={"entries": (gold.entries[0], entry)})
    changed = item.model_copy(update={change: "fulfilled" if change == "completion" else True})
    pred_entry = entry.model_copy(
        update={"fields": (field.model_copy(update={"items": (changed,)}),)}
    )
    pred = gold.model_copy(update={"entries": (gold.entries[0], pred_entry)})
    report = evaluate_observation(gold, pred)
    assert not report.is_exact_match
    assert report.field_report.mismatches


def test_second_entry_date_change_is_not_exact(make_observation) -> None:
    gold = make_observation(2)
    changed = gold.entries[1].model_copy(update={"date": date(2040, 2, 1)})
    pred = gold.model_copy(update={"entries": (gold.entries[0], changed)})
    report = evaluate_observation(gold, pred)
    assert not report.is_exact_match
    assert not report.date_match
    assert any("Entry 2" in note for note in report.notes)


def test_empty_observations_match(make_observation) -> None:
    report = evaluate_observation(make_observation(0), make_observation(0))
    assert report.is_exact_match
    assert report.text_report.cer == 0
