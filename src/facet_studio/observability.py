"""Run trace / observability page for product v1.

Read-only over a run directory.  It combines:

- ``workflow.json`` stages/events
- ``llm_calls.jsonl``
- ``tool_calls.jsonl``
- ``decision_records.jsonl``
- deterministic contract/trajectory checks (P4)
- grounding candidate flags (P4)

The page is a developer/interview surface, not the product scoreboard: it shows
facts about this run, not a writing-quality score and not a hallucination rate.
"""

from __future__ import annotations

import html
import json
import os
from pathlib import Path
from typing import Any

STAGE_HELP = {
    "intake": "检查形态是否合法，准备这次 run；不调用模型。",
    "plan": "读内容稿，决定这次写哪种形态、角度和 brief；只编排，不写正文。",
    "approval": "计划卡的人工确认门；auto_approved 表示这次自动通过。",
    "write": "一次 writer 写完当前形态；没有 editor/checker，也没有第二轮改稿。",
    "typeset": "把 Markdown 排版成 HTML / PDF / 小红书卡片；不新增事实。",
    "review": "人工验收门；auto_accepted 表示自动验收，仍然是草稿，不是发布。",
}

FINAL_STATUSES = {
    "approved",
    "typeset",
    "partial",
    "rejected",
    "changes_requested",
    "failed",
}

# A typeset/partial artifact is not settled: the run is still waiting for the
# user acceptance gate.  Only these statuses end a run.
SETTLED_STATUSES = {
    "approved",
    "rejected",
    "changes_requested",
    "failed",
    "cancelled",
}

CALL_STAGE_HELP = {
    "bundle_plan": "规划：读内容稿和请求，决定这次写什么形态、角度和 brief。",
    "write_wechat_article": "写作：一次写完公众号文章。",
    "write_xiaohongshu_note": "写作：一次写完小红书笔记。",
    "write_long_article": "写作：一次写完深度总结。",
    "visual_audit": "视觉审计：判断候选关键帧能不能当插图；不通过就 0 张。",
    "svg_spec": "SVG 规格：把正文里的关系占位符变成可渲染的图规格。",
    "typeset": "排版：Markdown → HTML/PDF/卡片。",
}

FIELD_HELP = {
    "模型": "这次实际调用的模型；模型不同，成本、速度和稳定性都会变。",
    "temperature": "采样温度；越低越稳定，越高越发散。写作通常用低温度。",
    "max_tokens": "单次调用允许生成的最大 token 数；太小会被截断，太大则更贵。",
    "skill 版本": "这次使用的写作 skill 版本；改 skill 后，同一请求的结果可能不同。",
    "内容": "Writer 实际看到的内容稿字数与候选图数；不是视频原始时长。",
    "request": "用户在聊天里提的写作要求；它决定形态、读者、长度和 must include/avoid。",
    "中心判断": "Planner 提炼的一句话核心；写作和排版都围绕它。",
    "tokens": "模型读+写的总量；影响成本和上下文预算。",
    "延迟": "从开始到结束的墙钟时间；包含模型调用和排版，不等同于单次模型延迟。",
    "机器检查": "P4 确定性合同/轨迹检查；通过不代表写作质量通过。",
    "grounding": "内容稿里没找到字面匹配的候选；不等于错，也不是幻觉率。",
}


def _read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            rows.append(value)
    return rows


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return default


def _display(value: Any, run_dir: Path) -> str:
    """Hide the machine-specific project root in a run trace page."""
    text = str(value if value is not None else "")
    try:
        project_root = run_dir.resolve().parents[2]
        text = text.replace(str(project_root), "<project>")
    except (IndexError, OSError):
        pass
    return text


def _relative(path_value: Any, run_dir: Path) -> str:
    text = str(path_value or "")
    if not text:
        return ""
    try:
        return Path(text).resolve().relative_to(run_dir.resolve()).as_posix()
    except (ValueError, OSError):
        return text


def _summary_line(trace: dict[str, Any]) -> str:
    tokens = _int((trace.get("usage") or {}).get("total_tokens"))
    seconds = round(_int(trace.get("latency_ms")) / 1000, 1)
    checks_total = _int(trace.get("checks_total"))
    checks_passed = _int(trace.get("checks_passed"))
    flags = len((trace.get("grounding") or {}).get("flags") or [])
    parts = [
        f"{len(trace.get('stages') or [])} 个阶段",
        f"{_int(trace.get('calls_total'))} 次模型调用",
        f"{tokens:,} tokens",
        f"约 {seconds} 秒",
    ]
    if checks_total:
        parts.append(f"机器检查 {checks_passed}/{checks_total}")
    if flags:
        parts.append(f"grounding 候选 {flags}")
    return "这次运行跑了 " + "、".join(parts) + "。"


def _usage_totals(records: list[dict[str, Any]]) -> dict[str, int]:
    keys = (
        "prompt_tokens",
        "completion_tokens",
        "total_tokens",
        "reasoning_tokens",
        "cached_tokens",
    )
    return {
        key: sum(_int((row.get("usage") or {}).get(key)) for row in records)
        for key in keys
    }


def _checks(run_id: str, run_dir: Path) -> list[dict[str, Any]]:
    """Run the P4 deterministic checks if the run has the required artifacts."""
    try:
        from .evals.product import _check_run

        result = _check_run(
            {
                "case_id": run_id,
                "run_id": run_id,
                "kind": "trace",
                "require_approval": False,
            },
            runs_root=run_dir.parent.parent,
        )
        return [
            {
                "check_id": str(item.get("check_id") or ""),
                "passed": bool(item.get("passed")),
                "detail": _display(item.get("detail"), run_dir),
            }
            for item in result.get("checks") or []
        ]
    except Exception as exc:  # noqa: BLE001 - observability must not break typeset
        return [
            {
                "check_id": "trace_check_error",
                "passed": False,
                "detail": f"{type(exc).__name__}: {exc}",
            }
        ]


