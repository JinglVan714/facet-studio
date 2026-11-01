"""Claim extraction coverage contract: claims + skipped_passages cover passages."""

from __future__ import annotations

from lunograph.writing_v3.claim_extract import _validate

PASSAGES = {
    "p1": {
        "passage_id": "p1",
        "segment_id": "seg1",
        "text": "第一句。第二句。",
        "sentence_ids": ["s1", "s2"],
        "t_start_ms": 0,
        "t_end_ms": 2000,
    },
    "p2": {
        "passage_id": "p2",
        "segment_id": "seg1",
        "text": "第三句。第四句。",
        "sentence_ids": ["s3", "s4"],
        "t_start_ms": 2000,
        "t_end_ms": 4000,
    },
}

CLAIM_P1 = {
    "passage_id": "p1",
    "text": "claim one",
    "quote": "第一句。",
    "sentence_ids": ["s1"],
    "kind": "fact",
    "status": "supported",
    "confidence": "high",
    "scope": "",
}


def test_coverage_complete_with_skip() -> None:
    claims, stats = _validate(
        [CLAIM_P1], [{"passage_id": "p2", "reason": "teaser"}], PASSAGES
    )

    assert len(claims) == 1
    assert stats["skipped"] == [{"passage_id": "p2", "reason": "teaser"}]
    assert stats["coverage"] == {
        "passages_total": 2,
        "passages_with_claims": 1,
        "passages_skipped": 1,
        "passages_unreported": [],
        "skip_reason_counts": {"teaser": 1},
    }


def test_coverage_reports_unreported_passage() -> None:
    _claims, stats = _validate([CLAIM_P1], [], PASSAGES)

    assert stats["coverage"]["passages_unreported"] == ["p2"]


def test_skip_for_claimed_passage_is_rejected() -> None:
    _claims, stats = _validate(
        [CLAIM_P1], [{"passage_id": "p1", "reason": "teaser"}], PASSAGES
    )

    assert stats["skipped"] == []
    assert stats["skipped_rejected"][0]["problems"] == ["passage_has_claim"]
    assert stats["coverage"]["passages_skipped"] == 0
    assert stats["coverage"]["passages_unreported"] == ["p2"]


def test_invalid_skip_is_rejected() -> None:
    _claims, stats = _validate(
        [CLAIM_P1],
        [
            {"passage_id": "p404", "reason": "other"},
            {"passage_id": "p2", "reason": ""},
        ],
        PASSAGES,
    )

    assert stats["skipped"] == []
    assert [row["problems"] for row in stats["skipped_rejected"]] == [
        ["unknown_passage"],
        ["empty_reason"],
    ]
    assert stats["coverage"]["passages_unreported"] == ["p2"]


def test_duplicate_skip_is_deduped() -> None:
    _claims, stats = _validate(
        [CLAIM_P1],
        [
            {"passage_id": "p2", "reason": "teaser"},
            {"passage_id": "p2", "reason": "teaser"},
        ],
        PASSAGES,
    )

    assert stats["skipped"] == [{"passage_id": "p2", "reason": "teaser"}]
    assert stats["skipped_duplicates"] == [
        {"passage_id": "p2", "reason": "teaser"}
    ]
