import json
from pathlib import Path

from facet_studio.evals.grounding import _audit_run, audit


def _write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def _run(tmp_path: Path) -> tuple[Path, str]:
    runs_root = tmp_path / "runs"
    run_id = "run_ground"
    run_dir = runs_root / "product_v1" / run_id
    form_dir = run_dir / "xiaohongshu_note"
    form_dir.mkdir(parents=True)
    (run_dir / "content").mkdir()
    (run_dir / "content" / "content.md").write_text(
        "300 张照片，768 个数字，0.756 分。这是内容稿。",
        encoding="utf-8",
    )
    (form_dir / "note.md").write_text(
        "# 标题\n\n300 张照片，768 个数字，0.999 分。"
        "“这是一句编造的引语内容”\n\n所有动物都能找到。\n",
        encoding="utf-8",
    )
    _write_json(
        run_dir / "run_meta.json",
        {
            "run_id": run_id,
            "form": "xiaohongshu_note",
            "status": "approved",
            "form_dir": str(form_dir),
            "output": "note.md",
            "planner_usage": {"total_tokens": 50},
            "planner_latency_ms": 100,
            "write": {
                "latency_ms": 1000,
                "usage": {"total_tokens": 100},
            },
            "artifacts": {"reader_html": str(form_dir / "reader.html")},
        },
    )
    _write_json(run_dir / "publish_review.json", {"decision": "approved"})
    return runs_root, run_id


def test_grounding_flags_ungrounded_number_quote_and_scope(tmp_path: Path) -> None:
    runs_root, run_id = _run(tmp_path)
    result = _audit_run(
        case_id="case_ground",
        run_id=run_id,
        run_dir=runs_root / "product_v1" / run_id,
    )
    assert result["numbers"]["grounded"] == 2  # 300, 768
    assert "0.999" in result["numbers"]["candidates"]
    assert "0.756" not in result["numbers"]["candidates"]
    assert "这是一句编造的引语内容" in result["quotes"]["candidates"]
    assert "所有" in result["scope"]["candidates"]
    assert result["review"] == "approved"
    assert result["runtime"]["total_tokens"] == 150


def test_grounding_summary_is_candidate_only(tmp_path: Path) -> None:
    runs_root, run_id = _run(tmp_path)
    report = audit(
        [
            {
                "case_id": "case_ground",
                "run_id": run_id,
                "video_id": "BVtest",
                "form": "xiaohongshu_note",
            }
        ],
        runs_root=runs_root,
    )
    assert report["summary"]["artifacts"] == 1
    assert report["summary"]["flags"] >= 3
    assert "not a hallucination rate" in report["summary"]["note"]
    assert report["cross_form"][0]["video_id"] == "BVtest"
