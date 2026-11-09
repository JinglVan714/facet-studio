"""Grounding / hallucination-candidate audit (P4).

Read-only over a run's Markdown and its exact content manuscript.  It does not
score writing quality and does not claim a hallucination rate: it lists
candidate flags (numbers, quotes, proper nouns, scope upgrades) with context so
a human can decide whether a flag is a source fact, model explanation, or an
invented video fact.

Model knowledge is explicitly allowed.  A flag means "not found in the content
manuscript", not "wrong".
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..core.config import get_settings

# Chinese characters are ``\w`` in Python, so a ``(?<![\w.])`` boundary
# silently skips numbers written next to Chinese text (``30多分钟``).  Use an
# ASCII-only boundary so those numbers are audited, while ``V4`` stays part
# of an entity rather than becoming a number.
NUMBER_RE = re.compile(r"(?<![A-Za-z0-9_.])\d+(?:[.,]\d+)*(?:%|％)?")
QUOTE_RE = re.compile(r"[「『“\"]([^」』”\"\n]{2,80})[」』”\"]")
ENTITY_RE = re.compile(
    r"\b(?:[A-Z][A-Za-z0-9]*(?:[-.][A-Za-z0-9]+)*|[A-Z]{2,}\d*)\b"
)
SCOPE_TERMS = re.compile(
    r"所有|全部|一定|从来|唯一|官方|已证实|必然|绝对|百分之百|100%|永远|"
    r"任何人|毫无例外|从不|总能|完全"
)
CODE_FENCE_RE = re.compile(r"```.*?```", re.DOTALL)
IMAGE_RE = re.compile(r"!\[[^\]]*\]\([^)]+\)")
URL_RE = re.compile(r"https?://\S+")
SOURCE_RE = re.compile(r"^\s*(?:本文根据|内容参考|本脚本根据).*$", re.MULTILINE)
SPACE_RE = re.compile(r"\s+")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _clean(text: str) -> str:
    text = CODE_FENCE_RE.sub(" ", text)
    text = IMAGE_RE.sub(" ", text)
    text = URL_RE.sub(" ", text)
    text = re.sub(r"figures/[^\s)）]+", " ", text)
    # Ordered-list markers are structure, not claims.
    text = re.sub(r"(?m)^\s*\d+[.)、]\s*", " ", text)
    text = SOURCE_RE.sub(" ", text)
    return SPACE_RE.sub(" ", text).strip()


def _canonical_number(value: str) -> str:
    return value.replace(",", "").replace("，", "").replace("％", "%")


def _numbers(text: str) -> list[str]:
    return [_canonical_number(item) for item in NUMBER_RE.findall(_clean(text))]


def _number_context(text: str, value: str, width: int = 32) -> str:
    clean = _clean(text)
    index = clean.find(value)
    if index < 0:
        index = clean.replace(",", "").find(value.replace(",", ""))
    if index < 0:
        return ""
    start = max(0, index - width)
    end = min(len(clean), index + len(value) + width)
    return ("…" if start else "") + clean[start:end] + ("…" if end < len(clean) else "")


def _quotes(text: str) -> list[str]:
    return [
        SPACE_RE.sub(" ", item).strip()
        for item in QUOTE_RE.findall(_clean(text))
        if item.strip()
    ]


def _entities(text: str) -> list[str]:
    return sorted(
        {
            item
            for item in ENTITY_RE.findall(_clean(text))
            if len(item) >= 3
        }
    )


def _scope_terms(text: str) -> list[str]:
    return sorted(set(SCOPE_TERMS.findall(_clean(text))))


def _audit_run(
    *,
    case_id: str,
    run_id: str,
    run_dir: Path,
) -> dict[str, Any]:
    meta = _read_json(run_dir / "run_meta.json")
    form = str(meta.get("form") or "")
    form_dir = Path(str(meta.get("form_dir") or run_dir / form))
    output_name = str(meta.get("output") or ("note.md" if form == "xiaohongshu_note" else "article.md"))
    output_path = form_dir / output_name
    content_path = run_dir / "content" / "content.md"
    if not output_path.is_file() or not content_path.is_file():
        return {
            "case_id": case_id,
            "run_id": run_id,
            "form": form,
            "status": "missing_artifact",
            "flags": [],
            "runtime": {},
        }

    output = _read_text(output_path)
    content = _read_text(content_path)
    content_text = _clean(content)
    content_compact = SPACE_RE.sub("", content_text)
    content_numbers = set(_numbers(content))
    content_quotes = set(_quotes(content))
    content_entities = set(_entities(content))
    content_scope = set(_scope_terms(content))

    flags: list[dict[str, Any]] = []
    output_numbers = _numbers(output)
    for value in sorted(set(output_numbers)):
        if value not in content_numbers:
            flags.append(
                {
                    "kind": "number_not_in_content",
                    "value": value,
                    "context": _number_context(output, value),
                    "note": "candidate; model knowledge/derived number or invented fact",
                }
            )
    # Short quoted terms are usually emphasis, not claimed quotations.
    output_quotes = {quote for quote in _quotes(output) if len(quote) >= 6}
    for quote in sorted(output_quotes):
        if quote not in content_quotes and quote not in content_text:
            flags.append(
                {
                    "kind": "quote_not_in_content",
                    "value": quote,
                    "context": "",
                    "note": "candidate; may be editorial emphasis or an invented quote",
                }
            )

    for entity in sorted(set(_entities(output))):
        if entity in content_entities or SPACE_RE.sub("", entity) in content_compact:
            continue
        flags.append(
            {
                "kind": "entity_not_in_content",
                "value": entity,
                "context": "",
                "note": "candidate; may be general knowledge/explanation",
            }
        )

    for term in sorted(set(_scope_terms(output)) - content_scope):
        flags.append(
            {
                "kind": "scope_term_not_in_content",
                "value": term,
                "context": "",
                "note": "candidate scope upgrade; check whether the source supports it",
            }
        )

    review_path = run_dir / "publish_review.json"
    review = _read_json(review_path) if review_path.is_file() else {}
    write = meta.get("write") or {}
    planner_usage = meta.get("planner_usage") or {}
    write_usage = write.get("usage") or {}
    return {
        "case_id": case_id,
        "run_id": run_id,
        "form": form,
        "status": str(meta.get("status") or ""),
        "review": review.get("decision") or "missing",
        "runtime": {
            "total_tokens": int(planner_usage.get("total_tokens") or 0)
            + int(write_usage.get("total_tokens") or 0),
            "latency_ms": int(meta.get("planner_latency_ms") or 0)
            + int(write.get("latency_ms") or 0),
        },
        "numbers": {
            "checked": len(set(output_numbers)),
            "grounded": len(set(output_numbers) & content_numbers),
            "all": sorted(set(output_numbers)),
            "candidates": sorted(set(output_numbers) - content_numbers),
        },
        "quotes": {
            "checked": len(output_quotes),
            "grounded": len(
                {
                    quote
                    for quote in output_quotes
                    if quote in content_quotes or quote in content_text
                }
            ),
            "candidates": sorted(
                {
                    quote
                    for quote in output_quotes
                    if quote not in content_quotes and quote not in content_text
                }
            ),
        },
        "entities": {
            "checked": len(set(_entities(output))),
            "grounded": len(set(_entities(output)) & content_entities),
            "candidates": sorted(set(_entities(output)) - content_entities),
        },
        "scope": {
            "in_content": sorted(set(_scope_terms(output)) & content_scope),
            "candidates": sorted(set(_scope_terms(output)) - content_scope),
        },
        "flags": flags,
    }


def _cross_form(artifacts: list[dict[str, Any]], cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    video_by_case = {
        str(spec.get("case_id")): str(spec.get("video_id") or "")
        for spec in cases
    }
    grouped: dict[str, dict[str, set[str]]] = {}
    for item in artifacts:
        if item.get("status") == "missing_artifact":
            continue
        video = video_by_case.get(item["case_id"], "")
        if not video:
            continue
        numbers = set(item.get("numbers", {}).get("all") or [])
        form = item.get("form") or "unknown"
        grouped.setdefault(video, {}).setdefault(form, set())
        grouped[video][form].update(numbers)
    result: list[dict[str, Any]] = []
    for video, forms in sorted(grouped.items()):
        result.append(
            {
                "video_id": video,
                "forms": {
                    form: sorted(values) for form, values in sorted(forms.items())
                },
                "note": "candidate-number coverage by form; omission is not a contradiction",
            }
        )
    return result


def audit(
    cases: list[dict[str, Any]], *, runs_root: Path
) -> dict[str, Any]:
    artifacts: list[dict[str, Any]] = []
    seen: set[str] = set()
    for spec in cases:
        run_id = str(spec.get("run_id") or "")
        if not run_id or run_id in seen:
            continue
        seen.add(run_id)
        artifacts.append(
            _audit_run(
                case_id=str(spec.get("case_id") or ""),
                run_id=run_id,
                run_dir=runs_root / "product_v1" / run_id,
            )
        )
    flags = [flag for item in artifacts for flag in item.get("flags", [])]
    by_kind: dict[str, int] = {}
    for flag in flags:
        by_kind[flag["kind"]] = by_kind.get(flag["kind"], 0) + 1
    runtime = {
        "artifacts": len(artifacts),
        "flags": len(flags),
        "flags_by_kind": by_kind,
        "total_tokens": sum(item.get("runtime", {}).get("total_tokens", 0) for item in artifacts),
        "latency_ms": sum(item.get("runtime", {}).get("latency_ms", 0) for item in artifacts),
    }
    return {
        "schema_version": "grounding-audit-v1",
        "created_at": _now(),
        "summary": {
            **runtime,
            "note": (
                "Candidate flags only: not found in the content manuscript. "
                "Model knowledge is allowed; quotes shorter than 6 chars are treated "
                "as emphasis, not claims. This is not a hallucination rate and not a "
                "writing-quality score. Human adjudication is optional."
            ),
        },
        "artifacts": artifacts,
        "cross_form": _cross_form(artifacts, cases),
    }


def render_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# Grounding / hallucination-candidate audit",
        "",
        f"- created_at: `{report['created_at']}`",
        f"- artifacts: {summary['artifacts']}",
        f"- candidate flags: {summary['flags']}",
        f"- by kind: {summary['flags_by_kind']}",
        f"- tokens: {summary['total_tokens']}",
        f"- latency: {summary['latency_ms']} ms",
        "",
        "> Candidate = not found in the content manuscript. Model knowledge is allowed; "
        "this is not a hallucination rate, not a writing-quality score.",
        "",
        "| case | form | status | review | tokens | latency | flags |",
        "|---|---|---|---|---:|---:|---:|",
    ]
    for item in report["artifacts"]:
        runtime = item.get("runtime") or {}
        lines.append(
            f"| {item.get('case_id')} | {item.get('form')} | {item.get('status')} | "
            f"{item.get('review')} | {runtime.get('total_tokens', 0)} | "
            f"{runtime.get('latency_ms', 0)} | {len(item.get('flags', []))} |"
        )
    lines += ["", "## Flags", ""]
    for item in report["artifacts"]:
        if not item.get("flags"):
            continue
        lines.append(f"### {item['case_id']} · {item['run_id']}")
        for flag in item["flags"]:
            context = f" — {flag['context']}" if flag.get("context") else ""
            lines.append(
                f"- `{flag['kind']}` `{flag['value']}`{context}"
            )
        lines.append("")
    lines += ["## Cross-form candidate numbers", ""]
    for item in report.get("cross_form") or []:
        lines.append(f"- **{item['video_id']}**: {item['forms']}")
    lines += ["", "## Note", "", summary["note"], ""]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Grounding / hallucination-candidate audit")
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--runs-root", type=Path, default=None)
    args = parser.parse_args(argv)

    cases_payload = _read_json(args.cases)
    cases = cases_payload.get("cases") or []
    settings = get_settings()
    runs_root = args.runs_root or settings.runs_root
    report = audit(cases, runs_root=Path(runs_root))
    args.out.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    json_path = args.out / f"grounding-{stamp}.json"
    md_path = args.out / f"grounding-{stamp}.md"
    json_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    md_path.write_text(render_markdown(report), encoding="utf-8")
    print(json_path)
    print(md_path)
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
