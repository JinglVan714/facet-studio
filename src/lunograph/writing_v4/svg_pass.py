"""Render writer/editor SVG placeholders into clean, deterministic diagrams.

The writer never writes SVG. It leaves:
    <!-- svg: 三层分类：A / B / C -->

This pass asks the model for a small diagram *spec* (JSON), then renders the
SVG locally.  The split keeps diagram geometry deterministic and testable.

Usage:
    PYTHONPATH=src python -m lunograph.writing_v4.svg_pass \
        --article runs/.../article.md \
        --out-article runs/.../article.md \
        --out-report runs/.../svg_report.md
"""

from __future__ import annotations

import argparse
import html
import json
import re
from pathlib import Path
from typing import Any

from ..core.config import get_settings
from ..providers.llm import DeepSeekLLM


PLACEHOLDER = re.compile(r"<!--\s*svg:\s*(.*?)\s*-->", re.S)
ALLOWED_KINDS = {"flow", "stack", "two-axis", "compare"}

SPEC_SYSTEM = """你是图表编辑。根据文章上下文和占位符描述，返回一个 JSON 图表规格；不要返回 SVG。

允许的 kind：
- "flow"：2–4 个顺序步骤，用方框和箭头。
- "stack"：2–4 层，用纵向层。
- "two-axis"：两条刻度/尺子对比（只用于同一量纲的刻度）。
- "compare"：2 个对象的并列对比，左右两张卡片。

字段：
{"kind":"flow|stack|two-axis|compare","title":"...","items":[{"label":"...","detail":"..."}],"caption":"..."}

要求：2–4 个 items；label/detail 只使用文章或占位符里出现的词；不引入新数字、事实或结论；caption 一句话，标注“示意”。
只输出 JSON。"""


class SpecError(ValueError):
    pass


