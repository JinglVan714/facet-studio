"""层 1.5 · 一致性契约：**分片之前**先对全片建一个全局对象。

## 为什么要有它

现在的分片由**时钟**决定（`CHUNK_MINUTES = 15.0`，`corpus.make_chunks`）。后果实测：
- `precision:"sentence"` 降级回退时锚点指向**另一句话**（6 条，全部来自边界处）；
- "跨片关系"是长期挂账的已知盲区（`prev_tail_ids` 硬编码空）。

改成**先建契约、再按语义边界分片**之后，边界落在话题真的换了的地方，
而且**契约本身可机械验收**（首尾相接？无缝？无重叠？覆盖全片？）——
现在没有任何东西可以验收分片。

## 契约的四个组件（spec §2.2a）与本次实现范围

| 组件 | 生产者 | 状态 |
|---|---|---|
| **主题分段** | 模型（全片一次） | ✅ 本文件实现（**分片的地基**） |
| **术语表** | **机械** | ✅ 本文件实现 |
| 事实首现表 | 模型 | ⏳ 留给 SELECT 用，晚一步 |
| 载体清单 | 半机械 | ⏳ 同上 |

**参照实现**：`neopen/story-shot-agent` 的 `continuity_guardian/consistency_contract.py`
（全局契约先建、分片引用）与 `long_script_chunker.py`（按语义边界切、允许重叠、entry/exit 状态）。
**只借机制，不借领域模型**（那套是剧情类的角色/情绪/镜头）。
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from .structured_out import call_with_repair

CONTRACT_VERSION = "contract/v1"
SEG_MIN, SEG_MAX = 2, 10          # 段数范围（软边界，写进提示词；校验只查拼接正确性）
SEG_SEARCH_SCOPE = "全文按时间线性化后的 unit 序列"

SEGMENT_SYSTEM = """你在为一段视频做**主题分段**——这是**全片一次**的任务，不是逐段任务。

给你全片的单元（unit）清单，按时间排序，每条带 id、毫秒、**逐字原文**。

请把全片切成若干段，输出每段的：
- `segment_id`：`seg1`、`seg2`…（顺序即时间顺序）
- `start_unit_id` / `end_unit_id`：该段的**首尾单元 id**（必须逐字来自给你的清单）
- `label`：一句话说明这一段在讲什么（**不超过 20 字**）

硬规则（违反会被校验器打回）：
1. **必须首尾相接、无缝、无重叠**：第 i 段 `end_unit_id` 的**下一个单元**，必须正好是第 i+1 段的 `start_unit_id`；
2. **第一段**必须从清单的**第一个**单元开始；**最后一段**必须到清单的**最后一个**单元结束；
3. 段边界要落在**话题真的换了**的地方——不要按等长时间切，也不要把同一话题切成两段；
4. 段数由内容决定（通常 3–8 段）。内容单一的视频可以只有 2 段。

你只做**切分与标签**，不做摘要、不做筛选、不删任何单元。

输出：只输出严格 JSON，不要 Markdown 代码块，不要解释文字。
"""

SEGMENT_USER = """全片共 {n} 个单元。

## 单元清单（id [毫秒] 逐字原文）
{lines}

