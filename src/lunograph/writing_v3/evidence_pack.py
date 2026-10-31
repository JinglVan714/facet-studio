"""Build a context-preserving EvidencePack from existing substrate JSON.

v3 prototype.  Reads EvidenceSnapshot / TemporalOutline / optional
KnowledgeSnapshot, groups claims by temporal segment, and emits one compact
JSON pack:

- segments keep the reader/argument order and point to unit/claim/frame IDs;
- units/claims/evidence/frames are top-level arrays (no repeated nested text);
- every claim keeps its exact evidence quotes and stance;
- frame candidates are near segment boundaries/claim times, with provenance;
- gaps/conflicts pass through unchanged.

No model is called; no facts are created.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from ..core.hashing import semantic_hash


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _norm(text: str) -> str:
    return "".join(ch for ch in text.lower() if ch.isalnum())


def _bigrams(text: str) -> set[str]:
    value = _norm(text)
    return {value[i : i + 2] for i in range(len(value) - 1)}


def _focus_text(request: dict[str, Any]) -> str:
    parts = [
        request.get("central_question", ""),
        request.get("job_to_be_done", ""),
        *request.get("required_information", []),
        *request.get("success_criteria", []),
    ]
    return "\n".join(str(part) for part in parts if part)


def _claim_evidence_links(snapshot: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    links: dict[str, list[dict[str, Any]]] = {}
    for link in snapshot.get("evidence_claim_links", []):
        links.setdefault(link["claim_id"], []).append(link)
    return links


def _assertion_segment_map(
    snapshot: dict[str, Any], outline: dict[str, Any]
) -> dict[str, str]:
    unit_segment = {u["unit_id"]: u["segment_id"] for u in outline.get("units", [])}
    assertion_segment: dict[str, str] = {}
    for assertion in snapshot.get("assertions", []):
        counts: dict[str, int] = {}
        for unit_id in assertion.get("unit_ids", []):
            segment_id = unit_segment.get(unit_id)
            if segment_id:
                counts[segment_id] = counts.get(segment_id, 0) + 1
        if counts:
            assertion_segment[assertion["id"]] = max(counts, key=counts.get)
    return assertion_segment


def _segment_of_claim(
    claim: dict[str, Any],
    *,
    segment_ids: set[str],
    assertion_segment: dict[str, str],
) -> str:
    chunk_id = claim.get("chunk_id")
    if chunk_id in segment_ids:
        return chunk_id
    assertion_id = claim.get("source_assertion_id")
    if assertion_id in assertion_segment:
        return assertion_segment[assertion_id]
    return "unassigned"


def _pack_size(pack: dict[str, Any]) -> int:
    return len(json.dumps(pack, ensure_ascii=False, indent=1))


def _trim_units(pack: dict[str, Any]) -> bool:
    for seg in reversed(pack["segments"]):
        if seg["unit_ids"]:
            removed = seg["unit_ids"].pop()
            pack["units"] = [u for u in pack["units"] if u["unit_id"] != removed]
            return True
    return False


def _trim_frames(pack: dict[str, Any]) -> bool:
    referenced = {
        fid for ev in pack["evidence"] for fid in ev.get("frame_ids", [])
    }
    for index in range(len(pack["frames"]) - 1, -1, -1):
        frame_id = pack["frames"][index]["frame_id"]
        if frame_id in referenced:
            continue
        pack["frames"].pop(index)
        for seg in pack["segments"]:
            if frame_id in seg["frame_ids"]:
                seg["frame_ids"].remove(frame_id)
        return True
    return False


def build_evidence_pack(
    *,
    snapshot: dict[str, Any],
    outline: dict[str, Any],
    knowledge: dict[str, Any] | None,
    request: dict[str, Any],
    skill_id: str,
    view_types: list[str] | None = None,
    max_chars: int = 90_000,
    max_frames: int = 30,
    frame_window_ms: int = 10_000,
    max_frames_per_segment: int = 2,
    max_claims_per_segment: int = 4,
    max_units_per_segment: int = 6,
    unit_window_ms: int = 10_000,
    max_frame_caption_chars: int = 160,
) -> dict[str, Any]:
    """Build one compact EvidencePack; never invent IDs or text."""
    segment_ids = {s["segment_id"] for s in outline.get("segments", [])}
    assertion_segment = _assertion_segment_map(snapshot, outline)
    evidence_by_id = {e["id"]: e for e in snapshot.get("evidence", [])}
    links_by_claim = _claim_evidence_links(snapshot)

    outline_units = outline.get("units", [])
    unit_by_id = {u["unit_id"]: u for u in outline_units}
    all_frames = sorted(
        snapshot.get("frames_index", {}).get("frames", []),
        key=lambda f: (int(f.get("t_ms", 0)), f["frame_id"]),
    )
    frames_by_id = {f["frame_id"]: f for f in all_frames}

    claims_by_segment: dict[str, list[dict[str, Any]]] = {}
    for claim in snapshot.get("claims", []):
        segment_id = _segment_of_claim(
            claim,
            segment_ids=segment_ids,
            assertion_segment=assertion_segment,
        )
        claims_by_segment.setdefault(segment_id, []).append(claim)

    # Deterministic focus selection: score claims against the request text and
    # their segment label, keep the top claims per segment.  This is a View,
    # not a coverage dump; all selected claims keep their exact evidence.
    segment_by_id = {s["segment_id"]: s for s in outline.get("segments", [])}
    focus = _focus_text(request)
    focus_grams = _bigrams(focus)
    claims_considered = sum(len(v) for v in claims_by_segment.values())
    selected_by_segment: dict[str, list[dict[str, Any]]] = {}
    for segment_id, claims in claims_by_segment.items():
        label_grams = _bigrams(segment_by_id.get(segment_id, {}).get("label", ""))

        def score(claim: dict[str, Any]) -> tuple[int, float, str]:
            claim_grams = _bigrams(claim.get("text", ""))
            lexical = len(claim_grams & focus_grams)
            label_bonus = 0.4 * len(claim_grams & label_grams)
            support_bonus = 0.5 if claim.get("support_status") == "supported" else 0.0
            return (lexical, label_bonus + support_bonus, claim["id"])

        ranked = sorted(claims, key=score, reverse=True)
        selected_by_segment[segment_id] = ranked[: max_claims_per_segment]
    claims_by_segment = selected_by_segment

    claims_out: list[dict[str, Any]] = []
    evidence_out: dict[str, dict[str, Any]] = {}
    for segment in outline.get("segments", []):
        segment_id = segment["segment_id"]
        for claim in claims_by_segment.get(segment_id, []):
            links = links_by_claim.get(claim["id"], [])
            evidence_ids: list[str] = []
            for link in links:
                evidence = evidence_by_id.get(link["evidence_id"])
                if evidence is None:
                    continue
                evidence_id = evidence["id"]
                evidence_ids.append(evidence_id)
                if evidence_id not in evidence_out:
                    locator = evidence.get("locator", {})
                    evidence_out[evidence_id] = {
                        "evidence_id": evidence_id,
                        "claim_ids": [],
                        "quote": evidence.get("raw_content", ""),
                        "t_start_ms": int(locator.get("t_start_ms", 0)),
                        "t_end_ms": int(locator.get("t_end_ms", 0)),
                        "frame_ids": list(
                            evidence.get("frame_refs")
                            or locator.get("frame_ids")
                            or []
                        ),
                        "capture_method": evidence.get("capture_method", "asr"),
                        "stance": link.get("stance", "supports"),
                        "rights_scope": evidence.get("rights_scope", "unknown"),
                    }
                if claim["id"] not in evidence_out[evidence_id]["claim_ids"]:
                    evidence_out[evidence_id]["claim_ids"].append(claim["id"])
            claims_out.append(
                {
                    "claim_id": claim["id"],
                    "segment_id": segment_id,
                    "text": claim.get("text", ""),
                    "kind": claim.get("kind", ""),
                    "support_status": claim.get("support_status", ""),
                    "evidence_ids": sorted(set(evidence_ids)),
                }
            )

    # Frames: candidates near a segment boundary/claim time, plus frames
    # referenced by evidence.  Assign to segments; cap globally/per segment.
    referenced_frames = {
        fid for ev in evidence_out.values() for fid in ev.get("frame_ids", [])
    }
    segment_frame_ids: dict[str, list[str]] = {}
    used_frames: set[str] = set()
    for segment in outline.get("segments", []):
        segment_id = segment["segment_id"]
        first_ms = int(segment.get("first_ms", 0))
        last_ms = int(segment.get("last_ms", 0))
        claim_ids = {
            c["claim_id"] for c in claims_out if c["segment_id"] == segment_id
        }
        claim_evidence_frames = {
            fid
            for ev in evidence_out.values()
            if set(ev["claim_ids"]) & claim_ids
            for fid in ev.get("frame_ids", [])
        }
        candidates = [
            f
            for f in all_frames
            if f["frame_id"] in claim_evidence_frames
            or f["frame_id"] in referenced_frames
            or (first_ms - frame_window_ms <= int(f.get("t_ms", 0)) <= last_ms + frame_window_ms)
        ]
        candidates.sort(
            key=lambda f: (
                0 if f["frame_id"] in claim_evidence_frames else 1,
                int(f.get("t_ms", 0)),
                f["frame_id"],
            )
        )
        selected: list[str] = []
        for frame in candidates:
            if len(selected) >= max_frames_per_segment:
                break
            if frame["frame_id"] in used_frames and frame["frame_id"] not in claim_evidence_frames:
                continue
            selected.append(frame["frame_id"])
            used_frames.add(frame["frame_id"])
        segment_frame_ids[segment_id] = selected

    frames_out: list[dict[str, Any]] = []
    for segment_id, frame_ids in segment_frame_ids.items():
        for frame_id in frame_ids:
            frame = frames_by_id.get(frame_id)
            if frame is None:
                continue
            vlm_text = (frame.get("vlm_text") or "").strip()
            caption = vlm_text[:max_frame_caption_chars]
            frames_out.append(
                {
                    "frame_id": frame_id,
                    "segment_ids": [
                        sid for sid, ids in segment_frame_ids.items() if frame_id in ids
                    ],
                    "t_ms": int(frame.get("t_ms", 0)),
                    "file": frame.get("file", ""),
                    "caption": caption,
                    "capture_method": "vlm" if caption else "none",
                    "strategy": frame.get("strategy", ""),
                }
            )
    # Dedupe frame records; cap global max_frames, keeping referenced first.
    dedup: dict[str, dict[str, Any]] = {}
    for frame in frames_out:
        dedup.setdefault(frame["frame_id"], frame)
    ordered_frames = sorted(
        dedup.values(),
        key=lambda f: (
            0 if f["frame_id"] in referenced_frames else 1,
            f["t_ms"],
            f["frame_id"],
        ),
    )[:max_frames]
    kept_frame_ids = {f["frame_id"] for f in ordered_frames}
    for segment in outline.get("segments", []):
        segment_id = segment["segment_id"]
        segment_frame_ids[segment_id] = [
            fid for fid in segment_frame_ids[segment_id] if fid in kept_frame_ids
        ]

    units_out: list[dict[str, Any]] = []
    segments_out: list[dict[str, Any]] = []
    for index, segment in enumerate(outline.get("segments", [])):
        segment_id = segment["segment_id"]
        claim_ids = [c["claim_id"] for c in claims_out if c["segment_id"] == segment_id]
        selected_claim_set = set(claim_ids)
        selected_times = [
            t
            for ev in evidence_out.values()
            if selected_claim_set & set(ev["claim_ids"])
            for t in (ev["t_start_ms"], ev["t_end_ms"])
        ]
        if selected_times:
            lo = min(selected_times) - unit_window_ms
            hi = max(selected_times) + unit_window_ms
            candidates = [
                u
                for u in outline_units
                if u.get("segment_id") == segment_id
                and int(u.get("t", [0, 0])[0]) <= hi
                and int(u.get("t", [0, 0])[1]) >= lo
            ]
            candidates.sort(
                key=lambda u: (
                    min(abs(int(u.get("t", [0, 0])[0]) - t) for t in selected_times),
                    int(u.get("t", [0, 0])[0]),
                    u["unit_id"],
                )
            )
            unit_ids = [u["unit_id"] for u in candidates[:max_units_per_segment]]
        else:
            unit_ids = []
        segments_out.append(
            {
                "segment_id": segment_id,
                "label": segment.get("label", ""),
                "first_ms": int(segment.get("first_ms", 0)),
                "last_ms": int(segment.get("last_ms", 0)),
                "prev_segment_id": (
                    outline["segments"][index - 1]["segment_id"] if index > 0 else None
                ),
                "next_segment_id": (
                    outline["segments"][index + 1]["segment_id"]
                    if index + 1 < len(outline["segments"])
                    else None
                ),
                "unit_ids": unit_ids,
                "claim_ids": claim_ids,
                "frame_ids": segment_frame_ids.get(segment_id, []),
            }
        )
        for unit_id in unit_ids:
            unit = unit_by_id.get(unit_id)
            if unit is None:
                continue
            units_out.append(
                {
                    "unit_id": unit_id,
                    "segment_id": segment_id,
                    "text": unit.get("raw", ""),
                    "t_start_ms": int(unit.get("t", [0, 0])[0]),
                    "t_end_ms": int(unit.get("t", [0, 0])[1]),
                }
            )

    gaps = []
    conflicts = []
    if knowledge:
        gaps = [
            {
                "gap_id": g.get("gap_id", ""),
                "description": g.get("description", ""),
                "related_cluster_ids": g.get("related_cluster_ids", []),
                "severity": g.get("severity", "major"),
                "status": g.get("status", "open"),
            }
            for g in knowledge.get("gaps", [])
        ]
        conflicts = [
            {
                "conflict_id": c.get("conflict_id", ""),
                "cluster_ids": c.get("cluster_ids", []),
                "claim_ids": c.get("claim_ids", []),
                "description": c.get("description", ""),
                "basis": c.get("basis", "explicit"),
                "severity": c.get("severity", "major"),
                "status": c.get("status", "needs_review"),
            }
            for c in knowledge.get("conflicts", [])
        ]

    pack: dict[str, Any] = {
        "schema_version": "evidence-pack-v3",
        "pack_id": "",
        "request_id": request.get("request_id")
        or f"req_{semantic_hash(request, drop_volatile=False)[:12]}",
        "video_id": snapshot.get("video_id", ""),
        "skill_id": skill_id,
        "evidence_snapshot_id": snapshot.get("snapshot_id", ""),
        "temporal_outline_id": outline.get("outline_id", ""),
        "view_types": view_types or ["mechanism", "highlight", "frame"],
        "selection": {
            "max_claims_per_segment": max_claims_per_segment,
            "claims_considered": claims_considered,
            "claims_selected": len(claims_out),
            "max_units_per_segment": max_units_per_segment,
            "unit_window_ms": unit_window_ms,
            "max_frame_caption_chars": max_frame_caption_chars,
            "focus_chars": len(focus),
        },
        "segments": segments_out,
        "units": units_out,
        "claims": sorted(claims_out, key=lambda c: (c["segment_id"], c["claim_id"])),
        "evidence": sorted(
            evidence_out.values(),
            key=lambda e: (e["t_start_ms"], e["evidence_id"]),
        ),
        "frames": ordered_frames,
        "gaps": gaps,
        "conflicts": conflicts,
        "budget": {
            "max_chars": max_chars,
            "max_frames": max_frames,
            "max_frames_per_segment": max_frames_per_segment,
            "frame_window_ms": frame_window_ms,
            "max_claims_per_segment": max_claims_per_segment,
            "max_units_per_segment": max_units_per_segment,
            "unit_window_ms": unit_window_ms,
        },
        "truncated": False,
        "truncation": {"units_dropped": 0, "frames_dropped": 0, "notes": []},
        "pack_hash": "",
    }

    # Explicit budget: drop unit context first, then unreferenced frame
    # candidates; keep claims/evidence intact.
    while _pack_size(pack) > max_chars and _trim_units(pack):
        pack["truncated"] = True
        pack["truncation"]["units_dropped"] += 1
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
    return pack


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a v3 EvidencePack from v2 substrate JSON.")
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--outline", type=Path, required=True)
    parser.add_argument("--knowledge", type=Path)
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--skill-id", default="reader_first_explainer")
    parser.add_argument("--view-types", nargs="*", default=None)
    parser.add_argument("--max-chars", type=int, default=90_000)
    parser.add_argument("--max-frames", type=int, default=60)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)

    snapshot = _read_json(args.snapshot)
    outline = _read_json(args.outline)
    request = _read_json(args.request)
    knowledge = _read_json(args.knowledge) if args.knowledge else None
    pack = build_evidence_pack(
        snapshot=snapshot,
        outline=outline,
        knowledge=knowledge,
        request=request,
        skill_id=args.skill_id,
        view_types=args.view_types,
        max_chars=args.max_chars,
        max_frames=args.max_frames,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(pack, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "out": str(args.out),
                "pack_id": pack["pack_id"],
                "pack_chars": pack["pack_chars"],
                "segments": len(pack["segments"]),
                "units": len(pack["units"]),
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
