"""层 1 · 校验器：能判定的用规则判（不请模型）。

检查项（全部机械可判）：
- **锚点合法性**：sid 存在、属于本分片 owned、时间与源句一致；fid 存在且落在断言时间窗内（E9 硬锚点）
- **引文**：quote 必须是锚点句的连续原文片段（逐字命中）
- **覆盖**：每个有内容的 sid 是否至少被一条断言引用；**未覆盖的显式列出**（允许不抽，不许悄悄丢）
- **冲突**：同一 sid 被不同分片产锚点 ⇒ 报冲突（所有权机制被突破）
- **重复**：断言的 (文本指纹 + 锚点指纹) 是否撞车
- **跨片关系**：本片内 vs 引用上一片尾部的，分别计数；远跨片为**已知盲区**，如实计数
"""
from __future__ import annotations

import json
import re
import sys
from difflib import SequenceMatcher
from pathlib import Path
from typing import Iterable

from .anchor import norm
from .corpus import sent_key


# 帧窗口口径（实测定死）：帧必须落在断言音频锚点窗口内，允许 ±20s 容差。
# 依据：实测 2 例越窗都发生在「画面比口播滞后」——幻灯片是那张，只是滚动早/晚了
# （+18.1s、+5.3s）。20s 覆盖真实滞后，同时仍挡住「拿五分钟外的帧当证据」。
# 偏差一律记进该引用的 frame_offset_ms，让复核者能一眼看出这条引用有多"远"。
FRAME_WINDOW_TOLERANCE_MS = 20_000


# ── 极性 / 限定词检查 ──────────────────────────────────────────────────────
# 为什么需要它：现有校验全部挂在 quote 上，而 quote 是好的。缺陷活在 text 里。
# 已确认实例（BV1eUhM6hEdn/c000-a001）：原话「这**不**全是运气」被写成「这全是运气」——
# 一个字的删除反转了断言，而该条 quote_hit=exact、precision=word，全绿。
# 所以这一类**必须单独查**：它不会被任何现有检查捕获。
NEGATION_TOKENS = ("不", "没", "否", "莫", "勿", "并非", "毫无", "无法", "无需", "未曾")

# 限定词（hedge）：模型倾向于把说话人的不确定语气抹平，把「可能/应该」写成断言。
# 方向一致（恒朝向更确定），所以不是随机噪声，是系统性偏置。
HEDGE_TOKENS = ("可能", "也许", "大概", "据说", "似乎", "应该", "差不多", "左右",
                "至少", "最多", "往往", "通常", "一般", "几乎", "估计", "未必")

# 这些词里含"非/别/未/无/不"但不是否定用法，做否定判定前先剔除。
# 实测：不剔除会使命中数从 39 涨到 49，10 条纯误报。
#
# ⚠️「差不多」**只能对本表生效，不能对 HEDGE 生效**——它本身就是一个限定词。
# 早先版本把两张表共用一份排除项，导致「差不多」被先删掉、HEDGE 永远匹配不到（死词）。
NEG_FALSE_FRIENDS = (
    "非常", "特别", "别的", "未来", "无论", "无数", "无法无天", "差不多",
    # 下列词含「不」但不是否定：混进判定会成片假阳性（实测把 11.2% 的产物句误报了一多半）
    "不同", "不少", "不错", "不仅", "不但", "不管", "不论", "不过", "不如", "不只", "不止",
    # 含「没」但是**肯定**：「没错」「没说错」= 说对了。金标里有两条误报就是它
    # （「没错，没错」被删 → 报"删否定"，其实删的是附和语）。
    "没说错", "没错",
    # 「莫名其妙」里的「莫」不是否定（金标：被删 → 报"删否定"，删的其实是转场语）
    "莫名其妙",
)
HEDGE_FALSE_FRIENDS: tuple[str, ...] = ()


def _hits(text: str, tokens: Iterable[str], false_friends: Iterable[str] = ()) -> list[str]:
    s = text
    for w in false_friends:
        s = s.replace(w, "")
    return [t for t in tokens if t in s]


