"""LangGraph workflow for one product run (P3 prototype).

The graph is intentionally a thin orchestration layer over the existing MCP
tools: it does not rewrite the writing engine and it does not add an editor or
checker.  It adds state, checkpointing, streaming events and two human gates
(plan approval, final acceptance).
"""

from __future__ import annotations

import json
import os
import time
import uuid
from datetime import datetime, timezone
from typing import Any, TypedDict

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from .mcp_server import (
    FORM_SKILLS,
    _new_run_id,
    _normalize_form,
    _read_json,
    _run_dir,
    _runs_root,
    _write_json,
    plan_article,
    review_artifact,
    typeset_article,
    write_form,
)
from .observability import write_trace

REVIEW_DECISIONS = {"approved", "changes_requested", "rejected"}


class WorkflowState(TypedDict, total=False):
    run_id: str
    video_id: str
    form: str
    request: str
    auto_approve: bool
    status: str
    plan: dict[str, Any]
    decision: str
    write: dict[str, Any]
    typeset: dict[str, Any]
    review: dict[str, Any]
    errors: list[str]
    usage: dict[str, int]
    stages: list[dict[str, Any]]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _merge_usage(
    left: dict[str, Any] | None, right: dict[str, Any] | None
) -> dict[str, int]:
    total: dict[str, int] = {}
    for source in (left or {}, right or {}):
        for key, value in source.items():
            if isinstance(value, (int, float)):
                total[key] = total.get(key, 0) + int(value)
    return total


def _stage(
    state: WorkflowState,
    name: str,
    status: str,
    started: float,
    *,
    usage: dict[str, Any] | None = None,
    error: str | None = None,
) -> list[dict[str, Any]]:
    stages = list(state.get("stages") or [])
    stages.append(
        {
            "name": name,
            "status": status,
            "duration_ms": int((time.perf_counter() - started) * 1000),
            "usage": usage or {},
            "error": error,
            "at": _now(),
        }
    )
    return stages


def _write_stage_tool_calls(run_id: str, stages: list[dict[str, Any]]) -> None:
    """Expose each workflow stage as a tool/step span in tool_calls.jsonl.

    The product workflow calls Python functions directly, not the writing_v4
    ToolRegistry.  Recording the stage boundary keeps tool/step observability
    honest without inventing a second execution layer.
    """
    rows = []
    for index, stage in enumerate(stages, start=1):
        usage = stage.get("usage") or {}
        rows.append(
            {
                "call_id": f"stage_{index}_{stage.get('name') or 'step'}",
                "run_id": run_id,
                "tool_name": str(stage.get("name") or "step"),
                "actor": "workflow",
                "status": str(stage.get("status") or ""),
                "latency_ms": int(stage.get("duration_ms") or 0),
                "usage": usage,
                "error": stage.get("error"),
                "created_at": stage.get("at") or _now(),
            }
        )
    path = _run_dir(run_id) / "tool_calls.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
    )


def _write_stage_decisions(
    run_id: str,
    values: dict[str, Any],
    stages: list[dict[str, Any]],
) -> None:
    """Record plan/approval/review decisions for the run trace page."""
    rows: list[dict[str, Any]] = []
    for stage in stages:
        name = str(stage.get("name") or "")
        status = str(stage.get("status") or "")
        if name == "plan" and status == "succeeded":
            rows.append(
                {
                    "decision_id": f"dec_{run_id}_plan",
                    "run_id": run_id,
                    "stage": "plan",
                    "question": "这次写哪种形态？",
                    "selected": str(values.get("form") or ""),
                    "decided_by": "lead_planner",
                    "basis": str((values.get("plan") or {}).get("central_idea") or ""),
                    "created_at": stage.get("at") or _now(),
                }
            )
        elif name == "approval":
            rows.append(
                {
                    "decision_id": f"dec_{run_id}_approval",
                    "run_id": run_id,
                    "stage": "approval",
                    "question": "确认计划卡后继续写作？",
                    "selected": status,
                    "decided_by": "auto_approve" if status == "auto_approved" else "user",
                    "created_at": stage.get("at") or _now(),
                }
            )
        elif name == "review":
            rows.append(
                {
                    "decision_id": f"dec_{run_id}_review",
                    "run_id": run_id,
                    "stage": "review",
                    "question": "产物是否验收通过？",
                    "selected": status,
                    "decided_by": "auto_accept" if status == "auto_accepted" else "user",
                    "created_at": stage.get("at") or _now(),
                }
            )
    path = _run_dir(run_id) / "decision_records.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
    )