def _grounding(run_id: str, run_dir: Path) -> dict[str, Any]:
    """Grounding candidate audit; never call it a hallucination rate."""
    try:
        from .evals.grounding import _audit_run

        result = _audit_run(case_id=run_id, run_id=run_id, run_dir=run_dir)
        flags = [
            {
                "kind": str(item.get("kind") or ""),
                "value": str(item.get("value") or ""),
                "context": str(item.get("context") or ""),
            }
            for item in result.get("flags") or []
        ]
        by_kind: dict[str, int] = {}
        for flag in flags:
            by_kind[flag["kind"]] = by_kind.get(flag["kind"], 0) + 1
        return {"flags": flags, "by_kind": by_kind}
    except Exception as exc:  # noqa: BLE001
        return {
            "flags": [],
            "by_kind": {"audit_error": 1},
            "error": f"{type(exc).__name__}: {exc}",
        }


def _visual_audit_summary(
    run_dir: Path, meta: dict[str, Any]
) -> dict[str, Any]:
    """Summarize the keyframe audit without re-running vision calls."""
    data = _read_json(run_dir / "visual_audit.json") or {}
    fallback = meta.get("visual_audit") or {}
    candidates = data.get("candidates") or []
    reasons: dict[str, int] = {}
    for item in candidates:
        if item.get("has_watermark"):
            reasons["水印/平台界面"] = reasons.get("水印/平台界面", 0) + 1
        if item.get("has_person"):
            reasons["人物出镜"] = reasons.get("人物出镜", 0) + 1
        if str(item.get("scene_type") or "") in {"ui", "other"}:
            reasons["屏幕/其他"] = reasons.get("屏幕/其他", 0) + 1
        if str(item.get("quality") or "") not in {"", "clear"}:
            reasons["画面质量"] = reasons.get("画面质量", 0) + 1
        if item.get("info_value") is False:
            reasons["信息价值低"] = reasons.get("信息价值低", 0) + 1
    return {
        "candidate_count": _int(data.get("candidate_count", fallback.get("candidate_count"))),
        "approved_count": _int(data.get("approved_count", fallback.get("approved_count"))),
        "reasons": reasons,
        "error": str(data.get("error") or fallback.get("error") or ""),
    }


def _story(
    meta: dict[str, Any],
    stages: list[dict[str, Any]],
    *,
    visual_audit: dict[str, Any],
) -> list[dict[str, Any]]:
    """Human-readable "what this run did" steps for the run page and chat card."""
    by_name = {str(item.get("name") or ""): item for item in stages}
    source = meta.get("source") or {}
    write = meta.get("write") or {}
    plan = meta.get("plan") or {}
    review = meta.get("review") or {}
    status = str(meta.get("status") or "")
    story: list[dict[str, Any]] = []

    def add(
        step: str,
        value: str,
        detail: str,
        stage: dict[str, Any] | None = None,
    ) -> None:
        item: dict[str, Any] = {"step": step, "status": value, "detail": detail}
        if stage:
            item["duration_ms"] = _int(stage.get("duration_ms"))
            item["tokens"] = _int((stage.get("usage") or {}).get("total_tokens"))
        story.append(item)

    if "intake" in by_name:
        add(
            "读取内容",
            "succeeded",
            f"{_int(source.get('content_chars'))} 字 · {_int(source.get('figure_count'))} 张候选图",
            by_name["intake"],
        )
    if "plan" in by_name:
        add(
            "规划",
            str(by_name["plan"].get("status") or "succeeded"),
            str(plan.get("central_idea") or "已生成写作计划"),
            by_name["plan"],
        )
    if status == "awaiting_plan_approval":
        add("计划确认", "awaiting", "等待你确认计划")
    if _int(visual_audit.get("candidate_count")):
        reasons = " · ".join(
            f"{name} {count}" for name, count in (visual_audit.get("reasons") or {}).items()
        )
        approved = _int(visual_audit.get("approved_count"))
        add(
            "视觉审计",
            "passed" if approved else "no_frames",
            f"{_int(visual_audit.get('candidate_count'))} 候选 / {approved} 通过"
            + (f"（{reasons}）" if reasons else ""),
        )
    if "write" in by_name:
        refs = write.get("figures_referenced") or []
        images = [item for item in refs if not str(item).lower().endswith(".svg")]
        approved = (
            _int(visual_audit.get("approved_count"))
            if _int(visual_audit.get("candidate_count"))
            else len(images)
        )
        parts = [f"{_int(write.get('output_chars'))} 字"]
        svg_count = len(write.get("svg_assets") or [])
        if svg_count:
            parts.append(f"{svg_count} 个图表")
        parts.append(f"{approved} 张关键帧")
        add("写作", str(by_name["write"].get("status") or "succeeded"), " · ".join(parts), by_name["write"])
    if "typeset" in by_name:
        add(
            "排版",
            str(by_name["typeset"].get("status") or "typeset"),
            f"{meta.get('form_label') or meta.get('form') or '成品'}预览已生成",
            by_name["typeset"],
        )
    if "review" in by_name:
        decision = str(review.get("decision") or by_name["review"].get("status") or "")
        detail = {
            "approved": "用户已验收",
            "changes_requested": "用户要求修改",
            "rejected": "用户已拒绝",
            "auto_accepted": "自动通过（未人工验收）",
        }.get(decision, "等待用户验收")
        add("验收", str(by_name["review"].get("status") or decision or "awaiting"), detail, by_name["review"])
    elif status in {"typeset", "awaiting_review"}:
        add("验收", "awaiting_review", "等待用户验收")
    return story


