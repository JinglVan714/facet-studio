"""Tests for deterministic validation and rendering."""

from __future__ import annotations

from pathlib import Path

from lunograph.writing.validate import render_bundle, validate_article

EDITED = "原文。0.756。"
ARTICLE = "# 标题\n\n这是第一段，数字 0.756。\n\n这是第二段，引用“原文。0.756。”。"

SENTENCES = [
    {
        "sentence_id": "seg1-s001",
        "segment_id": "seg1",
        "t_start_ms": 0,
        "t_end_ms": 1000,
        "text": "原文。",
    },
    {
        "sentence_id": "seg1-s002",
        "segment_id": "seg1",
        "t_start_ms": 1000,
        "t_end_ms": 2000,
        "text": "0.756。",
    },
]

PACK = {
    "pack_id": "ep3_test",
    "segments": [
        {
            "segment_id": "seg1",
            "label": "A",
            "t_start_ms": 0,
            "t_end_ms": 2000,
            "claim_ids": ["c1"],
            "sentence_ids": ["seg1-s001", "seg1-s002"],
            "frame_ids": [],
        }
    ],
    "claims": [
        {
            "claim_id": "c1",
            "segment_id": "seg1",
            "text": "原文和 0.756",
            "status": "supported",
            "scope": "",
            "evidence_ids": ["e1"],
            "sentence_ids": ["seg1-s001", "seg1-s002"],
            "t_start_ms": 0,
            "t_end_ms": 2000,
        }
    ],
    "evidence": [
        {
            "evidence_id": "e1",
            "claim_ids": ["c1"],
            "quote": "原文。0.756。",
            "t_start_ms": 0,
            "t_end_ms": 2000,
            "sentence_ids": ["seg1-s001", "seg1-s002"],
        }
    ],
    "frames": [],
    "gaps": [],
    "conflicts": [],
}

SOURCE_MAP = {
    "blocks": [
        {
            "block_index": 0,
            "segment_id": "seg1",
            "label": "A",
            "text_start": 0,
            "text_end": len(EDITED),
            "sentence_ids": ["seg1-s001", "seg1-s002"],
            "passage_ids": [],
            "claim_ids": ["c1"],
            "frames": [],
        }
    ]
}


def _validate(article: str = ARTICLE):
    return validate_article(
        article,
        edited_text=EDITED,
        pack=PACK,
        sentences=SENTENCES,
        source_map=SOURCE_MAP,
    )


def test_validate_article_reports_structure_and_binding() -> None:
    report = _validate()
    assert report["status"] in {"complete", "partial"}
    assert report["structure"]["ok"] is True
    assert report["reader_hygiene"]["ok"] is True
    assert report["quote_hygiene"]["kept"] >= 1
    assert report["binding"]["counts"]["facts"]["bound"] >= 1
    assert "article" in report


def test_source_line_is_not_a_binding_fact() -> None:
    article = (
        ARTICLE
        + "\n\n来源：B 站视频（BV1ACbi6DEvC；标题、发布日期与链接未提供）。"
    )
    report = _validate(article)
    assert report["binding"]["status"] == "complete"
    assert report["binding"]["unsupported_facts"] == []
    assert "BV1ACbi6DEvC" in report["article"]


def test_model_knowledge_terms_are_editorial_not_hard_facts() -> None:
    article = (
        ARTICLE
        + "\n\n补充术语：Programmatic Tool Calling，数字仍是 0.756。"
    )
    report = _validate(article)
    assert report["binding"]["status"] == "complete"
    assert report["binding"]["unsupported_facts"] == []
    values = {item["value"] for item in report["binding"]["editorial_terms"]}
    assert {"Programmatic", "Tool", "Calling"} <= values
    assert report["binding"]["counts"]["facts"]["editorial"] >= 3
    assert report["status"] == "complete"


def test_unsupported_number_still_fails_binding() -> None:
    article = ARTICLE + "\n\n另一个数字 9.999。"
    report = _validate(article)
    assert report["binding"]["status"] == "partial"
    assert report["binding"]["unsupported_facts"]
    assert all(
        item["kind"] != "latin"
        for item in report["binding"]["unsupported_facts"]
    )
    assert "binding" in report["failures"]
    assert report["status"] == "partial"


def test_reader_hygiene_allows_content_word_audit() -> None:
    report = _validate("# 标题\n\n视频没有给出任何审计或评估。\n\n第二段。")
    assert report["reader_hygiene"]["ok"] is True


def test_reader_hygiene_flags_ids_and_timecodes() -> None:
    report = _validate("# 标题\n\n段落 c_abc，时间 00:12。\n\n第二段。")
    assert report["reader_hygiene"]["ok"] is False
    kinds = {problem["kind"] for problem in report["reader_hygiene"]["problems"]}
    assert "internal_id" in kinds
    assert "timecode" in kinds
    assert report["status"] == "partial"


def test_code_fences_are_stripped() -> None:
    report = _validate("# 标题\n\n第一段。\n\n```\ncode\n```\n\n第二段。")
    assert report["code_fences_removed"] == 2
    assert report["structure"]["ok"] is True
    assert "```" not in report["article"]


def test_structure_requires_single_h1() -> None:
    report = _validate("没有标题。\n\n第二段。")
    assert report["structure"]["ok"] is False
    assert "structure" in report["failures"]


def test_render_bundle_writes_outputs(tmp_path: Path) -> None:
    report = _validate()
    class Skill:
        skill_id = "reader_first_explainer"
        version = "0.1.0"
        content_hash = "hash"
        hash_ok = True

    rendered = render_bundle(
        tmp_path,
        request={"request_hash": "req_hash"},
        skill=Skill(),
        context={"profile": "full_text", "context_hash": "ctx", "coverage": {}},
        validation=report,
    )
    assert (tmp_path / "reader.md").exists()
    assert (tmp_path / "audit.json").exists()
    assert (tmp_path / "citations.json").exists()
    assert rendered["reader"].endswith("reader.md")
    audit = (tmp_path / "audit.json").read_text(encoding="utf-8")
    assert "writing-audit-v1" in audit
