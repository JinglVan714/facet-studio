"""Run a multi-form bundle: compile -> Lead Planner -> writers -> bundle.

Usage:
    PYTHONPATH=src python -m facet_studio.writing_v4.run_bundle \
        --video-id BV17DHC6CELr \
        --content runs/.../content.md \
        --out-root runs/writing_v5 \
        --request "生成一套内容包：公众号 + 小红书" \
        --forms wechat_article,xiaohongshu_note
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ..core.config import get_settings
from .orchestrator import run_bundle


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run a multi-form writing bundle.")
    parser.add_argument("--video-id", required=True)
    parser.add_argument("--content", type=Path, required=True)
    parser.add_argument("--out-root", type=Path, default=Path("runs/writing_v5"))
    parser.add_argument("--request", default="")
    parser.add_argument("--request-file", type=Path, default=None)
    parser.add_argument(
        "--forms",
        default="",
        help="逗号分隔的 form id；留空让 planner 选",
    )
    parser.add_argument("--source-json", type=Path, default=None)
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--concurrency", type=int, default=3)
    parser.add_argument("--no-planner", action="store_true")
    parser.add_argument("--replay-from", type=Path, default=None)
    args = parser.parse_args(argv)

    settings = get_settings()
    if args.replay_from is None and not settings.provider_configured:
        raise SystemExit(
            "provider not configured (DEEPSEEK_API_KEY / DEEPSEEK_MODEL)"
        )

    request = args.request
    if args.request_file is not None:
        request = args.request_file.read_text(encoding="utf-8").strip()
    required_forms = [
        item.strip() for item in args.forms.split(",") if item.strip()
    ] or None

    result = run_bundle(
        video_id=args.video_id,
        content_path=args.content,
        out_root=args.out_root,
        request=request,
        required_forms=required_forms,
        source_json=args.source_json,
        settings=settings,
        concurrency=args.concurrency,
        run_id=args.run_id,
        use_planner=not args.no_planner,
        replay_from=args.replay_from,
    )
    summary = {
        "run_id": result.run_id,
        "run_dir": str(result.run_dir),
        "status": result.status,
        "bundle_manifest": str(result.run_dir / "bundle_manifest.json"),
        "bundle_md": str(result.run_dir / "bundle.md"),
        "forms": [
            {
                "form": item.form,
                "status": item.status,
                "output": item.output,
                "chars": item.output_chars,
                "error": item.error,
            }
            for item in result.forms
        ],
        "plan_source": result.plan.source,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
