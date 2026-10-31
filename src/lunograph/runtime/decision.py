"""Auditable agent/domain decisions."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from ..core.hashing import semantic_hash, utc_now_iso


class DecisionRecord(BaseModel):
    decision_id: str
    run_id: str
    stage: str
    question: str
    candidates: list[str] = Field(default_factory=list)
    selected: str
    basis: str
    evidence_ids: list[str] = Field(default_factory=list)
    context_pack_id: str | None = None
    decided_by: str = "system"
    confidence: float | None = None
    consequences: str = ""
    result: str = ""
    created_at: str


def make_decision(
    *,
    run_id: str,
    stage: str,
    question: str,
    selected: str,
    basis: str,
    candidates: list[str] | None = None,
    evidence_ids: list[str] | None = None,
    context_pack_id: str | None = None,
    decided_by: str = "system",
    confidence: float | None = None,
    consequences: str = "",
    result: str = "",
) -> dict[str, Any]:
    created = utc_now_iso()
    digest = semantic_hash(
        {
            "run_id": run_id,
            "stage": stage,
            "question": question,
            "selected": selected,
            "created_at": created,
        },
        drop_volatile=False,
    )
    return DecisionRecord(
        decision_id=f"dec_{digest[:12]}",
        run_id=run_id,
        stage=stage,
        question=question,
        candidates=candidates or [],
        selected=selected,
        basis=basis,
        evidence_ids=evidence_ids or [],
        context_pack_id=context_pack_id,
        decided_by=decided_by,
        confidence=confidence,
        consequences=consequences,
        result=result,
        created_at=created,
    ).model_dump(mode="json")
