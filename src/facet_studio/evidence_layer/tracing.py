"""模型调用的**计量与追踪**：本地 JSONL 是真源，Langfuse 只是其中一个视图。

## 接线位置 = 单一咽喉

全部模型调用都取 `extract_l1._client()`（`speakers._client` 是它的薄转发）。
所以只在 `_client()` 返回的对象外面包一层，就覆盖了**全部 active 调用点**——
包括**不走** `call_with_repair` 的裸调用
（`speakers` 说话人 / `verify_l1` 复核 / `standard_metrics` 的 ALCE 判定）。
在 `call_with_repair` 里挂 callback 会漏掉这些，这也是本模块不去那里挂的原因。

## 三条约束（缺一条这个模块就不该被合进来）

1. **旁路。** 没装 langfuse、没配 `LANGFUSE_*`、没网 ⇒ 管线行为与打点前**逐字节一致**。
   导入是惰性的；每个 langfuse 调用都包在 try/except 里；配了但连不上时，
   在进程启动时**一次性探测并整体关闭**（否则每次 CLI 调用都要等导出器超时）。
2. **本地留底是真源。** 每次调用先追加一行 JSONL。理由不是省事：
   Langfuse Hobby 只有 **50k units/月**（实测一轮全量重跑 ≈388 次调用 ≈776 units ≈ 64 轮），
   而本地文件免费、永久、可 grep、可进回归。**Langfuse 挂了不能影响成本可见性**——
   反过来（本地挂了只信云端）才是灾难。
3. **字段名照抄 OTel GenAI 语义约定**，换后端不用改打点代码。
   注意规范里**没有**成本字段（research/17 §2.2），所以成本走 `app.cost.usd`。

## 为什么同时留「原始 usage」

各家的 usage 字段名与口径都不同（DeepSeek 的 `prompt_cache_hit_tokens`、
OpenAI 的 `prompt_tokens_details.cached_tokens`、Anthropic 的 `cache_creation_input_tokens`），
而规范要求把缓存读写**折算进** `input_tokens`。折算一旦猜错，数字会**悄悄**偏掉。
⇒ 规范化字段与 `app.raw_usage` 一起存：报告用规范化的，核对时回原始那份。
（与 I1 同一条思路：**可核对**比"看起来对"重要。）

## 口径边界（明写，避免被当成"全都计了"）

- **计**：一切走 OpenAI 兼容 `chat.completions` 的文本调用（deepseek 端点）。
- **不计**：`frame_transcribe`（读图）与 `audio`（ASR）走第三方 MaaS 端点，
  该端点**没有公开价目**。报告里单列「未计量通道」，**不把它们当 0**。
"""
from __future__ import annotations

import json
import os
import threading
import time
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from pathlib import Path

from .constants import DATA_DIR, SETTINGS_DIR

CALLS_PATH = DATA_DIR / "_ops" / "llm_calls.jsonl"
PRICING_PATH = SETTINGS_DIR / "pricing.json"

#: 一次进程 = 一个 run_id。报告的"一轮全量重跑"就是按它分组。
RUN_ID = uuid.uuid4().hex[:12]

_TRACE_OFF = {"0", "false", "no", "off"}
_lock = threading.Lock()

_stage: ContextVar[str] = ContextVar("lmind_stage", default="unknown")
_attempt: ContextVar[int] = ContextVar("lmind_attempt", default=1)
_video: ContextVar[str] = ContextVar("lmind_video", default="")
_version: ContextVar[str] = ContextVar("lmind_version", default="")
_extra: ContextVar[dict] = ContextVar("lmind_extra", default={})
_lf_off: ContextVar[bool] = ContextVar("lmind_lf_off", default=False)

# ------------------------------------------------------------------ 开关

_lf_state: dict = {"decided": False, "client": None, "reason": ""}


def _trace_requested() -> tuple[bool, str]:
    """要不要打点。**只有显式配了 LANGFUSE_* 才开**，其余一律旁路。"""
    from .constants import load_env

    load_env()          # 凭证在仓库根的 .env 里，不是进程环境；不读就永远"未配置"
    flag = os.environ.get("LMIND_TRACE", "").strip().lower()
    if flag in _TRACE_OFF:
        return False, "LMIND_TRACE=0（显式关闭）"
    if not os.environ.get("LANGFUSE_SECRET_KEY") or not os.environ.get("LANGFUSE_PUBLIC_KEY"):
        return False, "未配置 LANGFUSE_*（打点旁路）"
    return True, ""


