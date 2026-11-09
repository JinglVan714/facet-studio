import json
from pathlib import Path
from types import SimpleNamespace

import facet_studio.workflow as workflow


def _fakes(monkeypatch, calls: dict[str, int]) -> None:
    def fake_plan(**kwargs):
        calls["plan"] += 1
        return {
            "status": "planned",
            "central_idea": "一个想法",
            "reader_goal": "读者目标",
            "angle": "角度",
            "brief": "brief",
            "must_use_figures": [],
            "shared_constraints": [],
            "content_chars": 100,
            "figure_count": 1,
            "form_label": "公众号",
            "planner_usage": {
                "prompt_tokens": 10,
                "completion_tokens": 20,
                "total_tokens": 30,
            },
        }

    def fake_write(run_id):
        calls["write"] += 1
        return {
            "run_id": run_id,
            "status": "written",
            "output_chars": 200,
            "usage": {
                "prompt_tokens": 100,
                "completion_tokens": 200,
                "total_tokens": 300,
            },
            "markdown": "BODY",
        }

    def fake_typeset(run_id):
        calls["typeset"] += 1
        return {
            "run_id": run_id,
            "status": "typeset",
            "typeset_errors": [],
            "preview_url": "http://preview",
        }

    def fake_review(run_id, decision, notes=""):
        calls["review"] += 1
        return {
            "run_id": run_id,
            "status": decision,
            "review_status": decision,
            "review": {"decision": decision, "notes": notes},
        }

    monkeypatch.setattr(workflow, "plan_article", fake_plan)
    monkeypatch.setattr(workflow, "write_form", fake_write)
    monkeypatch.setattr(workflow, "typeset_article", fake_typeset)
    monkeypatch.setattr(workflow, "review_artifact", fake_review)


