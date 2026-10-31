"""Canonical JSON, semantic hashes and file hashes.

Semantic hashes deliberately exclude volatile bookkeeping fields
(``created_at``, ``run_id``).  This is what makes replay comparable:
a replayed artifact may have a different timestamp but the same semantic
hash.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

VOLATILE_KEYS = frozenset({"created_at", "run_id", "generated_at"})


def canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


def _strip_volatile(value: Any, excluded: frozenset[str]) -> Any:
    if isinstance(value, dict):
        return {
            k: _strip_volatile(v, excluded)
            for k, v in value.items()
            if k not in excluded
        }
    if isinstance(value, (list, tuple)):
        return [_strip_volatile(v, excluded) for v in value]
    return value


def semantic_hash(
    value: Any,
    exclude_keys: Iterable[str] = (),
    *,
    drop_volatile: bool = True,
) -> str:
    excluded = set(exclude_keys)
    if drop_volatile:
        excluded |= VOLATILE_KEYS
    payload = _strip_volatile(value, frozenset(excluded))
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def file_sha256(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            chunk = fh.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def short_hash(value: str | bytes, length: int = 12) -> str:
    raw = value.encode("utf-8") if isinstance(value, str) else value
    return hashlib.sha256(raw).hexdigest()[:length]
