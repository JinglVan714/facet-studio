"""Deterministic rendering for table/chart/diagram/real-frame visuals.

No model call.  Charts and diagrams are rendered as clean SVG so the writer
layer has real images without an extra plotting dependency; a later adapter
can swap in Mermaid/Graphviz/matplotlib without changing the plan.

Layout rules are deliberately conservative:

* labels are measured and wrapped, never truncated to a fixed character count;
* diagrams use a layered DAG layout (or a small tidy tree) so edges do not run
  through boxes;
* charts use horizontal bars with wrapped labels and a readable value scale.
"""

from __future__ import annotations

import math
import re
import shutil
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

from .sections import join_article, split_article

SVG_HEADER = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
    'viewBox="0 0 {width} {height}">'
)
FONT = "font-family='Noto Sans CJK SC, Microsoft YaHei, PingFang SC, sans-serif'"
COLORS = ["#2f6fed", "#37a36e", "#d97706", "#8b5cf6", "#e11d48", "#0891b2"]
NODE_FILL = "#f8fafc"
NODE_STROKE = "#cbd5e1"
SOURCE_FILL = "#eef2ff"
SOURCE_STROKE = "#6366f1"
SINK_FILL = "#ecfdf5"
SINK_STROKE = "#10b981"
TEXT_COLOR = "#1f2937"
MUTED = "#6b7280"


def _text_width(text: str, size: float) -> float:
    width = 0.0
    for char in str(text):
        if char.isspace():
            width += size * 0.32
        elif ord(char) > 0x2E7F:
            width += size
        elif char in "ilI.,:;'|!`":
            width += size * 0.3
        elif char in "mwMW@%":
            width += size * 0.9
        else:
            width += size * 0.56
    return width


def _ellipsis(text: str, max_width: float, size: float) -> str:
    if _text_width(text + "…", size) <= max_width:
        return text + "…"
    while text and _text_width(text + "…", size) > max_width:
        text = text[:-1]
    return text + "…" if text else "…"


def _wrap_text(
    text: Any,
    max_width: float,
    size: float = 15,
    max_lines: int = 4,
) -> list[str]:
    """Wrap CJK/Latin text by measured width instead of character count."""
    value = str(text or "").strip()
    if not value:
        return [""]
    lines: list[str] = []
    for paragraph in value.splitlines() or [value]:
        tokens = re.findall(
            r"“[^”]*”|「[^」]*」|『[^』]*』|\"[^\"]*\"|"
            r"[A-Za-z0-9_./%+\-]+|\s+|.",
            paragraph,
        )
        current = ""
        for token in tokens:
            if token.isspace() and not current:
                continue
            candidate = current + token
            if not current or _text_width(candidate, size) <= max_width:
                current = candidate
                continue
            lines.append(current.strip())
            current = token.lstrip()
            while current and _text_width(current, size) > max_width:
                cut = len(current)
                while cut > 1 and _text_width(current[:cut], size) > max_width:
                    cut -= 1
                lines.append(current[:cut].strip())
                current = current[cut:].lstrip()
        if current.strip():
            lines.append(current.strip())
    lines = [line for line in lines if line]
    if not lines:
        return [""]
    # Do not start a line with closing punctuation or end one with an opener.
    closing = "，。；：、！？）》」』”’%,.;:!?)]}"
    opening = "（《「『“‘([{"
    for index in range(1, len(lines)):
        while lines[index] and lines[index][0] in closing:
            if _text_width(lines[index - 1] + lines[index][0], size) > max_width:
                break
            lines[index - 1] += lines[index][0]
            lines[index] = lines[index][1:]
    for index in range(1, len(lines)):
        while lines[index - 1] and lines[index - 1][-1] in opening:
            if _text_width(lines[index - 1][-1] + lines[index], size) > max_width:
                break
            lines[index] = lines[index - 1][-1] + lines[index]
            lines[index - 1] = lines[index - 1][:-1]
    lines = [line for line in lines if line]
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = _ellipsis(lines[-1], max_width, size)
    return lines


def _text_lines(
    lines: list[str],
    *,
    x: float,
    center_y: float,
    size: float,
    fill: str,
    anchor: str = "middle",
    weight: str = "normal",
) -> list[str]:
    line_height = size * 1.35
    start = center_y - (len(lines) - 1) * line_height / 2
    parts = []
    for index, line in enumerate(lines):
        y = start + index * line_height + size * 0.35
        parts.append(
            f"<text x='{x:.1f}' y='{y:.1f}' text-anchor='{anchor}' "
            f"{FONT} font-size='{size:g}' font-weight='{weight}' "
            f"fill='{fill}'>{escape(line)}</text>"
        )
    return parts


def _format_value(value: float, step: float = 1.0) -> str:
    """Format a tick with just enough decimals for the chosen step."""
    if abs(value) >= 10000:
        return f"{value:,.0f}"
    for decimals in range(0, 5):
        rendered = f"{value:.{decimals}f}"
        if abs(float(rendered) - value) <= step * 1e-6:
            return rendered
    return f"{value:.4f}"


