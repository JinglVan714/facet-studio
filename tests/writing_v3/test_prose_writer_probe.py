"""Tests for the P1 prose-only Writer prompt builder (no provider call)."""

from __future__ import annotations

from unittest.mock import patch

from facet_studio.writing_v3 import prose_writer_probe


def test_prose_system_replaces_json_and_id_contract() -> None:
    skill = """# Reader-first explainer

Intro.

## Inputs

- old evidence_pack

## Method

1. Find one thing.
2. Write a short `reader_path` and a `mechanism_or_steps` header.
3. Prefer `real_frame` only when a frame candidate actually shows the operation/result/claim. Otherwise use `text_experiment` or `no_demo`; never imply a demo that the evidence does not contain.

## Evidence discipline

- old grounded span with claim_ids

## Output

Return JSON with "sections".

## Self-review before returning

Old checks.
"""
    system = prose_writer_probe.build_prose_system(skill)
    assert "## Method" in system
    assert "Find one thing." in system
    assert "Markdown article" in system
    assert "claim_ids" not in system
    assert '"sections"' not in system
    assert "old grounded span" not in system
    assert "evidence_text" in system
    assert "Do not output claim/evidence IDs" in system
    assert "Do not expand acronyms" in system
    assert "Copy numbers exactly" in system
    assert "exact substring of the evidence" in system
    assert "reader_path" not in system
    assert "keep them out of the output" in system
    assert "text_experiment" not in system


def test_prose_system_keeps_examples_and_json_input_note() -> None:
    skill = "# Reader-first\n\nIntro.\n\n## Inputs\n\nold\n\n## Method\n\nM.\n"
    system = prose_writer_probe.build_prose_system(
        skill,
        "## 1. Example\n\nGood.",
        input_kind="json",
    )
    assert "## Examples" in system
    assert "## 1. Example" in system
    assert "evidence_view" in system
    assert "edited transcript" not in system


def test_user_prompt_shapes() -> None:
    request = {"central_question": "为什么？"}
    text_prompt = prose_writer_probe.build_user_prompt(
        request, "第一段。", input_kind="text"
    )
    json_prompt = prose_writer_probe.build_user_prompt(
        request, '{"schema":"v1"}', input_kind="json"
    )
    assert '"evidence_text":"第一段。"' in text_prompt
    assert '"evidence_view":{"schema":"v1"}' in json_prompt


def test_dry_run_writes_prompts_without_provider(tmp_path) -> None:
    request = tmp_path / "request.json"
    request.write_text('{"central_question":"为什么？"}', encoding="utf-8")
    source = tmp_path / "input.txt"
    source.write_text("第一段。", encoding="utf-8")
    skill_dir = tmp_path / "skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(
        "# Test reader-first\n\nIntro.\n\n## Inputs\n\n- request\n\n"
        "## Method\n\nFind one thing.\n\n"
        "## Evidence discipline\n\n- Use only evidence.\n\n"
        "## Output\n\nReturn Markdown.\n\n"
        "## Self-review before returning\n\nCheck.\n",
        encoding="utf-8",
    )
    out_dir = tmp_path / "out"
    with patch.object(
        prose_writer_probe,
        "get_settings",
        side_effect=AssertionError("dry run must not read settings"),
    ):
        code = prose_writer_probe.main(
            [
                "--case-id",
                "case",
                "--arm",
                "new_text",
                "--request",
                str(request),
                "--input",
                str(source),
                "--input-kind",
                "text",
                "--skill-dir",
                str(skill_dir),
                "--out-dir",
                str(out_dir),
            ]
        )
    assert code == 0
    assert (out_dir / "prompts" / "prose_writer.system.txt").exists()
    assert (out_dir / "prompts" / "prose_writer.user.txt").exists()
    assert (out_dir / "manifest.json").exists()
    assert not (out_dir / "article.md").exists()
