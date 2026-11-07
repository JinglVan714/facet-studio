"""Bundle orchestrator: compile -> plan -> per-form writers -> inspect -> bundle.

This is the real multi-agent consumer of the runtime harness:

- Lead Planner: one model call, chooses forms/angles/briefs (JSON only).
- Specialist writers: one call per form, independent, no cross-talk.
- Deterministic tools: content compile, structural inspect, bundle assembly.
- RunStore: task plan, working memory, artifact board, decisions, LLM/tool
  receipts and usage.

It is planner-executor, not a supervisor: no editor/checker rewrites a
product; each product is one writer call.
"""

from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..core.config import Settings, get_settings
from ..core.hashing import semantic_hash, utc_now_iso
from ..providers.llm import DeepSeekLLM, ReplayLLM
from ..runtime.artifact import RunStore
from ..runtime.decision import make_decision
from ..runtime.memory import ArtifactBoard, update_working_memory
from ..runtime.task_plan import TaskNode, TaskPlan
from ..runtime.tools import ToolExecutor
from .planner import LeadPlan, plan_bundle
from .skills import form_catalog, load_skill
from .tools import build_registry, parse_figure_catalog
from .writer import FormResult, write_form


@dataclass
class BundleResult:
    run_id: str
    run_dir: Path
    status: str
    plan: LeadPlan
    forms: list[FormResult]
    manifest: dict[str, Any] = field(default_factory=dict)


def _new_run_id(video_id: str) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"bundle_{stamp}_{video_id}"


def _catalog_roles(catalog: list[dict[str, str]]) -> dict[str, str]:
    return {item["form"]: str(item.get("role") or "writer") for item in catalog}


def _catalog_dirs(catalog: list[dict[str, str]]) -> dict[str, Path]:
    return {
        item["form"]: Path(item["skill_dir"])
        for item in catalog
        if item.get("skill_dir")
    }


def build_task_plan(
    run_id: str,
    plan: LeadPlan,
    catalog: list[dict[str, str]],
) -> TaskPlan:
    roles = _catalog_roles(catalog)
    nodes = [
        TaskNode(
            task_id="compile_content",
            kind="deterministic",
            capability="content_compile",
            output_contract="artifact/content",
        ),
        TaskNode(
            task_id="lead_plan",
            kind="agent",
            capability="planning",
            depends_on=["compile_content"],
            agent_role="lead_planner",
            output_contract="artifact/lead_plan",
        ),
    ]
    for item in plan.forms:
        nodes.append(
            TaskNode(
                task_id=f"write_{item.form}",
                kind="agent",
                capability="writing",
                depends_on=["lead_plan"],
                agent_role=roles.get(item.form, "writer"),
                output_contract=f"artifact/{item.form}",
            )
        )
        nodes.append(
            TaskNode(
                task_id=f"inspect_{item.form}",
                kind="deterministic",
                capability="inspect",
                depends_on=[f"write_{item.form}"],
                output_contract=f"artifact/inspect_{item.form}",
            )
        )
    nodes.append(
        TaskNode(
            task_id="assemble_bundle",
            kind="deterministic",
            capability="assemble",
            depends_on=[f"inspect_{item.form}" for item in plan.forms],
            output_contract="artifact/bundle",
        )
    )
    edges = [[dep, node.task_id] for node in nodes for dep in node.depends_on]
    plan_value = TaskPlan(
        task_plan_id="pending",
        run_id=run_id,
        nodes=nodes,
        edges=edges,
        budget_policy={},
        created_at=utc_now_iso(),
    )
    digest = semantic_hash(plan_value.model_dump(mode="json"), drop_volatile=False)
    return plan_value.model_copy(update={"task_plan_id": f"tp_{digest[:12]}"})


