"""Deterministic post-hoc binding of a prose article to the full pack.

The Writer no longer emits claim/evidence IDs or span-level quotes.  This
module walks the article instead:

- paragraphs are matched to pack sentences/claims/evidence/frames by character
  n-gram coverage (audit only; a paraphrase scores lower than a quote);
- numbers and Latin tokens are exact fact anchors: a token missing from the
  pack is reported as ``unsupported_fact``;
- quoted text is checked as an exact substring; long unbound quotes are
  reported separately from short term quotes.

No model call.  The full pack stays the only fact source.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

SCHEMA = "article-binding-v1"

NUMBER = re.compile(r"(?<![\w.])(\d+(?:\.\d+)*(?:%|:[0-9]+)?)(?![\w.])")
LATIN = re.compile(
    r"(?<![A-Za-z0-9_])([A-Za-z][A-Za-z0-9_.:-]*[A-Za-z0-9]|[A-Za-z])"
    r"(?![A-Za-z0-9_])"
)
SLUG = re.compile(r"(?<![\w.])(\d+[A-Za-z]+)(?![\w.])")
QUOTE_PATTERNS = (
    re.compile(r"“([^”]{4,120})”"),
    re.compile(r"「([^」]{4,120})」"),
    re.compile(r"`([^`]{2,120})`"),
)
NORMALIZE = re.compile(r"[^\w一-鿿]+")
QUOTE_NORMALIZE = re.compile(
    r"[\s，。！？、；：“”‘’（）()\[\]【】…—\-~·.,!?;:'\"<>《》]+"
)
QUOTE_FILLERS = re.compile(r"嗯|呃|哦|唉|哎呀")
BOUND_THRESHOLD = 0.45
PARTIAL_THRESHOLD = 0.18
MIN_PARAGRAPH_CHARS = 12
LONG_QUOTE_CHARS = 8


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _normalize(text: str) -> str:
    return NORMALIZE.sub("", text or "").lower()


def _ngrams(text: str, size: int = 3) -> set[str]:
    value = _normalize(text)
    if len(value) < size:
        return {value} if value else set()
    return {value[i : i + size] for i in range(len(value) - size + 1)}


def _coverage(article_grams: set[str], source_grams: set[str]) -> float:
    if not article_grams:
        return 0.0
    return len(article_grams & source_grams) / len(article_grams)


def extract_paragraphs(markdown: str) -> list[dict[str, Any]]:
    """Body paragraphs only: skip headings, image lines and italic captions."""
    paragraphs: list[dict[str, Any]] = []
    buffer: list[str] = []

    def flush() -> None:
        if not buffer:
            return
        text = "".join(buffer).strip()
        if text:
            paragraphs.append({"index": len(paragraphs), "text": text})
        buffer.clear()

    for line in markdown.splitlines():
        stripped = line.strip()
        if not stripped:
            flush()
            continue
        if stripped.startswith("#") or stripped.startswith("!["):
            flush()
            continue
        if (
            stripped.startswith("*")
            and stripped.endswith("*")
            and not stripped.startswith("**")
        ):
            flush()
            continue
        buffer.append(stripped)
    flush()
    return paragraphs


def _sources(
    pack: dict[str, Any],
    sentences: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    claims_by_sentence: dict[str, list[str]] = {}
    evidence_by_sentence: dict[str, list[str]] = {}
    for evidence in pack.get("evidence", []):
        evidence_id = evidence.get("evidence_id", "")
        for sentence_id in evidence.get("sentence_ids", []):
            evidence_by_sentence.setdefault(sentence_id, []).append(evidence_id)
            for claim_id in evidence.get("claim_ids", []):
                claims_by_sentence.setdefault(sentence_id, []).append(claim_id)

    sentence_rows: dict[str, dict[str, Any]] = {}
    for sentence in pack.get("sentences", []):
        sentence_rows[sentence.get("sentence_id", "")] = sentence
    for sentence in sentences or []:
        sentence_rows.setdefault(sentence.get("sentence_id", ""), sentence)

    sources: list[dict[str, Any]] = []
    for sentence in sentence_rows.values():
        sentence_id = sentence.get("sentence_id", "")
        sources.append(
            {
                "kind": "sentence",
                "id": sentence_id,
                "text": sentence.get("text", ""),
                "claim_ids": sorted(set(claims_by_sentence.get(sentence_id, []))),
                "evidence_ids": sorted(
                    set(evidence_by_sentence.get(sentence_id, []))
                ),
                "timecode": {
                    "t_start_ms": sentence.get("t_start_ms"),
                    "t_end_ms": sentence.get("t_end_ms"),
                },
            }
        )
    for claim in pack.get("claims", []):
        sources.append(
            {
                "kind": "claim",
                "id": claim.get("claim_id", ""),
                "text": claim.get("text", ""),
                "claim_ids": [claim.get("claim_id", "")],
                "evidence_ids": list(claim.get("evidence_ids", [])),
                "timecode": None,
            }
        )
    for evidence in pack.get("evidence", []):
        sources.append(
            {
                "kind": "evidence",
                "id": evidence.get("evidence_id", ""),
                "text": evidence.get("quote", ""),
                "claim_ids": list(evidence.get("claim_ids", [])),
                "evidence_ids": [evidence.get("evidence_id", "")],
                "timecode": {
                    "t_start_ms": evidence.get("t_start_ms"),
                    "t_end_ms": evidence.get("t_end_ms"),
                },
            }
        )
    for frame in pack.get("frames", []):
        caption = (frame.get("caption") or "").strip()
        if not caption:
            continue
        sources.append(
            {
                "kind": "frame",
                "id": frame.get("frame_id", ""),
                "text": caption,
                "claim_ids": [],
                "evidence_ids": [],
                "timecode": {"t_ms": frame.get("t_ms")},
            }
        )
    for source in sources:
        source["ngrams"] = _ngrams(source["text"])
    return sources


def _block_sources(
    pack: dict[str, Any],
    rendered_text: str | None,
    source_map: dict[str, Any] | None,
    sentences: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Edited-transcript blocks as broad paragraph-matching sources."""
    if not rendered_text or not source_map:
        return []
    evidence_by_sentence: dict[str, list[str]] = {}
    for evidence in pack.get("evidence", []):
        evidence_id = evidence.get("evidence_id", "")
        for sentence_id in evidence.get("sentence_ids", []):
            evidence_by_sentence.setdefault(sentence_id, []).append(evidence_id)
    sentences_by_id = {
        s.get("sentence_id", ""): s for s in pack.get("sentences", [])
    }
    for sentence in sentences or []:
        sentences_by_id.setdefault(sentence.get("sentence_id", ""), sentence)
    blocks: list[dict[str, Any]] = []
    for block in source_map.get("blocks", []):
        start = block.get("text_start")
        end = block.get("text_end")
        if not isinstance(start, int) or not isinstance(end, int):
            continue
        text = rendered_text[start:end]
        sentence_ids = list(block.get("sentence_ids", []))
        evidence_ids = sorted(
            {
                evidence_id
                for sentence_id in sentence_ids
                for evidence_id in evidence_by_sentence.get(sentence_id, [])
            }
        )
        times = [
            sentences_by_id[sentence_id]
            for sentence_id in sentence_ids
            if sentence_id in sentences_by_id
        ]
        timecode = None
        if times:
            starts = [t.get("t_start_ms") for t in times if t.get("t_start_ms") is not None]
            ends = [t.get("t_end_ms") for t in times if t.get("t_end_ms") is not None]
            timecode = {
                "t_start_ms": min(starts) if starts else None,
                "t_end_ms": max(ends) if ends else None,
            }
        blocks.append(
            {
                "kind": "block",
                "id": f"block_{block.get('block_index')}",
                "text": text,
                "claim_ids": list(block.get("claim_ids", [])),
                "evidence_ids": evidence_ids,
                "timecode": timecode,
                "segment_id": block.get("segment_id"),
                "ngrams": _ngrams(text),
            }
        )
    return blocks


