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
from .provenance import build_provenance
from .trace import TraceRecorder
from .writer_view import build_writer_bundle, build_writer_view


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _pack_size(pack: dict[str, Any]) -> int:
    return len(json.dumps(pack, ensure_ascii=False, indent=1))


def _minimal_contiguous_slice(
    quote: str,
    sentence_ids: list[str],
    sentence_by_id: dict[str, dict[str, Any]],
) -> list[str] | None:
    """Return the smallest contiguous sentence slice whose text contains quote."""
    ids = [sid for sid in sentence_ids if sid in sentence_by_id]
    if not quote or not ids:
        return None
    for length in range(1, len(ids) + 1):
        for start in range(0, len(ids) - length + 1):
            text = "".join(
                sentence_by_id[sid]["text"] for sid in ids[start : start + length]
            )
            if quote in text:
                return ids[start : start + length]
    return None


def _claim_anchor_ids(
    claim: dict[str, Any],
    *,
    sentence_by_id: dict[str, dict[str, Any]],
    passage_by_id: dict[str, dict[str, Any]],
    sentences_by_segment: dict[str, list[str]],
) -> tuple[list[str], str]:
    """Find the sentence(s) that contain the claim quote.

    Preference order: claim sentence_ids -> passage sentence_ids -> segment
    sentence_ids -> claim sentence_ids fallback.  The returned source is
    recorded in the pack so a quote that does not sit in the model's listed
    sentences is visible rather than silently accepted.
    """
    quote = claim.get("quote", "")
    claim_sentence_ids = claim.get("sentence_ids", [])
    anchor = _minimal_contiguous_slice(quote, claim_sentence_ids, sentence_by_id)
    if anchor:
        return anchor, "claim_sentences"
    passage = passage_by_id.get(claim.get("passage_id", ""))
    if passage:
        anchor = _minimal_contiguous_slice(
            quote, passage.get("sentence_ids", []), sentence_by_id
        )
        if anchor:
            return anchor, "passage_sentences"
    anchor = _minimal_contiguous_slice(
        quote, sentences_by_segment.get(claim.get("segment_id", ""), []), sentence_by_id
    )
    if anchor:
        return anchor, "segment_sentences"
    fallback = [sid for sid in claim_sentence_ids if sid in sentence_by_id]
    if fallback:
        return fallback, "fallback_claim_sentences"
    return [], "missing"


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
    max_claims_per_segment: int | None = None,
    max_sentences_per_segment: int | None = None,
    context_window: int = 2,
    max_frames_per_segment: int = 2,
    max_frames: int = 24,
    frame_window_ms: int = 12_000,
    max_frame_caption_chars: int = 160,
    max_chars: int | None = 60_000,
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
    passage_order = {p["passage_id"]: i for i, p in enumerate(passages)}
    sentence_order = {s["sentence_id"]: i for i, s in enumerate(sentences)}
    segment_index = {segment_id: i for i, segment_id in enumerate(segment_order)}

    # Segment labels: outline first (it is always tied to the temporal
    # segmentation), contract only as fallback.  Empty labels are reported,
    # not silently rendered as "".
    outline_labels = {
        s["segment_id"]: (s.get("label") or "").strip()
        for s in (outline_doc or {}).get("segments", [])
    }
    contract_labels = {
        s["segment_id"]: (s.get("label") or "").strip()
        for s in (contract or {}).get("segments", [])
    }
    segment_label: dict[str, str] = {}
    label_sources: dict[str, str] = {}
    label_warnings: list[str] = []
    for segment_id in segment_order:
        outline_label = outline_labels.get(segment_id, "")
        contract_label = contract_labels.get(segment_id, "")
        if outline_label:
            label = outline_label
            source = "outline"
        elif contract_label:
            label = contract_label
            source = "contract"
        else:
            label = ""
            source = "missing"
            label_warnings.append(segment_id)
        segment_label[segment_id] = label
        label_sources[segment_id] = source
    label_source_counts: dict[str, int] = {}
    for source in label_sources.values():
        label_source_counts[source] = label_source_counts.get(source, 0) + 1

    def claim_sort_key(claim: dict[str, Any]) -> tuple[int, int, int, int, str]:
        positions = [
            sentence_order[sid]
            for sid in claim.get("sentence_ids", [])
            if sid in sentence_order
        ]
        sentence_position = min(positions) if positions else len(sentences)
        return (
            segment_index.get(claim["segment_id"], len(segment_order)),
            passage_order.get(claim["passage_id"], len(passages)),
            sentence_position,
            int(claim.get("t_start_ms", 0)),
            claim["claim_id"],
        )

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
        if max_claims_per_segment is None:
            # No hard cap: cover every passage, then keep every remaining
            # claim.  Long/complex videos are handled by writer-view
            # partitioning, not by silently dropping claims here.
            for passage_id in passage_rank:
                best = sorted(by_passage[passage_id], key=score, reverse=True)[0]
                chosen.append(best)
                chosen_ids.add(best["claim_id"])
            for claim in sorted(items, key=score, reverse=True):
                if claim["claim_id"] not in chosen_ids:
                    chosen.append(claim)
                    chosen_ids.add(claim["claim_id"])
        else:
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
            {c["passage_id"] for c in chosen},
            key=lambda pid: passage_order.get(pid, len(passages)),
        )
    for segment_id in selected:
        selected[segment_id] = sorted(selected[segment_id], key=claim_sort_key)

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
    claims_out.sort(
        key=lambda c: claim_sort_key(selected_claim_by_id[c["claim_id"]])
    )

    all_passage_ids = {p["passage_id"] for p in passages}
    extracted_passage_ids = {c["passage_id"] for c in claims}
    selected_passage_ids = {c["passage_id"] for c in claims_out}
    skipped_passages: list[dict[str, Any]] = []
    for row in claims_doc.get("skipped_passages", []):
        if not isinstance(row, dict):
            continue
        passage = passage_by_id.get(row.get("passage_id"))
        if passage is None:
            continue
        skipped_passages.append(
            {
                "segment_id": passage["segment_id"],
                "passage_id": passage["passage_id"],
                "reason": (row.get("reason") or "").strip(),
            }
        )
    skipped_ids = {row["passage_id"] for row in skipped_passages}
    skip_reason_counts: dict[str, int] = {}
    for row in skipped_passages:
        reason = row["reason"]
        skip_reason_counts[reason] = skip_reason_counts.get(reason, 0) + 1
    unreported_passages = [
        {"segment_id": p["segment_id"], "passage_id": p["passage_id"]}
        for p in passages
        if p["passage_id"] not in extracted_passage_ids
        and p["passage_id"] not in skipped_ids
    ]
    coverage_report = {
        "passages_total": len(passages),
        "passages_with_extracted_claim": len(extracted_passage_ids & all_passage_ids),
        "passages_with_selected_claim": len(selected_passage_ids & all_passage_ids),
        "passages_skipped": len(skipped_ids),
        "skipped_passages": skipped_passages,
        "skip_reason_counts": skip_reason_counts,
        "passages_without_extracted_claim": [
            {"segment_id": p["segment_id"], "passage_id": p["passage_id"]}
            for p in passages
            if p["passage_id"] not in extracted_passage_ids
        ],
        "unreported_passages": unreported_passages,
        "passages_dropped_by_selection": [
            {"segment_id": p["segment_id"], "passage_id": p["passage_id"]}
            for p in passages
            if p["passage_id"] in extracted_passage_ids
            and p["passage_id"] not in selected_passage_ids
        ],
        "segments_with_zero_selected_claims": [
            segment_id
            for segment_id in segment_order
            if not selected.get(segment_id)
        ],
        "segments_with_zero_extracted_claims": [
            segment_id
            for segment_id in segment_order
            if not claims_by_segment.get(segment_id)
        ],
    }

    # Sentence context: every selected claim keeps at least one sentence that
    # contains its quote; neighbours are added only within the per-segment
    # budget.  Missing anchors are reported, never silently dropped.
    sentences_by_segment: dict[str, list[str]] = {}
    for sentence in sentences:
        sentences_by_segment.setdefault(sentence["segment_id"], []).append(
            sentence["sentence_id"]
        )
    claim_anchor: dict[str, list[str]] = {}
    claim_anchor_source: dict[str, str] = {}
    for segment_id in segment_order:
        for claim in selected.get(segment_id, []):
            anchor, source = _claim_anchor_ids(
                claim,
                sentence_by_id=sentence_by_id,
                passage_by_id=passage_by_id,
                sentences_by_segment=sentences_by_segment,
            )
            claim_anchor[claim["claim_id"]] = anchor
            claim_anchor_source[claim["claim_id"]] = source

    context_report: dict[str, Any] = {
        "window": context_window,
        "claims_total": 0,
        "claims_with_context": 0,
        "claims_without_context": 0,
        "anchor_sentences": 0,
        "neighbor_sentences": 0,
        "context_sentences": 0,
        "over_cap_segments": [],
        "missing_context_claims": [],
        "quote_not_in_claim_sentences": [],
        "anchor_source_counts": {},
    }
    segment_sentence_ids: dict[str, list[str]] = {}
    for segment_id in segment_order:
        claims_in_segment = selected.get(segment_id, [])
        anchor_ids: set[str] = set()
        for claim in claims_in_segment:
            anchor = claim_anchor.get(claim["claim_id"], [])
            source = claim_anchor_source.get(claim["claim_id"], "missing")
            context_report["anchor_source_counts"][source] = (
                context_report["anchor_source_counts"].get(source, 0) + 1
            )
            if source != "claim_sentences":
                context_report["quote_not_in_claim_sentences"].append(
                    {"claim_id": claim["claim_id"], "source": source}
                )
            if anchor:
                anchor_ids.update(anchor)
            else:
                context_report["missing_context_claims"].append(
                    {"claim_id": claim["claim_id"], "reason": source}
                )

        chosen: set[str] = set(anchor_ids)
        # Nearest neighbours first; anchors are never displaced by the cap.
        neighbours: dict[str, tuple[int, int]] = {}
        for sentence_id in anchor_ids:
            index = sentence_order.get(sentence_id)
            if index is None:
                continue
            for distance in range(1, context_window + 1):
                for position in (index - distance, index + distance):
                    if not 0 <= position < len(sentences):
                        continue
                    candidate = sentences[position]
                    if candidate["segment_id"] != segment_id:
                        continue
                    candidate_id = candidate["sentence_id"]
                    if candidate_id in chosen:
                        continue
                    rank = (distance, position)
                    current = neighbours.get(candidate_id)
                    if current is None or rank < current:
                        neighbours[candidate_id] = rank
        ordered_neighbours = sorted(neighbours.items(), key=lambda item: item[1])
        if max_sentences_per_segment is None:
            # No hard context cap; the writer view may partition later.
            for candidate_id, _ in ordered_neighbours:
                chosen.add(candidate_id)
        else:
            for candidate_id, _ in ordered_neighbours:
                if len(chosen) >= max_sentences_per_segment:
                    break
                chosen.add(candidate_id)
            if len(anchor_ids) > max_sentences_per_segment:
                context_report["over_cap_segments"].append(
                    {
                        "segment_id": segment_id,
                        "anchor_sentences": len(anchor_ids),
                        "cap": max_sentences_per_segment,
                    }
                )
        ordered = sorted(chosen, key=lambda sid: sentence_order.get(sid, 0))
        segment_sentence_ids[segment_id] = ordered
        context_report["claims_total"] += len(claims_in_segment)
        context_report["claims_with_context"] += sum(
            1 for claim in claims_in_segment if claim_anchor.get(claim["claim_id"])
        )
        context_report["anchor_sentences"] += len(anchor_ids)
        context_report["neighbor_sentences"] += len(chosen) - len(anchor_ids)
        context_report["context_sentences"] += len(chosen)
    context_report["claims_without_context"] = (
        context_report["claims_total"] - context_report["claims_with_context"]
    )

    # S1-2: evidence timecode is the union of the anchor sentence times, not
    # the enclosing passage.  If no anchor exists, keep the claim/passage
    # fallback and mark it explicitly.
    context_report["quote_not_in_sentence_text"] = []
    context_report["timecode_source_counts"] = {
        "anchor_sentences": 0,
        "claim_passage_fallback": 0,
    }
    claim_time_range: dict[str, tuple[int, int]] = {}
    for evidence in evidence_out:
        claim_id = evidence["claim_ids"][0]
        anchor = claim_anchor.get(claim_id, [])
        if anchor:
            evidence["sentence_ids"] = list(anchor)
            evidence["t_start_ms"] = min(
                sentence_by_id[sid]["t_start_ms"] for sid in anchor
            )
            evidence["t_end_ms"] = max(
                sentence_by_id[sid]["t_end_ms"] for sid in anchor
            )
            anchor_text = "".join(sentence_by_id[sid]["text"] for sid in anchor)
            context_report["timecode_source_counts"]["anchor_sentences"] += 1
            # Keep the common case compact: anchor_sentences/true are the
            # defaults; only anomalies are written per evidence.
            if evidence["quote"] not in anchor_text:
                evidence["timecode_source"] = "anchor_sentences"
                evidence["quote_in_sentence_text"] = False
                context_report["quote_not_in_sentence_text"].append(
                    evidence["evidence_id"]
                )
        else:
            claim = selected_claim_by_id[claim_id]
            evidence["sentence_ids"] = list(claim.get("sentence_ids", []))
            evidence["timecode_source"] = "claim_passage_fallback"
            evidence["quote_in_sentence_text"] = False
            context_report["timecode_source_counts"]["claim_passage_fallback"] += 1
            context_report["quote_not_in_sentence_text"].append(
                evidence["evidence_id"]
            )
        claim_time_range[claim_id] = (
            evidence["t_start_ms"],
            evidence["t_end_ms"],
        )

    provenance = build_provenance(
        claims_out=claims_out,
        selected_claim_by_id=selected_claim_by_id,
        sentence_by_id=sentence_by_id,
        snapshot_doc=snapshot_doc,
    )

    # Frames near selected claim times; cap per segment/global.
    all_frames = sorted(
        frames_index.get("frames", []),
        key=lambda f: (int(f.get("t_ms", 0)), f["frame_id"]),
    )
    used_frames: set[str] = set()
    segment_frame_ids: dict[str, list[str]] = {}
    per_segment_capped_candidates = 0
    for segment_id in segment_order:
        claim_times: list[int] = []
        for claim in selected.get(segment_id, []):
            claim_times.extend(
                claim_time_range.get(
                    claim["claim_id"], (claim["t_start_ms"], claim["t_end_ms"])
                )
            )
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
        per_segment_capped_candidates += max(
            0, len(candidates) - len(chosen_frames)
        )
        segment_frame_ids[segment_id] = chosen_frames

    frames_out = []
    captions_truncated = 0
    for frame in all_frames:
        if frame["frame_id"] not in used_frames:
            continue
        vlm_text = (frame.get("vlm_text") or "").strip()
        if len(vlm_text) > max_frame_caption_chars:
            captions_truncated += 1
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
    frame_selection = {
        "candidates_total": len(all_frames),
        "selected_total": len(frames_out),
        "per_segment_cap": max_frames_per_segment,
        "global_cap": max_frames,
        "per_segment_capped_candidates": per_segment_capped_candidates,
        "over_global_cap": len(frames_out) > max_frames,
        "captions_truncated": captions_truncated,
    }

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
            "segment_id": sentence_by_id[sid]["segment_id"],
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
            "context": context_report,
            "labels": {
                "sources": label_sources,
                "source_counts": label_source_counts,
                "warnings": label_warnings,
            },
            "coverage": coverage_report,
            "frame_selection": frame_selection,
            "max_frames_per_segment": max_frames_per_segment,
        },
        "segments": segments_out,
        "sentences": sentences_out,
        "claims": claims_out,
        "provenance": provenance,
        "evidence": sorted(evidence_out, key=lambda e: (e["t_start_ms"], e["evidence_id"])),
        "frames": frames_out,
        "gaps": gaps,
        "conflicts": conflicts,
        "budget": {
            "max_chars": max_chars,
            "max_frames": max_frames,
            "context_window": context_window,
            "frame_window_ms": frame_window_ms,
            "max_frame_caption_chars": max_frame_caption_chars,
        },
        "truncated": False,
        "truncation": {
            "sentences_dropped": 0,
            "dropped_sentence_ids": [],
            "context_sentences_before": context_report["context_sentences"],
            "context_sentences_after": context_report["context_sentences"],
            "frames_dropped": 0,
            "notes": [],
        },
        "pack_hash": "",
    }

    pack["truncation"]["context_sentences_after"] = len(pack["sentences"])
    if max_chars is not None and _pack_size(pack) > max_chars:
        pack["truncation"]["notes"].append("advisory_budget_exceeded")

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
    pack["over_budget"] = (
        max_chars is not None and pack["pack_chars"] > max_chars
    )
    pack["budget_excess_chars"] = (
        max(0, pack["pack_chars"] - max_chars) if max_chars is not None else 0
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
    parser.add_argument("--writer-out", type=Path)
    parser.add_argument("--max-chars", type=int, default=60_000)
    parser.add_argument("--writer-max-chars", type=int)
    parser.add_argument("--writer-bundle-dir", type=Path)
    parser.add_argument("--writer-part-max-chars", type=int)
    parser.add_argument("--context-window", type=int, default=2)
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
    build_kwargs = dict(
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
        context_window=args.context_window,
    )
    pack = build_pack(**build_kwargs, max_chars=args.max_chars)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    if args.video_id:
        pack["video_id"] = args.video_id
    args.out.write_text(json.dumps(pack, ensure_ascii=False, indent=1), encoding="utf-8")
    writer_view = None
    writer_view_path = None
    writer_view_chars = 0
    writer_view_compact_chars = 0
    writer_view_source_pack_id = None
    writer_view_parts = 0
    writer_view_oversize_parts = 0
    if args.writer_out:
        # The writer view is built from the full pack, which is never hard
        # truncated.  Audit metadata stays in the full pack; the view only
        # carries writing fields.
        writer_view_source_pack_id = pack.get("pack_id")
        writer_view = build_writer_view(
            pack, max_chars=args.writer_max_chars
        )
        writer_view_parts = (
            len(writer_view.get("parts", []))
            if "parts" in writer_view
            else 1
        )
        writer_view_oversize_parts = len(
            writer_view.get("manifest", {}).get("oversize_parts", [])
        )
        args.writer_out.parent.mkdir(parents=True, exist_ok=True)
        args.writer_out.write_text(
            json.dumps(writer_view, ensure_ascii=False, indent=1), encoding="utf-8"
        )
        writer_view_path = args.writer_out
        writer_view_chars = len(
            json.dumps(writer_view, ensure_ascii=False, indent=1)
        )
        writer_view_compact_chars = len(
            json.dumps(writer_view, ensure_ascii=False, separators=(",", ":"))
        )
    writer_bundle_dir = None
    writer_index_path = None
    writer_manifest_path = None
    writer_bundle_parts = 0
    writer_bundle_oversize_parts = 0
    writer_index_compact_chars = 0
    writer_parts_compact_chars = 0
    if args.writer_bundle_dir:
        writer_bundle_dir = args.writer_bundle_dir
        writer_bundle = build_writer_bundle(
            pack, max_chars_per_part=args.writer_part_max_chars
        )
        parts_dir = writer_bundle_dir / "writer_parts"
        writer_bundle_dir.mkdir(parents=True, exist_ok=True)
        parts_dir.mkdir(parents=True, exist_ok=True)
        writer_index_path = writer_bundle_dir / "writer_index.json"
        writer_manifest_path = writer_bundle_dir / "manifest.json"
        writer_index_path.write_text(
            json.dumps(writer_bundle["index"], ensure_ascii=False, indent=1),
            encoding="utf-8",
        )
        writer_manifest_path.write_text(
            json.dumps(writer_bundle["manifest"], ensure_ascii=False, indent=1),
            encoding="utf-8",
        )
        for part in writer_bundle["parts"]:
            (parts_dir / f"{part['part_id']}.json").write_text(
                json.dumps(part, ensure_ascii=False, indent=1),
                encoding="utf-8",
            )
        writer_bundle_parts = writer_bundle["manifest"]["parts_count"]
        writer_bundle_oversize_parts = len(
            writer_bundle["manifest"]["oversize_parts"]
        )
        writer_index_compact_chars = len(
            json.dumps(
                writer_bundle["index"],
                ensure_ascii=False,
                separators=(",", ":"),
            )
        )
        writer_parts_compact_chars = sum(
            len(
                json.dumps(part, ensure_ascii=False, separators=(",", ":"))
            )
            for part in writer_bundle["parts"]
        )
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
            outputs={
                "pack": args.out,
                "writer_view": writer_view_path,
                "writer_index": writer_index_path,
                "writer_manifest": writer_manifest_path,
            },
            counts={
                "claims_in": len(claims_doc.get("claims", [])),
                "claims_selected": len(pack["claims"]),
                "sentences_selected": len(pack["sentences"]),
                "frames_selected": len(pack["frames"]),
                "segments": len(pack["segments"]),
                "pack_chars": pack["pack_chars"],
                "pack_compact_chars": pack["pack_compact_chars"],
                "context_claims_total": pack["selection"]["context"]["claims_total"],
                "context_claims_with_context": pack["selection"]["context"]["claims_with_context"],
                "context_claims_without_context": pack["selection"]["context"]["claims_without_context"],
                "context_sentences": pack["selection"]["context"]["context_sentences"],
                "context_anchor_sentences": pack["selection"]["context"]["anchor_sentences"],
                "context_neighbor_sentences": pack["selection"]["context"]["neighbor_sentences"],
                "context_over_cap_segments": len(pack["selection"]["context"]["over_cap_segments"]),
                "context_missing_claims": len(pack["selection"]["context"]["missing_context_claims"]),
                "context_quote_not_in_sentence_text": len(pack["selection"]["context"]["quote_not_in_sentence_text"]),
                "context_timecode_sources": pack["selection"]["context"]["timecode_source_counts"],
                "label_source_counts": pack["selection"]["labels"]["source_counts"],
                "label_warnings": len(pack["selection"]["labels"]["warnings"]),
                "coverage_passages_total": pack["selection"]["coverage"]["passages_total"],
                "coverage_passages_skipped": pack["selection"]["coverage"]["passages_skipped"],
                "coverage_passages_unreported": len(pack["selection"]["coverage"]["unreported_passages"]),
                "coverage_passages_without_extracted_claim": len(pack["selection"]["coverage"]["passages_without_extracted_claim"]),
                "coverage_passages_dropped_by_selection": len(pack["selection"]["coverage"]["passages_dropped_by_selection"]),
                "coverage_segments_with_zero_selected_claims": len(pack["selection"]["coverage"]["segments_with_zero_selected_claims"]),
                "frame_candidates_total": pack["selection"]["frame_selection"]["candidates_total"],
                "frame_selected_total": pack["selection"]["frame_selection"]["selected_total"],
                "frame_captions_truncated": pack["selection"]["frame_selection"]["captions_truncated"],
                "frame_over_global_cap": pack["selection"]["frame_selection"]["over_global_cap"],
                "provenance_claims_with_source": pack["provenance"]["summary"]["claims_with_source"],
                "provenance_claims_without_source": pack["provenance"]["summary"]["claims_without_source"],
                "provenance_source_claim_count": pack["provenance"]["summary"]["source_claim_count"],
                "provenance_source_evidence_count": pack["provenance"]["summary"]["source_evidence_count"],
                "provenance_stance_counts": pack["provenance"]["summary"]["stance_counts"],
                "provenance_support_status_counts": pack["provenance"]["summary"]["support_status_counts"],
                "provenance_rights_scope_counts": pack["provenance"]["summary"]["rights_scope_counts"],
                "writer_view_chars": writer_view_chars,
                "writer_view_compact_chars": writer_view_compact_chars,
                "writer_view_parts": writer_view_parts,
                "writer_view_oversize_parts": writer_view_oversize_parts,
                "writer_view_source_pack_id": writer_view_source_pack_id,
                "writer_bundle_parts": writer_bundle_parts,
                "writer_bundle_oversize_parts": writer_bundle_oversize_parts,
                "writer_index_compact_chars": writer_index_compact_chars,
                "writer_parts_compact_chars": writer_parts_compact_chars,
                "over_budget": pack.get("over_budget", False),
                "budget_excess_chars": pack.get("budget_excess_chars", 0),
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
                "context": {
                    "claims_total": pack["selection"]["context"]["claims_total"],
                    "claims_with_context": pack["selection"]["context"]["claims_with_context"],
                    "claims_without_context": pack["selection"]["context"]["claims_without_context"],
                    "context_sentences": pack["selection"]["context"]["context_sentences"],
                    "anchor_sentences": pack["selection"]["context"]["anchor_sentences"],
                    "neighbor_sentences": pack["selection"]["context"]["neighbor_sentences"],
                    "over_cap_segments": len(pack["selection"]["context"]["over_cap_segments"]),
                    "missing_context_claims": len(pack["selection"]["context"]["missing_context_claims"]),
                    "quote_not_in_sentence_text": len(pack["selection"]["context"]["quote_not_in_sentence_text"]),
                    "timecode_sources": pack["selection"]["context"]["timecode_source_counts"],
                },
                "labels": {
                    "source_counts": pack["selection"]["labels"]["source_counts"],
                    "warnings": pack["selection"]["labels"]["warnings"],
                },
                "coverage": {
                    "passages_total": pack["selection"]["coverage"]["passages_total"],
                    "passages_skipped": pack["selection"]["coverage"]["passages_skipped"],
                    "passages_unreported": len(pack["selection"]["coverage"]["unreported_passages"]),
                    "passages_without_extracted_claim": len(pack["selection"]["coverage"]["passages_without_extracted_claim"]),
                    "passages_dropped_by_selection": len(pack["selection"]["coverage"]["passages_dropped_by_selection"]),
                    "segments_with_zero_selected_claims": len(pack["selection"]["coverage"]["segments_with_zero_selected_claims"]),
                },
                "provenance": pack["provenance"]["summary"],
                "writer_view": {
                    "path": str(args.writer_out) if args.writer_out else None,
                    "chars": writer_view_chars,
                    "compact_chars": writer_view_compact_chars,
                    "parts": writer_view_parts,
                    "oversize_parts": writer_view_oversize_parts,
                    "source_pack_id": writer_view_source_pack_id,
                },
                "writer_bundle": {
                    "dir": str(args.writer_bundle_dir)
                    if args.writer_bundle_dir
                    else None,
                    "parts": writer_bundle_parts,
                    "oversize_parts": writer_bundle_oversize_parts,
                    "index_compact_chars": writer_index_compact_chars,
                    "parts_compact_chars": writer_parts_compact_chars,
                },
                "over_budget": pack.get("over_budget", False),
                "budget_excess_chars": pack.get("budget_excess_chars", 0),
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
