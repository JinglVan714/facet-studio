"""Deterministic quote hygiene for prose articles.

The prose contract asks for quotation marks only around exact source text, but
models still quote paraphrases.  This pass removes the quotation marks around
any phrase that is not an exact (or punctuation/filler-normalized) substring
of the writer input.  It never changes the phrase itself; it only removes the
quote marks.  A report records what was kept and removed.

No model call.  This is an audit/cleanup pass, not a new fact source.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .bind_article import QUOTE_PATTERNS, _normalize_quote

SCHEMA = "quote-hygiene-v1"


def _in_source(value: str, source_text: str) -> bool:
    if not value:
        return False
    if value in source_text:
        return True
    normalized = _normalize_quote(value)
    return bool(normalized) and normalized in _normalize_quote(source_text)


def clean_article(article: str, source_text: str) -> dict[str, Any]:
    """Remove quote marks around phrases not found in the writer input."""
    report: dict[str, Any] = {
        "schema": SCHEMA,
        "checked": 0,
        "kept": 0,
        "removed": 0,
        "removed_quotes": [],
    }
    cleaned = article
    for pattern in QUOTE_PATTERNS:

        def replace(match: Any) -> str:
            value = match.group(1).strip()
            if len(_normalize_quote(value)) < 2:
                return match.group(0)
            report["checked"] += 1
            if _in_source(value, source_text):
                report["kept"] += 1
                return match.group(0)
            report["removed"] += 1
            report["removed_quotes"].append(value)
            return value

        cleaned = pattern.sub(replace, cleaned)
    report["changed"] = cleaned != article
    report["article_chars"] = len(cleaned)
    return {"article": cleaned, "report": report}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Remove quotation marks around phrases not present in the writer input."
    )
    parser.add_argument("--article", type=Path, required=True)
    parser.add_argument("--source-text", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args(argv)

    article = args.article.read_text(encoding="utf-8-sig")
    source_text = args.source_text.read_text(encoding="utf-8-sig")
    result = clean_article(article, source_text)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(result["article"], encoding="utf-8")
    args.report.write_text(
        json.dumps(result["report"], ensure_ascii=False, indent=1),
        encoding="utf-8",
    )
    print(json.dumps(result["report"], ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
