from __future__ import annotations

from collections.abc import Callable
from typing import Any

import yaml

from diary_photo_transcription.schemas import (
    CalendarDay,
    Completion,
    DayEntry,
    FieldItem,
    FieldLabel,
    FormField,
    ScoreObservation,
    ScoreState,
)


def _yaml_bytes(value: Any) -> bytes:
    rendered = yaml.safe_dump(
        value,
        allow_unicode=True,
        default_flow_style=False,
        sort_keys=False,
        width=10_000,
    )
    return rendered.encode("utf-8")


FRONTMATTER_TEXT_FIELDS: tuple[tuple[FieldLabel, str], ...] = (
    (FieldLabel.TAGESMOTTO, "qotd"),
    (FieldLabel.VVV, "makeItBetter"),
    (FieldLabel.LERNZIEL, "learningGoal"),
    (FieldLabel.EAT_THE_FROG, "eatTheFrog"),
    (FieldLabel.TAGESFREUDE, "lookingForward"),
    (FieldLabel.SELBSTV, "methodGoal"),
    (FieldLabel.SG, "socialGoal"),
    (FieldLabel.NEU, "newExperience"),
    (FieldLabel.MOT, "motivation"),
    (FieldLabel.TIL, "todayILearned"),
    (FieldLabel.BT, "bestThing"),
    (FieldLabel.BESONDERES, "special"),
    (FieldLabel.TR, "timeRecap"),
)

SCORE_POSITION_MAP: tuple[tuple[int, str, str], ...] = (
    (1, "outlook", "🔮"),
    (2, "sleep", "💤"),
    (3, "commitment", "⛑️"),
    (4, "social", "♥️"),
    (5, "learning", "📚"),
    (6, "sports", "👟"),
    (7, "health", "🍎"),
    (8, "todo", "⏱️"),
    (9, "work", "💼"),
    (10, "brokeness", "⚠️"),
    (11, "discipline", "⚙️"),
    (12, "organisation", "💭"),
    (13, "impact", "💣"),
    (14, "energy", "⚡"),
    (15, "fun", "🎉"),
    (16, "routine", "🔁"),
    (17, "feeling", "🙂"),
)


def _display(text: str) -> str:
    """Literal inline Markdown; line breaks cannot introduce blocks or list items."""
    # Entities keep Obsidian comments, math and wikilinks inert even when its
    # extension parsers run before ordinary Markdown backslash handling.
    entities = {
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        "\n": "<br>",
        "%": "&#37;",
        "$": "&#36;",
        "[": "&#91;",
        "]": "&#93;",
    }
    punctuation = "\\`*_{}()#+-.!|~"
    # Leading indentation must not turn a transcription paragraph into a code block.
    prefix = ""
    while text.startswith((" ", "\t")):
        prefix += "&#32;" if text[0] == " " else "&#9;"
        text = text[1:]
    return prefix + "".join(
        entities.get(char, "\\" + char if char in punctuation else char)
        for char in text.replace("\r\n", "\n").replace("\r", "\n")
    )


def _build_frontmatter(day: CalendarDay) -> dict[str, Any]:
    frontmatter: dict[str, Any] = {
        "date": day.date.isoformat(),
        "tags": "daily",
        "type": "daily",
        "meta_type": "note",
        "meta_project": "tagebuch",
        "meta_source": day.entries[0].source.model,
        "meta_generator": "ai",
        "schemaVersion": day.schema_version,
        "sources": [entry.source.model_dump(mode="json", by_alias=True) for entry in day.entries],
        "summaryAuthority": "non-authoritative",
    }

    conflicts: list[str] = []
    for field_label, fm_key in FRONTMATTER_TEXT_FIELDS:
        fields = [f for entry in day.entries for f in entry.fields if f.label == field_label]
        # Compare item boundaries and marks, not only flattened text.
        conflict = any(f.items != fields[0].items for f in fields[1:])
        text = " | ".join(item.text for item in fields[0].items) if fields else None
        frontmatter[fm_key] = None if conflict else text
        if conflict:
            conflicts.append(fm_key)

    for pos, key, _emoji in SCORE_POSITION_MAP:
        scores = [s for entry in day.entries for s in entry.scores if s.position == pos]
        conflict = len({(s.state, s.raw_value, s.value) for s in scores}) > 1
        score = scores[0] if scores else None
        frontmatter[key] = (
            score.value if not conflict and score and score.state is ScoreState.WRITTEN else None
        )
        if conflict:
            conflicts.append(key)
    frontmatter["summaryConflicts"] = conflicts

    return frontmatter


_SCORE_CELLS = {
    ScoreState.EMPTY: " ",
    ScoreState.STRUCK_THROUGH: "❔",
    ScoreState.ILLEGIBLE: "⟦unleserlich⟧",
}


def _render_score_table(scores: tuple[ScoreObservation, ...]) -> list[str]:
    by_pos = {s.position: s for s in scores}
    values = [
        " " if s is None else _SCORE_CELLS.get(s.state, str(s.raw_value))
        for s in (by_pos.get(pos) for pos, _key, _emoji in SCORE_POSITION_MAP)
    ]
    headers = [emoji for _, _, emoji in SCORE_POSITION_MAP]
    return [
        "# Stats",
        "",
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join([":-:"] * len(headers)) + " |",
        "| " + " | ".join(values) + " |",
        "",
    ]