def test_workflow_pauses_at_plan_then_review(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("FACET_STUDIO_RUNS_ROOT", str(tmp_path))
    calls = {"plan": 0, "write": 0, "typeset": 0, "review": 0}
    _fakes(monkeypatch, calls)

    progress: list[tuple[str, int, int]] = []
    started = workflow.start_workflow(
        "BVtest",
        "公众号",
        "写一篇公众号",
        on_event=lambda event, step, total: progress.append(
            (str(event.get("node") or event.get("type")), step, total)
        ),
    )
    assert "plan" in [item[0] for item in progress]
    assert started["status"] == "awaiting_plan_approval"
    assert started["next"] == ["approval"]
    assert started["plan"]["central_idea"] == "一个想法"
    assert calls == {"plan": 1, "write": 0, "typeset": 0, "review": 0}

    run_id = started["run_id"]
    written = workflow.resume_workflow(run_id, "approved")
    assert written["status"] == "awaiting_review"
    assert written["next"] == ["review"]
    assert calls == {"plan": 1, "write": 1, "typeset": 1, "review": 0}
    assert written["usage"]["total_tokens"] == 330

    accepted = workflow.resume_workflow(run_id, "approved", "ok")
    assert accepted["status"] == "approved"
    assert accepted["next"] == []
    assert calls == {"plan": 1, "write": 1, "typeset": 1, "review": 1}

    trace = workflow.get_workflow(run_id)
    assert [stage["name"] for stage in trace["stages"]] == [
        "intake",
        "plan",
        "approval",
        "write",
        "typeset",
        "review",
    ]
    assert trace["review"]["review"]["decision"] == "approved"
    assert trace["cost_estimate"] is None


def test_workflow_writes_tool_and_decision_spans(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("FACET_STUDIO_RUNS_ROOT", str(tmp_path))
    stages = [
        {"name": "plan", "status": "succeeded", "duration_ms": 10, "usage": {"total_tokens": 30}, "at": "t1"},
        {"name": "approval", "status": "auto_approved", "duration_ms": 0, "usage": {}, "at": "t2"},
        {"name": "review", "status": "auto_accepted", "duration_ms": 0, "usage": {}, "at": "t3"},
    ]
    workflow._write_stage_tool_calls("run_spans", stages)
    workflow._write_stage_decisions(
        "run_spans",
        {"form": "wechat_article", "plan": {"central_idea": "一个想法"}},
        stages,
    )
    run_dir = tmp_path / "product_v1" / "run_spans"
    tools = [json.loads(line) for line in (run_dir / "tool_calls.jsonl").read_text(encoding="utf-8").splitlines()]
    decisions = [
        json.loads(line)
        for line in (run_dir / "decision_records.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert [item["tool_name"] for item in tools] == ["plan", "approval", "review"]
    assert tools[0]["usage"]["total_tokens"] == 30
    assert [item["stage"] for item in decisions] == ["plan", "approval", "review"]
    assert decisions[0]["selected"] == "wechat_article"
    assert decisions[1]["selected"] == "auto_approved"


def test_workflow_auto_approve_skips_human_gates(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("FACET_STUDIO_RUNS_ROOT", str(tmp_path))
    calls = {"plan": 0, "write": 0, "typeset": 0, "review": 0}
    _fakes(monkeypatch, calls)

    result = workflow.start_workflow(
        "BVtest", "wechat_article", "写一篇", auto_approve=True
    )
    assert result["status"] == "typeset"
    assert result["next"] == []
    assert calls == {"plan": 1, "write": 1, "typeset": 1, "review": 0}


def test_snapshot_does_not_treat_auto_plan_as_human_gate() -> None:
    snapshot = SimpleNamespace(
        values={"auto_plan": True, "form": "wechat_article"},
        next=["approval"],
        interrupts=(),
    )
    assert workflow._snapshot_result("run_auto_plan", snapshot, [])["status"] == "running"
    manual = SimpleNamespace(
        values={"auto_plan": False, "form": "wechat_article"},
        next=["approval"],
        interrupts=(),
    )
    assert workflow._snapshot_result("run_manual_plan", manual, [])["status"] == "awaiting_plan_approval"


def test_workflow_auto_plan_skips_plan_gate_but_keeps_review(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("FACET_STUDIO_RUNS_ROOT", str(tmp_path))
    calls = {"plan": 0, "write": 0, "typeset": 0, "review": 0}
    _fakes(monkeypatch, calls)

    result = workflow.start_workflow(
        "BVtest", "wechat_article", "写一篇", auto_plan=True
    )
    assert result["status"] == "awaiting_review"
    assert result["next"] == ["review"]
    assert calls == {"plan": 1, "write": 1, "typeset": 1, "review": 0}


def test_workflow_background_start_and_wait(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("FACET_STUDIO_RUNS_ROOT", str(tmp_path))
    calls = {"plan": 0, "write": 0, "typeset": 0, "review": 0}
    _fakes(monkeypatch, calls)

    started = workflow.start_workflow(
        "BVtest", "wechat_article", "写一篇", auto_plan=True, background=True
    )
    assert started["status"] == "running"
    assert started["run_id"]
    waited = workflow.wait_workflow(started["run_id"], timeout_s=10)
    assert waited["wait_status"] == "ready"
    assert waited["status"] == "awaiting_review"
    assert calls == {"plan": 1, "write": 1, "typeset": 1, "review": 0}


def test_result_summary_uses_delivered_assets_not_cited_figures(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("FACET_STUDIO_RUNS_ROOT", str(tmp_path))
    run_id = "run_assets"
    run_dir = tmp_path / "product_v1" / run_id
    run_dir.mkdir(parents=True)
    (run_dir / "run_meta.json").write_text(
        json.dumps(
            {
                "visual_audit": {"candidate_count": 4, "approved_count": 0},
                "write": {
                    "figures_referenced": ["figures/fig-01.jpg"],
                    "svg_assets": [],
                },
                "typeset": {"xhs_export": {"images": ["xhs_export/01_cover.png"]}},
            }
        ),
        encoding="utf-8",
    )
    values = {
        "form": "xiaohongshu_note",
        "status": "awaiting_review",
        "write": {"output_chars": 565, "figures_referenced": ["figures/fig-01.jpg"]},
        "typeset": {"xhs_export": {"images": ["xhs_export/01_cover.png"]}},
    }
    summary = workflow._result_summary(values, run_id)
    assert "1 张卡片" in summary
    assert "0 张关键帧" in summary
    assert "引用 1 图" not in summary
    assert workflow._asset_facts(values, run_id) == {
        "keyframes": 0,
        "charts": 0,
        "cards": 1,
    }


def test_agent_view_omits_full_body() -> None:
    result = {
        "run_id": "run_view",
        "form": "wechat_article",
        "form_label": "公众号",
        "status": "awaiting_review",
        "summary": "公众号 · awaiting_review",
        "assets": {"keyframes": 0, "charts": 1, "cards": 0},
        "plan": {"central_idea": "一个想法", "brief": "很长"},
        "write": {"output": "BODY" * 10_000, "output_chars": 40_000},
        "typeset": {"preview_url": "http://preview", "typeset_errors": []},
        "usage": {"total_tokens": 12},
        "stages": [{"name": "plan", "status": "succeeded", "usage": {"total_tokens": 9}}],
    }
    view = workflow.agent_view(result)
    assert view["summary"] == "公众号 · awaiting_review"
    assert view["assets"]["charts"] == 1
    assert view["write"] == {"output_chars": 40000, "title_candidates": []}
    assert "output" not in view["write"]
    assert view["usage"] == {"total_tokens": 12}
    assert "preview_url" not in view["typeset"]
    assert "trace_url" not in view
    assert view["typeset"]["has_preview"] is True


def test_workflow_plan_changes_requested_stops(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("FACET_STUDIO_RUNS_ROOT", str(tmp_path))
    calls = {"plan": 0, "write": 0, "typeset": 0, "review": 0}
    _fakes(monkeypatch, calls)

    started = workflow.start_workflow("BVtest", "wechat_article")
    stopped = workflow.resume_workflow(started["run_id"], "changes_requested")
    assert stopped["status"] == "changes_requested"
    assert stopped["next"] == []
    assert calls == {"plan": 1, "write": 0, "typeset": 0, "review": 0}
