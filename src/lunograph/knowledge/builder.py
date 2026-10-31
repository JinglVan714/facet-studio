"""Generic KnowledgeSnapshot builder.

Exactly one model call (plus at most one structured-output retry) builds the
semantic index.  Everything the model returns is treated as a *candidate*:
IDs are re-derived, unknown references are dropped with warnings, unclustered
claims become singleton clusters, and invalid output degrades to an explicit
``partial`` snapshot instead of an empty success.
"""

from __future__ import annotations

import json
from typing import Any

from ..core.hashing import semantic_hash, utc_now_iso
from ..core.jsonutil import StructuredOutputError, extract_json_object
from ..core.sealing import seal
from ..providers.llm import LLMClient
from ..evidence.models import EvidenceSnapshot, TemporalOutline
from .models import (
    ENTITY_TYPES,
    KNOWLEDGE_RELATION_TYPES,
    ClaimCluster,
    Entity,
    KnowledgeConflict,
    KnowledgeGap,
    KnowledgeRelation,
    KnowledgeSnapshot,
)

_ENTITY_TYPE_MAP = {
    "person": "person",
    "人物": "person",
    "人": "person",
    "product": "product",
    "产品": "product",
    "商品": "product",
    "concept": "concept",
    "概念": "concept",
    "event": "event",
    "事件": "event",
    "method": "method",
    "方法": "method",
    "version": "version",
    "版本": "version",
    "location": "location",
    "地点": "location",
    "地区": "location",
    "organization": "organization",
    "机构": "organization",
    "组织": "organization",
    "other": "other",
    "其他": "other",
}

_SEVERITIES = {"critical", "major", "minor"}
_BASES = {"explicit", "derived", "inferred"}


class KnowledgeValidationError(RuntimeError):
    pass


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _clean_text(value: Any, default: str = "") -> str:
    text = str(value or "").strip()
    return text or default


def _entity_type(raw: Any) -> str:
    key = str(raw or "concept").strip()
    mapped = _ENTITY_TYPE_MAP.get(key) or _ENTITY_TYPE_MAP.get(key.lower())
    return mapped if mapped in ENTITY_TYPES else "other"


def _claim_json(snapshot: EvidenceSnapshot) -> list[dict[str, Any]]:
    evidence_by_claim: dict[str, list[dict[str, Any]]] = {}
    for link in snapshot.evidence_claim_links:
        evidence = snapshot.evidence_by_id().get(link.evidence_id)
        if evidence is None:
            continue
        evidence_by_claim.setdefault(link.claim_id, []).append(
            {
                "evidence_id": evidence.id,
                "t_start_ms": evidence.locator.t_start_ms,
                "t_end_ms": evidence.locator.t_end_ms,
                "quote": evidence.raw_content,
            }
        )
    rows = []
    for claim in snapshot.claims:
        rows.append(
            {
                "id": claim.id,
                "text": claim.text,
                "kind": claim.kind,
                "support_status": claim.support_status,
                "segment_id": claim.chunk_id,
                "evidence": evidence_by_claim.get(claim.id, []),
            }
        )
    return rows


def _build_user_payload(snapshot: EvidenceSnapshot, outline: TemporalOutline) -> dict[str, Any]:
    return {
        "task": "build_knowledge_snapshot",
        "video_id": snapshot.video_id,
        "claims": _claim_json(snapshot),
        "segments": [
            {"segment_id": s.segment_id, "label": s.label, "first_ms": s.first_ms, "last_ms": s.last_ms}
            for s in outline.segments
        ],
        "candidate_assertion_relations": [
            {"from": r.from_id, "to": r.to_id, "type": r.rel_type, "scope": "within_segment"}
            for r in snapshot.relations
        ],
        "constraints": {
            "every_claim_in_exactly_one_cluster": True,
            "do_not_invent_claim_ids": True,
            "do_not_use_outside_world_knowledge": True,
            "relations_only_from_allowed_types": list(KNOWLEDGE_RELATION_TYPES),
            "gap_is_evidence_gap_not_general_knowledge_gap": True,
        },
    }


