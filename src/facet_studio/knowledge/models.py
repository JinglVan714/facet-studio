"""Knowledge-layer models.

KnowledgeSnapshot is an immutable, rebuildable semantic index over an
EvidenceSnapshot.  It never becomes a new fact source: every node must point
back to existing claims/evidence.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

ENTITY_TYPES = (
    "person",
    "product",
    "concept",
    "event",
    "method",
    "version",
    "location",
    "organization",
    "other",
)

KNOWLEDGE_RELATION_TYPES = (
    "causes",
    "precedes",
    "depends_on",
    "part_of",
    "example_of",
    "compares_with",
    "illustrates",
    "qualifies",
    "derived_from",
)


class Entity(BaseModel):
    entity_id: str
    canonical_name: str
    aliases: list[str] = Field(default_factory=list)
    entity_type: str = "concept"
    mention_claim_ids: list[str] = Field(default_factory=list)
    identity_basis: str = "model_cluster"
    merge_status: str = "proposed"


class ClaimCluster(BaseModel):
    cluster_id: str
    canonical_claim: str
    member_claim_ids: list[str]
    entity_ids: list[str] = Field(default_factory=list)
    attribute: str = "unspecified"
    scope: dict[str, Any] | None = None
    supporting_evidence_ids: list[str] = Field(default_factory=list)
    contradicting_evidence_ids: list[str] = Field(default_factory=list)
    qualifying_evidence_ids: list[str] = Field(default_factory=list)
    segment_ids: list[str] = Field(default_factory=list)
    status: str = "supported"


class KnowledgeRelation(BaseModel):
    relation_id: str
    from_id: str
    to_id: str
    from_type: str
    to_type: str
    type: str
    basis: str = "explicit"
    confidence: float | None = None
    status: str = "active"
    source_claim_ids: list[str] = Field(default_factory=list)
    segment_scope: list[str] = Field(default_factory=list)


class KnowledgeConflict(BaseModel):
    conflict_id: str
    cluster_ids: list[str] = Field(default_factory=list)
    claim_ids: list[str] = Field(default_factory=list)
    description: str
    basis: str = "explicit"
    severity: str = "major"
    status: str = "needs_review"


class KnowledgeGap(BaseModel):
    gap_id: str
    description: str
    related_entity_ids: list[str] = Field(default_factory=list)
    related_cluster_ids: list[str] = Field(default_factory=list)
    severity: str = "major"
    status: str = "open"


class KnowledgeSnapshot(BaseModel):
    schema_version: str = "1.0"
    knowledge_snapshot_id: str = ""
    evidence_snapshot_id: str
    temporal_outline_id: str
    entities: list[Entity]
    claim_clusters: list[ClaimCluster]
    relations: list[KnowledgeRelation]
    conflicts: list[KnowledgeConflict]
    gaps: list[KnowledgeGap]
    knowledge_hash: str = ""
    status: str = "complete"
    build_method: str = "knowledge_builder/v1"
    build_warnings: list[str] = Field(default_factory=list)
    model_versions: dict[str, str] = Field(default_factory=dict)
    created_at: str

    def cluster_by_id(self) -> dict[str, ClaimCluster]:
        return {c.cluster_id: c for c in self.claim_clusters}

    def entity_by_id(self) -> dict[str, Entity]:
        return {e.entity_id: e for e in self.entities}

    def claim_ids(self) -> set[str]:
        return {cid for c in self.claim_clusters for cid in c.member_claim_ids}

    def coverage_stats(self) -> dict[str, Any]:
        attributed = [c for c in self.claim_clusters if c.attribute != "unspecified"]
        cross_segment = [
            r for r in self.relations if len(set(r.segment_scope)) > 1
        ]
        return {
            "entity_count": len(self.entities),
            "cluster_count": len(self.claim_clusters),
            "attributed_cluster_count": len(attributed),
            "relation_count": len(self.relations),
            "cross_segment_relation_count": len(cross_segment),
            "conflict_count": len(self.conflicts),
            "gap_count": len(self.gaps),
            "critical_gap_count": sum(1 for g in self.gaps if g.severity == "critical"),
        }
