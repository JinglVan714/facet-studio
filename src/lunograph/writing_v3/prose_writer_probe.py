"""P1 prose-only Writer probe.

Evaluation harness, not a product path.  It reuses the reader-first method and
examples, replaces the JSON/ID output contract with a Markdown-only contract,
and records one real model call per case/arm.  No claim/evidence IDs, quotes,
timecodes, plan header or self-review are requested from the model; post-hoc
binding is done separately by ``bind_article``.

Dry-run is the default: it builds prompts and writes them without calling the
provider.  Pass ``--run`` to perform the call.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from lunograph.core.config import get_settings
from lunograph.core.hashing import semantic_hash
from lunograph.core.tokens import estimate_text_tokens
from lunograph.providers.llm import CachedLLM, DeepSeekLLM, ProviderError
from lunograph.runtime.budget import BudgetPolicy, BudgetState

PROSE_EVIDENCE = """## Evidence discipline

- Use only facts, numbers, names, and claims present in the evidence. Do not add outside facts, numbers, names, citations, or frames.
- Do not output claim/evidence IDs, timecodes, passage IDs, or audit metadata.
- Do not expand acronyms, canonical names, or units that do not appear verbatim in the evidence. If the evidence has an ASR variant, paraphrase around it; do not silently substitute the canonical form.
- Copy numbers exactly as they appear in the evidence; do not round, convert units, or add precision.
- If you put quotation marks around a phrase, copy that text exactly from the evidence. Paraphrase in plain prose, not in quotation marks.
- Editorial sentences may organize, limit, or synthesize; they must not introduce new facts or causal claims.
- The reader text has no internal IDs, citation keys, timecodes, or audit language.
"""

PROSE_OUTPUT = """## Output

Return one Markdown article. The first line is a single `#` title line, followed by the body. Use optional `##` headings and normal paragraphs.

No JSON, no code fence, no plan header, no self-review, no claim/evidence IDs, no timecodes. Length is advisory: write as short as needed to explain the content clearly.
"""

PROSE_SELF_REVIEW = """## Self-review before returning

Ask, not scan a word list:

1. Does the opening create the reader's question, and does the article answer it?
2. Is there one mechanism/argument chain, or a pile of sections?
3. Does the conclusion add a synthesis/decision, or just repeat the sections?
4. Is the source attribution doing real work, or is "the video/speaker" the default subject?
5. Is every factual statement supported by the evidence, and is anything outside the evidence?
6. For every quoted phrase, is it an exact substring of the evidence? If not, remove the quotation marks and paraphrase.
7. Is any action/observation/number repeated when one mention would do?

If a check fails, revise that part before returning. Do not add rules or words just to pass; write the clearest version.
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


def _section(text: str, start: str, end: str) -> str:
    begin = text.find(start)
    if begin < 0:
        return ""
    finish = text.find(end, begin + len(start))
    if finish < 0:
        return text[begin:]
    return text[begin:finish]


def build_prose_system(
    skill_text: str,
    examples_text: str | None = None,
    *,
    input_kind: str = "text",
) -> str:
    """Replace the JSON/ID skill contract with a Markdown-only contract."""
    if input_kind == "text":
        evidence_line = (
            "- `evidence_text`: the edited transcript, in viewing order. "
            "Use it as the only content source."
        )
    else:
        evidence_line = (
            "- `evidence_view`: a writer view with claims, context sentences and "
            "frames. Use it as the only content source; do not output its IDs."
        )
    intro = skill_text[: skill_text.find("## Inputs")].strip()
    if not intro:
        intro = "# Reader-first explainer"
    method = _section(skill_text, "## Method", "## Evidence discipline").strip()
    if not method:
        method = (
            "## Method\n\nFind one controlling idea, build one mechanism/step "
            "chain, explain terms at first use, and end with a synthesis."
        )
    method = method.replace(
        "Write a short `reader_path` and a `mechanism_or_steps` header.",
        "Decide the reader path and the mechanism/steps internally; keep them "
        "out of the output.",
    ).replace(
        "Prefer `real_frame` only when a frame candidate actually shows the "
        "operation/result/claim. Otherwise use `text_experiment` or `no_demo`; "
        "never imply a demo that the evidence does not contain.",
        "When the evidence includes a visual cue, use it only if it actually "
        "shows the operation/result/claim; otherwise explain it in text. Never "
        "imply a demo that the evidence does not contain.",
    )
    parts = [
        intro,
        "## Inputs\n\n- `request`: central question, reader before/after, "
        "required/forbidden information.\n" + evidence_line,
        method,
        PROSE_EVIDENCE.strip(),
        PROSE_OUTPUT.strip(),
        PROSE_SELF_REVIEW.strip(),
    ]
    if examples_text:
        parts.append("## Examples\n\n" + examples_text.strip())
    parts.append(
        "Return only the Markdown article. No JSON, no code fence, no prose "
        "outside the article."
    )
    return "\n\n".join(parts)