def _form_request(plan: LeadPlan, item, form_name: str) -> str:  # noqa: ANN001
    """Build a form-scoped request.

    The original bundle request is deliberately not forwarded: a writer must
    only produce its own form.  The planner has already turned the bundle
    request into this form's angle/brief.
    """
    parts = [
        f"只写这个产物：{form_name}（{item.form}）。"
        "不要写其他形态（如公众号、小红书、短视频脚本），"
        "不要输出其他产物的标题或段落。"
    ]
    if item.brief:
        parts.append("编辑方向：" + item.brief)
    if item.angle:
        parts.append("角度：" + item.angle)
    if plan.shared_constraints:
        parts.append("共享约束：" + "；".join(plan.shared_constraints))
    if item.must_use_figures:
        parts.append("优先使用图示：" + "、".join(item.must_use_figures))
    return "\n\n".join(part for part in parts if part)


def _write_forms(
    *,
    store: RunStore,
    plan: LeadPlan,
    catalog: list[dict[str, str]],
    client,
    settings: Settings,
    source_json: Path | None,
    concurrency: int,
) -> list[FormResult]:
    roles = _catalog_roles(catalog)
    dirs = _catalog_dirs(catalog)
    names = {item["form"]: str(item.get("name") or item["form"]) for item in catalog}
    by_form = {item.form: item for item in plan.forms}
    results: dict[str, FormResult] = {}

    def run_one(form_id: str) -> FormResult:
        item = by_form[form_id]
        started = time.perf_counter()
        try:
            result = write_form(
                video_id=store.manifest.get("video_id", ""),
                content_path=store.root / "content" / "content.md",
                out_dir=store.root / form_id,
                skill_dir=dirs[form_id],
                request=_form_request(plan, item, names.get(form_id, form_id)),
                source_json=source_json,
                client=client,
                settings=settings,
                store=store,
                store_prefix=form_id,
            )
        except Exception as exc:  # noqa: BLE001 - failure is a first-class state
            result = FormResult(
                form=form_id,
                skill_id=dirs[form_id].name,
                skill_version="",
                role=roles.get(form_id, "writer"),
                status="failed",
                output="",
                output_chars=0,
                error=f"{type(exc).__name__}: {exc}",
            )
        duration_ms = int((time.perf_counter() - started) * 1000)
        stage_status = "succeeded" if result.status == "complete" else result.status
        store.record_stage(
            f"write_{form_id}",
            stage_status,
            duration_ms=duration_ms,
            error=result.error,
            artifacts=[f"{form_id}/{result.output}"] if result.output else [],
        )
        return result

    with ThreadPoolExecutor(max_workers=max(1, min(concurrency, len(plan.forms)))) as pool:
        futures = {pool.submit(run_one, item.form): item.form for item in plan.forms}
        for future in as_completed(futures):
            form_id = futures[future]
            results[form_id] = future.result()
    return [results[item.form] for item in plan.forms]


def _inspect_forms(
    *,
    store: RunStore,
    results: list[FormResult],
    tool_executor: ToolExecutor,
) -> dict[str, dict[str, Any]]:
    reports: dict[str, dict[str, Any]] = {}
    for result in results:
        task_id = f"inspect_{result.form}"
        if result.status != "complete":
            report = {
                "exists": False,
                "output": result.output,
                "chars": 0,
                "figures": [],
                "missing_figures": [],
                "skipped": "writer_failed",
            }
            store.record_stage(task_id, "skipped", error=result.error)
        else:
            report = tool_executor.execute(
                run_id=store.run_id,
                task_id=task_id,
                actor="orchestrator",
                tool_name="inspect_output",
                arguments={
                    "form_dir": str(store.root / result.form),
                    "output_name": result.output,
                },
            )
            store.record_stage(
                task_id,
                "succeeded",
                artifacts=[f"{result.form}/inspect.json"],
            )
        store.write_json(f"{result.form}/inspect.json", report, stage=task_id)
        reports[result.form] = report
    return reports


def _overall_status(results: list[FormResult]) -> str:
    if not results:
        return "failed"
    if all(item.status == "complete" for item in results):
        return "complete"
    if all(item.status != "complete" for item in results):
        return "failed"
    return "partial"