def _fact_tokens(text: str) -> list[dict[str, str]]:
    tokens: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for match in NUMBER.finditer(text):
        value = match.group(1)
        key = ("number", value)
        if key in seen:
            continue
        seen.add(key)
        tokens.append({"kind": "number", "value": value})
    for match in LATIN.finditer(text):
        value = match.group(1).rstrip(".:-")
        if len(value) < 2:
            continue
        key = ("latin", value.lower())
        if key in seen:
            continue
        seen.add(key)
        tokens.append({"kind": "latin", "value": value})
    for match in SLUG.finditer(text):
        value = match.group(1)
        key = ("latin", value.lower())
        if key in seen:
            continue
        seen.add(key)
        tokens.append({"kind": "latin", "value": value})
    return tokens


UNIT_GROUPS = {"gb": "g", "mb": "m", "kb": "k"}


def _fact_pattern(
    token: dict[str, str], *, relaxed: bool = False
) -> re.Pattern[str]:
    value = re.escape(token["value"])
    if token["kind"] == "number":
        return re.compile(r"(?<![\d.])" + value + r"(?![\d.])")
    if relaxed:
        return re.compile(
            r"(?<![A-Za-z0-9_])" + value,
            re.IGNORECASE,
        )
    return re.compile(
        r"(?<![A-Za-z0-9_])" + value + r"(?![A-Za-z0-9_])",
        re.IGNORECASE,
    )


