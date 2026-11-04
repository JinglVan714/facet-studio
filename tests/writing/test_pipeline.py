"""Dry-run pipeline test: no provider call."""

from __future__ import annotations

import json
from pathlib import Path

from lunograph.writing.pipeline import (
    _restore_unrequested_captions,
    _repair_diff_guard,
    run_pipeline,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SKILL_DIR = PROJECT_ROOT / "skills" / "writing" / "reader_first_explainer"

EDITED = "先收集问题。0.756。"

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
            "sentence_ids": ["seg1-s001", "seg1-s002"],
            "frame_ids": ["f1"],
        }
    ],
    "claims": [
        {
            "claim_id": "c1",
            "segment_id": "seg1",
            "status": "supported",
            "kind": "instruction",
            "text": "先收集问题，得到 0.756。",
            "scope": "",
            "t_start_ms": 0,
            "t_end_ms": 2000,
            "evidence_ids": ["e1"],
            "sentence_ids": ["seg1-s001", "seg1-s002"],
            "part_id": "part_01",
        }
    ],
    "evidence": [
        {
            "evidence_id": "e1",
            "claim_ids": ["c1"],
            "quote": "0.756",
            "t_start_ms": 0,
            "t_end_ms": 2000,
            "sentence_ids": ["seg1-s002"],
        }
    ],
    "sentences": [
        {
            "sentence_id": "seg1-s001",
            "segment_id": "seg1",
            "t_start_ms": 0,
            "t_end_ms": 1000,
            "text": "先收集问题。",
            "part_id": "part_01",
        },
        {
            "sentence_id": "seg1-s002",
            "segment_id": "seg1",
            "t_start_ms": 1000,
            "t_end_ms": 2000,
            "text": "0.756。",
            "part_id": "part_01",
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
        }
    ],
    "parts": [
        {
            "part_id": "part_01",
            "segment_ids": ["seg1"],
            "chars": len(EDITED),
            "oversize": False,
            "text_start": 0,
            "text_end": len(EDITED),
        }
    ],
    "coverage": {"unassigned_blocks": []},
}

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
            "frame_ids": ["f1"],
        }
    ],
    "claims": INDEX["claims"],
    "evidence": INDEX["evidence"],
    "frames": INDEX["frames"],
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
            "frames": [{"frame_id": "f1", "caption": "流程：收集问题"}],
        }
    ]
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


def _write(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=1)
        if not isinstance(value, str)
        else value,
        encoding="utf-8",
    )


def test_pipeline_dry_run_writes_context_and_prompts(tmp_path) -> None:
    request_path = tmp_path / "request.json"
    index_path = tmp_path / "index.json"
    edited_path = tmp_path / "edited.txt"
    pack_path = tmp_path / "pack.json"
    sentences_path = tmp_path / "sentences.json"
    source_map_path = tmp_path / "source_map.json"
    _write(request_path, REQUEST)
    _write(index_path, INDEX)
    _write(edited_path, EDITED)
    _write(pack_path, PACK)
    _write(sentences_path, {"sentences": INDEX["sentences"]})
    _write(source_map_path, SOURCE_MAP)

    result = run_pipeline(
        request_path=request_path,
        skill_dir=SKILL_DIR,
        index_path=index_path,
        edited_text_path=edited_path,
        pack_path=pack_path,
        sentences_path=sentences_path,
        source_map_path=source_map_path,
        out_dir=tmp_path / "out",
        run=False,
    )
    assert result["status"] == "dry_run"
    assert (tmp_path / "out" / "context.json").exists()
    assert (tmp_path / "out" / "writer" / "prompts" / "system.txt").exists()
    assert (tmp_path / "out" / "writer" / "prompts" / "user.txt").exists()
    assert (tmp_path / "out" / "writer" / "manifest.json").exists()
    assert (tmp_path / "out" / "manifest.json").exists()
    manifest = json.loads(
        (tmp_path / "out" / "manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["status"] == "dry_run"
    assert manifest["context"]["profile"] == "full_text"
    assert manifest["source_map"]["status"] == "complete"
    assert manifest["brief"]["status"] == "dry_run"
    assert (tmp_path / "out" / "source_map.json").exists()


def test_caption_restore_undoes_unrequested_repair_drift() -> None:
    before = (
        "# 标题\n\n![frame](assets/frame_1.jpg)\n\n"
        "*看原图里的左侧面板。*\n\n正文。"
    )
    after = (
        "# 标题\n\n![frame](assets/frame_1.jpg)\n\n"
        "*看新图里的会话列表。*\n\n正文。"
    )
    restored, paths = _restore_unrequested_captions(before, after, {"verifier": []})
    assert paths == ["frame_1.jpg"]
    assert "*看原图里的左侧面板。*" in restored
    assert "*看新图里的会话列表。*" not in restored


def test_caption_restore_keeps_requested_visual_fix() -> None:
    before = (
        "# 标题\n\n![frame](assets/frame_1.jpg)\n\n"
        "*看左侧面板。*\n\n正文。"
    )
    after = (
        "# 标题\n\n![frame](assets/frame_1.jpg)\n\n"
        "*看右侧面板。*\n\n正文。"
    )
    findings = {
        "verifier": [
            {
                "axis": "visual",
                "quote": "*看左侧面板。*",
                "action": "改到右侧面板",
            }
        ]
    }
    restored, paths = _restore_unrequested_captions(before, after, findings)
    assert paths == []
    assert "*看右侧面板。*" in restored


def test_repair_diff_guard_rejects_new_heading_and_image() -> None:
    before = "# 标题\n\n## 1. 一节\n\n正文。"
    after = "# 标题\n\n## 1. 一节\n\n## 2. 新节\n\n正文。"
    assert _repair_diff_guard(before, after)["ok"] is False
    with_image = "# 标题\n\n## 1. 一节\n\n![frame](assets/x.jpg)\n\n*看画面。*\n\n正文。"
    assert _repair_diff_guard(before, with_image)["ok"] is False
