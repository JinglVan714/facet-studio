"""层 0 · 自检与登记：算出来的覆盖率 / 合法性 + 产物出处登记。

这一层不设「门禁数量」（硬约束 2），只把**能算的事实**写进 manifest.json：
- 转录覆盖：首末句落在音频时长内的比例、锚点单调性、句内 end>=start
- 帧覆盖：帧时间戳跨度 / 视频时长、两种策略各自的帧数
- 产物非空：句数、token 数、帧数、字节数
- **出处登记**：谁产的（模型 / 端点 / 脚本版本 / 时间 / 参数）——M4 的落地形态
"""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

from .constants import DATA_DIR, PROJECT_ROOT

SCRIPT_VERSION = "layer0/0.1.0"


def sha256_of(path: Path | None, chunk: int = 1 << 20) -> str | None:
    if not path or not Path(path).exists():
        return None
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def _rel_safe(p) -> str | None:
    if p is None:
        return None
    p = Path(p)
    try:
        return str(p.relative_to(PROJECT_ROOT)).replace("\\", "/")
    except ValueError:
        return str(p)


def check_transcript(doc: dict, audio_path: Path | None) -> dict:
    sentences = doc.get("sentences") or []
    nonempty = [s for s in sentences if (s.get("text") or "").strip()]
    words = [w for s in sentences for w in (s.get("words") or [])]
    audio_dur = doc.get("audio_duration_s")

    checks: dict = {
        "sentence_count": len(sentences),
        "nonempty_sentence_count": len(nonempty),
        "empty_sentence_count": len(sentences) - len(nonempty),
        "word_token_count": len(words),
        "audio_duration_s": audio_dur,
        "first_start_s": round(nonempty[0]["start_ms"] / 1000, 2) if nonempty else None,
        "last_end_s": round(nonempty[-1]["end_ms"] / 1000, 2) if nonempty else None,
    }

    # 覆盖：首末句落在音频时长内的比例
    if nonempty and audio_dur:
        cover = (nonempty[-1]["end_ms"] / 1000.0) / audio_dur
        checks["time_coverage_ratio"] = round(cover, 4)
        checks["covers_to_last_5_percent"] = cover >= 0.95
    else:
        checks["time_coverage_ratio"] = None
        checks["covers_to_last_5_percent"] = None

    checks["monotonic_sentence_order"] = all(
        sentences[i]["start_ms"] >= sentences[i - 1]["start_ms"] for i in range(1, len(sentences))
    ) if len(sentences) > 1 else None
    checks["end_ge_start_all"] = all(s["end_ms"] >= s["start_ms"] for s in sentences) if sentences else None

    # 静默空隙（>5s）：只报告，不判好坏
    gaps = []
    for i in range(1, len(nonempty)):
        g = nonempty[i]["start_ms"] - nonempty[i - 1]["end_ms"]
        if g > 5000:
            gaps.append({"from_s": round(nonempty[i - 1]["end_ms"] / 1000, 2),
                         "to_s": round(nonempty[i]["start_ms"] / 1000, 2),
                         "gap_s": round(g / 1000, 2)})
    checks["gaps_gt_5s"] = gaps if gaps else []
    checks["max_gap_s"] = round(max((g["gap_s"] for g in gaps), default=0.0), 2)
    return checks


def check_frames(index: dict) -> dict:
    out: dict = {"duration_s": index.get("duration_s"), "strategies": {}}
    for name, st in (index.get("strategies") or {}).items():
        frames = [f for f in (st.get("frames") or []) if f.get("file")]
        ts = [f["t_ms"] for f in frames]
        dur = index.get("duration_s") or 0
        out["strategies"][name] = {
            "frame_count": len(frames),
            "first_ms": min(ts) if ts else None,
            "last_ms": max(ts) if ts else None,
            "span_ratio": round((max(ts) - min(ts)) / 1000.0 / dur, 4) if ts and dur else None,
            "monotonic": all(ts[i] >= ts[i - 1] for i in range(1, len(ts))) if len(ts) > 1 else None,
            "suspect_duplicates": (st.get("duplicate_marking") or {}).get("suspect_count"),
        }
    return out


def build_manifest(video_id: str, *, source: dict, transcript: dict | None,
                   transcript_path: Path | None, audio_path: Path | None,
                   frames_index: dict | None, extra_notes: list[str] | None = None) -> dict:
    media = Path(source["media_path"]) if source.get("media_path") else None
    manifest = {
        "video_id": video_id,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "script_version": SCRIPT_VERSION,
        "source": {
            "kind": source.get("source_kind"),
            "url": source.get("source_url"),
            "media_path": _rel_safe(media),
            "media_sha256": sha256_of(media),
            "media_size_bytes": source.get("media_size_bytes"),
            "duration_s": source.get("duration_s"),
            "title": source.get("title"),
            "uploader": source.get("uploader"),
        },
        "provenance": {},   # 谁产的：模型 / 端点 / 时间（M4）
        "checks": {},
        "notes": extra_notes or [],
    }

    if transcript is not None:
        manifest["provenance"]["transcript"] = {
            "kind": transcript.get("kind"),
            "engine": transcript.get("engine"),
            "model": transcript.get("model"),
            "endpoint": transcript.get("ws_endpoint"),
            "request_id": transcript.get("request_id"),
            "ssl_shim": transcript.get("ssl_shim"),
            "elapsed_s": transcript.get("elapsed_s"),
            "rtf": transcript.get("rtf"),
            "has_word_timestamps": transcript.get("has_word_timestamps"),
            "output_language": "source",
        }
        manifest["provenance"]["audio"] = {"sha256": sha256_of(audio_path),
                                           "path": _rel_safe(audio_path)}
        manifest["checks"]["transcript"] = check_transcript(transcript, audio_path)

    if frames_index is not None:
        manifest["provenance"]["frames"] = {
            "params": frames_index.get("params"),
            "naming": "<idx>_<t_ms>.jpg；序号在各自目录内唯一，毫秒级时间戳",
        }
        manifest["checks"]["frames"] = check_frames(frames_index)

    return manifest


def write_manifest(video_id: str, manifest: dict) -> Path:
    p = DATA_DIR / video_id / "manifest.json"
    p.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return p