def _langfuse():
    """返回可用的 langfuse client，或 None。**结果在进程内只判定一次。**

    ## 为什么**不**在启动时做连通性探测

    第一版做的是「探不通就整体关闭」。实测它有两个问题：

    1. **慢网会静默关闭打点**——`auth_check()` 撞上 4 秒超时就判定"不可用"，
       而网络其实是通的。探针脚本第一次跑 enabled=True、第二次 enabled=False，
       **同样的配置、同样的机器**。这种"时有时无"比彻底坏掉更难发现。
    2. 每次 CLI 调用都要先等一次网络往返。

    改为：**配了就建，不管通不通**；导出由 langfuse 的后台导出器异步做。
    唯一的同步点是退出时的 `flush()`，那里用**有界等待**（见 `flush`）。
    真正的兜底不是"探测网络"，是**本地 JSONL 才是真源**（本模块第一条约束）——
    所以导出失败不丢数据，只损失一个视图。
    """
    if _lf_off.get():
        return None
    if _lf_state["decided"]:
        return _lf_state["client"]
    with _lock:
        if _lf_state["decided"]:
            return _lf_state["client"]
        _lf_state["decided"] = True

        want, why = _trace_requested()
        if not want:
            _lf_state["reason"] = why
            return None
        try:
            from langfuse import Langfuse  # 惰性：没装就是 ModuleNotFoundError
        except Exception as e:  # noqa: BLE001
            _lf_state["reason"] = f"langfuse 不可用：{type(e).__name__}"
            return None
        try:
            # `timeout` 是 langfuse 的官方参数（默认 20s），它同时管住 HTTP 客户端与导出。
            # **这是"断网时退出要等多久"的唯一有效旋钮**——实测（不可路由地址）：
            #   timeout=1 → 退出 5.0s ｜ 2 → 7.1s ｜ 5 → 11.1s ｜ 默认 20 → 15.2s
            # 不设它，断网时每次 CLI 调用都要多等十几秒；那让"旁路"名存实亡。
            # 实测过的三条**无效**路径（写在注释里免得再试一遍）：
            #   · `OTEL_EXPORTER_OTLP_TIMEOUT` / `OTEL_BSP_EXPORT_TIMEOUT` —— 无效，langfuse 自己设了
            #   · `atexit.unregister(rm.shutdown)` —— 摘不掉（实测回调数 6→6；
            #     注册的是 `LangfuseResourceManager.shutdown`，但 unregister 就是匹配不上）
            #   · 探测连通性再决定关不关 —— 会让打点在慢网下**时有时无**（更坏，见前文）
            c = Langfuse(timeout=float(os.environ.get("LMIND_TRACE_TIMEOUT_S", "3")))
        except Exception as e:  # noqa: BLE001
            _lf_state["reason"] = f"初始化失败：{type(e).__name__}: {e}"
            return None
        _lf_state["client"] = c
        _lf_state["reason"] = "ok（未做连通性探测；导出失败只影响视图，不影响本地记录）"
        _install_flush_hook()
        return c


def trace_status() -> dict:
    """给 `lmind trace-status` / 探针脚本看：现在到底在打点没有。"""
    c = _langfuse()
    return {"enabled": c is not None, "reason": _lf_state["reason"],
            "run_id": RUN_ID, "calls_log": str(CALLS_PATH)}


# ------------------------------------------------------------------ 阶段上下文

@contextmanager
def trace_stage(name: str, version: str = "", **extra):
    """给这一段的模型调用打上 stage 标签，并可带上**提示词/技能版本**。

    `call_with_repair` 的 `stage` 参数本来就是为此留的（此前从未被读取）；
    4 个裸调用点在各自函数里显式包一段。

    `version` 会挂到 generation 的 **`version` 字段**上——langfuse 官方最佳实践
    把它列为 generations 的属性之一（"link managed prompts to generations to see
    which version was used"）。本项目的 `skill_version`（`summary/v3`）在同一份
    spec 里**两个版本共用一个字符串**，所以光靠它分不出"改了帧校验口径前后的产物"；
    把提示词版本也一起挂上，才回答得了「这条 trace 是哪版提示词产出的」。
    """
    st = _stage.set(name or "unknown")
    ve = _version.set(version or "")
    # **合并**而不是覆盖：`call_with_repair` 的内层 `trace_stage` 会重置 stage/version，
    # 若这里覆盖 `_extra`，外层挂的 `projection_run_id` / `artifact_id` 会丢，
    # 成本就无法按 run 聚合。嵌套 stage 必须保留父级 extra。
    ex = _extra.set({**(_extra.get() or {}), **(extra or {})})
    try:
        yield
    finally:
        _stage.reset(st)
        _version.reset(ve)
        _extra.reset(ex)


@contextmanager
def trace_attempt(n: int):
    if n == 1:
        yield
        return
    tok = _attempt.set(n)
    try:
        yield
    finally:
        _attempt.reset(tok)


@contextmanager
def trace_langfuse_off():
    """在并行线程里关闭 Langfuse span，只保留本地 JSONL。

    OTel/Langfuse 的 current-context token 在 `asyncio.to_thread` 的复制上下文里
    detach 会报 "created in a different Context"。并行评审只需要本地成本记录，
    不需要云端 span；CLI 主线程的 save 视图不受影响。
    """
    tok = _lf_off.set(True)
    try:
        yield
    finally:
        _lf_off.reset(tok)


