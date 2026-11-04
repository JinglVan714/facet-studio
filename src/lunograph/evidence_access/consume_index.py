"""Build consume-index-v1 and provide deterministic evidence lookups.

Reuse policy:
- substrate v1 stays frozen; this module only reads its artifacts;
- frame strategy/caption helpers are reused from ``light_context``;
- index/parts partition logic is reused from ``writer_view``;
- no model calls; everything is deterministic.

The index is an *access layer* for planners/verifiers/visual planning.  It is
not the Writer input: the Writer receives a separate working context.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from ..core.hashing import semantic_hash
from ..writing_v3.light_context import _caption_map, _frame_strategy
from ..writing_v3.writer_view import _partition_for_bundle

SCHEMA = "consume-index-v1"
NUMBER = re.compile(r"(?<![\w.])\d+(?:\.\d+)?%?(?![\w.])")
PROCESS_HINTS = re.compile(
    r"首先|然后|接着|最后|步骤|流程|先|再|之后|因为|所以|因此|导致|"
    r"相比|不同|对比|架构|组件|管道|循环|"
    r"first|then|finally|because|therefore|compared|pipeline|step",
    re.IGNORECASE,
)


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _sha_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _sha_obj(value: Any) -> str:
    return _sha_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    )


def _frame_id(frame: dict[str, Any]) -> str:
    return str(frame.get("frame_id") or Path(frame.get("file", "")).stem)


def normalize_frames_index(
    frames_index: dict[str, Any] | None,
    frames_vlm: dict[str, Any] | None = None,
    *,
    strategy: str | None = None,
) -> list[dict[str, Any]]:
    """Normalize raw ``frames_index`` (strategies) or snapshot ``frames``.

    Raw data has ``strategies.fixed_interval|scene``; some snapshots expose a
    top-level ``frames`` list.  ``pack_from_claims`` expects the latter, so
    this normalizer is the single adapter used by the writing layer.
    """
    if not frames_index:
        return []
    if frames_index.get("strategies"):
        name, raw_frames = _frame_strategy(frames_index, strategy or "scene")
    else:
        name = strategy or str(frames_index.get("strategy", ""))
        raw_frames = list(frames_index.get("frames", []))

    captions = _caption_map(frames_vlm)
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for frame in raw_frames:
        frame_id = _frame_id(frame)
        if not frame_id or frame_id in seen:
            continue
        seen.add(frame_id)
        caption = (
            frame.get("caption")
            or frame.get("vlm_text")
            or captions.get(frame_id, "")
            or ""
        ).strip()
        rows.append(
            {
                "frame_id": frame_id,
                "t_ms": int(frame.get("t_ms", 0)),
                "slot_end_ms": frame.get("slot_end_ms"),
                "scene_index": frame.get("scene_index"),
                "scene_start_ms": frame.get("scene_start_ms"),
                "scene_end_ms": frame.get("scene_end_ms"),
                "strategy": frame.get("strategy") or name,
                "file": frame.get("file", ""),
                "caption": caption,
                "caption_full_chars": len(caption),
                "capture_method": "vlm" if caption else "none",
            }
        )
    return sorted(rows, key=lambda row: (row["t_ms"], row["frame_id"]))


def _segment_block_map(
    source_map: dict[str, Any] | None,
) -> tuple[dict[str, dict[str, Any]], dict[str, int]]:
    segment_blocks: dict[str, dict[str, Any]] = {}
    sentence_blocks: dict[str, int] = {}
    for block in (source_map or {}).get("blocks", []):
        segment_id = str(block.get("segment_id", ""))
        if segment_id and segment_id not in segment_blocks:
            segment_blocks[segment_id] = block
        for sentence_id in block.get("sentence_ids", []):
            sentence_blocks.setdefault(str(sentence_id), int(block.get("block_index", 0)))
    return segment_blocks, sentence_blocks


def _assign_segment(t_ms: int, segments: list[dict[str, Any]]) -> str:
    for segment in segments:
        if segment["t_start_ms"] <= t_ms <= segment["t_end_ms"]:
            return segment["segment_id"]
    if not segments:
        return ""
    nearest = min(
        segments,
        key=lambda segment: min(
            abs(t_ms - segment["t_start_ms"]), abs(t_ms - segment["t_end_ms"])
        ),
    )
    return nearest["segment_id"]


def _claim_time(
    claim: dict[str, Any],
    evidence_by_claim: dict[str, list[dict[str, Any]]],
    passage_by_id: dict[str, dict[str, Any]],
    sentence_by_id: dict[str, dict[str, Any]],
    segment: dict[str, Any] | None,
) -> tuple[int, int]:
    if claim.get("t_start_ms") is not None and claim.get("t_end_ms") is not None:
        return int(claim["t_start_ms"]), int(claim["t_end_ms"])
    evidence = evidence_by_claim.get(claim.get("claim_id", ""), [])
    if evidence:
        return (
            min(int(item.get("t_start_ms", 0)) for item in evidence),
            max(int(item.get("t_end_ms", 0)) for item in evidence),
        )
    passage = passage_by_id.get(claim.get("passage_id", ""))
    if passage:
        return int(passage["t_start_ms"]), int(passage["t_end_ms"])
    times = [
        (int(sentence_by_id[sid]["t_start_ms"]), int(sentence_by_id[sid]["t_end_ms"]))
        for sid in claim.get("sentence_ids", [])
        if sid in sentence_by_id
    ]
    if times:
        return min(item[0] for item in times), max(item[1] for item in times)
    if segment is not None:
        return int(segment["t_start_ms"]), int(segment["t_end_ms"])
    return 0, 0


def build_consume_index(
    pack: dict[str, Any],
    passages: list[dict[str, Any]],
    sentences: list[dict[str, Any]],
    *,
    edited_text: str | None = None,
    source_map: dict[str, Any] | None = None,
    frames_index: dict[str, Any] | None = None,
    frames_vlm: dict[str, Any] | None = None,
    frame_strategy: str | None = None,
    video_id: str = "",
    max_chars_per_part: int | None = None,
) -> dict[str, Any]:
    """Build ``consume-index-v1`` from substrate v1 outputs.

    ``pack`` can be an EvidencePack (claim path) or a light pack (claims=[]).
    ``sentences`` should be the full transcript sentences; pack sentences are
    only a selection and are not enough for lookup/coverage.
    """
    pack_segments = list(pack.get("segments", []))
    segment_order = [str(segment.get("segment_id", "")) for segment in pack_segments]
    segment_by_id = {
        str(segment.get("segment_id", "")): segment for segment in pack_segments
    }
    segment_blocks, sentence_blocks = _segment_block_map(source_map)
    for segment_id in segment_blocks:
        if segment_id not in segment_by_id:
            segment_order.append(segment_id)

    passage_by_id = {str(item.get("passage_id", "")): item for item in passages}
    full_sentences = sentences or list(pack.get("sentences", []))
    sentence_by_id = {
        str(item.get("sentence_id", "")): item for item in full_sentences
    }

    # Evidence/claims: keep the pack's IDs and quotes for audit lookup.
    evidence_rows: list[dict[str, Any]] = []
    evidence_by_claim: dict[str, list[dict[str, Any]]] = {}
    for item in pack.get("evidence", []):
        row = {
            "evidence_id": str(item.get("evidence_id", "")),
            "claim_ids": list(item.get("claim_ids", [])),
            "quote": item.get("quote", ""),
            "t_start_ms": item.get("t_start_ms"),
            "t_end_ms": item.get("t_end_ms"),
            "sentence_ids": list(item.get("sentence_ids", [])),
        }
        evidence_rows.append(row)
        for claim_id in row["claim_ids"]:
            evidence_by_claim.setdefault(str(claim_id), []).append(row)

    segment_rows: list[dict[str, Any]] = []
    for segment_id in segment_order:
        source = segment_by_id.get(segment_id, {})
        block = segment_blocks.get(segment_id, {})
        t_start = source.get("t_start_ms")
        t_end = source.get("t_end_ms")
        if t_start is None or t_end is None:
            times = [
                (
                    int(passage_by_id[pid].get("t_start_ms", 0)),
                    int(passage_by_id[pid].get("t_end_ms", 0)),
                )
                for pid in block.get("passage_ids", [])
                if pid in passage_by_id
            ]
            if times:
                t_start = min(item[0] for item in times)
                t_end = max(item[1] for item in times)
        if t_start is None or t_end is None:
            t_start = int(block.get("text_start", 0)) if block else 0
            t_end = t_start
        segment_rows.append(
            {
                "segment_id": segment_id,
                "label": source.get("label") or block.get("label", ""),
                "t_start_ms": int(t_start),
                "t_end_ms": int(t_end),
                "part_id": None,
                "block_index": block.get("block_index"),
                "text_start": block.get("text_start"),
                "text_end": block.get("text_end"),
                "sentence_ids": list(
                    dict.fromkeys(
                        list(source.get("sentence_ids", []))
                        + list(block.get("sentence_ids", []))
                    )
                ),
                "passage_ids": list(block.get("passage_ids", [])),
                "claim_ids": list(
                    dict.fromkeys(
                        list(source.get("claim_ids", []))
                        + list(block.get("claim_ids", []))
                    )
                ),
                "frame_ids": [],
            }
        )
    segment_by_row = {row["segment_id"]: row for row in segment_rows}

    # Frames: prefer raw index (all candidates) and merge pack selection.
    pack_frames = {
        str(item.get("frame_id", "")): item for item in pack.get("frames", [])
    }
    frames = normalize_frames_index(
        frames_index, frames_vlm, strategy=frame_strategy
    )
    if not frames:
        for frame_id, item in pack_frames.items():
            caption = (item.get("caption") or "").strip()
            frames.append(
                {
                    "frame_id": frame_id,
                    "t_ms": int(item.get("t_ms", 0)),
                    "slot_end_ms": item.get("slot_end_ms"),
                    "scene_index": item.get("scene_index"),
                    "scene_start_ms": item.get("scene_start_ms"),
                    "scene_end_ms": item.get("scene_end_ms"),
                    "strategy": item.get("strategy", ""),
                    "file": item.get("file", ""),
                    "caption": caption,
                    "caption_full_chars": len(caption),
                    "capture_method": item.get("capture_method", "vlm" if caption else "none"),
                }
            )
    for frame in frames:
        selected = pack_frames.get(frame["frame_id"])
        frame["selected"] = selected is not None
        if selected is not None:
            if not frame["caption"]:
                frame["caption"] = (selected.get("caption") or "").strip()
                frame["caption_full_chars"] = len(frame["caption"])
            frame["segment_ids"] = list(selected.get("segment_ids", []))
        else:
            frame["segment_ids"] = []
        if not frame["segment_ids"]:
            segment_id = _assign_segment(frame["t_ms"], segment_rows)
            frame["segment_ids"] = [segment_id] if segment_id else []
        for segment_id in frame["segment_ids"]:
            row = segment_by_row.get(segment_id)
            if row is not None and frame["frame_id"] not in row["frame_ids"]:
                row["frame_ids"].append(frame["frame_id"])

    # Claims + sentences.
    claim_rows: list[dict[str, Any]] = []
    for claim in pack.get("claims", []):
        segment_id = str(claim.get("segment_id", ""))
        segment = segment_by_row.get(segment_id)
        block = segment_blocks.get(segment_id, {})
        claim_id = str(claim.get("claim_id", ""))
        t_start, t_end = _claim_time(
            claim, evidence_by_claim, passage_by_id, sentence_by_id, segment
        )
        claim_rows.append(
            {
                "claim_id": claim_id,
                "segment_id": segment_id,
                "status": claim.get("status", ""),
                "kind": claim.get("kind", ""),
                "text": claim.get("text", ""),
                "scope": claim.get("scope", ""),
                "quote": claim.get("quote", ""),
                "passage_id": claim.get("passage_id", ""),
                "t_start_ms": t_start,
                "t_end_ms": t_end,
                "block_index": sentence_blocks.get(
                    next(iter(claim.get("sentence_ids", [])), ""),
                    block.get("block_index"),
                ),
                "part_id": None,
                "sentence_ids": list(claim.get("sentence_ids", [])),
                "evidence_ids": list(claim.get("evidence_ids", [])),
                "source_claim_ids": list(
                    pack.get("provenance", {})
                    .get("claims", {})
                    .get(claim_id, {})
                    .get("source_claim_ids", [])
                ),
                "source_evidence_ids": list(
                    pack.get("provenance", {})
                    .get("claims", {})
                    .get(claim_id, {})
                    .get("source_evidence_ids", [])
                ),
            }
        )

    sentence_rows: list[dict[str, Any]] = []
    for sentence in full_sentences:
        sentence_id = str(sentence.get("sentence_id", ""))
        segment_id = str(sentence.get("segment_id", ""))
        sentence_rows.append(
            {
                "sentence_id": sentence_id,
                "segment_id": segment_id,
                "t_start_ms": int(sentence.get("t_start_ms", 0)),
                "t_end_ms": int(sentence.get("t_end_ms", 0)),
                "text": sentence.get("text", ""),
                "block_index": sentence_blocks.get(sentence_id),
                "part_id": None,
            }
        )
    sentence_rows.sort(key=lambda row: (row["t_start_ms"], row["sentence_id"]))

    # Parts: reuse writer_view's partition logic; never drop content.
    part_source = [
        {
            "segment_id": row["segment_id"],
            "label": row["label"],
            "claims": [
                {"claim_id": claim["claim_id"]}
                for claim in claim_rows
                if claim["segment_id"] == row["segment_id"]
            ],
            "block_index": row["block_index"],
            "text_start": row["text_start"],
            "text_end": row["text_end"],
        }
        for row in segment_rows
    ]
    groups, _oversize = _partition_for_bundle(
        part_source, max_chars_per_part=max_chars_per_part
    )
    parts: list[dict[str, Any]] = []
    for index, group in enumerate(groups, start=1):
        part_id = f"part_{index:02d}"
        segment_ids = [part_source[item]["segment_id"] for item in group]
        for segment_id in segment_ids:
            segment_by_row[segment_id]["part_id"] = part_id
        starts = [
            int(part_source[item]["text_start"])
            for item in group
            if part_source[item]["text_start"] is not None
        ]
        ends = [
            int(part_source[item]["text_end"])
            for item in group
            if part_source[item]["text_end"] is not None
        ]
        text_start = min(starts) if starts else None
        text_end = max(ends) if ends else None
        if edited_text and text_start is not None and text_end is not None:
            chars = len(edited_text[text_start:text_end])
        else:
            chars = len(json.dumps(part_source[group], ensure_ascii=False))
        parts.append(
            {
                "part_id": part_id,
                "block_from": min(
                    (
                        int(part_source[item]["block_index"])
                        for item in group
                        if part_source[item]["block_index"] is not None
                    ),
                    default=None,
                ),
                "block_to": max(
                    (
                        int(part_source[item]["block_index"])
                        for item in group
                        if part_source[item]["block_index"] is not None
                    ),
                    default=None,
                ),
                "segment_ids": segment_ids,
                "text_start": text_start,
                "text_end": text_end,
                "chars": chars,
                "oversize": (
                    max_chars_per_part is not None and chars > max_chars_per_part
                ),
            }
        )

    part_by_segment = {
        row["segment_id"]: row["part_id"] for row in segment_rows
    }
    for claim in claim_rows:
        claim["part_id"] = part_by_segment.get(claim["segment_id"])
    for sentence in sentence_rows:
        sentence["part_id"] = part_by_segment.get(sentence["segment_id"])

    selected_frame_ids = {
        frame_id for frame_id, item in pack_frames.items() if item
    }
    if selected_frame_ids:
        for frame in frames:
            frame["selected"] = frame["frame_id"] in selected_frame_ids

    blocks = list((source_map or {}).get("blocks", []))
    known_segments = set(segment_by_row)
    source = {
        "pack_id": pack.get("pack_id", ""),
        "pack_hash": pack.get("pack_hash", ""),
        "edited_sha256": _sha_text(edited_text) if edited_text is not None else "",
        "source_map_sha256": _sha_obj(source_map) if source_map is not None else "",
        "frames_index_sha256": _sha_obj(frames_index) if frames_index is not None else "",
        "frames_vlm_sha256": _sha_obj(frames_vlm) if frames_vlm is not None else "",
    }
    coverage = {
        "segments_total": len(segment_rows),
        "segments_with_claims": sum(1 for row in segment_rows if row["claim_ids"]),
        "segments_with_frames": sum(1 for row in segment_rows if row["frame_ids"]),
        "claims_total": len(claim_rows),
        "evidence_total": len(evidence_rows),
        "sentences_total": len(sentence_rows),
        "frames_total": len(frames),
        "frames_selected": sum(1 for frame in frames if frame.get("selected")),
        "unassigned_blocks": [
            block.get("block_index")
            for block in blocks
            if block.get("segment_id") not in known_segments
        ],
        "claims_unassigned": [
            claim["claim_id"]
            for claim in claim_rows
            if claim["segment_id"] not in known_segments
        ],
        "sentences_unassigned": [
            sentence["sentence_id"]
            for sentence in sentence_rows
            if sentence["segment_id"] not in known_segments
        ],
    }
    index: dict[str, Any] = {
        "schema": SCHEMA,
        "video_id": video_id or str(pack.get("video_id", "")),
        "timebase": "ms",
        "source": source,
        "segments": segment_rows,
        "claims": claim_rows,
        "evidence": evidence_rows,
        "sentences": sentence_rows,
        "frames": frames,
        "parts": parts,
        "blocks": blocks,
        "gaps": list(pack.get("gaps", [])),
        "conflicts": list(pack.get("conflicts", [])),
        "coverage": coverage,
        "index_hash": "",
    }
    payload = dict(index)
    payload.pop("index_hash", None)
    index["index_hash"] = semantic_hash(payload, drop_volatile=False)
    return index


def _find_part(index: dict[str, Any], part_id: str) -> dict[str, Any] | None:
    return next(
        (part for part in index.get("parts", []) if part["part_id"] == part_id),
        None,
    )


def get_part(
    index: dict[str, Any],
    part_id: str,
    *,
    edited_text: str | None = None,
) -> dict[str, Any]:
    """Return one part's segments/claims/sentences/frames and optional text."""
    part = _find_part(index, part_id)
    if part is None:
        return {"found": False, "part_id": part_id}
    segment_ids = set(part.get("segment_ids", []))
    segments = [
        row for row in index.get("segments", [])
        if row["segment_id"] in segment_ids
    ]
    claims = [
        row for row in index.get("claims", [])
        if row["segment_id"] in segment_ids
    ]
    sentences = [
        row for row in index.get("sentences", [])
        if row["segment_id"] in segment_ids
    ]
    frames = [
        row for row in index.get("frames", [])
        if set(row.get("segment_ids", [])) & segment_ids
    ]
    text = None
    if (
        edited_text is not None
        and part.get("text_start") is not None
        and part.get("text_end") is not None
    ):
        text = edited_text[int(part["text_start"]):int(part["text_end"])]
    return {
        "found": True,
        "part": part,
        "segments": segments,
        "claims": claims,
        "sentences": sentences,
        "frames": frames,
        "text": text,
    }


