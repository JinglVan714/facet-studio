"""Tests for visual planning validation and deterministic rendering."""

from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageDraw

from lunograph.media.planner import _validate, plan_visuals
from lunograph.media.render import (
    _caption,
    _chart_svg,
    _flow_svg,
    _frame_readability,
    _layered_ranks,
    _short_edge_label,
    _split_back_edges,
    _tree_layout,
    _wrap_text,
    render_visual_plan,
)
from lunograph.media.sections import join_article, split_article

ARTICLE = (
    "# 标题\n\n开头。\n\n"
    "## 第一节\n\n第一节正文，数字 0.756。\n\n"
    "## 第二节\n\n第二节正文，流程。"
)

INDEX = {
    "index_hash": "idx",
    "video_id": "BVtest",
    "frames": [
        {
            "frame_id": "f1",
            "t_ms": 500,
            "file": "frames/f1.jpg",
            "caption": "流程画面",
            "selected": True,
            "segment_ids": ["seg1"],
        }
    ],
    "claims": [
        {
            "claim_id": "c1",
            "text": "数字 0.756",
            "status": "supported",
            "scope": "",
            "t_start_ms": 0,
            "t_end_ms": 1000,
        }
    ],
    "evidence": [
        {
            "evidence_id": "e1",
            "claim_ids": ["c1"],
            "quote": "0.756",
            "t_start_ms": 0,
            "t_end_ms": 1000,
        }
    ],
    "sentences": [
        {"sentence_id": "s1", "segment_id": "seg1", "text": "0.756", "t_start_ms": 0, "t_end_ms": 1000}
    ],
}

PLAN = {
    "schema_version": "visual-plan-v1",
    "status": "complete",
    "visuals": [
        {
            "section_index": 1,
            "kind": "table",
            "caption": "看指标",
            "table": {
                "title": "指标",
                "columns": ["指标", "数值"],
                "rows": [["分数", "0.756"]],
            },
            "source_ids": ["e1"],
        },
        {
            "section_index": 1,
            "kind": "chart",
            "caption": "看分数",
            "chart": {
                "type": "bar",
                "title": "分数",
                "data": [{"label": "蝙蝠", "value": "0.756"}],
                "unit": None,
            },
            "source_ids": ["e1"],
        },
        {
            "section_index": 2,
            "kind": "diagram",
            "caption": "看流程",
            "diagram": {
                "nodes": [
                    {"id": "n1", "label": "收集问题"},
                    {"id": "n2", "label": "交给模型"},
                ],
                "edges": [{"from": "n1", "to": "n2", "label": "然后"}],
            },
            "source_ids": ["c1"],
        },
        {
            "section_index": 2,
            "kind": "real_frame",
            "caption": "看画面",
            "frame_id": "f1",
            "source_ids": ["f1"],
        },
    ],
}

RESPONSE_PAYLOAD = {
    "visuals": [
        {
            "section_index": 1,
            "kind": "chart",
            "caption": "看分数",
            "chart": {"type": "bar", "data": [{"label": "分数", "value": "0.756"}]},
            "source_ids": ["e1"],
        },
        {
            "section_index": 2,
            "kind": "diagram",
            "caption": "看流程",
            "diagram": {
                "nodes": [{"id": "n1", "label": "收集问题"}, {"id": "n2", "label": "交给模型"}],
                "edges": [{"from": "n1", "to": "n2"}],
            },
        },
        {
            "section_index": 2,
            "kind": "real_frame",
            "caption": "看画面",
            "frame_id": "f1",
        },
        {
            "section_index": 1,
            "kind": "chart",
            "caption": "坏数据",
            "chart": {"type": "bar", "data": [{"label": "编造", "value": "0.999"}]},
        },
        {
            "section_index": 2,
            "kind": "real_frame",
            "caption": "坏帧",
            "frame_id": "f9",
        },
    ]
}


class _Usage:
    def as_dict(self):
        return {"total_tokens": 10}


class _Response:
    text = json.dumps(RESPONSE_PAYLOAD, ensure_ascii=False)
    usage = _Usage()
    latency_ms = 5
    cached = False
    finish_reason = "stop"


