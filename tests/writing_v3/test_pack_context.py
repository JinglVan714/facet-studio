"""Deterministic contracts for context coverage in the v3 EvidencePack.

These tests use synthetic sentences/claims, not a real video or model call.
They lock the S1-1 rule: every selected claim keeps at least one sentence that
contains its quote, neighbours are added only within budget, and missing
anchors are reported rather than silently dropped.
"""

from __future__ import annotations

from lunograph.writing_v3.pack_from_claims import build_pack


def _sentence(sentence_id: str, text: str, start_ms: int, end_ms: int) -> dict:
    return {
        "sentence_id": sentence_id,
        "segment_id": "seg1",
        "text": text,
        "t_start_ms": start_ms,
        "t_end_ms": end_ms,
        "unit_ids": [f"u_{sentence_id}"],
    }


def _frame(frame_id: str, t_ms: int) -> dict:
    return {
        "frame_id": frame_id,
        "t_ms": t_ms,
        "file": f"{frame_id}.jpg",
        "strategy": "test",
        "vlm_text": "",
    }


def _passage(passage_id: str, sentence_ids: list[str], text: str) -> dict:
    return {
        "passage_id": passage_id,
        "segment_id": "seg1",
        "sentence_ids": sentence_ids,
        "text": text,
        "t_start_ms": 0,
        "t_end_ms": 6000,
    }


def _claim(
    claim_id: str,
    quote: str,
    sentence_ids: list[str],
    *,
    passage_id: str = "p1",
) -> dict:
    return {
        "claim_id": claim_id,
        "passage_id": passage_id,
        "segment_id": "seg1",
        "text": f"claim {claim_id}",
        "quote": quote,
        "sentence_ids": sentence_ids,
        "kind": "fact",
        "status": "supported",
        "confidence": "high",
        "scope": "",
        "t_start_ms": 0,
        "t_end_ms": 6000,
        "evidence_id": f"ev_{claim_id}",
    }


SENTENCES = [
    _sentence("s1", "第一句。", 0, 1000),
    _sentence("s2", "第二句。", 1000, 2000),
    _sentence("s3", "第三句。", 2000, 3000),
    _sentence("s4", "第四句。", 3000, 4000),
    _sentence("s5", "第五句。", 4000, 5000),
    _sentence("s6", "第六句。", 5000, 6000),
]


def _build(
    sentences: list[dict],
    claims: list[dict],
    *,
    passages: list[dict] | None = None,
    max_sentences_per_segment: int | None = None,
    context_window: int = 2,
    max_chars: int = 60_000,
    frames: list[dict] | None = None,
    frame_window_ms: int = 12_000,
    max_frames: int = 24,
    contract_segments: list[dict] | None = None,
    outline_segments: list[dict] | None = None,
    snapshot: dict | None = None,
    knowledge: dict | None = None,
    skipped_passages: list[dict] | None = None,
) -> dict:
    if passages is None:
        passages = [
            _passage(
                "p1",
                [sentence["sentence_id"] for sentence in sentences],
                "".join(sentence["text"] for sentence in sentences),
            )
        ]
    if contract_segments is None:
        contract_segments = [{"segment_id": "seg1", "label": "test"}]
    snapshot_doc = {"video_id": "v", "snapshot_id": "s"}
    if snapshot:
        snapshot_doc.update(snapshot)
    return build_pack(
        claims_doc={"claims": claims, "skipped_passages": skipped_passages or []},
        passages_doc={"passages": passages},
        sentences_doc={"sentences": sentences},
        frames_index={"frames": frames or []},
        request={"request_id": "req_test", "central_question": "test"},
        skill_id="test",
        contract={"segments": contract_segments},
        snapshot_doc=snapshot_doc,
        outline_doc={"outline_id": "o", "segments": outline_segments or []},
        knowledge=knowledge,
        max_sentences_per_segment=max_sentences_per_segment,
        context_window=context_window,
        max_chars=max_chars,
        frame_window_ms=frame_window_ms,
        max_frames=max_frames,
    )