def lookup_claim(index: dict[str, Any], claim_id: str) -> dict[str, Any]:
    """Claim -> evidence/quote/time/block/frames_near/segment."""
    claim = next(
        (row for row in index.get("claims", []) if row["claim_id"] == claim_id),
        None,
    )
    if claim is None:
        return {"found": False, "claim_id": claim_id}
    segment = next(
        (
            row
            for row in index.get("segments", [])
            if row["segment_id"] == claim.get("segment_id")
        ),
        None,
    )
    evidence = [
        row for row in index.get("evidence", [])
        if claim_id in row.get("claim_ids", [])
    ]
    frames_near = [
        row
        for row in index.get("frames", [])
        if claim["t_start_ms"] - 12_000 <= row["t_ms"] <= claim["t_end_ms"] + 12_000
    ]
    block = next(
        (
            row
            for row in index.get("blocks", [])
            if row.get("block_index") == claim.get("block_index")
            and row.get("segment_id") == claim.get("segment_id")
        ),
        None,
    )
    return {
        "found": True,
        "claim": claim,
        "segment": segment,
        "evidence": evidence,
        "block": block,
        "frames_near": frames_near,
    }


def lookup_frame(
    index: dict[str, Any],
    *,
    frame_id: str | None = None,
    t_ms: int | None = None,
    window_ms: int = 0,
) -> dict[str, Any]:
    """Frame by ID or time window; include nearby claims."""
    frames = index.get("frames", [])
    if frame_id is not None:
        frame = next((row for row in frames if row["frame_id"] == frame_id), None)
        selected = [frame] if frame is not None else []
    elif t_ms is not None:
        lo, hi = t_ms - window_ms, t_ms + window_ms
        selected = [row for row in frames if lo <= row["t_ms"] <= hi]
    else:
        return {"found": False, "frames": [], "claims_near": []}
    if not selected:
        return {"found": False, "frames": [], "claims_near": []}
    lo = min(row["t_ms"] for row in selected) - max(window_ms, 0)
    hi = max(row["t_ms"] for row in selected) + max(window_ms, 0)
    claims_near = [
        row
        for row in index.get("claims", [])
        if row["t_start_ms"] <= hi and row["t_end_ms"] >= lo
    ]
    return {
        "found": True,
        "frame": selected[0] if frame_id is not None else None,
        "frames": selected,
        "claims_near": claims_near,
    }


