from __future__ import annotations

from nexus.services.local_assist_final_gate import REQUIRED_FINAL_EVIDENCE, evaluate_final_gate


def _evidence() -> dict[str, bool]:
    return {key: True for key in REQUIRED_FINAL_EVIDENCE}


def test_final_gate_blocks_without_real_cloud_evidence() -> None:
    evidence = _evidence()
    evidence["real_cloud_local_runtime"] = False
    result = evaluate_final_gate(evidence, blockers={"real_cloud_local_runtime": "no_authorized_provider"})
    assert result["status"] == "BLOCKED"
    assert result["terminal_claim"] != "NEXUS_UNIVERSAL_LOCAL_ASSIST_PRODUCTIZED"
    assert "real_cloud_local_runtime" in result["blocking_requirements"]
    assert result["claim_boundary"]["production_ready"] is False
    assert result["claim_boundary"]["public_claim_allowed"] is False


def test_final_gate_productized_status_requires_all_evidence_but_not_public_claim() -> None:
    result = evaluate_final_gate(_evidence())
    assert result["status"] == "PASSED"
    assert result["terminal_claim"] == "NEXUS_UNIVERSAL_LOCAL_ASSIST_PRODUCTIZED"
    assert result["claim_boundary"]["production_ready"] is False
    assert result["claim_boundary"]["public_claim_allowed"] is False


def test_missing_invariant_blocks_even_when_feature_rows_are_green() -> None:
    evidence = _evidence()
    evidence["receipt_lineage_complete"] = False
    evidence["no_candidate_isolation_bypass"] = False
    result = evaluate_final_gate(evidence)
    assert result["status"] == "BLOCKED"
    assert set(result["blocking_requirements"]) >= {"receipt_lineage_complete", "no_candidate_isolation_bypass"}
