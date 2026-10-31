"""Build a compact v3 EvidencePack from aggregated claims.

Inputs: claims.json, passages.json, sentences.json, frames_index.json,
optional contract.json/knowledge_snapshot.json, request.json.
No model.  Selects claims by request focus, keeps sentence context around
selected claims, and chooses a few frames near selected claim times.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from ..core.hashing import semantic_hash
from .evidence_pack import _bigrams, _focus_text
from .trace import TraceRecorder


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _pack_size(pack: dict[str, Any]) -> int:
    return len(json.dumps(pack, ensure_ascii=False, indent=1))


def _trim_sentences(pack: dict[str, Any]) -> bool:
    for segment in reversed(pack["segments"]):
        if segment["sentence_ids"]:
            removed = segment["sentence_ids"].pop()
            pack["sentences"] = [
                s for s in pack["sentences"] if s["sentence_id"] != removed
            ]
            return True
    return False


def _trim_frames(pack: dict[str, Any]) -> bool:
    for segment in reversed(pack["segments"]):
        if segment["frame_ids"]:
            removed = segment["frame_ids"].pop()
            pack["frames"] = [
                f for f in pack["frames"] if f["frame_id"] != removed
            ]
            return True
    return False


def build_pack(
    *,
    claims_doc: dict[str, Any],
    passages_doc: dict[str, Any],
    sentences_doc: dict[str, Any],
    frames_index: dict[str, Any],
    request: dict[str, Any],
    skill_id: str,
    contract: dict[str, Any] | None = None,
    knowledge: dict[str, Any] | None = None,
    snapshot_doc: dict[str, Any] | None = None,
    outline_doc: dict[str, Any] | None = None,
    max_claims_per_segment: int = 6,
    max_sentences_per_segment: int = 6,
    max_frames_per_segment: int = 2,
    max_frames: int = 24,
    frame_window_ms: int = 12_000,
    max_frame_caption_chars: int = 160,
    max_chars: int = 60_000,
) -> dict[str, Any]:
    claims = claims_doc.get("claims", [])
    passages = passages_doc.get("passages", [])
    sentences = sentences_doc.get("sentences", [])
    sentence_by_id = {s["sentence_id"]: s for s in sentences}
    passage_by_id = {p["passage_id"]: p for p in passages}
    segment_order: list[str] = []
    segment_passages: dict[str, list[dict[str, Any]]] = {}
    for passage in passages:
        segment_id = passage["segment_id"]
        if segment_id not in segment_passages:
            segment_order.append(segment_id)
        segment_passages.setdefault(segment_id, []).append(passage)
    segment_label = {
        s["segment_id"]: s.get("label", "")
        for s in (contract or {}).get("segments", [])
    }

    # Focus selection per segment.
    focus_grams = _bigrams(_focus_text(request))
    claims_by_segment: dict[str, list[dict[str, Any]]] = {}
    for claim in claims:
        claims_by_segment.setdefault(claim["segment_id"], []).append(claim)
    selected: dict[str, list[dict[str, Any]]] = {}
    passage_coverage: dict[str, list[str]] = {}
    for segment_id, items in claims_by_segment.items():
        label_grams = _bigrams(segment_label.get(segment_id, ""))

        def score(claim: dict[str, Any]) -> tuple[int, float, str]:
            grams = _bigrams(claim.get("text", ""))
            lexical = len(grams & focus_grams)
            label_bonus = 0.4 * len(grams & label_grams)
            support = 0.5 if claim.get("status") == "supported" else 0.0
            return (lexical, label_bonus + support, claim["claim_id"])

        # Coverage first: every passage/beat gets its best claim, then fill
        # remaining slots by request focus.  This prevents a lexical top-k
        # from dropping a whole mode/step (e.g. standard mode in a four-mode
        # segment) when one passage has many similar claims.
        by_passage: dict[str, list[dict[str, Any]]] = {}
        for claim in items:
            by_passage.setdefault(claim["passage_id"], []).append(claim)
        passage_rank = sorted(
            by_passage,
            key=lambda pid: max(score(c) for c in by_passage[pid]),
            reverse=True,
        )
        chosen: list[dict[str, Any]] = []
        chosen_ids: set[str] = set()
        for passage_id in passage_rank[:max_claims_per_segment]:
            best = sorted(by_passage[passage_id], key=score, reverse=True)[0]
            chosen.append(best)
            chosen_ids.add(best["claim_id"])
        for claim in sorted(items, key=score, reverse=True):
            if len(chosen) >= max_claims_per_segment:
                break
            if claim["claim_id"] not in chosen_ids:
                chosen.append(claim)
                chosen_ids.add(claim["claim_id"])
        selected[segment_id] = chosen
        passage_coverage[segment_id] = sorted(
            {c["passage_id"] for c in chosen}
        )

    claims_out = []
    evidence_out = []
    selected_claim_by_id: dict[str, dict[str, Any]] = {}
    for segment_id, items in selected.items():
        for claim in items:
            selected_claim_by_id[claim["claim_id"]] = claim
            claims_out.append(
                {
                    "claim_id": claim["claim_id"],
                    "segment_id": segment_id,
                    "passage_id": claim["passage_id"],
                    "text": claim["text"],
                    "kind": claim["kind"],
                    "status": claim.get("status", "supported"),
                    "confidence": claim.get("confidence", "medium"),
                    "scope": claim.get("scope", ""),
                    "evidence_ids": [claim["evidence_id"]],
                }
            )
            evidence_out.append(
                {
                    "evidence_id": claim["evidence_id"],
                    "claim_ids": [claim["claim_id"]],
                    "quote": claim["quote"],
                    "t_start_ms": claim["t_start_ms"],
                    "t_end_ms": claim["t_end_ms"],
                    "sentence_ids": claim["sentence_ids"],
                    "capture_method": "asr",
                    "stance": "supports",
                }
            )

    # Sentence context: claim sentences plus neighbours in the same segment.
    sentence_order = {s["sentence_id"]: i for i, s in enumerate(sentences)}
    sentence_segment = {s["sentence_id"]: s["segment_id"] for s in sentences}
    segment_sentence_ids: dict[str, list[str]] = {}
    for segment_id in segment_order:
        claim_sentence_ids = {
            sid
            for claim in selected.get(segment_id, [])
            for sid in claim.get("sentence_ids", [])
        }
        indices = sorted(sentence_order[sid] for sid in claim_sentence_ids if sid in sentence_order)
        chosen: set[str] = set()
        for index in indices:
            for offset in range(-2, 3):
                pos = index + offset
                if 0 <= pos < len(sentences):
                    candidate = sentences[pos]
                    if candidate["segment_id"] == segment_id:
                        chosen.add(candidate["sentence_id"])
        ordered = sorted(chosen, key=lambda sid: sentence_order.get(sid, 0))
        segment_sentence_ids[segment_id] = ordered[:max_sentences_per_segment]

    # Frames near selected claim times; cap per segment/global.
    all_frames = sorted(
        frames_index.get("frames", []),
        key=lambda f: (int(f.get("t_ms", 0)), f["frame_id"]),
    )
    used_frames: set[str] = set()
    segment_frame_ids: dict[str, list[str]] = {}
    for segment_id in segment_order:
        claim_times = [
            t
            for claim in selected.get(segment_id, [])
            for t in (claim["t_start_ms"], claim["t_end_ms"])
        ]
        if claim_times:
            lo, hi = min(claim_times) - frame_window_ms, max(claim_times) + frame_window_ms
        else:
            passage_times = [
                t
                for p in segment_passages.get(segment_id, [])
                for t in (p["t_start_ms"], p["t_end_ms"])
            ]
            lo, hi = (min(passage_times), max(passage_times)) if passage_times else (0, 0)
        candidates = [
            f
            for f in all_frames
            if lo <= int(f.get("t_ms", 0)) <= hi
        ]
        candidates.sort(key=lambda f: (int(f.get("t_ms", 0)), f["frame_id"]))
        chosen_frames: list[str] = []
        for frame in candidates:
            if frame["frame_id"] in used_frames:
                continue
            chosen_frames.append(frame["frame_id"])
            used_frames.add(frame["frame_id"])
            if len(chosen_frames) >= max_frames_per_segment:
                break
        segment_frame_ids[segment_id] = chosen_frames

    frames_out = []
    for frame in all_frames:
        if frame["frame_id"] not in used_frames:
            continue
        vlm_text = (frame.get("vlm_text") or "").strip()
        caption = vlm_text[:max_frame_caption_chars]
        frames_out.append(
            {
                "frame_id": frame["frame_id"],
                "segment_ids": [
                    sid for sid, ids in segment_frame_ids.items() if frame["frame_id"] in ids
                ],
                "t_ms": int(frame.get("t_ms", 0)),
                "file": frame.get("file", ""),
                "caption": caption,
                "capture_method": "vlm" if caption else "none",
                "strategy": frame.get("strategy", ""),
            }
        )
    frames_out = frames_out[:max_frames]

    segments_out = []
    for index, segment_id in enumerate(segment_order):
        passage_items = segment_passages.get(segment_id, [])
        segments_out.append(
            {
                "segment_id": segment_id,
                "label": segment_label.get(segment_id, ""),
                "t_start_ms": min(p["t_start_ms"] for p in passage_items),
                "t_end_ms": max(p["t_end_ms"] for p in passage_items),
                "prev_segment_id": segment_order[index - 1] if index > 0 else None,
                "next_segment_id": (
                    segment_order[index + 1] if index + 1 < len(segment_order) else None
                ),
                "claim_ids": [c["claim_id"] for c in selected.get(segment_id, [])],
                "sentence_ids": segment_sentence_ids.get(segment_id, []),
                "frame_ids": [
                    fid for fid in segment_frame_ids.get(segment_id, [])
                    if any(f["frame_id"] == fid for f in frames_out)
                ],
            }
        )

    sentences_out = [
        {
            "sentence_id": sid,
            "segment_id": sentence_segment[sid],
            "text": sentence_by_id[sid]["text"],
            "t_start_ms": sentence_by_id[sid]["t_start_ms"],
            "t_end_ms": sentence_by_id[sid]["t_end_ms"],
        }
        for segment in segments_out
        for sid in segment["sentence_ids"]
        if sid in sentence_by_id
    ]

    gaps = []
    conflicts = []
    if knowledge:
        gaps = knowledge.get("gaps", [])
        conflicts = knowledge.get("conflicts", [])

    pack: dict[str, Any] = {
        "schema_version": "evidence-pack-v3",
        "pack_id": "",
        "request_id": request.get("request_id")
        or f"req_{semantic_hash(request, drop_volatile=False)[:12]}",
        "video_id": (snapshot_doc or {}).get("video_id")
        or (contract or {}).get("video_id", ""),
        "skill_id": skill_id,
        "evidence_snapshot_id": (snapshot_doc or {}).get("snapshot_id", ""),
        "temporal_outline_id": (outline_doc or {}).get("outline_id", ""),
        "view_types": ["mechanism", "highlight", "frame"],
        "selection": {
            "max_claims_per_segment": max_claims_per_segment,
            "claims_considered": len(claims),
            "claims_selected": len(claims_out),
            "passage_coverage": passage_coverage,
            "max_sentences_per_segment": max_sentences_per_segment,
            "max_frames_per_segment": max_frames_per_segment,
        },
        "segments": segments_out,
        "sentences": sentences_out,
        "claims": sorted(claims_out, key=lambda c: (c["segment_id"], c["claim_id"])),
        "evidence": sorted(evidence_out, key=lambda e: (e["t_start_ms"], e["evidence_id"])),
        "frames": frames_out,
        "gaps": gaps,
        "conflicts": conflicts,
        "budget": {
            "max_chars": max_chars,
            "max_frames": max_frames,
            "frame_window_ms": frame_window_ms,
            "max_frame_caption_chars": max_frame_caption_chars,
        },
        "truncated": False,
        "truncation": {"sentences_dropped": 0, "frames_dropped": 0, "notes": []},
        "pack_hash": "",
    }

    while _pack_size(pack) > max_chars and _trim_sentences(pack):
        pack["truncated"] = True
        pack["truncation"]["sentences_dropped"] += 1
    initial_frames = len(pack["frames"])
    while _pack_size(pack) > max_chars and _trim_frames(pack):
        pack["truncated"] = True
    pack["truncation"]["frames_dropped"] = initial_frames - len(pack["frames"])
    if _pack_size(pack) > max_chars:
        pack["truncation"]["notes"].append("claims_evidence_exceed_budget")

    payload = json.loads(json.dumps(pack, ensure_ascii=False))
    payload.pop("pack_id", None)
    payload.pop("pack_hash", None)
    digest = semantic_hash(payload, drop_volatile=False)
    pack["pack_id"] = f"ep3_{digest[:12]}"
    pack["pack_hash"] = digest
    pack["pack_chars"] = _pack_size(pack)
    pack["pack_compact_chars"] = len(
        json.dumps(pack, ensure_ascii=False, separators=(",", ":"))
    )
    return pack


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a compact EvidencePack from v3 claims.")
    parser.add_argument("--claims", type=Path, required=True)
    parser.add_argument("--passages", type=Path, required=True)
    parser.add_argument("--sentences", type=Path, required=True)
    parser.add_argument("--frames-index", type=Path)
    parser.add_argument("--snapshot", type=Path)
    parser.add_argument("--outline", type=Path)
    parser.add_argument("--video-id", default="")
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--contract", type=Path)
    parser.add_argument("--knowledge", type=Path)
    parser.add_argument("--skill-id", default="reader_first_explainer")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--max-chars", type=int, default=60_000)
    args = parser.parse_args(argv)

    claims_doc = _read_json(args.claims)
    passages_doc = _read_json(args.passages)
    sentences_doc = _read_json(args.sentences)
    snapshot_doc = _read_json(args.snapshot) if args.snapshot else None
    if args.frames_index:
        frames_index = _read_json(args.frames_index)
    elif snapshot_doc:
        frames_index = snapshot_doc.get("frames_index", {})
    else:
        raise SystemExit("one of --frames-index/--snapshot is required")
    request = _read_json(args.request)
    contract = _read_json(args.contract) if args.contract else None
    knowledge = _read_json(args.knowledge) if args.knowledge else None
    outline_doc = _read_json(args.outline) if args.outline else None
    pack = build_pack(
        claims_doc=claims_doc,
        passages_doc=passages_doc,
        sentences_doc=sentences_doc,
        frames_index=frames_index,
        request=request,
        skill_id=args.skill_id,
        contract=contract,
        knowledge=knowledge,
        snapshot_doc=snapshot_doc,
        outline_doc=outline_doc,
        max_chars=args.max_chars,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    if args.video_id:
        pack["video_id"] = args.video_id
    args.out.write_text(json.dumps(pack, ensure_ascii=False, indent=1), encoding="utf-8")
    trace = TraceRecorder(args.out.parent)
    try:
        trace.stage(
            "evidence_pack",
            status="complete",
            inputs={
                "claims": args.claims,
                "passages": args.passages,
                "sentences": args.sentences,
                "frames_index": args.frames_index,
                "snapshot": args.snapshot,
                "request": args.request,
            },
            outputs={"pack": args.out},
            counts={
                "claims_in": len(claims_doc.get("claims", [])),
                "claims_selected": len(pack["claims"]),
                "sentences_selected": len(pack["sentences"]),
                "frames_selected": len(pack["frames"]),
                "segments": len(pack["segments"]),
                "pack_chars": pack["pack_chars"],
                "pack_compact_chars": pack["pack_compact_chars"],
                "truncated": pack["truncated"],
                "truncation": pack["truncation"],
            },
            params=pack["budget"],
            decisions={"selection": pack["selection"]},
            samples=[{"segments": pack["segments"][:3]}],
        )
    finally:
        trace.close()
    print(
        json.dumps(
            {
                "out": str(args.out),
                "pack_id": pack["pack_id"],
                "pack_chars": pack["pack_chars"],
                "pack_compact_chars": pack["pack_compact_chars"],
                "segments": len(pack["segments"]),
                "sentences": len(pack["sentences"]),
                "claims": len(pack["claims"]),
                "evidence": len(pack["evidence"]),
                "frames": len(pack["frames"]),
                "truncated": pack["truncated"],
                "truncation": pack["truncation"],
            },
            ensure_ascii=False,
            indent=1,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
