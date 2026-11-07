"""Structured-output parsing with explicit failure."""

from __future__ import annotations

import json
import re
from typing import Any

_VOLATILE_KEYS = frozenset({"created_at", "run_id", "generated_at", "updated_at"})


def prompt_view(value: Any) -> Any:
    """Strip volatile bookkeeping from data embedded in LLM prompts.

    Replay compares request hashes; a differing timestamp must not make the
    same semantic request look different.
    """
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    if isinstance(value, dict):
        return {
            k: prompt_view(v) for k, v in value.items() if k not in _VOLATILE_KEYS
        }
    if isinstance(value, (list, tuple)):
        return [prompt_view(v) for v in value]
    return value


def prompt_view_contract(value: Any) -> Any:
    """Contract view that omits P1-only fields when they are empty.

    Legacy runs (markdown-article-v1 before P1) had no ``checks``,
    ``review_profile_id`` or ``appendix_heading`` keys.  Leaving empty defaults
    out keeps their writer/reviewer input hashes replayable; new contracts
    always carry non-empty checks/appendix values.
    """
    data = prompt_view(value)
    if isinstance(data, dict):
        for key in (
            "checks",
            "review_profile_id",
            "appendix_heading",
            "structural_section_roles",
        ):
            if key in data and data[key] in (None, [], {}):
                data.pop(key)
    return data


class StructuredOutputError(ValueError):
    def __init__(self, message: str, raw: str = ""):
        super().__init__(message)
        self.raw = raw


_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)


def extract_json_object(text: str) -> dict[str, Any]:
    """Parse a JSON object from a model response.

    Accepts a bare object, a fenced block, or prose surrounding one object.
    Raises :class:`StructuredOutputError` instead of guessing.
    """
    candidate = _FENCE.sub("", text.strip()).strip()
    attempts = [candidate]
    start, end = candidate.find("{"), candidate.rfind("}")
    if start != -1 and end > start and (start != 0 or end != len(candidate) - 1):
        attempts.append(candidate[start : end + 1])
    last_error: Exception | None = None
    for attempt in attempts:
        try:
            value = json.loads(attempt)
            if not isinstance(value, dict):
                raise StructuredOutputError("模型输出不是 JSON object", raw=text)
            return value
        except json.JSONDecodeError as exc:
            last_error = exc
    raise StructuredOutputError(f"无法解析 JSON: {last_error}", raw=text)
