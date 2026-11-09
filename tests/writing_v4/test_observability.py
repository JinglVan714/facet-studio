import json
from pathlib import Path

from facet_studio.observability import (
    collect_runs_dashboard,
    collect_trace,
    render_trace_html,
    write_trace,
)


def _write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def _run(tmp_path: Path) -> tuple[Path, str, dict]:
    run_id = "run_trace"
    runs_root = tmp_path / "runs"
    run_dir = runs_root / "product_v1" / run_id
    form_dir = run_dir / "wechat_article"
    form_dir.mkdir(parents=True)
    (run_dir / "content").mkdir()
    (run_dir / "content" / "content.md").write_text("内容稿。", encoding="utf-8")
    (form_dir / "article.md").write_text("# 标题\n\n正文。", encoding="utf-8")
    (form_dir / "reader.html").write_text("<html>reader</html>", encoding="utf-8")
    meta = {
        "run_id": run_id,
        "video_id": "BVtest",
        "form": "wechat_article",
        "form_label": "公众号",
        "status": "typeset",
        "request": "写一篇公众号",
        "form_dir": str(form_dir),
        "output": "article.md",
        "artifacts": {"reader_html": str(form_dir / "reader.html")},
        "planner_usage": {"total_tokens": 100},
        "planner_latency_ms": 20,
        "write": {
            "usage": {"total_tokens": 200},
            "latency_ms": 30,
        },
    }
    _write_json(run_dir / "run_meta.json", meta)
    _write_json(
        run_dir / "workflow.json",
        {
            "status": "typeset",
            "stages": [
                {"name": "plan", "status": "succeeded", "duration_ms": 20, "usage": {"total_tokens": 100}},
                {"name": "write", "status": "succeeded", "duration_ms": 30, "usage": {"total_tokens": 200}},
                {"name": "typeset", "status": "typeset", "duration_ms": 1, "usage": {}},
            ],
            "events": [{"type": "update", "node": "plan", "keys": ["plan"]}],
            "errors": [],
        },
    )
    (run_dir / "llm_calls.jsonl").write_text(
        json.dumps(
            {
                "stage": "write_wechat_article",
                "model": "deepseek-flash",
                "status": "succeeded",
                "usage": {"prompt_tokens": 50, "completion_tokens": 50, "total_tokens": 100},
                "latency_ms": 1234,
                "error": None,
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    (run_dir / "tool_calls.jsonl").write_text(
        json.dumps(
            {
                "tool_name": "compile_content",
                "actor": "orchestrator",
                "latency_ms": 2,
                "error": None,
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    (run_dir / "decision_records.jsonl").write_text(
        json.dumps(
            {
                "stage": "lead_plan",
                "question": "写哪种形态？",
                "selected": "wechat_article",
                "decided_by": "lead_planner",
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    return run_dir, run_id, meta


def test_collect_trace_combines_stages_calls_checks(tmp_path: Path) -> None:
    run_dir, run_id, meta = _run(tmp_path)
    trace = collect_trace(run_id, run_dir, meta)
    assert trace["calls_total"] == 1
    assert trace["tools_total"] == 1
    assert trace["decisions_total"] == 1
    assert len(trace["stages"]) == 3
    assert trace["usage"]["total_tokens"] == 100
    assert trace["latency_ms"] == 1234
    assert trace["checks_total"] > 0
    assert "stages" in trace and "llm_calls" in trace and "grounding" in trace


def test_collect_trace_story_is_human_readable(tmp_path: Path) -> None:
    run_dir, run_id, meta = _run(tmp_path)
    trace = collect_trace(run_id, run_dir, meta)
    steps = [item["step"] for item in trace["story"]]
    assert steps == ["规划", "写作", "排版", "验收"]
    assert trace["story"][-1]["detail"] == "等待用户验收"
    assert "call_id" not in json.dumps(trace["story"], ensure_ascii=False)


def test_render_trace_html_has_timeline_and_checks(tmp_path: Path) -> None:
    run_dir, run_id, meta = _run(tmp_path)
    trace = collect_trace(run_id, run_dir, meta)
    html = render_trace_html(trace)
    assert "运行数据" in html
    assert run_id in html
    assert "write_wechat_article" in html
    assert "compile_content" in html
    assert "机器检查" in html
    assert "不是写作质量分" in html
    assert "trace.html" not in html  # the page links artifacts, not itself


def test_write_trace_writes_html(tmp_path: Path) -> None:
    run_dir, run_id, meta = _run(tmp_path)
    path = write_trace(run_id, run_dir, meta)
    assert path.is_file()
    assert "运行数据" in path.read_text(encoding="utf-8")


def test_dashboard_summarizes_runs(tmp_path: Path) -> None:
    run_dir, run_id, meta = _run(tmp_path)
    write_trace(run_id, run_dir, meta)
    data = collect_runs_dashboard(tmp_path / "runs")
    assert data["summary"]["runs"] == 1
    assert data["summary"]["calls_total"] == 1
    assert data["summary"]["tokens_total"] == 100
    assert data["runs"][0]["run_id"] == run_id
    assert data["runs"][0]["checks_total"] > 0


def test_live_trace_auto_refreshes(tmp_path: Path) -> None:
    run_dir, run_id, meta = _run(tmp_path)
    meta["status"] = "written"
    trace = collect_trace(
        run_id,
        run_dir,
        meta,
        live=True,
        include_checks=False,
        include_grounding=False,
    )
    html = render_trace_html(trace)
    assert 'http-equiv="refresh"' in html
    assert "运行中" in html