def _record_decisions(
    *,
    store: RunStore,
    plan: LeadPlan,
    catalog: list[dict[str, str]],
    request: str,
) -> None:
    store.record_decision(
        make_decision(
            run_id=store.run_id,
            stage="lead_plan",
            question="这次生成哪些产物？",
            candidates=[item["form"] for item in catalog],
            selected=", ".join(item.form for item in plan.forms),
            basis=plan.central_idea or request or "按内容主线",
            decided_by="lead_planner" if plan.source == "planner" else "system",
            result=plan.source,
        )
    )
    for item in plan.forms:
        store.record_decision(
            make_decision(
                run_id=store.run_id,
                stage=f"write_{item.form}",
                question=f"{item.form} 的编辑方向是什么？",
                selected=item.brief,
                basis=item.reason or item.angle or "planner brief",
                decided_by="lead_planner" if plan.source == "planner" else "system",
            )
        )
    if plan.error:
        store.record_decision(
            make_decision(
                run_id=store.run_id,
                stage="lead_plan",
                question="planner 是否成功？",
                selected="fallback",
                basis=plan.error,
                decided_by="system",
                result="partial",
            )
        )


def _save_artifact_board(
    *,
    store: RunStore,
    plan: LeadPlan,
    results: list[FormResult],
    catalog: list[dict[str, str]],
) -> None:
    roles = _catalog_roles(catalog)
    board = ArtifactBoard(run_id=store.run_id, updated_at=utc_now_iso())
    board.write(
        path="lead_plan.json",
        artifact_id=f"{store.run_id}:lead_plan",
        version=1,
        writer_role="lead_planner",
        key="lead_plan",
    )
    for result in results:
        if result.status != "complete" or not result.output:
            continue
        board.write(
            path=f"{result.form}/{result.output}",
            artifact_id=f"{store.run_id}:{result.form}",
            version=1,
            writer_role=roles.get(result.form, result.role),
            key=f"output:{result.form}",
        )
    board.write(
        path="bundle.md",
        artifact_id=f"{store.run_id}:bundle",
        version=1,
        writer_role="orchestrator",
        key="bundle",
    )
    board.write(
        path="bundle_manifest.json",
        artifact_id=f"{store.run_id}:manifest",
        version=1,
        writer_role="orchestrator",
        key="manifest",
    )
    board.save(store)