def _retry_user_payload(
    snapshot: EvidenceSnapshot,
    outline: TemporalOutline,
    previous_output: str,
    errors: list[str],
) -> dict[str, Any]:
    payload = _build_user_payload(snapshot, outline)
    payload["repair"] = {
        "previous_output": previous_output[:12000],
        "validation_errors": errors,
        "instruction": "只修正结构与引用，不要新增 claim id 或视频外事实；重新输出完整 JSON。",
    }
    return payload


def build_knowledge_snapshot(
    provider: LLMClient,
    snapshot: EvidenceSnapshot,
    outline: TemporalOutline,
    *,
    system_prompt: str,
) -> KnowledgeSnapshot:
    user = json.dumps(_build_user_payload(snapshot, outline), ensure_ascii=False, indent=1)
    errors: list[str] = []
    raw_output = ""
    try:
        response = provider.complete(
            stage="knowledge_build",
            key=snapshot.snapshot_id,
            system=system_prompt,
            user=user,
            temperature=0.0,
        )
        raw_output = response.text
        payload = extract_json_object(raw_output)
        return _normalize(payload, snapshot, outline, provider.model, system_prompt, warnings=[])
    except StructuredOutputError as exc:
        errors.append(str(exc))
        raw_output = exc.raw
    except (KeyError, TypeError, ValueError) as exc:
        errors.append(f"{type(exc).__name__}: {exc}")

    try:
        retry_user = json.dumps(
            _retry_user_payload(snapshot, outline, raw_output, errors),
            ensure_ascii=False,
            indent=1,
        )
        response = provider.complete(
            stage="knowledge_build_retry",
            key=snapshot.snapshot_id,
            system=system_prompt,
            user=retry_user,
            temperature=0.0,
        )
        payload = extract_json_object(response.text)
        return _normalize(
            payload,
            snapshot,
            outline,
            provider.model,
            system_prompt,
            warnings=[f"首次结构化输出无效，已使用重试结果：{errors[0][:200]}"],
        )
    except (StructuredOutputError, KeyError, TypeError, ValueError) as exc:
        return _fallback_snapshot(
            snapshot,
            outline,
            provider.model,
            system_prompt,
            errors + [f"{type(exc).__name__}: {exc}"],
        )


def _fallback_snapshot(
    snapshot: EvidenceSnapshot,
    outline: TemporalOutline,
    model: str,
    system_prompt: str,
    errors: list[str],
) -> KnowledgeSnapshot:
    unit_segment = outline.segment_by_unit()
    clusters = []
    for claim in snapshot.claims:
        segment_ids = _claim_segment_ids(claim.id, claim.chunk_id, snapshot, unit_segment)
        clusters.append(
            ClaimCluster(
                cluster_id=_cluster_id([claim.id]),
                canonical_claim=claim.text,
                member_claim_ids=[claim.id],
                attribute="unspecified",
                segment_ids=segment_ids,
                status=_cluster_status([claim], snapshot),
            )
        )
    knowledge = KnowledgeSnapshot(
        evidence_snapshot_id=snapshot.snapshot_id,
        temporal_outline_id=outline.outline_id,
        entities=[],
        claim_clusters=clusters,
        relations=[],
        conflicts=[],
        gaps=[],
        status="partial",
        build_warnings=[
            "知识构建模型输出不可用，已降级为全部 singleton cluster 的 partial snapshot。",
            *errors,
        ],
        model_versions={
            "knowledge_model": model,
            "knowledge_prompt_hash": semantic_hash({"p": system_prompt}, drop_volatile=False)[:12],
        },
        created_at=utc_now_iso(),
    )
    _fill_cluster_evidence(knowledge.claim_clusters, snapshot)
    return seal(
        knowledge,
        id_field="knowledge_snapshot_id",
        hash_field="knowledge_hash",
        prefix="ks",
    )


