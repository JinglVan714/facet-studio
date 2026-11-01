"""Tests for the deterministic comprehension view builder."""

from __future__ import annotations

import json
from pathlib import Path

from lunograph.writing_v3 import comprehension_view

PACK = {
    "claims": [
        {
            "claim_id": "c1",
            "text": "第一句。",
            "status": "supported",
            "scope": "",
            "evidence_ids": ["e1"],
        },
        {
            "claim_id": "c2",
            "text": "第三句。",
            "status": "bounded",
            "scope": "只在这种情况下",
            "evidence_ids": ["e2"],
        },
    ],
    "evidence": [
        {
            "evidence_id": "e1",
            "quote": "第一句。",
            "sentence_ids": ["s1"],
            "t_start_ms": 0,
            "t_end_ms": 1000,
        },
        {
            "evidence_id": "e2",
            "quote": "第三句。",
            "sentence_ids": ["s3"],
            "t_start_ms": 2000,
            "t_end_ms": 3000,
        },
    ],
    "sentences": [
        {"sentence_id": "s1", "text": "第一句。"},
        {"sentence_id": "s2", "text": "第二句。"},
        {"sentence_id": "s3", "text": "第三句。"},
    ],
    "segments": [
        {
            "segment_id": "seg1",
            "label": "第一段",
            "claim_ids": ["c1"],
            "sentence_ids": ["s1", "s2"],
            "frame_ids": ["f1"],
        },
        {
            "segment_id": "seg2",
            "label": "第二段",
            "claim_ids": ["c2"],
            "sentence_ids": ["s3"],
            "frame_ids": ["f2"],
        },
    ],
    "frames": [
        {"frame_id": "f1", "caption": "第一段帧"},
        {"frame_id": "f2", "caption": "第二段帧"},
    ],
    "gaps": [{"description": "证据缺口"}],
    "conflicts": [{"description": "冲突"}],
}

PASSAGES = {
    "passages": [
        {
            "passage_id": "seg1-p01",
            "segment_id": "seg1",
            "t_start_ms": 0,
            "t_end_ms": 1500,
            "text": "第一句。第二句。",
        },
        {
            "passage_id": "seg2-p01",
            "segment_id": "seg2",
            "t_start_ms": 2000,
            "t_end_ms": 3000,
            "text": "第三句。",
        },
    ]
}


def test_lean_cw0_keeps_anchor_context_only() -> None:
    view = comprehension_view.build_lean_cw0_view(PACK)
    assert view["schema"] == "comprehension-view-v1"
    assert view["mode"] == "lean_cw0"
    assert view["segments"][0]["context"] == ["第一句。"]
    assert view["segments"][1]["context"] == ["第三句。"]
    assert view["segments"][0]["claims"][0]["evidence"][0]["span"] == [0, 4]
    bounded = view["segments"][1]["claims"][0]
    assert bounded["status"] == "bounded"
    assert bounded["scope"] == "只在这种情况下"
    assert view["gaps"] == [{"description": "证据缺口"}]
    assert view["conflicts"] == [{"description": "冲突"}]


def test_merged_frames_has_no_claims_or_evidence() -> None:
    view = comprehension_view.build_merged_frames_view(
        PACK, PASSAGES["passages"]
    )
    assert view["schema"] == "comprehension-view-v1"
    assert view["mode"] == "merged_frames"
    assert len(view["segments"]) == 2
    assert view["segments"][0]["passages"][0]["passage_id"] == "seg1-p01"
    assert view["segments"][0]["frames"] == [
        {"frame_id": "f1", "caption": "第一段帧"}
    ]
    rendered = comprehension_view.render_merged_frames_text(view)
    assert "[seg1-p01 0.00-1.50s] 第一句。第二句。" in rendered
    assert "frames: [f1] 第一段帧" in rendered
    assert "claim" not in rendered
    assert "evidence" not in rendered


def test_builder_respects_explicit_and_budget_modes() -> None:
    merged = comprehension_view.build_comprehension_view(
        PACK, PASSAGES["passages"], mode="merged_frames"
    )
    assert merged["mode"] == "merged_frames"
    assert merged["decision"]["reason"] == "explicit"
    lean = comprehension_view.build_comprehension_view(
        PACK, PASSAGES["passages"], mode="lean_cw0"
    )
    assert lean["mode"] == "lean_cw0"
    within = comprehension_view.build_comprehension_view(
        PACK,
        PASSAGES["passages"],
        mode="auto",
        budget_tokens=10**9,
    )
    assert within["mode"] == "merged_frames"
    assert within["decision"]["reason"] == "merged_frames_within_budget"
    assert within["decision"]["over_budget"] is False
    over = comprehension_view.build_comprehension_view(
        PACK, PASSAGES["passages"], mode="auto", budget_tokens=1
    )
    assert over["mode"] == "lean_cw0"
    assert over["decision"]["reason"] == "merged_frames_over_budget"
    assert over["decision"]["over_budget"] is True
    assert set(over["decision"]["candidates"]) == {
        "merged_frames",
        "lean_cw0",
    }


def test_builder_is_deterministic() -> None:
    first = comprehension_view.build_comprehension_view(
        PACK, PASSAGES["passages"], mode="auto"
    )
    second = comprehension_view.build_comprehension_view(
        PACK, PASSAGES["passages"], mode="auto"
    )
    assert first == second


def test_cli_writes_view_rendered_and_manifest(tmp_path: Path) -> None:
    pack_path = tmp_path / "pack.json"
    passages_path = tmp_path / "passages.json"
    pack_path.write_text(json.dumps(PACK, ensure_ascii=False), encoding="utf-8")
    passages_path.write_text(
        json.dumps(PASSAGES, ensure_ascii=False), encoding="utf-8"
    )
    code = comprehension_view.main(
        [
            "--pack",
            str(pack_path),
            "--passages",
            str(passages_path),
            "--mode",
            "lean_cw0",
            "--out-view",
            str(tmp_path / "view.json"),
            "--out-rendered",
            str(tmp_path / "rendered.txt"),
            "--out-manifest",
            str(tmp_path / "manifest.json"),
        ]
    )
    assert code == 0
    view = json.loads((tmp_path / "view.json").read_text(encoding="utf-8"))
    assert view["mode"] == "lean_cw0"
    assert (tmp_path / "rendered.txt").read_text(encoding="utf-8")
    manifest = json.loads(
        (tmp_path / "manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["mode"] == "lean_cw0"
    assert manifest["reason"] == "explicit"
