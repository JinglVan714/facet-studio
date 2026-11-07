"""层 1 · 提示词契约（版本化）。

E1 的强制后果：**只用结构化输出**——引用写进结构字段，绝不让模型在自然语言里带引用
（Anthropic 官方：citations 与 structured outputs 互斥，同开 400）。

E5 修订：boundary 不存摘要，只存 prev_sid/next_sid（原文邻居指针，零生成、可验证）。

本文件是「谁产的、用的哪版提示词」里的那个版本号来源。
"""
from __future__ import annotations

PROMPT_VERSION = "l1_extract/v4"

# v5：单元制。模型**引用 unit_ids**，不再自己写 quote —— 证据文本由代码拼接。
# 这是 spec §2.1/I1 的落地：**模型碰不到证据文本**，于是极性/限定词漂移在构造上不可能发生。
PROMPT_VERSION_UNITS = "l1_extract/v6-contract"   # v6：分片由一致性契约给定，并注入相邻段标签

REL_TYPES = ("supports", "refines", "contrasts", "causes", "tension", "sequence")

SYSTEM = """你在为一段视频制作**知识底稿**。底稿不是摘要、不是成稿：它只记录「视频里说了什么、凭什么这么说」。

你要做两件事：
1. 从给定的字幕句子里抽出**断言**（assertion）：一句话就能独立站住的内容单元；
2. 标出断言之间的**关系**（relation）。

硬规则（违反会被校验器直接拒绝）：
- 每条断言的 anchors 里**至少有一个 sid**，且该 sid 必须来自标记为 `[own]` 的句子。`[ctx]` 的句子只能用来理解上下文，不能作为锚点。
- **原子性（最重要）**：一条断言只讲**一件事**，且这件事必须能被它的锚点句子**完整支撑**。
  - 把长句拆成多条短断言，**不要**把多个事实塞进一条；
  - **禁止章节级/段落级摘要**（例：不要写「本节讲了 A、B、C 四类」这种把整段打包成一句的断言）；
  - 允许删掉口语与语气词、允许调整语序，但**不得引入原句没有的信息**，不得加入你自己的结论、评价、外部知识。
- **`quote` 是必填项**：必须是锚点句子里的一段**连续原文**（照抄原文，一个标点都不要改）。
  - 必须**逐字照抄**。字幕里的错别字、口语、语气词**一律保留原样**——你要做的是定位，不是纠错；
  - **不得补全、不得改写、不得替换说法**：例如字幕是「长程任务」就写「长程任务」，不许写成「长城任务」或「长期任务」；
    字幕是「树立 API」就写「树立 API」，不许写成「梳理 API」——即使你认为原文写错了；
  - 必须是**一段连续的原文**，不许把句子里不连续的两段拼接起来；
  - 宁短勿长：写最能支撑这条断言的那一小段（通常 10–40 字）；
  - 校验器会用它在字级时间戳里定位；**照抄不许自作主张**是唯一要求，不填 quote 会失去字级定位能力。
- 帧（frame）只在**你确认那一帧上有相关文字**时才引用，且该帧时间必须落在断言的音频锚点时间范围内。
- 抽不出断言的句子可以不抽——但**不许为了凑数编造**；空内容、纯寒暄、纯广告也可以抽（如实记录即可）。
- **宁多勿并**：同一句里有几个可独立成立的事实，就写几条断言。

关系类型只能从这几个里选（不许自造）：
- supports：A 支撑 B
- refines：A 细化/具体化 B
- contrasts：A 与 B 对照/冲突
- causes：A 导致/解释了 B
- tension：A 与 B 存在张力（未直接冲突但取向不同）
- sequence：A 与 B 是同一流程/步骤序列的先后（**只用于段级流程，不用于相邻句**）

输出：只输出严格 JSON，不要 Markdown 代码块，不要任何解释文字。
"""