def test_anchors_survive_when_cap_is_smaller_than_anchor_count() -> None:
    claims = [
        _claim("c1", "第一句。", ["s1"]),
        _claim("c2", "第三句。", ["s3"]),
        _claim("c3", "第五句。", ["s5"]),
        _claim("c4", "第六句。", ["s6"]),
    ]
    pack = _build(SENTENCES, claims, max_sentences_per_segment=2)
    context = pack["selection"]["context"]

    assert context["claims_total"] == 4
    assert context["claims_with_context"] == 4
    assert context["claims_without_context"] == 0
    assert context["anchor_sentences"] == 4
    assert context["neighbor_sentences"] == 0
    assert context["context_sentences"] == 4
    assert context["over_cap_segments"] == [
        {"segment_id": "seg1", "anchor_sentences": 4, "cap": 2}
    ]
    assert {"s1", "s3", "s5", "s6"} <= {
        sentence["sentence_id"] for sentence in pack["sentences"]
    }


def test_neighbours_are_added_within_cap() -> None:
    pack = _build(
        SENTENCES,
        [_claim("c1", "第三句。", ["s3"])],
        max_sentences_per_segment=5,
        context_window=2,
    )
    context = pack["selection"]["context"]

    assert context["claims_with_context"] == 1
    assert context["anchor_sentences"] == 1
    assert context["neighbor_sentences"] == 4
    assert context["context_sentences"] == 5
    assert {
        sentence["sentence_id"] for sentence in pack["sentences"]
    } == {"s1", "s2", "s3", "s4", "s5"}


def test_quote_outside_claim_sentences_uses_passage_anchor() -> None:
    pack = _build(SENTENCES, [_claim("c1", "第三句。", ["s1"])])
    context = pack["selection"]["context"]

    assert context["claims_with_context"] == 1
    assert context["quote_not_in_claim_sentences"] == [
        {"claim_id": "c1", "source": "passage_sentences"}
    ]
    assert "s3" in {sentence["sentence_id"] for sentence in pack["sentences"]}


def test_missing_anchor_is_reported() -> None:
    pack = _build(SENTENCES, [_claim("c1", "不存在的引用。", ["s404"])])
    context = pack["selection"]["context"]

    assert context["claims_with_context"] == 0
    assert context["claims_without_context"] == 1
    assert context["missing_context_claims"] == [
        {"claim_id": "c1", "reason": "missing"}
    ]
    assert context["quote_not_in_claim_sentences"] == [
        {"claim_id": "c1", "source": "missing"}
    ]


def test_budget_is_advisory_and_never_drops_content() -> None:
    pack = _build(
        SENTENCES,
        [_claim("c1", "第三句。", ["s3"])],
        context_window=2,
        max_chars=1,
    )

    assert pack["truncated"] is False
    assert pack["over_budget"] is True
    assert pack["budget_excess_chars"] > 0
    assert pack["truncation"]["sentences_dropped"] == 0
    assert pack["truncation"]["dropped_sentence_ids"] == []
    assert "advisory_budget_exceeded" in pack["truncation"]["notes"]
    assert "s3" in {sentence["sentence_id"] for sentence in pack["sentences"]}


def test_default_claim_selection_keeps_all_claims() -> None:
    claims = [
        _claim(f"c{i}", f"{i}句。", [f"s{i}"]) for i in range(1, 7)
    ]
    pack = _build(SENTENCES, claims)

    assert {claim["claim_id"] for claim in pack["claims"]} == {
        f"c{i}" for i in range(1, 7)
    }
    assert pack["selection"]["coverage"]["passages_dropped_by_selection"] == []


def test_evidence_timecode_uses_anchor_sentence_union() -> None:
    pack = _build(SENTENCES, [_claim("c1", "第三句。", ["s3"])])
    evidence = pack["evidence"][0]

    assert evidence["t_start_ms"] == 2000
    assert evidence["t_end_ms"] == 3000
    assert evidence["sentence_ids"] == ["s3"]
    assert "timecode_source" not in evidence
    assert "quote_in_sentence_text" not in evidence
    assert pack["selection"]["context"]["timecode_source_counts"] == {
        "anchor_sentences": 1,
        "claim_passage_fallback": 0,
    }


