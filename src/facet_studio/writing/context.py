"""Deterministic profile selection and working-context assembly.

Profile selection is code, not a model decision.  The Writer never browses
the corpus; it receives one assembled working context (or one part at a time).
No model calls.
"""

from __future__ import annotations

import json
from typing import Any

from ..core.hashing import semantic_hash
from ..core.tokens import estimate_text_tokens
from ..evidence_access import visual_lookup

DEFAULT_CONTEXT_BUDGET_TOKENS = 30_000
DEFAULT_SEGMENT_THRESHOLD = 24
DEFAULT_LONG_MS = 30 * 60 * 1000
PROFILES = {"full_text", "claim_lean", "index_parts", "sectioned", "multi_source"}


def measure_text(index: dict[str, Any], edited_text: str | None) -> dict[str, Any]:
    text = edited_text or ""
    segments = index.get("segments", [])
    duration_ms = max(
        (int(segment.get("t_end_ms", 0)) for segment in segments), default=0
    )
    return {
        "chars": len(text),
        "est_tokens": estimate_text_tokens(text),
        "segments": len(segments),
        "claims": len(index.get("claims", [])),
        "frames": len(index.get("frames", [])),
        "duration_ms": duration_ms,
    }


def select_profile(
    request: dict[str, Any],
    index: dict[str, Any],
    edited_text: str | None,
    *,
    skill: dict[str, Any] | None = None,
    context_budget_tokens: int = DEFAULT_CONTEXT_BUDGET_TOKENS,
    segment_threshold: int = DEFAULT_SEGMENT_THRESHOLD,
    long_ms: int = DEFAULT_LONG_MS,
) -> dict[str, Any]:
    """Choose a consumption profile from request + measured evidence size.

    Returns a decision record; ``profile`` is one of ``full_text``,
    ``claim_lean``, ``index_parts``, ``sectioned``, ``multi_source``.
    ``deferred`` marks profiles not implemented in P0 (sectioned/multi_source).
    """
    measured = measure_text(index, edited_text)
    video_ids = request.get("video_ids") or []
    audit_level = request.get("audit_level", "none")
    risk_level = request.get("risk_level", "low")
    sections_required = int(request.get("sections_required", 1) or 1)
    has_claims = bool(index.get("claims"))
    notes: list[str] = []
    claim_unavailable = False
    deferred = False

    override = request.get("profile_override")
    if override in PROFILES:
        profile = override
        basis = "profile_override"
        if profile == "claim_lean" and not has_claims:
            claim_unavailable = True
            notes.append("claim_lean requested but consume-index has no claims")
        if profile in {"sectioned", "multi_source"}:
            deferred = True
            notes.append(f"{profile} is deferred in P0")
        return {
            "profile": profile,
            "basis": basis,
            "measured": measured,
            "notes": notes,
            "claim_unavailable": claim_unavailable,
            "deferred": deferred,
        }

    if len(video_ids) > 1:
        return {
            "profile": "multi_source",
            "basis": "multiple_video_ids",
            "measured": measured,
            "notes": ["multi_source is deferred in P0"],
            "claim_unavailable": False,
            "deferred": True,
        }

    if audit_level in {"claim", "boundary", "reuse"} or risk_level == "high":
        if has_claims:
            return {
                "profile": "claim_lean",
                "basis": f"audit_level={audit_level}, risk_level={risk_level}",
                "measured": measured,
                "notes": [],
                "claim_unavailable": False,
                "deferred": False,
            }
        notes.append("claim/audit requested but no claims; fallback to full_text")
        return {
            "profile": "full_text",
            "basis": "claim_unavailable_fallback",
            "measured": measured,
            "notes": notes,
            "claim_unavailable": True,
            "deferred": False,
        }

    if sections_required > 1 or measured["duration_ms"] > long_ms:
        return {
            "profile": "sectioned",
            "basis": (
                f"sections_required={sections_required}, "
                f"duration_ms={measured['duration_ms']}"
            ),
            "measured": measured,
            "notes": ["sectioned is deferred in P0; use index_parts/full_text explicitly"],
            "claim_unavailable": False,
            "deferred": True,
        }

    if measured["est_tokens"] <= context_budget_tokens:
        return {
            "profile": "full_text",
            "basis": (
                f"est_tokens={measured['est_tokens']} <= "
                f"budget={context_budget_tokens}"
            ),
            "measured": measured,
            "notes": [],
            "claim_unavailable": False,
            "deferred": False,
        }

    if (
        measured["est_tokens"] > context_budget_tokens
        or measured["segments"] > segment_threshold
    ):
        return {
            "profile": "index_parts",
            "basis": (
                f"est_tokens={measured['est_tokens']} > "
                f"budget={context_budget_tokens} or "
                f"segments={measured['segments']} > {segment_threshold}"
            ),
            "measured": measured,
            "notes": [],
            "claim_unavailable": False,
            "deferred": False,
        }

    return {
        "profile": "full_text",
        "basis": "default",
        "measured": measured,
        "notes": [],
        "claim_unavailable": False,
        "deferred": False,
    }


