"""WorkingMemory, artifact board and read-only semantic memory refs.

The harness memory is deliberately narrow:

- WorkingMemory is the current run's blackboard.
- ArtifactBoard enforces one writer per artifact and expected-version writes.
- SemanticMemoryRef is a read-only pointer to the frozen snapshots.

Episodic/Procedural memory are later batches; they must not be faked here.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from ..core.hashing import utc_now_iso


class WorkingMemory(BaseModel):
    run_id: str
    task_plan_id: str = ""
    current_stage: str = ""
    artifact_refs: list[dict[str, Any]] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    active_constraints: list[str] = Field(default_factory=list)
    budget_state: dict[str, Any] = Field(default_factory=dict)
    updated_at: str

    def save(self, store) -> None:  # noqa: ANN001 - RunStore duck type
        store.write_state_json("working_memory.json", self)

    @classmethod
    def load(cls, store) -> "WorkingMemory | None":  # noqa: ANN001
        if not store.exists("working_memory.json"):
            return None
        return cls.model_validate(store.read_json("working_memory.json"))


class ArtifactBoardEntry(BaseModel):
    artifact_key: str = ""
    artifact_id: str
    path: str
    version: int = 1
    writer_role: str = "system"
    status: str = "committed"  # committed / conflict / draft
    updated_at: str


class ArtifactVersionConflict(RuntimeError):
    kind = "artifact_version_conflict"


class ArtifactBoard(BaseModel):
    run_id: str
    entries: list[ArtifactBoardEntry] = Field(default_factory=list)
    updated_at: str

    def entry(self, key: str) -> ArtifactBoardEntry | None:
        return next(
            (
                row
                for row in self.entries
                if row.artifact_key == key or row.path == key
            ),
            None,
        )

    def write(
        self,
        *,
        path: str,
        artifact_id: str,
        version: int,
        writer_role: str,
        expected_version: int | None = None,
        status: str = "committed",
        key: str | None = None,
    ) -> ArtifactBoardEntry:
        board_key = key or path
        existing = self.entry(board_key)
        current_version = existing.version if existing is not None else 0
        expected = current_version if expected_version is None else int(expected_version)
        if expected != current_version:
            raise ArtifactVersionConflict(
                f"{board_key} expected_version={expected}，当前 version={current_version}"
            )
        if version <= current_version:
            raise ArtifactVersionConflict(
                f"{board_key} 新 version={version} 必须大于当前 version={current_version}"
            )
        row = ArtifactBoardEntry(
            artifact_key=board_key,
            artifact_id=artifact_id,
            path=path,
            version=version,
            writer_role=writer_role,
            status=status,
            updated_at=utc_now_iso(),
        )
        self.entries = [
            item
            for item in self.entries
            if item.artifact_key != board_key and item.path != board_key
        ] + [row]
        self.updated_at = utc_now_iso()
        return row

    def save(self, store) -> None:  # noqa: ANN001
        store.write_state_json("artifact_board.json", self)

    @classmethod
    def load(cls, store, run_id: str) -> "ArtifactBoard":  # noqa: ANN001
        if not store.exists("artifact_board.json"):
            return cls(run_id=run_id, updated_at=utc_now_iso())
        board = cls.model_validate(store.read_json("artifact_board.json"))
        if not board.run_id:
            board = board.model_copy(update={"run_id": run_id})
        return board


class SemanticMemoryRef(BaseModel):
    """Read-only pointers to the frozen snapshots.

    There is intentionally no write method: the harness must never overwrite
    semantic memory (C-011/C-036).
    """

    evidence_snapshot_id: str
    temporal_outline_id: str = ""
    knowledge_snapshot_id: str = ""

    def as_readonly(self) -> dict[str, str]:
        return {
            "evidence_snapshot_id": self.evidence_snapshot_id,
            "temporal_outline_id": self.temporal_outline_id,
            "knowledge_snapshot_id": self.knowledge_snapshot_id,
            "mode": "read_only",
        }


def update_working_memory(
    store,
    *,
    run_id: str,
    stage: str,
    artifact_ref: dict[str, Any] | None = None,
    task_plan_id: str = "",
    budget_state: dict[str, Any] | None = None,
) -> WorkingMemory:
    memory = WorkingMemory.load(store) or WorkingMemory(
        run_id=run_id, updated_at=utc_now_iso()
    )
    if not task_plan_id:
        try:
            if store.exists("task_plan.json"):
                task_plan_id = str(
                    store.read_json("task_plan.json").get("task_plan_id") or ""
                )
        except Exception:
            task_plan_id = ""
    refs = list(memory.artifact_refs)
    if artifact_ref is not None:
        path = str(artifact_ref.get("path") or "")
        refs = [
            item for item in refs if str(item.get("path") or "") != path
        ] + [artifact_ref]
    memory = memory.model_copy(
        update={
            "current_stage": stage,
            "artifact_refs": refs,
            "task_plan_id": task_plan_id or memory.task_plan_id,
            "budget_state": (
                budget_state
                if budget_state is not None
                else memory.budget_state
            ),
            "updated_at": utc_now_iso(),
        }
    )
    memory.save(store)
    return memory
