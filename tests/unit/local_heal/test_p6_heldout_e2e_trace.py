"""P6-G3: E2E Trace Tests."""
from __future__ import annotations

import json
import pytest
from nexus.services.local_heal.p6_heldout_e2e_trace import generate_e2e_trace


def test_trace_generates_for_all_rows():
    receipts = [{"case_id": "H01", "quota_scenario": "healthy", "degradation_action": "keep_full_committee",
                 "cloud_allowed": True, "local_allowed": True, "committee_allowed": True, "p5_allowed": True,
                 "candidate_count_min": 3, "candidate_count_max": 10, "receipt_complete": True, "blocked_reasons": []}]
    rows, summary = generate_e2e_trace(receipts)
    assert len(rows) == 1
    assert rows[0]["evidence_kind"] == "p6_heldout_dry_run_synthetic"
    assert rows[0]["real_execution_evidence"] is False
    assert rows[0]["public_claim_allowed"] is False


def test_real_evidence_triggers_rollback():
    rows, summary = generate_e2e_trace([{"case_id": "H01", "quota_scenario": "healthy", "degradation_action": "keep_full_committee",
                                          "cloud_allowed": True, "local_allowed": True, "committee_allowed": True, "p5_allowed": True,
                                          "candidate_count_min": 3, "candidate_count_max": 10, "receipt_complete": True, "blocked_reasons": [],
                                          "real_execution_evidence": True}])
    assert summary["canary_severity"] == "rollback"
    assert "real_execution_evidence" in summary["rollback_triggers"]


def test_public_claim_triggers_rollback():
    rows, summary = generate_e2e_trace([{"case_id": "H01", "quota_scenario": "healthy", "degradation_action": "keep_full_committee",
                                          "cloud_allowed": True, "local_allowed": True, "committee_allowed": True, "p5_allowed": True,
                                          "candidate_count_min": 3, "candidate_count_max": 10, "receipt_complete": True, "blocked_reasons": [],
                                          "public_claim_allowed": True}])
    assert summary["canary_severity"] == "rollback"
    assert "public_claim_allowed" in summary["rollback_triggers"]