def collect_trace(
    run_id: str,
    run_dir: Path,
    meta: dict[str, Any],
    *,
    include_checks: bool = True,
    include_grounding: bool = True,
    live: bool = False,
) -> dict[str, Any]:
    """Collect a normalized trace for one run.  Read-only."""
    workflow = _read_json(run_dir / "workflow.json")
    llm_calls = _read_jsonl(run_dir / "llm_calls.jsonl")
    tool_calls = _read_jsonl(run_dir / "tool_calls.jsonl")
    decisions = _read_jsonl(run_dir / "decision_records.jsonl")

    stages = [
        {
            "name": str(item.get("name") or ""),
            "status": str(item.get("status") or ""),
            "duration_ms": _int(item.get("duration_ms")),
            "usage": item.get("usage") or {},
            "error": item.get("error"),
            "at": item.get("at"),
        }
        for item in (workflow.get("stages") or meta.get("stages") or [])
    ]

    call_usage = _usage_totals(llm_calls)
    if llm_calls:
        usage = call_usage
    else:
        write = meta.get("write") or {}
        planner = meta.get("planner_usage") or {}
        write_usage = write.get("usage") or {}
        audit = meta.get("visual_audit_usage") or {}
        usage = {
            key: _int(planner.get(key)) + _int(write_usage.get(key)) + _int(audit.get(key))
            for key in (
                "prompt_tokens",
                "completion_tokens",
                "total_tokens",
                "reasoning_tokens",
                "cached_tokens",
            )
        }

    latency_ms = sum(_int(row.get("latency_ms")) for row in llm_calls)
    if not latency_ms:
        write = meta.get("write") or {}
        latency_ms = _int(meta.get("planner_latency_ms")) + _int(write.get("latency_ms"))

    artifacts = {
        key: _relative(value, run_dir)
        for key, value in (meta.get("artifacts") or {}).items()
        if isinstance(value, str)
    }
    write = meta.get("write") or {}
    source_meta = meta.get("source") or {}
    plan = meta.get("plan") or {}
    form = str(meta.get("form") or "")
    plan_form = next(
        (
            item
            for item in (plan.get("forms") or [])
            if str(item.get("form") or "") == form
        ),
        {},
    )
    first_call = llm_calls[0] if llm_calls else {}
    context = {
        "content_chars": _int(source_meta.get("content_chars")),
        "figure_count": _int(source_meta.get("figure_count")),
        "figures_referenced": len(write.get("figures_referenced") or []),
        "keyframes_referenced": (
            _int((meta.get("visual_audit") or {}).get("approved_count"))
            if _int((meta.get("visual_audit") or {}).get("candidate_count"))
            else len(
                [
                    item
                    for item in (write.get("figures_referenced") or [])
                    if not str(item).lower().endswith(".svg")
                ]
            )
        ),
        "output_chars": _int(write.get("output_chars")),
        "svg_count": len(write.get("svg_assets") or []),
        "card_count": len(
            ((meta.get("typeset") or {}).get("xhs_export") or {}).get("images")
            or (meta.get("artifacts") or {}).get("xhs_cards")
            or []
        ),
        "visual_audit": _visual_audit_summary(run_dir, meta),
        "skill_id": str(write.get("skill_id") or ""),
        "skill_version": str(write.get("skill_version") or ""),
        "request": str(meta.get("request") or ""),
        "central_idea": str(plan.get("central_idea") or ""),
        "plan_angle": str(plan_form.get("angle") or plan.get("angle") or ""),
        "plan_reader": str(plan.get("reader_goal") or ""),
        "plan_brief": str(plan_form.get("brief") or ""),
        "model": str(first_call.get("model") or ""),
        "temperature": first_call.get("temperature"),
        "max_tokens": first_call.get("max_tokens"),
        "form": form,
        "video_id": str(meta.get("video_id") or ""),
        "source_title": str(source_meta.get("title") or ""),
        "started_at": str(meta.get("created_at") or ""),
    }
    checks = _checks(run_id, run_dir) if include_checks else []
    grounding = (
        _grounding(run_id, run_dir)
        if include_grounding
        else {"flags": [], "by_kind": {}}
    )
    review = _read_json(run_dir / "publish_review.json")

    return {
        "run_id": run_id,
        "trace_url": str(
            os.environ.get("FACET_STUDIO_PREVIEW_BASE", "http://127.0.0.1:8765/runs")
        ).rstrip("/")
        + f"/{run_id}",
        "video_id": str(meta.get("video_id") or ""),
        "form": str(meta.get("form") or ""),
        "form_label": str(meta.get("form_label") or meta.get("form") or ""),
        "status": str(meta.get("status") or ""),
        "workflow_status": str(workflow.get("status") or ""),
        "next": workflow.get("next") or [],
        "request": str(meta.get("request") or ""),
        "source": meta.get("source") or {},
        "created_at": meta.get("created_at"),
        "updated_at": meta.get("updated_at"),
        "review": {
            "decision": str(review.get("decision") or ""),
            "notes": str(review.get("notes") or ""),
            "reviewed_at": review.get("reviewed_at"),
        },
        "stages": stages,
        "story": _story(meta, stages, visual_audit=_visual_audit_summary(run_dir, meta)),
        "events": workflow.get("events") or [],
        "llm_calls": llm_calls,
        "tool_calls": tool_calls,
        "decisions": decisions,
        "usage": usage,
        "calls_total": len(llm_calls),
        "calls_known": bool(llm_calls),
        "tokens_known": bool(llm_calls) or bool(usage.get("total_tokens")),
        "tools_total": len(tool_calls),
        "decisions_total": len(decisions),
        "latency_ms": latency_ms,
        "cost_estimate": workflow.get("cost_estimate") or meta.get("cost_estimate"),
        "checks": checks,
        "checks_passed": sum(1 for item in checks if item.get("passed")),
        "checks_total": len(checks),
        "grounding": grounding,
        "context": context,
        "live": live,
        "final": str(meta.get("status") or "") in FINAL_STATUSES,
        "help": {
            "stage": STAGE_HELP,
            "call": CALL_STAGE_HELP,
            "field": FIELD_HELP,
        },
        "summary": _summary_line(
            {
                "stages": stages,
                "calls_total": len(llm_calls),
                "usage": usage,
                "latency_ms": latency_ms,
                "checks_total": len(checks),
                "checks_passed": sum(1 for item in checks if item.get("passed")),
                "grounding": grounding,
            }
        ),
        "artifacts": artifacts,
    }


