"""One-call form writer.

The writer sees the content manuscript (the thing itself), a form skill, and
a short request.  It writes once.  The runner then adds the source line,
copies figures, renders SVG placeholders, and writes metadata.  There is no
draft stage, editor, checker or word list.

The writer never sees the source machinery: no video title, uploader,
timecodes, frame IDs or material-packet labels.
"""

from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..core.config import Settings, get_settings
from ..core.hashing import sha256_text
from ..providers.llm import DeepSeekLLM
from .skills import LoadedSkill, load_skill
from .svg_pass import build_svg_assets

TITLE_COMMENT = re.compile(
    r"<!--\s*title_candidates?\s*:\s*(.*?)\s*-->", re.IGNORECASE | re.DOTALL
)
READER_CONTRACT_COMMENT = re.compile(
    r"<!--\s*reader_contract\s*:\s*(.*?)\s*-->", re.IGNORECASE | re.DOTALL
)
IMAGE_REF = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")
SIDECAR_REF = re.compile(r"^\s*[-*]\s*(figures/[^\s:：]+)", re.MULTILINE)
SOURCE_TAIL = re.compile(r"\n*---\s*\n+\s*(本文根据|本脚本根据|内容参考)[^\n]*$")


class WriterError(RuntimeError):
    kind = "writer_error"


@dataclass
class FormResult:
    form: str
    skill_id: str
    skill_version: str
    role: str
    status: str
    output: str
    output_chars: int
    title_candidates: list[str] = field(default_factory=list)
    figures: list[str] = field(default_factory=list)
    figures_referenced: list[str] = field(default_factory=list)
    missing_figures: list[str] = field(default_factory=list)
    svg_assets: list[str] = field(default_factory=list)
    reader_contract: dict[str, Any] | None = None
    usage: dict[str, int] = field(default_factory=dict)
    latency_ms: int = 0
    error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "form": self.form,
            "skill_id": self.skill_id,
            "skill_version": self.skill_version,
            "role": self.role,
            "status": self.status,
            "output": self.output,
            "output_chars": self.output_chars,
            "title_candidates": self.title_candidates,
            "figures": self.figures,
            "figures_referenced": self.figures_referenced,
            "missing_figures": self.missing_figures,
            "svg_assets": self.svg_assets,
            "reader_contract": self.reader_contract,
            "usage": self.usage,
            "latency_ms": self.latency_ms,
            "error": self.error,
        }


def extract_title_candidates(text: str) -> tuple[str, list[str]]:
    """Pull the optional title-candidate sidecar out of the writer output."""
    match = TITLE_COMMENT.search(text)
    if match is None:
        return text, []
    raw = match.group(1)
    candidates: list[str] = []
    # Models occasionally use " / " or " | " as candidate separators even
    # when the skill asks for "；".  Accept them, but keep spaces inside a
    # single candidate intact (e.g. "清洁 / 保湿" is not split).
    for part in re.split(r"[；;\n]+|\s+/\s+|\s*\|\s*", raw):
        # Strip list bullets, but never strip a leading number like "0.8".
        part = re.sub(
            r"^\s*(?:[-*•]\s*|\d{1,2}[.、)](?!\d)\s*)", "", part
        ).strip()
        if part:
            candidates.append(part)
    cleaned = TITLE_COMMENT.sub("", text).strip() + "\n"
    return cleaned, candidates[:3]


def extract_reader_contract(
    text: str,
) -> tuple[str, dict[str, Any] | None, str]:
    """Pull the reader-contract sidecar out of the writer output.

    The contract is audit-only: it makes the writer's reader assumption
    visible without entering the article body.  Invalid JSON is preserved as
    raw text, never silently interpreted.
    """
    match = READER_CONTRACT_COMMENT.search(text)
    if match is None:
        return text, None, ""
    raw = match.group(1).strip()
    cleaned = READER_CONTRACT_COMMENT.sub("", text).strip() + "\n"
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return cleaned, None, raw
    if not isinstance(value, dict):
        return cleaned, None, raw
    return cleaned, value, raw


