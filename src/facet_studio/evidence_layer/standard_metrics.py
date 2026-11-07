"""公认指标实现（对齐公开口径，不自造定义）。

为什么单独一个模块：**主指标必须是公开定义的**，这样结果能被外部核对、面试能讲清出处。
自定义诊断（如单源句占比）不在这里；新投影层接入后由新的诊断模块负责，并在报告里标为自定义。

已实现（口径与出处见 `docs/research/22-standard-eval-metrics.md`）：
- `citation_recall_alce`  — ALCE 的 citation recall（Gao et al., EMNLP 2023, arXiv:2305.14627）
    断言级 0/1：**至少有一条引用** 且 **所有被引片段拼接后整体蕴含该断言**；对全部断言取平均；
    无引用的断言记 0（"its citation recall is 1 iff there is at least one citation"）。
- `anchor_grounding`      — 时间锚点的区间定位质量：R@1@IoU0.5 与 mIoU
    （TALL arXiv:1705.05524 / Hendricks arXiv:1708.01641；Charades-STA 惯例 R@1/R@5@{0.5,0.7}）
- `agreement_kappa`       — 标注一致性 Cohen's κ 与解释档位（Landis & Koch；Krippendorff α 惯例）

**判定器声明（硬性）**：ALCE 口径要求公开判定器。我们不使用 ALCE 的 TRUE-NLI(T5-11B)，
而是用 `deepseek-flash` 做蕴含判定（零样本），并在报告中写明——
LongCite 换判定器导致 κ 从 0.247/0.146 提升到 0.544/0.655，**判定器是结果的一部分，不能省略**。
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from .constants import DATA_DIR
from .evidence import EVIDENCE_BASELINE
from .tracing import trace_stage

#: ALCE 判定用的提示词版（本项不是 ALCE 官方 TRUE-NLI，判定器与提示词随报告一并公开）。
ALCE_JUDGE_VERSION = "alce_judge/v1"

JUDGE_MODEL_DEFAULT = "deepseek-flash"
ALCE_JUDGE_NOTE = ("judge=deepseek-flash（零样本蕴含判定）；非 ALCE 官方 TRUE-NLI(T5-11B)，"
                   "故本项为『ALCE 口径、自选判定器』，判定器与提示词随报告一并公开")

ENTAIL_SYSTEM = """你在做**引用蕴含判定**（citation entailment），这是 ALCE 引用评测的核心动作。

给你一条断言，以及它引用的若干片段（拼接在一起）。判断：**这些片段能否推出这条断言**。

要点：
- 只依据片段内容判断，不要用你的背景知识；片段的措辞与断言不同不算问题；
- 若断言包含片段里没有的信息（数字、专名、因果、评价、外推），判 NO；
- 若片段足以支撑断言的主要意思，判 YES。

