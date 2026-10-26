from __future__ import annotations

import re
from datetime import date as CalendarDate
from enum import StrEnum
from typing import Annotated, Any, Final, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    model_validator,
)

_SHA256 = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
_NONEMPTY = Annotated[str, StringConstraints(min_length=1)]
SCHEMA_VERSION: Final = 2


def _to_camel(value: str) -> str:
    head, *tail = value.split("_")
    return head + "".join(part.capitalize() for part in tail)


class DomainModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=_to_camel,
        extra="forbid",
        frozen=True,
        populate_by_name=True,
    )


class DateCertainty(StrEnum):
    CERTAIN = "certain"
    UNCERTAIN = "uncertain"
    UNKNOWN = "unknown"


class OverviewTag(StrEnum):
    SHORT_ENTRY = "short_entry"
    LONG_TEXT = "long_text"
    SPARSE_PAGE = "sparse_page"
    DENSE_PAGE = "dense_page"
    WRITING_APPEARS_HASTY = "writing_appears_hasty"
    WRITING_APPEARS_CAREFUL = "writing_appears_careful"
    DIFFICULT_LEGIBILITY = "difficult_legibility"
    UNUSUAL_LAYOUT = "unusual_layout"
    MULTIPLE_DAYS = "multiple_days"
    OVERFLOW_TO_LEFT_PAGE = "overflow_to_left_page"
    MORNING_ROUTINE_SKIPPED = "morning_routine_skipped"
    MANY_CORRECTIONS = "many_corrections"
    MIXED_WRITING_SIZES = "mixed_writing_sizes"
    OTHER = "other"


class PhotoOverview(DomainModel):
    tags: tuple[OverviewTag, ...] = Field(...)
    note: _NONEMPTY


class LayoutObservation(DomainModel):
    follows_expected_layout: bool | None
    deviation_note: _NONEMPTY | None = None


SCORE_POSITION_COUNT = 17
HABIT_AGGREGATE_POSITION = 16
MAX_SCORE_VALUE = 6


class FieldLabel(StrEnum):
    """The closed set of labels of the left diary page.

    Values are the labels as written on paper. Three of them carry no written
    label at all and are recognised by position and form only.
    """

    DATUM = "Datum"
    TAGESMOTTO = "Tagesmotto"
    VVV = "VvV"
    LERNZIEL = "Lernziel"
    EAT_THE_FROG = "Eat the Frog"
    TAGESFREUDE = "Tagesfreude"
    PRIOS = "Prios"
    FUN = "Fun"
    STOEREN = "Stören"
    SCHOEN = "Schön"
    DANKBAR = "dankbar"
    TODOS = "ToDos"
    TAGESERLEBNIS = "Tageserlebnis"
    PRO = "Pro"
    CONS = "Cons"
    SELBSTV = "SelbstV"
    SG = "SG"
    LFT = "LFT"
    NEU = "Neu"
    MOT = "Mot"
    TIL = "TIL"
    BT = "BT"
    BESONDERES = "+"
    TR = "TR"


class Completion(StrEnum):
    """Evening completion mark of one morning-written value.

    ``UNMARKED`` means not assessed. It must never be read as a failure.
    """

    FULFILLED = "fulfilled"
    NOT_FULFILLED = "not_fulfilled"
    UNMARKED = "unmarked"


class ScoreState(StrEnum):
    """Why a score position does or does not carry a value.

    Every position is reported even when empty. Without ``STRUCK_THROUGH`` and
    ``EMPTY`` a gap forces the model to shift the remaining values forward and
    corrupts the whole row.
    """

    WRITTEN = "written"
    STRUCK_THROUGH = "struck_through"
    EMPTY = "empty"
    ILLEGIBLE = "illegible"


class FieldItem(DomainModel):
    text: _NONEMPTY
    completion: Completion
    struck_through: bool = False


class FormField(DomainModel):
    label: FieldLabel
    raw_label_text: _NONEMPTY | None = None
    items: tuple[FieldItem, ...] = Field(..., description="Empty when visible but unfilled")


class ScoreObservation(DomainModel):
    position: int = Field(ge=1, le=SCORE_POSITION_COUNT)
    symbol_description: _NONEMPTY
    state: ScoreState
    raw_value: _NONEMPTY | None = None
    value: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_value_matches_state(self) -> Self:
        if self.state is ScoreState.WRITTEN:
            if self.raw_value is None or self.value is None:
                raise ValueError("a written score requires literal and numeric values")
            pattern = (
                r"[0-9]+(?:/[1-9][0-9]*)?"
                if self.position == HABIT_AGGREGATE_POSITION
                else r"[0-6]"
            )
            if not re.fullmatch(pattern, self.raw_value):
                raise ValueError("invalid literal score notation or value outside 0-6")
            if int(self.raw_value.split("/")[0]) != self.value:
                raise ValueError("literal and numeric score values disagree")
        elif self.raw_value is not None or self.value is not None:
            raise ValueError("only a written score may carry a value")
        exceeds_scale = (
            self.value is not None
            and self.position != HABIT_AGGREGATE_POSITION
            and self.value > MAX_SCORE_VALUE
        )
        if exceeds_scale:
            raise ValueError(f"score values above {MAX_SCORE_VALUE} are misreadings")
        return self


