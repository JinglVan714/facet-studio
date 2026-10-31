"""Seal an artifact with a semantic hash and a content-derived ID."""

from __future__ import annotations

from typing import TypeVar

from pydantic import BaseModel

from .hashing import semantic_hash

T = TypeVar("T", bound=BaseModel)


def seal(
    model: T,
    *,
    id_field: str,
    hash_field: str,
    prefix: str,
    exclude_keys: tuple[str, ...] = (),
) -> T:
    """Return a copy with ``hash_field`` and ``id_field`` set.

    The hash is computed over the semantic payload only: the ID itself, the
    hash field, timestamps and run IDs are excluded.
    """
    payload = model.model_dump(mode="json")
    payload.pop(id_field, None)
    payload.pop(hash_field, None)
    digest = semantic_hash(payload, exclude_keys)
    return model.model_copy(
        update={hash_field: digest, id_field: f"{prefix}_{digest[:12]}"}
    )
