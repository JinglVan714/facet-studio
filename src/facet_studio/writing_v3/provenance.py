"""Audit-only provenance from writing claims back to substrate claims/evidence.

The writing layer aggregates passages into writing-level claims.  This module
links each selected writing claim to the snapshot's atomic claims and evidence
by unit-ID overlap (sentence -> unit -> assertion -> snapshot claim/evidence).

The result lives in the full pack under ``provenance``.  It is deliberately
kept out of the writer-facing view: it is audit/trace data, not writing input.
"""

from __future__ import annotations

from typing import Any


def _empty_summary(claims_total: int) -> dict[str, Any]:
    return {
        "claims_total": claims_total,
        "claims_with_source": 0,
        "claims_without_source": claims_total,
        "claims_without_source_ids": [],
        "source_claim_count": 0,
        "source_evidence_count": 0,
        "stance_counts": {},
        "support_status_counts": {},
        "rights_scope_counts": {},
    }


def build_provenance(
    *,
    claims_out: list[dict[str, Any]],
    selected_claim_by_id: dict[str, dict[str, Any]],
    sentence_by_id: dict[str, dict[str, Any]],
    snapshot_doc: dict[str, Any] | None,
) -> dict[str, Any]:
    """Return a compact, deterministic provenance block.

    Preference is unit overlap because it is stable across claim extraction and
    does not depend on video-specific IDs.  A writing claim can link to several
    atomic claims/evidence items; all are kept as IDs, never as copied text.
    """
    if not snapshot_doc:
        return {"summary": _empty_summary(len(claims_out)), "claims": {}}

    assertions = snapshot_doc.get("assertions", [])
    snapshot_claims = snapshot_doc.get("claims", [])
    snapshot_evidence = snapshot_doc.get("evidence", [])
    links = snapshot_doc.get("evidence_claim_links", [])
    if not assertions and not snapshot_claims:
        return {"summary": _empty_summary(len(claims_out)), "claims": {}}

    unit_to_assertions: dict[str, set[str]] = {}
    assertion_by_id: dict[str, dict[str, Any]] = {}
    for assertion in assertions:
        assertion_id = assertion["id"]
        assertion_by_id[assertion_id] = assertion
        for unit_id in assertion.get("unit_ids", []):
            unit_to_assertions.setdefault(unit_id, set()).add(assertion_id)

    claim_by_assertion: dict[str, dict[str, Any]] = {}
    for claim in snapshot_claims:
        claim_by_assertion[claim["id"]] = claim
        source_assertion_id = claim.get("source_assertion_id")
        if source_assertion_id:
            claim_by_assertion.setdefault(source_assertion_id, claim)

    evidence_by_id = {e["id"]: e for e in snapshot_evidence}
    links_by_claim: dict[str, list[dict[str, Any]]] = {}
    for link in links:
        links_by_claim.setdefault(link["claim_id"], []).append(link)

    claim_rows: dict[str, dict[str, Any]] = {}
    rights_by_claim: dict[str, set[str]] = {}
    stance_counts: dict[str, int] = {}
    support_status_counts: dict[str, int] = {}
    rights_scope_counts: dict[str, int] = {}
    source_claim_ids: set[str] = set()
    source_evidence_ids: set[str] = set()
    correction_assertion_ids: set[str] = set()
    claims_without_source: list[str] = []

    for writing_claim in claims_out:
        writing_id = writing_claim["claim_id"]
        source = selected_claim_by_id.get(writing_id, {})
        unit_ids: set[str] = set()
        for sentence_id in source.get("sentence_ids", []):
            sentence = sentence_by_id.get(sentence_id)
            if sentence:
                unit_ids.update(sentence.get("unit_ids", []))

        assertion_ids: set[str] = set()
        for unit_id in unit_ids:
            assertion_ids.update(unit_to_assertions.get(unit_id, set()))

        row_claims: set[str] = set()
        row_evidence: set[str] = set()
        row_stances: set[str] = set()
        row_statuses: set[str] = set()
        row_rights: set[str] = set()
        for assertion_id in sorted(assertion_ids):
            snap_claim = claim_by_assertion.get(assertion_id)
            if snap_claim is None:
                continue
            snap_claim_id = snap_claim["id"]
            row_claims.add(snap_claim_id)
            status = snap_claim.get("support_status")
            if status:
                row_statuses.add(status)
            for link in links_by_claim.get(snap_claim_id, []):
                evidence_id = link.get("evidence_id")
                if not evidence_id:
                    continue
                row_evidence.add(evidence_id)
                stance = link.get("stance")
                if stance:
                    row_stances.add(stance)
                evidence = evidence_by_id.get(evidence_id)
                if evidence and evidence.get("rights_scope"):
                    row_rights.add(evidence["rights_scope"])
            if assertion_by_id.get(assertion_id, {}).get("corrections"):
                correction_assertion_ids.add(assertion_id)

        if not row_claims and not row_evidence:
            claims_without_source.append(writing_id)
            continue

        row: dict[str, Any] = {
            "source_claim_ids": sorted(row_claims),
            "source_evidence_ids": sorted(row_evidence),
        }
        # Keep the common case compact: supported/supports are defaults.
        if row_statuses and row_statuses != {"supported"}:
            row["support_statuses"] = sorted(row_statuses)
        if row_stances and row_stances != {"supports"}:
            row["stances"] = sorted(row_stances)
        claim_rows[writing_id] = row
        rights_by_claim[writing_id] = row_rights
        source_claim_ids.update(row_claims)
        source_evidence_ids.update(row_evidence)
        for status in row_statuses:
            support_status_counts[status] = support_status_counts.get(status, 0) + 1
        for stance in row_stances:
            stance_counts[stance] = stance_counts.get(stance, 0) + 1
        for right in row_rights:
            rights_scope_counts[right] = rights_scope_counts.get(right, 0) + 1

    # Per-claim rights only when rights are not globally uniform; the summary
    # already carries the uniform case.
    if len(rights_scope_counts) > 1:
        for writing_id, rights in rights_by_claim.items():
            if rights:
                claim_rows[writing_id]["rights_scopes"] = sorted(rights)

    summary: dict[str, Any] = {
        "claims_total": len(claims_out),
        "claims_with_source": len(claim_rows),
        "claims_without_source": len(claims_without_source),
        "claims_without_source_ids": claims_without_source,
        "source_claim_count": len(source_claim_ids),
        "source_evidence_count": len(source_evidence_ids),
        "stance_counts": stance_counts,
        "support_status_counts": support_status_counts,
        "rights_scope_counts": rights_scope_counts,
    }
    if correction_assertion_ids:
        summary["asr_correction_count"] = len(correction_assertion_ids)
    return {"summary": summary, "claims": claim_rows}
