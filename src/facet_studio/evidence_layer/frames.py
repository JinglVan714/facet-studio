"""层 0 · 抽帧：媒体 -> 帧图片 + 帧↔时间戳对照。

按 D4/D5/D6/D9 的裁定实现：
- **两种策略都跑**（固定间隔 + 场景切分），各自独立落盘：`frames/` 与 `frames_scene/`。
- **只标记重复、不删帧**：pHash 距离写进索引，消费期再决定用不用（D5）。
- **本层不产出画面文字**：不调读图模型、不做 OCR，只保证帧本身全留（D6）。
- 内容相关的抽帧参数全部登记进索引与 manifest，不写死在流程里。

固定间隔的意义：屏幕录制类素材场景切分失效（实测 22.9min 只切出 3 段）；
场景切分的意义：实拍类素材一秒多的节奏才切得开（实测中位 1.64s）。
"""
from __future__ import annotations

import json
import statistics
import subprocess
import time
from pathlib import Path

from .constants import (
    DATA_DIR,
    DEFAULT_FRAME_HEIGHT,
    DEFAULT_FRAME_INTERVAL_S,
    DEFAULT_MIN_SCENE_LEN_S,
    DEFAULT_PHASH_DISTANCE,
    DEFAULT_SCENE_MAX_SCENES,
    DEFAULT_SCENE_THRESHOLD,
    TOOLS_DIR,
)


def ffmpeg_exe() -> str:
    """与 yt-dlp 共用一个 ffmpeg 垫片（tools/ffmpeg.exe）。"""
    target = TOOLS_DIR / "ffmpeg.exe"
    if target.exists():
        return str(target)
    import shutil

    import imageio_ffmpeg

    TOOLS_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy2(imageio_ffmpeg.get_ffmpeg_exe(), target)
    return str(target)


# ------------------------------------------------------------------ 时间轴规划

def fixed_timeline(duration_s: float, interval_s: float) -> list[tuple[float, float]]:
    """固定间隔：返回 [(取样时间, 槽位末), ...]，覆盖全片。"""
    times = []
    t = interval_s / 2  # 从半个间隔开始，避免抓到 0s 的黑帧/片头黑场
    while t < duration_s:
        times.append((t, min(t + interval_s, duration_s)))
        t += interval_s
    return times


def scene_timeline(media: Path, threshold: float, min_scene_len_s: float,
                   max_scenes: int) -> tuple[list[tuple[float, float]], dict]:
    """场景切分：ContentDetector + 显式短场景合并 + 上限保护。"""
    from scenedetect import ContentDetector, SceneManager, open_video

    t0 = time.time()
    video = open_video(str(media))
    sm = SceneManager()
    sm.add_detector(ContentDetector(threshold=threshold))
    sm.detect_scenes(video, show_progress=False)
    raw = [(s.get_seconds(), e.get_seconds()) for s, e in sm.get_scene_list(start_in_scene=True)]

    merged: list[list[float]] = []
    for s, e in raw:
        if merged and (e - merged[-1][0]) < min_scene_len_s:
            merged[-1][1] = e
        else:
            merged.append([s, e])
    scenes = [(s, e) for s, e in merged if e > s]

    truncated = False
    if len(scenes) > max_scenes:
        # 切分失效（内容变化过密）时按等距截断，并把「被截断」写进索引
        step = len(scenes) / max_scenes
        scenes = [scenes[int(i * step)] for i in range(max_scenes)]
        truncated = True

    durs = [e - s for s, e in scenes]
    stats = {
        "scene_count": len(scenes),
        "truncated_to_max": truncated,
        "min_s": round(min(durs), 2) if durs else None,
        "median_s": round(statistics.median(durs), 2) if durs else None,
        "max_s": round(max(durs), 2) if durs else None,
        "decode_elapsed_s": round(time.time() - t0, 1),
    }
    return scenes, stats


# ------------------------------------------------------------------ 落帧

def _grab(media: Path, t: float, target: Path, height: int) -> bool:
    cmd = [ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
           "-ss", f"{t:.3f}", "-i", str(media), "-frames:v", "1",
           "-vf", f"scale=-2:{height}", "-q:v", "3", str(target)]
    p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    return p.returncode == 0 and target.exists() and target.stat().st_size > 0