## 输出 JSON 格式
{{
  "segments": [
    {{"segment_id": "seg1", "start_unit_id": "…", "end_unit_id": "…", "label": "…"}},
    {{"segment_id": "seg2", "start_unit_id": "…", "end_unit_id": "…", "label": "…"}}
  ]
}}
"""


def _linearize(units: list[dict]) -> list[dict]:
    """全片单元的**确定性线性化**：按 (有无时间, 起止, unit_id) 排。

    契约的所有校验都相对这个序列做——"首尾相接"因此是**可机械判定的**。
    """
    return sorted([u for u in units if (u.get("t") or [None])[0] is not None],
                  key=lambda u: (u["t"][0], u["t"][1], u["unit_id"]))


def render_units_for_contract(seq: list[dict], max_len: int = 60) -> str:
    out = []
    for u in seq:
        t = (u["t"][0] or 0) / 1000
        raw = (u.get("raw") or "").strip()
        if len(raw) > max_len:
            raw = raw[:max_len] + "…"
        out.append(f"- {u['unit_id']} [{t:.0f}s] {raw}")
    return "\n".join(out)


# ------------------------------------------------------------------ 校验（机械）

def validate_segments(segments, seq: list[dict]) -> list[str]:
    """相对线性化序列校验：**首尾相接、无缝、无重叠、覆盖全片**。

    这是契约里唯一能机械判定的部分；段标签的**语义**质量没有机械办法验收——
    所以 spec 写明：**unit 是全局的、与分段无关 ⇒ 分段坏只影响上下文装配、不坏数据。**
    """
    errs: list[str] = []
    if not isinstance(segments, list) or not segments:
        return ["segments 为空或不是数组"]
    ids = [u["unit_id"] for u in seq]
    pos = {uid: i for i, uid in enumerate(ids)}
    for i, s in enumerate(segments):
        tag = f"segments[{i}]"
        if not isinstance(s, dict):
            errs.append(f"{tag} 不是对象"); continue
        for k in ("segment_id", "start_unit_id", "end_unit_id", "label"):
            v = s.get(k)
            if not (isinstance(v, str) and v.strip()):
                errs.append(f"{tag} 缺 {k}")
        a, b = s.get("start_unit_id"), s.get("end_unit_id")
        if a not in pos:
            errs.append(f"{tag} start_unit_id 不在清单里：{a}"); continue
        if b not in pos:
            errs.append(f"{tag} end_unit_id 不在清单里：{b}"); continue
        if pos[a] > pos[b]:
            errs.append(f"{tag} 起点在终点之后：{a} > {b}")
    if errs:
        return errs
    if pos[segments[0]["start_unit_id"]] != 0:
        errs.append(f"第一段没有从全片第一个单元开始（应为 {ids[0]}，实为 "
                    f"{segments[0]['start_unit_id']}）")
    if pos[segments[-1]["end_unit_id"]] != len(ids) - 1:
        errs.append(f"最后一段没有到全片最后一个单元结束（应为 {ids[-1]}，实为 "
                    f"{segments[-1]['end_unit_id']}）")
    for i in range(len(segments) - 1):
        cur_end = pos[segments[i]["end_unit_id"]]
        nxt_start = pos[segments[i + 1]["start_unit_id"]]
        if nxt_start != cur_end + 1:
            if nxt_start <= cur_end:
                errs.append(f"segments[{i}] 与 [{i+1}] 重叠或倒序："
                            f"{segments[i]['end_unit_id']} → {segments[i+1]['start_unit_id']}")
            else:
                gap = ids[cur_end + 1:nxt_start]
                errs.append(f"segments[{i}] 与 [{i+1}] 之间有空洞（{len(gap)} 个单元未归属，"
                            f"如 {gap[:3]}）")
    return errs


# ------------------------------------------------------------------ 术语表（机械）

_LATIN = re.compile(r"[A-Za-z][A-Za-z0-9_.\-]{1,}")
_QUOTED = re.compile(r"[“\"']([^”\"']{2,16})[”\"']")
_STOP = {"the", "and", "for", "with", "that", "this", "you", "are", "was", "not"}


def build_term_table(seq: list[dict], min_count: int = 1) -> dict:
    """**机械**术语表：专名/术语候选 + 首次出现的单元。

    与分段不同，这一项完全可复算（纯字符串统计），所以它在契约里的可信级别是 ✅。
    **但它只是候选**——"这是不是一个术语"仍需判断，所以下游只能当检索线索用，不能当事实。
    """
    hits: dict[str, dict] = {}

    def bump(term: str, u: dict) -> None:
        t = term.strip()
        if not t or len(t) < 2 or t.lower() in _STOP:
            return
        r = hits.setdefault(t, {"term": t, "count": 0, "first_unit_id": u["unit_id"],
                                "first_ms": u["t"][0], "via": set()})
        r["count"] += 1
        r["via"].add("latin" if t[0].isascii() else "quoted")

    for u in seq:
        raw = u.get("raw") or ""
        for m in _LATIN.finditer(raw):
            bump(m.group(0), u)
        for m in _QUOTED.finditer(raw):
            bump(m.group(1), u)

    terms = [{**v, "via": sorted(v["via"])} for v in hits.values() if v["count"] >= min_count]
    terms.sort(key=lambda x: (x["first_ms"] or 0, x["term"]))
    return {"count": len(terms), "terms": terms}


# ------------------------------------------------------------------ 构建

def build_contract(client, model: str, seq: list[dict], out_dir: Path | None = None) -> dict:
    """全片一次扫描 → 契约（分段 + 术语表）。**分段走有界修复链，绝不放行非法拼接。**"""
    user = SEGMENT_USER.format(n=len(seq), lines=render_units_for_contract(seq))
    out = call_with_repair(client, model, SEGMENT_SYSTEM, user,
                           lambda d: validate_segments(d.get("segments"), seq),
                           stage="l1_contract", version=CONTRACT_VERSION)
    if not out.ok:
        raise RuntimeError(f"契约（分段）生成失败：{out.note()}")

    segs = []
    pos = {u["unit_id"]: i for i, u in enumerate(seq)}
    for s in out.data["segments"]:
        a, b = pos[s["start_unit_id"]], pos[s["end_unit_id"]]
        segs.append({
            "segment_id": s["segment_id"], "label": (s.get("label") or "").strip(),
            "start_unit_id": s["start_unit_id"], "end_unit_id": s["end_unit_id"],
            "unit_ids": [u["unit_id"] for u in seq[a:b + 1]],
            "first_ms": seq[a]["t"][0], "last_ms": seq[b]["t"][1],
        })

    terms = build_term_table(seq)
    contract = {
        "version": CONTRACT_VERSION,
        "video_id": None,
        "unit_count": len(seq),
        "segments": segs,
        "terms": terms,
        "produced_by": {"model": model, "prompt": "contract/v1", "attempts": out.attempts},
        "components": {
            "segments": {"producer": "model", "credit": "structure_verifiable_semantics_not"},
            "terms": {"producer": "code", "credit": "reproducible"},
            "first_mention": {"producer": None, "credit": None, "status": "not_built"},
            "carriers": {"producer": None, "credit": None, "status": "not_built"},
        },
        "note": ("unit 是全局的、与分段无关 ⇒ 分段坏只影响上下文装配，不坏数据。"
                 "段标签是 advisory，不进任何门禁。"),
    }
    return contract


def make_contract_chunks(contract: dict, units: list[dict],
                         context_units: int = 12) -> list[dict]:
    """契约驱动的分片（取代 `units.make_unit_chunks` 的时间窗）。

    三条规则（spec §2.2b）：
    1. **数据不重叠**：单元只属于一段（契约校验已保证首尾相接、无缝、无重叠）；
    2. **工作上下文可重叠**：每片多看前后各 `context_units` 个单元——这是"允许重叠"那一半；
    3. **entry/exit 状态**：用**相邻段的标签**做免费近似（`prev_label` / `next_label`）。

    对标 `story-shot-agent` 的 `long_script_chunker`：按场景边界切、`overlap_scenes=3`、
    带 `entry/exit` 状态。**只借机制**——它是剧情类的角色状态，我们是知识类的话题标签。
    """
    by_id = {u["unit_id"]: u for u in units}
    seq = _linearize(units)
    pos = {u["unit_id"]: i for i, u in enumerate(seq)}
    segs = contract.get("segments") or []
    out = []
    for i, sg in enumerate(segs):
        uids = [u for u in sg.get("unit_ids") or [] if u in by_id]
        if not uids:
            continue
        lo = pos[uids[0]] - context_units
        hi = pos[uids[-1]] + context_units
        ctx = [u["unit_id"] for u in seq[max(0, lo):hi + 1] if u["unit_id"] not in set(uids)]
        out.append({
            "chunk_id": sg["segment_id"],
            "owned": uids,
            "context": ctx,
            "first_ms": sg.get("first_ms"), "last_ms": sg.get("last_ms"),
            "segment_label": sg.get("label"),
            "prev_label": segs[i - 1].get("label") if i > 0 else None,
            "next_label": segs[i + 1].get("label") if i + 1 < len(segs) else None,
            "chunking": "contract",
        })
    return out


def write_contract(contract: dict, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    p = out_dir / "contract.json"
    p.write_text(json.dumps(contract, ensure_ascii=False, indent=2), encoding="utf-8")
    return p
