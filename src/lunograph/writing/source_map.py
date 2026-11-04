"""Deterministic source map for the editorial brief.

This is a *view* over the consume index and edited text, not a new substrate
and not a model summary.  It gives the brief planner enough structure to see
the material's shape: sections, candidate anchors, numbers, frames, and the
places where the source is silent (speaker labels, topology, claim path).

Everything here is optional/unknown-tolerant: missing claims or speaker
labels must not become invented facts.
"""

from __future__ import annotations

import re
from typing import Any

from ..core.hashing import semantic_hash
from ..core.text import CAPTION_PROMPT_CHARS, truncate_caption

SCHEMA = "source-map-v1"
NUMBER = re.compile(r"(?<![0-9A-Za-z_.])\d+(?:\.\d+)?%?(?![0-9A-Za-z_.])")
CHANNEL_HINT = re.compile(
    r"(?m)^\s*(?P<channel>[^\n/|]{2,60}?)\s+"
    r"(?:bilibili|B站|哔哩哔哩)\s*$"
)
DATE = re.compile(r"(?<!\d)(20\d{2})[-/年](\d{1,2})[-/月](\d{1,2})")
VIEW_COUNT = re.compile(r"\d+(?:\.\d+)?\s*万|\d+\s*(?:播放|观看|views?)", re.I)
COMMENT_NOISE = ("回复", "评论", "弹幕", "LV", "lv", "@", "发消息")


def _channel_candidates(frames: list[dict[str, Any]]) -> dict[str, int]:
    """Return watermark channel candidates with their frame frequency.

    Frame OCR often repeats the same watermark; a one-off truncated OCR line
    (for example ``的编程宇宙 bilibili``) must not beat the repeated full
    ``轩辕的编程宇宙 bilibili`` line.
    """
    counts: dict[str, int] = {}
    for frame in frames:
        for match in CHANNEL_HINT.finditer(str(frame.get("caption", ""))):
            channel = match.group("channel").strip()
            if not channel:
                continue
            if channel.lower() in {"bilibili", "b 站", "哔哩哔哩"}:
                continue
            counts[channel] = counts.get(channel, 0) + 1
    return counts


def _channel_from_frames(frames: list[dict[str, Any]]) -> str:
    """Pick the most frequent, longest watermark channel, not the first hit.

    The result is still a hint from the video's own frame text, not an
    external lookup.  Callers should attribute it to the frame/watermark.
    """
    counts = _channel_candidates(frames)
    if not counts:
        return "unknown"
    candidates: list[tuple[int, int, str]] = []
    for channel, count in counts.items():
        # Drop a candidate that is only a suffix of a candidate seen at least
        # as often (the classic truncated OCR line).
        if any(
            channel != other
            and channel.endswith(other)
            and counts[other] >= count
            for other in counts
        ):
            continue
        candidates.append((count, len(channel), channel))
    if not candidates:
        return "unknown"
    candidates.sort(key=lambda item: (-item[0], -item[1], item[2]))
    return candidates[0][2]