def _nice_ticks(low: float, high: float, count: int = 4) -> list[float]:
    if high <= low:
        high = low + 1
    raw_step = (high - low) / max(count, 1)
    exponent = math.floor(math.log10(raw_step)) if raw_step > 0 else 0
    fraction = raw_step / (10**exponent)
    if fraction <= 1:
        nice_fraction = 1.0
    elif fraction <= 2:
        nice_fraction = 2.0
    elif fraction <= 2.5:
        nice_fraction = 2.5
    elif fraction <= 5:
        nice_fraction = 5.0
    else:
        nice_fraction = 10.0
    step = nice_fraction * (10**exponent)
    start = math.ceil(low / step) * step
    end = math.floor(high / step) * step
    ticks = []
    value = start
    guard = 0
    while value <= end + step * 1e-6 and guard < 50:
        ticks.append(round(value, 10))
        value += step
        guard += 1
    return ticks or [low, high]


def _bar_chart_svg(spec: dict[str, Any]) -> str | None:
    data = spec.get("data") or []
    values: list[tuple[str, float, str]] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        raw = str(item.get("value", "")).strip()
        try:
            number = float(raw.rstrip("%"))
        except ValueError:
            continue
        values.append((str(item.get("label", "")), number, raw))
    if not values:
        return None

    title = str(spec.get("title", "")).strip()
    unit = str(spec.get("unit", "") or "").strip()
    width = 780
    margin = 28
    title_lines = _wrap_text(title, width - margin * 2, 18, 2) if title else []
    title_h = 30 + (len(title_lines) - 1) * 24 if title_lines else 8

    label_size = 13
    label_max = 210
    wrapped_labels = [
        _wrap_text(label, label_max, label_size, 2) for label, _, _ in values
    ]
    label_width = max(
        (_text_width(max(lines, key=lambda line: _text_width(line, label_size)), label_size)
         for lines in wrapped_labels),
        default=80,
    )
    label_width = max(70, min(label_max, label_width))
    left = margin + label_width + 14
    right = width - margin - 64
    plot_w = max(120, right - left)

    row_heights = [max(36, len(lines) * 18 + 18) for lines in wrapped_labels]
    bottom = 42
    height = int(title_h + sum(row_heights) + bottom + 12)
    max_value = max(value for _, value, _ in values)
    min_value = min(0.0, min(value for _, value, _ in values))
    if max_value == min_value:
        max_value = min_value + 1
    span = max_value - min_value
    plot_left = left + (0 - min_value) / span * plot_w
    plot_right = left + (max_value - min_value) / span * plot_w
    zero_x = left + (0 - min_value) / span * plot_w

    parts = [
        SVG_HEADER.format(width=width, height=height),
        "<rect width='100%' height='100%' fill='#ffffff'/>",
    ]
    for index, line in enumerate(title_lines):
        parts.append(
            f"<text x='{margin}' y='{28 + index * 24}' {FONT} font-size='18' "
            f"font-weight='bold' fill='#111827'>{escape(line)}</text>"
        )
    if unit:
        parts.append(
            f"<text x='{width - margin}' y='{28}' text-anchor='end' {FONT} "
            f"font-size='12' fill='{MUTED}'>单位：{escape(unit)}</text>"
        )

    ticks = _nice_ticks(min_value, max_value, 4)
    tick_step = ticks[1] - ticks[0] if len(ticks) > 1 else 1
    for tick in ticks:
        if tick < min_value - 1e-9 or tick > max_value + 1e-9:
            continue
        tick_x = left + (tick - min_value) / span * plot_w
        parts.append(
            f"<line x1='{tick_x:.1f}' y1='{title_h:.1f}' x2='{tick_x:.1f}' "
            f"y2='{height - bottom + 4:.1f}' stroke='#e5e7eb' stroke-dasharray='3 4'/>"
        )
        parts.append(
            f"<text x='{tick_x:.1f}' y='{height - bottom + 22:.1f}' text-anchor='middle' "
            f"{FONT} font-size='11' fill='{MUTED}'>{escape(_format_value(tick, tick_step))}</text>"
        )
    parts.append(
        f"<line x1='{plot_left:.1f}' y1='{height - bottom + 4:.1f}' "
        f"x2='{plot_right:.1f}' y2='{height - bottom + 4:.1f}' stroke='#9ca3af'/>"
    )
    parts.append(
        f"<line x1='{zero_x:.1f}' y1='{title_h:.1f}' x2='{zero_x:.1f}' "
        f"y2='{height - bottom + 4:.1f}' stroke='#6b7280'/>"
    )

    y = title_h + 6
    for index, ((label, value, raw), lines) in enumerate(zip(values, wrapped_labels)):
        row_h = row_heights[index]
        center_y = y + row_h / 2
        parts.extend(
            _text_lines(
                lines,
                x=left - 12,
                center_y=center_y,
                size=label_size,
                fill="#374151",
                anchor="end",
            )
        )
        bar_end = left + (value - min_value) / span * plot_w
        x1, x2 = sorted((zero_x, bar_end))
        if x2 - x1 < 2:
            x2 = x1 + 2
        bar_y = center_y - 9
        parts.append(
            f"<rect x='{x1:.1f}' y='{bar_y:.1f}' width='{x2 - x1:.1f}' "
            f"height='18' rx='4' fill='{COLORS[index % len(COLORS)]}'/>"
        )
        value_text = raw if (not unit or raw.endswith(unit)) else raw + unit
        value_x = x2 + 7 if value >= 0 else x1 - 7
        anchor = "start" if value >= 0 else "end"
        parts.append(
            f"<text x='{value_x:.1f}' y='{center_y + 4:.1f}' text-anchor='{anchor}' "
            f"{FONT} font-size='12' font-weight='bold' fill='#111827'>{escape(value_text)}</text>"
        )
        y += row_h
    parts.append("</svg>")
    return "\n".join(parts)


