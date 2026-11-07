"""Deterministic comprehension views for the Writer.

Two modes from the same full pack:

- ``merged_frames``: merged passages + frame captions; no claims/IDs/context.
  For short/mid content where the transcript itself is small enough.
- ``lean_cw0``: claims + anchor-only context + bounded claims/scope + frames.
  For longer content where claim/context selection compresses the transcript.

The full pack stays the audit source; these views add no facts.  Mode selection
is an advisory budget decision (estimated tokens), recorded, never a hard
quality gate.  See docs/substrate-view-split.md.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from ..core.tokens import estimate_text_tokens
from .writer_view import _quote_span

SCHEMA = "comprehension-view-v1"
MODES = ("merged_frames", "lean_cw0")


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _compact(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _gaps(pack: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {"description": gap.get("description", "")}
        for gap in pack.get("gaps", [])
    ]


def _conflicts(pack: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {"description": conflict.get("description", "")}
        for conflict in pack.get("conflicts", [])
    ]


def build_merged_frames_view(
    pack: dict[str, Any], passages: list[dict[str, Any]]
) -> dict[str, Any]:
    """Merged transcript + frame captions; no claims/evidence/context JSON."""
    frames_by_id = {f["frame_id"]: f for f in pack.get("frames", [])}
    segment_frames: dict[str, list[dict[str, Any]]] = {}
    for segment in pack.get("segments", []):
        segment_frames[segment.get("segment_id", "")] = [
            {
                "frame_id": frame_id,
                "caption": frames_by_id[frame_id].get("caption", ""),
            }
            for frame_id in segment.get("frame_ids", [])
            if frame_id in frames_by_id
        ]

    groups: list[tuple[str, list[dict[str, Any]]]] = []
    for passage in passages:
        segment_id = passage.get("segment_id") or ""
        if not groups or groups[-1][0] != segment_id:
            groups.append((segment_id, []))
        groups[-1][1].append(passage)

    segments: list[dict[str, Any]] = []
    for segment_id, items in groups:
        segments.append(
            {
                "segment_id": segment_id,
                "passages": [
                    {
                        "passage_id": passage.get("passage_id", ""),
                        "t_start_ms": int(passage.get("t_start_ms", 0)),
                        "t_end_ms": int(passage.get("t_end_ms", 0)),
                        "text": passage.get("text", ""),
                    }
                    for passage in items
                ],
                "frames": segment_frames.get(segment_id, []),
            }
        )
    return {
        "schema": SCHEMA,
        "mode": "merged_frames",
        "segments": segments,
    }


def render_merged_frames_text(view: dict[str, Any]) -> str:
    """Render merged_frames in the same plain-text shape as the probe B+frames."""
    lines: list[str] = []
    for segment in view.get("segments", []):
        for passage in segment.get("passages", []):
            start = int(passage.get("t_start_ms", 0)) / 1000
            end = int(passage.get("t_end_ms", 0)) / 1000
            lines.append(
                f"[{passage.get('passage_id', '')} {start:.2f}-{end:.2f}s] "
                f"{passage.get('text', '')}"
            )
        captions = [
            frame
            for frame in segment.get("frames", [])
            if (frame.get("caption") or "").strip()
        ]
        if captions:
            rendered = " | ".join(
                f"[{frame.get('frame_id', '')}] "
                f"{(frame.get('caption') or '').strip().replace(chr(10), ' / ')}"
                for frame in captions
            )
            lines.append(f"frames: {rendered}")
        lines.append("")
    return "\n".join(lines).strip()


def build_lean_cw0_view(pack: dict[str, Any]) -> dict[str, Any]:
    """Claims + anchor-only context + frames; bounded claims keep status/scope."""
    claims_by_id = {c["claim_id"]: c for c in pack.get("claims", [])}
    evidence_by_id = {e["evidence_id"]: e for e in pack.get("evidence", [])}
    sentences_by_id = {s["sentence_id"]: s for s in pack.get("sentences", [])}
    frames_by_id = {f["frame_id"]: f for f in pack.get("frames", [])}

    segments: list[dict[str, Any]] = []
    for segment in pack.get("segments", []):
        claim_ids = segment.get("claim_ids", [])
        anchor_order: list[str] = []
        for claim_id in claim_ids:
            claim = claims_by_id.get(claim_id)
            if claim is None:
                continue
            for evidence_id in claim.get("evidence_ids", []):
                evidence = evidence_by_id.get(evidence_id)
                if evidence is None:
                    continue
                for sentence_id in evidence.get("sentence_ids", []):
                    if sentence_id not in anchor_order:
                        anchor_order.append(sentence_id)
        context = [
            sentences_by_id[sentence_id]["text"]
            for sentence_id in anchor_order
            if sentence_id in sentences_by_id
        ]
        joined_context = "".join(context)

        claims: list[dict[str, Any]] = []
        for claim_id in claim_ids:
            claim = claims_by_id.get(claim_id)
            if claim is None:
                continue
            evidence: list[dict[str, Any]] = []
            for evidence_id in claim.get("evidence_ids", []):
                item = evidence_by_id.get(evidence_id)
                if item is None:
                    continue
                quote = item.get("quote", "")
                span = _quote_span(joined_context, quote)
                entry: dict[str, Any] = {"evidence_id": item["evidence_id"]}
                if span is not None:
                    entry["span"] = span
                else:
                    entry["quote"] = quote
                evidence.append(entry)
            claims.append(
                {
                    "claim_id": claim["claim_id"],
                    "text": claim.get("text", ""),
                    "status": claim.get("status", ""),
                    "scope": claim.get("scope", ""),
                    "evidence": evidence,
                }
            )
        frames = [
            {
                "frame_id": frame_id,
                "caption": frames_by_id[frame_id].get("caption", ""),
            }
            for frame_id in segment.get("frame_ids", [])
            if frame_id in frames_by_id
        ]
        segments.append(
            {
                "label": segment.get("label", ""),
                "claims": claims,
                "context": context,
                "frames": frames,
            }
        )
    return {
        "schema": SCHEMA,
        "mode": "lean_cw0",
        "segments": segments,
        "gaps": _gaps(pack),
        "conflicts": _conflicts(pack),
    }


def render_lean_cw0_text(view: dict[str, Any]) -> str:
    return _compact(view)


def _candidate(
    view: dict[str, Any], rendered: str
) -> dict[str, Any]:
    return {
        "view": view,
        "rendered": rendered,
        "chars": len(rendered),
        "est_tokens": estimate_text_tokens(rendered),
    }


def build_comprehension_view(
    pack: dict[str, Any],
    passages: list[dict[str, Any]],
    *,
    mode: str = "auto",
    budget_tokens: int | None = None,
) -> dict[str, Any]:
    """Build both candidates, choose a mode, and return view + rendered + decision."""
    if mode not in ("auto", *MODES):
        raise ValueError(f"未知 mode: {mode}")
    merged_view = build_merged_frames_view(pack, passages)
    merged_rendered = render_merged_frames_text(merged_view)
    lean_view = build_lean_cw0_view(pack)
    lean_rendered = render_lean_cw0_text(lean_view)
    candidates = {
        "merged_frames": _candidate(merged_view, merged_rendered),
        "lean_cw0": _candidate(lean_view, lean_rendered),
    }

    if mode == "auto":
        if budget_tokens is None:
            chosen = min(candidates, key=lambda name: candidates[name]["est_tokens"])
            reason = "smaller_estimated_tokens"
        elif candidates["merged_frames"]["est_tokens"] <= budget_tokens:
            chosen = "merged_frames"
            reason = "merged_frames_within_budget"
        else:
            chosen = "lean_cw0"
            reason = "merged_frames_over_budget"
    else:
        chosen = mode
        reason = "explicit"

    chosen_candidate = candidates[chosen]
    over_budget = (
        budget_tokens is not None
        and chosen_candidate["est_tokens"] > budget_tokens
    )
    decision = {
        "mode": chosen,
        "reason": reason,
        "budget_tokens": budget_tokens,
        "over_budget": over_budget,
        "candidates": {
            name: {
                "chars": item["chars"],
                "est_tokens": item["est_tokens"],
            }
            for name, item in candidates.items()
        },
    }
    return {
        "schema": SCHEMA,
        "mode": chosen,
        "view": chosen_candidate["view"],
        "rendered": chosen_candidate["rendered"],
        "decision": decision,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build a deterministic comprehension view from a full pack."
    )
    parser.add_argument("--pack", type=Path, required=True)
    parser.add_argument("--passages", type=Path, required=True)
    parser.add_argument("--mode", choices=["auto", *MODES], default="auto")
    parser.add_argument("--budget-tokens", type=int)
    parser.add_argument("--out-view", type=Path, required=True)
    parser.add_argument("--out-rendered", type=Path, required=True)
    parser.add_argument("--out-manifest", type=Path, required=True)
    args = parser.parse_args(argv)

    pack = _read_json(args.pack)
    passages = _read_json(args.passages).get("passages", [])
    try:
        result = build_comprehension_view(
            pack,
            passages,
            mode=args.mode,
            budget_tokens=args.budget_tokens,
        )
    except ValueError as exc:
        print(f"invalid mode: {exc}", file=sys.stderr)
        return 4

    args.out_view.parent.mkdir(parents=True, exist_ok=True)
    args.out_rendered.parent.mkdir(parents=True, exist_ok=True)
    args.out_manifest.parent.mkdir(parents=True, exist_ok=True)
    args.out_view.write_text(
        json.dumps(result["view"], ensure_ascii=False, indent=1),
        encoding="utf-8",
    )
    args.out_rendered.write_text(result["rendered"], encoding="utf-8")
    args.out_manifest.write_text(
        json.dumps(result["decision"], ensure_ascii=False, indent=1),
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "mode": result["mode"],
                "decision": result["decision"],
                "out_view": str(args.out_view),
                "out_rendered": str(args.out_rendered),
            },
            ensure_ascii=False,
            indent=1,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
