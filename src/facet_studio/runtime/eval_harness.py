"""EvalCase / EvalRun: regression over a fixed run, not a model self-score.

An EvalCase names a run (or a baseline) and a list of deterministic checks.
EvalRun records pass/fail per check and the metrics it read.  The runner never
changes the run and never counts ``findings=0`` or a judge score as quality.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from ..core.hashing import semantic_hash, utc_now_iso


class EvalCheckResult(BaseModel):
    check_id: str
    kind: str
    passed: bool
    detail: str


class EvalCase(BaseModel):
    case_id: str
    video_id: str = ""
    request_path: str = ""
    baseline_run_id: str = ""
    checks: list[dict[str, Any]] = Field(default_factory=list)
    notes: str = ""


class EvalRun(BaseModel):
    eval_run_id: str = ""
    case_id: str
    run_id: str
    results: list[EvalCheckResult] = Field(default_factory=list)
    passed: bool = False
    metrics: dict[str, Any] = Field(default_factory=dict)
    created_at: str
    eval_hash: str = ""


def load_case(path: Path) -> EvalCase:
    payload = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    return EvalCase.model_validate(payload)


def _read(store, name: str) -> Any | None:  # noqa: ANN001 - RunStore duck type
    try:
        if store.exists(name):
            return store.read_json(name)
    except Exception:
        return None
    return None


def _quality(evaluation: dict[str, Any]) -> dict[str, Any]:
    return evaluation.get("quality") or {}


def _check(
    check: dict[str, Any],
    *,
    evaluation: dict[str, Any],
    store,  # noqa: ANN001
) -> EvalCheckResult:
    check_id = str(check.get("id") or check.get("kind") or "check")
    kind = str(check.get("kind") or "")
    quality = _quality(evaluation)
    contract_checks = (evaluation.get("contract") or {}).get("checks") or {}
    if kind == "contract_checks_passed":
        passed = bool(contract_checks) and all(
            bool(item.get("passed")) for item in contract_checks.values()
        )
        detail = "; ".join(
            f"{key}={item.get('passed')}" for key, item in contract_checks.items()
        )
    elif kind == "binding_coverage_min":
        minimum = float(check.get("min") or 1.0)
        actual = float(quality.get("binding_coverage") or 0.0)
        passed = actual >= minimum
        detail = f"binding_coverage={actual}, min={minimum}"
    elif kind == "blocker_count_max":
        maximum = int(check.get("max") or 0)
        actual = int(quality.get("blocker_count") or 0)
        passed = actual <= maximum
        detail = f"blocker_count={actual}, max={maximum}"
    elif kind == "unresolved_findings_max":
        maximum = int(check.get("max") or 0)
        actual = int(quality.get("unresolved_finding_count") or 0)
        passed = actual <= maximum
        detail = f"unresolved={actual}, max={maximum}"
    elif kind == "thread_post_count_min":
        minimum = int(check.get("min") or 1)
        thread = _read(store, "thread_posts.json") or {}
        body = [
            post
            for post in thread.get("posts", [])
            if isinstance(post, dict) and post.get("role") != "sources"
        ]
        passed = len(body) >= minimum
        detail = f"body_posts={len(body)}, min={minimum}"
    elif kind == "thread_sources_post":
        thread = _read(store, "thread_posts.json") or {}
        posts = [post for post in thread.get("posts", []) if isinstance(post, dict)]
        passed = bool(posts) and posts[-1].get("role") == "sources"
        detail = f"last_role={posts[-1].get('role') if posts else None}"
    elif kind == "local_editor_not_failed":
        report = _read(store, "local_editor_report.json") or {}
        status = str(report.get("status") or "")
        passed = status in {"succeeded", "partial", "no_op", "no_targets"}
        detail = f"local_editor_status={status or 'missing'}"
    elif kind == "local_editor_introduced_zero":
        report = _read(store, "local_editor_report.json") or {}
        introduced = report.get("introduced_claims") or []
        passed = not introduced
        detail = f"introduced_claims={introduced}"
    elif kind == "media_slot_count_min":
        minimum = int(check.get("min") or 1)
        presentation = _read(store, "presentation_plan.json") or {}
        slots = presentation.get("media_slots") or []
        passed = len(slots) >= minimum
        detail = f"media_slots={len(slots)}, min={minimum}"
    elif kind == "media_asset_count_min":
        minimum = int(check.get("min") or 1)
        assets_dir = Path(store.root) / "assets"
        count = (
            len([path for path in assets_dir.glob("*") if path.is_file()])
            if assets_dir.exists()
            else 0
        )
        passed = count >= minimum
        detail = f"assets={count}, min={minimum}"
    elif kind == "publish_approved":
        review = _read(store, "publish_review.json") or {}
        passed = review.get("decision") == "publish_approved"
        detail = f"decision={review.get('decision') or 'missing'}"
    elif kind == "reader_artifact_exists":
        passed = store.exists("reader.md")
        detail = "reader.md present" if passed else "missing reader.md"
    elif kind == "reader_audit_split":
        passed = bool(
            store.exists("reader.md")
            and store.exists("final.md")
            and store.read_text("reader.md") == store.read_text("final.md")
        )
        detail = (
            "reader.md == final.md (reader artifact)"
            if passed
            else "reader.md/final.md missing or differ"
        )
    elif kind == "audit_artifact_complete":
        audit = _read(store, "audit.json") or {}
        passed = bool(
            audit.get("audit_id")
            and audit.get("evidence_snapshot_id")
            and int(audit.get("citation_count") or 0) > 0
            and int(audit.get("binding_count") or 0) > 0
        )
        detail = (
            f"citations={audit.get('citation_count')}, "
            f"bindings={audit.get('binding_count')}"
        )
    elif kind == "reader_no_audit_tokens":
        matched = [
            item
            for key, item in contract_checks.items()
            if "reader_no_audit_tokens" in str(key)
        ]
        passed = bool(matched) and all(bool(item.get("passed")) for item in matched)
        detail = (
            matched[0].get("detail") if matched else "no reader_no_audit_tokens check"
        )
    elif kind == "body_chars_between":
        minimum = int(check.get("min") or 0)
        maximum = int(check.get("max") or 0)
        actual = int(quality.get("body_chars") or 0)
        passed = actual >= minimum and (maximum <= 0 or actual <= maximum)
        detail = f"body_chars={actual}, bounds={minimum}-{maximum}"
    else:
        passed = False
        detail = f"unknown eval check kind={kind!r}"
    return EvalCheckResult(
        check_id=check_id, kind=kind, passed=passed, detail=detail
    )


def run_case(case: EvalCase, store, settings) -> EvalRun:  # noqa: ANN001
    current_evaluation = (
        (getattr(store, "manifest", {}) or {}).get("current", {}) or {}
    ).get("evaluation") or ""
    evaluation = (
        _read(store, current_evaluation)
        or _read(store, "evaluation.pre_review.json")
        or _read(store, "evaluation.json")
        or {}
    )
    results = [
        _check(check, evaluation=evaluation, store=store)
        for check in case.checks
    ]
    metrics = {
        "binding_coverage": _quality(evaluation).get("binding_coverage"),
        "blocker_count": _quality(evaluation).get("blocker_count"),
        "unresolved_finding_count": _quality(evaluation).get(
            "unresolved_finding_count"
        ),
        "body_chars": _quality(evaluation).get("body_chars"),
        "contract_id": (evaluation.get("contract") or {}).get("id"),
    }
    run = EvalRun(
        case_id=case.case_id,
        run_id=store.run_id,
        results=results,
        passed=bool(results) and all(item.passed for item in results),
        metrics=metrics,
        created_at=utc_now_iso(),
    )
    digest = semantic_hash(
        {
            "case": case.case_id,
            "run": store.run_id,
            "results": [item.model_dump(mode="json") for item in results],
        },
        drop_volatile=False,
    )
    run = run.model_copy(
        update={"eval_run_id": f"er_{digest[:12]}", "eval_hash": digest}
    )
    output_dir = Path(settings.runs_root) / "eval_runs" / case.case_id
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / f"{store.run_id}.json").write_text(
        json.dumps(run.model_dump(mode="json"), ensure_ascii=False, indent=1)
        + "\n",
        encoding="utf-8",
    )
    return run
