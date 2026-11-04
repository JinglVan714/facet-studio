"""Skill package loader (Agent Skills format).

A skill is a directory with ``manifest.json`` + ``SKILL.md`` and optional
``examples.md`` / ``rubric.md`` / ``SOURCES.md`` / references / scripts /
assets.  This module only loads and hashes the package; the Writer prompt is
built separately.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

HASH_FILES = (
    "SKILL.md",
    "examples.md",
    "rubric.md",
    "SOURCES.md",
    "references/planning.md",
    "references/structure.md",
    "references/visuals.md",
    "references/evidence.md",
)
REQUIRED_MANIFEST = ("schema_version", "skill_id", "version", "output_contract")


class SkillError(ValueError):
    """Invalid or incomplete skill package."""


@dataclass(frozen=True)
class SkillPackage:
    skill_dir: Path
    manifest: dict[str, Any]
    body: str
    planning: str
    examples: str
    rubric: str
    sources: str
    content_hash: str
    hash_ok: bool

    @property
    def skill_id(self) -> str:
        return str(self.manifest.get("skill_id", ""))

    @property
    def version(self) -> str:
        return str(self.manifest.get("version", ""))

    @property
    def status(self) -> str:
        return str(self.manifest.get("status", ""))


def _read(path: Path, *, required: bool = False) -> str:
    if not path.exists():
        if required:
            raise SkillError(f"missing skill file: {path}")
        return ""
    return path.read_text(encoding="utf-8-sig")


def _strip_frontmatter(text: str) -> str:
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) == 3:
            return parts[2].strip()
    return text.strip()


def _content_hash(skill_dir: Path) -> str:
    digest = hashlib.sha256()
    for name in HASH_FILES:
        digest.update(name.encode("utf-8"))
        digest.update(b"\0")
        path = skill_dir / name
        if path.exists():
            digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def load_skill(skill_dir: Path) -> SkillPackage:
    """Load and validate a skill package; does not call a model."""
    skill_dir = Path(skill_dir)
    if not skill_dir.is_dir():
        raise SkillError(f"skill directory not found: {skill_dir}")
    manifest_path = skill_dir / "manifest.json"
    if not manifest_path.exists():
        raise SkillError(f"missing manifest.json: {skill_dir}")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        raise SkillError(f"invalid manifest.json: {exc}") from exc
    if not isinstance(manifest, dict):
        raise SkillError("manifest.json must be an object")
    problems = [
        f"{key} is required"
        for key in REQUIRED_MANIFEST
        if not manifest.get(key)
    ]
    if manifest.get("output_contract") != "markdown":
        problems.append("output_contract must be 'markdown' for the prose Writer")
    if problems:
        raise SkillError("; ".join(problems))

    body = _strip_frontmatter(_read(skill_dir / "SKILL.md", required=True))
    planning = _read(skill_dir / "references/planning.md")
    examples = _read(skill_dir / "examples.md")
    rubric = _read(skill_dir / "rubric.md")
    sources = _read(skill_dir / "SOURCES.md")
    content_hash = _content_hash(skill_dir)
    declared = manifest.get("manifest_hash")
    hash_ok = not declared or declared == content_hash
    return SkillPackage(
        skill_dir=skill_dir,
        manifest=manifest,
        body=body,
        planning=planning,
        examples=examples,
        rubric=rubric,
        sources=sources,
        content_hash=content_hash,
        hash_ok=hash_ok,
    )
