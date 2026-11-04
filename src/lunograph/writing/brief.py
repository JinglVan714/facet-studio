"""Editorial brief planner (editorial-brief-v1).

This is intentionally not a section-outline generator.  It receives a
deterministic source map plus the skill's planning reference, and returns a
one-page editorial contract: angle, promise, throughline, spine, anchors,
title candidates, stance, cut list, challenge, and evidence status.

The schema is a semantic contract, not a rigid field checklist: optional
fields are kept optional; unknown speaker/claim type stays unknown.
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
from ..providers.llm import CachedLLM, DeepSeekLLM, ProviderError
from ..runtime.budget import BudgetPolicy, BudgetState
from .request import DEFAULT_READER_PROFILE

SCHEMA = "editorial-brief-v1"
BRIEF_INSTRUCTION = """You are the editorial brief planner for a video-to-article system.

Use the planning reference below as your method, not as a schema to fill mechanically.
You receive a writing request, a deterministic source map, and optionally the compiled evidence text.
Return one JSON object:

{"schema_version":"editorial-brief-v1","shape":"narrative|analytical|procedural|comparative|mixed","reader":{"knows":"...","asks":"...","wants":"..."},"core_argument":"one arguable sentence","source_question":"the question the source makes the reader ask","payoff":"what the reader gets","throughline":"the one sentence the whole piece serves","spine":[{"move":"what changes in the reader's understanding","connector":"because|but|therefore|and","anchors":["anchor id or short quote"],"weight":"slow|fast|gold|optional"}],"titles":[{"text":"...","promise":"...","fulfilled_by":"move/anchor","chosen":true}],"stance":{"narrator":"first_person_source|host_led|third_person","speaker_policy":"explicit_only|unknown_as_video"},"cut":["..."],"challenge":"strongest alternative angle and why not","evidence_status":["measured/hypothetical/single case/speaker unknown"],"concept_ledger":[{"term":"...","definition":"one concise sentence","analogy":"...","counterexample":"...","how_much":"assume_known|one_line|short_explanation","status":"..."}],"mechanism_chain":[{"link":"...","why":"...","evidence":"...","status":"..."}],"number_ledger":[{"value":"...","metric":"...","task":"...","baseline":"...","status":"..."}],"source_block":{"video":"...","channel":"...","date":"...","link":"...","official":["..."],"missing":["..."]},"texture_policy":"...","next_step":"...","notes":"free-form"}

Rules:
- Do not write H2s, per-section promises/takeaways, visual slots, chart specs, or prose. This is not an outline.
- The request is not an outline. `required_information` is coverage, not order; if the request enumerates topics, do not mirror the list. Find the source's own question/payoff; if the request conflicts, say so in challenge/notes.
- Choose one title (chosen=true) that promises a real payoff, not just an architecture/setup; it must have fulfilled_by. Avoid list subtitles, "如何..." mechanism lists, anonymous pronouns, and absolute words ("只是/就是/唯一/真正/第一次/所有/任何") unless the source supports that scope. Prefer a concrete subject + conflict/question, a source quote/number, or a before/after.
- Spine is 3-5 editorial moves; each move changes the reader's understanding; connectors must be real. Do not turn it into a topic list or a section schema. Core claims need at least one source_map anchor.
- Mark claim type (measured/hypothetical/opinion/unknown), speaker (explicit/unknown), and same/cross comparison when relevant. Never turn a hypothesis/demo into a measurement; never guess a speaker; "大家伙都说" is a relay, not the speaker's own evaluation.
- Include what to cut and the strongest alternative angle. Do not cut the single best proof of a core claim just because it sits in a side story; use it briefly.
- Knowledge brief (required; for the writer, not reader prose):
  - concept_ledger: 3-5 load-bearing terms only. `definition` is one concise sentence. `how_much` is `assume_known`, `one_line`, or `short_explanation`, chosen from the request's reader_profile; if no profile, assume a smart general reader with some technical baseline. Keep the standard term; do not write a glossary or textbook.
  - mechanism_chain: 3-5 links; each link says why it holds and what evidence supports it; mark `unknown` where the source does not explain it.
  - number_ledger: every number that matters; metric/task/baseline/status; if unknown, say unknown; do not invent numbers or baselines.
  - source_block: use source_map.provenance/source_metadata. Frame OCR/watermark fields are "画面显示/未核实"; never invent links, dates, titles, or official docs. If a field is a frame-OCR hint, keep `metadata_source`/`unverified` rather than stating it as official.
  - texture_policy: preserve concrete dialogue, jokes, side stories, demo details, and small gestures; skip only greetings, sponsorship, channel logistics, routine sign-off, and repetition.
  - next_step: one natural source entry or next action; do not invent a URL.
