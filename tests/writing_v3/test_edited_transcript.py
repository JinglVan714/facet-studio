"""Tests for the deterministic edited-transcript renderer."""

from __future__ import annotations

import hashlib

import pytest

from lunograph.writing_v3 import edited_transcript

PACK = {
    "claims": [
        {
            "claim_id": "c1",
            "segment_id": "seg1",
            "status": "supported",
            "scope": "",
            "text": "CLAIM-ONLY-TEXT-1",
            "evidence_ids": ["e1"],
        },
        {
            "claim_id": "c2",
            "segment_id": "seg1",
            "status": "supported",
            "scope": "",
            "text": "CLAIM-ONLY-TEXT-2",
            "evidence_ids": ["e2"],
        },
        {
            "claim_id": "c3",
            "segment_id": "seg2",
            "status": "bounded",
            "scope": "只在这个范围",
            "text": "CLAIM-ONLY-TEXT-3",
            "evidence_ids": ["e3"],
        },
        {
            "claim_id": "c4",
            "segment_id": "seg1",
            "status": "supported",
            "scope": "",
            "text": "CLAIM-ONLY-TEXT-4",
            "evidence_ids": ["e4"],
        },
    ],
    "evidence": [
        {
            "evidence_id": "e1",
            "claim_ids": ["c1"],
            "quote": "第一句。",
            "sentence_ids": ["s1"],
            "t_start_ms": 0,
            "t_end_ms": 1000,
        },
        {
            "evidence_id": "e2",
            "claim_ids": ["c2"],
            "quote": "第三句。",
            "sentence_ids": ["s3"],
            "t_start_ms": 2000,
            "t_end_ms": 3000,
        },
        {
            "evidence_id": "e3",
            "claim_ids": ["c3"],
            "quote": "第六句。",
            "sentence_ids": ["s6"],
            "t_start_ms": 5000,
            "t_end_ms": 6000,
        },
        {
            "evidence_id": "e4",
            "claim_ids": ["c4"],
            "quote": "第三句。",
            "sentence_ids": ["s3"],
            "t_start_ms": 2000,
            "t_end_ms": 3000,
        },
    ],
    "sentences": [
        {"sentence_id": "s1", "segment_id": "seg1", "text": "第一句。"},
        {"sentence_id": "s3", "segment_id": "seg1", "text": "第三句。"},
        {"sentence_id": "s6", "segment_id": "seg2", "text": "第六句。"},
    ],
    "segments": [
        {
            "segment_id": "seg1",
            "label": "第一段",
            "claim_ids": ["c1", "c2", "c4"],
            "sentence_ids": ["s1", "s2", "s3", "s4"],
            "frame_ids": ["f1", "f2"],
        },
        {
            "segment_id": "seg2",
            "label": "",
            "claim_ids": ["c3"],
            "sentence_ids": ["s5", "s6", "s7", "s8"],
            "frame_ids": ["f3"],
        },
    ],
    "frames": [
        {"frame_id": "f1", "caption": "画面一"},
        {"frame_id": "f2", "caption": ""},
        {"frame_id": "f3", "caption": "画面三\n第二行"},
    ],
}

SENTENCES = [
    {"sentence_id": "s1", "segment_id": "seg1", "text": "第一句。"},
    {"sentence_id": "s2", "segment_id": "seg1", "text": "第二句。"},
    {"sentence_id": "s3", "segment_id": "seg1", "text": "第三句。"},
    {"sentence_id": "s4", "segment_id": "seg1", "text": "第四句。"},
    {"sentence_id": "s5", "segment_id": "seg2", "text": "第五句。"},
    {"sentence_id": "s6", "segment_id": "seg2", "text": "第六句。"},
    {"sentence_id": "s7", "segment_id": "seg2", "text": "第七句。"},
    {"sentence_id": "s8", "segment_id": "seg2", "text": "第八句。"},
]

PASSAGES = {
    "passages": [
        {
            "passage_id": "p1",
            "segment_id": "seg1",
            "sentence_ids": ["s1", "s2", "s3", "s4"],
            "t_start_ms": 0,
            "t_end_ms": 4000,
            "text": "第一句。第二句。第三句。第四句。",
        },
        {
            "passage_id": "p2",
            "segment_id": "seg2",
            "sentence_ids": ["s5", "s6", "s7", "s8"],
            "t_start_ms": 5000,
            "t_end_ms": 9000,
            "text": "第五句。第六句。第七句。第八句。",
        },
    ]
}


def _build(**kwargs):
    return edited_transcript.build_edited_transcript(
        PACK,
        PASSAGES["passages"],
        SENTENCES,
        **kwargs,
    )


def test_full_view_is_linear_and_carries_no_ids_or_timecodes() -> None:
    result = _build(mode="full")
    text = result["text"]
    assert result["mode"] == "full"
    assert "## 第一段" in text
    assert "## 第2段" in text
    assert "第一句。第二句。第三句。第四句。" in text
    assert "第五句。" in text
    assert "第七句。第八句。" in text
    assert "（画面1：画面一）" in text
    assert "（画面1：画面三 / 第二行）" in text
    assert "CLAIM-ONLY-TEXT" not in text
    assert "p1" not in text
    assert "s1" not in text
    assert "0.00" not in text
    assert "f1" not in text


