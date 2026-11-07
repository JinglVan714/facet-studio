"""Two-step index+parts probe for large writer bundles.

Step 1: read the writer index (segment labels + claims, no quotes/context)
and select the part_ids needed for the questions.
Step 2: read only the selected parts and answer the same fixed questions.

This is the C consumption path from the view contract.  It is a probe, not a
writing stage: dry-run by default, one selection call + one answer call per
case with ``--run``.  See docs/s2-probe/protocol.md.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any

from facet_studio.core.hashing import semantic_hash
from facet_studio.core.jsonutil import StructuredOutputError, extract_json_object
from facet_studio.providers.llm import (
    CachedLLM,
    DeepSeekLLM,
    ProviderError,
)

from .probe import SYSTEM as ANSWER_SYSTEM
from .probe import build_user_prompt, load_questions

SELECT_SYSTEM = """你是一个证据选择器。给定一个 writer index 和一组问题，选出回答问题所需的 part。

规则：
- index 的每个 segment 有 part_id、label 和 claims；只根据 index 判断哪些 part 需要读。
- 只返回一个 JSON 对象：{"part_ids":["part_01","part_02"]}。
- 不要回答问题；不要选 index 里不存在的 part；至少选一个 part。
- 宁可多选一个相邻 part，也不要漏掉回答所需的证据。
"""


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _sha_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _compact(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def build_selection_prompt(
    index: dict[str, Any], questions: list[dict[str, Any]]
) -> str:
    numbered = "\n".join(
        f"{i}. {item['question']}"
        for i, item in enumerate(questions, start=1)
    )
    return (
        "Index:\n<<<\n"
        f"{_compact(index)}\n"
        ">>>\n\n"
        "Questions:\n"
        f"{numbered}\n\n"
        'Return only {"part_ids":["part_01", ...]} with the parts needed.'
    )


def parse_selection(text: str, valid_part_ids: set[str]) -> list[str]:
    """Parse and validate part_ids; return [] when nothing valid is selected."""
    try:
        payload = extract_json_object(text)
    except StructuredOutputError:
        return []
    raw = payload.get("part_ids")
    if not isinstance(raw, list):
        return []
    selected: list[str] = []
    for item in raw:
        if not isinstance(item, str):
            continue
        if item not in valid_part_ids or item in selected:
            continue
        selected.append(item)
    return selected


def load_selected_segments(
    parts_dir: Path, part_ids: list[str]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return (selected parts, flattened segments) in the given order."""
    parts: list[dict[str, Any]] = []
    segments: list[dict[str, Any]] = []
    for part_id in part_ids:
        path = parts_dir / f"{part_id}.json"
        part = _read_json(path)
        parts.append(part)
        segments.extend(part.get("segments", []))
    return parts, segments


def build_answer_input(
    segments: list[dict[str, Any]], index: dict[str, Any]
) -> str:
    """Flatten selected parts into the same writer-view shape as the A view."""
    return _compact(
        {
            "schema": "writer-view-v1",
            "segments": segments,
            "gaps": index.get("gaps", []),
            "conflicts": index.get("conflicts", []),
        }
    )


