"""Deterministic edited-transcript renderer for the Writer.

The Writer should read a linear, de-duplicated, high-signal text, not a JSON
evidence view.  This module projects the full pack (or its claim selection)
into one text plus an audit-only source map.

Two render branches, one output shape:

- ``full``: every passage in time order, grouped by segment.
- ``anchored``: only the sentences that claims point to, de-duplicated and in
  time order; an optional neighbour window (``neighbor``, default 0) can keep
  pronouns and causal links readable.  ``status="bounded"`` anchors keep an
  inline ``（限制：scope）`` marker.

The rendered text carries no passage/sentence/claim IDs and no timecodes.  The
source map carries them for audit and post-hoc binding.  Nothing is invented
and nothing is hard-truncated; over-budget is recorded only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

from ..core.tokens import estimate_text_tokens

SCHEMA = "edited-transcript-v1"
SOURCE_SCHEMA = "edited-transcript-source-map-v1"
MODES = ("full", "anchored")
BOUNDARY_MARKER = "（限制）"


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _sha_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _char_bigrams(text: str) -> set[str]:
    value = re.sub(r"[^\w一-鿿]+", "", text or "").lower()
    return {value[i : i + 2] for i in range(len(value) - 1)}


def _best_boundary_sentence(
    claim_text: str,
    sentence_ids: list[str],
    sentences_by_id: dict[str, dict[str, Any]],
    pack_sentences_by_id: dict[str, dict[str, Any]],
) -> str | None:
    """Pick the sentence that best carries the claim's limitation wording."""
    if not sentence_ids:
        return None
    claim_grams = _char_bigrams(claim_text)
    if not claim_grams:
        return sentence_ids[0]
    best_id = sentence_ids[0]
    best_score = -1.0
    for sentence_id in sentence_ids:
        sentence = sentences_by_id.get(sentence_id) or pack_sentences_by_id.get(
            sentence_id
        )
        if sentence is None:
            continue
        sentence_grams = _char_bigrams(sentence.get("text", ""))
        if not sentence_grams:
            continue
        score = len(claim_grams & sentence_grams) / len(claim_grams)
        if score > best_score:
            best_score = score
            best_id = sentence_id
    return best_id


def _boundary_map(
    segment: dict[str, Any],
    claims_by_id: dict[str, dict[str, Any]],
    evidence_by_id: dict[str, dict[str, Any]],
    sentences_by_id: dict[str, dict[str, Any]],
    pack_sentences_by_id: dict[str, dict[str, Any]],
) -> tuple[set[str], dict[str, str]]:
    boundary_ids: set[str] = set()
    boundary_scopes: dict[str, str] = {}
    for claim_id in segment.get("claim_ids", []):
        claim = claims_by_id.get(claim_id)
        if claim is None or claim.get("status") != "bounded":
            continue
        sentence_ids: list[str] = []
        for evidence_id in claim.get("evidence_ids", []):
            evidence = evidence_by_id.get(evidence_id)
            if evidence is None:
                continue
            for sentence_id in evidence.get("sentence_ids", []):
                if sentence_id not in sentence_ids:
                    sentence_ids.append(sentence_id)
        sentence_id = _best_boundary_sentence(
            claim.get("text", ""),
            sentence_ids,
            sentences_by_id,
            pack_sentences_by_id,
        )
        if not sentence_id:
            continue
        boundary_ids.add(sentence_id)
        scope = (claim.get("scope") or "").strip()
        if scope and sentence_id not in boundary_scopes:
            boundary_scopes[sentence_id] = scope
    return boundary_ids, boundary_scopes


