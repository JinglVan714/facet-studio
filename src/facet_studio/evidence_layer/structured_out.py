"""harness · 结构化产出兜底链（P0-1）。

问题：模型返回「能解析的 JSON」不等于「结构正确」——实测出现过缺 `rel_type` 的关系、
没有任何锚点的断言、下标越界的引用。没有兜底链时，这些会静默污染下游。

机制（来自 ZCode 源码的做法，见 docs/research/08 §4）：
    schema 校验 → repair（把校验错误回给模型，只让它修结构）→ nudge（提醒格式再试一次）
    → escalate（放弃并用**显式的诚实尾注**标记，绝不静默通过）

硬纪律（对应 PROJECT-BRIEF 硬约束 3「不接受无限校正」）：
- **有界**：每次调用最多 1 repair + 1 nudge，之后一律 escalate；
- **不静默**：每次尝试都记录（尝试序号、错误、耗时、原始响应）；
- **可核对**：escalate 的产物带着失败原因进入报告，而不是消失在日志里。
"""
from __future__ import annotations

import json
import time
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass, field
from typing import Any, Callable

MAX_REPAIR = 1
MAX_NUDGE = 1

DEFAULT_REPAIR_INSTRUCTION = (
    "修复要求（**只动报错涉及的地方，其余内容逐字保留**）：\n"
    "1) **不得删除已有字段**：特别是每条断言的 `quote`（必填）与 `frame_refs`；\n"
    "2) 缺字段就补上（缺 quote 必须逐字回填原文片段；缺 frame_refs 就补该断言时间窗内的帧 ID）；\n"
    "3) 不要新增、删除或改写断言的语义内容，也不要改锚点的时间戳；\n"
    "4) 只输出修正后的完整 JSON。"
)

PROJECTION_REPAIR_INSTRUCTION = (
    "修复要求（**只动报错涉及的地方，其余内容逐字保留**）：\n"
    "1) 不要新增 `quote`、`raw`、`unit_ids`、`anchors`、`sid`、时间等证据坐标字段；\n"
    "2) 缺字段就补上；`kind` 必填，`evidence=gloss` 时 `kind` 不能是 `fact` 且必须给 `gloss_reason`；\n"
    "3) 不要新增、删除或改写正文的语义内容；`assertion_ids` 只能来自给定的 writer_content；\n"
    "4) 只输出修正后的完整 JSON。"
)


@contextmanager
def _stage_ctx(stage: str, attempt: int, version: str = ""):
    """惰性取 tracing——`structured_out` 是纯逻辑模块，不该在导入期就拉起追踪依赖。

    打点是**旁路**：这一段自身出任何问题都退化成空上下文，绝不影响兜底链。
    注意不能写成 `try: with ...: yield / except: yield`——那样业务异常会被
    这个 `except` 吞掉再 yield 一次，触发 "generator didn't stop"。
    """
    ctx = None
    try:
        from .tracing import trace_attempt, trace_stage

        ctx = ExitStack()
        ctx.enter_context(trace_stage(stage, version=version))
        ctx.enter_context(trace_attempt(attempt))
    except Exception:  # noqa: BLE001
        ctx = None
    if ctx is None:
        yield
        return
    with ctx:
        yield


@dataclass
class Outcome:
    data: dict | None
    ok: bool
    attempts: list[dict] = field(default_factory=list)
    escalated: bool = False
    raw_final: str = ""
    elapsed_s: float = 0.0

    def note(self) -> str:
        """给下游的诚实尾注：模型这次到底交出了什么。"""
        if self.ok:
            return f"ok（尝试 {len(self.attempts)} 次）"
        return (f"ESCALATED：{len(self.attempts)} 次尝试后仍未产出合法结构；"
                f"最后一次错误：{self.attempts[-1].get('error') if self.attempts else '未知'}")


def _validate_shape(data: Any, schema_check: Callable[[Any], list[str]]) -> list[str]:
    if not isinstance(data, dict):
        return [f"顶层类型应为 object，实际 {type(data).__name__}"]
    try:
        return schema_check(data)
    except Exception as e:  # noqa: BLE001
        return [f"schema 检查自身异常：{type(e).__name__}: {e}"]