def _unit_pattern(token: dict[str, str]) -> re.Pattern[str] | None:
    letter = UNIT_GROUPS.get(token["value"].lower())
    if not letter:
        return None
    return re.compile(
        r"(?<![A-Za-z])" + re.escape(letter) + r"B?(?![A-Za-z])",
        re.IGNORECASE,
    )


def _text_match(token: dict[str, str], text: str | None) -> tuple[bool, bool]:
    """Return (found, format_variant) for a token in one text."""
    if not text:
        return False, False
    if _fact_pattern(token).search(text):
        return True, False
    if token["kind"] == "latin" and _fact_pattern(
        token, relaxed=True
    ).search(text):
        return True, True
    unit = _unit_pattern(token)
    if unit is not None and unit.search(text):
        return True, True
    return False, False


def _fact_matches(
    token: dict[str, str],
    sources: list[dict[str, Any]],
    *,
    max_matches: int,
) -> list[dict[str, Any]]:
    strict = _fact_pattern(token)
    relaxed = (
        _fact_pattern(token, relaxed=True)
        if token["kind"] == "latin"
        else None
    )
    unit = _unit_pattern(token)
    matches: list[dict[str, Any]] = []
    for source in sources:
        text = source["text"]
        if strict.search(text):
            match_type = "exact"
        elif relaxed is not None and relaxed.search(text):
            match_type = "variant"
        elif unit is not None and unit.search(text):
            match_type = "variant"
        else:
            continue
        matches.append(
            {
                "kind": source["kind"],
                "id": source["id"],
                "match_type": match_type,
                "claim_ids": source["claim_ids"],
                "evidence_ids": source["evidence_ids"],
                "timecode": source["timecode"],
            }
        )
        if len(matches) >= max_matches:
            break
    return matches


def _quote_values(text: str) -> list[str]:
    values: list[str] = []
    for pattern in QUOTE_PATTERNS:
        for match in pattern.finditer(text):
            value = match.group(1).strip()
            if value and value not in values:
                values.append(value)
    return values


def _normalize_quote(text: str) -> str:
    """Normalize punctuation and discourse fillers, not content words."""
    value = QUOTE_NORMALIZE.sub("", text or "")
    return QUOTE_FILLERS.sub("", value)


