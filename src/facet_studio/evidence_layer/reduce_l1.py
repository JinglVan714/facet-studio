"""层 1 · 跨片协调（Coordinator，P0-2）。

角色定位（见 docs/jd-coverage.md §1）：Extractor 各自写自己的分片；**Coordinator 是唯一的全局写者**。
它做三件事，全部是机械可核对的（不调模型、不引入新的不确定源）：

1. **全局去重**：按「文本指纹 + 锚点指纹」找跨片重复断言；
   保留最早出现的，其余作为 `duplicates_of` 记录在报告里（**不删除**，只标记）。
2. **冲突标记**：同一锚点区间（同一句）上出现语义不同的断言 ⇒ 标 `conflict_group`，
   **两条都保留**（底稿不做真值判断，冲突是事实）。
3. **跨片连接**：把上一片尾部窗口（`prev_tail_ids`）与本片头部断言连起来（`sequence`，标 low），
   让「跨片关系未启用」这个已知盲区变成「有保守连接 + 有计数」。

产物：`assertions_reduced.jsonl` / `relations_reduced.jsonl` / `reduce_report.json`
原始 `assertions.jsonl` 不动（可追溯）。
"""
from __future__ import annotations

import json
from pathlib import Path

from .corpus import sent_key


def _anchor_key(a: dict) -> str:
    return "-".join(sorted(x.get("sid", "") for x in (a.get("anchors") or [])))


def load(path: Path) -> list[dict]:
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def reduce_chunks(video_id: str, substrate_dir: Path) -> dict:
    assertions = load(substrate_dir / "assertions.jsonl")
    relations = load(substrate_dir / "relations.jsonl")

    # ---- 1) 全局去重（按文本指纹 + 锚点指纹）----
    seen: dict[str, str] = {}
    duplicates: list[dict] = []
    kept: list[dict] = []
    for a in assertions:
        fp = f"{sent_key(a.get('text') or '')}|{_anchor_key(a)}"
        if fp in seen:
            duplicates.append({"kept": seen[fp], "dropped": a["id"], "fingerprint": fp})
            a["duplicate_of"] = seen[fp]
            kept.append(a)          # 仍然保留，只是标记
        else:
            seen[fp] = a["id"]
            kept.append(a)

    # ---- 2) 同锚点分组（**不是冲突**）----
    # 口径校准：一句 20–30 秒的口播常含多件事，原子化抽取本来就该在一句上产出多条断言。
    # 所以「同锚点多条」是**正常且期望**的，不是冲突；它只报告规模（一句最多承载几条）。
    # 真正的「冲突」需要语义判定，规则做不到 ⇒ 不在本层下结论（底稿不做真值判断）。
    by_anchor: dict[str, list[dict]] = {}
    for a in kept:
        key = _anchor_key(a)
        if key:
            by_anchor.setdefault(key, []).append(a)
    groups: list[dict] = []
    for key, items in by_anchor.items():
        if len(items) < 2:
            continue
        fps = {sent_key(x.get("text") or "") for x in items}
        if len(fps) > 1:                      # 同一句上出现多条不同断言
            gid = f"g{len(groups):03d}"
            for x in items:
                x["same_anchor_group"] = gid
            groups.append({"group": gid, "anchor": key, "count": len(items),
                           "assertion_ids": [x["id"] for x in items][:12],
                           "note": "同句多断言：原子化的正常结果，并列保留；本条不是冲突判定"})

    # ---- 3) 跨片连接（prev_tail_ids 接线）----
    chunk_order: list[str] = []
    for a in kept:
        if a.get("chunk_id") not in chunk_order:
            chunk_order.append(a.get("chunk_id"))
    by_chunk: dict[str, list[dict]] = {}
    for a in kept:
        by_chunk.setdefault(a.get("chunk_id"), []).append(a)

    cross: list[dict] = []
    for i in range(1, len(chunk_order)):
        prev, cur = chunk_order[i - 1], chunk_order[i]
        prev_tail = by_chunk.get(prev, [])[-3:]      # 上一片尾部 3 条
        cur_head = by_chunk.get(cur, [])[:3]         # 本片头部 3 条
        for pf in prev_tail:
            for ch in cur_head:
                cross.append({
                    "id": f"x{i:03d}-{pf['id']}->{ch['id']}",
                    "chunk_id": cur,
                    "from_id": pf["id"], "to_id": ch["id"], "rel_type": "sequence",
                    "link_kind": "cross_prev_chunk",
                    "confidence": "low",
                    "note": "跨片保守连接（时间连续性），非语义判断",
                    "produced_by": {"model": None, "prompt_version": "reduce/v1",
                                    "produced_at": None, "by": "coordinator-rules"},
                })

    # ---- 落盘 ----
    # ⚠️ 2026-10-16（审计 A1 的同族）：这里此前用裸 `open("w")` 写，**绕开了唯一闸门**——
    # 而闸门的 docstring 恰恰**点名**了 `*_reduced.jsonl`：
    # 「`project.load_assertions()` 优先读它。所以覆盖那个文件，效果等同于覆盖默认产物
    #   ——下游会静默地改读另一份数据，而文件名看起来完全正常。」
    # 也就是说：专门为这个文件建的闸门，这个写者自己没走。
    from .artifacts import OverwriteRefused, guarded_write_jsonl

    try:
        guarded_write_jsonl(substrate_dir / "assertions_reduced.jsonl", kept,
                            what="assertions_reduced.jsonl")
        guarded_write_jsonl(substrate_dir / "relations_reduced.jsonl", relations + cross,
                            what="relations_reduced.jsonl")
    except OverwriteRefused as e:
        raise SystemExit(f"[reduce] {e}") from e

    report = {
        "video_id": video_id,
        "input_assertions": len(assertions),
        "kept_assertions": len(kept),
        "global_duplicates": duplicates,
        "global_duplicate_count": len(duplicates),
        "same_anchor_groups": groups,
        "same_anchor_group_count": len(groups),
        "conflict_policy": "本层不做冲突判定（需语义判断，规则做不到；底稿不做真值判断）——"
                           "若下游需要，应由 Verifier/投影层以显式 flag 表达",
        "cross_chunk_relations": len(cross),
        "cross_chunk_policy": "上一片尾 3 条 × 本片头 3 条，sequence/low，仅表时间连续",
        "chunk_order": chunk_order,
        "by": "coordinator-rules（机械规则，不含模型判断）",
    }
    (substrate_dir / "reduce_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report
