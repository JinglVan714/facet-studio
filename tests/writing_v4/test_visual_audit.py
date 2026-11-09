import json
from pathlib import Path

from facet_studio.writing_v4.visual_audit import (
    audit_content,
    audit_decision,
    extract_candidates,
    filter_content_for_approved,
    normalize_audit,
)


def _write_content(tmp_path: Path) -> Path:
    (tmp_path / "figures").mkdir()
    (tmp_path / "figures" / "fig-01.jpg").write_bytes(b"fake")
    (tmp_path / "figures" / "fig-02.jpg").write_bytes(b"fake")
    content = (
        "正文第一段。\n\n"
        "（画面参考 1（可选，非必用）：手把鸡块抛起；图：figures/fig-01.jpg）\n\n"
        "正文第二段。\n\n"
        "（画面参考 2（可选，非必用）：博主出镜讲解；图：figures/fig-02.jpg）\n"
    )
    path = tmp_path / "content.md"
    path.write_text(content, encoding="utf-8")
    return path


def test_extract_candidates_gets_context_and_files(tmp_path: Path) -> None:
    path = _write_content(tmp_path)
    candidates = extract_candidates(path.read_text(encoding="utf-8"))
    assert [item["file"] for item in candidates] == [
        "figures/fig-01.jpg",
        "figures/fig-02.jpg",
    ]
    assert "手把鸡块抛起" in candidates[0]["note"]
    assert "正文第一段" in candidates[0]["context"]


def test_extract_candidates_supports_legacy_图示_notes(tmp_path: Path) -> None:
    (tmp_path / "figures").mkdir()
    (tmp_path / "figures" / "fig-01.jpg").write_bytes(b"fake")
    (tmp_path / "figures" / "fig-02.jpg").write_bytes(b"fake")
    content = (
        "正文第一段。\n\n"
        "（图示 1：晋剧狸猫换太子；图：figures/fig-01.jpg）\n\n"
        "正文第二段。\n\n"
        "（图示 2：博主出镜；图：figures/fig-02.jpg）\n"
    )
    candidates = extract_candidates(content)
    assert [item["file"] for item in candidates] == [
        "figures/fig-01.jpg",
        "figures/fig-02.jpg",
    ]
    filtered = filter_content_for_approved(
        content,
        [
            {
                "file": "figures/fig-01.jpg",
                "caption": "狸猫换太子戏台",
            }
        ],
    )
    assert "关键帧候选（已通过视觉审计，可选）：狸猫换太子戏台" in filtered
    assert "figures/fig-01.jpg" in filtered
    assert "figures/fig-02.jpg" not in filtered


def test_audit_decision_and_normalize() -> None:
    allowed = normalize_audit(
        {
            "scene_type": "operation",
            "has_person": False,
            "has_watermark": False,
            "quality": "clear",
            "self_contained": True,
            "info_value": True,
        }
    )
    assert allowed["use_keyframe"] is True
    assert audit_decision({**allowed, "has_person": True}) is False
    assert audit_decision({**allowed, "has_watermark": True}) is False
    assert audit_decision({**allowed, "quality": "ok"}) is False
    assert audit_decision({**allowed, "scene_type": "ui"}) is False


def test_audit_content_keeps_only_approved_frames(tmp_path: Path) -> None:
    path = _write_content(tmp_path)

    class FakeClient:
        def __init__(self) -> None:
            self.calls = 0

        def complete(self, **kwargs):
            self.calls += 1
            text = json.dumps(
                {
                    "scene_type": "operation" if self.calls == 1 else "person",
                    "has_person": self.calls != 1,
                    "has_watermark": False,
                    "quality": "clear",
                    "self_contained": True,
                    "info_value": True,
                    "caption": "手把鸡块抛起" if self.calls == 1 else "博主出镜",
                    "reason": "操作细节" if self.calls == 1 else "人物出镜",
                },
                ensure_ascii=False,
            )

            class Response:
                pass

            Response.text = text
            return Response()

    result = audit_content(path, client=FakeClient(), max_frames=2)
    assert result["candidate_count"] == 2
    assert result["approved_count"] == 1
    assert result["approved"][0]["file"] == "figures/fig-01.jpg"
    assert (tmp_path / "visual_audit.json").is_file()

    filtered = filter_content_for_approved(
        path.read_text(encoding="utf-8"), result["approved"]
    )
    assert "关键帧候选（已通过视觉审计，可选）：手把鸡块抛起" in filtered
    assert "figures/fig-02.jpg" not in filtered
    assert "画面参考" not in filtered