def _extract_json(text: str) -> dict[str, Any]:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        raise SpecError("no JSON object in response")
    try:
        data = json.loads(text[start : end + 1])
    except json.JSONDecodeError as exc:
        raise SpecError(f"invalid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise SpecError("spec is not an object")
    return data


def _clean_text(value: Any, fallback: str = "") -> str:
    text = str(value or "").strip()
    return text or fallback


def normalize_spec(raw: dict[str, Any]) -> dict[str, Any]:
    kind = _clean_text(raw.get("kind"), "flow").lower()
    if kind == "three-column":
        kind = "flow"
    if kind not in ALLOWED_KINDS:
        kind = "flow"
    items = raw.get("items")
    if not isinstance(items, list):
        raise SpecError("items is not a list")
    cleaned = []
    for item in items[:4]:
        if not isinstance(item, dict):
            continue
        label = _clean_text(item.get("label"))
        detail = _clean_text(item.get("detail"))
        if label:
            cleaned.append({"label": label, "detail": detail})
    if len(cleaned) < 2:
        raise SpecError("need at least 2 items")
    title = _clean_text(raw.get("title"), "示意")
    caption = _clean_text(raw.get("caption"), title)
    if not caption.startswith("示意"):
        caption = "示意：" + caption
    return {"kind": kind, "title": title, "items": cleaned, "caption": caption}


def _wrap(text: str, width: int = 16, max_lines: int = 2) -> list[str]:
    text = _clean_text(text)
    if not text:
        return []
    lines = []
    current = ""
    for char in text:
        current += char
        if len(current) >= width:
            lines.append(current)
            current = ""
            if len(lines) >= max_lines:
                break
    if current and len(lines) < max_lines:
        lines.append(current)
    if len(lines) == max_lines and len("".join(lines)) < len(text):
        lines[-1] = lines[-1][: max(0, width - 1)] + "…"
    return lines


def _svg_open(title: str) -> str:
    return (
        '<svg viewBox="0 0 720 210" xmlns="http://www.w3.org/2000/svg" '
        'role="img" aria-label="' + html.escape(title, quote=True) + '">\n'
        "<title>" + html.escape(title) + "</title>\n"
        '<g font-family="system-ui, -apple-system, \'Segoe UI\', \'Microsoft YaHei\', sans-serif">\n'
    )


def render_flow(spec: dict[str, Any]) -> str:
    items = spec["items"]
    n = len(items)
    margin = 20
    gap = 12
    box_w = (720 - margin * 2 - gap * (n - 1)) / n
    box_h = 118
    parts = [
        _svg_open(spec["title"]),
        '<defs><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" '
        'markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
        '<path d="M 0 0 L 10 5 L 0 10 z" fill="#64748b"/></marker></defs>\n',
    ]
    fills = ["#f1f5f9", "#eff6ff", "#fef3c7", "#f0fdf4"]
    strokes = ["#cbd5e1", "#bfdbfe", "#fde68a", "#bbf7d0"]
    for index, item in enumerate(items):
        x = margin + index * (box_w + gap)
        parts.append(
            f'<rect x="{x:.1f}" y="28" width="{box_w:.1f}" height="{box_h}" rx="14" '
            f'fill="{fills[index % len(fills)]}" stroke="{strokes[index % len(strokes)]}"/>\n'
        )
        cx = x + box_w / 2
        parts.append(
            f'<text x="{cx:.1f}" y="62" text-anchor="middle" font-size="18" '
            f'font-weight="700" fill="#0f172a">{html.escape(item["label"])}</text>\n'
        )
        lines = _wrap(item["detail"], width=max(10, int(box_w / 16)), max_lines=2)
        for line_index, line in enumerate(lines):
            parts.append(
                f'<text x="{cx:.1f}" y="{92 + line_index * 21}" text-anchor="middle" '
                f'font-size="13" fill="#475569">{html.escape(line)}</text>\n'
            )
        if index < n - 1:
            ax = x + box_w + 1
            parts.append(
                f'<line x1="{ax:.1f}" y1="87" x2="{ax + gap - 2:.1f}" y2="87" '
                'stroke="#64748b" stroke-width="2" marker-end="url(#arrow)"/>\n'
            )
    parts.append("</g>\n</svg>\n")
    return "".join(parts)


def render_stack(spec: dict[str, Any]) -> str:
    items = spec["items"][:4]
    row_h = 44
    top = 26
    parts = [_svg_open(spec["title"])]
    for index, item in enumerate(items):
        y = top + index * (row_h + 8)
        parts.append(
            f'<rect x="20" y="{y}" width="680" height="{row_h}" rx="10" '
            'fill="#f8fafc" stroke="#cbd5e1"/>\n'
        )
        parts.append(
            f'<text x="36" y="{y + 27}" font-size="16" font-weight="700" fill="#0f172a">'
            f'{html.escape(item["label"])}</text>\n'
        )
        if item["detail"]:
            parts.append(
                f'<text x="250" y="{y + 27}" font-size="13" fill="#475569">'
                f'{html.escape(item["detail"])}</text>\n'
            )
    parts.append("</g>\n</svg>\n")
    return "".join(parts)


def render_two_axis(spec: dict[str, Any]) -> str:
    items = spec["items"][:2]
    parts = [_svg_open(spec["title"])]
    for index, item in enumerate(items):
        y = 64 + index * 72
        parts.append(
            f'<text x="24" y="{y - 12}" font-size="14" font-weight="700" fill="#0f172a">'
            f'{html.escape(item["label"])}</text>\n'
        )
        if item["detail"]:
            parts.append(
                f'<text x="24" y="{y + 8}" font-size="12" fill="#475569">'
                f'{html.escape(item["detail"])}</text>\n'
            )
        parts.append(
            f'<line x1="170" y1="{y}" x2="660" y2="{y}" stroke="#cbd5e1" stroke-width="2"/>\n'
        )
        for tick in (0.25, 0.5, 0.75):
            x = 170 + tick * 490
            parts.append(
                f'<line x1="{x:.1f}" y1="{y - 6}" x2="{x:.1f}" y2="{y + 6}" '
                'stroke="#94a3b8" stroke-width="1.5"/>\n'
            )
    parts.append("</g>\n</svg>\n")
    return "".join(parts)


def render_compare(spec: dict[str, Any]) -> str:
    items = spec["items"][:2]
    n = len(items)
    margin = 20
    gap = 16
    box_w = (720 - margin * 2 - gap * (n - 1)) / n
    parts = [_svg_open(spec["title"])]
    fills = ["#f1f5f9", "#eff6ff"]
    strokes = ["#cbd5e1", "#bfdbfe"]
    for index, item in enumerate(items):
        x = margin + index * (box_w + gap)
        parts.append(
            f'<rect x="{x:.1f}" y="30" width="{box_w:.1f}" height="122" rx="14" '
            f'fill="{fills[index % 2]}" stroke="{strokes[index % 2]}"/>\n'
        )
        cx = x + box_w / 2
        parts.append(
            f'<text x="{cx:.1f}" y="66" text-anchor="middle" font-size="19" '
            f'font-weight="700" fill="#0f172a">{html.escape(item["label"])}</text>\n'
        )
        lines = _wrap(item["detail"], width=max(12, int(box_w / 15)), max_lines=3)
        for line_index, line in enumerate(lines):
            parts.append(
                f'<text x="{cx:.1f}" y="{96 + line_index * 22}" text-anchor="middle" '
                f'font-size="13" fill="#475569">{html.escape(line)}</text>\n'
            )
    parts.append(
        f'<line x1="{margin + box_w + gap / 2:.1f}" y1="42" '
        f'x2="{margin + box_w + gap / 2:.1f}" y2="140" stroke="#e2e8f0" stroke-width="2"/>\n'
    )
    parts.append("</g>\n</svg>\n")
    return "".join(parts)


def render_svg(spec: dict[str, Any]) -> str:
    if spec["kind"] == "stack":
        return render_stack(spec)
    if spec["kind"] == "two-axis":
        return render_two_axis(spec)
    if spec["kind"] == "compare":
        return render_compare(spec)
    return render_flow(spec)


def _context(article: str, start: int, end: int, width: int = 700) -> str:
    left = article[max(0, start - width) : start]
    right = article[end : end + width]
    return left + "\n...[占位符]...\n" + right


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render SVG placeholders.")
    parser.add_argument("--article", type=Path, required=True)
    parser.add_argument("--out-article", type=Path, required=True)
    parser.add_argument("--out-report", type=Path, required=True)
    parser.add_argument("--max", type=int, default=2)
    args = parser.parse_args(argv)

    args.out_article.parent.mkdir(parents=True, exist_ok=True)
    args.out_report.parent.mkdir(parents=True, exist_ok=True)
    article = args.article.read_text(encoding="utf-8")
    matches = list(PLACEHOLDER.finditer(article))
    if not matches:
        args.out_article.write_text(article, encoding="utf-8")
        args.out_report.write_text("无 SVG 占位符。\n", encoding="utf-8")
        print("no svg placeholders")
        return 0

    settings = get_settings()
    if not settings.provider_configured:
        raise SystemExit("provider not configured")
    client = DeepSeekLLM(settings)
    figures_dir = args.out_article.parent / "figures"
    figures_dir.mkdir(parents=True, exist_ok=True)

    report: list[str] = ["# SVG pass\n"]
    replacements: list[tuple[int, int, str]] = []
    for index, match in enumerate(matches[: args.max], start=1):
        brief = match.group(1).strip()
        context = _context(article, match.start(), match.end())
        user = (
            "占位符描述：\n"
            + brief
            + "\n\n文章上下文：\n"
            + context
            + "\n\n请返回 JSON 图表规格。"
        )
        try:
            response = client.complete(
                stage="writing_v4_svg_spec",
                key=brief,
                system=SPEC_SYSTEM,
                user=user,
                max_tokens=4096,
                temperature=0.0,
            )
            spec = normalize_spec(_extract_json(response.text))
            svg = render_svg(spec)
            filename = f"svg-{index:02d}.svg"
            (figures_dir / filename).write_text(svg, encoding="utf-8")
            replacement = f"![{spec['caption']}](figures/{filename})"
            replacements.append((match.start(), match.end(), replacement))
            report.append(
                f"## {index}. {brief}\n\n- kind: {spec['kind']}\n"
                f"- file: figures/{filename}\n- caption: {spec['caption']}\n"
            )
        except Exception as exc:  # noqa: BLE001 - report and skip
            report.append(f"## {index}. {brief}\n\n- skipped: {exc}\n")
            replacements.append((match.start(), match.end(), ""))

    for match in matches[args.max:]:
        report.append(
            f"## 超过上限\n\n{match.group(1).strip()}\n\n- skipped: max {args.max}/篇\n"
        )
        replacements.append((match.start(), match.end(), ""))

    # Replace from the end so offsets stay valid.
    for start, end, replacement in sorted(replacements, reverse=True):
        article = article[:start] + replacement + article[end:]
    args.out_article.write_text(article, encoding="utf-8")
    args.out_report.write_text("\n".join(report) + "\n", encoding="utf-8")
    print(f"rendered {len(replacements)} placeholder(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
