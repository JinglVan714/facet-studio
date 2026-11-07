"""层 1 · 计划产物（P1 的接口层，先落地最小版）。

为什么要有「计划」这个显式产物（而不是把分片逻辑埋在代码里）：
- 2026 的编排共识是 **确定性控制流 + LLM 推理节点 + 持久执行 runtime** 三者分离
  （MAF 官方："agents handle reasoning, workflows handle control flow"）；
- 计划就是那个「控制流的持久化表示」：它先被算出来、落盘、可复核，
  再由执行器逐项消费；崩溃后能按计划**从上次的步骤继续**，而不是重跑整条管线。

当前版本是**确定性计划**（分片由时间窗 + 所有权规则算出来，不调模型），
所以它天然可复现；后续若引入「LLM 规划器」，产出的仍然是同一个 plan 结构（steps 列表）。
"""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

from .constants import DATA_DIR
from .corpus import load_corpus  # noqa: F401 —— 计划构建不再自己切分片，见 build_layer1_plan

PLAN_VERSION = "plan/v1"


def _step_id(kind: str, index: int) -> str:
    return f"{kind}-{index:03d}"


def build_layer1_plan(video_id: str, chunk_minutes: float = 15.0) -> dict:
    """为「语料 → 知识底稿」生成计划。

    投影层已按新设计重建，不再挂在 L1 计划里；它有自己的 Selector → Writer →
    Reviewer → Renderer → Auditor 流程（`docs/DESIGN-PROJECTION.md`）。
    """
    # ⚠️ 分片必须与 `lmind l1` **同一份实现**。此前这里用 `make_chunks`（句级时间窗）+
    # `extract_chunk_to`（v4 抽取），与 `lmind l1` 的契约分段 + 单元制完全分叉——
    # 实测同一条视频，执行器只切出 **1 片**，`lmind l1` 切 **8 片**。
    # **同一个项目里两条 L1，跑哪条看你敲了哪个命令**，这是最坏的一种不一致。
    from .run_l1 import prepare_l1

    prep = prepare_l1(video_id, chunk_minutes=chunk_minutes)
    chunks = prep["chunks"]
    corpus = prep["corpus"]

    steps: list[dict] = []
    for i, ch in enumerate(chunks):
        steps.append({
            "id": _step_id("extract", i),
            "kind": "extract",
            "chunk_id": ch["chunk_id"],
            # owned 是**单元 id**（不是 sid）：L1 的抽取粒度是 unit，
            # 记成 sid 会让"这一步抽了什么"与产物对不上。
            "owned_units": ch["owned"],
            "range_ms": [ch["first_ms"], ch["last_ms"]],
            "segment_label": ch.get("segment_label"),
            "status": "pending",
            "produces": f"assertions:{ch['chunk_id']}",
        })
    steps.append({"id": _step_id("reduce", 0), "kind": "reduce",
                  "depends_on": [s["id"] for s in steps if s["kind"] == "extract"],
                  "status": "pending",
                  "produces": "assertions.jsonl + relations.jsonl（带覆盖闸门）"})
    steps.append({"id": _step_id("validate", 0), "kind": "validate",
                  "depends_on": [_step_id("reduce", 0)], "status": "pending",
                  "produces": "layer1_report.json"})
    steps.append({"id": _step_id("verify", 0), "kind": "verify",
                  "depends_on": [_step_id("reduce", 0)], "status": "pending",
                  "produces": "verify_report.json"})

    plan = {
        "plan_version": PLAN_VERSION,
        "video_id": video_id,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "goal": "把语料抽成可回链的知识底稿（断言 + 锚点 + 关系），完成校验与复核",
        "planner": "deterministic（契约语义分段 + 所有权裁定；不调模型）",
        "params": {"chunk_minutes": chunk_minutes},
        "chunking": prep["chunking"],          # contract | time_window —— 计划要自报口径
        "inputs": {
            "transcript_sha256": _file_sha256(DATA_DIR / video_id / "transcript" / "transcript.json"),
            "frames_index_sha256": _file_sha256(DATA_DIR / video_id / "frames_index.json"),
            "sentences_total": len(corpus["order"]),
            "sentences_with_content": sum(1 for s in corpus["sentences"].values() if s["has_content"]),
            "frames_total": len(corpus.get("frames") or {}),
            "units_total": prep["ustats"]["unit_count"],
            "content_units": prep["ustats"]["content_unit_count"],
        },
        "steps": steps,
    }
    plan["plan_id"] = "p1-" + hashlib.sha256(
        json.dumps({"v": PLAN_VERSION, "vid": video_id,
                    "steps": [s["id"] for s in steps]}, ensure_ascii=False).encode("utf-8")
    ).hexdigest()[:12]
    return plan


def _file_sha256(p: Path) -> str | None:
    if not p.exists():
        return None
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def write_plan(plan: dict) -> Path:
    base = DATA_DIR / plan["video_id"] / "plans"
    base.mkdir(parents=True, exist_ok=True)
    p = base / f"{plan['plan_id']}.json"
    p.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    return p


def latest_plan(video_id: str) -> dict | None:
    base = DATA_DIR / video_id / "plans"
    if not base.exists():
        return None
    files = sorted(base.glob("p1-*.json"), key=lambda f: f.stat().st_mtime)
    if not files:
        return None
    return json.loads(files[-1].read_text(encoding="utf-8"))


def note_step_done(plan_path: Path, step_id: str, extra: dict | None = None) -> None:
    """把某个步骤标记为 done（供执行器在每步成功后调用；plan 落盘 → 可恢复）。"""
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    for s in plan["steps"]:
        if s["id"] == step_id:
            s["status"] = "done"
            s["finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
            if extra:
                s.update(extra)
            break
    plan_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