def polarity_shift(a: dict) -> list[dict]:
    """比对 quote → text，返回极性/限定词相关的改动。

    纪律：**这是 suspect 通道，不是门禁**。它的用途是**排序人工复核**，不是判错。

    ## 判定单元：**词元净计数**，不是对齐片段（2026-10-17 重写）

    旧版把 difflib 的对齐片段当判定单元（"这一段 old 有否定、new 没有 ⇒ 删了否定"）。
    金标 36 条逐条读过之后，**最大的误报类（9/31）就是这个判定单元本身**——
    对齐是"找最长公共子串"，它会把同一个词挪到别处，于是报出根本没发生的删除：

    - 「知道**不可能**啊，这个**不可能**符合市场」→「这**不可能**，它**不**符合市场」
      被报成"删了限定词「可能」"。真相：**「不可能」里的「可能」不是限定词，是否定式**，
      计数时得先把 `否定字+可能` 扣掉。
    - 「全量也subject condensed」→「全量**塞不进** context」被报成"加了否定"。
      真相：quote 里本来就有这个否定（被 ASR 打乱），**净计数没涨**。

    ⇒ 改成：**只有该词元在整条断言里的净计数真的朝那个方向变了，才报**。
    比对依然跑，但**只用来定位**——给复核者指出"改在哪儿"，不再参与判定。

    ## 顺带修掉的三类（都是净计数管不到的）

    - **反问句**：整条跳过。「会不会产生网红」→「会不会产生网红」被报成加否定；
      「离得开医院呢？」→「离不开医院」被报成加否定。疑问改写成陈述，语义没变。
    - **问号消失**：quote 有 `？` 而 text 没有 ⇒ 把疑问改成了断言，同上跳过。
    - **压缩**：整个分句被删（> `_POL_MAX_SPAN` 字）是合并重叠信息，不是删否定。

    实现要点（两个曾经错过的洞，改后由自检用例守着）：
    1. **delete / replace / insert 三种 opcode 统一按"old 有、new 无 ⇒ 删"判定**。
       早先只在 `delete` 分支查删除，于是 `不能去→必须去`、`不行→可行` 这类
       被 difflib 对齐成 `replace` 的**全部漏检**——而改写越狠越容易走 replace，
       等于"越需要抓的越抓不到"。**这条现在由净计数接管**（与对齐方式无关，更强）。
    2. 两张词表的排除项分开（见 NEG_FALSE_FRIENDS 上方注释）。
    """
    q = (a.get("quote") or "").strip()
    t = (a.get("text") or "").strip()
    if not q or not t or q == t:
        return []
    if _POL_RHETORICAL.search(q):
        return []                       # 整条是反问句：否定是修辞，不是逻辑
    if re.search(r"[？?]", q) and not _POL_INTERROGATIVE.search(t):
        # 原文在问、产物这边一点疑问痕迹都没有 ⇒ 把疑问改写成了陈述，
        # 「离得开医院呢？」→「离不开医院」正是这一类，否定是修辞不是逻辑。
        # **判据放在 text 上，不放在 quote 的标点上**：间接引语（「你家有葱吗？」
        # →「我问他家**有没有**葱」）照样是问句，只是不带问号，不能一起吞掉。
        return []
    out: list[dict] = []
    sm = SequenceMatcher(None, q, t, autojunk=False)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            continue
        old, new = q[i1:i2], t[j1:j2]
        if not old and not new:
            continue
        neg_old = _hits(old, NEGATION_TOKENS, NEG_FALSE_FRIENDS)
        neg_new = _hits(new, NEGATION_TOKENS, NEG_FALSE_FRIENDS)
        hed_old = _hits(old, HEDGE_TOKENS, HEDGE_FALSE_FRIENDS)
        hed_new = _hits(new, HEDGE_TOKENS, HEDGE_FALSE_FRIENDS)

        # 每个分支：先过 `_keep_span`（形状闸门），再过计数闸门。
        #
        # **删除按「集合」判，加法按「计数」判**——两个方向各自对着自己的误报模式：
        # - 删除：**只有该词元在 text 里彻底消失才算改了命题**。少掉重复的那一次
        #   只是合并冗余（「没这个**没**有什么讲究」→「没有什么讲究」），极性没动。
        #   金标里 5 条误报全是这一类。
        # - 加法：**不能**用集合判。原文别处有一个「不」、模型又给另一个分句补了一个，
        #   那是实打实的加否定（`{不}` ⊆ `{不}`，集合判会把它吞掉）。
        if neg_old and not neg_new:
            for tok in neg_old:
                if _count(t, tok) == 0 and _count(q, tok) > 0 \
                        and _keep_span(old, tuple(neg_old)):
                    out.append({"kind": "deleted_negation", "token": tok,
                                "old": old, "new": new})
                    break
        elif hed_old and not hed_new:
            for tok in hed_old:
                if _count(t, tok, hedge=True) == 0 and _count(q, tok, hedge=True) > 0 \
                        and _keep_span(old, tuple(hed_old)):
                    out.append({"kind": "deleted_hedge", "token": tok,
                                "old": old, "new": new})
                    break
        if neg_new and not neg_old:
            for tok in neg_new:
                # 加法方向不看 `_POL_MAX_SPAN`：补的是"否定+它修饰的整段"，
                # 天然就长（金标里那条真信号 new = 「这类不可逆的人类行为需求，」13 字）。
                if _count(t, tok) > _count(q, tok) \
                        and _keep_span(new, tuple(neg_new), cap=False):
                    out.append({"kind": "added_negation", "token": tok,
                                "old": old, "new": new})
                    break
    return out


