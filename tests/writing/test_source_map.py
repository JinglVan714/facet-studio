"""Tests for the deterministic source-map view."""

from __future__ import annotations

from lunograph.writing.source_map import build_source_map

EDITED = (
    "## 开场\n\n"
    "先看 0.756 这个分数。\n\n"
    "## 机制\n\n"
    "这里解释了为什么分数会偏低。"
)

INDEX = {
    "video_id": "BVtest",
    "segments": [{"segment_id": "seg1"}],
    "claims": [
        {
            "claim_id": "c1",
            "segment_id": "seg1",
            "text": "分数 0.756",
            "status": "supported",
            "t_start_ms": 0,
            "t_end_ms": 1000,
        }
    ],
    "evidence": [
        {
            "evidence_id": "e1",
            "claim_ids": ["c1"],
            "quote": "0.756",
            "t_start_ms": 0,
            "t_end_ms": 1000,
            "sentence_ids": ["s1"],
        }
    ],
    "sentences": [
        {
            "sentence_id": "s1",
            "segment_id": "seg1",
            "t_start_ms": 0,
            "t_end_ms": 1000,
            "text": "先看 0.756 这个分数。",
        },
        {
            "sentence_id": "s2",
            "segment_id": "seg1",
            "t_start_ms": 1000,
            "t_end_ms": 2000,
            "text": "这里解释了为什么分数会偏低。",
        },
    ],
    "parts": [{"part_id": "part_01"}],
    "frames": [
        {
            "frame_id": "f1",
            "t_ms": 500,
            "file": "frames/f1.jpg",
            "caption": "分数轴",
            "selected": True,
        }
    ],
}


def test_build_source_map_is_deterministic_and_structured() -> None:
    first = build_source_map(INDEX, EDITED)
    second = build_source_map(INDEX, EDITED)
    assert first == second
    assert first["schema_version"] == "source-map-v1"
    assert first["topology"] == "unknown"
    assert [section["heading"] for section in first["sections"]] == ["开场", "机制"]
    assert first["sections"][0]["gist"] == "先看 0.756 这个分数。"
    assert any(anchor["id"] == "c1" for anchor in first["anchors"])
    assert any(anchor["id"] == "e1" for anchor in first["anchors"])
    assert any(item["value"] == "0.756" for item in first["numbers"])
    assert first["frames"][0]["frame_id"] == "f1"
    assert first["anchors"][0]["speaker"] == "unknown"
    assert first["anchors"][0]["claim_type"] == "unknown"
    assert len(first["source_map_hash"]) == 64


def test_build_source_map_keeps_number_occurrences_and_provenance() -> None:
    index = dict(INDEX)
    index["sentences"] = [
        {
            "sentence_id": "s1",
            "segment_id": "seg1",
            "t_start_ms": 0,
            "t_end_ms": 1000,
            "text": "她有 150 万孩子。",
        },
        {
            "sentence_id": "s2",
            "segment_id": "seg1",
            "t_start_ms": 1000,
            "t_end_ms": 2000,
            "text": "后来又说 160 万。",
        },
        {
            "sentence_id": "s3",
            "segment_id": "seg1",
            "t_start_ms": 2000,
            "t_end_ms": 3000,
            "text": "还是 150 万。",
        },
    ]
    source_map = build_source_map(index, EDITED)
    values = [row["value"] for row in source_map["numbers"]]
    assert values.count("150") == 2
    assert "160" in values
    assert source_map["numbers"][0]["metric"] == "unknown"
    assert source_map["numbers"][0]["verification"] == "unverified"
    assert source_map["provenance"]["video_id"] == "BVtest"
    assert "link" in source_map["provenance"]["missing"]
    assert source_map["frames"][0]["provenance"] == "video_frame"