@contextmanager
def trace_run(video_id: str = "", **extra):
    """一次 CLI 调用的范围（trace 级属性）。"""
    v = _video.set(video_id or "")
    ex = _extra.set({**(extra or {})})
    try:
        yield
    finally:
        _video.reset(v)
        _extra.reset(ex)


def current_stage() -> str:
    return _stage.get()


#: observation 名字表。**名字是给评测器/仪表盘/保存的筛选项用的标识符，当 API 对待**
#: ——langfuse 官方最佳实践的原话。所以：
#: ① 用**动词开头**的主动语态（`extract-assertions` 而不是 `l1_extract_units`）；
#: ② **不放动态值**（不放模型名——官方点名 `gpt-4o` 这类命名；模型已经是独立属性；
#:    也不放重试序号、video_id 这些每次不同的东西）；
#: ③ 稳定、低基数 ⇒ 按 name 分组就是「按 stage 看 token」。
OBSERVATION_NAMES = {
    "l1_contract": "build-consistency-contract",
    "l1_extract": "extract-assertions",
    "l1_extract_units": "extract-assertions-units",
    "l1_verify": "verify-assertions",
    "speakers": "attribute-speakers",
    "alce_judge": "judge-citations",
    # 投影层（阶段 A 起预留；不改变现有 stage 的映射）
    "project_brief": "project-build-brief",
    "project_select": "project-select-evidence",
    "project_plan": "project-plan-outline",
    "project_author": "project-author-draft",
    "project_contract": "project-check-contract",
    "project_review_author": "project-review-author",
    "project_review_reader": "project-review-reader",
    "project_review_domain": "project-review-domain",
    "project_review_editorial": "project-review-editorial",
    "project_review_platform": "project-review-platform",
    "project_chief_editor": "project-merge-findings",
    "project_revision": "project-revise-draft",
    "project_review_targeted": "project-review-targeted",
    "project_final_reader": "project-final-read",
}


def observation_name(stage: str) -> str:
    return OBSERVATION_NAMES.get(stage, f"chat-{stage}" if stage else "chat")


def set_run_context(video_id: str = "", **extra) -> None:
    """给「这一次 CLI 调用」定范围，并**开一根 root span**。**只设不重置**——
    一个进程就是一条命令，没有"恢复上一个上下文"的语义。

    ## 为什么必须有 root span

    langfuse 是 OTel 后端：**没有活动父 span 时，每个 observation 会自成一个 trace**。
    不加根的话，一轮 388 次调用就是**388 条 trace**，后台看不到"一轮"这个整体——
    而验收要的正是"能在后台看到 trace（一条），且 token 分 stage 可见"。
    根 span 一开，全部 generation 挂在它下面，才是一条 trace。

    顺带用 `propagate_attributes` 把 trace 级属性一次设好：`session_id` 让
    **多轮之间能串起来**（官方口径："one trace per turn and one session per conversation"），
    `tags` / `metadata` 提供上线前就定好的切分维度。
    """
    _video.set(video_id or "")
    norm = {f"app.{k}" if not k.startswith(("app.", "gen_ai.")) else k: v
            for k, v in (extra or {}).items()}
    _extra.set(norm)
    _open_root(video_id, norm)


def _open_root(video_id: str, extra: dict) -> None:
    lf = _langfuse()
    if lf is None or _lf_state.get("root") is not None:
        return
    cmd = str(extra.get("app.cmd") or "run")
    tags = [f"cli:{cmd}"] + ([f"video:{video_id}"] if video_id else [])
    meta = {k: str(v) for k, v in extra.items() if v not in (None, "")}
    meta["app.run_id"] = RUN_ID
    # session_id = **video_id**，不是 run_id。
    # 官方口径：session 用来把「先后发生的多个工作单元」串起来——"Each step is its own
    # trace, and the session ties them together"；而"单请求应用不需要 session"。
    # 第一版把 session_id 设成 run_id，那等于**每条 session 只有一个 trace**，
    # Sessions 视图里除了一堆孤立的单 trace 什么都没有（自审时发现）。
    # 本项目的"先后单元"就是**同一条视频的一轮轮重跑** ⇒ 用 video_id，
    # Sessions 视图立刻变成"这条视频我跑过几轮、每轮什么结果"。
    # 没有 video_id 的命令（如 probe）退回 run_id，避免落到一个空 session 里。
    session = video_id or RUN_ID
    root_input = {"video_id": video_id or None, **{k: v for k, v in extra.items()}}
    try:
        root = lf.start_as_current_observation(
            name=f"lmind-{cmd}", as_type="span", input=root_input)
        root.__enter__()
        _lf_state["root"] = root
        # A context token may only be detached in the context that created it.
        # Parallel writer threads can trigger the fallback root; remember the
        # owner so a later main-thread close cannot detach across contexts.
        _lf_state["root_thread"] = threading.get_ident()
    except Exception:  # noqa: BLE001
        return
    # 兼容桥：v4 平台的 trace 顶部那个 Input/Output 框读的是 **trace 级**字段，
    # 而 v4 的推荐做法是把 I/O 放在**根 observation** 上。两者都写，才能在
    # "点开一条 trace" 和 "看列表" 两个位置都看到东西。
    # 官方标注这是 deprecated（"legacy method for backward compatibility with
    # Langfuse platform features that still rely on trace-level input/output"），
    # **属于可撤的桥**：哪天 SDK/UI 不再需要，删掉这段即可，根 observation 那份不受影响。
    try:
        lf.set_current_trace_io(input=root_input)
    except Exception:  # noqa: BLE001
        pass
    try:
        from langfuse import propagate_attributes

        pa = propagate_attributes(session_id=session, tags=tags, metadata=meta,
                                  trace_name=f"lmind {cmd}")
        pa.__enter__()
        _lf_state["pa"] = pa
    except Exception:  # noqa: BLE001
        pass