def _field_title(field: FormField, title: str) -> str:
    if field.raw_label_text is not None:
        return f"{title} ({_display(field.raw_label_text)})"
    return title


def _render_item(item: FieldItem) -> str:
    struck = " (durchgestrichen)" if item.struck_through else ""
    return f"{_display(item.text)} ({item.completion.value}){struck}"


def _checkbox(done: bool) -> str:
    return "[x]" if done else "[ ]"


def _numbered(index: int, _item: FieldItem) -> str:
    return f"{index}. "


def _bullet(_index: int, _item: FieldItem) -> str:
    return "- "


def _prio(index: int, item: FieldItem) -> str:
    return f"- {_checkbox(item.completion is Completion.FULFILLED)} {index}. "


def _todo(_index: int, item: FieldItem) -> str:
    # A struck-through ToDo is done.
    return f"- {_checkbox(item.struck_through or item.completion is Completion.FULFILLED)} "


Marker = Callable[[int, FieldItem], str]
_PLAN_SECTIONS = (
    (FieldLabel.PRIOS, "Prioritäten", _prio),
    (FieldLabel.TODOS, "ToDos", _todo),
    (FieldLabel.FUN, "Vorfreude & Fun", _bullet),
)
_OPINION_SECTIONS = ((FieldLabel.PRO, "Pro"), (FieldLabel.CONS, "Contra"))
_OBSERVATIONS = (
    (FieldLabel.STOEREN, "Stören"),
    (FieldLabel.SCHOEN, "Schön"),
    (FieldLabel.DANKBAR, "Dankbar"),
    (FieldLabel.LFT, "Looking Forward To"),
)


def _list_section(field: FormField | None, title: str, level: int, marker: Marker) -> list[str]:
    if field is None:
        return []
    items = [marker(i, item) + _render_item(item) for i, item in enumerate(field.items, start=1)]
    return [f"{'#' * level} {_field_title(field, title)}", "", *items, ""]


def _is_summary_only(field: FormField) -> bool:
    """A single plain item can live exclusively in its summary property."""
    return (
        len(field.items) == 1
        and field.items[0].completion is Completion.UNMARKED
        and not field.items[0].struck_through
        and field.raw_label_text is None
    )


_SUMMARY_LABELS = {label for label, _ in FRONTMATTER_TEXT_FIELDS}


def _render_entry_body(entry: DayEntry, header: str | None) -> list[str]:
    lines = [f"## {header}", ""] if header else []
    if entry.scores:
        lines.extend(_render_score_table(entry.scores))

    field_map = {f.label: f for f in entry.fields if f.items}
    extra_fields = [
        f
        for f in entry.fields
        if not f.items
        or f.label is FieldLabel.DATUM
        or (f.label in _SUMMARY_LABELS and (header is not None or not _is_summary_only(f)))
    ]
    if extra_fields:
        lines.extend(["# Formular", ""])
        for field in extra_fields:
            lines.extend([f"### {_display(field.raw_label_text or field.label.value)}", ""])
            if not field.items:
                lines.append("_Sichtbar, aber leer._")
            lines.extend(f"- {_render_item(item)}" for item in field.items)
            lines.append("")

    lines.extend(
        _list_section(field_map.get(FieldLabel.TAGESERLEBNIS), "Tagesablauf", 1, _numbered)
    )

    plan = [
        line
        for label, title, marker in _PLAN_SECTIONS
        for line in _list_section(field_map.get(label), title, 3, marker)
    ]
    if plan:
        lines.extend(["# Plan", "", *plan])

    thoughts = [
        line
        for label, title in _OPINION_SECTIONS
        for line in _list_section(field_map.get(label), title, 2, _bullet)
    ]
    observations = [
        f"- **{_field_title(field, title)}:** {_render_item(item)}"
        for label, title in _OBSERVATIONS
        if (field := field_map.get(label)) is not None
        for item in field.items
    ]
    if observations:
        thoughts.extend(["## Beobachtungen", "", *observations, ""])
    if entry.paragraphs:
        thoughts.extend(["## Erlebnis", "", "\n\n".join(_display(p) for p in entry.paragraphs), ""])
    if thoughts:
        lines.extend(["# Gedanken", "", *thoughts])

    if entry.visual_notes:
        lines.extend(
            ["## Besonderheiten", "", *(f"- {_display(n)}" for n in entry.visual_notes), ""]
        )
    if entry.crossed_out_corrections_omitted:
        lines.extend(["_Durchgestrichene Korrekturen wurden ausgelassen._", ""])
    return lines


def render_markdown(day: CalendarDay) -> bytes:
    """Render a canonical day to UTF-8 Markdown with deterministic YAML frontmatter."""
    multi = len(day.entries) > 1
    body = [
        line
        for index, entry in enumerate(day.entries, start=1)
        for line in _render_entry_body(entry, f"Quelle {index}" if multi else None)
    ]
    content = "\n".join(body).strip() + "\n"
    return b"---\n" + _yaml_bytes(_build_frontmatter(day)) + b"---\n\n" + content.encode("utf-8")