def _normalize(
    payload: dict[str, Any],
    snapshot: EvidenceSnapshot,
    outline: TemporalOutline,
    model: str,
    system_prompt: str,
    warnings: list[str],
) -> KnowledgeSnapshot:
    claims = snapshot.claim_by_id()
    evidence_ids = set(snapshot.evidence_by_id())
    unit_segment = outline.segment_by_unit()

    # --- entities -------------------------------------------------------
    entities: list[Entity] = []
    entity_by_canonical: dict[str, Entity] = {}
    ref_to_entity: dict[str, str] = {}
    name_to_entity: dict[str, str] = {}
    raw_entities = _list(payload.get("entities"))
    for index, raw in enumerate(raw_entities, 1):
        if not isinstance(raw, dict):
            warnings.append(f"entity #{index} 不是对象，已丢弃")
            continue
        name = _clean_text(raw.get("canonical_name") or raw.get("name"))
        if not name:
            warnings.append(f"entity #{index} 缺少 canonical_name，已丢弃")
            continue
        mention_ids = []
        for cid in _list(raw.get("mention_claim_ids") or raw.get("mentions")):
            cid = str(cid)
            if cid in claims:
                mention_ids.append(cid)
            else:
                warnings.append(f"entity {name} 引用不存在的 claim {cid}，已丢弃该引用")
        if not mention_ids:
            warnings.append(f"entity {name} 没有有效 mention，按“必须回指 claim”规则丢弃")
            continue
        aliases = [str(a).strip() for a in _list(raw.get("aliases")) if str(a).strip()]
        canonical_key = name
        if canonical_key in entity_by_canonical:
            existing = entity_by_canonical[canonical_key]
            existing.aliases = sorted(set(existing.aliases + aliases + [name]))
            existing.mention_claim_ids = sorted(set(existing.mention_claim_ids + mention_ids))
            ref = str(raw.get("ref") or raw.get("entity_ref") or f"e{index}")
            ref_to_entity[ref] = existing.entity_id
            warnings.append(f"实体 {name} 重复出现，已合并到 {existing.entity_id}")
            continue
        entity = Entity(
            entity_id=_entity_id(name, _entity_type(raw.get("entity_type"))),
            canonical_name=name,
            aliases=sorted(set(aliases)),
            entity_type=_entity_type(raw.get("entity_type")),
            mention_claim_ids=sorted(set(mention_ids)),
        )
        entities.append(entity)
        entity_by_canonical[name] = entity
        name_to_entity[name] = entity.entity_id
        for alias in entity.aliases:
            name_to_entity.setdefault(alias, entity.entity_id)
        ref = str(raw.get("ref") or raw.get("entity_ref") or f"e{index}")
        ref_to_entity[ref] = entity.entity_id

    # --- clusters -------------------------------------------------------
    raw_clusters = _list(payload.get("claim_clusters") or payload.get("clusters"))
    assigned: set[str] = set()
    clusters: list[ClaimCluster] = []
    cluster_by_members: dict[tuple[str, ...], ClaimCluster] = {}
    ref_to_cluster: dict[str, str] = {}
    for index, raw in enumerate(raw_clusters, 1):
        if not isinstance(raw, dict):
            warnings.append(f"cluster #{index} 不是对象，已丢弃")
            continue
        members: list[str] = []
        for cid in _list(raw.get("member_claim_ids") or raw.get("claims")):
            cid = str(cid)
            if cid not in claims:
                warnings.append(f"cluster #{index} 引用不存在的 claim {cid}，已丢弃该引用")
                continue
            if cid in assigned:
                warnings.append(f"claim {cid} 出现在多个 cluster，保留首次归属")
                continue
            if cid not in members:
                members.append(cid)
        if not members:
            warnings.append(f"cluster #{index} 没有有效成员，已丢弃")
            continue
        canonical = _clean_text(
            raw.get("canonical_claim") or raw.get("claim"),
            default=_canonical_from_claims(members, claims),
        )
        attribute = _clean_text(raw.get("attribute"), default="unspecified")
        entity_ids: list[str] = []
        for ref in _list(raw.get("entity_refs") or raw.get("entity_ids")):
            ref = str(ref)
            resolved = ref_to_entity.get(ref) or name_to_entity.get(ref)
            if resolved is None:
                warnings.append(f"cluster {canonical[:24]} 引用未知 entity {ref}，已丢弃该引用")
                continue
            entity_ids.append(resolved)
        if not entity_ids:
            entity_ids = _entities_in_text(canonical, entities)
        member_key = tuple(sorted(members))
        if member_key in cluster_by_members:
            existing = cluster_by_members[member_key]
            existing.entity_ids = sorted(set(existing.entity_ids + entity_ids))
            ref = str(raw.get("ref") or f"c{index}")
            ref_to_cluster[ref] = existing.cluster_id
            warnings.append(f"cluster 成员集合重复，已合并到 {existing.cluster_id}")
            continue
        cluster_id = _cluster_id(members)
        cluster = ClaimCluster(
            cluster_id=cluster_id,
            canonical_claim=canonical,
            member_claim_ids=sorted(members),
            entity_ids=sorted(set(entity_ids)),
            attribute=attribute,
            segment_ids=_cluster_segment_ids(
                members, claims, unit_segment, snapshot
            ),
            status=_cluster_status([claims[c] for c in members], snapshot),
        )
        clusters.append(cluster)
        cluster_by_members[member_key] = cluster
        assigned.update(members)
        ref = str(raw.get("ref") or f"c{index}")
        ref_to_cluster[ref] = cluster_id

    # Leftover claims -> singleton clusters (never silently lose a claim).
    for claim in snapshot.claims:
        if claim.id in assigned:
            continue
        cluster = ClaimCluster(
            cluster_id=_cluster_id([claim.id]),
            canonical_claim=claim.text,
            member_claim_ids=[claim.id],
            entity_ids=_entities_in_text(claim.text, entities),
            attribute="unspecified",
            segment_ids=_claim_segment_ids(claim.id, claim.chunk_id, snapshot, unit_segment),
            status=_cluster_status([claim], snapshot),
        )
        clusters.append(cluster)
        assigned.add(claim.id)
        warnings.append(f"claim {claim.id} 未被模型聚类，已保留为 singleton cluster")

    _fill_cluster_evidence(clusters, snapshot)
    cluster_ids = {c.cluster_id for c in clusters}
    entity_ids_all = {e.entity_id for e in entities}

    # --- relations ------------------------------------------------------
    relations: list[KnowledgeRelation] = []
    seen_relations: set[tuple[str, str, str]] = set()
    for index, raw in enumerate(_list(payload.get("relations") or payload.get("knowledge_relations")), 1):
        if not isinstance(raw, dict):
            warnings.append(f"relation #{index} 不是对象，已丢弃")
            continue
        from_ref = str(raw.get("from") or raw.get("from_ref") or raw.get("from_id") or "")
        to_ref = str(raw.get("to") or raw.get("to_ref") or raw.get("to_id") or "")
        from_id = ref_to_cluster.get(from_ref) or ref_to_entity.get(from_ref) or name_to_entity.get(from_ref)
        to_id = ref_to_cluster.get(to_ref) or ref_to_entity.get(to_ref) or name_to_entity.get(to_ref)
        if from_id is None or to_id is None:
            warnings.append(f"relation #{index} 端点无法解析，已丢弃")
            continue
        if from_id == to_id:
            warnings.append(f"relation #{index} 是自指，已丢弃")
            continue
        rel_type = _clean_text(raw.get("type") or raw.get("relation_type"))
        if rel_type not in KNOWLEDGE_RELATION_TYPES:
            warnings.append(f"relation #{index} 类型 {rel_type!r} 不在允许列表，已丢弃")
            continue
        from_type = _endpoint_type(from_id, cluster_ids, entity_ids_all, raw.get("from_type"))
        to_type = _endpoint_type(to_id, cluster_ids, entity_ids_all, raw.get("to_type"))
        if from_type is None or to_type is None:
            warnings.append(f"relation #{index} 端点类型不合法，已丢弃")
            continue
        key = (from_id, to_id, rel_type)
        if key in seen_relations:
            continue
        seen_relations.add(key)
        basis = _clean_text(raw.get("basis"), default="inferred")
        if basis not in _BASES:
            basis = "inferred"
        confidence = _clamp_confidence(raw.get("confidence"))
        source_claim_ids = [
            str(x) for x in _list(raw.get("source_claim_ids")) if str(x) in claims
        ]
        relations.append(
            KnowledgeRelation(
                relation_id=f"kr_{semantic_hash({'f': from_id, 't': to_id, 'r': rel_type}, drop_volatile=False)[:12]}",
                from_id=from_id,
                to_id=to_id,
                from_type=from_type,
                to_type=to_type,
                type=rel_type,
                basis=basis,
                confidence=confidence,
                source_claim_ids=source_claim_ids,
                segment_scope=_relation_segment_scope(
                    from_id, to_id, clusters, entities, unit_segment, snapshot
                ),
            )
        )

    # --- conflicts ------------------------------------------------------
    conflicts: list[KnowledgeConflict] = []
    for index, raw in enumerate(_list(payload.get("conflicts")), 1):
        if not isinstance(raw, dict):
            continue
        cluster_refs = [
            ref_to_cluster.get(str(x), str(x))
            for x in _list(raw.get("cluster_refs") or raw.get("cluster_ids"))
        ]
        cluster_refs = [x for x in cluster_refs if x in cluster_ids]
        claim_ids = [str(x) for x in _list(raw.get("claim_ids")) if str(x) in claims]
        description = _clean_text(raw.get("description"))
        if not description or len(set(cluster_refs) | set(claim_ids)) < 2:
            warnings.append(f"conflict #{index} 缺少可定位目标或描述，已丢弃")
            continue
        severity = _clean_text(raw.get("severity"), default="major")
        if severity not in _SEVERITIES:
            severity = "major"
        conflicts.append(
            KnowledgeConflict(
                conflict_id=f"cf_{semantic_hash({'c': sorted(cluster_refs), 'a': sorted(claim_ids), 'd': description}, drop_volatile=False)[:12]}",
                cluster_ids=sorted(set(cluster_refs)),
                claim_ids=sorted(set(claim_ids)),
                description=description,
                basis=_clean_text(raw.get("basis"), default="explicit"),
                severity=severity,
            )
        )

    # --- gaps -----------------------------------------------------------
    gaps: list[KnowledgeGap] = []
    for index, raw in enumerate(_list(payload.get("gaps")), 1):
        if not isinstance(raw, dict):
            continue
        description = _clean_text(raw.get("description"))
        if not description:
            warnings.append(f"gap #{index} 缺少描述，已丢弃")
            continue
        related_entities = []
        for ref in _list(raw.get("related_entity_refs") or raw.get("related_entity_ids")):
            resolved = ref_to_entity.get(str(ref)) or name_to_entity.get(str(ref)) or str(ref)
            if resolved in entity_ids_all:
                related_entities.append(resolved)
        related_clusters = []
        for ref in _list(raw.get("related_cluster_refs") or raw.get("related_cluster_ids")):
            resolved = ref_to_cluster.get(str(ref), str(ref))
            if resolved in cluster_ids:
                related_clusters.append(resolved)
        severity = _clean_text(raw.get("severity"), default="major")
        if severity not in _SEVERITIES:
            severity = "major"
        gaps.append(
            KnowledgeGap(
                gap_id=f"gap_{semantic_hash({'d': description, 'e': sorted(related_entities), 'c': sorted(related_clusters)}, drop_volatile=False)[:12]}",
                description=description,
                related_entity_ids=sorted(set(related_entities)),
                related_cluster_ids=sorted(set(related_clusters)),
                severity=severity,
            )
        )

    status = "complete" if not warnings else "partial"
    knowledge = KnowledgeSnapshot(
        evidence_snapshot_id=snapshot.snapshot_id,
        temporal_outline_id=outline.outline_id,
        entities=sorted(entities, key=lambda e: e.entity_id),
        claim_clusters=sorted(clusters, key=lambda c: c.cluster_id),
        relations=sorted(relations, key=lambda r: r.relation_id),
        conflicts=sorted(conflicts, key=lambda c: c.conflict_id),
        gaps=sorted(gaps, key=lambda g: g.gap_id),
        status=status,
        build_warnings=warnings,
        model_versions={
            "knowledge_model": model,
            "knowledge_prompt_hash": semantic_hash({"p": system_prompt}, drop_volatile=False)[:12],
        },
        created_at=utc_now_iso(),
    )
    knowledge = seal(
        knowledge,
        id_field="knowledge_snapshot_id",
        hash_field="knowledge_hash",
        prefix="ks",
    )
    return knowledge


