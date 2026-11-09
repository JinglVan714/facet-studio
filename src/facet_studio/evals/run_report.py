"""Read-only run report: workflow trace + artifact contract + grounding.

This is the developer-facing "one run, one report" view.  It combines the
LangGraph ``workflow.json`` trace, the deterministic product checks and the
grounding candidate audit.  It never scores writing quality and never writes
into the run directory.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..core.config import get_settings
from .grounding import _audit_run
from .product import _check_run, sanitize_paths


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _workflow(run_dir: Path) -> dict[str, Any]:
    path = run_dir / "workflow.json"
    return _read_json(path) if path.is_file() else {}


def _llm_calls(run_dir: Path) -> list[dict[str, Any]]:
    path = run_dir / "llm_calls.jsonl"
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def build_run_report(run_id: str, *, runs_root: Path) -> dict[str, Any]:
    run_dir = runs_root / "product_v1" / run_id
    if not (run_dir / "run_meta.json").is_file():
        raise FileNotFoundError(f"run 不存在：{run_id}")
    meta = _read_json(run_dir / "run_meta.json")
    workflow = _workflow(run_dir)
    calls = _llm_calls(run_dir)
    contract = _check_run(
        {
            "case_id": run_id,
            "kind": "run_report",
            "run_id": run_id,
            # Keep the manual gate visible: an unapproved run must not look
            # like a published one just because the machine checks passed.
            "require_approval": True,
        },
        runs_root=runs_root,
    )
    grounding = _audit_run(case_id=run_id, run_id=run_id, run_dir=run_dir)
    return {
        "schema_version": "facet-run-report-v1",
        "created_at": _now(),
        "run_id": run_id,
        "video_id": meta.get("video_id"),
        "form": meta.get("form"),
        "status": meta.get("status"),
        "review": grounding.get("review"),
        "workflow": {
            "status": workflow.get("status"),
            "next": workflow.get("next"),
            "stages": workflow.get("stages") or [],
            "events": workflow.get("events") or [],
            "usage": workflow.get("usage") or {},
            "cost_estimate": workflow.get("cost_estimate"),
            "errors": workflow.get("errors") or [],
        },
        "contract": {
            # Machine contract only; manual acceptance stays a separate check.
            "passed": contract.get("contract_passed"),
            "checks": contract.get("checks") or [],
            "metrics": contract.get("metrics") or {},
        },
        "llm_calls": {
            "count": len(calls),
            "total_tokens": sum(
                int((call.get("usage") or {}).get("total_tokens") or 0)
                for call in calls
            ),
            "by_stage": {
                stage: sum(
                    1 for call in calls if str(call.get("stage") or "") == stage
                )
                for stage in sorted(
                    {str(call.get("stage") or "") for call in calls}
                )
            },
        },
        "grounding": grounding,
        "notes": (
            "Developer run report. Contract/trajectory checks are process checks; "
            "grounding flags are candidates, not a hallucination rate. No writing "
            "quality score; human acceptance remains the only publish gate."
        ),
    }


def render_markdown(report: dict[str, Any]) -> str:
    manual = next(
        (
            check
            for check in (report["contract"].get("checks") or [])
            if check.get("check_id") == "manual_acceptance"
        ),
        {},
    )
    lines = [
        f"# Run report — {report['run_id']}",
        "",
        f"- created_at: `{report['created_at']}`",
        f"- video: `{report.get('video_id') or ''}`",
        f"- form: `{report.get('form') or ''}`",
        f"- status: `{report.get('status') or ''}`",
        f"- review: `{report.get('review') or ''}`",
        f"- contract passed (machine checks): `{report['contract']['passed']}`",
        f"- manual acceptance: `{manual.get('passed')}` "
        f"({manual.get('detail') or 'missing'})",
        "",
        "## Workflow stages",
        "",
    ]
    stages = report["workflow"]["stages"]
    if stages:
        lines += [
            "| stage | status | duration_ms | tokens | error |",
            "|---|---|---:|---:|---|",
        ]
        for stage in stages:
            usage = stage.get("usage") or {}
            lines.append(
                f"| {stage.get('name')} | {stage.get('status')} | "
                f"{stage.get('duration_ms')} | {usage.get('total_tokens') or 0} | "
                f"{stage.get('error') or ''} |"
            )
    else:
        lines.append("_No workflow trace (legacy P1/P2 run)._")
    calls = report.get("llm_calls") or {}
    lines += [
        "",
        "## LLM calls",
        "",
        f"- count: {calls.get('count', 0)}",
        f"- total tokens: {calls.get('total_tokens', 0)}",
        f"- by stage: {calls.get('by_stage', {})}",
        "",
        "## Contract checks",
        "",
        "| check | passed | detail |",
        "|---|---|---|",
    ]
    for check in report["contract"]["checks"]:
        lines.append(
            f"| {check.get('check_id')} | {check.get('passed')} | "
            f"{check.get('detail') or ''} |"
        )
    grounding = report["grounding"]
    flags = grounding.get("flags") or []
    lines += [
        "",
        "## Grounding candidates",
        "",
        f"- status: `{grounding.get('status')}`",
        f"- flags: {len(flags)}",
        "",
    ]
    if flags:
        lines += ["| kind | value | context |", "|---|---|---|"]
        for flag in flags:
            lines.append(
                f"| {flag.get('kind')} | `{flag.get('value')}` | "
                f"{flag.get('context') or ''} |"
            )
    lines += ["", "## Notes", "", report["notes"], ""]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a read-only run report")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--runs-root", type=Path, default=None)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    settings = get_settings()
    runs_root = args.runs_root or settings.runs_root
    report = build_run_report(args.run_id, runs_root=Path(runs_root))
    report = sanitize_paths(
        report, [settings.project_root, Path(runs_root).resolve()]
    )
    args.out.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    json_path = args.out / f"run-report-{args.run_id}-{stamp}.json"
    md_path = args.out / f"run-report-{args.run_id}-{stamp}.md"
    json_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    md_path.write_text(render_markdown(report), encoding="utf-8")
    print(json_path)
    print(md_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
