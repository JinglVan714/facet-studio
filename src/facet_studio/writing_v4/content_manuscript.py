"""Compile substrate artifacts into a content-only manuscript for the writer.

Material stays material: this layer owns the transcript, figure selection,
figure copying and source metadata.  The writer receives only the content —
continuous paragraphs plus inline `图示` notes — with no video title, uploader,
timecodes, frame IDs, OCR labels, or source line.

The pipeline adds the source line after writing.  The writer never sees the
machinery that produced the content.

Usage:
    PYTHONPATH=src python -m facet_studio.writing_v4.content_manuscript \
        --video-id <video-id> \
        --out runs/<run>/<video-id>/content.md
"""

from __future__ import annotations

import argparse
import re
import shutil
from pathlib import Path
from typing import Any

from .continuous_text import _frames_in_order, _select_for_paragraph
from .material_packet import (
    _caption_map,
    _clean_caption,
    _group_transcript,
    _read_json,
)


META_REPLACEMENTS = (
    ("这一期视频", "这次"),
    ("这条视频", "这次"),
    ("这期视频", "这次"),
    ("本期视频", "这次"),
    ("视频比较长", "内容比较长"),
    ("拍这条视频", "准备这些内容"),
    ("拍完视频以后", "事后"),
    ("拍完视频", "事后"),
    ("拍视频", "准备内容"),
    ("视频里", "内容里"),
    ("视频中", "内容中"),
    ("码下来", ""),
    ("下期见", ""),
    ("本期内容就到这里", ""),
)


def _strip_video_meta(text: str) -> str:
    for source, target in META_REPLACEMENTS:
        text = text.replace(source, target)
    return text


OCR_SPOON_SEPARATOR = re.compile(r"(勺尖|半勺|大半勺|小勺|大勺)\.(\d+)克")
OCR_NUMBER_SEPARATOR = re.compile(r"(\d+勺)\.(\d+)克")
OCR_LEADING_DECIMAL = re.compile(r"(?<=[一-鿿])\.(\d+)克")


VOICE_REPLACEMENTS = (
    ("我的建议", "建议"),
    ("我建议", "建议"),
    ("我一般会", "一般会"),
    ("我一般", "一般"),
    ("我平时", "平时"),
    ("我现在", "现在"),
    ("我这两天", "最近"),
    ("我说实话", ""),
    ("我觉得", ""),
    ("我认为", "可以说"),
    ("我保证", ""),
    ("大家相信我", ""),
    ("相信我", ""),
    ("大家好", ""),
    ("朋友们好", ""),
    ("hello", ""),
    ("大家注意", "注意"),
    ("很多宝宝", "很多人"),
    ("宝宝们", "你"),
    ("你们", "你"),
    ("咱们", "你"),
)

def _normalize_voice(text: str) -> str:
    for source, target in VOICE_REPLACEMENTS:
        text = text.replace(source, target)
    return text

def _normalize_ocr_numbers(text: str) -> str:
    """Normalize OCR punctuation around Chinese units.

    Two different OCR errors share the same dot: a separator between a
    spoon measure and grams (``1勺.10克``) and a missing leading zero
    (``.5克``).  Keep the rules unit-based, not ingredient-based, so they
    apply to any content rather than one recipe.
    """
    text = OCR_SPOON_SEPARATOR.sub(r"\1\2克", text)
    text = OCR_NUMBER_SEPARATOR.sub(r"\1\2克", text)
    text = OCR_LEADING_DECIMAL.sub(r"0.\1克", text)
    return text


def _figure_name(index: int, source: Path) -> str:
    suffix = source.suffix.lower() or ".jpg"
    return f"fig-{index:02d}{suffix}"


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


def _short_visual_note(text: str, limit: int = 80) -> str:
    """Short, de-noised visual reference for the writer.

    The full OCR caption stays in the evidence layer; the writer only needs a
    hint to decide whether a keyframe is worth using.  Long OCR dumps were
    crowding out the actual content, so rank lines by informativeness, keep at
    most two, and hard-cap the result.
    """
    parts = [part.strip() for part in re.split(r"[；\n]+", text or "") if part.strip()]
    parts = [
        part.replace("[unclear]", "").strip()
        for part in parts
        if "bilibili" not in part.lower()
    ]
    parts = [part for part in parts if part and part not in _UI_ONLY]
    # OCR often repeats the same line with a truncated copy; keep the longer
    # version so the note does not repeat itself.
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


