"""Minimal writing pipeline: request + skill + consume index -> Writer -> audit.

Dry-run is the default.  ``run=True`` performs one Writer call; validation and
rendering are deterministic and reuse substrate v1 binding/quote hygiene.

The semantic verifier runs once, on the delivered article (after polish and
visuals).  If it is blocking, the pipeline spends its single bounded repair on
that delivered article, then re-validates binding/contract.  There is no
second verifier loop; the manifest records that the repaired article was not
re-audited.
"""

from __future__ import annotations

import difflib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..core.config import get_settings
from ..media.audit import load_article_frame_images
from ..media.planner import plan_visuals
from ..media.render import render_visual_plan
from .brief import write_brief
from .context import build_working_context
from .contract import audit_contract
from .polish import run_polish
from .request import load_request
from .skill import load_skill
from .source_map import build_source_map
from .validate import render_bundle, validate_article
from .verifier import run_verifier
from .writer import run_writer

MATERIAL_AXES = {
    "source",
    "claim_scope",
    "number",
    "mechanism",
    "term",
    "visual",
}


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(value, str):
        path.write_text(value, encoding="utf-8")
    else:
        path.write_text(
            json.dumps(value, ensure_ascii=False, indent=1), encoding="utf-8"
        )


def _brief_title(brief: dict[str, Any] | None) -> str:
    if not brief:
        return ""
    for item in brief.get("titles", []):
        if isinstance(item, dict) and item.get("chosen"):
            return str(item.get("text", ""))
    return ""


def _resolve_brief_mode(
    requested: str,
    request: dict[str, Any],
    source_map: dict[str, Any],
) -> dict[str, Any]:
    """Choose a brief mode; policy is advisory, overridable, not a hard gate."""
    if requested in {"none", "mini", "full"}:
        return {"mode": requested, "basis": "override"}
    if requested == "human_review":
        return {"mode": "full", "basis": "human_review", "human_review": True}
    if request.get("risk_level") == "high" or request.get("audit_level") not in {
        None,
        "none",
    }:
        return {"mode": "full", "basis": "risk_or_audit"}
    chars = int(source_map.get("text_chars", 0) or 0)
    segments = int(source_map.get("segment_count", 0) or 0)
    if chars <= 6000 and segments <= 8:
        return {"mode": "mini", "basis": "short_single_argument"}
    return {"mode": "full", "basis": "long_or_multi_topic"}


def _verifier_major(item: dict[str, Any]) -> bool:
    severity = item.get("severity")
    axis = item.get("axis")
    if severity in {"critical", "high"}:
        return True
    return severity == "medium" and axis in MATERIAL_AXES


def _report_blocking(report: dict[str, Any] | None) -> bool:
    return bool(
        report
        and report.get("status") == "complete"
        and (
            report.get("red_line")
            or any(_verifier_major(item) for item in report.get("findings", []))
        )
    )


def _material_counts(report: dict[str, Any] | None) -> dict[str, int]:
    findings = (report or {}).get("findings", [])
    return {
        "critical": sum(
            1 for item in findings if item.get("severity") == "critical"
        ),
        "high": sum(1 for item in findings if item.get("severity") == "high"),
        "material_medium": sum(
            1 for item in findings if _verifier_major(item)
        ),
        "total": len(findings),
    }


IMAGE_LINE = re.compile(r"!\[[^\]]*\]\(assets/([^)]+)\)")
CAPTION_TOKEN = ("caption", "图注", "画面", "image", "visual", "看哪里", "看这里")


def _image_captions(article: str) -> dict[str, tuple[int, str]]:
    """Map image path -> (caption line index, caption line) for an article."""
    lines = article.splitlines()
    captions: dict[str, tuple[int, str]] = {}
    for index, line in enumerate(lines):
        match = IMAGE_LINE.search(line)
        if not match:
            continue
        path = match.group(1)
        for look in range(index + 1, min(len(lines), index + 6)):
            stripped = lines[look].strip()
            if not stripped:
                continue
            if stripped.startswith("*") and stripped.endswith("*"):
                captions[path] = (look, lines[look])
            break
    return captions


