"""P5-I7: P4 Integration Tests."""
from __future__ import annotations

import os
import pytest
from nexus.services.local_heal.committee_routed_tool import (
    CommitteeRoutedToolRequest,
    evaluate_and_execute,
)
from nexus.services.local_heal.receipt import build_repair_receipt


def _valid_request(**overrides):
    defaults = {
        "task_id": "t1",
        "repo_root": "/tmp",
        "target_file": "foo.py",
        "difficulty": "hard",
        "execution_topology": "cloud_with_local_assist",
        "p3_route_status": "shadow_stage5_escalation_recommended",
        "hard_case_escalation_reason": "retry_failed",
        "proposer_specs": [{"model": "a", "role": "primary"}, {"model": "b", "role": "secondary"}],
        "judge_model": "judge",
    }
    defaults.update(overrides)
    return CommitteeRoutedToolRequest(**defaults)


def test_p5_disabled_first_valid():
    """P5-I7: P5 disabled → first-valid selection (existing behavior)."""
    os.environ.pop("NEXUS_ENABLE_P5_DIVERSITY_SELECTION", None)
    req = _valid_request()
    result = evaluate_and_execute(req)
    # No P5 fields in receipt_fragment
    assert "p5_diversity_selector_used" not in result.receipt_fragment


def _mock_producer(request):
    return []


def test_p5_enabled_selector_invoked():
    """P5-I7: P5 enabled → diversity selector invoked (no candidates → zero_winner)."""
    os.environ["NEXUS_ENABLE_P5_DIVERSITY_SELECTION"] = "1"
    os.environ["NEXUS_ENABLE_P4_COMMITTEE_ROUTED_TOOL"] = "1"
    try:
        req = _valid_request()
        result = evaluate_and_execute(req, candidate_producer=_mock_producer)
        # No candidates → zero_winner path
        assert result.winner_found is False
        assert result.receipt_fragment.get("p4_zero_winner") is True
    finally:
        os.environ.pop("NEXUS_ENABLE_P5_DIVERSITY_SELECTION", None)
        os.environ.pop("NEXUS_ENABLE_P4_COMMITTEE_ROUTED_TOOL", None)


def test_p5_enabled_fail_closed():
    """P5-I7: P5 enabled but no candidates → zero_winner with fail_closed."""
    os.environ["NEXUS_ENABLE_P5_DIVERSITY_SELECTION"] = "1"
    os.environ["NEXUS_ENABLE_P4_COMMITTEE_ROUTED_TOOL"] = "1"
    try:
        req = _valid_request()
        result = evaluate_and_execute(req, candidate_producer=_mock_producer)
        assert result.winner_found is False
        assert result.receipt_fragment.get("p4_fail_closed") is True
    finally:
        os.environ.pop("NEXUS_ENABLE_P5_DIVERSITY_SELECTION", None)
        os.environ.pop("NEXUS_ENABLE_P4_COMMITTEE_ROUTED_TOOL", None)


def test_p5_receipt_fields_present():
    """P5-I7: P4 receipt fields present when committee invoked."""
    os.environ["NEXUS_ENABLE_P5_DIVERSITY_SELECTION"] = "1"
    os.environ["NEXUS_ENABLE_P4_COMMITTEE_ROUTED_TOOL"] = "1"
    try:
        req = _valid_request()
        result = evaluate_and_execute(req, candidate_producer=_mock_producer)
        fragment = result.receipt_fragment
        # P4 fields present
        assert "p4_committee_invoked" in fragment
        assert "p4_winner_found" in fragment
        assert "p4_solved_by_committee" in fragment
    finally:
        os.environ.pop("NEXUS_ENABLE_P5_DIVERSITY_SELECTION", None)
        os.environ.pop("NEXUS_ENABLE_P4_COMMITTEE_ROUTED_TOOL", None)