def _decision(value: Any) -> tuple[str, str]:
    if isinstance(value, dict):
        return str(value.get("decision") or ""), str(value.get("notes") or "")
    return str(value or ""), ""


def intake_node(state: WorkflowState) -> dict[str, Any]:
    started = time.perf_counter()
    form = _normalize_form(str(state.get("form") or ""))
    if form not in FORM_SKILLS:
        return {
            "status": "failed",
            "errors": [f"未知 form：{form}"],
            "stages": _stage(state, "intake", "failed", started, error="未知 form"),
        }
    return {
        "form": form,
        "status": "intake",
        "stages": _stage(state, "intake", "succeeded", started),
    }


def plan_node(state: WorkflowState) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        result = plan_article(
            video_id=str(state["video_id"]),
            form=str(state["form"]),
            request=str(state.get("request") or ""),
            run_id=str(state["run_id"]),
        )
        plan = {
            key: result.get(key)
            for key in (
                "central_idea",
                "reader_goal",
                "angle",
                "brief",
                "must_use_figures",
                "shared_constraints",
                "content_chars",
                "figure_count",
                "form_label",
            )
        }
        usage = _merge_usage(state.get("usage"), result.get("planner_usage"))
        return {
            "plan": plan,
            "status": "planned",
            "usage": usage,
            "stages": _stage(
                state,
                "plan",
                "succeeded",
                started,
                usage=result.get("planner_usage"),
            ),
        }
    except Exception as exc:  # noqa: BLE001 - surface failure in state
        message = f"规划失败：{type(exc).__name__}: {exc}"
        return {
            "status": "failed",
            "errors": [message],
            "stages": _stage(state, "plan", "failed", started, error=message),
        }


def approval_node(state: WorkflowState) -> dict[str, Any]:
    started = time.perf_counter()
    if state.get("auto_approve"):
        return {
            "decision": "approved",
            "status": "planned",
            "stages": _stage(state, "approval", "auto_approved", started),
        }
    value = interrupt(
        {
            "run_id": state.get("run_id"),
            "plan": state.get("plan"),
            "question": "确认计划卡后继续写作？",
            "decisions": ["approved", "changes_requested"],
        }
    )
    decision, _notes = _decision(value)
    approved = decision == "approved"
    return {
        "decision": "approved" if approved else "changes_requested",
        "status": "planned" if approved else "changes_requested",
        "stages": _stage(
            state,
            "approval",
            "approved" if approved else "changes_requested",
            started,
        ),
    }


def write_node(state: WorkflowState) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        result = write_form(run_id=str(state["run_id"]))
        # The Markdown body is already on disk; keep the workflow trace lean.
        result = {key: value for key, value in result.items() if key != "markdown"}
        usage = _merge_usage(state.get("usage"), result.get("usage"))
        status = str(result.get("status") or "written")
        return {
            "write": result,
            "status": status,
            "usage": usage,
            "stages": _stage(
                state,
                "write",
                "succeeded" if status == "written" else status,
                started,
                usage=result.get("usage"),
                error=result.get("error"),
            ),
        }
    except Exception as exc:  # noqa: BLE001
        message = f"写作失败：{type(exc).__name__}: {exc}"
        return {
            "status": "failed",
            "errors": [message],
            "stages": _stage(state, "write", "failed", started, error=message),
        }


def typeset_node(state: WorkflowState) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        result = typeset_article(run_id=str(state["run_id"]))
        status = str(result.get("status") or "typeset")
        errors = list(state.get("errors") or []) + list(
            result.get("typeset_errors") or []
        )
        return {
            "typeset": result,
            "status": status,
            "errors": errors,
            "stages": _stage(
                state,
                "typeset",
                "succeeded" if status == "typeset" else status,
                started,
                error="; ".join(result.get("typeset_errors") or []) or None,
            ),
        }
    except Exception as exc:  # noqa: BLE001
        message = f"排版失败：{type(exc).__name__}: {exc}"
        return {
            "status": "failed",
            "errors": list(state.get("errors") or []) + [message],
            "stages": _stage(state, "typeset", "failed", started, error=message),
        }


