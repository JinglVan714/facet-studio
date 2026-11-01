"""Tests for the merged_frames grounding adapter."""

from __future__ import annotations

import json
from pathlib import Path

from lunograph.writing_v3 import bind_merged_frames

PACK = {
    "claims": [
        {"claim_id": "c1", "evidence_ids": ["e1"]},
        {"claim_id": "c2", "evidence_ids": ["e2"]},
        {"claim_id": "c3", "evidence_ids": ["e3"]},
    ],
    "evidence": [
        {
            "evidence_id": "e1",
            "claim_ids": ["c1"],
            "quote": "第一句。第二句。",
            "sentence_ids": ["s1", "s2"],
            "t_start_ms": 0,
            "t_end_ms": 2000,
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
            "quote": "第三句。补充。",
            "sentence_ids": ["s3"],
            "t_start_ms": 2000,
            "t_end_ms": 3500,
        },
    ],
    "frames": [
        {
            "frame_id": "f1",
            "caption": "画面一 看这里",
            "t_ms": 1500,
        }
    ],
    "sentences": [
        {"sentence_id": "s1", "text": "第一句。"},
        {"sentence_id": "s2", "text": "第二句。"},
        {"sentence_id": "s3", "text": "第三句。"},
        {"sentence_id": "s4", "text": "第四句。"},
    ],
    "segments": [
        {
            "segment_id": "seg1",
            "claim_ids": ["c1"],
            "sentence_ids": ["s1", "s2", "s4"],
            "frame_ids": ["f1"],
        },
        {
            "segment_id": "seg2",
            "claim_ids": ["c2", "c3"],
            "sentence_ids": ["s3"],
            "frame_ids": [],
        },
    ],
}

PASSAGES = {
    "passages": [
        {
            "passage_id": "p1",
            "segment_id": "seg1",
            "t_start_ms": 0,
            "t_end_ms": 2500,
            "text": "第一句。第二句。第四句。",
            "sentence_ids": ["s1", "s2", "s4"],
        },
        {
            "passage_id": "p2",
            "segment_id": "seg2",
            "t_start_ms": 2000,
            "t_end_ms": 3500,
            "text": "第三句。",
            "sentence_ids": ["s3"],
        },
    ]
}


def _output(spans: list[dict]) -> dict:
    return {
        "sections": [
            {"section_id": "sec1", "paragraphs": [{"spans": spans}]}
        ]
    }


def test_exact_and_substring_bind_to_evidence() -> None:
    exact = bind_merged_frames.bind_span(
        {"role": "grounded", "grounding_ref": {"passage_id": "p1", "quote": "第一句。"}},
        span_ref="s0/p0/sp0",
        pack=PACK,
        passages_by_id={p["passage_id"]: p for p in PASSAGES["passages"]},
    )
    assert exact["status"] == "bound"
    assert exact["evidence_ids"] == ["e1"]
    assert exact["claim_ids"] == ["c1"]
    assert exact["timecode"] == {"t_start_ms": 0, "t_end_ms": 2000}
    substring = bind_merged_frames.bind_span(
        {"role": "grounded", "grounding_ref": {"passage_id": "p1", "quote": "第二句。"}},
        span_ref="s0/p0/sp1",
        pack=PACK,
        passages_by_id={p["passage_id"]: p for p in PASSAGES["passages"]},
    )
    assert substring["status"] == "bound"
    assert substring["evidence_ids"] == ["e1"]


def test_unbound_quote_and_missing_ref() -> None:
    passages = {p["passage_id"]: p for p in PASSAGES["passages"]}
    unbound = bind_merged_frames.bind_span(
        {"role": "grounded", "grounding_ref": {"passage_id": "p1", "quote": "第四句。"}},
        span_ref="s0/p0/sp0",
        pack=PACK,
        passages_by_id=passages,
    )
    assert unbound["status"] == "unbound"
    missing = bind_merged_frames.bind_span(
        {"role": "grounded"},
        span_ref="s0/p0/sp1",
        pack=PACK,
        passages_by_id=passages,
    )
    assert missing["status"] == "error"
    assert "missing_grounding_ref" in missing["notes"]


