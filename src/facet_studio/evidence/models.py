"""Evidence-domain models.

These models are deliberately independent of any framework, database or
provider.  Raw substrate fields that we do not interpret are kept so the
adapter stays lossless (``extra="allow"``).
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

GROUNDING_ORIGINS = ("video_native", "external_document", "web_search", "user_input")
EVIDENCE_STANCES = ("supports", "contradicts", "qualifies", "contextualizes")
CLAIM_KINDS = ("factual", "causal", "comparative", "instructional", "evaluative")
SUPPORT_STATUSES = (
    "supported",
    "partially_supported",
    "contradicted",
    "unknown",
    "unsupported",
    "no_source",
    "needs_review",
)


class Anchor(BaseModel):
    model_config = ConfigDict(extra="allow")

    unit_id: str
    sid: str
    start_ms: int
    end_ms: int
    precision: str = "unit"


class Unit(BaseModel):
    model_config = ConfigDict(extra="allow")

    unit_id: str
    sid: str
    char_span: tuple[int, int]
    byte_span: tuple[int, int]
    t: tuple[int, int]
    channel: str
    raw: str
    len: int
    filler_only: bool = False
    forced_split: bool = False
    alignment_failed: bool = False
    produced_by: dict[str, Any] = Field(default_factory=dict)

    @property
    def start_ms(self) -> int:
        return self.t[0]

    @property
    def end_ms(self) -> int:
        return self.t[1]


class OutlineUnit(Unit):
    segment_id: str


class Assertion(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str
    chunk_id: str
    text: str
    unit_ids: list[str]
    anchors: list[Anchor]
    quote: str
    quote_source: str
    kind: str
    status: str
    boundary: Any | None = None
    frame_refs: list[str] = Field(default_factory=list)
    corrections: list[Any] = Field(default_factory=list)
    produced_by: dict[str, Any] = Field(default_factory=dict)
    frame_offsets_ms: dict[str, int] = Field(default_factory=dict)
    quote_hit: str = "exact"


class AssertionRelation(BaseModel):
    """A local relation from the source substrate.

    It is preserved as a hint only; it is not a ``KnowledgeRelation``.
    """

    model_config = ConfigDict(extra="allow")

    id: str
    chunk_id: str
    from_id: str
    to_id: str
    rel_type: str
    link_kind: str
    produced_by: dict[str, Any] = Field(default_factory=dict)


class ExtractionConflict(BaseModel):
    """ASR vs screen-text disagreement (extraction conflict, not knowledge)."""

    model_config = ConfigDict(extra="allow")

    sid: str
    frame_id: str | None = None
    frame_t_ms: int | None = None
    asr: str | None = None
    screen: str | None = None
    window: str | None = None
    ambiguous: bool | None = None
    sentence_text: str | None = None
    screen_text: str | None = None
    unit_ids: list[str] = Field(default_factory=list)
    in_quote: bool | None = None
    frame_advisory: bool | None = None


class FrameInfo(BaseModel):
    frame_id: str
    t_ms: int
    file: str
    strategy: str
    slot_end_ms: int | None = None
    vlm_text: str | None = None
    vlm_model: str | None = None


class FramesIndex(BaseModel):
    video_id: str
    duration_s: float
    media_path: str | None = None
    frames: list[FrameInfo] = Field(default_factory=list)
    vlm_models: list[str] = Field(default_factory=list)
    vlm_coverage: float = 0.0


class SourceFile(BaseModel):
    path: str
    sha256: str
    bytes: int


class SourceManifest(BaseModel):
    video_id: str
    root: str
    files: list[SourceFile]
    media_path: str | None = None
    media_available: bool = False
    notes: list[str] = Field(default_factory=list)


class Claim(BaseModel):
    id: str
    text: str
    kind: str
    claim_form: str
    modality: str
    scope: dict[str, Any] | None = None
    certainty: float | None = None
    support_status: str
    review_status: str = "unreviewed"
    assertion_holder: str | None = None
    source_assertion_id: str
    chunk_id: str | None = None


class EvidenceLocator(BaseModel):
    video_id: str
    t_start_ms: int
    t_end_ms: int
    frame_ids: list[str] = Field(default_factory=list)
    unit_ids: list[str] = Field(default_factory=list)


class EvidenceSpan(BaseModel):
    id: str
    source_id: str
    unit_ids: list[str]
    grounding_origin: str = "video_native"
    capture_method: str = "asr"
    modality: str = "speech"
    locator: EvidenceLocator
    raw_content: str
    normalized_content: str
    kind: str
    assertion_mode: str = "explicit"
    extraction_quality: dict[str, Any] = Field(default_factory=dict)
    context_refs: dict[str, Any] = Field(default_factory=dict)
    rights_scope: str = "unknown"
    provenance: dict[str, Any] = Field(default_factory=dict)
    frame_refs: list[str] = Field(default_factory=list)


class EvidenceClaimLink(BaseModel):
    id: str
    claim_id: str
    evidence_id: str
    stance: str
    basis: str
    scope: dict[str, Any] | None = None
    weight: str = "primary"
    provenance: dict[str, Any] = Field(default_factory=dict)


class EvidenceSnapshot(BaseModel):
    schema_version: str = "1.0"
    snapshot_id: str = ""
    video_id: str
    project_id: str = "default"
    source_manifest: SourceManifest
    derived_asset_hashes: dict[str, str]
    units: list[Unit]
    assertions: list[Assertion]
    relations: list[AssertionRelation]
    corrections: list[ExtractionConflict]
    correction_ledger_meta: dict[str, Any] = Field(default_factory=dict)
    frames_index: FramesIndex
    claims: list[Claim]
    evidence: list[EvidenceSpan]
    evidence_claim_links: list[EvidenceClaimLink]
    snapshot_hash: str = ""
    status: str = "complete"
    build_warnings: list[str] = Field(default_factory=list)
    build_method: str = "lmind_adapter/v1"
    model_versions: dict[str, str] = Field(default_factory=dict)
    created_at: str

    def claim_by_id(self) -> dict[str, Claim]:
        return {c.id: c for c in self.claims}

    def evidence_by_id(self) -> dict[str, EvidenceSpan]:
        return {e.id: e for e in self.evidence}

    def links_by_claim(self) -> dict[str, list[EvidenceClaimLink]]:
        out: dict[str, list[EvidenceClaimLink]] = {}
        for link in self.evidence_claim_links:
            out.setdefault(link.claim_id, []).append(link)
        return out


class Segment(BaseModel):
    segment_id: str
    label: str
    start_unit_id: str
    end_unit_id: str
    unit_ids: list[str]
    first_ms: int
    last_ms: int


class CoverageReport(BaseModel):
    unit_count: int
    segment_count: int
    units_in_segments: int
    units_unassigned: list[str]
    assertion_count: int
    units_with_assertion: int
    unit_coverage: float
    segment_coverage: float
    duration_ms: int
    first_ms: int
    last_ms: int
    warnings: list[str] = Field(default_factory=list)


class TemporalOutline(BaseModel):
    schema_version: str = "1.0"
    outline_id: str = ""
    evidence_snapshot_id: str
    units: list[OutlineUnit]
    segments: list[Segment]
    coverage_report: CoverageReport
    outline_hash: str = ""
    build_method: str = "temporal_outline/v1"
    status: str = "complete"
    created_at: str

    def segment_by_unit(self) -> dict[str, str]:
        return {u.unit_id: u.segment_id for u in self.units}

    def segment_by_id(self) -> dict[str, Segment]:
        return {s.segment_id: s for s in self.segments}
