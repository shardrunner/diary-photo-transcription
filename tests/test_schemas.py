from datetime import date

import pytest
from pydantic import ValidationError

from diary_photo_transcription.schemas import (
    SCORE_POSITION_COUNT,
    FieldLabel,
    FormField,
    ObservedEntry,
    PhotoObservation,
    ScoreObservation,
    model_response_json_schema,
)


def _score(position: int, **overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "position": position,
        "symbolDescription": f"Symbol {position}",
        "state": "written",
        "rawValue": "3",
        "value": 3,
    }
    payload.update(overrides)
    return payload


def _full_score_row() -> list[dict[str, object]]:
    return [_score(position) for position in range(1, SCORE_POSITION_COUNT + 1)]


def _entry_payload(**overrides: object) -> dict[str, object]:
    present = {
        "label": "Pro",
        "rawLabelText": "Pro:",
        "items": [{"text": "gute Zeit gehabt", "completion": "unmarked", "struckThrough": False}],
    }
    payload: dict[str, object] = {
        "date": "2040-01-02",
        "dateCertainty": "certain",
        "fields": [present],
        "absentLabels": [label.value for label in FieldLabel if label is not FieldLabel.PRO],
        "scores": _full_score_row(),
        "paragraphs": ["Ein synthetischer Absatz."],
        "crossedOutCorrectionsOmitted": True,
        "visualNotes": [],
    }
    payload.update(overrides)
    return payload


def _observation_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "schemaVersion": 2,
        "photoOverview": {"tags": ["sparse_page"], "note": "Synthetische Beobachtung."},
        "layout": {"followsExpectedLayout": True, "deviationNote": None},
        "entries": [_entry_payload()],
        "visualNotes": [],
    }
    payload.update(overrides)
    return payload


def test_observation_carries_fields_scores_and_free_text() -> None:
    observation = PhotoObservation.model_validate(_observation_payload())
    entry = observation.entries[0]

    assert entry.date == date(2040, 1, 2)
    assert entry.fields[0].label is FieldLabel.PRO
    assert entry.fields[0].raw_label_text == "Pro:"
    assert len(entry.scores) == SCORE_POSITION_COUNT
    assert entry.paragraphs == ("Ein synthetischer Absatz.",)


@pytest.mark.parametrize("version", [1, 3])
def test_unsupported_observation_version_is_rejected(version: int) -> None:
    with pytest.raises(ValidationError, match="schemaVersion"):
        PhotoObservation.model_validate(_observation_payload(schemaVersion=version))


def test_response_schema_pins_version_with_supported_numeric_bounds() -> None:
    version = model_response_json_schema()["properties"]["schemaVersion"]
    assert version["type"] == "integer"
    assert version["minimum"] == version["maximum"] == 2


def test_score_may_report_a_position_without_a_value() -> None:
    """A struck-through Ausblick must be expressible, otherwise the row shifts."""
    score = ScoreObservation.model_validate(
        {
            "position": 1,
            "symbolDescription": "Stundenglas",
            "state": "struck_through",
        }
    )

    assert score.value is None
    assert score.raw_value is None


@pytest.mark.parametrize("state", ["struck_through", "empty", "illegible"])
def test_score_without_written_state_must_not_carry_a_value(state: str) -> None:
    with pytest.raises(ValidationError):
        ScoreObservation.model_validate(
            {
                "position": 1,
                "symbolDescription": "Stundenglas",
                "state": state,
                "rawValue": "4",
                "value": 4,
            }
        )


def test_written_score_requires_its_literal_value() -> None:
    with pytest.raises(ValidationError):
        ScoreObservation.model_validate(
            {"position": 3, "symbolDescription": "Helm", "state": "written"}
        )


def test_score_value_above_six_is_rejected_outside_the_counter() -> None:
    """The shifted habit count that corrupted a whole row must not validate."""
    with pytest.raises(ValidationError):
        ScoreObservation.model_validate(_score(15, rawValue="9", value=9))


