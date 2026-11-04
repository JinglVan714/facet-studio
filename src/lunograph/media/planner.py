"""Model-assisted visual planner with deterministic validation.

The planner proposes at most a few visuals per article.  Code validates every
frame ID, number, node/edge and source ID before anything is rendered; an
unsupported visual is skipped with a reason, never silently rendered.
"""

from __future__ import annotations

import json
import re
from dataclasses import replace
from pathlib import Path
from typing import Any

from ..core.config import get_settings
from ..core.hashing import semantic_hash
from ..core.jsonutil import StructuredOutputError, extract_json_object
from ..core.text import CAPTION_PROMPT_CHARS, truncate_caption
from ..providers.llm import CachedLLM, DeepSeekLLM, ProviderError
from ..runtime.budget import BudgetPolicy, BudgetState
from .sections import section_text, split_article

SCHEMA = "visual-plan-v1"
NUMBER = re.compile(r"(?<![0-9A-Za-z_.])\d+(?:\.\d+)?%?(?![0-9A-Za-z_.])")
IDENTIFIER = re.compile(r"\b[A-Za-z][A-Za-z0-9]*_[A-Za-z0-9_]+\b")
STATUSES = {"measured", "hypothesis", "demo", "illustration", "unknown"}

SYSTEM = """You are the visual planner for a reader-first video article. You receive article sections, selected frames, claims and evidence. Choose at most a few visuals that materially help a reader understand; prefer tables for comparisons/categories, charts for numbers, diagrams for process/causal/architecture, and real frames only when the frame actually shows the operation/result/claim and is readable.

Return one JSON object:
{"visuals":[{"section_index":0,"kind":"diagram|chart|table|real_frame|none","status":"measured|hypothesis|demo|illustration|unknown","intent":"...","caption":"看哪里","diagram":{"nodes":[{"id":"n1","label":"..."}],"edges":[{"from":"n1","to":"n2","label":"..."}]},"chart":{"type":"bar|line","title":"...","data":[{"label":"...","value":0.0}],"unit":null},"table":{"title":"...","columns":["..."],"rows":[["..."]]},"frame_id":"...","source_ids":["..."]}]}

Rules:
- Every number in a chart/table must appear in the provided evidence.
- Every frame_id must be one of the provided frames.
- Diagram nodes/edges must be grounded in the article/evidence; do not invent relations.
- `status` is required for chart/table/diagram: use `hypothesis` for an assumed example, `demo` for a single run/observation, `illustration` for a schematic, `measured` only if the video reports a measurement. Use `unknown` if unsure.
- If a section already has a Markdown table (has_table=true), do not propose another table; choose a diagram/chart only if it adds something, or no_visual.
- If planned_visuals is present, treat it as the writing plan's visual slots: use the same section_index and prefer the planned kind; if the planned kind cannot be grounded in the evidence, choose another grounded visual or none. Do not add more than one unplanned visual.
- Respect `max_visuals`. If `genre` is `narrative` or `mixed` (interview, conversation, story), choose at most 2 visuals total; do not add section-summary diagrams; prefer a real frame or a dialogue/quote visual. If `genre` is `analytical` or `procedural`, prefer charts, real frames, or diagrams that add information rather than restating the prose.
- Prefer at least one diagram for a process/mechanism section when it materially helps; do not fill every section.
- caption is a "look here" cue, not a summary.
- The caption must describe only what the visual itself shows; do not use it to assert a number, ranking, or mechanism the image/table/chart does not display.
- For `hypothesis`/`illustration`/`demo`, the caption must say 假设/示意/单次演示; do not call it 数据/实测/基准. Never imply a benchmark the video did not run.
- Use no_visual when no visual helps; do not force a bad frame.
- source_ids are audit-only; do not put IDs in captions.
"""


def _write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(value, str):
        path.write_text(value, encoding="utf-8")
    else:
        path.write_text(
            json.dumps(value, ensure_ascii=False, indent=1), encoding="utf-8"
        )


def _candidate_payload(index: dict[str, Any], *, max_frames: int = 24) -> dict[str, Any]:
    frames = index.get("frames", [])
    selected = [frame for frame in frames if frame.get("selected")]
    if not selected:
        selected = [frame for frame in frames if frame.get("caption")]
    frame_rows = []
    for frame in selected[:max_frames]:
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
                "segment_ids": frame.get("segment_ids", []),
            }
        )
    return {
        "frames": frame_rows,
        "claims": [
            {
                "claim_id": claim.get("claim_id", ""),
                "text": claim.get("text", ""),
                "status": claim.get("status", ""),
                "scope": claim.get("scope", ""),
                "t_start_ms": claim.get("t_start_ms"),
                "t_end_ms": claim.get("t_end_ms"),
            }
            for claim in index.get("claims", [])
        ],
        "evidence": [
            {
                "evidence_id": evidence.get("evidence_id", ""),
                "claim_ids": evidence.get("claim_ids", []),
                "quote": evidence.get("quote", ""),
                "t_start_ms": evidence.get("t_start_ms"),
                "t_end_ms": evidence.get("t_end_ms"),
            }
            for evidence in index.get("evidence", [])
        ],
    }


