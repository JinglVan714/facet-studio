"""Deterministic grounding adapter for the ``merged_frames`` comprehension view.

The Writer does not see claim/evidence IDs in this mode.  Its grounded spans
carry a ``grounding_ref`` instead:

- ``{"passage_id": "...", "quote": "..."}`` for text, optionally with
  ``t_start_ms``/``t_end_ms``;
- ``{"frame_id": "...", "caption": "..."}`` for a real frame.

This adapter maps the ref to the full pack's evidence/claim IDs, timecodes and
frame IDs.  It never invents facts and never fuzzy-matches: exact/substring
containment only.  Unresolved spans are reported as unbound/ambiguous/error;
nothing is silently accepted.  See docs/substrate-view-split.md §5.2.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Iterator

SCHEMA = "merged-frames-bindings-v1"


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _iter_spans(
    output: dict[str, Any],
) -> Iterator[tuple[str, dict[str, Any], dict[str, Any], dict[str, Any]]]:
    for section_index, section in enumerate(output.get("sections", [])):
        for paragraph_index, paragraph in enumerate(section.get("paragraphs", [])):
            for span_index, span in enumerate(paragraph.get("spans", [])):
                yield (
                    f"s{section_index}/p{paragraph_index}/sp{span_index}",
                    section,
                    paragraph,
                    span,
                )


def _evidence_time(evidence: dict[str, Any]) -> dict[str, int] | None:
    if "t_start_ms" not in evidence or "t_end_ms" not in evidence:
        return None
    return {
        "t_start_ms": int(evidence["t_start_ms"]),
        "t_end_ms": int(evidence["t_end_ms"]),
    }


def _binding(
    *,
    span_ref: str,
    status: str,
    evidence_ids: list[str],
    claim_ids: list[str],
    timecode: dict[str, int] | None,
    notes: list[str],
    candidates: list[dict[str, Any]] | None = None,
    frame: dict[str, Any] | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "span_ref": span_ref,
        "status": status,
        "evidence_ids": evidence_ids,
        "claim_ids": claim_ids,
        "timecode": timecode,
        "notes": notes,
    }
    if candidates is not None:
        result["candidates"] = candidates
    if frame is not None:
        result["frame"] = frame
    return result


def bind_span(
    span: dict[str, Any],
    *,
    span_ref: str,
    pack: dict[str, Any],
    passages_by_id: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    ref = span.get("grounding_ref")
    if not isinstance(ref, dict):
        return _binding(
            span_ref=span_ref,
            status="error",
            evidence_ids=[],
            claim_ids=[],
            timecode=None,
            notes=["missing_grounding_ref"],
        )

    frame_id = ref.get("frame_id")
    if isinstance(frame_id, str) and frame_id:
        frames_by_id = {f["frame_id"]: f for f in pack.get("frames", [])}
        frame = frames_by_id.get(frame_id)
        if frame is None:
            return _binding(
                span_ref=span_ref,
                status="error",
                evidence_ids=[],
                claim_ids=[],
                timecode=None,
                notes=[f"unknown_frame:{frame_id}"],
            )
        caption = (ref.get("caption") or "").strip()
        frame_caption = (frame.get("caption") or "").strip()
        caption_matches = bool(caption) and caption in frame_caption
        return _binding(
            span_ref=span_ref,
            status="frame_bound",
            evidence_ids=[],
            claim_ids=[],
            timecode=None,
            notes=["frame_caption_mismatch"] if caption and not caption_matches else [],
            frame={
                "frame_id": frame_id,
                "t_ms": frame.get("t_ms"),
                "caption_matches": caption_matches,
            },
        )

    quote = ref.get("quote")
    passage_id = ref.get("passage_id")
    if not isinstance(quote, str) or not quote.strip():
        return _binding(
            span_ref=span_ref,
            status="error",
            evidence_ids=[],
            claim_ids=[],
            timecode=None,
            notes=["missing_quote"],
        )
    passage = None
    if passage_id is not None:
        passage = passages_by_id.get(passage_id)
        if passage is None:
            return _binding(
                span_ref=span_ref,
                status="error",
                evidence_ids=[],
                claim_ids=[],
                timecode=None,
                notes=[f"unknown_passage:{passage_id}"],
            )
        if quote not in passage.get("text", ""):
            return _binding(
                span_ref=span_ref,
                status="error",
                evidence_ids=[],
                claim_ids=[],
                timecode=None,
                notes=["quote_not_in_passage"],
            )

    passage_sentence_ids = set(passage.get("sentence_ids", [])) if passage else None
    evidence = pack.get("evidence", [])
    containing: list[dict[str, Any]] = []
    for item in evidence:
        candidate_quote = item.get("quote", "")
        if quote not in candidate_quote:
            continue
        if passage_sentence_ids is not None and not (
            passage_sentence_ids & set(item.get("sentence_ids", []))
        ):
            continue
        containing.append(item)

    if containing:
        if len(containing) == 1:
            item = containing[0]
            return _binding(
                span_ref=span_ref,
                status="bound",
                evidence_ids=[item["evidence_id"]],
                claim_ids=list(item.get("claim_ids", [])),
                timecode=_evidence_time(item),
                notes=[],
            )
        candidates = [
            {
                "evidence_id": item["evidence_id"],
                "claim_ids": list(item.get("claim_ids", [])),
                "quote": item.get("quote", ""),
            }
            for item in containing
        ]
        return _binding(
            span_ref=span_ref,
            status="ambiguous",
            evidence_ids=[item["evidence_id"] for item in containing],
            claim_ids=sorted(
                {
                    claim_id
                    for item in containing
                    for claim_id in item.get("claim_ids", [])
                }
            ),
            timecode=None,
            notes=["multiple_evidence_contain_quote"],
            candidates=candidates,
        )

    # The Writer quote may cover several evidence quotes (a longer span).
    covered = [
        item
        for item in evidence
        if item.get("quote", "")
        and item.get("quote", "") in quote
        and (
            passage_sentence_ids is None
            or passage_sentence_ids & set(item.get("sentence_ids", []))
        )
    ]
    if covered:
        return _binding(
            span_ref=span_ref,
            status="partial",
            evidence_ids=[item["evidence_id"] for item in covered],
            claim_ids=sorted(
                {
                    claim_id
                    for item in covered
                    for claim_id in item.get("claim_ids", [])
                }
            ),
            timecode=None,
            notes=["multi_evidence_quote"],
            candidates=[
                {
                    "evidence_id": item["evidence_id"],
                    "claim_ids": list(item.get("claim_ids", [])),
                    "quote": item.get("quote", ""),
                }
                for item in covered
            ],
        )

    return _binding(
        span_ref=span_ref,
        status="unbound",
        evidence_ids=[],
        claim_ids=[],
        timecode=None,
        notes=["quote_not_in_evidence"],
    )


def bind_output(
    output: dict[str, Any],
    *,
    pack: dict[str, Any],
    passages: list[dict[str, Any]],
) -> dict[str, Any]:
    passages_by_id = {p["passage_id"]: p for p in passages}
    bindings: list[dict[str, Any]] = []
    counts = {
        "grounded": 0,
        "bound": 0,
        "partial": 0,
        "ambiguous": 0,
        "unbound": 0,
        "frame_bound": 0,
        "error": 0,
        "editorial": 0,
    }
    for span_ref, _section, _paragraph, span in _iter_spans(output):
        role = span.get("role")
        if role == "editorial":
            counts["editorial"] += 1
            continue
        if role != "grounded":
            continue
        counts["grounded"] += 1
        binding = bind_span(
            span,
            span_ref=span_ref,
            pack=pack,
            passages_by_id=passages_by_id,
        )
        counts[binding["status"]] += 1
        bindings.append(binding)
    if counts["grounded"] == 0:
        status = "failed"
    elif counts["error"] == counts["grounded"]:
        status = "failed"
    elif (
        counts["error"]
        + counts["partial"]
        + counts["ambiguous"]
        + counts["unbound"]
    ):
        status = "partial"
    else:
        status = "complete"
    return {
        "schema": SCHEMA,
        "status": status,
        "counts": counts,
        "bindings": bindings,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Bind merged_frames grounded spans back to the full pack."
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--pack", type=Path, required=True)
    parser.add_argument("--passages", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)

    output = _read_json(args.output)
    pack = _read_json(args.pack)
    passages = _read_json(args.passages).get("passages", [])
    report = bind_output(output, pack=pack, passages=passages)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    print(
        json.dumps(
            {"status": report["status"], "counts": report["counts"]},
            ensure_ascii=False,
            indent=1,
        )
    )
    return (
        0
        if report["status"] == "complete"
        else (5 if report["status"] == "partial" else 6)
    )


if __name__ == "__main__":
    sys.exit(main())