def _frame_metadata(frames: list[dict[str, Any]]) -> dict[str, Any]:
    """Extract title/date/official hints from frame OCR.

    The video page in a frame often contains a title line, a view count, and
    a publish date.  Comment/UI lines can also contain dates, so only lines
    with a view count and without comment noise qualify.  Every candidate is
    a *hint*: it is stored with provenance and must be written as
    “画面显示/未核实”, never as an official link.
    """
    title_candidates: list[dict[str, Any]] = []
    date_candidates: list[dict[str, Any]] = []
    official_hints: list[dict[str, Any]] = []

    for frame in frames:
        caption = str(frame.get("caption", ""))
        frame_id = str(frame.get("frame_id", ""))
        lines = [line.strip() for line in caption.splitlines() if line.strip()]
        for index, line in enumerate(lines):
            date_match = DATE.search(line)
            if not date_match:
                continue
            noisy = any(token in line for token in COMMENT_NOISE)
            if not noisy and VIEW_COUNT.search(line):
                date_candidates.append(
                    {
                        "value": date_match.group(0),
                        "source": "frame_ocr",
                        "confidence": "medium",
                        "frame_id": frame_id,
                        "line": line[:160],
                    }
                )
                for back in range(index - 1, max(-1, index - 4), -1):
                    candidate = lines[back].strip()
                    if not candidate:
                        continue
                    if DATE.search(candidate) or any(
                        token in candidate for token in COMMENT_NOISE
                    ):
                        break
                    if len(candidate) <= 120:
                        title_candidates.append(
                            {
                                "value": candidate,
                                "source": "frame_ocr",
                                "confidence": "medium",
                                "frame_id": frame_id,
                            }
                        )
                    break
            if (
                not noisy
                and ("官方" in line or "团队" in line)
                and date_match
            ):
                official_hints.append(
                    {
                        "value": line[:200],
                        "source": "frame_ocr",
                        "confidence": "low",
                        "frame_id": frame_id,
                    }
                )

    def _dedupe(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        seen: set[str] = set()
        result: list[dict[str, Any]] = []
        for row in rows:
            value = str(row.get("value", "")).strip()
            if not value or value in seen:
                continue
            seen.add(value)
            result.append(row)
        return result

    title_candidates = _dedupe(title_candidates)
    date_candidates = _dedupe(date_candidates)
    official_hints = _dedupe(official_hints)
    return {
        "title": title_candidates[0] if title_candidates else None,
        "title_candidates": title_candidates[:3],
        "date": date_candidates[0] if date_candidates else None,
        "date_candidates": date_candidates[:3],
        "official_hints": official_hints[:3],
    }
ANCHOR_HINTS = (
    "为什么",
    "怎么",
    "但是",
    "因为",
    "所以",
    "第一次",
    "最后",
    "不知道",
    "意思是",
    "问题",
    "关键",
    "其实",
)


def _sections(edited_text: str) -> list[dict[str, Any]]:
    lines = edited_text.splitlines()
    sections: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for index, line in enumerate(lines, start=1):
        stripped = line.strip()
        if stripped.startswith("## "):
            if current:
                sections.append(current)
            current = {
                "heading": stripped[3:].strip(),
                "line_start": index,
                "line_end": index,
                "gist": "",
            }
        elif current is not None:
            current["line_end"] = index
            if not current["gist"] and stripped:
                current["gist"] = stripped[:160]
    if current:
        sections.append(current)
    if not sections and edited_text.strip():
        sections.append(
            {
                "heading": "",
                "line_start": 1,
                "line_end": len(lines),
                "gist": edited_text.strip().splitlines()[0][:160],
            }
        )
    return sections


def _score_sentence(text: str) -> int:
    score = 0
    if NUMBER.search(text):
        score += 3
    if any(quote in text for quote in ("“", "”", "「", "」", '"')):
        score += 2
    if 12 <= len(text) <= 180:
        score += 1
    score += sum(1 for hint in ANCHOR_HINTS if hint in text)
    return score


def _anchor_from_sentence(sentence: dict[str, Any]) -> dict[str, Any]:
    text = str(sentence.get("text", "")).strip()
    return {
        "id": str(sentence.get("sentence_id", "")),
        "quote_or_paraphrase": text,
        "span": {
            "t_start_ms": sentence.get("t_start_ms"),
            "t_end_ms": sentence.get("t_end_ms"),
            "segment_id": sentence.get("segment_id", ""),
        },
        "claim_type": "unknown",
        "speaker": "unknown",
        "relation": "unknown",
        "note": "auto-selected sentence; verify in source",
    }


def _anchor_from_claim(claim: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(claim.get("claim_id", "")),
        "quote_or_paraphrase": str(claim.get("text", "")).strip(),
        "span": {
            "t_start_ms": claim.get("t_start_ms"),
            "t_end_ms": claim.get("t_end_ms"),
            "segment_id": claim.get("segment_id", ""),
        },
        "claim_type": "unknown",
        "speaker": "unknown",
        "relation": "unknown",
        "note": f"claim status={claim.get('status', '')}; verify in source",
    }


def _anchor_from_evidence(evidence: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(evidence.get("evidence_id", "")),
        "quote_or_paraphrase": str(evidence.get("quote", "")).strip(),
        "span": {
            "t_start_ms": evidence.get("t_start_ms"),
            "t_end_ms": evidence.get("t_end_ms"),
            "sentence_ids": evidence.get("sentence_ids", []),
        },
        "claim_type": "unknown",
        "speaker": "unknown",
        "relation": "unknown",
        "note": "evidence quote; verify speaker/context in source",
    }


def _numbers_from_sentences(
    sentences: list[dict[str, Any]], *, limit: int = 30
) -> list[dict[str, Any]]:
    """Keep every meaningful occurrence, not just the first value.

    The same value can mean different things in different sentences (e.g. two
    conflicting follower counts).  The ledger keeps the sentence identity so
    the brief/writer can see the conflict instead of silently collapsing it.
    """
    numbers: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for sentence in sentences:
        text = str(sentence.get("text", ""))
        sentence_id = str(sentence.get("sentence_id", ""))
        for match in NUMBER.finditer(text):
            value = match.group(0)
            key = (value, sentence_id)
            if key in seen:
                continue
            seen.add(key)
            start = max(0, match.start() - 36)
            end = min(len(text), match.end() + 36)
            numbers.append(
                {
                    "value": value,
                    "span": {
                        "t_start_ms": sentence.get("t_start_ms"),
                        "t_end_ms": sentence.get("t_end_ms"),
                        "sentence_id": sentence_id,
                    },
                    "context": text[start:end].strip(),
                    "metric": "unknown",
                    "task": "unknown",
                    "baseline": "unknown",
                    "status": "video_claim",
                    "verification": "unverified",
                }
            )
            if len(numbers) >= limit:
                return numbers
    return numbers


def build_source_map(
    index: dict[str, Any],
    edited_text: str,
    *,
    max_anchors: int = 30,
    max_numbers: int = 30,
    max_frames: int = 20,
) -> dict[str, Any]:
    """Build a flexible source-map-v1 view; deterministic, no model."""
    sentences = [row for row in index.get("sentences", []) if isinstance(row, dict)]
    claims = [row for row in index.get("claims", []) if isinstance(row, dict)]
    evidence = [row for row in index.get("evidence", []) if isinstance(row, dict)]
    frames = [row for row in index.get("frames", []) if isinstance(row, dict)]

    anchors: list[dict[str, Any]] = []
    seen_texts: set[str] = set()

    def add(anchor: dict[str, Any]) -> None:
        text = str(anchor.get("quote_or_paraphrase", "")).strip()
        if not text or text in seen_texts or len(anchors) >= max_anchors:
            return
        seen_texts.add(text)
        anchors.append(anchor)

    for claim in claims:
        add(_anchor_from_claim(claim))
    for item in evidence:
        add(_anchor_from_evidence(item))

    ranked = sorted(
        sentences,
        key=lambda sentence: (-_score_sentence(str(sentence.get("text", ""))), sentence.get("t_start_ms") or 0),
    )
    for sentence in ranked:
        add(_anchor_from_sentence(sentence))

    selected_frames = [
        frame
        for frame in frames
        if frame.get("selected") or frame.get("caption")
    ][:max_frames]
    frame_rows = []
    for frame in selected_frames:
        caption, caption_full_chars, caption_truncated = truncate_caption(
            str(frame.get("caption", "")), CAPTION_PROMPT_CHARS
        )
        frame_rows.append(
            {
                "frame_id": frame.get("frame_id", ""),
                "t_ms": frame.get("t_ms"),
                "caption": caption,
                "caption_full_chars": caption_full_chars,
                "caption_truncated": caption_truncated,
                "file": frame.get("file", ""),
                "capture_method": frame.get("capture_method", ""),
                "provenance": "video_frame",
            }
        )

    metadata = _frame_metadata(frames)
    channel = _channel_from_frames(frames)
    title_row = metadata.get("title")
    date_row = metadata.get("date")
    official_hints = metadata.get("official_hints") or []
    title = str(title_row.get("value")) if isinstance(title_row, dict) else "unknown"
    date = str(date_row.get("value")) if isinstance(date_row, dict) else "unknown"

    missing: list[str] = []
    if title == "unknown":
        missing.append("title")
    if channel == "unknown":
        missing.append("channel")
    if date == "unknown":
        missing.append("date")
    # A link/official document is a URL, not an OCR hint; keep them missing
    # even when a frame shows an announcement.
    missing.extend(["link", "official_docs"])

    gaps: list[str] = []
    if not claims:
        gaps.append("claim_path_absent")
    if not evidence:
        gaps.append("evidence_path_absent")
    gaps.append("speaker_labels_absent")
    gaps.append("topology_inferred_unknown")
    if channel != "unknown":
        gaps.append("channel_from_frame_watermark")
    if title != "unknown":
        gaps.append("title_from_frame_ocr")
    if date != "unknown":
        gaps.append("date_from_frame_ocr")
    if official_hints:
        gaps.append("official_hint_from_frame_ocr")
    if not any(
        value != "unknown" for value in (title, channel, date)
    ) and not official_hints:
        gaps.append("source_metadata_absent")

    duration_ms = max(
        (int(segment.get("t_end_ms", 0)) for segment in index.get("segments", [])),
        default=0,
    )
    source_metadata = {
        "channel": {
            "value": channel,
            "source": "frame_watermark" if channel != "unknown" else "unknown",
            "confidence": "high" if channel != "unknown" else "unknown",
        },
        "title": title_row
        or {"value": "unknown", "source": "unknown", "confidence": "unknown"},
        "date": date_row
        or {"value": "unknown", "source": "unknown", "confidence": "unknown"},
        "official_hints": official_hints,
        "unverified": True,
        "note": "frame OCR/watermark hints; write as 画面显示/未核实, never as an official link",
    }
    provenance = {
        "video_id": str(index.get("video_id", "")),
        "source_type": "video",
        "duration_ms": duration_ms,
        "title": title,
        "channel": channel,
        "date": date,
        "link": "unknown",
        "official": [],
        "missing": missing,
        "frame_provenance": "video_frame",
    }

    payload = {
        "schema_version": SCHEMA,
        "topology": "unknown",
        "video_id": str(index.get("video_id", "")),
        "text_chars": len(edited_text),
        "segment_count": len(index.get("segments", [])),
        "part_count": len(index.get("parts", [])),
        "claim_count": len(claims),
        "evidence_count": len(evidence),
        "sentence_count": len(sentences),
        "sections": _sections(edited_text),
        "anchors": anchors,
        "numbers": _numbers_from_sentences(sentences, limit=max_numbers),
        "frames": frame_rows,
        "source_metadata": source_metadata,
        "provenance": provenance,
        "gaps": gaps,
        "source_map_hash": "",
    }
    payload["source_map_hash"] = semantic_hash(
        {key: value for key, value in payload.items() if key != "source_map_hash"},
        drop_volatile=False,
    )
    return payload