def _working_frames(
    index: dict[str, Any], *, max_frames: int = 24
) -> list[dict[str, Any]]:
    frames = index.get("frames", [])
    selected = [frame for frame in frames if frame.get("selected")]
    if not selected:
        selected = [frame for frame in frames if frame.get("caption")]
    rows = []
    for frame in selected[:max_frames]:
        caption = frame.get("caption", "") or ""
        rows.append(
            {
                "frame_id": frame.get("frame_id", ""),
                "t_ms": frame.get("t_ms"),
                "file": frame.get("file", ""),
                "caption": caption,
                "capture_method": frame.get("capture_method", "none"),
                "caption_truncated": bool(
                    frame.get("caption_full_chars")
                    and frame.get("caption_full_chars") > len(caption)
                ),
                "segment_ids": list(frame.get("segment_ids", [])),
            }
        )
    return rows


def _visual_opportunities(
    index: dict[str, Any], *, max_items: int = 8
) -> list[dict[str, Any]]:
    opportunities: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for segment in index.get("segments", []):
        segment_id = segment.get("segment_id", "")
        result = visual_lookup(index, segment_id=segment_id)
        for candidate in result.get("candidates", []):
            kind = candidate.get("kind", "")
            if kind == "no_visual":
                continue
            key = (segment_id, kind)
            if key in seen:
                continue
            seen.add(key)
            opportunities.append(
                {
                    "segment_id": segment_id,
                    "kind": kind,
                    "reason": candidate.get("reason", ""),
                    "evidence_ids": list(candidate.get("evidence_ids", [])),
                    "frame_ids": (
                        [candidate["frame_id"]]
                        if candidate.get("frame_id")
                        else []
                    ),
                }
            )
            if len(opportunities) >= max_items:
                return opportunities
    return opportunities


def _claim_context(
    claim: dict[str, Any],
    sentences_by_segment: dict[str, list[dict[str, Any]]],
    *,
    neighbor: int = 1,
    max_sentences: int = 6,
) -> list[str]:
    segment_sentences = sentences_by_segment.get(claim.get("segment_id", ""), [])
    claim_sentence_ids = set(claim.get("sentence_ids", []))
    if not segment_sentences:
        return []
    if claim_sentence_ids:
        indices = [
            index
            for index, sentence in enumerate(segment_sentences)
            if sentence.get("sentence_id") in claim_sentence_ids
        ]
        selected: list[str] = []
        for center in indices:
            lo = max(0, center - neighbor)
            hi = min(len(segment_sentences), center + neighbor + 1)
            for sentence in segment_sentences[lo:hi]:
                text = sentence.get("text", "")
                if text and text not in selected:
                    selected.append(text)
                if len(selected) >= max_sentences:
                    return selected
        return selected
    lo = int(claim.get("t_start_ms", 0))
    hi = int(claim.get("t_end_ms", lo))
    return [
        sentence.get("text", "")
        for sentence in segment_sentences
        if int(sentence.get("t_end_ms", 0)) >= lo
        and int(sentence.get("t_start_ms", 0)) <= hi
    ][:max_sentences]


def _claim_rows(index: dict[str, Any]) -> list[dict[str, Any]]:
    sentences_by_segment: dict[str, list[dict[str, Any]]] = {}
    for sentence in index.get("sentences", []):
        sentences_by_segment.setdefault(sentence.get("segment_id", ""), []).append(
            sentence
        )
    for rows in sentences_by_segment.values():
        rows.sort(key=lambda row: (row.get("t_start_ms", 0), row.get("sentence_id", "")))
    claims = []
    for claim in index.get("claims", []):
        claims.append(
            {
                "claim_id": claim.get("claim_id", ""),
                "text": claim.get("text", ""),
                "status": claim.get("status", ""),
                "kind": claim.get("kind", ""),
                "scope": claim.get("scope", ""),
                "t_start_ms": claim.get("t_start_ms"),
                "t_end_ms": claim.get("t_end_ms"),
                "evidence_ids": list(claim.get("evidence_ids", [])),
                "sentence_ids": list(claim.get("sentence_ids", [])),
                "part_id": claim.get("part_id"),
                "context": _claim_context(claim, sentences_by_segment),
            }
        )
    return claims