def build_user_prompt(
    request: dict[str, Any],
    input_text: str,
    *,
    input_kind: str,
) -> str:
    if input_kind == "json":
        payload = {
            "request": request,
            "evidence_view": json.loads(input_text),
        }
    else:
        payload = {"request": request, "evidence_text": input_text}
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def _sha_text(text: str) -> str:
    import hashlib

    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "P1 prose-only Writer probe: edited text/view + Markdown contract; "
            "dry-run by default."
        )
    )
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--arm", required=True, help="e.g. new_text / old_input")
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument(
        "--input-kind", choices=["text", "json"], default="text"
    )
    parser.add_argument(
        "--skill-dir",
        type=Path,
        default=Path("skills/writing/reader_first_explainer"),
    )
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--temperature", type=float, default=0.3)
    parser.add_argument("--max-tokens", type=int, default=None)
    parser.add_argument("--budget-tokens", type=int, default=300_000)
    parser.add_argument("--cache-dir", type=Path)
    parser.add_argument("--model", help="override the configured model")
    parser.add_argument(
        "--run",
        action="store_true",
        help="perform the provider call; without it this is a dry run",
    )
    parser.add_argument("--no-cache", action="store_true")
    args = parser.parse_args(argv)

    request = _read_json(args.request)
    input_text = args.input.read_text(encoding="utf-8-sig")
    skill = _skill_body(args.skill_dir / "SKILL.md")
    examples_path = args.skill_dir / "examples.md"
    examples = (
        examples_path.read_text(encoding="utf-8-sig")
        if examples_path.exists()
        else None
    )
    system = build_prose_system(skill, examples, input_kind=args.input_kind)
    user = build_user_prompt(
        request, input_text, input_kind=args.input_kind
    )

    args.out_dir.mkdir(parents=True, exist_ok=True)
    prompts_dir = args.out_dir / "prompts"
    prompts_dir.mkdir(parents=True, exist_ok=True)
    system_path = prompts_dir / "prose_writer.system.txt"
    user_path = prompts_dir / "prose_writer.user.txt"
    system_path.write_text(system, encoding="utf-8")
    user_path.write_text(user, encoding="utf-8")

    model = args.model or "configured"
    manifest = {
        "schema": "p1-prose-probe-v1",
        "case_id": args.case_id,
        "arm": args.arm,
        "input_kind": args.input_kind,
        "input": {
            "path": str(args.input),
            "chars": len(input_text),
            "est_tokens": estimate_text_tokens(input_text),
            "sha256": _sha_text(input_text),
        },
        "request": str(args.request),
        "skill": str(args.skill_dir),
        "system": {
            "path": str(system_path),
            "chars": len(system),
            "sha256": _sha_text(system),
        },
        "user": {
            "path": str(user_path),
            "chars": len(user),
            "sha256": _sha_text(user),
        },
        "model": model,
        "temperature": args.temperature,
        "status": "dry_run",
        "usage": None,
        "latency_ms": None,
        "finish_reason": None,
        "cached": None,
        "article_chars": None,
        "article_est_tokens": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    if not args.run:
        (args.out_dir / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=1),
            encoding="utf-8",
        )
        print(
            json.dumps(
                {
                    "status": "dry_run",
                    "out_dir": str(args.out_dir),
                    "system_chars": len(system),
                    "user_chars": len(user),
                    "input_chars": len(input_text),
                    "note": "no provider call; pass --run to execute",
                },
                ensure_ascii=False,
                indent=1,
            )
        )
        return 0

    from dataclasses import replace

    settings = get_settings()
    if args.model:
        settings = replace(settings, model=args.model)
    model = settings.model
    manifest["model"] = model
    if not settings.provider_configured:
        print("provider 未配置；拒绝伪造 P1 结果", file=sys.stderr)
        return 2

    llm_calls_path = args.out_dir / "llm_calls.jsonl"
    llm_calls_path.write_text("", encoding="utf-8")

    def call_sink(record: dict[str, Any]) -> None:
        with llm_calls_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    policy = BudgetPolicy(max_calls=1, max_tokens=args.budget_tokens)
    budget = BudgetState(policy)
    inner = DeepSeekLLM(settings, budget=budget, call_sink=call_sink)
    cache_dir = args.cache_dir or (settings.runs_root / "_cache" / "llm")
    provider = (
        inner
        if args.no_cache
        else CachedLLM(inner, cache_dir, call_sink=call_sink)
    )
    key = semantic_hash(
        {
            "case_id": args.case_id,
            "arm": args.arm,
            "model": model,
            "system_sha": manifest["system"]["sha256"],
            "user_sha": manifest["user"]["sha256"],
        },
        drop_volatile=False,
    )
    try:
        response = provider.complete(
            stage="p1_prose_writer",
            key=key,
            system=system,
            user=user,
            max_tokens=args.max_tokens,
            temperature=args.temperature,
        )
    except ProviderError as exc:
        manifest["status"] = "provider_error"
        manifest["error"] = {"kind": exc.kind, "message": str(exc)}
        (args.out_dir / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=1),
            encoding="utf-8",
        )
        print(f"provider error: {exc}", file=sys.stderr)
        return 4

    article = response.text
    (args.out_dir / "raw_response.txt").write_text(article, encoding="utf-8")
    (args.out_dir / "article.md").write_text(article, encoding="utf-8")
    manifest.update(
        {
            "status": "complete",
            "usage": response.usage.as_dict(),
            "latency_ms": response.latency_ms,
            "finish_reason": response.finish_reason,
            "cached": response.cached,
            "article_chars": len(article),
            "article_est_tokens": estimate_text_tokens(article),
            "llm_calls": str(llm_calls_path),
        }
    )
    (args.out_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1),
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "status": "complete",
                "case_id": args.case_id,
                "arm": args.arm,
                "usage": manifest["usage"],
                "latency_ms": manifest["latency_ms"],
                "article_chars": manifest["article_chars"],
                "out_dir": str(args.out_dir),
            },
            ensure_ascii=False,
            indent=1,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
