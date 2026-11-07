"""Skill loading with core + form composition.

A form skill may ``extends`` another skill (for example, ``wechat-article``
extends ``video-article``) and add platform references via ``includes``.  The
loader concatenates the core method, the form layer and the examples; it does
not build a per-form pipeline.

The writer only sees the composed system prompt and the user template.  It
does not see the source machinery (video / substrate / material packet).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEFAULTS: dict[str, Any] = {
    "skill": "SKILL.md",
    "examples": "references/examples.md",
    "prompt": "prompts/user.md",
    "source_line": "article",
    "output_name": "article.md",
    "max_tokens": 65536,
    "temperature": 0.5,
    "role": "writer",
    "form": "",
    "name": "",
    "description": "",
    "version": "0.0.0",
    "kind": "form",
}


class SkillError(RuntimeError):
    kind = "skill_error"


@dataclass
class LoadedSkill:
    skill_dir: Path
    manifest: dict[str, Any]
    system_parts: list[str]
    example_parts: list[str]
    user_template: str

    @property
    def id(self) -> str:
        return str(self.manifest.get("id") or self.skill_dir.name)

    @property
    def form(self) -> str:
        return str(self.manifest.get("form") or self.id)

    @property
    def name(self) -> str:
        return str(self.manifest.get("name") or self.id)

    @property
    def role(self) -> str:
        return str(self.manifest.get("role") or "writer")

    @property
    def version(self) -> str:
        return str(self.manifest.get("version") or "0.0.0")

    @property
    def kind(self) -> str:
        return str(self.manifest.get("kind") or "form")

    @property
    def source_line(self) -> str:
        return str(self.manifest.get("source_line") or "article")

    @property
    def output_name(self) -> str:
        return str(self.manifest.get("output_name") or "article.md")

    @property
    def max_tokens(self) -> int:
        return int(self.manifest.get("max_tokens") or DEFAULTS["max_tokens"])

    @property
    def temperature(self) -> float:
        return float(self.manifest.get("temperature") or DEFAULTS["temperature"])

    @property
    def system(self) -> str:
        parts = list(self.system_parts)
        if self.example_parts:
            parts.append("# 例子参考\n\n" + "\n\n---\n\n".join(self.example_parts))
        return "\n\n---\n\n".join(part for part in parts if part.strip())

    def render_user(
        self,
        *,
        request: str,
        content: str,
        catalog: str = "",
    ) -> str:
        text = self.user_template
        text = text.replace(
            "{request}", request.strip() or "（未指定；按 skill 默认读者）"
        )
        text = text.replace("{catalog}", catalog)
        if "{content}" in text:
            text = text.replace("{content}", content)
        else:
            text = text.rstrip() + "\n\n这件事的完整内容：\n\n" + content
        return text


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError as exc:
        raise SkillError(f"缺少 manifest：{path}") from exc
    except json.JSONDecodeError as exc:
        raise SkillError(f"manifest 不是合法 JSON：{path}: {exc}") from exc
    if not isinstance(value, dict):
        raise SkillError(f"manifest 必须是 object：{path}")
    return value


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise SkillError(f"缺少 skill 文件：{path}") from exc


def _resolve(base: Path, value: str) -> Path:
    path = Path(value)
    return path.resolve() if path.is_absolute() else (base / path).resolve()


def load_skill(skill_dir: Path, _seen: set[Path] | None = None) -> LoadedSkill:
    """Load a skill and, if present, its ``extends`` parent.

    The child's manifest overrides scalar fields (id/form/name/role/output/
    source_line/temperature/max_tokens); system parts and examples are
    appended parent-first so the core method stays in front of the form layer.
    """
    skill_dir = Path(skill_dir).resolve()
    seen = set(_seen or ())
    if skill_dir in seen:
        raise SkillError(f"skill extends 循环：{skill_dir}")
    seen.add(skill_dir)

    manifest = _read_json(skill_dir / "manifest.json")
    parent: LoadedSkill | None = None
    if manifest.get("extends"):
        parent_dir = _resolve(skill_dir, str(manifest["extends"]))
        if not (parent_dir / "manifest.json").is_file():
            raise SkillError(f"extends 指向的 skill 不存在：{parent_dir}")
        parent = load_skill(parent_dir, seen)

    merged: dict[str, Any] = dict(DEFAULTS)
    if parent is not None:
        merged.update(parent.manifest)
    merged.update(manifest)

    system_parts: list[str] = list(parent.system_parts) if parent else []
    skill_file = skill_dir / str(merged.get("skill") or DEFAULTS["skill"])
    system_parts.append(_read_text(skill_file))

    for include in manifest.get("includes") or []:
        system_parts.append(_read_text(_resolve(skill_dir, str(include))))

    example_parts: list[str] = list(parent.example_parts) if parent else []
    examples_value = manifest.get("examples")
    if examples_value:
        examples_path = _resolve(skill_dir, str(examples_value))
        if examples_path.is_file():
            example_parts.append(_read_text(examples_path))
    elif parent is None:
        default_examples = skill_dir / str(DEFAULTS["examples"])
        if default_examples.is_file():
            example_parts.append(_read_text(default_examples))

    own_prompt = manifest.get("prompt")
    if own_prompt:
        user_template = _read_text(_resolve(skill_dir, str(own_prompt)))
    elif parent is not None:
        user_template = parent.user_template
    else:
        user_template = _read_text(skill_dir / str(DEFAULTS["prompt"]))

    return LoadedSkill(
        skill_dir=skill_dir,
        manifest=merged,
        system_parts=system_parts,
        example_parts=example_parts,
        user_template=user_template,
    )


def form_catalog(skills_root: Path) -> list[dict[str, str]]:
    """Return form skills for the planner, without loading full prompts."""
    catalog: list[dict[str, str]] = []
    root = Path(skills_root)
    for manifest_path in sorted(root.glob("*/manifest.json")):
        data = _read_json(manifest_path)
        if str(data.get("kind") or "form") != "form":
            continue
        merged: dict[str, Any] = dict(data)
        if data.get("extends"):
            parent_path = _resolve(manifest_path.parent, str(data["extends"])) / "manifest.json"
            if parent_path.is_file():
                parent = _read_json(parent_path)
                merged = {**parent, **data}
        form_id = str(merged.get("form") or "")
        if not form_id:
            continue
        catalog.append(
            {
                "form": form_id,
                "name": str(merged.get("name") or merged.get("id") or ""),
                "role": str(merged.get("role") or "writer"),
                "description": str(merged.get("description") or ""),
                "skill_dir": str(manifest_path.parent),
            }
        )
    return catalog
