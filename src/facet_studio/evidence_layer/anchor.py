"""层 1 · 锚点精化：句级 → 字级。

问题：断言的时间锚点继承自句子，而句子可能长达 30 秒（实测：短视频 30s/句、长视频 17–20s/句），
「回链到原片第几秒」就只能是句级精度。

做法（不用再调一次模型）：
- 模型已经给出 `quote`（锚点句中的原文片段，提示词要求逐字）；
- 层 0 已经存了**字级时间戳**（`transcript.json` 的 `words`，长视频 3872 个 token）；
- 程序在词表里找 quote 覆盖的最小连续窗口 ⇒ 得到精确到词的 [start_ms, end_ms]。

纪律：匹配不上**不静默降级**——标 `sentence_level` 并把 quote 留给人复核；
匹配上了也不丢句级锚点（同时保留，句级是回退，词级是精化）。
"""
from __future__ import annotations

import re

CJK = r"一-鿿㐀-䶿ༀ-࿿"
KEEP = re.compile(rf"[{CJK}a-zA-Z0-9]")


def norm(s: str) -> str:
    """归一化：只保留中文字符与字母数字，其余（标点/空格/语气词以外的符号）丢弃。"""
    return "".join(KEEP.findall(s or ""))


def build_char_map(quote: str) -> tuple[str, list[int]]:
    """返回 (归一化后的字符串, 每个字符 → 原串下标)。"""
    chars, idx = [], []
    for i, ch in enumerate(quote or ""):
        if KEEP.match(ch):
            chars.append(ch)
            idx.append(i)
    return "".join(chars), idx


def refine_anchor(sentence_text: str, words: list[dict], quote: str,
                  sent_start_ms: int, sent_end_ms: int) -> dict:
    """用 quote 在词表里定位最小连续窗口。

    返回 {"start_ms", "end_ms", "precision", "matched_tokens", "match_ratio", "detail"}
    precision ∈ {"word", "sentence"}
    """
    base = {"start_ms": sent_start_ms, "end_ms": sent_end_ms,
            "precision": "sentence", "matched_tokens": 0, "match_ratio": None, "detail": None}
    if not words or not quote:
        return base

    q_norm, _ = build_char_map(quote)
    if len(q_norm) < 2:
        return base

    toks = []
    for w in words:
        t = norm(w.get("text"))
        if t:
            toks.append((t, int(w["start_ms"]), int(w["end_ms"])))
    if not toks:
        return base

    # 逐词累加字符位置（token → 在拼接串里的 [c_start, c_end)）
    bounds: list[tuple[int, int]] = []
    cursor = 0
    for t, _, _ in toks:
        bounds.append((cursor, cursor + len(t)))
        cursor += len(t)
    joined = "".join(t for t, _, _ in toks)

    char_at = joined.find(q_norm)
    if char_at < 0:
        # quote 不是词表的连续子串（可能模型改了字）⇒ 报告，不猜
        return {**base, "detail": "quote 未在字级词表中连续命中"}
    char_end = char_at + len(q_norm)

    # 字符位置 → 词下标（覆盖该字符区间的词才入选）
    lo_i = next((i for i, (s, e) in enumerate(bounds) if s <= char_at < e), None)
    hi_i = next((i for i, (s, e) in enumerate(bounds) if s < char_end <= e), None)
    if lo_i is None or hi_i is None or hi_i < lo_i:
        return {**base, "detail": "定位失败"}

    covered = bounds[hi_i][1] - bounds[lo_i][0]
    return {
        "start_ms": toks[lo_i][1],
        "end_ms": toks[hi_i][2],
        "precision": "word",
        "matched_tokens": hi_i - lo_i + 1,
        "match_ratio": round(min(1.0, len(q_norm) / covered), 3) if covered else None,
        "detail": None,
    }


def enrich_assertion_anchors(a: dict, corpus: dict) -> dict:
    """把断言里的句级锚点换成字级（成功时），原地写回并记 precision。"""
    t_doc = corpus.get("words_by_sent") or {}
    out = []
    for an in a.get("anchors") or []:
        sid = an.get("sid")
        src = (corpus.get("sentences") or {}).get(sid)
        if not src:
            out.append(an)
            continue
        words = t_doc.get(sid) or []
        refined = refine_anchor(src.get("text", ""), words, a.get("quote") or "",
                                src["start_ms"], src["end_ms"])
        out.append({
            "sid": sid,
            "start_ms": refined["start_ms"],
            "end_ms": refined["end_ms"],
            "sentence_start_ms": src["start_ms"],   # 句子边界同时保留
            "sentence_end_ms": src["end_ms"],
            "precision": refined["precision"],
            "match_ratio": refined["match_ratio"],
            "anchor_detail": refined["detail"],
        })
    a["anchors"] = out
    return a
