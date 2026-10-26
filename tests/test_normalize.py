"""Review reasons and day grouping; model text is never changed."""

import json
from pathlib import Path

import pytest

from diary_photo_transcription.normalize import normalize_observation
from diary_photo_transcription.render import render_markdown
from diary_photo_transcription.schemas import (
    SCORE_POSITION_COUNT,
    FieldItem,
    FieldLabel,
    FormField,
    PhotoObservation,
    PhotoProvenance,
)

_ALL_LABELS = [label.value for label in FieldLabel]
_ILLEGIBLE_SCORE_ROW = [
    {
        "position": position,
        "symbolDescription": f"Symbol {position}",
        "state": "illegible",
    }
    for position in range(1, SCORE_POSITION_COUNT + 1)
]


@pytest.mark.parametrize("location", ["entry_note", "photo_note", "raw_label"])
def test_retained_uncertainty(make_observation, synthetic_day, location):
    observation = make_observation(1)
    entry = observation.entries[0]
    marker = "⟦unsicher: Wort⟧ ⟦unleserlich⟧"
    if location == "entry_note":
        entry = entry.model_copy(update={"visual_notes": (marker,)})
    elif location == "photo_note":
        observation = observation.model_copy(update={"visual_notes": (marker,)})
    else:
        entry = entry.model_copy(
            update={"fields": (FormField(label="Datum", raw_label_text=marker, items=()),)}
        )
    observation = observation.model_copy(update={"entries": (entry,)})
    result = normalize_observation(observation, synthetic_day.entries[0].source)
    assert {"uncertain_text", "unreadable_text"} <= set(result.review_issues[0].reasons)


def test_unsupported_date_is_review_not_rejection(make_observation, synthetic_day):
    result = normalize_observation(make_observation(1), synthetic_day.entries[0].source)
    assert "unsupported_date" in result.review_issues[0].reasons
    assert result.days


def test_photo_without_entries_still_reports_uncertainty(make_observation, synthetic_day):
    observation = make_observation(0).model_copy(update={"visual_notes": ("⟦unsicher: Rand⟧",)})
    result = normalize_observation(observation, synthetic_day.entries[0].source)
    assert [(i.entry_index, i.reasons) for i in result.review_issues] == [
        (None, ("uncertain_text",))
    ]


@pytest.mark.parametrize("date_text", ["1. Januar", "01.01.2040", "⟦unleserlich⟧"])
def test_date_field_is_evidence_without_invented_format_validation(
    make_observation, synthetic_day, date_text
):
    observation = make_observation(1)
    field = FormField(label="Datum", items=(FieldItem(text=date_text, completion="unmarked"),))
    entry = observation.entries[0].model_copy(
        update={
            "fields": (field,),
            "absent_labels": tuple(label for label in FieldLabel if label != field.label),
        }
    )
    result = normalize_observation(
        observation.model_copy(update={"entries": (entry,)}), synthetic_day.entries[0].source
    )
    assert result.days[0].date == entry.date
    assert all("unsupported_date" not in issue.reasons for issue in result.review_issues)
    if date_text == "⟦unleserlich⟧":
        assert "unreadable_text" in result.review_issues[0].reasons


def test_date_elsewhere_remains_valid_but_requests_evidence_review(make_observation, synthetic_day):
    observation = make_observation(1)
    entry = observation.entries[0].model_copy(update={"paragraphs": ("2040-01-01: Text",)})
    observation = observation.model_copy(update={"entries": (entry,)})
    result = normalize_observation(observation, synthetic_day.entries[0].source)
    assert result.days[0].date == entry.date
    assert "unsupported_date" in result.review_issues[0].reasons


def test_synthetic_raw_response_runs_to_markdown_and_review(tmp_path: Path) -> None:
    raw = json.dumps(
        {
            "schemaVersion": 2,
            "photoOverview": {
                "tags": ["long_text", "overflow_to_left_page"],
                "note": "Nur synthetischer visueller Eindruck.",
            },
            "layout": {
                "followsExpectedLayout": False,
                "deviationNote": "Synthetische Fortsetzung links.",
            },
            "entries": [
                {
                    "date": "2040-01-02",
                    "dateCertainty": "certain",
                    "paragraphs": [
                        "Zuerst rechts.",
                        "Danach links mit ⟦unleserlich⟧.",
                    ],
                    "fields": [],
                    "absentLabels": _ALL_LABELS,
                    "scores": [],
                    "crossedOutCorrectionsOmitted": False,
                    "visualNotes": [],
                },
                {
                    "date": None,
                    "dateCertainty": "unknown",
                    "paragraphs": ["Ein synthetischer Absatz ohne Datum."],
                    "fields": [],
                    "absentLabels": _ALL_LABELS,
                    "scores": _ILLEGIBLE_SCORE_ROW,
                    "crossedOutCorrectionsOmitted": False,
                    "visualNotes": [],
                },
            ],
            "visualNotes": [],
        },
        ensure_ascii=False,
    )
    raw_path = tmp_path / "raw.json"
    raw_path.write_text(raw, encoding="utf-8")
    observation = PhotoObservation.model_validate_json(raw_path.read_text(encoding="utf-8"))
    result = normalize_observation(
        observation,
        PhotoProvenance(
            photo_path="synthetic/non-private.jpg",
            photo_sha256="a" * 64,
            model="local-test-model",
            sdk_version="0.0-test",
            prompt_version=1,
            schema_version=2,
        ),
    )

    assert len(result.days) == 1
    rendered = render_markdown(result.days[0]).decode()
    assert rendered.index(r"Zuerst rechts\.") < rendered.index("Danach links")
    assert [issue.entry_index for issue in result.review_issues] == [1, 2]
    assert "unsupported_date" in result.review_issues[0].reasons
    assert set(result.review_issues[1].reasons) == {"unknown_date", "illegible_score"}