def test_evidence_timecode_spans_two_sentences() -> None:
    pack = _build(
        SENTENCES,
        [_claim("c1", "第三句。第四句。", ["s3", "s4"])],
    )
    evidence = pack["evidence"][0]

    assert evidence["t_start_ms"] == 2000
    assert evidence["t_end_ms"] == 4000
    assert evidence["sentence_ids"] == ["s3", "s4"]
    assert "quote_in_sentence_text" not in evidence


def test_missing_anchor_falls_back_to_claim_timecode() -> None:
    pack = _build(SENTENCES, [_claim("c1", "不存在的引用。", ["s404"])])
    evidence = pack["evidence"][0]

    assert evidence["t_start_ms"] == 0
    assert evidence["t_end_ms"] == 6000
    assert evidence["timecode_source"] == "claim_passage_fallback"
    assert evidence["quote_in_sentence_text"] is False
    assert pack["selection"]["context"]["quote_not_in_sentence_text"] == [
        evidence["evidence_id"]
    ]


def test_frame_window_uses_anchor_timecode() -> None:
    frames = [_frame("f1000", 1000), _frame("f3000", 3000), _frame("f5000", 5000)]
    pack = _build(
        SENTENCES,
        [_claim("c1", "第三句。", ["s3"])],
        frames=frames,
        frame_window_ms=500,
    )

    assert [frame["frame_id"] for frame in pack["frames"]] == ["f3000"]


def test_frames_over_global_cap_are_reported_not_dropped() -> None:
    frames = [_frame("f1000", 1000), _frame("f3000", 3000)]
    pack = _build(
        SENTENCES,
        [_claim("c1", "第三句。", ["s3"])],
        frames=frames,
        max_frames=1,
    )

    assert {frame["frame_id"] for frame in pack["frames"]} == {"f1000", "f3000"}
    assert pack["selection"]["frame_selection"]["over_global_cap"] is True


def test_claims_are_sorted_by_sentence_order() -> None:
    claims = [
        _claim("c3", "第五句。", ["s5"]),
        _claim("c1", "第一句。", ["s1"]),
        _claim("c2", "第三句。", ["s3"]),
    ]
    pack = _build(SENTENCES, claims)

    assert [claim["claim_id"] for claim in pack["claims"]] == ["c1", "c2", "c3"]
    assert pack["segments"][0]["claim_ids"] == ["c1", "c2", "c3"]


def test_claims_are_sorted_by_passage_order() -> None:
    passages = [
        _passage("p1", ["s1", "s2", "s3"], "第一句。第二句。第三句。"),
        _passage("p2", ["s4", "s5", "s6"], "第四句。第五句。第六句。"),
    ]
    claims = [
        _claim("c2", "第五句。", ["s5"], passage_id="p2"),
        _claim("c1", "第二句。", ["s2"], passage_id="p1"),
    ]
    pack = _build(SENTENCES, claims, passages=passages)

    assert [claim["claim_id"] for claim in pack["claims"]] == ["c1", "c2"]
    assert pack["segments"][0]["claim_ids"] == ["c1", "c2"]


def test_outline_label_takes_precedence() -> None:
    pack = _build(
        SENTENCES,
        [_claim("c1", "第一句。", ["s1"])],
        contract_segments=[{"segment_id": "seg1", "label": "contract label"}],
        outline_segments=[{"segment_id": "seg1", "label": "outline label"}],
    )

    assert pack["segments"][0]["label"] == "outline label"
    assert pack["selection"]["labels"]["sources"]["seg1"] == "outline"
    assert pack["selection"]["labels"]["warnings"] == []