def test_source_map_uses_frame_channel_hint() -> None:
    index = dict(INDEX)
    index["frames"] = [
        {
            "frame_id": "f1",
            "t_ms": 500,
            "file": "frames/f1.jpg",
            "caption": "CodingStartup起码课 bilibili\n300 张动物照片",
            "selected": True,
        }
    ]
    source_map = build_source_map(index, EDITED)
    assert source_map["provenance"]["channel"] == "CodingStartup起码课"
    assert "channel" not in source_map["provenance"]["missing"]


def test_source_map_prefers_repeated_full_channel_over_truncated_suffix() -> None:
    index = dict(INDEX)
    index["frames"] = [
        {
            "frame_id": "f1",
            "t_ms": 500,
            "file": "frames/f1.jpg",
            "caption": "deepseek Harness 开发者预览版\n的编程宇宙 bilibili\n设计思路",
            "selected": True,
        },
        {
            "frame_id": "f2",
            "t_ms": 1000,
            "file": "frames/f2.jpg",
            "caption": "轩辕的编程宇宙 bilibili\nCreator",
            "selected": True,
        },
        {
            "frame_id": "f3",
            "t_ms": 1500,
            "file": "frames/f3.jpg",
            "caption": "轩辕的编程宇宙 bilibili\nSettings",
            "selected": True,
        },
    ]
    source_map = build_source_map(index, EDITED)
    assert source_map["provenance"]["channel"] == "轩辕的编程宇宙"
    assert source_map["source_metadata"]["channel"]["source"] == "frame_watermark"


def test_source_map_extracts_title_and_date_from_video_page_frame() -> None:
    index = dict(INDEX)
    index["frames"] = [
        {
            "frame_id": "f1",
            "t_ms": 500,
            "file": "frames/f1.jpg",
            "caption": (
                "直播 游戏中心 会员购\n"
                "Agent和Harness到底是什么？一个动画彻底搞懂！\n"
                "24.6万 669 2026-05-15 18:02:14 含AI生成内容\n"
                "工具链 扩展"
            ),
            "selected": True,
        }
    ]
    source_map = build_source_map(index, EDITED)
    assert source_map["provenance"]["title"] == (
        "Agent和Harness到底是什么？一个动画彻底搞懂！"
    )
    assert source_map["provenance"]["date"] == "2026-05-15"
    assert source_map["source_metadata"]["title"]["source"] == "frame_ocr"
    assert "title" not in source_map["provenance"]["missing"]
    assert "date" not in source_map["provenance"]["missing"]


def test_source_map_does_not_use_comment_date_as_video_date() -> None:
    index = dict(INDEX)
    index["frames"] = [
        {
            "frame_id": "f1",
            "t_ms": 500,
            "file": "frames/f1.jpg",
            "caption": "2025-07-31 19:10 9697 回复\n多新鲜呐",
            "selected": True,
        }
    ]
    source_map = build_source_map(index, EDITED)
    assert source_map["provenance"]["date"] == "unknown"
    assert "date" in source_map["provenance"]["missing"]


def test_source_map_caps_prompt_frame_caption_but_reports_full_length() -> None:
    index = dict(INDEX)
    long_caption = "整屏文字 " * 80
    index["frames"] = [
        {
            "frame_id": "f1",
            "t_ms": 500,
            "file": "frames/f1.jpg",
            "caption": long_caption,
            "selected": True,
        }
    ]
    source_map = build_source_map(index, EDITED)
    frame = source_map["frames"][0]
    assert frame["caption_truncated"] is True
    assert frame["caption_full_chars"] == len(long_caption.strip())
    assert len(frame["caption"]) <= 241
    assert frame["caption"].endswith("…")


def test_build_source_map_reports_missing_claim_path() -> None:
    index = {key: value for key, value in INDEX.items() if key not in {"claims", "evidence"}}
    source_map = build_source_map(index, EDITED)
    assert "claim_path_absent" in source_map["gaps"]
    assert "evidence_path_absent" in source_map["gaps"]
    assert "speaker_labels_absent" in source_map["gaps"]
