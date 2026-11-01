"""Provenance joins writing claims back to substrate claims/evidence."""

from __future__ import annotations

from .test_pack_context import SENTENCES, _build, _claim


def _snapshot(*, unit_ids: list[str], status: str = "supported", stance: str = "supports") -> dict:
    return {
        "assertions": [
            {
                "id": "a1",
                "unit_ids": unit_ids,
                "corrections": [{"wrong": "x", "right": "y", "why": "test"}],
            }
        ],
        "claims": [
            {
                "id": "a1",
                "source_assertion_id": "a1",
                "support_status": status,
            }
        ],
        "evidence": [
            {
                "id": "ev_a1",
                "unit_ids": unit_ids,
                "rights_scope": "unknown_public_video",
            }
        ],
        "evidence_claim_links": [
            {"claim_id": "a1", "evidence_id": "ev_a1", "stance": stance}
        ],
    }


def test_provenance_links_writing_claim_to_substrate() -> None:
    pack = _build(
        SENTENCES,
        [_claim("c1", "第二句。", ["s2"])],
        snapshot=_snapshot(
            unit_ids=["u_s2"], status="partially_supported", stance="qualifies"
        ),
    )
    provenance = pack["provenance"]

    assert provenance["summary"]["claims_with_source"] == 1
    assert provenance["summary"]["claims_without_source"] == 0
    assert provenance["summary"]["source_claim_count"] == 1
    assert provenance["summary"]["source_evidence_count"] == 1
    assert provenance["summary"]["stance_counts"] == {"qualifies": 1}
    assert provenance["summary"]["support_status_counts"] == {
        "partially_supported": 1
    }
    assert provenance["summary"]["rights_scope_counts"] == {
        "unknown_public_video": 1
    }
    assert provenance["summary"]["asr_correction_count"] == 1

    row = provenance["claims"]["c1"]
    assert row["source_claim_ids"] == ["a1"]
    assert row["source_evidence_ids"] == ["ev_a1"]
    assert row["support_statuses"] == ["partially_supported"]
    assert row["stances"] == ["qualifies"]
    assert "rights_scopes" not in row


def test_provenance_reports_missing_source() -> None:
    pack = _build(
        SENTENCES,
        [_claim("c1", "第二句。", ["s2"])],
        snapshot=_snapshot(unit_ids=["u_s6"]),
    )
    provenance = pack["provenance"]

    assert provenance["summary"]["claims_with_source"] == 0
    assert provenance["summary"]["claims_without_source"] == 1
    assert provenance["summary"]["claims_without_source_ids"] == ["c1"]
    assert provenance["claims"] == {}


def test_provenance_omits_default_status_and_stance() -> None:
    pack = _build(
        SENTENCES,
        [_claim("c1", "第二句。", ["s2"])],
        snapshot=_snapshot(unit_ids=["u_s2"]),
    )
    row = pack["provenance"]["claims"]["c1"]

    assert "support_statuses" not in row
    assert "stances" not in row
