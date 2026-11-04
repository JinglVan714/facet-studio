"""Tests for consume-index-v1 and deterministic evidence lookups."""

from __future__ import annotations

from lunograph.evidence_access import (
    build_consume_index,
    get_part,
    lookup_claim,
    lookup_frame,
    normalize_frames_index,
    slice_evidence,
    visual_lookup,
)

TEXT = (
    "## A\n首先收集问题。然后把问题交给模型。\n\n"
    "## B\n模型返回结果，分数是 0.756。另一个结果是 0.81，第三个是 0.62。"
)
BLOCK0_END = len("## A\n首先收集问题。然后把问题交给模型。")
BLOCK1_START = BLOCK0_END + 2
BLOCK1_END = len(TEXT)

SENTENCES = [
    {
        "sentence_id": "seg1-s001",
        "segment_id": "seg1",
        "t_start_ms": 0,
        "t_end_ms": 1000,
        "text": "首先收集问题。",
    },
    {
        "sentence_id": "seg1-s002",
        "segment_id": "seg1",
        "t_start_ms": 1000,
        "t_end_ms": 2000,
        "text": "然后把问题交给模型。",
    },
    {
        "sentence_id": "seg2-s001",
        "segment_id": "seg2",
        "t_start_ms": 2000,
        "t_end_ms": 3000,
        "text": "模型返回结果，分数是 0.756。",
    },
    {
        "sentence_id": "seg2-s002",
        "segment_id": "seg2",
        "t_start_ms": 3000,
        "t_end_ms": 4000,
        "text": "另一个结果是 0.81，第三个是 0.62。",
    },
]

PASSAGES = [
    {
        "passage_id": "seg1-p01",
        "segment_id": "seg1",
        "sentence_ids": ["seg1-s001", "seg1-s002"],
        "t_start_ms": 0,
        "t_end_ms": 2000,
        "text": "首先收集问题。然后把问题交给模型。",
    },
    {
        "passage_id": "seg2-p01",
        "segment_id": "seg2",
        "sentence_ids": ["seg2-s001", "seg2-s002"],
        "t_start_ms": 2000,
        "t_end_ms": 4000,
        "text": "模型返回结果，分数是 0.756。另一个结果是 0.81，第三个是 0.62。",
    },
]

PACK = {
    "pack_id": "ep3_test",
    "pack_hash": "packhash",
    "video_id": "BVtest",
    "segments": [
        {
            "segment_id": "seg1",
            "label": "A",
            "t_start_ms": 0,
            "t_end_ms": 2000,
            "claim_ids": ["c1"],
            "sentence_ids": ["seg1-s001", "seg1-s002"],
            "frame_ids": ["00001_000000500"],
        },
        {
            "segment_id": "seg2",
            "label": "B",
            "t_start_ms": 2000,
            "t_end_ms": 4000,
            "claim_ids": ["c2"],
            "sentence_ids": ["seg2-s001", "seg2-s002"],
            "frame_ids": ["00002_000002500"],
        },
    ],
    "claims": [
        {
            "claim_id": "c1",
            "segment_id": "seg1",
            "status": "supported",
            "kind": "instruction",
            "text": "先收集问题，再交给模型。",
            "scope": "",
            "quote": "首先收集问题",
            "passage_id": "seg1-p01",
            "sentence_ids": ["seg1-s001", "seg1-s002"],
            "evidence_ids": ["e1"],
            "t_start_ms": 0,
            "t_end_ms": 2000,
        },
        {
            "claim_id": "c2",
            "segment_id": "seg2",
            "status": "bounded",
            "kind": "fact",
            "text": "分数是 0.756，另一个是 0.81，第三个是 0.62。",
            "scope": "这组数据",
            "quote": "0.756",
            "passage_id": "seg2-p01",
            "sentence_ids": ["seg2-s001", "seg2-s002"],
            "evidence_ids": ["e2"],
            "t_start_ms": 2000,
            "t_end_ms": 4000,
        },
    ],
    "evidence": [
        {
            "evidence_id": "e1",
            "claim_ids": ["c1"],
            "quote": "首先收集问题",
            "t_start_ms": 0,
            "t_end_ms": 1000,
            "sentence_ids": ["seg1-s001"],
        },
        {
            "evidence_id": "e2",
            "claim_ids": ["c2"],
            "quote": "0.756",
            "t_start_ms": 2000,
            "t_end_ms": 3000,
            "sentence_ids": ["seg2-s001"],
        },
    ],
    "frames": [
        {
            "frame_id": "00001_000000500",
            "segment_ids": ["seg1"],
            "t_ms": 500,
            "file": "frames/00001_000000500.jpg",
            "caption": "流程：收集问题",
            "capture_method": "vlm",
            "strategy": "fixed_interval",
        },
        {
            "frame_id": "00002_000002500",
            "segment_ids": ["seg2"],
            "t_ms": 2500,
            "file": "frames/00002_000002500.jpg",
            "caption": "分数 0.756",
            "capture_method": "vlm",
            "strategy": "fixed_interval",
        },
    ],
    "gaps": [],
    "conflicts": [],
    "provenance": {
        "claims": {
            "c1": {
                "source_claim_ids": ["a1"],
                "source_evidence_ids": ["e1"],
            },
            "c2": {
                "source_claim_ids": ["a2"],
                "source_evidence_ids": ["e2"],
            },
        }
    },
}

