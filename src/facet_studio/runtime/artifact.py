"""Immutable artifact store for one Run.

Artifact rules: immutable, idempotent, replayable.
- content-identical write is a no-op;
- different content at the same path is refused, never overwritten;
- a new version gets a new run/revision.
"""

from __future__ import annotations

import json
import secrets
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from pydantic import BaseModel

from ..core.config import project_root
from ..core.hashing import file_sha256, utc_now_iso
from ..core.ids import validate_run_id
from .task_plan import TaskPlan, default_task_plan, update_node


class OverwriteRefused(RuntimeError):
    pass


class RunExistsError(RuntimeError):
    pass


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _jsonl_bytes(rows: Iterable[dict[str, Any]]) -> bytes:
    return "".join(
        json.dumps(row, ensure_ascii=False) + "\n" for row in rows
    ).encode("utf-8")


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(data)
    tmp.replace(path)


class RunStore:
    def __init__(self, runs_root: Path, run_id: str):
        self.runs_root = runs_root
        self.run_id = validate_run_id(run_id)
        self.root = runs_root / run_id
        if not self.root.exists():
            raise FileNotFoundError(f"run 不存在: {self.root}")
        self.manifest_path = self.root / "manifest.json"
        self._manifest = self._load_manifest()
        # Provider call sinks can run on section-draft worker threads.
        self._lock = threading.RLock()

    # ------------------------------------------------------------------
    # creation
    # ------------------------------------------------------------------
    @classmethod
    def create(
        cls,
        runs_root: Path,
        *,
        video_id: str,
        data_root: Path,
        operation: str = "generate",
        run_id: str | None = None,
        budget_policy: dict[str, Any] | None = None,
        source_run_id: str | None = None,
        snapshot_mode: str | None = None,
    ) -> "RunStore":
        if run_id is None:
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            run_id = f"run_{stamp}_{video_id}_{secrets.token_hex(2)}"
        run_id = validate_run_id(run_id)
        root = runs_root / run_id
        if root.exists():
            raise RunExistsError(f"run 已存在: {root}")
        root.mkdir(parents=True, exist_ok=False)
        (root / "sections").mkdir()
        now = utc_now_iso()
        manifest = {
            "schema_version": "1.0",
            "run_id": run_id,
            "operation": operation,
            "video_id": video_id,
            "status": "running",
            "started_at": now,
            "ended_at": None,
            "data_root": str(data_root.resolve()),
            "source_run_id": source_run_id,
            "snapshot_mode": snapshot_mode,
            "stages": {},
            "artifacts": {},
            "current": {},
            "usage": {
                "calls": 0,
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
                "reasoning_tokens": 0,
                "latency_ms": 0,
            },
            "notes": [],
        }
        _atomic_write(root / "manifest.json", _json_bytes(manifest))
        plan = default_task_plan(run_id, budget_policy)
        _atomic_write(root / "task_plan.json", _json_bytes(plan.model_dump(mode="json")))
        return cls(runs_root, run_id)

    # ------------------------------------------------------------------
    # paths and basic IO
    # ------------------------------------------------------------------
    def path(self, name: str) -> Path:
        candidate = (self.root / name).resolve()
        if self.root.resolve() not in candidate.parents and candidate != self.root.resolve():
            raise ValueError(f"非法 artifact 路径: {name}")
        return self.root / name

    def exists(self, name: str) -> bool:
        return self.path(name).exists()

    def read_json(self, name: str) -> Any:
        return json.loads(self.path(name).read_text(encoding="utf-8-sig"))

    def read_text(self, name: str) -> str:
        return self.path(name).read_text(encoding="utf-8")

    def read_jsonl(self, name: str) -> list[dict[str, Any]]:
        path = self.path(name)
        if not path.exists():
            return []
        return [
            json.loads(line)
            for line in path.read_text(encoding="utf-8-sig").splitlines()
            if line.strip()
        ]

    # ------------------------------------------------------------------
    # immutable writes
    # ------------------------------------------------------------------
    def write_json(
        self,
        name: str,
        value: BaseModel | dict[str, Any],
        *,
        stage: str,
        parent_ids: list[str] | None = None,
    ) -> str:
        payload = value.model_dump(mode="json") if isinstance(value, BaseModel) else value
        return self._write_immutable(name, _json_bytes(payload), stage, parent_ids)

    def write_state_json(
        self,
        name: str,
        value: BaseModel | dict[str, Any],
    ) -> None:
        """Write mutable run state (WorkingMemory / ArtifactBoard).

        These are blackboards, not artifacts: they change on every stage and
        must not be treated as immutable deliverables.  They are still written
        atomically inside the run root.
        """
        payload = value.model_dump(mode="json") if isinstance(value, BaseModel) else value
        _atomic_write(self.path(name), _json_bytes(payload))

    def write_text(
        self,
        name: str,
        text: str,
        *,
        stage: str,
        parent_ids: list[str] | None = None,
    ) -> str:
        return self._write_immutable(name, text.encode("utf-8"), stage, parent_ids)

    def write_jsonl(
        self,
        name: str,
        rows: Iterable[dict[str, Any]],
        *,
        stage: str,
        parent_ids: list[str] | None = None,
    ) -> str:
        return self._write_immutable(name, _jsonl_bytes(rows), stage, parent_ids)

    def register_file(
        self,
        name: str,
        *,
        stage: str,
        parent_ids: list[str] | None = None,
    ) -> str:
        """Register an existing file (copied figure / rendered SVG) by hash.

        Binary assets are copied by domain code; this keeps them in the same
        immutable manifest as text artifacts without rewriting them.
        """
        path = self.path(name)
        if not path.is_file():
            raise FileNotFoundError(f"artifact 不存在: {path}")
        digest = file_sha256(path)
        if name.replace("\\", "/") not in self._manifest["artifacts"]:
            self._register(name, digest, path.stat().st_size, stage, parent_ids)
        return digest

    def _write_immutable(
        self,
        name: str,
        data: bytes,
        stage: str,
        parent_ids: list[str] | None,
    ) -> str:
        path = self.path(name)
        digest = _sha(data)
        if path.exists():
            existing = path.read_bytes()
            if existing == data:
                self._ensure_registered(name, stage, parent_ids)
                return digest
            raise OverwriteRefused(
                f"拒绝覆盖已有 artifact: {name}（内容不同）。新版本请使用新 run/revision。"
            )
        _atomic_write(path, data)
        self._register(name, digest, len(data), stage, parent_ids)
        return digest

    def _ensure_registered(
        self, name: str, stage: str, parent_ids: list[str] | None
    ) -> None:
        if name in self._manifest["artifacts"]:
            return
        path = self.path(name)
        self._register(name, file_sha256(path), path.stat().st_size, stage, parent_ids)

    def _register(
        self,
        name: str,
        digest: str,
        size: int,
        stage: str,
        parent_ids: list[str] | None,
    ) -> None:
        rel = name.replace("\\", "/")
        self._manifest["artifacts"][rel] = {
            "sha256": digest,
            "bytes": size,
            "stage": stage,
            "created_at": utc_now_iso(),
            "parent_ids": parent_ids or [],
        }
        self._save_manifest()

    # ------------------------------------------------------------------
    # logs
    # ------------------------------------------------------------------
    def append_jsonl(self, name: str, row: dict[str, Any], *, id_key: str) -> bool:
        with self._lock:
            rows = self.read_jsonl(name)
            if any(
                str(existing.get(id_key)) == str(row.get(id_key))
                for existing in rows
            ):
                return False
            rows.append(row)
            _atomic_write(self.path(name), _jsonl_bytes(rows))
            return True

    def record_decision(self, record: dict[str, Any]) -> None:
        self.append_jsonl("decision_records.jsonl", record, id_key="decision_id")

    def record_tool_call(self, record: dict[str, Any]) -> None:
        self.append_jsonl("tool_calls.jsonl", record, id_key="call_id")

    def record_llm_call(self, record: dict[str, Any]) -> None:
        with self._lock:
            inserted = self.append_jsonl(
                "llm_calls.jsonl", record, id_key="call_id"
            )
            if not inserted:
                return
            usage = record.get("usage") or {}
            bucket = self._manifest["usage"]
            bucket["calls"] = int(bucket.get("calls", 0)) + 1
            for key in (
                "prompt_tokens",
                "completion_tokens",
                "total_tokens",
                "reasoning_tokens",
            ):
                bucket[key] = int(bucket.get(key, 0)) + int(
                    usage.get(key, 0) or 0
                )
            bucket["latency_ms"] = int(bucket.get("latency_ms", 0)) + int(
                record.get("latency_ms", 0) or 0
            )
            self._save_manifest()

    def load_llm_records(self) -> list[dict[str, Any]]:
        return self.read_jsonl("llm_calls.jsonl")

    # ------------------------------------------------------------------
    # manifest / task plan
    # ------------------------------------------------------------------
    def _load_manifest(self) -> dict[str, Any]:
        return json.loads(self.manifest_path.read_text(encoding="utf-8-sig"))

    def _save_manifest(self) -> None:
        with self._lock:
            self._manifest["updated_at"] = utc_now_iso()
            _atomic_write(self.manifest_path, _json_bytes(self._manifest))

    @property
    def manifest(self) -> dict[str, Any]:
        return self._manifest

    def refresh_manifest(self) -> dict[str, Any]:
        self._manifest = self._load_manifest()
        return self._manifest

    def load_task_plan(self) -> TaskPlan:
        return TaskPlan.model_validate(self.read_json("task_plan.json"))

    def save_task_plan(self, plan: TaskPlan) -> None:
        """Replace the run's task plan (used by the bundle orchestrator)."""
        self._save_task_plan(plan)

    def _save_task_plan(self, plan: TaskPlan) -> None:
        with self._lock:
            _atomic_write(
                self.path("task_plan.json"), _json_bytes(plan.model_dump(mode="json"))
            )

    def record_stage(
        self,
        stage: str,
        status: str,
        *,
        duration_ms: int = 0,
        error: str | None = None,
        artifacts: list[str] | None = None,
    ) -> None:
        self._manifest["stages"][stage] = {
            "status": status,
            "duration_ms": duration_ms,
            "error": error,
            "artifacts": artifacts or [],
            "updated_at": utc_now_iso(),
        }
        self._save_manifest()
        with self._lock:
            plan = self.load_task_plan()
            node_status = {
                "succeeded": "succeeded",
                "partial": "partial",
                "failed": "failed",
                "running": "running",
                "skipped": "skipped",
                "reused": "reused",
            }.get(status, status)
            if any(n.task_id == stage for n in plan.nodes):
                plan = update_node(
                    plan,
                    stage,
                    node_status,
                    error=error,
                    attempt={
                        "status": status,
                        "duration_ms": duration_ms,
                        "error": error,
                        "at": utc_now_iso(),
                    },
                )
                self._save_task_plan(plan)

    def set_current(self, key: str, value: Any) -> None:
        self._manifest["current"][key] = value
        self._save_manifest()

    def set_status(self, status: str, *, ended: bool = False) -> None:
        self._manifest["status"] = status
        if ended:
            self._manifest["ended_at"] = utc_now_iso()
        self._save_manifest()

    def add_note(self, note: str) -> None:
        self._manifest["notes"].append(note)
        self._save_manifest()

    # ------------------------------------------------------------------
    # provider sink
    # ------------------------------------------------------------------
    def llm_sink(self, record: dict[str, Any]) -> None:
        self.record_llm_call(record)

    def artifact(self, name: str) -> dict[str, Any] | None:
        return self._manifest["artifacts"].get(name.replace("\\", "/"))

    def verify_artifacts(self) -> list[str]:
        """Return files whose on-disk hash no longer matches the manifest."""
        errors = []
        for name, record in self._manifest["artifacts"].items():
            path = self.path(name)
            if not path.exists() or file_sha256(path) != record["sha256"]:
                errors.append(name)
        return errors


def _sha(data: bytes) -> str:
    import hashlib

    return hashlib.sha256(data).hexdigest()


def default_runs_root() -> Path:
    return project_root() / "runs"
