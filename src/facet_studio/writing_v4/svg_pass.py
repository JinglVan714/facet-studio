"""Render writer/editor SVG placeholders into clean, deterministic diagrams.

The writer never writes SVG. It leaves:
    <!-- svg: 三层分类：A / B / C -->

This pass asks the model for a small diagram *spec* (JSON), then renders the
SVG locally.  The split keeps diagram geometry deterministic and testable.

Usage:
    PYTHONPATH=src python -m facet_studio.writing_v4.svg_pass \
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
ALLOWED_KINDS = {
    "flow",
    "stack",
    "two-axis",
    "compare",
    "tree",
    "timeline",
    "matrix",
    "cards",
    "cause",
}

SPEC_SYSTEM = """你是图表编辑。根据文章上下文和占位符描述，返回一个 JSON 图表规格；不要返回 SVG。

允许的 kind：
- "flow"：2–4 个顺序步骤，用方框和箭头。
- "stack"：2–4 层，用纵向层。
- "two-axis"：两条刻度/尺子对比（只用于同一量纲的刻度）。
- "compare"：2 个对象的并列对比，左右两张卡片。
- "tree"：2–4 个层级/分类；items[0] 是根，其余是子项。
- "timeline"：2–4 个时间点/阶段，横向时间线。
- "matrix"：2–4 个项放 2×2/网格（优先 4 个），用于四象限/多维归类。
- "cards"：2–4 张并列的观点/摘要卡，不画箭头。
- "cause"：2–4 步因果链，纵向箭头。

字段：
{"kind":"flow|stack|two-axis|compare|tree|timeline|matrix|cards|cause","title":"...","items":[{"label":"...","detail":"..."}],"caption":"..."}

要求：2–4 个 items；label ≤ 8 个汉字，detail ≤ 24 个汉字（太长会被截断）；如果占位符有更多步骤/层，先合并成 4 个阶段，不要丢关键动作；label/detail 只使用文章或占位符里出现的词；不引入新数字、事实或结论；caption 只进报告，不渲染成图注。
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
    truncated = len(cleaned) - 4 if len(cleaned) > 4 else 0
    title = _clean_text(raw.get("title"), "示意")
    caption = _clean_text(raw.get("caption"), title)
    if not caption.startswith("示意"):
        caption = "示意：" + caption
    return {
        "kind": kind,
        "title": title,
        "items": cleaned[:4],
        "caption": caption,
        "truncated": truncated,
    }


def _wrap(text: str, width: int = 16, max_lines: int = 2) -> list[str]:
    text = _clean_text(text)
    if not text:
        return []
    lines: list[str] = []
    remaining = text
    while remaining and len(lines) < max_lines:
        if len(remaining) <= width:
            lines.append(remaining)
            remaining = ""
            break
        cut = width
        # Prefer a punctuation break near the edge instead of cutting a
        # Chinese phrase in half.
        for index in range(width, max(width - 6, 0), -1):
            if remaining[index - 1] in "，。；：、,.;: ":
                cut = index
                break
        lines.append(remaining[:cut])
        remaining = remaining[cut:]
    if remaining:
        lines[-1] = lines[-1][: max(0, width - 1)] + "…"
    return lines


def _svg_open(title: str, height: int = 210) -> str:
    return (
        f'<svg viewBox="0 0 720 {height}" xmlns="http://www.w3.org/2000/svg" '
        'role="img" aria-label="' + html.escape(title, quote=True) + '">\n'
        "<title>" + html.escape(title) + "</title>\n"
        '<g font-family="system-ui, -apple-system, \'Segoe UI\', \'Microsoft YaHei\', sans-serif">\n'
        '<text x="700" y="14" text-anchor="end" font-size="11" fill="#8A847A">示意</text>\n'
    )


