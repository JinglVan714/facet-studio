"""WritingRequest loader/validator (``writing-request-v1``).

The request is a frozen input: it defines the reader, the central question,
the required/forbidden content, and whether audit/claim/parts are needed.
No model calls.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..core.hashing import semantic_hash

SCHEMA = "writing-request-v1"
RISK_LEVELS = {"low", "medium", "high"}
AUDIT_LEVELS = {"none", "claim", "boundary", "reuse"}
PROFILES = {"full_text", "claim_lean", "index_parts", "sectioned", "multi_source"}
BRIEF_MODES = {"auto", "none", "mini", "full", "human_review"}

REQUIRED_TEXT = [
    "schema_version",
    "request_id",
    "method_id",
    "form_id",
    "central_question",
    "job_to_be_done",
    "reader_before_state",
    "desired_reader_outcome",
]

DEFAULT_MEDIA_POLICY = {
    "allowed_kinds": [
        "real_frame",
        "table",
        "chart",
        "diagram",
        "text_experiment",
        "no_visual",
    ],
    "max_assets": 6,
    "generated_image_policy": "editorial_only",
    "real_frame_policy": "only_if_relevant",
}

DEFAULT_SOURCE_POLICY = {
    "substrate_facts": True,
    "model_knowledge": "editorial_only",
    "user_supplements": False,
    "external_web": False,
}

# The profile is optional and may be injected by the caller.  When absent we
# assume a capable reader with some technical baseline: keep standard terms,
# explain only when a term is load-bearing, and do not write an encyclopedia.
DEFAULT_READER_PROFILE = (
    "A smart general reader with some technical baseline. Keep standard terms; "
    "explain only load-bearing or genuinely unfamiliar terms in one concise "
    "sentence or analogy. Do not write an encyclopedia or a paper. If the "
    "request provides reader_profile/audience, follow it instead."
)


def validate_request(data: dict[str, Any]) -> dict[str, Any]:
    """Validate and normalize a request; raise ``ValueError`` on problems."""
    if not isinstance(data, dict):
        raise ValueError("request must be a JSON object")
    problems: list[str] = []
    for key in REQUIRED_TEXT:
        if not isinstance(data.get(key), str) or not data.get(key, "").strip():
            problems.append(f"{key} must be a non-empty string")
    if data.get("schema_version") != SCHEMA:
        problems.append(f"schema_version must be {SCHEMA}")
    video_ids = data.get("video_ids")
    if (
        not isinstance(video_ids, list)
        or not video_ids
        or not all(isinstance(item, str) and item for item in video_ids)
    ):
        problems.append("video_ids must be a non-empty list of strings")
    for key in ("success_criteria", "required_information", "forbidden_information"):
        value = data.get(key, [])
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            problems.append(f"{key} must be a list of strings")
    for key in ("reader_profile", "audience", "primary_objective"):
        value = data.get(key)
        if value is not None and (
            not isinstance(value, str) or not value.strip()
        ):
            problems.append(f"{key} must be a non-empty string when provided")
    risk = data.get("risk_level", "low")
    if risk not in RISK_LEVELS:
        problems.append(f"risk_level must be one of {sorted(RISK_LEVELS)}")
    audit = data.get("audit_level", "none")
    if audit not in AUDIT_LEVELS:
        problems.append(f"audit_level must be one of {sorted(AUDIT_LEVELS)}")
    sections = data.get("sections_required", 1)
    if not isinstance(sections, int) or isinstance(sections, bool) or sections < 1:
        problems.append("sections_required must be an integer >= 1")
    brief_mode = data.get("brief_mode", "auto")
    if brief_mode not in BRIEF_MODES:
        problems.append(f"brief_mode must be one of {sorted(BRIEF_MODES)}")
    override = data.get("profile_override")
    if override is not None and override not in PROFILES:
        problems.append(f"profile_override must be one of {sorted(PROFILES)} or null")
    for key in ("media_policy", "source_policy"):
        value = data.get(key, {})
        if not isinstance(value, dict):
            problems.append(f"{key} must be an object")
    if problems:
        raise ValueError("; ".join(problems))

    normalized = dict(data)
    normalized.setdefault("language", "zh")
    normalized.setdefault("platform", "markdown")
    normalized.setdefault("risk_level", "low")
    normalized.setdefault("audit_level", "none")
    normalized.setdefault("sections_required", 1)
    normalized.setdefault("media_policy", dict(DEFAULT_MEDIA_POLICY))
    normalized.setdefault("source_policy", dict(DEFAULT_SOURCE_POLICY))
    normalized.setdefault("brief_mode", "auto")
    normalized.setdefault("profile_override", None)
    normalized.setdefault("success_criteria", [])
    normalized.setdefault("required_information", [])
    normalized.setdefault("forbidden_information", [])
    payload = {
        key: value for key, value in normalized.items() if key != "request_hash"
    }
    normalized["request_hash"] = semantic_hash(payload, drop_volatile=False)
    return normalized


def load_request(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    return validate_request(data)
