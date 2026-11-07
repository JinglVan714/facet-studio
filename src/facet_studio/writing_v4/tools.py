"""Domain tools for the bundle orchestrator.

These are deterministic services with explicit schemas and real receipts:
content compile, structural inspect and bundle assembly.  Model calls stay
provider calls; they are not disguised as tools.
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import Any

from ..core.hashing import sha256_text
from ..runtime.tools import ToolRegistry, ToolSpec
from .writer import figure_refs, missing_figures

FIGURE_NOTE = re.compile(r"图：\s*(figures/[^\s）)]+)")


def parse_figure_catalog(content: str) -> list[str]:
    """Figure ids (``fig-01.jpg``) in content order."""
    names = [Path(match.group(1)).name for match in FIGURE_NOTE.finditer(content)]
    return list(dict.fromkeys(names))


def compile_content(args: dict[str, Any]) -> dict[str, Any]:
    source = Path(str(args["content_path"]))
    out_dir = Path(str(args["out_dir"]))
    out_dir.mkdir(parents=True, exist_ok=True)
    text = source.read_text(encoding="utf-8")
    (out_dir / "content.md").write_text(text, encoding="utf-8")

    figures: list[str] = []
    figures_src = source.parent / "figures"
    figures_dst = out_dir / "figures"
    if figures_src.is_dir():
        figures_dst.mkdir(parents=True, exist_ok=True)
        for item in sorted(figures_src.iterdir()):
            if item.is_file():
                shutil.copy2(item, figures_dst / item.name)
                figures.append(f"figures/{item.name}")
    return {
        "content_path": str(out_dir / "content.md"),
        "content_sha256": sha256_text(text),
        "chars": len(text),
        "figures": figures,
        "figure_count": len(figures),
    }


def inspect_output(args: dict[str, Any]) -> dict[str, Any]:
    form_dir = Path(str(args["form_dir"]))
    output_name = str(args.get("output_name") or "article.md")
    path = form_dir / output_name
    if not path.is_file():
        return {
            "exists": False,
            "output": output_name,
            "chars": 0,
            "figures": [],
            "missing_figures": [],
        }
    text = path.read_text(encoding="utf-8")
    return {
        "exists": True,
        "output": output_name,
        "chars": len(text),
        "figures": figure_refs(text),
        "missing_figures": missing_figures(text, form_dir),
    }


def assemble_bundle(args: dict[str, Any]) -> dict[str, Any]:
    run_dir = Path(str(args["run_dir"]))
    video_id = str(args["video_id"])
    plan = args.get("plan") or {}
    forms = args.get("forms") or []

    lines = [f"# 内容包：{video_id}", "", "## 总编辑计划", ""]
    lines.append(f"- 控制性 idea：{plan.get('central_idea', '')}")
    lines.append(f"- 读者目标：{plan.get('reader_goal', '')}")
    lines.append("")
    plan_forms = plan.get("forms") or []
    if plan_forms:
        lines.append("### 产物选择")
        for item in plan_forms:
            lines.append(
                f"- **{item.get('form', '')}**：{item.get('angle', '')} — "
                f"{item.get('brief', '')}"
            )
        lines.append("")

    lines.append("## 产物")
    for item in forms:
        form = item.get("form", "")
        output = item.get("output") or "article.md"
        status = item.get("status", "")
        chars = item.get("output_chars", 0)
        figures = len(item.get("figures_referenced") or [])
        svg = len(item.get("svg_assets") or [])
        lines.append(
            f"- [{form}]({form}/{output}) — {chars} 字 — "
            f"{figures} 图 / {svg} SVG — {status}"
        )
        if item.get("error"):
            lines.append(f"  - error: {item['error']}")
    lines.append("")

    constraints = plan.get("shared_constraints") or []
    if constraints:
        lines.append("## 共享约束")
        lines.extend(f"- {item}" for item in constraints)
        lines.append("")

    contracts = [
        (item.get("form", ""), item.get("reader_contract") or {})
        for item in forms
    ]
    contracts = [(form, contract) for form, contract in contracts if contract]
    if contracts:
        lines.append("## 读者契约")
        for form, contract in contracts:
            lines.append(
                f"- **{form}**：{contract.get('title_promise', '')} "
                f"（目标：{contract.get('reader_goal', '')}）"
            )
        lines.append("")

    path = run_dir / "bundle.md"
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return {"path": str(path), "forms": len(forms)}


def build_registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(
        ToolSpec(
            name="compile_content",
            description="把内容稿和 figures 复制到 run 目录，返回内容 hash/字数/图示。",
            input_schema={
                "required": ["content_path", "out_dir"],
                "properties": {
                    "content_path": {"type": "string"},
                    "out_dir": {"type": "string"},
                },
            },
            allowed_roles=["orchestrator"],
            side_effect="write",
            timeout_s=30,
        ),
        compile_content,
    )
    registry.register(
        ToolSpec(
            name="inspect_output",
            description="检查一个产物是否存在、字数、图示引用和缺失图示。",
            input_schema={
                "required": ["form_dir"],
                "properties": {
                    "form_dir": {"type": "string"},
                    "output_name": {"type": "string"},
                },
            },
            allowed_roles=["orchestrator"],
            side_effect="read",
            timeout_s=10,
        ),
        inspect_output,
    )
    registry.register(
        ToolSpec(
            name="assemble_bundle",
            description="把 plan 和各产物结果装配成 bundle.md。",
            input_schema={
                "required": ["run_dir", "video_id", "plan", "forms"],
                "properties": {
                    "run_dir": {"type": "string"},
                    "video_id": {"type": "string"},
                    "plan": {"type": "object"},
                    "forms": {"type": "array"},
                },
            },
            allowed_roles=["orchestrator"],
            side_effect="write",
            timeout_s=10,
        ),
        assemble_bundle,
    )
    return registry