def _scope_segment_ids(
    index: dict[str, Any],
    *,
    segment_id: str | None = None,
    claim_id: str | None = None,
    t0_ms: int | None = None,
    t1_ms: int | None = None,
    neighbor_ms: int = 0,
) -> list[str]:
    segments = index.get("segments", [])
    if claim_id is not None:
        claim = next(
            (row for row in index.get("claims", []) if row["claim_id"] == claim_id),
            None,
        )
        if claim is None:
            return []
        lo = claim["t_start_ms"] - max(neighbor_ms, 0)
        hi = claim["t_end_ms"] + max(neighbor_ms, 0)
        return [
            row["segment_id"]
            for row in segments
            if row["t_start_ms"] <= hi and row["t_end_ms"] >= lo
        ]
    if segment_id is not None:
        return [segment_id]
    if t0_ms is not None or t1_ms is not None:
        lo = t0_ms if t0_ms is not None else -10**15
        hi = t1_ms if t1_ms is not None else 10**15
        return [
            row["segment_id"]
            for row in segments
            if row["t_start_ms"] <= hi and row["t_end_ms"] >= lo
        ]
    return [row["segment_id"] for row in segments]


def slice_evidence(
    index: dict[str, Any],
    *,
    segment_id: str | None = None,
    claim_id: str | None = None,
    t0_ms: int | None = None,
    t1_ms: int | None = None,
    neighbor_ms: int = 0,
) -> dict[str, Any]:
    """Return ordered segments/claims/sentences/frames in a scope."""
    segment_ids = set(
        _scope_segment_ids(
            index,
            segment_id=segment_id,
            claim_id=claim_id,
            t0_ms=t0_ms,
            t1_ms=t1_ms,
            neighbor_ms=neighbor_ms,
        )
    )
    lo = t0_ms
    hi = t1_ms
    if claim_id is not None:
        claim = next(
            (row for row in index.get("claims", []) if row["claim_id"] == claim_id),
            None,
        )
        if claim is not None:
            lo = claim["t_start_ms"] - max(neighbor_ms, 0)
            hi = claim["t_end_ms"] + max(neighbor_ms, 0)
    segments = [
        row for row in index.get("segments", [])
        if row["segment_id"] in segment_ids
        and (lo is None or row["t_end_ms"] >= lo)
        and (hi is None or row["t_start_ms"] <= hi)
    ]
    claims = [
        row for row in index.get("claims", [])
        if row["segment_id"] in segment_ids
        and (lo is None or row["t_end_ms"] >= lo)
        and (hi is None or row["t_start_ms"] <= hi)
    ]
    sentences = [
        row for row in index.get("sentences", [])
        if row["segment_id"] in segment_ids
        and (lo is None or row["t_end_ms"] >= lo)
        and (hi is None or row["t_start_ms"] <= hi)
    ]
    frames = [
        row for row in index.get("frames", [])
        if set(row.get("segment_ids", [])) & segment_ids
        and (lo is None or row["t_ms"] >= lo)
        and (hi is None or row["t_ms"] <= hi)
    ]
    return {
        "scope": {
            "segment_ids": sorted(segment_ids),
            "claim_id": claim_id,
            "t0_ms": lo,
            "t1_ms": hi,
        },
        "segments": sorted(segments, key=lambda row: row["t_start_ms"]),
        "claims": sorted(claims, key=lambda row: row["t_start_ms"]),
        "sentences": sorted(sentences, key=lambda row: row["t_start_ms"]),
        "frames": sorted(frames, key=lambda row: row["t_ms"]),
    }


