"""说话人归属层（用户裁定 B）：把「谁在说」作为**显式、可核对**的一层，供投影引用。

背景（为什么需要它）：访谈类素材实测 ALCE citation recall 只有 0.6154——
因为断言是对话原文（"您…还是到这儿来？"），**说话人不在断言内容里**，
投影模型为了让总结读得懂，**自己推断了"谁说的"**，而这个推断没有底稿支撑。
不做说话人分离的代价在这里显性暴露。裁定 B = 把说话人做成一层显式证据，让模型**引用**而不是**推断**。

设计约束（守住底稿纪律）：
1. **必须有证据**：每条归属都要能指回句子里的线索（称谓/自我介绍/被点名），无证据则**留空**（不许猜）；
2. **是模型产出**：所以登记 model/prompt_version/produced_at，并标 advisory（不参与任何判定）；
3. **只做「句子级角色/名字」**，不做音频分离（用户 M1 裁定）、不做全片说话人聚类；
4. 落在语料层的**独立文件**（`speaker_map.json`），不改 `transcript.json`（原稿只读）。
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from .constants import DATA_DIR
from .tracing import trace_stage

SPEAKER_VERSION = "speaker_map/v1"

SYSTEM = """你在为一段视频的字幕做**说话人归属**，但粒度是**连续句块**，不是单句。

为什么用句块：字幕的句子边界由 ASR 按停顿切分，**不对齐说话人边界**——
一句话里常常混了两个人在说（例如"把菜菜子请到咱们节目啊…大家好我是菜菜子"）。
所以正确的问题是：**从第几句到第几句是同一个人在说**。

硬规则（违反即作废）：
1. **证据必须来自该句块内部**：evidence 只能引用 spk_from..spk_to 范围内句子的连续原文片段；
2. **只有明确的第一人称线索才算证据**：自我介绍（"我是…"）、自述（"我以为…""我们那边…"）、
   明显的连续对话归属线索（一问一答且能确认提问方/回答方）。**单纯提到某人的名字不算证据**；
3. **拿不准就不要输出这一段**——宁可段数少、范围小，**绝不许凭常识猜**；
4. 名字用字幕里出现过的写法；判断不了名字时给角色（"主持人"/"嘉宾"）；
5. 块之间**不要重叠**；允许有句子不属于任何块（留空）。