def _e(value: Any) -> str:
    return html.escape(str(value if value is not None else ""))


def _tokens(value: Any) -> str:
    return f"{_int(value):,}" if _int(value) else "0"


def _status_class(value: str) -> str:
    value = value.lower()
    if value in {"succeeded", "approved", "typeset", "auto_approved", "auto_accepted", "complete"}:
        return "ok"
    if value in {"failed", "error", "rejected", "partial"}:
        return "bad"
    return "wait"


def _status_dot(value: str) -> str:
    return f'<span class="dot {_status_class(value)}"></span>'


def _check_rows(checks: list[dict[str, Any]]) -> str:
    if not checks:
        return '<p class="muted">没有可用的机器检查（run 可能还没排版或缺少产物）。</p>'
    rows = []
    for item in checks:
        state = "通过" if item.get("passed") else "未通过"
        cls = "ok" if item.get("passed") else "bad"
        rows.append(
            "<tr>"
            f'<td><span class="pill {cls}">{state}</span></td>'
            f"<td><code>{_e(item.get('check_id'))}</code></td>"
            f"<td>{_e(item.get('detail'))}</td>"
            "</tr>"
        )
    return (
        '<div class="table-wrap"><table><thead><tr>'
        "<th>结果</th><th>检查</th><th>详情</th>"
        "</tr></thead><tbody>"
        + "".join(rows)
        + "</tbody></table></div>"
    )


def _stage_rows(stages: list[dict[str, Any]]) -> str:
    if not stages:
        return '<p class="muted">没有 stage 记录（可能是 CLI run，不是 workflow run）。</p>'
    rows = []
    for item in stages:
        usage = item.get("usage") or {}
        error = str(item.get("error") or "")
        error_html = _e(error) if error else '<span class="muted">—</span>'
        rows.append(
            "<tr>"
            f"<td>{_status_dot(item.get('status', ''))} {_e(item.get('status'))}</td>"
            f"<td><strong>{_e(item.get('name'))}</strong></td>"
            f"<td>{_int(item.get('duration_ms')):,} ms</td>"
            f"<td>{_tokens(usage.get('total_tokens'))}</td>"
            f"<td>{error_html}</td>"
            "</tr>"
        )
    return (
        '<div class="table-wrap"><table><thead><tr>'
        "<th>状态</th><th>阶段</th><th>耗时</th><th>tokens</th><th>错误</th>"
        "</tr></thead><tbody>"
        + "".join(rows)
        + "</tbody></table></div>"
    )


def _clip(value: Any, limit: int = 900) -> str:
    text = str(value if value is not None else "")
    return text if len(text) <= limit else text[:limit].rstrip() + "…"


def _pre(value: Any) -> str:
    if isinstance(value, (dict, list)):
        text = json.dumps(value, ensure_ascii=False, indent=2)
    else:
        text = str(value if value is not None else "")
    return f"<pre>{_e(_clip(text))}</pre>"


def _stage_details(stages: list[dict[str, Any]]) -> str:
    if not stages:
        return ""
    items = []
    for index, item in enumerate(stages, 1):
        name = str(item.get("name") or "")
        help_text = STAGE_HELP.get(name, "workflow 的一个阶段。")
        usage = item.get("usage") or {}
        error = str(item.get("error") or "")
        items.append(
            '<details class="record"><summary>'
            f"{_status_dot(item.get('status', ''))}<b>{index}. {_e(name)}</b>"
            f"<span class=\"muted\">{_int(item.get('duration_ms')):,} ms · "
            f"{_tokens(usage.get('total_tokens'))} tokens</span>"
            "</summary><div class=\"record-body\">"
            f"<p>{_e(help_text)}</p>"
            f"<p><b>状态</b> {_e(item.get('status'))}"
            f"{' · <b>错误</b> ' + _e(error) if error else ''}</p>"
            f"{_pre(usage)}"
            "</div></details>"
        )
    return '<div class="records">' + "".join(items) + "</div>"


def _llm_details(calls: list[dict[str, Any]]) -> str:
    if not calls:
        return ""
    items = []
    for index, call in enumerate(calls, 1):
        usage = call.get("usage") or {}
        status = str(call.get("status") or "")
        error = str(call.get("error") or "")
        raw = _clip(call.get("raw_response") or "", 700)
        items.append(
            '<details class="record"><summary>'
            f"{_status_dot(status)}<b>#{index} {_e(call.get('stage'))}</b>"
            f"<code>{_e(call.get('model'))}</code>"
            f"<span class=\"muted\">{_tokens(usage.get('total_tokens'))} tokens · "
            f"{_int(call.get('latency_ms')):,} ms</span>"
            "</summary><div class=\"record-body\">"
            f"<p>{_e(CALL_STAGE_HELP.get(str(call.get('stage') or ''), '一次模型调用。'))}</p>"
            f"<p><b>key</b> {_e(call.get('key'))} · <b>finish</b> {_e(call.get('finish_reason'))} · "
            f"<b>max_tokens</b> {_e(call.get('max_tokens'))} · <b>temperature</b> {_e(call.get('temperature'))}</p>"
            f"<p><b>input_hash</b> {_e(str(call.get('input_hash') or '')[:16])} · "
            f"<b>system_hash</b> {_e(str(call.get('system_hash') or '')[:16])} · "
            f"<b>user_hash</b> {_e(str(call.get('user_hash') or '')[:16])}</p>"
            f"{'<p><b>错误</b> ' + _e(error) + '</p>' if error else ''}"
            f"{_pre(usage)}"
            f"{_pre(raw) if raw else ''}"
            "</div></details>"
        )
    return '<div class="records">' + "".join(items) + "</div>"