def _close_root() -> None:
    """关根 span，把这一轮的总量写进 trace 的 output。

    根 observation 的 input/output 是 trace 列表里唯一能看到的东西
    （官方："trace-level I/O derives from it"），所以别让它空着——
    空着的 trace 在后台是一行没有信息的东西，等于没打点。
    """
    owner = _lf_state.pop("root_thread", None)
    foreign = owner is not None and owner != threading.get_ident()
    for key in ("pa", "root"):
        cm = _lf_state.pop(key, None)
        if cm is None:
            continue
        if foreign:
            # The owning thread is gone; detaching here would raise
            # "created in a different Context". The local JSONL remains the
            # source of truth and the process is exiting anyway.
            continue
        try:
            if key == "root":
                lf = _lf_state.get("client")
                summary = _run_summary()
                if lf is not None and summary:
                    lf.update_current_span(output=summary, level="DEFAULT")
                    lf.set_current_trace_io(output=summary)   # 兼容桥，见 _open_root
            cm.__exit__(None, None, None)
        except Exception:  # noqa: BLE001
            pass


def _run_summary() -> dict:
    """从**本地记录**回读本轮总量——不依赖云端，也因此永远答得出来。"""
    try:
        calls = [json.loads(l) for l in CALLS_PATH.read_text(encoding="utf-8").splitlines()
                 if l.strip()]
    except Exception:  # noqa: BLE001
        return {}
    mine = [c for c in calls if c.get("app.run_id") == RUN_ID]
    if not mine:
        return {}
    by_stage: dict[str, int] = {}
    for c in mine:
        by_stage[c.get("app.stage") or "?"] = by_stage.get(c.get("app.stage") or "?", 0) + 1
    return {"calls": len(mine), "calls_by_stage": by_stage,
            "input_tokens": sum(c.get("gen_ai.usage.input_tokens") or 0 for c in mine),
            "output_tokens": sum(c.get("gen_ai.usage.output_tokens") or 0 for c in mine),
            "cost_usd": round(sum(c.get("app.cost.usd") or 0 for c in mine), 6),
            "errors": sum(1 for c in mine if c.get("error.type"))}


# ------------------------------------------------------------------ 用法归一化

def _as_dict(obj) -> dict:
    if obj is None:
        return {}
    if isinstance(obj, dict):
        return obj
    for attr in ("model_dump", "to_dict", "dict"):
        f = getattr(obj, attr, None)
        if callable(f):
            try:
                return f()
            except Exception:  # noqa: BLE001
                continue
    return {k: v for k, v in vars(obj).items()} if hasattr(obj, "__dict__") else {}


def _int_or_none(v) -> int | None:
    return int(v) if isinstance(v, (int, float)) else None


