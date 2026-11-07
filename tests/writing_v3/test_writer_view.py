"""A/C view contract: lean view, quote spans, index, parts, no content loss."""

from __future__ import annotations

from facet_studio.writing_v3.writer_view import (
    build_writer_bundle,
    build_writer_index,
    build_writer_view,
    resolve_quote,
)

from .test_pack_context import SENTENCES, _build, _claim, _frame


def _synthetic_pack(segment_count: int = 3) -> dict:
    pack = {
        "claims": [],
        "evidence": [],
        "sentences": [],
        "frames": [],
        "segments": [],
        "gaps": [],
        "conflicts": [],
    }
    for index in range(1, segment_count + 1):
        claim_id = f"c{index}"
        evidence_id = f"ev{index}"
        sentence_id = f"s{index}"
        pack["claims"].append(
            {
                "claim_id": claim_id,
                "text": "x" * 80,
                "kind": "fact",
                "status": "supported",
                "scope": "",
                "evidence_ids": [evidence_id],
            }
        )
        pack["evidence"].append(
            {"evidence_id": evidence_id, "quote": "q" * 20}
        )
        pack["sentences"].append(
            {
                "sentence_id": sentence_id,
                "segment_id": f"seg{index}",
                "text": "t" * 80,
                "t_start_ms": 0,
                "t_end_ms": 1,
            }
        )
        pack["segments"].append(
            {
                "segment_id": f"seg{index}",
                "label": "label",
                "claim_ids": [claim_id],
                "sentence_ids": [sentence_id],
                "frame_ids": [],
            }
        )
    return pack


def test_lean_view_keeps_claim_evidence_context_frames_gaps() -> None:
    pack = _build(
        SENTENCES,
        [_claim("c1", "第二句。", ["s2"])],
        frames=[_frame("f3000", 3000)],
        knowledge={
            "gaps": [{"description": "gap desc", "severity": "major"}],
            "conflicts": [],
        },
    )
    view = build_writer_view(pack)

    assert view["schema"] == "writer-view-v1"
    assert set(view) == {"schema", "segments", "gaps", "conflicts"}
    segment = view["segments"][0]
    assert set(segment) == {"label", "claims", "context", "frames"}
    claim = segment["claims"][0]
    assert set(claim) == {
        "claim_id",
        "text",
        "status",
        "scope",
        "evidence",
    }
    assert claim["claim_id"] == "c1"
    evidence = claim["evidence"][0]
    assert evidence["evidence_id"] == "ev_c1"
    assert resolve_quote(segment["context"], evidence) == "第二句。"
    assert "第二句。" in segment["context"]
    assert segment["frames"] == [{"frame_id": "f3000", "caption": ""}]
    assert view["gaps"] == [{"description": "gap desc"}]
    assert view["conflicts"] == []


def test_lean_view_quote_fallback_when_not_in_context() -> None:
    pack = _build(
        SENTENCES,
        [_claim("c1", "不存在的引用。", ["s1"])],
    )
    view = build_writer_view(pack)
    segment = view["segments"][0]
    evidence = segment["claims"][0]["evidence"][0]

    assert evidence["evidence_id"] == "ev_c1"
    assert evidence["quote"] == "不存在的引用。"
    assert "span" not in evidence


def test_quote_span_rejects_duplicate_context_match() -> None:
    pack = {
        "claims": [
            {
                "claim_id": "c1",
                "text": "claim",
                "kind": "fact",
                "status": "supported",
                "scope": "",
                "evidence_ids": ["ev1"],
            }
        ],
        "evidence": [{"evidence_id": "ev1", "quote": "同一句。"}],
        "sentences": [
            {
                "sentence_id": "s1",
                "segment_id": "seg1",
                "text": "同一句。",
                "t_start_ms": 0,
                "t_end_ms": 1,
            },
            {
                "sentence_id": "s2",
                "segment_id": "seg1",
                "text": "同一句。",
                "t_start_ms": 1,
                "t_end_ms": 2,
            },
        ],
        "frames": [],
        "segments": [
            {
                "segment_id": "seg1",
                "label": "label",
                "claim_ids": ["c1"],
                "sentence_ids": ["s1", "s2"],
                "frame_ids": [],
            }
        ],
        "gaps": [],
        "conflicts": [],
    }
    view = build_writer_view(pack)
    evidence = view["segments"][0]["claims"][0]["evidence"][0]

    assert evidence["quote"] == "同一句。"
    assert "span" not in evidence


def test_writer_view_drops_audit_fields() -> None:
    pack = _build(
        SENTENCES,
        [_claim("c1", "第二句。", ["s2"])],
        frames=[_frame("f3000", 3000)],
    )
    view = build_writer_view(pack)
    serialized = str(view)

    for audit_key in [
        "pack_id",
        "pack_hash",
        "selection",
        "provenance",
        "budget",
        "truncation",
        "evidence_snapshot_id",
        "temporal_outline_id",
        "sentence_id",
        "passage_id",
        "segment_id",
        "t_start_ms",
        "t_end_ms",
        "capture_method",
        "strategy",
        "file",
        "kind",
    ]:
        assert audit_key not in serialized


def test_writer_view_partitions_without_dropping_content() -> None:
    pack = _synthetic_pack()
    view = build_writer_view(pack, max_chars=1)

    assert view["schema"] == "writer-view-parts-v1"
    assert view["manifest"]["note"] == "segments partitioned; no content dropped"
    part_claims = [
        claim["claim_id"]
        for part in view["parts"]
        for segment in part["segments"]
        for claim in segment["claims"]
    ]
    assert part_claims == ["c1", "c2", "c3"]
    assert len(view["manifest"]["oversize_parts"]) == 3


def test_writer_index_covers_segments_and_claims_without_content() -> None:
    pack = _synthetic_pack()
    index = build_writer_index(pack)

    assert index["schema"] == "writer-index-v1"
    assert [segment["part_id"] for segment in index["segments"]] == [
        "part_01",
        "part_02",
        "part_03",
    ]
    assert [
        claim["claim_id"]
        for segment in index["segments"]
        for claim in segment["claims"]
    ] == ["c1", "c2", "c3"]
    serialized = str(index)
    assert "quote" not in serialized
    assert "context" not in serialized
    assert "frames" not in serialized


def test_writer_bundle_covers_all_content() -> None:
    pack = _synthetic_pack()
    bundle = build_writer_bundle(pack)

    assert bundle["manifest"]["parts_count"] == 3
    assert bundle["manifest"]["segments_total"] == 3
    assert bundle["manifest"]["claims_total"] == 3
    part_claims = [
        claim["claim_id"]
        for part in bundle["parts"]
        for segment in part["segments"]
        for claim in segment["claims"]
    ]
    assert part_claims == ["c1", "c2", "c3"]
    assert [row["part_id"] for row in bundle["manifest"]["parts"]] == [
        "part_01",
        "part_02",
        "part_03",
    ]
    assert bundle["manifest"]["oversize_parts"] == []


def test_writer_bundle_keeps_oversize_parts() -> None:
    pack = _synthetic_pack()
    bundle = build_writer_bundle(pack, max_chars_per_part=1)

    assert bundle["manifest"]["parts_count"] == 3
    assert len(bundle["manifest"]["oversize_parts"]) == 3
    part_claims = [
        claim["claim_id"]
        for part in bundle["parts"]
        for segment in part["segments"]
        for claim in segment["claims"]
    ]
    assert part_claims == ["c1", "c2", "c3"]
