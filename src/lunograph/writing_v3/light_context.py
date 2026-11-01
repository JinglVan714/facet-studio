"""Lightweight context builder for the no-claim path.

One-off writing does not need claim extraction.  This builder turns the
transcript (sentences/passages), temporal outline, and frame index into a
pack-shaped context with empty claims/evidence.  The edited-transcript renderer
can then produce the full writer-facing text; ``bind_article`` audits it against
the transcript.

No model call.  Claims/evidence stay empty; the full pack audit remains the
optional claim path.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .edited_transcript import build_edited_transcript

SCHEMA = "light-context-v1"


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _caption_map(frame_captions: Any | None) -> dict[str, str]:
    if not frame_captions:
        return {}
    if isinstance(frame_captions, dict) and "per_frame" in frame_captions:
        source = frame_captions.get("per_frame", {})
    elif isinstance(frame_captions, dict):
        source = frame_captions
    else:
        return {}
    captions: dict[str, str] = {}
    for frame_id, value in source.items():
        if isinstance(value, dict):
            text = value.get("text") or value.get("caption") or ""
        else:
            text = str(value)
        captions[str(frame_id)] = text.strip()
    return captions


def _frame_strategy(
    frames_index: dict[str, Any], preferred: str
) -> tuple[str, list[dict[str, Any]]]:
    strategies = frames_index.get("strategies") or {}
    if preferred in strategies:
        return preferred, list(strategies[preferred].get("frames", []))
    for name, value in strategies.items():
        return name, list(value.get("frames", []))
    return preferred, []


def _select_frames(
    frames: list[dict[str, Any]], max_count: int
) -> list[dict[str, Any]]:
    if max_count <= 0:
        return list(frames)
    if len(frames) <= max_count:
        return list(frames)
    if max_count == 1:
        return [frames[len(frames) // 2]]
    indices = {
        round(i * (len(frames) - 1) / (max_count - 1))
        for i in range(max_count)
    }
    return [frames[index] for index in sorted(indices)]


def _assign_segment(
    t_ms: int, segments: list[dict[str, Any]]
) -> str:
    for segment in segments:
        if segment["t_start_ms"] <= t_ms <= segment["t_end_ms"]:
            return segment["segment_id"]
    return min(
        segments,
        key=lambda segment: min(
            abs(t_ms - segment["t_start_ms"]),
            abs(t_ms - segment["t_end_ms"]),
        ),
    )["segment_id"]


def build_light_context(
    passages: list[dict[str, Any]],
    sentences: list[dict[str, Any]],
    outline: dict[str, Any],
    frames_index: dict[str, Any],
    *,
    frame_captions: Any | None = None,
    video_id: str = "",
    strategy: str = "scene",
    max_frames_per_segment: int = 2,
    max_caption_chars: int = 160,
) -> dict[str, Any]:
    """Build a pack-shaped context with no claims/evidence."""
    segments: list[dict[str, Any]] = []
    for outline_segment in outline.get("segments", []):
        segment_id = outline_segment.get("segment_id", "")
        segment_passages = [
            passage
            for passage in passages
            if passage.get("segment_id") == segment_id
        ]
        sentence_ids: list[str] = []
        for passage in segment_passages:
            for sentence_id in passage.get("sentence_ids", []):
                if sentence_id not in sentence_ids:
                    sentence_ids.append(sentence_id)
        segments.append(
            {
                "segment_id": segment_id,
                "label": outline_segment.get("label", ""),
                "t_start_ms": int(
                    outline_segment.get(
                        "first_ms",
                        segment_passages[0].get("t_start_ms", 0)
                        if segment_passages
                        else 0,
                    )
                ),
                "t_end_ms": int(
                    outline_segment.get(
                        "last_ms",
                        segment_passages[-1].get("t_end_ms", 0)
                        if segment_passages
                        else 0,
                    )
                ),
                "claim_ids": [],
                "sentence_ids": sentence_ids,
                "frame_ids": [],
            }
        )
    if not segments:
        return {
            "schema_version": SCHEMA,
            "video_id": video_id,
            "segments": [],
            "sentences": sentences,
            "claims": [],
            "evidence": [],
            "frames": [],
        }

    strategy_name, strategy_frames = _frame_strategy(frames_index, strategy)
    captions = _caption_map(frame_captions)
    frames_by_segment: dict[str, list[dict[str, Any]]] = {
        segment["segment_id"]: [] for segment in segments
    }
    for frame in strategy_frames:
        t_ms = int(frame.get("t_ms", 0))
        segment_id = _assign_segment(t_ms, segments)
        frames_by_segment.setdefault(segment_id, []).append(frame)

    frames_out: list[dict[str, Any]] = []
    for segment in segments:
        selected = _select_frames(
            sorted(
                frames_by_segment.get(segment["segment_id"], []),
                key=lambda frame: int(frame.get("t_ms", 0)),
            ),
            max_frames_per_segment,
        )
        for frame in selected:
            file_name = frame.get("file", "")
            frame_id = Path(file_name).stem
            full_caption = captions.get(frame_id, "")
            caption = full_caption[:max_caption_chars].rstrip()
            frames_out.append(
                {
                    "frame_id": frame_id,
                    "segment_ids": [segment["segment_id"]],
                    "t_ms": int(frame.get("t_ms", 0)),
                    "file": file_name,
                    "caption": caption,
                    "capture_method": "vlm" if caption else "none",
                    "strategy": strategy_name,
                    "caption_truncated": len(full_caption) > max_caption_chars,
                    "caption_full_chars": len(full_caption),
                }
            )
            segment["frame_ids"].append(frame_id)

    return {
        "schema_version": SCHEMA,
        "pack_id": f"light_{video_id}" if video_id else "light",
        "video_id": video_id,
        "segments": segments,
        "sentences": sentences,
        "claims": [],
        "evidence": [],
        "frames": frames_out,
        "gaps": [],
        "conflicts": [],
        "selection": {
            "claims_considered": 0,
            "claims_selected": 0,
            "context": {
                "window": 0,
                "claims_total": 0,
                "claims_with_context": 0,
                "claims_without_context": 0,
                "context_sentences": len(sentences),
            },
            "frame_selection": {
                "strategy": strategy_name,
                "max_frames_per_segment": max_frames_per_segment,
                "frames_selected": len(frames_out),
                "captions_truncated": sum(
                    1 for frame in frames_out if frame["caption_truncated"]
                ),
            },
        },
        "provenance": {
            "summary": {
                "claims_total": 0,
                "claims_with_source": 0,
                "claims_without_source": 0,
            },
            "claims": {},
        },
        "budget": {
            "max_chars": None,
            "max_frames": None,
            "context_window": 0,
        },
        "truncated": False,
        "truncation": {"sentences_dropped": 0, "frames_dropped": 0},
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build a no-claim light context and its full edited text."
    )
    parser.add_argument("--passages", type=Path, required=True)
    parser.add_argument("--sentences", type=Path, required=True)
    parser.add_argument("--outline", type=Path, required=True)
    parser.add_argument("--frames-index", type=Path, required=True)
    parser.add_argument("--frame-captions", type=Path)
    parser.add_argument("--video-id", default="")
    parser.add_argument("--strategy", default="scene")
    parser.add_argument("--max-frames-per-segment", type=int, default=2)
    parser.add_argument("--max-caption-chars", type=int, default=160)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--out-text", type=Path, required=True)
    parser.add_argument("--out-source-map", type=Path, required=True)
    parser.add_argument("--out-manifest", type=Path, required=True)
    args = parser.parse_args(argv)

    passages = _read_json(args.passages).get("passages", [])
    sentences = _read_json(args.sentences).get("sentences", [])
    outline = _read_json(args.outline)
    frames_index = _read_json(args.frames_index)
    frame_captions = (
        _read_json(args.frame_captions) if args.frame_captions else None
    )
    context = build_light_context(
        passages,
        sentences,
        outline,
        frames_index,
        frame_captions=frame_captions,
        video_id=args.video_id,
        strategy=args.strategy,
        max_frames_per_segment=args.max_frames_per_segment,
        max_caption_chars=args.max_caption_chars,
    )
    result = build_edited_transcript(
        context, passages, sentences, mode="full"
    )
    for path in (
        args.out,
        args.out_text,
        args.out_source_map,
        args.out_manifest,
    ):
        path.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(context, ensure_ascii=False, indent=1), encoding="utf-8"
    )
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
                "out": str(args.out),
                "mode": result["mode"],
                "text_chars": len(result["text"]),
                "frames": len(context["frames"]),
                "segments": len(context["segments"]),
                "decision": result["decision"],
            },
            ensure_ascii=False,
            indent=1,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
