"""证据层共享工具：底稿读取、证据基准、原子写与可复算指纹。

证据层（L0/L1/L1.5）与投影层共用同一份读取口径；投影层只读，不反向依赖其他模块。

这里只放**证据层自己的东西**：
- 断言 / 关系的读取（`assertions_reduced.jsonl` 优先）；
- 可引用证据文本的基准（默认 `quote`，见 `EVIDENCE_BASELINE`）；
- 文件指纹与原子写；
- 帧关联复用的数字 / 术语抽取正则。

**不放**产物结构归一化（`iter_units` 在 `artifact_shape.py`）与任何投影逻辑。
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from pathlib import Path

from .constants import DATA_DIR

# ── 证据基准口径 ───────────────────────────────────────────────────────────
# 一条断言有两个文本字段：`quote`（逐字原文，**证据**）与 `text`（模型改写，**表述**）。
# 可引用证据默认取 `quote`；`text` 只用于理解，不作为证据。
EVIDENCE_BASELINE = os.environ.get("LMIND_EVIDENCE_BASELINE", "quote")
EVIDENCE_BASELINES = ("quote", "text")


def assertion_evidence(a: dict, baseline: str | None = None) -> str:
    """断言的**可引用证据文本**。

    默认取 `quote`（逐字原文）。`quote` 缺失时**不回退到 `text`**——
    静默回退会让口径悄无声息地变回去；改为返回空串，由调用方计数上报。
    """
    baseline = baseline or EVIDENCE_BASELINE
    if baseline not in EVIDENCE_BASELINES:
        raise ValueError(f"未知基准 {baseline!r}，只允许 {EVIDENCE_BASELINES}")
    if baseline == "text":
        return a.get("text") or ""
    return a.get("quote") or ""


def evidence_texts(video_id: str, baseline: str | None = None) -> dict[str, str]:
    """断言 id → 可引用证据文本（校验与指标的统一入口）。"""
    return {a["id"]: assertion_evidence(a, baseline) for a in load_assertions(video_id)}


# ------------------------------------------------------------------ 底稿读取

def _assertions_path(video_id: str, reduced: bool = True) -> Path:
    sub = DATA_DIR / video_id / "substrate"
    p = sub / ("assertions_reduced.jsonl" if reduced else "assertions.jsonl")
    return p if p.exists() else sub / "assertions.jsonl"


def load_assertions(video_id: str, reduced: bool = True) -> list[dict]:
    p = _assertions_path(video_id, reduced)
    if not p.exists():
        raise FileNotFoundError(f"缺少 {p}，请先跑层 1")
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def load_relations(video_id: str) -> list[dict]:
    sub = DATA_DIR / video_id / "substrate"
    p = sub / "relations_reduced.jsonl"
    if not p.exists():
        p = sub / "relations.jsonl"
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()] if p.exists() else []


# ------------------------------------------------------------------ 指纹与原子写

def _sha256(p: Path) -> str | None:
    if not p or not p.exists():
        return None
    h = hashlib.sha256()
    with p.open("rb") as f:
        for c in iter(lambda: f.read(1 << 20), b""):
            h.update(c)
    return h.hexdigest()[:16]


def write_json_atomic(path: Path, data) -> None:  # noqa: D401
    """原子写（临时文件 + os.replace，避免半截文件）。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=path.stem, suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


# ------------------------------------------------------------------ 帧关联复用

# 数字提取：**只认"当作事实说出来的数"**，避免误伤行文里的序号。
#
# 两条口径：
# 1. **带单位**：中文量词 + 拉丁后缀（K/M/G/B/T、px/p、bit、token、参数、层、维…）。
#    带单位的数字一定是事实陈述。
# 2. **裸数字 ≥3 位**：短文里 3 位以上的裸数字基本不可能是序号或行文修辞。
#    2 位以内的裸数字不查——"三个步骤""第一点"这类会大量假阳性。
_NUMERIC = re.compile(
    r"\d+(?:\.\d+)?\s*(?:%|年|月|日|元|千|万|亿|秒|分钟|小时|度|岁|个|条|只|种|倍|层|维|页|帧"
    r"|[KkMmGgBbTt](?![a-z])|px|p(?![a-z])|bit[s]?|byte[s]?|token[s]?|参数)"
    # 版本号：`GPT-4` / `Claude-3.5` / `v2`。AI 语料里错一个版本号是硬伤，
    # 且这个模式**不会**误伤 `vLLM` / `wav2vec` / `bilibili`（要带连字符或纯 v+数字）。
    r"|[A-Za-z]{2,}-\d+(?:\.\d+)?|\bv\d+(?:\.\d+)?\b"
    r"|\b\d{3,}\b")

_TERM = re.compile(r"[“\"]([^”\"]{2,12})[”\"]")
