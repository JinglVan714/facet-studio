"""Tests for the two-step index+parts probe."""

from __future__ import annotations

import json
from pathlib import Path

from lunograph.providers.llm import LLMResponse, LLMUsage
from lunograph.writing_v3 import probe_parts

INDEX = {
    "schema": "writer-index-v1",
    "segments": [
        {
            "part_id": "part_01",
            "label": "第一段",
            "claims": [
                {
                    "claim_id": "c_1",
                    "text": "第一句。",
                    "status": "supported",
                    "scope": "",
                }
            ],
        },
        {
            "part_id": "part_02",
            "label": "第二段",
            "claims": [
                {
                    "claim_id": "c_2",
                    "text": "第三句。",
                    "status": "bounded",
                    "scope": "只在这种情况下",
                }
            ],
        },
    ],
    "gaps": [],
    "conflicts": [],
}

PART_1 = {
    "schema": "writer-part-v1",
    "part_id": "part_01",
    "segments": [
        {
            "label": "第一段",
            "claims": [
                {
                    "claim_id": "c_1",
                    "text": "第一句。",
                    "status": "supported",
                    "scope": "",
                    "evidence": [{"evidence_id": "ev_1", "span": [0, 4]}],
                }
            ],
            "context": ["第一句。"],
            "frames": [],
        }
    ],
}

PART_2 = {
    "schema": "writer-part-v1",
    "part_id": "part_02",
    "segments": [
        {
            "label": "第二段",
            "claims": [
                {
                    "claim_id": "c_2",
                    "text": "第三句。",
                    "status": "bounded",
                    "scope": "只在这种情况下",
                    "evidence": [{"evidence_id": "ev_2", "span": [0, 4]}],
                }
            ],
            "context": ["第三句。"],
            "frames": [],
        }
    ],
}

QUESTIONS = {
    "schema": "s2-probe-questions-v1",
    "case_id": "T",
    "questions": [
        {"id": "q1", "type": "central", "question": "发生了什么？"},
        {"id": "q2", "type": "quote", "question": "逐字引用第一句。"},
    ],
}


def _write_fixtures(tmp_path: Path) -> dict[str, Path]:
    index_path = tmp_path / "writer_index.json"
    index_path.write_text(json.dumps(INDEX, ensure_ascii=False), encoding="utf-8")
    parts_dir = tmp_path / "writer_parts"
    parts_dir.mkdir()
    (parts_dir / "part_01.json").write_text(
        json.dumps(PART_1, ensure_ascii=False), encoding="utf-8"
    )
    (parts_dir / "part_02.json").write_text(
        json.dumps(PART_2, ensure_ascii=False), encoding="utf-8"
    )
    questions_path = tmp_path / "questions.json"
    questions_path.write_text(
        json.dumps(QUESTIONS, ensure_ascii=False), encoding="utf-8"
    )
    return {
        "index": index_path,
        "parts_dir": parts_dir,
        "questions": questions_path,
    }


def test_selection_prompt_contains_index_and_questions() -> None:
    text = probe_parts.build_selection_prompt(INDEX, QUESTIONS["questions"])
    assert "part_01" in text
    assert "发生了什么？" in text
    assert "part_ids" in text


def test_parse_selection_validates_and_dedupes() -> None:
    valid = {"part_01", "part_02"}
    assert probe_parts.parse_selection(
        '{"part_ids":["part_01","part_02","part_02","bad"]}', valid
    ) == ["part_01", "part_02"]
    assert probe_parts.parse_selection("not json", valid) == []
    assert probe_parts.parse_selection('{"part_ids":"part_01"}', valid) == []


def test_load_selected_segments_keeps_order() -> None:
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        paths = _write_fixtures(Path(tmp))
        parts, segments = probe_parts.load_selected_segments(
            paths["parts_dir"], ["part_02", "part_01"]
        )
        assert [part["part_id"] for part in parts] == ["part_02", "part_01"]
        assert [segment["label"] for segment in segments] == ["第二段", "第一段"]


def test_answer_input_is_writer_view_shape() -> None:
    segments = [PART_1["segments"][0], PART_2["segments"][0]]
    payload = json.loads(probe_parts.build_answer_input(segments, INDEX))
    assert payload["schema"] == "writer-view-v1"
    assert len(payload["segments"]) == 2
    assert payload["gaps"] == []


def test_dry_run_writes_selection_prompt_only(tmp_path: Path) -> None:
    paths = _write_fixtures(tmp_path)
    out_dir = tmp_path / "out"
    code = probe_parts.main(
        [
            "--case-id",
            "T",
            "--index",
            str(paths["index"]),
            "--parts-dir",
            str(paths["parts_dir"]),
            "--questions",
            str(paths["questions"]),
            "--out-dir",
            str(out_dir),
        ]
    )
    assert code == 0
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "dry_run"
    assert (out_dir / "prompts" / "select.system.txt").exists()
    assert (out_dir / "prompts" / "select.user.txt").exists()
    assert not (out_dir / "answer.txt").exists()


def test_run_path_selects_parts_then_answers(tmp_path: Path, monkeypatch) -> None:
    class FakeSettings:
        provider_configured = True
        model = "fake-model"
        runs_root = tmp_path

    class FakeLLM:
        def __init__(self, settings, *, call_sink=None):
            self.settings = settings
            self.model = settings.model
            self.call_sink = call_sink

        def complete(
            self, *, stage, key, system, user, max_tokens=None, temperature=0.0
        ):
            if stage == "s2_probe_select":
                text = '{"part_ids":["part_01"]}'
            else:
                text = "FAKE ANSWER"
            if self.call_sink is not None:
                self.call_sink(
                    {
                        "call_id": "call_fake",
                        "stage": stage,
                        "key": key,
                        "raw_response": "SHOULD NOT BE IN JSONL",
                        "usage": {
                            "prompt_tokens": 1,
                            "completion_tokens": 2,
                            "total_tokens": 3,
                        },
                        "latency_ms": 5,
                        "finish_reason": "stop",
                        "status": "succeeded",
                    }
                )
            return LLMResponse(
                text=text,
                model=self.model,
                provider="fake",
                usage=LLMUsage(
                    prompt_tokens=1, completion_tokens=2, total_tokens=3
                ),
                latency_ms=5,
                finish_reason="stop",
            )

    monkeypatch.setattr("lunograph.core.config.get_settings", lambda: FakeSettings())
    monkeypatch.setattr(probe_parts, "DeepSeekLLM", FakeLLM)

    paths = _write_fixtures(tmp_path)
    out_dir = tmp_path / "run"
    code = probe_parts.main(
        [
            "--case-id",
            "T",
            "--index",
            str(paths["index"]),
            "--parts-dir",
            str(paths["parts_dir"]),
            "--questions",
            str(paths["questions"]),
            "--out-dir",
            str(out_dir),
            "--run",
            "--no-cache",
        ]
    )
    assert code == 0
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "complete"
    assert manifest["selection"]["part_ids"] == ["part_01"]
    assert (out_dir / "answer.txt").read_text(encoding="utf-8") == "FAKE ANSWER"
    calls = [
        json.loads(line)
        for line in (out_dir / "llm_calls.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    assert len(calls) == 2
    assert {call["stage"] for call in calls} == {
        "s2_probe_select",
        "s2_probe_answer",
    }
    assert all("raw_response" not in call for call in calls)