def call_with_repair(client, model: str, system: str, user: str,
                     schema_check: Callable[[Any], list[str]],
                     stage: str = "", version: str = "",
                     max_tokens: int | None = None,
                     repair_instruction: str | None = None,
                     capture_raw: bool = False,
                     raw_limit: int = 20000) -> Outcome:
    """调用模型并用兜底链保证结构；绝不静默通过非法产物。

    `stage` 是**计量标签**（`l1_extract_units` / `l1_contract` / `l3_verify` / …）：
    它随 `tracing.trace_stage` 进入上下文，被 `tracing` 记进每次调用。
    `repaired`/`nudge` 的重试也会带上尝试序号——**重试次数是要计入成本的**，
    而以前它只体现在次数字段的目录里，不在任何成本视图里。

    `repair_instruction`：证据层与投影层的修复文案不同。默认保留证据层文案
    （含 quote/frame 补全）；投影层必须传 `PROJECTION_REPAIR_INSTRUCTION` 或自己的文案，
    否则会诱导模型补 quote，违反 D2/denylist。

    `max_tokens`：可选输出上限；`None` 时不传，保持旧行为。

    `capture_raw`：把每次尝试的原始响应写进 `attempts[*]["raw"]`（截断到 `raw_limit`），
    供 D5 的“原始响应/错误必须落盘”。默认 False，保持证据层旧行为。
    """
    out = Outcome(data=None, ok=False)
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    t_all = time.time()
    tries = 0
    budget = 1 + MAX_REPAIR + MAX_NUDGE

    while tries < budget:
        tries += 1
        t0 = time.time()
        rec: dict = {"try": tries, "phase": "initial" if tries == 1 else ("repair" if tries <= 1 + MAX_REPAIR else "nudge")}
        try:
            with _stage_ctx(stage or "unknown", tries, version):
                kwargs = {"model": model, "messages": messages,
                          "response_format": {"type": "json_object"}, "temperature": 0}
                if max_tokens is not None:
                    kwargs["max_tokens"] = max_tokens
                resp = client.chat.completions.create(**kwargs)
            raw = resp.choices[0].message.content or ""
            rec["raw_chars"] = len(raw)
            if capture_raw:
                rec["raw"] = raw[:raw_limit]
                rec["raw_truncated"] = len(raw) > raw_limit
        except Exception as e:  # noqa: BLE001
            rec.update(elapsed_s=round(time.time() - t0, 2), error=f"调用失败：{type(e).__name__}: {e}")
            out.attempts.append(rec)
            continue

        try:
            data = _parse_json(raw)
        except Exception as e:  # noqa: BLE001
            data = None
            rec.update(elapsed_s=round(time.time() - t0, 2), error=f"JSON 解析失败：{type(e).__name__}: {e}")
            out.attempts.append(rec)
            messages = _repair_messages(messages, raw, f"输出不是合法 JSON：{e}",
                                        repair_instruction)
            continue

        errs = _validate_shape(data, schema_check)
        rec.update(elapsed_s=round(time.time() - t0, 2), error="; ".join(errs)[:400] if errs else None)
        out.attempts.append(rec)
        if not errs:
            out.data, out.ok, out.raw_final = data, True, raw
            break
        # 带着校验错误要求模型只修结构（不是重新做任务）
        messages = _repair_messages(messages, raw, "；".join(errs[:6]),
                                    repair_instruction)

    if not out.ok:
        out.escalated = True
    out.elapsed_s = round(time.time() - t_all, 2)
    return out


def _repair_messages(messages: list[dict], raw: str, errors: str,
                     repair_instruction: str | None = None) -> list[dict]:
    """把「你的输出哪里不合规」回给模型，并要求只修结构、不要改动语义内容。

    `repair_instruction` 为空时使用证据层默认文案；投影层必须显式传自己的文案，
    避免出现“缺 quote 必须逐字回填”这类违反 D2 的指令。
    """
    instruction = repair_instruction or DEFAULT_REPAIR_INSTRUCTION
    return messages + [
        {"role": "assistant", "content": raw[:6000]},
        {"role": "user", "content":
            f"你的上一条输出不合规，校验器报错如下：\n{errors}\n\n{instruction}"},
    ]