def _canonical_from_claims(member_ids: list[str], claims: dict[str, Any]) -> str:
    text = "；".join(claims[cid].text for cid in member_ids if cid in claims)
    return text[:400] or "（未命名知识簇）"


def _entity_id(name: str, entity_type: str) -> str:
    return f"en_{semantic_hash({'n': name, 't': entity_type}, drop_volatile=False)[:12]}"


def _cluster_id(member_ids: list[str]) -> str:
    return f"cl_{semantic_hash({'m': sorted(member_ids)}, drop_volatile=False)[:12]}"


def _clamp_confidence(value: Any) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return max(0.0, min(1.0, number))


def _endpoint_type(
    endpoint_id: str,
    cluster_ids: set[str],
    entity_ids: set[str],
    declared: Any,
) -> str | None:
    if endpoint_id in cluster_ids:
        return "claim_cluster"
    if endpoint_id in entity_ids:
        return "entity"
    declared = str(declared or "")
    return declared if declared in {"entity", "claim_cluster"} else None


def _entities_in_text(text: str, entities: list[Entity]) -> list[str]:
    """Conservative deterministic mention matching (longest alias first)."""
    candidates: list[tuple[str, str]] = []
    for entity in entities:
        for name in [entity.canonical_name, *entity.aliases]:
            if name and name in text:
                candidates.append((name, entity.entity_id))
    candidates.sort(key=lambda item: (-len(item[0]), item[0]))
    taken: list[tuple[int, int]] = []
    found: list[str] = []
    for name, entity_id in candidates:
        for start in _find_all(text, name):
            end = start + len(name)
            if any(start < t_end and end > t_start for t_start, t_end in taken):
                continue
            taken.append((start, end))
            if entity_id not in found:
                found.append(entity_id)
    return sorted(found)