def build_content_manuscript(
    *,
    video_id: str,
    data_root: Path,
    out_path: Path,
    figures_dir: Path | None = None,
    transcript_path: Path | None = None,
    source_path: Path | None = None,
) -> tuple[str, int]:
    video_dir = data_root / video_id
    source = _read_json(source_path or video_dir / "source.json")
    transcript = _read_json(
        transcript_path or video_dir / "transcript" / "transcript.json"
    )
    frames_index = _read_json(video_dir / "frames_index.json")

    uploader = str(source.get("uploader") or "")
    scene_captions = _caption_map(video_dir / "frames_vlm__frames_scene.json")
    fixed_captions = _caption_map(video_dir / "frames_vlm__frames.json")
    if not scene_captions and not fixed_captions:
        raise SystemExit(f"no frame captions found under {video_dir}")

    paragraphs = _group_transcript(transcript.get("sentences") or [])
    frames = _frames_in_order(
        frames_index, scene_captions, fixed_captions, uploader
    )
    figures_dir = figures_dir or (out_path.parent / "figures")
    figures_dir.mkdir(parents=True, exist_ok=True)

    def figure_path(frame: dict[str, Any], number: int) -> str:
        source_path = video_dir / str(frame["path"])
        destination = figures_dir / _figure_name(number, source_path)
        if not destination.exists():
            shutil.copy2(source_path, destination)
        try:
            relative = destination.relative_to(out_path.parent).as_posix()
        except ValueError:
            relative = str(destination)
        return relative

    parts: list[str] = []
    frame_index = 0
    figure_number = 0
    for paragraph in paragraphs:
        end = int(paragraph[-1]["end_ms"])
        text = _normalize_ocr_numbers(_normalize_voice(_strip_video_meta("".join(item["text"] for item in paragraph))))
        parts.append(text)
        candidates: list[dict[str, Any]] = []
        while frame_index < len(frames) and frames[frame_index]["t_ms"] <= end:
            candidates.append(frames[frame_index])
            frame_index += 1
        selected = _select_for_paragraph(candidates, max_frames=1)
        notes: list[str] = []
        for frame in selected:
            figure_number += 1
            relative = figure_path(frame, figure_number)
            caption = (
                _normalize_ocr_numbers(
                    _normalize_voice(_strip_video_meta(frame["text"]))
                )
                if frame["text"]
                else ""
            )
            notes.append(
                f"画面参考 {figure_number}（可选，非必用）："
                f"{_short_visual_note(caption)}；图：{relative}"
            )
        if notes:
            parts.append("")
            parts.append("（" + " ｜ ".join(notes) + "）")
        parts.append("")

    if frame_index < len(frames):
        selected = _select_for_paragraph(frames[frame_index:], max_frames=1)
        notes = []
        for frame in selected:
            figure_number += 1
            relative = figure_path(frame, figure_number)
            caption = (
                _normalize_ocr_numbers(
                    _normalize_voice(_strip_video_meta(frame["text"]))
                )
                if frame["text"]
                else ""
            )
            notes.append(
                f"画面参考 {figure_number}（可选，非必用）："
                f"{_short_visual_note(caption)}；图：{relative}"
            )
        if notes:
            parts.append("（" + " ｜ ".join(notes) + "）")
            parts.append("")

    text = "\n".join(parts).rstrip() + "\n"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(text, encoding="utf-8")
    return text, figure_number


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a content-only manuscript.")
    parser.add_argument("--video-id", required=True)
    parser.add_argument("--data-root", type=Path, default=Path("data"))
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--figures-dir", type=Path, default=None)
    parser.add_argument("--transcript-json", type=Path, default=None)
    parser.add_argument("--source-json", type=Path, default=None)
    args = parser.parse_args(argv)

    text, figure_count = build_content_manuscript(
        video_id=args.video_id,
        data_root=args.data_root,
        out_path=args.out,
        figures_dir=args.figures_dir,
        transcript_path=args.transcript_json,
        source_path=args.source_json,
    )
    print(f"wrote {args.out} ({len(text)} chars, {figure_count} figures)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