def test_contract_label_is_fallback() -> None:
    pack = _build(
        SENTENCES,
        [_claim("c1", "第一句。", ["s1"])],
        contract_segments=[{"segment_id": "seg1", "label": "contract label"}],
        outline_segments=[],
    )

    assert pack["segments"][0]["label"] == "contract label"
    assert pack["selection"]["labels"]["sources"]["seg1"] == "contract"
    assert pack["selection"]["labels"]["warnings"] == []


def test_missing_label_is_reported() -> None:
    pack = _build(
        SENTENCES,
        [_claim("c1", "第一句。", ["s1"])],
        contract_segments=[],
        outline_segments=[],
    )

    assert pack["segments"][0]["label"] == ""
    assert pack["selection"]["labels"]["sources"]["seg1"] == "missing"
    assert pack["selection"]["labels"]["warnings"] == ["seg1"]


def test_coverage_reports_passage_without_extracted_claim() -> None:
    passages = [
        _passage("p1", ["s1", "s2", "s3"], "第一句。第二句。第三句。"),
        _passage("p2", ["s4", "s5", "s6"], "第四句。第五句。第六句。"),
    ]
    pack = _build(
        SENTENCES,
        [_claim("c1", "第二句。", ["s2"], passage_id="p1")],
        passages=passages,
    )
    coverage = pack["selection"]["coverage"]

    assert coverage["passages_total"] == 2
    assert coverage["passages_with_extracted_claim"] == 1
    assert coverage["passages_with_selected_claim"] == 1
    assert coverage["passages_without_extracted_claim"] == [
        {"segment_id": "seg1", "passage_id": "p2"}
    ]
    assert coverage["passages_skipped"] == 0
    assert coverage["unreported_passages"] == [
        {"segment_id": "seg1", "passage_id": "p2"}
    ]
    assert coverage["passages_dropped_by_selection"] == []
    assert coverage["segments_with_zero_selected_claims"] == []


def test_coverage_reports_skipped_passage() -> None:
    passages = [
        _passage("p1", ["s1", "s2", "s3"], "第一句。第二句。第三句。"),
        _passage("p2", ["s4", "s5", "s6"], "第四句。第五句。第六句。"),
    ]
    pack = _build(
        SENTENCES,
        [_claim("c1", "第二句。", ["s2"], passage_id="p1")],
        passages=passages,
        skipped_passages=[{"passage_id": "p2", "reason": "teaser"}],
    )
    coverage = pack["selection"]["coverage"]

    assert coverage["passages_skipped"] == 1
    assert coverage["skipped_passages"] == [
        {"segment_id": "seg1", "passage_id": "p2", "reason": "teaser"}
    ]
    assert coverage["skip_reason_counts"] == {"teaser": 1}
    assert coverage["unreported_passages"] == []
    assert coverage["passages_without_extracted_claim"] == [
        {"segment_id": "seg1", "passage_id": "p2"}
    ]


def test_coverage_reports_selection_drop() -> None:
    passages = [
        _passage("p1", ["s1", "s2", "s3"], "第一句。第二句。第三句。"),
        _passage("p2", ["s4", "s5", "s6"], "第四句。第五句。第六句。"),
    ]
    # Force the selection cap to one claim so one passage is dropped.
    pack_capped = build_pack(
        claims_doc={"claims": [
            _claim("c1", "第二句。", ["s2"], passage_id="p1"),
            _claim("c2", "第五句。", ["s5"], passage_id="p2"),
        ]},
        passages_doc={"passages": passages},
        sentences_doc={"sentences": SENTENCES},
        frames_index={"frames": []},
        request={"request_id": "req_test", "central_question": "test"},
        skill_id="test",
        contract={"segments": [{"segment_id": "seg1", "label": "test"}]},
        snapshot_doc={"video_id": "v", "snapshot_id": "s"},
        outline_doc={"outline_id": "o", "segments": []},
        max_claims_per_segment=1,
    )
    coverage = pack_capped["selection"]["coverage"]

    assert coverage["passages_dropped_by_selection"] == [
        {"segment_id": "seg1", "passage_id": "p1"}
    ]
    assert coverage["passages_without_extracted_claim"] == []
