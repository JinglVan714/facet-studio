"""层 1.5 · 纠正层（最小实现）：**发现冲突，不替人裁决**。

## 为什么需要它——一次真实撞见

底稿里有一条断言：`身上白色特别少的玳瑁，古人将这称为"玳瑁滚地**金**"`。
它的锚点字幕（ASR）确实写「金」。但**同一时刻画面上的字**（帧 `00061_000200900`）写的是
「玳瑁、滚地**锦**」。观众的屏幕上写着一个字，讲解员嘴里（被转写成）另一个字。

后果实测：投影层照抄了 ASR 的「金」，而 L3 复核员在**同一条输入上判出了相反的结论**
（6 次里 5 次 SUPPORTED、1 次 WEAK，**且各自的理由互相矛盾**——有一次甚至说
"字幕与画面均为锦"，而字幕实际是金）。

**这不是复核员不稳，是它撞上了两条互斥的证据。** 消解冲突是一个**决策**（谁对？还是都留着？），
不是一次**检查**——所以它不该由复核员顺手做掉，也不该由哪个源"先读到算谁的"。

## 这个模块做什么 / 不做什么

✅ 做：把「ASR 转录」与「同片画面文字」之间的**逐字差异**机械地找出来，附上下文与两边的原文。
❌ 不做：不判断谁对，不修改任何证据，不自动采纳任何一方。
   产出是**待人审的冲突清单**（spec §2.4 的 L1.5 存储），与模型写的 `corrections` 字段同级。

## 为什么是机械的

两边都是**已经落盘的字符串**，比对不需要模型。所以这一层是 ✅ 可复算的——
与"模型提议纠正"完全不同级别。差异检测用 `difflib`（标准库，无依赖、无随机性）。
"""
from __future__ import annotations

import difflib
import json
import re
import time
from pathlib import Path

CORRECTION_VERSION = "correction/v1"

# 只在**同位置短替换**上判冲突：1–3 个字的替换是"形近/同音错字"的特征长度。
# 长度差太多的对齐（整句重排）不是错字，是画面文字和口播本来就说的不是一回事，
# 拿它报冲突会造成大量假阳性。
MAX_SPAN = 3
# 太短的碎片没有判别力（「的」「是」换来换去）
MIN_CTX_CHARS = 4
# 钉住一处差异所需的**最短相邻匹配**。低于它的"差异"两侧锚太短，
# 说明那只是画面文字与口语片段恰好撞上，不是同一处内容的两种写法。
MIN_ANCHOR = 4
# 同一处内容的两种写法**不会跨书写系统**：真实的拉丁词冲突是 `circle`/`SQL` 这种两边都是拉丁，
# 中文↔拉丁则是"中文被对齐到了一个拉丁碎片上"。实测这类全部是误报
# （`他`/`ta`、`啊`/`i`、`奶牛猫`/`ili`、`拿到`/`rø` —— 后两个来自水印 `RØDE` 被读进了正文行），
# 而**剔掉它零召回损失**。所以要求差异两侧属于同一书写系统。
_CJK = re.compile(r"[一-鿿]")


