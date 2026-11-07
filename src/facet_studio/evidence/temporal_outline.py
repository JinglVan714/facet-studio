"""Deterministic temporal structure (units + segments).

A segment is a time range with a human label.  It is *not* a knowledge
topic and must never be used as a KnowledgeSnapshot substitute.
"""

from __future__ import annotations

from typing import Any

from ..core.hashing import utc_now_iso
from ..core.sealing import seal
from .models import (
    CoverageReport,
    EvidenceSnapshot,
    OutlineUnit,
    Segment,
    TemporalOutline,
)


def build_temporal_outline(
    snapshot: EvidenceSnapshot, contract: dict[str, Any]
) -> TemporalOutline:
    unit_by_id = {u.unit_id: u for u in snapshot.units}
    unit_segment: dict[str, str] = {}
    segments: list[Segment] = []
    warnings: list[str] = []

    for raw in contract.get("segments", []):
        segment = Segment(
            segment_id=raw["segment_id"],
            label=raw.get("label", ""),
            start_unit_id=raw.get("start_unit_id", ""),
            end_unit_id=raw.get("end_unit_id", ""),
            unit_ids=list(raw.get("unit_ids", [])),
            first_ms=int(raw.get("first_ms", 0)),
            last_ms=int(raw.get("last_ms", 0)),
        )
        segments.append(segment)
        missing = [uid for uid in segment.unit_ids if uid not in unit_by_id]
        if missing:
            warnings.append(f"{segment.segment_id} 引用不存在的 unit: {missing[:5]}")
        for uid in segment.unit_ids:
            if uid in unit_segment and unit_segment[uid] != segment.segment_id:
                warnings.append(
                    f"unit {uid} 同时属于 {unit_segment[uid]} 和 {segment.segment_id}；保留前者"
                )
                continue
            unit_segment[uid] = segment.segment_id

    unassigned = [u.unit_id for u in snapshot.units if u.unit_id not in unit_segment]
    for uid in unassigned:
        unit_segment[uid] = "unassigned"
    if unassigned:
        warnings.append(f"{len(unassigned)} 个 unit 未被 contract segment 覆盖")

    outline_units = [
        OutlineUnit(
            **unit.model_dump(mode="python"),
            segment_id=unit_segment[unit.unit_id],
        )
        for unit in snapshot.units
    ]

    covered_units = {uid for a in snapshot.assertions for uid in a.unit_ids if uid in unit_by_id}
    first_ms = min((u.start_ms for u in snapshot.units), default=0)
    last_ms = max((u.end_ms for u in snapshot.units), default=0)
    coverage = CoverageReport(
        unit_count=len(snapshot.units),
        segment_count=len(segments),
        units_in_segments=len(snapshot.units) - len(unassigned),
        units_unassigned=unassigned,
        assertion_count=len(snapshot.assertions),
        units_with_assertion=len(covered_units),
        unit_coverage=(len(covered_units) / len(snapshot.units)) if snapshot.units else 0.0,
        segment_coverage=(
            (len(snapshot.units) - len(unassigned)) / len(snapshot.units)
            if snapshot.units
            else 0.0
        ),
        duration_ms=int(snapshot.frames_index.duration_s * 1000),
        first_ms=first_ms,
        last_ms=last_ms,
        warnings=warnings,
    )

    outline = TemporalOutline(
        evidence_snapshot_id=snapshot.snapshot_id,
        units=outline_units,
        segments=segments,
        coverage_report=coverage,
        status="complete" if not warnings else "partial",
        created_at=utc_now_iso(),
    )
    return seal(
        outline,
        id_field="outline_id",
        hash_field="outline_hash",
        prefix="to",
    )