USER_TEMPLATE = """视频共 {n_owned} 句需要处理（标 `[own]`），另有 {n_ctx} 句只读上下文（标 `[ctx]`，仅供理解，不可作为锚点）。

## 句子
{lines}

## 本片可引用的帧（时间是毫秒；如有文字转录，那是模型读图所得，仅供参考，可能有误）
{frames}

## 输出 JSON 格式
{{
  "assertions": [
    {{
      "text": "断言文本（原语言，可压缩合并，不得新增信息）",
      "anchors": [
        {{"sid": "s0007", "start_ms": 12340, "end_ms": 18900}}
      ],
      "frame_refs": ["00003_000105000"],
      "quote": "锚点句中的连续原文片段（必填，逐字照抄，用于字级定位）",
      "boundary": {{"prev_sid": "s0006", "next_sid": "s0008"}}
    }}
  ],
  "relations": [
    {{"from_local": 0, "to_local": 1, "rel_type": "refines"}}
  ]
}}

`from_local` / `to_local` 指的是**本次输出里 assertions 数组的下标**（从 0 开始）。
`boundary` 只允许填相邻句子的 sid（原文本就是锚点句子本身），不要写摘要。
"""


SYSTEM_UNITS = """你在为一段视频制作**知识底稿**。底稿不是摘要、不是成稿：它只记录「视频里说了什么、凭什么这么说」。

这次给你的不是整句字幕，而是**已经切好的单元（unit）**——每个单元是一个独立可引用的子句，带 id、时间与**逐字原文**。

你要做两件事：
1. 挑出**断言**：把若干个单元组织成一句能独立站住的话；
2. 标出断言之间的**关系**。

硬规则（违反会被校验器直接拒绝）：
- **你只能引用 `unit_ids`，不能写引文。** 证据就是单元原文，由系统拼接，**你写不出也改不动它**。
  你要做的是"指出是哪几个单元"，不是"把原话抄一遍"。
- `unit_ids` **至少一个**，且必须来自标记 `[own]` 的单元。`[ctx]` 只用于理解上下文，不能作为证据。
- **原子性（最重要）**：一条断言只讲**一件事**，且这件事必须能被它所引的单元**完整支撑**。
  - 把长内容拆成多条短断言，**不要**把几件事塞进一条；
  - **禁止章节级/段落级摘要**（例：不要写「本节讲了 A、B、C 四类」）；
  - 允许删掉口语与语气词、允许调整语序，但**不得引入原文没有的信息**，不得加入你自己的结论、评价、外部知识。
- `text` 是**你的表述**（可压缩合并），**不是证据**：
  - 原文里的错别字、口误、口语**一律不要替它改**——纠正请放到 `corrections` 字段（见下），
    系统会把纠正作为**待人审的建议**记录，不会当成事实；
  - **限定词（可能/应该/大概/不）承载事实**：原文有就保留，或者用 `status: bounded` 声明它是有条件的。
    把"可能是"写成"是"，是把断言的强度改了——这属于越界。
- 帧（frame）只在**你确认那一帧上有相关文字**时才引用，且该帧时间必须落在断言的时间范围内。
- 抽不出断言的单元可以不抽——但**不许为了凑数编造**；空内容、纯寒暄、纯广告也可以抽（如实记录即可）。
- **宁多勿并**：几个可独立成立的事实，就写几条断言。

每条断言还要给两个字段：
- `kind`：`fact`（事实）/ `inference`（推断）/ `opinion`（观点）/ `experience`（亲历）——**由内容定，不是由体裁定**；
- `status`：`supported`（原文直接说了）/ `bounded`（原文说了但带条件或限定）——选 `bounded` 时**必须**填 `boundary` 写清条件。

关系类型只能从这几个里选（不许自造）：
- supports：A 支撑 B
- refines：A 细化/具体化 B
- contrasts：A 与 B 对照/冲突
- causes：A 导致/解释了 B
- tension：A 与 B 存在张力（未直接冲突但取向不同）
- sequence：A 与 B 是同一流程/步骤序列的先后（**只用于段级流程，不用于相邻单元**）

输出：只输出严格 JSON，不要 Markdown 代码块，不要任何解释文字。
"""

