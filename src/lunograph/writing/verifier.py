"""Optional independent semantic Verifier (read-only findings).

This is the single high-risk check the architecture allows: it sees the
article, the continuous source text, and the compact source/number/concept
ledger; it does not rewrite, does not see the writer's plan/self-review, and
returns quote-located findings for one bounded repair.  The pipeline may call
it twice: once to drive the bounded repair, and once as a read-only audit of
the repaired/polished artifact (no second repair loop).
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from ..core.config import get_settings
from ..core.hashing import semantic_hash
from ..core.jsonutil import StructuredOutputError, extract_json_object
from ..providers.llm import CachedLLM, DeepSeekLLM, ImageInput, ProviderError
from ..runtime.budget import BudgetPolicy, BudgetState
from .request import DEFAULT_READER_PROFILE

SCHEMA = "verifier-report-v1"
AXES = {
    "source",
    "claim_scope",
    "number",
    "consistency",
    "term",
    "mechanism",
    "title_cta",
    "visual",
    "reader",
}
SEVERITIES = {"critical", "high", "medium", "low"}

SYSTEM = """You are an independent verifier for a reader-first article built from a video.

You do not rewrite. You return only quote-located findings.

Inputs:
- article: the final reader-facing Markdown.
- source_text: the compiled video text; the only source for video facts.
- reader_profile: the intended reader, if provided.
- source_block / number_ledger / concept_ledger / mechanism_chain: compact checklists (not the writer's plan). `source_text` wins; a planner ledger can be wrong, so do not treat it as truth.
- image_manifest + images: the article's real frames, if provided. The manifest lists each image's name, frame id and caption; images are in the same order. Captions in the article refer to these images.
- visual_manifest: the rendered visuals' spec (kind/status/caption; diagram nodes/edges; chart data; table rows). Check each caption against the spec; do not require a chart/diagram caption to state anything the spec does not contain.
- request.video_ids is the authoritative video identifier from the frozen request. A source line may use it even if source_text only contains a short prefix; do not mark it as invented. source_block frame-OCR/watermark metadata is a hint, not an official link.

Check:
- source: are product/model/official claims attributed correctly? Does the article turn “the video says” into “official/confirmed”? Is the source line present and honest? Are missing title/date/link/official docs disclosed? Does the source line contradict a frame-OCR metadata hint (channel/title/date)? If a quote is attributed to a named speaker and source_text has no speaker labels, check whether the surrounding text explicitly identifies the speaker (e.g. “X 说”, third-person address); if not, flag source medium/high. Do not assume the nearest named person said it.
- claim_scope: absolutes, over-generalization, single case -> general rule, body/boundary contradiction.
- number: metric, task, baseline, unit; bare or mixed-denominator numbers; conflicting values.
- consistency: title/body, claim vs body, term vs definition, repeated claims; does the body deliver the title?
- term: is a load-bearing term used as its own explanation? Is it over-explained as a textbook (respect reader_profile; the default is a smart general reader with some technical baseline, not AI beginner)? Is it unexplained where comprehension actually breaks?
- mechanism: missing “why”; an unknown mechanism filled with a causal claim.
- title_cta: title promise, anonymous/term-first title, source/next step, invented URL.
- visual: if images are provided, compare each caption with the image. Report only what is visible. Flag a caption that claims a number/ranking/mechanism the image does not show, an image too dark/unreadable, or a caption pointing to the wrong region. Do not infer from the caption. If no images are provided, do not invent visual findings.
- reader: only issues that affect comprehension, not taste.

Return one JSON object:
{"status":"complete","red_line":false,"findings":[{"axis":"source|claim_scope|number|consistency|term|mechanism|title_cta|visual|reader","severity":"critical|high|medium|low","quote":"exact text from the article","observation":"...","impact":"...","action":"..."}]}

Rules:
- Quote exactly from the article. Maximum 12 findings; prioritize the highest-impact ones.
- No invented sources, facts, numbers, or URLs. “unverified” is not the same as “false”; do not mark it false.
- red_line is true only for a key fact/product capability written as confirmed without a source, or a contradiction that would materially mislead the reader.
- Do not critique pure style; do not rewrite; do not add new content.
- If there are no findings, return an empty findings list.
- Return JSON only.
"""


def _clean_findings(value: Any) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    if not isinstance(value, list):
        return findings
    for item in value:
        if not isinstance(item, dict):
            continue
        quote = str(item.get("quote", "")).strip()
        observation = str(item.get("observation", "")).strip()
        if not quote or not observation:
            continue
        axis = str(item.get("axis", "reader")).strip()
        if axis not in AXES:
            axis = "reader"
        severity = str(item.get("severity", "medium")).strip()
        if severity not in SEVERITIES:
            severity = "medium"
        findings.append(
            {
                "axis": axis,
                "severity": severity,
                "quote": quote,
                "observation": observation,
                "impact": str(item.get("impact", "")).strip(),
                "action": str(item.get("action", "")).strip(),
            }
        )
        if len(findings) >= 12:
            break
    return findings


def run_verifier(
    article: str,
    source_text: str,
    brief: dict[str, Any] | None,
    source_map: dict[str, Any] | None,
    request: dict[str, Any] | None,
    out_dir: Path,
    *,
    run: bool = False,
    provider: Any | None = None,
    model: str | None = None,
    temperature: float = 0.0,
    images: list[dict[str, Any]] | None = None,
    visual_plan: dict[str, Any] | None = None,
) -> dict[str, Any]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    brief = brief or {}
    source_map = source_map or {}
    request = request or {}
    source_block = brief.get("source_block")
    if not isinstance(source_block, dict):
        source_block = source_map.get("provenance", {})
    number_ledger = brief.get("number_ledger")
    if not isinstance(number_ledger, list):
        number_ledger = source_map.get("numbers", [])
    image_inputs: list[ImageInput] = []
    image_manifest: list[dict[str, Any]] = []
    for index, item in enumerate(images or []):
        if not isinstance(item, dict):
            continue
        data = item.get("data")
        if not isinstance(data, (bytes, bytearray)) or not data:
            continue
        name = str(item.get("name") or f"image_{index + 1}")
        media_type = str(item.get("media_type") or "image/jpeg")
        image_inputs.append(
            ImageInput(data=bytes(data), media_type=media_type, name=name)
        )
        image_manifest.append(
            {
                "name": name,
                "frame_id": str(item.get("frame_id", "")),
                "caption": str(item.get("caption", "")),
                "media_type": media_type,
            }
        )
    payload = {
        "request": {
            "central_question": request.get("central_question", ""),
            "reader_profile": request.get("reader_profile")
            or DEFAULT_READER_PROFILE,
            "platform": request.get("platform", ""),
            "primary_objective": request.get("primary_objective", ""),
            "video_ids": list(request.get("video_ids") or []),
        },
        "article": article,
        "source_text": source_text,
        "source_block": source_block,
        "number_ledger": number_ledger,
        "concept_ledger": brief.get("concept_ledger", []),
        "mechanism_chain": brief.get("mechanism_chain", []),
    }
    if image_manifest:
        payload["image_manifest"] = image_manifest
    visual_manifest: list[dict[str, Any]] = []
    for visual in (visual_plan or {}).get("visuals", []):
        if not isinstance(visual, dict):
            continue
        caption = str(visual.get("caption", "")).strip()
        core = re.sub(
            r"^\s*(?:看哪里|看这里)\s*[：:]\s*", "", caption
        ).strip()
        if core and core not in article:
            continue
        row: dict[str, Any] = {
            "kind": visual.get("kind", ""),
            "status": visual.get("status", "unknown"),
            "caption": caption,
        }
        if visual.get("frame_id"):
            row["frame_id"] = visual["frame_id"]
        for key in ("diagram", "chart", "table"):
            if isinstance(visual.get(key), dict):
                row[key] = visual[key]
        visual_manifest.append(row)
    if visual_manifest:
        payload["visual_manifest"] = visual_manifest
    system = SYSTEM
    user = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    system_path = out_dir / "prompts" / "verifier.system.txt"
    user_path = out_dir / "prompts" / "verifier.user.txt"
    system_path.parent.mkdir(parents=True, exist_ok=True)
    system_path.write_text(system, encoding="utf-8")
    user_path.write_text(user, encoding="utf-8")
    article_hash = semantic_hash({"article": article}, drop_volatile=False)

    if not run:
        return {
            "schema_version": SCHEMA,
            "status": "dry_run",
            "red_line": False,
            "findings": [],
            "article_hash": article_hash,
            "images": image_manifest,
            "visual_manifest": len(visual_manifest),
            "visual_status": "dry_run",
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
                    "red_line": False,
                    "findings": [],
                    "article_hash": article_hash,
                    "images": image_manifest,
                    "visual_status": "not_provided",
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
                "source_block": source_block,
                "number_ledger": number_ledger,
                "image_hashes": [image.hash() for image in image_inputs],
                "system": system,
                "user": user,
                "model": model_name,
            },
            drop_volatile=False,
        )
        call_kwargs: dict[str, Any] = {
            "stage": "writing_verifier",
            "key": key,
            "system": system,
            "user": user,
            "max_tokens": None,
            "temperature": temperature,
        }
        if image_inputs:
            call_kwargs["images"] = image_inputs
        response = provider.complete(**call_kwargs)
        raw = getattr(response, "text", str(response))
        (out_dir / "raw_response.txt").write_text(raw, encoding="utf-8")
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
            "red_line": False,
            "findings": [],
            "article_hash": article_hash,
            "images": image_manifest,
            "visual_status": "provider_error",
        }
    except (StructuredOutputError, ValueError) as exc:
        return {
            "schema_version": SCHEMA,
            "status": "invalid_output",
            "error": str(exc),
            "red_line": False,
            "findings": [],
            "article_hash": article_hash,
            "images": image_manifest,
            "visual_status": "invalid_output",
        }

    findings = _clean_findings(parsed.get("findings"))
    red_line = bool(parsed.get("red_line")) or any(
        item["severity"] == "critical" for item in findings
    )
    report = {
        "schema_version": SCHEMA,
        "status": "complete",
        "red_line": red_line,
        "findings": findings,
        "article_hash": article_hash,
        "source_block": source_block,
        "images": [
            {
                **row,
                "sha256": image.hash(),
                "bytes": len(image.data),
            }
            for row, image in zip(image_manifest, image_inputs)
        ],
        "visual_manifest": len(visual_manifest),
        "visual_status": "checked" if image_inputs else "not_provided",
        "usage": usage,
        "model": model_name,
        "latency_ms": latency_ms,
        "cached": cached,
        "finish_reason": finish_reason,
    }
    (out_dir / "verifier_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    return report
