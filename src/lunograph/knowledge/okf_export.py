"""Minimal read-only OKF projection.

OKF is an export/navigation format derived from a fixed KnowledgeSnapshot.
It is never read back as a fact source and never becomes the internal query
layer.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from ..core.time import format_range
from .models import KnowledgeSnapshot


def _slug(text: str, fallback: str) -> str:
    slug = re.sub(r"[^\w一-鿿-]+", "-", text).strip("-")
    return slug[:40] or fallback


def export_okf(knowledge: KnowledgeSnapshot, output_dir: Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    entities_dir = output_dir / "entities"
    clusters_dir = output_dir / "claims"
    entities_dir.mkdir(exist_ok=True)
    clusters_dir.mkdir(exist_ok=True)

    entity_files: dict[str, str] = {}
    for entity in knowledge.entities:
        filename = f"{_slug(entity.canonical_name, entity.entity_id)}.md"
        entity_files[entity.entity_id] = filename
        lines = [
            "---",
            f"id: {entity.entity_id}",
            f"type: {entity.entity_type}",
            f"aliases: {entity.aliases}",
            "status: generated",
            "---",
            "",
            f"# {entity.canonical_name}",
            "",
            f"提及该实体的 claims: {len(entity.mention_claim_ids)}",
            "",
        ]
        for cid in entity.mention_claim_ids:
            lines.append(f"- `{cid}`")
        (entities_dir / filename).write_text("\n".join(lines) + "\n", encoding="utf-8")

    for cluster in knowledge.claim_clusters:
        lines = [
            "---",
            f"id: {cluster.cluster_id}",
            f"attribute: {cluster.attribute}",
            f"status: {cluster.status}",
            f"entities: {cluster.entity_ids}",
            "source: knowledge_snapshot",
            "---",
            "",
            f"# {cluster.canonical_claim}",
            "",
        ]
        for cid in cluster.member_claim_ids:
            lines.append(f"- claim `{cid}`")
        lines.append("")
        (clusters_dir / f"{cluster.cluster_id}.md").write_text(
            "\n".join(lines) + "\n", encoding="utf-8"
        )

    index = ["# Knowledge Index", "", "## Entities", ""]
    for entity in knowledge.entities:
        index.append(
            f"- [{entity.canonical_name}](entities/{entity_files[entity.entity_id]})"
        )
    index.extend(["", "## Claim clusters", ""])
    for cluster in knowledge.claim_clusters:
        index.append(
            f"- [{cluster.canonical_claim[:80]}](claims/{cluster.cluster_id}.md)"
        )
    index.extend(["", "## Gaps", ""])
    for gap in knowledge.gaps:
        index.append(f"- {gap.description} ({gap.severity})")
    (output_dir / "index.md").write_text("\n".join(index) + "\n", encoding="utf-8")

    return {
        "format": "okf_projection/v0.1",
        "output_dir": str(output_dir),
        "entity_pages": len(knowledge.entities),
        "cluster_pages": len(knowledge.claim_clusters),
        "note": "只读派生投影；不是事实源，也不参与内部主查询。",
    }
