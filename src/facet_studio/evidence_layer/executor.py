"""层 1 · 执行器：按计划逐步执行，每步落检查点，可中断、可续跑、有审批门（P1）。

设计（对照 2026 的编排共识，见 docs/research/09/10）：
- **计划 = 控制流的持久化表示**（`plans/p1-*.json`，规则算出，可复现）
- **状态 = 执行到哪了**（`runs/<run_id>.json`，每步写一次）——与计划分离，计划不被执行污染
- **幂等**：每步产物各自落盘；重跑默认跳过 `done` 的步骤（崩溃续跑的基础）
- **审批门**：标注为 expensive 的步骤在无批准时**挂起**（interrupt），批准后从原位恢复
- 这套语义与 LangGraph 的 checkpointer / `interrupt()` 同构；等数据契约稳定后可平移到 LangGraph
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

from .constants import DATA_DIR

EXPENSIVE_STEPS = {"extract", "asr"}          # 需要审批门的步骤类型（fallback）
DEFAULT_MODEL = "deepseek-flash"


def needs_approval(step: dict) -> bool:
    """审批门判定：计划里显式声明优先（`needs_approval`），否则按步骤类型兜底。"""
    if "needs_approval" in step:
        return bool(step["needs_approval"])
    return step.get("kind") in EXPENSIVE_STEPS


# ------------------------------------------------------------------ 状态读写

def runs_dir(video_id: str) -> Path:
    return DATA_DIR / video_id / "runs"


def new_run(plan: dict) -> dict:
    return {
        "run_id": f"run-{time.strftime('%Y%m%d-%H%M%S')}-{os.getpid()}",
        "plan_id": plan["plan_id"],
        "video_id": plan["video_id"],
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "status": "running",                  # running | interrupted | done | failed
        "steps": {},                          # step_id -> {status, attempts, elapsed_s, error, note}
        "events": [],                         # 追加式事件流（时间、步骤、事件类型、备注）
    }


def load_run(video_id: str, run_id: str | None = None) -> tuple[dict | None, Path | None]:
    base = runs_dir(video_id)
    if not base.exists():
        return None, None
    files = sorted(base.glob("run-*.json"), key=lambda f: f.stat().st_mtime)
    if not files:
        return None, None
    path = next((f for f in files if f.stem == run_id), files[-1]) if run_id else files[-1]
    return json.loads(path.read_text(encoding="utf-8")), path


def save_run(state: dict, path: Path) -> None:
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def _event(state: dict, step_id: str, kind: str, note: str = "") -> None:
    state["events"].append({"at": time.strftime("%H:%M:%S"), "step": step_id, "event": kind, "note": note})


# ------------------------------------------------------------------ 步骤实现

def _step_extract(step: dict, plan: dict) -> tuple[bool, str]:
    """单片抽取——**与 `lmind l1` 走同一份实现**（`prepare_l1` + `extract_one_chunk`）。

    此前这里自己调 `make_chunks` + `extract_chunk_to`（v4），与 `lmind l1` 完全分叉。
    现在共用，所以**检查点目录也是同一个 `_l1u_chunks/`**：
    先跑过 `lmind l1` 再跑执行器，已抽过的片直接命中，不重复花钱。
    """
    from .run_l1 import prepare_l1, extract_one_chunk, substrate_dir

    vid = plan["video_id"]
    prep = prepare_l1(vid, chunk_minutes=plan["params"].get("chunk_minutes", 15.0))
    chunk = next((c for c in prep["chunks"] if c["chunk_id"] == step["chunk_id"]), None)
    if chunk is None:
        return False, f"计划里的分片不存在：{step['chunk_id']}"
    ckpt = substrate_dir(vid) / "_l1u_chunks"
    r = extract_one_chunk(chunk, prep["corpus"], prep["units_by_id"],
                          plan.get("model", DEFAULT_MODEL), ckpt)
    st = r.get("status") or {}
    note = (f"断言 {len(r['assertions'])} / 关系 {len(r['relations'])}"
            + ("（命中检查点，跳过重跑）" if r.get("_cached") else "")
            + (f" [ESCALATED: {st.get('note')}]" if st.get("escalated") else ""))
    return True, note


def _step_reduce(step: dict, plan: dict) -> tuple[bool, str]:
    """合并分片 → 默认产物。**带覆盖闸门**（`lmind/artifacts.py`）。

    ## 修掉的两条隐患（都实测确认过）

    1. **不再 glob `_chunks/`**：旧写法 `glob("*")` 会把**任何**遗留分片一起合并。
       现在只读计划里这几片，来源明确。
    2. **不再写 `assertions_reduced.jsonl`**：旧路径经 `reduce_chunks` 写那个文件，
       而 `project.load_assertions()` **优先读它**——于是跑一次 `exec` 会让**全部下游**
       静默改读执行器的产物，而文件名看起来完全正常。**这是比直接覆盖更隐蔽的一种破坏。**
       现在两者合并成同一条路，只写默认名 + 闸门。

    真正的"去重/跨片连接"（`reduce_chunks`）没有被丢掉——它只是不再**顺带覆盖默认产物**。
    要跑它请显式调用，产物会带后缀。
    """
    from .artifacts import guarded_write_jsonl, OverwriteRefused

    vid = plan["video_id"]
    sub = DATA_DIR / vid / "substrate"
    want = [s["chunk_id"] for s in plan["steps"] if s["kind"] == "extract"]
    files = [sub / "_l1u_chunks" / f"{cid}.json" for cid in want]
    missing = [f.name for f in files if not f.exists()]
    if missing:
        return False, f"缺少分片产物：{missing[:3]}（共 {len(missing)} 片未抽）"
    assertions, relations = [], []
    for f in files:
        r = json.loads(f.read_text(encoding="utf-8"))
        assertions.extend(r.get("assertions") or [])
        relations.extend(r.get("relations") or [])

    # ⚠️ **写盘前必须先跑一遍 validate**——它不是"额外检查"，它是默认产物的**规范形态**。
    #
    # 原因：`validate_l1.check_assertion()` 会**就地**给断言加上两个派生字段
    # （`quote_hit`、`frame_offsets_ms`），而它们是在做检查时顺手写上的，拆不开。
    # `run_l1_units` 的顺序恰好是"先 validate 再写盘"，所以字段进了文件；
    # 执行器原来是 reduce→写盘→validate，**改写发生在写盘之后，永远进不了文件**。
    #
    # 这不是格式差异，是**内容缺失**：`/quote_hit` 是引文命中级别的唯一记录。
    # 发现它的是那道的覆盖闸门——第一次运行就报了字节不同（`44e87f85c3ef` vs `df44a46b433f`）。
    # **闸门拦下的不是"重复劳动"，是我差点写出去的一份残缺产物。**
    from .corpus import load_corpus
    from .run_l1 import prepare_l1
    from .validate_l1 import validate

    corpus = load_corpus(vid)
    corpus["units_by_id"] = prepare_l1(vid)["units_by_id"]
    validate(assertions, relations, corpus, chunk_ownership={})   # 就地富化，报告此处不用

    try:
        a = guarded_write_jsonl(sub / "assertions.jsonl", assertions, what="assertions.jsonl")
        guarded_write_jsonl(sub / "relations.jsonl", relations, what="relations.jsonl")
    except OverwriteRefused as e:
        return False, str(e)
    verb = "写入" if a["written"] else a["reason"]
    return True, (f"合并 {len(files)} 片 → 断言 {len(assertions)} / 关系 {len(relations)}"
                  f"（{verb}；{a['sha256'][:12]}）")


def _step_validate(step: dict, plan: dict) -> tuple[bool, str]:
    """校验**默认产物**。改口径后必须与 `lmind l1` 一致地读 `assertions.jsonl`
    （此前读 `assertions_reduced.jsonl`——那个文件已不再由管线产生）。"""
    from .corpus import load_corpus
    from .run_l1 import substrate_dir, prepare_l1
    from .validate_l1 import validate, write_report

    vid = plan["video_id"]
    sub = substrate_dir(vid)
    corpus = load_corpus(vid)
    corpus["units_by_id"] = prepare_l1(vid)["units_by_id"]   # 单元级覆盖要用
    assertions = [json.loads(l) for l in (sub / "assertions.jsonl").read_text(
        encoding="utf-8").splitlines() if l.strip()]
    relations = [json.loads(l) for l in (sub / "relations.jsonl").read_text(
        encoding="utf-8").splitlines() if l.strip()]
    rep = validate(assertions, relations, corpus, chunk_ownership={})
    rep["video_id"] = vid
    rep["validated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    write_report(vid, rep, sub)
    return True, (f"断言 {rep['assertion_count']}；句级覆盖 {rep['coverage']['coverage_ratio']}；"
                  f"单元级 {rep['unit_coverage'].get('unit_coverage_ratio')}；"
                  f"错误 {rep['error_count']}")


def _step_verify(step: dict, plan: dict) -> tuple[bool, str]:
    from .verify_l1 import verify_sample

    rep = verify_sample(plan["video_id"], sample_size=12, assertions_file="assertions.jsonl")
    return True, f"抽样 {rep['verifier']['sample_size']}；支撑率 {rep['support_rate']}"


def _step_transcribe(step: dict, plan: dict) -> tuple[bool, str]:
    from .pipeline import step_transcribe as _t

    doc = _t(plan["video_id"], force=False)
    return True, f"转录 {doc['sentence_count']} 句；rtf {doc.get('rtf')}"


def _step_frames(step: dict, plan: dict) -> tuple[bool, str]:
    from .pipeline import step_frames as _f

    idx = _f(plan["video_id"])
    parts = [f"{k}:{v.get('frame_count')}" for k, v in idx["strategies"].items()]
    return True, "抽帧 " + "、".join(parts)


def _step_manifest(step: dict, plan: dict) -> tuple[bool, str]:
    from .pipeline import step_manifest as _m

    m = _m(plan["video_id"])
    return True, f"manifest 写入 {m['video_id']}"


HANDLERS = {
    "extract": _step_extract,
    "reduce": _step_reduce,
    "validate": _step_validate,
    "verify": _step_verify,
    "transcribe": _step_transcribe,
    "frames": _step_frames,
    "manifest": _step_manifest,
}


# ------------------------------------------------------------------ 主体

def step_state(state: dict, step_id: str) -> dict:
    return state["steps"].setdefault(step_id, {"status": "pending", "attempts": 0})


def run_plan(plan: dict, *, run_id: str | None = None, force_steps: set[str] | None = None,
             stop_before: set[str] | None = None, max_steps: int | None = None) -> dict:
    """执行计划。返回最终 state；遇到审批门会以 status=interrupted 返回（可再次调用续跑）。

    - `force_steps`：强制重跑（忽略已完成）
    - `stop_before`：演示用——执行到某步之前停下（模拟崩溃）
    """
    video_id = plan["video_id"]
    runs_dir(video_id).mkdir(parents=True, exist_ok=True)
    state, state_path = load_run(video_id, run_id)
    if state is None or state.get("plan_id") != plan["plan_id"]:
        state = new_run(plan)
        state_path = runs_dir(video_id) / f"{state['run_id']}.json"
        _event(state, "-", "run_created", f"plan {plan['plan_id']}")
    state["status"] = "running"
    save_run(state, state_path)
    print(f"[run] {state['run_id']}  plan={plan['plan_id']}  共 {len(plan['steps'])} 步")

    executed = 0
    for step in plan["steps"]:
        sid, kind = step["id"], step["kind"]
        st = step_state(state, sid)

        if st["status"] == "done" and not (force_steps and sid in force_steps):
            print(f"  [skip] {sid}（已完成）")
            continue
        if stop_before and sid in stop_before:
            state["status"] = "interrupted"
            _event(state, sid, "stop_before", "演示：执行到该步之前停下")
            print(f"  [stop] 在 {sid} 之前停下（模拟崩溃）")
            save_run(state, state_path)
            return state

        # 审批门：声明需要批准的步骤在无批准时挂起（interrupt），批准后从原位恢复
        if needs_approval(step) and not st.get("approved"):
            state["status"] = "interrupted"
            st["status"] = "awaiting_approval"
            _event(state, sid, "interrupt", "需要人工批准（昂贵操作）")
            save_run(state, state_path)
            print(f"  [GATE] {sid} 需要批准：{step.get('produces', kind)}"
                  f"\n         批准：python -m lmind.cli approve {video_id} {sid}")
            return state

        handler = HANDLERS.get(kind)
        if handler is None:
            st.update(status="failed", error=f"没有实现 {kind} 的处理器")
            _event(state, sid, "failed", st["error"])
            save_run(state, state_path)
            continue

        print(f"  [run ] {sid} …", flush=True)
        st["attempts"] += 1
        t0 = time.time()
        try:
            ok, note = handler(step, plan)
        except Exception as e:  # noqa: BLE001
            ok, note = False, f"{type(e).__name__}: {e}"
        st["elapsed_s"] = round(time.time() - t0, 1)
        st["note"] = note
        st["status"] = "done" if ok else "failed"
        st["error"] = None if ok else note
        _event(state, sid, st["status"], note)
        save_run(state, state_path)
        print(f"  [{'ok  ' if ok else 'FAIL'}] {sid}  {st['elapsed_s']}s  {note}")

        executed += 1
        if max_steps and executed >= max_steps:
            state["status"] = "interrupted"
            _event(state, sid, "max_steps", f"达到 max_steps={max_steps}")
            save_run(state, state_path)
            print(f"  [pause] 达到 max_steps={max_steps}，状态已保存")
            return state

    state["status"] = "done"
    state["finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    _event(state, "-", "run_done", "")
    save_run(state, state_path)
    return state


def approve(video_id: str, step_id: str, run_id: str | None = None) -> dict:
    """批准某个卡在审批门的步骤（批准后再次 run_plan 即从该步恢复）。"""
    state, path = load_run(video_id, run_id)
    if state is None or path is None:
        raise FileNotFoundError("没有可继续的 run")
    st = step_state(state, step_id)
    if st.get("status") != "awaiting_approval":
        raise RuntimeError(f"{step_id} 当前状态是 {st.get('status')}，不是在等批准")
    st["approved"] = True
    st["approved_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    _event(state, step_id, "approved", "人工批准")
    save_run(state, path)
    return state


def summarize(state: dict) -> str:
    done = sum(1 for s in state["steps"].values() if s["status"] == "done")
    waiting = [k for k, s in state["steps"].items() if s["status"] == "awaiting_approval"]
    failed = [k for k, s in state["steps"].items() if s["status"] == "failed"]
    pending = [k for k, s in state["steps"].items() if s["status"] == "pending"]
    return (f"status={state['status']}  done={done}/{len(state['steps'])}  "
            f"待批准={waiting or '无'}  failed={failed or '无'}  pending={len(pending)}")