# ---- 收窄的两道闸门（2026-10-17）--------------------------------------------
#
# 依据：`data/regression/polarity_gold.json` —— 36 条候选**逐条读全文**人工判读。
# 收窄前：真 2 / 灰 3 / **误报 31** ⇒ 精度（松）**13.9%**、（严）5.6%。
#
# 第一道（`_count`，见 `polarity_shift` 的分支里）治的是最大的一类：
# **对齐 artifact**——判定单元本身错了。改判定单元即根除，不需要规则堆。
# 第二道（`_keep_span`）治剩下三类形状问题：
#
#   整句/分句被压缩   ⇒ `_POL_MAX_SPAN`
#   单字/超短片段     ⇒ `_POL_MIN_SPAN`
#   口吃/重复         ⇒ `_POL_STUTTER`
#
# **不治的（已知、如实留着）**：说话人自我更正（「不是你这个…」）、
# ASR 打乱导致的"补否定"（「subject condensed」→「塞不进 context」）。
# 机械层面分不出来，交给 L3/人工。
POLARITY_CHECK_VERSION = "polarity/v2"     # v1→v2：判定单元由「对齐片段」改为「词元净计数」

_POL_MIN_SPAN = 2
_POL_MAX_SPAN = 6       # 超过这个长度还整体被删 ⇒ 是压缩，不是删否定/限定词
_POL_RHETORICAL = re.compile(r"能不能|是不是|会不会|行不行|对不对|好不好")
_POL_STUTTER = re.compile(r"(不\s*不|没\s*没|是\s*是|行\s*行|对\s*对)")
# 「text 这边还在问」的样子：间接疑问（「我问他家有没有葱」）或任何疑问痕迹
_POL_INTERROGATIVE = re.compile(r"有没有|是不是|是否|问|什么|怎么|为啥|多少|吗|呢")

# 否定字（用于「否定字+限定词」的扣减，见 `_count`）
_POL_NEG_CHARS = "不没非无别莫勿未"


def _keep_span(s: str, tokens: tuple[str, ...], *, cap: bool = True) -> bool:
    """形状闸门：这段改动**看起来像不像**一次真的极性改动。"""
    s = s.strip()
    if len(s) < _POL_MIN_SPAN and s not in tokens:
        # 太短 ⇒ 切分/对齐噪声。**但「短」如果是因为这个词元本身就短，就不算噪声**——
        # 单字否定被删是**最危险**的一类（本模块开头那条实例就是
        # 「这**不**全是运气」→「这全是运气」，一个字反转断言）。
        # 早先这条闸门不认识词元、一律按长度砍，正好把那条实例砍掉了（自检当场抓住）。
        return False
    if cap and len(s) > _POL_MAX_SPAN:
        return False                # 整个分句被删 ⇒ 压缩（合并重叠信息）
    if _POL_STUTTER.search(s):
        return False                # 口吃重复，合并重复是允许的
    return True


def _count(s: str, token: str, *, hedge: bool = False) -> int:
    """数 token 的净出现次数。两道扣减，都各有实据：

    1. **假朋友**（`NEG_FALSE_FRIENDS`）：否则「不同」「没错」里的否定字都算成一次否定。
       `w == token` 必须跳过——「差不多」**同时**在 NEG_FALSE_FRIENDS 和 HEDGE_TOKENS 里，
       连自己一起剔掉会让计数恒为 0 ⇒ 所有「差不多」的删除被静默吞掉。
       （这就是 NEG_FALSE_FRIENDS 上方那条注释警告过的同一类错，换个地方又踩一次。）
    2. **`否定字 + 限定词`**（仅 `hedge=True`）：「**不可能**」里的「可能」是不是定式的一部分，
       不是限定词。不扣掉就会报出"删了限定词 可能"——金标里这条误报的原样重演。
    """
    for w in NEG_FALSE_FRIENDS:
        if w == token:
            continue
        s = s.replace(w, "")
    n = s.count(token)
    if hedge:
        for c in _POL_NEG_CHARS:
            n -= s.count(c + token)
    return max(0, n)


