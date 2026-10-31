"""v3 claim extraction/aggregation: passages -> writing-level claims.

One model call over the passage list.  The model merges sentence fragments,
skips greetings/small talk/logistics, and returns claims with exact quotes and
sentence IDs.  Code validates quotes, dedupes near-duplicates, derives stable
claim/evidence IDs, and writes a trace receipt.

No outside facts; no per-video vocabulary.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

from lunograph.core.hashing import semantic_hash
from lunograph.core.jsonutil import StructuredOutputError, extract_json_object
from lunograph.providers.llm import DeepSeekLLM, ProviderError
from lunograph.runtime.budget import BudgetPolicy, BudgetState

from .trace import TraceRecorder

KINDS = {"fact", "opinion", "experience", "inference", "instruction"}
STATUSES = {"supported", "bounded"}
NORMALIZE = re.compile(r"\s+")


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _normalize(text: str) -> str:
    return NORMALIZE.sub("", text or "")


def _bigrams(text: str) -> set[str]:
    value = _normalize(text).lower()
    return {value[i : i + 2] for i in range(len(value) - 1)}


def _near_duplicate(a: str, b: str, threshold: float = 0.86) -> bool:
    ga, gb = _bigrams(a), _bigrams(b)
    if not ga or not gb:
        return _normalize(a) == _normalize(b)
    return len(ga & gb) / len(ga | gb) >= threshold


SYSTEM = """You are the evidence compiler for a video-writing system. You receive passages from one video, each with passage_id, sentence_ids, time range, and exact ASR text.

Extract writing-level claims, not sentence-level paraphrases:
- Merge fragments that make one claim; do not restate every sentence.
- Keep only claims that help a reader understand the video's mechanism/process/argument/evidence.
- Skip greetings, self-introductions, "watch until the end" teasers, small talk, sponsorship, channel logistics, and UI click-by-click details unless they are necessary to a claim.
- Every claim needs an exact quote that is a continuous substring of its passage text. Do not paraphrase the quote, translate it, add punctuation, or join distant fragments.
- Use sentence_ids from that passage. Do not invent IDs or facts.
- Prefer 1-3 claims per passage; merge duplicates within a passage. Aim for a compact set (roughly 20-50 claims for a 10-20 minute video), not coverage.
- kind: fact|opinion|experience|inference|instruction.
- status: supported (quote directly supports it) | bounded (quote supports only part/with a scope).
- confidence: high|medium|low.
- scope: short reader-facing scope, or empty.

