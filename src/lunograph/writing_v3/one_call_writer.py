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
from lunograph.providers.llm import DeepSeekLLM, ProviderError
from lunograph.runtime.budget import BudgetPolicy, BudgetState

ID_LIKE = re.compile(r"(?<![A-Za-z0-9])[a-z]{2,8}_[0-9a-f]{6,}(?![A-Za-z0-9])")
CITATION = re.compile(r"\[S\d+\]|\[cite[^\]]*\]", re.IGNORECASE)
TIMECODE = re.compile(r"(?<!\d)\d{1,2}:\d{2}(?::\d{2})?(?!\d)")
NUMBER = re.compile(r"\d+(?:\.\d+)?")


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


def _validate_output(
    output: dict[str, Any], pack: dict[str, Any]
) -> list[str]:
    issues: list[str] = []
    claims = {c["claim_id"]: c for c in pack.get("claims", [])}
    evidence = {e["evidence_id"]: e for e in pack.get("evidence", [])}
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
                claim_ids = span.get("claim_ids") or []
                evidence_ids = span.get("evidence_ids") or []
                quote = span.get("quote")
                if not text.strip():
                    issues.append(f"{path}.text empty")
                if role == "grounded":
                    if not claim_ids or not evidence_ids:
                        issues.append(f"{path} grounded without claim/evidence")
                    for cid in claim_ids:
                        if cid not in claims:
                            issues.append(f"{path} unknown claim {cid}")
                    for eid in evidence_ids:
                        if eid not in evidence:
                            issues.append(f"{path} unknown evidence {eid}")
                    bound_quotes = [
                        evidence[eid]["quote"]
                        for eid in evidence_ids
                        if eid in evidence
                    ]
                    joined = "\n".join(bound_quotes)
                    if quote and not any(quote in q for q in bound_quotes):
                        issues.append(f"{path}.quote not in bound evidence")
                    for number in NUMBER.findall(text):
                        if number not in joined:
                            issues.append(
                                f"{path} number {number!r} not in bound evidence"
                            )
                elif role == "editorial":
                    if claim_ids or evidence_ids or quote:
                        issues.append(f"{path} editorial carries binding/quote")
                else:
                    issues.append(f"{path} invalid role {role!r}")
    reader_text = "\n".join(_span_texts(output))
    if ID_LIKE.search(reader_text):
        issues.append("reader text contains internal ID")
    if CITATION.search(reader_text):
        issues.append("reader text contains citation marker")
    if TIMECODE.search(reader_text):
        issues.append("reader text contains timecode")
    return issues


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
    parser.add_argument("--max-tokens", type=int, default=65536)
    parser.add_argument("--budget-tokens", type=int, default=300_000)
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)

    pack = _read_json(args.pack)
    request = _read_json(args.request)
    if args.validate_only:
        if args.output is None:
            raise SystemExit("--validate-only requires --output")
        output = _read_json(args.output)
        issues = _validate_output(output, pack)
        args.out_dir.mkdir(parents=True, exist_ok=True)
        metrics_path = args.out_dir / "metrics.json"
        metrics = (
            _read_json(metrics_path) if metrics_path.exists() else {}
        )
        metrics["status"] = "complete" if not issues else "partial"
        metrics["issues"] = issues
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
    system = skill + "\n\nReturn only one JSON object; no markdown fence, no prose outside JSON."
    user = json.dumps(
        {"request": request, "evidence_pack": pack},
        ensure_ascii=False,
        separators=(",", ":"),
    )

    policy = BudgetPolicy(max_calls=1, max_tokens=args.budget_tokens)
    budget = BudgetState(policy)
    provider = DeepSeekLLM(settings, budget=budget)
    args.out_dir.mkdir(parents=True, exist_ok=True)
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

    issues = _validate_output(output, pack)
    reader = _render_reader(
        output, pack, data_root=settings.data_root, out_dir=args.out_dir
    )
    (args.out_dir / "writer_output.json").write_text(
        json.dumps(output, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    (args.out_dir / "reader.md").write_text(reader, encoding="utf-8")
    metrics = {
        "status": "complete" if not issues else "partial",
        "issues": issues,
        "calls": calls,
        "reader_chars": len(reader),
        "pack_chars": pack.get("pack_chars"),
        "pack_id": pack.get("pack_id"),
        "skill": str(args.skill_dir),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    (args.out_dir / "metrics.json").write_text(
        json.dumps(metrics, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    print(json.dumps(metrics, ensure_ascii=False, indent=1))
    return 0 if not issues else 5


if __name__ == "__main__":
    sys.exit(main())