SOURCE_MAP = {
    "blocks": [
        {
            "block_index": 0,
            "segment_id": "seg1",
            "label": "A",
            "text_start": 0,
            "text_end": BLOCK0_END,
            "sentence_ids": ["seg1-s001", "seg1-s002"],
            "passage_ids": ["seg1-p01"],
            "claim_ids": ["c1"],
            "frames": [
                {"frame_id": "00001_000000500", "caption": "流程：收集问题"}
            ],
        },
        {
            "block_index": 1,
            "segment_id": "seg2",
            "label": "B",
            "text_start": BLOCK1_START,
            "text_end": BLOCK1_END,
            "sentence_ids": ["seg2-s001", "seg2-s002"],
            "passage_ids": ["seg2-p01"],
            "claim_ids": ["c2"],
            "frames": [
                {"frame_id": "00002_000002500", "caption": "分数 0.756"}
            ],
        },
    ]
}

FRAMES_INDEX = {
    "strategies": {
        "fixed_interval": {
            "kind": "fixed_interval",
            "frames": [
                {
                    "idx": 1,
                    "t_ms": 500,
                    "slot_end_ms": 1500,
                    "file": "frames/00001_000000500.jpg",
                },
                {
                    "idx": 2,
                    "t_ms": 2500,
                    "slot_end_ms": 3500,
                    "file": "frames/00002_000002500.jpg",
                },
            ],
        }
    }
}

FRAMES_VLM = {
    "per_frame": {
        "00001_000000500": {"text": "流程：收集问题"},
        "00002_000002500": {"text": "分数 0.756"},
    }
}


def _build(**kwargs):
    return build_consume_index(
        PACK,
        PASSAGES,
        SENTENCES,
        edited_text=TEXT,
        source_map=SOURCE_MAP,
        frames_index=FRAMES_INDEX,
        frames_vlm=FRAMES_VLM,
        video_id="BVtest",
        **kwargs,
    )


def test_normalize_frames_index_uses_strategy_and_caption() -> None:
    rows = normalize_frames_index(FRAMES_INDEX, FRAMES_VLM)
    assert [row["frame_id"] for row in rows] == [
        "00001_000000500",
        "00002_000002500",
    ]
    assert rows[0]["strategy"] == "fixed_interval"
    assert rows[0]["caption"] == "流程：收集问题"
    assert rows[0]["capture_method"] == "vlm"
    assert rows[0]["slot_end_ms"] == 1500


def test_build_consume_index_fields_and_coverage() -> None:
    index = _build()
    assert index["schema"] == "consume-index-v1"
    assert index["video_id"] == "BVtest"
    assert len(index["segments"]) == 2
    assert len(index["claims"]) == 2
    assert len(index["sentences"]) == 4
    assert len(index["frames"]) == 2
    assert len(index["parts"]) == 2
    seg1 = index["segments"][0]
    assert seg1["segment_id"] == "seg1"
    assert seg1["block_index"] == 0
    assert seg1["text_start"] == 0
    assert seg1["text_end"] == BLOCK0_END
    assert seg1["part_id"] == "part_01"
    claim = next(row for row in index["claims"] if row["claim_id"] == "c1")
    assert claim["block_index"] == 0
    assert claim["part_id"] == "part_01"
    assert claim["source_claim_ids"] == ["a1"]
    assert index["coverage"]["unassigned_blocks"] == []
    assert index["coverage"]["claims_unassigned"] == []
    assert index["index_hash"]


