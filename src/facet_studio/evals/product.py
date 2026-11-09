"""P4 product eval harness: deterministic checks over real run artifacts.

This is deliberately read-only: it never generates content, never changes a run,
and never treats a model self-score as quality.  It measures the product contract
(artifact exists, platform shape, figures, trajectory, usage, manual acceptance)
and writes a reproducible report under ``evals/product_v1/reports``.

LLM judge / human reader test are separate and are not fabricated here.
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..core.config import get_settings

REQUIRED_STAGES = ["intake", "plan", "approval", "write", "typeset", "review"]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _run_path(run_dir: Path, value: Any, default: Path) -> Path:
    """Resolve a run artifact path.

    Real runs store absolute paths; committed fixtures store paths relative to
    the run directory.  Resolving both against the run dir keeps the harness
    portable without rewriting existing run metadata.
    """
    if value in (None, ""):
        return default
    path = Path(str(value))
    return path if path.is_absolute() else (run_dir / path)


def _result(check_id: str, passed: bool, detail: str) -> dict[str, Any]:
    return {"check_id": check_id, "passed": bool(passed), "detail": detail}


def sanitize_paths(value: Any, roots: list[Path]) -> Any:
    """Replace local absolute roots in a report with ``<project>``.

    Reports are committed as developer evidence; absolute machine paths add no
    value and leak the local layout.  This is a display-time transform only.
    """
    if isinstance(value, dict):
        return {key: sanitize_paths(item, roots) for key, item in value.items()}
    if isinstance(value, list):
        return [sanitize_paths(item, roots) for item in value]
    if isinstance(value, str):
        text = value
        for root in roots:
            text = text.replace(str(root), "<project>")
        return text
    return value


def _workflow_trajectory_checks(
    *,
    workflow: dict[str, Any],
    stage_names: list[str],
    stage_status: dict[str, str],
    planner_usage: dict[str, Any],
    write_usage: dict[str, Any],
) -> list[dict[str, Any]]:
    """Trajectory checks over the LangGraph workflow trace.

    These are process checks, not writing-quality scores: stage presence and
    order, no editor/checker/repair stages, no failed stage, the human review
    gate, and usage being recorded for plan/write.
    """
    checks: list[dict[str, Any]] = []
    checks.append(
        _result(
            "trajectory_stages",
            all(name in stage_names for name in REQUIRED_STAGES),
            f"stages={stage_names}",
        )
    )
    ordered = [name for name in stage_names if name in REQUIRED_STAGES]
    checks.append(
        _result(
            "trajectory_order",
            ordered == REQUIRED_STAGES,
            f"ordered={ordered}",
        )
    )
    forbidden = [name for name in stage_names if name in {"editor", "checker", "repair"}]
    checks.append(
        _result(
            "trajectory_no_editor",
            not forbidden,
            f"forbidden={forbidden}",
        )
    )
    failed = [
        name
        for name, status in stage_status.items()
        if status in {"failed", "error"}
    ]
    workflow_errors = [str(item) for item in (workflow.get("errors") or [])]
    checks.append(
        _result(
            "trajectory_failures",
            not failed and not workflow_errors,
            f"failed_stages={failed}, errors={workflow_errors}",
        )
    )
    review_status = stage_status.get("review") or ""
    checks.append(
        _result(
            "trajectory_hitl",
            review_status in {"approved", "auto_accepted"},
            f"review_status={review_status or 'missing'}",
        )
    )
    stage_usage = {
        str(item.get("name") or ""): item.get("usage") or {}
        for item in (workflow.get("stages") or [])
    }
    plan_tokens = int(
        stage_usage.get("plan", {}).get("total_tokens")
        or planner_usage.get("total_tokens")
        or 0
    )
    write_tokens = int(
        stage_usage.get("write", {}).get("total_tokens")
        or write_usage.get("total_tokens")
        or 0
    )
    checks.append(
        _result(
            "trajectory_usage",
            plan_tokens > 0 and write_tokens > 0,
            f"plan_tokens={plan_tokens}, write_tokens={write_tokens}",
        )
    )
    return checks


def _check_run(
    spec: dict[str, Any],
    *,
    runs_root: Path,
) -> dict[str, Any]:
    case_id = str(spec.get("case_id") or "")
    run_id = str(spec.get("run_id") or "")
    kind = str(spec.get("kind") or "capability")
    checks: list[dict[str, Any]] = []
    if not run_id:
        return {
            "case_id": case_id,
            "kind": kind,
            "run_id": "",
            "status": "not_run",
            "passed": False,
            "checks": [
                _result("run_exists", False, "case has no run_id (not run)"),
            ],
            "metrics": {},
            "notes": spec.get("notes", ""),
        }

    run_dir = runs_root / "product_v1" / run_id
    meta_path = run_dir / "run_meta.json"
    if not meta_path.is_file():
        return {
            "case_id": case_id,
            "kind": kind,
            "run_id": run_id,
            "status": "missing",
            "passed": False,
            "checks": [_result("run_exists", False, f"missing {meta_path}")],
            "metrics": {},
            "notes": spec.get("notes", ""),
        }

    meta = _read_json(meta_path)
    form = str(meta.get("form") or "")
    form_dir = _run_path(run_dir, meta.get("form_dir"), run_dir / form)
    output_name = str(meta.get("output") or ("note.md" if form == "xiaohongshu_note" else "article.md"))
    markdown_path = form_dir / output_name
    markdown = _read_text(markdown_path) if markdown_path.is_file() else ""
    write = meta.get("write") or {}
    planner_usage = meta.get("planner_usage") or {}
    write_usage = write.get("usage") or {}
    artifacts = meta.get("artifacts") or {}
    review_path = run_dir / "publish_review.json"
    review = _read_json(review_path) if review_path.is_file() else {}
    workflow_path = run_dir / "workflow.json"
    workflow = _read_json(workflow_path) if workflow_path.is_file() else {}

    status = str(meta.get("status") or "")
    healthy = status in {"typeset", "approved"}
    checks.append(_result("status_healthy", healthy, f"status={status}"))
    reader_value = artifacts.get("reader_html")
    reader_path = _run_path(run_dir, reader_value, run_dir / "reader.html")
    checks.append(
        _result(
            "reader_artifact",
            bool(reader_value and reader_path.is_file()),
            f"reader_html={reader_value or 'missing'}",
        )
    )

    require_approval = bool(spec.get("require_approval", True))
    review_stale = bool(meta.get("review_stale"))
    approved = review.get("decision") == "approved" and not review_stale
    checks.append(
        _result(
            "manual_acceptance",
            approved if require_approval else True,
            f"review={review.get('decision') or 'missing'}"
            + (", stale=true" if review_stale else ""),
        )
    )

    missing_figures = write.get("missing_figures") or []
    figures = write.get("figures_referenced") or []
    min_figures = int(spec.get("min_figures") or 0)
    max_figures = int(spec.get("max_figures") or 0)
    figure_ok = not missing_figures and len(figures) >= min_figures
    if max_figures > 0:
        figure_ok = figure_ok and len(figures) <= max_figures
    missing_on_disk = [
        item for item in figures if not (form_dir / str(item)).is_file()
    ]
    checks.append(
        _result(
            "figures",
            figure_ok and not missing_on_disk,
            f"figures={len(figures)}, missing={missing_figures}, "
            f"missing_on_disk={missing_on_disk}",
        )
    )

    body_chars = int(write.get("output_chars") or len(markdown))
    min_chars = int(spec.get("min_body_chars") or 0)
    max_chars = int(spec.get("max_body_chars") or 0)
    chars_ok = body_chars >= min_chars and (max_chars <= 0 or body_chars <= max_chars)
    checks.append(
        _result(
            "body_chars",
            chars_ok,
            f"output_chars={body_chars}, bounds={min_chars}-{max_chars or '∞'}",
        )
    )

    must_include = [str(item) for item in spec.get("must_include") or []]
    missing_terms = [item for item in must_include if item not in markdown]
    checks.append(
        _result(
            "fact_keywords",
            not missing_terms,
            f"missing={missing_terms}",
        )
    )
    must_not_include = [str(item) for item in spec.get("must_not_include") or []]
    present_terms = [item for item in must_not_include if item in markdown]
    checks.append(
        _result(
            "forbidden_keywords",
            not present_terms,
            f"present={present_terms}",
        )
    )

    stages = workflow.get("stages") or []
    stage_names = [str(item.get("name") or "") for item in stages]
    stage_status = {
        str(item.get("name") or ""): str(item.get("status") or "") for item in stages
    }
    planner_trace = bool(planner_usage)
    if workflow:
        checks.extend(
            _workflow_trajectory_checks(
                workflow=workflow,
                stage_names=stage_names,
                stage_status=stage_status,
                planner_usage=planner_usage,
                write_usage=write_usage,
            )
        )
    else:
        writer_calls = int(bool(write_usage))
        # Older approved runs predate planner_usage; do not call that a
        # one-writer failure.  Report the missing planner trace separately.
        trajectory_ok = writer_calls == 1
        if spec.get("require_planner_trace"):
            trajectory_ok = trajectory_ok and planner_trace
        trajectory_detail = (
            f"legacy planner_trace={planner_trace}, writer_calls={writer_calls}"
        )
        checks.append(_result("trajectory", trajectory_ok, trajectory_detail))

    audit_usage = meta.get("visual_audit_usage") or {}
    total_tokens = (
        int(planner_usage.get("total_tokens") or 0)
        + int(write_usage.get("total_tokens") or 0)
        + int(audit_usage.get("total_tokens") or 0)
    )
    latency = int(meta.get("planner_latency_ms") or 0) + int(
        write.get("latency_ms") or 0
    )
    checks.append(
        _result(
            "usage_present",
            total_tokens > 0 and latency > 0,
            f"tokens={total_tokens} (plan+write+visual_audit), latency_ms={latency} (plan+write)",
        )
    )

    if form == "wechat_article":
        html_path = _run_path(run_dir, artifacts.get("wechat_html"), form_dir / "wechat.html")
        html = _read_text(html_path) if html_path.is_file() else ""
        main_match = re.search(
            r'<main id="wechat-article"[^>]*>(.*?)</main>', html, re.DOTALL
        )
        main = main_match.group(1) if main_match else ""
        image_count = main.count("<img")
        checks.append(
            _result(
                "wechat_artifact",
                html_path.is_file()
                and bool(main)
                and "<h1" not in main
                and "copy-image-btn" in html
                and image_count >= int(spec.get("min_images") or 0),
                f"html={html_path.is_file()}, main={bool(main)}, "
                f"h1_in_main={'<h1' in main}, images={image_count}",
            )
        )
    elif form == "xiaohongshu_note":
        export_dir = _run_path(run_dir, artifacts.get("xhs_export_dir"), form_dir / "xhs_export")
        existing = sorted(export_dir.glob("*.png")) if export_dir.is_dir() else []
        dims_ok = False
        if existing:
            try:
                from PIL import Image

                dims_ok = all(Image.open(path).size == (1080, 1440) for path in existing)
            except Exception:
                dims_ok = False
        reader = _run_path(run_dir, artifacts.get("reader_html"), run_dir / "reader.html")
        reader_text = _read_text(reader) if reader.is_file() else ""
        checks.append(
            _result(
                "xhs_artifact",
                bool(existing)
                and dims_ok
                and len(existing) >= int(spec.get("min_cards") or 0)
                and "copy-note-btn" in reader_text
                and "copy-image-btn" in reader_text,
                f"cards={len(existing)}, dims_1080x1440={dims_ok}, "
                f"copy_ui={'copy-note-btn' in reader_text and 'copy-image-btn' in reader_text}",
            )
        )
    elif form == "long_article":
        pdf_path = _run_path(run_dir, artifacts.get("pdf"), form_dir / "article.pdf")
        pages = 0
        if pdf_path.is_file():
            try:
                from pypdf import PdfReader

                pages = len(PdfReader(str(pdf_path)).pages)
            except Exception:
                pages = 0
        body_md = form_dir / "_pdf_body.md"
        body_text = _read_text(body_md) if body_md.is_file() else ""
        min_pages = int(spec.get("min_pages") or 1)
        max_pages = int(spec.get("max_pages") or 0)
        pages_ok = pages >= min_pages and (max_pages <= 0 or pages <= max_pages)
        checks.append(
            _result(
                "pdf_artifact",
                pdf_path.is_file()
                and pages_ok
                and "本文根据" not in body_text
                and "内容参考" not in body_text,
                f"pdf={pdf_path.is_file()}, pages={pages}, "
                f"body_has_source={'本文根据' in body_text or '内容参考' in body_text}",
            )
        )

    return {
        "case_id": case_id,
        "kind": kind,
        "run_id": run_id,
        "status": status,
        "form": form,
        "passed": all(item["passed"] for item in checks),
        "contract_passed": all(
            item["passed"]
            for item in checks
            if item["check_id"] != "manual_acceptance"
        ),
        "checks": checks,
        "metrics": {
            "body_chars": body_chars,
            "figures": len(figures),
            "planner_tokens": int(planner_usage.get("total_tokens") or 0),
            "writer_tokens": int(write_usage.get("total_tokens") or 0),
            "total_tokens": total_tokens,
            "latency_ms": latency,
            "review": review.get("decision") or "missing",
            "workflow": bool(workflow),
            "planner_trace": planner_trace or bool(workflow),
        },
        "notes": spec.get("notes", ""),
    }


def _p95(values: list[int]) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    index = min(len(ordered) - 1, int(round(0.95 * (len(ordered) - 1))))
    return ordered[index]


def evaluate(
    cases: list[dict[str, Any]], *, runs_root: Path
) -> dict[str, Any]:
    results = [_check_run(spec, runs_root=runs_root) for spec in cases]
    run_results = [item for item in results if item["status"] not in {"not_run", "missing"}]
    passed = [item for item in run_results if item["passed"]]
    contract_passed = [
        item for item in run_results if item.get("contract_passed")
    ]
    latencies = [
        int(item["metrics"].get("latency_ms") or 0)
        for item in run_results
        if item["metrics"].get("latency_ms")
    ]
    tokens = [
        int(item["metrics"].get("total_tokens") or 0)
        for item in run_results
        if item["metrics"].get("total_tokens")
    ]
    errors = [
        item
        for item in run_results
        if item["status"] in {"failed", "partial"}
        or any(
            not check["passed"]
            and (
                check["check_id"] == "status_healthy"
                or check["check_id"].startswith("trajectory")
            )
            for check in item["checks"]
        )
    ]
    trajectory_checks = [
        check
        for item in run_results
        for check in item["checks"]
        if check["check_id"].startswith("trajectory")
    ]
    trajectory_passed = [
        check for check in trajectory_checks if check["passed"]
    ]
    summary = {
        "cases_total": len(results),
        "cases_run": len(run_results),
        "cases_missing": len(results) - len(run_results),
        "cases_passed": len(passed),
        "deterministic_pass_rate": round(len(passed) / len(run_results), 4)
        if run_results
        else None,
        # Machine contract only; manual acceptance is reported separately
        # because the user remains the only publish gate.
        "contract_pass_rate": round(len(contract_passed) / len(run_results), 4)
        if run_results
        else None,
        # task-success pass@1 / pass^k need judged trials; do not label the
        # deterministic contract pass rate as a quality score.
        "pass_at_1": None,
        "pass_at_k": None,
        "manual_acceptance_rate": round(
            sum(1 for item in run_results if item["metrics"].get("review") == "approved")
            / len(run_results),
            4,
        )
        if run_results
        else None,
        "error_rate": round(len(errors) / len(run_results), 4) if run_results else None,
        "planner_trace_rate": round(
            sum(1 for item in run_results if item["metrics"].get("planner_trace"))
            / len(run_results),
            4,
        )
        if run_results
        else None,
        "trajectory_checks": len(trajectory_checks),
        "trajectory_pass_rate": round(
            len(trajectory_passed) / len(trajectory_checks), 4
        )
        if trajectory_checks
        else None,
        "p50_latency_ms": int(statistics.median(latencies)) if latencies else 0,
        "p95_latency_ms": _p95(latencies),
        "total_tokens": sum(tokens),
        "run_cases": [item["case_id"] for item in run_results],
        "missing_cases": [
            item["case_id"] for item in results if item["status"] in {"not_run", "missing"}
        ],
        "notes": (
            "Deterministic product checks only. deterministic_pass_rate is not task "
            "success; pass@1/pass^k require judged trials. No LLM judge, no human "
            "reader test, no fabricated pass@k. Missing cases stay missing until generated."
        ),
    }
    return {
        "schema_version": "product-eval-v1",
        "dataset": "product_v1",
        "created_at": _now(),
        "summary": summary,
        "cases": results,
    }


def render_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# Product v1 eval report",
        "",
        f"- created_at: `{report['created_at']}`",
        f"- cases: {summary['cases_run']} run / {summary['cases_total']} total"
        f" ({summary['cases_missing']} missing)",
        f"- deterministic pass rate (incl. manual acceptance): "
        f"{summary['deterministic_pass_rate']}",
        f"- contract pass rate (machine checks only): {summary['contract_pass_rate']}",
        f"- pass@1 / pass^k: not computed (needs judged trials)",
        f"- manual acceptance: {summary['manual_acceptance_rate']}",
        f"- planner trace: {summary['planner_trace_rate']}",
        f"- trajectory checks: {summary['trajectory_checks']} "
        f"(pass rate {summary['trajectory_pass_rate']})",
        f"- error rate: {summary['error_rate']}",
        f"- p50/p95 latency: {summary['p50_latency_ms']} / {summary['p95_latency_ms']} ms",
        f"- tokens: {summary['total_tokens']}",
        "",
        "| case | kind | run | status | passed |",
        "|---|---|---|---|---|",
    ]
    for item in report["cases"]:
        lines.append(
            f"| {item['case_id']} | {item['kind']} | {item['run_id'] or '—'} | "
            f"{item['status']} | {item['passed']} |"
        )
    lines += [
        "",
        "## Notes",
        "",
        summary["notes"],
        "",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="P4 product eval harness")
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--runs-root", type=Path, default=None)
    parser.add_argument(
        "--gate",
        action="store_true",
        help=(
            "exit non-zero unless all cases are run, deterministic and trajectory "
            "pass rates meet --gate-min-pass, and error rate is zero"
        ),
    )
    parser.add_argument("--gate-min-pass", type=float, default=1.0)
    parser.add_argument(
        "--gate-require-manual",
        action="store_true",
        help="also require manual acceptance rate to meet --gate-min-pass",
    )
    args = parser.parse_args(argv)

    cases_payload = _read_json(args.cases)
    cases = cases_payload.get("cases") or []
    settings = get_settings()
    runs_root = args.runs_root or settings.runs_root
    report = evaluate(cases, runs_root=Path(runs_root))
    report = sanitize_paths(
        report, [settings.project_root, Path(runs_root).resolve()]
    )
    args.out.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    json_path = args.out / f"report-{stamp}.json"
    md_path = args.out / f"report-{stamp}.md"
    json_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    md_path.write_text(render_markdown(report), encoding="utf-8")
    print(json_path)
    print(md_path)
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    if args.gate:
        summary = report["summary"]
        failures: list[str] = []
        if summary["cases_missing"]:
            failures.append(f"missing cases: {summary['missing_cases']}")
        keys = ["contract_pass_rate", "trajectory_pass_rate"]
        if args.gate_require_manual:
            keys.append("manual_acceptance_rate")
        for key in keys:
            value = summary.get(key)
            if value is None or value < args.gate_min_pass:
                failures.append(f"{key}={value} < {args.gate_min_pass}")
        if summary.get("error_rate"):
            failures.append(f"error_rate={summary['error_rate']}")
        if failures:
            print("GATE FAILED: " + "; ".join(failures))
            return 1
        print(f"GATE PASSED at min pass rate {args.gate_min_pass}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