def test_habit_counter_position_may_exceed_six() -> None:
    counter = ScoreObservation.model_validate(_score(16, rawValue="9/10", value=9))

    assert counter.value == 9


def test_score_row_must_cover_every_position_exactly_once() -> None:
    incomplete = _full_score_row()[:-1]
    with pytest.raises(ValidationError):
        ObservedEntry.model_validate(_entry_payload(scores=incomplete))

    duplicated = _full_score_row()
    duplicated[1] = _score(1)
    with pytest.raises(ValidationError):
        ObservedEntry.model_validate(_entry_payload(scores=duplicated))


def test_absent_labels_and_fields_must_together_cover_every_label() -> None:
    with pytest.raises(ValidationError):
        ObservedEntry.model_validate(_entry_payload(absentLabels=["VvV"]))


def test_a_label_cannot_be_present_and_absent_at_once() -> None:
    with pytest.raises(ValidationError):
        ObservedEntry.model_validate(
            _entry_payload(absentLabels=[label.value for label in FieldLabel])
        )


def test_entry_without_any_content_is_rejected() -> None:
    with pytest.raises(ValidationError):
        ObservedEntry.model_validate(
            _entry_payload(
                fields=[],
                paragraphs=[],
                scores=[],
                absentLabels=[label.value for label in FieldLabel],
            )
        )


def test_list_items_carry_their_own_completion_mark() -> None:
    entry = ObservedEntry.model_validate(
        _entry_payload(
            fields=[
                {
                    "label": "Prios",
                    "rawLabelText": "Prios:",
                    "items": [
                        {
                            "text": "Wäsche waschen",
                            "completion": "fulfilled",
                            "struckThrough": False,
                        },
                        {
                            "text": "Liste durchgehen",
                            "completion": "not_fulfilled",
                            "struckThrough": False,
                        },
                        {"text": "offen", "completion": "unmarked", "struckThrough": False},
                    ],
                }
            ],
            absentLabels=[label.value for label in FieldLabel if label is not FieldLabel.PRIOS],
        )
    )

    assert [item.completion.value for item in entry.fields[0].items] == [
        "fulfilled",
        "not_fulfilled",
        "unmarked",
    ]


def test_unlabelled_field_reports_no_raw_label_text() -> None:
    entry = ObservedEntry.model_validate(
        _entry_payload(
            fields=[
                {
                    "label": "Tageserlebnis",
                    "items": [{"text": "Arbeit", "completion": "unmarked", "struckThrough": False}],
                }
            ],
            absentLabels=[
                label.value for label in FieldLabel if label is not FieldLabel.TAGESERLEBNIS
            ],
        )
    )

    assert entry.fields[0].raw_label_text is None


def test_model_response_schema_excludes_defensive_architecture() -> None:
    serialized = str(model_response_json_schema())

    for forbidden in ("readingOrder", "bbox", "modelConfidence", "paragraphId"):
        assert forbidden not in serialized


def test_empty_is_not_absent_or_missing(make_observation):
    observation = make_observation(1)
    field = FormField(label="Datum", items=())
    data = observation.entries[0].model_dump()
    data["fields"] = (field,)
    with pytest.raises(ValueError, match="present and absent"):
        type(observation.entries[0]).model_validate(data)
    data["absent_labels"] = tuple(label for label in FieldLabel if label != field.label)
    assert type(observation.entries[0]).model_validate(data).fields[0].items == ()
    with pytest.raises(ValueError):
        FormField.model_validate({"label": "Datum"})


@pytest.mark.parametrize(
    ("position", "raw", "value"),
    [(1, "99", None), (1, "4", 3), (1, "4", None), (1, "4/10", 4), (16, "9/0", 9), (16, "9/10", 8)],
)
def test_written_score_requires_consistent_literal(
    position: int, raw: str, value: int | None
) -> None:
    with pytest.raises(ValueError):
        ScoreObservation(
            position=position,
            symbol_description="Synthetic",
            state="written",
            raw_value=raw,
            value=value,
        )
