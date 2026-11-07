"""层 0 · 帧转录：批量把帧上的字读出来（模型产出，不是原料）。

依据 docs/layer0-probe-report.md §8 的实测：
- 批量 = 16（更小的批量判不出重复，且单帧成本更高）；
- 判据是「有没有新增信息」：模型给出的 `representatives` 是**主信号**，pHash 降为辅助；
- **原始帧一张不删**（D5/D9 修订）：本模块只新增产物，不改动 frames/。

产出：data/<video_id>/frames_vlm/<stem>.txt（人读）、frames_vlm.json（程序用，含 text_hash 与代表帧标记）。
本模块的输出是**模型产出**，任何消费方都必须知道它的出处（模型 / 提示词版本 / 时间）。
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import time
from pathlib import Path

from .audio import apply_ssl_shim
from .constants import DATA_DIR, DEFAULT_VLM_ENDPOINT, DEFAULT_VLM_MODEL

PROMPT_VERSION = "frame_batch/v1"
BATCH_SIZE = 16
# 批级并发（F2 实测 2026-10-13，见 docs/layer0-probe-report.md §10）：
# 3 路把 46 帧的墙钟从 446s 压到 124s（2.6×），3/3 批成功、零缺帧、无失败码。
DEFAULT_CONCURRENCY = 3

BATCH_PROMPT = """下面给你 {n} 张来自同一段视频的截图，**按时间顺序**排列，编号从 1 到 {n}。
每张图前面的文字是它的帧 ID。

请对每一张分别处理，只输出严格 JSON（不要 Markdown 代码块，不要解释）：
{{
  "frames": {{
    "<帧ID>": "该帧上所有可见文字的逐字转录：保持层级；表格用 | 分隔列；看不清写 [unclear]；无文字填空字符串",
    ...
  }},
  "redundant": ["与上一张相比没有新增可读信息的帧ID", ...],
  "representatives": ["从这 {n} 张里挑出的信息不重复的代表帧ID", ...]
}}