def _parse_json(text: str) -> Any:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        parts = cleaned.split("```")
        cleaned = parts[1] if len(parts) > 1 else cleaned
        if cleaned.startswith("json"):
            cleaned = cleaned[4:]
    cleaned = cleaned.strip()
    if not cleaned.startswith("{"):
        import re
        m = re.search(r"\{.*\}", cleaned, re.S)
        if m:
            cleaned = m.group(0)
    return json.loads(cleaned)


# ---------------------------------------------------------------- 具体 schema

def board_check(data: dict, frames_available: bool = False,
                frame_windows: dict[str, tuple[int, int, str]] | None = None) -> list[str]:
    """层 1 抽取的 schema：断言/关系必须结构合法，否则不能进入底稿。

    `frames_available=True` 时额外要求「至少一条断言引用帧」——依据：实测同一提示词
    两次运行，模型一次引用 54 次、一次 0 次（temperature=0 也不稳定），
    所以「帧是否进入证据链」不能靠模型自觉，必须变成可校验约束 + 有界修复。
    """
    errs: list[str] = []
    if "assertions" not in data or not isinstance(data["assertions"], list):
        errs.append("缺少 assertions 数组")
        return errs
    if not data["assertions"]:
        errs.append("assertions 为空数组")
    from .extract_l1 import FRAME_REF_HARD_REQUIREMENT
    if frames_available and FRAME_REF_HARD_REQUIREMENT:
        refs = sum(len(a.get("frame_refs") or []) for a in data["assertions"]
                   if isinstance(a, dict))
        if refs == 0:
            errs.append("本片提供了帧与帧文字，但没有一条断言引用 frame_refs（要求至少 1 处）")
    for i, a in enumerate(data["assertions"][:200]):
        if not isinstance(a, dict):
            errs.append(f"assertions[{i}] 不是对象")
            continue
        if not (a.get("text") or "").strip():
            errs.append(f"assertions[{i}] 缺 text")
        if not (a.get("quote") or "").strip():
            errs.append(f"assertions[{i}] 缺 quote（引文必填）")
        anchors = a.get("anchors")
        if not isinstance(anchors, list) or not anchors:
            errs.append(f"assertions[{i}] 缺 anchors 或为空")
        else:
            for j, an in enumerate(anchors):
                if not isinstance(an, dict) or not an.get("sid"):
                    errs.append(f"assertions[{i}].anchors[{j}] 缺 sid")
                elif not isinstance(an.get("start_ms"), int) or not isinstance(an.get("end_ms"), int):
                    errs.append(f"assertions[{i}].anchors[{j}] 时间戳必须是整数")
    # 注意：**不按断言强制引用帧**。实测教训——强制 130+ 条逐条补帧会让有界修复链兜不住
    # （3 次尝试后 ESCALATE，产出 0 断言），而且更重要的是：
    # 「模型不引用」可能正因为那些帧**确实支撑不了那条断言**，逼它引用等于让它编证据。
    # 正确做法：帧-断言的关联用**机器算**（见 lmind/frame_link.py），模型只做它能判定的部分。
    n = len(data["assertions"])
    rels = data.get("relations")
    if rels is None:
        errs.append("缺少 relations 数组（可为空数组）")
        return errs
    if not isinstance(rels, list):
        errs.append("relations 不是数组")
        return errs
    for k, r in enumerate(rels[:400]):
        if not isinstance(r, dict):
            errs.append(f"relations[{k}] 不是对象")
            continue
        if not r.get("rel_type"):
            errs.append(f"relations[{k}] 缺 rel_type")
        for key in ("from_local", "to_local"):
            v = r.get(key)
            if not isinstance(v, int) or not (0 <= v < n):
                errs.append(f"relations[{k}].{key} 越界或非整数")
    return errs