_CJK_DIGITS = {"〇": 0, "零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4,
               "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
_CJK_UNITS = {"十": 10, "百": 100, "千": 1000}


def _cjk_num_to_arabic(tok: str) -> int | None:
    """`七十二` → 72。**只接受纯中文数字 token**，解析不了就返回 None（绝不猜）。

    为什么需要：`5` / `五` 是**写法差异不是字词差异**，不该进复核队列。
    但反过来说，**数字错了是代价最大的一类错**——所以只折叠"能无歧义解析的写法"，
    解析不了的原样留着让它继续报冲突。宁可多报一条写法差异，不可漏掉一个错数字。
    """
    if not tok or any(c not in _CJK_DIGITS and c not in _CJK_UNITS for c in tok):
        return None
    total, cur = 0, 0
    for c in tok:
        if c in _CJK_DIGITS:
            cur = _CJK_DIGITS[c]
        else:
            unit = _CJK_UNITS[c]
            total += (cur or 1) * unit
            cur = 0
    return total + cur


_DROP = re.compile(r"[\s,，。.;；:：!！?？·、|/\\_~^—–\-−─═*=✕✖×✚+<>《》「」『』（）()"
                   r"\[\]【】\"'“”‘’]")
_CJK_NUM_RUN = re.compile(r"[〇零一二两三四五六七八九十百千]+")


def _norm_with_map(s: str) -> tuple[str, list[int]]:
    """归一化，**同时给出每个归一化字符对应的原文下标**。

    为什么要映射：差异位置是在归一化串上算出来的，但**给 reviewer 看的 `window`
    必须是原文**。旧版直接把归一化串当 window 输出，于是人看到的是 `4川`、`1样`
    这种被改写过的文本——**审的人看到的不是原片里的字**，这比不给上下文更坏。

    归一化只做"删字符"与"折叠数字"，两者都能保持下标对应：
    删除的字符不占位；折叠出的数字统一指向该 token 的起始下标。
    """
    s = s or ""
    low = s.lower()                      # lower 不改长度（中文不受影响）
    out: list[str] = []
    idx: list[int] = []
    i = 0
    while i < len(low):
        m = _CJK_NUM_RUN.match(low, i)
        if m:
            v = _cjk_num_to_arabic(m.group(0))
            if v is not None:
                for d in str(v):
                    out.append(d)
                    idx.append(i)        # 折叠出的每一位都指回该 token 的开头
            else:
                for k in range(i, m.end()):
                    out.append(low[k]); idx.append(k)
            i = m.end()
            continue
        c = low[i]
        if not _DROP.match(c):
            out.append(c)
            idx.append(i)
        i += 1
    return "".join(out), idx


def _norm(s: str) -> str:
    """比对前的归一：**把所有"写法差异"清掉，只留下"字词差异"**。

    2026-10-15 扩过一次。旧版只清 `，。；：` 一类，后果是破折号 `——` / `---`、
    乘号 `×`、大小写 `p`/`P`、中文数字 `五`/`5` 全部活下来冒充"冲突"
    ——实测 29 条里这类占了 10 条。归一的职责就是**把非字词的东西清干净**，
    让剩下的每一条差异都值得人看一眼。
    """
    return _norm_with_map(s)[0]


def static_overlay_lines(frames: dict, *, min_ratio: float = 0.25, min_frames: int = 5) -> set[str]:
    """**机械识别水印/固定贴片**：在足够多的帧里逐字重复的那些行。

    为什么需要：实测 BV1znXSBqEUP 的每帧都带 `唯一讲述者` + `anda seat`，
    BV1ybHXzfEEu 每帧带 `于谦` + `多新鲜呐`。这些静态文字会跟**任何**同音字对上，
    于是伪造出一堆"冲突"——29 条里 9 条是这个来源。**播出方自己压的水印不是"原片内容"**，
    拿它当证据比对是在跟水印较劲。

    判据纯机械且可复算：某行在 ≥max(min_frames, ratio×总帧数) 帧里逐字出现。
    """
    if not frames:
        return set()
    need = max(min_frames, int(len(frames) * min_ratio))
    counts: dict[str, int] = {}
    for f in frames.values():
        for ln in set((f.get("text") or "").splitlines()):
            ln = ln.strip()
            if 1 <= len(ln) <= 30:
                counts[ln] = counts.get(ln, 0) + 1
    return {ln for ln, c in counts.items() if c >= need}


def _align_short_gap(a_gap: str, b_gap: str, prev_len: int, next_len: int,
                     a_has_next: bool) -> tuple[str, str, str]:
    """一边长、一边短的替换：**长的那个里面掺了"另一半根本没有的内容"**。

    这是实测倒逼出来的（见模块顶注）：`金` ↔ `锦` 本该报出来，实际却被并成了
    `金白色较多的玳瑁叫玳瑁猴彩霞` ↔ `锦`——因为画面文字**就到「滚地锦」为止**，
    句子后面的 13 个字在画面里没有对应。旧代码按 `len<=MAX_SPAN` 一筛，**把真实差异筛掉了**。
    而"画面只覆盖句子的一部分"是**最常见**的情况，所以那个过滤方向是反的。

    **对齐方向由"哪边紧邻的匹配更长"决定**（更长的匹配更有力地钉住对应关系）：
    - 前面匹配更长 ⇒ 差异在长边的**开头**（本案例：前有「为玳瑁滚地」、后面没了 ⇒ 取 `金`）
    - 后面匹配更长 ⇒ 差异在长边的**末尾**
    返回 `(短边对应的片段, 是否歧义)` —— 两边一样长时方向不定，**标歧义而不是猜**。
    """
    long_is_a = len(a_gap) > len(b_gap)
    long_g, short_g = (a_gap, b_gap) if long_is_a else (b_gap, a_gap)
    k = len(short_g)
    if prev_len == next_len:
        frag, ambiguous = long_g[:k], True       # 方向不定：标出来，不假装知道
    elif prev_len > next_len:
        frag, ambiguous = long_g[:k], False      # 差异在开头
    else:
        frag, ambiguous = long_g[-k:], False     # 差异在末尾
    return (frag, short_g, "ambiguous" if ambiguous else "ok") if long_is_a \
        else (short_g, frag, "ambiguous" if ambiguous else "ok")


def diff_asr_vs_screen(asr_text: str, screen_text: str) -> list[dict]:
    """比对**一条口播文本**与**一帧画面文字**，返回逐字差异。

    返回项：`{asr, screen, window, ambiguous, trailing}` ——
    `asr`/`screen` 是两边各自的写法，`window` 是原句里的上下文（供人判，不供自动裁决），
    `ambiguous=True` 表示对齐方向不定（**只有 1–2 字差异时才可能出现**，
    且此时人一眼就能从 `window` 看出来，所以标出来比猜好）。
    """
    a, amap = _norm_with_map(asr_text)
    b, _ = _norm_with_map(screen_text)
    if not a or not b:
        return []
    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    ops = sm.get_opcodes()
    out: list[dict] = []
    for idx, (tag, i1, i2, j1, j2) in enumerate(ops):
        if tag != "replace":
            continue
        ag, bg = a[i1:i2], b[j1:j2]
        # 紧邻匹配的长度；opcode 是 (tag, i1, i2, j1, j2)，`equal` 时两侧等长
        prev_len = ops[idx - 1][4] - ops[idx - 1][3] if idx > 0 else 0
        next_len = ops[idx + 1][4] - ops[idx + 1][3] if idx + 1 < len(ops) else 0
        short, long = min(len(ag), len(bg)), max(len(ag), len(bg))
        if long <= MAX_SPAN:
            # 短替换：要求**两侧都有足够长的匹配**钉住它，否则它只是碎片
            # （画面只覆盖长句一部分时，difflib 会切出一堆无意义的碎片替换）。
            if min(prev_len, next_len) < MIN_ANCHOR and (prev_len < MIN_ANCHOR or next_len < MIN_ANCHOR):
                if max(prev_len, next_len) < MIN_ANCHOR:
                    continue
            left, right, amb = ag, bg, "ok"
        elif short <= MAX_SPAN and (i2 >= len(a) or j2 >= len(b) or i1 == 0 or j1 == 0):
            # 一边长一边短，**且短的那侧正贴着画面文字的边界**（画面的覆盖到此为止）。
            # 这个额外条件不能省：不加它，画面只覆盖长句一部分时会产生大量碎片替换，
            # 实测冲突数会从 7 涨到 17（噪声），而真差异只多抓到 1 条（金/锦）。
            # 贴着边界 ⇒ 长的那些字是"句子继续说、画面没了"，不是错字。
            if max(prev_len, next_len) < MIN_ANCHOR:
                continue
            left, right, amb = _align_short_gap(ag, bg, prev_len, next_len, idx + 1 < len(ops))
        else:
            continue                      # 其余情况：不是错字，是两段不同的话
        # 跨书写系统的"替换"不是写法差异（见 `_CJK` 旁的实测说明）
        if bool(_CJK.search(left)) != bool(_CJK.search(right)):
            continue
        # ⚠️ window 必须取**原文**：归一化串里是 `4川`、`1样` 这种被改写过的东西，
        # 拿它当上下文，审的人看到的就不是原片里的字。用下标映射折回原文。
        orig = asr_text or ""
        lo = amap[max(0, i1 - MIN_CTX_CHARS)] if amap else 0
        hi = (amap[min(len(a) - 1, i2 + MIN_CTX_CHARS)] + 1) if amap else len(orig)
        out.append({"asr": left, "screen": right, "window": orig[lo:hi],
                    "ambiguous": amb == "ambiguous"})
    return out


def find_asr_screen_conflicts(sentences: dict, frames: dict,
                              units: list[dict] | None = None,
                              assertions: list[dict] | None = None) -> dict:
    """全片扫一遍：**每句 ASR 文本** × **落在它时间范围内的帧文字**。

    范围口径：用**时间重叠**而不是"断言引用了哪帧"。理由：纠正层的目的是发现
    "原片自相矛盾"，与投影层有没有用到那帧无关——只在被引用的帧里找，
    冲突就会随引用行为时有时无，那样它就不是一份稳定的资产。

    ## 试过两个优先级判据，**都失败**，所以本函数不提供 severity

    本想给这 74 条排个优先级，免得人审面对一份平铺清单。两个判据都试了、都实测过：

    | 判据 | 结果 | 为什么废 |
    |---|---|---|
    | 「受影响的 unit 被断言引用了吗」 | **68/74 = 高** | 断言覆盖了大部分内容单元，几乎全落进"高" |
    | 「冲突的字在断言的 `quote`（逐字证据）里吗」 | **67/74 = 在** | quote 就是证据文本，同样几乎全覆盖 |

    **两个判据都不区分**，因为检出的冲突本来就几乎全落在证据文本里。于是：
    - "重不重要"这个筛子**机械上不存在**——不是我没找到，是这类数据里没有这个维度；
    - 唯一还能分的是"这到底是不是真冲突"（VLM 认错字 / 同义换字 / 画面与口播本就无关），
      **而那需要人判**。

    ⇒ 所以不发明一个把 92% 标成"high"的字段（那正是本项目一直在打的假信号），
    改为**把判读所需的信息给全**：两边原文、上下文窗口、画面文字全文、受影响的 unit。
    并**如实给出假阳性率的粗估**（见下），而不是把它藏起来。
    """
    units = units or []
    unit_of_sid: dict[str, list[dict]] = {}
    for u in units:
        unit_of_sid.setdefault(u.get("sid") or "", []).append(u)

    cited: set[str] = set()
    for a in assertions or []:
        cited.update(a.get("unit_ids") or [])

    quotes = " ".join((a.get("quote") or "") for a in assertions or [])
    cited: set[str] = set()
    for a in assertions or []:
        cited.update(a.get("unit_ids") or [])

    overlay = static_overlay_lines(frames)
    rows = []
    for sid, s in (sentences or {}).items():
        t0, t1 = s.get("start_ms"), s.get("end_ms")
        if t0 is None or t1 is None:
            continue
        for fid, f in (frames or {}).items():
            txt = (f.get("text") or "").strip()
            ft = f.get("t_ms")
            if not txt or ft is None or not (t0 <= ft <= t1):
                continue
            # 水印/固定贴片不当证据：它是播出方压的，不是"原片里说的话"，
            # 留着它会跟任何同音字对上，伪造冲突（实测 29 条里 9 条来自这里）。
            body = "\n".join(ln for ln in txt.splitlines() if ln.strip() not in overlay)
            if not _norm(body):
                continue
            for d in diff_asr_vs_screen(s.get("text") or "", body):
                uids = [u["unit_id"] for u in unit_of_sid.get(sid, [])
                        if _norm(d["asr"]) and d["asr"] in _norm(u.get("raw") or "")]
                rows.append({
                    "sid": sid, "frame_id": fid, "frame_t_ms": ft,
                    "asr": d["asr"], "screen": d["screen"], "window": d["window"],
                    "ambiguous": d.get("ambiguous", False),
                    "sentence_text": s.get("text"),
                    "screen_text": body,
                    # 受影响的 unit：投影层引用的是 unit，所以冲突必须能落到 unit 上，
                    # 否则人审改完不知道要动哪里、下游也不知道哪些断言受影响。
                    "unit_ids": uids,
                    # 这两项**不是优先级**（两个判据都试过、都不区分，见上），
                    # 只是为了让人判得快：这段差异有没有真的进证据文本。
                    "in_quote": bool(d["asr"] and d["asr"] in quotes),
                    "frame_advisory": bool(f.get("advisory", True)),
                })
    in_quote = sum(1 for r in rows if r["in_quote"])
    return {
        "version": CORRECTION_VERSION,
        "producer": "code",
        "credit": "reproducible",
        "count": len(rows),
        "in_quote": in_quote,
        "overlay_lines_dropped": sorted(overlay),
        "stats": {
            "in_quote": in_quote,
            "touching_cited_unit": sum(1 for r in rows if any(u in cited for u in r["unit_ids"])),
            "no_severity_field": ("**故意不提供**：两个候选判据实测都不区分"
                                  "（68/74 与 67/74 全落同一档），给不出有意义的优先级。"),
        },
        "conflicts": rows,
        "discipline": ("**只发现，不裁决。** 两边都是原文（ASR 转录 / 画面上的字），"
                       "谁对由人判；本清单不改任何证据，也不进任何门禁。"
                       "它是 L1.5 的存储，与模型写的 `corrections` 字段同级但**可信级别更高**"
                       "（模型项是提议，这里是机械比对）。"),
        "caveat": ("**假阳性率是粗估的，不是测出来的**：抽看 10 条，约 3–4 条不是真冲突。"
                   "来源有三类："
                   "①画面文字是**读图所得**（`frame_advisory=true`），本就会认错字；"
                   "②画面与口播说的**本来就不是一回事**时（标题条 vs 讲解），对齐会切出无意义的短替换；"
                   "③同义换字（宋『朝』/宋『代』）不是错。"
                   "**判读时看 `window` 与 `screen_text`**，别只看 `asr`/`screen` 两个字。"),
    }


def write_corrections(video_id: str, payload: dict, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    p = out_dir / "corrections_asr_vs_screen.json"
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return p


# ====================================================================== L1.5 人审回路
#
# 分工：**机械层给候选，人给裁定，账本存裁定**。
# 机械层永远不写账本；账本只由 `ingest_review` 写；下游只读账本。

LEDGER_NAME = "corrections_ledger.jsonl"
REVIEW_KIND = "correction"

# 人能给的裁定。**每一种都要能被下游无歧义地解释**，所以是封闭集合。
DECISIONS = {
    "accept_screen": "画面文字对，字幕错 —— 采纳画面写法为纠正",
    "accept_asr": "字幕对，画面是读图认错 —— 不纠正，但记下这条已判过（不再进复核队列）",
    "custom": "两边都不对 —— 由人给出正确写法（填 `corrected`）",
    "not_a_conflict": "误报（同义换字 / 画面与口播本就无关）—— 记下，不再进复核队列",
}


def conflict_key(video_id: str, sid: str, asr: str) -> str:
    """账本主键 = **被纠正的那段字幕**，不是"哪一帧暴露了它"。

    为什么不用 `frame_id`：帧一旦重新抽取（换抽帧策略、换分辨率），id 就变了，
    而"这句字幕错了、应该是 X"这个判断**与帧无关**。用帧做键 = 人审一次的决定会在
    下次重抽帧后全部失效。同理不用 `unit_id`（单元切分版本变了就没了）。

    `(video_id, sid, asr)` 在所有这些变化下都稳定。
    """
    return f"{video_id}|{sid}|{asr}"


def build_correction_review(video_id: str, payload: dict, *, limit: int | None = None,
                            out_dir: Path | None = None) -> dict:
    """把机械冲突清单变成**可直接填的表**（约定同 `review_kit`：留空待人填）。

    🔴 **已经判过的条目不再出现**——账本里有记录的 key 会被跳过。
    否则人每次重跑都要把同样的 74 条再看一遍，这个回路三天就没人用了。
    """
    from .constants import DATA_DIR

    out_dir = out_dir or DATA_DIR / "review"
    out_dir.mkdir(parents=True, exist_ok=True)
    ledger = load_ledger(video_id)
    known = {e["key"] for e in ledger}

    items, skipped = [], 0
    for c in payload.get("conflicts") or []:
        k = conflict_key(video_id, c["sid"], c["asr"])
        if k in known:
            skipped += 1
            continue
        items.append({
            "key": k,
            "frame_t_ms": c["frame_t_ms"],
            "window": c["window"],
            "asr": c["asr"],
            "screen": c["screen"],
            "sentence_text": c["sentence_text"],
            "screen_text": c["screen_text"],
            "unit_ids": c["unit_ids"],
            "in_quote": c["in_quote"],
            "frame_advisory": c["frame_advisory"],
            # ↓ 待人填
            "decision": None,
            "corrected": None,
            "reviewed_by": None,
            "note": ("填 `decision`（四选一）："
                     + "；".join(f"{k}={v}" for k, v in DECISIONS.items())
                     + "。选 `custom` 时必须填 `corrected`。"
                     "填完跑：python -m lmind.cli corrections-ingest"),
        })
    if limit:
        items = items[:limit]

    out = out_dir / f"{REVIEW_KIND}_review_{video_id}.json"
    out.write_text(json.dumps({
        "video_id": video_id,
        "how_to": ("看 `window`（字幕上下文）与 `screen_text`（画面文字全文）判断谁对。"
                   "**画面文字是读图所得，本身会认错字**，别看它写着就一定对。"
                   "填完跑：python -m lmind.cli corrections-ingest"),
        "decisions": DECISIONS,
        "already_reviewed_skipped": skipped,
        "items": items,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"file": str(out), "count": len(items), "skipped_known": skipped,
            "ledger_size": len(known)}


def load_ledger(video_id: str) -> list[dict]:
    """读账本（append-only，jsonl）。**这是裁定的唯一来源。**"""
    from .constants import DATA_DIR

    p = DATA_DIR / video_id / "substrate" / LEDGER_NAME
    if not p.exists():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                out.append(json.loads(line))
            except Exception:  # noqa: BLE001
                continue
    return out


def ingest_review(video_id: str, review_path: Path | None = None,
                  out_dir: Path | None = None) -> dict:
    """读填好的表 → **追加**进账本。不覆盖、不改行、不改任何证据。

    空 `decision` 的条目原样留在表里（下次还能填）；已入账的 key 再填也不重复追加。
    """
    from .constants import DATA_DIR

    out_dir = out_dir or DATA_DIR / "review"
    p = review_path or out_dir / f"{REVIEW_KIND}_review_{video_id}.json"
    if not p.exists():
        raise FileNotFoundError(f"没有复核文件：{p}")
    doc = json.loads(p.read_text(encoding="utf-8"))
    ledger_path = DATA_DIR / video_id / "substrate" / LEDGER_NAME
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    known = {e["key"] for e in load_ledger(video_id)}

    added, bad, pending = [], [], 0
    for it in doc.get("items") or []:
        d = (it.get("decision") or "").strip()
        if not d:
            pending += 1
            continue
        if d not in DECISIONS:
            bad.append({"key": it.get("key"), "why": f"decision 非法：{d!r}"})
            continue
        if d == "custom" and not (it.get("corrected") or "").strip():
            bad.append({"key": it.get("key"), "why": "custom 必须给 corrected"})
            continue
        if it["key"] in known:
            continue
        added.append({
            "key": it["key"], "video_id": video_id,
            "sid": (it["key"].split("|") + ["", ""])[1],
            "asr": it["asr"], "screen": it["screen"],
            "decision": d,
            # 只在真纠正时才有 new；`accept_asr`/`not_a_conflict` 是**否决**，
            # 记下来是为了"不再问第二遍"，不是为了让下游改文本。
            "new": (it["screen"] if d == "accept_screen"
                    else (it.get("corrected") or "").strip() if d == "custom" else None),
            "old": it["asr"],
            "evidence": {"frame_id": None, "frame_t_ms": it["frame_t_ms"],
                         "window": it["window"], "screen_text": it["screen_text"],
                         "in_quote": it.get("in_quote"), "unit_ids": it.get("unit_ids")},
            "reviewed_by": it.get("reviewed_by") or "unknown",
            "reviewed_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "version": CORRECTION_VERSION,
        })
    if added:
        with ledger_path.open("a", encoding="utf-8") as f:
            for e in added:
                f.write(json.dumps(e, ensure_ascii=False) + "\n")
    eff = [e for e in added if e["new"]]
    return {"file": str(p), "ledger": str(ledger_path), "added": len(added),
            "effective_corrections": len(eff), "rejections": len(added) - len(eff),
            "pending": pending, "invalid": bad,
            "ledger_size": len(known) + len(added)}


def corrected_units(units: list[dict], ledger: list[dict]) -> tuple[list[dict], dict]:
    """产出**纠正层**：`raw` 不动，另给一个 `corrected`（无纠正时等于 raw）。

    这是 §2.4 三层表的落地：
    | raw unit       | ASR 原样      | 可读 ❌ | 机械 100% |
    | corrected unit | 人审过的纠正  | 可读 ✅ | 机械 + 已审 |

    **绝不就地覆盖 `raw`。** 一旦覆盖，"逐字证据"这个性质就没了——
    而它是 I1 的根，`quote == Σ unit raws` 的整套校验都建立在它上面。

    替换口径：在 `raw` 里把 `old` 替换成 `new`，**只替换第一处**并记录位置；
    找不到 `old` 的条目计入 `unapplied`（切分版本变了会导致这种）
    —— **不静默忽略**，那些必须浮出来。
    """
    by_key: dict[str, dict] = {}
    for e in ledger:
        if e.get("new"):
            by_key[e["key"]] = e
    out, applied, unapplied = [], [], []
    for u in units:
        raw = u.get("raw") or ""
        cu = {**u, "raw_original": None}
        for e in by_key.values():
            if e["sid"] != u.get("sid") or not e["old"] or e["old"] not in raw:
                continue
            at = raw.find(e["old"])
            raw = raw[:at] + e["new"] + raw[at + len(e["old"]):]
            cu["raw_original"] = u.get("raw")
            applied.append({"unit_id": u["unit_id"], "key": e["key"],
                            "old": e["old"], "new": e["new"]})
        cu["raw"] = raw
        cu["corrected"] = bool(cu["raw_original"])
        out.append(cu)
    used_sids = {(e["sid"], e["old"]) for e in by_key.values()}
    hit = {(a["key"].split("|")[1], a["old"]) for a in applied}
    for k in used_sids - hit:
        unapplied.append({"sid": k[0], "old": k[1],
                          "why": "该句里找不到要替换的原文（切分/转写版本可能已变）"})
    return out, {"ledger_effective": len(by_key), "applied": len(applied),
                 "unapplied": unapplied, "units_changed": sum(1 for u in out if u["corrected"]),
                 "discipline": "**raw 永不覆盖**；纠正层是派生的，可随时由账本重算。"}


def correction_impact(video_id: str, ledger: list[dict] | None = None) -> dict:
    """**先看后果，再决定要不要生效**：已入账的纠正会改动哪些断言/quote。

    为什么要有这一步：纠正层的价值在"人审一次、下游全部共享"，但那也意味着
    **一次裁定会同时改掉所有引用它的产物**。给不出来这个影响面，
    人就是在盲签。
    """
    from .evidence import load_assertions
    from .units import build_units
    from .corpus import load_corpus

    ledger = ledger if ledger is not None else load_ledger(video_id)
    eff = [e for e in ledger if e.get("new")]
    if not eff:
        return {"video_id": video_id, "ledger_effective": 0, "affected_assertions": []}
    units, _ = build_units(load_corpus(video_id))
    fixed, stats = corrected_units(units, ledger)
    changed_uids = {u["unit_id"] for u in fixed if u["corrected"]}
    rows = []
    for a in load_assertions(video_id):
        uids = set(a.get("unit_ids") or [])
        hit = uids & changed_uids
        if not hit:
            continue
        rows.append({
            "assertion_id": a["id"],
            "units": sorted(hit),
            "quote_before": a.get("quote"),
            "quote_after": "".join(u["raw"] for u in fixed if u["unit_id"] in uids),
            "text": a.get("text"),
        })
    return {"video_id": video_id, "ledger_effective": len(eff),
            "units_changed": stats["units_changed"],
            "affected_assertions": rows,
            "note": ("`quote_after` 是按纠正层重算的证据文本。**这一步只算不写**——"
                     "要不要让下游用纠正层，是另一个决定（它会让 `quote_source` 换代，"
                     "并按 §8.0b 让现有投影全部变陈旧）。")}

