"""层 0 · 取流：URL / 本地文件 -> 统一的可处理媒体与来源记录。

两种输入：
- URL（B 站等）→ yt-dlp 下载并合并（B 站是 DASH 分离流，合并是必需的）
- 本地文件 → 直接登记，不复制（原始数据不入库）

产出：data/<video_id>/raw/ 下的媒体文件 + data/<video_id>/source.json
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

from .constants import COOKIES_PATH, DATA_DIR, PROJECT_ROOT, TOOLS_DIR


def child_env() -> dict:
    """子进程统一 UTF-8，避免 Windows 控制台 GBK 把中文标题写崩。"""
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    return env


def ffmpeg_for_ytdlp() -> str:
    """yt-dlp 只认名为 ffmpeg 的可执行文件；imageio-ffmpeg 自带的那个名字不匹配，
    这里复制成 tools/ffmpeg.exe 并返回路径（不改系统环境变量，不动 PATH）。"""
    target = TOOLS_DIR / "ffmpeg.exe"
    if not target.exists():
        import shutil

        import imageio_ffmpeg

        TOOLS_DIR.mkdir(parents=True, exist_ok=True)
        shutil.copy2(imageio_ffmpeg.get_ffmpeg_exe(), target)
    return str(target)


def is_url(s: str) -> bool:
    return urlparse(s).scheme in {"http", "https"}


def _probe_streams(path: Path) -> tuple[bool, bool]:
    """返回 (有视频轨, 有音频轨)。合并失败的半成品会在这里暴露。"""
    try:
        import av

        with av.open(str(path)) as c:
            return bool(c.streams.video), bool(c.streams.audio)
    except Exception:  # noqa: BLE001
        return False, False


def acquire_url(url: str, max_height: int = 1080) -> dict:
    env = child_env()
    ffmpeg = ffmpeg_for_ytdlp()
    # 公开视频不强制要 cookies；有登录态文件时才带上（1080p/会员片可能需要）。
    cookie_args = ["--cookies", str(COOKIES_PATH)] if COOKIES_PATH.exists() else []

    meta_cmd = [sys.executable, "-m", "yt_dlp", *cookie_args,
                "--simulate", "--no-warnings", "--dump-single-json", url]
    p = subprocess.run(meta_cmd, capture_output=True, text=True, encoding="utf-8",
                       errors="replace", env=env)
    if p.returncode != 0:
        raise RuntimeError(f"yt-dlp metadata failed: {p.stderr[-500:]}")

    meta = json.loads(p.stdout)
    vid = meta.get("id") or "unknown"
    raw_dir = DATA_DIR / vid / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)

    dl_cmd = [sys.executable, "-m", "yt_dlp", *cookie_args,
              "--no-warnings", "--no-playlist",
              "--ffmpeg-location", ffmpeg,
              "-f", f"bv*[height<={max_height}]+ba/b[height<={max_height}]/b",
              "--merge-output-format", "mp4",
              "-o", str(raw_dir / "%(id)s.%(ext)s"), url]
    p = subprocess.run(dl_cmd, capture_output=True, text=True, encoding="utf-8",
                       errors="replace", env=env)
    if p.returncode != 0:
        raise RuntimeError(f"yt-dlp download failed: {p.stderr[-500:]}")

    media = _pick_media(raw_dir)
    info = _source_record(vid, url, meta, media, max_height)
    (DATA_DIR / vid / "source.json").write_text(json.dumps(info, ensure_ascii=False, indent=2),
                                                encoding="utf-8")
    return info


def acquire_local(path_str: str) -> dict:
    media = Path(path_str).expanduser().resolve()
    if not media.exists():
        raise FileNotFoundError(media)
    vid = media.stem
    has_v, has_a = _probe_streams(media)
    info = {
        "video_id": vid,
        "source_url": None,
        "source_kind": "local_file",
        "title": media.name,
        "duration_s": _probe_duration(media),
        "media_path": str(media),
        "media_size_bytes": media.stat().st_size,
        "media_has_av_streams": has_v and has_a,
        "raw_files": [media.name],
        "audio_only_path": None,
        "max_height_requested": None,
        "extractor": None,
    }
    (DATA_DIR / vid).mkdir(parents=True, exist_ok=True)
    (DATA_DIR / vid / "source.json").write_text(json.dumps(info, ensure_ascii=False, indent=2),
                                                encoding="utf-8")
    return info


def _probe_duration(path: Path) -> float | None:
    try:
        import av

        with av.open(str(path)) as c:
            return round(float(c.duration / av.time_base), 3) if c.duration else None
    except Exception:  # noqa: BLE001
        return None


def _pick_media(raw_dir: Path) -> Path:
    """合并成功时优先选「同时含音视频轨」的文件；否则退回体积最大者。"""
    candidates = sorted((f for f in raw_dir.iterdir()
                         if f.suffix.lower() in {".mp4", ".mkv", ".webm", ".flv", ".m4a"}),
                        key=lambda f: f.stat().st_size, reverse=True)
    if not candidates:
        raise FileNotFoundError(f"raw 目录下没有媒体文件：{raw_dir}")
    for f in candidates:
        has_v, has_a = _probe_streams(f)
        if has_v and has_a:
            return f
    return candidates[0]


def _source_record(vid: str, url: str, meta: dict, media: Path, max_height: int) -> dict:
    raw_dir = media.parent
    all_media = sorted((f for f in raw_dir.iterdir()
                        if f.suffix.lower() in {".mp4", ".mkv", ".webm", ".flv", ".m4a"}),
                       key=lambda f: f.stat().st_size, reverse=True)
    audio_only = next((f for f in all_media if _probe_streams(f) == (False, True)), None)
    has_v, has_a = _probe_streams(media)
    rel = lambda p: str(p.relative_to(PROJECT_ROOT)).replace("\\", "/") if PROJECT_ROOT in p.parents else str(p)
    return {
        "video_id": vid,
        "source_url": url,
        "source_kind": "url",
        "title": meta.get("title"),
        "duration_s": meta.get("duration"),
        "uploader": meta.get("uploader"),
        "upload_date": meta.get("upload_date"),
        "media_path": rel(media),
        "media_size_bytes": media.stat().st_size,
        "media_has_av_streams": has_v and has_a,
        "audio_only_path": rel(audio_only) if audio_only else None,
        "raw_files": [f.name for f in all_media],
        "max_height_requested": max_height,
        "extractor": meta.get("extractor"),
    }
