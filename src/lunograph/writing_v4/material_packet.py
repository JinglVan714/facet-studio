"""Compile substrate artifacts into one Markdown material packet.

The packet is the writer's only input.  It keeps the full transcript (grouped
into readable paragraphs), frame paths with OCR text, and source metadata.
It deliberately contains no claims, brief, IDs, or audit language.

Usage:
    PYTHONPATH=src python -m lunograph.writing_v4.material_packet \
        --video-id <video-id> \
        --out runs/<run>/<video-id>/material.md
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _fmt_ms(ms: int) -> str:
    total = max(0, int(ms)) // 1000
    minutes, seconds = divmod(total, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    return f"{minutes:02d}:{seconds:02d}"


def _fmt_duration(seconds: float) -> str:
    total = max(0, int(round(float(seconds or 0))))
    minutes, sec = divmod(total, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours} 小时 {minutes} 分 {sec} 秒"
    return f"{minutes} 分 {sec} 秒"


def _clean_caption(text: str, uploader: str = "") -> str:
    """Drop the platform/uploader watermark lines, keep the OCR content."""
    lines = [line.strip() for line in (text or "").splitlines() if line.strip()]
    if not lines:
        return ""
    first = lines[0]
    if "bilibili" in first.lower() or (uploader and uploader in first):
        lines = lines[1:]
    if uploader:
        lines = [line for line in lines if line != uploader]
    return "；".join(lines)


def _caption_map(path: Path | None) -> dict[str, dict[str, Any]]:
    if path is None or not path.exists():
        return {}
    data = _read_json(path)
    per_frame = data.get("per_frame") or {}
    return {
        str(key): value
        for key, value in per_frame.items()
        if isinstance(value, dict)
    }


def _group_transcript(
    sentences: list[dict[str, Any]],
    *,
    max_chars: int = 180,
    max_gap_ms: int = 6000,
) -> list[list[dict[str, Any]]]:
    """Group ASR sentences into readable paragraphs without changing wording."""
    paragraphs: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    chars = 0
    for sentence in sentences:
        text = str(sentence.get("text") or "").strip()
        if not text:
            continue
        start = int(sentence.get("start_ms", sentence.get("t_start_ms", 0)) or 0)
        end = int(sentence.get("end_ms", sentence.get("t_end_ms", start)) or start)
        if current:
            previous_end = int(current[-1].get("end_ms") or 0)
            if chars + len(text) > max_chars or start - previous_end > max_gap_ms:
                paragraphs.append(current)
                current = []
                chars = 0
        current.append(
            {
                "start_ms": start,
                "end_ms": end,
                "text": re.sub(r"\s+", "", text),
            }
        )
        chars += len(text)
    if current:
        paragraphs.append(current)
    return paragraphs


def _strategy_frames(
    frames_index: dict[str, Any],
) -> list[tuple[str, dict[str, Any]]]:
    """Return (strategy name, frame) in a useful order: scene first, then fixed."""
    strategies = frames_index.get("strategies") or {}
    names = list(strategies)
    names.sort(key=lambda name: (0 if "scene" in name else 1, name))
    result: list[tuple[str, dict[str, Any]]] = []
    for name in names:
        for frame in strategies[name].get("frames") or []:
            result.append((name, frame))
    return result


def _frame_lines(
    frames_index: dict[str, Any],
    scene_captions: dict[str, dict[str, Any]],
    fixed_captions: dict[str, dict[str, Any]],
    uploader: str,
    *,
    path_prefix: str = "",
) -> tuple[list[str], list[str]]:
    """Build scene-frame and fixed-frame bullet lines, skipping failed frames."""
    scene_lines: list[str] = []
    fixed_lines: list[str] = []
    seen: set[tuple[int, str]] = set()
    for strategy, frame in _strategy_frames(frames_index):
        path = str(frame.get("file") or "")
        if not path:
            continue
        stem = Path(path).stem
        captions = scene_captions if "scene" in strategy else fixed_captions
        caption = captions.get(stem, {})
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
        line = f"- [{_fmt_ms(t_ms)}] `{path_prefix}{path}`"
        line += f"；画面文字：{text if text else '（无）'}"
        if "scene" in strategy:
            scene_lines.append(line)
        else:
            fixed_lines.append(line)
    return scene_lines, fixed_lines


def _outline_lines(outline_path: Path | None) -> list[str]:
    if outline_path is None or not outline_path.exists():
        return []
    data = _read_json(outline_path)
    lines: list[str] = []
    for segment in data.get("segments") or []:
        label = str(segment.get("label") or "").strip()
        first = int(segment.get("first_ms") or 0)
        last = int(segment.get("last_ms") or first)
        if label:
            lines.append(f"- [{_fmt_ms(first)}–{_fmt_ms(last)}] {label}")
    return lines


def build_packet(
    *,
    video_id: str,
    data_root: Path,
    request: str = "",
    outline_path: Path | None = None,
    transcript_path: Path | None = None,
    source_path: Path | None = None,
) -> str:
    video_dir = data_root / video_id
    source = _read_json(source_path or video_dir / "source.json")
    transcript = _read_json(
        transcript_path or video_dir / "transcript" / "transcript.json"
    )
    frames_index = _read_json(video_dir / "frames_index.json")

    uploader = str(source.get("uploader") or "")
    title = str(source.get("title") or video_id)
    scene_captions = _caption_map(video_dir / "frames_vlm__frames_scene.json")
    fixed_captions = _caption_map(video_dir / "frames_vlm__frames.json")
    if not scene_captions and not fixed_captions:
        raise SystemExit(f"no frame captions found under {video_dir}")

    paragraphs = _group_transcript(transcript.get("sentences") or [])
    scene_lines, fixed_lines = _frame_lines(
        frames_index,
        scene_captions,
        fixed_captions,
        uploader,
        path_prefix=f"data/{video_id}/",
    )
    outline_lines = _outline_lines(outline_path)

    parts: list[str] = []
    parts.append(f"# 素材包：{title}")
    parts.append("")
    parts.append("> 这是写作用的素材，不是文章。时间码只用于定位，不要写进文章。")
    parts.append("")
    parts.append("## 视频信息")
    parts.append("")
    parts.append(f"- 原标题（仅参考，不要直接当文章标题）：{title}")
    parts.append(f"- UP 主：{uploader or '（未知）'}")
    parts.append(f"- 时长：{_fmt_duration(source.get('duration_s') or 0)}")
    parts.append(f"- 链接：{source.get('source_url') or '（未知）'}")
    parts.append(f"- 上传日期：{source.get('upload_date') or '（未知）'}")
    parts.append(f"- 视频 ID：{video_id}")
    parts.append("")

    if request.strip():
        parts.append("## 请求")
        parts.append("")
        parts.append(request.strip())
        parts.append("")

    if outline_lines:
        parts.append("## 视频原有章节（仅参考，不必照搬）")
        parts.append("")
        parts.extend(outline_lines)
        parts.append("")

    parts.append("## 完整转写（按时间顺序）")
    parts.append("")
    parts.append("> 转写保留原话，可能有 ASR 错误、同音字或缺少标点；数字或专名不确定时不要猜。")
    parts.append("")
    for paragraph in paragraphs:
        start = paragraph[0]["start_ms"]
        end = paragraph[-1]["end_ms"]
        text = "".join(item["text"] for item in paragraph)
        parts.append(f"[{_fmt_ms(start)}–{_fmt_ms(end)}] {text}")
        parts.append("")

    parts.append("## 关键帧")
    parts.append("")
    if scene_lines:
        parts.append("### 场景帧（代表性）")
        parts.append("")
        parts.extend(scene_lines)
        parts.append("")
    if fixed_lines:
        parts.append("### 固定间隔帧（代表性）")
        parts.append("")
        parts.extend(fixed_lines)
        parts.append("")
    if not scene_lines and not fixed_lines:
        parts.append("（没有可用的关键帧文字。）")
        parts.append("")

    return "\n".join(parts).rstrip() + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a writer-facing material packet.")
    parser.add_argument("--video-id", required=True)
    parser.add_argument("--data-root", type=Path, default=Path("data"))
    parser.add_argument("--outline", type=Path, default=None)
    parser.add_argument("--request", default="")
    parser.add_argument("--request-file", type=Path, default=None)
    parser.add_argument("--transcript-json", type=Path, default=None)
    parser.add_argument("--source-json", type=Path, default=None)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)

    request = args.request
    if args.request_file is not None:
        request = args.request_file.read_text(encoding="utf-8").strip()

    packet = build_packet(
        video_id=args.video_id,
        data_root=args.data_root,
        request=request,
        outline_path=args.outline,
        transcript_path=args.transcript_json,
        source_path=args.source_json,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(packet, encoding="utf-8")
    print(f"wrote {args.out} ({len(packet)} chars)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