def _tool_details(calls: list[dict[str, Any]]) -> str:
    if not calls:
        return ""
    items = []
    for index, call in enumerate(calls, 1):
        items.append(
            '<details class="record"><summary>'
            f"<b>#{index} {_e(call.get('tool_name') or call.get('task_id'))}</b>"
            f"<span class=\"muted\">{_e(call.get('actor'))} · "
            f"{_int(call.get('latency_ms')):,} ms</span>"
            "</summary><div class=\"record-body\">"
            f"<p><b>status</b> {_e(call.get('status'))}</p>"
            f"{_pre(call.get('arguments') or {})}"
            f"{_pre(call.get('result') or {})}"
            f"{'<p><b>错误</b> ' + _e(call.get('error')) + '</p>' if call.get('error') else ''}"
            "</div></details>"
        )
    return '<div class="records">' + "".join(items) + "</div>"


def _decision_details(decisions: list[dict[str, Any]]) -> str:
    if not decisions:
        return ""
    items = []
    for index, item in enumerate(decisions, 1):
        items.append(
            '<details class="record"><summary>'
            f"<b>#{index} {_e(item.get('stage'))}</b>"
            f"<span class=\"muted\">{_e(item.get('selected'))}</span>"
            "</summary><div class=\"record-body\">"
            f"<p><b>问题</b> {_e(item.get('question'))}</p>"
            f"<p><b>选择</b> {_e(item.get('selected'))} · <b>由谁</b> {_e(item.get('decided_by'))}</p>"
            f"{'<p><b>依据</b> ' + _e(item.get('basis')) + '</p>' if item.get('basis') else ''}"
            f"{_pre(item.get('candidates') or [])}"
            "</div></details>"
        )
    return '<div class="records">' + "".join(items) + "</div>"


def _llm_rows(calls: list[dict[str, Any]]) -> str:
    if not calls:
        return '<p class="muted">没有 llm_calls.jsonl；usage 来自 run_meta 汇总。</p>'
    rows = []
    for call in calls:
        usage = call.get("usage") or {}
        status = str(call.get("status") or "")
        error = str(call.get("error") or "")
        error_html = _e(error) if error else '<span class="muted">—</span>'
        rows.append(
            "<tr>"
            f"<td>{_status_dot(status)} {_e(status)}</td>"
            f"<td><code>{_e(call.get('stage'))}</code></td>"
            f"<td>{_e(call.get('model'))}</td>"
            f"<td>{_tokens(usage.get('prompt_tokens'))}</td>"
            f"<td>{_tokens(usage.get('completion_tokens'))}</td>"
            f"<td>{_tokens(usage.get('total_tokens'))}</td>"
            f"<td>{_int(call.get('latency_ms')):,} ms</td>"
            f"<td>{error_html}</td>"
            "</tr>"
        )
    return (
        '<div class="table-wrap"><table><thead><tr>'
        "<th>状态</th><th>stage</th><th>model</th><th>prompt</th>"
        "<th>completion</th><th>total</th><th>延迟</th><th>错误</th>"
        "</tr></thead><tbody>"
        + "".join(rows)
        + "</tbody></table></div>"
    )


def _tool_rows(calls: list[dict[str, Any]]) -> str:
    if not calls:
        return '<p class="muted">没有 tool_calls.jsonl；product workflow 的工具调用在 stage/事件里。</p>'
    rows = []
    for call in calls:
        error = str(call.get("error") or "")
        error_html = _e(error) if error else '<span class="muted">—</span>'
        rows.append(
            "<tr>"
            f"<td><code>{_e(call.get('tool_name') or call.get('task_id'))}</code></td>"
            f"<td>{_e(call.get('actor'))}</td>"
            f"<td>{_int(call.get('latency_ms')):,} ms</td>"
            f"<td>{error_html}</td>"
            "</tr>"
        )
    return (
        '<div class="table-wrap"><table><thead><tr>'
        "<th>工具</th><th>actor</th><th>耗时</th><th>错误</th>"
        "</tr></thead><tbody>"
        + "".join(rows)
        + "</tbody></table></div>"
    )


def _decision_rows(decisions: list[dict[str, Any]]) -> str:
    if not decisions:
        return '<p class="muted">没有 decision_records.jsonl。</p>'
    rows = []
    for item in decisions:
        rows.append(
            "<tr>"
            f"<td><code>{_e(item.get('stage'))}</code></td>"
            f"<td>{_e(item.get('question'))}</td>"
            f"<td>{_e(item.get('selected'))}</td>"
            f"<td>{_e(item.get('decided_by'))}</td>"
            "</tr>"
        )
    return (
        '<div class="table-wrap"><table><thead><tr>'
        "<th>stage</th><th>问题</th><th>选择</th><th>由谁决定</th>"
        "</tr></thead><tbody>"
        + "".join(rows)
        + "</tbody></table></div>"
    )


def _grounding_rows(grounding: dict[str, Any]) -> str:
    flags = grounding.get("flags") or []
    if not flags:
        return '<p class="muted">没有 grounding candidate flags（或内容稿/产物不完整）。</p>'
    rows = []
    for flag in flags[:30]:
        context = str(flag.get("context") or "")
        rows.append(
            "<tr>"
            f"<td><code>{_e(flag.get('kind'))}</code></td>"
            f"<td>{_e(flag.get('value'))}</td>"
            f"<td>{_e(context)}</td>"
            "</tr>"
        )
    more = (
        f'<p class="muted">仅显示前 30 条，共 {len(flags)} 条。</p>'
        if len(flags) > 30
        else ""
    )
    return (
        more
        + '<div class="table-wrap"><table><thead><tr>'
        "<th>类型</th><th>候选值</th><th>上下文</th>"
        "</tr></thead><tbody>"
        + "".join(rows)
        + "</tbody></table></div>"
    )


