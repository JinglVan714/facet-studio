"""Final style/voice polish pass (one bounded call).

The principles are informed by the MIT-licensed reference skills
(``great-writer`` burstiness/asymmetry/analogy, ``rednote`` voice and
write/check separation, ``avoid-ai-writing`` preservation); the prompt text is
original.  The polish may rewrite wording and terms but must preserve facts,
numbers, exact quotes, source/claim status and the source line.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..core.config import get_settings
from ..core.hashing import semantic_hash
from ..providers.llm import CachedLLM, DeepSeekLLM, ProviderError
from ..runtime.budget import BudgetPolicy, BudgetState
from .request import DEFAULT_READER_PROFILE

SCHEMA = "polish-report-v1"

SYSTEM = """You are the final editor for a reader-first article.

Polish voice, rhythm, clarity, the title/opening/ending, and term expression. You may rewrite the video's phrasing, ASR fragments, and local explanations into standard, concise Chinese; the source wording is not sacred.

Preserve every fact, number, exact quotation, source/claim status, and the reader-facing source line/next step. Do not add facts, numbers, quotes, URLs, or images. Do not compute new numbers, differences, ratios, percentages, or derived values; if a value is not in the source/article, do not introduce it. Do not turn a video claim into an official fact; do not remove an “unverified/视频称” qualification. Use the reader_profile.

Polish principles:
- Vary sentence length and section shape; avoid uniform “scene → table → aphorism” sections and repeated “不是 X 而是 Y”.
- Use one load-bearing analogy where it helps; do not stack analogies.
- Prefer a standard term plus a one-line definition over a long local paraphrase. Keep the term; do not write a textbook.
- Cut filler, repeated claims, and meta-narration; keep the concrete scene/example that carries the point.
- Keep the article's core judgment, evidence, and boundary; do not invent a new thesis.

Return only the revised Markdown article. No JSON, no commentary, no code fence."""


def run_polish(
    article: str,
    source_text: str,
    brief: dict[str, Any] | None,
    request: dict[str, Any] | None,
    out_dir: Path,
    *,
    run: bool = False,
    provider: Any | None = None,
    model: str | None = None,
    temperature: float = 0.2,
) -> dict[str, Any]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    brief = brief or {}
    request = request or {}
    payload = {
        "request": {
            "central_question": request.get("central_question", ""),
            "reader_profile": request.get("reader_profile")
            or DEFAULT_READER_PROFILE,
            "platform": request.get("platform", ""),
            "primary_objective": request.get("primary_objective", ""),
        },
        "article": article,
        "source_text": source_text,
        "source_block": brief.get("source_block", {}),
        "number_ledger": brief.get("number_ledger", []),
    }
    system = SYSTEM
    user = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    system_path = out_dir / "prompts" / "polish.system.txt"
    user_path = out_dir / "prompts" / "polish.user.txt"
    system_path.parent.mkdir(parents=True, exist_ok=True)
    system_path.write_text(system, encoding="utf-8")
    user_path.write_text(user, encoding="utf-8")

    if not run:
        return {
            "schema_version": SCHEMA,
            "status": "dry_run",
            "article": "",
            "article_hash": "",
        }

    usage: dict[str, Any] = {}
    latency_ms = 0
    cached = False
    finish_reason = None
    try:
        if provider is None:
            settings = get_settings()
            if model:
                from dataclasses import replace

                settings = replace(settings, model=model)
            if not settings.provider_configured:
                return {
                    "schema_version": SCHEMA,
                    "status": "provider_unconfigured",
                    "article": "",
                    "article_hash": "",
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
            provider = CachedLLM(
                inner, settings.runs_root / "_cache" / "llm", call_sink=call_sink
            )
            model_name = settings.model
        else:
            model_name = getattr(provider, "model", model or "injected")
        key = semantic_hash(
            {
                "article": article,
                "source_text": source_text,
                "brief": {
                    key: brief.get(key)
                    for key in ("source_block", "number_ledger")
                },
                "system": system,
                "user": user,
                "model": model_name,
            },
            drop_volatile=False,
        )
        response = provider.complete(
            stage="writing_polish",
            key=key,
            system=system,
            user=user,
            max_tokens=None,
            temperature=temperature,
        )
        raw = getattr(response, "text", str(response)).strip()
        (out_dir / "raw_response.md").write_text(raw, encoding="utf-8")
        usage_obj = getattr(response, "usage", None)
        if usage_obj is not None and hasattr(usage_obj, "as_dict"):
            usage = usage_obj.as_dict()
        latency_ms = int(getattr(response, "latency_ms", 0) or 0)
        cached = bool(getattr(response, "cached", False))
        finish_reason = getattr(response, "finish_reason", None)
    except ProviderError as exc:
        return {
            "schema_version": SCHEMA,
            "status": "provider_error",
            "error": {"kind": exc.kind, "message": str(exc)},
            "article": "",
            "article_hash": "",
        }

    if not raw:
        return {
            "schema_version": SCHEMA,
            "status": "provider_output_empty",
            "finish_reason": finish_reason,
            "article": "",
            "article_hash": "",
            "usage": usage,
        }
    if finish_reason == "length":
        return {
            "schema_version": SCHEMA,
            "status": "truncated",
            "finish_reason": finish_reason,
            "article": raw,
            "article_hash": semantic_hash({"article": raw}, drop_volatile=False),
            "usage": usage,
        }
    (out_dir / "polished.md").write_text(raw, encoding="utf-8")
    report = {
        "schema_version": SCHEMA,
        "status": "complete",
        "article": raw,
        "article_hash": semantic_hash({"article": raw}, drop_volatile=False),
        "usage": usage,
        "model": model_name,
        "latency_ms": latency_ms,
        "cached": cached,
        "finish_reason": finish_reason,
    }
    (out_dir / "polish_report.json").write_text(
        json.dumps(
            {key: value for key, value in report.items() if key != "article"},
            ensure_ascii=False,
            indent=1,
        ),
        encoding="utf-8",
    )
    return report
