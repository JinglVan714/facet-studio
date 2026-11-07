"""Deterministic ASR unit -> sentence -> passage prototype.

The substrate's ASR units are often word/phrase-sized (median ~11 chars).
This stage merges them into sentences by punctuation/silence/speaker, then
groups sentences into passages by segment and size.  No model is called.

The output is a context-preserving intermediate for claim extraction:
sentences and passages keep unit IDs and time ranges, so downstream claims can
quote exact text and stay auditable.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

from .trace import TraceRecorder

SENTENCE_END = ("。", "！", "？", "!", "?")
STRIP_WS = re.compile(r"\s+")


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8-sig").splitlines()
        if line.strip()
    ]


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _clean(text: str) -> str:
    return STRIP_WS.sub("", text or "")


def _segment_map(contract: dict[str, Any]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for segment in contract.get("segments", []):
        for unit_id in segment.get("unit_ids", []):
            mapping[unit_id] = segment.get("segment_id", "")
    return mapping


def merge_sentences(
    units: list[dict[str, Any]],
    unit_segment: dict[str, str],
    *,
    max_gap_ms: int = 2000,
    max_sentence_chars: int = 180,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    reasons: dict[str, int] = {}
    order = sorted(
        units,
        key=lambda u: (int(u.get("t", [0, 0])[0]), u.get("unit_id", "")),
    )
    sentences: list[dict[str, Any]] = []
    current: list[dict[str, Any]] = []
    current_text = ""
    current_reason = "start"

    def flush() -> None:
        nonlocal current, current_text, current_reason
        if not current:
            return
        segment_id = unit_segment.get(
            current[0]["unit_id"], current[0].get("sid", "unassigned")
        )
        index = sum(1 for s in sentences if s["segment_id"] == segment_id) + 1
        sentences.append(
            {
                "sentence_id": f"{segment_id}-s{index:03d}",
                "segment_id": segment_id,
                "unit_ids": [u["unit_id"] for u in current],
                "t_start_ms": int(current[0].get("t", [0, 0])[0]),
                "t_end_ms": int(current[-1].get("t", [0, 0])[1]),
                "text": current_text,
                "boundary_reason": current_reason,
                "filler_only": all(u.get("filler_only") for u in current),
            }
        )
        reasons[current_reason] = reasons.get(current_reason, 0) + 1
        current = []
        current_text = ""
        current_reason = "start"

    for unit in order:
        text = _clean(unit.get("raw", ""))
        if not text:
            continue
        start = int(unit.get("t", [0, 0])[0])
        previous_end = int(current[-1].get("t", [0, 0])[1]) if current else start
        segment_id = unit_segment.get(unit["unit_id"], unit.get("sid", "unassigned"))
        current_segment = (
            unit_segment.get(current[0]["unit_id"], current[0].get("sid", "unassigned"))
            if current
            else segment_id
        )
        if current and segment_id != current_segment:
            current_reason = "segment_change"
            flush()
        elif current and start - previous_end > max_gap_ms:
            current_reason = "silence_gap"
            flush()
        elif current and current_text.endswith(SENTENCE_END):
            current_reason = "sentence_end"
            flush()
        elif current and len(current_text) + len(text) > max_sentence_chars:
            current_reason = "max_chars"
            flush()
        current.append(unit)
        current_text += text
    if current:
        current_reason = "end"
        flush()
    return sentences, reasons


def group_passages(
    sentences: list[dict[str, Any]],
    *,
    max_sentences_per_passage: int = 4,
    max_passage_chars: int = 450,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    reasons: dict[str, int] = {}
    passages: list[dict[str, Any]] = []
    current: list[dict[str, Any]] = []
    current_chars = 0

    def flush(reason: str) -> None:
        nonlocal current, current_chars
        if not current:
            return
        segment_id = current[0]["segment_id"]
        index = sum(1 for p in passages if p["segment_id"] == segment_id) + 1
        passages.append(
            {
                "passage_id": f"{segment_id}-p{index:02d}",
                "segment_id": segment_id,
                "sentence_ids": [s["sentence_id"] for s in current],
                "t_start_ms": current[0]["t_start_ms"],
                "t_end_ms": current[-1]["t_end_ms"],
                "text": "".join(s["text"] for s in current),
                "boundary_reason": reason,
            }
        )
        reasons[reason] = reasons.get(reason, 0) + 1
        current = []
        current_chars = 0

    for sentence in sentences:
        if current and sentence["segment_id"] != current[0]["segment_id"]:
            flush("segment_change")
        if current and len(current) >= max_sentences_per_passage:
            flush("max_sentences")
        if current and current_chars + len(sentence["text"]) > max_passage_chars:
            flush("max_chars")
        current.append(sentence)
        current_chars += len(sentence["text"])
    if current:
        flush("end")
    return passages, reasons


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="v3 deterministic unit->sentence->passage merge.")
    parser.add_argument("--units", type=Path, required=True)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--max-gap-ms", type=int, default=2000)
    parser.add_argument("--max-sentence-chars", type=int, default=180)
    parser.add_argument("--max-sentences-per-passage", type=int, default=4)
    parser.add_argument("--max-passage-chars", type=int, default=450)
    args = parser.parse_args(argv)

    units = _read_jsonl(args.units)
    contract = _read_json(args.contract)
    unit_segment = _segment_map(contract)
    sentences, sentence_reasons = merge_sentences(
        units,
        unit_segment,
        max_gap_ms=args.max_gap_ms,
        max_sentence_chars=args.max_sentence_chars,
    )
    passages, passage_reasons = group_passages(
        sentences,
        max_sentences_per_passage=args.max_sentences_per_passage,
        max_passage_chars=args.max_passage_chars,
    )

    args.out_dir.mkdir(parents=True, exist_ok=True)
    sentences_path = args.out_dir / "sentences.json"
    passages_path = args.out_dir / "passages.json"
    sentences_path.write_text(
        json.dumps({"sentences": sentences}, ensure_ascii=False, indent=1),
        encoding="utf-8",
    )
    passages_path.write_text(
        json.dumps({"passages": passages}, ensure_ascii=False, indent=1),
        encoding="utf-8",
    )
    trace = TraceRecorder(args.out_dir)
    try:
        receipt = trace.stage(
            "transcript_merge",
            status="complete",
            inputs={"units": args.units, "contract": args.contract},
            outputs={"sentences": sentences_path, "passages": passages_path},
            counts={
                "units_in": len(units),
                "sentences_out": len(sentences),
                "passages_out": len(passages),
                "sentence_chars_median": sorted(len(s["text"]) for s in sentences)[
                    len(sentences) // 2
                ],
                "passage_chars_median": sorted(len(p["text"]) for p in passages)[
                    len(passages) // 2
                ],
                "filler_only_sentences": sum(1 for s in sentences if s["filler_only"]),
            },
            params={
                "max_gap_ms": args.max_gap_ms,
                "max_sentence_chars": args.max_sentence_chars,
                "max_sentences_per_passage": args.max_sentences_per_passage,
                "max_passage_chars": args.max_passage_chars,
            },
            decisions={
                "sentence_boundary_reasons": sentence_reasons,
                "passage_boundary_reasons": passage_reasons,
            },
            samples=[
                {
                    "sentences": sentences[:3],
                    "passages": passages[:3],
                }
            ],
        )
    finally:
        trace.close()
    print(
        json.dumps(
            {
                "out_dir": str(args.out_dir),
                "units_in": len(units),
                "sentences_out": len(sentences),
                "passages_out": len(passages),
                "sentence_reasons": sentence_reasons,
                "passage_reasons": passage_reasons,
                "receipt": receipt,
            },
            ensure_ascii=False,
            indent=1,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