规则：
- 只写你**确实看清**的字；不许猜测、不许总结、不许补充图中没有的内容；
- `redundant` 的判据是「**有没有新增信息**」：只是滚动位置变化、内容与上一张相同，就算 redundant；
- `representatives` 要尽量少而全：选中的帧合起来应覆盖这批图里的全部信息。
"""


def _load_env() -> None:
    p = DATA_DIR.parent / ".env"
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        os.environ.setdefault(k.strip(), v.strip())


def _text_hash(text: str) -> str:
    norm = "".join(text.split())
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()[:16]


# 模型在看不清楚时会输出这类占位符。它们是**抽取失败**，不是内容——
# 实测：video 参数模式下，模型对 8 帧全部回 "[unclear]" 并把它们标成 redundant
# （见 docs/layer0-probe-report.md §9）。绝不能让占位符进入任何结论。
PLACEHOLDER_PATTERNS = (r"^\[unclear\]$", r"^\[?unclear\]?$", r"^（?看不清）?$",
                        r"^看不清$", r"^\[无法辨认\]$", r"^\[模糊\]$")


def classify_text(text: str) -> tuple[str, bool]:
    """返回 (清理后的文本, 是否判定为读取失败)。"""
    norm = (text or "").strip()
    if not norm:
        return "", True
    compact = "".join(norm.split())
    for pat in PLACEHOLDER_PATTERNS:
        if re.match(pat, compact, flags=re.IGNORECASE):
            return "", True
    # 整段几乎只有占位符且无其他内容
    stripped = re.sub(r"\[unclear\]|看不清|无法辨认", "", compact)
    if len(stripped) <= 1:
        return "", True
    return norm, False


def _parse_json(text: str) -> dict:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        parts = cleaned.split("```")
        cleaned = parts[1] if len(parts) > 1 else cleaned
        if cleaned.startswith("json"):
            cleaned = cleaned[4:]
    return json.loads(cleaned.strip())


def _run_batch(bi: int, batch: list[Path], api_key: str, model: str, endpoint: str,
               video_id: str, timeout: int = 600,
               frame_dir_name: str = "frames") -> dict:
    """单批：调一次读图模型 → 解析 → 原始响应落盘。可并发调用（帧文件名各自独立）。"""
    import dashscope

    content: list[dict] = [{"text": BATCH_PROMPT.format(n=len(batch))}]
    for f in batch:
        b64 = base64.b64encode(f.read_bytes()).decode("ascii")
        content.append({"text": f"帧ID: {f.stem}"})
        content.append({"image": f"data:image/jpeg;base64,{b64}"})

    t0 = time.time()
    rec: dict = {"batch_index": bi, "frames": [f.stem for f in batch],
                 "model": model, "prompt_version": PROMPT_VERSION}
    try:
        resp = dashscope.MultiModalConversation.call(
            api_key=api_key, model=model,
            messages=[{"role": "user", "content": content}],
            timeout=timeout)
    except Exception as e:  # noqa: BLE001
        rec.update(ok=False, elapsed_s=round(time.time() - t0, 2),
                   error=f"{type(e).__name__}: {e}"[:300])
        return rec

    rec["elapsed_s"] = round(time.time() - t0, 2)
    status = getattr(resp, "status_code", None)
    if status != 200:
        rec.update(ok=False, status_code=status, message=str(getattr(resp, "message", ""))[:300])
        return rec

    body = resp.output.choices[0].message.content
    text = body[0].get("text") if isinstance(body, list) else str(body)
    # Include the frame directory: fixed/scene batches can now run in parallel
    # and must not overwrite each other's raw responses.
    rec["raw_file"] = f"{frame_dir_name}_batch{bi:03d}.txt"
    try:
        parsed = _parse_json(text)
        rec["ok"] = True
        rec["per_frame"] = parsed.get("frames", {})
        rec["redundant"] = [str(x) for x in (parsed.get("redundant") or [])]
        rec["representatives"] = [str(x) for x in (parsed.get("representatives") or [])]
        rec["missing_frames"] = [f.stem for f in batch if f.stem not in rec["per_frame"]]
    except Exception as e:  # noqa: BLE001
        rec.update(ok=False, parse_error=f"{type(e).__name__}: {e}"[:300])
    # 原始响应一律落盘：失败时是诊断依据，成功时是复核依据
    raw_dir = DATA_DIR / video_id / "frames_vlm" / "_raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    (raw_dir / rec["raw_file"]).write_text(text, encoding="utf-8")
    rec["raw_chars"] = len(text)
    return rec


def select_frame_names(index: dict, frame_dir_name: str,
                       max_frames: int) -> list[str]:
    """Deterministic fast-profile scene-frame selection.

    Keeps the frames most likely to carry new information: large pHash change
    from the previous frame, long scenes, and the first/last frame. Returns
    file paths as recorded in frames_index.json; callers use their basenames.
    No model call, no per-video rules.
    """
    key = "fixed_interval" if frame_dir_name == "frames" else "scene"
    strategy = (index.get("strategies") or {}).get(key) or {}
    frames = strategy.get("frames") or []
    # Fixed 30s frames are already the sparse baseline; never downsample them.
    if frame_dir_name == "frames":
        return [f.get("file") for f in frames if f.get("file")]
    if max_frames <= 0 or len(frames) <= max_frames:
        return [f.get("file") for f in frames if f.get("file")]
    dm = strategy.get("duplicate_marking") or {}
    per = {Path(row.get("file") or "").name: row.get("phash_distance_prev")
           for row in dm.get("per_frame") or []}
    scored = []
    for i, frame in enumerate(frames):
        name = Path(frame.get("file") or "").name
        score = float(per.get(name) or 0)
        span = (frame.get("scene_end_ms") or 0) - (frame.get("scene_start_ms") or 0)
        if span >= 5000:
            score += 20
        if i in (0, len(frames) - 1):
            score += 10
        scored.append((score, i, frame.get("file")))
    keep = sorted(i for _, i, _ in sorted(scored, key=lambda x: (-x[0], x[1]))[:max_frames])
    return [frames[i]["file"] for i in keep if frames[i].get("file")]


def select_fast_frames(video_id: str, frame_dir_name: str,
                       max_frames: int) -> list[str] | None:
    p = DATA_DIR / video_id / "frames_index.json"
    if not p.exists():
        return None
    try:
        return select_frame_names(json.loads(p.read_text(encoding="utf-8")),
                                  frame_dir_name, max_frames)
    except Exception:  # noqa: BLE001 - selection is an optimization
        return None


def transcribe_frames(video_id: str, frame_dir_name: str = "frames",
                      batch_size: int = BATCH_SIZE, model: str = DEFAULT_VLM_MODEL,
                      endpoint: str = DEFAULT_VLM_ENDPOINT,
                      limit_batches: int | None = None, start_batch: int = 0,
                      concurrency: int = DEFAULT_CONCURRENCY,
                      timeout: int = 600,
                      only_files: list[str] | None = None) -> dict:
    apply_ssl_shim()
    _load_env()
    import dashscope

    dashscope.base_http_api_url = endpoint
    api_key = os.environ.get("DASHSCOPE_API_KEY")
    if not api_key:
        raise RuntimeError("没有 DASHSCOPE_API_KEY")

    frame_dir = DATA_DIR / video_id / frame_dir_name
    files = sorted(frame_dir.glob("*.jpg"))
    if only_files is not None:
        wanted = {Path(x).name for x in only_files}
        files = [p for p in files if p.name in wanted]
    if not files:
        raise FileNotFoundError(f"{frame_dir} 下没有帧（selection={len(only_files or [])}）")

    batches = [files[i:i + batch_size] for i in range(0, len(files), batch_size)]
    if limit_batches is not None:
        batches = batches[start_batch:start_batch + limit_batches]

    records: list[dict] = []
    jobs = list(enumerate(batches, start=start_batch))
    if concurrency and concurrency > 1:
        from concurrent.futures import ThreadPoolExecutor

        t_all = time.time()
        with ThreadPoolExecutor(max_workers=concurrency) as ex:
            records = list(ex.map(
                lambda job: _run_batch(job[0], job[1], api_key, model, endpoint,
                                       video_id, timeout=timeout,
                                       frame_dir_name=frame_dir_name), jobs))
        print(f"[vlm] {len(batches)} 批 × 并发 {concurrency}：墙钟 {round(time.time() - t_all, 1)}s")
    else:
        for bi, batch in jobs:
            records.append(_run_batch(bi, batch, api_key, model, endpoint, video_id,
                                      timeout=timeout,
                                      frame_dir_name=frame_dir_name))

    for rec in records:
        print(f"[vlm] batch {rec['batch_index']}: {len(rec.get('frames') or [])} 帧 "
              f"{rec.get('elapsed_s')}s ok={rec.get('ok')} "
              f"redundant={len(rec.get('redundant') or [])} "
              f"reps={len(rec.get('representatives') or [])}"
              + (f" PARSE_ERROR={rec.get('parse_error') or rec.get('error') or rec.get('message')}"
                 if not rec.get("ok") else ""))

    # 汇总：逐帧文本 + 文本哈希 + 是否代表帧
    out_dir = DATA_DIR / video_id / "frames_vlm"
    out_dir.mkdir(parents=True, exist_ok=True)
    per_frame: dict[str, dict] = {}
    for rec in records:
        if not rec.get("ok"):
            continue
        reps = set(rec.get("representatives") or [])
        red = set(rec.get("redundant") or [])
        for stem, text in (rec.get("per_frame") or {}).items():
            text = text if isinstance(text, str) else str(text)
            cleaned, failed = classify_text(text)
            per_frame[stem] = {
                "text": cleaned,
                "text_hash": _text_hash(cleaned) if cleaned else None,
                "read_failed": failed,
                "raw_text": text if failed else None,   # 保留原始输出以便复核
                "is_representative": stem in reps,
                "redundant_with_prev": stem in red,
                "batch_index": rec["batch_index"],
            }
            (out_dir / f"{stem}.txt").write_text(cleaned, encoding="utf-8")

    # 续跑合并：本次只跑了部分批次时，把结果并入已有产物，不冲掉其它批。
    # 文件名必须带帧目录名——否则对 frames/ 与 frames_scene/ 各跑一次会互相覆盖
    # （实测踩过：短视频 frames_scene 的转录被长视频 frames 的转录冲掉，帧引用归零）
    summary_path = DATA_DIR / video_id / f"frames_vlm__{frame_dir_name}.json"
    new_batches = [{k: v for k, v in r.items() if k not in ("raw", "per_frame")} for r in records]
    if summary_path.exists() and (limit_batches is not None or start_batch):
        prev = json.loads(summary_path.read_text(encoding="utf-8"))
        # Only successful re-runs may replace previous per-frame text. A failed
        # batch must not delete the previous (still usable) transcription.
        rerun_frames = {f.stem for r in records if r.get("ok")
                        for f in files if f.stem in (r.get("frames") or [])}
        merged_per_frame = {k: v for k, v in (prev.get("per_frame") or {}).items()
                            if k not in rerun_frames}
        merged_per_frame.update(per_frame)
        per_frame = merged_per_frame
        by_idx = {b["batch_index"]: b for b in (prev.get("batches") or [])}
        by_idx.update({b["batch_index"]: b for b in new_batches})
        new_batches = [by_idx[k] for k in sorted(by_idx)]

    failed_batches = [b["batch_index"] for b in new_batches if not b.get("ok")]
    missing_frames = [f.stem for f in files if f.stem not in per_frame]
    if missing_frames or failed_batches:
        print(f"[vlm][WARN] 未覆盖 {len(missing_frames)} 帧；失败批次 {failed_batches}。"
              f"原始响应见 frames_vlm/_raw/，可只重跑失败批次（--start-batch/--limit-batches）")

    summary = {
        "video_id": video_id,
        "source_dir": frame_dir_name,
        "provenance": {"model": model, "endpoint": endpoint, "prompt_version": PROMPT_VERSION,
                       "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                       "batch_size": batch_size,
                       "note": "模型产出（advisory）：只做转录与重复标记，不参与任何判定"},
        "frame_count": len(files),
        "transcribed_count": len(per_frame),
        "read_failed_count": sum(1 for v in per_frame.values() if v["read_failed"]),
        "representative_count": sum(1 for v in per_frame.values() if v["is_representative"]),
        "redundant_count": sum(1 for v in per_frame.values() if v["redundant_with_prev"]),
        "unique_text_count": len({v["text_hash"] for v in per_frame.values() if v["text_hash"]}),
        "failed_batches": failed_batches,
        "missing_frames": missing_frames,
        "coverage_ratio": round(len(per_frame) / len(files), 4) if files else None,
        "per_frame": per_frame,
        "batches": new_batches,
    }
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary
