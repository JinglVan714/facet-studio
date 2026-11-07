"""层 1 · Verifier：干净上下文复核（P0-3）。

与 Validator 的分工（这是本项目的刻意设计）：
- **Validator = 规则**：能机械判定的（锚点合法性、覆盖、冲突、重复、引文命中）——便宜、可复现、无争议；
- **Verifier = 模型，但换干净的上下文**：判断「断言是否真被它的锚点支撑」——这件事规则判不了，
  只能在**看不到抽取过程**的上下文里做（Cognition 的做法：验证要在无污染上下文里进行，见 research/09）。

硬纪律：
- **有界**：抽样 N 条（默认 12），token 与时间都可控；
- **只出报告，不改断言**：Verifier 没有写权限——避免「自己改自己」的循环；
- **未支撑的必须落到报告里**，供人复核，不允许静默丢弃或静默采纳。
"""
from __future__ import annotations

import json
import random
import time
from pathlib import Path

from .audio import apply_ssl_shim
from .constants import DATA_DIR
from .corpus import load_corpus
from .extract_l1 import _client
from .tracing import trace_stage

#: 提示词版本：进 generation 的 `version` 字段，回答「这条 trace 是哪版提示词产出的」。
#: 改提示词/校验口径必须升它（与 `prompts_l1.PROMPT_VERSION` 同一纪律）。
VERIFY_L1_VERSION = "l1_verify/v1"

SYSTEM_VERIFIER = """你是一个**独立复核员**。你只会看到：一条断言，以及它所依据的原文片段。

你的任务：判断这条断言是否**被给定原文充分支撑**。
- 只依据给你的原文判断，不要使用你的背景知识，也不要推测视频里"大概"还说了什么；
- 断言可以是对原文的压缩或改写，但**不能包含原文没有的信息**；
- 如果断言引用了原文之外的数字、名字、因果关系，判 NOT_SUPPORTED；
- 如果原文足以支撑断言的主要意思，判 SUPPORTED（细节措辞不同不算问题）。

只输出严格 JSON：{"verdict": "SUPPORTED" | "NOT_SUPPORTED", "reason": "一句话（不超过 40 字）"}
"""


def _build_items(corpus: dict, assertions: list[dict]) -> list[dict]:
    items = []
    for a in assertions:
        sids = [x.get("sid") for x in (a.get("anchors") or []) if x.get("sid") in corpus["sentences"]]
        if not sids:
            continue
        src = "\n".join(corpus["sentences"][s]["text"] for s in sids)
        items.append({"id": a["id"], "text": a.get("text") or "",
                      "quote": a.get("quote") or "", "source": src,
                      "anchors": [{"sid": s, "start_ms": corpus["sentences"][s]["start_ms"],
                                   "end_ms": corpus["sentences"][s]["end_ms"]} for s in sids]})
    return items


def verify_sample(video_id: str, sample_size: int = 12, model: str = "deepseek-flash",
                  assertions_file: str = "assertions.jsonl", seed: int = 7) -> dict:
    apply_ssl_shim()
    corpus = load_corpus(video_id)
    path = DATA_DIR / video_id / "substrate" / assertions_file
    if not path.exists():
        raise FileNotFoundError(path)
    assertions = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
    items = _build_items(corpus, assertions)
    if not items:
        raise RuntimeError("没有可复核的断言（缺锚点）")

    rng = random.Random(seed)
    sample = rng.sample(items, min(sample_size, len(items)))
    client = _client()

    results = []
    for it in sample:
        user = (f"断言：{it['text']}\n\n"
                f"它所依据的原文：\n{it['source']}\n\n"
                f"（抽取者从原文里摘出的片段，供参考：{it['quote'][:120]}）\n\n"
                f"请判断并只输出 JSON。")
        t0 = time.time()
        try:
            with trace_stage("l1_verify", version=VERIFY_L1_VERSION):
                resp = client.chat.completions.create(
                    model=model,
                    messages=[{"role": "system", "content": SYSTEM_VERIFIER},
                              {"role": "user", "content": user}],
                    response_format={"type": "json_object"}, temperature=0)
            raw = resp.choices[0].message.content or "{}"
            data = json.loads(raw)
            verdict = str(data.get("verdict", "")).upper()
            ok = verdict in {"SUPPORTED", "NOT_SUPPORTED"}
            results.append({
                "assertion_id": it["id"], "text": it["text"][:80],
                "anchor_sids": [x["sid"] for x in it["anchors"]],
                "verdict": verdict if ok else "UNPARSED",
                "reason": str(data.get("reason", ""))[:120] if ok else raw[:120],
                "elapsed_s": round(time.time() - t0, 2),
            })
        except Exception as e:  # noqa: BLE001
            results.append({"assertion_id": it["id"], "verdict": "ERROR",
                            "reason": f"{type(e).__name__}: {e}"[:120],
                            "elapsed_s": round(time.time() - t0, 2)})

    supported = sum(1 for r in results if r["verdict"] == "SUPPORTED")
    not_supported = [r for r in results if r["verdict"] == "NOT_SUPPORTED"]
    report = {
        "video_id": video_id,
        "verifier": {"model": model, "sample_size": len(sample), "seed": seed,
                     "context": "干净上下文：只看断言 + 锚点原文，看不到抽取过程",
                     "writes": "无（只出报告，不改断言）", "assertions_file": assertions_file},
        "total_assertions": len(assertions),
        "supported": supported,
        "not_supported_count": len(not_supported),
        "unparsed_or_error": sum(1 for r in results if r["verdict"] in {"UNPARSED", "ERROR"}),
        "support_rate": round(supported / max(1, len(results)), 4),
        "not_supported_examples": not_supported[:8],
        "results": results,
    }
    out = DATA_DIR / video_id / "substrate" / "verify_report.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report
