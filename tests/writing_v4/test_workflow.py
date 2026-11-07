from pathlib import Path

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

    started = workflow.start_workflow("BVtest", "公众号", "写一篇公众号")
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