def _line_chart_svg(spec: dict[str, Any]) -> str | None:
    data = spec.get("data") or []
    values: list[tuple[str, float]] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        raw = str(item.get("value", "")).strip()
        try:
            values.append((str(item.get("label", "")), float(raw.rstrip("%"))))
        except ValueError:
            continue
    if not values:
        return None

    title = str(spec.get("title", "")).strip()
    width, height = 780, 380
    margin, left, right, top, bottom = 28, 58, 28, 60, 72
    plot_w = width - left - right
    plot_h = height - top - bottom
    max_value = max(value for _, value in values)
    min_value = min(0.0, min(value for _, value in values))
    span = max(max_value - min_value, 1e-9)
    ticks = _nice_ticks(min_value, max_value, 4)
    tick_step = ticks[1] - ticks[0] if len(ticks) > 1 else 1
    title_lines = _wrap_text(title, width - margin * 2, 18, 2) if title else []

    parts = [
        SVG_HEADER.format(width=width, height=height),
        "<rect width='100%' height='100%' fill='#ffffff'/>",
    ]
    for index, line in enumerate(title_lines):
        parts.append(
            f"<text x='{margin}' y='{28 + index * 24}' {FONT} font-size='18' "
            f"font-weight='bold' fill='#111827'>{escape(line)}</text>"
        )
    for tick in ticks:
        if tick < min_value - 1e-9 or tick > max_value + 1e-9:
            continue
        y = top + (max_value - tick) / span * plot_h
        parts.append(
            f"<line x1='{left}' y1='{y:.1f}' x2='{width - right}' y2='{y:.1f}' "
            f"stroke='#e5e7eb' stroke-dasharray='3 4'/>"
        )
        parts.append(
            f"<text x='{left - 10}' y='{y + 4:.1f}' text-anchor='end' {FONT} "
            f"font-size='11' fill='{MUTED}'>{escape(_format_value(tick, tick_step))}</text>"
        )
    zero_y = top + (max_value - 0) / span * plot_h
    parts.append(
        f"<line x1='{left}' y1='{zero_y:.1f}' x2='{width - right}' y2='{zero_y:.1f}' "
        f"stroke='#9ca3af'/>"
    )
    step_x = plot_w / max(len(values) - 1, 1)
    points = []
    for index, (label, value) in enumerate(values):
        x = left + index * step_x
        y = top + (max_value - value) / span * plot_h
        points.append((x, y))
    path = " ".join(
        ("M" if index == 0 else "L") + f"{x:.1f},{y:.1f}"
        for index, (x, y) in enumerate(points)
    )
    parts.append(
        f"<path d='{path}' fill='none' stroke='{COLORS[0]}' stroke-width='3' "
        "stroke-linejoin='round' stroke-linecap='round'/>"
    )
    label_width = max(step_x - 8, 40)
    for index, ((label, value), (x, y)) in enumerate(zip(values, points)):
        parts.append(
            f"<circle cx='{x:.1f}' cy='{y:.1f}' r='5' fill='#ffffff' "
            f"stroke='{COLORS[0]}' stroke-width='3'/>"
        )
        parts.append(
            f"<text x='{x:.1f}' y='{y - 12:.1f}' text-anchor='middle' {FONT} "
            f"font-size='12' font-weight='bold' fill='#111827'>{escape(str(value))}</text>"
        )
        for line_index, line in enumerate(_wrap_text(label, label_width, 11, 2)):
            parts.append(
                f"<text x='{x:.1f}' y='{height - bottom + 18 + line_index * 14:.1f}' "
                f"text-anchor='middle' {FONT} font-size='11' fill='#374151'>{escape(line)}</text>"
            )
    parts.append("</svg>")
    return "\n".join(parts)


def _chart_svg(spec: dict[str, Any]) -> str | None:
    if str(spec.get("type", "bar")).lower() == "line":
        return _line_chart_svg(spec)
    return _bar_chart_svg(spec)


def _short_edge_label(value: Any, limit: int = 18) -> str:
    """Edge labels are arrows, not paragraphs; keep them terse."""
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    for separator in ("：", ":", "，", ",", "；", ";", "、"):
        head = text.split(separator, 1)[0].strip()
        if 4 <= len(head) <= limit:
            return head
    return text[: limit - 1].rstrip("，,、；;：: ") + "…"


def _clean_graph(spec: dict[str, Any]) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    nodes: list[dict[str, str]] = []
    seen: set[str] = set()
    for raw in spec.get("nodes") or []:
        if not isinstance(raw, dict):
            continue
        node_id = str(raw.get("id", "")).strip()
        label = str(raw.get("label", "")).strip()
        if not node_id or not label or node_id in seen:
            continue
        nodes.append({"id": node_id, "label": label})
        seen.add(node_id)
    edges: list[dict[str, str]] = []
    seen_edges: set[tuple[str, str]] = set()
    for raw in spec.get("edges") or []:
        if not isinstance(raw, dict):
            continue
        start = str(raw.get("from", "")).strip()
        end = str(raw.get("to", "")).strip()
        if start not in seen or end not in seen or start == end:
            continue
        key = (start, end)
        if key in seen_edges:
            continue
        seen_edges.add(key)
        edges.append(
            {
                "from": start,
                "to": end,
                "label": _short_edge_label(raw.get("label", "")),
            }
        )
    return nodes, edges


