"""LangGraph workflow for one product run (P3 prototype).

The graph is intentionally a thin orchestration layer over the existing MCP
tools: it does not rewrite the writing engine and it does not add an editor or
checker.  It adds state, checkpointing, streaming events and two human gates
(plan approval, final acceptance).
"""

from __future__ import annotations

import json
import os
import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Any, TypedDict

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from .mcp_server import (
    FORM_LABELS,
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
    auto_plan: bool
    auto_accept: bool
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


_BACKGROUND_RUNS: dict[str, threading.Thread] = {}
_BACKGROUND_LOCK = threading.Lock()


def _trace_url(run_id: str) -> str:
    base = str(
        os.environ.get("FACET_STUDIO_PREVIEW_BASE", "http://127.0.0.1:8765/runs")
    ).rstrip("/")
    return f"{base}/{run_id}"


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
    if state.get("auto_plan") or state.get("auto_approve"):
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
    if state.get("auto_accept") or state.get("auto_approve"):
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
    auto_plan = bool(values.get("auto_plan") or values.get("auto_approve"))
    auto_accept = bool(values.get("auto_accept") or values.get("auto_approve"))
    if "approval" in next_nodes:
        # In end-to-end mode the approval node is about to auto-run; this
        # transient snapshot must not look like a human gate.
        status = "running" if auto_plan else "awaiting_plan_approval"
    elif "review" in next_nodes:
        status = "typeset" if auto_accept else "awaiting_review"
    else:
        status = str(values.get("status") or "unknown")
    interrupts = [
        getattr(item, "value", item)
        for item in (getattr(snapshot, "interrupts", ()) or ())
    ]
    usage = values.get("usage") or {}
    trace_url = _trace_url(run_id)
    return {
        "run_id": run_id,
        "thread_id": run_id,
        "trace_url": trace_url,
        "video_id": values.get("video_id"),
        "form": values.get("form"),
        "form_label": FORM_LABELS.get(str(values.get("form") or ""), ""),
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
        "summary": _result_summary(values, run_id),
        "assets": _asset_facts(values, run_id),
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


def _asset_facts(values: dict[str, Any], run_id: str = "") -> dict[str, int]:
    """Count what the reader actually receives, not what the writer cited.

    `write.figures_referenced` is pre-visual-audit; a rejected keyframe must
    not reappear in the chat summary as a delivered image. XHS cards are a
    generated cover, not video keyframes, so they are reported separately.
    """
    meta: dict[str, Any] = {}
    if run_id:
        meta_path = _run_dir(run_id) / "run_meta.json"
        if meta_path.is_file():
            try:
                meta = _read_json(meta_path)
            except (OSError, ValueError):
                meta = {}
    write = values.get("write") or meta.get("write") or {}
    typeset = values.get("typeset") or meta.get("typeset") or {}
    visual = meta.get("visual_audit") or {}
    if visual and "approved_count" in visual:
        keyframes = int(visual.get("approved_count") or 0)
    else:
        keyframes = len(
            [
                figure
                for figure in (write.get("figures_referenced") or [])
                if not str(figure).lower().endswith(".svg")
            ]
        )
    svg_assets = write.get("svg_assets") or []
    charts = len(svg_assets)
    if not charts:
        charts = len(
            [
                figure
                for figure in (write.get("figures_referenced") or [])
                if str(figure).lower().endswith(".svg")
            ]
        )
    cards = len(((typeset.get("xhs_export") or {}).get("images") or []))
    if not cards:
        cards = len(((meta.get("artifacts") or {}).get("xhs_cards") or []))
    return {"keyframes": keyframes, "charts": charts, "cards": cards}


def _result_summary(values: dict[str, Any], run_id: str = "") -> str:
    form = str(values.get("form") or "")
    label = FORM_LABELS.get(form, form or "产物")
    write = values.get("write") or {}
    parts = [label, str(values.get("status") or "running")]
    if write.get("output_chars"):
        parts.append(f"{int(write['output_chars']):,} 字")
    assets = _asset_facts(values, run_id)
    if form == "xiaohongshu_note":
        parts.append(f"{assets['cards']} 张卡片")
        parts.append(f"{assets['keyframes']} 张关键帧")
        if assets["charts"]:
            parts.append(f"{assets['charts']} 个图表")
    elif assets["keyframes"] or assets["charts"]:
        if assets["charts"]:
            parts.append(f"{assets['charts']} 个图表")
        parts.append(f"{assets['keyframes']} 张关键帧")
    else:
        parts.append("0 图")
    tokens = _int_usage(values)
    if tokens:
        parts.append(f"{tokens:,} tokens")
    return " · ".join(parts)


def _int_usage(values: dict[str, Any]) -> int:
    usage = values.get("usage") or {}
    try:
        return int(usage.get("total_tokens") or 0)
    except (TypeError, ValueError):
        return 0


def _running_result(run_id: str, state: WorkflowState) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "thread_id": run_id,
        "trace_url": _trace_url(run_id),
        "video_id": state.get("video_id"),
        "form": state.get("form"),
        "form_label": FORM_LABELS.get(str(state.get("form") or ""), ""),
        "request": state.get("request"),
        "status": "running",
        "next": [],
        "interrupt": None,
        "events": [],
        "stages": [],
        "usage": {},
        "cost_estimate": None,
        "plan": None,
        "write": None,
        "typeset": None,
        "review": None,
        "errors": [],
        "summary": _result_summary(dict(state), run_id),
        "assets": {"keyframes": 0, "charts": 0, "cards": 0},
        "updated_at": _now(),
    }


def _init_background_run(run_id: str, state: WorkflowState) -> None:
    """Make run_meta/workflow readable before the first LLM call finishes."""
    run_dir = _run_dir(run_id)
    run_dir.mkdir(parents=True, exist_ok=True)
    meta_path = run_dir / "run_meta.json"
    if not meta_path.is_file():
        _write_json(
            meta_path,
            {
                "schema_version": "product-v1-run",
                "run_id": run_id,
                "video_id": state.get("video_id"),
                "form": state.get("form"),
                "form_label": FORM_LABELS.get(str(state.get("form") or ""), ""),
                "request": state.get("request"),
                "status": "running",
                "created_at": _now(),
            },
        )
    wf_path = run_dir / "workflow.json"
    if not wf_path.is_file():
        _write_json(wf_path, _running_result(run_id, state))


def _background_worker(run_id: str, state: WorkflowState) -> None:
    try:
        _execute(run_id, state, check_existing=False)
    except Exception as exc:  # noqa: BLE001 - surface in the persisted trace
        path = _run_dir(run_id) / "workflow.json"
        previous = _read_json(path) if path.is_file() else _running_result(run_id, state)
        previous.update(
            {
                "status": "failed",
                "errors": [f"{type(exc).__name__}: {exc}"],
                "updated_at": _now(),
            }
        )
        _write_json(path, previous)
    finally:
        with _BACKGROUND_LOCK:
            _BACKGROUND_RUNS.pop(run_id, None)


def start_workflow(
    video_id: str,
    form: str,
    request: str = "",
    auto_approve: bool = False,
    auto_plan: bool = False,
    auto_accept: bool = False,
    background: bool = False,
    on_event: Any = None,
) -> dict[str, Any]:
    """Start a checkpointed workflow.

    ``auto_plan=True`` skips the plan gate (end-to-end by default for chat);
    ``auto_accept=True`` is only for explicit automation and skips user
    acceptance.  ``background=True`` returns a running result immediately so
    the chat can show live progress; use ``wait_workflow`` to await the next
    gate.
    """
    normalized = _normalize_form(form)
    if normalized not in FORM_SKILLS:
        raise ValueError(f"未知 form：{form}")
    run_id = _new_run_id(video_id, normalized)
    if _run_dir(run_id).exists():
        run_id = f"{run_id}_{uuid.uuid4().hex[:6]}"
    legacy = bool(auto_approve)
    state: WorkflowState = {
        "run_id": run_id,
        "video_id": video_id,
        "form": normalized,
        "request": request,
        "auto_approve": legacy,
        "auto_plan": bool(auto_plan) or legacy,
        "auto_accept": bool(auto_accept) or legacy,
        "errors": [],
        "usage": {},
        "stages": [],
    }
    if not background:
        return _execute(run_id, state, check_existing=False, on_event=on_event)
    _init_background_run(run_id, state)
    thread = threading.Thread(
        target=_background_worker,
        args=(run_id, state),
        name=f"facet-workflow-{run_id}",
        daemon=True,
    )
    with _BACKGROUND_LOCK:
        _BACKGROUND_RUNS[run_id] = thread
    thread.start()
    return _running_result(run_id, state)


_WAIT_STATES = {
    "awaiting_plan_approval",
    "awaiting_review",
    "typeset",
    "partial",
    "failed",
    "approved",
    "rejected",
    "changes_requested",
}


def _plan_view(plan: dict[str, Any]) -> dict[str, Any]:
    return {
        key: plan.get(key)
        for key in ("central_idea", "reader_goal", "angle", "must_use_figures")
        if plan.get(key) is not None
    }


def agent_view(result: dict[str, Any]) -> dict[str, Any]:
    """The MCP-facing result: enough for a grounded reply, no full body.

    LibreChat truncates large MCP outputs. Returning `write.output` plus the
    full plan used to cut off the summary and push the model toward stale
    pre-audit figure counts. The trace page and card API read the full
    workflow.json separately.
    """
    plan = result.get("plan") or {}
    write = result.get("write") or {}
    typeset = result.get("typeset") or {}
    review = result.get("review") or {}
    xhs = typeset.get("xhs_export") or {}
    cards = list(xhs.get("images") or xhs.get("card_urls") or [])
    stages = [
        {
            "name": stage.get("name"),
            "status": stage.get("status"),
            "duration_ms": stage.get("duration_ms"),
        }
        for stage in (result.get("stages") or [])
        if isinstance(stage, dict)
    ]
    interrupt = result.get("interrupt")
    interrupt_view: dict[str, Any] | None = None
    if isinstance(interrupt, dict):
        interrupt_view = {
            key: interrupt.get(key)
            for key in ("run_id", "question", "decisions")
            if interrupt.get(key) is not None
        }
        if interrupt.get("plan"):
            interrupt_view["plan"] = _plan_view(interrupt["plan"])
    view: dict[str, Any] = {
        "run_id": result.get("run_id"),
        "video_id": result.get("video_id"),
        "form": result.get("form"),
        "form_label": result.get("form_label"),
        "status": result.get("status"),
        "next": result.get("next") or [],
        "interrupt": interrupt_view,
        "summary": result.get("summary"),
        "assets": result.get("assets")
        or {"keyframes": 0, "charts": 0, "cards": len(cards)},
        "usage": {"total_tokens": _int_usage(result)},
        "stages": stages,
        "errors": result.get("errors") or [],
    }
    if plan:
        view["plan"] = _plan_view(plan)
    if write:
        view["write"] = {
            "output_chars": write.get("output_chars"),
            "title_candidates": write.get("title_candidates") or [],
        }
    if typeset:
        # The chat card owns the preview links. Agents used to paste
        # `preview_url` into the final reply; keep only presence flags so the
        # model cannot leak a raw URL.
        view["typeset"] = {
            "has_preview": bool(
                typeset.get("preview_url")
                or typeset.get("wechat_url")
                or cards
            ),
            "typeset_errors": typeset.get("typeset_errors") or [],
        }
    if review:
        view["review"] = {
            "decision": review.get("decision"),
            "notes": review.get("notes"),
        }
    for key in ("wait_status", "timeout", "error"):
        if key in result:
            view[key] = result[key]
    return view


def wait_workflow(run_id: str, timeout_s: int = 120) -> dict[str, Any]:
    """Wait until the workflow reaches a human gate or a terminal state."""
    run_dir = _run_dir(run_id)
    if not run_dir.is_dir():
        raise FileNotFoundError(f"workflow 不存在：{run_id}")
    deadline = time.time() + max(1, min(int(timeout_s), 300))
    last: dict[str, Any] = {}
    while True:
        path = run_dir / "workflow.json"
        if path.is_file():
            last = _read_json(path)
            status = str(last.get("status") or "")
            if status in _WAIT_STATES:
                return {**last, "wait_status": "ready"}
        with _BACKGROUND_LOCK:
            thread = _BACKGROUND_RUNS.get(run_id)
        if thread is not None and not thread.is_alive():
            if path.is_file():
                last = _read_json(path)
                if str(last.get("status") or "") in _WAIT_STATES:
                    return {**last, "wait_status": "ready"}
            return {
                **last,
                "wait_status": "failed",
                "error": "workflow thread exited before a gate",
            }
        if time.time() >= deadline:
            return {**last, "wait_status": "timeout", "timeout": True}
        time.sleep(0.5)


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
