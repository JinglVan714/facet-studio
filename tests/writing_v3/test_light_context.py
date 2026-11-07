"""Tests for the no-claim light context builder."""

from __future__ import annotations

from facet_studio.writing_v3 import edited_transcript, light_context

PASSAGES = [
    {
        "passage_id": "p1",
        "segment_id": "seg1",
        "sentence_ids": ["s1", "s2"],
        "t_start_ms": 0,
        "t_end_ms": 2000,
        "text": "第一句。第二句。",
    },
    {
        "passage_id": "p2",
        "segment_id": "seg2",
        "sentence_ids": ["s3", "s4"],
        "t_start_ms": 3000,
        "t_end_ms": 5000,
        "text": "第三句。第四句。",
    },
]
SENTENCES = [
    {"sentence_id": "s1", "segment_id": "seg1", "text": "第一句。", "t_start_ms": 0, "t_end_ms": 1000},
    {"sentence_id": "s2", "segment_id": "seg1", "text": "第二句。", "t_start_ms": 1000, "t_end_ms": 2000},
    {"sentence_id": "s3", "segment_id": "seg2", "text": "第三句。", "t_start_ms": 3000, "t_end_ms": 4000},
    {"sentence_id": "s4", "segment_id": "seg2", "text": "第四句。", "t_start_ms": 4000, "t_end_ms": 5000},
]
OUTLINE = {
    "segments": [
        {"segment_id": "seg1", "label": "第一段", "first_ms": 0, "last_ms": 2000},
        {"segment_id": "seg2", "label": "第二段", "first_ms": 3000, "last_ms": 5000},
    ]
}
FRAMES_INDEX = {
    "strategies": {
        "scene": {
            "frames": [
                {"t_ms": 500, "file": "frames_scene/f1.jpg"},
                {"t_ms": 3500, "file": "frames_scene/f2.jpg"},
                {"t_ms": 4500, "file": "frames_scene/f3.jpg"},
            ]
        }
    }
}
CAPTIONS = {
    "per_frame": {
        "f1": {"text": "第一段画面"},
        "f2": {"text": "第二段画面 A"},
        "f3": {"text": ""},
    }
}


def test_light_context_has_no_claims_and_assigns_frames() -> None:
    context = light_context.build_light_context(
        PASSAGES,
        SENTENCES,
        OUTLINE,
        FRAMES_INDEX,
        frame_captions=CAPTIONS,
        video_id="v1",
    )
    assert context["claims"] == []
    assert context["evidence"] == []
    assert context["segments"][0]["claim_ids"] == []
    assert context["segments"][0]["frame_ids"] == ["f1"]
    assert context["segments"][1]["frame_ids"] == ["f2", "f3"]
    assert context["frames"][0]["caption"] == "第一段画面"
    assert context["frames"][1]["caption"] == "第二段画面 A"
    assert context["frames"][2]["caption"] == ""


def test_light_context_renders_full_text_without_boundaries() -> None:
    context = light_context.build_light_context(
        PASSAGES,
        SENTENCES,
        OUTLINE,
        FRAMES_INDEX,
        frame_captions=CAPTIONS,
        video_id="v1",
    )
    result = edited_transcript.build_edited_transcript(
        context, PASSAGES, SENTENCES, mode="full"
    )
    assert result["mode"] == "full"
    assert "## 第一段" in result["text"]
    assert "第一句。第二句。" in result["text"]
    assert "（画面1：第一段画面）" in result["text"]
    assert "（限制" not in result["text"]
    assert "c_" not in result["text"]
    assert "s1" not in result["text"]


def test_frame_selection_respects_max_per_segment() -> None:
    context = light_context.build_light_context(
        PASSAGES,
        SENTENCES,
        OUTLINE,
        FRAMES_INDEX,
        frame_captions=CAPTIONS,
        video_id="v1",
        max_frames_per_segment=1,
    )
    assert context["segments"][0]["frame_ids"] == ["f1"]
    assert context["segments"][1]["frame_ids"] == ["f3"]


def test_long_caption_is_capped_and_reported() -> None:
    captions = {"per_frame": {"f1": {"text": "长" * 300}}}
    context = light_context.build_light_context(
        PASSAGES,
        SENTENCES,
        OUTLINE,
        FRAMES_INDEX,
        frame_captions=captions,
        video_id="v1",
        max_caption_chars=10,
    )
    frame = context["frames"][0]
    assert len(frame["caption"]) == 10
    assert frame["caption_truncated"] is True
    assert frame["caption_full_chars"] == 300
    assert context["selection"]["frame_selection"]["captions_truncated"] == 1


def test_no_frames_still_builds_text() -> None:
    context = light_context.build_light_context(
        PASSAGES,
        SENTENCES,
        OUTLINE,
        {"strategies": {}},
        video_id="v1",
    )
    result = edited_transcript.build_edited_transcript(
        context, PASSAGES, SENTENCES, mode="full"
    )
    assert context["frames"] == []
    assert "第一句。第二句。" in result["text"]
    assert "（画面" not in result["text"]


def test_same_input_same_output() -> None:
    first = light_context.build_light_context(
        PASSAGES, SENTENCES, OUTLINE, FRAMES_INDEX, frame_captions=CAPTIONS
    )
    second = light_context.build_light_context(
        PASSAGES, SENTENCES, OUTLINE, FRAMES_INDEX, frame_captions=CAPTIONS
    )
    assert first == second
