"""Lean writer-facing views of the full EvidencePack.

A = single lean view; C = index + parts; D = full pack stays audit-only.
The full pack is never hard-truncated; these views are deterministic
projections that keep every claim/evidence/frame ID and every quote
(quote text or a span into the segment context).

See docs/substrate-view-contract.md for the contract.
"""

from __future__ import annotations

import json
from typing import Any

CAPTION_CHARS = 80


def _view_size(view: dict[str, Any]) -> int:
    return len(json.dumps(view, ensure_ascii=False, separators=(",", ":")))


def _quote_span(context: str, quote: str) -> list[int] | None:
    """Return [start, end] only when quote occurs exactly once in context."""
    if not quote:
        return None
    start = context.find(quote)
    if start < 0:
        return None
    if context.find(quote, start + 1) != -1:
        return None
    return [start, start + len(quote)]


def resolve_quote(context: list[str], evidence: dict[str, Any]) -> str:
    """Resolve an evidence entry to its exact quote (span or fallback)."""
    if "quote" in evidence:
        return evidence["quote"]
    start, end = evidence["span"]
    return "".join(context)[start:end]


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


def _lean_segments(pack: dict[str, Any]) -> list[dict[str, Any]]:
    claims_by_id = {c["claim_id"]: c for c in pack.get("claims", [])}
    evidence_by_id = {e["evidence_id"]: e for e in pack.get("evidence", [])}
    sentences_by_id = {s["sentence_id"]: s for s in pack.get("sentences", [])}
    frames_by_id = {f["frame_id"]: f for f in pack.get("frames", [])}

    segments: list[dict[str, Any]] = []
    for segment in pack.get("segments", []):
        context = [
            sentences_by_id[sentence_id]["text"]
            for sentence_id in segment.get("sentence_ids", [])
            if sentence_id in sentences_by_id
        ]
        joined_context = "".join(context)

        claims: list[dict[str, Any]] = []
        for claim_id in segment.get("claim_ids", []):
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
                "caption": frames_by_id[frame_id].get("caption", "")[
                    :CAPTION_CHARS
                ],
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
    return segments


def _partition_segments(
    segments: list[dict[str, Any]],
    *,
    max_chars: int,
    gaps: list[dict[str, Any]],
    conflicts: list[dict[str, Any]],
) -> dict[str, Any]:
    """Split segments into parts under a char budget, never dropping content."""
    parts: list[dict[str, Any]] = []
    current: list[dict[str, Any]] = []
    oversize_parts: list[dict[str, Any]] = []

    def flush() -> None:
        nonlocal current
        if not current:
            return
        part = {
            "schema": "writer-part-v1",
            "part_id": f"part_{len(parts) + 1:02d}",
            "segments": current,
        }
        parts.append(part)
        current = []

    for segment in segments:
        if not current:
            current = [segment]
        else:
            candidate = current + [segment]
            if _view_size(
                {"segments": candidate, "gaps": gaps, "conflicts": conflicts}
            ) > max_chars:
                flush()
                current = [segment]
            else:
                current = candidate
        size = _view_size(
            {"segments": current, "gaps": gaps, "conflicts": conflicts}
        )
        if size > max_chars:
            oversize_parts.append(
                {
                    "part_id": f"part_{len(parts) + 1:02d}",
                    "segment_labels": [
                        item.get("label", "") for item in current
                    ],
                    "chars": size,
                }
            )
            flush()
    flush()

    return {
        "schema": "writer-view-parts-v1",
        "manifest": {
            "max_chars": max_chars,
            "parts": len(parts),
            "segments_total": len(segments),
            "claims_total": sum(len(segment.get("claims", [])) for segment in segments),
            "oversize_parts": oversize_parts,
            "note": "segments partitioned; no content dropped",
        },
        "parts": parts,
        "gaps": gaps,
        "conflicts": conflicts,
    }


def build_writer_view(
    pack: dict[str, Any], *, max_chars: int | None = None
) -> dict[str, Any]:
    """A: lean single view; when over budget, partition into parts (C-like)."""
    segments = _lean_segments(pack)
    gaps = _gaps(pack)
    conflicts = _conflicts(pack)
    view = {
        "schema": "writer-view-v1",
        "segments": segments,
        "gaps": gaps,
        "conflicts": conflicts,
    }
    if max_chars is not None and _view_size(view) > max_chars:
        return _partition_segments(
            segments,
            max_chars=max_chars,
            gaps=gaps,
            conflicts=conflicts,
        )
    return view