def render_flow(spec: dict[str, Any]) -> str:
    items = spec["items"]
    n = len(items)
    margin = 20
    gap = 16
    box_w = (720 - margin * 2 - gap * (n - 1)) / n
    box_h = 132
    parts = [
        _svg_open(spec["title"], 180),
        '<defs><marker id="arrow" viewBox="0 0 10 10" '
        'markerUnits="userSpaceOnUse" markerWidth="8" markerHeight="8" refX="8" refY="4" orient="auto-start-reverse">'
        '<path d="M 0 0 L 8 4 L 0 8 z" fill="#5A554E"/></marker></defs>\n',
    ]
    fills = ["#F4F3EE", "#EEEDE6", "#F6E7D8", "#EEEDE6"]
    strokes = ["#D8D3C8", "#D8D3C8", "#D8D3C8", "#D8D3C8"]
    for index, item in enumerate(items):
        x = margin + index * (box_w + gap)
        parts.append(
            f'<rect x="{x:.1f}" y="30" width="{box_w:.1f}" height="{box_h}" rx="14" '
            f'fill="{fills[index % len(fills)]}" stroke="{strokes[index % len(strokes)]}"/>\n'
        )
        cx = x + box_w / 2
        parts.append(
            f'<text x="{cx:.1f}" y="70" text-anchor="middle" font-size="20" '
            f'font-weight="700" fill="#191817">{html.escape(item["label"])}</text>\n'
        )
        lines = _wrap(item["detail"], width=max(10, int(box_w / 14)), max_lines=2)
        for line_index, line in enumerate(lines):
            parts.append(
                f'<text x="{cx:.1f}" y="{104 + line_index * 23}" text-anchor="middle" '
                f'font-size="14" fill="#5A554E">{html.escape(line)}</text>\n'
            )
        if index < n - 1:
            ax = x + box_w + 1
            parts.append(
                f'<line x1="{ax + 2:.1f}" y1="104" x2="{ax + gap - 4:.1f}" y2="104" '
                'stroke="#5A554E" stroke-width="2" marker-end="url(#arrow)"/>\n'
            )
    parts.append("</g>\n</svg>\n")
    return "".join(parts)


def render_stack(spec: dict[str, Any]) -> str:
    items = spec["items"][:4]
    row_h = 48
    top = 24
    parts = [_svg_open(spec["title"], 240)]
    for index, item in enumerate(items):
        y = top + index * (row_h + 8)
        parts.append(
            f'<rect x="20" y="{y}" width="680" height="{row_h}" rx="10" '
            'fill="#FAF9F5" stroke="#D8D3C8"/>\n'
        )
        parts.append(
            f'<text x="36" y="{y + 30}" font-size="18" font-weight="700" fill="#191817">'
            f'{html.escape(item["label"])}</text>\n'
        )
        if item["detail"]:
            lines = _wrap(item["detail"], width=48, max_lines=1)
            parts.append(
                f'<text x="250" y="{y + 30}" font-size="14" fill="#5A554E">'
                f'{html.escape(lines[0] if lines else item["detail"])}</text>\n'
            )
    parts.append("</g>\n</svg>\n")
    return "".join(parts)


def render_two_axis(spec: dict[str, Any]) -> str:
    items = spec["items"][:2]
    parts = [_svg_open(spec["title"], 220)]
    for index, item in enumerate(items):
        y = 64 + index * 72
        parts.append(
            f'<text x="24" y="{y - 12}" font-size="14" font-weight="700" fill="#191817">'
            f'{html.escape(item["label"])}</text>\n'
        )
        if item["detail"]:
            parts.append(
                f'<text x="24" y="{y + 8}" font-size="12" fill="#5A554E">'
                f'{html.escape(item["detail"])}</text>\n'
            )
        parts.append(
            f'<line x1="170" y1="{y}" x2="660" y2="{y}" stroke="#D8D3C8" stroke-width="2"/>\n'
        )
        for tick in (0.25, 0.5, 0.75):
            x = 170 + tick * 490
            parts.append(
                f'<line x1="{x:.1f}" y1="{y - 6}" x2="{x:.1f}" y2="{y + 6}" '
                'stroke="#8A847A" stroke-width="1.5"/>\n'
            )
    parts.append("</g>\n</svg>\n")
    return "".join(parts)