def test_get_part_returns_text_and_items() -> None:
    index = _build()
    part = get_part(index, "part_01", edited_text=TEXT)
    assert part["found"] is True
    assert "首先收集问题" in part["text"]
    assert [claim["claim_id"] for claim in part["claims"]] == ["c1"]
    assert [sentence["sentence_id"] for sentence in part["sentences"]] == [
        "seg1-s001",
        "seg1-s002",
    ]
    assert [frame["frame_id"] for frame in part["frames"]] == [
        "00001_000000500"
    ]


def test_lookup_claim_returns_evidence_and_frames() -> None:
    index = _build()
    result = lookup_claim(index, "c1")
    assert result["found"] is True
    assert result["claim"]["status"] == "supported"
    assert [item["evidence_id"] for item in result["evidence"]] == ["e1"]
    assert result["block"]["block_index"] == 0
    assert "00001_000000500" in [
        frame["frame_id"] for frame in result["frames_near"]
    ]


def test_lookup_frame_by_id_and_time() -> None:
    index = _build()
    by_id = lookup_frame(index, frame_id="00002_000002500")
    assert by_id["found"] is True
    assert by_id["frame"]["frame_id"] == "00002_000002500"
    assert "c2" in [claim["claim_id"] for claim in by_id["claims_near"]]
    by_time = lookup_frame(index, t_ms=2500, window_ms=10)
    assert [frame["frame_id"] for frame in by_time["frames"]] == [
        "00002_000002500"
    ]


def test_slice_evidence_segment_scope() -> None:
    index = _build()
    result = slice_evidence(index, segment_id="seg2")
    assert result["scope"]["segment_ids"] == ["seg2"]
    assert [claim["claim_id"] for claim in result["claims"]] == ["c2"]
    assert [sentence["sentence_id"] for sentence in result["sentences"]] == [
        "seg2-s001",
        "seg2-s002",
    ]
    assert [frame["frame_id"] for frame in result["frames"]] == [
        "00002_000002500"
    ]


def test_visual_lookup_numbers_and_process() -> None:
    index = _build()
    numbers = visual_lookup(index, segment_id="seg2")
    kinds = {candidate["kind"] for candidate in numbers["candidates"]}
    assert "chart" in kinds
    assert "table" in kinds
    assert "real_frame" in kinds
    chart = next(
        candidate for candidate in numbers["candidates"] if candidate["kind"] == "chart"
    )
    assert {item["value"] for item in chart["numbers"]} == {
        "0.756",
        "0.81",
        "0.62",
    }

    process = visual_lookup(index, segment_id="seg1")
    process_kinds = {candidate["kind"] for candidate in process["candidates"]}
    assert "diagram" in process_kinds
    assert "real_frame" in process_kinds


def test_partition_never_drops_segments() -> None:
    index = _build(max_chars_per_part=10)
    assert len(index["parts"]) == 2
    covered = {
        segment_id
        for part in index["parts"]
        for segment_id in part["segment_ids"]
    }
    assert covered == {"seg1", "seg2"}
    assert all(part["oversize"] is True for part in index["parts"])


def test_light_pack_without_claims_still_builds() -> None:
    light_pack = dict(PACK)
    light_pack["claims"] = []
    light_pack["evidence"] = []
    light_pack["provenance"] = {}
    index = build_consume_index(
        light_pack,
        PASSAGES,
        SENTENCES,
        edited_text=TEXT,
        source_map=SOURCE_MAP,
        frames_index=FRAMES_INDEX,
        frames_vlm=FRAMES_VLM,
        video_id="BVtest",
    )
    assert index["claims"] == []
    assert index["evidence"] == []
    assert len(index["segments"]) == 2
    assert len(index["parts"]) == 2
    assert lookup_claim(index, "c1")["found"] is False
