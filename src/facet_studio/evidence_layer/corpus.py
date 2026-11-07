"""层 1 · 语料加载与分片（不含模型调用）。

分片机制按 E6 修订实现：**所有权 + 只读上下文**
- 每句有且只有一个**拥有者分片**（按句起点落在哪个时间窗）；
- 分片 i 的输入 = 自己范围内的句（owned）+ 前后各 N 句**只读上下文**（context）；
- 只有 owned 句可以被用来做锚点 ⇒ 从结构上保证「零重复抽取」，不依赖模型自觉；
- 校验器会查「同一 sid 被两个分片产锚点」并直接报冲突。

依据：实测 3883 token / 22.9 分钟 ⇒ 1 小时视频约 10k token，加上帧表与指令会超出安全上下文，
分片是必须的；分片参数进 settings/params.json（素材预设，不是客观常量）。
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .constants import DATA_DIR

CONTEXT_SENTENCES = 3          # 分片前后各带几句只读上下文
CHUNK_MINUTES = 15.0           # 时间窗（可调参数）


def load_corpus(video_id: str) -> dict:
    """读层 0 的产物，建立可回链的语料：句子表 + 帧表（含帧转录文本，若有）。"""
    base = DATA_DIR / video_id
    t_path = base / "transcript" / "transcript.json"
    if not t_path.exists():
        raise FileNotFoundError(f"缺少 {t_path}，请先跑层 0")
    doc = json.loads(t_path.read_text(encoding="utf-8"))

    sentences: dict[str, dict] = {}
    order: list[str] = []
    words_by_sent: dict[str, list[dict]] = {}
    for i, s in enumerate(doc.get("sentences") or []):
        sid = f"s{i:04d}"
        text = s.get("text") or ""
        sentences[sid] = {
            "sid": sid,
            "start_ms": int(s["start_ms"]),
            "end_ms": int(s["end_ms"]),
            "text": text,
            "has_content": bool(text.strip()),
        }
        order.append(sid)
        if s.get("words"):
            words_by_sent[sid] = s["words"]

    frames: dict[str, dict] = {}
    f_index = base / "frames_index.json"
    if f_index.exists():
        idx = json.loads(f_index.read_text(encoding="utf-8"))
        for strategy, st in (idx.get("strategies") or {}).items():
            for f in st.get("frames") or []:
                if not f.get("file"):
                    continue
                fid = Path(f["file"]).stem
                frames[fid] = {"fid": fid, "strategy": strategy, "t_ms": int(f["t_ms"])}

    # 帧转录：advisory，只作为模型上下文。
    # 按目录名分别读取（frames/ 与 frames_scene/ 各有自己的产物文件），
    # 只有 fid 与 frames_index.json 对得上的才会被吸收；对不上的一律记账，不静默丢。
    orphans: list[dict] = []
    for vlm_path in sorted(base.glob("frames_vlm*.json")):
        vlm = json.loads(vlm_path.read_text(encoding="utf-8"))
        for fid, rec in (vlm.get("per_frame") or {}).items():
            if fid in frames:
                frames[fid]["text"] = rec.get("text") or ""
                frames[fid]["text_hash"] = rec.get("text_hash")
                frames[fid]["is_representative"] = rec.get("is_representative")
                frames[fid]["advisory"] = True
            elif len(orphans) < 20:
                orphans.append({"fid": fid, "from": vlm_path.name})

    return {
        "video_id": video_id,
        "audio_duration_ms": int(round((doc.get("audio_duration_s") or 0) * 1000)),
        "transcript_provenance": {
            "model": doc.get("model"), "request_id": doc.get("request_id"),
            "kind": doc.get("kind"),
        },
        "sentences": sentences,
        "order": order,
        "frames": frames,                 # 帧表（含帧转录文本，若有）
        "orphan_frame_texts": orphans,    # 转录存在但帧不在本视频索引里（记账用）
        "words_by_sent": words_by_sent,   # 字级时间戳，供锚点精化用
    }


def make_chunks(corpus: dict, chunk_minutes: float = CHUNK_MINUTES,
                context_sentences: int = CONTEXT_SENTENCES) -> list[dict]:
    """按时间窗切分，返回带 owned/context 标记的分片列表。

    只把 **有内容的句子** 纳入 owned（空句在报告里单独统计，见 validator）。
    """
    content_sids = [sid for sid in corpus["order"] if corpus["sentences"][sid]["has_content"]]
    if not content_sids:
        return []

    window_ms = int(chunk_minutes * 60 * 1000)
    chunks: list[list[str]] = []
    current: list[str] = []
    window_start = corpus["sentences"][content_sids[0]]["start_ms"]
    for sid in content_sids:
        s = corpus["sentences"][sid]
        if current and (s["start_ms"] - window_start) >= window_ms:
            chunks.append(current)
            current, window_start = [], s["start_ms"]
        current.append(sid)
    if current:
        chunks.append(current)

    out = []
    pos = {sid: i for i, sid in enumerate(content_sids)}
    for ci, owned in enumerate(chunks):
        lo = pos[owned[0]] - context_sentences
        hi = pos[owned[-1]] + context_sentences
        ctx = content_sids[max(0, lo):hi + 1]
        out.append({
            "chunk_id": f"c{ci:03d}",
            "owned": owned,
            "context": [sid for sid in ctx if sid not in set(owned)],
            "first_ms": corpus["sentences"][owned[0]]["start_ms"],
            "last_ms": corpus["sentences"][owned[-1]]["end_ms"],
        })
    return out


def sent_key(text: str) -> str:
    """断言去重用的文本指纹（忽略空白）。"""
    norm = "".join(text.split())
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()[:16]