def render_compare(spec: dict[str, Any]) -> str:
    items = spec["items"][:2]
    n = len(items)
    margin = 20
    gap = 16
    box_w = (720 - margin * 2 - gap * (n - 1)) / n
    parts = [_svg_open(spec["title"], 190)]
    fills = ["#F4F3EE", "#F6E7D8"]
    strokes = ["#D8D3C8", "#D8D3C8"]
    for index, item in enumerate(items):
        x = margin + index * (box_w + gap)
        parts.append(
            f'<rect x="{x:.1f}" y="32" width="{box_w:.1f}" height="140" rx="14" '
            f'fill="{fills[index % 2]}" stroke="{strokes[index % 2]}"/>\n'
        )
        cx = x + box_w / 2
        parts.append(
            f'<text x="{cx:.1f}" y="74" text-anchor="middle" font-size="21" '
            f'font-weight="700" fill="#191817">{html.escape(item["label"])}</text>\n'
        )
        lines = _wrap(item["detail"], width=max(12, int(box_w / 14)), max_lines=3)
        for line_index, line in enumerate(lines):
            parts.append(
                f'<text x="{cx:.1f}" y="{110 + line_index * 23}" text-anchor="middle" '
                f'font-size="14" fill="#5A554E">{html.escape(line)}</text>\n'
            )
    parts.append(
        f'<line x1="{margin + box_w + gap / 2:.1f}" y1="46" '
        f'x2="{margin + box_w + gap / 2:.1f}" y2="160" stroke="#D8D3C8" stroke-width="2"/>\n'
    )
    parts.append("</g>\n</svg>\n")
    return "".join(parts)


def render_tree(spec: dict[str, Any]) -> str:
    items = spec["items"][:4]
    root = items[0]
    children = items[1:] or [root]
    parts = [_svg_open(spec["title"], 220)]
    root_w, root_h = 260, 54
    root_x = (720 - root_w) / 2
    parts.append(
        f'<rect x="{root_x:.1f}" y="14" width="{root_w}" height="{root_h}" rx="12" '
        'fill="#F4F3EE" stroke="#D8D3C8"/>\n'
    )
    parts.append(
        f'<text x="360" y="47" text-anchor="middle" font-size="18" '
        f'font-weight="700" fill="#191817">{html.escape(root["label"])}</text>\n'
    )
    n = len(children)
    margin, gap = 24, 12
    child_w = (720 - margin * 2 - gap * (n - 1)) / n
    child_y, child_h = 128, 76
    for index, item in enumerate(children):
        x = margin + index * (child_w + gap)
        cx = x + child_w / 2
        parts.append(
            f'<line x1="360" y1="{14 + root_h}" x2="{cx:.1f}" y2="{child_y}" '
            'stroke="#8A847A" stroke-width="2"/>\n'
        )
        parts.append(
            f'<rect x="{x:.1f}" y="{child_y}" width="{child_w:.1f}" height="{child_h}" '
            'rx="10" fill="#FAF9F5" stroke="#D8D3C8"/>\n'
        )
        parts.append(
            f'<text x="{cx:.1f}" y="{child_y + 26}" text-anchor="middle" '
            f'font-size="15" font-weight="700" fill="#191817">'
            f'{html.escape(item["label"])}</text>\n'
        )
        lines = _wrap(item["detail"], width=max(10, int(child_w / 14)), max_lines=2)
        for line_index, line in enumerate(lines):
            parts.append(
                f'<text x="{cx:.1f}" y="{child_y + 48 + line_index * 18}" '
                f'text-anchor="middle" font-size="12" fill="#5A554E">'
                f'{html.escape(line)}</text>\n'
            )
    parts.append("</g>\n</svg>\n")
    return "".join(parts)


def render_timeline(spec: dict[str, Any]) -> str:
    items = spec["items"][:4]
    parts = [_svg_open(spec["title"], 220)]
    n = len(items)
    margin = 54
    step = (720 - margin * 2) / (n - 1) if n > 1 else 0
    y = 108
    parts.append(
        f'<line x1="{margin}" y1="{y}" x2="{720 - margin}" y2="{y}" '
        'stroke="#D8D3C8" stroke-width="3"/>\n'
    )
    for index, item in enumerate(items):
        x = margin + index * step
        parts.append(
            f'<circle cx="{x:.1f}" cy="{y}" r="7" fill="#c96442"/>\n'
        )
        lines = _wrap(item["label"], width=14, max_lines=2)
        for line_index, line in enumerate(lines):
            parts.append(
                f'<text x="{x:.1f}" y="{30 + line_index * 18}" text-anchor="middle" '
                f'font-size="17" font-weight="700" fill="#191817">'
                f'{html.escape(line)}</text>\n'
            )
        detail_lines = _wrap(item["detail"], width=18, max_lines=2)
        for line_index, line in enumerate(detail_lines):
            parts.append(
                f'<text x="{x:.1f}" y="{y + 30 + line_index * 18}" '
                f'text-anchor="middle" font-size="12" fill="#5A554E">'
                f'{html.escape(line)}</text>\n'
            )
    parts.append("</g>\n</svg>\n")
    return "".join(parts)


