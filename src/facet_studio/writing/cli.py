"""CLI for the minimal writing pipeline.

Dry-run is the default; pass ``--run`` to perform one Writer call.

Example::

    python -m facet_studio.writing.cli \\
      --request evals/writing/requests/BV17.json \\
      --skill-dir skills/writing/reader_first_explainer \\
      --index runs/_consume_index/BV17.json \\
      --edited-text runs/m1_light/BV17/light_text.txt \\
      --pack runs/m1_light/BV17/light_pack.json \\
      --sentences runs/v3_poc/BV17_transcript/sentences.json \\
      --source-map runs/m1_light/BV17/source_map.json \\
      --out-dir runs/_writing/BV17
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .pipeline import run_pipeline


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Minimal writing pipeline (dry-run by default).")
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--skill-dir", type=Path, required=True)
    parser.add_argument("--index", type=Path, required=True)
    parser.add_argument("--edited-text", type=Path, required=True)
    parser.add_argument("--pack", type=Path, required=True)
    parser.add_argument("--sentences", type=Path, required=True)
    parser.add_argument("--source-map", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument(
        "--profile",
        default="auto",
        choices=["auto", "full_text", "claim_lean", "index_parts", "sectioned"],
    )
    parser.add_argument("--run", action="store_true")
    parser.add_argument(
        "--brief-mode",
        default="auto",
        choices=["auto", "none", "mini", "full", "human_review"],
        help="editorial brief policy; auto is advisory and overridable",
    )
    parser.add_argument("--model")
    parser.add_argument("--temperature", type=float, default=0.3)
    parser.add_argument("--max-tokens", type=int, default=None)
    parser.add_argument("--no-cache", action="store_true")
    parser.add_argument(
        "--brief-full-text",
        action="store_true",
        help="force full evidence text into the brief planner (default: auto)",
    )
    parser.add_argument(
        "--brief-source-map-only",
        action="store_true",
        help="force source-map-only brief input (default: full text for full mode)",
    )
    parser.add_argument(
        "--no-visuals",
        action="store_true",
        help="disable visual planner/renderer (default: on when media allowed)",
    )
    parser.add_argument(
        "--no-verifier",
        action="store_true",
        help="disable the independent semantic verifier",
    )
    parser.add_argument(
        "--verify-after-repair",
        action="store_true",
        help="run a read-only post-repair verifier confirmation (extra call)",
    )
    parser.add_argument(
        "--no-polish",
        action="store_true",
        help="disable the final style/voice polish pass",
    )
    args = parser.parse_args(argv)

    result = run_pipeline(
        request_path=args.request,
        skill_dir=args.skill_dir,
        index_path=args.index,
        edited_text_path=args.edited_text,
        pack_path=args.pack,
        sentences_path=args.sentences,
        source_map_path=args.source_map,
        out_dir=args.out_dir,
        run=args.run,
        profile=args.profile,
        model=args.model,
        temperature=args.temperature,
        max_tokens=args.max_tokens,
        no_cache=args.no_cache,
        visuals=not args.no_visuals,
        verifier=not args.no_verifier,
        verify_after_repair=args.verify_after_repair,
        polish=not args.no_polish,
        brief_mode=args.brief_mode,
        brief_include_full_text=(
            False
            if args.brief_source_map_only
            else True if args.brief_full_text else None
        ),
    )
    print(json.dumps(result, ensure_ascii=False, indent=1))
    status = result.get("status")
    if status in {"dry_run", "complete", "partial"}:
        return 0
    if status == "provider_unconfigured":
        return 2
    if status == "unsupported_profile":
        return 3
    return 4


if __name__ == "__main__":
    sys.exit(main())
