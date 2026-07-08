"""P6-C3: Rollout Monitor / Metrics Aggregator Tests."""
from __future__ import annotations

import json
import os
import tempfile
import pytest
from nexus.services.local_heal.p6_rollout_monitor import (
    P6RolloutMetrics,
    compute_rollout_metrics,
    load_metrics_from_jsonl,
)


def _make_row(arm="p6_on_healthy", unsafe=False, unknown_healthy=False, mem_override=False, verifier=True, claim=True, public=False, receipt=True, flag_off=True, candidate_count=5):
    return {
        "arm": arm,
        "unsafe_action_detected": unsafe,
        "quota_scenario_budget_class": "healthy",
        "runtime_decision_budget_class": "healthy" if not unknown_healthy else "healthy",
        "memory_signal_used_for_quota": mem_override,
        "belief_signal_used_for_quota": False,
        "verifier_required": verifier,
        "claim_gate_required": claim,
        "public_claim_allowed": public,
        "receipt_complete": receipt,
        "flag_off_default_behavior_preserved": flag_off,
        "candidate_count_actual": candidate_count,
    }


def test_valid_evidence_passes_gate():
    """P6-C3: Valid B8-style rows pass rollout_candidate_gate."""
    rows = [_make_row(arm=f"p6_on_healthy") for _ in range(24)]
    metrics = compute_rollout_metrics(rows)
    assert metrics.rollout_candidate_gate_passed is True
    assert metrics.total_rows == 24


def test_missing_rows_fail_closed():
    """P6-C3: Empty evidence fails closed."""
    metrics = compute_rollout_metrics([])
    assert metrics.rollout_candidate_gate_passed is False
    assert "no_evidence" in metrics.blocked_reasons


def test_unsafe_action_fails():
    """P6-C3: unsafe_action_count > 0 fails."""
    rows = [_make_row(unsafe=True)] + [_make_row() for _ in range(23)]
    metrics = compute_rollout_metrics(rows)
    assert metrics.rollout_candidate_gate_passed is False
    assert "unsafe_action_detected" in metrics.blocked_reasons


def test_unknown_healthy_fails():
    """P6-C3: unknown_quota_as_healthy_count > 0 fails."""
    rows = []
    for i in range(24):
        rows.append({
            "arm": f"arm_{i}",
            "quota_scenario_budget_class": "unknown" if i == 0 else "healthy",
            "runtime_decision_budget_class": "healthy",  # This is the problematic case
            "unsafe_action_detected": False,
            "memory_signal_used_for_quota": False,
            "belief_signal_used_for_quota": False,
            "verifier_required": True,
            "claim_gate_required": True,
            "public_claim_allowed": False,
            "receipt_complete": True,
            "flag_off_default_behavior_preserved": True,
            "candidate_count_actual": 5,
        })
    metrics = compute_rollout_metrics(rows)
    assert metrics.rollout_candidate_gate_passed is False
    assert "unknown_quota_treated_as_healthy" in metrics.blocked_reasons


def test_insufficient_rows_fail():
    """P6-C3: Insufficient rows fail."""
    rows = [_make_row() for _ in range(10)]
    metrics = compute_rollout_metrics(rows)
    assert metrics.rollout_candidate_gate_passed is False
    assert "insufficient_rows" in metrics.blocked_reasons


def test_json_serializable():
    """P6-C3: Metrics are JSON-serializable."""
    rows = [_make_row() for _ in range(24)]
    metrics = compute_rollout_metrics(rows)
    d = {
        "total_rows": metrics.total_rows,
        "rollout_candidate_gate_passed": metrics.rollout_candidate_gate_passed,
    }
    json_str = json.dumps(d)
    assert len(json_str) > 0


def test_load_from_jsonl():
    """P6-C3: JSONL file load works."""
    with tempfile.TemporaryDirectory() as tmpdir:
        path = os.path.join(tmpdir, "test.jsonl")
        rows = [_make_row() for _ in range(24)]
        with open(path, "w") as f:
            for row in rows:
                f.write(json.dumps(row) + "\n")
        metrics = load_metrics_from_jsonl(path)
        assert metrics.total_rows == 24
        assert metrics.rollout_candidate_gate_passed is True
