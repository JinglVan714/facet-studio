"""Tests for mode-aware Writer output validation."""

from __future__ import annotations

import json
from pathlib import Path

from facet_studio.writing_v3 import one_call_writer as writer

PACK = {
    "claims": [
        {"claim_id": "c1", "evidence_ids": ["e1"]},
        {"claim_id": "c2", "evidence_ids": ["e2"]},
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
    ],
    "frames": [
        {"frame_id": "f1", "caption": "画面一", "t_ms": 1500, "file": "frames/f1.jpg"}
    ],
    "sentences": [
        {"sentence_id": "s1", "text": "第一句。"},
        {"sentence_id": "s2", "text": "第二句。"},
        {"sentence_id": "s3", "text": "第三句。"},
    ],
    "segments": [
        {
            "segment_id": "seg1",
            "claim_ids": ["c1"],
            "sentence_ids": ["s1", "s2"],
            "frame_ids": ["f1"],
        },
        {
            "segment_id": "seg2",
            "claim_ids": ["c2"],
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
            "t_end_ms": 2000,
            "text": "第一句。第二句。",
            "sentence_ids": ["s1", "s2"],
        },
        {
            "passage_id": "p2",
            "segment_id": "seg2",
            "t_start_ms": 2000,
            "t_end_ms": 3000,
            "text": "第三句。",
            "sentence_ids": ["s3"],
        },
    ]
}


def _output(spans: list[dict]) -> dict:
    return {
        "plan_header": {"title": "测试"},
        "sections": [
            {
                "section_id": "sec1",
                "heading": "标题",
                "paragraphs": [{"spans": spans}],
            }
        ],
    }


def test_merged_frames_valid_grounding_has_no_issues() -> None:
    output = _output(
        [
            {
                "text": "第一句。",
                "role": "grounded",
                "grounding_ref": {"passage_id": "p1", "quote": "第一句。"},
            },
            {"text": "组织性句子。", "role": "editorial"},
        ]
    )
    issues, report = writer._validate_output_merged_frames(
        output, PACK, PASSAGES["passages"]
    )
    assert issues == []
    assert report["status"] == "complete"
    assert report["counts"]["bound"] == 1
    assert report["counts"]["editorial"] == 1


def test_merged_frames_rejects_ids_missing_ref_and_bad_quote() -> None:
    output = _output(
        [
            {
                "text": "第一句。",
                "role": "grounded",
                "claim_ids": ["c1"],
                "evidence_ids": ["e1"],
                "quote": "第一句。",
                "grounding_ref": {"passage_id": "p1", "quote": "第一句。"},
            },
            {"text": "第二句。", "role": "grounded"},
            {
                "text": "第三句。",
                "role": "grounded",
                "grounding_ref": {"passage_id": "p1", "quote": "第三句。"},
            },
        ]
    )
    issues, report = writer._validate_output_merged_frames(
        output, PACK, PASSAGES["passages"]
    )
    assert any("should not carry claim/evidence IDs" in issue for issue in issues)
    assert any("grounded without grounding_ref" in issue for issue in issues)
    assert any("binding error" in issue for issue in issues)
    assert report["status"] != "complete"


def test_merged_frames_numbers_must_be_bound() -> None:
    output = _output(
        [
            {
                "text": "0.756",
                "role": "grounded",
                "grounding_ref": {"passage_id": "p1", "quote": "第一句。"},
            }
        ]
    )
    issues, report = writer._validate_output_merged_frames(
        output, PACK, PASSAGES["passages"]
    )
    assert any("number '0.756' not in bound evidence" in issue for issue in issues)
    assert report["status"] == "complete"  # binding itself succeeded


def test_full_pack_validation_still_requires_claim_evidence() -> None:
    valid = _output(
        [
            {
                "text": "第一句。",
                "role": "grounded",
                "claim_ids": ["c1"],
                "evidence_ids": ["e1"],
                "quote": "第一句。",
            }
        ]
    )
    assert writer._validate_output(valid, PACK) == []
    editorial_with_binding = _output(
        [
            {
                "text": "组织。",
                "role": "editorial",
                "claim_ids": ["c1"],
            }
        ]
    )
    issues = writer._validate_output(editorial_with_binding, PACK)
    assert any("editorial carries binding" in issue for issue in issues)


def test_validate_only_merged_frames_writes_bindings(tmp_path: Path) -> None:
    output = _output(
        [
            {
                "text": "第一句。",
                "role": "grounded",
                "grounding_ref": {"passage_id": "p1", "quote": "第一句。"},
            }
        ]
    )
    output_path = tmp_path / "output.json"
    pack_path = tmp_path / "pack.json"
    passages_path = tmp_path / "passages.json"
    request_path = tmp_path / "request.json"
    output_path.write_text(json.dumps(output, ensure_ascii=False), encoding="utf-8")
    pack_path.write_text(json.dumps(PACK, ensure_ascii=False), encoding="utf-8")
    passages_path.write_text(
        json.dumps(PASSAGES, ensure_ascii=False), encoding="utf-8"
    )
    request_path.write_text("{}", encoding="utf-8")
    out_dir = tmp_path / "out"
    code = writer.main(
        [
            "--pack",
            str(pack_path),
            "--skill-dir",
            str(tmp_path),
            "--request",
            str(request_path),
            "--out-dir",
            str(out_dir),
            "--validate-only",
            "--view-mode",
            "merged_frames",
            "--passages",
            str(passages_path),
            "--output",
            str(output_path),
        ]
    )
    assert code == 0
    metrics = json.loads((out_dir / "metrics.json").read_text(encoding="utf-8"))
    assert metrics["status"] == "complete"
    assert metrics["binding_status"] == "complete"
    assert (out_dir / "bindings.json").exists()
