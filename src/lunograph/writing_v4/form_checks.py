"""Floor checks for non-article forms.

These are form-aware versions of :mod:`article_checks`: they keep the same
"do not leak the machinery" rule, but do not force an H1/source-line shape
onto a social note or a production script.  They are floors, not judges.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

LEAK_WORDS = (
    "素材包",
    "内容稿",
    "原文",
    "转写",
    "证据包",
    "视频里",
    "视频中",
    "这条视频",
    "这个视频",
    "本期视频",
    "UP 主",
    "UP主",
    "作者说",
    "作者建议",
    "作者提到",
    "claim",
    "audit",
)
TIMECODE = re.compile(r"(?<![\d:])\d{1,2}:\d{2}(?![\d:])")
IMAGE = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")
FIGURE_PATH = re.compile(r"figures/[A-Za-z0-9._\-/]+")
SOURCE_TAIL = re.compile(
    r"\n*---\s*\n+\s*((?:本文根据|素材来源)[^\n]*)\s*$"
)
TITLE = re.compile(r"^#\s+(.+)$", re.M)


def split_source_block(text: str) -> tuple[str, str]:
    """Keep the one-line provenance out of the body being checked."""
    match = SOURCE_TAIL.search(text)
    if not match:
        return text, ""
    return text[: match.start()].rstrip() + "\n", match.group(1).strip()


def _image_issues(text: str, *, repo_root: Path, article_dir: Path) -> list[str]:
    issues: list[str] = []
    targets = set(IMAGE.findall(text))
    targets.update(FIGURE_PATH.findall(text))
    for target in sorted(targets):
        target = target.strip()
        if not target:
            continue
        candidates = [repo_root / target, article_dir / target]
        if not any(path.exists() for path in candidates):
            issues.append(f"missing image: {target}")
    return issues


def _leak_issues(body: str) -> list[str]:
    issues: list[str] = []
    for index, line in enumerate(body.splitlines(), start=1):
        for word in LEAK_WORDS:
            if word in line:
                issues.append(f"line {index}: leak word {word!r}")
        for match in TIMECODE.finditer(line):
            issues.append(f"line {index}: timecode {match.group(0)!r}")
    return issues


def _text_chars(body: str) -> int:
    return len(re.sub(r"\s+", "", body))


def check_social(
    path: Path,
    *,
    repo_root: Path,
    require_source: bool = True,
) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    body, source = split_source_block(text)
    issues: list[str] = []
    warnings: list[str] = []

    if not TITLE.search(body):
        issues.append("missing H1 title")
    issues.extend(_leak_issues(body))
    issues.extend(_image_issues(body, repo_root=repo_root, article_dir=path.parent))
    if require_source and not source:
        issues.append("missing one-line source line at the end")

    chars = _text_chars(body)
    if chars < 120:
        warnings.append(f"social note is short ({chars} chars)")
    if chars > 900:
        warnings.append(f"social note is long ({chars} chars)")

    return {
        "form": "social",
        "path": str(path),
        "chars": chars,
        "source": source,
        "issues": issues,
        "warnings": warnings,
        "ok": not issues,
    }


def check_script(
    path: Path,
    *,
    repo_root: Path,
    require_source: bool = True,
) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    body, source = split_source_block(text)
    issues: list[str] = []
    warnings: list[str] = []

    if not TITLE.search(body):
        issues.append("missing H1 title")
    if "## 旁白" not in body:
        issues.append("missing 旁白 section")
    if "## 镜头" not in body and "## 分镜" not in body:
        issues.append("missing 镜头/分镜 section")
    issues.extend(_leak_issues(body))
    issues.extend(_image_issues(body, repo_root=repo_root, article_dir=path.parent))
    if require_source and not source:
        issues.append("missing one-line source line at the end")

    chars = _text_chars(body)
    if chars < 400:
        warnings.append(f"script is short ({chars} chars)")
    if chars > 3000:
        warnings.append(f"script is long ({chars} chars)")

    return {
        "form": "script",
        "path": str(path),
        "chars": chars,
        "source": source,
        "issues": issues,
        "warnings": warnings,
        "ok": not issues,
    }


def check_form(
    path: Path,
    *,
    profile: str,
    repo_root: Path,
    require_source: bool = True,
) -> dict[str, Any]:
    if profile == "social":
        return check_social(path, repo_root=repo_root, require_source=require_source)
    if profile == "script":
        return check_script(path, repo_root=repo_root, require_source=require_source)
    if profile == "article":
        from .article_checks import check_article

        report = check_article(path, repo_root=repo_root)
        report = dict(report)
        report.setdefault("form", "article")
        report.setdefault("warnings", [])
        return report
    if profile == "none":
        return {
            "form": "none",
            "path": str(path),
            "issues": [],
            "warnings": [],
            "ok": True,
        }
    raise ValueError(f"unknown check profile: {profile}")


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Floor checks for a writing form.")
    parser.add_argument("path", type=Path)
    parser.add_argument("--profile", default="social", choices=["social", "script", "article", "none"])
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--no-require-source", action="store_true")
    args = parser.parse_args(argv)

    report = check_form(
        args.path,
        profile=args.profile,
        repo_root=args.repo_root,
        require_source=not args.no_require_source,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
