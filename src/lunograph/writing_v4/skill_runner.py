"""Run one writing skill from its manifest.  One writer call, no pipeline.

The article path in :mod:`run` predates multi-form support.  This runner keeps
the same provider boundary but reads the form (skill, examples, user prompt,
source-line policy, floor-check profile) from a small ``manifest.json``.  Form
differences live in the skill; the runner stays generic.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..core.config import get_settings
from ..providers.llm import DeepSeekLLM
from .form_checks import check_form

MANIFEST_REQUIRED = ("id", "version", "skill")
DEFAULTS = {
    "forms": [],
    "examples": "",
    "prompt": "",
    "user_template": "",
    "source_line": "none",
    "check_profile": "none",
    "require_source": True,
    "quality_rubric": "",
    "inputs": ["content.md"],
    "max_tokens": 8192,
    "temperature": 0.6,
    "output_name": "output.md",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _sha_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def load_manifest(path: Path) -> dict[str, Any]:
    """Load a skill manifest and resolve its relative file references."""
    path = path.resolve()
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    for key in MANIFEST_REQUIRED:
        if not data.get(key):
            raise ValueError(f"manifest missing {key!r}: {path}")
    manifest = {**DEFAULTS, **data}
    base = path.parent
    for key in ("skill", "examples", "prompt"):
        value = manifest.get(key)
        if value:
            manifest[key] = str((base / value).resolve())
    manifest["manifest_path"] = str(path)
    return manifest


def build_system(manifest: dict[str, Any]) -> str:
    skill = _read(Path(manifest["skill"]))
    examples = ""
    if manifest.get("examples"):
        examples_path = Path(manifest["examples"])
        if examples_path.exists():
            examples = _read(examples_path)
    if examples:
        return f"{skill}\n\n---\n\n# 例子参考\n\n{examples}"
    return skill


def build_user(manifest: dict[str, Any], *, request: str, content: str) -> str:
    template = manifest.get("user_template") or ""
    if manifest.get("prompt"):
        template = _read(Path(manifest["prompt"]))
    if not template:
        raise ValueError("manifest needs prompt or user_template")
    return (
        template.replace("{request}", request or "（未指定；按 skill 默认读者）")
        .replace("{content}", content)
    )


def _source_line(
    policy: str,
    *,
    settings,  # noqa: ANN001 - Settings dataclass
    video_id: str,
    source_path: Path | None = None,
) -> str:
    if policy in {"", "none"}:
        return ""
    source_file = source_path or settings.data_root / video_id / "source.json"
    source: dict[str, Any] = {}
    if source_file.exists():
        source = json.loads(source_file.read_text(encoding="utf-8-sig"))
    title = str(source.get("title") or video_id)
    uploader = str(source.get("uploader") or "")
    named = title != video_id and not (not uploader and title.startswith("BV"))
    if policy == "article":
        if named:
            return f"本文根据 B 站视频《{title}》（UP 主：{uploader}）整理；画面截取自原视频。"
        return f"本文根据 B 站视频（{title}）整理；画面截取自原视频。"
    if policy == "social":
        if named:
            return f"素材来源：B 站视频《{title}》（UP 主：{uploader}）。"
        return f"素材来源：B 站视频（{video_id}）。"
    if policy == "script":
        if named:
            return f"素材来源：B 站视频《{title}》（UP 主：{uploader}）；画面仅作分镜参考。"
        return f"素材来源：B 站视频（{video_id}）；画面仅作分镜参考。"
    raise ValueError(f"unknown source_line policy: {policy}")


def _write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def _append_receipt(path: Path, event: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False) + "\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run one writing skill from a manifest.")
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--video-id", required=True)
    parser.add_argument("--content", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--request", default="")
    parser.add_argument("--request-file", type=Path, default=None)
    parser.add_argument("--source-json", type=Path, default=None)
    parser.add_argument("--temperature", type=float, default=None)
    parser.add_argument("--max-tokens", type=int, default=None)
    args = parser.parse_args(argv)

    settings = get_settings()
    if not settings.provider_configured:
        raise SystemExit("provider not configured (DEEPSEEK_API_KEY / DEEPSEEK_MODEL)")

    manifest = load_manifest(args.manifest)
    request = args.request
    if args.request_file is not None:
        request = args.request_file.read_text(encoding="utf-8").strip()
    content = _read(args.content)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    receipts_path = args.out_dir / "receipts.jsonl"
    if receipts_path.exists():
        receipts_path.unlink()

    skill_text = _read(Path(manifest["skill"]))
    system = build_system(manifest)
    user = build_user(manifest, request=request, content=content)
    _append_receipt(
        receipts_path,
        {
            "ts": _now(),
            "event": "skill_load",
            "skill_id": manifest["id"],
            "skill_version": manifest["version"],
            "skill_sha256": _sha_text(skill_text),
            "system_sha256": _sha_text(system),
            "status": "succeeded",
        },
    )
    _append_receipt(
        receipts_path,
        {
            "ts": _now(),
            "event": "content_read",
            "path": str(args.content),
            "sha256": _sha_file(args.content),
            "chars": len(content),
            "status": "succeeded",
        },
    )

    temperature = (
        args.temperature if args.temperature is not None else float(manifest["temperature"])
    )
    max_tokens = (
        args.max_tokens if args.max_tokens is not None else int(manifest["max_tokens"])
    )

    client = DeepSeekLLM(settings)
    response = client.complete(
        stage=f"writing_v4_{manifest['id']}",
        key=args.video_id,
        system=system,
        user=user,
        max_tokens=max_tokens,
        temperature=temperature,
    )

    run_id = f"{args.video_id}_{manifest['id']}_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    started_at = _now()
    output_name = manifest.get("output_name") or "output.md"
    output_path = args.out_dir / output_name
    meta_path = args.out_dir / "response_meta.json"
    run_manifest_path = args.out_dir / "run_manifest.json"

    if not response.text.strip():
        _append_receipt(
            receipts_path,
            {
                "ts": _now(),
                "event": "writer",
                "status": "failed",
                "finish_reason": response.finish_reason,
            },
        )
        _write_json(
            run_manifest_path,
            {
                "schema": "writing-v4-run-v1",
                "run_id": run_id,
                "video_id": args.video_id,
                "skill": {
                    "id": manifest["id"],
                    "version": manifest["version"],
                    "sha256": _sha_text(skill_text),
                },
                "content": {"path": str(args.content), "sha256": _sha_file(args.content)},
                "status": "failed",
                "error": "empty writer response",
                "started_at": started_at,
                "ended_at": _now(),
            },
        )
        return 1

    source_line = _source_line(
        manifest.get("source_line", "none"),
        settings=settings,
        video_id=args.video_id,
        source_path=args.source_json,
    )
    output = response.text.strip() + "\n"
    if source_line:
        output = output.rstrip() + "\n\n---\n\n" + source_line + "\n"
    output_path.write_text(output, encoding="utf-8")

    check = check_form(
        output_path,
        profile=manifest.get("check_profile", "none"),
        repo_root=settings.project_root,
        require_source=bool(manifest.get("require_source", True)),
    )
    _write_json(args.out_dir / "checks.json", check)

    meta = {
        "run_id": run_id,
        "video_id": args.video_id,
        "skill": manifest["id"],
        "skill_version": manifest["version"],
        "skill_sha256": _sha_text(skill_text),
        "content": str(args.content),
        "content_sha256": _sha_file(args.content),
        "model": response.model,
        "provider": response.provider,
        "finish_reason": response.finish_reason,
        "latency_ms": response.latency_ms,
        "usage": response.usage.as_dict(),
        "temperature": temperature,
        "max_tokens": max_tokens,
        "output_chars": len(output),
    }
    _write_json(meta_path, meta)
    _append_receipt(
        receipts_path,
        {
            "ts": _now(),
            "event": "writer",
            "status": "succeeded",
            "model": response.model,
            "usage": response.usage.as_dict(),
            "latency_ms": response.latency_ms,
            "finish_reason": response.finish_reason,
        },
    )
    _append_receipt(
        receipts_path,
        {
            "ts": _now(),
            "event": "form_check",
            "profile": manifest.get("check_profile", "none"),
            "ok": check["ok"],
            "issues": check["issues"],
        },
    )

    status = "succeeded" if check["ok"] else "partial"
    _write_json(
        run_manifest_path,
        {
            "schema": "writing-v4-run-v1",
            "run_id": run_id,
            "video_id": args.video_id,
            "skill": {
                "id": manifest["id"],
                "version": manifest["version"],
                "sha256": _sha_text(skill_text),
                "manifest": manifest["manifest_path"],
            },
            "content": {
                "path": str(args.content),
                "sha256": _sha_file(args.content),
                "chars": len(content),
            },
            "status": status,
            "started_at": started_at,
            "ended_at": _now(),
            "stages": {
                "skill_load": {"status": "succeeded"},
                "writer": {
                    "status": "succeeded",
                    "model": response.model,
                    "usage": response.usage.as_dict(),
                    "latency_ms": response.latency_ms,
                    "finish_reason": response.finish_reason,
                },
                "checks": {
                    "status": "succeeded" if check["ok"] else "failed",
                    "issues": check["issues"],
                    "warnings": check["warnings"],
                },
            },
            "decisions": [
                {
                    "stage": "skill_route",
                    "question": "which writing form?",
                    "selected": manifest["id"],
                    "basis": "explicit request",
                },
                {
                    "stage": "source_line",
                    "question": "how to attribute the source?",
                    "selected": manifest.get("source_line", "none"),
                    "basis": "skill manifest",
                },
            ],
            "artifacts": {
                output_name: {"sha256": _sha_file(output_path), "bytes": output_path.stat().st_size},
                "checks.json": {"sha256": _sha_file(args.out_dir / "checks.json")},
                "response_meta.json": {"sha256": _sha_file(meta_path)},
            },
            "usage": response.usage.as_dict(),
        },
    )
    print(json.dumps({**meta, "check": check}, ensure_ascii=False, indent=2))
    return 0 if check["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