def check_assertion(a: dict, corpus: dict, owned: set[str], frames: dict,
                    frame_tolerance_ms: int = FRAME_WINDOW_TOLERANCE_MS) -> list[str]:
    """返回该断言的错误列表（空 = 通过）。

    锚点时间有两种合法形态：
    - `precision=word`：由 quote 在字级词表里定位得到，**必须落在句子区间内**；
    - `precision=sentence`：与源句时间完全一致。
    """
    errs: list[str] = []
    anchors = a.get("anchors") or []
    if not anchors:
        errs.append("没有锚点")
    for an in anchors:
        sid = an.get("sid")
        if sid not in corpus["sentences"]:
            errs.append(f"锚点 sid 不存在: {sid}")
            continue
        if sid not in owned:
            errs.append(f"锚点 sid 不属于本片 owned（越权引用上下文）: {sid}")
        src = corpus["sentences"][sid]
        prec = an.get("precision", "sentence")
        if prec == "unit":
            # 单元制（v5）：时间直接来自单元，只需落在所属句的区间内
            if not (src["start_ms"] <= an["start_ms"] <= an["end_ms"] <= src["end_ms"]):
                errs.append(f"单元锚点超出句子区间: {sid} [{an['start_ms']},{an['end_ms']}] "
                            f"not in [{src['start_ms']},{src['end_ms']}]")
        elif prec == "word":
            if not (src["start_ms"] <= an["start_ms"] <= an["end_ms"] <= src["end_ms"]):
                errs.append(f"字级锚点超出句子区间: {sid} [{an['start_ms']},{an['end_ms']}] "
                            f"not in [{src['start_ms']},{src['end_ms']}]")
        else:
            if an.get("start_ms") != src["start_ms"] or an.get("end_ms") != src["end_ms"]:
                errs.append(f"句级锚点时间与源句不一致: {sid}")

    # 帧引用：口径见 FRAME_WINDOW_TOLERANCE_MS 的注释
    if anchors and a.get("frame_refs"):
        sids = [x["sid"] for x in anchors if x.get("sid") in corpus["sentences"]]
        if sids:
            lo = min(corpus["sentences"][s]["start_ms"] for s in sids)
            hi = max(corpus["sentences"][s]["end_ms"] for s in sids)
            for fid in a["frame_refs"]:
                # 防御：fid 必须是字符串。非字符串（模型偶发返回对象）若直接进 frames.get
                # 会炸成 `unhashable type: 'dict'`，把整条视频的校验连同已抽好的断言一起带走
                # （BV1ybHXzfEEu 实测就是这样丢了 216 条断言）。
                if not isinstance(fid, str):
                    errs.append(f"帧 id 类型非法（应为字符串，收到 {type(fid).__name__}）")
                    continue
                f = frames.get(fid)
                if not f:
                    errs.append(f"帧 id 不存在: {fid}")
                    continue
                offset = 0 if lo <= f["t_ms"] <= hi else (f["t_ms"] - hi if f["t_ms"] > hi else f["t_ms"] - lo)
                a.setdefault("frame_offsets_ms", {})[fid] = offset
                if not (lo - frame_tolerance_ms <= f["t_ms"] <= hi + frame_tolerance_ms):
                    errs.append(f"帧越出容忍窗口(±{frame_tolerance_ms}ms): {fid} t={f['t_ms']} "
                                f"window=[{lo},{hi}] offset={offset}")

    # 引文命中：两级口径
    #   exact      = 原始字符逐字命中（含标点、引号字形）
    #   normalized = 去掉标点/空白后命中（实测：模型会把弯引号统一成直角引号，文字本身正确）
    # 都命中不了才算失败；命中级别写回断言，报告里分开统计。
    q = (a.get("quote") or "").strip()
    if q and a.get("quote_source") == "derived:units":
        # 单元制（v5）：引文是**代码从所引单元拼接出来的**，所以校验从
        # 「引文 ∈ 句子」变成「引文 == Σ 所引单元的原文」——这是指针校验，不是字符串比对。
        # 模型没有 quote 字段可写，因此这一类**在构造上不可能失败**；这里查的是
        # 拼接本身有没有出错（units.jsonl 与断言是不是同一版产出的）。
        units = (corpus.get("units_by_id") or {})
        uids = a.get("unit_ids") or []
        if not uids:
            errs.append("单元制断言缺 unit_ids")
        else:
            miss = [u for u in uids if u not in units]
            if miss:
                errs.append(f"引用了不存在的单元（底稿与 units.jsonl 版本不一致？）：{miss[:3]}")
                a["quote_hit"] = "miss"
            else:
                expect = "".join((units[u].get("raw") or "") for u in uids)
                if expect == a.get("quote"):
                    a["quote_hit"] = "exact"
                else:
                    a["quote_hit"] = "miss"
                    errs.append("引文与所引单元的原文拼接不一致（派生字段被改动过？）")
    elif q:
        sids = [x["sid"] for x in anchors if x.get("sid") in corpus["sentences"]]
        texts = [corpus["sentences"][s]["text"] for s in sids]
        if any(q in t for t in texts):
            a["quote_hit"] = "exact"
        elif any(norm(q) in norm(t) for t in texts):
            a["quote_hit"] = "normalized"
        else:
            a["quote_hit"] = "miss"
            errs.append("引文未在锚点句中命中（逐字与归一化都不中；需人工复核，非丢弃）")
    return errs


def assertion_fingerprint(a: dict) -> str:
    anchors = sorted(x.get("sid", "") for x in (a.get("anchors") or []))
    return f"{sent_key(a.get('text') or '')}|{'-'.join(anchors)}"


