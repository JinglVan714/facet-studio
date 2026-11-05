"""Deterministic floor checks for a reader-facing article.

This is not a quality judge.  It catches leaks (material/audit language,
timecodes) and broken image paths so the reader never sees the machinery.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

LEAK_WORDS = (
    "素材",
    "素材包",
    "内容稿",
    "原文",
    "转写",
    "证据包",
    "视频里",
    "视频中",
    "本条视频",
    "这个视频",
    "UP 主",
    "UP主",
    "画面里",
    "画面中",
    "claim",
    "audit",
)
TIMECODE = re.compile(r"(?<![\d:])\d{1,2}:\d{2}(?![\d:])")
IMAGE = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")


def check_article(article_path: Path, *, repo_root: Path) -> dict[str, object]:
    text = article_path.read_text(encoding="utf-8")
    issues: list[str] = []

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines or not lines[0].startswith("# "):
        issues.append("missing H1 title")
    if not lines or "本文根据" not in lines[-1] or "整理" not in lines[-1]:
        issues.append("missing one-line source line at the end")

    body_lines = lines[:-1] if lines else []
    for index, line in enumerate(body_lines, start=1):
        for word in LEAK_WORDS:
            if word in line:
                issues.append(f"line {index}: leak word {word!r}")
        for match in TIMECODE.finditer(line):
            issues.append(f"line {index}: timecode {match.group(0)!r}")

    for target in IMAGE.findall(text):
        target = target.strip()
        candidates = [repo_root / target, article_path.parent / target]
        if not any(path.exists() for path in candidates):
            issues.append(f"missing image: {target}")

    return {
        "article": str(article_path),
        "chars": len(text),
        "issues": issues,
        "ok": not issues,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Floor checks for a reader article.")
    parser.add_argument("article", type=Path)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    args = parser.parse_args(argv)

    report = check_article(args.article, repo_root=args.repo_root)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