def normalize_usage(usage) -> tuple[dict, dict]:
    """把各家 usage 折成 OTel GenAI 的四元组。返回 (规范字段, 原始 dict)。

    规范要求缓存两类**都应计入** `input_tokens`（即规范里的 input = 总 prompt）。
    但各家对「总 prompt」的记账方式相反：

    | 口径 | 判别依据（**看键名，不看值**） | `input_tokens` 的含义 |
    |---|---|---|
    | Anthropic | 有 `cache_read_input_tokens` / `cache_creation_input_tokens` | **只是没命中的尾巴**，总 prompt = 三者之和 |
    | DeepSeek | 有 `prompt_cache_hit_tokens` / `prompt_cache_miss_tokens` | 已是总 prompt，另给命中/未命中拆分 |
    | OpenAI | `prompt_tokens_details.cached_tokens` | 已是总 prompt |

    **判别必须看键名是否存在，不能看值是否非零**——第一版按"`cache_creation` 是不是真值"
    分支，于是 Anthropic 那组（`cache_creation=0`）掉进了 OpenAI 分支，
    把 `input=200, cache_read=1000` 记成 input=200：总 prompt 少报了 6 倍，
    而**它不会报错**。抓出它的是 `scripts/trace_probe.py` 的本地对照。
    """
    raw = _as_dict(usage)
    if not raw:
        return {}, {}
    det = raw.get("prompt_tokens_details") or raw.get("input_tokens_details") or {}
    det = det if isinstance(det, dict) else {}

    def g(*names):
        for n in names:
            v = raw.get(n)
            if isinstance(v, (int, float)):
                return int(v)
        return None

    inp = g("prompt_tokens", "input_tokens")
    out = g("completion_tokens", "output_tokens")
    hit = g("prompt_cache_hit_tokens")
    miss = g("prompt_cache_miss_tokens")

    anthropic_style = ("cache_read_input_tokens" in raw or "cache_creation_input_tokens" in raw)
    if anthropic_style:
        cache_read = g("cache_read_input_tokens") or 0
        cache_create = g("cache_creation_input_tokens") or 0
    else:
        cache_read = g("cache_read_input_tokens", "cache_read_tokens")
        if cache_read is None:
            v = det.get("cached_tokens")
            cache_read = int(v) if isinstance(v, (int, float)) else None
        if cache_read is None:
            cache_read = hit
        cache_create = g("cache_creation_input_tokens")
        if cache_create is None:
            v = det.get("cache_write_tokens")
            cache_create = int(v) if isinstance(v, (int, float)) else None

    # 归一成「总 prompt」
    if inp is None:
        total = None
        accounting = "无 input 字段"
    elif anthropic_style:
        total = inp + (cache_read or 0) + (cache_create or 0)
        accounting = ("Anthropic 口径：input_tokens 只是未命中尾巴，"
                      "总 prompt = input + cache_read + cache_creation")
    elif hit is not None and miss is not None:
        total = inp
        accounting = "DeepSeek 口径：prompt_tokens 已含缓存读（另有 hit/miss 拆分），不重复相加"
    elif cache_read:
        total = inp
        accounting = "OpenAI 口径：prompt_tokens 已含缓存读，不重复相加"
    else:
        total = inp
        accounting = "无缓存分项；input_tokens 按上报值"

    # deepseek-flash 是**推理模型**：实测 max_tokens=32 时 32 个 output 全是
    # `reasoning_tokens`、正文为空、finish_reason=length。所以推理 token 必须单列——
    # 否则「输出很短却按 32 个 token 计费」看起来像计费错误，实际是推理花掉了。
    creason = None
    cdet = raw.get("completion_tokens_details")
    if isinstance(cdet, dict):
        v = cdet.get("reasoning_tokens")
        creason = int(v) if isinstance(v, (int, float)) else None
    if creason is None:
        creason = g("reasoning_tokens", "reasoning_output_tokens")

    norm = {
        "gen_ai.usage.input_tokens": total,
        "gen_ai.usage.output_tokens": out,
        "gen_ai.usage.cache_read.input_tokens": cache_read,
        "gen_ai.usage.cache_creation.input_tokens": cache_create,
        "gen_ai.usage.reasoning.output_tokens": creason,
    }
    return {k: v for k, v in norm.items()}, {"raw": raw, "accounting": accounting,
                                            "cache_miss_reported": miss}


# ------------------------------------------------------------------ 定价与成本

_pricing_cache: dict = {}


def pricing() -> dict:
    if not _pricing_cache:
        try:
            _pricing_cache.update(json.loads(PRICING_PATH.read_text(encoding="utf-8")))
        except Exception as e:  # noqa: BLE001
            _pricing_cache.update({"models": {}, "_error": f"{type(e).__name__}: {e}"})
    return _pricing_cache


def _is_peak(when_utc: datetime) -> bool:
    p = pricing()
    if when_utc.weekday() >= 5 and p.get("peak_weekdays_only", True):
        return False
    hm = when_utc.strftime("%H:%M")
    for lo, hi in p.get("peak_windows_utc") or []:
        if lo <= hm < hi:
            return True
    return False


def cost_usd(model: str, *, input_tokens, output_tokens, cache_read,
             cache_miss, when_utc: datetime) -> dict:
    """按定价表换算。**算不出来就返回 None，不猜。**"""
    entry = (pricing().get("models") or {}).get(model)
    if not entry:
        return {"usd": None, "pricing_version": pricing().get("pricing_version"),
                "tier": None, "basis": "unknown_model（定价表里没有这个模型）"}
    tier = "peak" if _is_peak(when_utc) else "off_peak"
    rate = entry.get(tier) or {}
    p_hit, p_miss, p_out = (rate.get("input_cache_hit"), rate.get("input_cache_miss"),
                            rate.get("output"))
    if None in (p_hit, p_miss, p_out):
        return {"usd": None, "pricing_version": pricing().get("pricing_version"),
                "tier": tier, "basis": "定价表缺该档位"}
    if cache_miss is not None:
        miss, basis = cache_miss, "exact（供应商给出了 miss 拆分）"
    elif input_tokens is not None and cache_read is not None:
        miss, basis = max(0, input_tokens - cache_read), "derived（input − cache_read）"
    elif input_tokens is not None:
        # 拿不到缓存拆分 ⇒ 全部按 miss 价算，是**上界**，必须标出来
        miss, basis = input_tokens, "upper_bound（无缓存拆分，全部按 miss 价）"
    else:
        return {"usd": None, "pricing_version": pricing().get("pricing_version"),
                "tier": tier, "basis": "无 token 数"}
    usd = (miss * p_miss + (cache_read or 0) * p_hit + (output_tokens or 0) * p_out) / 1e6
    return {"usd": round(usd, 8), "pricing_version": pricing().get("pricing_version"),
            "tier": tier, "basis": basis}


