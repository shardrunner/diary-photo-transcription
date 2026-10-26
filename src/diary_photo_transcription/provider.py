"""Provider-neutral request types: the captured photo and one model response."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from decimal import Decimal
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError


@dataclass(frozen=True, slots=True)
class TokenUsage:
    """Visible output and thinking/reasoning tokens are counted separately."""

    input_tokens: int
    output_tokens: int
    thinking_tokens: int
    total_tokens: int


@dataclass(frozen=True, slots=True)
class ModelResult:
    raw_text: str
    usage: TokenUsage
    interaction_id: str | None
    request_duration_seconds: float
    # Provider-reported cost; when absent the adapter estimates it from usage.
    cost_usd: Decimal | None = None


@dataclass(frozen=True, slots=True)
class PhotoSnapshot:
    """Immutable source bytes and identity; prepare upload pixels only on demand."""

    path: Path
    sha256: str
    source_bytes: bytes = field(repr=False)

    @classmethod
    def capture(cls, path: Path) -> PhotoSnapshot:
        path = path.resolve(strict=True)
        source = path.read_bytes()
        return cls(path, hashlib.sha256(source).hexdigest(), source)

    @property
    def upload_bytes(self) -> bytes:
        """EXIF-orient and re-encode the captured bytes without any source metadata."""
        try:
            with Image.open(BytesIO(self.source_bytes)) as image:
                if image.format != "JPEG":
                    raise ValueError("selected photo is not a JPEG")
                image.load()
                oriented = ImageOps.exif_transpose(image).convert("RGB")
                clean = Image.frombytes("RGB", oriented.size, oriented.tobytes())
                buffer = BytesIO()
                clean.save(buffer, format="JPEG", quality=95)
        except (UnidentifiedImageError, OSError) as error:
            raise ValueError("selected photo is not a valid JPEG") from error
        return buffer.getvalue()
