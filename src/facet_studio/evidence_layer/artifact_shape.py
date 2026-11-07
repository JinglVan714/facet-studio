"""产物结构归一化：把任意 shape 的产物拆成统一的 unit 列表。

**为什么独立于证据层**：`iter_units` 读的是产物的 `sections[]`，不是底稿；
它服务于评测 / 指标 / 渲染，不应让证据层反向依赖投影产物结构。

当前 MVP 只注册 `prose_sections`（`sections[] → sentences[]`），
条目型（`items[]`）保留在归一化里供未来 shape 使用，但 MVP 不产出。
"""
from __future__ import annotations


def iter_units(artifact: dict) -> list[dict]:
    """把任何体裁的产物**规范化**成统一单元列表——所有检查函数的唯一入口。

    规范化规则（一处定义，处处受益，新体裁自动兼容）：
    - 分句型（`sentences`）与条目型（`items`）统一成 unit；
    - **`evidence` 一律显式**：缺省即 `supported`（条目型没有主持词的概念）；
    - 保留 `_shape` 供少数确实需要区分的地方使用（如反罗列判据）。
    """
    out: list[dict] = []
    for sec in artifact.get("sections") or []:
        sid = sec.get("section_id")
        for s in sec.get("sentences") or []:
            out.append({**s, "section_id": sid, "_shape": "sentence",
                        "evidence": s.get("evidence") or "supported"})
        for it in sec.get("items") or []:
            out.append({**it, "section_id": sid, "_shape": "item",
                        "evidence": it.get("evidence") or "supported"})
    return out