def test_frame_binding_and_unknown_frame() -> None:
    passages = {p["passage_id"]: p for p in PASSAGES["passages"]}
    frame = bind_merged_frames.bind_span(
        {"role": "grounded", "grounding_ref": {"frame_id": "f1", "caption": "看这里"}},
        span_ref="s0/p0/sp0",
        pack=PACK,
        passages_by_id=passages,
    )
    assert frame["status"] == "frame_bound"
    assert frame["frame"]["frame_id"] == "f1"
    assert frame["frame"]["t_ms"] == 1500
    assert frame["frame"]["caption_matches"] is True
    unknown = bind_merged_frames.bind_span(
        {"role": "grounded", "grounding_ref": {"frame_id": "missing"}},
        span_ref="s0/p0/sp1",
        pack=PACK,
        passages_by_id=passages,
    )
    assert unknown["status"] == "error"
    assert "unknown_frame:missing" in unknown["notes"]


def test_ambiguous_and_multi_evidence_are_reported() -> None:
    passages = {p["passage_id"]: p for p in PASSAGES["passages"]}
    ambiguous = bind_merged_frames.bind_span(
        {"role": "grounded", "grounding_ref": {"passage_id": "p2", "quote": "第三句。"}},
        span_ref="s0/p0/sp0",
        pack=PACK,
        passages_by_id=passages,
    )
    assert ambiguous["status"] == "ambiguous"
    assert set(ambiguous["evidence_ids"]) == {"e2", "e3"}
    multi = bind_merged_frames.bind_span(
        {"role": "grounded", "grounding_ref": {"quote": "第一句。第二句。第三句。"}},
        span_ref="s0/p0/sp1",
        pack=PACK,
        passages_by_id=passages,
    )
    assert multi["status"] == "partial"
    assert multi["evidence_ids"] == ["e1", "e2"]
    assert "multi_evidence_quote" in multi["notes"]


def test_output_counts_and_status() -> None:
    output = _output(
        [
            {"role": "grounded", "grounding_ref": {"passage_id": "p1", "quote": "第一句。"}},
            {"role": "grounded", "grounding_ref": {"passage_id": "p1", "quote": "第四句。"}},
            {"role": "grounded", "grounding_ref": {"frame_id": "f1", "caption": "看这里"}},
            {"role": "grounded"},
            {"role": "editorial", "text": "组织性句子"},
        ]
    )
    report = bind_merged_frames.bind_output(
        output, pack=PACK, passages=PASSAGES["passages"]
    )
    assert report["status"] == "partial"
    assert report["counts"] == {
        "grounded": 4,
        "bound": 1,
        "partial": 0,
        "ambiguous": 0,
        "unbound": 1,
        "frame_bound": 1,
        "error": 1,
        "editorial": 1,
    }


def test_cli_writes_report(tmp_path: Path) -> None:
    output = _output(
        [{"role": "grounded", "grounding_ref": {"passage_id": "p1", "quote": "第一句。"}}]
    )
    output_path = tmp_path / "output.json"
    pack_path = tmp_path / "pack.json"
    passages_path = tmp_path / "passages.json"
    output_path.write_text(json.dumps(output, ensure_ascii=False), encoding="utf-8")
    pack_path.write_text(json.dumps(PACK, ensure_ascii=False), encoding="utf-8")
    passages_path.write_text(
        json.dumps(PASSAGES, ensure_ascii=False), encoding="utf-8"
    )
    out_path = tmp_path / "bindings.json"
    code = bind_merged_frames.main(
        [
            "--output",
            str(output_path),
            "--pack",
            str(pack_path),
            "--passages",
            str(passages_path),
            "--out",
            str(out_path),
        ]
    )
    assert code == 0
    report = json.loads(out_path.read_text(encoding="utf-8"))
    assert report["status"] == "complete"
    assert report["bindings"][0]["evidence_ids"] == ["e1"]