def _layered_ranks(
    node_ids: list[str], edges: list[dict[str, str]]
) -> dict[str, int]:
    """Longest-path ranks, with source nodes pulled next to their consumers."""
    outgoing: dict[str, list[str]] = {node_id: [] for node_id in node_ids}
    incoming: dict[str, int] = {node_id: 0 for node_id in node_ids}
    for edge in edges:
        outgoing[edge["from"]].append(edge["to"])
        incoming[edge["to"]] += 1
    rank = {node_id: 0 for node_id in node_ids}
    queue = [node_id for node_id in node_ids if incoming[node_id] == 0]
    processed: list[str] = []
    while queue:
        current = queue.pop(0)
        processed.append(current)
        for target in outgoing[current]:
            rank[target] = max(rank[target], rank[current] + 1)
            incoming[target] -= 1
            if incoming[target] == 0:
                queue.append(target)
    if len(processed) < len(node_ids):
        # Cycle: keep the graph drawable by appending unresolved nodes.
        base = max(rank.values(), default=0) + 1
        unresolved = [node_id for node_id in node_ids if node_id not in processed]
        for offset, node_id in enumerate(unresolved):
            rank[node_id] = base + offset
    sources = {
        node_id for node_id in node_ids if not any(
            edge["to"] == node_id for edge in edges
        )
    }
    for node_id in node_ids:
        if node_id in sources and outgoing[node_id]:
            target_rank = min(rank[target] for target in outgoing[node_id])
            rank[node_id] = max(0, target_rank - 1)
    used = sorted(set(rank.values()))
    compact = {value: index for index, value in enumerate(used)}
    return {node_id: compact[rank[node_id]] for node_id in node_ids}


def _tree_layout(
    node_ids: list[str], edges: list[dict[str, str]]
) -> tuple[str, dict[str, int], dict[str, list[str]]] | None:
    """Return (root, depth, children) for a small branching tree, else None."""
    incoming = {node_id: 0 for node_id in node_ids}
    children: dict[str, list[str]] = {node_id: [] for node_id in node_ids}
    for edge in edges:
        incoming[edge["to"]] += 1
        children[edge["from"]].append(edge["to"])
    if any(count > 1 for count in incoming.values()):
        return None
    roots = [node_id for node_id in node_ids if incoming[node_id] == 0]
    if len(roots) != 1:
        return None
    root = roots[0]
    depth = {root: 0}
    queue = [root]
    while queue:
        current = queue.pop(0)
        for child in children[current]:
            depth[child] = depth[current] + 1
            queue.append(child)
    if len(depth) != len(node_ids):
        return None
    if max((len(items) for items in children.values()), default=0) < 2:
        return None
    if max(depth.values()) > 3:
        return None
    return root, depth, children


def _node_box(
    label: str, *, max_text_width: float, font_size: float = 15
) -> tuple[list[str], float, float]:
    lines = _wrap_text(label, max_text_width, font_size, 4)
    widest = max(_text_width(line, font_size) for line in lines)
    width = max(148, min(300, widest + 34))
    height = max(50, len(lines) * font_size * 1.35 + 22)
    return lines, width, height


def _node_parts(
    *,
    x: float,
    y: float,
    width: float,
    height: float,
    label: str,
    fill: str,
    stroke: str,
) -> list[str]:
    lines = _wrap_text(label, width - 30, 15, 4)
    parts = [
        f"<rect x='{x:.1f}' y='{y:.1f}' width='{width:.1f}' height='{height:.1f}' "
        f"rx='10' fill='{fill}' stroke='{stroke}' stroke-width='1.5'/>",
    ]
    parts.extend(
        _text_lines(
            lines,
            x=x + width / 2,
            center_y=y + height / 2,
            size=15,
            fill=TEXT_COLOR,
        )
    )
    return parts


