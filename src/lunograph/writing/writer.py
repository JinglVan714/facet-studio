"""One prose Writer call with prompt/trace/usage artifacts.

Dry-run is the default: it writes prompts/manifest without calling a provider.
Pass ``run=True`` (CLI ``--run``) to perform one model call.
"""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..core.config import get_settings
from ..core.hashing import semantic_hash
from ..core.tokens import estimate_text_tokens
from ..providers.llm import CachedLLM, DeepSeekLLM, ProviderError
from ..runtime.budget import BudgetPolicy, BudgetState
from ..writing_v3.trace import TraceRecorder
from .prompt import (
    REPAIR_INSTRUCTION,
    build_repair_user,
    build_system_prompt,
    build_user_prompt,
    sha_text,
)
from .skill import SkillPackage

SCHEMA = "writing-writer-v1"


def _write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(value, str):
        path.write_text(value, encoding="utf-8")
    else:
        path.write_text(
            json.dumps(value, ensure_ascii=False, indent=1), encoding="utf-8"
        )


def _title(article: str) -> str:
    for line in article.splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            return stripped[2:].strip()
    return ""


def run_writer(
    *,
    request: dict[str, Any],
    skill: SkillPackage,
    context: dict[str, Any],
    out_dir: Path,
    run: bool = False,
    model: str | None = None,
    temperature: float = 0.3,
    max_tokens: int | None = None,
    no_cache: bool = False,
    repair_draft: str | None = None,
    repair_findings: dict[str, Any] | None = None,
    writing_plan: dict[str, Any] | None = None,
    writing_brief: dict[str, Any] | None = None,
) -> dict[str, Any]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    profile = context.get("profile", "")
    input_kind = "claim" if profile == "claim_lean" else "text"
    repair_mode = repair_draft is not None and repair_findings is not None
    if repair_mode:
        system = (
            build_system_prompt(skill, input_kind=input_kind)
            + "\n\n"
            + REPAIR_INSTRUCTION
        )
        user = build_repair_user(
            request,
            context,
            repair_draft or "",
            repair_findings or {},
            writing_plan=writing_plan,
            writing_brief=writing_brief,
        )
    else:
        system = build_system_prompt(skill, input_kind=input_kind)
        user = build_user_prompt(
            request,
            context,
            writing_plan=writing_plan,
            writing_brief=writing_brief,
        )

    system_path = out_dir / "prompts" / "system.txt"
    user_path = out_dir / "prompts" / "user.txt"
    _write(system_path, system)
    _write(user_path, user)
    manifest: dict[str, Any] = {
        "schema": SCHEMA,
        "status": "dry_run",
        "mode": "repair" if repair_mode else "write",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "request_hash": request.get("request_hash", ""),
        "skill": {
            "skill_id": skill.skill_id,
            "version": skill.version,
            "status": skill.status,
            "content_hash": skill.content_hash,
            "hash_ok": skill.hash_ok,
        },
        "context": {
            "profile": profile,
            "context_hash": context.get("context_hash", ""),
            "chars": len(context.get("text", "")),
            "est_tokens": estimate_text_tokens(context.get("text", "")),
            "claims": len(context.get("claims", [])),
            "frames": len(context.get("frames", [])),
        },
        "input_kind": input_kind,
        "writing_plan": (
            {
                "title": writing_plan.get("title", ""),
                "sections": len(writing_plan.get("toc", [])),
                "hash": writing_plan.get("plan_hash")
                or semantic_hash(
                    {
                        "title": writing_plan.get("title", ""),
                        "controlling_idea": writing_plan.get("controlling_idea", ""),
                        "toc": writing_plan.get("toc", []),
                    },
                    drop_volatile=False,
                ),
            }
            if writing_plan and writing_plan.get("toc")
            else None
        ),
        "writing_brief": (
            {
                "title": next(
                    (
                        item.get("text", "")
                        for item in writing_brief.get("titles", [])
                        if item.get("chosen")
                    ),
                    "",
                ),
                "moves": len(writing_brief.get("spine", [])),
                "hash": writing_brief.get("brief_hash", ""),
            }
            if writing_brief and writing_brief.get("core_argument")
            else None
        ),
        "system": {
            "path": str(system_path),
            "chars": len(system),
            "sha256": sha_text(system),
        },
        "user": {
            "path": str(user_path),
            "chars": len(user),
            "sha256": sha_text(user),
        },
        "model": model or "configured",
        "temperature": temperature,
        "max_tokens": max_tokens,
        "max_tokens_source": (
            "provider_default" if max_tokens is None else "cli_override"
        ),
        "usage": None,
        "latency_ms": None,
        "finish_reason": None,
        "cached": None,
        "article_chars": None,
        "output_hash": None,
    }
    manifest_path = out_dir / "manifest.json"

    if not run:
        _write(manifest_path, manifest)
        return {"status": "dry_run", "out_dir": str(out_dir), "manifest": manifest}

    settings = get_settings()
    if model:
        settings = replace(settings, model=model)
    manifest["model"] = settings.model
    if not settings.provider_configured:
        manifest["status"] = "provider_unconfigured"
        _write(manifest_path, manifest)
        return {"status": "provider_unconfigured", "out_dir": str(out_dir)}

    llm_calls_path = out_dir / "llm_calls.jsonl"
    llm_calls_path.write_text("", encoding="utf-8")

    def call_sink(record: dict[str, Any]) -> None:
        with llm_calls_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    # The budget is total tokens for the call; max_tokens is the provider's
    # output cap. Do not conflate them: a caller-set output cap must not
    # shrink the total budget (and leave max_tokens unset by default).
    budget = BudgetState(
        BudgetPolicy(
            max_calls=1,
            max_tokens=settings.budget_max_tokens,
        )
    )
    inner = DeepSeekLLM(settings, budget=budget, call_sink=call_sink)
    cache_dir = settings.runs_root / "_cache" / "llm"
    provider = (
        inner
        if no_cache
        else CachedLLM(inner, cache_dir, call_sink=call_sink)
    )
    key = semantic_hash(
        {
            "request_hash": request.get("request_hash", ""),
            "skill_hash": skill.content_hash,
            "context_hash": context.get("context_hash", ""),
            "system_sha": manifest["system"]["sha256"],
            "user_sha": manifest["user"]["sha256"],
            "model": settings.model,
        },
        drop_volatile=False,
    )
    try:
        response = provider.complete(
            stage="writing_writer",
            key=key,
            system=system,
            user=user,
            max_tokens=max_tokens,
            temperature=temperature,
        )
    except ProviderError as exc:
        manifest["status"] = "provider_error"
        manifest["error"] = {"kind": exc.kind, "message": str(exc)}
        _write(manifest_path, manifest)
        return {"status": "provider_error", "out_dir": str(out_dir)}

    article = response.text
    raw_path = out_dir / "raw_response.md"
    article_path = out_dir / "article.md"
    _write(raw_path, article)
    _write(article_path, article)
    usage = response.usage.as_dict()
    output_hash = semantic_hash({"article": article}, drop_volatile=False)
    writer_output = {
        "schema_version": "writer-output-v1",
        "status": "complete",
        "format": "markdown",
        "title": _title(article),
        "article": article,
        "self_review": {},
        "usage": usage,
        "prompt_hashes": {
            "system": manifest["system"]["sha256"],
            "user": manifest["user"]["sha256"],
        },
        "model": settings.model,
        "temperature": temperature,
        "finish_reason": response.finish_reason,
        "latency_ms": response.latency_ms,
        "cached": response.cached,
        "output_hash": output_hash,
    }
    writer_output_path = out_dir / "writer_output.json"
    _write(writer_output_path, writer_output)
    manifest.update(
        {
            "status": "complete",
            "usage": usage,
            "latency_ms": response.latency_ms,
            "finish_reason": response.finish_reason,
            "cached": response.cached,
            "article_chars": len(article),
            "article_est_tokens": estimate_text_tokens(article),
            "output_hash": output_hash,
            "llm_calls": str(llm_calls_path),
        }
    )
    _write(manifest_path, manifest)

    trace = TraceRecorder(out_dir)
    try:
        trace.stage(
            "writer",
            status="complete",
            inputs={
                "system_prompt": system_path,
                "user_prompt": user_path,
                "llm_calls": llm_calls_path,
            },
            outputs={
                "raw_response": raw_path,
                "article": article_path,
                "writer_output": writer_output_path,
                "manifest": manifest_path,
            },
            counts={
                "article_chars": len(article),
                "article_est_tokens": estimate_text_tokens(article),
                "claims_in_context": len(context.get("claims", [])),
                "frames_in_context": len(context.get("frames", [])),
            },
            params={
                "model": settings.model,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "profile": profile,
            },
            decisions={
                "cached": response.cached,
                "finish_reason": response.finish_reason,
                "skill_hash_ok": skill.hash_ok,
            },
            samples=[{"article_head": article[:200]}],
        )
    finally:
        trace.close()
    return {
        "status": "complete",
        "out_dir": str(out_dir),
        "article": article,
        "manifest": manifest,
        "writer_output": writer_output,
    }