def _find_all(text: str, needle: str) -> list[int]:
    positions: list[int] = []
    start = 0
    while True:
        idx = text.find(needle, start)
        if idx == -1:
            return positions
        positions.append(idx)
        start = idx + 1


def _claim_segment_ids(
    claim_id: str,
    chunk_id: str | None,
    snapshot: EvidenceSnapshot,
    unit_segment: dict[str, str],
) -> list[str]:
    if chunk_id:
        return [chunk_id]
    claim = snapshot.claim_by_id().get(claim_id)
    if claim is None:
        return []
    unit_ids: list[str] = []
    for link in snapshot.evidence_claim_links:
        if link.claim_id != claim_id:
            continue
        evidence = snapshot.evidence_by_id().get(link.evidence_id)
        if evidence is not None:
            unit_ids.extend(evidence.locator.unit_ids)
    segments = sorted({unit_segment[u] for u in unit_ids if u in unit_segment})
    return segments


def _cluster_segment_ids(
    member_ids: list[str],
    claims: dict[str, Any],
    unit_segment: dict[str, str],
    snapshot: EvidenceSnapshot,
) -> list[str]:
    segments: set[str] = set()
    for cid in member_ids:
        claim = claims.get(cid)
        if claim is None:
            continue
        segments.update(
            _claim_segment_ids(cid, claim.chunk_id, snapshot, unit_segment)
        )
    return sorted(segments)