USER_TEMPLATE_UNITS = """视频共 {n_owned} 个单元需要处理（标 `[own]`），另有 {n_ctx} 个只读上下文单元（标 `[ctx]`，仅供理解，不可作为证据）。
{seg_ctx}

## 单元（格式：id [起止毫秒] 逐字原文）
{lines}

## 本片可引用的帧（时间是毫秒；如有文字转录，那是模型读图所得，仅供参考，可能有误）
{frames}

## 输出 JSON 格式
{{
  "assertions": [
    {{
      "text": "断言文本（原语言，可压缩合并，不得新增信息）",
      "unit_ids": ["s0007-u02", "s0007-u03"],
      "kind": "fact",
      "status": "supported",
      "boundary": null,
      "frame_refs": [],
      "corrections": [{{"unit_id": "s0007-u02", "wrong": "树立", "right": "梳理", "why": "上下文在讲 API 整理"}}]
    }}
  ],
  "relations": [
    {{"from_local": 0, "to_local": 1, "rel_type": "refines"}}
  ]
}}

`from_local` / `to_local` 指的是**本次输出里 assertions 数组的下标**（从 0 开始）。
`corrections` 是可选的：只有你确信原文被语音识别弄错时才填（如英文术语被听成同音词）。
**它只是待审建议**——系统不会拿它当事实，也不会替你改单元原文。
"""


def render_user_units(corpus: dict, chunk: dict, frame_table: list[dict],
                      units_by_id: dict) -> str:
    def line(tag: str, uid: str) -> str:
        u = units_by_id.get(uid)
        if not u:
            return ""
        t0, t1 = (u.get("t") or [None, None])
        return f"[{tag}] {uid} [{t0}-{t1}] {u.get('raw')}"

    lines = [line("own", u) for u in chunk["owned"]]
    lines += [line("ctx", u) for u in chunk.get("context") or []]
    lines = [x for x in lines if x]

    flines = []
    for f in frame_table:
        t = (f.get("text") or "").replace("\n", " ")
        suffix = f"  文字(模型读图)={t[:80]}" if t else ""
        flines.append(f"- {f['fid']}  t={f['t_ms']}ms{suffix}")
    # 相邻段标签 = entry/exit 状态的免费近似（契约已算好，直接用）
    prev_lb, next_lb = chunk.get("prev_label"), chunk.get("next_label")
    if chunk.get("segment_label") or prev_lb or next_lb:
        seg_ctx = (f"\n你正在处理的这一段：**{chunk.get('segment_label') or '（未命名）'}**。\n"
                   f"上一段：{prev_lb or '（无，本片开头）'}；下一段：{next_lb or '（无，本片结尾）'}。\n"
                   "**段标签只用于理解上下文，不是证据，也不要写进 text。**\n")
    else:
        seg_ctx = ""
    return USER_TEMPLATE_UNITS.format(
        n_owned=len(chunk["owned"]), n_ctx=len(chunk.get("context") or []),
        seg_ctx=seg_ctx,
        lines="\n".join(lines), frames="\n".join(flines) or "（本片无可用帧）",
    )


def render_user(corpus: dict, chunk: dict, frame_table: list[dict]) -> str:
    lines = []
    for sid in chunk["owned"]:
        s = corpus["sentences"][sid]
        lines.append(f"[own] {sid} [{s['start_ms']}-{s['end_ms']}] {s['text']}")
    for sid in chunk["context"]:
        s = corpus["sentences"][sid]
        lines.append(f"[ctx] {sid} [{s['start_ms']}-{s['end_ms']}] {s['text']}")

    flines = []
    for f in frame_table:
        t = (f.get("text") or "").replace("\n", " ")
        suffix = f"  文字(模型读图)={t[:80]}" if t else ""
        flines.append(f"- {f['fid']}  t={f['t_ms']}ms{suffix}")
    return USER_TEMPLATE.format(
        n_owned=len(chunk["owned"]), n_ctx=len(chunk["context"]),
        lines="\n".join(lines), frames="\n".join(flines) or "（本片无可用帧）",
    )