def _quote_matches(quote: str, sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    for source in sources:
        if quote in source["text"]:
            matches.append(
                {
                    "kind": source["kind"],
                    "id": source["id"],
                    "match_type": "exact",
                    "claim_ids": source["claim_ids"],
                    "evidence_ids": source["evidence_ids"],
                    "timecode": source["timecode"],
                }
            )
            if len(matches) >= 3:
                return matches
    normalized_quote = _normalize_quote(quote)
    if not normalized_quote:
        return matches
    for source in sources:
        if normalized_quote in _normalize_quote(source["text"]):
            matches.append(
                {
                    "kind": source["kind"],
                    "id": source["id"],
                    "match_type": "normalized",
                    "claim_ids": source["claim_ids"],
                    "evidence_ids": source["evidence_ids"],
                    "timecode": source["timecode"],
                }
            )
            if len(matches) >= 3:
                break
    return matches


def _paragraph_matches(
    text: str,
    sources: list[dict[str, Any]],
    *,
    max_matches: int = 3,
) -> list[dict[str, Any]]:
    if len(_normalize(text)) < MIN_PARAGRAPH_CHARS:
        return []
    grams = _ngrams(text)
    scored: list[tuple[float, int, dict[str, Any]]] = []
    for index, source in enumerate(sources):
        score = _coverage(grams, source["ngrams"])
        if score <= 0:
            continue
        scored.append((score, index, source))
    scored.sort(key=lambda item: (-item[0], item[1]))
    matches: list[dict[str, Any]] = []
    for score, _index, source in scored[:max_matches]:
        matches.append(
            {
                "kind": source["kind"],
                "id": source["id"],
                "score": round(score, 4),
                "claim_ids": source["claim_ids"],
                "evidence_ids": source["evidence_ids"],
                "timecode": source["timecode"],
            }
        )
    return matches


def bind_article(
    article: str,
    pack: dict[str, Any],
    sentences: list[dict[str, Any]] | None = None,
    *,
    rendered_text: str | None = None,
    source_map: dict[str, Any] | None = None,
    input_text: str | None = None,
    max_matches: int = 5,
) -> dict[str, Any]:
    """Bind one article to the pack; return a deterministic report."""
    paragraphs = extract_paragraphs(article)
    sources = _sources(pack, sentences)
    block_sources = _block_sources(pack, rendered_text, source_map, sentences)
    paragraph_sources = sources + block_sources
    input_source = (
        {
            "kind": "input",
            "id": "writer_input",
            "text": input_text,
            "claim_ids": [],
            "evidence_ids": [],
            "timecode": None,
        }
        if input_text is not None
        else None
    )
    paragraph_reports: list[dict[str, Any]] = []
    unsupported: list[dict[str, Any]] = []
    outside_input_facts: list[dict[str, Any]] = []
    outside_input_quotes: list[dict[str, Any]] = []
    quote_unbound: list[dict[str, Any]] = []
    quote_unbound_long: list[dict[str, Any]] = []
    facts_total = 0
    facts_bound = 0
    facts_in_input = 0
    facts_outside_input = 0
    facts_format_variant = 0
    quotes_total = 0
    quotes_bound = 0
    quotes_in_input = 0
    quotes_outside_input = 0

    for paragraph in paragraphs:
        text = paragraph["text"]
        matches = _paragraph_matches(text, paragraph_sources)
        best = matches[0]["score"] if matches else 0.0
        if best >= BOUND_THRESHOLD:
            status = "bound"
        elif best >= PARTIAL_THRESHOLD:
            status = "partial"
        else:
            status = "unbound"

        facts: list[dict[str, Any]] = []
        for token in _fact_tokens(text):
            facts_total += 1
            found = _fact_matches(token, sources, max_matches=max_matches)
            fact_status = "bound" if found else "unsupported"
            fact_variant = bool(found) and all(
                match["match_type"] == "variant" for match in found
            )
            input_found = False
            input_variant = False
            input_status = "not_checked"
            if input_source is not None:
                input_found, input_variant = _text_match(
                    token, input_source["text"]
                )
                if input_found:
                    input_status = "in_input"
                    facts_in_input += 1
                elif found:
                    input_status = (
                        "outside_input_variant"
                        if fact_variant
                        else "outside_input"
                    )
                    if input_status == "outside_input":
                        facts_outside_input += 1
                        outside_input_facts.append(
                            {
                                "paragraph_index": paragraph["index"],
                                "kind": token["kind"],
                                "value": token["value"],
                                "context": text,
                            }
                        )
                else:
                    input_status = "unsupported"
            if input_variant or fact_variant:
                facts_format_variant += 1
            if found:
                facts_bound += 1
            else:
                unsupported.append(
                    {
                        "paragraph_index": paragraph["index"],
                        "kind": token["kind"],
                        "value": token["value"],
                        "context": text,
                    }
                )
            facts.append(
                {
                    "kind": token["kind"],
                    "value": token["value"],
                    "status": fact_status,
                    "input_status": input_status,
                    "format_variant": bool(input_variant or fact_variant),
                    "matches": found,
                }
            )

        quotes: list[dict[str, Any]] = []
        for value in _quote_values(text):
            quotes_total += 1
            found = _quote_matches(value, sources)
            input_found = (
                _quote_matches(value, [input_source])
                if input_source is not None
                else []
            )
            input_status = "not_checked"
            if input_source is not None:
                if input_found:
                    input_status = "in_input"
                    quotes_in_input += 1
                elif found:
                    input_status = "outside_input"
                    quotes_outside_input += 1
                    outside_input_quotes.append(
                        {
                            "paragraph_index": paragraph["index"],
                            "value": value,
                        }
                    )
                else:
                    input_status = "unsupported"
            if found:
                quotes_bound += 1
                quote_status = "bound"
            else:
                quote_status = "unbound"
                record = {
                    "paragraph_index": paragraph["index"],
                    "value": value,
                    "long": len(_normalize(value)) >= LONG_QUOTE_CHARS,
                }
                quote_unbound.append(record)
                if record["long"]:
                    quote_unbound_long.append(record)
            quotes.append(
                {
                    "value": value,
                    "status": quote_status,
                    "input_status": input_status,
                    "matches": found,
                    "input_matches": input_found,
                }
            )

        paragraph_reports.append(
            {
                "index": paragraph["index"],
                "text": text,
                "status": status,
                "best_score": round(best, 4),
                "matches": matches,
                "facts": facts,
                "quotes": quotes,
            }
        )

    paragraph_counts = {
        "total": len(paragraph_reports),
        "bound": sum(1 for p in paragraph_reports if p["status"] == "bound"),
        "partial": sum(
            1 for p in paragraph_reports if p["status"] == "partial"
        ),
        "unbound": sum(1 for p in paragraph_reports if p["status"] == "unbound"),
    }
    counts = {
        "paragraphs": paragraph_counts,
        "facts": {
            "total": facts_total,
            "bound": facts_bound,
            "unsupported": len(unsupported),
            "in_input": facts_in_input,
            "outside_input": facts_outside_input,
            "format_variant": facts_format_variant,
            "input_checked": input_source is not None,
            "coverage": (
                round(facts_bound / facts_total, 4) if facts_total else 1.0
            ),
        },
        "quotes": {
            "total": quotes_total,
            "bound": quotes_bound,
            "unbound": len(quote_unbound),
            "unbound_long": len(quote_unbound_long),
            "in_input": quotes_in_input,
            "outside_input": quotes_outside_input,
            "input_checked": input_source is not None,
            "coverage": (
                round(quotes_bound / quotes_total, 4) if quotes_total else 1.0
            ),
        },
        "sources": {
            "sentences": sum(
                1 for source in sources if source["kind"] == "sentence"
            ),
            "claims": sum(1 for source in sources if source["kind"] == "claim"),
            "evidence": sum(
                1 for source in sources if source["kind"] == "evidence"
            ),
            "frames": sum(1 for source in sources if source["kind"] == "frame"),
            "blocks": len(block_sources),
        },
    }
    status = (
        "complete"
        if not unsupported
        and not quote_unbound_long
        and not outside_input_facts
        and not outside_input_quotes
        else "partial"
    )
    return {
        "schema": SCHEMA,
        "status": status,
        "pack_id": pack.get("pack_id"),
        "input_scope_checked": input_source is not None,
        "counts": counts,
        "paragraphs": paragraph_reports,
        "unsupported_facts": unsupported,
        "outside_input_facts": outside_input_facts,
        "outside_input_quotes": outside_input_quotes,
        "quote_unbound": quote_unbound,
        "notes": [
            "paragraph binding is character n-gram coverage over sentences/claims/evidence/blocks, not span-level semantics",
            "fact anchors are Arabic numbers and Latin tokens; Chinese proper nouns are covered only by paragraph matching",
            "quote checks are exact first, then normalized for punctuation/discourse fillers; a paraphrase is reported as unbound",
            "input scope checks facts/quotes against the writer input when provided; unit/spacing variants are format_variant, not outside_input",
            "no model call; pack plus optional full transcript remains the only fact source",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Bind a prose article to the full pack deterministically: "
            "paragraph matches, fact anchors, quoted substrings."
        )
    )
    parser.add_argument("--article", type=Path, required=True)
    parser.add_argument("--pack", type=Path, required=True)
    parser.add_argument(
        "--sentences",
        type=Path,
        help="可选：完整转写句表；补齐 pack 只保留 selection 时缺失的句子",
    )
    parser.add_argument(
        "--rendered-text",
        type=Path,
        help="可选：edited transcript 文本；与 --source-map 一起提供 block 级匹配",
    )
    parser.add_argument("--source-map", type=Path)
    parser.add_argument(
        "--input-text",
        type=Path,
        help="可选：Writer 实际输入；提供后增加 in_input/outside_input 检查",
    )
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--max-matches", type=int, default=5)
    args = parser.parse_args(argv)

    if (args.rendered_text is None) != (args.source_map is None):
        parser.error("--rendered-text 与 --source-map 必须同时提供")

    article = args.article.read_text(encoding="utf-8-sig")
    pack = _read_json(args.pack)
    sentences = (
        _read_json(args.sentences).get("sentences", [])
        if args.sentences
        else None
    )
    rendered_text = (
        args.rendered_text.read_text(encoding="utf-8-sig")
        if args.rendered_text
        else None
    )
    source_map = _read_json(args.source_map) if args.source_map else None
    input_text = (
        args.input_text.read_text(encoding="utf-8-sig")
        if args.input_text
        else None
    )
    report = bind_article(
        article,
        pack,
        sentences,
        rendered_text=rendered_text,
        source_map=source_map,
        input_text=input_text,
        max_matches=args.max_matches,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "status": report["status"],
                "out": str(args.out),
                "counts": report["counts"],
                "unsupported_fact_count": len(report["unsupported_facts"]),
                "outside_input_fact_count": len(
                    report["outside_input_facts"]
                ),
                "outside_input_quote_count": len(
                    report["outside_input_quotes"]
                ),
                "quote_unbound_long_count": report["counts"]["quotes"][
                    "unbound_long"
                ],
            },
            ensure_ascii=False,
            indent=1,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