def _frames_for_segment(
    segment: dict[str, Any], frames_by_id: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    frames: list[dict[str, Any]] = []
    for frame_id in segment.get("frame_ids", []):
        frame = frames_by_id.get(frame_id)
        if frame is None:
            continue
        caption = (frame.get("caption") or "").strip()
        if not caption:
            continue
        frames.append({"frame_id": frame_id, "caption": caption})
    return frames


def _group_passages(
    passages: list[dict[str, Any]],
) -> list[tuple[str, list[dict[str, Any]]]]:
    groups: list[tuple[str, list[dict[str, Any]]]] = []
    for passage in passages:
        segment_id = passage.get("segment_id") or ""
        if not groups or groups[-1][0] != segment_id:
            groups.append((segment_id, []))
        groups[-1][1].append(passage)
    return groups


def _segment_order(
    pack: dict[str, Any], grouped: list[tuple[str, list[dict[str, Any]]]]
) -> list[tuple[str, list[dict[str, Any]]]]:
    """Use pack segment order first, then any passages not in the pack."""
    by_segment = {segment_id: items for segment_id, items in grouped}
    ordered: list[tuple[str, list[dict[str, Any]]]] = []
    for segment in pack.get("segments", []):
        segment_id = segment.get("segment_id") or ""
        if segment_id in by_segment:
            ordered.append((segment_id, by_segment.pop(segment_id)))
    for segment_id, items in grouped:
        if segment_id in by_segment:
            ordered.append((segment_id, by_segment.pop(segment_id)))
    return ordered


def _label(
    segment: dict[str, Any] | None, fallback_index: int
) -> str:
    if segment is not None:
        label = (segment.get("label") or "").strip()
        if label:
            return label
    return f"第{fallback_index}段"


def _marked_text(
    sentence: dict[str, Any],
    boundary_ids: set[str],
    boundary_scopes: dict[str, str],
) -> str:
    text = sentence.get("text", "")
    sentence_id = sentence.get("sentence_id", "")
    if sentence_id in boundary_ids:
        scope = boundary_scopes.get(sentence_id, "")
        text = (
            f"（限制：{scope}）" if scope else BOUNDARY_MARKER
        ) + text
    return text


def build_full_blocks(
    pack: dict[str, Any],
    passages: list[dict[str, Any]],
    sentences: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Every passage in order, grouped by segment, with non-empty frames.

    When the full sentence list is supplied, boundaries are marked in place;
    otherwise the passage text is used verbatim.
    """
    frames_by_id = {f["frame_id"]: f for f in pack.get("frames", [])}
    segments_by_id = {
        s.get("segment_id", ""): s for s in pack.get("segments", [])
    }
    claims_by_id = {c["claim_id"]: c for c in pack.get("claims", [])}
    evidence_by_id = {e["evidence_id"]: e for e in pack.get("evidence", [])}
    sentences_by_id = {s["sentence_id"]: s for s in (sentences or [])}
    pack_sentences_by_id = {
        s["sentence_id"]: s for s in pack.get("sentences", [])
    }
    blocks: list[dict[str, Any]] = []
    grouped = _group_passages(passages)
    for index, (segment_id, items) in enumerate(_segment_order(pack, grouped), start=1):
        segment = segments_by_id.get(segment_id)
        sentence_ids: list[str] = []
        passage_ids: list[str] = []
        for passage in items:
            passage_ids.append(passage.get("passage_id", ""))
            for sentence_id in passage.get("sentence_ids", []):
                if sentence_id not in sentence_ids:
                    sentence_ids.append(sentence_id)
        boundary_ids: set[str] = set()
        boundary_scopes: dict[str, str] = {}
        if segment is not None:
            boundary_ids, boundary_scopes = _boundary_map(
                segment,
                claims_by_id,
                evidence_by_id,
                sentences_by_id,
                pack_sentences_by_id,
            )
        texts: list[str] = []
        for passage in items:
            passage_sentence_ids = list(passage.get("sentence_ids", []))
            complete = bool(passage_sentence_ids) and all(
                sentence_id in sentences_by_id
                or sentence_id in pack_sentences_by_id
                for sentence_id in passage_sentence_ids
            )
            if not complete:
                texts.append(passage.get("text", ""))
                continue
            pieces: list[str] = []
            for sentence_id in passage_sentence_ids:
                sentence = sentences_by_id.get(
                    sentence_id
                ) or pack_sentences_by_id.get(sentence_id)
                if sentence is None:
                    continue
                pieces.append(
                    _marked_text(sentence, boundary_ids, boundary_scopes)
                )
            texts.append("".join(pieces))
        frames = _frames_for_segment(segment, frames_by_id) if segment else []
        blocks.append(
            {
                "segment_id": segment_id,
                "label": _label(segment, index),
                "content": "".join(texts),
                "sentence_ids": sentence_ids,
                "passage_ids": passage_ids,
                "claim_ids": list(segment.get("claim_ids", [])) if segment else [],
                "boundary_sentence_ids": [
                    sid for sid in sentence_ids if sid in boundary_ids
                ],
                "boundary_scopes": {
                    sid: boundary_scopes[sid]
                    for sid in sentence_ids
                    if sid in boundary_scopes
                },
                "frames": frames,
            }
        )
    return blocks


def _sentence_order(
    sentences: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    by_segment: dict[str, list[dict[str, Any]]] = {}
    for sentence in sentences:
        by_segment.setdefault(sentence.get("segment_id", ""), []).append(sentence)
    return by_segment


def build_anchored_blocks(
    pack: dict[str, Any],
    sentences: list[dict[str, Any]],
    passages: list[dict[str, Any]],
    *,
    neighbor: int = 0,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Claim-anchored sentences with a small neighbour window and boundaries."""
    if neighbor < 0:
        raise ValueError("neighbor 必须 >= 0")
    frames_by_id = {f["frame_id"]: f for f in pack.get("frames", [])}
    claims_by_id = {c["claim_id"]: c for c in pack.get("claims", [])}
    evidence_by_id = {e["evidence_id"]: e for e in pack.get("evidence", [])}
    sentences_by_id = {s["sentence_id"]: s for s in sentences}
    pack_sentences_by_id = {
        s["sentence_id"]: s for s in pack.get("sentences", [])
    }
    sentences_by_segment = _sentence_order(sentences)
    passage_by_sentence: dict[str, str] = {}
    for passage in passages:
        for sentence_id in passage.get("sentence_ids", []):
            passage_by_sentence[sentence_id] = passage.get("passage_id", "")

    blocks: list[dict[str, Any]] = []
    seen_sentence_ids: set[str] = set()
    skipped_segments: list[str] = []
    skipped_anchors: list[str] = []
    for index, segment in enumerate(pack.get("segments", []), start=1):
        segment_id = segment.get("segment_id", "")
        audio_sentences = sentences_by_segment.get(segment_id, [])
        if not audio_sentences:
            audio_sentences = [
                pack_sentences_by_id[sid]
                for sid in segment.get("sentence_ids", [])
                if sid in pack_sentences_by_id
            ]
        order = {s["sentence_id"]: i for i, s in enumerate(audio_sentences)}

        anchor_ids: list[str] = []
        for claim_id in segment.get("claim_ids", []):
            claim = claims_by_id.get(claim_id)
            if claim is None:
                continue
            for evidence_id in claim.get("evidence_ids", []):
                evidence = evidence_by_id.get(evidence_id)
                if evidence is None:
                    continue
                for sentence_id in evidence.get("sentence_ids", []):
                    if sentence_id not in anchor_ids:
                        anchor_ids.append(sentence_id)
        boundary_ids, boundary_scopes = _boundary_map(
            segment,
            claims_by_id,
            evidence_by_id,
            sentences_by_id,
            pack_sentences_by_id,
        )

        selected: set[str] = set()
        for sentence_id in anchor_ids:
            if sentence_id not in order:
                skipped_anchors.append(sentence_id)
                continue
            position = order[sentence_id]
            start = max(0, position - neighbor)
            end = min(len(audio_sentences), position + neighbor + 1)
            for item in audio_sentences[start:end]:
                selected.add(item["sentence_id"])
        selected_ids = [
            sentence["sentence_id"]
            for sentence in audio_sentences
            if sentence["sentence_id"] in selected
            and sentence["sentence_id"] not in seen_sentence_ids
        ]
        if not selected_ids:
            skipped_segments.append(segment_id)
            continue
        seen_sentence_ids.update(selected_ids)

        parts: list[str] = []
        for sentence_id in selected_ids:
            sentence = sentences_by_id.get(sentence_id) or pack_sentences_by_id.get(
                sentence_id
            )
            if sentence is None:
                continue
            parts.append(
                _marked_text(sentence, boundary_ids, boundary_scopes)
            )
        content = "".join(parts)
        if not content:
            skipped_segments.append(segment_id)
            continue
        passage_ids: list[str] = []
        for sentence_id in selected_ids:
            passage_id = passage_by_sentence.get(sentence_id, "")
            if passage_id and passage_id not in passage_ids:
                passage_ids.append(passage_id)
        blocks.append(
            {
                "segment_id": segment_id,
                "label": _label(segment, index),
                "content": content,
                "sentence_ids": selected_ids,
                "passage_ids": passage_ids,
                "claim_ids": list(segment.get("claim_ids", [])),
                "boundary_sentence_ids": [
                    sid for sid in selected_ids if sid in boundary_ids
                ],
                "boundary_scopes": {
                    sid: boundary_scopes[sid]
                    for sid in selected_ids
                    if sid in boundary_scopes
                },
                "frames": _frames_for_segment(segment, frames_by_id),
            }
        )
    stats = {
        "skipped_segments": skipped_segments,
        "skipped_anchor_sentences": sorted(set(skipped_anchors)),
    }
    return blocks, stats


def _frame_line(frames: list[dict[str, Any]]) -> str:
    if not frames:
        return ""
    parts = [
        f"画面{index}：{frame['caption'].replace(chr(10), ' / ')}"
        for index, frame in enumerate(frames, start=1)
    ]
    return "（" + "；".join(parts) + "）"


def render_blocks(
    blocks: list[dict[str, Any]],
) -> tuple[str, list[dict[str, Any]]]:
    """Render blocks to text and return a source map with exact offsets."""
    block_texts: list[str] = []
    for block in blocks:
        lines: list[str] = []
        if block["label"]:
            lines.append(f"## {block['label']}")
        if block["content"]:
            lines.append(block["content"])
        frame_line = _frame_line(block["frames"])
        if frame_line:
            lines.append(frame_line)
        block_texts.append("\n".join(lines))

    rendered = "\n\n".join(block_texts)
    source_blocks: list[dict[str, Any]] = []
    cursor = 0
    for index, (block, block_text) in enumerate(zip(blocks, block_texts)):
        start = cursor
        end = start + len(block_text)
        source_blocks.append(
            {
                "block_index": index,
                "segment_id": block["segment_id"],
                "label": block["label"],
                "text_start": start,
                "text_end": end,
                "sentence_ids": block["sentence_ids"],
                "passage_ids": block["passage_ids"],
                "claim_ids": block["claim_ids"],
                "boundary_sentence_ids": block["boundary_sentence_ids"],
                "boundary_scopes": block.get("boundary_scopes", {}),
                "frames": [
                    {
                        "frame_index": frame_index,
                        "frame_id": frame["frame_id"],
                        "caption": frame["caption"],
                    }
                    for frame_index, frame in enumerate(block["frames"], start=1)
                ],
            }
        )
        cursor = end + 2
    return rendered, source_blocks


def _candidate(
    blocks: list[dict[str, Any]],
) -> dict[str, Any]:
    text, source_blocks = render_blocks(blocks)
    return {
        "blocks": blocks,
        "rendered": text,
        "source_blocks": source_blocks,
        "chars": len(text),
        "est_tokens": estimate_text_tokens(text),
    }


def build_edited_transcript(
    pack: dict[str, Any],
    passages: list[dict[str, Any]],
    sentences: list[dict[str, Any]] | None = None,
    *,
    mode: str = "auto",
    neighbor: int = 0,
    auto_ratio: float = 1.5,
    budget_chars: int | None = None,
) -> dict[str, Any]:
    """Build full/anchored candidates, choose one, and return text + audit map."""
    if mode not in ("auto", *MODES):
        raise ValueError(f"未知 mode: {mode}")
    if auto_ratio <= 0:
        raise ValueError("auto_ratio 必须 > 0")
    if mode in ("auto", "anchored") and sentences is None:
        raise ValueError("auto/anchored 需要 sentences（完整转写句表）")

    full = _candidate(build_full_blocks(pack, passages, sentences))
    full["mode"] = "full"
    anchored_blocks, anchored_stats = build_anchored_blocks(
        pack,
        sentences or [],
        passages,
        neighbor=neighbor,
    )
    anchored = _candidate(anchored_blocks)
    anchored["mode"] = "anchored"
    candidates = {"full": full, "anchored": anchored}

    if mode == "auto":
        if not full["rendered"]:
            chosen, reason = "anchored", "full_empty"
        elif not anchored["rendered"]:
            chosen, reason = "full", "anchored_empty"
        elif full["chars"] <= anchored["chars"] * auto_ratio:
            chosen, reason = "full", "full_within_ratio"
        else:
            chosen, reason = "anchored", "anchored_saves_more_than_ratio"
    else:
        chosen, reason = mode, "explicit"

    chosen_candidate = candidates[chosen]
    over_budget = (
        budget_chars is not None and chosen_candidate["chars"] > budget_chars
    )
    decision = {
        "mode": chosen,
        "reason": reason,
        "auto_ratio": auto_ratio,
        "neighbor": neighbor,
        "budget_chars": budget_chars,
        "over_budget": over_budget,
        "budget_excess_chars": (
            max(0, chosen_candidate["chars"] - budget_chars)
            if budget_chars is not None
            else 0
        ),
        "candidates": {
            name: {
                "chars": item["chars"],
                "est_tokens": item["est_tokens"],
                "blocks": len(item["blocks"]),
                "sentences": sum(
                    len(block["sentence_ids"]) for block in item["blocks"]
                ),
                "frames": sum(len(block["frames"]) for block in item["blocks"]),
                "boundary_sentences": sum(
                    len(block["boundary_sentence_ids"])
                    for block in item["blocks"]
                ),
            }
            for name, item in candidates.items()
        },
        "segments_total": len(pack.get("segments", [])),
        "skipped_segments": anchored_stats["skipped_segments"],
        "skipped_anchor_sentences": anchored_stats[
            "skipped_anchor_sentences"
        ],
    }
    source_map = {
        "schema": SOURCE_SCHEMA,
        "mode": chosen,
        "text_sha256": _sha_text(chosen_candidate["rendered"]),
        "text_chars": chosen_candidate["chars"],
        "text_est_tokens": chosen_candidate["est_tokens"],
        "blocks": chosen_candidate["source_blocks"],
    }
    return {
        "schema": SCHEMA,
        "mode": chosen,
        "text": chosen_candidate["rendered"],
        "source_map": source_map,
        "decision": decision,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Render a full pack into one linear edited transcript plus an "
            "audit-only source map.  No model call, no hard truncation."
        )
    )
    parser.add_argument("--pack", type=Path, required=True)
    parser.add_argument("--passages", type=Path, required=True)
    parser.add_argument(
        "--sentences",
        type=Path,
        help="完整转写句表；auto/anchored 需要",
    )
    parser.add_argument("--mode", choices=["auto", *MODES], default="auto")
    parser.add_argument("--neighbor", type=int, default=0)
    parser.add_argument("--auto-ratio", type=float, default=1.5)
    parser.add_argument("--budget-chars", type=int)
    parser.add_argument("--out-text", type=Path, required=True)
    parser.add_argument("--out-source-map", type=Path, required=True)
    parser.add_argument("--out-manifest", type=Path, required=True)
    args = parser.parse_args(argv)

    if args.mode in ("auto", "anchored") and args.sentences is None:
        parser.error("--mode auto/anchored 需要 --sentences")

    pack = _read_json(args.pack)
    passages = _read_json(args.passages).get("passages", [])
    sentences = (
        _read_json(args.sentences).get("sentences", [])
        if args.sentences
        else []
    )
    try:
        result = build_edited_transcript(
            pack,
            passages,
            sentences,
            mode=args.mode,
            neighbor=args.neighbor,
            auto_ratio=args.auto_ratio,
            budget_chars=args.budget_chars,
        )
    except ValueError as exc:
        print(f"invalid input: {exc}", file=sys.stderr)
        return 4

    for path in (args.out_text, args.out_source_map, args.out_manifest):
        path.parent.mkdir(parents=True, exist_ok=True)
    args.out_text.write_text(result["text"], encoding="utf-8")
    args.out_source_map.write_text(
        json.dumps(result["source_map"], ensure_ascii=False, indent=1),
        encoding="utf-8",
    )
    args.out_manifest.write_text(
        json.dumps(result["decision"], ensure_ascii=False, indent=1),
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "status": "complete",
                "mode": result["mode"],
                "decision": result["decision"],
                "out_text": str(args.out_text),
                "out_source_map": str(args.out_source_map),
            },
            ensure_ascii=False,
            indent=1,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
