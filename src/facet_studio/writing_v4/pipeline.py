"""End-to-end writing pathway: writer -> editorial pass -> SVG pass.

The writer is one call.  The editorial pass is bounded: review a fix list,
then apply only that list.  SVG placeholders are rendered locally from a
small spec, never written by the model as raw SVG.  No word-list floor check.

Usage:
    PYTHONPATH=src python -m facet_studio.writing_v4.pipeline \
        --video-id <video-id> \
        --content runs/.../content.md \
        --out-dir runs/.../out

    # Re-run editorial + SVG on an existing draft:
    ... --article runs/.../content_final_v3/article.md
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from . import consistency_pass, run, svg_pass


def _copy_figures(source_dir: Path, out_dir: Path) -> int:
    source = source_dir / "figures"
    if not source.is_dir():
        return 0
    target = out_dir / "figures"
    target.mkdir(parents=True, exist_ok=True)
    copied = 0
    for item in source.iterdir():
        if item.is_file():
            shutil.copy2(item, target / item.name)
            copied += 1
    return copied


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Writer -> editor -> SVG -> checks.")
    parser.add_argument("--video-id", required=True)
    parser.add_argument("--content", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--article", type=Path, default=None,
                        help="Existing draft; skips the writer call.")
    parser.add_argument("--source-json", type=Path, default=None)
    parser.add_argument("--request", default="")
    parser.add_argument("--request-file", type=Path, default=None)
    parser.add_argument("--temperature", type=float, default=0.4)
    parser.add_argument("--skip-svg", action="store_true")
    args = parser.parse_args(argv)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    _copy_figures(args.content.parent, args.out_dir)

    draft_path = args.out_dir / "article_draft.md"
    if args.article is not None:
        shutil.copy2(args.article, draft_path)
        _copy_figures(args.article.parent, args.out_dir)
    else:
        run.main(
            [
                "--video-id", args.video_id,
                "--packet", str(args.content),
                "--out-dir", str(args.out_dir),
                "--request", args.request,
                *(["--request-file", str(args.request_file)] if args.request_file else []),
                *(["--source-json", str(args.source_json)] if args.source_json else []),
                "--temperature", str(args.temperature),
            ]
        )
        produced = args.out_dir / "article.md"
        if produced.exists():
            produced.replace(draft_path)

    edited_path = args.out_dir / "article_edited.md"
    consistency_pass.main(
        [
            "--article", str(draft_path),
            "--content", str(args.content),
            "--out-article", str(edited_path),
            "--out-report", str(args.out_dir / "consistency_report.md"),
            "--out-dir", str(args.out_dir),
        ]
    )

    final_path = args.out_dir / "article.md"
    if args.skip_svg:
        shutil.copy2(edited_path, final_path)
        (args.out_dir / "svg_report.md").write_text("跳过 SVG pass。\n", encoding="utf-8")
    else:
        svg_pass.main(
            [
                "--article", str(edited_path),
                "--out-article", str(final_path),
                "--out-report", str(args.out_dir / "svg_report.md"),
            ]
        )

    print(json.dumps({"article": str(final_path)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