def _summary(
    *,
    case_id: str,
    status: str,
    model: str,
    index_path: Path,
    questions_path: Path,
    questions_count: int,
    index_chars: int,
    part_sizes: dict[str, int],
    selection: dict[str, Any],
    answer: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema": "s2-probe-index-parts-v1",
        "case_id": case_id,
        "status": status,
        "model": model,
        "params": {
            "max_tokens": None,
            "max_tokens_source": "provider_default",
            "temperature": 0.0,
        },
        "index": {
            "path": str(index_path),
            "chars": index_chars,
            "sha256": _sha_text(index_path.read_text(encoding="utf-8-sig")),
        },
        "questions": {
            "path": str(questions_path),
            "count": questions_count,
        },
        "part_sizes": part_sizes,
        "selection": selection,
        "answer": answer,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Two-step index+parts probe (select parts, then answer)."
    )
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--index", type=Path, required=True)
    parser.add_argument("--parts-dir", type=Path, required=True)
    parser.add_argument("--questions", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--model")
    parser.add_argument("--cache-dir", type=Path)
    parser.add_argument("--no-cache", action="store_true")
    args = parser.parse_args(argv)

    try:
        questions_payload = load_questions(args.questions)
    except (OSError, ValueError) as exc:
        print(f"invalid questions: {exc}", file=sys.stderr)
        return 4
    questions = questions_payload["questions"]
    index = _read_json(args.index)
    valid_part_ids = {
        segment.get("part_id")
        for segment in index.get("segments", [])
        if isinstance(segment.get("part_id"), str)
    }
    if not valid_part_ids:
        print("index 没有 part_id", file=sys.stderr)
        return 4
    part_sizes: dict[str, int] = {}
    for part_id in sorted(valid_part_ids):
        path = args.parts_dir / f"{part_id}.json"
        if not path.exists():
            print(f"缺少 part 文件: {path}", file=sys.stderr)
            return 4
        part_sizes[part_id] = len(path.read_text(encoding="utf-8-sig"))

    args.out_dir.mkdir(parents=True, exist_ok=True)
    select_system_path = args.out_dir / "prompts" / "select.system.txt"
    select_user_path = args.out_dir / "prompts" / "select.user.txt"
    answer_system_path = args.out_dir / "prompts" / "answer.system.txt"
    answer_user_path = args.out_dir / "prompts" / "answer.user.txt"
    for path in (
        select_system_path,
        select_user_path,
        answer_system_path,
        answer_user_path,
    ):
        path.parent.mkdir(parents=True, exist_ok=True)
    select_system_path.write_text(SELECT_SYSTEM, encoding="utf-8")
    select_user_path.write_text(
        build_selection_prompt(index, questions), encoding="utf-8"
    )
    answer_system_path.write_text(ANSWER_SYSTEM, encoding="utf-8")

    index_text = _compact(index)
    index_chars = len(index_text)
    index_sha = _sha_text(index_text)
    selection = {
        "raw": None,
        "part_ids": [],
        "usage": None,
        "latency_ms": None,
        "error": None,
    }
    answer = {
        "raw": None,
        "chars": None,
        "usage": None,
        "latency_ms": None,
        "error": None,
    }

    if not args.run:
        (args.out_dir / "manifest.json").write_text(
            json.dumps(
                _summary(
                    case_id=args.case_id,
                    status="dry_run",
                    model="",
                    index_path=args.index,
                    questions_path=args.questions,
                    questions_count=len(questions),
                    index_chars=index_chars,
                    part_sizes=part_sizes,
                    selection=selection,
                    answer=answer,
                ),
                ensure_ascii=False,
                indent=1,
            ),
            encoding="utf-8",
        )
        print(
            json.dumps(
                {
                    "status": "dry_run",
                    "case_id": args.case_id,
                    "index_chars": index_chars,
                    "part_sizes": part_sizes,
                    "note": "no provider call; pass --run to select and answer",
                },
                ensure_ascii=False,
                indent=1,
            )
        )
        return 0

    from facet_studio.core.config import get_settings

    settings = get_settings()
    if args.model:
        settings = replace(settings, model=args.model)
    if not settings.provider_configured:
        print("provider 未配置；拒绝伪造 probe 结果", file=sys.stderr)
        return 2

    llm_calls_path = args.out_dir / "llm_calls.jsonl"
    llm_calls_path.write_text("", encoding="utf-8")

    def call_sink(record: dict[str, Any]) -> None:
        row = dict(record)
        raw = row.pop("raw_response", "")
        row["raw_response_sha256"] = _sha_text(raw)
        row["raw_response_chars"] = len(raw)
        with llm_calls_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    inner = DeepSeekLLM(settings, call_sink=call_sink)
    cache_dir = args.cache_dir or (settings.runs_root / "_cache" / "llm")
    provider = (
        inner
        if args.no_cache
        else CachedLLM(inner, cache_dir, call_sink=call_sink)
    )

    select_user_text = select_user_path.read_text(encoding="utf-8")
    select_key = semantic_hash(
        {
            "case_id": args.case_id,
            "step": "select",
            "index_sha": index_sha,
            "questions": [item["question"] for item in questions],
        },
        drop_volatile=False,
    )
    try:
        select_response = provider.complete(
            stage="s2_probe_select",
            key=select_key,
            system=SELECT_SYSTEM,
            user=select_user_text,
            temperature=args.temperature,
        )
    except ProviderError as exc:
        selection["error"] = {"kind": exc.kind, "message": str(exc)}
        (args.out_dir / "manifest.json").write_text(
            json.dumps(
                _summary(
                    case_id=args.case_id,
                    status="error",
                    model=settings.model,
                    index_path=args.index,
                    questions_path=args.questions,
                    questions_count=len(questions),
                    index_chars=index_chars,
                    part_sizes=part_sizes,
                    selection=selection,
                    answer=answer,
                ),
                ensure_ascii=False,
                indent=1,
            ),
            encoding="utf-8",
        )
        return 3

    (args.out_dir / "selection_raw.txt").write_text(
        select_response.text, encoding="utf-8"
    )
    selected_ids = parse_selection(select_response.text, valid_part_ids)
    selection_error = None
    if not selected_ids:
        selected_ids = sorted(valid_part_ids)
        selection_error = "selection_invalid_fallback_all"
    selection.update(
        {
            "raw": {
                "path": str(args.out_dir / "selection_raw.txt"),
                "chars": len(select_response.text),
            },
            "part_ids": selected_ids,
            "usage": select_response.usage.as_dict(),
            "latency_ms": select_response.latency_ms,
            "error": selection_error,
            "cached": select_response.cached,
        }
    )
    (args.out_dir / "selection.json").write_text(
        json.dumps({"part_ids": selected_ids}, ensure_ascii=False, indent=1),
        encoding="utf-8",
    )

    parts, segments = load_selected_segments(args.parts_dir, selected_ids)
    answer_input = build_answer_input(segments, index)
    answer_user = build_user_prompt(answer_input, questions)
    answer_user_path.write_text(answer_user, encoding="utf-8")
    answer_key = semantic_hash(
        {
            "case_id": args.case_id,
            "step": "answer",
            "parts": selected_ids,
            "questions": [item["question"] for item in questions],
        },
        drop_volatile=False,
    )
    try:
        answer_response = provider.complete(
            stage="s2_probe_answer",
            key=answer_key,
            system=ANSWER_SYSTEM,
            user=answer_user,
            temperature=args.temperature,
        )
    except ProviderError as exc:
        answer["error"] = {"kind": exc.kind, "message": str(exc)}
        (args.out_dir / "manifest.json").write_text(
            json.dumps(
                _summary(
                    case_id=args.case_id,
                    status="partial",
                    model=settings.model,
                    index_path=args.index,
                    questions_path=args.questions,
                    questions_count=len(questions),
                    index_chars=index_chars,
                    part_sizes=part_sizes,
                    selection=selection,
                    answer=answer,
                ),
                ensure_ascii=False,
                indent=1,
            ),
            encoding="utf-8",
        )
        return 3

    answer_path = args.out_dir / "answer.txt"
    answer_path.write_text(answer_response.text, encoding="utf-8")
    answer.update(
        {
            "raw": {
                "path": str(answer_path),
                "chars": len(answer_response.text),
            },
            "chars": len(answer_input),
            "usage": answer_response.usage.as_dict(),
            "latency_ms": answer_response.latency_ms,
            "error": None,
            "cached": answer_response.cached,
        }
    )
    status = "complete" if selection_error is None else "partial"
    (args.out_dir / "manifest.json").write_text(
        json.dumps(
            _summary(
                case_id=args.case_id,
                status=status,
                model=settings.model,
                index_path=args.index,
                questions_path=args.questions,
                questions_count=len(questions),
                index_chars=index_chars,
                part_sizes=part_sizes,
                selection=selection,
                answer=answer,
            ),
            ensure_ascii=False,
            indent=1,
        ),
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "status": status,
                "case_id": args.case_id,
                "selected": selected_ids,
                "selection_usage": selection["usage"],
                "selection_error": selection_error,
                "answer_input_chars": len(answer_input),
                "answer_usage": answer["usage"],
                "latency_ms": (
                    (selection["latency_ms"] or 0)
                    + (answer["latency_ms"] or 0)
                ),
                "out_dir": str(args.out_dir),
            },
            ensure_ascii=False,
            indent=1,
        )
    )
    return 0 if status in {"complete", "partial"} else 3


if __name__ == "__main__":
    sys.exit(main())
