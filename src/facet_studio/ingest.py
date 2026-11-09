"""P5 source ingestion: new video -> evidence layer -> content manuscript cache.

This is the product-facing bridge.  The evidence layer does acquisition, frame
extraction, ASR, VLM and substrate; the writing layer only consumes the
resulting ``content.md + figures`` exactly as it does for cached sources.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from .core.config import CONTENT_CACHE_DIRNAME, get_settings
from .evidence_layer import acquire
from .evidence_layer.ingest import run_ingest
from .writing_v4.content_manuscript import build_content_manuscript


def ingest_source(
    target: str,
    *,
    profile: str = "quality",
    force: bool = False,
    max_height: int = 1080,
    build_content: bool = True,
    include_evidence: bool = False,
) -> dict[str, Any]:
    """Acquire a URL/local video and build a cached content manuscript.

    ``target`` is a Bilibili URL or a local video path.  The returned
    ``content_path`` is placed where the existing MCP source resolver already
    looks, so the normal plan/write/typeset flow can use it immediately.

    The product path defaults to ``include_evidence=False``: the writing layer
    only consumes transcript + frames + VLM captions, so the paid contract/L1
    knowledge substrate is skipped.  Set ``include_evidence=True`` when the
    evidence pipeline itself is the goal.
    """
    if profile not in {"fast", "quality"}:
        raise ValueError(f"profile 必须是 fast/quality：{profile}")
    settings = get_settings()
    info = (
        acquire.acquire_url(target, max_height=max_height)
        if acquire.is_url(target)
        else acquire.acquire_local(target)
    )
    video_id = str(info["video_id"])
    ingestion = run_ingest(
        video_id,
        profile=profile,
        force=force,
        content_only=not include_evidence,
    )
    content_path = (
        settings.runs_root
        / CONTENT_CACHE_DIRNAME
        / video_id
        / "content_final_v3"
        / "content.md"
    )
    content_chars = 0
    figure_count = 0
    if build_content:
        text, figure_count = build_content_manuscript(
            video_id=video_id,
            data_root=settings.data_root,
            out_path=content_path,
        )
        content_chars = len(text)
    return {
        "video_id": video_id,
        "status": "content_ready" if build_content else "evidence_ready",
        "source": info,
        "ingest": ingestion,
        "content_path": str(content_path),
        "content_chars": content_chars,
        "figure_count": figure_count,
        "content_sha256": (
            hashlib.sha256(Path(content_path).read_bytes()).hexdigest()
            if Path(content_path).is_file()
            else ""
        ),
    }