只输出严格 JSON：{"entailed": true 或 false, "reason": "一句话，不超过 30 字"}
"""


# ---------------------------------------------------------------- ALCE citation recall

def citation_recall_alce(video_id: str, artifact_path: Path, *,
                         model: str = JUDGE_MODEL_DEFAULT,
                         sample: int | None = None, seed: int = 5) -> dict:
    """按 ALCE 定义算 citation recall。

    断言粒度 = 产物里的一条 unit（句/条目）；其「被引片段」= 它挂的每条断言的文本拼接。
    """
    from .extract_l1 import _client
    from .artifact_shape import iter_units
    from .evidence import _assertions_path

    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    from .evidence import assertion_evidence

    aid_text: dict[str, str] = {}
    aid_sid: dict[str, str] = {}
    for line in _assertions_path(video_id).read_text(encoding="utf-8").splitlines():
        if line.strip():
            a = json.loads(line)
            # 口径 v2：被引片段取 **quote（逐字原文）**，不是 text（模型改写）。
            # v1 用 text ⇒ 这个指标量的其实是「产物文本 vs 断言文本」，
            # 即两个模型产物之间的一致性，不是「产物 vs 视频证据」。
            aid_text[a["id"]] = assertion_evidence(a)
            aid_sid[a["id"]] = ((a.get("anchors") or [{}])[0].get("sid") or "")

    # 说话人块：**属于被引证据的一部分**（用户裁定 B）
    # 依据：访谈实测——断言是对话原文（"我出道就穿成这样来了"），说话人不在其中；
    # 若不把归属算作证据，任何带人名的表述都会被判"不被支撑"（实测 0.6154）。
    sp_path = DATA_DIR / video_id / "speaker_map.json"
    sp_blocks = json.loads(sp_path.read_text(encoding="utf-8")).get("blocks") if sp_path.exists() else []

    def speaker_note(sid: str) -> str | None:
        for b in sp_blocks or []:
            if b["spk_from"] <= sid <= b["spk_to"] and (b.get("speaker") or b.get("role")):
                who = b.get("speaker") or f"（{b.get('role')}）"
                return f"（该句的说话人：{who}；句块 {b['spk_from']}..{b['spk_to']}）"
        return None

    units = [u for u in iter_units(artifact) if u.get("evidence") != "gloss"]
    if sample and sample < len(units):
        import random
        units = random.Random(seed).sample(units, sample)

    client = _client()
    items = []
    for u in units:
        ids = [a for a in (u.get("assertion_ids") or []) if a in aid_text]
        if not ids:
            # ALCE：无引用的断言，recall 记 0
            items.append({"unit": u.get("sid") or u.get("id"), "recall": 0.0,
                          "reason": "无引用（ALCE 定义：记 0）", "assertion_ids": []})
            continue
        lines = []
        for a in ids:
            note = speaker_note(aid_sid.get(a, ""))
            lines.append(f"- {aid_text[a]}" + (f" {note}" if note else ""))
        concat = "\n".join(lines)
        user = (f"断言：{u.get('text')}\n\n被引用的片段（拼接）：\n{concat}\n\n"
                "注意：片段后括号里的「说话人」属于被引证据的一部分——"
                "如果它给出了说话人，句子里把这句话归给该说话人**是有依据的**。\n"
                "请判定并只输出 JSON。")
        t0 = time.time()
        try:
            with trace_stage("alce_judge", version=ALCE_JUDGE_VERSION):
                resp = client.chat.completions.create(
                    model=model,
                    messages=[{"role": "system", "content": ENTAIL_SYSTEM},
                              {"role": "user", "content": user}],
                    response_format={"type": "json_object"}, temperature=0)
            data = json.loads(resp.choices[0].message.content or "{}")
            recall = 1.0 if data.get("entailed") is True else 0.0
            items.append({"unit": u.get("sid") or u.get("id"), "recall": recall,
                          "reason": str(data.get("reason", ""))[:80],
                          "assertion_ids": ids, "elapsed_s": round(time.time() - t0, 2)})
        except Exception as e:  # noqa: BLE001
            items.append({"unit": u.get("sid") or u.get("id"), "recall": None,
                          "reason": f"{type(e).__name__}: {e}"[:80], "assertion_ids": ids})

    scored = [i for i in items if i["recall"] is not None]
    recall = sum(i["recall"] for i in scored) / max(1, len(scored))
    return {
        "metric": "citation_recall (ALCE)",
        "definition": "断言级 0/1：至少一条引用 且 被引片段拼接蕴含该断言；无引用记 0；对全部断言平均",
        "judge": ALCE_JUDGE_NOTE,
        # 基准口径必须随数字一起报：换基准会让数字不可比，不显式记就会在新旧混用时误导
        "evidence_baseline": EVIDENCE_BASELINE,
        "baseline_note": ("被引片段取断言 quote（逐字原文）。v1 曾用 text（模型改写），"
                          "那种口径下本指标测的是两个模型产物之间的一致性，与旧数字不可比。"),
        "judge_human_agreement": ("未测。参照公开数字：ALCE 官方 NLI judge κ=0.247/0.146，"
                                  "GPT-4o judge κ=0.544/0.655 —— 本指标当前无已知的人工相关性。"),
        "scored": len(scored), "skipped": len(items) - len(scored),
        "citation_recall": round(recall, 4),
        "zero_recall_cases": [i for i in scored if i["recall"] == 0.0][:10],
        "items": items,
    }


# ---------------------------------------------------------------- 时间锚点（区间定位）

def iou(a: tuple[int, int], b: tuple[int, int]) -> float:
    lo, hi = max(a[0], b[0]), min(a[1], b[1])
    inter = max(0, hi - lo)
    union = (a[1] - a[0]) + (b[1] - b[0]) - inter
    return inter / union if union > 0 else 0.0


def anchor_grounding(video_id: str, gold_path: Path | None = None, *,
                     thresholds: tuple[float, ...] = (0.3, 0.5, 0.7),
                     human_precision_ms: int = 1000) -> dict:
    """时间锚点的区间定位质量：R@1@IoU(θ) 与 mIoU。

    两套口径都报（因为人工核定的精度有限）：
    - **strict**：直接用人工填的区间；
    - **±1 秒宽容**：把人工区间两端各放宽 human_precision_ms 后再算
      （依据：人工只能精确到秒，用毫秒尺子量秒级标注会系统性低估）。

    gold 文件格式：
      {"items": [{"assertion_id": "...", "gold_start_ms": ..., "gold_end_ms": ...}, ...]}
      （早期格式为裸数组，也支持）
    """
    from .evidence import load_assertions

    gold: dict[str, tuple[int, int]] = {}
    if gold_path and Path(gold_path).exists():
        doc = json.loads(Path(gold_path).read_text(encoding="utf-8"))
        items = doc.get("items") if isinstance(doc, dict) else doc
        for row in items or []:
            if row.get("gold_start_ms") is None:
                continue
            gold[row["assertion_id"]] = (int(row["gold_start_ms"]), int(row["gold_end_ms"]))

    rows = []
    for a in load_assertions(video_id):
        if a["id"] not in gold:
            continue
        an = (a.get("anchors") or [{}])[0]
        pred = (int(an.get("start_ms") or 0), int(an.get("end_ms") or 0))
        g = gold[a["id"]]
        g_loose = (g[0] - human_precision_ms, g[1] + human_precision_ms)
        rows.append({"assertion_id": a["id"], "pred": pred, "gold": g,
                     "iou": round(iou(pred, g), 4),
                     "iou_loose": round(iou(pred, g_loose), 4)})

    if not rows:
        return {"metric": "anchor_grounding (temporal grounding 口径)",
                "status": "无人工核定样本（需要 gold 文件）",
                "gold_path": str(gold_path) if gold_path else None,
                "hint": "见 docs/eval-methodology.md §6：由人核定区间后即可算 R@n 与 mIoU"}

    n = len(rows)
    # 「起点都在 ±1s 内」：人工与系统都是秒级标注，用这条看是否只是**整体偏移**
    # （严格 IoU 对短区间苛刻；这条区分「端点都在附近」与「整体偏了」两类问题）
    boundary_ok = sum(1 for r in rows
                      if abs(r["pred"][0] - r["gold"][0]) <= human_precision_ms
                      and abs(r["pred"][1] - r["gold"][1]) <= human_precision_ms)
    out = {"metric": "anchor_grounding (temporal grounding 口径)",
           "definition": "把秒级锚点视为区间，按 TALL/Charades-STA 惯例报 R@1@IoU(θ) 与 mIoU",
           "note": "「±k 秒点误差」无公认定义，本项只报区间口径；"
                   "人工与系统均为秒级标注（精度对等），故直接用 IoU",
           "n": n,
           "mIoU": round(sum(r["iou"] for r in rows) / n, 4),
           "boundary_within_1s": round(boundary_ok / n, 4),
           "rows": rows}
    for th in thresholds:
        out[f"R@1@IoU{th}"] = round(sum(1 for r in rows if r["iou"] >= th) / n, 4)
    return out


# ---------------------------------------------------------------- 一致性

def kappa(pairs: list[tuple[str, str]]) -> dict:
    """Cohen's κ（两标注者、离散标签）。档位解释用 Landis & Koch 惯例。"""
    if not pairs:
        return {"status": "无标注对"}
    labels = sorted({x for p in pairs for x in p})
    n = len(pairs)
    po = sum(1 for a, b in pairs if a == b) / n
    pe = 0.0
    for lab in labels:
        pa = sum(1 for a, _ in pairs if a == lab) / n
        pb = sum(1 for _, b in pairs if b == lab) / n
        pe += pa * pb
    k = (po - pe) / (1 - pe) if pe < 1 else 1.0
    level = ("几乎完全一致" if k > 0.80 else "substantial（0.61–0.80）" if k >= 0.61
             else "moderate（0.41–0.60）" if k >= 0.41 else "fair/poor（<0.41）")
    return {"metric": "Cohen's kappa", "n": n, "po": round(po, 4), "pe": round(pe, 4),
            "kappa": round(k, 4), "level": level,
            "reference": "Landis & Koch 档位；Krippendorff α 惯例：≥0.667 暂定、≥0.80 可靠"}
