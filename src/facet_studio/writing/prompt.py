"""Prose Writer prompt builder.

The skill body is the system prompt; examples are appended.  The user prompt
contains the frozen request plus the assembled working context.  No IDs or
timecodes are added to the full-text path.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from .request import DEFAULT_READER_PROFILE
from .skill import SkillPackage

TEXT_INPUT_NOTE = (
    "The user prompt contains `evidence_text`: the compiled edited transcript, "
    "in viewing order. Use it as the only source for video facts; model "
    "knowledge may explain, analogize, or organize, but must not be presented "
    "as a video fact. The user prompt also contains `reader_profile`; follow "
    "it."
)
CLAIM_INPUT_NOTE = (
    "The user prompt contains `claim_view`: writing-level claims with status, "
    "scope, context sentences and frame captions. Use it as the evidence "
    "source for video facts; do not output claim/evidence IDs. The user prompt "
    "also contains `reader_profile`; follow it."
)
FINAL_LINE = (
    "Return only the Markdown article. No JSON, no code fence, no prose "
    "outside the article."
)
REPAIR_INSTRUCTION = """## Repair task

The draft was rejected by deterministic binding/structure checks or an
independent verifier. Fix only the listed problems. Do not add new facts,
numbers, names, quotes or visuals.

For binding issues: if a number/unit/identifier is not in the evidence, remove
it or paraphrase around it. If a quoted phrase is listed as unbound/outside/not
exact, remove the quotation marks and paraphrase it in plain prose, or delete
the quoted fragment; do not leave a near-verbatim quote in quotation marks and
do not add new quotes to compensate.

For semantic issues (contract/verifier): qualify unverified source/product
claims with “视频称/未核实”, add the missing source line/next step without
inventing URLs, state the metric/task/baseline or remove the number, hedge
absolute claims to the evidence scope, define only load-bearing terms in one
concise sentence (keep the term), fix title/body mismatch, and remove any claim
the source does not support. If the source line contradicts a frame-OCR
metadata hint (channel/title/date), correct it with “画面显示/未核实”; never
invent a link.

For speaker findings: if the source has no speaker labels and the finding says
the attribution is unsupported, replace the named attribution with “对话里/
视频里” or remove the quote; do not guess from proximity. If the source
explicitly addresses a person in third person (“X，你……”), attribute the
line to the other speaker, not to the addressed person.

For visual issues: do not change an image or its caption unless a listed
finding explicitly quotes that image/caption. If a caption claims something
the image does not show, rewrite the caption to describe only what the finding
says is visible, or remove the image and its caption. Do not invent a new
caption about unseen content, a replacement image, or a new frame. Preserve
existing image paths unless removing a bad visual. Keep the article's
headings and structure unless the finding is about a heading; keep all
supported content. Return the full corrected Markdown article only."""


def _brief_payload(brief: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "shape",
        "reader",
        "core_argument",
        "source_question",
        "payoff",
        "throughline",
        "spine",
        "titles",
        "stance",
        "cut",
        "title_check",
        "concept_ledger",
        "mechanism_chain",
        "number_ledger",
        "source_block",
        "texture_policy",
        "next_step",
    )
    payload = {key: brief[key] for key in keys if key in brief}
    titles = payload.get("titles")
    if isinstance(titles, list):
        chosen = [
            item
            for item in titles
            if isinstance(item, dict) and item.get("chosen")
        ]
        if chosen:
            payload["titles"] = chosen
    return payload


def build_repair_user(
    request: dict[str, Any],
    context: dict[str, Any],
    draft: str,
    findings: dict[str, Any],
    writing_plan: dict[str, Any] | None = None,
    writing_brief: dict[str, Any] | None = None,
) -> str:
    profile = context.get("profile", "")
    payload: dict[str, Any] = {
        "request": request,
        "reader_profile": request.get("reader_profile") or DEFAULT_READER_PROFILE,
        "draft": draft,
        "issues": findings,
    }
    if profile == "claim_lean":
        payload["claim_view"] = {
            "claims": context.get("claims", []),
            "frames": context.get("frames", []),
        }
    else:
        payload["evidence_text"] = context.get("text", "")
    if writing_brief and writing_brief.get("core_argument"):
        payload["writing_brief"] = _brief_payload(writing_brief)
    elif writing_plan and writing_plan.get("toc"):
        payload["writing_plan"] = {
            "title": writing_plan.get("title", ""),
            "controlling_idea": writing_plan.get("controlling_idea", ""),
            "toc": writing_plan.get("toc", []),
        }
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def build_system_prompt(
    skill: SkillPackage, *, input_kind: str = "text"
) -> str:
    parts = [skill.body]
    note = CLAIM_INPUT_NOTE if input_kind == "claim" else TEXT_INPUT_NOTE
    parts.append(f"## Input note\n\n{note}")
    if skill.examples:
        parts.append("## Examples\n\n" + skill.examples.strip())
    parts.append(FINAL_LINE)
    return "\n\n".join(parts)


def build_user_prompt(
    request: dict[str, Any],
    context: dict[str, Any],
    writing_plan: dict[str, Any] | None = None,
    writing_brief: dict[str, Any] | None = None,
) -> str:
    profile = context.get("profile", "")
    if profile == "full_text":
        payload = {
            "request": request,
            "reader_profile": request.get("reader_profile") or DEFAULT_READER_PROFILE,
            "evidence_text": context.get("text", ""),
        }
    elif profile == "claim_lean":
        payload = {
            "request": request,
            "reader_profile": request.get("reader_profile") or DEFAULT_READER_PROFILE,
            "claim_view": {
                "claims": context.get("claims", []),
                "frames": context.get("frames", []),
            },
        }
    else:
        raise ValueError(
            f"Writer prompt does not support profile={profile!r}; "
            "use full_text/claim_lean, or inject one part for index_parts"
        )
    if writing_brief and writing_brief.get("core_argument"):
        payload["writing_brief"] = _brief_payload(writing_brief)
    elif writing_plan and writing_plan.get("toc"):
        payload["writing_plan"] = {
            "title": writing_plan.get("title", ""),
            "controlling_idea": writing_plan.get("controlling_idea", ""),
            "toc": writing_plan.get("toc", []),
        }
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def sha_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