def review_node(state: WorkflowState) -> dict[str, Any]:
    started = time.perf_counter()
    if state.get("auto_approve"):
        return {
            "status": state.get("status") or "typeset",
            "stages": _stage(state, "review", "auto_accepted", started),
        }
    value = interrupt(
        {
            "run_id": state.get("run_id"),
            "plan": state.get("plan"),
            "typeset": state.get("typeset"),
            "question": "产物是否验收通过？",
            "decisions": sorted(REVIEW_DECISIONS),
        }
    )
    decision, notes = _decision(value)
    if decision not in REVIEW_DECISIONS:
        decision = "changes_requested"
    try:
        result = review_artifact(
            run_id=str(state["run_id"]), decision=decision, notes=notes
        )
        return {
            "review": result,
            "status": str(result.get("status") or decision),
            "stages": _stage(state, "review", decision, started),
        }
    except Exception as exc:  # noqa: BLE001
        message = f"验收失败：{type(exc).__name__}: {exc}"
        return {
            "status": "failed",
            "errors": list(state.get("errors") or []) + [message],
            "stages": _stage(state, "review", "failed", started, error=message),
        }


def _after_plan(state: WorkflowState) -> str:
    return "approval" if state.get("status") != "failed" else END


def _after_approval(state: WorkflowState) -> str:
    return "write" if state.get("decision") == "approved" else END


def _after_write(state: WorkflowState) -> str:
    return "typeset" if state.get("status") == "written" else END


def build_graph(checkpointer: Any = None):
    graph = StateGraph(WorkflowState)
    graph.add_node("intake", intake_node)
    graph.add_node("plan", plan_node)
    graph.add_node("approval", approval_node)
    graph.add_node("write", write_node)
    graph.add_node("typeset", typeset_node)
    graph.add_node("review", review_node)

    graph.add_edge(START, "intake")
    graph.add_conditional_edges(
        "intake",
        lambda state: "plan" if state.get("status") != "failed" else END,
        {"plan": "plan", END: END},
    )
    graph.add_conditional_edges(
        "plan", _after_plan, {"approval": "approval", END: END}
    )
    graph.add_conditional_edges(
        "approval", _after_approval, {"write": "write", END: END}
    )
    graph.add_conditional_edges(
        "write", _after_write, {"typeset": "typeset", END: END}
    )
    graph.add_edge("typeset", "review")
    graph.add_edge("review", END)
    return graph.compile(checkpointer=checkpointer)


def _workflow_db():
    root = _runs_root()
    root.mkdir(parents=True, exist_ok=True)
    return root / "_workflow_checkpoints.sqlite"


def _chunk_events(chunk: Any) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    if not isinstance(chunk, dict):
        return events
    for node, update in chunk.items():
        if node == "__interrupt__":
            values = (
                [getattr(item, "value", item) for item in update]
                if isinstance(update, (list, tuple))
                else update
            )
            events.append({"type": "interrupt", "value": values, "at": _now()})
        else:
            events.append(
                {
                    "type": "update",
                    "node": node,
                    "keys": sorted(update.keys()) if isinstance(update, dict) else [],
                    "at": _now(),
                }
            )
    return events


def _cost_estimate(usage: dict[str, Any]) -> float | None:
    input_rate = os.getenv("FACET_STUDIO_INPUT_COST_PER_MTOK")
    output_rate = os.getenv("FACET_STUDIO_OUTPUT_COST_PER_MTOK")
    if not input_rate or not output_rate:
        return None
    try:
        prompt = int(usage.get("prompt_tokens", 0) or 0)
        completion = int(usage.get("completion_tokens", 0) or 0)
        return round(
            prompt / 1_000_000 * float(input_rate)
            + completion / 1_000_000 * float(output_rate),
            6,
        )
    except (TypeError, ValueError):
        return None


def _snapshot_result(
    run_id: str, snapshot: Any, events: list[dict[str, Any]]
) -> dict[str, Any]:
    values = dict(snapshot.values or {})
    next_nodes = list(snapshot.next or ())
    if "approval" in next_nodes:
        status = "awaiting_plan_approval"
    elif "review" in next_nodes:
        status = "awaiting_review"
    else:
        status = str(values.get("status") or "unknown")
    interrupts = [
        getattr(item, "value", item)
        for item in (getattr(snapshot, "interrupts", ()) or ())
    ]
    usage = values.get("usage") or {}
    trace_url = None
    if (_run_dir(run_id) / "trace.html").is_file():
        base = str(
            os.environ.get("FACET_STUDIO_PREVIEW_BASE", "http://127.0.0.1:8765/runs")
        ).rstrip("/")
        trace_url = f"{base}/{run_id}"
    return {
        "run_id": run_id,
        "thread_id": run_id,
        "trace_url": trace_url,
        "video_id": values.get("video_id"),
        "form": values.get("form"),
        "request": values.get("request"),
        "status": status,
        "next": next_nodes,
        "interrupt": interrupts[0] if interrupts else None,
        "events": events,
        "stages": values.get("stages") or [],
        "usage": usage,
        "cost_estimate": _cost_estimate(usage),
        "plan": values.get("plan"),
        "write": values.get("write"),
        "typeset": values.get("typeset"),
        "review": values.get("review"),
        "errors": values.get("errors") or [],
        "updated_at": _now(),
    }


