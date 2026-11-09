"""Visual audit for keyframe candidates, using the writing model's vision.

The evidence layer only adapts inputs (transcript + frames).  This module runs
in the writing layer: it shows candidate frames to ``deepseek-flash`` (which
supports image input) and applies the keyframe gate.  Only approved frames are
left in the run's content copy, so the planner/writer cannot pick an audited-
out frame by accident.

No local OCR/ASR and no DashScope VLM understanding here.
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..core.config import get_settings
from ..providers.llm import DeepSeekLLM, ImageInput

FRAME_RE = re.compile(
    r"(?:画面参考|图示)\s*(\d+)\s*(?:（可选，非必用）)?[:：](.*?)；图：(figures/[^）\s]+)"
)
ALLOWED_TYPES = {"operation", "object", "scene", "change", "detail", "evidence"}
REJECT_TYPES = {"person", "ui", "other"}

AUDIT_SYSTEM = "你是严格的视觉插图审核员。只根据图片和给定正文判断，不猜测画面外的内容。"

AUDIT_USER = """判断这张候选图是否适合作为文章插图。

正文上下文：
{context}

内容稿里的画面说明：{note}

只输出严格 JSON（不要 Markdown、不要解释）：
{{
  "scene_type": "operation|object|scene|change|detail|evidence|person|ui|other",
  "has_person": false,
  "has_watermark": false,
  "quality": "clear|ok|poor",
  "self_contained": true,
  "info_value": true,
  "caption": "不超过20个汉字，只描述画面本身",
  "reason": "不超过30个汉字"
}}

scene_type：operation=真实操作/动作；object=具体物体/产品/设备/食材；
scene=真实场景/环境；change=前后变化/结果；detail=局部细节/材质/手法；
evidence=实验/测试/现场演示的视觉证据；person=可识别人物；ui=屏幕/界面/PPT/代码；
other=其他。

规则：
- 有关键帧价值才通过：真实操作、具体对象、真实场景、前后变化、细节、视觉证据。
- 人物出镜、平台水印/logo/遮挡性贴纸、模糊/遮挡/构图混乱、纯装饰、屏幕/UI 为主，一律不通过。
- self_contained：脱离视频上下文也能理解画面在表达什么。
- info_value：画面提供实际信息，不是纯装饰/表情/空镜。
- 不要为了让图通过而放宽标准。
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _extract_json(text: str) -> dict[str, Any]:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("no JSON object in response")
    data = json.loads(text[start : end + 1])
    if not isinstance(data, dict):
        raise ValueError("audit response is not an object")
    return data


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value or "").strip().lower() in {"true", "1", "yes", "y", "是"}


def audit_decision(record: dict[str, Any]) -> bool:
    return (
        record.get("scene_type") in ALLOWED_TYPES
        and not record.get("has_person")
        and not record.get("has_watermark")
        and record.get("quality") == "clear"
        and bool(record.get("self_contained"))
        and bool(record.get("info_value"))
    )


def normalize_audit(raw: dict[str, Any]) -> dict[str, Any]:
    scene_type = str(raw.get("scene_type") or "other").strip().lower()
    if scene_type not in ALLOWED_TYPES | REJECT_TYPES:
        scene_type = "other"
    quality = str(raw.get("quality") or "poor").strip().lower()
    if quality not in {"clear", "ok", "poor"}:
        quality = "poor"
    record = {
        "scene_type": scene_type,
        "has_person": _as_bool(raw.get("has_person")),
        "has_watermark": _as_bool(raw.get("has_watermark")),
        "quality": quality,
        "self_contained": _as_bool(raw.get("self_contained")),
        "info_value": _as_bool(raw.get("info_value")),
        "caption": str(raw.get("caption") or "").strip()[:40],
        "reason": str(raw.get("reason") or "").strip()[:60],
    }
    record["use_keyframe"] = audit_decision(record)
    return record


