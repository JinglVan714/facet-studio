import json
from pathlib import Path

from facet_studio.writing_v4.content_manuscript import (
    _short_visual_note,
    build_content_manuscript,
)


def _write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def test_short_visual_note_caps_and_drops_watermark() -> None:
    text = "bilibili\n" + "很长的画面文字" * 30
    note = _short_visual_note(text, limit=40)
    assert "bilibili" not in note
    assert len(note) <= 41
    assert note.endswith("…")


def test_content_manuscript_labels_optional_visual_and_no_caption(
    tmp_path: Path,
) -> None:
    video = tmp_path / "data" / "BVtest"
    (video / "frames").mkdir(parents=True)
    (video / "frames" / "a.jpg").write_bytes(b"fake")
    _write_json(
        video / "source.json",
        {"video_id": "BVtest", "title": "测试视频", "uploader": "测试UP"},
    )
    _write_json(
        video / "transcript" / "transcript.json",
        {
            "sentences": [
                {"start_ms": 0, "end_ms": 5000, "text": "这是正文第一段。"},
            ]
        },
    )
    _write_json(
        video / "frames_index.json",
        {
            "strategies": {
                "fixed_interval": {
                    "frames": [{"file": "frames/a.jpg", "t_ms": 1000}]
                }
            }
        },
    )
    _write_json(
        video / "frames_vlm__frames.json",
        {
            "per_frame": {
                "a": {
                    "text": "bilibili\n画面里的关键信息 300 克",
                    "is_representative": True,
                }
            }
        },
    )

    out = tmp_path / "out" / "content.md"
    text, figure_count = build_content_manuscript(
        video_id="BVtest", data_root=tmp_path / "data", out_path=out
    )
    assert figure_count == 1
    assert "这是正文第一段。" in text
    assert "画面参考 1（可选，非必用）" in text
    assert "图：figures/fig-01.jpg" in text
    assert "图示 1" not in text
    assert "bilibili" not in text
    assert (out.parent / "figures" / "fig-01.jpg").is_file()
