"""M1 product wiring: prose Writer -> quote hygiene -> post-hoc binding.

This is the technical "writing" entry, not a skill.  It uses the proven
Markdown-only prose contract and the light/full edited text; the default path
does not need claim extraction.  A pack is optional and only used for audit
binding.

- ``--article``: bind/clean an existing article (no model call).
- otherwise: delegate one real or dry-run Writer call to
  ``prose_writer_probe``, then clean and bind.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import prose_writer_probe
from .bind_article import bind_article
from .quote_hygiene import clean_article


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(value, str):
        path.write_text(value, encoding="utf-8")
    else:
        path.write_text(
            json.dumps(value, ensure_ascii=False, indent=1), encoding="utf-8"
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "M1 writing path: one prose Writer call (or an existing article) "
            "+ quote hygiene + deterministic binding."
        )
    )
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--edited-text", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument(
        "--article",
        type=Path,
        help="已有文章：跳过模型，只做 quote hygiene + binding",
    )
    parser.add_argument("--pack", type=Path, help="audit pack（可选）")
    parser.add_argument(
        "--sentences", type=Path, help="完整转写句表（binding 需要）"
    )
    parser.add_argument("--source-map", type=Path)
    parser.add_argument(
        "--skill-dir",
        type=Path,
        default=Path("skills/writing/reader_first_explainer"),
    )
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--no-cache", action="store_true")
    parser.add_argument("--temperature", type=float, default=0.3)
    parser.add_argument("--max-tokens", type=int, default=None)
    parser.add_argument("--model")
    args = parser.parse_args(argv)

    out_dir = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    edited_text = args.edited_text.read_text(encoding="utf-8-sig")
    writer_dir = out_dir / "writer"

    if args.article is not None:
        raw_article = args.article.read_text(encoding="utf-8-sig")
        writer_dir.mkdir(parents=True, exist_ok=True)
        _write(writer_dir / "article.md", raw_article)
        writer_manifest: dict[str, Any] = {
            "status": "external_article",
            "article_path": str(args.article),
        }
    else:
        writer_args = [
            "--case-id",
            args.case_id,
            "--arm",
            "generate",
            "--request",
            str(args.request),
            "--input",
            str(args.edited_text),
            "--input-kind",
            "text",
            "--skill-dir",
            str(args.skill_dir),
            "--out-dir",
            str(writer_dir),
            "--temperature",
            str(args.temperature),
        ]
        if args.run:
            writer_args.append("--run")
        if args.no_cache:
            writer_args.append("--no-cache")
        if args.max_tokens is not None:
            writer_args.extend(["--max-tokens", str(args.max_tokens)])
        if args.model:
            writer_args.extend(["--model", args.model])
        code = prose_writer_probe.main(writer_args)
        if code != 0:
            return code
        writer_manifest_path = writer_dir / "manifest.json"
        writer_manifest = (
            _read_json(writer_manifest_path)
            if writer_manifest_path.exists()
            else {}
        )
        article_path = writer_dir / "article.md"
        if not article_path.exists():
            _write(
                out_dir / "manifest.json",
                {
                    "schema": "v3-generate-v1",
                    "status": "dry_run",
                    "case_id": args.case_id,
                    "writer": writer_manifest,
                    "note": "pass --run to call the writer",
                    "created_at": datetime.now(timezone.utc).isoformat(),
                },
            )
            print(
                json.dumps(
                    {"status": "dry_run", "out_dir": str(out_dir)},
                    ensure_ascii=False,
                    indent=1,
                )
            )
            return 0
        raw_article = article_path.read_text(encoding="utf-8")

    hygiene = clean_article(raw_article, edited_text)
    cleaned = hygiene["article"]
    _write(out_dir / "article_raw.md", raw_article)
    _write(out_dir / "article.md", cleaned)
    _write(out_dir / "quote_hygiene.json", hygiene["report"])
    _write(out_dir / "reader.md", cleaned)

    binding: dict[str, Any] | None = None
    if args.pack is not None and args.sentences is not None:
        pack = _read_json(args.pack)
        sentences = _read_json(args.sentences).get("sentences", [])
        source_map = (
            _read_json(args.source_map) if args.source_map else None
        )
        binding = bind_article(
            cleaned,
            pack,
            sentences,
            rendered_text=edited_text,
            source_map=source_map,
            input_text=edited_text,
        )
        _write(out_dir / "binding.json", binding)

    manifest = {
        "schema": "v3-generate-v1",
        "status": "complete" if binding and binding["status"] == "complete" else "partial",
        "case_id": args.case_id,
        "writer": writer_manifest,
        "quote_hygiene": hygiene["report"],
        "binding_status": binding["status"] if binding else None,
        "binding_counts": binding["counts"] if binding else None,
        "article_chars": len(cleaned),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    _write(out_dir / "manifest.json", manifest)
    print(
        json.dumps(
            {
                "status": manifest["status"],
                "out_dir": str(out_dir),
                "article_chars": manifest["article_chars"],
                "quote_hygiene": hygiene["report"],
                "binding_status": manifest["binding_status"],
                "binding_counts": manifest["binding_counts"],
            },
            ensure_ascii=False,
            indent=1,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
