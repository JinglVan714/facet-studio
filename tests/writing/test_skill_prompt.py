"""Tests for skill loading, prompt assembly, and Writer dry-run."""

from __future__ import annotations

import json
from pathlib import Path

from facet_studio.writing.prompt import (
    build_repair_user,
    build_system_prompt,
    build_user_prompt,
)
from facet_studio.writing.request import validate_request
from facet_studio.writing.skill import load_skill
from facet_studio.writing.writer import run_writer

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SKILL_DIR = PROJECT_ROOT / "skills" / "writing" / "reader_first_explainer"

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


def test_load_skill_package() -> None:
    skill = load_skill(SKILL_DIR)
    assert skill.skill_id == "reader_first_explainer"
    assert skill.version == "2.0.0"
    assert skill.status == "draft_v2"
    assert skill.hash_ok is True
    assert "The one rule that matters" in skill.body
    assert "writing_brief" in skill.body
    assert "Terms and explanation" in skill.body
    assert "Voice" in skill.body
    assert "Write what the video has" in skill.body
    assert "Planning 不是 outline" in skill.planning
    structure = (SKILL_DIR / "references" / "structure.md").read_text(
        encoding="utf-8-sig"
    )
    assert "H2 = 目录" in structure
    assert "Title / TOC" in skill.rubric
    assert "Examples" in skill.examples


def test_build_prompts_for_full_text() -> None:
    skill = load_skill(SKILL_DIR)
    system = build_system_prompt(skill, input_kind="text")
    assert "Reader-first explainer" in system
    assert "evidence_text" in system
    assert "Return only the Markdown article" in system
    user = build_user_prompt(
        validate_request(REQUEST),
        {"profile": "full_text", "text": "先收集问题。"},
    )
    assert '"evidence_text":"先收集问题。"' in user
    assert "claim_view" not in user


def test_build_prompts_include_reader_profile() -> None:
    skill = load_skill(SKILL_DIR)
    default_user = build_user_prompt(
        validate_request(REQUEST), {"profile": "full_text", "text": "证据。"}
    )
    assert "smart general reader" in default_user
    custom = validate_request(
        dict(REQUEST, reader_profile="AI beginner; explain terms more")
    )
    custom_user = build_user_prompt(
        custom, {"profile": "full_text", "text": "证据。"}
    )
    assert "AI beginner; explain terms more" in custom_user


def test_build_prompts_for_claim_view() -> None:
    skill = load_skill(SKILL_DIR)
    system = build_system_prompt(skill, input_kind="claim")
    assert "claim_view" in system
    user = build_user_prompt(
        validate_request(REQUEST),
        {
            "profile": "claim_lean",
            "claims": [{"claim_id": "c1", "text": "主张"}],
            "frames": [],
        },
    )
    assert '"claim_view"' in user
    assert '"c1"' in user


def test_writer_brief_payload_drops_planner_only_fields_and_spare_titles() -> None:
    brief = {
        "core_argument": "核心判断",
        "challenge": "planner-only",
        "evidence_status": ["single case"],
        "title_check": {"chosen": "标题", "issues": []},
        "titles": [
            {"text": "标题", "chosen": True},
            {"text": "备选", "chosen": False},
        ],
        "concept_ledger": [{"term": "点积"}],
    }
    user = build_user_prompt(
        validate_request(REQUEST),
        {"profile": "full_text", "text": "证据。"},
        writing_brief=brief,
    )
    payload = json.loads(user)
    writing_brief = payload["writing_brief"]
    assert "challenge" not in writing_brief
    assert "evidence_status" not in writing_brief
    assert writing_brief["titles"] == [{"text": "标题", "chosen": True}]
    assert writing_brief["title_check"]["chosen"] == "标题"


def test_build_repair_user_includes_draft_and_issues() -> None:
    user = build_repair_user(
        validate_request(REQUEST),
        {"profile": "full_text", "text": "证据。"},
        "# 标题\n\n草稿。",
        {"unsupported_facts": [{"value": "GB"}]},
    )
    assert '"draft":"# 标题' in user
    assert '"issues"' in user
    assert '"GB"' in user
    assert '"evidence_text":"证据。"' in user


def test_writer_dry_run_writes_prompts_without_provider(tmp_path) -> None:
    skill = load_skill(SKILL_DIR)
    context = {
        "profile": "full_text",
        "text": "先收集问题。",
        "context_hash": "ctx_hash",
        "claims": [],
        "frames": [],
    }
    result = run_writer(
        request=validate_request(REQUEST),
        skill=skill,
        context=context,
        out_dir=tmp_path,
        run=False,
    )
    assert result["status"] == "dry_run"
    assert (tmp_path / "prompts" / "system.txt").exists()
    assert (tmp_path / "prompts" / "user.txt").exists()
    manifest = result["manifest"]
    assert manifest["status"] == "dry_run"
    assert manifest["skill"]["skill_id"] == "reader_first_explainer"
    assert manifest["context"]["profile"] == "full_text"
    assert manifest["usage"] is None
