"""TaskPlan: the execution DAG, explicitly not the article blueprint."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from ..core.hashing import semantic_hash, utc_now_iso

NODE_SPECS = [
    ("ingest", "deterministic", "evidence_query", []),
    ("build_evidence", "deterministic", "evidence_query", ["ingest"]),
    ("temporal_outline", "deterministic", "evidence_query", ["build_evidence"]),
    ("build_knowledge", "agent", "planning", ["build_evidence", "temporal_outline"]),
    ("intent_feasibility", "deterministic", "planning", ["build_knowledge"]),
    ("skill_route", "deterministic", "planning", ["intent_feasibility"]),
    ("plan_draft", "agent", "planning", ["skill_route"]),
    ("selection", "deterministic", "planning", ["plan_draft"]),
    ("content_plan", "deterministic", "planning", ["selection"]),
    ("context_pack", "deterministic", "planning", ["content_plan"]),
    ("draft", "agent", "drafting", ["context_pack"]),
    ("review", "agent", "review", ["draft"]),
    ("repair", "agent", "repair", ["review"]),
    ("local_edit", "agent", "local_edit", ["repair"]),
    ("export", "deterministic", "render", ["local_edit"]),
    ("human_review", "human_gate", "human_review", ["export"]),
    ("eval", "deterministic", "review", ["export", "human_review"]),
]


class TaskNode(BaseModel):
    model_config = ConfigDict(extra="allow")

    task_id: str
    kind: str  # deterministic / agent / human_gate
    capability: str
    depends_on: list[str] = Field(default_factory=list)
    input_artifact_ids: list[str] = Field(default_factory=list)
    output_contract: str = ""
    agent_role: str | None = None
    tool_policy: list[str] = Field(default_factory=list)
    retry_policy: str = "none"
    status: str = "pending"
    error: str | None = None
    attempts: list[dict[str, Any]] = Field(default_factory=list)


class TaskPlan(BaseModel):
    task_plan_id: str
    run_id: str
    nodes: list[TaskNode]
    edges: list[list[str]]
    budget_policy: dict[str, Any]
    created_by: str = "runtime/task_plan/v1"
    status: str = "pending"
    plan_version: int = 1
    created_at: str


def default_task_plan(run_id: str, budget_policy: dict[str, Any] | None = None) -> TaskPlan:
    nodes = [
        TaskNode(
            task_id=node_id,
            kind=kind,
            capability=capability,
            depends_on=deps,
            output_contract=f"artifact/{node_id}",
            agent_role={
                "draft": "writer",
                "local_edit": "local_editor",
            }.get(node_id),
        )
        for node_id, kind, capability, deps in NODE_SPECS
    ]
    edges = [[dep, node.task_id] for node in nodes for dep in node.depends_on]
    plan = TaskPlan(
        task_plan_id="pending",
        run_id=run_id,
        nodes=nodes,
        edges=edges,
        budget_policy=budget_policy or {},
        created_at=utc_now_iso(),
    )
    digest = semantic_hash(plan.model_dump(mode="json"), drop_volatile=False)
    return plan.model_copy(update={"task_plan_id": f"tp_{digest[:12]}"})


def update_node(
    plan: TaskPlan,
    task_id: str,
    status: str,
    *,
    error: str | None = None,
    attempt: dict[str, Any] | None = None,
) -> TaskPlan:
    nodes = []
    for node in plan.nodes:
        if node.task_id != task_id:
            nodes.append(node)
            continue
        attempts = list(node.attempts)
        if attempt:
            attempts.append(attempt)
        nodes.append(
            node.model_copy(
                update={"status": status, "error": error, "attempts": attempts}
            )
        )
    overall = _overall_status(nodes)
    return plan.model_copy(update={"nodes": nodes, "status": overall})


def _overall_status(nodes: list[TaskNode]) -> str:
    statuses = [n.status for n in nodes]
    if any(s == "failed" for s in statuses):
        if any(s in {"succeeded", "skipped", "reused"} for s in statuses):
            return "partial"
        return "failed"
    if any(s == "running" for s in statuses):
        return "running"
    if all(s in {"succeeded", "skipped", "reused"} for s in statuses):
        return "succeeded"
    if any(s in {"partial", "succeeded"} for s in statuses):
        return "partial"
    return "pending"
