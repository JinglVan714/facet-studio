"""Tests for the editorial brief planner."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from facet_studio.writing.brief import _title_check, write_brief
from facet_studio.writing.pipeline import _resolve_brief_mode
from facet_studio.writing.request import validate_request
from facet_studio.writing.skill import load_skill

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SKILL_DIR = PROJECT_ROOT / "skills" / "writing" / "reader_first_explainer"

REQUEST = {
    "schema_version": "writing-request-v1",
    "request_id": "req_brief",
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

SOURCE_MAP = {
    "schema_version": "source-map-v1",
    "topology": "unknown",
    "source_map_hash": "sm",
    "anchors": [{"id": "s1", "quote_or_paraphrase": "0.756"}],
    "numbers": [{"value": "0.756"}],
}

PAYLOAD = {
    "shape": "analytical",
    "reader": {"knows": "知道一点", "asks": "为什么", "wants": "能解释"},
    "core_argument": "固定门槛是错的工具，应该看排名。",
    "source_question": "分数为什么奇怪？",
    "payoff": "理解两条分数带。",
    "throughline": "失败 → 诊断 → 排名。",
    "spine": [
        {"move": "先看到失败", "connector": "because", "anchors": ["s1"]},
        {"move": "解释两条带", "connector": "but", "anchors": ["s1"]},
        {"move": "改看排名", "connector": "therefore", "anchors": ["s1"]},
    ],
    "titles": [
        {"text": "0.756 的蝙蝠", "promise": "解释分数", "fulfilled_by": "move 2"},
        {"text": "另一个标题"},
    ],
    "stance": {"narrator": "third_person", "speaker_policy": "explicit_only"},
    "cut": ["不写安装"],
    "challenge": "共享空间是诊断，不是 payoff。",
    "evidence_status": ["single case"],
    "concept_ledger": [
        {
            "term": "点积",
            "definition": "衡量两个向量方向有多一致",
            "analogy": "",
            "counterexample": "",
            "how_much": "one_line",
            "status": "assume_known",
        }
    ],
    "mechanism_chain": [
        {"link": "共享空间让图文可比", "why": "两个 encoder 输出同一坐标", "evidence": "s1", "status": "unknown"}
    ],
    "number_ledger": [
        {"value": "0.756", "metric": "cosine", "task": "300-photo search", "baseline": "unknown", "status": "video_claim"}
    ],
    "source_block": {
        "video": "BVtest",
        "channel": "unknown",
        "date": "unknown",
        "link": "unknown",
        "official": [],
        "missing": ["link"],
    },
    "texture_policy": "保留演示数字和失败画面",
    "next_step": "来源：BVtest",
}


class _Usage:
    def as_dict(self):
        return {"total_tokens": 42}


class _Response:
    text = json.dumps(PAYLOAD, ensure_ascii=False)
    usage = _Usage()
    latency_ms = 3
    cached = False
    finish_reason = "stop"


class _Provider:
    model = "fake"

    def __init__(self) -> None:
        self.user: dict = {}

    def complete(self, **kwargs):
        self.user = json.loads(kwargs["user"])
        return _Response()


def test_write_brief_returns_flexible_contract(tmp_path: Path) -> None:
    provider = _Provider()
    brief = write_brief(
        validate_request(REQUEST),
        SOURCE_MAP,
        load_skill(SKILL_DIR),
        tmp_path,
        run=True,
        provider=provider,
    )
    assert brief["status"] == "complete"
    assert brief["shape"] == "analytical"
    assert brief["titles"][0]["chosen"] is True
    assert brief["titles"][1]["chosen"] is False
    assert len(brief["spine"]) == 3
    assert brief["brief_hash"]
    assert brief["source_map_hash"] == "sm"
    assert brief["input_mode"] == "source_map"
    assert provider.user["source_map"]["schema_version"] == "source-map-v1"
    assert "evidence_text" not in provider.user
    assert "smart general reader" in provider.user["reader_profile"]
    assert brief["concept_ledger"][0]["term"] == "点积"
    assert brief["mechanism_chain"][0]["link"]
    assert brief["number_ledger"][0]["value"] == "0.756"
    assert brief["source_block"]["video"] == "BVtest"
    assert brief["texture_policy"]
    assert brief["next_step"]
    assert (tmp_path / "brief.json").exists()


def test_write_brief_includes_full_text_when_requested(tmp_path: Path) -> None:
    provider = _Provider()
    write_brief(
        validate_request(REQUEST),
        SOURCE_MAP,
        load_skill(SKILL_DIR),
        tmp_path,
        run=True,
        provider=provider,
        evidence_text="原始文本",
        include_full_text=True,
    )
    assert provider.user["evidence_text"] == "原始文本"


def test_write_brief_falls_back_to_source_map_ledgers(tmp_path: Path) -> None:
    class _NoLedgerResponse(_Response):
        text = json.dumps(
            {
                key: value
                for key, value in PAYLOAD.items()
                if key not in {"number_ledger", "source_block"}
            },
            ensure_ascii=False,
        )

    class _NoLedgerProvider(_Provider):
        def complete(self, **kwargs):
            self.user = json.loads(kwargs["user"])
            return _NoLedgerResponse()

    source_map = dict(
        SOURCE_MAP,
        provenance={"video_id": "BVtest", "missing": ["link"]},
        numbers=[{"value": "0.756", "status": "video_claim"}],
    )
    brief = write_brief(
        validate_request(REQUEST),
        source_map,
        load_skill(SKILL_DIR),
        tmp_path,
        run=True,
        provider=_NoLedgerProvider(),
    )
    assert brief["number_ledger"][0]["value"] == "0.756"
    assert brief["source_block"]["video"] == "BVtest"


def test_write_brief_merges_frame_metadata_into_source_block(tmp_path: Path) -> None:
    class _UnknownSourceResponse(_Response):
        text = json.dumps(
            {
                key: (
                    {
                        "video": "BVtest",
                        "channel": "unknown",
                        "title": "unknown",
                        "date": "unknown",
                        "link": "unknown",
                        "official": [],
                        "missing": ["title", "channel", "date", "link", "official_docs"],
                    }
                    if key == "source_block"
                    else value
                )
                for key, value in PAYLOAD.items()
            },
            ensure_ascii=False,
        )

    class _UnknownSourceProvider(_Provider):
        def complete(self, **kwargs):
            self.user = json.loads(kwargs["user"])
            return _UnknownSourceResponse()

    source_map = dict(
        SOURCE_MAP,
        provenance={
            "video_id": "BVtest",
            "channel": "轩辕的编程宇宙",
            "title": "Agent和Harness到底是什么？",
            "date": "2026-05-15",
            "link": "unknown",
            "missing": ["link", "official_docs"],
        },
        source_metadata={
            "channel": {"value": "轩辕的编程宇宙", "source": "frame_watermark"},
            "title": {
                "value": "Agent和Harness到底是什么？",
                "source": "frame_ocr",
            },
            "date": {"value": "2026-05-15", "source": "frame_ocr"},
            "official_hints": [
                {"value": "DeepSeek Harness 团队 2026年8月13日", "source": "frame_ocr"}
            ],
        },
    )
    brief = write_brief(
        validate_request(REQUEST),
        source_map,
        load_skill(SKILL_DIR),
        tmp_path,
        run=True,
        provider=_UnknownSourceProvider(),
    )
    block = brief["source_block"]
    assert block["channel"] == "轩辕的编程宇宙"
    assert block["title"] == "Agent和Harness到底是什么？"
    assert block["date"] == "2026-05-15"
    assert block["metadata_source"]["channel"] == "frame_watermark"
    assert block["unverified"] is True
    assert "official_hints" in block
    assert "title" not in block["missing"]
    assert "channel" not in block["missing"]
    assert "link" in block["missing"]


def test_write_brief_uses_request_video_id_over_short_index_prefix(tmp_path: Path) -> None:
    provider = _Provider()
    source_map = dict(
        SOURCE_MAP,
        provenance={
            "video_id": "BV1AC",
            "channel": "unknown",
            "missing": ["link"],
        },
    )
    request = dict(REQUEST, video_ids=["BV1ACbi6DEvC"])
    brief = write_brief(
        validate_request(request),
        source_map,
        load_skill(SKILL_DIR),
        tmp_path,
        run=True,
        provider=provider,
    )
    assert brief["source_block"]["video"] == "BV1ACbi6DEvC"


def test_title_check_flags_absolute_words_and_unbound_quotes() -> None:
    brief = {
        "titles": [{"text": "某方法：只是换了个说法", "chosen": True}],
    }
    check = _title_check(brief, {})
    assert "title_absolute:只是" in check["issues"]
    brief["titles"][0]["text"] = "「不存在的引语」：标题"
    check = _title_check(brief, {})
    assert "title_quote_not_in_source" in check["issues"]


def test_write_brief_rejects_missing_core(tmp_path: Path) -> None:
    class _BadProvider(_Provider):
        def complete(self, **kwargs):
            return _ResponseBad()

    class _ResponseBad(_Response):
        text = json.dumps({"spine": PAYLOAD["spine"]}, ensure_ascii=False)

    brief = write_brief(
        validate_request(REQUEST),
        SOURCE_MAP,
        load_skill(SKILL_DIR),
        tmp_path,
        run=True,
        provider=_BadProvider(),
    )
    assert brief["status"] == "invalid_output"
    assert "missing_core" in brief["problems"]


def test_resolve_brief_mode_is_advisory_and_overridable() -> None:
    short = {"text_chars": 3000, "segment_count": 3}
    long = {"text_chars": 20000, "segment_count": 30}
    low = validate_request(REQUEST)
    high = dict(low, risk_level="high")
    assert _resolve_brief_mode("none", low, long)["mode"] == "none"
    assert _resolve_brief_mode("mini", low, long)["mode"] == "mini"
    assert _resolve_brief_mode("auto", low, short)["mode"] == "mini"
    assert _resolve_brief_mode("auto", low, long)["mode"] == "full"
    assert _resolve_brief_mode("auto", high, short)["mode"] == "full"
    assert _resolve_brief_mode("human_review", low, short)["human_review"] is True


def test_request_validates_brief_mode() -> None:
    with pytest.raises(ValueError, match="brief_mode"):
        validate_request(dict(REQUEST, brief_mode="weird"))
