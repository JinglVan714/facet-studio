"""Tests for the S2 probe harness (deterministic rendering + dry-run)."""

from __future__ import annotations

import json
from pathlib import Path

from lunograph.writing_v3 import probe
from lunograph.writing_v3.writer_view import resolve_quote

UNITS = [
    {"unit_id": "u1", "t": [0, 1000], "channel": "speech", "raw": "第一句。"},
    {"unit_id": "u2", "t": [1000, 2500], "channel": "speech", "raw": "第二句。"},
]

PASSAGES = {
    "passages": [
        {
            "passage_id": "seg1-p01",
            "segment_id": "seg1",
            "t_start_ms": 0,
            "t_end_ms": 2500,
            "text": "第一句。第二句。",
        },
        {
            "passage_id": "seg2-p01",
            "segment_id": "seg2",
            "t_start_ms": 3000,
            "t_end_ms": 4000,
            "text": "第三句。",
        },
    ]
}

VIEW = {
    "schema": "writer-view-v1",
    "segments": [
        {
            "label": "片段",
            "claims": [
                {
                    "claim_id": "c_1",
                    "text": "第一句。",
                    "status": "supported",
                    "scope": "",
                    "evidence": [{"evidence_id": "ev_1", "span": [0, 4]}],
                }
            ],
            "context": ["第一句。", "第二句。"],
            "frames": [{"frame_id": "f_1", "caption": "看这里"}],
        }
    ],
    "gaps": [],
    "conflicts": [],
}

QUESTIONS = {
    "schema": "s2-probe-questions-v1",
    "case_id": "T",
    "questions": [
        {"id": "q1", "type": "central", "question": "发生了什么？"},
        {"id": "q2", "type": "quote", "question": "逐字引用第一句。"},
    ],
}

VIEW_TWO_SEGMENTS = {
    "schema": "writer-view-v1",
    "segments": [
        {
            "label": "第一段",
            "claims": [],
            "context": ["第一句。", "第二句。"],
            "frames": [{"frame_id": "f_1", "caption": "第一段帧"}],
        },
        {
            "label": "第二段",
            "claims": [],
            "context": ["第三句。"],
            "frames": [{"frame_id": "f_2", "caption": "第二段帧\n带换行"}],
        },
    ],
    "gaps": [],
    "conflicts": [],
}


def _write_fixtures(tmp_path: Path) -> dict[str, Path]:
    units = tmp_path / "units.jsonl"
    units.write_text(
        "\n".join(json.dumps(item, ensure_ascii=False) for item in UNITS) + "\n",
        encoding="utf-8",
    )
    passages = tmp_path / "passages.json"
    passages.write_text(json.dumps(PASSAGES, ensure_ascii=False), encoding="utf-8")
    view = tmp_path / "writer_view.json"
    view.write_text(json.dumps(VIEW, ensure_ascii=False), encoding="utf-8")
    questions = tmp_path / "questions.json"
    questions.write_text(
        json.dumps(QUESTIONS, ensure_ascii=False), encoding="utf-8"
    )
    return {
        "units": units,
        "passages": passages,
        "view": view,
        "questions": questions,
    }


def test_render_raw_asr_keeps_one_line_per_unit_and_times() -> None:
    text = probe.render_raw_asr(UNITS)
    lines = text.splitlines()
    assert len(lines) == 2
    assert lines[0] == "[0.00-1.00s] 第一句。"
    assert lines[1] == "[1.00-2.50s] 第二句。"


def test_render_merged_text_has_passages_times_and_no_claims() -> None:
    text = probe.render_merged_text(PASSAGES["passages"])
    assert "[seg1-p01 0.00-2.50s] 第一句。第二句。" in text
    assert "[seg2-p01 3.00-4.00s] 第三句。" in text
    assert "\n\n" in text
    assert "claim" not in text
    assert "evidence" not in text


def test_render_lean_view_is_compact_json_with_resolvable_span() -> None:
    text = probe.render_lean_view(VIEW)
    assert '": ' not in text  # compact separators
    assert json.loads(text) == VIEW
    segment = VIEW["segments"][0]
    evidence = segment["claims"][0]["evidence"][0]
    assert resolve_quote(segment["context"], evidence) == "第一句。"


def test_render_merged_text_with_frames_is_merged_text_plus_frames() -> None:
    text = probe.render_merged_text_with_frames(
        PASSAGES["passages"], VIEW_TWO_SEGMENTS
    )
    assert "[seg1-p01 0.00-2.50s] 第一句。第二句。" in text
    assert "[seg2-p01 3.00-4.00s] 第三句。" in text
    assert "frames: [f_1] 第一段帧" in text
    assert "frames: [f_2] 第二段帧 / 带换行" in text
    assert "claim" not in text
    assert "evidence" not in text


def test_merged_text_with_frames_requires_matching_segments() -> None:
    try:
        probe.render_merged_text_with_frames(PASSAGES["passages"], VIEW)
    except ValueError as exc:
        assert "writer view segments" in str(exc)
    else:  # pragma: no cover - the fixture must mismatch
        raise AssertionError("expected a segment-count mismatch")


def test_dry_run_merged_text_frames_variant(tmp_path: Path) -> None:
    paths = _write_fixtures(tmp_path)
    view_path = tmp_path / "view_two.json"
    view_path.write_text(
        json.dumps(VIEW_TWO_SEGMENTS, ensure_ascii=False), encoding="utf-8"
    )
    out_dir = tmp_path / "frames_out"
    code = probe.main(
        [
            "--case-id",
            "T",
            "--passages",
            str(paths["passages"]),
            "--writer-view",
            str(view_path),
            "--questions",
            str(paths["questions"]),
            "--out-dir",
            str(out_dir),
            "--variant",
            "merged_text_frames",
        ]
    )
    assert code == 0
    manifest = json.loads(
        (out_dir / "manifest.json").read_text(encoding="utf-8")
    )
    assert set(manifest["variants"]) == {"merged_text_frames"}
    rendered = (out_dir / "merged_text_frames" / "rendered.txt").read_text(
        encoding="utf-8"
    )
    assert "frames: [f_1] 第一段帧" in rendered
    assert "claim" not in rendered