- reader_profile: use the request's `reader_profile`/`audience` if present; otherwise assume a smart general reader with some technical baseline. Do not default to an AI beginner.
- Return JSON only.
"""


def _write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(value, str):
        path.write_text(value, encoding="utf-8")
    else:
        path.write_text(
            json.dumps(value, ensure_ascii=False, indent=1), encoding="utf-8"
        )


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _clean_titles(value: Any) -> list[dict[str, Any]]:
    titles: list[dict[str, Any]] = []
    for item in _as_list(value):
        if isinstance(item, str):
            item = {"text": item}
        if not isinstance(item, dict):
            continue
        text = str(item.get("text") or item.get("title") or "").strip()
        if not text:
            continue
        titles.append(
            {
                "text": text,
                "promise": str(item.get("promise", "")).strip(),
                "fulfilled_by": str(item.get("fulfilled_by", "")).strip(),
                "chosen": bool(item.get("chosen", False)),
            }
        )
    if titles and not any(item["chosen"] for item in titles):
        titles[0]["chosen"] = True
    return titles


def _clean_spine(value: Any) -> list[dict[str, Any]]:
    moves: list[dict[str, Any]] = []
    for item in _as_list(value):
        if isinstance(item, str):
            item = {"move": item}
        if not isinstance(item, dict):
            continue
        move = str(
            item.get("move")
            or item.get("beat")
            or item.get("step")
            or item.get("section")
            or ""
        ).strip()
        if not move:
            continue
        anchors = [
            str(anchor).strip()
            for anchor in _as_list(item.get("anchors") or item.get("anchor"))
            if str(anchor).strip()
        ]
        moves.append(
            {
                "move": move,
                "connector": str(item.get("connector", "")).strip(),
                "anchors": anchors,
                "weight": str(item.get("weight", "")).strip(),
            }
        )
    return moves


def _clean_concepts(value: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in _as_list(value):
        if not isinstance(item, dict):
            continue
        term = str(item.get("term") or "").strip()
        if not term:
            continue
        how = str(item.get("how_much", "one_line")).strip()
        if how not in {"assume_known", "one_line", "short_explanation"}:
            how = "one_line"
        rows.append(
            {
                "term": term,
                "definition": str(item.get("definition", "")).strip(),
                "analogy": str(item.get("analogy", "")).strip(),
                "counterexample": str(item.get("counterexample", "")).strip(),
                "how_much": how,
                "status": str(item.get("status", "")).strip(),
            }
        )
    return rows


def _clean_mechanism(value: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in _as_list(value):
        if not isinstance(item, dict):
            continue
        link = str(item.get("link") or item.get("step") or "").strip()
        if not link:
            continue
        rows.append(
            {
                "link": link,
                "why": str(item.get("why", "")).strip(),
                "evidence": str(item.get("evidence", "")).strip(),
                "status": str(item.get("status", "")).strip(),
            }
        )
    return rows


def _clean_number_ledger(value: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in _as_list(value):
        if not isinstance(item, dict):
            continue
        value_text = str(item.get("value", "")).strip()
        if not value_text:
            continue
        rows.append(
            {
                "value": value_text,
                "metric": str(item.get("metric", "unknown")).strip() or "unknown",
                "task": str(item.get("task", "unknown")).strip() or "unknown",
                "baseline": str(item.get("baseline", "unknown")).strip() or "unknown",
                "status": str(item.get("status", "unknown")).strip() or "unknown",
                "context": str(item.get("context", "")).strip(),
            }
        )
    return rows


UNKNOWN_VALUES = {
    "",
    "unknown",
    "unverified",
    "n/a",
    "none",
    "未知",
    "未提供",
    "未核实",
    "未给出",
}


def _is_unknown(value: Any) -> bool:
    text = str(value or "").strip().lower()
    return (
        text in UNKNOWN_VALUES
        or text.startswith("unknown")
        or text.startswith("未提供")
        or text.startswith("未核实")
    )


def _clean_source_block(
    value: Any, source_map: dict[str, Any] | None
) -> dict[str, Any]:
    source_map = source_map or {}
    provenance = source_map.get("provenance")
    metadata = source_map.get("source_metadata")
    provenance = provenance if isinstance(provenance, dict) else {}
    metadata = metadata if isinstance(metadata, dict) else {}

    def _metadata_value(field: str) -> tuple[str, str]:
        row = metadata.get(field)
        if isinstance(row, dict):
            return str(row.get("value", "")).strip(), str(
                row.get("source", "unknown")
            ).strip()
        return "", "unknown"

    def _provenance_value(field: str) -> str:
        if field == "video":
            return str(provenance.get("video_id", "")).strip()
        return str(provenance.get(field, "")).strip()

    def _fill(field: str, current: str) -> str:
        if not _is_unknown(current):
            return current.strip()
        for candidate in (
            _provenance_value(field),
            _metadata_value(field)[0],
        ):
            if candidate and not _is_unknown(candidate):
                return candidate
        return current.strip() or "unknown"

    value = value if isinstance(value, dict) else {}
    official = [
        str(item).strip()
        for item in _as_list(value.get("official"))
        if str(item).strip()
    ]
    missing = [
        str(item).strip()
        for item in _as_list(value.get("missing"))
        if str(item).strip()
    ]

    block = {
        "video": _fill("video", str(value.get("video", "")).strip()),
        "channel": _fill("channel", str(value.get("channel", "")).strip()),
        "title": _fill("title", str(value.get("title", "")).strip()),
        "date": _fill("date", str(value.get("date", "")).strip()),
        "link": _fill("link", str(value.get("link", "")).strip()),
        "official": official,
        "missing": missing,
    }

    # A frame-OCR hint is not a verified link.  Keep official docs empty; put
    # visible announcement hints in a separate field.
    official_hints = [
        row for row in _as_list(metadata.get("official_hints")) if isinstance(row, dict)
    ]
    if official_hints:
        block["official_hints"] = official_hints

    metadata_source: dict[str, str] = {}
    for field in ("channel", "title", "date"):
        source = _metadata_value(field)[1]
        if source != "unknown":
            metadata_source[field] = source
    if metadata_source:
        block["metadata_source"] = metadata_source
        block["unverified"] = True

    # Recompute missing: known fields are not missing; unknown link/official
    # docs stay missing even when an OCR announcement hint exists.
    known = {
        field
        for field in ("title", "channel", "date")
        if block.get(field) and not _is_unknown(block[field])
    }
    recomputed = [field for field in missing if field not in known]
    for field in ("title", "channel", "date", "link", "official_docs"):
        if field not in known and field not in recomputed:
            recomputed.append(field)
    # If the caller explicitly supplied missing fields, keep their order and
    # only add fields that are genuinely unknown.
    block["missing"] = recomputed
    return block


def _title_check(
    brief: dict[str, Any], source_map: dict[str, Any] | None
) -> dict[str, Any]:
    """Advisory title checks: unscoped absolute words and source quotes.

    Subject specificity is taught by the planning examples and the title
    prompt; it is not reduced to a pronoun/stop-word heuristic here.
    """
    titles = brief.get("titles") or []
    chosen = next((item for item in titles if item.get("chosen")), None)
    if not isinstance(chosen, dict):
        return {"chosen": "", "issues": []}
    title = str(chosen.get("text", "")).strip()
    issues: list[str] = []
    absolute = re.findall(
        r"(只是|就是|唯一|真正|第一次|所有|任何|永远|证明)", title
    )
    for word in sorted(set(absolute)):
        issues.append(f"title_absolute:{word}")
    quotes = re.findall(r"[“「]([^”」]{2,})[”」]", title)
    anchors_text = json.dumps(source_map or {}, ensure_ascii=False)
    for quote in quotes:
        if quote not in anchors_text:
            issues.append("title_quote_not_in_source")
            break
    return {"chosen": title, "issues": issues}


def _validate(
    payload: dict[str, Any], *, source_map: dict[str, Any] | None = None
) -> tuple[dict[str, Any], list[str]]:
    problems: list[str] = []
    core = str(
        payload.get("core_argument")
        or payload.get("core")
        or payload.get("controlling_idea")
        or ""
    ).strip()
    if not core:
        problems.append("missing_core")
    spine = _clean_spine(payload.get("spine"))
    if not spine:
        problems.append("missing_spine")
    elif len(spine) < 3:
        problems.append("too_few_moves")
    elif len(spine) > 7:
        problems.append("too_many_moves")
    titles = _clean_titles(payload.get("titles") or payload.get("title"))
    if not titles:
        problems.append("missing_title")
    chosen = next((item for item in titles if item["chosen"]), None)
    if chosen is None and titles:
        titles[0]["chosen"] = True
        chosen = titles[0]
    if chosen is not None and not chosen["fulfilled_by"]:
        problems.append("title_without_fulfilled_by")
    reader = payload.get("reader")
    if isinstance(reader, str):
        reader = {"summary": reader}
    if not isinstance(reader, dict):
        reader = {}
    if not reader:
        problems.append("missing_reader")
    payoff = str(payload.get("payoff", "")).strip()
    throughline = str(payload.get("throughline", "")).strip()
    if not payoff:
        problems.append("missing_payoff")
    if not throughline:
        problems.append("missing_throughline")
    cut = [str(item).strip() for item in _as_list(payload.get("cut")) if str(item).strip()]
    evidence_status = [
        str(item).strip()
        for item in _as_list(payload.get("evidence_status"))
        if str(item).strip()
    ]
    concepts = _clean_concepts(
        payload.get("concept_ledger") or payload.get("concepts")
    )
    mechanisms = _clean_mechanism(
        payload.get("mechanism_chain") or payload.get("mechanism")
    )
    numbers = _clean_number_ledger(
        payload.get("number_ledger") or payload.get("numbers")
    )
    if not numbers and source_map:
        numbers = _clean_number_ledger(source_map.get("numbers"))
    source_block = _clean_source_block(payload.get("source_block"), source_map)
    texture_policy = str(payload.get("texture_policy", "")).strip()
    next_step = str(payload.get("next_step", "")).strip()
    if not concepts:
        problems.append("missing_concept_ledger")
    if not mechanisms:
        problems.append("missing_mechanism_chain")
    if not numbers:
        problems.append("missing_number_ledger")
    if not source_block.get("video"):
        problems.append("missing_source_block")
    brief = {
        "schema_version": SCHEMA,
        "shape": str(payload.get("shape", "mixed") or "mixed"),
        "reader": {
            "knows": str(reader.get("knows", "")).strip(),
            "asks": str(reader.get("asks", "")).strip(),
            "wants": str(reader.get("wants", "")).strip(),
        },
        "core_argument": core,
        "source_question": str(payload.get("source_question", "")).strip(),
        "payoff": payoff,
        "throughline": throughline,
        "spine": spine,
        "titles": titles,
        "stance": payload.get("stance") if isinstance(payload.get("stance"), dict) else {},
        "cut": cut,
        "challenge": str(payload.get("challenge", "")).strip(),
        "evidence_status": evidence_status,
        "concept_ledger": concepts,
        "mechanism_chain": mechanisms,
        "number_ledger": numbers,
        "source_block": source_block,
        "texture_policy": texture_policy,
        "next_step": next_step,
        "notes": str(payload.get("notes", "")).strip(),
    }
    title_check = _title_check(brief, source_map)
    brief["title_check"] = title_check
    problems.extend(
        issue for issue in title_check.get("issues", []) if issue not in problems
    )
    return brief, problems


def _brief_hash(brief: dict[str, Any]) -> str:
    return semantic_hash(
        {
            "reader": brief.get("reader", {}),
            "core_argument": brief.get("core_argument", ""),
            "source_question": brief.get("source_question", ""),
            "payoff": brief.get("payoff", ""),
            "throughline": brief.get("throughline", ""),
            "spine": brief.get("spine", []),
            "titles": brief.get("titles", []),
            "stance": brief.get("stance", {}),
            "cut": brief.get("cut", []),
            "challenge": brief.get("challenge", ""),
            "evidence_status": brief.get("evidence_status", []),
            "concept_ledger": brief.get("concept_ledger", []),
            "mechanism_chain": brief.get("mechanism_chain", []),
            "number_ledger": brief.get("number_ledger", []),
            "source_block": brief.get("source_block", {}),
            "texture_policy": brief.get("texture_policy", ""),
            "next_step": brief.get("next_step", ""),
        },
        drop_volatile=False,
    )


def write_brief(
    request: dict[str, Any],
    source_map: dict[str, Any],
    skill: Any,
    out_dir: Path,
    *,
    run: bool = False,
    provider: Any | None = None,
    model: str | None = None,
    temperature: float = 0.2,
    max_tokens: int | None = None,
    evidence_text: str | None = None,
    include_full_text: bool = True,
) -> dict[str, Any]:
    out_dir = Path(out_dir)
    planning = str(getattr(skill, "planning", "") or "")
    system = BRIEF_INSTRUCTION
    if planning:
        system = f"{BRIEF_INSTRUCTION}\n\n## Planning reference\n\n{planning}"
    payload: dict[str, Any] = {
        "request": request,
        "reader_profile": request.get("reader_profile") or DEFAULT_READER_PROFILE,
        "source_map": source_map,
    }
    if include_full_text and evidence_text:
        payload["evidence_text"] = evidence_text
    user = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    system_path = out_dir / "prompts" / "brief.system.txt"
    user_path = out_dir / "prompts" / "brief.user.txt"
    _write(system_path, system)
    _write(user_path, user)

    if not run:
        return {
            "schema_version": SCHEMA,
            "status": "dry_run",
            "shape": "mixed",
            "core_argument": "",
            "spine": [],
            "titles": [],
            "source_map_hash": source_map.get("source_map_hash", ""),
        }

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
                    "shape": "mixed",
                    "core_argument": "",
                    "spine": [],
                    "titles": [],
                    "source_map_hash": source_map.get("source_map_hash", ""),
                }
            llm_calls_path = out_dir / "llm_calls.jsonl"
            llm_calls_path.write_text("", encoding="utf-8")

            def call_sink(record: dict[str, Any]) -> None:
                with llm_calls_path.open("a", encoding="utf-8") as handle:
                    handle.write(json.dumps(record, ensure_ascii=False) + "\n")

            budget = BudgetState(
                BudgetPolicy(max_calls=1, max_tokens=settings.budget_max_tokens)
            )
            inner = DeepSeekLLM(settings, budget=budget, call_sink=call_sink)
            cache_dir = settings.runs_root / "_cache" / "llm"
            provider = CachedLLM(inner, cache_dir, call_sink=call_sink)
            model_name = settings.model
        else:
            model_name = getattr(provider, "model", model or "injected")
        key = semantic_hash(
            {
                "request_hash": request.get("request_hash", ""),
                "source_map_hash": source_map.get("source_map_hash", ""),
                "system": system,
                "user": user,
                "model": model_name,
            },
            drop_volatile=False,
        )
        response = provider.complete(
            stage="writing_brief",
            key=key,
            system=system,
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
            "shape": "mixed",
            "core_argument": "",
            "spine": [],
            "titles": [],
            "source_map_hash": source_map.get("source_map_hash", ""),
        }
    except (StructuredOutputError, ValueError) as exc:
        return {
            "schema_version": SCHEMA,
            "status": "invalid_output",
            "error": str(exc),
            "shape": "mixed",
            "core_argument": "",
            "spine": [],
            "titles": [],
            "source_map_hash": source_map.get("source_map_hash", ""),
        }

    brief, problems = _validate(parsed, source_map=source_map)
    # The request's video id is the authoritative identifier.  The consume
    # index often keeps only a short prefix (e.g. BV1AC), which is enough for
    # internal lookup but not for a reader-facing source line.
    request_video_ids = [
        str(item).strip()
        for item in (request.get("video_ids") or [])
        if str(item).strip()
    ]
    if request_video_ids:
        brief["source_block"]["video"] = request_video_ids[0]
    status = "complete" if not {"missing_core", "missing_spine", "missing_title"} & set(problems) else "invalid_output"
    brief.update(
        {
            "status": status,
            "problems": problems,
            "source_map_hash": source_map.get("source_map_hash", ""),
            "brief_hash": _brief_hash(brief),
            "input_mode": "source_map+full_text" if include_full_text and evidence_text else "source_map",
            "usage": usage,
            "model": model_name,
            "latency_ms": latency_ms,
            "cached": cached,
            "finish_reason": finish_reason,
        }
    )
    _write(out_dir / "brief.json", brief)
    return brief