def copy_figures(content_dir: Path, out_dir: Path) -> list[str]:
    """Copy the content manuscript's figures next to the product."""
    source = Path(content_dir) / "figures"
    target = Path(out_dir) / "figures"
    if not source.is_dir():
        return []
    target.mkdir(parents=True, exist_ok=True)
    copied: list[str] = []
    for item in sorted(source.iterdir()):
        if item.is_file():
            shutil.copy2(item, target / item.name)
            copied.append(f"figures/{item.name}")
    return copied


def figure_refs(article: str) -> list[str]:
    """Return Markdown image refs plus ``- figures/...`` sidecar refs."""
    refs = [match.group(1).strip() for match in IMAGE_REF.finditer(article)]
    refs += [match.group(1).strip() for match in SIDECAR_REF.finditer(article)]
    return list(dict.fromkeys(refs))


def missing_figures(article: str, out_dir: Path) -> list[str]:
    missing: list[str] = []
    for ref in figure_refs(article):
        if ref.startswith(("http://", "https://", "data:")):
            continue
        path = Path(ref)
        candidate = path if path.is_absolute() else Path(out_dir) / path
        if not candidate.exists():
            missing.append(ref)
    return missing


def _read_source(
    *, data_root: Path, video_id: str, source_path: Path | None
) -> dict[str, Any] | None:
    path = source_path or (data_root / video_id / "source.json")
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8-sig"))


def ensure_source_line(
    article: str,
    *,
    data_root: Path,
    video_id: str,
    source_path: Path | None = None,
    style: str = "article",
) -> str:
    """Append the one-line source after writing, outside the body."""
    if style == "none":
        return article
    tail = [line.strip() for line in article.splitlines() if line.strip()][-3:]
    if any(line.startswith(("本文根据", "本脚本根据", "内容参考")) for line in tail):
        return article
    source = _read_source(
        data_root=data_root, video_id=video_id, source_path=source_path
    )
    if source is None:
        return article
    title = str(source.get("title") or video_id)
    uploader = str(source.get("uploader") or "")
    if title == video_id or (not uploader and title.startswith("BV")):
        title_part = f"B 站视频（{title}）"
    elif uploader:
        title_part = f"B 站视频《{title}》（UP 主：{uploader}）"
    else:
        title_part = f"B 站视频《{title}》"
    if style == "script":
        line = f"本脚本根据 {title_part}整理；引用画面均来自原视频。"
    elif style == "social":
        line = f"内容参考 {title_part}；画面来自原视频。"
    else:
        line = f"本文根据 {title_part}整理；画面截取自原视频。"
    return article.rstrip() + "\n\n---\n\n" + line + "\n"


def _write_artifact(
    name: str,
    text: str,
    *,
    out_dir: Path,
    store: Any | None,
    store_prefix: str,
    stage: str,
) -> None:
    if store is not None:
        store.write_text(f"{store_prefix}/{name}", text, stage=stage)
    else:
        path = Path(out_dir) / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


