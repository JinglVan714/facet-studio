"""Read-only adapter for the existing ``lmind`` evidence substrate.

The adapter never writes into the source directory.  It records source file
hashes so a later build can prove that the substrate did not change.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from ..core.hashing import file_sha256, semantic_hash, utc_now_iso
from ..core.sealing import seal
from .models import (
    Anchor,
    Assertion,
    AssertionRelation,
    Claim,
    EvidenceClaimLink,
    EvidenceLocator,
    EvidenceSnapshot,
    EvidenceSpan,
    ExtractionConflict,
    FrameInfo,
    FramesIndex,
    SourceFile,
    SourceManifest,
    Unit,
)

REQUIRED_SUBSTRATE_FILES = (
    "substrate/assertions.jsonl",
    "substrate/units.jsonl",
    "substrate/contract.json",
    "substrate/relations.jsonl",
    "frames_index.json",
)

# 并非每条视频都有 ASR/画面异文清单；缺失表示“上游未记录冲突”，
# 不表示证据冲突被忽略。ingest 会把缺失项写进 source_manifest.notes。
OPTIONAL_SUBSTRATE_FILES = (
    "substrate/corrections_asr_vs_screen.json",
)

_EMPTY_CORRECTIONS = {"conflicts": []}

_ATTRIBUTION_MARKERS = ("讲解员说", "视频称", "据介绍", "表示", "认为", "声称", "他说", "她说")

_CLAIM_KIND_MAP = {
    "fact": "factual",
    "opinion": "evaluative",
    "evaluative": "evaluative",
    "instruction": "instructional",
    "instructional": "instructional",
    "causal": "causal",
    "comparison": "comparative",
    "comparative": "comparative",
}


class SourceChangedError(RuntimeError):
    """输入 substrate 与 ingest 记录不一致。"""


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}:{line_no} 不是合法 JSON: {exc}") from exc
    return rows


def _normalize_ws(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _claim_kind(raw_kind: str) -> str:
    return _CLAIM_KIND_MAP.get(raw_kind, "factual")


def _support_status(raw_status: str) -> str:
    if raw_status == "supported":
        return "supported"
    if raw_status == "bounded":
        return "partially_supported"
    if raw_status in {"contradicted", "unsupported", "unknown", "no_source", "needs_review"}:
        return raw_status
    return "needs_review"


def _claim_form(text: str) -> str:
    return "attributed" if any(marker in text for marker in _ATTRIBUTION_MARKERS) else "direct"


def discover_substrate(data_root: Path, video_id: str) -> Path:
    root = data_root / video_id
    missing = [name for name in REQUIRED_SUBSTRATE_FILES if not (root / name).exists()]
    if missing:
        raise FileNotFoundError(f"{root} 缺少必要文件: {', '.join(missing)}")
    return root


def _present_optional_files(root: Path) -> list[str]:
    return [name for name in OPTIONAL_SUBSTRATE_FILES if (root / name).exists()]


def build_ingest_record(video_id: str, data_root: Path) -> dict[str, Any]:
    root = discover_substrate(data_root, video_id)
    files: list[SourceFile] = []
    for name in (*REQUIRED_SUBSTRATE_FILES, *_present_optional_files(root)):
        path = root / name
        files.append(
            SourceFile(
                path=str(path.relative_to(data_root)).replace("\\", "/"),
                sha256=file_sha256(path),
                bytes=path.stat().st_size,
            )
        )
    for extra in sorted(root.glob("frames_vlm*.json")):
        files.append(
            SourceFile(
                path=str(extra.relative_to(data_root)).replace("\\", "/"),
                sha256=file_sha256(extra),
                bytes=extra.stat().st_size,
            )
        )

    contract = _read_json(root / "substrate/contract.json")
    assertions = _read_jsonl(root / "substrate/assertions.jsonl")
    relations = _read_jsonl(root / "substrate/relations.jsonl")
    units = _read_jsonl(root / "substrate/units.jsonl")
    frames_index = _read_json(root / "frames_index.json")

    notes = [
        "原始 media 文件不在本仓库 data/ 中时，首版只使用语音/字幕证据。",
        "所有 substrate 文件只读；snapshot 记录其 SHA256。",
    ]
    missing_optional = [
        name for name in OPTIONAL_SUBSTRATE_FILES if not (root / name).exists()
    ]
    if missing_optional:
        notes.append(f"缺少可选 substrate 文件，按无记录处理: {missing_optional}")

    manifest = SourceManifest(
        video_id=video_id,
        root=str(data_root.resolve()),
        files=files,
        media_path=frames_index.get("media_path"),
        media_available=_media_available(frames_index.get("media_path")),
        notes=notes,
    )
    record = {
        "schema_version": "1.0",
        "video_id": video_id,
        "data_root": str(data_root.resolve()),
        "source_manifest": manifest.model_dump(mode="json"),
        "counts": {
            "units": len(units),
            "contract_unit_count": contract.get("unit_count"),
            "assertions": len(assertions),
            "relations": len(relations),
            "segments": len(contract.get("segments", [])),
            "frames": _count_frames(frames_index),
        },
        "status": "complete",
        "created_at": utc_now_iso(),
    }
    record["ingest_hash"] = semantic_hash(record, exclude_keys=("data_root",))
    return record


def _count_frames(frames_index: dict[str, Any]) -> int:
    seen: set[str] = set()
    for strategy in frames_index.get("strategies", {}).values():
        for frame in strategy.get("frames", []):
            seen.add(Path(frame["file"]).stem)
    return len(seen)


def _media_available(media_path: str | None) -> bool:
    if not media_path:
        return False
    path = Path(media_path)
    candidates = [path]
    if not path.is_absolute():
        candidates.append(Path.cwd() / path)
        candidates.append(Path.cwd().parent / path)
    return any(p.exists() for p in candidates)


def build_evidence_snapshot(ingest: dict[str, Any]) -> EvidenceSnapshot:
    """Build an immutable EvidenceSnapshot from an ingest record.

    Fails with :class:`SourceChangedError` when any recorded source hash no
    longer matches.  Input files are never modified.
    """
    data_root = Path(ingest["data_root"])
    video_id = ingest["video_id"]
    root = discover_substrate(data_root, video_id)

    for item in ingest["source_manifest"]["files"]:
        path = data_root / item["path"]
        if not path.exists() or file_sha256(path) != item["sha256"]:
            raise SourceChangedError(f"来源文件已变化或缺失: {item['path']}")

    units_raw = _read_jsonl(root / "substrate/units.jsonl")
    assertions_raw = _read_jsonl(root / "substrate/assertions.jsonl")
    relations_raw = _read_jsonl(root / "substrate/relations.jsonl")
    contract = _read_json(root / "substrate/contract.json")
    corrections_path = root / "substrate/corrections_asr_vs_screen.json"
    corrections_raw = (
        _read_json(corrections_path)
        if corrections_path.exists()
        else dict(_EMPTY_CORRECTIONS)
    )
    frames_index_raw = _read_json(root / "frames_index.json")

    units: list[Unit] = []
    warnings: list[str] = []
    unit_ids: set[str] = set()
    for raw in units_raw:
        unit = Unit.model_validate(raw)
        if unit.unit_id in unit_ids:
            warnings.append(f"重复 unit_id: {unit.unit_id}")
        unit_ids.add(unit.unit_id)
        units.append(unit)

    assertions: list[Assertion] = []
    seen_assertions: set[str] = set()
    for raw in assertions_raw:
        assertion = Assertion.model_validate(raw)
        if assertion.id in seen_assertions:
            warnings.append(f"重复 assertion id: {assertion.id}")
        seen_assertions.add(assertion.id)
        missing_units = [u for u in assertion.unit_ids if u not in unit_ids]
        if missing_units:
            warnings.append(f"{assertion.id} 引用不存在的 unit: {missing_units}")
        assertions.append(assertion)

    relations = [AssertionRelation.model_validate(raw) for raw in relations_raw]
    for rel in relations:
        if rel.from_id not in seen_assertions or rel.to_id not in seen_assertions:
            warnings.append(f"relation {rel.id} 端点不存在")

    correction_meta = {k: v for k, v in corrections_raw.items() if k != "conflicts"}
    corrections = [ExtractionConflict.model_validate(raw) for raw in corrections_raw.get("conflicts", [])]

    frames_index, frame_warnings = _build_frames_index(root, frames_index_raw)
    warnings.extend(frame_warnings)
    known_frames = {f.frame_id for f in frames_index.frames}

    claims: list[Claim] = []
    evidence: list[EvidenceSpan] = []
    links: list[EvidenceClaimLink] = []
    for assertion in assertions:
        claim_kind = _claim_kind(assertion.kind)
        claim = Claim(
            id=assertion.id,
            text=assertion.text,
            kind=claim_kind,
            claim_form=_claim_form(assertion.text),
            modality="stated",
            scope={"segment_id": assertion.chunk_id},
            support_status=_support_status(assertion.status),
            review_status="unreviewed",
            assertion_holder=None,
            source_assertion_id=assertion.id,
            chunk_id=assertion.chunk_id,
        )
        claims.append(claim)

        starts = [a.start_ms for a in assertion.anchors] or [0]
        ends = [a.end_ms for a in assertion.anchors] or [0]
        missing_frames = [f for f in assertion.frame_refs if f not in known_frames]
        if missing_frames:
            warnings.append(f"{assertion.id} 引用不在 frames_index 的帧: {missing_frames}")
        evidence_id = f"ev_{assertion.id}"
        span = EvidenceSpan(
            id=evidence_id,
            source_id=video_id,
            unit_ids=list(assertion.unit_ids),
            grounding_origin="video_native",
            capture_method="asr",
            modality="speech",
            locator=EvidenceLocator(
                video_id=video_id,
                t_start_ms=min(starts),
                t_end_ms=max(ends),
                frame_ids=list(assertion.frame_refs),
                unit_ids=list(assertion.unit_ids),
            ),
            raw_content=assertion.quote,
            normalized_content=_normalize_ws(assertion.quote),
            kind="quote" if claim_kind == "evaluative" else "fact",
            assertion_mode="uncertain" if assertion.status == "bounded" else "explicit",
            extraction_quality={
                "quote_hit": assertion.quote_hit,
                "quote_source": assertion.quote_source,
                "anchor_precision": sorted({a.precision for a in assertion.anchors}),
            },
            context_refs={"segment_id": assertion.chunk_id, "assertion_id": assertion.id},
            rights_scope="unknown_public_video",
            provenance={
                "assertion_produced_by": assertion.produced_by,
                "source_file": "substrate/assertions.jsonl",
                "unit_source_file": "substrate/units.jsonl",
            },
            frame_refs=list(assertion.frame_refs),
        )
        evidence.append(span)
        links.append(
            EvidenceClaimLink(
                id=f"ecl_{assertion.id}",
                claim_id=claim.id,
                evidence_id=evidence_id,
                stance="supports",
                basis="derived",
                scope={"segment_id": assertion.chunk_id},
                weight="primary",
                provenance={
                    "note": "claim 由 assertion 规范化而来，quote 为其所依据的 unit 原文",
                },
            )
        )

    coverage = _unit_coverage(units, assertions)
    if coverage < 1.0:
        warnings.append(f"unit 覆盖率 {coverage:.1%}，存在未被 assertion 覆盖的 unit")

    status = "complete" if not warnings else "partial"
    source_manifest = SourceManifest.model_validate(ingest["source_manifest"])
    model_versions = _collect_model_versions(units_raw, assertions, frames_index_raw, contract)
    snapshot = EvidenceSnapshot(
        video_id=video_id,
        source_manifest=source_manifest,
        derived_asset_hashes=_derived_hashes(units_raw, assertions_raw, frames_index_raw, corrections_raw),
        units=units,
        assertions=assertions,
        relations=relations,
        corrections=corrections,
        correction_ledger_meta=correction_meta,
        frames_index=frames_index,
        claims=claims,
        evidence=evidence,
        evidence_claim_links=links,
        status=status,
        build_warnings=warnings,
        model_versions=model_versions,
        created_at=utc_now_iso(),
    )
    snapshot = seal(
        snapshot,
        id_field="snapshot_id",
        hash_field="snapshot_hash",
        prefix="es",
        # 路径和“本机是否有 media”不是语义内容，不应改变 snapshot 身份。
        exclude_keys=("root", "media_available"),
    )
    return snapshot


def _build_frames_index(root: Path, raw: dict[str, Any]) -> tuple[FramesIndex, list[str]]:
    warnings: list[str] = []
    frames: dict[str, FrameInfo] = {}
    for strategy_name, strategy in raw.get("strategies", {}).items():
        for frame in strategy.get("frames", []):
            frame_id = Path(frame["file"]).stem
            info = FrameInfo(
                frame_id=frame_id,
                t_ms=int(frame["t_ms"]),
                file=frame["file"],
                strategy=strategy_name,
                slot_end_ms=frame.get("slot_end_ms"),
            )
            previous = frames.get(frame_id)
            if previous is None or (info.slot_end_ms or 0) < (previous.slot_end_ms or 0):
                frames[frame_id] = info

    vlm_models: set[str] = set()
    vlm_files = sorted(root.glob("frames_vlm*.json"))
    for path in vlm_files:
        try:
            payload = _read_json(path)
        except Exception as exc:  # pragma: no cover - defensive
            warnings.append(f"无法读取 {path.name}: {exc}")
            continue
        model = (payload.get("provenance") or {}).get("model")
        if model:
            vlm_models.add(str(model))
        for frame_id, item in (payload.get("per_frame") or {}).items():
            if frame_id not in frames:
                continue
            text = (item.get("text") or "").strip()
            if text and not frames[frame_id].vlm_text:
                frames[frame_id] = frames[frame_id].model_copy(
                    update={"vlm_text": text, "vlm_model": model}
                )

    with_text = sum(1 for f in frames.values() if f.vlm_text)
    index = FramesIndex(
        video_id=raw.get("video_id", ""),
        duration_s=float(raw.get("duration_s") or 0.0),
        media_path=raw.get("media_path"),
        frames=sorted(frames.values(), key=lambda f: (f.t_ms, f.frame_id)),
        vlm_models=sorted(vlm_models),
        vlm_coverage=(with_text / len(frames)) if frames else 0.0,
    )
    if not frames:
        warnings.append("frames_index 为空")
    return index, warnings


def _unit_coverage(units: list[Unit], assertions: list[Assertion]) -> float:
    if not units:
        return 0.0
    covered = {uid for a in assertions for uid in a.unit_ids}
    known = {u.unit_id for u in units}
    return len(covered & known) / len(known)


def _collect_model_versions(
    units_raw: list[dict[str, Any]],
    assertions: list[Assertion],
    frames_raw: dict[str, Any],
    contract: dict[str, Any],
) -> dict[str, str]:
    versions: dict[str, str] = {}
    for assertion in assertions:
        produced = assertion.produced_by or {}
        if produced.get("model"):
            versions["assertion_model"] = str(produced["model"])
        if produced.get("prompt_version"):
            versions["assertion_prompt"] = str(produced["prompt_version"])
    if frames_raw.get("provenance", {}).get("model"):
        versions["vlm_model"] = str(frames_raw["provenance"]["model"])
    if contract.get("produced_by", {}).get("model"):
        versions["contract_model"] = str(contract["produced_by"]["model"])
    unit_configs = sorted(
        {
            str((row.get("produced_by") or {}).get("config_hash"))
            for row in units_raw
            if (row.get("produced_by") or {}).get("config_hash")
        }
    )
    if unit_configs:
        versions["unit_config_hash"] = ",".join(unit_configs)
    versions.setdefault("unit_version", "unit/v1")
    return versions


def _derived_hashes(
    units_raw: list[dict[str, Any]],
    assertions_raw: list[dict[str, Any]],
    frames_raw: dict[str, Any],
    corrections_raw: dict[str, Any],
) -> dict[str, str]:
    return {
        "units": semantic_hash(units_raw),
        "assertions": semantic_hash(assertions_raw),
        "frames": semantic_hash(frames_raw),
        "corrections": semantic_hash(corrections_raw),
    }