def build_writer_index(
    pack: dict[str, Any], part_map: dict[int, str] | None = None
) -> dict[str, Any]:
    """C first layer: segment/claim index, no quotes/context/frames."""
    claims_by_id = {c["claim_id"]: c for c in pack.get("claims", [])}
    segments: list[dict[str, Any]] = []
    for index, segment in enumerate(pack.get("segments", [])):
        claims = []
        for claim_id in segment.get("claim_ids", []):
            claim = claims_by_id.get(claim_id)
            if claim is None:
                continue
            claims.append(
                {
                    "claim_id": claim["claim_id"],
                    "text": claim.get("text", ""),
                    "status": claim.get("status", ""),
                    "scope": claim.get("scope", ""),
                }
            )
        segments.append(
            {
                "part_id": (
                    part_map.get(index)
                    if part_map is not None
                    else f"part_{index + 1:02d}"
                ),
                "label": segment.get("label", ""),
                "claims": claims,
            }
        )
    return {
        "schema": "writer-index-v1",
        "segments": segments,
        "gaps": _gaps(pack),
        "conflicts": _conflicts(pack),
    }


def _partition_for_bundle(
    segments: list[dict[str, Any]],
    *,
    max_chars_per_part: int | None,
) -> tuple[list[list[int]], list[dict[str, Any]]]:
    """Return groups of segment indices and oversize metadata."""
    if max_chars_per_part is None:
        return [[index] for index in range(len(segments))], []
    groups: list[list[int]] = []
    oversize: list[dict[str, Any]] = []
    current: list[int] = []
    for index, segment in enumerate(segments):
        if not current:
            current = [index]
        else:
            candidate = current + [index]
            size = _view_size(
                {
                    "segments": [segments[item] for item in candidate],
                }
            )
            if size > max_chars_per_part:
                groups.append(current)
                current = [index]
            else:
                current = candidate
        size = _view_size(
            {"segments": [segments[item] for item in current]}
        )
        if size > max_chars_per_part:
            oversize.append(
                {
                    "part_id": f"part_{len(groups) + 1:02d}",
                    "segment_labels": [
                        segments[item].get("label", "") for item in current
                    ],
                    "chars": size,
                }
            )
            groups.append(current)
            current = []
    if current:
        groups.append(current)
    return groups, oversize


def build_writer_bundle(
    pack: dict[str, Any], *, max_chars_per_part: int | None = None
) -> dict[str, Any]:
    """C: index + parts + manifest; parts default to one segment each."""
    segments = _lean_segments(pack)
    groups, oversize = _partition_for_bundle(
        segments, max_chars_per_part=max_chars_per_part
    )
    parts: list[dict[str, Any]] = []
    part_map: dict[int, str] = {}
    part_rows: list[dict[str, Any]] = []
    for group_index, group in enumerate(groups, start=1):
        part_id = f"part_{group_index:02d}"
        part = {
            "schema": "writer-part-v1",
            "part_id": part_id,
            "segments": [segments[index] for index in group],
        }
        parts.append(part)
        for index in group:
            part_map[index] = part_id
        part_rows.append(
            {
                "part_id": part_id,
                "file": f"writer_parts/{part_id}.json",
                "segment_labels": [
                    segments[index].get("label", "") for index in group
                ],
                "claim_count": sum(
                    len(segments[index].get("claims", [])) for index in group
                ),
                "chars": _view_size(part),
                "oversize": (
                    max_chars_per_part is not None
                    and _view_size(part) > max_chars_per_part
                ),
            }
        )

    index = build_writer_index(pack, part_map)
    part_chars = {row["part_id"]: row["chars"] for row in part_rows}
    for row in oversize:
        if row["part_id"] in part_chars:
            row["chars"] = part_chars[row["part_id"]]
    manifest = {
        "schema": "writer-bundle-v1",
        "index": "writer_index.json",
        "parts_count": len(part_rows),
        "parts": part_rows,
        "segments_total": len(segments),
        "claims_total": sum(len(segment.get("claims", [])) for segment in segments),
        "max_chars_per_part": max_chars_per_part,
        "oversize_parts": oversize,
        "note": "segments partitioned; no content dropped",
    }
    return {"index": index, "parts": parts, "manifest": manifest}
