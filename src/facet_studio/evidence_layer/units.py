"""层 0→1 · 单元化：把 ASR 段切成**可引用的子句单元**（确定性，不调模型）。

## 为什么要有这一层

现在的"证据单元"是**模型即兴选的片段**（`prompts_l1` 要求"宁短勿长，通常 10–40 字"）。
后果实测：同一底稿同参数两次跑，选中的断言集合只有 **Jaccard 0.429**（`docs/EXPERIMENT-*`）。
**边界由模型即兴决定 ⇒ 不可复算、不可穷尽、覆盖率没有同量级的分母。**

改成由代码按标点切子句之后：
1. **穷尽且不重叠** ⇒ 覆盖账本第一次有和分子同量级的分母（现在 BV1B5411A7ax 的分母是 9，
   而断言有 91 条——分母比分子小两个数量级，覆盖率恒 100%）；
2. **边界可复算** ⇒ 同一视频两次跑出同一套 unit；
3. **模型碰不到证据文本** ⇒ 极性与限定词的漂移从"伪装成证据"变成"显式 advisory"；
4. **"引文被切太窄"消失** ⇒ 下游引用 unit_id，不再自己选片段。

## 复算契约（I3）

`UNIT_SEPARATORS` / `UNIT_MAX_CHARS` **就是 I3 说的"同配置"**。改任一项 = 换 L1 版本 =
旧底稿全部失效。所以它们必须进配置 hash，且改动要能被识别出来。
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

UNIT_VERSION = "unit/v1"

# 分隔符集合（实测语料盘点：，2153 / 。836 、253 ？201 ：42 ！16 ；4 / ASCII . , ? 各数十）。
# `、` 是显式决策：**切**。理由——并列项（"陪伴、信息和深度"）本身就是可独立引用的内容单元；
# 不切则整段并列成为一个单元，长且指代不明。这个决定连同版本一起冻结。
UNIT_SEPARATORS = "，。、；：？！,.;:?!"

# 超长兜底：实测全部 3528 个单元里 >60 字的只有 1 个（0.03%，来自一段几乎没标点的
# 流式 ASR 输出）。兜底不是为常态准备的，是为"某段标点几乎为零"准备的。
UNIT_MAX_CHARS = 40

# 纯填充词单元（"啊""对，""嗯"）——不参与覆盖账本的分母，否则分母永远含一半口水词。
# 实测：切分后 18.6% 的单元 <4 字，访谈类 32%。
FILLER_CHARS = set("啊嗯哦呃呀吧呢嘛唉哎哈噢喔诶")


def config_hash() -> str:
    """配置指纹：分隔符集合 + 兜底阈值 + 版本号。进 provenance，用来判断底稿是哪一版。"""
    blob = json.dumps({"v": UNIT_VERSION, "sep": UNIT_SEPARATORS, "max": UNIT_MAX_CHARS},
                      ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


# ------------------------------------------------------------------ 切分

def split_clauses(text: str) -> list[tuple[int, int]]:
    """按分隔符切子句，返回 `[(start, end), ...]` 字符区间。

    **区间连续且完整覆盖**（分隔符并入前一个单元），所以 Σ(单元长度) == len(text)，
    覆盖账本因此可以做到精确，而不是"大概"。
    """
    spans: list[tuple[int, int]] = []
    start = 0
    for i, ch in enumerate(text):
        if ch in UNIT_SEPARATORS:
            spans.append((start, i + 1))
            start = i + 1
    if start < len(text):                      # 结尾没有分隔符的残段也算一个单元
        spans.append((start, len(text)))
    return [(a, b) for a, b in spans if b > a]


def _is_ignorable(ch: str) -> bool:
    """既不是可引用内容、也不带独立时间的字符：分隔符与空白。

    ⚠️ 空白必须一起处理：首版只去了分隔符，于是 `BV1eUhM6hEdn/s0007` 这类**句里多一个空格、
    词流里没有**的句子假报"对齐失败"（4 句，全部是同一个原因）。
    注意 `split_clauses` **不**按空白切——英文句子的空格是词间分隔，不是子句边界。
    """
    return ch in UNIT_SEPARATORS or ch.isspace()


def _strip_seps(s: str) -> str:
    return "".join(ch for ch in s if not _is_ignorable(ch))


def align_chars_to_words(text: str, words: list[dict]) -> tuple[list[tuple[int, int | None]], bool]:
    """把 `text` 的每个字符映射到时间 `(start_ms, end_ms)`。

    **前提（必须验证）**：`text` 去分隔符后应与 `words` 去分隔符后的拼接**逐字相等**。
    ⚠️ **两侧都要去分隔符**——首版只去了 `text` 一侧，于是 38 句（`BV1ybHXzfEEu` 里 19/78）
    假报"对齐失败"。真实原因是 **ASR 的 `words` 流里也含标点**：
    句侧是 `就说“于老师`，词侧是 `就说：“于老师`（多一个全角冒号当独立 token）。
    对齐不成立时返回 `ok=False`，调用方**不许猜**（标 `alignment_failed`，留给人复核）。
    """
    content_words = [(w, _strip_seps(w.get("text") or "")) for w in words]
    content_words = [(w, t) for w, t in content_words if t]
    word_txt = "".join(t for _, t in content_words)
    if _strip_seps(text) != word_txt:
        return [(None, None)] * len(text), False

    per_char: list[tuple[int, int | None]] = []
    wi, off = 0, 0
    cur: tuple[int | None, int | None] = (None, None)
    for ch in text:
        if _is_ignorable(ch):
            per_char.append(cur)               # 标点/空白挂到前一个词（它没有自己的时间）
            continue
        if wi >= len(content_words):           # 理论不可达（上面已验等长）
            return [(None, None)] * len(text), False
        if off == 0:
            w = content_words[wi][0]
            cur = (int(w["start_ms"]), int(w["end_ms"]))
        per_char.append(cur)
        off += 1
        if off >= len(content_words[wi][1]):
            wi, off = wi + 1, 0
    return per_char, True


def _split_long(text: str, spans: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """超长兜底：按字符数强制再切。**只在超过阈值时触发**，且切点会记录在单元上。"""
    out: list[tuple[int, int]] = []
    for a, b in spans:
        if len(_strip_seps(text[a:b])) <= UNIT_MAX_CHARS:
            out.append((a, b))
            continue
        cur = a
        while cur < b:
            nxt = min(cur + UNIT_MAX_CHARS, b)
            out.append((cur, nxt))
            cur = nxt
    return out


# ------------------------------------------------------------------ 构建

def build_units_for_sentence(sid: str, text: str, words: list[dict]) -> tuple[list[dict], dict]:
    """一句 → 一批单元。返回 `(units, stats)`。"""
    stats = {"alignment_failed": 0, "forced_splits": 0, "filler_only": 0, "chars": len(text)}
    if not text.strip():
        return [], stats

    per_char, ok = align_chars_to_words(text, words or [])
    stats["alignment_failed"] = 0 if ok else 1

    raw_spans = split_clauses(text)
    spans = _split_long(text, raw_spans)
    stats["forced_splits"] = len(spans) - len(raw_spans)

    units: list[dict] = []
    for i, (a, b) in enumerate(spans):
        raw = text[a:b]
        body = _strip_seps(raw)
        if not body:
            continue
        times = [t for t in per_char[a:b] if t[0] is not None]
        t_start = min(t[0] for t in times) if times else None
        t_end = max(t[1] for t in times) if times else None
        is_filler = all(ch in FILLER_CHARS or _is_ignorable(ch) for ch in raw)
        if is_filler:
            stats["filler_only"] += 1
        units.append({
            "unit_id": f"{sid}-u{i:02d}",
            "sid": sid,
            "char_span": [a, b],
            "byte_span": [len(text[:a].encode("utf-8")), len(text[:b].encode("utf-8"))],
            "t": [t_start, t_end],
            "channel": "speech",
            "raw": raw,
            "len": len(body),
            "filler_only": is_filler,
            "forced_split": len(_strip_seps(raw)) > UNIT_MAX_CHARS or (a, b) not in set(raw_spans),
            "alignment_failed": not ok,
            "produced_by": {"unit_version": UNIT_VERSION, "config_hash": config_hash()},
        })
    return units, stats


def build_units(corpus: dict) -> tuple[list[dict], dict]:
    """整条视频 → 全部单元 + 统计。**纯函数**：同 corpus + 同配置 ⇒ 逐字节相同（I3）。"""
    words_by_sent = corpus.get("words_by_sent") or {}
    units: list[dict] = []
    agg = {"sentences": 0, "alignment_failed_sentences": 0, "forced_splits": 0,
           "filler_only": 0, "total_chars": 0, "unit_chars": 0}
    for sid in corpus.get("order") or []:
        s = corpus["sentences"][sid]
        text = s.get("text") or ""
        if not text.strip():
            continue
        us, st = build_units_for_sentence(sid, text, words_by_sent.get(sid) or [])
        units.extend(us)
        agg["sentences"] += 1
        agg["alignment_failed_sentences"] += st["alignment_failed"]
        agg["forced_splits"] += st["forced_splits"]
        agg["filler_only"] += st["filler_only"]
        agg["total_chars"] += st["chars"]
        agg["unit_chars"] += sum(u["len"] for u in us)
    agg["unit_count"] = len(units)
    agg["content_unit_count"] = sum(1 for u in units if not u["filler_only"])
    agg["short_units"] = sum(1 for u in units if u["len"] < 4)
    agg["max_len"] = max((u["len"] for u in units), default=0)
    agg["coverage_exact"] = agg["unit_chars"] == len(
        "".join(_strip_seps(corpus["sentences"][s]["text"]) for s in corpus.get("order") or []))
    agg["unit_version"] = UNIT_VERSION
    agg["config_hash"] = config_hash()
    return units, agg


def make_unit_chunks(units: list[dict], chunk_minutes: float = 15.0,
                     context_units: int = 12) -> list[dict]:
    """按时间窗把**单元**分片，沿用既有的「所有权 + 只读上下文」纪律。

    与旧的句级分片同构，但单位是单元——这样 L1 抽取的输入单位与证据单位是同一个东西，
    **模型不再需要"从句子文本里挑一段当引文"这一步**。

    只把**有内容**的单元纳入 owned（纯填充单元不参与，但**不丢**——它们仍在 units.jsonl 里，
    由覆盖账本按豁免口径处理）。
    """
    content = [u for u in units if not u.get("filler_only") and u.get("t") and u["t"][0] is not None]
    if not content:
        return []
    window_ms = int(chunk_minutes * 60 * 1000)
    groups: list[list[dict]] = []
    cur: list[dict] = []
    win_start = content[0]["t"][0]
    for u in content:
        if cur and (u["t"][0] - win_start) >= window_ms:
            groups.append(cur)
            cur, win_start = [], u["t"][0]
        cur.append(u)
    if cur:
        groups.append(cur)

    pos = {u["unit_id"]: i for i, u in enumerate(content)}
    out = []
    for ci, g in enumerate(groups):
        lo = pos[g[0]["unit_id"]] - context_units
        hi = pos[g[-1]["unit_id"]] + context_units
        ctx = content[max(0, lo):hi + 1]
        out.append({
            "chunk_id": f"c{ci:03d}",
            "owned": [u["unit_id"] for u in g],
            "context": [u["unit_id"] for u in ctx if u["unit_id"] not in {x["unit_id"] for x in g}],
            "first_ms": g[0]["t"][0],
            "last_ms": g[-1]["t"][1],
        })
    return out


def write_units(video_id: str, units: list[dict], stats: dict, out_dir: Path,
                *, allow_overwrite: bool = False) -> Path:
    """写 `units.jsonl`。**过闸门**（2026-10-16，审计 A1 的同族第三个写者）。

    为什么这个文件也必须受保护：它是**版本承载件**。spec §2.1 写得很直白——
    「改分隔符集合 = 换 L1 版本 = **旧底稿全部失效**，必须能识别出来」。
    而此前这里是裸 `open("w")`：改了单元定义 ⇒ `units.jsonl` 被**静默换掉**，
    而 `assertions.jsonl` 里引的还是旧 `unit_id` ⇒ 下游会报
    「引用了不存在的单元（底稿与 units.jsonl 版本不一致？）」——**症状出现在别处，
    根因在这里，而且已经无法回溯**（这正是 D1 那场事故的同一个形状）。

    同配置重跑 ⇒ 字节相同 ⇒ 幂等跳过；换了配置 ⇒ **拒绝**并提示版本化。
    """
    from .artifacts import OverwriteRefused, guarded_write_jsonl

    out_dir.mkdir(parents=True, exist_ok=True)
    p = out_dir / "units.jsonl"
    try:
        guarded_write_jsonl(p, units, what="units.jsonl", allow_overwrite=allow_overwrite)
    except OverwriteRefused as e:
        raise SystemExit(
            f"[units] {e}\n"
            f"  ⚠️ 单元定义变了（config_hash={stats.get('config_hash')}）⇒ 按 spec §2.1，"
            f"**旧底稿全部失效**。这是「换 L1 版本」，不是重跑：\n"
            f"     先把现有 substrate 备份/并存，再决定是重跑断言还是回退单元定义。") from e
    (out_dir / "units_report.json").write_text(
        json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")
    return p
