"""Offline schema/render/eval demonstration; never creates an API client."""

from pathlib import Path

from diary_photo_transcription.atomic import atomic_write
from diary_photo_transcription.evaluate import evaluate_observation
from diary_photo_transcription.normalize import normalize_observation
from diary_photo_transcription.provenance import sha256
from diary_photo_transcription.render import render_markdown
from diary_photo_transcription.schemas import PhotoObservation, PhotoProvenance


def main() -> None:
    fixtures = Path(__file__).parent
    observation = PhotoObservation.model_validate_json((fixtures / "expected.json").read_text())
    provenance = PhotoProvenance(
        photo_path="examples/demo/source.jpg",
        photo_sha256=sha256(fixtures / "source.jpg"),
        model="synthetic-reference",
        sdk_version="offline",
        prompt_version=9,
        schema_version=2,
    )
    result = normalize_observation(observation, provenance)
    for day in result.days:
        rendered = render_markdown(day)
        assert rendered == (fixtures / f"{day.date}.md").read_bytes()
        atomic_write(Path("private/demo") / f"{day.date}.md", rendered)
    report = evaluate_observation(observation, observation)
    assert report.is_exact_match
    print(f"Offline fixture validated; {len(result.review_issues)} review issue(s); private/demo/")
    print("Self-comparison tests software consistency, not handwriting recognition quality.")


if __name__ == "__main__":
    main()