def run_bundle(
    *,
    video_id: str,
    content_path: Path,
    out_root: Path,
    request: str = "",
    required_forms: list[str] | None = None,
    source_json: Path | None = None,
    client: Any | None = None,
    settings: Settings | None = None,
    concurrency: int = 3,
    run_id: str | None = None,
    use_planner: bool = True,
    replay_from: Path | None = None,
) -> BundleResult:
    settings = settings or get_settings()
    run_id = run_id or _new_run_id(video_id)
    store = RunStore.create(
        Path(out_root),
        video_id=video_id,
        data_root=settings.data_root,
        operation="bundle_generate",
        run_id=run_id,
    )

    if client is None:
        if replay_from is not None:
            records = [
                json.loads(line)
                for line in (Path(replay_from) / "llm_calls.jsonl")
                .read_text(encoding="utf-8-sig")
                .splitlines()
                if line.strip()
            ]
            client = ReplayLLM(records, call_sink=store.llm_sink)
        else:
            client = DeepSeekLLM(settings, call_sink=store.llm_sink)
    elif getattr(client, "call_sink", None) is None:
        # Injected clients (tests, alternate providers) still get the trace.
        client.call_sink = store.llm_sink

    registry = build_registry()
    tool_executor = ToolExecutor(registry, call_sink=store.record_tool_call)

    compile_started = time.perf_counter()
    compiled = tool_executor.execute(
        run_id=run_id,
        task_id="compile_content",
        actor="orchestrator",
        tool_name="compile_content",
        arguments={
            "content_path": str(content_path),
            "out_dir": str(store.root / "content"),
        },
    )
    compile_ms = int((time.perf_counter() - compile_started) * 1000)
    content_file = store.root / "content" / "content.md"
    content = content_file.read_text(encoding="utf-8")
    content_sha = str(compiled["content_sha256"])
    figures = list(compiled.get("figures") or [])
    figure_ids = parse_figure_catalog(content)

    catalog = form_catalog(settings.skills_root / "writing")
    planner_skill = load_skill(settings.skills_root / "writing" / "bundle-planner")
    plan_started = time.perf_counter()
    if use_planner:
        plan, _raw = plan_bundle(
            client=client,
            skill=planner_skill,
            content=content,
            catalog=catalog,
            request=request,
            required_forms=required_forms,
            available_figures=figure_ids,
            video_id=video_id,
        )
    else:
        from .planner import fallback_plan

        plan = fallback_plan(catalog=catalog, required_forms=required_forms)
    plan_ms = int((time.perf_counter() - plan_started) * 1000)

    store.write_json("lead_plan.json", plan.as_dict(), stage="lead_plan")
    _record_decisions(store=store, plan=plan, catalog=catalog, request=request)

    task_plan = build_task_plan(run_id, plan, catalog)
    store.save_task_plan(task_plan)
    store.record_stage(
        "compile_content",
        "succeeded",
        duration_ms=compile_ms,
        artifacts=["content/content.md"],
    )
    store.record_stage(
        "lead_plan",
        "succeeded",
        duration_ms=plan_ms,
        artifacts=["lead_plan.json"],
    )

    semantic = {
        "evidence_snapshot_id": f"content:{content_sha}",
        "temporal_outline_id": "",
        "knowledge_snapshot_id": "",
        "mode": "read_only",
        "content_sha256": content_sha,
        "content_path": "content/content.md",
        "figures": figure_ids,
        "skills": [f"{item.form}:{item.form}" for item in plan.forms],
    }
    store.write_json("semantic_memory.json", semantic, stage="compile_content")
    update_working_memory(
        store,
        run_id=run_id,
        stage="lead_plan",
        artifact_ref={"path": "lead_plan.json", "kind": "plan"},
        task_plan_id=task_plan.task_plan_id,
        budget_state=store.manifest.get("usage", {}),
    )

    results = _write_forms(
        store=store,
        plan=plan,
        catalog=catalog,
        client=client,
        settings=settings,
        source_json=source_json,
        concurrency=concurrency,
    )
    reports = _inspect_forms(
        store=store,
        results=results,
        tool_executor=tool_executor,
    )

    assemble_started = time.perf_counter()
    assembled = tool_executor.execute(
        run_id=run_id,
        task_id="assemble_bundle",
        actor="orchestrator",
        tool_name="assemble_bundle",
        arguments={
            "run_dir": str(store.root),
            "video_id": video_id,
            "plan": plan.as_dict(),
            "forms": [item.as_dict() for item in results],
        },
    )
    assemble_ms = int((time.perf_counter() - assemble_started) * 1000)
    store.register_file("bundle.md", stage="assemble_bundle")
    store.record_stage(
        "assemble_bundle",
        "succeeded",
        duration_ms=assemble_ms,
        artifacts=["bundle.md"],
    )

    status = _overall_status(results)
    manifest = {
        "schema_version": "bundle-v1",
        "run_id": run_id,
        "video_id": video_id,
        "content_sha256": content_sha,
        "content_chars": len(content),
        "figure_count": len(figures),
        "model": getattr(client, "model", ""),
        "plan": plan.as_dict(),
        "forms": [item.as_dict() for item in results],
        "inspect": reports,
        "usage": store.manifest.get("usage", {}),
        "status": status,
        "task_plan_id": task_plan.task_plan_id,
        "bundle_md": str(assembled.get("path", "")),
        "created_at": utc_now_iso(),
    }
    store.write_json("bundle_manifest.json", manifest, stage="assemble_bundle")
    _save_artifact_board(
        store=store, plan=plan, results=results, catalog=catalog
    )
    update_working_memory(
        store,
        run_id=run_id,
        stage="assemble_bundle",
        artifact_ref={"path": "bundle_manifest.json", "kind": "manifest"},
        task_plan_id=task_plan.task_plan_id,
        budget_state=store.manifest.get("usage", {}),
    )
    store.set_status(status, ended=True)

    return BundleResult(
        run_id=run_id,
        run_dir=store.root,
        status=status,
        plan=plan,
        forms=results,
        manifest=manifest,
    )
