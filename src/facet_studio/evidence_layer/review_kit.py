"""人工核定套件：时间锚点的人工基准。

锚点准不准必须有人听原片；没有人工基准就算不出 R@1/mIoU。
产物在 `data/review/anchor_review_<video>.json`：抽 N 条断言，附「原句 + 自动锚点区间」，
`gold_start_ms` / `gold_end_ms` 留空待人填。
填完后在 Python 里调用 `lmind.standard_metrics.anchor_grounding(<video>, gold_path)`。
"""
from __future__ import annotations

import json
from pathlib import Path

from .constants import DATA_DIR


def build_anchor_review(video_id: str, n: int = 15,
                        out_dir: Path | None = None) -> dict:
    """抽断言做时间锚点人工核定。

    抽法（可复核）：按时间均匀分层抽样，优先抽**字级/单元级锚点**（可精确定位的那批），
    每条给出「自动锚点区间」与「锚点句原文」，人只需听过原片后填 gold 区间。
    """
    from .corpus import load_corpus
    from .evidence import load_assertions

    corpus = load_corpus(video_id)
    rows = []
    for a in load_assertions(video_id):
        an = (a.get("anchors") or [{}])[0]
        sid = an.get("sid")
        src = (corpus["sentences"].get(sid) or {}).get("text") or ""
        if an.get("precision") not in ("word", "unit"):
            continue
        rows.append({
            "assertion_id": a["id"],
            "assertion_text": a.get("text"),
            "quote": a.get("quote"),
            "source_sentence": src,
            "auto_start_ms": an.get("start_ms"),
            "auto_end_ms": an.get("end_ms"),
            "auto_readable": f"{(an.get('start_ms') or 0)/1000:.1f}s–{(an.get('end_ms') or 0)/1000:.1f}s",
            "gold_start_ms": None,
            "gold_end_ms": None,
            "note": "听完原片对应位置后填 gold_start_ms / gold_end_ms（毫秒）。"
                    "若这句话原片里根本没说，填 gold_start_ms = -1 表示「不存在」。",
        })
    if len(rows) > n:
        # 分层：按时间排序后等距抽，避免全挤在一处
        step = len(rows) / n
        rows = [rows[int(i * step)] for i in range(n)]

    out_dir = out_dir or DATA_DIR / "review"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"anchor_review_{video_id}.json"
    out.write_text(json.dumps({
        "video_id": video_id,
        "how_to": "听/看原片对应位置，填 gold_start_ms 与 gold_end_ms（毫秒）。"
                  "填完调用 lmind.standard_metrics.anchor_grounding(video_id, gold_path)。",
        "items": rows,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"file": str(out), "count": len(rows)}