def grab_frames(media: Path, timeline: list[tuple[float, float]], out_dir: Path,
                height: int, prefix: str) -> list[dict]:
    """把时间轴上的点落成 jpg；文件名 = 序号_毫秒.jpg。"""
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for idx, (t, slot_end) in enumerate(timeline):
        ms = int(round(t * 1000))
        name = f"{prefix}{idx:05d}_{ms:09d}.jpg"
        ok = _grab(media, t, out_dir / name, height)
        rows.append({
            "idx": idx,
            "t_ms": ms,
            "slot_end_ms": int(round(slot_end * 1000)),
            "file": f"{out_dir.name}/{name}" if ok else None,
        })
    return rows


# ------------------------------------------------------------------ 去重标记（只标记，不删）

def mark_duplicates(rows: list[dict], base_dir: Path, threshold: int = DEFAULT_PHASH_DISTANCE) -> dict:
    """对已落盘的帧算 pHash，标记与**前一帧**距离 ≤ threshold 的为疑似重复。"""
    try:
        import imagehash
        from PIL import Image
    except ImportError as e:  # noqa: BLE001
        return {"available": False, "reason": f"imagehash 未安装：{e}"}

    hashes: list[tuple[str, object]] = []
    for r in rows:
        if not r.get("file"):
            continue
        p = base_dir / r["file"]
        with Image.open(p) as im:
            hashes.append((r["file"], imagehash.phash(im)))

    flags: list[dict] = []
    for i, (f, h) in enumerate(hashes):
        if i == 0:
            flags.append({"file": f, "phash_distance_prev": None, "suspect_duplicate": False})
            continue
        d = h - hashes[i - 1][1]
        flags.append({"file": f, "phash_distance_prev": int(d), "suspect_duplicate": bool(d <= threshold)})

    return {
        "available": True,
        "algorithm": "phash",
        "threshold": threshold,
        "suspect_count": sum(1 for x in flags if x["suspect_duplicate"]),
        "total": len(flags),
        "per_frame": flags,
        "note": "仅标记，不删帧（D5：去重发生在消费期）",
    }


# ------------------------------------------------------------------ 对外入口

def extract_frames(video_id: str, media: Path, duration_s: float, *,
                   interval_s: float = DEFAULT_FRAME_INTERVAL_S,
                   scene_threshold: float = DEFAULT_SCENE_THRESHOLD,
                   min_scene_len_s: float = DEFAULT_MIN_SCENE_LEN_S,
                   max_scenes: int = DEFAULT_SCENE_MAX_SCENES,
                   height: int = DEFAULT_FRAME_HEIGHT,
                   phash_distance: int = DEFAULT_PHASH_DISTANCE,
                   do_scene: bool = True) -> dict:
    out_root = DATA_DIR / video_id
    result: dict = {
        "video_id": video_id,
        "media_path": str(media),
        "duration_s": duration_s,
        "params": {
            "interval_s": interval_s,
            "scene_threshold": scene_threshold,
            "min_scene_len_s": min_scene_len_s,
            "max_scenes": max_scenes,
            "height": height,
            "phash_distance": phash_distance,
        },
        "strategies": {},
    }

    tl = fixed_timeline(duration_s, interval_s)
    rows = grab_frames(media, tl, out_root / "frames", height, prefix="")
    result["strategies"]["fixed_interval"] = {
        "kind": "fixed_interval",
        "interval_s": interval_s,
        "frame_count": len([r for r in rows if r["file"]]),
        "frames": rows,
        "duplicate_marking": mark_duplicates(rows, out_root),
    }

    if do_scene:
        scenes, stats = scene_timeline(media, scene_threshold, min_scene_len_s, max_scenes)
        scene_rows = []
        for i, (s, e) in enumerate(scenes):
            scene_rows.append({"idx": i, "scene_start_ms": int(round(s * 1000)),
                               "scene_end_ms": int(round(e * 1000)),
                               "slot_end_ms": int(round(e * 1000))})
        # 场景中点作为取样点
        tl2 = [((r["scene_start_ms"] + r["scene_end_ms"]) / 2000.0, r["scene_end_ms"] / 1000.0)
               for r in scene_rows]
        rows2 = grab_frames(media, tl2, out_root / "frames_scene", height, prefix="")
        for r, s in zip(rows2, scene_rows):
            r["scene_index"] = s["idx"]
            r["scene_start_ms"] = s["scene_start_ms"]
            r["scene_end_ms"] = s["scene_end_ms"]
        result["strategies"]["scene"] = {
            "kind": "scene_midpoint",
            "stats": stats,
            "frame_count": len([r for r in rows2 if r["file"]]),
            "frames": rows2,
            "duplicate_marking": mark_duplicates(rows2, out_root),
        }

    (out_root / "frames_index.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result
