"""Deterministic validation/rendering for the prose Writer.

Reuses substrate v1 ``quote_hygiene`` and ``bind_article``.  Structure and
reader-hygiene checks are intentionally small; they are technical gates, not
reader-quality scores.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from ..writing_v3.bind_article import bind_article
from ..writing_v3.quote_hygiene import clean_article
from .contract import SOURCE_HEADING, SOURCE_LINE

ID_PATTERN = re.compile(
    r"\b(?:c_[A-Za-z0-9]+|ev_[A-Za-z0-9]+|seg\d+-[sp]\d+)\b"
)
AUDIT_WORD = re.compile(
    r"\b(?:claim_id|evidence_id|sentence_id|passage_id|timecode|citation)\b"
    r"|时间码|引用键"
)
TIMECODE = re.compile(r"\b\d{1,2}:\d{2}(?::\d{2})?\b")
CITE_MARK = re.compile(r"\[(?:cite|ref)[^\]]*\]", re.IGNORECASE)


def strip_code_fences(article: str) -> tuple[str, int]:
    """Remove fenced-code delimiters while keeping their content as text.

    The prose contract forbids fenced code; this is a deterministic cleanup,
    not a content rewrite.  The removed-fence count is reported in validation.
    """
    lines: list[str] = []
    removed = 0
    for line in article.splitlines():
        if line.strip().startswith("```"):
            removed += 1
            continue
        lines.append(line)
    return "\n".join(lines), removed


def _structure(article: str) -> dict[str, Any]:
    lines = article.splitlines()
    h1 = [
        line.strip()
        for line in lines
        if line.strip().startswith("# ") and not line.strip().startswith("## ")
    ]
    fences = [line for line in lines if line.strip().startswith("```")]
    paragraphs = [
        line.strip()
        for line in lines
        if line.strip()
        and not line.strip().startswith("#")
        and not line.strip().startswith("![")
        and not (
            line.strip().startswith("*")
            and line.strip().endswith("*")
            and not line.strip().startswith("**")
        )
    ]
    problems = []
    if len(h1) != 1:
        problems.append("article must have exactly one H1")
    if fences:
        problems.append("article must not contain code fences")
    if len(paragraphs) < 2:
        problems.append("article must contain at least two body paragraphs")
    return {"ok": not problems, "problems": problems, "h1": h1, "paragraphs": len(paragraphs)}


def _strip_source_block(article: str) -> str:
    """Remove reader-facing provenance lines before fact/quote binding.

    A source line/heading is metadata (video id, channel, link, official docs),
    not a video claim.  Binding it as a fact would mark a legitimate BV id as
    unsupported because it is absent from the edited transcript.
    """
    lines = article.splitlines()
    kept: list[str] = []
    skipping_section = False
    for line in lines:
        stripped = line.strip()
        if SOURCE_HEADING.match(stripped):
            skipping_section = True
            continue
        if skipping_section:
            if stripped.startswith("## "):
                skipping_section = False
                kept.append(line)
            continue
        if SOURCE_LINE.match(line):
            continue
        kept.append(line)
    return "\n".join(kept).strip()


def _demote_editorial_latin(binding: dict[str, Any]) -> dict[str, Any]:
    """Treat unexplained Latin tokens as editorial terms, not video facts.

    The skill allows the Writer to introduce/expand standard terms from model
    knowledge.  The deterministic binder cannot tell an explanatory term
    (``Programmatic Tool Calling``) from an invented product claim, so Latin
    tokens are advisory here and left to the independent verifier.  Numbers,
    quotes and outside-input facts remain hard binding gates.
    """
    unsupported = binding.get("unsupported_facts") or []
    latin = [item for item in unsupported if item.get("kind") == "latin"]
    if not latin:
        return binding
    hard = [item for item in unsupported if item.get("kind") != "latin"]
    binding["unsupported_facts"] = hard
    binding["editorial_terms"] = latin
    counts = binding.get("counts", {}).get("facts")
    if isinstance(counts, dict):
        counts["unsupported"] = len(hard)
        counts["editorial"] = len(latin)
        hard_total = counts.get("total", 0) - len(latin)
        counts["coverage"] = (
            round(counts.get("bound", 0) / hard_total, 4) if hard_total else 1.0
        )
    keys = {
        (item.get("paragraph_index"), item.get("kind"), item.get("value"))
        for item in latin
    }
    for paragraph in binding.get("paragraphs", []):
        index = paragraph.get("index")
        for fact in paragraph.get("facts", []):
            if (
                (index, fact.get("kind"), fact.get("value")) in keys
                and fact.get("status") == "unsupported"
            ):
                fact["status"] = "editorial"
                fact["input_status"] = "editorial"
    if (
        not hard
        and not binding.get("counts", {}).get("quotes", {}).get("unbound_long")
        and not binding.get("outside_input_facts")
        and not binding.get("outside_input_quotes")
    ):
        binding["status"] = "complete"
    return binding


def _reader_hygiene(article: str) -> dict[str, Any]:
    problems = []
    for pattern, label in (
        (ID_PATTERN, "internal_id"),
        (AUDIT_WORD, "audit_language"),
        (TIMECODE, "timecode"),
        (CITE_MARK, "citation_mark"),
    ):
        for match in pattern.finditer(article):
            problems.append({"kind": label, "value": match.group(0)})
    return {"ok": not problems, "problems": problems}


def validate_article(
    article: str,
    *,
    edited_text: str,
    pack: dict[str, Any],
    sentences: list[dict[str, Any]],
    source_map: dict[str, Any] | None = None,
) -> dict[str, Any]:
    article, code_fences_removed = strip_code_fences(article)
    hygiene = clean_article(article, edited_text)
    cleaned = hygiene["article"]
    binding = _demote_editorial_latin(
        bind_article(
            _strip_source_block(cleaned),
            pack,
            sentences,
            rendered_text=edited_text,
            source_map=source_map,
            input_text=edited_text,
        )
    )
    structure = _structure(cleaned)
    reader_hygiene = _reader_hygiene(cleaned)
    failures = []
    if not structure["ok"]:
        failures.append("structure")
    if not reader_hygiene["ok"]:
        failures.append("reader_hygiene")
    if binding.get("status") != "complete":
        failures.append("binding")
    status = "complete" if not failures else "partial"
    return {
        "schema_version": "validation-report-v1",
        "status": status,
        "article": cleaned,
        "quote_hygiene": hygiene["report"],
        "code_fences_removed": code_fences_removed,
        "binding": binding,
        "structure": structure,
        "reader_hygiene": reader_hygiene,
        "failures": failures,
    }


def render_bundle(
    out_dir: Path,
    *,
    request: dict[str, Any],
    skill: Any,
    context: dict[str, Any],
    validation: dict[str, Any],
    visual_plan: dict[str, Any] | None = None,
    media_assets: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    cleaned = validation["article"]
    binding = validation["binding"]
    (out_dir / "reader.md").write_text(cleaned, encoding="utf-8")
    (out_dir / "article.md").write_text(cleaned, encoding="utf-8")
    (out_dir / "binding.json").write_text(
        json.dumps(binding, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    (out_dir / "quote_hygiene.json").write_text(
        json.dumps(validation["quote_hygiene"], ensure_ascii=False, indent=1),
        encoding="utf-8",
    )
    (out_dir / "validation.json").write_text(
        json.dumps(
            {key: value for key, value in validation.items() if key != "article"},
            ensure_ascii=False,
            indent=1,
        ),
        encoding="utf-8",
    )

    citations: dict[str, dict[str, Any]] = {}
    for paragraph in binding.get("paragraphs", []):
        for fact in paragraph.get("facts", []):
            for match in fact.get("matches", []):
                key = f"{match.get('kind')}:{match.get('id')}"
                row = citations.setdefault(
                    key,
                    {
                        "kind": match.get("kind"),
                        "id": match.get("id"),
                        "timecode": match.get("timecode"),
                        "claim_ids": match.get("claim_ids", []),
                        "evidence_ids": match.get("evidence_ids", []),
                        "span_refs": [],
                    },
                )
                row["span_refs"].append(
                    {
                        "paragraph_index": paragraph.get("index"),
                        "fact": fact.get("value"),
                    }
                )
        for quote in paragraph.get("quotes", []):
            for match in quote.get("matches", []):
                key = f"{match.get('kind')}:{match.get('id')}"
                row = citations.setdefault(
                    key,
                    {
                        "kind": match.get("kind"),
                        "id": match.get("id"),
                        "timecode": match.get("timecode"),
                        "claim_ids": match.get("claim_ids", []),
                        "evidence_ids": match.get("evidence_ids", []),
                        "span_refs": [],
                    },
                )
                row["span_refs"].append(
                    {
                        "paragraph_index": paragraph.get("index"),
                        "quote": quote.get("value"),
                    }
                )
    citations_doc = {
        "schema_version": "citations-v1",
        "status": validation["status"],
        "granularity": "fact/quote/block; paragraph->claim is approximate",
        "citations": list(citations.values()),
    }
    (out_dir / "citations.json").write_text(
        json.dumps(citations_doc, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    audit = {
        "schema_version": "writing-audit-v1",
        "status": validation["status"],
        "request_hash": request.get("request_hash", ""),
        "skill": {
            "skill_id": getattr(skill, "skill_id", ""),
            "version": getattr(skill, "version", ""),
            "content_hash": getattr(skill, "content_hash", ""),
            "hash_ok": getattr(skill, "hash_ok", None),
        },
        "context": {
            "profile": context.get("profile", ""),
            "context_hash": context.get("context_hash", ""),
            "coverage": context.get("coverage", {}),
        },
        "binding_status": binding.get("status"),
        "binding_counts": binding.get("counts"),
        "validation": {
            "status": validation["status"],
            "failures": validation["failures"],
            "structure": validation["structure"],
            "reader_hygiene": validation["reader_hygiene"],
            "quote_hygiene": validation["quote_hygiene"],
        },
        "citations": "citations.json",
        "visual_plan": visual_plan or {},
        "media_assets": media_assets or [],
        "known_risks": list(validation["failures"]),
    }
    (out_dir / "audit.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    return {
        "reader": str(out_dir / "reader.md"),
        "article": str(out_dir / "article.md"),
        "binding": str(out_dir / "binding.json"),
        "citations": str(out_dir / "citations.json"),
        "audit": str(out_dir / "audit.json"),
        "validation": str(out_dir / "validation.json"),
    }