def test_full_view_also_marks_bounded_sentences_in_place() -> None:
    result = _build(mode="full")
    assert "（限制：只在这个范围）第六句。" in result["text"]
    block = result["source_map"]["blocks"][1]
    assert block["boundary_sentence_ids"] == ["s6"]
    assert block["boundary_scopes"] == {"s6": "只在这个范围"}


def test_full_view_drops_empty_frame_captions() -> None:
    result = _build(mode="full")
    assert result["text"].count("（画面") == 2
    frames = result["source_map"]["blocks"][0]["frames"]
    assert [item["frame_id"] for item in frames] == ["f1"]


def test_anchored_view_uses_anchor_neighbours_and_dedupes() -> None:
    result = _build(mode="anchored", neighbor=1)
    text = result["text"]
    assert result["mode"] == "anchored"
    assert "第一句。" in text
    assert "第二句。" in text
    assert "第三句。" in text
    assert "第四句。" in text
    assert "第五句。" in text
    assert "第六句。" in text
    assert "第七句。" in text
    assert "第八句。" not in text
    assert text.count("第三句。") == 1
    blocks = result["source_map"]["blocks"]
    assert blocks[0]["sentence_ids"] == ["s1", "s2", "s3", "s4"]
    assert blocks[1]["sentence_ids"] == ["s5", "s6", "s7"]


def test_anchored_view_marks_bounded_sentences() -> None:
    result = _build(mode="anchored", neighbor=0)
    text = result["text"]
    assert "（限制：只在这个范围）第六句。" in text
    assert "（限制）第一句。" not in text
    block = result["source_map"]["blocks"][1]
    assert block["boundary_sentence_ids"] == ["s6"]
    assert block["boundary_scopes"] == {"s6": "只在这个范围"}
    assert block["sentence_ids"] == ["s6"]


def test_anchored_view_neighbor_zero_is_strict() -> None:
    result = _build(mode="anchored", neighbor=0)
    text = result["text"]
    assert "第一句。" in text
    assert "第三句。" in text
    assert "第六句。" in text
    assert "第二句。" not in text
    assert "第五句。" not in text


def test_source_map_offsets_exactly_cover_blocks() -> None:
    result = _build(mode="full")
    text = result["text"]
    blocks = result["source_map"]["blocks"]
    assert blocks
    for index, block in enumerate(blocks):
        chunk = text[block["text_start"] : block["text_end"]]
        assert chunk.startswith("## ")
        assert chunk == chunk.rstrip()
        if index < len(blocks) - 1:
            assert text[block["text_end"] : block["text_end"] + 2] == "\n\n"
    assert result["source_map"]["text_sha256"] == hashlib.sha256(
        text.encode("utf-8")
    ).hexdigest()
    assert result["source_map"]["text_chars"] == len(text)


def test_anchored_source_map_keeps_claim_and_passage_ids_for_audit() -> None:
    result = _build(mode="anchored", neighbor=1)
    block = result["source_map"]["blocks"][1]
    assert block["segment_id"] == "seg2"
    assert block["passage_ids"] == ["p2"]
    assert block["claim_ids"] == ["c3"]
    assert block["boundary_sentence_ids"] == ["s6"]


def test_auto_chooses_full_when_selection_saves_little() -> None:
    result = _build(mode="auto", auto_ratio=3.0)
    assert result["mode"] == "full"
    assert result["decision"]["reason"] == "full_within_ratio"


def test_auto_chooses_anchored_when_selection_saves_enough() -> None:
    result = _build(mode="auto", auto_ratio=0.5)
    assert result["mode"] == "anchored"
    assert result["decision"]["reason"] == "anchored_saves_more_than_ratio"


def test_explicit_mode_overrides_auto() -> None:
    result = _build(mode="anchored", auto_ratio=100.0)
    assert result["mode"] == "anchored"
    assert result["decision"]["reason"] == "explicit"


def test_budget_is_advisory_and_never_truncates() -> None:
    result = _build(mode="full", budget_chars=1)
    assert result["decision"]["over_budget"] is True
    assert result["decision"]["budget_excess_chars"] > 0
    assert "第一句。" in result["text"]
    assert "第八句。" in result["text"]


def test_same_input_same_output() -> None:
    first = _build(mode="anchored", neighbor=1)
    second = _build(mode="anchored", neighbor=1)
    assert first["text"] == second["text"]
    assert first["source_map"] == second["source_map"]
    assert first["decision"] == second["decision"]


def test_anchored_requires_sentences() -> None:
    with pytest.raises(ValueError):
        edited_transcript.build_edited_transcript(
            PACK, PASSAGES["passages"], None, mode="anchored"
        )


def test_full_mode_does_not_require_sentences() -> None:
    result = edited_transcript.build_edited_transcript(
        PACK, PASSAGES["passages"], None, mode="full"
    )
    assert result["mode"] == "full"
    assert "第一句。" in result["text"]
