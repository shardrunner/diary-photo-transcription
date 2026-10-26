import json
import socket
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from PIL import Image

from diary_photo_transcription import gemini
from diary_photo_transcription.gemini import GeminiResult, GeminiUsage
from diary_photo_transcription.schemas import (
    CalendarDay,
    DayEntry,
    FieldItem,
    FieldLabel,
    FormField,
    PhotoObservation,
    PhotoProvenance,
    ScoreObservation,
)


@pytest.fixture(autouse=True)
def isolate_local_config(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TAGEBUCH_CONFIG", "")
    monkeypatch.setenv("PYTHON_DOTENV_DISABLED", "1")
    for key in (
        "GEMINI_API_KEY",
        "GOOGLE_API_KEY",
        "GOOGLE_GENAI_DEBUG",
        "GOOGLE_APPLICATION_CREDENTIALS",
        "GOOGLE_CLOUD_PROJECT",
        "GOOGLE_GENAI_USE_VERTEXAI",
        "GOOGLE_CLOUD_LOCATION",
    ):
        monkeypatch.delenv(key, raising=False)

    def blocked(*args, **kwargs):
        raise AssertionError("Network access is forbidden in tests; mock the transport")

    for method in ("connect", "connect_ex", "sendto", "sendmsg"):
        monkeypatch.setattr(socket.socket, method, blocked)
    for method in (
        "create_connection",
        "getaddrinfo",
        "gethostbyname",
        "gethostbyname_ex",
        "gethostbyaddr",
        "getnameinfo",
    ):
        monkeypatch.setattr(socket, method, blocked)


@pytest.fixture
def synthetic_day() -> CalendarDay:
    return CalendarDay(
        schema_version=2,
        date=date(2040, 1, 2),
        entries=(
            DayEntry(
                source=PhotoProvenance(
                    photo_path="private/source/synthetic.jpg",
                    photo_sha256="a" * 64,
                    model="local-test-model",
                    sdk_version="0.0-test",
                    prompt_version=1,
                    schema_version=2,
                ),
                source_entry_index=1,
                fields=(
                    FormField(
                        label="Prios",
                        raw_label_text="Prios:",
                        items=(
                            FieldItem(text="Erster Punkt", completion="fulfilled"),
                            FieldItem(text="Zweiter Punkt", completion="unmarked"),
                        ),
                    ),
                ),
                scores=(
                    ScoreObservation(
                        position=1,
                        symbol_description="Stundenglas",
                        state="struck_through",
                    ),
                    ScoreObservation(
                        position=3,
                        symbol_description="Helm",
                        state="written",
                        raw_value="4",
                        value=4,
                    ),
                ),
                paragraphs=(
                    "Synthetischer Absatz.",
                    "Reiner Testtext mit ⟦unsicher: Beispiel⟧.",
                ),
                crossed_out_corrections_omitted=False,
                visual_notes=("Synthetische sichtbare Notiz.",),
            ),
        ),
    )


def _observation(count: int) -> PhotoObservation:
    """Minimal valid observation with `count` dated text-only entries."""
    return PhotoObservation.model_validate(
        {
            "schemaVersion": 2,
            "photoOverview": {"tags": [], "note": "Synthetic"},
            "layout": {"followsExpectedLayout": True},
            "visualNotes": [],
            "entries": [
                {
                    "date": date(2040, 1, index + 1),
                    "dateCertainty": "certain",
                    "fields": [],
                    "absentLabels": list(FieldLabel),
                    "scores": [],
                    "paragraphs": ["Example text."],
                    "crossedOutCorrectionsOmitted": False,
                    "visualNotes": [],
                }
                for index in range(count)
            ],
        }
    )


@pytest.fixture
def make_observation() -> Callable[[int], PhotoObservation]:
    return _observation


DEMO_RAW = (Path(__file__).parents[1] / "examples/demo/expected.json").read_text("utf-8")


def _clean_raw() -> str:
    """The demo observation without anything a reviewer would need to re-check."""
    data = json.loads(DEMO_RAW.replace("⟦unleserlich⟧", "Boot"))
    entry = data["entries"][0]
    entry["absentLabels"].remove("Datum")
    entry["fields"] = [
        {"label": "Datum", "items": [{"text": "2040-01-02", "completion": "unmarked"}]}
    ]
    return json.dumps(data, ensure_ascii=False)


@dataclass
class FakeGemini:
    """Offline stand-in for the paid request; records prompts and saves evidence."""

    raw_text: str = DEMO_RAW
    error: Exception | None = None
    prompts: list[str] = field(default_factory=list)

    @staticmethod
    def clean_raw() -> str:
        return _clean_raw()

    def request(self, client: object, *, model: str, prompt: str, **kwargs: Any) -> GeminiResult:
        self.prompts.append(prompt)
        if on_interaction := kwargs.get("on_interaction"):
            on_interaction({"interaction": {"output_text": self.raw_text}})
        if self.error is not None:
            raise self.error
        return GeminiResult(
            raw_text=self.raw_text,
            usage=GeminiUsage(100, 20, 30, 150),
            interaction_id="interaction",
            request_duration_seconds=0.1,
        )


@pytest.fixture
def fake_gemini(monkeypatch: pytest.MonkeyPatch) -> FakeGemini:
    fake = FakeGemini()
    monkeypatch.setattr(gemini, "create_client", lambda: object())
    monkeypatch.setattr(gemini, "request_observation", fake.request)
    return fake


def _make_photo(path: Path, color: tuple[int, int, int] = (10, 20, 30)) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (8, 8), color).save(path, "JPEG")
    return path


@pytest.fixture
def make_photo() -> Callable[..., Path]:
    return _make_photo
