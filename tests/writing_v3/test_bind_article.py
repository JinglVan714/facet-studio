"""Tests for deterministic post-hoc article binding."""

from __future__ import annotations

from facet_studio.writing_v3 import bind_article

PACK = {
    "pack_id": "p1",
    "sentences": [
        {
            "sentence_id": "s1",
            "text": "第一句。产品有 1805 年历史。",
            "t_start_ms": 0,
            "t_end_ms": 1000,
        },
        {
            "sentence_id": "s2",
            "text": "它支持 95% 的准确率。",
            "t_start_ms": 1000,
            "t_end_ms": 2000,
        },
        {
            "sentence_id": "s3",
            "text": "界面显示 127.0.0.1:3080。",
            "t_start_ms": 2000,
            "t_end_ms": 3000,
        },
    ],
    "claims": [
        {
            "claim_id": "c1",
            "text": "产品有 1805 年历史。",
            "evidence_ids": ["e1"],
        },
        {
            "claim_id": "c2",
            "text": "它支持 95% 的准确率。",
            "evidence_ids": ["e2"],
        },
    ],
    "evidence": [
        {
            "evidence_id": "e1",
            "claim_ids": ["c1"],
            "quote": "产品有 1805 年历史。",
            "sentence_ids": ["s1"],
            "t_start_ms": 0,
            "t_end_ms": 1000,
        },
        {
            "evidence_id": "e2",
            "claim_ids": ["c2"],
            "quote": "它支持 95% 的准确率。",
            "sentence_ids": ["s2"],
            "t_start_ms": 1000,
            "t_end_ms": 2000,
        },
    ],
    "frames": [
        {
            "frame_id": "f1",
            "caption": "界面显示 127.0.0.1:3080",
            "t_ms": 2500,
        }
    ],
}

ARTICLE = """# 标题

第一段：产品有 1805 年的历史。

第二段：它支持 95% 的准确率，并在 127.0.0.1:3080 上运行。

第三段：它还有一个不存在的 2077 功能。

![演示画面](assets/00017_000525000.jpg)

*看这里：一个 9999 的图注。*

引用：“产品有 1805 年历史。”

长引用：“这是一个不存在的结论。”
"""


def test_extract_paragraphs_skips_markdown_scaffolding() -> None:
    paragraphs = bind_article.extract_paragraphs(ARTICLE)
    texts = [paragraph["text"] for paragraph in paragraphs]
    assert texts[0].startswith("第一段")
    assert len(texts) == 5
    assert all("![" not in text for text in texts)
    assert all("00017_000525000" not in text for text in texts)
    assert all("9999" not in text for text in texts)


def test_fact_anchors_bind_and_unsupported_is_reported() -> None:
    report = bind_article.bind_article(ARTICLE, PACK)
    assert report["counts"]["facts"]["total"] == 5
    assert report["counts"]["facts"]["bound"] == 4
    assert report["counts"]["facts"]["unsupported"] == 1
    unsupported = report["unsupported_facts"][0]
    assert unsupported["value"] == "2077"
    assert unsupported["paragraph_index"] == 2
    assert report["status"] == "partial"


def test_number_boundary_does_not_match_a_longer_number() -> None:
    article = "产品有 18 年历史。"
    report = bind_article.bind_article(article, PACK)
    assert report["unsupported_facts"][0]["value"] == "18"


def test_fact_match_carries_claim_evidence_and_timecode() -> None:
    report = bind_article.bind_article("产品有 1805 年历史。", PACK)
    fact = report["paragraphs"][0]["facts"][0]
    assert fact["value"] == "1805"
    assert fact["status"] == "bound"
    match = fact["matches"][0]
    assert match["kind"] in {"sentence", "claim", "evidence"}
    assert match["claim_ids"] == ["c1"]
    assert match["evidence_ids"] == ["e1"]
    assert match["timecode"] == {"t_start_ms": 0, "t_end_ms": 1000}


def test_quote_bound_and_long_unbound_are_reported() -> None:
    report = bind_article.bind_article(ARTICLE, PACK)
    quotes = [
        quote for paragraph in report["paragraphs"] for quote in paragraph["quotes"]
    ]
    assert any(
        quote["value"] == "产品有 1805 年历史。" and quote["status"] == "bound"
        for quote in quotes
    )
    assert any(
        quote["value"] == "这是一个不存在的结论。" and quote["status"] == "unbound"
        for quote in quotes
    )
    assert report["counts"]["quotes"]["unbound_long"] == 1


def test_paragraph_matching_reports_scores_and_status() -> None:
    report = bind_article.bind_article(ARTICLE, PACK)
    first = report["paragraphs"][0]
    assert first["status"] == "bound"
    assert first["best_score"] >= bind_article.BOUND_THRESHOLD
    assert first["matches"]
    assert first["matches"][0]["claim_ids"] == ["c1"]


def test_latin_token_binds_when_present() -> None:
    pack = {
        "sentences": [
            {
                "sentence_id": "s1",
                "text": "DeepSeek Harness 是一个运行框架。",
                "t_start_ms": 0,
                "t_end_ms": 1000,
            }
        ],
        "claims": [],
        "evidence": [],
        "frames": [],
    }
    report = bind_article.bind_article("DeepSeek Harness 能做很多事。", pack)
    assert report["counts"]["facts"]["unsupported"] == 0
    values = [fact["value"] for fact in report["paragraphs"][0]["facts"]]
    assert "DeepSeek" in values
    assert "Harness" in values