def write_form(
    *,
    video_id: str,
    content_path: Path,
    out_dir: Path,
    skill_dir: Path,
    request: str = "",
    source_json: Path | None = None,
    client: Any | None = None,
    settings: Settings | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
    store: Any | None = None,
    store_prefix: str = "",
) -> FormResult:
    """Write one form once; optional ``store`` records artifacts and traces."""
    settings = settings or get_settings()
    skill: LoadedSkill = load_skill(skill_dir)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    content = Path(content_path).read_text(encoding="utf-8")
    system = skill.system
    user = skill.render_user(request=request, content=content)

    if client is None:
        if not settings.provider_configured:
            raise WriterError("provider not configured (DEEPSEEK_API_KEY / DEEPSEEK_MODEL)")
        client = DeepSeekLLM(settings)

    stage = f"write_{skill.form}"
    response = client.complete(
        stage=stage,
        key=f"{video_id}:{skill.form}",
        system=system,
        user=user,
        max_tokens=max_tokens if max_tokens is not None else skill.max_tokens,
        temperature=temperature if temperature is not None else skill.temperature,
    )
    text = (response.text or "").strip()
    if not text:
        raise WriterError(f"empty response (finish_reason={response.finish_reason})")

    text, candidates = extract_title_candidates(text)
    text, reader_contract, reader_contract_raw = extract_reader_contract(text)
    text = ensure_source_line(
        text,
        data_root=settings.data_root,
        video_id=video_id,
        source_path=source_json,
        style=skill.source_line,
    )

    copied = copy_figures(Path(content_path).parent, out_dir)
    if store is not None:
        for name in copied:
            store.register_file(
                f"{store_prefix}/{name}",
                stage=stage,
            )

    text, svg_report, svg_assets = build_svg_assets(
        text,
        client=client,
        key_prefix=f"{video_id}:{skill.form}",
    )
    if svg_assets:
        figures_dir = out_dir / "figures"
        figures_dir.mkdir(parents=True, exist_ok=True)
        for asset in svg_assets:
            (figures_dir / asset["filename"]).write_text(
                asset["svg"], encoding="utf-8"
            )
            if store is not None:
                store.register_file(
                    f"{store_prefix}/figures/{asset['filename']}",
                    stage=stage,
                )

    article = text.rstrip() + "\n"
    _write_artifact(
        skill.output_name,
        article,
        out_dir=out_dir,
        store=store,
        store_prefix=store_prefix,
        stage=stage,
    )
    if candidates:
        _write_artifact(
            "title_candidates.md",
            "\n".join(f"- {item}" for item in candidates) + "\n",
            out_dir=out_dir,
            store=store,
            store_prefix=store_prefix,
            stage=stage,
        )
    if reader_contract:
        _write_artifact(
            "reader_contract.json",
            json.dumps(reader_contract, ensure_ascii=False, indent=2) + "\n",
            out_dir=out_dir,
            store=store,
            store_prefix=store_prefix,
            stage=stage,
        )
    if svg_report.strip() != "无 SVG 占位符。":
        _write_artifact(
            "svg_report.md",
            svg_report,
            out_dir=out_dir,
            store=store,
            store_prefix=store_prefix,
            stage=stage,
        )

    refs = figure_refs(article)
    missing = missing_figures(article, out_dir)
    meta = {
        "video_id": video_id,
        "form": skill.form,
        "skill": skill.id,
        "skill_version": skill.version,
        "role": skill.role,
        "model": response.model,
        "provider": response.provider,
        "finish_reason": response.finish_reason,
        "latency_ms": response.latency_ms,
        "usage": response.usage.as_dict(),
        "content": {
            "path": str(content_path),
            "sha256": sha256_text(content),
            "chars": len(content),
        },
        "request": request,
        "output": skill.output_name,
        "output_chars": len(article),
        "title_candidates": candidates,
        "reader_contract": reader_contract,
        "reader_contract_raw": reader_contract_raw,
        "figures": copied,
        "figures_referenced": refs,
        "missing_figures": missing,
        "svg_assets": [asset["filename"] for asset in svg_assets],
        "replayed": bool(getattr(response, "replayed", False)),
    }
    _write_artifact(
        "response_meta.json",
        json.dumps(meta, ensure_ascii=False, indent=2) + "\n",
        out_dir=out_dir,
        store=store,
        store_prefix=store_prefix,
        stage=stage,
    )

    return FormResult(
        form=skill.form,
        skill_id=skill.id,
        skill_version=skill.version,
        role=skill.role,
        status="complete",
        output=skill.output_name,
        output_chars=len(article),
        title_candidates=candidates,
        figures=copied,
        figures_referenced=refs,
        missing_figures=missing,
        svg_assets=[asset["filename"] for asset in svg_assets],
        reader_contract=reader_contract,
        usage=response.usage.as_dict(),
        latency_ms=response.latency_ms,
    )