输出严格 JSON：
{
  "blocks": [
    {"spk_from": "s0004", "spk_to": "s0004", "speaker": "于谦", "role": "嘉宾",
     "evidence": "我是于谦啊（本块内连续原文）"}
  ],
  "notes": "整体判断说明（例如：大量句子混人，故只标出可判定的块）"
}
"""

ROLE_ONLY_HINT = """若字幕里几乎没有出现人名，只依据问答交错给出 role（主持人/嘉宾），
但**交替模式本身不算充分证据**——只有当一方明显在提问、另一方在回答，且这种模式连续出现 ≥3 轮时，
才可据此给 role；否则一律 null。"""


def _client():
    from .extract_l1 import _client as c
    return c()


def build_speaker_map(video_id: str, *, model: str = "deepseek-flash",
                      batch_size: int = 60, limit: int | None = None) -> dict:
    """为每条句子推断说话人（有证据才填）。返回并落盘 `speaker_map.json`。"""
    from .corpus import load_corpus

    corpus = load_corpus(video_id)
    sids = [sid for sid in corpus["order"] if corpus["sentences"][sid]["has_content"]]
    if limit:
        sids = sids[:limit]

    client = _client()
    per_sentence: dict[str, dict] = {}
    blocks: list[dict] = []
    rejected: list[dict] = []
    pos = {sid: i for i, sid in enumerate(sids)}
    batches = [sids[i:i + batch_size] for i in range(0, len(sids), batch_size)]
    for bi, batch in enumerate(batches):
        lines = "\n".join(
            f"{sid} [{corpus['sentences'][sid]['start_ms']/1000:.1f}s] {corpus['sentences'][sid]['text']}"
            for sid in batch)
        user = (f"## 字幕（按时间顺序；{len(batch)} 句，块不可跨批）\n{lines}\n\n"
                f"## 补充约束\n{ROLE_ONLY_HINT}\n\n请给出说话人句块。")
        try:
            with trace_stage("speakers", version=SPEAKER_VERSION):
                resp = client.chat.completions.create(
                    model=model,
                    messages=[{"role": "system", "content": SYSTEM},
                              {"role": "user", "content": user}],
                    response_format={"type": "json_object"}, temperature=0)
            data = json.loads(resp.choices[0].message.content or "{}")
            for row in data.get("blocks") or []:
                a, b = row.get("spk_from"), row.get("spk_to")
                sp, role, ev = row.get("speaker"), row.get("role"), (row.get("evidence") or "").strip()
                if a not in pos or b not in pos or pos[a] > pos[b]:
                    rejected.append({"block": row, "reason": "句号越界或倒序"})
                    continue
                if a not in batch or b not in batch:
                    rejected.append({"block": row, "reason": "块跨批"})
                    continue
                span_text = " ".join(corpus["sentences"][s]["text"] for s in sids[pos[a]:pos[b] + 1])
                if not ev:
                    rejected.append({"block": row, "reason": "无证据"})
                    continue
                # 机械校验：证据必须能在**该块范围内**逐字找到
                if ev not in span_text:
                    rejected.append({"block": row, "reason": f"证据不在块内：{ev[:20]}"})
                    continue
                # 机械校验：块之间不重叠
                if any(not (pos[b] < pos[x["spk_from"]] or pos[a] > pos[x["spk_to"]]) for x in blocks):
                    rejected.append({"block": row, "reason": "与已有块重叠"})
                    continue
                blk = {"spk_from": a, "spk_to": b, "speaker": sp or None, "role": role or None,
                       "evidence": ev, "sentence_count": pos[b] - pos[a] + 1}
                blocks.append(blk)
                for s in sids[pos[a]:pos[b] + 1]:
                    per_sentence[s] = {"speaker": sp or None, "role": role or None,
                                       "block": f"{a}..{b}", "evidence": ev}
        except Exception as e:  # noqa: BLE001
            rejected.append({"batch": bi, "reason": f"{type(e).__name__}: {e}"[:80]})

    named = sum(1 for v in per_sentence.values() if v.get("speaker"))
    roled = sum(1 for v in per_sentence.values() if not v.get("speaker") and v.get("role"))
    covered = len(per_sentence)
    doc = {
        "video_id": video_id,
        "provenance": {"model": model, "prompt_version": SPEAKER_VERSION,
                       "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                       "advisory": True,
                       "granularity": "连续句块（不是单句）——因为 ASR 句子边界不对齐说话人边界",
                       "note": "模型产出：有块内证据才填；不参与任何判定"},
        "total_sentences": len(sids),
        "covered_sentences": covered,
        "unattributed": len(sids) - covered,
        "named": named, "role_only": roled,
        "blocks": blocks,
        "rejected": rejected[:20],
        "per_sentence": per_sentence,
    }
    p = DATA_DIR / video_id / "speaker_map.json"
    p.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    return doc


def speaker_table_for_prompt(video_id: str, sids: list[str]) -> str:
    """给投影用的「说话人句块表」——只列有归属的块，且只列与本次证据相关的。"""
    p = DATA_DIR / video_id / "speaker_map.json"
    if not p.exists():
        return ""
    doc = json.loads(p.read_text(encoding="utf-8"))
    want = set(sids)
    rows = []
    for b in doc.get("blocks") or []:
        if want and not (want & set(_expand(b, doc))):
            continue
        who = b.get("speaker") or (f"（{b.get('role')}）" if b.get("role") else "?")
        rows.append(f"- {b['spk_from']}..{b['spk_to']}（{b.get('sentence_count')} 句）：{who}"
                    + (f"　依据：{b['evidence']}" if b.get("evidence") else ""))
    if not rows:
        return ""
    head = "## 说话人句块（模型推断、块内可核对；**只能引用这里给出的归属**）"
    tail = ("（**句块之外的句子没有归属**：写「对话中提到」「有人问」这类不含名字的说法，"
            "或标 gloss——不许自行推断是谁说的）")
    return "\n".join([head, *rows[:60], tail])


def _expand(block: dict, doc: dict) -> list[str]:
    a, b = block["spk_from"], block["spk_to"]
    keys = list((doc.get("per_sentence") or {}).keys())
    out, on = [], False
    for k in keys:
        if k == a:
            on = True
        if on:
            out.append(k)
        if k == b:
            break
    return out
