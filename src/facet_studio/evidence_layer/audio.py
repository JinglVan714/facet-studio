"""层 0 · 音轨与转录：媒体 -> 16k 单声道 wav -> 带字级时间戳的原稿转录。

两条硬规则（来自实测与调研）：
1. **转录原稿只读**：任何校正另存，绝不覆盖原稿（回链永远指向原稿）。
2. **保留 ASR 完整原始响应**（D10）：它是「这条转录是谁产的」的唯一证据。
"""
from __future__ import annotations

import json
import os
import ssl
import time
import wave
from pathlib import Path

from .constants import DATA_DIR, DEFAULT_ASR_MODEL, DEFAULT_ASR_WS_ENDPOINT, SAMPLE_RATE


def apply_ssl_shim() -> str:
    """本机证书库损坏：import dashscope/aiohttp 会抛 SSLError[ASN1]。

    把 create_default_context 的失败回退到 certifi，必须在 import dashscope 之前调用。
    """
    import certifi

    original = ssl.create_default_context

    def patched(*a, **kw):
        try:
            return original(*a, **kw)
        except ssl.SSLError:
            return original(cafile=certifi.where())

    ssl.create_default_context = patched
    return certifi.where()


def wav_duration(path: Path) -> float:
    with wave.open(str(path), "rb") as wf:
        return wf.getnframes() / float(wf.getframerate())


def extract_wav(media: Path, wav_path: Path, limit_s: float | None = None) -> dict:
    """PyAV 解码音轨（不需要系统 ffmpeg），重采样为 16k 单声道 s16。"""
    import av

    wav_path.parent.mkdir(parents=True, exist_ok=True)
    resampler = av.AudioResampler(format="s16", layout="mono", rate=SAMPLE_RATE)
    written = 0
    t0 = time.time()
    with av.open(str(media)) as container:
        if not container.streams.audio:
            raise RuntimeError("媒体里没有音轨")
        stream = container.streams.audio[0]
        stream.thread_type = "AUTO"
        with wave.open(str(wav_path), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(SAMPLE_RATE)
            for frame in container.decode(stream):
                for rf in resampler.resample(frame):
                    if limit_s is not None and written / SAMPLE_RATE >= limit_s:
                        break
                    wf.writeframes(rf.to_ndarray().tobytes())
                    written += rf.samples
                if limit_s is not None and written / SAMPLE_RATE >= limit_s:
                    break
    dur = written / SAMPLE_RATE
    return {
        "backend": "pyav",
        "wav": str(wav_path),
        "duration_s": round(dur, 2),
        "bytes": wav_path.stat().st_size,
        "elapsed_s": round(time.time() - t0, 2),
        "rtf": round((time.time() - t0) / dur, 4) if dur else None,
    }


def _transcribe_dashscope(wav_path: Path, model: str, ws_endpoint: str) -> dict:
    certifi_path = apply_ssl_shim()
    import dashscope
    from dashscope.audio.asr import Recognition

    api_key = os.environ.get("DASHSCOPE_API_KEY")
    if not api_key:
        raise RuntimeError("环境里没有 DASHSCOPE_API_KEY（需从 .env 加载）")
    dashscope.api_key = api_key
    dashscope.base_websocket_api_url = ws_endpoint

    t0 = time.time()
    result = Recognition(model=model, format="wav", sample_rate=SAMPLE_RATE,
                         callback=None, enable_words=True).call(file=str(wav_path))
    elapsed = round(time.time() - t0, 2)

    status = getattr(result, "status_code", None)
    if status != 200:
        raise RuntimeError(f"ASR 失败 status={status} message={getattr(result, 'message', '')}")

    raw_sentences = result.get_sentence() or []
    sentences = []
    for s in raw_sentences:
        row = {"start_ms": s.get("begin_time"), "end_ms": s.get("end_time"), "text": s.get("text")}
        if s.get("words"):
            row["words"] = [
                {"start_ms": w.get("begin_time"), "end_ms": w.get("end_time"),
                 "text": w.get("text") or w.get("word")}
                for w in s["words"]
            ]
        sentences.append(row)

    dur = wav_duration(wav_path)
    return {
        "kind": "transcript_original",          # 原稿：不可被覆盖
        "engine": "dashscope",
        "model": model,
        "ws_endpoint": ws_endpoint,
        "ssl_shim": "certifi" if certifi_path else None,
        "request_id": getattr(result, "request_id", None),
        "audio_duration_s": round(dur, 2),
        "elapsed_s": elapsed,
        "rtf": round(elapsed / dur, 3) if dur else None,
        "sentence_count": len(sentences),
        "has_word_timestamps": any("words" in r for r in sentences),
        "missing_words_reason": None,           # 字级时间戳缺失时在这里写原因，不许留空沉默
        "sentences": sentences,
    }


def transcribe(wav_path: Path, model: str = DEFAULT_ASR_MODEL,
               ws_endpoint: str = DEFAULT_ASR_WS_ENDPOINT) -> dict:
    """Transcribe with DashScope (Qwen-Audio 3.1 ASR).

    A non-200 response is an explicit failure; there is no local ASR fallback
    in the product path.
    """
    return _transcribe_dashscope(wav_path, model, ws_endpoint)


def write_transcript(doc: dict, out_dir: Path, stem: str = "transcript") -> dict[str, str]:
    """落三种产物：原稿 json（含原始响应）、人读 txt、逐句 txt。"""
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / f"{stem}.json"
    readable_path = out_dir / f"{stem}.txt"

    json_path.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = []
    for s in doc["sentences"]:
        text = (s.get("text") or "").strip()
        lines.append(f"[{s['start_ms'] / 1000:8.2f}-{s['end_ms'] / 1000:8.2f}] {text}")
    readable_path.write_text("\n".join(lines), encoding="utf-8")
    return {"json": str(json_path), "txt": str(readable_path)}


def original_path(video_id: str) -> Path:
    return DATA_DIR / video_id / "transcript" / "transcript.json"
