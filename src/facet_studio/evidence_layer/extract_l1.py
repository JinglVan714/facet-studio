"""层 1 · 抽取：分片调用模型 -> 断言 + 关系（结构化输出）。

可靠性做法集中在这里：
- **结构化输出**（response_format=json_object），E1；
- 模型只给本地下标，全局 id 由程序生成（模型不碰 id，避免造 id）；
- **失败不静默**：解析失败/超时进 errors，写出原始响应以便复核；
- 每条断言登记出处（模型 / 提示词版本 / 时间），E2 + M4。
"""
from __future__ import annotations

import functools
import json
import os
import re
import time
from pathlib import Path

from .anchor import enrich_assertion_anchors
from .audio import apply_ssl_shim
from .structured_out import board_check, call_with_repair
from .constants import DATA_DIR
from .corpus import sent_key  # noqa: F401  (供 fingerprint 使用)
from .prompts_l1 import (  # noqa: F401
    PROMPT_VERSION, PROMPT_VERSION_UNITS, REL_TYPES, SYSTEM, SYSTEM_UNITS,
    render_user, render_user_units,
)

ASSERT_KINDS = ("fact", "inference", "opinion", "experience")
ASSERT_STATUS = ("supported", "bounded")

# schema 版本：进缓存键，也进报告。**改了校验规则必须升它**，否则会命中旧缓存，
# 造成"以为改了其实没跑"的假象（与 prompt_version / unit config_hash 同一纪律）。
SCHEMA_VERSION = "l1_schema/v3"   # v3：frame_refs 改为挽救而非判失败

# 帧引用是**偏好，不是有效性条件**（2026-10-15 决策："保证输出"）。
# 背景：BV1ybHXzfEEu（315 帧访谈）首轮产出约 95 条但无帧引用 ⇒ 触发修复 ⇒ 二次只剩 37 条，
# 该片覆盖掉到 0.60。而 board_check 自己的注释本就写着：
#   「'模型不引用'可能正因为那些帧确实支撑不了那条断言，逼它引用等于让它编证据。」
# ⇒ 不再因"没有帧引用"打回重试；改为**报数**（帧引用率），把"视觉有没有进证据链"留在台面上。
FRAME_REF_HARD_REQUIREMENT = False

DEFAULT_MODEL = "deepseek-flash"
MAX_FRAMES_PER_CHUNK = 60
MAX_RETRIES = 2


def _load_env() -> None:
    """薄转发到 `constants.load_env`——**实现只有一份**（此前 tracing 看不到它，见该函数注释）。"""
    from .constants import load_env

    load_env()


