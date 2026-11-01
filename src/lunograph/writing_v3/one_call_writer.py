"""v3 P0: one Skill-driven Writer call.

Input: EvidencePack JSON + Skill directory + request JSON.
Output: writer_output.json, reader.md, raw_response.txt, metrics.json.

No v2 writing chain.  One model call by default; deterministic binding/hygiene
checks; media assets copied when a chosen frame exists.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from lunograph.core.config import get_settings
from lunograph.core.jsonutil import StructuredOutputError, extract_json_object
from lunograph.providers.llm import CachedLLM, DeepSeekLLM, ProviderError
from lunograph.runtime.budget import BudgetPolicy, BudgetState

from .bind_merged_frames import bind_output as bind_merged_frames_output
from .bind_merged_frames import bind_span as bind_merged_frames_span

ID_LIKE = re.compile(r"(?<![A-Za-z0-9])[a-z]{2,8}_[0-9a-f]{6,}(?![A-Za-z0-9])")
CITATION = re.compile(r"\[S\d+\]|\[cite[^\]]*\]", re.IGNORECASE)
TIMECODE = re.compile(r"(?<!\d)\d{1,2}:\d{2}(?::\d{2})?(?!\d)")
NUMBER = re.compile(r"\d+(?:\.\d+)?")

MERGED_FRAMES_CONTRACT = """
## Evidence mode: merged_frames (overrides the skill's evidence_pack discipline)

The evidence is merged transcript passages plus per-segment frame captions. It has no claim/evidence IDs.

- A grounded span must include:
  "grounding_ref": {"passage_id": "<id from evidence>", "quote": "<exact continuous substring of that passage's text>"}
  or for a real frame:
  "grounding_ref": {"frame_id": "<id from evidence>", "caption": "<short look-here caption>"}
- Do NOT output claim_ids/evidence_ids in this mode.
- The quote must be copied exactly from the passage (continuous substring); do not translate, join distant fragments, or add punctuation.
- Numbers in a grounded span must appear in the bound quote or frame caption.
- Editorial spans: role="editorial", no grounding_ref, no claim/evidence/quote; they may organize/limit/synthesize but not add facts.
- The rest of the output schema (plan_header, sections, media_choices, self_review) is unchanged.
"""

LEAN_CW0_CONTRACT = """
## Evidence mode: lean_cw0

evidence_view is the writer view: claims (claim_id/text/status/scope/evidence), context sentences, frames. Use claim/evidence IDs and exact quotes from the view.