def extract_candidates(content: str) -> list[dict[str, Any]]:
    """Return candidates with the paragraph context around each note."""
    blocks = content.split("\n\n")
    candidates: list[dict[str, Any]] = []
    for index, block in enumerate(blocks):
        for match in FRAME_RE.finditer(block):
            context = "\n\n".join(blocks[max(0, index - 1) : index + 1])[:1200]
            candidates.append(
                {
                    "index": int(match.group(1)),
                    "note": match.group(2).strip(),
                    "file": match.group(3),
                    "context": context,
                }
            )
    return candidates


def filter_content_for_approved(
    content: str, approved: list[dict[str, Any]]
) -> str:
    """Remove audited-out frame notes; relabel approved ones.

    The original cached content stays untouched; only the run copy is filtered.
    """
    by_file = {item["file"]: item for item in approved}
    lines: list[str] = []
    for line in content.splitlines():
        if "画面参考" not in line and "图示" not in line:
            lines.append(line)
            continue
        match = FRAME_RE.search(line)
        if not match:
            lines.append(line)
            continue
        item = by_file.get(match.group(3))
        if item is None:
            # drop the whole note line; blank lines around it are harmless
            continue
        caption = item.get("caption") or match.group(2)
        lines.append(
            f"关键帧候选（已通过视觉审计，可选）：{caption}；图：{match.group(3)}"
        )
    return "\n".join(lines)


def audit_content(
    content_path: Path,
    *,
    client: DeepSeekLLM,
    max_frames: int = 6,
    out_path: Path | None = None,
) -> dict[str, Any]:
    """Audit candidates with the vision model and write ``visual_audit.json``."""
    content_path = Path(content_path)
    content = content_path.read_text(encoding="utf-8")
    candidates = extract_candidates(content)[:max_frames]
    records: list[dict[str, Any]] = []
    errors: list[str] = []
    for candidate in candidates:
        image_path = content_path.parent / candidate["file"]
        if not image_path.is_file():
            errors.append(f"missing image: {candidate['file']}")
            continue
        image = ImageInput(
            data=image_path.read_bytes(),
            media_type="image/jpeg",
            name=Path(candidate["file"]).stem,
        )
        try:
            response = client.complete(
                stage="visual_audit",
                key=f"visual_audit:{candidate['file']}",
                system=AUDIT_SYSTEM,
                user=AUDIT_USER.format(
                    context=candidate["context"], note=candidate["note"]
                ),
                images=[image],
                max_tokens=4096,
                temperature=0.0,
            )
            audit = normalize_audit(_extract_json(response.text))
            records.append({**candidate, **audit})
        except Exception as exc:  # noqa: BLE001 - audit is advisory
            errors.append(
                f"{candidate['file']}: {type(exc).__name__}: {exc}"[:300]
            )
    approved = [item for item in records if item.get("use_keyframe")]
    result = {
        "schema_version": "visual-audit-v1",
        "created_at": _now(),
        "content_path": str(content_path),
        "candidate_count": len(candidates),
        "approved_count": len(approved),
        "approved": approved,
        "candidates": records,
        "errors": errors,
    }
    destination = out_path or (content_path.parent / "visual_audit.json")
    destination.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    result["path"] = str(destination)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit keyframe candidates with vision")
    parser.add_argument("--content", type=Path, required=True)
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--max-frames", type=int, default=6)
    args = parser.parse_args(argv)
    settings = get_settings()
    if not settings.provider_configured:
        raise SystemExit("provider not configured")
    client = DeepSeekLLM(settings)
    result = audit_content(
        args.content,
        client=client,
        max_frames=args.max_frames,
        out_path=args.out,
    )
    print(json.dumps(
        {
            "path": result["path"],
            "candidate_count": result["candidate_count"],
            "approved_count": result["approved_count"],
            "approved": [item["file"] for item in result["approved"]],
            "errors": result["errors"],
        },
        ensure_ascii=False,
        indent=2,
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