def _cluster_status(member_claims: list[Any], snapshot: EvidenceSnapshot) -> str:
    statuses = [c.support_status for c in member_claims]
    if "contradicted" in statuses:
        return "conflicted"
    if any(s != "supported" for s in statuses):
        return "partially_supported"
    return "supported"


def _fill_cluster_evidence(clusters: list[ClaimCluster], snapshot: EvidenceSnapshot) -> None:
    evidence_by_id = snapshot.evidence_by_id()
    links_by_claim: dict[str, list[Any]] = {}
    for link in snapshot.evidence_claim_links:
        links_by_claim.setdefault(link.claim_id, []).append(link)
    for cluster in clusters:
        supporting: set[str] = set()
        contradicting: set[str] = set()
        qualifying: set[str] = set()
        for cid in cluster.member_claim_ids:
            for link in links_by_claim.get(cid, []):
                if link.evidence_id not in evidence_by_id:
                    continue
                if link.stance == "supports":
                    supporting.add(link.evidence_id)
                elif link.stance == "contradicts":
                    contradicting.add(link.evidence_id)
                elif link.stance == "qualifies":
                    qualifying.add(link.evidence_id)
        cluster.supporting_evidence_ids = sorted(supporting)
        cluster.contradicting_evidence_ids = sorted(contradicting)
        cluster.qualifying_evidence_ids = sorted(qualifying)
        if cluster.contradicting_evidence_ids:
            cluster.status = "conflicted"


