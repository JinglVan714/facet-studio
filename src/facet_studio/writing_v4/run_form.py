"""Run one writing skill once: content in, product out.

This is the single-form CLI for the writing-v5 path.  It uses the same
``write_form`` as the bundle orchestrator: skill composition (core + form
layer), figure copy, SVG placeholder rendering, title-candidate sidecar,
source line and metadata.  No draft/editor/checker.

Usage:
    PYTHONPATH=src python -m facet_studio.writing_v4.run_form \
        --video-id <video-id> \
        --content runs/.../content.md \
        --out-dir runs/.../<form> \
        --skill-dir skills/writing/wechat-article \
        --request "..."
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ..core.config import get_settings
from .writer import WriterError, write_form


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run one writing skill once.")
    parser.add_argument("--video-id", required=True)
    parser.add_argument("--content", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument(
        "--skill-dir",
        type=Path,
        default=Path("skills/writing/wechat-article"),
    )
    parser.add_argument("--request", default="")
    parser.add_argument("--request-file", type=Path, default=None)
    parser.add_argument("--source-json", type=Path, default=None)
    parser.add_argument("--temperature", type=float, default=None)
    parser.add_argument("--max-tokens", type=int, default=None)
    args = parser.parse_args(argv)

    settings = get_settings()
    if not settings.provider_configured:
        raise SystemExit(
            "provider not configured (DEEPSEEK_API_KEY / DEEPSEEK_MODEL)"
        )

    request = args.request
    if args.request_file is not None:
        request = args.request_file.read_text(encoding="utf-8").strip()

    try:
        result = write_form(
            video_id=args.video_id,
            content_path=args.content,
            out_dir=args.out_dir,
            skill_dir=args.skill_dir,
            request=request,
            source_json=args.source_json,
            settings=settings,
            temperature=args.temperature,
            max_tokens=args.max_tokens,
        )
    except WriterError as exc:
        raise SystemExit(str(exc)) from exc

    print(json.dumps(result.as_dict(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
