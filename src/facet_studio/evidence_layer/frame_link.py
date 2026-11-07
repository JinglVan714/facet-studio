"""帧 ↔ 断言关联（机械层）：把"视觉线索"接进底稿，而不逼模型猜。

为什么用机械算法而不是让模型判（实测教训）：
- 我先试过「按断言强制模型引用帧」⇒ 130+ 条逐条补引用，有界修复链兜不住（3 次尝试后
  ESCALATE，产出 0 断言）；
- 更重要的是**原则问题**：模型不引用，可能正因为那些帧确实支撑不了那条断言。
  逼它引用 = 让它编证据，与「证据不足就留空」直接冲突。

所以改成：**机器算候选**（文本可比的字面关联），标注为 `frame_candidates`，
与模型给的 `frame_refs` **分开放**——一个是模型判断，一个是可复算的机器信号，互不冒名。

召回口径（保守）：
1. **数字命中**：断言里的数字（含单位）出现在帧文字里 ⇒ 候选（命中最强）；
2. **术语命中**：断言里的引号术语 / 专名出现在帧文字里 ⇒ 候选；
3. **字符 n-gram 重叠**：断言与帧文字的最长公共子串 ≥ min_overlap 字 ⇒ 候选（兜底）。

每条候选带 `matched_by`（命中方式）与 `overlap`（重叠长度），**可复核、可复算**。
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from .constants import DATA_DIR
from .evidence import _NUMERIC, _TERM

FRAME_LINK_VERSION = "frame_link/v1"


def _longest_common_substring_len(a: str, b: str) -> int:
    """最长公共子串长度（用于兜底匹配）。串长可控（断言 ≤ 100 字，帧文字已截断）。"""
    if not a or not b:
        return 0
    best = 0
    prev = [0] * (len(b) + 1)
    for i in range(1, len(a) + 1):
        cur = [0] * (len(b) + 1)
        ai = a[i - 1]
        for j in range(1, len(b) + 1):
            if ai == b[j - 1]:
                cur[j] = prev[j - 1] + 1
                if cur[j] > best:
                    best = cur[j]
        prev = cur
    return best


def _frames_with_text(video_id: str) -> dict[str, str]:
    """{fid: 文字}——合并该视频所有帧转录产物。"""
    out: dict[str, str] = {}
    base = DATA_DIR / video_id
    for p in sorted(base.glob("frames_vlm*.json")):
        doc = json.loads(p.read_text(encoding="utf-8"))
        for fid, rec in (doc.get("per_frame") or {}).items():
            if rec.get("text"):
                out.setdefault(fid, rec["text"])
    return out


def _frame_time_index(video_id: str) -> dict[str, int]:
    p = DATA_DIR / video_id / "frames_index.json"
    if not p.exists():
        return {}
    doc = json.loads(p.read_text(encoding="utf-8"))
    idx = {}
    for st in (doc.get("strategies") or {}).values():
        for f in st.get("frames") or []:
            if f.get("file"):
                idx[Path(f["file"]).stem] = int(f["t_ms"])
    return idx


def link_frames(video_id: str, *, window_ms: int = 20_000, min_overlap: int = 4,
                max_candidates: int = 3) -> dict:
    """为每条断言算「帧候选」。产物落 `frame_candidates.json`（与 assertions 分开存）。"""
    from .evidence import load_assertions

    frames_text = _frames_with_text(video_id)
    frame_t = _frame_time_index(video_id)
    if not frames_text or not frame_t:
        return {"applicable": False, "reason": "没有帧文字或帧索引"}

    out: dict[str, dict] = {}
    stats = {"number": 0, "term": 0, "overlap": 0, "none": 0}
    for a in load_assertions(video_id):
        an = (a.get("anchors") or [{}])[0]
        lo, hi = an.get("start_ms"), an.get("end_ms")
        if lo is None:
            continue
        text = a.get("text") or ""
        nums = set(_NUMERIC.findall(text))
        terms = set(_TERM.findall(text))
        cands = []
        for fid, ftxt in frames_text.items():
            t_ms = frame_t.get(fid)
            if t_ms is None or not (lo - window_ms <= t_ms <= hi + window_ms):
                continue
            matched_by, overlap = None, 0
            hit_nums = [n for n in nums if n in ftxt]
            hit_terms = [t for t in terms if t in ftxt]
            if hit_nums:
                matched_by, overlap = "number", max(len(n) for n in hit_nums)
            elif hit_terms:
                matched_by, overlap = "term", max(len(t) for t in hit_terms)
            else:
                ov = _longest_common_substring_len(text, ftxt)
                if ov >= min_overlap:
                    matched_by, overlap = "overlap", ov
            if matched_by:
                cands.append({"fid": fid, "t_ms": t_ms, "matched_by": matched_by, "overlap": overlap})
        cands.sort(key=lambda c: (-{"number": 2, "term": 1, "overlap": 0}[c["matched_by"]], -c["overlap"]))
        if cands:
            out[a["id"]] = {"candidates": cands[:max_candidates],
                            "already_cited": bool(a.get("frame_refs"))}
            stats[cands[0]["matched_by"]] += 1
        else:
            stats["none"] += 1

    doc = {
        "video_id": video_id,
        "version": FRAME_LINK_VERSION,
        "method": "机械算法算帧候选（数字/术语/最长公共子串），**非模型判断**",
        "params": {"window_ms": window_ms, "min_overlap": min_overlap},
        "total_assertions": len(out) + stats["none"],
        "with_candidates": len(out),
        "stats": stats,
        "links": out,
    }
    p = DATA_DIR / video_id / "frame_candidates.json"
    p.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    return doc


def candidate_table_for_prompt(video_id: str, assertion_ids: list[str]) -> str:
    """给投影用的帧候选表（只列有候选的断言）。"""
    p = DATA_DIR / video_id / "frame_candidates.json"
    if not p.exists():
        return ""
    doc = json.loads(p.read_text(encoding="utf-8"))
    rows = []
    for aid in assertion_ids:
        rec = doc["links"].get(aid)
        if not rec:
            continue
        best = rec["candidates"][0]
        rows.append(f"- {aid} → 帧 {best['fid']}（@{best['t_ms']/1000:.0f}s，"
                    f"依据 {best['matched_by']}，重叠 {best['overlap']} 字）")
    if not rows:
        return ""
    head = "## 帧候选（机器匹配，可复核；**引用时优先用这些**）"
    return "\n".join([head, *rows[:80]])
