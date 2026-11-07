"""Small append-only trace/receipt recorder for v3 prototypes.

Every stage can write a receipt (counts, params, hashes, decisions, samples)
and append one JSONL event.  This is intentionally smaller than a full
harness: enough to answer "what went in, what came out, what was dropped".
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class TraceRecorder:
    def __init__(self, out_dir: Path):
        self.out_dir = out_dir
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.receipts_dir = out_dir / "stage_receipts"
        self.receipts_dir.mkdir(parents=True, exist_ok=True)
        self.trace_path = out_dir / "trace.jsonl"
        self._trace = self.trace_path.open("a", encoding="utf-8")

    def close(self) -> None:
        self._trace.close()

    def event(self, event: str, **fields: Any) -> None:
        self._trace.write(
            json.dumps(
                {"ts": _now(), "event": event, **fields},
                ensure_ascii=False,
            )
            + "\n"
        )
        self._trace.flush()

    def stage(
        self,
        stage: str,
        *,
        status: str,
        inputs: dict[str, Path | None],
        outputs: dict[str, Path | None],
        counts: dict[str, Any],
        params: dict[str, Any] | None = None,
        decisions: dict[str, Any] | None = None,
        samples: list[Any] | None = None,
    ) -> dict[str, Any]:
        receipt = {
            "stage": stage,
            "status": status,
            "ts": _now(),
            "inputs": {
                name: (
                    {
                        "path": str(path),
                        "sha256": _file_sha256(path),
                        "bytes": path.stat().st_size,
                    }
                    if path is not None and path.exists()
                    else None
                )
                for name, path in inputs.items()
            },
            "outputs": {
                name: (
                    {
                        "path": str(path),
                        "sha256": _file_sha256(path),
                        "bytes": path.stat().st_size,
                    }
                    if path is not None and path.exists()
                    else None
                )
                for name, path in outputs.items()
            },
            "counts": counts,
            "params": params or {},
            "decisions": decisions or {},
            "samples": samples or [],
        }
        receipt_path = self.receipts_dir / f"{stage}.json"
        receipt_path.write_text(
            json.dumps(receipt, ensure_ascii=False, indent=1), encoding="utf-8"
        )
        self.event("stage", stage=stage, status=status, counts=counts)
        return receipt
