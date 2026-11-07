"""层 0 · 管线：把取流 / 抽帧 / 转录 / 自检串成一条可复跑的链。

用法见 lmind/cli.py。设计约束：
- 每个阶段各自可单独跑，互不依赖内部状态，只依赖 data/<video_id>/ 下的产物；
- 转录原稿一旦存在就**不覆盖**（--force 才会重跑），任何校正另存；
- 全部计算型结果（覆盖率等）在 manifest 里现算，不缓存。
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from . import acquire, audio, frames as frames_mod, manifest as manifest_mod
from .constants import DATA_DIR


def _load_dotenv() -> None:
    import os

    p = DATA_DIR.parent / ".env"
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        os.environ.setdefault(k.strip(), v.strip())


def load_source(video_id: str) -> dict:
    p = DATA_DIR / video_id / "source.json"
    if not p.exists():
        raise FileNotFoundError(f"没有 {p}，请先跑 acquire")
    return json.loads(p.read_text(encoding="utf-8"))


def step_acquire(target: str, max_height: int = 1080) -> dict:
    if acquire.is_url(target):
        info = acquire.acquire_url(target, max_height)
    else:
        info = acquire.acquire_local(target)
    print(f"[acquire] {info['video_id']}  {info.get('duration_s')}s  "
          f"{info.get('media_size_bytes')} bytes  av_streams={info.get('media_has_av_streams')}")
    return info


def step_frames(video_id: str, *, interval_s: float | None = None,
                scene_threshold: float | None = None, do_scene: bool = True,
                height: int | None = None) -> dict:
    from .constants import DEFAULT_FRAME_HEIGHT, DEFAULT_FRAME_INTERVAL_S, DEFAULT_SCENE_THRESHOLD

    src = load_source(video_id)
    media = Path(src["media_path"])
    duration = float(src.get("duration_s") or 0)
    idx = frames_mod.extract_frames(
        video_id, media, duration,
        interval_s=interval_s or DEFAULT_FRAME_INTERVAL_S,
        scene_threshold=scene_threshold or DEFAULT_SCENE_THRESHOLD,
        height=height or DEFAULT_FRAME_HEIGHT,
        do_scene=do_scene,
    )
    for name, st in idx["strategies"].items():
        dm = st.get("duplicate_marking") or {}
        print(f"[frames] {name}: {st.get('frame_count')} 帧"
              + (f"，疑似重复 {dm.get('suspect_count')}/{dm.get('total')}" if dm.get("available") else ""))
    return idx


def step_transcribe(video_id: str, *, force: bool = False, limit_s: float | None = None) -> dict:
    _load_dotenv()
    src = load_source(video_id)
    media = Path(src["media_path"])
    out_dir = DATA_DIR / video_id / "transcript"
    stem = "transcript"
    json_path = out_dir / f"{stem}.json"

    if json_path.exists() and not force and limit_s is None:
        print(f"[asr] 原稿已存在，跳过（--force 可重跑）：{json_path}")
        return json.loads(json_path.read_text(encoding="utf-8"))

    wav_path = out_dir / "audio_16k.wav"
    if not wav_path.exists() or force:
        info = audio.extract_wav(media, wav_path)
        print(f"[audio] {info['backend']}  {info['duration_s']}s  {info['elapsed_s']}s  rtf={info['rtf']}")

    doc = audio.transcribe(wav_path)
    paths = audio.write_transcript(doc, out_dir, stem)
    print(f"[asr] ok sentences={doc['sentence_count']} words={doc['has_word_timestamps']} "
          f"elapsed={doc['elapsed_s']}s rtf={doc['rtf']} request_id={doc['request_id']}")
    print(f"[asr] -> {paths['json']}")
    return doc


def step_manifest(video_id: str, notes: list[str] | None = None) -> dict:
    src = load_source(video_id)
    t_path = DATA_DIR / video_id / "transcript" / "transcript.json"
    transcript = json.loads(t_path.read_text(encoding="utf-8")) if t_path.exists() else None
    f_path = DATA_DIR / video_id / "frames_index.json"
    f_index = json.loads(f_path.read_text(encoding="utf-8")) if f_path.exists() else None
    wav = DATA_DIR / video_id / "transcript" / "audio_16k.wav"

    m = manifest_mod.build_manifest(
        video_id, source=src, transcript=transcript, transcript_path=t_path,
        audio_path=wav if wav.exists() else None, frames_index=f_index, extra_notes=notes,
    )
    p = manifest_mod.write_manifest(video_id, m)
    chk = m["checks"]
    if "transcript" in chk:
        t = chk["transcript"]
        print(f"[check] 转录 {t['nonempty_sentence_count']}/{t['sentence_count']} 句非空，"
              f"覆盖 {t['time_coverage_ratio']}，最大空隙 {t['max_gap_s']}s，"
              f"单调={t['monotonic_sentence_order']}")
    for name, c in (chk.get("frames") or {}).get("strategies", {}).items():
        print(f"[check] 帧({name}) {c['frame_count']} 张，跨度比 {c['span_ratio']}，"
              f"疑似重复 {c['suspect_duplicates']}")
    print(f"[manifest] -> {p}")
    return m


def run(target: str, *, max_height: int = 1080, do_frames: bool = True,
        do_asr: bool = True, force: bool = False, parallel: bool = True) -> dict:
    t0 = time.time()
    info = step_acquire(target, max_height)
    vid = info["video_id"]
    if parallel and do_frames and do_asr:
        # Both stages only depend on the acquired media and write to distinct
        # directories; overlapping them hides most of the ASR latency behind
        # frame extraction.
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=2) as ex:
            f_frames = ex.submit(step_frames, vid)
            f_asr = ex.submit(step_transcribe, vid, force=force)
            f_frames.result()
            f_asr.result()
    else:
        if do_frames:
            step_frames(vid)
        if do_asr:
            step_transcribe(vid, force=force)
    m = step_manifest(vid, notes=[f"total_pipeline_elapsed_s={round(time.time() - t0, 1)}"])
    return m