def _allowed_ids(index: dict[str, Any]) -> set[str]:
    ids = {frame.get("frame_id", "") for frame in index.get("frames", [])}
    ids |= {claim.get("claim_id", "") for claim in index.get("claims", [])}
    ids |= {evidence.get("evidence_id", "") for evidence in index.get("evidence", [])}
    return {value for value in ids if value}


def _evidence_numbers(index: dict[str, Any]) -> set[str]:
    values: set[str] = set()
    for claim in index.get("claims", []):
        values.update(NUMBER.findall(claim.get("text", "")))
    for evidence in index.get("evidence", []):
        values.update(NUMBER.findall(evidence.get("quote", "")))
    for sentence in index.get("sentences", []):
        values.update(NUMBER.findall(sentence.get("text", "")))
    for frame in index.get("frames", []):
        values.update(NUMBER.findall(frame.get("caption", "")))
    return values


def _valid_number(value: Any, allowed: set[str]) -> bool:
    return str(value).strip() in allowed


def _allowed_text(index: dict[str, Any], sections: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for sentence in index.get("sentences", []):
        parts.append(str(sentence.get("text", "")))
    for claim in index.get("claims", []):
        parts.append(str(claim.get("text", "")))
    for evidence in index.get("evidence", []):
        parts.append(str(evidence.get("quote", "")))
    return "\n".join(parts)


def _bad_identifier(text: str, allowed_text: str) -> str:
    for token in IDENTIFIER.findall(str(text)):
        if token not in allowed_text:
            return token
    return ""


def _validate(
    payload: dict[str, Any],
    *,
    sections: list[dict[str, Any]],
    index: dict[str, Any],
    max_visuals: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    allowed_ids = _allowed_ids(index)
    allowed_numbers = _evidence_numbers(index)
    allowed_text = _allowed_text(index, sections)
    frame_ids = {frame.get("frame_id", "") for frame in index.get("frames", [])}
    visuals: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    raw_visuals = payload.get("visuals")
    if not isinstance(raw_visuals, list):
        return [], [{"reason": "visuals_not_list"}]
    for raw in raw_visuals:
        if len(visuals) >= max_visuals:
            skipped.append({"reason": "max_visuals", "raw": raw})
            continue
        if not isinstance(raw, dict):
            skipped.append({"reason": "invalid_visual", "raw": raw})
            continue
        kind = str(raw.get("kind", "none"))
        if kind == "none":
            continue
        try:
            section_index = int(raw.get("section_index", -1))
        except (TypeError, ValueError):
            section_index = -1
        if section_index < 0 or section_index >= len(sections):
            skipped.append({"reason": "bad_section_index", "raw": raw})
            continue
        caption = str(raw.get("caption", "")).strip() or "看这里"
        source_ids = [
            value for value in raw.get("source_ids", []) if value in allowed_ids
        ]
        status = str(raw.get("status", "unknown")).strip().lower()
        if status not in STATUSES:
            status = "unknown"
        row: dict[str, Any] = {
            "section_index": section_index,
            "kind": kind,
            "status": status,
            "intent": str(raw.get("intent", "")).strip(),
            "caption": caption,
            "source_ids": source_ids,
        }
        if kind == "real_frame":
            frame_id = str(raw.get("frame_id", ""))
            if frame_id not in frame_ids:
                skipped.append({"reason": "unknown_frame", "frame_id": frame_id})
                continue
            row["frame_id"] = frame_id
        elif kind == "chart":
            chart = raw.get("chart") if isinstance(raw.get("chart"), dict) else {}
            data = chart.get("data")
            if not isinstance(data, list) or not data:
                skipped.append({"reason": "empty_chart"})
                continue
            clean_data = []
            ok = True
            for item in data:
                if not isinstance(item, dict) or "value" not in item:
                    ok = False
                    break
                if not _valid_number(item.get("value"), allowed_numbers):
                    ok = False
                    break
                clean_data.append(
                    {
                        "label": str(item.get("label", "")),
                        "value": item.get("value"),
                    }
                )
            if not ok:
                skipped.append({"reason": "chart_number_not_in_evidence"})
                continue
            row["chart"] = {
                "type": str(chart.get("type", "bar")),
                "title": str(chart.get("title", "")),
                "unit": chart.get("unit"),
                "data": clean_data,
            }
        elif kind == "table":
            section_text_value = section_text(sections[section_index])
            if "\n|" in section_text_value or section_text_value.lstrip().startswith("|"):
                skipped.append({"reason": "section_has_table"})
                continue
            table = raw.get("table") if isinstance(raw.get("table"), dict) else {}
            columns = table.get("columns")
            rows = table.get("rows")
            if not isinstance(columns, list) or not isinstance(rows, list) or not rows:
                skipped.append({"reason": "empty_table"})
                continue
            clean_rows = []
            ok = True
            bad_identifier = ""
            for values in rows:
                if not isinstance(values, list):
                    ok = False
                    break
                for value in values:
                    if NUMBER.fullmatch(str(value).strip()) and not _valid_number(
                        value, allowed_numbers
                    ):
                        ok = False
                        break
                    bad_identifier = _bad_identifier(str(value), allowed_text)
                    if bad_identifier:
                        ok = False
                        break
                if not ok:
                    break
                clean_rows.append([str(value) for value in values])
            if not ok:
                reason = (
                    "identifier_not_in_evidence"
                    if bad_identifier
                    else "table_number_not_in_evidence"
                )
                skipped.append({"reason": reason})
                continue
            row["table"] = {
                "title": str(table.get("title", "")),
                "columns": [str(value) for value in columns],
                "rows": clean_rows,
            }
        elif kind == "diagram":
            diagram = raw.get("diagram") if isinstance(raw.get("diagram"), dict) else {}
            nodes = diagram.get("nodes")
            edges = diagram.get("edges", [])
            if not isinstance(nodes, list) or not nodes:
                skipped.append({"reason": "empty_diagram"})
                continue
            clean_nodes = []
            node_ids: set[str] = set()
            for node in nodes:
                if not isinstance(node, dict):
                    continue
                node_id = str(node.get("id", ""))
                label = str(node.get("label", ""))
                if not node_id or not label:
                    continue
                bad_identifier = _bad_identifier(label, allowed_text)
                if bad_identifier:
                    break
                clean_nodes.append({"id": node_id, "label": label})
                node_ids.add(node_id)
            if not clean_nodes:
                skipped.append({"reason": "invalid_nodes"})
                continue
            if len(clean_nodes) != len(nodes):
                skipped.append({"reason": "identifier_not_in_evidence"})
                continue
            clean_edges = []
            for edge in edges if isinstance(edges, list) else []:
                if not isinstance(edge, dict):
                    continue
                start = str(edge.get("from", ""))
                end = str(edge.get("to", ""))
                if start in node_ids and end in node_ids:
                    label = str(edge.get("label", ""))
                    if _bad_identifier(label, allowed_text):
                        continue
                    clean_edges.append(
                        {
                            "from": start,
                            "to": end,
                            "label": label,
                        }
                    )
            row["diagram"] = {"nodes": clean_nodes, "edges": clean_edges}
        else:
            skipped.append({"reason": "unknown_kind", "kind": kind})
            continue
        visuals.append(row)
    return visuals, skipped


def _planned_visuals(writing_plan: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Project the writing plan's visual slots into the visual planner payload."""
    if not writing_plan:
        return []
    planned: list[dict[str, Any]] = []
    for fallback, section in enumerate(writing_plan.get("toc", []), start=1):
        if not isinstance(section, dict):
            continue
        visual = section.get("visual") if isinstance(section.get("visual"), dict) else {}
        kind = str(visual.get("kind", "none"))
        if kind == "none":
            continue
        try:
            index = int(section.get("index", fallback))
        except (TypeError, ValueError):
            index = fallback
        planned.append(
            {
                "section_index": index,
                "heading": str(section.get("heading", "")),
                "kind": kind,
                "intent": str(visual.get("intent", "")),
            }
        )
    return planned


def plan_visuals(
    article: str,
    index: dict[str, Any],
    request: dict[str, Any],
    out_dir: Path,
    *,
    run: bool = False,
    provider: Any | None = None,
    max_visuals: int | None = None,
    genre: str = "",
    model: str | None = None,
    temperature: float = 0.0,
    max_tokens: int = 16384,
    writing_plan: dict[str, Any] | None = None,
) -> dict[str, Any]:
    out_dir = Path(out_dir)
    try:
        requested_max = int((request.get("media_policy") or {}).get("max_assets") or 6)
    except (TypeError, ValueError):
        requested_max = 6
    if requested_max < 1:
        requested_max = 6
    if max_visuals is None:
        max_visuals = requested_max
    else:
        max_visuals = max(1, min(int(max_visuals), requested_max))
    title, sections = split_article(article)
    section_payload = []
    for section in sections:
        text = section_text(section)
        section_payload.append(
            {
                "index": section["index"],
                "heading": section.get("heading", ""),
                "text": text,
                "has_table": "\n|" in text or text.lstrip().startswith("|"),
            }
        )
    if not run:
        return {
            "schema_version": SCHEMA,
            "status": "dry_run",
            "visuals": [],
            "skipped": [],
            "max_visuals": max_visuals,
            "genre": genre,
            "sections": [
                {"index": item["index"], "heading": item["heading"]}
                for item in section_payload
            ],
        }

    payload = _candidate_payload(index)
    payload["article_title"] = title
    payload["sections"] = section_payload
    payload["max_visuals"] = max_visuals
    payload["genre"] = genre
    payload["media_policy"] = request.get("media_policy") or {}
    planned_visuals = _planned_visuals(writing_plan)
    if planned_visuals:
        payload["planned_visuals"] = planned_visuals
    user = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    system_path = out_dir / "prompts" / "visual_planner.system.txt"
    user_path = out_dir / "prompts" / "visual_planner.user.txt"
    _write(system_path, SYSTEM)
    _write(user_path, user)

    usage: dict[str, Any] = {}
    latency_ms = 0
    cached = False
    finish_reason = None
    try:
        if provider is None:
            settings = get_settings()
            if model:
                settings = replace(settings, model=model)
            if not settings.provider_configured:
                return {
                    "schema_version": SCHEMA,
                    "status": "provider_unconfigured",
                    "visuals": [],
                    "skipped": [],
                }
            llm_calls_path = out_dir / "llm_calls.jsonl"
            llm_calls_path.write_text("", encoding="utf-8")

            def call_sink(record: dict[str, Any]) -> None:
                with llm_calls_path.open("a", encoding="utf-8") as handle:
                    handle.write(json.dumps(record, ensure_ascii=False) + "\n")

            budget = BudgetState(
                BudgetPolicy(max_calls=1, max_tokens=max_tokens + 20000)
            )
            inner = DeepSeekLLM(settings, budget=budget, call_sink=call_sink)
            cache_dir = settings.runs_root / "_cache" / "llm"
            provider = CachedLLM(inner, cache_dir, call_sink=call_sink)
            model_name = settings.model
        else:
            model_name = getattr(provider, "model", model or "injected")
        key = semantic_hash(
            {
                "article": article,
                "index_hash": index.get("index_hash", ""),
                "system": SYSTEM,
                "user": user,
                "model": model_name,
            },
            drop_volatile=False,
        )
        response = provider.complete(
            stage="visual_planner",
            key=key,
            system=SYSTEM,
            user=user,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        raw = getattr(response, "text", str(response))
        _write(out_dir / "raw_response.txt", raw)
        usage_obj = getattr(response, "usage", None)
        if usage_obj is not None and hasattr(usage_obj, "as_dict"):
            usage = usage_obj.as_dict()
        latency_ms = int(getattr(response, "latency_ms", 0) or 0)
        cached = bool(getattr(response, "cached", False))
        finish_reason = getattr(response, "finish_reason", None)
        parsed = extract_json_object(raw)
    except ProviderError as exc:
        return {
            "schema_version": SCHEMA,
            "status": "provider_error",
            "error": {"kind": exc.kind, "message": str(exc)},
            "visuals": [],
            "skipped": [],
        }
    except (StructuredOutputError, ValueError) as exc:
        return {
            "schema_version": SCHEMA,
            "status": "invalid_output",
            "error": str(exc),
            "visuals": [],
            "skipped": [],
        }

    visuals, skipped = _validate(
        parsed,
        sections=sections,
        index=index,
        max_visuals=max_visuals,
    )
    plan = {
        "schema_version": SCHEMA,
        "status": "complete" if visuals else "no_visuals",
        "visuals": visuals,
        "skipped": skipped,
        "max_visuals": max_visuals,
        "genre": genre,
        "sections": [
            {"index": item["index"], "heading": item["heading"]}
            for item in section_payload
        ],
        "usage": usage,
        "model": model_name,
        "latency_ms": latency_ms,
        "cached": cached,
        "finish_reason": finish_reason,
    }
    _write(out_dir / "plan.json", plan)
    return plan
