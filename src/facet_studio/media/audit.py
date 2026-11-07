"""Reader-facing frame audit helpers (no model call).

The final semantic verifier can receive the real frames that the article
actually displays.  This module loads only those frames, keeps their rendered
caption, and downscales them for a VLM call.  Charts/diagrams are SVG/text
specs, not video evidence, so they are not included here.
"""

from __future__ import annotations

import re
from io import BytesIO
from pathlib import Path
from typing import Any

FRAME_IMAGE = re.compile(r"!\[frame\]\(assets/([^)]+)\)")
CAPTION_LINE = re.compile(r"^\s*\*[^*].*\*\s*$")


def _caption_after(lines: list[str], start: int) -> str:
    for line in lines[start + 1 : start + 6]:
        stripped = line.strip()
        if not stripped:
            continue
        if CAPTION_LINE.match(stripped):
            return stripped.strip("*").strip()
        # A non-caption paragraph means the caption is missing; do not walk
        # deep into the section looking for an unrelated italic line.
        break
    return ""


def _prepare_image(data: bytes, max_edge: int = 1024) -> tuple[bytes, str, dict[str, Any]]:
    """Return (bytes, media_type, metadata); fall back to original bytes."""
    try:
        from PIL import Image
    except ImportError:
        return data, "image/jpeg", {"downscaled": False, "pillow": "unavailable"}
    try:
        with Image.open(BytesIO(data)) as image:
            width, height = image.size
            image = image.convert("RGB")
            image.thumbnail((max_edge, max_edge))
            buffer = BytesIO()
            image.save(buffer, format="JPEG", quality=80, optimize=True)
            return (
                buffer.getvalue(),
                "image/jpeg",
                {
                    "downscaled": (width, height) != image.size,
                    "width": width,
                    "height": height,
                    "sent_width": image.size[0],
                    "sent_height": image.size[1],
                },
            )
    except Exception:
        return data, "image/jpeg", {"downscaled": False, "error": "image_decode_failed"}


def load_article_frame_images(
    article: str,
    assets_dir: Path,
    *,
    max_images: int = 6,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Load frame images referenced by ``article`` in reading order.

    Returns ``(images, skipped)``.  ``images`` rows contain the bytes for the
    VLM call plus the rendered caption and frame id for the prompt manifest.
    ``skipped`` makes missing/large assets explicit instead of silent.
    """
    lines = article.splitlines()
    assets_dir = Path(assets_dir)
    images: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, line in enumerate(lines):
        for match in FRAME_IMAGE.finditer(line):
            name = match.group(1)
            if name in seen:
                continue
            seen.add(name)
            if len(images) >= max_images:
                skipped.append({"name": name, "reason": "max_images"})
                continue
            path = assets_dir / name
            if not path.is_file():
                skipped.append({"name": name, "reason": "missing_asset"})
                continue
            original = path.read_bytes()
            data, media_type, meta = _prepare_image(original)
            frame_id = path.stem
            if frame_id.startswith("frame_"):
                frame_id = frame_id[len("frame_") :]
            images.append(
                {
                    "data": data,
                    "media_type": media_type,
                    "name": name,
                    "frame_id": frame_id,
                    "caption": _caption_after(lines, index),
                    "original_bytes": len(original),
                    "sent_bytes": len(data),
                    **meta,
                }
            )
    return images, skipped
