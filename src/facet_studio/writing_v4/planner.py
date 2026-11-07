"""Lead Planner: choose forms, angles and short briefs.

The planner is one model call.  It does not write prose.  Its output is a
small JSON plan that the orchestrator turns into a TaskPlan and per-form
writer briefs.  Invalid or failed plans fall back to a deterministic plan so
one bad call never blocks the bundle.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..core.jsonutil import StructuredOutputError, extract_json_object
from .skills import LoadedSkill


class PlanError(ValueError):
    kind = "plan_error"


@dataclass
class PlannedForm:
    form: str
    reason: str
    angle: str
    brief: str
    must_use_figures: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "form": self.form,
            "reason": self.reason,
            "angle": self.angle,
            "brief": self.brief,
            "must_use_figures": self.must_use_figures,
        }


@dataclass
class LeadPlan:
    central_idea: str
    reader_goal: str
    forms: list[PlannedForm]
    shared_constraints: list[str] = field(default_factory=list)
    notes: str = ""
    source: str = "planner"
    error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "central_idea": self.central_idea,
            "reader_goal": self.reader_goal,
            "forms": [item.as_dict() for item in self.forms],
            "shared_constraints": self.shared_constraints,
            "notes": self.notes,
            "source": self.source,
            "error": self.error,
        }


def _form_ids(catalog: list[dict[str, str]]) -> set[str]:
    return {str(item.get("form")) for item in catalog}


def catalog_text(catalog: list[dict[str, str]]) -> str:
    lines = []
    for item in catalog:
        lines.append(
            f"- {item['form']}（{item.get('name', '')}，角色 {item.get('role', 'writer')}）："
            f"{item.get('description', '')}"
        )
    return "\n".join(lines)


def _normalize_figure(value: Any) -> str:
    return Path(str(value or "")).name


def parse_plan(
    text: str,
    *,
    catalog: list[dict[str, str]],
    required_forms: list[str] | None = None,
    available_figures: list[str] | None = None,
) -> LeadPlan:
    try:
        data = extract_json_object(text)
    except StructuredOutputError as exc:
        raise PlanError(str(exc)) from exc

    valid_forms = _form_ids(catalog)
    available = {_normalize_figure(item) for item in (available_figures or [])}
    raw_forms = data.get("forms")
    if not isinstance(raw_forms, list) or not raw_forms:
        raise PlanError("计划缺少 forms")

    planned: list[PlannedForm] = []
    seen: set[str] = set()
    for item in raw_forms:
        if not isinstance(item, dict):
            continue
        form_id = str(item.get("form") or "").strip()
        if form_id not in valid_forms or form_id in seen:
            continue
        seen.add(form_id)
        angle = str(item.get("angle") or "").strip()
        brief = str(item.get("brief") or angle).strip()
        if not brief:
            continue
        figures = [
            _normalize_figure(value)
            for value in (item.get("must_use_figures") or [])
            if _normalize_figure(value) in available
        ]
        planned.append(
            PlannedForm(
                form=form_id,
                reason=str(item.get("reason") or "").strip(),
                angle=angle,
                brief=brief[:600],
                must_use_figures=list(dict.fromkeys(figures)),
            )
        )

    if not planned:
        raise PlanError("计划里没有可用的 form")

    if required_forms:
        required = []
        for form_id in required_forms:
            if form_id not in valid_forms:
                raise PlanError(f"未知 form：{form_id}")
            if form_id not in required:
                required.append(form_id)
        by_form = {item.form: item for item in planned}
        planned = [
            by_form.get(form_id)
            or PlannedForm(
                form=form_id,
                reason="request required",
                angle="",
                brief="按请求和内容写；保持同一事实/范围。",
            )
            for form_id in required
        ]
    else:
        planned = planned[:4]

    constraints = [
        str(item).strip()
        for item in (data.get("shared_constraints") or [])
        if str(item).strip()
    ][:8]
    return LeadPlan(
        central_idea=str(data.get("central_idea") or "").strip(),
        reader_goal=str(data.get("reader_goal") or "").strip(),
        forms=planned,
        shared_constraints=constraints,
        notes=str(data.get("notes") or "").strip(),
    )


def fallback_plan(
    *,
    catalog: list[dict[str, str]],
    required_forms: list[str] | None = None,
    error: str = "",
) -> LeadPlan:
    valid_forms = _form_ids(catalog)
    if required_forms:
        forms = [item for item in required_forms if item in valid_forms]
    else:
        preferred = ["wechat_article", "xiaohongshu_note", "long_article"]
        forms = [item for item in preferred if item in valid_forms][:3]
        if not forms:
            forms = sorted(valid_forms)[:2]
    planned = [
        PlannedForm(
            form=form_id,
            reason="planner fallback",
            angle="按内容主线写",
            brief="按 skill 和 request 写；一条主线，保持同一事实/范围；不同产物角度不同。",
        )
        for form_id in forms
    ]
    if not planned:
        raise PlanError("没有可用的 form 可 fallback")
    return LeadPlan(
        central_idea="（planner 未返回；按内容主线写）",
        reader_goal="快速理解这件事的主线",
        forms=planned,
        shared_constraints=["同一事实/数字/范围", "不同产物角度不同，不要复制粘贴"],
        source="fallback",
        error=error or None,
    )


def plan_bundle(
    *,
    client,  # noqa: ANN001 - provider boundary; injected for tests
    skill: LoadedSkill,
    content: str,
    catalog: list[dict[str, str]],
    request: str,
    required_forms: list[str] | None = None,
    available_figures: list[str] | None = None,
    video_id: str,
) -> tuple[LeadPlan, str]:
    planner_request = request.strip()
    if required_forms:
        planner_request += "\n\n本次必须包含的产物：" + ", ".join(required_forms)
    if available_figures:
        planner_request += "\n\n可用图示（只能用这些）：" + ", ".join(
            available_figures
        )
    user = skill.render_user(
        request=planner_request,
        content=content,
        catalog=catalog_text(catalog),
    )
    try:
        response = client.complete(
            stage="bundle_plan",
            key=f"{video_id}:planner",
            system=skill.system,
            user=user,
            max_tokens=skill.max_tokens,
            temperature=skill.temperature,
        )
    except Exception as exc:  # noqa: BLE001 - fallback is explicit
        return (
            fallback_plan(
                catalog=catalog,
                required_forms=required_forms,
                error=f"{type(exc).__name__}: {exc}",
            ),
            "",
        )

    raw = response.text or ""
    try:
        return (
            parse_plan(
                raw,
                catalog=catalog,
                required_forms=required_forms,
                available_figures=available_figures,
            ),
            raw,
        )
    except PlanError as exc:
        return (
            fallback_plan(
                catalog=catalog,
                required_forms=required_forms,
                error=str(exc),
            ),
            raw,
        )