def render_matrix(spec: dict[str, Any]) -> str:
    items = spec["items"][:4]
    parts = [_svg_open(spec["title"], 210)]
    margin, gap = 24, 12
    box_w = (720 - margin * 2 - gap) / 2
    box_h = 74
    for index, item in enumerate(items):
        x = margin + (index % 2) * (box_w + gap)
        y = 28 + (index // 2) * (box_h + gap)
        parts.append(
            f'<rect x="{x:.1f}" y="{y}" width="{box_w:.1f}" height="{box_h}" '
            'rx="10" fill="#FAF9F5" stroke="#D8D3C8"/>\n'
        )
        cx = x + box_w / 2
        parts.append(
            f'<text x="{cx:.1f}" y="{y + 26}" text-anchor="middle" '
            f'font-size="15" font-weight="700" fill="#191817">'
            f'{html.escape(item["label"])}</text>\n'
        )
        lines = _wrap(item["detail"], width=max(12, int(box_w / 16)), max_lines=2)
        for line_index, line in enumerate(lines):
            parts.append(
                f'<text x="{cx:.1f}" y="{y + 49 + line_index * 17}" '
                f'text-anchor="middle" font-size="12" fill="#5A554E">'
                f'{html.escape(line)}</text>\n'
            )
    parts.append("</g>\n</svg>\n")
    return "".join(parts)


def render_cards(spec: dict[str, Any]) -> str:
    items = spec["items"][:4]
    parts = [_svg_open(spec["title"], 200)]
    n = len(items)
    margin, gap = 20, 12
    box_w = (720 - margin * 2 - gap * (n - 1)) / n
    box_h = 146
    for index, item in enumerate(items):
        x = margin + index * (box_w + gap)
        parts.append(
            f'<rect x="{x:.1f}" y="28" width="{box_w:.1f}" height="{box_h}" '
            'rx="12" fill="#FAF9F5" stroke="#D8D3C8"/>\n'
        )
        cx = x + box_w / 2
        parts.append(
            f'<text x="{cx:.1f}" y="60" text-anchor="middle" '
            f'font-size="16" font-weight="700" fill="#191817">'
            f'{html.escape(item["label"])}</text>\n'
        )
        lines = _wrap(item["detail"], width=max(10, int(box_w / 14)), max_lines=3)
        for line_index, line in enumerate(lines):
            parts.append(
                f'<text x="{cx:.1f}" y="{88 + line_index * 20}" '
                f'text-anchor="middle" font-size="12" fill="#5A554E">'
                f'{html.escape(line)}</text>\n'
            )
    parts.append("</g>\n</svg>\n")
    return "".join(parts)


def render_cause(spec: dict[str, Any]) -> str:
    items = spec["items"][:4]
    parts = [
        _svg_open(spec["title"], 232),
        '<defs><marker id="arrow" viewBox="0 0 10 10" '
        'markerUnits="userSpaceOnUse" markerWidth="8" markerHeight="8" refX="8" refY="4" orient="auto-start-reverse">'
        '<path d="M 0 0 L 8 4 L 0 8 z" fill="#5A554E"/></marker></defs>\n',
    ]
    top, row_h, gap = 18, 44, 10
    for index, item in enumerate(items):
        y = top + index * (row_h + gap)
        parts.append(
            f'<rect x="20" y="{y}" width="680" height="{row_h}" rx="9" '
            'fill="#FAF9F5" stroke="#D8D3C8"/>\n'
        )
        parts.append(
            f'<text x="36" y="{y + 27}" font-size="16" font-weight="700" '
            f'fill="#191817">{html.escape(item["label"])}</text>\n'
        )
        if item["detail"]:
            lines = _wrap(item["detail"], width=38, max_lines=1)
            parts.append(
                f'<text x="220" y="{y + 27}" font-size="14" fill="#5A554E">'
                f'{html.escape(lines[0] if lines else item["detail"])}</text>\n'
            )
        if index < len(items) - 1:
            parts.append(
                f'<line x1="360" y1="{y + row_h + 1}" x2="360" y2="{y + row_h + gap - 3}" '
                'stroke="#5A554E" stroke-width="2" marker-end="url(#arrow)"/>\n'
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
    if spec["kind"] == "tree":
        return render_tree(spec)
    if spec["kind"] == "timeline":
        return render_timeline(spec)
    if spec["kind"] == "matrix":
        return render_matrix(spec)
    if spec["kind"] == "cards":
        return render_cards(spec)
    if spec["kind"] == "cause":
        return render_cause(spec)
    return render_flow(spec)


def _context(article: str, start: int, end: int, width: int = 700) -> str:
    left = article[max(0, start - width) : start]
    right = article[end : end + width]
    return left + "\n...[占位符]...\n" + right


def build_svg_assets(
    article: str,
    *,
    client,  # noqa: ANN001 - provider boundary; injected for tests
    key_prefix: str,
    max_placeholders: int = 2,
) -> tuple[str, str, list[dict[str, str]]]:
    """Replace placeholders and return ``(article, report, assets)``.

    Assets are returned as dicts with ``filename``/``svg``/``caption``; the
    caller writes them (and can register them in the run store).  A failed
    spec is reported and the placeholder is removed, never rendered as fake
    content.
    """
    matches = list(PLACEHOLDER.finditer(article))
    if not matches:
        return article, "无 SVG 占位符。\n", []

    report: list[str] = ["# SVG pass\n"]
    replacements: list[tuple[int, int, str]] = []
    assets: list[dict[str, str]] = []
    for index, match in enumerate(matches[:max_placeholders], start=1):
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
                stage=f"{key_prefix}_svg_spec",
                key=f"{key_prefix}:svg:{index}",
                system=SPEC_SYSTEM,
                user=user,
                max_tokens=4096,
                temperature=0.0,
            )
            spec = normalize_spec(_extract_json(response.text))
            svg = render_svg(spec)
            filename = f"svg-{index:02d}.svg"
            assets.append(
                {"filename": filename, "svg": svg, "caption": spec["caption"]}
            )
            # Captions are optional in the product; the SVG carries its own
            # title/labels, so do not add a Markdown caption.
            replacement = f"![](figures/{filename})"
            replacements.append((match.start(), match.end(), replacement))
            report.append(
                f"## {index}. {brief}\n\n- kind: {spec['kind']}\n"
                f"- file: figures/{filename}\n- caption: {spec['caption']}\n"
                + (
                    f"- warning: {spec['truncated']} item(s) grouped/truncated "
                    "to keep the diagram readable; check the labels.\n"
                    if spec.get("truncated")
                    else ""
                )
            )
        except Exception as exc:  # noqa: BLE001 - report and skip
            report.append(f"## {index}. {brief}\n\n- skipped: {exc}\n")
            replacements.append((match.start(), match.end(), ""))

    for match in matches[max_placeholders:]:
        report.append(
            f"## 超过上限\n\n{match.group(1).strip()}\n\n"
            f"- skipped: max {max_placeholders}/篇\n"
        )
        replacements.append((match.start(), match.end(), ""))

    # Replace from the end so offsets stay valid.
    for start, end, replacement in sorted(replacements, reverse=True):
        article = article[:start] + replacement + article[end:]
    return article, "\n".join(report) + "\n", assets


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
    if not PLACEHOLDER.search(article):
        args.out_article.write_text(article, encoding="utf-8")
        args.out_report.write_text("无 SVG 占位符。\n", encoding="utf-8")
        print("no svg placeholders")
        return 0

    settings = get_settings()
    if not settings.provider_configured:
        raise SystemExit("provider not configured")
    client = DeepSeekLLM(settings)
    new_article, report, assets = build_svg_assets(
        article,
        client=client,
        key_prefix=str(args.article),
        max_placeholders=args.max,
    )
    figures_dir = args.out_article.parent / "figures"
    figures_dir.mkdir(parents=True, exist_ok=True)
    for asset in assets:
        (figures_dir / asset["filename"]).write_text(asset["svg"], encoding="utf-8")
    args.out_article.write_text(new_article, encoding="utf-8")
    args.out_report.write_text(report, encoding="utf-8")
    print(f"rendered {len(assets)} placeholder(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