def _artifact_links(artifacts: dict[str, str]) -> str:
    if not artifacts:
        return '<p class="muted">没有 artifact。</p>'
    links = []
    for key, value in sorted(artifacts.items()):
        if not value:
            continue
        if value.startswith(("http://", "https://")):
            href = value
        elif len(value) > 2 and value[1] == ":":
            # Absolute Windows path outside the run dir: show it as text, not
            # as a broken relative link.
            links.append(f'<span class="artifact">{_e(key)}</span>')
            continue
        else:
            href = "./" + value.lstrip("./")
        links.append(f'<a class="artifact" href="{_e(href)}">{_e(key)}</a>')
    return '<div class="artifacts">' + "".join(links) + "</div>"


def render_trace_html(trace: dict[str, Any]) -> str:
    """Render a standalone run trace dashboard."""
    usage = trace.get("usage") or {}
    grounding = trace.get("grounding") or {}
    context = trace.get("context") or {}
    review = trace.get("review") or {}
    status = trace.get("status") or ""
    review_decision = review.get("decision") or "draft"
    cost = trace.get("cost_estimate")
    cost_text = f"${cost:.4f}" if isinstance(cost, (int, float)) else "—"
    flags_count = len(grounding.get("flags") or [])
    by_kind = grounding.get("by_kind") or {}
    by_kind_text = " · ".join(f"{key} {value}" for key, value in by_kind.items()) or "—"
    checks_passed = trace.get("checks_passed") or 0
    checks_total = trace.get("checks_total") or 0
    check_text = f"{checks_passed}/{checks_total}" if checks_total else "—"
    final_status = {"approved", "typeset", "partial", "rejected", "changes_requested", "failed"}
    live = bool(trace.get("live")) and status not in final_status
    refresh = '<meta http-equiv="refresh" content="3">' if live else ""
    model_text = context.get("model") or "—"
    temp = context.get("temperature")
    max_tokens = context.get("max_tokens")
    temp_text = "—" if temp is None else str(temp)
    max_text = "—" if max_tokens is None else f"{_int(max_tokens):,}"
    source_value = str(context.get("video_id") or "—")
    source_title = str(context.get("source_title") or "").strip()
    if source_title and source_title != source_value:
        source_value = f"{source_value} · {source_title}"
    config_rows = [
        ("来源", source_value, ""),
        ("形态", str(trace.get("form_label") or trace.get("form") or "—"), ""),
        ("请求", context.get("request") or "—", FIELD_HELP["request"]),
        ("模型", model_text, FIELD_HELP["模型"]),
        ("temperature", temp_text, FIELD_HELP["temperature"]),
        ("max_tokens", max_text, FIELD_HELP["max_tokens"]),
        (
            "skill 版本",
            f"{context.get('skill_id') or '—'} {context.get('skill_version') or ''}".strip(),
            FIELD_HELP["skill 版本"],
        ),
        (
            "内容",
            f"{_int(context.get('content_chars')):,} 字 · {_int(context.get('figure_count'))} 图",
            FIELD_HELP["内容"],
        ),
        ("中心判断", context.get("central_idea") or "—", FIELD_HELP["中心判断"]),
    ]
    config_html = "".join(
        "<tr>"
        f"<td><strong>{_e(label)}</strong></td>"
        f"<td>{_e(value)}</td>"
        f"<td>{_e(help_text)}</td>"
        "</tr>"
        for label, value, help_text in config_rows
    )
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
{refresh}
<title>运行数据 · {_e(trace.get('run_id'))}</title>
<style>
:root{{--bg:#f2efe8;--paper:#fffdf9;--ink:#1b1916;--muted:#6b645b;--line:#ddd6c9;--accent:#b5502f;--ok:#2f7d4a;--bad:#b23a2e;--wait:#a07a2c}}
*{{box-sizing:border-box}}
body{{margin:0;background:radial-gradient(1100px 500px at 50% -10%,#fffdf9 0%,var(--bg) 60%);
color:var(--ink);font-family:system-ui,"Segoe UI","Microsoft YaHei","PingFang SC",sans-serif;line-height:1.7}}
.page{{max-width:1080px;margin:0 auto;padding:34px 20px 80px}}
.top{{display:flex;justify-content:space-between;gap:18px;align-items:flex-start;flex-wrap:wrap;margin-bottom:18px}}
.kicker{{font-size:11px;letter-spacing:.18em;text-transform:uppercase;color:var(--accent);font-weight:750}}
h1{{font-family:"Noto Serif SC","Source Han Serif SC","Songti SC",SimSun,Georgia,serif;font-size:30px;line-height:1.25;margin:6px 0 6px}}
.sub{{font-size:13px;color:var(--muted);word-break:break-all}}
.badges{{display:flex;gap:8px;flex-wrap:wrap;margin-top:10px}}
.badge{{font-size:12px;border:1px solid var(--line);background:var(--paper);border-radius:999px;padding:4px 10px;color:var(--muted)}}
.card{{background:var(--paper);border:1px solid var(--line);border-radius:16px;padding:20px 22px;margin:0 0 16px;box-shadow:0 10px 30px rgba(66,50,32,.05)}}
h2{{font-size:17px;margin:0 0 12px;letter-spacing:.01em}}
h2 .hint{{font-size:12px;font-weight:400;color:var(--muted);margin-left:8px}}
.stats{{display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:10px;margin:0 0 16px}}
.stat{{background:var(--paper);border:1px solid var(--line);border-radius:14px;padding:14px 16px}}
.stat .label{{font-size:11px;color:var(--muted);letter-spacing:.08em;text-transform:uppercase}}
.stat .value{{font-size:22px;font-weight:750;margin-top:4px;font-variant-numeric:tabular-nums}}
.muted{{color:var(--muted);font-size:13px}}
.dot{{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:6px;vertical-align:1px}}
.dot.ok{{background:var(--ok)}}.dot.bad{{background:var(--bad)}}.dot.wait{{background:var(--wait)}}
.pill{{display:inline-block;font-size:12px;border-radius:999px;padding:2px 8px;border:1px solid var(--line)}}
.pill.ok{{color:var(--ok);background:#eef6f0;border-color:#cfe4d5}}.pill.bad{{color:var(--bad);background:#fbeeeb;border-color:#edc9c2}}
.table-wrap{{overflow-x:auto;border:1px solid var(--line);border-radius:12px;background:#fff}}
table{{width:100%;border-collapse:collapse;font-size:13px}}
th,td{{border-bottom:1px solid var(--line);padding:9px 11px;text-align:left;vertical-align:top}}
th{{background:#f1ede4;font-size:12px;color:#3c372f;white-space:nowrap}}
tbody tr:last-child td{{border-bottom:0}}
tbody tr:nth-child(even){{background:#faf8f3}}
code{{background:#f1ede4;border-radius:4px;padding:1px 5px;font-size:.92em;white-space:nowrap}}
.kv{{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px 20px}}
.kv span{{display:block;font-size:11px;letter-spacing:.08em;color:var(--muted);text-transform:uppercase;margin-bottom:3px}}
.kv strong{{font-size:13px;font-weight:600;line-height:1.55;word-break:break-word}}
.artifacts{{display:flex;gap:8px;flex-wrap:wrap}}
.artifact{{font-size:12px;color:var(--ink);background:#f1ede4;border:1px solid var(--line);border-radius:999px;padding:5px 10px;text-decoration:none}}
.artifact:hover{{color:var(--accent);border-color:var(--accent)}}
.grid2{{display:grid;grid-template-columns:1fr 1fr;gap:16px}}
.summary-line{{font-size:16px;line-height:1.7;font-weight:600}}
.howto{{font-size:13px;color:var(--muted);line-height:1.75}}
.howto b{{color:var(--ink)}}
.config-table td:last-child{{color:var(--muted);font-size:12px;line-height:1.55}}
details.record{{border:1px solid var(--line);border-radius:12px;background:#fff;margin:8px 0;overflow:hidden}}
details.record summary{{cursor:pointer;padding:10px 12px;font-size:13px;display:flex;gap:8px;align-items:center;flex-wrap:wrap}}
details.record summary::marker{{color:var(--accent)}}
details.record .record-body{{padding:0 12px 12px;font-size:12px;color:var(--muted);line-height:1.65}}
details.record pre{{background:#211d19;color:#f4f1e8;padding:10px 12px;border-radius:8px;overflow-x:auto;font-size:11.5px;line-height:1.55;margin:8px 0 0}}
.live-banner{{background:#fbf4ef;border:1px solid #edc9c2;color:#8a4a36;border-radius:10px;padding:8px 12px;font-size:13px;margin:0 0 12px}}
@media(max-width:760px){{.grid2{{grid-template-columns:1fr}}.page{{padding:22px 12px 60px}}.card{{padding:16px}}}}
</style>
</head>
<body>
<div class="page">
<div class="top">
<div>
<div class="kicker">Facet Studio · Run trace</div>
<h1>运行数据</h1>
<div class="sub">{_e(trace.get('run_id'))}</div>
<div class="badges">
<span class="badge">视频 {_e(trace.get('video_id') or '—')}</span>
<span class="badge">{_e(trace.get('form_label') or trace.get('form'))}</span>
<span class="badge">run {_e(status or '—')}</span>
<span class="badge">验收 {_e(review_decision)}</span>
</div>
</div>
<div class="muted">开发/面试观测页 · 不展示写作质量分<br>数据来自 workflow / llm_calls / tool_calls / decision_records</div>
</div>

<div class="card">
{f'<div class="live-banner">运行中：页面每 3 秒自动刷新；结束后再回来看完整检查。</div>' if live else ''}
<div class="summary-line">{_e(trace.get('summary'))}</div>
<div class="howto" style="margin-top:10px">
<b>怎么看：</b>阶段 = 编排步骤；模型调用 = 一次 LLM 请求；工具调用 = workflow 的 step span；机器检查 = P4 合同/轨迹；grounding 候选 = 内容稿里没找到的字面匹配，<b>不是错，也不是幻觉率</b>。点任意一条记录可以展开参数和结果。
</div>
</div>

<div class="stats">
<div class="stat"><div class="label">调用</div><div class="value">{_int(trace.get('calls_total'))}</div></div>
<div class="stat"><div class="label">tokens</div><div class="value">{_tokens(usage.get('total_tokens'))}</div></div>
<div class="stat"><div class="label">延迟</div><div class="value">{_int(trace.get('latency_ms')):,}<span style="font-size:12px"> ms</span></div></div>
<div class="stat"><div class="label">成本</div><div class="value">{cost_text}</div></div>
<div class="stat"><div class="label">工具</div><div class="value">{_int(trace.get('tools_total'))}</div></div>
<div class="stat"><div class="label">合同/轨迹</div><div class="value">{check_text}</div></div>
<div class="stat"><div class="label">grounding 候选</div><div class="value">{flags_count}</div></div>
</div>

<div class="card">
<h2>这次运行的配置 <span class="hint">参数 + 说人话：这是什么、为什么重要</span></h2>
<div class="table-wrap">
<table class="config-table">
<thead><tr><th>字段</th><th>本次值</th><th>这是什么</th></tr></thead>
<tbody>{config_html}</tbody>
</table>
</div>
</div>

<div class="card">
<h2>执行时间线 <span class="hint">workflow stages · 点开看每个阶段</span></h2>
{_stage_rows(trace.get('stages') or [])}
{_stage_details(trace.get('stages') or [])}
</div>

<div class="card">
<h2>模型调用 <span class="hint">llm_calls.jsonl · 每条调用可展开</span></h2>
{_llm_rows(trace.get('llm_calls') or [])}
{_llm_details(trace.get('llm_calls') or [])}
</div>

<div class="grid2">
<div class="card">
<h2>工具调用 <span class="hint">tool_calls.jsonl · 每条 span 可展开</span></h2>
{_tool_rows(trace.get('tool_calls') or [])}
{_tool_details(trace.get('tool_calls') or [])}
</div>
<div class="card">
<h2>决策记录 <span class="hint">decision_records.jsonl · 点开看依据</span></h2>
{_decision_rows(trace.get('decisions') or [])}
{_decision_details(trace.get('decisions') or [])}
</div>
</div>

<div class="card">
<h2>机器检查 <span class="hint">P4 deterministic contract/trajectory；不是写作质量分</span></h2>
{_check_rows(trace.get('checks') or [])}
</div>

<div class="card">
<h2>Grounding candidates <span class="hint">候选标记，不是幻觉率</span></h2>
<p class="muted">{_e(by_kind_text)}</p>
{_grounding_rows(grounding)}
</div>

<div class="card">
<h2>产物 <span class="hint">相对本 run 目录</span></h2>
{_artifact_links(trace.get('artifacts') or {})}
<p class="muted" style="margin:12px 0 0">只读页面；不自动发布。验收状态以 publish_review.json 为准。</p>
</div>
</div>
</body></html>"""


def _percentile(values: list[int], fraction: float) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(round((len(ordered) - 1) * fraction))))
    return int(ordered[index])


def collect_runs_dashboard(runs_root: Path, *, limit: int = 50) -> dict[str, Any]:
    """Recent runs + aggregate stats for the local dev dashboard."""
    root = runs_root / "product_v1"
    candidates = [item for item in root.iterdir() if item.is_dir()] if root.is_dir() else []

    def _run_sort_key(item: Path) -> tuple[str, str]:
        # Run ids begin with a UTC stamp; use it instead of directory mtime,
        # which changes when trace.json/trace.html is regenerated.  Non-stamped
        # ids (smoke_*, demo) sort after the stamped runs.
        name = item.name
        stamp = name[:16] if len(name) >= 16 and name[:8].isdigit() and name[8] == "T" else ""
        return (stamp, name)

    candidates.sort(key=_run_sort_key, reverse=True)
    runs: list[dict[str, Any]] = []
    for run_dir in candidates[:limit]:
        meta = _read_json(run_dir / "run_meta.json")
        if not meta:
            continue
        trace = _read_json(run_dir / "trace.json")
        if not trace:
            try:
                trace = collect_trace(
                    run_dir.name,
                    run_dir,
                    meta,
                    include_checks=False,
                    include_grounding=False,
                )
            except Exception:  # noqa: BLE001
                trace = {}
        usage = trace.get("usage") or {}
        review = _read_json(run_dir / "publish_review.json")
        runs.append(
            {
                "run_id": run_dir.name,
                "video_id": meta.get("video_id"),
                "title": str(
                    (meta.get("plan") or {}).get("central_idea")
                    or meta.get("request")
                    or ""
                )[:160],
                "form": meta.get("form"),
                "form_label": meta.get("form_label") or meta.get("form"),
                "status": meta.get("status"),
                "review": review.get("decision") or "draft",
                "calls_total": _int(trace.get("calls_total")),
                "calls_known": bool(trace.get("llm_calls")),
                "tokens_known": bool(trace.get("llm_calls")) or bool(usage.get("total_tokens")),
                "tools_total": _int(trace.get("tools_total")),
                "tokens": _int(usage.get("total_tokens")),
                "latency_ms": _int(trace.get("latency_ms")),
                "cost_estimate": trace.get("cost_estimate"),
                "checks_passed": _int(trace.get("checks_passed")),
                "checks_total": _int(trace.get("checks_total")),
                "grounding_flags": len((trace.get("grounding") or {}).get("flags") or []),
                "updated_at": meta.get("updated_at") or meta.get("created_at"),
            }
        )

    latencies = [item["latency_ms"] for item in runs if item["latency_ms"]]
    errors = [item for item in runs if item.get("status") in {"failed", "partial"}]
    check_total = sum(item["checks_total"] for item in runs)
    check_passed = sum(item["checks_passed"] for item in runs)
    costs = [item["cost_estimate"] for item in runs if isinstance(item.get("cost_estimate"), (int, float))]
    return {
        "summary": {
            "runs": len(runs),
            "calls_total": sum(item["calls_total"] for item in runs),
            "tokens_total": sum(item["tokens"] for item in runs),
            "latency_p50_ms": _percentile(latencies, 0.50),
            "latency_p95_ms": _percentile(latencies, 0.95),
            "error_rate": round(len(errors) / len(runs), 4) if runs else 0.0,
            "checks_passed": check_passed,
            "checks_total": check_total,
            "grounding_flags": sum(item["grounding_flags"] for item in runs),
            "cost_total": round(sum(costs), 6) if costs else None,
        },
        "runs": runs,
    }


def write_trace(
    run_id: str,
    run_dir: Path,
    meta: dict[str, Any],
    *,
    live: bool = False,
    include_checks: bool = True,
    include_grounding: bool = True,
) -> Path:
    """Collect and write ``trace.html`` next to the run artifacts."""
    trace = collect_trace(
        run_id,
        run_dir,
        meta,
        include_checks=include_checks,
        include_grounding=include_grounding,
        live=live,
    )
    path = run_dir / "trace.html"
    path.write_text(render_trace_html(trace), encoding="utf-8")
    (run_dir / "trace.json").write_text(
        json.dumps(trace, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return path


def trace_summary(run_id: str, run_dir: Path, meta: dict[str, Any]) -> dict[str, Any]:
    """Cheap summary for ``get_run``; no checks/grounding scans."""
    trace = collect_trace(
        run_id,
        run_dir,
        meta,
        include_checks=False,
        include_grounding=False,
    )
    return {
        "trace_url": "trace.html",
        "stages": trace["stages"],
        "calls_total": trace["calls_total"],
        "calls_known": trace["calls_known"],
        "tokens_known": trace["tokens_known"],
        "tools_total": trace["tools_total"],
        "decisions_total": trace["decisions_total"],
        "usage": trace["usage"],
        "latency_ms": trace["latency_ms"],
        "cost_estimate": trace["cost_estimate"],
    }