@functools.lru_cache(maxsize=1)
def _client():
    """**全部模型调用的单一咽喉。**

    10 个调用点（contract / extract×2 / l3_verify / blueprint / draft /
    speakers / verify_l1 / ALCE 判定 / baseline）全都取这里，
    `speakers._client()` 是它的薄转发。所以计量与追踪只在这一处包一层即全覆盖——
    在 `call_with_repair` 里挂会漏掉那 4 个裸调用点。

    `lru_cache`：此前每片都新建一个 OpenAI 客户端（各带一个连接池）。
    客户端本身线程安全且可复用，缓存掉是纯收益。

    打点关闭时 `tracing.wrap` **原样返回**，零开销、零行为差异。
    """
    apply_ssl_shim()
    from openai import OpenAI

    from . import tracing

    _load_env()
    raw = OpenAI(api_key=os.environ["DEEPSEEK_API_KEY"],
                 base_url=os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com"))
    return tracing.wrap(raw, provider="deepseek")


def _parse_json(text: str) -> dict:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        parts = cleaned.split("```")
        cleaned = parts[1] if len(parts) > 1 else cleaned
        if cleaned.startswith("json"):
            cleaned = cleaned[4:]
    cleaned = cleaned.strip()
    if not cleaned.startswith("{"):
        m = re.search(r"\{.*\}", cleaned, re.S)
        if m:
            cleaned = m.group(0)
    return json.loads(cleaned)


def call_model(client, model: str, user: str, frames_available: bool = False,
               frame_windows: dict | None = None):
    """走结构化产出兜底链（P0-1）：schema 校验 → repair → nudge → escalate。

    `frame_windows`：帧时间窗（只含带文字的帧）。给了它，board_check 就会
    **按断言**要求「时间窗内有带字帧的断言必须引用帧」——实测帧引用率只有 7–54%，
    而理论可引用率近 100%，说明视觉线索没进证据链，必须变成可判定约束。

    返回 (parsed|None, 原始文本, 耗时, 错误, outcome)。
    """
    import functools

    check = functools.partial(board_check, frames_available=frames_available)
    out = call_with_repair(client, model, SYSTEM, user, check,
                           stage="l1_extract", version=PROMPT_VERSION)
    err = None if out.ok else out.note()
    return out.data, out.raw_final, out.elapsed_s, err, out


def frames_for_chunk(corpus: dict, chunk: dict) -> list[dict]:
    """给分片挑帧：优先代表帧，其次其余帧；时间落在分片窗口内。"""
    lo, hi = chunk["first_ms"], chunk["last_ms"]
    in_window = [f for f in (corpus.get("frames") or {}).values() if lo <= f["t_ms"] <= hi]
    in_window.sort(key=lambda f: f["t_ms"])
    reps = [f for f in in_window if f.get("is_representative")]
    others = [f for f in in_window if not f.get("is_representative")]
    return (reps + others)[:MAX_FRAMES_PER_CHUNK]


def board_check_units(data: dict, allowed_units: set[str],
                      frames_available: bool = False,
                      frame_windows: dict | None = None) -> list[str]:
    """单元制抽取的 schema（v5）：断言的证据是 `unit_ids`，不是模型写的 `quote`。

    检查项与 v4 的 board_check 同构，但"引文必填"换成了"证据单元必填且必须属于本片 owned"——
    **可判定性更强**：v4 要逐字比对引文，v5 只需查 id 是否在允许集合里。
    """
    errs: list[str] = []
    if not isinstance(data.get("assertions"), list):
        return ["缺少 assertions 数组"]
    if not data["assertions"]:
        errs.append("assertions 为空数组")
    if frames_available and FRAME_REF_HARD_REQUIREMENT:
        refs = sum(len(a.get("frame_refs") or []) for a in data["assertions"] if isinstance(a, dict))
        if refs == 0:
            errs.append("本片提供了帧与帧文字，但没有一条断言引用 frame_refs（要求至少 1 处）")
    for i, a in enumerate(data["assertions"][:200]):
        if not isinstance(a, dict):
            errs.append(f"assertions[{i}] 不是对象")
            continue
        if not (a.get("text") or "").strip():
            errs.append(f"assertions[{i}] 缺 text")
        uids = a.get("unit_ids")
        if not isinstance(uids, list) or not uids:
            errs.append(f"assertions[{i}] 缺 unit_ids 或为空（证据单元必填）")
        else:
            bad = [u for u in uids if u not in allowed_units]
            if bad:
                errs.append(f"assertions[{i}] 引用了不存在的单元 id：{bad[:3]}")
        if a.get("kind") not in ASSERT_KINDS:
            errs.append(f"assertions[{i}] kind 必须是 {ASSERT_KINDS} 之一")
        if a.get("status") not in ASSERT_STATUS:
            errs.append(f"assertions[{i}] status 必须是 {ASSERT_STATUS} 之一")
        if a.get("status") == "bounded" and not (a.get("boundary") or "").strip():
            errs.append(f"assertions[{i}] status=bounded 时必须填 boundary（写清条件）")
        # frame_refs 的元素类型必须查：实测模型会返回 [{"frame_id": "..."}] 这类对象数组，
        # 它能通过"是不是数组"的检查，然后在校验器的 frames.get(fid) 处炸成
        # `TypeError: unhashable type: 'dict'`（BV1ybHXzfEEu 就是这样崩的，216 条断言全丢）。
        fr = a.get("frame_refs")
        if fr is not None and not isinstance(fr, list):
            errs.append(f"assertions[{i}] frame_refs 必须是数组")
        # 元素形状**不判失败**：对象形状会在 coerce_frame_refs 里被无损取出 id。
        # 判失败会让整片重生成，代价是产出被削（实测 seg3：38 条），而那与断言质量无关。
    for j, r in enumerate(data.get("relations") or []):
        if not isinstance(r, dict):
            errs.append(f"relations[{j}] 不是对象"); continue
        if r.get("rel_type") not in REL_TYPES:
            errs.append(f"relations[{j}] rel_type 不在词表内：{r.get('rel_type')}")
        for k in ("from_local", "to_local"):
            v = r.get(k)
            if not isinstance(v, int) or not (0 <= v < len(data["assertions"])):
                errs.append(f"relations[{j}] {k} 下标越界：{v}")
    return errs


def coerce_frame_refs(refs) -> tuple[list[str], int]:
    """把 frame_refs 规范成字符串列表，**尽量挽救而不是重跑**。

    实测模型会写成 `[{"frame": "00011_000345000", "t": 345000}]`。这**不是断言错了**——
    断言本身完好，只是帧引用的形状不对。之前的做法是让 schema 检查判失败 ⇒ 整片重生成
    ⇒ 产出被削（`BV1qoHe6mEx6/seg3`：38 条）。按"保证输出"的原则，这里**无损取出 id**，
    取不出来的才丢，并返回丢弃数（不静默）。
    """
    if not isinstance(refs, list):
        return [], 0
    out, dropped = [], 0
    for r in refs:
        if isinstance(r, str):
            out.append(r)
            continue
        if isinstance(r, dict):
            got = next((v for k, v in r.items()
                        if k in ("frame", "frame_id", "fid", "id") and isinstance(v, str)), None)
            if got:
                out.append(got)
            else:
                dropped += 1
            continue
        dropped += 1
    # 去重、保序
    seen, uniq = set(), []
    for x in out:
        if x not in seen:
            seen.add(x); uniq.append(x)
    return uniq, dropped


def _uid_sort_key(uid: str) -> tuple[str, int]:
    sid, _, idx = uid.rpartition("-u")
    try:
        return (sid, int(idx))
    except ValueError:
        return (uid, 0)


def extract_chunk_units(client, corpus: dict, units_by_id: dict, chunk: dict,
                        model: str) -> dict:
    """单元制抽取（v5）：模型挑 `unit_ids`，**证据文本（quote）由代码拼接**。

    这是 I1 的落地点：模型无论如何都写不出 `quote`，因为它没有这个字段可写。
    于是"引文是不是逐字"这个问题**从"比对字符串"变成"指针是否存在"**——整类问题消失。
    """
    frame_table = frames_for_chunk(corpus, chunk)
    has_frame_text = any(f.get("text") for f in frame_table)
    fw = {f["fid"]: (int(f["t_ms"]), int(f["t_ms"]), (f.get("text") or "")[:40])
          for f in frame_table if f.get("text")}
    user = render_user_units(corpus, chunk, frame_table, units_by_id)
    allowed_units = set(chunk["owned"]) | set(chunk.get("context") or [])
    check = functools.partial(board_check_units, allowed_units=allowed_units,
                              frames_available=has_frame_text, frame_windows=fw)
    out = call_with_repair(client, model, SYSTEM_UNITS, user, check,
                           stage="l1_extract_units", version=PROMPT_VERSION_UNITS)
    err = None if out.ok else out.note()
    rec = {"chunk_id": chunk["chunk_id"], "elapsed_s": out.elapsed_s, "raw": out.raw_final,
           "error": err, "model": model, "prompt_version": PROMPT_VERSION_UNITS,
           "attempts": out.attempts, "escalated": out.escalated}
    if out.data is None:
        return {"record": rec, "assertions": [], "relations": [],
                "status": {"ok": False, "escalated": True, "note": out.note()}}

    ts = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    owned = set(chunk["owned"])
    assertions, local_to_global, dropped = [], {}, []
    frame_ref_dropped = 0
    for i, a in enumerate(out.data.get("assertions") or []):
        aid = f"{chunk['chunk_id']}-a{i:03d}"
        local_to_global[i] = aid
        # 只接受 owned 的单元（ctx 只能用于理解，不能当证据）；按时间排序，保证 quote 可复算
        uids = sorted({u for u in (a.get("unit_ids") or []) if u in owned}, key=_uid_sort_key)
        if not uids:
            dropped.append({"local_index": i, "reason": "没有可用的 owned 单元",
                            "raw_unit_ids": a.get("unit_ids")})
            continue
        _fr, _fr_dropped = coerce_frame_refs(a.get("frame_refs"))
        if _fr_dropped:
            frame_ref_dropped += _fr_dropped
        us = [units_by_id[u] for u in uids]
        anchors = [{"unit_id": u["unit_id"], "sid": u["sid"],
                    "start_ms": (u.get("t") or [None, None])[0],
                    "end_ms": (u.get("t") or [None, None])[1],
                    "precision": "unit"} for u in us]
        item = {
            "id": aid, "chunk_id": chunk["chunk_id"],
            "text": (a.get("text") or "").strip(),
            "unit_ids": uids,
            "anchors": anchors,
            # ↓↓↓ 派生字段：**不是模型写的**
            "quote": "".join(u.get("raw") or "" for u in us),
            "quote_source": "derived:units",
            "kind": a.get("kind"), "status": a.get("status"),
            "boundary": a.get("boundary"),
            # 帧引用规范化：对象形状无损取 id；取不出来的丢弃并计数（见 coerce_frame_refs）
            "frame_refs": _fr, 
            "corrections": a.get("corrections") or [],
            "produced_by": {"model": model, "prompt_version": PROMPT_VERSION_UNITS, "produced_at": ts},
        }
        assertions.append(item)

    relations = []
    for j, r in enumerate(out.data.get("relations") or []):
        rel_type = r.get("rel_type")
        f_id, t_id = local_to_global.get(r.get("from_local")), local_to_global.get(r.get("to_local"))
        kept = {a["id"] for a in assertions}
        if rel_type not in REL_TYPES or f_id not in kept or t_id not in kept:
            relations.append({"id": f"{chunk['chunk_id']}-r{j:03d}", "invalid": True,
                              "reason": f"关系非法或端点被丢弃：{rel_type} {f_id}->{t_id}",
                              "raw": r, "chunk_id": chunk["chunk_id"]})
            continue
        relations.append({"id": f"{chunk['chunk_id']}-r{j:03d}", "chunk_id": chunk["chunk_id"],
                          "from_id": f_id, "to_id": t_id, "rel_type": rel_type,
                          "link_kind": "within_chunk",
                          "produced_by": {"model": model, "prompt_version": PROMPT_VERSION_UNITS,
                                          "produced_at": ts}})

    status = {"ok": True, "escalated": out.escalated, "repairs": max(0, len(out.attempts) - 1),
              "assertions": len(assertions), "relations": len(relations),
              "dropped_no_owned_unit": len(dropped),
              "frame_ref_dropped": frame_ref_dropped}
    return {"record": rec, "assertions": assertions, "relations": relations,
            "status": status, "dropped": dropped}


def extract_chunk_to(chunk: dict, corpus: dict, model: str, out_path: Path,
                     client=None) -> dict:
    """把单个分片的抽取结果落成独立产物（供执行器逐片续跑）。

    幂等：产物已存在则直接读回，不重新调用模型。
    """
    if out_path.exists():
        return json.loads(out_path.read_text(encoding="utf-8"))
    own_client = client or _client()
    r = extract_chunk(own_client, corpus, chunk, model, prev_tail_ids=[])
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(r, ensure_ascii=False, indent=2), encoding="utf-8")
    return r