# ------------------------------------------------------------------ 本地留底

def _append(rec: dict) -> None:
    """追加一行。**写不进去也不能影响调用**（磁盘满/权限问题不该让管线挂）。"""
    try:
        CALLS_PATH.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(rec, ensure_ascii=False) + "\n"
        with _lock:
            with CALLS_PATH.open("a", encoding="utf-8") as f:
                f.write(line)
    except Exception:  # noqa: BLE001
        pass


def record(*, stage: str, model: str, provider: str, duration_ms: int,
           usage, finish_reasons=None, error: str | None = None,
           resp_chars: int | None = None, reasoning_chars: int | None = None) -> dict:
    when = datetime.now(timezone.utc)
    norm, rawinfo = normalize_usage(usage)
    # **成功与失败记录的字段集必须一样**：调用失败时 `usage=None`，归一化返回空 dict，
    # 于是那一行就少了四个 token 字段——同一份 JSONL 里两种 schema。
    # 消费方（`cost_report.py` / 外部脚本）得靠 `.get()` 兜，很容易写成
    # `r["gen_ai.usage.input_tokens"]` 然后在**只有失败记录时才崩**。
    # 实测踩到：本地自审脚本正是这么崩的。补齐成显式 `None`。
    for _k in ("gen_ai.usage.input_tokens", "gen_ai.usage.output_tokens",
               "gen_ai.usage.cache_read.input_tokens",
               "gen_ai.usage.cache_creation.input_tokens",
               "gen_ai.usage.reasoning.output_tokens"):
        norm.setdefault(_k, None)
    extra = dict(_extra.get() or {})
    c = cost_usd(model, input_tokens=norm.get("gen_ai.usage.input_tokens"),
                 output_tokens=norm.get("gen_ai.usage.output_tokens"),
                 cache_read=norm.get("gen_ai.usage.cache_read.input_tokens"),
                 cache_miss=rawinfo.get("cache_miss_reported"), when_utc=when)
    rec = {
        "ts": when.isoformat(timespec="seconds"),
        "app.run_id": RUN_ID,
        "app.video_id": _video.get() or None,
        "app.stage": stage,
        "app.attempt": _attempt.get(),
        **extra,
        "gen_ai.operation.name": "chat",
        "gen_ai.provider.name": provider,
        "gen_ai.request.model": model,
        "gen_ai.response.finish_reasons": list(finish_reasons or []),
        "duration_ms": duration_ms,
        "app.prompt_version": _version.get() or None,
        "app.response_chars": resp_chars,
        "app.reasoning_chars": reasoning_chars,
        "error.type": error,
        **norm,
        "app.usage_accounting": rawinfo.get("accounting"),
        "app.raw_usage": rawinfo.get("raw"),
        "app.cost.usd": c["usd"],
        "app.price.tier": c["tier"],
        "app.price.basis": c["basis"],
        "app.pricing_version": c["pricing_version"],
    }
    _append(rec)
    return rec


# ------------------------------------------------------------------ langfuse 视图

class _NullGen:
    def set(self, **kw) -> None:  # noqa: D102
        return None


def _usage_details(rec: dict) -> dict:
    """**只发 `input` / `output` 两个键。** 这是实测逼出来的，不是偏好。

    Langfuse 的 `totalTokens` = `usage_details` 里**所有数值字段之和**。
    第一版同时发了规范键与供应商原始字段（`input`/`output`/`prompt_tokens`/
    `completion_tokens`/`total_tokens`/`prompt_cache_hit_tokens`/…），
    于是总量被重复计了 3–4 倍，而**它不会报错**——
    远端数字看起来完全合理，只是比真值大。

    实测（五个探针，同一时间窗）：

    | 传进 usage_details | 云端 totalTokens |
    |---|---|
    | `{input:100, output:50}` | **150** ✓ |
    | `{input, output, total:150}` | **150** ✓（`total` 被当显式总量，不累加）|
    | `{input, output, input_cached_tokens:20}` | **170** ✗ 多算 20 |
    | `{input, output, input_cache_read:20}` | **170** ✗ |
    | `{input, output, input_cache_creation:20}` | **170** ✗ |

    ⇒ 缓存/推理 token **不进 usage_details**，改放 metadata + 本地 JSONL。
    宁可云端少一列，也不要云端多一个**错的**数。
    """
    ud: dict = {}
    if rec.get("gen_ai.usage.input_tokens") is not None:
        ud["input"] = rec["gen_ai.usage.input_tokens"]
    if rec.get("gen_ai.usage.output_tokens") is not None:
        ud["output"] = rec["gen_ai.usage.output_tokens"]
    return ud


