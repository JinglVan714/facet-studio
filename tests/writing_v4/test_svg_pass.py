import xml.etree.ElementTree as ET

import pytest

from facet_studio.writing_v4.svg_pass import (
    PLACEHOLDER,
    SpecError,
    build_svg_assets,
    normalize_spec,
    render_svg,
)


def test_placeholder_regex_finds_brief() -> None:
    text = "前言\n\n<!-- svg: 三层分类：毛色 / 类群 / 登记 -->\n\n后文"
    matches = list(PLACEHOLDER.finditer(text))
    assert len(matches) == 1
    assert "三层分类" in matches[0].group(1)


def test_normalize_rejects_too_few_items() -> None:
    with pytest.raises(SpecError):
        normalize_spec({"kind": "flow", "items": [{"label": "只有一个"}]})


def test_normalize_defaults_kind_and_caption() -> None:
    spec = normalize_spec(
        {
            "title": "两层关系",
            "items": [
                {"label": "A", "detail": "第一层"},
                {"label": "B", "detail": "第二层"},
            ],
            "caption": "两层关系",
        }
    )
    assert spec["kind"] == "flow"
    assert spec["caption"].startswith("示意")


@pytest.mark.parametrize("kind", ["two-axis", "compare", "matrix", "cards", "cause"])
def test_relationship_kinds_are_rejected(kind: str) -> None:
    with pytest.raises(SpecError):
        normalize_spec(
            {
                "kind": kind,
                "title": "关系图",
                "items": [
                    {"label": "A", "detail": "a"},
                    {"label": "B", "detail": "b"},
                ],
            }
        )


def test_render_flow_is_valid_svg() -> None:
    spec = normalize_spec(
        {
            "kind": "flow",
            "title": "三步",
            "items": [
                {"label": "洗", "detail": "先洗"},
                {"label": "切", "detail": "再切"},
                {"label": "炸", "detail": "最后炸"},
            ],
        }
    )
    svg = render_svg(spec)
    ET.fromstring(svg)
    assert svg.count("<rect") == 3
    assert 'marker-end="url(#arrow)"' in svg


@pytest.mark.parametrize(
    "kind",
    ["tree", "timeline"],
)
def test_render_new_visual_kinds(kind: str) -> None:
    spec = normalize_spec(
        {
            "kind": kind,
            "title": "语义图",
            "items": [
                {"label": "一", "detail": "第一步"},
                {"label": "二", "detail": "第二步"},
                {"label": "三", "detail": "第三步"},
                {"label": "四", "detail": "第四步"},
            ],
        }
    )
    svg = render_svg(spec)
    ET.fromstring(svg)
    assert "<svg" in svg


def test_build_svg_assets_omits_caption() -> None:
    class FakeClient:
        def complete(self, **kwargs):
            class Response:
                text = '{"kind":"tree","title":"三点","items":[{"label":"A","detail":"a"},{"label":"B","detail":"b"}],"caption":"示意"}'

            return Response()

    article, report, assets = build_svg_assets(
        "前文\n\n<!-- svg: 三点 -->\n\n后文",
        client=FakeClient(),
        key_prefix="test",
    )
    assert len(assets) == 1
    assert "![](figures/svg-01.svg)" in article
    assert "![示意" not in article
    assert "caption" in report


def test_build_svg_assets_skips_unsupported_kind() -> None:
    class FakeClient:
        def complete(self, **kwargs):
            class Response:
                text = '{"kind":"two-axis","title":"分数轴","items":[{"label":"文字","detail":"0.6–0.76"},{"label":"图片","detail":"0.78–0.95"}]}'

            return Response()

    article, report, assets = build_svg_assets(
        "前文\n\n<!-- svg: 分数分布 -->\n\n后文",
        client=FakeClient(),
        key_prefix="test",
    )
    assert assets == []
    assert "![](figures/" not in article
    assert "unsupported kind" in report


def test_render_escapes_xml() -> None:
    spec = normalize_spec(
        {
            "kind": "flow",
            "title": "A & B",
            "items": [
                {"label": "<分类>", "detail": "x & y"},
                {"label": "第二层", "detail": ""},
            ],
        }
    )
    svg = render_svg(spec)
    ET.fromstring(svg)
    assert "&lt;分类&gt;" in svg
    assert "&amp;" in svg