Return only one JSON object:
{"claims":[{"passage_id":"...","text":"...","quote":"...","sentence_ids":["..."],"kind":"fact","status":"supported","confidence":"high","scope":""}]}
"""


def _validate(raw_claims: list[dict[str, Any]], passages: dict[str, dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for index, raw in enumerate(raw_claims):
        passage_id = raw.get("passage_id")
        passage = passages.get(passage_id)
        text = (raw.get("text") or "").strip()
        quote = (raw.get("quote") or "").strip()
        sentence_ids = raw.get("sentence_ids") or []
        kind = raw.get("kind")
        status = raw.get("status")
        confidence = raw.get("confidence", "medium")
        scope = (raw.get("scope") or "").strip()
        problems: list[str] = []
        if passage is None:
            problems.append("unknown_passage")
        if not text:
            problems.append("empty_text")
        if not quote:
            problems.append("empty_quote")
        if passage is not None and quote and quote not in passage["text"]:
            problems.append("quote_not_in_passage")
        if passage is not None:
            allowed = set(passage.get("sentence_ids", []))
            if not sentence_ids or not set(sentence_ids) <= allowed:
                problems.append("bad_sentence_ids")
        if kind not in KINDS:
            problems.append("bad_kind")
        if status not in STATUSES:
            problems.append("bad_status")
        if problems:
            rejected.append({"index": index, "problems": problems, "raw": raw})
            continue
        accepted.append(
            {
                "passage_id": passage_id,
                "segment_id": passage["segment_id"],
                "text": text,
                "quote": quote,
                "sentence_ids": list(sentence_ids),
                "kind": kind,
                "status": status,
                "confidence": confidence,
                "scope": scope,
                "t_start_ms": passage["t_start_ms"],
                "t_end_ms": passage["t_end_ms"],
            }
        )
    # Deduplicate near-identical claims within/across passages.
    deduped: list[dict[str, Any]] = []
    duplicates: list[dict[str, Any]] = []
    for claim in accepted:
        duplicate_of = next(
            (c["claim_id"] for c in deduped if _near_duplicate(c["text"], claim["text"])),
            None,
        )
        if duplicate_of:
            duplicates.append({"text": claim["text"], "duplicate_of": duplicate_of})
            continue
        digest = semantic_hash(
            {"passage_id": claim["passage_id"], "text": claim["text"], "quote": claim["quote"]},
            drop_volatile=False,
        )
        claim["claim_id"] = f"c_{digest[:12]}"
        claim["evidence_id"] = f"ev_{digest[:12]}"
        deduped.append(claim)
    return deduped, {
        "accepted": len(accepted),
        "deduped": len(deduped),
        "rejected": rejected,
        "duplicates": duplicates,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="v3 claim extraction/aggregation from passages.")
    parser.add_argument("--passages", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--max-tokens", type=int, default=32768)
    parser.add_argument("--budget-tokens", type=int, default=120000)
    parser.add_argument("--temperature", type=float, default=0.0)
    args = parser.parse_args(argv)

    from lunograph.core.config import get_settings

    settings = get_settings()
    if not settings.provider_configured:
        print("provider 未配置；拒绝伪造 claim extraction", file=sys.stderr)
        return 2
    data = _read_json(args.passages)
    passages_list = data.get("passages", [])
    passages = {p["passage_id"]: p for p in passages_list}
    user = json.dumps({"passages": passages_list}, ensure_ascii=False)
    policy = BudgetPolicy(max_calls=1, max_tokens=args.budget_tokens)
    budget = BudgetState(policy)
    provider = DeepSeekLLM(settings, budget=budget)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    raw_path = args.out_dir / "claim_extract_raw.txt"
    try:
        response = provider.complete(
            stage="v3_claim_extract",
            key=semantic_hash({"passages": passages_list}, drop_volatile=False),
            system=SYSTEM,
            user=user,
            max_tokens=args.max_tokens,
            temperature=args.temperature,
        )
        raw_path.write_text(response.text, encoding="utf-8")
    except ProviderError as exc:
        print(f"provider error: {exc}", file=sys.stderr)
        return 3
    try:
        payload = extract_json_object(response.text)
        raw_claims = payload.get("claims")
        if not isinstance(raw_claims, list):
            raise StructuredOutputError("claims must be a list")
    except StructuredOutputError as exc:
        print(f"invalid model output: {exc}", file=sys.stderr)
        return 4

    claims, stats = _validate(raw_claims, passages)
    claims_path = args.out_dir / "claims.json"
    claims_path.write_text(
        json.dumps({"claims": claims}, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    trace = TraceRecorder(args.out_dir)
    try:
        trace.stage(
            "claim_extract",
            status="complete",
            inputs={"passages": args.passages},
            outputs={"claims": claims_path, "raw": raw_path},
            counts={
                "passages_in": len(passages_list),
                "claims_raw": len(raw_claims),
                "claims_accepted": len(claims),
                "claims_rejected": len(stats["rejected"]),
                "claims_duplicates": len(stats["duplicates"]),
                "claims_per_segment": {
                    segment: sum(1 for c in claims if c["segment_id"] == segment)
                    for segment in sorted({c["segment_id"] for c in claims})
                },
            },
            params={
                "max_tokens": args.max_tokens,
                "temperature": args.temperature,
                "kinds": sorted(KINDS),
                "statuses": sorted(STATUSES),
            },
            decisions={
                "rejected": stats["rejected"],
                "duplicates": stats["duplicates"],
            },
            samples=[
                {
                    "claims": claims[:5],
                    "usage": response.usage.as_dict(),
                    "latency_ms": response.latency_ms,
                }
            ],
        )
    finally:
        trace.close()
    print(
        json.dumps(
            {
                "out_dir": str(args.out_dir),
                "passages_in": len(passages_list),
                "claims_raw": len(raw_claims),
                "claims_accepted": len(claims),
                "claims_rejected": len(stats["rejected"]),
                "claims_duplicates": len(stats["duplicates"]),
                "usage": response.usage.as_dict(),
                "latency_ms": response.latency_ms,
            },
            ensure_ascii=False,
            indent=1,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