def _restore_unrequested_captions(
    before: str,
    after: str,
    findings: dict[str, Any],
) -> tuple[str, list[str]]:
    """Undo caption edits the repair was not asked to make.

    A text-only repair can invent a new caption that no longer matches the
    image.  If no finding quotes the caption or asks for a visual change,
    restore the original caption while keeping the body repair.
    """
    before_captions = _image_captions(before)
    after_captions = _image_captions(after)
    findings_text = json.dumps(findings, ensure_ascii=False).lower()
    caption_related = any(token in findings_text for token in CAPTION_TOKEN)
    restore: dict[int, str] = {}
    restored: list[str] = []
    for path, (line_index, caption) in after_captions.items():
        original = before_captions.get(path)
        if not original or original[1] == caption:
            continue
        if caption_related and (
            path.lower() in findings_text
            or original[1].lower() in findings_text
            or caption.lower() in findings_text
        ):
            continue
        restore[line_index] = original[1]
        restored.append(path)
    if not restore:
        return after, []
    lines = after.splitlines()
    for index, caption in restore.items():
        if 0 <= index < len(lines):
            lines[index] = caption
    return "\n".join(lines), restored


def _repair_diff_guard(before: str, after: str) -> dict[str, Any]:
    """Keep repair bounded: no new sections/images, no wholesale rewrite."""
    before_lines = before.splitlines()
    after_lines = after.splitlines()
    h2_before = [line for line in before_lines if line.strip().startswith("## ")]
    h2_after = [line for line in after_lines if line.strip().startswith("## ")]
    images_before = len(re.findall(r"!\[[^\]]*\]\(", before))
    images_after = len(re.findall(r"!\[[^\]]*\]\(", after))
    similarity = difflib.SequenceMatcher(None, before, after).ratio()
    changed = 1.0 - similarity
    problems: list[str] = []
    if len(h2_before) != len(h2_after):
        problems.append("heading_count_changed")
    if images_after > images_before:
        problems.append("new_image_added")
    # changed_ratio is diagnostic, not a hard gate: a long repair can be
    # legitimate.  Structural changes (new sections/images) are the guard.
    return {
        "ok": not problems,
        "changed_ratio": round(changed, 4),
        "problems": problems,
    }


def _repair_findings(
    validation: dict[str, Any],
    contract: dict[str, Any],
    verifier_report: dict[str, Any] | None,
) -> dict[str, Any]:
    binding = validation.get("binding", {})
    return {
        "unsupported_facts": binding.get("unsupported_facts", []),
        "quote_unbound": binding.get("quote_unbound", []),
        "outside_input_facts": binding.get("outside_input_facts", []),
        "outside_input_quotes": binding.get("outside_input_quotes", []),
        "structure": validation.get("structure", {}),
        "reader_hygiene": validation.get("reader_hygiene", {}),
        "contract": contract.get("findings", []),
        "verifier": (verifier_report or {}).get("findings", []),
    }