def _execute(
    run_id: str,
    payload: Any,
    *,
    check_existing: bool,
    on_event: Any = None,
) -> dict[str, Any]:
    db = _workflow_db()
    with SqliteSaver.from_conn_string(str(db)) as checkpointer:
        app = build_graph(checkpointer)
        config = {"configurable": {"thread_id": run_id}}
        snapshot = app.get_state(config)
        if check_existing and not snapshot.values:
            raise FileNotFoundError(f"workflow 不存在：{run_id}")
        path = _run_dir(run_id) / "workflow.json"
        if check_existing and not snapshot.next and path.is_file():
            return _read_json(path)
        previous = _read_json(path) if path.is_file() else {}
        events: list[dict[str, Any]] = list(previous.get("events") or [])
        step = 0
        for chunk in app.stream(payload, config, stream_mode="updates"):
            chunk_events = _chunk_events(chunk)
            events.extend(chunk_events)
            for event in chunk_events:
                step += 1
                if on_event is not None:
                    try:
                        on_event(event, step, 8)
                    except Exception:  # noqa: BLE001 - progress is advisory
                        pass
            # Keep the trace page live while the workflow is still running.
            # Checks/grounding are deliberately skipped here; they run at the
            # end and would be noisy on an incomplete artifact.
            live_snapshot = app.get_state(config)
            live_result = _snapshot_result(run_id, live_snapshot, events)
            _write_json(path, live_result)
            meta_path = _run_dir(run_id) / "run_meta.json"
            if meta_path.is_file():
                write_trace(
                    run_id,
                    _run_dir(run_id),
                    _read_json(meta_path),
                    live=True,
                    include_checks=False,
                    include_grounding=False,
                )
        snapshot = app.get_state(config)
        result = _snapshot_result(run_id, snapshot, events)
        _write_json(path, result)
        _write_stage_tool_calls(run_id, result.get("stages") or [])
        _write_stage_decisions(
            run_id,
            dict(snapshot.values or {}),
            result.get("stages") or [],
        )
        run_dir = _run_dir(run_id)
        meta_path = run_dir / "run_meta.json"
        if meta_path.is_file():
            write_trace(run_id, run_dir, _read_json(meta_path))
        return result


def start_workflow(
    video_id: str,
    form: str,
    request: str = "",
    auto_approve: bool = False,
    on_event: Any = None,
) -> dict[str, Any]:
    """Start a checkpointed workflow and pause at the plan gate by default."""
    normalized = _normalize_form(form)
    if normalized not in FORM_SKILLS:
        raise ValueError(f"未知 form：{form}")
    run_id = _new_run_id(video_id, normalized)
    if _run_dir(run_id).exists():
        run_id = f"{run_id}_{uuid.uuid4().hex[:6]}"
    state: WorkflowState = {
        "run_id": run_id,
        "video_id": video_id,
        "form": normalized,
        "request": request,
        "auto_approve": auto_approve,
        "errors": [],
        "usage": {},
        "stages": [],
    }
    return _execute(run_id, state, check_existing=False, on_event=on_event)


def resume_workflow(
    run_id: str,
    decision: str,
    notes: str = "",
    on_event: Any = None,
) -> dict[str, Any]:
    """Resume a paused plan or review gate."""
    if decision not in REVIEW_DECISIONS:
        raise ValueError(f"decision 必须是 {sorted(REVIEW_DECISIONS)}")
    return _execute(
        run_id,
        Command(resume={"decision": decision, "notes": notes}),
        check_existing=True,
        on_event=on_event,
    )


def get_workflow(run_id: str) -> dict[str, Any]:
    """Read the persisted workflow trace for a run."""
    path = _run_dir(run_id) / "workflow.json"
    if not path.is_file():
        raise FileNotFoundError(f"workflow 不存在：{run_id}")
    return _read_json(path)