def _relation_segment_scope(
    from_id: str,
    to_id: str,
    clusters: list[ClaimCluster],
    entities: list[Entity],
    unit_segment: dict[str, str],
    snapshot: EvidenceSnapshot,
) -> list[str]:
    by_cluster = {c.cluster_id: c for c in clusters}
    by_entity = {e.entity_id: e for e in entities}
    segments: set[str] = set()
    for endpoint in (from_id, to_id):
        if endpoint in by_cluster:
            segments.update(by_cluster[endpoint].segment_ids)
        elif endpoint in by_entity:
            for cid in by_entity[endpoint].mention_claim_ids:
                claim = snapshot.claim_by_id().get(cid)
                if claim and claim.chunk_id:
                    segments.add(claim.chunk_id)
    return sorted(segments)


def validate_knowledge_snapshot(
    knowledge: KnowledgeSnapshot, snapshot: EvidenceSnapshot
) -> list[str]:
    errors: list[str] = []
    claim_ids = set(snapshot.claim_by_id())
    evidence_ids = set(snapshot.evidence_by_id())
    entity_ids = {e.entity_id for e in knowledge.entities}
    cluster_ids = {c.cluster_id for c in knowledge.claim_clusters}

    for entity in knowledge.entities:
        for cid in entity.mention_claim_ids:
            if cid not in claim_ids:
                errors.append(f"{entity.entity_id} mention 不存在的 claim {cid}")
    covered: set[str] = set()
    for cluster in knowledge.claim_clusters:
        for cid in cluster.member_claim_ids:
            if cid not in claim_ids:
                errors.append(f"{cluster.cluster_id} 含不存在的 claim {cid}")
            if cid in covered:
                errors.append(f"claim {cid} 属于多个 cluster")
            covered.add(cid)
        for eid in (
            cluster.supporting_evidence_ids
            + cluster.contradicting_evidence_ids
            + cluster.qualifying_evidence_ids
        ):
            if eid not in evidence_ids:
                errors.append(f"{cluster.cluster_id} 含不存在的 evidence {eid}")
        for enid in cluster.entity_ids:
            if enid not in entity_ids:
                errors.append(f"{cluster.cluster_id} 含不存在的 entity {enid}")
    missing = claim_ids - covered
    if missing:
        errors.append(f"{len(missing)} 个 claim 未进入任何 cluster: {sorted(missing)[:5]}")
    for relation in knowledge.relations:
        if relation.from_id not in cluster_ids | entity_ids:
            errors.append(f"{relation.relation_id} from 端点不存在")
        if relation.to_id not in cluster_ids | entity_ids:
            errors.append(f"{relation.relation_id} to 端点不存在")
    for conflict in knowledge.conflicts:
        for cid in conflict.cluster_ids:
            if cid not in cluster_ids:
                errors.append(f"{conflict.conflict_id} 引用不存在的 cluster {cid}")
        for cid in conflict.claim_ids:
            if cid not in claim_ids:
                errors.append(f"{conflict.conflict_id} 引用不存在的 claim {cid}")
    for gap in knowledge.gaps:
        for cid in gap.related_cluster_ids:
            if cid not in cluster_ids:
                errors.append(f"{gap.gap_id} 引用不存在的 cluster {cid}")
        for eid in gap.related_entity_ids:
            if eid not in entity_ids:
                errors.append(f"{gap.gap_id} 引用不存在的 entity {eid}")
    return errors