def content_capture_enabled() -> bool:
    """要不要把**正文**打进 trace。默认关。

    官方最佳实践说"每个操作都应有 input/output"，但 OTel GenAI 规范明确警告
    内容捕获含 PII，Claude Code 自己的遥测也把内容级字段全部默认关（`OTEL_LOG_*`）。
    本项目照同一条口径：**默认只报结构（消息条数、字符数、finish_reason），
    正文要显式开 `LMIND_TRACE_CONTENT=1`**。结构足以回答"这次调用喂了多少东西"，
    而正文是隐私面。

    ⚠️ 这里必须自己先 `load_env()`：本项目的开关写在仓库根的 `.env` 里，
    而调用顺序不保证 `.env` 已被读过。**同一个坑犯过一次**（见 `_trace_requested`），
    症状都是"配了却静默不生效"。
    """
    from .constants import load_env

    load_env()
    return os.environ.get("LMIND_TRACE_CONTENT", "").strip().lower() not in ("", *_TRACE_OFF)


def _in_payload(kw: dict, content: bool) -> dict:
    msgs = kw.get("messages") or []
    chars = sum(len(str(m.get("content") or "")) for m in msgs
                if isinstance(m, dict))
    out = {"messages": len(msgs), "chars": chars,
           "response_format": (kw.get("response_format") or {}).get("type"),
           "temperature": kw.get("temperature"), "max_tokens": kw.get("max_tokens")}
    if content:
        out["messages_full"] = msgs
    return {k: v for k, v in out.items() if v is not None}


@contextmanager
def _lf_generation(name: str, model: str, metadata: dict, input_payload: dict,
                   version: str | None = None):
    """一个 generation observation。**任何一步失败都退化成空操作，绝不冒泡。**"""
    lf = _langfuse()
    if lf is None:
        yield _NullGen()
        return
    cm = None
    try:
        cm = lf.start_as_current_observation(name=name, as_type="generation",
                                             metadata=metadata or None, version=version,
                                             input=input_payload or None)
        cm.__enter__()
    except Exception:  # noqa: BLE001
        yield _NullGen()
        return

    class _Gen:
        def set(self, *, usage_details=None, output=None, level=None, status=None,
                cost_usd=None, meta_extra=None) -> None:
            try:
                lf.update_current_generation(
                    model=model, usage_details=usage_details or None,
                    # 成本由**我们自己的定价表**换算后上报。langfuse 内置价目表里
                    # 通常没有 deepseek-flash，不上报就会显示成 0 或空白——
                    # 那是"看着达标但粒度不对"的典型：数字没报错，但它是缺的。
                    cost_details=({"total": cost_usd} if cost_usd is not None else None),
                    output=output,
                    metadata={**(metadata or {}), **(meta_extra or {})} or None,
                    level=level, status_message=status)
            except Exception:  # noqa: BLE001
                pass

    try:
        yield _Gen()
    except BaseException as e:                      # noqa: BLE001
        try:
            cm.__exit__(type(e), e, e.__traceback__)
        except Exception:  # noqa: BLE001
            pass
        raise
    else:
        try:
            cm.__exit__(None, None, None)
        except Exception:  # noqa: BLE001
            pass


# ------------------------------------------------------------------ 客户端包装