def test_normalized_quote_matches_filler_variant() -> None:
    pack = {
        "sentences": [
            {
                "sentence_id": "s1",
                "text": "他说：“产品有 1805 年历史，嗯，很久了。”",
                "t_start_ms": 0,
                "t_end_ms": 1000,
            }
        ],
        "claims": [],
        "evidence": [],
        "frames": [],
    }
    report = bind_article.bind_article("“产品有 1805 年历史，很久了”", pack)
    quote = report["paragraphs"][0]["quotes"][0]
    assert quote["status"] == "bound"
    assert quote["matches"][0]["match_type"] == "normalized"
    assert report["counts"]["quotes"]["unbound_long"] == 0


def test_optional_full_transcript_fills_pack_selection_gaps() -> None:
    pack = {
        "sentences": [
            {
                "sentence_id": "s1",
                "text": "第一句。",
                "t_start_ms": 0,
                "t_end_ms": 1000,
            }
        ],
        "claims": [],
        "evidence": [],
        "frames": [],
    }
    transcript = [
        {
            "sentence_id": "s1",
            "text": "第一句。",
            "t_start_ms": 0,
            "t_end_ms": 1000,
        },
        {
            "sentence_id": "s2",
            "text": "产品有 1805 年历史。",
            "t_start_ms": 1000,
            "t_end_ms": 2000,
        },
    ]
    report = bind_article.bind_article(
        "产品有 1805 年历史。", pack, transcript
    )
    assert report["counts"]["facts"]["bound"] == 1
    assert report["counts"]["sources"]["sentences"] == 2


def test_block_source_matching_uses_rendered_text_and_offsets() -> None:
    rendered = "## 第一段\n产品有 1805 年历史，并且有详细的记录。"
    source_map = {
        "blocks": [
            {
                "block_index": 0,
                "segment_id": "seg1",
                "text_start": 0,
                "text_end": len(rendered),
                "sentence_ids": ["s1"],
                "claim_ids": ["c1"],
            }
        ]
    }
    report = bind_article.bind_article(
        "产品有 1805 年历史，并且有详细的记录。",
        PACK,
        rendered_text=rendered,
        source_map=source_map,
    )
    first = report["paragraphs"][0]
    assert first["matches"]
    assert first["matches"][0]["kind"] == "block"
    assert report["counts"]["sources"]["blocks"] == 1


def test_input_scope_marks_fact_in_input() -> None:
    report = bind_article.bind_article(
        "产品有 1805 年历史。",
        PACK,
        input_text="第一句。产品有 1805 年历史。",
    )
    fact = report["paragraphs"][0]["facts"][0]
    assert fact["input_status"] == "in_input"
    assert report["counts"]["facts"]["in_input"] == 1
    assert report["input_scope_checked"] is True
    assert report["status"] == "complete"


def test_input_scope_marks_fact_outside_input() -> None:
    report = bind_article.bind_article(
        "产品有 1805 年历史。",
        PACK,
        input_text="第一句。",
    )
    fact = report["paragraphs"][0]["facts"][0]
    assert fact["input_status"] == "outside_input"
    assert report["counts"]["facts"]["outside_input"] == 1
    assert report["outside_input_facts"]
    assert report["status"] == "partial"


def test_format_variant_spacing_is_in_input() -> None:
    pack = {
        "sentences": [
            {
                "sentence_id": "s1",
                "text": "ClaudeCode 是一个工具。",
                "t_start_ms": 0,
                "t_end_ms": 1000,
            }
        ],
        "claims": [],
        "evidence": [],
        "frames": [],
    }
    report = bind_article.bind_article(
        "Claude 是一个工具。",
        pack,
        input_text="ClaudeCode 是一个工具。",
    )
    fact = report["paragraphs"][0]["facts"][0]
    assert fact["value"] == "Claude"
    assert fact["input_status"] == "in_input"
    assert fact["format_variant"] is True
    assert report["counts"]["facts"]["format_variant"] == 1
    assert report["status"] == "complete"


def test_format_variant_unit_is_in_input() -> None:
    pack = {
        "sentences": [
            {
                "sentence_id": "s1",
                "text": "存储占用 3 个 G。",
                "t_start_ms": 0,
                "t_end_ms": 1000,
            }
        ],
        "claims": [],
        "evidence": [],
        "frames": [],
    }
    report = bind_article.bind_article(
        "存储占用 3 GB。",
        pack,
        input_text="存储占用 3 个 G。",
    )
    facts = {
        fact["value"]: fact for fact in report["paragraphs"][0]["facts"]
    }
    assert facts["GB"]["input_status"] == "in_input"
    assert facts["GB"]["format_variant"] is True
    assert report["status"] == "complete"


def test_quote_outside_input_is_reported() -> None:
    report = bind_article.bind_article(
        "“产品有 1805 年历史。”",
        PACK,
        input_text="第一句。",
    )
    assert report["counts"]["quotes"]["outside_input"] == 1
    assert report["outside_input_quotes"]
    assert report["status"] == "partial"


def test_no_input_text_marks_not_checked() -> None:
    report = bind_article.bind_article("产品有 1805 年历史。", PACK)
    fact = report["paragraphs"][0]["facts"][0]
    assert fact["input_status"] == "not_checked"
    assert report["input_scope_checked"] is False


def test_no_fact_anchors_is_complete() -> None:
    report = bind_article.bind_article("这是一段纯编辑性的判断，没有数字和专名。", PACK)
    assert report["counts"]["facts"]["total"] == 0
    assert report["counts"]["facts"]["coverage"] == 1.0
    assert report["status"] == "complete"


def test_same_input_same_report() -> None:
    first = bind_article.bind_article(ARTICLE, PACK)
    second = bind_article.bind_article(ARTICLE, PACK)
    assert first == second
