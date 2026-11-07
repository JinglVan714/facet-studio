"""Attempt and ToolCall records.

These are audit sidecars; they never replace run artifacts.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from ..core.hashing import semantic_hash, utc_now_iso


class Attempt(BaseModel):
    attempt_id: str
    run_id: str
    task_id: str
    actor: str
    input_hash: str
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)
    model_receipt: dict[str, Any] | None = None
    usage: dict[str, Any] = Field(default_factory=dict)
    outcome: str = "succeeded"  # succeeded / partial / failed / unknown
    error: str | None = None
    started_at: str
    ended_at: str
    duration_ms: int = 0


class ToolCallRecord(BaseModel):
    call_id: str
    run_id: str
    task_id: str
    actor: str
    tool_name: str
    arguments: dict[str, Any]
    attempt: int = 1
    result: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    latency_ms: int = 0
    usage: dict[str, Any] = Field(default_factory=dict)
    created_at: str


def make_tool_call(
    *,
    run_id: str,
    task_id: str,
    actor: str,
    tool_name: str,
    arguments: dict[str, Any],
    attempt: int = 1,
    result: dict[str, Any] | None = None,
    error: str | None = None,
    latency_ms: int = 0,
    usage: dict[str, Any] | None = None,
) -> dict[str, Any]:
    created = utc_now_iso()
    digest = semantic_hash(
        {
            "run_id": run_id,
            "task": task_id,
            "tool": tool_name,
            "args": arguments,
            "attempt": attempt,
            "created_at": created,
        },
        drop_volatile=False,
    )
    return ToolCallRecord(
        call_id=f"tc_{digest[:12]}",
        run_id=run_id,
        task_id=task_id,
        actor=actor,
        tool_name=tool_name,
        arguments=arguments,
        attempt=attempt,
        result=result or {},
        error=error,
        latency_ms=latency_ms,
        usage=usage or {},
        created_at=created,
    ).model_dump(mode="json")
