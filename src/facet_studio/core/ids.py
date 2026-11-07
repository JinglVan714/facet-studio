"""Stable identifiers.

Domain objects never accept model-invented IDs.  IDs are derived from
canonical content (or from an already-validated parent ID set) so that the
same input produces the same identity across runs.
"""

from __future__ import annotations

import re
from typing import Iterable

from .hashing import short_hash

_SEPARATOR = "\x1f"
_SAFE_RUN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")


def make_id(prefix: str, *parts: object, length: int = 12) -> str:
    seed = _SEPARATOR.join(str(p) for p in parts)
    return f"{prefix}_{short_hash(seed, length)}"


def make_id_from_members(prefix: str, members: Iterable[str], length: int = 12) -> str:
    return make_id(prefix, *sorted(members), length=length)


def validate_run_id(run_id: str) -> str:
    if not _SAFE_RUN_ID.match(run_id):
        raise ValueError(f"非法 run_id: {run_id!r}")
    return run_id
