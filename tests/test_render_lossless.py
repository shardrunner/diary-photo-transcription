import pytest
import yaml

from diary_photo_transcription.render import (
    FRONTMATTER_TEXT_FIELDS,
    SCORE_POSITION_MAP,
    render_markdown,
)
from diary_photo_transcription.schemas import (
    CalendarDay,
    Completion,
    FieldItem,
    FieldLabel,
    FormField,
    ScoreObservation,
    ScoreState,
)


def render_fields(day, fields, *, multi=False):
    entry = day.entries[0].model_copy(update={"fields": tuple(fields), "scores": ()})
    entries = (entry, entry) if multi else (entry,)
    text = render_markdown(day.model_copy(update={"entries": entries})).decode()
    _, fm, body = text.split("---", 2)
    return yaml.safe_load(fm), body


@pytest.mark.parametrize("label", list(FieldLabel))
@pytest.mark.parametrize("completion", list(Completion))
@pytest.mark.parametrize("struck", [False, True])
def test_every_label_preserves_item_states(synthetic_day, label, completion, struck):
    field = FormField(
        label=label,
        items=(
            FieldItem(
                text=f"Visible {label}",
                completion=completion,
                struck_through=struck,
            ),
        ),
    )
    fm, body = render_fields(synthetic_day, [field], multi=True)
    for source in body.split("## Quelle ")[1:]:
        display_label = r"\+" if label == FieldLabel.BESONDERES else label.value
        assert f"Visible {display_label}" in source
        assert f"({completion.value})" in source
        assert ("(durchgestrichen)" in source) is struck
    assert fm["summaryAuthority"] == "non-authoritative"


@pytest.mark.parametrize("label,key", FRONTMATTER_TEXT_FIELDS)
def test_multi_entry_text_conflicts_are_not_selected(synthetic_day, label, key):
    entries = tuple(
        synthetic_day.entries[0].model_copy(
            update={
                "fields": (
                    FormField(label=label, items=(FieldItem(text=text, completion="unmarked"),)),
                )
            }
        )
        for text in ("First", "Second")
    )
    rendered = render_markdown(synthetic_day.model_copy(update={"entries": entries})).decode()
    _, fm_text, body = rendered.split("---", 2)
    fm = yaml.safe_load(fm_text)
    assert fm[key] is None
    assert key in fm["summaryConflicts"]
    assert "First" in body.split("## Quelle 2")[0]
    assert "Second" in body.split("## Quelle 2")[1]


@pytest.mark.parametrize("state", list(ScoreState))
@pytest.mark.parametrize("position", range(1, 18))
def test_score_conflicts_and_raw_notation(synthetic_day, state, position):
    first = ScoreObservation(
        position=position,
        symbol_description="test",
        state="written",
        raw_value="9/10" if position == 16 else "4",
        value=9 if position == 16 else 4,
    )
    second = ScoreObservation(
        position=position,
        symbol_description="test",
        state=state,
        raw_value="3" if state == ScoreState.WRITTEN else None,
        value=3 if state == ScoreState.WRITTEN else None,
    )
    entries = tuple(
        synthetic_day.entries[0].model_copy(update={"scores": (score,)})
        for score in (first, second)
    )
    rendered = render_markdown(synthetic_day.model_copy(update={"entries": entries})).decode()
    _, fm_text, body = rendered.split("---", 2)
    key = SCORE_POSITION_MAP[position - 1][1]
    fm = yaml.safe_load(fm_text)
    assert fm[key] is None
    assert key in fm["summaryConflicts"]
    assert body.count("# Stats") == 2
    if position == 16:
        assert "9/10" in body


@pytest.mark.parametrize("label", list(FieldLabel))
@pytest.mark.parametrize("multi", [False, True])
@pytest.mark.parametrize("completion", list(Completion))
@pytest.mark.parametrize("struck", [False, True])
def test_every_literal_label_survives(synthetic_day, label, multi, completion, struck):
    raw_label = f"{label.value}:"
    field = FormField(
        label=label,
        raw_label_text=raw_label,
        items=(FieldItem(text="Literal item", completion=completion, struck_through=struck),),
    )
    _, body = render_fields(synthetic_day, [field], multi=multi)
    sources = body.split("## Quelle ")[1:] if multi else [body]
    for source in sources:
        assert raw_label in source
        assert f"Literal item ({completion.value})" in source
        assert ("(durchgestrichen)" in source) is struck