def _coverage_reading(buckets: dict) -> str:
    """由 `uncited_len_buckets` **生成**的解读，不是一句写死的文案。

    2026-10-16 修（审计 **B7**）。此前的 `reading` 是一句固定的话
    「未覆盖单元以短语气碎片为主属正常（访谈/播客大量寒暄）」，
    而实测它与自己旁边那组数字**在 2/5 条视频上相反**：
    `BV1qoHe6mEx6` 的分档是 `{≤4字:56, 5-10字:78, >10字:29}`、`BV1znXSBqEUP` 是 `{28,40,13}`
    ——多数根本不是短语气碎片。
    把结论**预先钉在数字旁边**，读的人就不会再去质疑它了。这正是本项目反对的
    "推出来的判断"：它看起来像结论，其实是没看数据时写的。
    """
    short = buckets.get("<=4字", 0)
    mid = buckets.get("5-10字", 0)
    longn = buckets.get(">10字", 0)
    total = short + mid + longn
    if not total:
        return "无未覆盖单元。"
    head = f"未覆盖 {total} 个内容单元：≤4 字 {short} / 5-10 字 {mid} / >10 字 {longn}。"
    if short / total >= 0.6:
        tail = "以短语气碎片为主 ⇒ 属正常（访谈/播客大量寒暄）。"
    elif longn / total >= 0.25:
        tail = ("**长未引项占比偏高** ⇒ 不能只当寒暄处理，"
                "逐个看 `uncited_long` 判断是真漏了内容还是元话语/提问。")
    else:
        tail = "短碎片与中长项混杂 ⇒ 看 `uncited_long` 逐个判断。"
    return head + tail


def _unit_coverage(assertions: list[dict], corpus: dict) -> dict:
    """**证据粒度**的覆盖：内容单元里有多少被至少一条断言引用过。

    为什么要单独算：句子级 `coverage` 会把「一句 12 个单元只引了 2 个」记成满分。
    实测 `BV1ybHXzfEEu` 句子级 0.974、单元级 **0.6727**（差 30 个点；spec §2.2(d) 的表里同值）。
    句子级数字**不是错的**（它测的是"这段讲了没讲被记下来"），但它不该被当成证据完整度。

    分母只算**内容单元**（`filler_only=False`）——语气词碎片不是"该被覆盖的东西"。
    未覆盖单元按长度分档，好判断到底是遗漏还是本来就是闲聊。
    """
    ubi = corpus.get("units_by_id") or {}
    if not ubi:
        return {"status": "skipped", "reason": "无 units_by_id（旧版产物）"}
    cited: set[str] = set()
    for a in assertions:
        cited.update(a.get("unit_ids") or [])
    content = [u for u in ubi.values() if not u.get("filler_only")]
    uncited = [u for u in content if u["unit_id"] not in cited]
    n = len(content)
    uncited_sorted = sorted(uncited, key=lambda u: -len(u.get("raw") or ""))
    buckets = {
        "<=4字": sum(1 for u in uncited if len(u.get("raw") or "") <= 4),
        "5-10字": sum(1 for u in uncited if 5 <= len(u.get("raw") or "") <= 10),
        ">10字": sum(1 for u in uncited if len(u.get("raw") or "") > 10),
    }
    return {
        "content_unit_count": n,
        "cited_unit_count": n - len(uncited),
        "unit_coverage_ratio": round((n - len(uncited)) / n, 4) if n else None,
        "uncited_long": [{"unit_id": u["unit_id"], "raw": u.get("raw"), "sid": u.get("sid")}
                         for u in uncited_sorted[:25]],
        "uncited_len_buckets": buckets,
        "reading": _coverage_reading(buckets),
    }