def build_working_context(
    index: dict[str, Any],
    request: dict[str, Any],
    edited_text: str | None,
    *,
    profile: str = "auto",
    skill: dict[str, Any] | None = None,
    context_budget_tokens: int = DEFAULT_CONTEXT_BUDGET_TOKENS,
    segment_threshold: int = DEFAULT_SEGMENT_THRESHOLD,
    long_ms: int = DEFAULT_LONG_MS,
) -> dict[str, Any]:
    """Build the Writer-facing working context for one profile.

    ``profile="auto"`` calls :func:`select_profile`; explicit profiles are
    recorded and still validated.  ``sectioned``/``multi_source`` are
    explicitly unsupported in P0 (status ``unsupported_profile``).
    """
    if profile == "auto":
        selection = select_profile(
            request,
            index,
            edited_text,
            skill=skill,
            context_budget_tokens=context_budget_tokens,
            segment_threshold=segment_threshold,
            long_ms=long_ms,
        )
        chosen = selection["profile"]
    else:
        if profile not in PROFILES:
            raise ValueError(f"unknown profile: {profile}")
        selection = {
            "profile": profile,
            "basis": "explicit",
            "measured": measure_text(index, edited_text),
            "notes": [],
            "claim_unavailable": False,
            "deferred": profile in {"sectioned", "multi_source"},
        }
        chosen = profile

    if chosen in {"sectioned", "multi_source"}:
        return {
            "schema_version": "working-context-v1",
            "status": "unsupported_profile",
            "profile": chosen,
            "selection": selection,
            "text": "",
            "parts": [],
            "claims": [],
            "frames": [],
            "visual_opportunities": [],
            "budget": {
                "context_budget_tokens": context_budget_tokens,
                "actual_tokens": 0,
                "over_budget": False,
            },
            "coverage": {},
            "context_hash": "",
        }

    claims: list[dict[str, Any]] = []
    parts: list[dict[str, Any]] = []
    text = ""
    if chosen == "full_text":
        text = edited_text or ""
    elif chosen == "claim_lean":
        claims = _claim_rows(index)
    elif chosen == "index_parts":
        parts = [
            {
                "part_id": part.get("part_id", ""),
                "segment_ids": list(part.get("segment_ids", [])),
                "chars": part.get("chars", 0),
                "oversize": bool(part.get("oversize", False)),
                "text_start": part.get("text_start"),
                "text_end": part.get("text_end"),
            }
            for part in index.get("parts", [])
        ]

    frames = _working_frames(index)
    visual_opportunities = _visual_opportunities(index)

    if chosen == "full_text":
        payload_for_budget = text
    elif chosen == "claim_lean":
        payload_for_budget = json.dumps(
            {"claims": claims, "frames": frames}, ensure_ascii=False
        )
    else:
        payload_for_budget = json.dumps(parts, ensure_ascii=False)
    actual_tokens = estimate_text_tokens(payload_for_budget)
    segments_total = len(index.get("segments", []))
    claims_total = len(index.get("claims", []))
    sentences_total = len(index.get("sentences", []))
    frames_total = len(index.get("frames", []))
    coverage = {
        "segments_total": segments_total,
        "segments_used": segments_total,
        "claims_total": claims_total,
        "claims_used": len(claims),
        "sentences_total": sentences_total,
        "sentences_used": len(claims) and sum(
            len(claim.get("context", [])) for claim in claims
        ),
        "frames_total": frames_total,
        "frames_used": len(frames),
        "unreported": list(index.get("coverage", {}).get("unassigned_blocks", [])),
    }
    context: dict[str, Any] = {
        "schema_version": "working-context-v1",
        "status": "complete",
        "profile": chosen,
        "selection": selection,
        "text": text,
        "parts": parts,
        "claims": claims,
        "frames": frames,
        "visual_opportunities": visual_opportunities,
        "budget": {
            "context_budget_tokens": context_budget_tokens,
            "actual_tokens": actual_tokens,
            "over_budget": actual_tokens > context_budget_tokens,
            "excess_tokens": max(0, actual_tokens - context_budget_tokens),
        },
        "coverage": coverage,
        "source_map_ref": None,
        "context_hash": "",
    }
    payload = dict(context)
    payload.pop("context_hash", None)
    context["context_hash"] = semantic_hash(payload, drop_volatile=False)
    return context