def _filter_media_assets(
    article: str, media_assets: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Drop assets the repaired article no longer references."""
    referenced = set(re.findall(r"\]\(assets/([^)]+)\)", article))
    kept: list[dict[str, Any]] = []
    for asset in media_assets:
        path = asset.get("path")
        if not path:
            kept.append(asset)
            continue
        if Path(str(path)).name in referenced:
            kept.append(asset)
    return kept


def run_pipeline(
    *,
    request_path: Path,
    skill_dir: Path,
    index_path: Path,
    edited_text_path: Path,
    pack_path: Path,
    sentences_path: Path,
    source_map_path: Path,
    out_dir: Path,
    run: bool = False,
    profile: str = "auto",
    model: str | None = None,
    temperature: float = 0.3,
    max_tokens: int | None = None,
    no_cache: bool = False,
    visuals: bool = True,
    data_root: Path | None = None,
    visual_provider: Any | None = None,
    verifier: bool = True,
    verifier_provider: Any | None = None,
    verify_after_repair: bool = False,
    polish: bool = True,
    polish_provider: Any | None = None,
    brief_mode: str = "auto",
    brief_include_full_text: bool | None = None,
) -> dict[str, Any]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    request = load_request(Path(request_path))
    skill = load_skill(Path(skill_dir))
    index = _read_json(Path(index_path))
    edited_text = Path(edited_text_path).read_text(encoding="utf-8-sig")
    pack = _read_json(Path(pack_path))
    sentences = _read_json(Path(sentences_path)).get("sentences", [])
    source_map = _read_json(Path(source_map_path))

    context = build_working_context(
        index, request, edited_text, profile=profile, skill=skill.manifest
    )
    _write(out_dir / "context.json", context)
    planning_source_map = build_source_map(
        index,
        edited_text,
        max_anchors=20,
        max_numbers=12,
    )
    _write(out_dir / "source_map.json", planning_source_map)
    brief_decision = _resolve_brief_mode(brief_mode, request, planning_source_map)
    brief: dict[str, Any] | None = None
    if run and brief_decision["mode"] != "none":
        include_full_text = (
            brief_decision["mode"] == "full"
            if brief_include_full_text is None
            else brief_include_full_text
        )
        brief = write_brief(
            request,
            planning_source_map,
            skill,
            out_dir / "brief",
            run=True,
            model=model,
            evidence_text=context.get("text", ""),
            include_full_text=include_full_text,
        )
        _write(out_dir / "brief" / "brief.json", brief)
    writer_brief = brief if brief and brief.get("status") == "complete" else None

    writer_result = run_writer(
        request=request,
        skill=skill,
        context=context,
        out_dir=out_dir / "writer",
        run=run,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        no_cache=no_cache,
        writing_brief=writer_brief,
    )
    manifest: dict[str, Any] = {
        "schema": "writing-pipeline-v1",
        "status": writer_result["status"],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "request_hash": request.get("request_hash", ""),
        "verifier_mode": "final_only",
        "skill": {
            "skill_id": skill.skill_id,
            "version": skill.version,
            "status": skill.status,
            "content_hash": skill.content_hash,
            "hash_ok": skill.hash_ok,
        },
        "context": {
            "profile": context.get("profile", ""),
            "status": context.get("status", ""),
            "context_hash": context.get("context_hash", ""),
            "selection": context.get("selection", {}),
            "budget": context.get("budget", {}),
        },
        "writer_status": writer_result["status"],
        "source_map": {
            "status": "complete",
            "hash": planning_source_map.get("source_map_hash", ""),
            "chars": planning_source_map.get("text_chars", 0),
            "sections": len(planning_source_map.get("sections", [])),
            "anchors": len(planning_source_map.get("anchors", [])),
            "numbers": len(planning_source_map.get("numbers", [])),
            "topology": planning_source_map.get("topology", "unknown"),
            "source_metadata": planning_source_map.get("source_metadata", {}),
        },
        "brief": {
            "mode": brief_decision["mode"],
            "basis": brief_decision["basis"],
            "human_review": brief_decision.get("human_review", False),
            "status": (brief or {}).get("status")
            or ("skipped" if brief_decision["mode"] == "none" else "dry_run"),
            "shape": (brief or {}).get("shape", ""),
            "title": _brief_title(brief),
            "moves": len((brief or {}).get("spine", [])),
            "hash": (brief or {}).get("brief_hash", ""),
            "problems": (brief or {}).get("problems", []),
            "title_check": (brief or {}).get("title_check", {}),
        },
    }
    if writer_result["status"] != "complete":
        _write(out_dir / "manifest.json", manifest)
        return {
            "status": writer_result["status"],
            "out_dir": str(out_dir),
            "manifest": manifest,
        }

    article = writer_result["article"]
    validation = validate_article(
        article,
        edited_text=edited_text,
        pack=pack,
        sentences=sentences,
        source_map=source_map,
    )
    contract = audit_contract(article, brief=writer_brief, source_map=source_map)
    _write(out_dir / "contract_report.json", contract)

    polish_report: dict[str, Any] | None = None
    if run and polish:
        polish_result = run_polish(
            article,
            edited_text,
            writer_brief,
            request,
            out_dir / "polish",
            run=True,
            provider=polish_provider,
            model=model,
        )
        polish_report = {
            key: value for key, value in polish_result.items() if key != "article"
        }
        if (
            polish_result.get("status") == "complete"
            and polish_result.get("article")
        ):
            polished = polish_result["article"]
            polished_validation = validate_article(
                polished,
                edited_text=edited_text,
                pack=pack,
                sentences=sentences,
                source_map=source_map,
            )
            polish_report["validation_status"] = polished_validation["status"]
            if polished_validation["status"] == "complete":
                article = polished
                validation = polished_validation
            else:
                polish_report["discarded"] = "binding_or_structure"
        _write(out_dir / "polish_report.json", polish_report)
        contract = audit_contract(
            article, brief=writer_brief, source_map=source_map
        )
        _write(out_dir / "contract_report.json", contract)

    brief_shape = str((writer_brief or {}).get("shape", "") or "")
    try:
        media_max = int((request.get("media_policy") or {}).get("max_assets") or 6)
    except (TypeError, ValueError):
        media_max = 6
    if media_max < 1:
        media_max = 6
    if brief_shape in {"narrative", "mixed"}:
        media_max = min(media_max, 2)

    visual_plan: dict[str, Any] | None = None
    media_assets: list[dict[str, Any]] = []
    if visuals:
        visual_plan = plan_visuals(
            article,
            index,
            request,
            out_dir / "visual",
            run=run,
            provider=visual_provider,
            max_visuals=media_max,
            genre=brief_shape,
            model=model,
        )
        _write(out_dir / "visual" / "plan.json", visual_plan)
        if visual_plan.get("visuals"):
            root = data_root or get_settings().data_root
            rendered_media = render_visual_plan(
                article,
                visual_plan,
                index,
                out_dir / "output",
                data_root=root,
                video_id=str(pack.get("video_id") or index.get("video_id", "")),
            )
            article = rendered_media["article"]
            media_assets = rendered_media["assets"]
            _write(out_dir / "visual" / "render.json", rendered_media)

    validation = validate_article(
        article,
        edited_text=edited_text,
        pack=pack,
        sentences=sentences,
        source_map=source_map,
    )
    _write(out_dir / "validation.json", validation)
    contract_final = audit_contract(
        article, brief=writer_brief, source_map=source_map
    )
    _write(out_dir / "contract_report.json", contract_final)

    verifier_final_report: dict[str, Any] | None = None
    verifier_unverified = False
    final_verifier_blocking = False
    image_rows: list[dict[str, Any]] = []
    image_skipped: list[dict[str, Any]] = []
    if run and verifier:
        image_rows, image_skipped = load_article_frame_images(
            article, out_dir / "output" / "assets"
        )
        verifier_final_report = run_verifier(
            article,
            edited_text,
            writer_brief,
            source_map,
            request,
            out_dir / "verifier_final",
            run=True,
            provider=verifier_provider,
            model=model,
            images=image_rows,
            visual_plan=visual_plan,
        )
        _write(out_dir / "verifier_final_report.json", verifier_final_report)
        # Compatibility pointer for readers that still look for the old name.
        _write(out_dir / "verifier_report.json", verifier_final_report)
        if verifier_final_report.get("status") == "complete":
            final_verifier_blocking = _report_blocking(verifier_final_report)
        else:
            verifier_unverified = True

    repair_info: dict[str, Any] | None = None
    post_repair_report: dict[str, Any] | None = None
    post_images: list[dict[str, Any]] = []
    post_skipped: list[dict[str, Any]] = []
    candidate_article: str | None = None
    candidate_validation: dict[str, Any] | None = None
    candidate_contract: dict[str, Any] | None = None
    needs_repair = (
        validation["status"] != "complete"
        or contract_final.get("status") == "partial"
        or final_verifier_blocking
    )
    if run and needs_repair:
        findings = _repair_findings(
            validation, contract_final, verifier_final_report
        )
        repair_result = run_writer(
            request=request,
            skill=skill,
            context=context,
            out_dir=out_dir / "writer_repair",
            run=True,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            no_cache=no_cache,
            repair_draft=article,
            repair_findings=findings,
            writing_brief=writer_brief,
        )
        repair_manifest = repair_result.get("manifest", {})
        repair_info = {
            "trigger": {
                "validation": validation["status"],
                "contract": contract_final.get("status"),
                "verifier_blocking": final_verifier_blocking,
            },
            "status": repair_result["status"],
            "out_dir": str(out_dir / "writer_repair"),
            "accepted": False,
            "verification_after_repair": "not_reaudited",
            "usage": repair_manifest.get("usage"),
            "latency_ms": repair_manifest.get("latency_ms"),
            "model": repair_manifest.get("model"),
        }
        if repair_result["status"] == "complete":
            repaired, restored_captions = _restore_unrequested_captions(
                article, repair_result["article"], findings
            )
            if restored_captions:
                repair_info["restored_captions"] = restored_captions
            repaired_validation = validate_article(
                repaired,
                edited_text=edited_text,
                pack=pack,
                sentences=sentences,
                source_map=source_map,
            )
            repair_info["validation_status"] = repaired_validation["status"]
            if repaired_validation["status"] == "complete":
                guard = _repair_diff_guard(article, repaired)
                repair_info["diff_guard"] = guard
                if guard["ok"]:
                    candidate_article = repaired
                    candidate_validation = repaired_validation
                    candidate_contract = audit_contract(
                        repaired, brief=writer_brief, source_map=source_map
                    )
                else:
                    repair_info["rejected"] = "diff_guard"
            else:
                repair_info["rejected"] = "binding_or_structure"

    if candidate_article is not None:
        if run and verifier and verify_after_repair:
            post_images, post_skipped = load_article_frame_images(
                candidate_article, out_dir / "output" / "assets"
            )
            post_repair_report = run_verifier(
                candidate_article,
                edited_text,
                writer_brief,
                source_map,
                request,
                out_dir / "verifier_final_after",
                run=True,
                provider=verifier_provider,
                model=model,
                images=post_images,
                visual_plan=visual_plan,
            )
            _write(out_dir / "verifier_final_after_report.json", post_repair_report)
            repair_info["verification_after_repair"] = "reaudited"
            repair_info["verifier_after"] = {
                "status": post_repair_report.get("status"),
                "red_line": bool(post_repair_report.get("red_line")),
                "findings": len(post_repair_report.get("findings", [])),
                "blocking": _report_blocking(post_repair_report),
                "visual_status": post_repair_report.get("visual_status"),
                "images": len(post_images),
                "images_skipped": post_skipped,
                "path": str(out_dir / "verifier_final_after_report.json"),
            }
            before_counts = _material_counts(verifier_final_report)
            after_counts = _material_counts(post_repair_report)
            repair_info["audit_comparison"] = {
                "before": before_counts,
                "after": after_counts,
            }
            if post_repair_report.get("status") != "complete":
                repair_info["rejected"] = "post_audit_unverified"
            elif (
                after_counts["critical"] > before_counts["critical"]
                or after_counts["high"] > before_counts["high"]
                or after_counts["material_medium"]
                > before_counts["material_medium"]
            ):
                repair_info["rejected"] = "post_audit_worse"
            else:
                article = candidate_article
                validation = candidate_validation
                contract_final = candidate_contract
                _write(out_dir / "contract_report.json", contract_final)
                repair_info["accepted"] = True
        else:
            article = candidate_article
            validation = candidate_validation
            contract_final = candidate_contract
            _write(out_dir / "contract_report.json", contract_final)
            repair_info["accepted"] = True

    media_assets = _filter_media_assets(article, media_assets)
    repair_accepted = bool(repair_info and repair_info.get("accepted"))
    delivered_verifier_report = (
        post_repair_report
        if repair_accepted and post_repair_report
        else verifier_final_report
    )
    delivered_blocking = _report_blocking(delivered_verifier_report)
    delivered_unverified = bool(
        delivered_verifier_report
        and delivered_verifier_report.get("status") != "complete"
    )
    semantic_failed = (
        contract_final.get("status") == "partial"
        or delivered_blocking
        or delivered_unverified
    )
    final_status = (
        "partial"
        if validation["status"] != "complete" or semantic_failed
        else "complete"
    )
    final_failures = list(validation["failures"])
    if contract_final.get("status") == "partial" and "contract" not in final_failures:
        final_failures.append("contract")
    if delivered_blocking and "verifier" not in final_failures:
        final_failures.append("verifier")
    if delivered_unverified and "verifier_unverified" not in final_failures:
        final_failures.append("verifier_unverified")
    if (
        repair_accepted
        and not post_repair_report
        and "repair_not_reaudited" not in final_failures
    ):
        final_failures.append("repair_not_reaudited")
    rendered = render_bundle(
        out_dir / "output",
        request=request,
        skill=skill,
        context=context,
        validation=validation,
        visual_plan=visual_plan,
        media_assets=media_assets,
    )
    manifest.update(
        {
            "status": final_status,
            "validation_status": validation["status"],
            "failures": final_failures,
            "binding_status": validation["binding"].get("status"),
            "repair": repair_info,
            "contract": {
                "status": contract_final.get("status"),
                "blocking": len(contract_final.get("blocking", [])),
                "findings": len(contract_final.get("findings", [])),
                "path": str(out_dir / "contract_report.json"),
            },
            "verifier": {
                "status": "not_run",
                "red_line": False,
                "findings": 0,
                "blocking": False,
                "usage": None,
                "path": None,
                "note": "initial verifier removed; see verifier_final",
            },
            "verifier_final": {
                "executed": verifier_final_report is not None,
                "status": (verifier_final_report or {}).get("status"),
                "red_line": bool(
                    (verifier_final_report or {}).get("red_line")
                ),
                "findings": len(
                    (verifier_final_report or {}).get("findings", [])
                ),
                "blocking": final_verifier_blocking,
                "unverified": verifier_unverified,
                "drove_repair": final_verifier_blocking,
                "visual_status": (verifier_final_report or {}).get(
                    "visual_status"
                ),
                "images": len(image_rows),
                "images_skipped": image_skipped,
                "usage": (verifier_final_report or {}).get("usage"),
                "path": (
                    str(out_dir / "verifier_final_report.json")
                    if verifier_final_report
                    else None
                ),
            },
            "verifier_final_after": {
                "executed": post_repair_report is not None,
                "used_for_delivery": bool(
                    repair_accepted and post_repair_report
                ),
                "status": (post_repair_report or {}).get("status"),
                "red_line": bool((post_repair_report or {}).get("red_line")),
                "findings": len((post_repair_report or {}).get("findings", [])),
                "blocking": _report_blocking(post_repair_report),
                "unverified": bool(
                    post_repair_report
                    and post_repair_report.get("status") != "complete"
                ),
                "visual_status": (post_repair_report or {}).get(
                    "visual_status"
                ),
                "images": len(post_images),
                "images_skipped": post_skipped,
                "usage": (post_repair_report or {}).get("usage"),
                "path": (
                    str(out_dir / "verifier_final_after_report.json")
                    if post_repair_report
                    else None
                ),
            },
            "polish": {
                "status": (polish_report or {}).get("status"),
                "validation_status": (polish_report or {}).get(
                    "validation_status"
                ),
                "discarded": (polish_report or {}).get("discarded"),
                "usage": (polish_report or {}).get("usage"),
                "path": (
                    str(out_dir / "polish_report.json")
                    if polish_report
                    else None
                ),
            },
            "visuals": {
                "status": (visual_plan or {}).get("status"),
                "count": len((visual_plan or {}).get("visuals", [])),
                "assets": len(media_assets),
                "max_assets": media_max,
                "genre": brief_shape,
                "usage": (visual_plan or {}).get("usage"),
            },
            "output": rendered,
            "writer": {
                "usage": writer_result["manifest"].get("usage"),
                "latency_ms": writer_result["manifest"].get("latency_ms"),
                "model": writer_result["manifest"].get("model"),
                "output_hash": writer_result["manifest"].get("output_hash"),
            },
        }
    )
    _write(out_dir / "manifest.json", manifest)
    return {
        "status": final_status,
        "out_dir": str(out_dir),
        "manifest": manifest,
        "output": rendered,
    }