def _split_back_edges(
    node_ids: list[str], edges: list[dict[str, str]]
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    """Split out DFS back edges so ranking sees a DAG."""
    adjacency: dict[str, list[tuple[int, str]]] = {node_id: [] for node_id in node_ids}
    for index, edge in enumerate(edges):
        adjacency[edge["from"]].append((index, edge["to"]))
    color = {node_id: 0 for node_id in node_ids}
    back: set[int] = set()

    def visit(node_id: str) -> None:
        color[node_id] = 1
        for index, target in adjacency[node_id]:
            if color[target] == 1:
                back.add(index)
            elif color[target] == 0:
                visit(target)
        color[node_id] = 2

    for node_id in node_ids:
        if color[node_id] == 0:
            visit(node_id)
    forward = [edge for index, edge in enumerate(edges) if index not in back]
    backward = [edge for index, edge in enumerate(edges) if index in back]
    return forward, backward


def _label_box(
    x: float, y: float, text: str, anchor: str
) -> tuple[float, float, float, float]:
    width = _text_width(text, 12) + 6
    height = 16
    if anchor == "middle":
        left = x - width / 2
    elif anchor == "end":
        left = x - width
    else:
        left = x
    return left, y - 12, width, height


def _overlaps(
    first: tuple[float, float, float, float],
    second: tuple[float, float, float, float],
) -> bool:
    ax, ay, aw, ah = first
    bx, by, bw, bh = second
    return ax < bx + bw and bx < ax + aw and ay < by + bh and by < ay + ah


def _place_label(
    candidates: list[tuple[float, float, str]],
    occupied: list[tuple[float, float, float, float]],
    text: str,
) -> tuple[float, float, str]:
    for x, y, anchor in candidates:
        box = _label_box(x, y, text, anchor)
        if not any(_overlaps(box, other) for other in occupied):
            occupied.append(box)
            return x, y, anchor
    x, y, anchor = candidates[0]
    occupied.append(_label_box(x, y, text, anchor))
    return x, y, anchor


def _arrow_defs() -> str:
    return (
        "<defs><marker id='arrow' markerWidth='10' markerHeight='10' refX='9' refY='3' "
        "orient='auto'><path d='M0,0 L0,6 L9,3 z' fill='#6b7280'/></marker>"
        "<filter id='soft' x='-20%' y='-20%' width='140%' height='140%'>"
        "<feDropShadow dx='0' dy='1' stdDeviation='1.2' flood-opacity='0.10'/>"
        "</filter></defs>"
    )


def _edge_label(
    x: float, y: float, label: str, *, anchor: str = "middle"
) -> str:
    return (
        f"<text x='{x:.1f}' y='{y:.1f}' text-anchor='{anchor}' {FONT} font-size='12' "
        f"fill='{MUTED}' paint-order='stroke' stroke='#ffffff' stroke-width='4' "
        f"stroke-linejoin='round'>{escape(label)}</text>"
    )


def _flow_dag_svg(
    nodes: list[dict[str, str]], edges: list[dict[str, str]]
) -> str:
    node_ids = [node["id"] for node in nodes]
    labels = {node["id"]: node["label"] for node in nodes}
    forward_edges, back_edges = _split_back_edges(node_ids, edges)
    ranks = _layered_ranks(node_ids, forward_edges)
    groups: dict[int, list[str]] = {}
    for node_id in node_ids:
        groups.setdefault(ranks[node_id], []).append(node_id)

    sizes: dict[str, tuple[list[str], float, float]] = {}
    for node_id in node_ids:
        sizes[node_id] = _node_box(labels[node_id], max_text_width=230)
    rank_gap = 66
    box_gap = 36
    margin_x, margin_y = 36, 30
    rank_widths: dict[int, float] = {}
    rank_heights: dict[int, float] = {}
    for rank, members in groups.items():
        widths = [sizes[node_id][1] for node_id in members]
        heights = [sizes[node_id][2] for node_id in members]
        rank_widths[rank] = sum(widths) + box_gap * (len(members) - 1)
        rank_heights[rank] = max(heights)
    canvas_w = max(720, max(rank_widths.values()) + margin_x * 2)
    rank_y: dict[int, float] = {}
    cursor = margin_y
    for rank in sorted(groups):
        rank_y[rank] = cursor
        cursor += rank_heights[rank] + rank_gap
    canvas_h = cursor - rank_gap + margin_y
    positions: dict[str, tuple[float, float, float, float]] = {}
    for rank, members in groups.items():
        cursor_x = (canvas_w - rank_widths[rank]) / 2
        for node_id in members:
            _, width, height = sizes[node_id]
            y = rank_y[rank] + (rank_heights[rank] - height) / 2
            positions[node_id] = (cursor_x, y, width, height)
            cursor_x += width + box_gap

    outgoing = {node_id: 0 for node_id in node_ids}
    incoming = {node_id: 0 for node_id in node_ids}
    for edge in edges:
        outgoing[edge["from"]] += 1
        incoming[edge["to"]] += 1

    parts = [
        SVG_HEADER.format(width=canvas_w, height=canvas_h),
        _arrow_defs(),
        "<rect width='100%' height='100%' fill='#ffffff'/>",
    ]
    for node_id in node_ids:
        x, y, width, height = positions[node_id]
        if incoming[node_id] == 0:
            fill, stroke = SOURCE_FILL, SOURCE_STROKE
        elif outgoing[node_id] == 0:
            fill, stroke = SINK_FILL, SINK_STROKE
        else:
            fill, stroke = NODE_FILL, NODE_STROKE
        parts.extend(
            _node_parts(
                x=x,
                y=y,
                width=width,
                height=height,
                label=labels[node_id],
                fill=fill,
                stroke=stroke,
            )
        )

    occupied = [
        (x - 2, y - 2, width + 4, height + 4)
        for x, y, width, height in positions.values()
    ]
    label_parts: list[str] = []
    lane = 0

    def add_label(candidates: list[tuple[float, float, str]], text: str) -> None:
        x, y, anchor = _place_label(candidates, occupied, text)
        label_parts.append(_edge_label(x, y, text, anchor=anchor))

    for edge in forward_edges:
        start_id, end_id = edge["from"], edge["to"]
        sx, sy, sw, sh = positions[start_id]
        ex, ey, ew, _ = positions[end_id]
        start_x, start_y = sx + sw / 2, sy + sh
        end_x, end_y = ex + ew / 2, ey
        rank_delta = ranks[end_id] - ranks[start_id]
        if rank_delta == 1:
            control = (end_y - start_y) * 0.55
            path = (
                f"M{start_x:.1f},{start_y:.1f} "
                f"C{start_x:.1f},{start_y + control:.1f} "
                f"{end_x:.1f},{end_y - control:.1f} "
                f"{end_x:.1f},{end_y:.1f}"
            )
            mid = ((start_x + end_x) / 2, (start_y + end_y) / 2)
            candidates = [
                (mid[0], mid[1], "middle"),
                (mid[0], mid[1] - 18, "middle"),
                (mid[0], mid[1] + 18, "middle"),
                (mid[0] - 24, mid[1] - 18, "middle"),
                (mid[0] + 24, mid[1] + 18, "middle"),
            ]
        else:
            lane_x = canvas_w - 16 - lane * 10
            lane += 1
            path = (
                f"M{start_x:.1f},{start_y:.1f} "
                f"L{start_x:.1f},{start_y + 16:.1f} "
                f"Q{start_x:.1f},{start_y + 24:.1f} {lane_x:.1f},{start_y + 24:.1f} "
                f"L{lane_x:.1f},{end_y - 24:.1f} "
                f"Q{lane_x:.1f},{end_y - 16:.1f} {end_x:.1f},{end_y - 16:.1f} "
                f"L{end_x:.1f},{end_y:.1f}"
            )
            mid_y = (start_y + end_y) / 2
            candidates = [
                (lane_x - 6, mid_y, "end"),
                (lane_x - 6, mid_y - 18, "end"),
                (lane_x - 6, mid_y + 18, "end"),
                (lane_x + 6, mid_y, "start"),
            ]
        parts.append(
            f"<path d='{path}' fill='none' stroke='#6b7280' stroke-width='1.8' "
            "stroke-linejoin='round' marker-end='url(#arrow)'/>"
        )
        if edge["label"]:
            add_label(candidates, edge["label"])

    for edge in back_edges:
        sx, sy, sw, sh = positions[edge["from"]]
        ex, ey, ew, eh = positions[edge["to"]]
        start_x, start_y = sx + sw, sy + sh / 2
        end_x, end_y = ex + ew, ey + eh / 2
        lane_x = canvas_w - 16 - lane * 10
        lane += 1
        path = (
            f"M{start_x:.1f},{start_y:.1f} "
            f"L{lane_x - 12:.1f},{start_y:.1f} "
            f"Q{lane_x:.1f},{start_y:.1f} {lane_x:.1f},{start_y + 12:.1f} "
            f"L{lane_x:.1f},{end_y - 12:.1f} "
            f"Q{lane_x:.1f},{end_y:.1f} {lane_x - 12:.1f},{end_y:.1f} "
            f"L{end_x:.1f},{end_y:.1f}"
        )
        mid_y = (start_y + end_y) / 2
        parts.append(
            f"<path d='{path}' fill='none' stroke='#6b7280' stroke-width='1.8' "
            "stroke-linejoin='round' marker-end='url(#arrow)'/>"
        )
        if edge["label"]:
            add_label(
                [
                    (lane_x - 6, mid_y, "end"),
                    (lane_x - 6, mid_y - 18, "end"),
                    (lane_x - 6, mid_y + 18, "end"),
                    (lane_x + 6, mid_y, "start"),
                ],
                edge["label"],
            )

    parts.extend(label_parts)
    parts.append("</svg>")
    return "\n".join(parts)


def _flow_tree_svg(
    nodes: list[dict[str, str]],
    edges: list[dict[str, str]],
    root: str,
    depth: dict[str, int],
    children: dict[str, list[str]],
) -> str:
    labels = {node["id"]: node["label"] for node in nodes}
    max_depth = max(depth.values())
    sizes: dict[str, tuple[list[str], float, float]] = {}
    for node in nodes:
        sizes[node["id"]] = _node_box(node["label"], max_text_width=190)
    col_widths: dict[int, float] = {}
    for node_id, level in depth.items():
        col_widths[level] = max(col_widths.get(level, 0), sizes[node_id][1])
    row_height = max(size[2] for size in sizes.values()) + 20
    margin_x, margin_y = 34, 30
    col_gap = 72
    canvas_w = sum(col_widths.values()) + col_gap * max_depth + margin_x * 2
    canvas_w = max(720, canvas_w)
    # Center the columns inside the canvas.
    col_x: dict[int, float] = {}
    cursor_x = (canvas_w - (sum(col_widths.values()) + col_gap * max_depth)) / 2
    for level in range(max_depth + 1):
        col_x[level] = cursor_x
        cursor_x += col_widths[level] + col_gap

    leaf_y: dict[str, float] = {}
    centers: dict[str, float] = {}
    leaf_cursor = 0

    def place(node_id: str) -> float:
        nonlocal leaf_cursor
        if not children[node_id]:
            center = margin_y + leaf_cursor * row_height + row_height / 2
            leaf_cursor += 1
        else:
            child_centers = [place(child) for child in children[node_id]]
            center = (child_centers[0] + child_centers[-1]) / 2
        centers[node_id] = center
        return center

    place(root)
    canvas_h = max(
        margin_y * 2 + leaf_cursor * row_height,
        margin_y * 2 + row_height,
    )
    positions: dict[str, tuple[float, float, float, float]] = {}
    for node_id, level in depth.items():
        _, width, height = sizes[node_id]
        x = col_x[level] + (col_widths[level] - width) / 2
        y = centers[node_id] - height / 2
        positions[node_id] = (x, y, width, height)

    outgoing = {node_id: 0 for node_id in labels}
    for edge in edges:
        outgoing[edge["from"]] += 1
    parts = [
        SVG_HEADER.format(width=canvas_w, height=canvas_h),
        _arrow_defs(),
        "<rect width='100%' height='100%' fill='#ffffff'/>",
    ]
    for node in nodes:
        node_id = node["id"]
        x, y, width, height = positions[node_id]
        if node_id == root:
            fill, stroke = SOURCE_FILL, SOURCE_STROKE
        elif outgoing[node_id] == 0:
            fill, stroke = SINK_FILL, SINK_STROKE
        else:
            fill, stroke = NODE_FILL, NODE_STROKE
        parts.extend(
            _node_parts(
                x=x,
                y=y,
                width=width,
                height=height,
                label=labels[node_id],
                fill=fill,
                stroke=stroke,
            )
        )
    for edge in edges:
        sx, sy, sw, sh = positions[edge["from"]]
        ex, ey, _, eh = positions[edge["to"]]
        start_x, start_y = sx + sw, sy + sh / 2
        end_x, end_y = ex, ey + eh / 2
        control = (end_x - start_x) * 0.45
        path = (
            f"M{start_x:.1f},{start_y:.1f} "
            f"C{start_x + control:.1f},{start_y:.1f} "
            f"{end_x - control:.1f},{end_y:.1f} "
            f"{end_x:.1f},{end_y:.1f}"
        )
        parts.append(
            f"<path d='{path}' fill='none' stroke='#6b7280' stroke-width='1.8' "
            "marker-end='url(#arrow)'/>"
        )
        if edge["label"]:
            parts.append(
                _edge_label(
                    (start_x + end_x) / 2,
                    (start_y + end_y) / 2 - 6,
                    edge["label"],
                )
            )
    parts.append("</svg>")
    return "\n".join(parts)


def _flow_svg(spec: dict[str, Any]) -> str | None:
    nodes, edges = _clean_graph(spec)
    if not nodes:
        return None
    tree = _tree_layout([node["id"] for node in nodes], edges)
    if tree is not None:
        return _flow_tree_svg(nodes, edges, *tree)
    return _flow_dag_svg(nodes, edges)


def _cell(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ").strip()


def _table_markdown(spec: dict[str, Any]) -> str:
    columns = [_cell(value) for value in spec.get("columns", [])]
    rows = spec.get("rows", [])
    if not columns:
        return ""
    lines = ["| " + " | ".join(columns) + " |", "|" + "|".join(["---"] * len(columns)) + "|"]
    for row in rows:
        values = list(row) + [""] * max(0, len(columns) - len(row))
        lines.append(
            "| " + " | ".join(_cell(value) for value in values[: len(columns)]) + " |"
        )
    return "\n".join(lines)


def _insert_before_last_paragraph(
    lines: list[str], snippet: str
) -> list[str]:
    """Keep the section's closing takeaway after the visual."""
    blocks: list[tuple[int, int]] = []
    start = None
    for index, line in enumerate(lines):
        if line.strip():
            if start is None:
                start = index
        elif start is not None:
            blocks.append((start, index))
            start = None
    if start is not None:
        blocks.append((start, len(lines)))
    if len(blocks) < 2:
        insert_at = len(lines)
    else:
        last_start, last_end = blocks[-1]
        last_text = "\n".join(lines[last_start:last_end]).lstrip()
        # A trailing table is content, not a takeaway; keep it before the visual.
        insert_at = len(lines) if last_text.startswith("|") else last_start
    prefix = [""] if insert_at > 0 and lines[insert_at - 1].strip() else []
    suffix = [""] if insert_at < len(lines) and lines[insert_at].strip() else []
    lines[insert_at:insert_at] = prefix + [snippet] + suffix
    return lines


def _frame_readability(path: Path, caption: str = "") -> dict[str, Any]:
    """Cheap pixel-level gate for real frames, with a caption-aware exception.

    A frame can be technically present but mostly black, washed out, or too
    small to read.  The visual planner sees captions, not pixels, so this is
    the deterministic guard before a frame is inserted.

    Dark-mode slides and UI screenshots are common in technical videos: their
    global non-dark ratio is low even though the text is legible.  When the
    frame has a substantive VLM/OCR caption, allow a lower dark-slide bar; a
    black frame with no caption is still rejected.
    """
    try:
        from PIL import Image, ImageStat
    except ImportError:  # optional: do not block frames when Pillow is absent
        return {"status": "unavailable"}
    try:
        with Image.open(path) as image:
            gray = image.convert("L")
            width, height = gray.size
            sample = gray.resize((160, 90))
            pixels = list(sample.getdata())
            non_dark = sum(1 for value in pixels if value > 50) / max(len(pixels), 1)
            stddev = ImageStat.Stat(sample).stddev[0]
    except Exception:
        return {"status": "unreadable"}
    caption_chars = len(caption.strip())
    ok = width >= 320 and height >= 180 and non_dark >= 0.10 and stddev >= 20
    override = ""
    if (
        not ok
        and caption_chars >= 20
        and width >= 320
        and height >= 180
        and non_dark >= 0.04
        and stddev >= 18
    ):
        ok = True
        override = "caption_dark_slide"
    result = {
        "status": "ok" if ok else "low",
        "width": width,
        "height": height,
        "non_dark": round(non_dark, 3),
        "stddev": round(stddev, 1),
        "caption_chars": caption_chars,
    }
    if override:
        result["override"] = override
    return result


def _caption(kind: str, caption: str, status: str = "unknown") -> str:
    caption = re.sub(r"^\s*(?:看哪里|看这里)\s*[：:]\s*", "", caption).strip()
    lead = "" if caption.startswith("看") else "看哪里："
    if not caption:
        lead, caption = "看哪里：", "看这里"
    if kind == "real_frame":
        return f"*{lead}{caption}*"
    verb = "整理" if kind == "table" else "绘制"
    if status in {"hypothesis", "illustration"}:
        suffix = f"（根据视频中的假设/示意{verb}）"
    elif status == "demo":
        suffix = f"（根据视频中的单次演示{verb}）"
    else:
        suffix = f"（根据视频内容{verb}）"
    return f"*{lead}{caption}{suffix}*"


def render_visual_plan(
    article: str,
    plan: dict[str, Any],
    index: dict[str, Any],
    out_dir: Path,
    *,
    data_root: Path | None = None,
    video_id: str = "",
) -> dict[str, Any]:
    title, sections = split_article(article)
    out_dir = Path(out_dir)
    assets_dir = out_dir / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)
    frames_by_id = {
        frame.get("frame_id", ""): frame for frame in index.get("frames", [])
    }
    by_section: dict[int, list[dict[str, Any]]] = {}
    for visual in plan.get("visuals", []):
        by_section.setdefault(int(visual.get("section_index", 0)), []).append(visual)
    assets: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    rendered = 0
    for section in sections:
        visuals = by_section.get(section["index"], [])
        for visual in visuals:
            kind = visual.get("kind", "")
            caption = str(visual.get("caption", "")).strip() or "看这里"
            status = str(visual.get("status", "unknown")).strip().lower() or "unknown"
            snippet = ""
            source_type = ""
            path = None
            readability: dict[str, Any] | None = None
            if kind == "table":
                section_body = "\n".join(section.get("lines", []))
                if "\n|" in section_body or section_body.lstrip().startswith("|"):
                    skipped.append(
                        {
                            "reason": "section_has_table",
                            "caption": caption,
                        }
                    )
                    continue
                table = _table_markdown(visual.get("table", {}))
                if not table:
                    skipped.append({"reason": "empty_table", "visual": visual})
                    continue
                snippet = table + "\n\n" + _caption(kind, caption, status)
                source_type = "derived_table"
            elif kind == "chart":
                svg = _chart_svg(visual.get("chart", {}))
                if not svg:
                    skipped.append({"reason": "chart_render_failed", "visual": visual})
                    continue
                path = assets_dir / f"chart_{rendered + 1:02d}.svg"
                path.write_text(svg, encoding="utf-8")
                snippet = f"![chart](assets/{path.name})\n\n" + _caption(kind, caption, status)
                source_type = "derived_chart"
            elif kind == "diagram":
                svg = _flow_svg(visual.get("diagram", {}))
                if not svg:
                    skipped.append({"reason": "diagram_render_failed", "visual": visual})
                    continue
                path = assets_dir / f"diagram_{rendered + 1:02d}.svg"
                path.write_text(svg, encoding="utf-8")
                snippet = f"![diagram](assets/{path.name})\n\n" + _caption(kind, caption, status)
                source_type = "derived_diagram"
            elif kind == "real_frame":
                frame_id = str(visual.get("frame_id", ""))
                frame = frames_by_id.get(frame_id)
                if frame is None:
                    skipped.append({"reason": "unknown_frame", "frame_id": frame_id})
                    continue
                file_name = frame.get("file", "")
                source = None
                if data_root is not None and video_id and file_name:
                    source = Path(data_root) / video_id / file_name
                if source is None or not source.exists():
                    skipped.append(
                        {
                            "reason": "frame_file_missing",
                            "frame_id": frame_id,
                            "source": str(source) if source else "",
                        }
                    )
                    continue
                readability = _frame_readability(
                    source, str(frame.get("caption", "") or "")
                )
                if readability["status"] in {"low", "unreadable"}:
                    skipped.append(
                        {
                            "reason": "frame_low_readability",
                            "frame_id": frame_id,
                            "readability": readability,
                        }
                    )
                    continue
                safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", frame_id)
                path = assets_dir / f"frame_{safe_name}{source.suffix or '.jpg'}"
                shutil.copy2(source, path)
                snippet = f"![frame](assets/{path.name})\n\n" + _caption(kind, caption, status)
                source_type = "real_frame"
            else:
                skipped.append({"reason": "unknown_kind", "kind": kind})
                continue
            _insert_before_last_paragraph(section["lines"], snippet)
            asset = {
                "kind": kind,
                "source_type": source_type,
                "path": str(path) if path else None,
                "caption": caption,
                "source_ids": visual.get("source_ids", []),
            }
            if readability is not None:
                asset["readability"] = readability
            assets.append(asset)
            rendered += 1
    return {
        "article": join_article(title, sections),
        "assets": assets,
        "skipped": skipped,
        "rendered": rendered,
    }
