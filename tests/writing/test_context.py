"""Tests for request validation and deterministic working-context assembly."""

from __future__ import annotations

import pytest

from facet_studio.writing import (
    build_working_context,
    measure_text,
    select_profile,
    validate_request,
)

TEXT = "先收集问题。然后把问题交给模型。最后拿回结果。"

INDEX = {
    "schema": "consume-index-v1",
    "video_id": "BVtest",
    "segments": [
        {
            "segment_id": "seg1",
            "label": "A",
            "t_start_ms": 0,
            "t_end_ms": 2000,
            "part_id": "part_01",
            "claim_ids": ["c1"],
            "sentence_ids": ["s1", "s2"],
            "frame_ids": ["f1"],
        },
        {
            "segment_id": "seg2",
            "label": "B",
            "t_start_ms": 2000,
            "t_end_ms": 4000,
            "part_id": "part_02",
            "claim_ids": ["c2"],
            "sentence_ids": ["s3", "s4"],
            "frame_ids": ["f2"],
        },
    ],
    "claims": [
        {
            "claim_id": "c1",
            "segment_id": "seg1",
            "status": "supported",
            "kind": "instruction",
            "text": "先收集问题，再交给模型。",
            "scope": "",
            "t_start_ms": 0,
            "t_end_ms": 2000,
            "evidence_ids": ["e1"],
            "sentence_ids": ["s1", "s2"],
            "part_id": "part_01",
        },
        {
            "claim_id": "c2",
            "segment_id": "seg2",
            "status": "bounded",
            "kind": "fact",
            "text": "结果是 0.756，另一个是 0.81。",
            "scope": "这组数据",
            "t_start_ms": 2000,
            "t_end_ms": 4000,
            "evidence_ids": ["e2"],
            "sentence_ids": ["s3", "s4"],
            "part_id": "part_02",
        },
    ],
    "evidence": [
        {
            "evidence_id": "e1",
            "claim_ids": ["c1"],
            "quote": "先收集问题",
            "t_start_ms": 0,
            "t_end_ms": 1000,
            "sentence_ids": ["s1"],
        },
        {
            "evidence_id": "e2",
            "claim_ids": ["c2"],
            "quote": "0.756",
            "t_start_ms": 2000,
            "t_end_ms": 3000,
            "sentence_ids": ["s3"],
        },
    ],
    "sentences": [
        {
            "sentence_id": "s1",
            "segment_id": "seg1",
            "t_start_ms": 0,
            "t_end_ms": 1000,
            "text": "先收集问题。",
            "part_id": "part_01",
        },
        {
            "sentence_id": "s2",
            "segment_id": "seg1",
            "t_start_ms": 1000,
            "t_end_ms": 2000,
            "text": "然后把问题交给模型。",
            "part_id": "part_01",
        },
        {
            "sentence_id": "s3",
            "segment_id": "seg2",
            "t_start_ms": 2000,
            "t_end_ms": 3000,
            "text": "结果是 0.756。",
            "part_id": "part_02",
        },
        {
            "sentence_id": "s4",
            "segment_id": "seg2",
            "t_start_ms": 3000,
            "t_end_ms": 4000,
            "text": "另一个是 0.81。",
            "part_id": "part_02",
        },
    ],
    "frames": [
        {
            "frame_id": "f1",
            "t_ms": 500,
            "file": "frames/f1.jpg",
            "caption": "流程：收集问题",
            "capture_method": "vlm",
            "caption_full_chars": 8,
            "selected": True,
            "segment_ids": ["seg1"],
        },
        {
            "frame_id": "f2",
            "t_ms": 2500,
            "file": "frames/f2.jpg",
            "caption": "分数 0.756",
            "capture_method": "vlm",
            "caption_full_chars": 8,
            "selected": True,
            "segment_ids": ["seg2"],
        },
    ],
    "parts": [
        {
            "part_id": "part_01",
            "segment_ids": ["seg1"],
            "chars": 100,
            "oversize": False,
            "text_start": 0,
            "text_end": 40,
        },
        {
            "part_id": "part_02",
            "segment_ids": ["seg2"],
            "chars": 80,
            "oversize": False,
            "text_start": 42,
            "text_end": 80,
        },
    ],
    "coverage": {"unassigned_blocks": []},
}