class ObservedEntry(DomainModel):
    date: CalendarDate | None = None
    date_certainty: DateCertainty = Field(...)
    fields: tuple[FormField, ...] = Field(...)
    absent_labels: tuple[FieldLabel, ...] = Field(...)
    scores: tuple[ScoreObservation, ...] = Field(...)
    paragraphs: tuple[_NONEMPTY, ...] = Field(...)
    crossed_out_corrections_omitted: bool = Field(...)
    visual_notes: tuple[_NONEMPTY, ...] = Field(...)

    @model_validator(mode="after")
    def validate_date_certainty(self) -> Self:
        if self.date_certainty is DateCertainty.UNKNOWN and self.date is not None:
            raise ValueError("date must be absent when date certainty is unknown")
        if self.date_certainty is not DateCertainty.UNKNOWN and self.date is None:
            raise ValueError("date is required unless date certainty is unknown")
        return self

    @model_validator(mode="after")
    def validate_every_label_is_accounted_for(self) -> Self:
        present = [field.label for field in self.fields]
        if len(present) != len(set(present)):
            raise ValueError("each label may appear at most once")
        if len(self.absent_labels) != len(set(self.absent_labels)):
            raise ValueError("each absent label may appear at most once")
        overlap = set(present) & set(self.absent_labels)
        if overlap:
            raise ValueError("a label cannot be present and absent at once")
        if set(present) | set(self.absent_labels) != set(FieldLabel):
            raise ValueError("every label must be reported as present or absent")
        return self

    @model_validator(mode="after")
    def validate_score_row_is_complete(self) -> Self:
        if not self.scores:
            return self
        positions = [score.position for score in self.scores]
        if sorted(positions) != list(range(1, SCORE_POSITION_COUNT + 1)):
            raise ValueError(
                f"the score row needs every position 1 to {SCORE_POSITION_COUNT} exactly once"
            )
        return self

    @model_validator(mode="after")
    def validate_entry_is_not_empty(self) -> Self:
        if not (self.fields or self.scores or self.paragraphs):
            raise ValueError("a visible entry needs fields, scores or paragraphs")
        return self


class PhotoObservation(DomainModel):
    """The complete model-produced observation; it contains no local IDs or geometry."""

    # Equal bounds pin the version using Gemini's documented JSON Schema subset.
    schema_version: int = Field(default=SCHEMA_VERSION, ge=SCHEMA_VERSION, le=SCHEMA_VERSION)
    photo_overview: PhotoOverview = Field(...)
    layout: LayoutObservation = Field(...)
    entries: tuple[ObservedEntry, ...] = Field(...)
    visual_notes: tuple[_NONEMPTY, ...] = Field(...)


def model_response_json_schema() -> dict[str, Any]:
    """Return the strict JSON Schema passed to Gemini structured output."""
    return PhotoObservation.model_json_schema(by_alias=True)


class PhotoProvenance(DomainModel):
    photo_path: _NONEMPTY
    photo_sha256: _SHA256
    model: _NONEMPTY
    sdk_version: _NONEMPTY
    prompt_version: int = Field(ge=1)
    schema_version: int = Field(ge=1)


class DayEntry(DomainModel):
    source: PhotoProvenance
    source_entry_index: int = Field(ge=1)
    fields: tuple[FormField, ...] = ()
    scores: tuple[ScoreObservation, ...] = ()
    paragraphs: tuple[_NONEMPTY, ...] = ()
    crossed_out_corrections_omitted: bool
    visual_notes: tuple[_NONEMPTY, ...] = ()


class CalendarDay(DomainModel):
    schema_version: int = Field(ge=1)
    date: CalendarDate
    entries: tuple[DayEntry, ...] = Field(min_length=1)


class ReviewIssue(DomainModel):
    """Review reasons for one entry, or for the whole photo when it has no entries."""

    entry_index: int | None = Field(ge=1)
    reasons: tuple[_NONEMPTY, ...]


class NormalizationResult(DomainModel):
    days: tuple[CalendarDay, ...]
    review_issues: tuple[ReviewIssue, ...]