def extract_chunk(client, corpus: dict, chunk: dict, model: str,
                  prev_tail_ids: list[str]) -> dict:
    frame_table = frames_for_chunk(corpus, chunk)
    has_frame_text = any(f.get("text") for f in frame_table)
    # 帧时间窗（只算**带文字的帧**——没文字的帧引用它没有意义）
    fw = {f["fid"]: (int(f["t_ms"]), int(f["t_ms"]), (f.get("text") or "")[:40])
          for f in frame_table if f.get("text")}
    user = render_user(corpus, chunk, frame_table)
    parsed, raw, elapsed, err, outcome = call_model(client, model, user,
                                                    frames_available=has_frame_text,
                                                    frame_windows=fw)
    rec = {"chunk_id": chunk["chunk_id"], "elapsed_s": elapsed, "raw": raw,
           "error": err, "model": model, "prompt_version": PROMPT_VERSION,
           "attempts": outcome.attempts, "escalated": outcome.escalated}
    if parsed is None:
        # 显式记账：这一片没产出，不允许静默当作"抽不到东西"
        return {"record": rec, "assertions": [], "relations": [],
                "status": {"ok": False, "escalated": True, "note": outcome.note()}}

    ts = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    assertions: list[dict] = []
    local_to_global: dict[int, str] = {}
    for i, a in enumerate(parsed.get("assertions") or []):
        aid = f"{chunk['chunk_id']}-a{i:03d}"
        local_to_global[i] = aid
        item = {
            "id": aid,
            "chunk_id": chunk["chunk_id"],
            "text": (a.get("text") or "").strip(),
            "anchors": a.get("anchors") or [],
            "frame_refs": a.get("frame_refs") or [],
            "quote": a.get("quote"),
            "boundary": a.get("boundary") or {},
            "produced_by": {"model": model, "prompt_version": PROMPT_VERSION, "produced_at": ts},
        }
        # 锚点精化：句级 → 字级（用 quote 在字级词表里定位，失败则保留句级并标原因）
        enrich_assertion_anchors(item, corpus)
        assertions.append(item)

    relations: list[dict] = []
    for j, r in enumerate(parsed.get("relations") or []):
        rel_type = r.get("rel_type")
        if rel_type not in REL_TYPES:
            relations.append({"id": f"{chunk['chunk_id']}-r{j:03d}", "invalid": True,
                              "reason": f"关系类型不在词表内: {rel_type}", "raw": r,
                              "chunk_id": chunk["chunk_id"]})
            continue
        f_idx, t_idx = r.get("from_local"), r.get("to_local")
        f_id, t_id = local_to_global.get(f_idx), local_to_global.get(t_idx)
        if f_id is None or t_id is None:
            relations.append({"id": f"{chunk['chunk_id']}-r{j:03d}", "invalid": True,
                              "reason": "关系端点下标越界", "raw": r, "chunk_id": chunk["chunk_id"]})
            continue
        relations.append({
            "id": f"{chunk['chunk_id']}-r{j:03d}",
            "chunk_id": chunk["chunk_id"],
            "from_id": f_id, "to_id": t_id, "rel_type": rel_type,
            "link_kind": "within_chunk",
            "produced_by": {"model": model, "prompt_version": PROMPT_VERSION, "produced_at": ts},
        })

    status = {"ok": True, "escalated": outcome.escalated,
              "repairs": max(0, len(outcome.attempts) - 1),
              "assertions": len(assertions), "relations": len(relations)}
    return {"record": rec, "assertions": assertions, "relations": relations, "status": status}
