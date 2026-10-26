from __future__ import annotations

import hashlib
import json
from pathlib import Path

from diary_photo_transcription.config import ProjectConfig
from diary_photo_transcription.prompts import PROMPT_VERSION
from diary_photo_transcription.schemas import SCHEMA_VERSION


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def config_fingerprint(config: ProjectConfig) -> str:
    """Hash every setting that can change the model output.

    The vault target and the SDK version are excluded: an SDK upgrade must not
    resubmit unchanged photos. The SDK version stays in run provenance.
    """
    payload = {
        "effectivePrompt": config.effective_prompt,
        "localConfig": config.local.model_dump(exclude={"vault_dir"}),
        "mediaResolution": config.media_resolution,
        "model": config.model,
        "promptVersion": PROMPT_VERSION,
        "schemaVersion": SCHEMA_VERSION,
        "thinkingLevel": config.thinking_level,
    }
    serialized = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def extraction_run_id(photo_sha256: str, config: ProjectConfig) -> str:
    """Identify one photo extraction per output-relevant configuration."""
    return f"{photo_sha256[:16]}-{config_fingerprint(config)[:16]}"
