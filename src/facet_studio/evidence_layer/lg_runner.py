"""LangGraph 版执行器（C 阶段）：把手写执行器平移到 LangGraph。

与手写版的**映射关系**（面试可讲这是"平移而非重写"）：
| 手写执行器                      | LangGraph 版                                          |
|--------------------------------|-------------------------------------------------------|
| `plans/p1-*.json`（计划）       | 同一个计划文件，作为图的 `state["plan"]`               |
| `runs/run-*.json`（检查点）     | **`SqliteSaver` 的 thread 检查点**（官方持久化）        |
| `approve()` + `status=awaiting` | **中断 + `update_state` 批准 + 恢复**（同 `interrupt` 语义）|
| `--stop-before` / `--max-steps` | 同一个语义，收敛进图内的「能不能继续」判定              |
| `execute_one()`（步骤实现）     | **完全复用**（`lmind/steps.py`，幂等）                  |

关键设计：
- **单节点循环 + 步索引**：下一步是什么是**数据**（计划 + 索引），不是拓扑——
  加步骤类型不用改图（图管控制流、数据管内容，正是 research/09 的编排分层）。
- **「能不能继续」只有一处判定**（`_can_continue`）：中断（审批门/演示/暂停）与结束
  都从这一处返回，避免 runner 与 route 各判一次导致行为不一致。
- 幂等由 `steps.execute_one` 保证：LangGraph 恢复时会重跑节点，官方要求副作用幂等。
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import TypedDict

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph

from .constants import DATA_DIR
from .steps import execute_one, needs_approval


class RunState(TypedDict, total=False):
    plan: dict
    step_index: int
    records: dict
    events: list
    stop_before: str | None
    max_steps: int | None
    executed: int


def _db_path(video_id: str) -> Path:
    d = DATA_DIR / video_id / "runs"
    d.mkdir(parents=True, exist_ok=True)
    return d / "langgraph.sqlite"


def init_state(plan: dict, *, stop_before: str | None = None,
               max_steps: int | None = None) -> RunState:
    return {"plan": plan, "step_index": 0, "records": {}, "events": [],
            "stop_before": stop_before, "max_steps": max_steps, "executed": 0}


# ------------------------------------------------------------------ 图

def _step_node(state: RunState) -> RunState:
    plan = state["plan"]
    idx = state.get("step_index", 0)
    steps = plan["steps"]
    if idx >= len(steps):
        return {}

    step = steps[idx]
    sid = step["id"]
    records = dict(state.get("records") or {})
    events = list(state.get("events") or [])
    rec = dict(records.get(sid) or {"status": "pending", "attempts": 0})

    if rec.get("status") == "done":                     # 续跑：已完成直接跳过（幂等）
        events.append({"at": time.strftime("%H:%M:%S"), "step": sid,
                       "event": "skip", "note": "已完成（检查点恢复）"})
        return {"step_index": idx + 1, "records": records, "events": events,
                "executed": int(state.get("executed") or 0) + 1}

    t0 = time.time()
    rec["attempts"] = int(rec.get("attempts") or 0) + 1
    try:
        ok, note = execute_one(step, plan)
    except Exception as e:  # noqa: BLE001
        ok, note = False, f"{type(e).__name__}: {e}"
    rec.update(status="done" if ok else "failed", elapsed_s=round(time.time() - t0, 1),
               note=note, error=None if ok else note)
    records[sid] = rec
    events.append({"at": time.strftime("%H:%M:%S"), "step": sid,
                   "event": rec["status"], "note": note})
    return {"step_index": idx + 1, "records": records, "events": events,
            "executed": int(state.get("executed") or 0) + 1}


def _can_continue(state: RunState) -> tuple[bool, str, str | None]:
    """唯一的「能不能继续」判定。返回 (可否继续, 原因, 待批准的步骤 id)。"""
    plan = state["plan"]
    steps = plan["steps"]
    idx = state.get("step_index", 0)
    if idx >= len(steps):
        return False, "finished", None

    sid = steps[idx]["id"]
    if state.get("stop_before") and sid == state["stop_before"]:
        return False, "stopped_before", None
    ms = state.get("max_steps")
    if ms and int(state.get("executed") or 0) >= ms:
        return False, "max_steps", None

    step = steps[idx]
    rec = (state.get("records") or {}).get(sid) or {}
    if needs_approval(step) and not rec.get("approved"):
        return False, "awaiting_approval", sid
    return True, "running", None


def _route(state: RunState) -> str:
    ok, _why, _sid = _can_continue(state)
    return "step" if ok else END


def build_graph(video_id: str):
    """编译图；返回 (app, saver_cm)。检查点落 `data/<id>/runs/langgraph.sqlite`。"""
    g = StateGraph(RunState)
    g.add_node("step", _step_node)
    g.add_edge(START, "step")
    g.add_conditional_edges("step", _route, {"step": "step", END: END})
    saver_cm = SqliteSaver.from_conn_string(str(_db_path(video_id)))
    saver = saver_cm.__enter__()
    return g.compile(checkpointer=saver), saver_cm


# ------------------------------------------------------------------ 对外接口

def _config(thread: str) -> dict:
    return {"configurable": {"thread_id": thread}}


def run_langgraph(plan: dict, *, stop_before: str | None = None, max_steps: int | None = None,
                  thread: str | None = None, verbose: bool = True) -> dict:
    video_id = plan["video_id"]
    thread = thread or plan["plan_id"]
    app, _cm = build_graph(video_id)
    config = _config(thread)

    snap = app.get_state(config)
    if not snap.values:                       # 首个 run：写入初始状态
        app.update_state(config, init_state(plan, stop_before=stop_before, max_steps=max_steps))
    else:                                     # 续跑：更新演示/暂停参数
        app.update_state(config, {"stop_before": stop_before, "max_steps": max_steps})

    if verbose:
        print(f"[lg] thread={thread}  plan={plan['plan_id']}  共 {len(plan['steps'])} 步")

    while True:
        snap = app.get_state(config)
        values = dict(snap.values or {})
        ok, why, sid = _can_continue(values)
        if not ok:
            break
        nxt = values["plan"]["steps"][values.get("step_index", 0)]["id"]
        if verbose:
            print(f"  [run ] {nxt} …", flush=True)
        app.invoke(None, config)
        if verbose:
            snap2 = app.get_state(config)
            rec = ((snap2.values or {}).get("records") or {}).get(nxt) or {}
            print(f"  [{'ok  ' if rec.get('status') == 'done' else 'FAIL'}] {nxt}  "
                  f"{rec.get('elapsed_s')}s  {rec.get('note')}")

    return status_of(video_id, plan, thread=thread)


def approve_step(video_id: str, plan: dict, step_id: str, thread: str | None = None,
                 verbose: bool = True) -> dict:
    """批准某步并继续（等价手写版的 approve + 再次 exec）。"""
    thread = thread or plan["plan_id"]
    app, _cm = build_graph(video_id)
    config = _config(thread)
    snap = app.get_state(config)
    records = dict((snap.values or {}).get("records") or {})
    rec = dict(records.get(step_id) or {})
    if rec.get("approved"):
        raise RuntimeError(f"{step_id} 已经批准过了")
    rec["approved"] = True
    rec["approved_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    records[step_id] = rec
    app.update_state(config, {"records": records})     # 人工介入：改状态后从原位继续
    return run_langgraph(plan, thread=thread, verbose=verbose)


def status_of(video_id: str, plan: dict, thread: str | None = None) -> dict:
    thread = thread or plan["plan_id"]
    app, _cm = build_graph(video_id)
    config = _config(thread)
    snap = app.get_state(config)
    values = dict(snap.values or {})

    # ⚠️ **这个 thread 还没有任何检查点时必须早退**：空快照里没有 `plan` 键，
    # 而 `_can_continue()` 第一行就是 `state["plan"]` ⇒ 直接 KeyError。
    # 触发条件恰恰是**最普通的一次使用**：对一条从没跑过 LangGraph 的视频敲 `lg-status`。
    # （实测：`./run.sh lg-status BV1B5411A7ax` → `[ERROR] KeyError: 'plan'`。
    #  同文件的 `state_history()` 用了 `(v.get("plan") or {})` 所以没崩——
    #  同一份数据、两种写法、只崩一个，正是"未跑过的路径没人走过"的典型。）
    if not values.get("plan"):
        steps = plan.get("steps") or []
        return {
            "thread": thread, "status": "not_started",
            "reason": "这个 thread 还没有检查点（该视频没跑过 langgraph 执行器）",
            "done": 0, "failed": [], "total": len(steps), "step_index": 0,
            "next_step": steps[0]["id"] if steps else None,
            "pending_approval": None, "records": {}, "events": [],
            "db": str(_db_path(video_id)),
        }

    ok, why, sid = _can_continue(values)
    steps = plan["steps"]
    idx = values.get("step_index", 0)
    records = values.get("records") or {}
    return {
        "thread": thread,
        "status": ("done" if why == "finished" else
                   "awaiting_approval" if why == "awaiting_approval" else
                   "paused" if why in ("stopped_before", "max_steps") else "running"),
        "reason": why,
        "done": sum(1 for r in records.values() if r.get("status") == "done"),
        "failed": [k for k, r in records.items() if r.get("status") == "failed"],
        "total": len(steps),
        "step_index": idx,
        "next_step": steps[idx]["id"] if idx < len(steps) else None,
        "pending_approval": sid,
        "records": records,
        "events": values.get("events") or [],
        "db": str(_db_path(video_id)),
    }


def state_history(video_id: str, plan: dict, thread: str | None = None, limit: int = 20) -> list[dict]:
    """time travel 素材：列出该 thread 的历史检查点（LangGraph 原生能力）。"""
    thread = thread or plan["plan_id"]
    app, _cm = build_graph(video_id)
    out = []
    for i, snap in enumerate(app.get_state_history(_config(thread))):
        if i >= limit:
            break
        v = snap.values or {}
        out.append({"checkpoint_id": snap.config["configurable"].get("checkpoint_id"),
                    "step_index": v.get("step_index"), "created_at": getattr(snap, "created_at", None),
                    "next": (v.get("plan") or {}).get("steps", [{}])[v.get("step_index", 0)]["id"]
                            if v.get("step_index", 0) < len((v.get("plan") or {}).get("steps") or []) else None})
    return out
