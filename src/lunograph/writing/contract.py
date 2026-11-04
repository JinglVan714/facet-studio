"""Deterministic reader-facing contract audit.

This is not a quality score.  It checks the small set of structural promises
that the writer/brief must keep and that binding cannot see:

- a reader-facing source line exists;
- a title quote/number is actually in the body;
- every image has a caption line;
- a known source gap is disclosed;
- absolute words are surfaced as advisory findings for the semantic Verifier.

Findings are deliberately explicit and quote-located; the Verifier decides
whether an advisory item is a real defect.
"""

from __future__ import annotations

import re
from typing import Any

NUMBER = re.compile(r"(?<![0-9A-Za-z_.])\d+(?:\.\d+)?%?(?![0-9A-Za-z_.])")
SOURCE_LINE = re.compile(
    r"(?m)^\s*(?:\*\*)?(?:来源|来源信息|Source)(?:\*\*)?\s*[:：]"
)
SOURCE_HEADING = re.compile(r"(?m)^##\s*(?:来源|来源信息|Source)\s*$")
TITLE_QUOTE = re.compile(r"[“「]([^”」]{2,})[”」]")
IMAGE = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")
ABSOLUTE = re.compile(r"(任何|唯一|所有|必然|证明|就是|真正|永远)")
GENERAL_MISSING_MARKERS = (
    "未提供",
    "没有提供",
    "待补",
    "unknown",
    "未核实",
    "未知",
    "未给出",
)
FIELD_MARKERS = {
    "title": ("标题",),
    "channel": ("频道", "up主", "作者", "账号"),
    "date": ("日期", "发布"),
    "link": ("链接", "url"),
    "official_docs": ("官方", "文档"),
}


def _undisclosed_missing(source_text: str, missing: list[str]) -> list[str]:
    """Fields not covered by a general or field-specific disclosure.

    A bare search hint ("可在 B 站搜索") is not a disclosure that the title /
    channel / date / link are missing.
    """
    text = source_text.lower()
    general = any(marker in text for marker in GENERAL_MISSING_MARKERS)
    uncovered: list[str] = []
    for field in missing:
        if general:
            continue
        aliases = FIELD_MARKERS.get(field, ())
        if any(alias in text for alias in aliases):
            continue
        uncovered.append(field)
    return uncovered


def _finding(
    axis: str,
    severity: str,
    quote: str,
    observation: str,
    impact: str,
    action: str,
    *,
    blocking: bool = False,
) -> dict[str, Any]:
    return {
        "axis": axis,
        "severity": severity,
        "quote": quote,
        "observation": observation,
        "impact": impact,
        "action": action,
        "blocking": blocking,
    }


def _source_missing(brief: dict[str, Any] | None, source_map: dict[str, Any] | None) -> list[str]:
    block = (brief or {}).get("source_block")
    if isinstance(block, dict):
        return [str(item) for item in block.get("missing", []) if str(item).strip()]
    provenance = (source_map or {}).get("provenance")
    if isinstance(provenance, dict):
        return [str(item) for item in provenance.get("missing", []) if str(item).strip()]
    return []


def audit_contract(
    article: str,
    *,
    brief: dict[str, Any] | None = None,
    source_map: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return deterministic findings; never calls a model or edits the article."""
    findings: list[dict[str, Any]] = []
    lines = article.splitlines()
    title_line = next((line.strip() for line in lines if line.strip().startswith("# ")), "")
    body = "\n".join(lines[1:]) if title_line else article

    has_source = bool(SOURCE_LINE.search(article) or SOURCE_HEADING.search(article))
    if not has_source:
        findings.append(
            _finding(
                "source",
                "high",
                title_line[:120],
                "No reader-facing source line/heading.",
                "The reader cannot tell what video/official material the article is based on.",
                "Add one short source line near the end (title/channel/date/link or a search term; mark unknown fields).",
                blocking=True,
            )
        )

    source_text = "\n".join(
        line for line in lines if SOURCE_LINE.search(line) or line.strip().startswith("来源")
    ) or article

    if title_line:
        for quote in TITLE_QUOTE.findall(title_line):
            if quote not in body:
                findings.append(
                    _finding(
                        "title_cta",
                        "medium",
                        title_line[:160],
                        f"Title quote {quote!r} does not appear verbatim in the body.",
                        "The title implies a quotation the article does not actually contain.",
                        "Put the exact quote in the body or remove the quotation marks from the title.",
                        blocking=True,
                    )
                )
        for number in NUMBER.findall(title_line):
            if number not in body:
                findings.append(
                    _finding(
                        "title_cta",
                        "medium",
                        title_line[:160],
                        f"Title number {number!r} does not appear in the body.",
                        "The title promise is not cashed by the body.",
                        "Use the number in the body or remove it from the title.",
                        blocking=True,
                    )
                )

    for match in IMAGE.finditer(article):
        line_index = article.count("\n", 0, match.start())
        following = [
            line.strip()
            for line in lines[line_index + 1 : line_index + 4]
            if line.strip()
        ]
        if not following or not (
            following[0].startswith("*") and following[0].endswith("*")
        ):
            findings.append(
                _finding(
                    "image_caption",
                    "medium",
                    match.group(0)[:120],
                    "Image has no caption line immediately after it.",
                    "A reader cannot tell what to look for; the image becomes decoration.",
                    "Add a one-line 'look here' caption that matches what the image actually shows.",
                    blocking=True,
                )
            )

    missing = _source_missing(brief, source_map)
    if missing and has_source:
        uncovered = _undisclosed_missing(source_text, missing)
        if uncovered:
            findings.append(
                _finding(
                    "source",
                    "medium",
                    source_text[:160],
                    f"Source gaps {uncovered!r} are known but not disclosed in the source line.",
                    "The reader may read a video claim as an official/verified fact.",
                    "Disclose the missing title/date/link/official docs in the source line; do not invent them.",
                    blocking=True,
                )
            )

    absolutes = ABSOLUTE.findall(article)
    if absolutes:
        unique = sorted(set(absolutes))
        first = absolutes[0]
        findings.append(
            _finding(
                "consistency",
                "low",
                f"{first} ×{absolutes.count(first)}；{', '.join(unique)}",
                "Absolute words are present; each needs a scope check against the evidence.",
                "Unscoped absolutes can turn a single demo/case into a general rule.",
                "Hedge each absolute to the source scope or keep it only where the evidence supports it.",
                blocking=False,
            )
        )

    blocking = [item for item in findings if item.get("blocking")]
    return {
        "schema_version": "writing-contract-v1",
        "status": "partial" if blocking else "complete",
        "findings": findings,
        "blocking": blocking,
        "counts": {
            "findings": len(findings),
            "blocking": len(blocking),
            "absolutes": len(absolutes),
        },
    }