class _Provider:
    model = "fake"

    def __init__(self) -> None:
        self.user: dict = {}

    def complete(self, **kwargs):
        self.user = json.loads(kwargs["user"])
        return _Response()


def test_split_and_join_article() -> None:
    title, sections = split_article(ARTICLE)
    assert title == "# 标题"
    assert [section["heading"] for section in sections] == ["", "第一节", "第二节"]
    assert join_article(title, sections).strip() == ARTICLE.strip()


def test_plan_visuals_validates_numbers_and_frames(tmp_path: Path) -> None:
    plan = plan_visuals(
        ARTICLE,
        INDEX,
        {"request_id": "req"},
        tmp_path,
        run=True,
        provider=_Provider(),
    )
    assert plan["status"] == "complete"
    assert [visual["kind"] for visual in plan["visuals"]] == [
        "chart",
        "diagram",
        "real_frame",
    ]
    assert any(item["reason"] == "chart_number_not_in_evidence" for item in plan["skipped"])
    assert any(item["reason"] == "unknown_frame" for item in plan["skipped"])
    assert plan["usage"] == {"total_tokens": 10}


def test_render_visual_plan_inserts_table_chart_diagram_frame(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    frame_file = data_root / "BVtest" / "frames" / "f1.jpg"
    frame_file.parent.mkdir(parents=True)
    image = Image.new("RGB", (640, 360), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle([40, 40, 600, 120], fill="black")
    draw.rectangle([80, 160, 560, 320], fill="#2f6fed")
    image.save(frame_file)
    out_dir = tmp_path / "output"
    result = render_visual_plan(
        ARTICLE,
        PLAN,
        INDEX,
        out_dir,
        data_root=data_root,
        video_id="BVtest",
    )
    article = result["article"]
    assert "| 指标 | 数值 |" in article
    assert "![chart](assets/chart_" in article
    assert "![diagram](assets/diagram_" in article
    assert "![frame](assets/frame_f1" in article
    assert "看指标" in article
    assert len(result["assets"]) == 4
    assert (out_dir / "assets").is_dir()
    assert result["rendered"] == 4


def test_render_places_visual_before_section_takeaway(tmp_path: Path) -> None:
    article = "# 标题\n\n## 第一节\n\n第一段说明。\n\n最后一句是本节收束。"
    result = render_visual_plan(
        article,
        PLAN,
        INDEX,
        tmp_path / "output",
        data_root=tmp_path / "missing",
        video_id="BVtest",
    )
    rendered_article = result["article"]
    assert rendered_article.index("![chart]") < rendered_article.index("最后一句是本节收束")


def test_render_skips_table_when_section_already_has_table(tmp_path: Path) -> None:
    article = "# 标题\n\n## 第一节\n\n| 指标 | 数值 |\n|---|---|\n| 分数 | 0.756 |"
    result = render_visual_plan(
        article,
        {
            "visuals": [
                {
                    "section_index": 1,
                    "kind": "table",
                    "caption": "看指标",
                    "table": {"columns": ["指标", "数值"], "rows": [["分数", "0.756"]]},
                }
            ]
        },
        INDEX,
        tmp_path / "output",
    )
    assert result["rendered"] == 0
    assert any(item["reason"] == "section_has_table" for item in result["skipped"])


def test_render_skips_low_readability_frame(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    frame_file = data_root / "BVtest" / "frames" / "f1.jpg"
    frame_file.parent.mkdir(parents=True)
    Image.new("RGB", (640, 360), "black").save(frame_file)
    result = render_visual_plan(
        ARTICLE,
        {
            "visuals": [
                {
                    "section_index": 1,
                    "kind": "real_frame",
                    "caption": "看画面",
                    "frame_id": "f1",
                }
            ]
        },
        INDEX,
        tmp_path / "output",
        data_root=data_root,
        video_id="BVtest",
    )
    assert result["rendered"] == 0
    assert any(
        item["reason"] == "frame_low_readability" for item in result["skipped"]
    )


def test_frame_readability_accepts_dark_slide_with_caption(tmp_path: Path) -> None:
    frame_file = tmp_path / "dark_slide.jpg"
    image = Image.new("RGB", (640, 360), "black")
    draw = ImageDraw.Draw(image)
    draw.rectangle([40, 40, 240, 90], fill="white")
    image.save(frame_file)
    result = _frame_readability(
        frame_file,
        "真实结果：768 个数字压扁成 2D，熊猫、老虎、长颈鹿各自聚成一堆",
    )
    assert result["status"] == "ok"
    assert result["override"] == "caption_dark_slide"
    assert result["caption_chars"] >= 20


def test_frame_readability_rejects_dark_frame_without_caption(tmp_path: Path) -> None:
    frame_file = tmp_path / "black.jpg"
    Image.new("RGB", (640, 360), "black").save(frame_file)
    result = _frame_readability(frame_file, "看画面")
    assert result["status"] == "low"


def test_plan_visuals_respects_max_visuals(tmp_path: Path) -> None:
    provider = _Provider()
    plan = plan_visuals(
        ARTICLE,
        INDEX,
        {"request_id": "req", "media_policy": {"max_assets": 6}},
        tmp_path,
        run=True,
        provider=provider,
        max_visuals=2,
        genre="mixed",
    )
    assert plan["max_visuals"] == 2
    assert plan["genre"] == "mixed"
    assert len(plan["visuals"]) == 2
    assert any(item["reason"] == "max_visuals" for item in plan["skipped"])
    assert provider.user["max_visuals"] == 2
    assert provider.user["genre"] == "mixed"


def test_plan_visuals_uses_request_max_assets(tmp_path: Path) -> None:
    plan = plan_visuals(
        ARTICLE,
        INDEX,
        {"request_id": "req", "media_policy": {"max_assets": 2}},
        tmp_path,
        run=True,
        provider=_Provider(),
    )
    assert plan["max_visuals"] == 2
    assert len(plan["visuals"]) == 2


def test_render_skips_missing_frame_file(tmp_path: Path) -> None:
    result = render_visual_plan(
        ARTICLE,
        {
            "visuals": [
                {
                    "section_index": 1,
                    "kind": "real_frame",
                    "caption": "看画面",
                    "frame_id": "f1",
                }
            ]
        },
        INDEX,
        tmp_path / "output",
        data_root=tmp_path / "missing",
        video_id="BVtest",
    )
    assert result["rendered"] == 0
    assert any(item["reason"] == "frame_file_missing" for item in result["skipped"])


def test_plan_visuals_passes_planned_slots_to_provider(tmp_path: Path) -> None:
    provider = _Provider()
    plan_visuals(
        ARTICLE,
        INDEX,
        {"request_id": "req"},
        tmp_path,
        run=True,
        provider=provider,
        writing_plan={
            "title": "标题",
            "toc": [
                {
                    "index": 1,
                    "heading": "第一节",
                    "visual": {"kind": "diagram", "intent": "画出流程"},
                },
                {
                    "index": 2,
                    "heading": "第二节",
                    "visual": {"kind": "none", "intent": ""},
                },
            ],
        },
    )
    assert provider.user["planned_visuals"] == [
        {
            "section_index": 1,
            "heading": "第一节",
            "kind": "diagram",
            "intent": "画出流程",
        }
    ]


def test_layered_ranks_keeps_parallel_branches_on_the_same_rank() -> None:
    ranks = _layered_ranks(
        ["n1", "n2", "n3", "n4", "n5", "n6", "n7"],
        [
            {"from": "n1", "to": "n2", "label": ""},
            {"from": "n2", "to": "n5", "label": ""},
            {"from": "n3", "to": "n4", "label": ""},
            {"from": "n4", "to": "n6", "label": ""},
            {"from": "n5", "to": "n7", "label": ""},
            {"from": "n6", "to": "n7", "label": ""},
        ],
    )
    assert ranks["n1"] == ranks["n3"] == 0
    assert ranks["n2"] == ranks["n4"] == 1
    assert ranks["n5"] == ranks["n6"] == 2
    assert ranks["n7"] == 3


def test_short_edge_label_keeps_arrows_terse() -> None:
    assert (
        _short_edge_label(
            "每一轮循环都在管：参数合法吗、格式对不对、上下文多长、要不要确认、要不要重试"
        )
        == "每一轮循环都在管"
    )
    assert len(_short_edge_label("没有标点的一段很长的边标签" * 3)) <= 18


def test_caption_does_not_duplicate_look_here() -> None:
    assert _caption("chart", "看这里：看分数") == (
        "*看分数（根据视频内容绘制）*"
    )
    assert _caption("diagram", "看哪里：看流程") == (
        "*看流程（根据视频内容绘制）*"
    )
    assert _caption("chart", "0.8 门槛") == (
        "*看哪里：0.8 门槛（根据视频内容绘制）*"
    )


def test_caption_marks_hypothesis_and_demo_status() -> None:
    assert _caption("chart", "看两根柱子", "hypothesis") == (
        "*看两根柱子（根据视频中的假设/示意绘制）*"
    )
    assert _caption("table", "看结果", "demo") == (
        "*看结果（根据视频中的单次演示整理）*"
    )


def test_wrap_text_preserves_content_and_chart_wraps_labels() -> None:
    text = "两张蝙蝠照片与一张老虎照片的相似度"
    lines = _wrap_text(text, 120, 13, 3)
    assert "".join(lines) == text
    assert len(lines) > 1
    quoted = _wrap_text("粉丝追问/命名：腿冷不冷、叫“大头菜”", 120, 13, 3)
    assert any("“大头菜”" in line for line in quoted)
    assert not any(line[:1] in "，。；：、！？》」』" for line in quoted[1:])
    svg = _chart_svg(
        {
            "type": "bar",
            "title": "分数对比：跨模态分数整体低于 0.8",
            "data": [
                {"label": "两张蝙蝠照片", "value": "0.951"},
                {"label": "会飞的动物 与 最像的蝙蝠", "value": "0.756"},
            ],
        }
    )
    assert svg is not None
    assert "两张蝙蝠照片" in svg
    assert "会飞的动物" in svg
    assert "[18]" not in svg


def test_flow_svg_wraps_labels_and_routes_edges_between_ranks() -> None:
    svg = _flow_svg(
        {
            "nodes": [
                {"id": "n1", "label": "输入一句话"},
                {"id": "n2", "label": "embed() 把文字变成 768 个数字"},
                {"id": "n3", "label": "预计算向量库"},
                {"id": "n4", "label": "逐个点积"},
                {"id": "n5", "label": "排序后取前 10"},
            ],
            "edges": [
                {"from": "n1", "to": "n2", "label": "送入"},
                {"from": "n2", "to": "n4", "label": "查询"},
                {"from": "n3", "to": "n4", "label": "参与"},
                {"from": "n4", "to": "n5", "label": "得到"},
            ],
        }
    )
    assert svg is not None
    assert "embed() 把文字变成" in svg
    assert "768 个数字" in svg
    assert svg.count("marker-end='url(#arrow)'") == 4


def test_tree_layout_handles_mind_map_star() -> None:
    tree = _tree_layout(
        ["root", "a", "b", "c", "d"],
        [{"from": "root", "to": child, "label": ""} for child in "abcd"],
    )
    assert tree is not None
    root, depth, children = tree
    assert root == "root"
    assert depth == {"root": 0, "a": 1, "b": 1, "c": 1, "d": 1}
    assert children["root"] == ["a", "b", "c", "d"]


def test_split_back_edges_makes_cycles_drawable() -> None:
    forward, backward = _split_back_edges(
        ["n1", "n2", "n3"],
        [
            {"from": "n1", "to": "n2", "label": ""},
            {"from": "n2", "to": "n3", "label": ""},
            {"from": "n3", "to": "n1", "label": ""},
        ],
    )
    assert len(forward) == 2
    assert backward == [{"from": "n3", "to": "n1", "label": ""}]


def test_visual_planner_rejects_invented_code_identifiers() -> None:
    _, sections = split_article(ARTICLE)
    visuals, skipped = _validate(
        {
            "visuals": [
                {
                    "section_index": 2,
                    "kind": "table",
                    "caption": "看模式",
                    "table": {
                        "columns": ["模式", "工具"],
                        "rows": [["方案 A", "只暴露 tool_x（tool_x）"]],
                    },
                }
            ]
        },
        sections=sections,
        index=INDEX,
        max_visuals=6,
    )
    assert visuals == []
    assert any(
        item["reason"] == "identifier_not_in_evidence" for item in skipped
    )
