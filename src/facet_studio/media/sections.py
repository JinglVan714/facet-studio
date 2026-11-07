"""Split/rejoin a Markdown article around H2 sections.

The visual layer inserts assets after a section body; binding and reader
hygiene ignore image lines and italic captions, so this stays audit-safe.
"""

from __future__ import annotations

from typing import Any


def split_article(article: str) -> tuple[str, list[dict[str, Any]]]:
    lines = article.splitlines()
    title = ""
    body_start = 0
    for index, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("# ") and not stripped.startswith("## "):
            title = stripped
            body_start = index + 1
            break

    sections: list[dict[str, Any]] = []
    current: dict[str, Any] = {"index": 0, "heading": "", "lines": []}
    for line in lines[body_start:]:
        stripped = line.strip()
        if stripped.startswith("## "):
            sections.append(current)
            current = {
                "index": len(sections),
                "heading": stripped[3:].strip(),
                "lines": [],
            }
        else:
            current["lines"].append(line)
    sections.append(current)
    for section in sections:
        while section["lines"] and not section["lines"][0].strip():
            section["lines"].pop(0)
        while section["lines"] and not section["lines"][-1].strip():
            section["lines"].pop()
    return title, sections


def section_text(section: dict[str, Any]) -> str:
    heading = section.get("heading", "")
    body = "\n".join(section.get("lines", [])).strip()
    return (heading + "\n\n" + body).strip() if heading else body


def join_article(title: str, sections: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    if title:
        parts.append(title)
    for section in sections:
        body = "\n".join(section.get("lines", [])).strip()
        heading = section.get("heading", "")
        if heading:
            parts.append(f"## {heading}" + (f"\n\n{body}" if body else ""))
        elif body:
            parts.append(body)
    return "\n\n".join(parts).strip() + "\n"