REQUEST = {
    "schema_version": "writing-request-v1",
    "request_id": "req_test",
    "video_ids": ["BVtest"],
    "method_id": "reader_first_explainer",
    "form_id": "article",
    "central_question": "它如何工作？",
    "job_to_be_done": "解释机制。",
    "reader_before_state": "不知道机制。",
    "desired_reader_outcome": "能复述机制。",
    "success_criteria": ["能复述机制"],
    "required_information": ["步骤"],
    "forbidden_information": ["外部事实"],
    "language": "zh",
    "platform": "markdown",
    "risk_level": "low",
    "audit_level": "none",
    "sections_required": 1,
}


def _request(**overrides):
    data = dict(REQUEST)
    data.update(overrides)
    return data


def test_validate_request_defaults_and_hash() -> None:
    request = validate_request(_request())
    assert request["schema_version"] == "writing-request-v1"
    assert request["profile_override"] is None
    assert request["request_hash"]
    assert request["media_policy"]["generated_image_policy"] == "editorial_only"


def test_validate_request_rejects_missing_question() -> None:
    data = _request()
    data.pop("central_question")
    with pytest.raises(ValueError, match="central_question"):
        validate_request(data)


def test_validate_request_rejects_bad_audit_level() -> None:
    with pytest.raises(ValueError, match="audit_level"):
        validate_request(_request(audit_level="everything"))


def test_measure_text() -> None:
    measured = measure_text(INDEX, TEXT)
    assert measured["chars"] == len(TEXT)
    assert measured["segments"] == 2
    assert measured["claims"] == 2
    assert measured["duration_ms"] == 4000


def test_select_profile_full_text_default() -> None:
    selection = select_profile(_request(), INDEX, TEXT)
    assert selection["profile"] == "full_text"
    assert selection["claim_unavailable"] is False


def test_select_profile_claim_path() -> None:
    selection = select_profile(_request(audit_level="boundary"), INDEX, TEXT)
    assert selection["profile"] == "claim_lean"
    assert selection["claim_unavailable"] is False


def test_select_profile_claim_fallback() -> None:
    index = dict(INDEX)
    index["claims"] = []
    selection = select_profile(_request(audit_level="boundary"), index, TEXT)
    assert selection["profile"] == "full_text"
    assert selection["claim_unavailable"] is True


def test_select_profile_index_parts_over_budget() -> None:
    selection = select_profile(
        _request(), INDEX, TEXT, context_budget_tokens=1
    )
    assert selection["profile"] == "index_parts"


def test_select_profile_sectioned_deferred() -> None:
    selection = select_profile(_request(sections_required=2), INDEX, TEXT)
    assert selection["profile"] == "sectioned"
    assert selection["deferred"] is True


def test_build_full_text_context() -> None:
    context = build_working_context(INDEX, _request(), TEXT)
    assert context["status"] == "complete"
    assert context["profile"] == "full_text"
    assert context["text"] == TEXT
    assert context["claims"] == []
    assert [frame["frame_id"] for frame in context["frames"]] == ["f1", "f2"]
    assert context["context_hash"]
    assert context["budget"]["over_budget"] is False


def test_build_claim_lean_context() -> None:
    context = build_working_context(
        INDEX, _request(audit_level="boundary"), TEXT
    )
    assert context["profile"] == "claim_lean"
    assert context["text"] == ""
    assert [claim["claim_id"] for claim in context["claims"]] == ["c1", "c2"]
    assert context["claims"][0]["context"]
    assert context["coverage"]["claims_used"] == 2


def test_build_index_parts_context() -> None:
    context = build_working_context(INDEX, _request(), TEXT, profile="index_parts")
    assert context["profile"] == "index_parts"
    assert context["text"] == ""
    assert [part["part_id"] for part in context["parts"]] == [
        "part_01",
        "part_02",
    ]


def test_build_sectioned_is_explicitly_unsupported() -> None:
    context = build_working_context(INDEX, _request(), TEXT, profile="sectioned")
    assert context["status"] == "unsupported_profile"
    assert context["profile"] == "sectioned"


def test_visual_opportunities_reuse_lookup() -> None:
    context = build_working_context(INDEX, _request(), TEXT)
    kinds = {item["kind"] for item in context["visual_opportunities"]}
    assert "real_frame" in kinds
    assert "chart" in kinds or "diagram" in kinds
