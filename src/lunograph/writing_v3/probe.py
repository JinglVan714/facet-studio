"""S2 probe: fixed questions over raw ASR / merged transcript / lean view.

This is an evaluation harness, not a writing stage.  It renders one video's
substrate in four comparable forms (raw ASR, merged text, lean view, merged
text + frames), asks the same fixed questions, and records one model call per
form.  The renderers add no facts and no per-video hints.

Dry-run is the default: it renders inputs and prompts and writes a manifest,
but does not call the provider.  Pass ``--run`` to perform the calls.

See docs/s2-probe/protocol.md for the probe protocol and scoring rules.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any

from lunograph.core.hashing import semantic_hash
from lunograph.providers.llm import (
    CachedLLM,
    DeepSeekLLM,
    ProviderError,
)

VARIANTS = ("raw_asr", "merged_text", "lean_view")
MERGED_TEXT_FRAMES = "merged_text_frames"

SYSTEM = """你只能根据给定输入回答关于一个视频的问题。

输入可能是以下形式之一：
- 原始 ASR 单元：每行一个单元，含起止秒数和逐字转写文本；
- 合并后的转写：段落 ID、时间范围、合并后的原文；
- 合并转写 + 帧：段落 ID/时间/原文，每段后跟一行 `frames: [frame_id] caption`；帧只作视觉证据；
- 结构化 writer view（JSON）：segments 内含 claims、context 句子和 frames。此形式中，evidence 的 `span:[start,end]` 是 `"".join(segment.context)` 的下标区间；若给出 `quote`，它是精确的兜底引文。claim 的 `status:"bounded"` + `scope` 表示视频明确说的限制、不确定或适用范围；回答边界问题时优先使用这些 claim。

