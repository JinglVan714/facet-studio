"""Compile substrate artifacts into one continuous writer-facing text.

Same information as the material packet, different arrangement: the transcript
is continuous prose, and key frames/OCR sit next to the paragraph they belong
to.  No timecodes, no separate frame table.

Usage:
    PYTHONPATH=src python -m facet_studio.writing_v4.continuous_text \
        --video-id <video-id> \
        --out runs/<run>/<video-id>/continuous.md
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Any

from .material_packet import (
    _caption_map,
    _clean_caption,
    _fmt_duration,
    _group_transcript,
    _read_json,
)


def _frames_in_order(
    frames_index: dict[str, Any],
    scene_captions: dict[str, dict[str, Any]],
    fixed_captions: dict[str, dict[str, Any]],
    uploader: str,
) -> list[dict[str, Any]]:
    strategies = frames_index.get("strategies") or {}
    names = list(strategies)
    names.sort(key=lambda name: (0 if "scene" in name else 1, name))
    frames: list[dict[str, Any]] = []
    seen: set[tuple[int, str]] = set()
    for name in names:
        captions = scene_captions if "scene" in name else fixed_captions
        for frame in strategies[name].get("frames") or []:
            path = str(frame.get("file") or "")
            if not path:
                continue
            caption = captions.get(Path(path).stem, {})
            if caption.get("read_failed"):
                continue
            if caption and caption.get("is_representative") is False:
                continue
            text = _clean_caption(str(caption.get("text") or ""), uploader)
            t_ms = int(frame.get("t_ms") or 0)
            key = (t_ms // 1000, text)
            if key in seen:
                continue
            seen.add(key)
            frames.append(
                {"t_ms": t_ms, "path": path, "text": text, "strategy": name}
            )
    frames.sort(key=lambda item: (item["t_ms"], item["path"]))
    return frames


def _select_for_paragraph(
    frames: list[dict[str, Any]], *, max_frames: int
) -> list[dict[str, Any]]:
    """Pick the most informative 1-2 frames for a paragraph.

    The transcript already carries the spoken content; the frame note is an
    anchor to a visual, not a second transcript.  Prefer longer OCR (tables,
    code, diagrams), digits, and scene frames.
    """
    if not frames:
        return []

    def score(frame: dict[str, Any]) -> int:
        text = frame["text"]
        value = len(text)
        if any(char.isdigit() for char in text):
            value += 8
        if any(char in text for char in "：:；;|"):
            value += 4
        if frame.get("strategy") == "scene":
            value += 2
        return value

    ranked = sorted(frames, key=score, reverse=True)
    selected: list[dict[str, Any]] = []
    for frame in ranked:
        if len(selected) >= max_frames:
            break
        if len(frame["text"]) < 4 and not any(
            char.isdigit() for char in frame["text"]
        ):
            continue
        selected.append(frame)
    selected.sort(key=lambda item: item["t_ms"])
    return selected


_UI_ONLY = {
    "设置",
    "插件",
    "插件配置",
    "插件列表",
    "模型",
    "通用设置",
    "预览版",
    "标准模式",
    "自定义",
    "当前使用",
}


def _short_note(text: str, limit: int = 80) -> str:
    parts = [part.strip() for part in re.split(r"[；\n]+", text or "") if part.strip()]
    parts = [
        part.replace("[unclear]", "").strip()
        for part in parts
        if "bilibili" not in part.lower()
    ]
    parts = [part for part in parts if part and part not in _UI_ONLY]
    deduped: list[str] = []
    for part in sorted(parts, key=len, reverse=True):
        if any(part in existing or existing in part for existing in deduped):
            continue
        deduped.append(part)
    parts = deduped

    def score(part: str) -> int:
        value = len(part)
        if any(char.isdigit() for char in part):
            value += 20
        if any(char in part for char in "：:；;|"):
            value += 8
        if len(part) < 4:
            value -= 40
        return value

    ranked = sorted(range(len(parts)), key=lambda i: score(parts[i]), reverse=True)
    keep = sorted(ranked[:2])
    hint = "；".join(parts[index] for index in keep).strip("； ")
    if len(hint) > limit:
        hint = hint[:limit].rstrip() + "…"
    return hint or "画面"


def _visual_note(frames: list[dict[str, Any]], *, path_prefix: str) -> str:
    if not frames:
        return ""
    parts: list[str] = []
    for frame in frames:
        text = _short_note(frame["text"]) if frame["text"] else "画面"
        parts.append(
            "画面参考（可选，非必用）："
            f"{text}；图：`{path_prefix}{frame['path']}`"
        )
    return "（" + " ｜ ".join(parts) + "）"


def build_continuous_text(
    *,
    video_id: str,
    data_root: Path,
    request: str = "",
) -> str:
    video_dir = data_root / video_id
    source = _read_json(video_dir / "source.json")
    transcript = _read_json(video_dir / "transcript" / "transcript.json")
    frames_index = _read_json(video_dir / "frames_index.json")

    uploader = str(source.get("uploader") or "")
    title = str(source.get("title") or video_id)
    scene_captions = _caption_map(video_dir / "frames_vlm__frames_scene.json")
    fixed_captions = _caption_map(video_dir / "frames_vlm__frames.json")
    if not scene_captions and not fixed_captions:
        raise SystemExit(f"no frame captions found under {video_dir}")

    paragraphs = _group_transcript(transcript.get("sentences") or [])
    frames = _frames_in_order(
        frames_index, scene_captions, fixed_captions, uploader
    )
    path_prefix = f"data/{video_id}/"

    parts: list[str] = []
    parts.append(f"# {title}")
    parts.append("")
    parts.append(
        f"UP 主：{uploader or '（未知）'}｜时长：{_fmt_duration(source.get('duration_s') or 0)}"
        f"｜链接：{source.get('source_url') or '（未知）'}"
    )
    parts.append("")
    if request.strip():
        parts.append(f"请求：{request.strip()}")
        parts.append("")
    parts.append("下面是这条视频的完整素材，按原本的讲述顺序连成一条；关键帧和画面文字夹在对应位置。")
    parts.append("")

    frame_index = 0
    for paragraph in paragraphs:
        end = int(paragraph[-1]["end_ms"])
        text = "".join(item["text"] for item in paragraph)
        parts.append(text)
        candidates: list[dict[str, Any]] = []
        while frame_index < len(frames) and frames[frame_index]["t_ms"] <= end:
            candidates.append(frames[frame_index])
            frame_index += 1
        selected = _select_for_paragraph(candidates, max_frames=1)
        note = _visual_note(selected, path_prefix=path_prefix)
        if note:
            parts.append("")
            parts.append(note)
        parts.append("")

    if frame_index < len(frames):
        selected = _select_for_paragraph(frames[frame_index:], max_frames=1)
        note = _visual_note(selected, path_prefix=path_prefix)
        if note:
            parts.append(note)
            parts.append("")

    return "\n".join(parts).rstrip() + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a continuous writer-facing text.")
    parser.add_argument("--video-id", required=True)
    parser.add_argument("--data-root", type=Path, default=Path("data"))
    parser.add_argument("--request", default="")
    parser.add_argument("--request-file", type=Path, default=None)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)

    request = args.request
    if args.request_file is not None:
        request = args.request_file.read_text(encoding="utf-8").strip()

    text = build_continuous_text(
        video_id=args.video_id,
        data_root=args.data_root,
        request=request,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(text, encoding="utf-8")
    print(f"wrote {args.out} ({len(text)} chars)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
