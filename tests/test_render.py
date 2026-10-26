import pytest
import yaml

from diary_photo_transcription.render import render_markdown
from diary_photo_transcription.schemas import CalendarDay, FieldItem, FieldLabel, FormField


def test_markdown_render_is_byte_identical(synthetic_day: CalendarDay) -> None:
    first = render_markdown(synthetic_day)
    second = render_markdown(synthetic_day)

    assert first == second
    assert first.endswith(b"\n")
    assert b"\r" not in first
    rendered = first.decode()
    assert "meta_type: note" in rendered
    assert "meta_project: tagebuch" in rendered
    assert "meta_generator: ai" in rendered
    assert "commitment: 4" in rendered
    assert "outlook: null" in rendered
    assert rendered.index(r"Synthetischer Absatz\.") < rendered.index("Reiner Testtext")
    assert "# Stats" in rendered
    assert "| 🔮 | 💤 | ⛑️ |" in rendered
    assert "| ❔ |   | 4 |" in rendered
    assert "# Plan" in rendered
    assert "### Prioritäten" in rendered
    assert "- [x] 1. Erster Punkt" in rendered
    assert "## Erlebnis" in rendered


def test_markdown_supports_multiple_sources_per_day(synthetic_day: CalendarDay) -> None:
    first_entry = synthetic_day.entries[0]
    second_entry = first_entry.model_copy(
        update={
            "source": first_entry.source.model_copy(
                update={"photo_path": "private/source/synthetic-2.jpg"}
            ),
            "source_entry_index": 2,
        }
    )
    day = synthetic_day.model_copy(update={"entries": (first_entry, second_entry)})

    rendered = render_markdown(day).decode()

    assert rendered.index("## Quelle 1") < rendered.index("## Quelle 2")


@pytest.mark.parametrize("label", list(FieldLabel))
def test_visible_empty_fields(synthetic_day, label):
    field = FormField(label=label, items=())
    entry = synthetic_day.entries[0].model_copy(update={"fields": (field,), "scores": ()})
    text = render_markdown(synthetic_day.model_copy(update={"entries": (entry,)})).decode()
    _, fm, body = text.split("---", 2)
    assert "Sichtbar, aber leer" in body
    if label == FieldLabel.TAGESMOTTO:
        assert yaml.safe_load(fm)["qotd"] == ""


def test_contextual_display(synthetic_day):
    source = "<!-- hidden --> *literal* [link](x)\n# not heading"
    field = FormField(
        label="ToDos",
        raw_label_text="<b>*label*</b>",
        items=(FieldItem(text=source, completion="unmarked"),),
    )
    entry = synthetic_day.entries[0].model_copy(
        update={
            "fields": (field,),
            "scores": (),
            "paragraphs": (source,),
            "visual_notes": (source,),
        }
    )
    body = (
        render_markdown(synthetic_day.model_copy(update={"entries": (entry,)}))
        .decode()
        .split("---", 2)[2]
    )
    assert (
        "&lt;\\!\\-\\- hidden \\-\\-&gt; \\*literal\\* &#91;link&#93;\\(x\\)<br>\\# not heading"
        in body
    )
    assert "### ToDos (&lt;b&gt;\\*label\\*&lt;/b&gt;)" in body
    assert "- [ ] " in body
    assert entry.fields[0].items[0].text == source


@pytest.mark.parametrize(
    ("source", "literal"),
    [
        ("%%hidden words%%", "&#37;&#37;hidden words&#37;&#37;"),
        ("$math words$", "&#36;math words&#36;"),
        ("$$display words$$", "&#36;&#36;display words&#36;&#36;"),
        ("[[source words|alias]]", r"&#91;&#91;source words\|alias&#93;&#93;"),
        ("![[embedded words]]", r"\!&#91;&#91;embedded words&#93;&#93;"),
        ("&#37;literal entity", r"&amp;\#37;literal entity"),
    ],
)
def test_obsidian_syntax_is_literal_in_all_body_contexts(synthetic_day, source, literal):
    field = FormField(
        label="ToDos",
        raw_label_text=source,
        items=(FieldItem(text=source, completion="unmarked"),),
    )
    entry = synthetic_day.entries[0].model_copy(
        update={
            "fields": (field,),
            "scores": (),
            "paragraphs": (source,),
            "visual_notes": (source,),
        }
    )
    body = (
        render_markdown(synthetic_day.model_copy(update={"entries": (entry,)}))
        .decode()
        .split("---", 2)[2]
    )
    assert body.count(literal) == 4
    assert source not in body
    assert entry.paragraphs == (source,)
    assert entry.fields[0].items[0].text == source


def test_summary_evidence_is_plain_and_absence_distinct(synthetic_day):
    source = "<!-- literal --> *text*\nnext"
    field = FormField(label="Tagesmotto", items=(FieldItem(text=source, completion="unmarked"),))
    entry = synthetic_day.entries[0].model_copy(update={"fields": (field,)})
    text = render_markdown(synthetic_day.model_copy(update={"entries": (entry,)})).decode()
    assert yaml.safe_load(text.split("---", 2)[1])["qotd"] == source
    entry = entry.model_copy(update={"fields": ()})
    text = render_markdown(synthetic_day.model_copy(update={"entries": (entry,)})).decode()
    assert yaml.safe_load(text.split("---", 2)[1])["qotd"] is None