- grounded spans carry claim_ids/evidence_ids/quote (the existing skill contract).
- status="bounded" + scope are explicit limitations/qualifications; use them when the article needs a boundary.
- editorial spans carry no binding.
- Do not use claims/quotes/frames that are not in the view.
"""


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _skill_body(path: Path) -> str:
    text = path.read_text(encoding="utf-8-sig")
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) == 3:
            return parts[2].strip()
    return text.strip()


def _span_texts(output: dict[str, Any]):
    for section in output.get("sections", []):
        yield section.get("heading", "")
        for paragraph in section.get("paragraphs", []):
            for span in paragraph.get("spans", []):
                yield span.get("text", "")


def _iter_spans(output: dict[str, Any]):
    for s_index, section in enumerate(output.get("sections", [])):
        for p_index, paragraph in enumerate(section.get("paragraphs", [])):
            for sp_index, span in enumerate(paragraph.get("spans", [])):
                yield (
                    f"s{s_index}/p{p_index}/sp{sp_index}",
                    section,
                    paragraph,
                    span,
                )


def _validate_structure(output: dict[str, Any]) -> list[str]:
    """Mode-independent structure and reader-hygiene checks."""
    issues: list[str] = []
    if not output.get("plan_header", {}).get("title"):
        issues.append("plan_header.title missing")
    if not output.get("sections"):
        issues.append("sections missing")
    for s_index, section in enumerate(output.get("sections", [])):
        if not section.get("section_id"):
            issues.append(f"sections[{s_index}].section_id missing")
        if not section.get("heading"):
            issues.append(f"sections[{s_index}].heading missing")
        if not section.get("paragraphs"):
            issues.append(f"sections[{s_index}].paragraphs missing")
        for p_index, paragraph in enumerate(section.get("paragraphs", [])):
            if not paragraph.get("spans"):
                issues.append(
                    f"sections[{s_index}].paragraphs[{p_index}].spans missing"
                )
            for sp_index, span in enumerate(paragraph.get("spans", [])):
                path = f"sections[{s_index}].paragraphs[{p_index}].spans[{sp_index}]"
                text = span.get("text", "")
                role = span.get("role")
                if not text.strip():
                    issues.append(f"{path}.text empty")
                if role == "editorial":
                    if (
                        span.get("claim_ids")
                        or span.get("evidence_ids")
                        or span.get("quote")
                        or span.get("grounding_ref")
                    ):
                        issues.append(
                            f"{path} editorial carries binding/quote/grounding_ref"
                        )
                elif role != "grounded":
                    issues.append(f"{path} invalid role {role!r}")
    reader_text = "\n".join(_span_texts(output))
    if ID_LIKE.search(reader_text):
        issues.append("reader text contains internal ID")
    if CITATION.search(reader_text):
        issues.append("reader text contains citation marker")
    if TIMECODE.search(reader_text):
        issues.append("reader text contains timecode")
    return issues


def _validate_output(
    output: dict[str, Any], pack: dict[str, Any]
) -> list[str]:
    """Validate a full_pack/lean_cw0 output that carries claim/evidence IDs."""
    issues = _validate_structure(output)
    claims = {c["claim_id"]: c for c in pack.get("claims", [])}
    evidence = {e["evidence_id"]: e for e in pack.get("evidence", [])}
    for path, _section, _paragraph, span in _iter_spans(output):
        if span.get("role") != "grounded":
            continue
        text = span.get("text", "")
        claim_ids = span.get("claim_ids") or []
        evidence_ids = span.get("evidence_ids") or []
        quote = span.get("quote")
        if not claim_ids or not evidence_ids:
            issues.append(f"{path} grounded without claim/evidence")
        for cid in claim_ids:
            if cid not in claims:
                issues.append(f"{path} unknown claim {cid}")
        for eid in evidence_ids:
            if eid not in evidence:
                issues.append(f"{path} unknown evidence {eid}")
        bound_quotes = [
            evidence[eid]["quote"] for eid in evidence_ids if eid in evidence
        ]
        joined = "\n".join(bound_quotes)
        if quote and not any(quote in q for q in bound_quotes):
            issues.append(f"{path}.quote not in bound evidence")
        for number in NUMBER.findall(text):
            if number not in joined:
                issues.append(f"{path} number {number!r} not in bound evidence")
    return issues


def _validate_output_merged_frames(
    output: dict[str, Any],
    pack: dict[str, Any],
    passages: list[dict[str, Any]],
) -> tuple[list[str], dict[str, Any]]:
    """Validate a merged_frames output via grounding_ref and the audit adapter."""
    issues = _validate_structure(output)
    span_by_ref: dict[str, dict[str, Any]] = {}
    for path, _section, _paragraph, span in _iter_spans(output):
        span_by_ref[path] = span
        if span.get("role") != "grounded":
            continue
        ref = span.get("grounding_ref")
        if not isinstance(ref, dict):
            issues.append(f"{path} grounded without grounding_ref")
        elif "frame_id" not in ref and not (ref.get("quote") or "").strip():
            issues.append(f"{path} grounding_ref missing quote")
        if span.get("claim_ids") or span.get("evidence_ids"):
            issues.append(
                f"{path} merged_frames should not carry claim/evidence IDs"
            )
    report = bind_merged_frames_output(output, pack=pack, passages=passages)
    evidence_by_id = {e["evidence_id"]: e for e in pack.get("evidence", [])}
    frames_by_id = {f["frame_id"]: f for f in pack.get("frames", [])}
    for binding in report["bindings"]:
        status = binding["status"]
        path = binding["span_ref"]
        if status not in {"bound", "frame_bound"}:
            issues.append(f"{path} binding {status}: {binding.get('notes')}")
            continue
        span = span_by_ref.get(path, {})
        numbers = NUMBER.findall(span.get("text", ""))
        if not numbers:
            continue
        if status == "bound":
            joined = "\n".join(
                evidence_by_id[eid]["quote"]
                for eid in binding["evidence_ids"]
                if eid in evidence_by_id
            )
        else:
            frame_id = (binding.get("frame") or {}).get("frame_id")
            joined = frames_by_id.get(frame_id, {}).get("caption", "")
        for number in numbers:
            if number not in joined:
                issues.append(f"{path} number {number!r} not in bound evidence")
    return issues, report


def _render_reader(
    output: dict[str, Any],
    pack: dict[str, Any],
    *,
    data_root: Path,
    out_dir: Path,
) -> str:
    lines: list[str] = []
    title = output.get("plan_header", {}).get("title") or "未命名"
    lines.append(f"# {title}")
    lines.append("")
    frame_by_id = {f["frame_id"]: f for f in pack.get("frames", [])}
    media_by_section: dict[str, list[dict[str, Any]]] = {}
    for choice in output.get("media_choices", []):
        media_by_section.setdefault(choice.get("section_id"), []).append(choice)
    for section in output.get("sections", []):
        lines.append(f"## {section.get('heading', '')}")
        lines.append("")
        for paragraph in section.get("paragraphs", []):
            text = "".join(
                span.get("text", "") for span in paragraph.get("spans", [])
            )
            if text:
                lines.append(text)
                lines.append("")
        for choice in media_by_section.get(section.get("section_id"), []):
            frame_id = choice.get("frame_id")
            frame = frame_by_id.get(frame_id)
            if not frame:
                continue
            source = data_root / pack.get("video_id", "") / frame.get("file", "")
            if not source.exists():
                continue
            assets = out_dir / "assets"
            assets.mkdir(parents=True, exist_ok=True)
            asset_name = f"{frame_id}{source.suffix or '.jpg'}"
            shutil.copy2(source, assets / asset_name)
            lines.append(f"![演示画面](assets/{asset_name})")
            lines.append("")
            caption = (choice.get("caption") or "").strip()
            if caption:
                lines.append(f"*{caption}*")
                lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="v3 one-call Writer PoC")
    parser.add_argument("--pack", type=Path, required=True)
    parser.add_argument("--skill-dir", type=Path, required=True)
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--temperature", type=float, default=0.3)
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=None,
        help="optional; default provider/settings max_output_tokens",
    )
    parser.add_argument("--budget-tokens", type=int, default=300_000)
    parser.add_argument("--cache-dir", type=Path)
    parser.add_argument("--no-cache", action="store_true")
    parser.add_argument(
        "--view-mode",
        choices=["full_pack", "merged_frames", "lean_cw0"],
        default="full_pack",
    )
    parser.add_argument("--view", type=Path)
    parser.add_argument("--passages", type=Path)
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)

    if args.view_mode == "merged_frames":
        if args.passages is None:
            parser.error("--view-mode merged_frames 需要 --passages")
        if not args.validate_only and args.view is None:
            parser.error(
                "--view-mode merged_frames 运行需要 --view（rendered text）"
            )
    elif args.view_mode == "lean_cw0" and not args.validate_only and args.view is None:
        parser.error("--view-mode lean_cw0 运行需要 --view（writer view JSON）")

    pack = _read_json(args.pack)
    request = _read_json(args.request)
    passages = (
        _read_json(args.passages).get("passages", []) if args.passages else []
    )
    if args.validate_only:
        if args.output is None:
            raise SystemExit("--validate-only requires --output")
        output = _read_json(args.output)
        args.out_dir.mkdir(parents=True, exist_ok=True)
        metrics_path = args.out_dir / "metrics.json"
        metrics = (
            _read_json(metrics_path) if metrics_path.exists() else {}
        )
        if args.view_mode == "merged_frames":
            issues, report = _validate_output_merged_frames(
                output, pack, passages
            )
            bindings_path = args.out_dir / "bindings.json"
            bindings_path.write_text(
                json.dumps(report, ensure_ascii=False, indent=1),
                encoding="utf-8",
            )
            metrics["binding_status"] = report["status"]
            metrics["binding_counts"] = report["counts"]
            metrics["bindings"] = str(bindings_path)
        else:
            issues = _validate_output(output, pack)
        metrics["status"] = "complete" if not issues else "partial"
        metrics["issues"] = issues
        metrics["view_mode"] = args.view_mode
        metrics_path.write_text(
            json.dumps(metrics, ensure_ascii=False, indent=1), encoding="utf-8"
        )
        print(
            json.dumps(
                {"status": metrics["status"], "issues": issues},
                ensure_ascii=False,
                indent=1,
            )
        )
        return 0 if not issues else 5

    settings = get_settings()
    if not settings.provider_configured:
        print("provider 未配置；拒绝伪造 PoC", file=sys.stderr)
        return 2
    skill = _skill_body(args.skill_dir / "SKILL.md")
    examples_path = args.skill_dir / "examples.md"
    if examples_path.exists():
        skill += "\n\n## Examples\n\n" + examples_path.read_text(encoding="utf-8")
    mode_contract = ""
    if args.view_mode == "merged_frames":
        mode_contract = MERGED_FRAMES_CONTRACT
    elif args.view_mode == "lean_cw0":
        mode_contract = LEAN_CW0_CONTRACT
    system = (
        skill
        + mode_contract
        + "\n\nReturn only one JSON object; no markdown fence, no prose outside JSON."
    )
    view_text = None
    view_json = None
    if args.view_mode == "merged_frames":
        view_text = args.view.read_text(encoding="utf-8")
        user = json.dumps(
            {"request": request, "evidence_text": view_text},
            ensure_ascii=False,
            separators=(",", ":"),
        )
    elif args.view_mode == "lean_cw0":
        view_json = _read_json(args.view)
        user = json.dumps(
            {"request": request, "evidence_view": view_json},
            ensure_ascii=False,
            separators=(",", ":"),
        )
    else:
        user = json.dumps(
            {"request": request, "evidence_pack": pack},
            ensure_ascii=False,
            separators=(",", ":"),
        )

    policy = BudgetPolicy(max_calls=1, max_tokens=args.budget_tokens)
    budget = BudgetState(policy)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    prompts_dir = args.out_dir / "prompts"
    prompts_dir.mkdir(parents=True, exist_ok=True)
    system_path = prompts_dir / "v3_writer.system.txt"
    user_path = prompts_dir / "v3_writer.user.txt"
    system_path.write_text(system, encoding="utf-8")
    user_path.write_text(user, encoding="utf-8")
    llm_calls_path = args.out_dir / "llm_calls.jsonl"
    llm_calls_path.write_text("", encoding="utf-8")

    def call_sink(record: dict[str, Any]) -> None:
        with llm_calls_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    inner = DeepSeekLLM(settings, budget=budget, call_sink=call_sink)
    cache_dir = args.cache_dir or (settings.runs_root / "_cache" / "llm")
    provider = (
        inner
        if args.no_cache
        else CachedLLM(inner, cache_dir, call_sink=call_sink)
    )
    calls: list[dict[str, Any]] = []
    raw_text = ""
    try:
        response = provider.complete(
            stage="v3_writer",
            key=pack["pack_hash"],
            system=system,
            user=user,
            max_tokens=args.max_tokens,
            temperature=args.temperature,
        )
        raw_text = response.text
        calls.append(
            {
                "stage": "v3_writer",
                "model": response.model,
                "latency_ms": response.latency_ms,
                "usage": response.usage.as_dict(),
                "finish_reason": response.finish_reason,
                "cached": response.cached,
            }
        )
        (args.out_dir / "raw_response.txt").write_text(raw_text, encoding="utf-8")
        try:
            output = extract_json_object(raw_text)
        except StructuredOutputError as exc:
            print(f"invalid JSON: {exc}", file=sys.stderr)
            (args.out_dir / "metrics.json").write_text(
                json.dumps({"status": "invalid_json", "calls": calls}, ensure_ascii=False, indent=1),
                encoding="utf-8",
            )
            return 3
    except ProviderError as exc:
        print(f"provider error: {exc}", file=sys.stderr)
        (args.out_dir / "metrics.json").write_text(
            json.dumps({"status": "provider_error", "error": str(exc), "calls": calls}, ensure_ascii=False, indent=1),
            encoding="utf-8",
        )
        return 4

    bindings_path = None
    binding_report = None
    if args.view_mode == "merged_frames":
        issues, binding_report = _validate_output_merged_frames(
            output, pack, passages
        )
        bindings_path = args.out_dir / "bindings.json"
        bindings_path.write_text(
            json.dumps(binding_report, ensure_ascii=False, indent=1),
            encoding="utf-8",
        )
    else:
        issues = _validate_output(output, pack)
    reader = _render_reader(
        output, pack, data_root=settings.data_root, out_dir=args.out_dir
    )
    (args.out_dir / "writer_output.json").write_text(
        json.dumps(output, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    (args.out_dir / "reader.md").write_text(reader, encoding="utf-8")
    if view_text is not None:
        view_chars = len(view_text)
    elif view_json is not None:
        view_chars = len(
            json.dumps(
                view_json, ensure_ascii=False, separators=(",", ":")
            )
        )
    else:
        view_chars = len(
            json.dumps(pack, ensure_ascii=False, separators=(",", ":"))
        )
    metrics = {
        "status": "complete" if not issues else "partial",
        "issues": issues,
        "view_mode": args.view_mode,
        "view_path": str(args.view) if args.view else None,
        "view_chars": view_chars,
        "binding_status": (
            binding_report["status"] if binding_report else None
        ),
        "binding_counts": (
            binding_report["counts"] if binding_report else None
        ),
        "bindings": str(bindings_path) if bindings_path else None,
        "calls": calls,
        "cached": response.cached,
        "reader_chars": len(reader),
        "pack_chars": pack.get("pack_chars"),
        "pack_id": pack.get("pack_id"),
        "pack_hash": pack.get("pack_hash"),
        "skill": str(args.skill_dir),
        "prompt_system": str(system_path),
        "prompt_user": str(user_path),
        "llm_calls": str(llm_calls_path),
        "cache_dir": str(cache_dir),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    (args.out_dir / "metrics.json").write_text(
        json.dumps(metrics, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    print(json.dumps(metrics, ensure_ascii=False, indent=1))
    return 0 if not issues else 5


if __name__ == "__main__":
    sys.exit(main())