def test_user_prompt_is_fixed_template_with_numbered_questions() -> None:
    text = probe.build_user_prompt("INPUT", QUESTIONS["questions"])
    assert "Input:\n<<<\nINPUT\n>>>" in text
    assert "1. 发生了什么？" in text
    assert "2. 逐字引用第一句。" in text
    assert "证据不足" in text


def test_dry_run_writes_prompts_but_never_calls_provider(tmp_path: Path) -> None:
    paths = _write_fixtures(tmp_path)
    out_dir = tmp_path / "out"
    code = probe.main(
        [
            "--case-id",
            "T",
            "--units",
            str(paths["units"]),
            "--passages",
            str(paths["passages"]),
            "--writer-view",
            str(paths["view"]),
            "--questions",
            str(paths["questions"]),
            "--out-dir",
            str(out_dir),
        ]
    )
    assert code == 0
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "dry_run"
    assert manifest["case_id"] == "T"
    assert set(manifest["variants"]) == {"raw_asr", "merged_text", "lean_view"}
    system_hashes = {
        item["prompts"]["system"]["sha256"]
        for item in manifest["variants"].values()
    }
    assert len(system_hashes) == 1
    user_hashes = {
        item["prompts"]["user"]["sha256"]
        for item in manifest["variants"].values()
    }
    assert len(user_hashes) == 3
    for variant in probe.VARIANTS:
        variant_dir = out_dir / variant
        assert (variant_dir / "rendered.txt").exists()
        assert (variant_dir / "prompts" / "system.txt").exists()
        assert (variant_dir / "prompts" / "user.txt").exists()
        assert not (variant_dir / "response.txt").exists()
    assert not (out_dir / "llm_calls.jsonl").exists()


def test_run_path_writes_responses_and_hashed_calls(
    tmp_path: Path, monkeypatch
) -> None:
    from lunograph.providers.llm import LLMResponse, LLMUsage

    class FakeSettings:
        provider_configured = True
        model = "fake-model"
        runs_root = tmp_path

    class FakeLLM:
        def __init__(self, settings, *, call_sink=None):
            self.settings = settings
            self.model = settings.model
            self.call_sink = call_sink

        def complete(self, *, stage, key, system, user, max_tokens=None, temperature=0.0):
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
                text="FAKE ANSWER",
                model=self.model,
                provider="fake",
                usage=LLMUsage(
                    prompt_tokens=1, completion_tokens=2, total_tokens=3
                ),
                latency_ms=5,
                finish_reason="stop",
            )

    monkeypatch.setattr("lunograph.core.config.get_settings", lambda: FakeSettings())
    monkeypatch.setattr(probe, "DeepSeekLLM", FakeLLM)

    paths = _write_fixtures(tmp_path)
    out_dir = tmp_path / "run"
    code = probe.main(
        [
            "--case-id",
            "T",
            "--units",
            str(paths["units"]),
            "--passages",
            str(paths["passages"]),
            "--writer-view",
            str(paths["view"]),
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
    assert manifest["model"] == "fake-model"
    for variant in probe.VARIANTS:
        assert (out_dir / variant / "response.txt").read_text(
            encoding="utf-8"
        ) == "FAKE ANSWER"
        assert manifest["variants"][variant]["usage"]["total_tokens"] == 3
    calls = [
        json.loads(line)
        for line in (out_dir / "llm_calls.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    assert len(calls) == 3
    assert all("raw_response" not in call for call in calls)
    assert all(call["raw_response_sha256"] for call in calls)


def test_dry_run_is_deterministic(tmp_path: Path) -> None:
    paths = _write_fixtures(tmp_path)
    outputs = []
    for name in ("a", "b"):
        out_dir = tmp_path / name
        code = probe.main(
            [
                "--case-id",
                "T",
                "--units",
                str(paths["units"]),
                "--passages",
                str(paths["passages"]),
                "--writer-view",
                str(paths["view"]),
                "--questions",
                str(paths["questions"]),
                "--out-dir",
                str(out_dir),
            ]
        )
        assert code == 0
        outputs.append(
            {
                variant: (out_dir / variant / "rendered.txt").read_bytes()
                for variant in probe.VARIANTS
            }
        )
    assert outputs[0] == outputs[1]


def test_question_sets_cover_required_types() -> None:
    root = Path(__file__).resolve().parents[2]
    required = {"central", "mechanism", "procedure", "boundary", "quote"}
    for name in ("questions_BV1AC.json", "questions_BV17.json"):
        payload = probe.load_questions(root / "docs" / "s2-probe" / name)
        questions = payload["questions"]
        assert len(questions) == 6
        assert {item["type"] for item in questions} >= required
        assert len({item["id"] for item in questions}) == 6
    for name in ("questions_v2_BV1AC.json", "questions_v2_BV17.json"):
        payload = probe.load_questions(root / "docs" / "s2-probe" / name)
        questions = payload["questions"]
        assert len(questions) == 9
        assert {item["type"] for item in questions} >= required | {
            "frame",
            "synthesis",
        }
        assert len({item["id"] for item in questions}) == 9
    payload = probe.load_questions(
        root / "docs" / "s2-probe" / "questions_BV1yb.json"
    )
    questions = payload["questions"]
    assert len(questions) == 7
    assert {item["type"] for item in questions} >= required | {"synthesis"}
    assert len({item["id"] for item in questions}) == 7
