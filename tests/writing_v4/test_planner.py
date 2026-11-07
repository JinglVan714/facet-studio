import json
from pathlib import Path

import pytest

from facet_studio.providers.llm import LLMResponse, LLMUsage
from facet_studio.writing_v4.planner import (
    PlanError,
    fallback_plan,
    parse_plan,
    plan_bundle,
)
from facet_studio.writing_v4.skills import form_catalog, load_skill

ROOT = Path(__file__).resolve().parents[2]
SKILLS = ROOT / "skills" / "writing"
CATALOG = form_catalog(SKILLS)


def _plan_text() -> str:
    return json.dumps(
        {
            "central_idea": "先理解反常识，再按三步做对。",
            "reader_goal": "读完能说出为什么旧做法不对，并知道按什么顺序做。",
            "forms": [
                {
                    "form": "wechat_article",
                    "reason": "有完整机制",
                    "angle": "从反常识切入",
                    "brief": "先给反常识，再讲机制和边界。",
                    "must_use_figures": ["fig-01.jpg", "fig-99.jpg"],
                },
                {
                    "form": "xiaohongshu_note",
                    "reason": "有一个能上手的动作",
                    "angle": "只保留最反直觉的动作",
                    "brief": "一条主线覆盖整体。",
                    "must_use_figures": [],
                },
            ],
            "shared_constraints": ["同一组数字和范围", "角度不同"],
        },
        ensure_ascii=False,
    )


class FakeLLM:
    provider = "fake"
    model = "fake-model"

    def __init__(self, text: str):
        self.text = text
        self.call_sink = None

    def complete(self, *, stage, key, system, user, max_tokens=None, temperature=0.0, images=None):
        return LLMResponse(
            text=self.text,
            model=self.model,
            provider=self.provider,
            usage=LLMUsage(prompt_tokens=1, completion_tokens=2, total_tokens=3),
            latency_ms=1,
            finish_reason="stop",
        )


def test_parse_plan_filters_figures_and_forms() -> None:
    plan = parse_plan(
        _plan_text(),
        catalog=CATALOG,
        available_figures=["fig-01.jpg"],
    )
    assert [item.form for item in plan.forms] == [
        "wechat_article",
        "xiaohongshu_note",
    ]
    assert plan.forms[0].must_use_figures == ["fig-01.jpg"]
    assert plan.shared_constraints == ["同一组数字和范围", "角度不同"]
    assert plan.source == "planner"


def test_parse_plan_required_forms_adds_missing() -> None:
    data = json.loads(_plan_text())
    data["forms"] = data["forms"][:1]
    plan = parse_plan(
        json.dumps(data, ensure_ascii=False),
        catalog=CATALOG,
        required_forms=["wechat_article", "xiaohongshu_note"],
    )
    assert [item.form for item in plan.forms] == [
        "wechat_article",
        "xiaohongshu_note",
    ]
    assert plan.forms[1].brief


def test_parse_plan_rejects_invalid_json() -> None:
    with pytest.raises(PlanError):
        parse_plan("not json", catalog=CATALOG)


def test_fallback_plan_prefers_social_forms() -> None:
    plan = fallback_plan(catalog=CATALOG)
    forms = [item.form for item in plan.forms]
    assert "wechat_article" in forms
    assert "xiaohongshu_note" in forms
    assert plan.source == "fallback"


def test_plan_bundle_falls_back_on_provider_error() -> None:
    class Broken:
        provider = "fake"
        model = "fake"
        call_sink = None

        def complete(self, **kwargs):
            raise RuntimeError("boom")

    skill = load_skill(SKILLS / "bundle-planner")
    plan, raw = plan_bundle(
        client=Broken(),
        skill=skill,
        content="这件事的完整内容。",
        catalog=CATALOG,
        request="写个内容包",
        required_forms=["wechat_article", "xiaohongshu_note"],
        available_figures=[],
        video_id="BV1",
    )
    assert plan.source == "fallback"
    assert plan.error and "boom" in plan.error
    assert raw == ""


def test_plan_bundle_parses_valid_plan() -> None:
    skill = load_skill(SKILLS / "bundle-planner")
    plan, raw = plan_bundle(
        client=FakeLLM(_plan_text()),
        skill=skill,
        content="这件事的完整内容。",
        catalog=CATALOG,
        request="写个内容包",
        required_forms=["wechat_article", "xiaohongshu_note"],
        available_figures=["fig-01.jpg"],
        video_id="BV1",
    )
    assert plan.source == "planner"
    assert raw
    assert [item.form for item in plan.forms] == [
        "wechat_article",
        "xiaohongshu_note",
    ]
