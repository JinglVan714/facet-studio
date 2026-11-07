"""One planning call before the Writer.

The planner builds the article's framework: a short title, a question/answer
TOC, each section's promise/key example/visual slot/takeaway.  The Writer then
writes to this plan instead of inventing its own section list.
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

SCHEMA = "writing-plan-v1"
VISUAL_KINDS = {"diagram", "chart", "table", "real_frame", "none"}
HEADING_PREFIX = re.compile(r"^\s*(?:\d+[.、)]|第[一二三四五六七八九十]+[章节])\s*")

SYSTEM = """You are the planning editor for a video-to-article system. You receive a writing request and the compiled evidence text (or claim view). Design a standalone article that gives a reader who has not watched the video approximately the same understanding and experience as watching it.

Return one JSON object:
{"title":"...","controlling_idea":"...","toc":[{"index":1,"heading":"...","promise":"...","key_example":"...","visual":{"kind":"diagram|chart|table|real_frame|none","intent":"..."},"takeaway":"..."}]}

Rules:
- 4-7 sections. Each heading is short, concrete, parallel, and a step in the article's question/answer chain. Do not use generic labels (background/introduction/summary/other).
- Each section has: promise (what the reader will understand), key_example (a concrete scene/demo/quote/number from the evidence), a visual slot if it materially helps, and a one-sentence takeaway. The Writer will open the section with key_example, so it must be a specific moment, not a summary.
- Prefer a teaching narrative: start from a concrete question/scene/claim, then explain the mechanism, show the example/demo, and state the takeaway. Do not produce a topic list.
- Visual slots: table for comparisons/categories; chart for numbers; diagram for process/causal/architecture; real_frame only if the evidence frames show it and it is readable; none if no visual helps. Do not give most sections a table; tables are for parallel comparison, not the default.
- Use only facts/numbers/names/quotes in the evidence for the plan. Model knowledge may explain/analogize/background but must not be presented as a video fact.
- Title: concrete, short, states the subject/question; use one concrete object/image from the evidence when possible. If you use a subtitle, make it a transformation, contrast, or question ("从A到B：...如何..."), not a list of abstract nouns. No slogan, no gimmick that obscures the subject.
- Do not include a separate introduction/conclusion section; the opening lives in section 1, the synthesis in the final section.
"""


def _write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(value, str):
        path.write_text(value, encoding="utf-8")
    else:
        path.write_text(
            json.dumps(value, ensure_ascii=False, indent=1), encoding="utf-8"
        )


def _clean_heading(value: Any) -> str:
    text = str(value or "").strip()
    text = HEADING_PREFIX.sub("", text).strip()
    return text


def _validate(payload: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    problems: list[str] = []
    title = str(payload.get("title", "")).strip()
    controlling = str(payload.get("controlling_idea", "")).strip()
    if not title:
        problems.append("missing_title")
    toc_raw = payload.get("toc")
    if not isinstance(toc_raw, list):
        return {"title": title, "controlling_idea": controlling, "toc": []}, [
            "toc_not_list"
        ]
    toc: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, raw in enumerate(toc_raw, start=1):
        if not isinstance(raw, dict):
            problems.append(f"toc_{index}_invalid")
            continue
        heading = _clean_heading(raw.get("heading"))
        if not heading or heading in seen:
            problems.append(f"toc_{index}_bad_heading")
            continue
        seen.add(heading)
        visual = raw.get("visual") if isinstance(raw.get("visual"), dict) else {}
        kind = str(visual.get("kind", "none"))
        if kind not in VISUAL_KINDS:
            kind = "none"
        toc.append(
            {
                "index": len(toc) + 1,
                "heading": heading,
                "promise": str(raw.get("promise", "")).strip(),
                "key_example": str(raw.get("key_example", "")).strip(),
                "visual": {
                    "kind": kind,
                    "intent": str(visual.get("intent", "")).strip(),
                },
                "takeaway": str(raw.get("takeaway", "")).strip(),
            }
        )
    if len(toc) < 3:
        problems.append("too_few_sections")
    if len(toc) > 7:
        toc = toc[:7]
        problems.append("too_many_sections_truncated")
    return {
        "title": title,
        "controlling_idea": controlling,
        "toc": toc,
    }, problems


def plan_article(
    request: dict[str, Any],
    context: dict[str, Any],
    out_dir: Path,
    *,
    run: bool = False,
    provider: Any | None = None,
    model: str | None = None,
    temperature: float = 0.2,
    max_tokens: int | None = None,
) -> dict[str, Any]:
    out_dir = Path(out_dir)
    if not run:
        return {
            "schema_version": SCHEMA,
            "status": "dry_run",
            "title": "",
            "controlling_idea": "",
            "toc": [],
        }
    payload: dict[str, Any] = {"request": request}
    if context.get("profile") == "claim_lean":
        payload["claim_view"] = {
            "claims": context.get("claims", []),
            "frames": context.get("frames", []),
        }
    else:
        payload["evidence_text"] = context.get("text", "")
        payload["frames"] = context.get("frames", [])
    user = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    system_path = out_dir / "prompts" / "writing_planner.system.txt"
    user_path = out_dir / "prompts" / "writing_planner.user.txt"
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
                    "title": "",
                    "controlling_idea": "",
                    "toc": [],
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
                "context_hash": context.get("context_hash", ""),
                "system": SYSTEM,
                "user": user,
                "model": model_name,
            },
            drop_volatile=False,
        )
        response = provider.complete(
            stage="writing_planner",
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
            "title": "",
            "controlling_idea": "",
            "toc": [],
        }
    except (StructuredOutputError, ValueError) as exc:
        return {
            "schema_version": SCHEMA,
            "status": "invalid_output",
            "error": str(exc),
            "title": "",
            "controlling_idea": "",
            "toc": [],
        }

    plan, problems = _validate(parsed)
    plan.update(
        {
            "schema_version": SCHEMA,
            "status": "complete" if plan["toc"] else "invalid_output",
            "problems": problems,
            "plan_hash": semantic_hash(
                {
                    "title": plan["title"],
                    "controlling_idea": plan["controlling_idea"],
                    "toc": plan["toc"],
                },
                drop_volatile=False,
            ),
            "usage": usage,
            "model": model_name,
            "latency_ms": latency_ms,
            "cached": cached,
            "finish_reason": finish_reason,
        }
    )
    _write(out_dir / "plan.json", plan)
    return plan