规则：
- 只使用输入中出现的事实，不补充外部知识。
- 如果输入证据不足，明确说“证据不足”并说明缺什么；不要猜。
- 按题号逐题回答；答案简洁、具体。
- 要求逐字引用时，复制原文连续子串，不要改写或翻译。
"""


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8-sig").splitlines()
        if line.strip()
    ]


def _sha_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _file_info(path: Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    return {
        "path": str(path),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "bytes": path.stat().st_size,
    }


def render_raw_asr(units: list[dict[str, Any]]) -> str:
    """Render ASR units as one line per unit: time range + exact text."""
    lines: list[str] = []
    for unit in units:
        times = unit.get("t") or [0, 0]
        start = int(times[0]) / 1000 if len(times) > 0 else 0.0
        end = int(times[1]) / 1000 if len(times) > 1 else 0.0
        channel = unit.get("channel") or ""
        suffix = "" if channel in ("", "speech") else f" ({channel})"
        lines.append(f"[{start:.2f}-{end:.2f}s]{suffix} {unit.get('raw', '')}")
    return "\n".join(lines)


def render_merged_text(passages: list[dict[str, Any]]) -> str:
    """Render merged passages with IDs and time ranges; no claims/quotes/frames."""
    lines: list[str] = []
    previous_segment: str | None = None
    for passage in passages:
        segment_id = passage.get("segment_id") or ""
        if previous_segment is not None and segment_id != previous_segment:
            lines.append("")
        previous_segment = segment_id
        start = int(passage.get("t_start_ms", 0)) / 1000
        end = int(passage.get("t_end_ms", 0)) / 1000
        lines.append(
            f"[{passage.get('passage_id', '')} {start:.2f}-{end:.2f}s] "
            f"{passage.get('text', '')}"
        )
    return "\n".join(lines)


def render_lean_view(view: dict[str, Any]) -> str:
    """Render the A lean view exactly as a writer-facing compact JSON input."""
    return json.dumps(view, ensure_ascii=False, separators=(",", ":"))


def render_merged_text_with_frames(
    passages: list[dict[str, Any]], view: dict[str, Any]
) -> str:
    """Render merged text plus per-segment frame captions; no claims/IDs.

    This is the B+frames ablation: same transcript text as merged_text, plus
    the same frame captions that the lean view carries.  It answers whether
    frames alone can reproduce the lean view's frame-only advantage without
    paying for claim/evidence/context duplication.
    """
    groups: list[tuple[str, list[dict[str, Any]]]] = []
    for passage in passages:
        segment_id = passage.get("segment_id") or ""
        if not groups or groups[-1][0] != segment_id:
            groups.append((segment_id, []))
        groups[-1][1].append(passage)
    view_segments = view.get("segments", [])
    if len(groups) != len(view_segments):
        raise ValueError(
            "passages segments="
            f"{len(groups)} != writer view segments={len(view_segments)}"
        )
    lines: list[str] = []
    for (_, items), view_segment in zip(groups, view_segments):
        for passage in items:
            start = int(passage.get("t_start_ms", 0)) / 1000
            end = int(passage.get("t_end_ms", 0)) / 1000
            lines.append(
                f"[{passage.get('passage_id', '')} {start:.2f}-{end:.2f}s] "
                f"{passage.get('text', '')}"
            )
        frames = [
            frame
            for frame in view_segment.get("frames", [])
            if (frame.get("caption") or "").strip()
        ]
        if frames:
            rendered = " | ".join(
                f"[{frame.get('frame_id', '')}] "
                f"{(frame.get('caption') or '').strip().replace(chr(10), ' / ')}"
                for frame in frames
            )
            lines.append(f"frames: {rendered}")
        lines.append("")
    return "\n".join(lines).strip()


def build_user_prompt(input_text: str, questions: list[dict[str, Any]]) -> str:
    """Fixed user template: input block + numbered questions."""
    numbered = "\n".join(
        f"{index}. {item['question']}"
        for index, item in enumerate(questions, start=1)
    )
    return (
        "Input:\n<<<\n"
        f"{input_text}\n"
        ">>>\n\n"
        "Questions:\n"
        f"{numbered}\n\n"
        "Answer all questions by number. For each, if the evidence is missing, "
        'say "证据不足" and explain what is missing. Do not use outside knowledge.'
    )


def load_questions(path: Path) -> dict[str, Any]:
    payload = _read_json(path)
    questions = payload.get("questions")
    if not isinstance(questions, list) or not questions:
        raise ValueError("questions 必须是非空 list")
    seen: set[str] = set()
    for item in questions:
        if not isinstance(item, dict):
            raise ValueError("每个 question 必须是 object")
        for key in ("id", "type", "question"):
            value = item.get(key)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"question 缺字段或为空: {key}")
        if item["id"] in seen:
            raise ValueError(f"question id 重复: {item['id']}")
        seen.add(item["id"])
    return payload


def render_input(
    variant: str,
    *,
    units_path: Path | None,
    passages_path: Path | None,
    writer_view_path: Path | None,
) -> str:
    if variant == "raw_asr":
        if units_path is None:
            raise ValueError("raw_asr 需要 --units")
        return render_raw_asr(_read_jsonl(units_path))
    if variant == "merged_text":
        if passages_path is None:
            raise ValueError("merged_text 需要 --passages")
        return render_merged_text(_read_json(passages_path).get("passages", []))
    if variant == "lean_view":
        if writer_view_path is None:
            raise ValueError("lean_view 需要 --writer-view")
        return render_lean_view(_read_json(writer_view_path))
    if variant == MERGED_TEXT_FRAMES:
        if passages_path is None or writer_view_path is None:
            raise ValueError(
                "merged_text_frames 需要 --passages 和 --writer-view"
            )
        return render_merged_text_with_frames(
            _read_json(passages_path).get("passages", []),
            _read_json(writer_view_path),
        )
    raise ValueError(f"未知 variant: {variant}")


def prepare_variant(
    variant: str,
    *,
    units_path: Path | None,
    passages_path: Path | None,
    writer_view_path: Path | None,
    questions: list[dict[str, Any]],
    out_dir: Path,
) -> dict[str, Any]:
    """Write rendered input and prompts for one variant; no model call."""
    rendered_text = render_input(
        variant,
        units_path=units_path,
        passages_path=passages_path,
        writer_view_path=writer_view_path,
    )
    user_text = build_user_prompt(rendered_text, questions)
    variant_dir = out_dir / variant
    prompts_dir = variant_dir / "prompts"
    prompts_dir.mkdir(parents=True, exist_ok=True)
    rendered_path = variant_dir / "rendered.txt"
    system_path = prompts_dir / "system.txt"
    user_path = prompts_dir / "user.txt"
    rendered_path.write_text(rendered_text, encoding="utf-8")
    system_path.write_text(SYSTEM, encoding="utf-8")
    user_path.write_text(user_text, encoding="utf-8")
    return {
        "variant": variant,
        "rendered": {
            "path": str(rendered_path),
            "chars": len(rendered_text),
            "sha256": _sha_text(rendered_text),
        },
        "prompts": {
            "system": {
                "path": str(system_path),
                "chars": len(SYSTEM),
                "sha256": _sha_text(SYSTEM),
            },
            "user": {
                "path": str(user_path),
                "chars": len(user_text),
                "sha256": _sha_text(user_text),
            },
        },
        "response": None,
        "usage": None,
        "latency_ms": None,
        "finish_reason": None,
        "cached": None,
        "error": None,
    }


def _summary(
    *,
    case_id: str,
    status: str,
    model: str,
    temperature: float,
    questions_path: Path,
    questions_payload: dict[str, Any],
    input_paths: dict[str, Path | None],
    variants: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema": "s2-probe-manifest-v1",
        "case_id": case_id,
        "status": status,
        "model": model,
        "params": {
            # No probe-specific output cap: use the provider/settings default.
            "max_tokens": None,
            "max_tokens_source": "provider_default",
            "temperature": temperature,
        },
        "questions": {
            "path": str(questions_path),
            "sha256": _file_info(questions_path)["sha256"],  # type: ignore[index]
            "count": len(questions_payload["questions"]),
            "types": [item["type"] for item in questions_payload["questions"]],
        },
        "inputs": {name: _file_info(path) for name, path in input_paths.items()},
        "variants": variants,
        "note": (
            "dry_run: rendered inputs/prompts only, no provider call. "
            "Pass --run to call the model."
            if status == "dry_run"
            else "one call per variant; prompts/responses/usage retained"
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "S2 probe: fixed questions over raw ASR / merged text / lean view "
            "/ merged text + frames."
        )
    )
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--units", type=Path)
    parser.add_argument("--passages", type=Path)
    parser.add_argument("--writer-view", type=Path)
    parser.add_argument("--questions", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument(
        "--variant",
        choices=["all", *VARIANTS, MERGED_TEXT_FRAMES],
        default="all",
    )
    parser.add_argument(
        "--run",
        action="store_true",
        help="perform provider calls; without it this is a dry run",
    )
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--model", help="override the configured model")
    parser.add_argument("--cache-dir", type=Path)
    parser.add_argument("--no-cache", action="store_true")
    args = parser.parse_args(argv)

    selected = list(VARIANTS) if args.variant == "all" else [args.variant]
    required = {
        "raw_asr": (("units", args.units),),
        "merged_text": (("passages", args.passages),),
        "lean_view": (("writer_view", args.writer_view),),
        MERGED_TEXT_FRAMES: (
            ("passages", args.passages),
            ("writer_view", args.writer_view),
        ),
    }
    for variant in selected:
        for name, path in required[variant]:
            if path is None:
                parser.error(
                    f"--variant {variant} 需要 --{name.replace('_', '-')}"
                )

    try:
        questions_payload = load_questions(args.questions)
    except (OSError, ValueError) as exc:
        print(f"invalid questions: {exc}", file=sys.stderr)
        return 4

    input_paths = {
        "units": args.units,
        "passages": args.passages,
        "writer_view": args.writer_view,
    }
    args.out_dir.mkdir(parents=True, exist_ok=True)
    variants: dict[str, Any] = {}
    for variant in selected:
        variants[variant] = prepare_variant(
            variant,
            units_path=args.units,
            passages_path=args.passages,
            writer_view_path=args.writer_view,
            questions=questions_payload["questions"],
            out_dir=args.out_dir,
        )

    from lunograph.core.config import get_settings

    settings = get_settings()
    if args.model:
        settings = replace(settings, model=args.model)
    model = settings.model
    if not args.run:
        summary = _summary(
            case_id=args.case_id,
            status="dry_run",
            model=model,
            temperature=args.temperature,
            questions_path=args.questions,
            questions_payload=questions_payload,
            input_paths=input_paths,
            variants=variants,
        )
        (args.out_dir / "manifest.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=1),
            encoding="utf-8",
        )
        print(
            json.dumps(
                {
                    "status": "dry_run",
                    "case_id": args.case_id,
                    "out_dir": str(args.out_dir),
                    "variants": {
                        name: {
                            "chars": item["rendered"]["chars"],
                            "user_prompt_chars": item["prompts"]["user"]["chars"],
                        }
                        for name, item in variants.items()
                    },
                    "questions": len(questions_payload["questions"]),
                    "note": "no provider call; pass --run to execute",
                },
                ensure_ascii=False,
                indent=1,
            )
        )
        return 0

    if not settings.provider_configured:
        print("provider 未配置；拒绝伪造 probe 结果", file=sys.stderr)
        return 2

    llm_calls_path = args.out_dir / "llm_calls.jsonl"
    llm_calls_path.write_text("", encoding="utf-8")

    def call_sink(record: dict[str, Any]) -> None:
        # Keep the response text in response.txt; the jsonl carries identity,
        # usage and a content hash, not a second copy of the response.
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

    completed = 0
    failed = 0
    for variant in selected:
        item = variants[variant]
        system_path = Path(item["prompts"]["system"]["path"])
        user_path = Path(item["prompts"]["user"]["path"])
        system_text = system_path.read_text(encoding="utf-8")
        user_text = user_path.read_text(encoding="utf-8")
        key = semantic_hash(
            {
                "case_id": args.case_id,
                "variant": variant,
                "questions_sha": item["prompts"]["user"]["sha256"],
                "input_sha": item["rendered"]["sha256"],
            },
            drop_volatile=False,
        )
        try:
            response = provider.complete(
                stage="s2_probe",
                key=key,
                system=system_text,
                user=user_text,
                temperature=args.temperature,
            )
        except ProviderError as exc:
            failed += 1
            item["error"] = {"kind": exc.kind, "message": str(exc)}
            continue
        completed += 1
        response_path = args.out_dir / variant / "response.txt"
        response_path.write_text(response.text, encoding="utf-8")
        item["response"] = {
            "path": str(response_path),
            "chars": len(response.text),
            "sha256": _sha_text(response.text),
        }
        item["usage"] = response.usage.as_dict()
        item["latency_ms"] = response.latency_ms
        item["finish_reason"] = response.finish_reason
        item["cached"] = response.cached

    status = (
        "complete" if failed == 0 else ("partial" if completed else "error")
    )
    summary = _summary(
        case_id=args.case_id,
        status=status,
        model=model,
        temperature=args.temperature,
        questions_path=args.questions,
        questions_payload=questions_payload,
        input_paths=input_paths,
        variants=variants,
    )
    (args.out_dir / "manifest.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=1),
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "status": status,
                "case_id": args.case_id,
                "out_dir": str(args.out_dir),
                "model": model,
                "variants": {
                    name: {
                        "chars": item["rendered"]["chars"],
                        "usage": item["usage"],
                        "latency_ms": item["latency_ms"],
                        "cached": item["cached"],
                        "error": item["error"],
                    }
                    for name, item in variants.items()
                },
            },
            ensure_ascii=False,
            indent=1,
        )
    )
    return 0 if status == "complete" else 3


if __name__ == "__main__":
    sys.exit(main())