class _TracedCompletions:
    def __init__(self, real, provider: str):
        self._real = real
        self._provider = provider

    def create(self, **kw):
        model = str(kw.get("model") or "")
        stage = current_stage()
        pver = _version.get()
        extra = dict(_extra.get() or {})
        content = content_capture_enabled()
        meta = {"app.stage": stage, "app.attempt": _attempt.get(),
                "app.prompt_version": pver or None,
                "gen_ai.operation.name": "chat",
                "gen_ai.provider.name": self._provider,
                "gen_ai.request.model": model, **extra}
        if not content:
            meta["app.content_capture"] = "off（正文未采集；LMIND_TRACE_CONTENT=1 可开）"
        # **兜底开根**：脚本/探针直接取 `_client()` 时没人调 `set_run_context`，
        # 于是没人开根 span —— 而 OTel 下没有活动父 span 的 observation
        # **每个都会自成一个 trace**。实测：探针的调用在后台变成一堆孤立的
        # `chat-unknown` 单观测 trace（自审时发现）。
        # 在这里兜住，就保证了「任何入口产生的调用都挂在一条 trace 上」。
        if _lf_state.get("root") is None and _lf_state.get("client") is not None:
            _open_root(_video.get() or "", {**extra})
        t0 = time.perf_counter()
        with _lf_generation(observation_name(stage), model, meta,
                            _in_payload(kw, content), version=pver or None) as gen:
            try:
                resp = self._real.create(**kw)
            except Exception as e:  # noqa: BLE001
                rec = record(stage=stage, model=model, provider=self._provider,
                             duration_ms=int((time.perf_counter() - t0) * 1000),
                             usage=None, error=f"{type(e).__name__}: {e}"[:300])
                gen.set(level="ERROR", status=rec["error.type"])
                raise
            dur = int((time.perf_counter() - t0) * 1000)
            usage = getattr(resp, "usage", None)
            fin, text, think = None, "", ""
            try:
                fin = [c.finish_reason for c in (resp.choices or []) if c.finish_reason]
                text = (resp.choices[0].message.content or "") if resp.choices else ""
                # **思维链**：deepseek-flash 是推理模型，正文之外还有 `reasoning_content`。
                # 官方最佳实践把它列为必采项（"You should always capture thinking on each
                # generation in the tree"）——只看正文会漏掉"它为什么这么答"。
                # 实测：回答是中文「2」，而 reasoning 是英文的推演。
                think = getattr(resp.choices[0].message, "reasoning_content", "") or ""
            except Exception:  # noqa: BLE001
                pass
            rec = record(stage=stage, model=model, provider=self._provider, duration_ms=dur,
                         usage=usage, finish_reasons=fin, resp_chars=len(text),
                         reasoning_chars=len(think))
            out = {"chars": len(text), "finish_reasons": fin,
                   "reasoning_chars": len(think)}
            if content:
                out["text"] = text
                out["reasoning"] = think        # 思维链：官方最佳实践要求必采
            gen.set(usage_details=_usage_details(rec), cost_usd=rec.get("app.cost.usd"),
                    output=out,
                    # 缓存/推理拆分走 metadata：**不能**进 usage_details（会被累加，见其注释）
                    meta_extra={
                        "gen_ai.usage.cache_read.input_tokens":
                            rec.get("gen_ai.usage.cache_read.input_tokens"),
                        "gen_ai.usage.cache_creation.input_tokens":
                            rec.get("gen_ai.usage.cache_creation.input_tokens"),
                        "gen_ai.usage.reasoning.output_tokens":
                            rec.get("gen_ai.usage.reasoning.output_tokens"),
                        "app.price.tier": rec.get("app.price.tier"),
                        "app.price.basis": rec.get("app.price.basis"),
                        "app.duration_ms": rec.get("duration_ms"),
                        "app.response_chars": rec.get("app.response_chars"),
                    })
            return resp


class _TracedChat:
    def __init__(self, real, provider: str):
        # `real` 是 openai 的 `client.chat` 命名空间，真正的调用入口是它的 `.completions`
        self.completions = _TracedCompletions(real.completions, provider)


class TracedClient:
    """`openai.OpenAI` 的**透明代理**：只拦 `chat.completions.create`，其余原样透传。"""

    def __init__(self, real, provider: str = "unknown"):
        self._real = real
        self.chat = _TracedChat(real.chat, provider)

    def __getattr__(self, item):
        return getattr(self._real, item)


def wrap(client, provider: str = "unknown"):
    """包一层；**打点关闭时原样返回**，保证零开销、零行为差异。"""
    if _langfuse() is None and not _local_only():
        return client
    try:
        return TracedClient(client, provider)
    except Exception:  # noqa: BLE001
        return client


def _local_only() -> bool:
    """即使 Langfuse 关掉，**本地 JSONL 照记**（它才是真源）。"""
    if os.environ.get("LMIND_TRACE", "").strip().lower() in _TRACE_OFF:
        return False
    return os.environ.get("LMIND_TRACE_LOCAL", "1").strip().lower() not in _TRACE_OFF


# ------------------------------------------------------------------ 收尾

_flush_installed = False


def _install_flush_hook() -> None:
    global _flush_installed
    if _flush_installed:
        return
    _flush_installed = True
    import atexit

    def _do() -> None:
        flush()

    atexit.register(_do)


def flush() -> None:
    """收尾导出。**有界等待**——这是整条链路上唯一会同步等网络的地方。

    `langfuse.flush()` 自己没有超时参数，所以在守护线程里做，最多等
    `LMIND_TRACE_FLUSH_TIMEOUT_S`（默认 5 秒）。超时就放弃这次导出：
    本地 JSONL 已经落盘，**丢的只是一个视图**。
    之后摘掉 langfuse 的 atexit 钩子，否则它会再等一次无界 flush。
    """
    c = _lf_state.get("client")
    if c is None:
        return
    _close_root()                              # 先关根 span（trace 才算完整）
    t = threading.Thread(target=_flush_now, args=(c,), daemon=True)
    t.start()
    t.join(timeout=float(os.environ.get("LMIND_TRACE_FLUSH_TIMEOUT_S", "5")))
    # 剩下那截（langfuse 自己的 atexit `shutdown`，内含无界 `force_flush`）**摘不掉**，
    # 所以真正的旋钮是上面构造时的 `timeout=`。实测的完整退出耗时见该处注释。


def _flush_now(c) -> None:
    try:
        c.flush()
    except Exception:  # noqa: BLE001
        pass
