"""Paid work: initial extraction and refinement, both published as complete runs."""

from __future__ import annotations

import json
from concurrent.futures import CancelledError
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from threading import Event
from typing import Any
from uuid import uuid4

from diary_photo_transcription import gemini, openai_api
from diary_photo_transcription.config import ProjectConfig, load_project_config
from diary_photo_transcription.normalize import review_targets
from diary_photo_transcription.prompts import PROMPT_VERSION, refinement_prompt
from diary_photo_transcription.provenance import config_fingerprint, extraction_run_id, sha256
from diary_photo_transcription.provider import ModelResult, PhotoSnapshot
from diary_photo_transcription.runs import (
    active_dir,
    keep_failed,
    pending_revisions,
    publish,
    read_issues,
    read_meta,
    read_observation,
    write_artifacts,
)
from diary_photo_transcription.schemas import SCHEMA_VERSION, PhotoObservation, PhotoProvenance

PHOTO_SUFFIXES = frozenset({".jpg", ".jpeg"})


@dataclass(frozen=True, slots=True)
class ExtractionResult:
    run_dir: Path
    observation: PhotoObservation
    usage: dict[str, Any]
    skipped: bool = False

    @property
    def estimated_cost(self) -> Decimal:
        return Decimal(self.usage["estimatedStandardCostUsd"])


def discover_source_photos(source_dir: Path) -> list[Path]:
    """JPEGs directly in the source directory, any suffix capitalization."""
    return sorted(
        p for p in source_dir.iterdir() if p.is_file() and p.suffix.lower() in PHOTO_SUFFIXES
    )


def _usage(response: ModelResult, config: ProjectConfig) -> dict[str, Any]:
    """Content-free request metadata."""
    return {
        "interactionId": response.interaction_id,
        "model": config.model,
        "mediaResolution": config.media_resolution,
        "thinkingLevel": config.thinking_level,
        "requestDurationSeconds": round(response.request_duration_seconds, 6),
        "inputTokens": response.usage.input_tokens,
        "outputTokens": response.usage.output_tokens,
        "thinkingTokens": response.usage.thinking_tokens,
        "totalTokens": response.usage.total_tokens,
        "estimatedStandardCostUsd": format(
            _adapter(config).estimate_standard_cost_usd(response.usage), "f"
        ),
    }


def _adapter(config: ProjectConfig) -> Any:
    """The provider module; looked up at call time so tests can patch it."""
    return openai_api if config.provider == "openai" else gemini


def _display_path(photo: Path) -> str:
    try:
        return photo.relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        return photo.name


def _request_run(
    staging: Path,
    final: Path,
    photo: PhotoSnapshot,
    config: ProjectConfig,
    prompt: str,
    meta: dict[str, Any],
) -> ExtractionResult:
    """Save the provider response first, then validate, render and publish atomically."""
    staging.mkdir(parents=True)
    try:
        adapter = _adapter(config)
        response = adapter.request_observation(
            adapter.create_client(),
            model=config.model,
            photo=photo,
            prompt=prompt,
            thinking_level=config.thinking_level,
            media_resolution=config.media_resolution,
            on_interaction=lambda evidence: (staging / "interaction.json").write_text(
                json.dumps(evidence, ensure_ascii=False), encoding="utf-8"
            ),
        )
        usage = _usage(response, config)
        observation = write_artifacts(
            staging,
            response.raw_text,
            {
                **meta,
                "configFingerprint": config_fingerprint(config),
                "provenance": PhotoProvenance(
                    photo_path=_display_path(photo.path),
                    photo_sha256=photo.sha256,
                    model=config.model,
                    sdk_version=config.sdk_version,
                    prompt_version=PROMPT_VERSION,
                    schema_version=SCHEMA_VERSION,
                ).model_dump(mode="json", by_alias=True),
                "usage": usage,
            },
            prompt,
        )
        publish(staging, final)
    except BaseException as error:
        keep_failed(staging, error)
        raise
    return ExtractionResult(final, observation, usage)


def extract_photo(
    photo_path: Path,
    config: ProjectConfig,
    output_dir: Path,
    *,
    force: bool = False,
    cancel_event: Event | None = None,
) -> ExtractionResult:
    """Extract one photo unless this photo/config was already published (or `force`)."""
    photo = PhotoSnapshot.capture(photo_path)
    run = output_dir / extraction_run_id(photo.sha256, config)
    if force:
        run = run.with_name(f"{run.name}-rerun-{uuid4().hex}")
    elif run.exists():
        observation = read_observation(active_dir(run))
        return ExtractionResult(run, observation, read_meta(run)["usage"], skipped=True)
    if cancel_event is not None and cancel_event.is_set():
        raise CancelledError("Extraction cancelled before the provider request")
    staging = output_dir / f".staging-{uuid4().hex}"
    return _request_run(staging, run, photo, config, config.effective_prompt, {})


def find_source_photo(meta: dict[str, Any], source_dir: Path) -> Path | None:
    """Locate the photo by content hash, trying the recorded path first."""
    expected = meta["provenance"]["photoSha256"]
    recorded = Path(meta["provenance"]["photoPath"])
    candidates = [recorded, source_dir / recorded.name]
    if source_dir.is_dir():
        candidates += discover_source_photos(source_dir)
    for candidate in candidates:
        if candidate.is_file() and sha256(candidate) == expected:
            return candidate.resolve()
    return None


def refinement_config(run: Path) -> ProjectConfig:
    """Current local settings with the model, thinking and resolution the run was made with."""
    usage = read_meta(run)["usage"]
    return load_project_config(
        model=usage["model"],
        thinking_level=usage["thinkingLevel"],
        media_resolution=usage["mediaResolution"],
    )


def refine_run(run: Path, source_dir: Path) -> ExtractionResult | None:
    """Paid second pass over flagged places; the result waits for approve/reject."""
    if pending := pending_revisions(run):
        raise ValueError(f"{run.name} has undecided revision {pending[0]}; approve or reject it")
    parent = active_dir(run)
    targets = review_targets(read_observation(parent), read_issues(parent))
    if not targets:
        return None
    meta = read_meta(parent)
    photo_path = find_source_photo(meta, source_dir)
    if photo_path is None:
        raise FileNotFoundError(f"Source photo for {run.name} not found in {source_dir}")
    photo = PhotoSnapshot.capture(photo_path)
    if photo.sha256 != meta["provenance"]["photoSha256"]:
        raise ValueError(f"Source photo changed while refining {run.name}")
    config = refinement_config(run)
    revision = uuid4().hex
    return _request_run(
        run / "revisions" / f".staging-{revision}",
        run / "revisions" / revision,
        photo,
        config,
        refinement_prompt(targets, config.effective_prompt),
        {"parentRawSha256": sha256(parent / "raw.json")},
    )