def visual_lookup(
    index: dict[str, Any],
    *,
    segment_id: str | None = None,
    claim_id: str | None = None,
    t_start_ms: int | None = None,
    t_end_ms: int | None = None,
) -> dict[str, Any]:
    """Deterministic visual candidates; no model call.

    Candidates are hints for the VisualPlanner: frames to inspect, numbers
    that may become a chart/table, and process/causal text that may become a
    diagram.  Classification/series/axis still need a vision/model pass later.
    """
    sliced = slice_evidence(
        index,
        segment_id=segment_id,
        claim_id=claim_id,
        t0_ms=t_start_ms,
        t1_ms=t_end_ms,
    )
    claims = sliced["claims"]
    sentences = sliced["sentences"]
    frames = sliced["frames"]
    evidence = [
        row
        for row in index.get("evidence", [])
        if any(claim_id in row.get("claim_ids", []) for claim_id in
               {claim["claim_id"] for claim in claims})
    ]

    numbers: list[dict[str, Any]] = []
    seen_numbers: set[str] = set()
    for kind, rows, text_key in (
        ("claim", claims, "text"),
        ("sentence", sentences, "text"),
        ("evidence", evidence, "quote"),
    ):
        for row in rows:
            for match in NUMBER.finditer(row.get(text_key, "")):
                value = match.group(0)
                if value in seen_numbers:
                    continue
                seen_numbers.add(value)
                numbers.append(
                    {
                        "value": value,
                        "raw": value,
                        "source_kind": kind,
                        "source_id": row.get("claim_id")
                        or row.get("sentence_id")
                        or row.get("evidence_id"),
                    }
                )

    has_process = any(
        PROCESS_HINTS.search(row.get("text", "") or row.get("quote", ""))
        for row in claims + sentences + evidence
    )
    candidates: list[dict[str, Any]] = []
    for frame in frames[:3]:
        payload = {
            "kind": "real_frame",
            "frame_id": frame["frame_id"],
            "t_ms": frame["t_ms"],
            "caption": frame.get("caption", ""),
        }
        candidates.append(
            {
                "candidate_id": f"vc_{semantic_hash(payload, drop_volatile=False)[:12]}",
                "kind": "real_frame",
                "frame_id": frame["frame_id"],
                "t_ms": frame["t_ms"],
                "raw_text": frame.get("caption", ""),
                "numbers": [],
                "relation_ids": [],
                "evidence_ids": [],
                "deterministic": True,
                "needs_model": True,
                "reason": "frame_caption_available",
            }
        )
    if len(numbers) >= 2:
        payload = {"kind": "chart", "numbers": [n["value"] for n in numbers]}
        candidates.append(
            {
                "candidate_id": f"vc_{semantic_hash(payload, drop_volatile=False)[:12]}",
                "kind": "chart",
                "frame_id": None,
                "t_ms": claims[0]["t_start_ms"] if claims else None,
                "raw_text": "",
                "numbers": numbers,
                "relation_ids": [],
                "evidence_ids": [
                    row["evidence_id"]
                    for row in evidence
                    if row.get("evidence_id")
                ],
                "deterministic": True,
                "needs_model": True,
                "reason": "numbers_present",
            }
        )
    if has_process:
        payload = {"kind": "diagram", "segment_ids": sliced["scope"]["segment_ids"]}
        candidates.append(
            {
                "candidate_id": f"vc_{semantic_hash(payload, drop_volatile=False)[:12]}",
                "kind": "diagram",
                "frame_id": None,
                "t_ms": claims[0]["t_start_ms"] if claims else None,
                "raw_text": "",
                "numbers": [],
                "relation_ids": [],
                "evidence_ids": [
                    row["evidence_id"] for row in evidence if row.get("evidence_id")
                ],
                "deterministic": True,
                "needs_model": True,
                "reason": "process_or_causal_hints",
            }
        )
    if len(numbers) >= 3:
        payload = {"kind": "table", "numbers": [n["value"] for n in numbers]}
        candidates.append(
            {
                "candidate_id": f"vc_{semantic_hash(payload, drop_volatile=False)[:12]}",
                "kind": "table",
                "frame_id": None,
                "t_ms": claims[0]["t_start_ms"] if claims else None,
                "raw_text": "",
                "numbers": numbers,
                "relation_ids": [],
                "evidence_ids": [
                    row["evidence_id"] for row in evidence if row.get("evidence_id")
                ],
                "deterministic": True,
                "needs_model": True,
                "reason": "multiple_numbers",
            }
        )
    if not candidates:
        candidates.append(
            {
                "candidate_id": "vc_none",
                "kind": "no_visual",
                "frame_id": None,
                "t_ms": None,
                "raw_text": "",
                "numbers": [],
                "relation_ids": [],
                "evidence_ids": [],
                "deterministic": True,
                "needs_model": False,
                "reason": "no_candidate",
            }
        )
    return {"scope": sliced["scope"], "candidates": candidates}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build consume-index-v1 from substrate v1 artifacts (no model)."
    )
    parser.add_argument("--pack", type=Path, required=True)
    parser.add_argument("--passages", type=Path, required=True)
    parser.add_argument("--sentences", type=Path, required=True)
    parser.add_argument("--edited-text", type=Path, required=True)
    parser.add_argument("--source-map", type=Path, required=True)
    parser.add_argument("--frames-index", type=Path)
    parser.add_argument("--frames-vlm", type=Path)
    parser.add_argument(
        "--frame-strategy",
        default=None,
        help="scene|fixed_interval; default: scene if available, else fixed_interval",
    )
    parser.add_argument("--video-id", default="")
    parser.add_argument("--max-chars-per-part", type=int, default=None)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)

    pack = _read_json(args.pack)
    passages = _read_json(args.passages).get("passages", [])
    sentences = _read_json(args.sentences).get("sentences", [])
    edited_text = args.edited_text.read_text(encoding="utf-8-sig")
    source_map = _read_json(args.source_map)
    frames_index = _read_json(args.frames_index) if args.frames_index else None
    frames_vlm = _read_json(args.frames_vlm) if args.frames_vlm else None
    index = build_consume_index(
        pack,
        passages,
        sentences,
        edited_text=edited_text,
        source_map=source_map,
        frames_index=frames_index,
        frames_vlm=frames_vlm,
        frame_strategy=args.frame_strategy,
        video_id=args.video_id,
        max_chars_per_part=args.max_chars_per_part,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(index, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "status": "complete",
                "out": str(args.out),
                "segments": len(index["segments"]),
                "claims": len(index["claims"]),
                "sentences": len(index["sentences"]),
                "frames": len(index["frames"]),
                "parts": len(index["parts"]),
                "index_hash": index["index_hash"],
            },
            ensure_ascii=False,
            indent=1,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