def validate(assertions: list[dict], relations: list[dict], corpus: dict,
             chunk_ownership: dict[str, list[str]]) -> dict:
    """chunk_ownership: sid -> [chunk_id...]，用于发现所有权冲突。"""
    frames = corpus.get("frames") or {}
    # 逐条跑 check_assertion（此前是死代码，errors 恒空）
    owned = {sid for sid, s in corpus["sentences"].items() if s["has_content"]}
    errors: list[dict] = []
    for a in assertions:
        errs = check_assertion(a, corpus, owned, frames)
        if errs:
            errors.append({"assertion": a.get("id"), "chunk_id": a.get("chunk_id"), "errors": errs})

    # 帧引用偏差分布（口径：±FRAME_WINDOW_TOLERANCE_MS，偏差必须露出）
    offsets = [abs(v) for a in assertions for v in (a.get("frame_offsets_ms") or {}).values()]
    frame_offset_stats = {
        "count": len(offsets),
        "in_window": sum(1 for v in offsets if v == 0),
        "within_tolerance": sum(1 for v in offsets if 0 < v <= FRAME_WINDOW_TOLERANCE_MS),
        "out_of_window": sum(1 for v in offsets if v > FRAME_WINDOW_TOLERANCE_MS),
        "max_abs_offset_ms": max(offsets) if offsets else None,
        "tolerance_ms": FRAME_WINDOW_TOLERANCE_MS,
    }

    seen_fp: dict[str, str] = {}
    duplicates: list[dict] = []
    sid_hits: dict[str, list[str]] = {}

    for a in assertions:
        for sid in (x.get("sid") for x in (a.get("anchors") or [])):
            if sid:
                sid_hits.setdefault(sid, []).append(a["id"])
        fp = assertion_fingerprint(a)
        if fp in seen_fp:
            duplicates.append({"a": seen_fp[fp], "b": a["id"], "fingerprint": fp})
        else:
            seen_fp[fp] = a["id"]

    # 所有权冲突：同一**所有权单位**被多个分片的断言锚定。
    # ⚠️ 口径随单元制而变（2026-10-15）：旧口径按 `sid`（句子）判所有权，那是句级分片时代的假设。
    # 现在所有权的最小单位是 **unit**——一个 30 秒的 ASR 段有十几个单元，
    # 契约完全可以把 u00–u07 放 seg1、u09–u14 放 seg2，**这是正确的分片，不是冲突**。
    # 实测：不改口径会在 BV1B5411A7ax 上误报 5 条"冲突"（全部是这种）。
    own_chunks: dict[str, set[str]] = {}
    for a in assertions:
        for an in (a.get("anchors") or []):
            key = an.get("unit_id") or an.get("sid")
            if key:
                own_chunks.setdefault(key, set()).add(a.get("chunk_id"))
    ownership_conflicts = [{"key": k, "chunks": sorted(v)}
                           for k, v in own_chunks.items() if len(v) > 1]

    content_sids = [sid for sid in corpus["order"] if corpus["sentences"][sid]["has_content"]]
    covered = [sid for sid in content_sids if sid in sid_hits]
    uncovered = [sid for sid in content_sids if sid not in sid_hits]

    rel_types: dict[str, int] = {}
    cross_prev = 0
    within = 0
    invalid_relations: list[dict] = []
    # 因果时序一致性：如果 rel_type 声明的是"因 → 果"，那两端的锚点时间应当 因 ≤ 果。
    # 实测（5 条视频 / 50 条 causes）：13 条倒置。逐条看下来**不是错误**，而是模型把
    # 「理由 → 结论」（论述关系，时序无约束）也标成了 causes——讲者先说结论后给理由，
    # 于是时序看起来是反的。所以这个检查的用途不是判错，是**量出 causes 这个标签有多混**，
    # 并让任何"因果必须先于结果"的下游用法有据可依。
    causal_order: list[dict] = []
    _rel_by_id = {a.get("id"): a for a in assertions}

    def _anchor_start(aid: str):
        a = _rel_by_id.get(aid) or {}
        an = (a.get("anchors") or [{}])[0] if a.get("anchors") else {}
        return an.get("start_ms")

    for r in relations:
        if r.get("invalid") or not r.get("rel_type"):
            if not r.get("invalid"):
                r["invalid"] = True
                r["reason"] = r.get("reason") or "缺少 rel_type 字段"
            invalid_relations.append({"id": r.get("id"), "reason": r.get("reason"),
                                      "chunk_id": r.get("chunk_id")})
            rel_types["(invalid)"] = rel_types.get("(invalid)", 0) + 1
            continue
        rel_types[r["rel_type"]] = rel_types.get(r["rel_type"], 0) + 1
        if r.get("link_kind") == "cross_prev_chunk":
            cross_prev += 1
        else:
            within += 1
        if r.get("rel_type") == "causes":
            ts_from, ts_to = _anchor_start(r.get("from_id")), _anchor_start(r.get("to_id"))
            if ts_from is not None and ts_to is not None and ts_from > ts_to:
                causal_order.append({
                    "relation": r.get("id"), "from_id": r.get("from_id"), "to_id": r.get("to_id"),
                    "from_ms": ts_from, "to_ms": ts_to, "delta_ms": ts_from - ts_to,
                    "from_text": ((_rel_by_id.get(r.get("from_id")) or {}).get("text") or "")[:70],
                    "to_text": ((_rel_by_id.get(r.get("to_id")) or {}).get("text") or "")[:70],
                })

    # 原子性：断言是否只有一件事 + 能否被锚点句子支撑
    #  - 符号数 > 60：疑似一条塞了多件事（中文里 60 字通常已经跨了多个事实）
    #  - 断言符号数 > 锚点源句符号数：锚点撑不住这条断言（回链可能被破坏）
    atomic_suspects: list[dict] = []
    ratio_samples: list[float] = []
    for a in assertions:
        text_len = len("".join((a.get("text") or "").split()))
        sids = [x.get("sid") for x in (a.get("anchors") or []) if x.get("sid") in corpus["sentences"]]
        if not sids or not text_len:
            continue
        src_len = max(len("".join(corpus["sentences"][s]["text"].split())) for s in sids)
        ratio = text_len / src_len if src_len else None
        if ratio:
            ratio_samples.append(ratio)
        flags = []
        if text_len > 60:
            flags.append("符号数>60（疑似非原子）")
        if ratio and ratio > 1.0:
            flags.append(f"断言比锚点句还长（ratio={ratio:.2f}）")
        if flags:
            atomic_suspects.append({"assertion": a["id"], "text_len": text_len,
                                    "anchor_src_len": src_len, "ratio": round(ratio, 3) if ratio else None,
                                    "flags": flags, "text": (a.get("text") or "")[:60]})

    # 极性 / 限定词变动（口径与理由见 NEGATION_TOKENS 上方注释）
    # 写回断言本身（同 quote_hit / frame_offsets_ms 的做法），供 review_kit 与下游读取。
    polarity_suspects: list[dict] = []
    for a in assertions:
        shifts = polarity_shift(a)
        if not shifts:
            continue
        a["polarity_shifts"] = shifts
        polarity_suspects.append({
            "assertion": a["id"], "chunk_id": a.get("chunk_id"),
            "kinds": sorted({s["kind"] for s in shifts}),
            "quote": (a.get("quote") or "")[:120],
            "text": (a.get("text") or "")[:120],
            "shifts": shifts,
            "quote_hit": a.get("quote_hit"),
        })

    # 引文命中级别（exact / normalized / miss，由 check_assertion 写回）
    quote_hits: dict[str, int] = {"exact": 0, "normalized": 0, "miss": 0}
    for a in assertions:
        lvl = a.get("quote_hit")
        if lvl in quote_hits:
            quote_hits[lvl] += 1

    # 锚点精度统计（字级 = 用 quote 在词表里定位成功；句级 = 回退）
    prec: dict[str, int] = {"unit": 0, "word": 0, "sentence": 0}
    fallback: list[dict] = []
    frame_ref_total = 0
    for a in assertions:
        has_quote = bool((a.get("quote") or "").strip())
        if not has_quote:
            prec["no_quote"] = prec.get("no_quote", 0) + 1
        for an in a.get("anchors") or []:
            p = an.get("precision", "sentence")
            prec[p] = prec.get(p, 0) + 1
            if p != "word":
                fallback.append({"assertion": a["id"], "sid": an.get("sid"),
                                 "reason": ("未提供 quote" if not has_quote
                                            else an.get("anchor_detail") or "未命中")})
        frame_ref_total += len(a.get("frame_refs") or [])

    return {
        "assertion_count": len(assertions),
        "relation_count": len(relations),
        "errors": errors,
        "error_count": len(errors),
        "frame_offset_stats": frame_offset_stats,
        "duplicate_assertions": duplicates,
        "ownership_conflicts": ownership_conflicts,
        "anchors": {
            "unit_level": prec.get("unit", 0),
            "word_level": prec.get("word", 0),
            "sentence_level_fallback": prec.get("sentence", 0),
            "unit_or_word_ratio": round((prec.get("unit", 0) + prec.get("word", 0))
                                        / max(1, sum(prec.values())), 4),
            "word_level_ratio": round((prec.get("word", 0) + prec.get("unit", 0))
                                      / max(1, sum(prec.values())), 4),
            "assertions_without_quote": prec.get("no_quote", 0),
            "quote_hit_levels": quote_hits,
            "fallback_examples": fallback[:10],
            "frame_refs_total": frame_ref_total,
        },
        "atomicity": {
            "suspect_count": len(atomic_suspects),
            "suspect_ratio": round(len(atomic_suspects) / max(1, len(assertions)), 4),
            "text_len_median": sorted(int(len("".join((a.get("text") or "").split())))
                                      for a in assertions)[len(assertions) // 2] if assertions else None,
            "ratio_to_source_median": round(sorted(ratio_samples)[len(ratio_samples) // 2], 3) if ratio_samples else None,
            "examples": atomic_suspects[:8],
        },
        "polarity": {
            # 换版必须显式（同 SCHEMA_VERSION / PROMPT_VERSION_UNITS 的做法）。
            # 为什么这一版特别需要它：v1 把 36 条候选**写回了 `assertions.jsonl`**
            # 的 `polarity_shifts` 字段，而 `revalidate` 明说不改那个文件 ⇒
            # 存量里躺着 36 条 **v1 规则的** shift，且没有任何东西会覆盖它们。
            # 打了版本号，读到旧字段的人至少能看出它不是当前规则算的。
            "check_version": POLARITY_CHECK_VERSION,
            "suspect_count": len(polarity_suspects),
            "suspect_ratio": round(len(polarity_suspects) / max(1, len(assertions)), 4),
            "by_kind": {
                k: sum(1 for p in polarity_suspects if k in p["kinds"])
                for k in ("deleted_negation", "deleted_hedge", "added_negation")
            },
            # 全量写入报告，不截断：这一类的量级在 1e1，人工过一遍成本极低，
            # 而漏掉一条反转（如「这不全是运气」→「这全是运气」）的代价极高。
            "suspects": polarity_suspects,
            "discipline": ("suspect 通道，非门禁。反问句、说话人自我更正都会命中且语义通常不变；"
                           "用途是排序人工复核。已确认的真反转实例：BV1eUhM6hEdn/c000-a001。"),
        },
        "coverage": {
            "content_sentence_count": len(content_sids),
            "covered_count": len(covered),
            "coverage_ratio": round(len(covered) / len(content_sids), 4) if content_sids else None,
            "uncovered_sids": uncovered,
            "granularity_note": "⚠️ 这是**句子级**覆盖，不是证据粒度。一句话只要有 1 条断言锚上就算覆盖，"
                                "但它可能有 12 个单元、只被引了 2 个。真粒度见 unit_coverage。",
        },
        "unit_coverage": _unit_coverage(assertions, corpus),
        "relations": {
            "by_type": rel_types,
            "invalid_count": len(invalid_relations),
            "invalid_examples": invalid_relations[:8],
            "within_chunk": within,
            "cross_prev_chunk_tail": cross_prev,
            "cross_chunk_status": "未启用（prev_tail_ids 未接线）——当前所有关系都在片内",
            "causal_order": {
                "causes_count": rel_types.get("causes", 0),
                "temporally_inverted": len(causal_order),
                "inverted_ratio": round(len(causal_order) / max(1, rel_types.get("causes", 0)), 4),
                "examples": causal_order[:6],
                "reading": ("倒置多为「理由 → 结论」（论述关系）被标成 causes，不是错误。"
                            "用途：让任何依赖'因果先于结果'的下游用法知道这个标签有多混。"),
            },
            "known_blind_spot": "跨片关系：当前未抽取（跨片候选句已单独计数，见 cross_chunk_candidates）",
        },
    }


def write_report(video_id: str, report: dict, out_dir: Path, suffix: str = "") -> Path:
    """`suffix` 用来在不覆盖既有产出的前提下并存多版（如 v5 单元制先写成 `_v5`）。"""
    p = out_dir / f"layer1_report{suffix}.json"
    p.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return p


# ── 自检（`python -m lmind.validate_l1`）────────────────────────────────────
# 守的是两个已经犯过的错，别让它们回来：
#   ① 词表共用排除项 ⇒「差不多」成死词；
#   ② 只在 delete 分支查删除 ⇒ 对齐成 replace 的删否定全部漏检。
# 这两条都不会报错，只会让命中数悄悄变少——所以必须有用例钉住。
_SELF_TEST_HIT = [
    ({"quote": "这不全是运气，它其实是有方法的", "text": "这全是运气，它其实是有方法的"}, "deleted_negation"),
    ({"quote": "我们不能去", "text": "我们必须去"}, "deleted_negation"),      # replace 方向
    ({"quote": "他没有说", "text": "他确实说"}, "deleted_negation"),          # replace 方向
    ({"quote": "无法访问", "text": "可以访问"}, "deleted_negation"),          # replace 方向
    ({"quote": "可能这个就是一个事实", "text": "这是一个事实"}, "deleted_hedge"),
    ({"quote": "这差不多就是答案", "text": "这就是答案"}, "deleted_hedge"),    # 死词回归
    ({"quote": "你家有葱吗？", "text": "我问他家有没有葱"}, "added_negation"),
]
_SELF_TEST_CLEAN = [
    {"quote": "这里非常关键", "text": "这里关键"},
    {"quote": "未来很重要", "text": "很重要"},
    {"quote": "特别重要", "text": "重要"},
    {"quote": "完全相同的一句话", "text": "完全相同的一句话"},
    {"quote": "差不多就是这样", "text": "差不多就是如此"},   # 限定词被保留 ⇒ 不该报
]


def _self_test() -> int:
    # Windows 控制台默认 GBK：不打这一行，**失败信息本身就打不出来**（`∅` 崩在 print 里），
    # 于是"有用例挂了"看起来像"脚本崩了"，第一现场被覆盖掉。
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    bad = 0
    for a, want in _SELF_TEST_HIT:
        kinds = {s["kind"] for s in polarity_shift(a)}
        if want not in kinds:
            print(f"FAIL 应命中 {want}: {a['quote']!r} -> {a['text']!r}，实得 {kinds or '∅'}")
            bad += 1
    for a in _SELF_TEST_CLEAN:
        if polarity_shift(a):
            print(f"FAIL 不应命中: {a['quote']!r} -> {a['text']!r}")
            bad += 1
    n = len(_SELF_TEST_HIT) + len(_SELF_TEST_CLEAN)
    print(f"self-test: {n - bad}/{n} 通过" + ("" if not bad else f"（{bad} 失败）"))
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(_self_test())
