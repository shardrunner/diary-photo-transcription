# Papierlegende: supported daily layout

This pipeline targets a specific German diary template, not arbitrary forms.
The public description below is a layout contract; personal tracker definitions
are retained only in the ignored local backup.

## Left page

24 labels are enumerated by `FieldLabel` in `schemas.py`; their mappings are in
[alias-verzeichnis.md](alias-verzeichnis.md). Datum is top left, Tagesmotto top
right, and Tageserlebnis a central list: these three have no written label.
Written labels usually end in a colon. Preserve the actual spelling in
`rawLabelText`; `Contra:` maps to `Cons`.

Completion applies to each item: tick = fulfilled, cross = not_fulfilled,
no mark = unmarked (not failure). Absent morning fields are normal; missing dates
require review. Do not invent absent fields or derive dates from filenames.

## Right page

17 positional scores precede free paragraphs, which may continue onto the left
page. Preserve reading order and paragraph boundaries. The symbol mapping is in
the alias directory. Position is authoritative; an emoji is only a visual aid.

Scores are integers 0–6, except position 16, a nonnegative counter. The counter
may be written as an integer or numerator/denominator (e.g. fictional `9/10`,
normalized value 9). No other fractions or decimals are legitimate.
Empty, illegible and struck-through scores are distinct, never zero by default.

## Three meanings of strike-through

| Location | Meaning | Extraction |
| --- | --- | --- |
| ToDo item | completed | retain text and `struckThrough=true` |
| Score | not recorded | `state=struck_through`, no value |
| Other text | correction | omit; `crossedOutCorrectionsOmitted=true` |

Mark unreadable text `⟦unleserlich⟧` and uncertain readings
`⟦unsicher: LESART⟧`. Never guess from private vocabulary.

Central habit/experience trackers and video are outside the daily flow.
