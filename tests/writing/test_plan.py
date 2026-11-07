"""Tests for the pre-Writer article plan."""

from __future__ import annotations

import json
from pathlib import Path

from facet_studio.writing.planner import plan_article
from facet_studio.writing.prompt import build_repair_user, build_user_prompt
from facet_studio.writing.request import validate_request

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

CONTEXT = {
    "profile": "full_text",
    "text": "先收集问题。然后把问题交给模型。最后拿回结果。",
    "context_hash": "ctx",
    "claims": [],
    "frames": [],
}

PAYLOAD = {
    "title": "一句话怎么把三步串起来",
    "controlling_idea": "先收集、再交给模型、最后拿回结果，三步构成一条链。",
    "toc": [
        {
            "index": 1,
            "heading": "1. 先收集问题：为什么不能直接问模型",
            "promise": "读者知道第一步为什么存在。",
            "key_example": "先把问题收进一个输入框。",
            "visual": {"kind": "diagram", "intent": "画出三步链路"},
            "takeaway": "不先收集，模型拿不到可执行的问题。",
        },
        {
            "index": 2,
            "heading": "2. 把问题交给模型：中间发生了什么",
            "promise": "读者能复述模型决定和工具调用。",
            "key_example": "模型决定调用哪个工具。",
            "visual": {"kind": "diagram", "intent": "画出模型→工具→结果"},
            "takeaway": "模型负责决策，工具负责执行。",
        },
        {
            "index": 3,
            "heading": "3. 拿回结果：为什么还要再交给模型",
            "promise": "读者理解结果回流的原因。",
            "key_example": "工具返回结果后再交给模型。",
            "visual": {"kind": "none", "intent": ""},
            "takeaway": "结果不回流，模型无法给出最终回答。",
        },
    ],
}


class _Usage:
    def as_dict(self):
        return {"total_tokens": 20}


class _Response:
    text = json.dumps(PAYLOAD, ensure_ascii=False)
    usage = _Usage()
    latency_ms = 7
    cached = False
    finish_reason = "stop"


class _Provider:
    model = "fake"

    def complete(self, **kwargs):
        return _Response()


def test_plan_article_cleans_numbering_and_returns_toc(tmp_path: Path) -> None:
    plan = plan_article(
        validate_request(REQUEST),
        CONTEXT,
        tmp_path,
        run=True,
        provider=_Provider(),
    )
    assert plan["status"] == "complete"
    assert plan["title"] == "一句话怎么把三步串起来"
    assert [section["heading"] for section in plan["toc"]] == [
        "先收集问题：为什么不能直接问模型",
        "把问题交给模型：中间发生了什么",
        "拿回结果：为什么还要再交给模型",
    ]
    assert plan["usage"] == {"total_tokens": 20}
    assert len(plan["plan_hash"]) == 64
    assert (tmp_path / "plan.json").exists()


def test_user_prompt_includes_writing_plan() -> None:
    prompt = build_user_prompt(
        validate_request(REQUEST),
        CONTEXT,
        writing_plan=PAYLOAD,
    )
    assert '"writing_plan"' in prompt
    assert "先收集问题" in prompt
    assert "evidence_text" in prompt


def test_repair_prompt_includes_writing_plan() -> None:
    prompt = build_repair_user(
        validate_request(REQUEST),
        CONTEXT,
        "# 草稿\n\n正文。",
        {"unsupported_facts": []},
        writing_plan=PAYLOAD,
    )
    assert '"writing_plan"' in prompt
    assert "先收集问题" in prompt
    assert '"draft"' in prompt