@pytest.mark.parametrize(
    "label,title",
    [
        (FieldLabel.TAGESERLEBNIS, "# Tagesablauf"),
        (FieldLabel.PRIOS, "### Prioritäten"),
        (FieldLabel.TODOS, "### ToDos"),
        (FieldLabel.FUN, "### Vorfreude & Fun"),
        (FieldLabel.PRO, "## Pro"),
        (FieldLabel.CONS, "## Contra"),
        (FieldLabel.STOEREN, "Stören"),
        (FieldLabel.SCHOEN, "Schön"),
        (FieldLabel.DANKBAR, "Dankbar"),
        (FieldLabel.LFT, "Looking Forward To"),
    ],
)
def test_literal_labels_keep_useful_titles(synthetic_day, label, title):
    raw_label = "Originale Schreibweise :"
    field = FormField(
        label=label,
        raw_label_text=raw_label,
        items=(FieldItem(text="Only once", completion="fulfilled"),),
    )
    _, body = render_fields(synthetic_day, [field])
    assert title in body
    assert raw_label in body
    assert body.count("Only once (fulfilled)") == 1


def test_single_simple_summary_keeps_appearance(synthetic_day: CalendarDay):
    field = FormField(label="Tagesmotto", items=(FieldItem(text="Simple", completion="unmarked"),))
    fm, body = render_fields(synthetic_day, [field])
    assert fm["qotd"] == "Simple"
    assert "Simple" not in body


@pytest.mark.parametrize("completion", list(Completion))
def test_single_complex_summary_is_also_transcribed(synthetic_day, completion):
    field = FormField(
        label="Tagesmotto",
        items=(
            FieldItem(text="First", completion=completion, struck_through=True),
            FieldItem(text="Second", completion="unmarked"),
        ),
    )
    _, body = render_fields(synthetic_day, [field])
    assert f"First ({completion.value}) (durchgestrichen)" in body
    assert "Second (unmarked)" in body


@pytest.mark.parametrize("label,key", FRONTMATTER_TEXT_FIELDS)
@pytest.mark.parametrize("completion", [Completion.FULFILLED, Completion.NOT_FULFILLED])
def test_equal_text_with_different_marks_conflicts(synthetic_day, label, key, completion):
    entries = tuple(
        synthetic_day.entries[0].model_copy(
            update={
                "fields": (
                    FormField(label=label, items=(FieldItem(text="Same", completion=state),)),
                )
            }
        )
        for state in (Completion.UNMARKED, completion)
    )
    text = render_markdown(synthetic_day.model_copy(update={"entries": entries})).decode()
    _, fm, body = text.split("---", 2)
    assert yaml.safe_load(fm)[key] is None
    assert "Same (unmarked)" in body
    assert f"Same ({completion.value})" in body


@pytest.mark.parametrize("second_raw", ["9", "9/11", "9/10"])
def test_counter_summary_compares_literal_not_only_numerator(synthetic_day, second_raw):
    entries = tuple(
        synthetic_day.entries[0].model_copy(
            update={
                "scores": (
                    ScoreObservation(
                        position=16,
                        symbol_description="test",
                        state="written",
                        raw_value=raw,
                        value=9,
                    ),
                )
            }
        )
        for raw in ("9/10", second_raw)
    )
    text = render_markdown(synthetic_day.model_copy(update={"entries": entries})).decode()
    _, fm_text, body = text.split("---", 2)
    fm = yaml.safe_load(fm_text)
    assert fm["routine"] == (9 if second_raw == "9/10" else None)
    assert ("routine" in fm["summaryConflicts"]) is (second_raw != "9/10")
    assert "9/10" in body.split("## Quelle 2")[0]
    assert f"| {second_raw} |" in body.split("## Quelle 2")[1]


@pytest.mark.parametrize("label", list(FieldLabel))
@pytest.mark.parametrize("completion", list(Completion))
@pytest.mark.parametrize("struck", [False, True])
def test_single_entry_item_states(synthetic_day, label, completion, struck):
    field = FormField(
        label=label,
        items=(
            FieldItem(
                text="Visible text",
                completion=completion,
                struck_through=struck,
            ),
        ),
    )
    fm, body = render_fields(synthetic_day, [field])
    summary_key = dict(FRONTMATTER_TEXT_FIELDS).get(label)
    if summary_key and completion is Completion.UNMARKED and not struck:
        assert fm[summary_key] == "Visible text"
    else:
        assert f"Visible text ({completion.value})" in body
        assert ("(durchgestrichen)" in body) is struck
