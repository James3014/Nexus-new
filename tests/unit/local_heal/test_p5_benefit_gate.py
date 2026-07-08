"""P5-V1: Benefit Gate — Counterfactual Off/On Proof Tests."""
from __future__ import annotations

import os
import pytest
from nexus.services.local_heal.committee_routed_tool import (
    CommitteeRoutedToolRequest,
    evaluate_and_execute,
)


def _run_counterfactual(raw_candidates, request_overrides=None):
    """Run P5 off and P5 on with same candidates, return both results."""
    def producer(req):
        return raw_candidates

    base = {
        "task_id": "p5-v1",
        "repo_root": "/tmp",
        "target_file": "foo.py",
        "difficulty": "hard",
        "execution_topology": "cloud_with_local_assist",
        "p3_route_status": "shadow_stage5_escalation_recommended",
        "hard_case_escalation_reason": "retry_failed",
        "proposer_specs": [{"model": "a", "role": "primary"}, {"model": "b", "role": "secondary"}],
        "judge_model": "judge",
    }
    if request_overrides:
        base.update(request_overrides)

    # P5 OFF
    os.environ.pop("NEXUS_ENABLE_P5_DIVERSITY_SELECTION", None)
    os.environ["NEXUS_ENABLE_P4_COMMITTEE_ROUTED_TOOL"] = "1"
    req_off = CommitteeRoutedToolRequest(**base)
    result_off = evaluate_and_execute(req_off, candidate_producer=producer)

    # P5 ON
    os.environ["NEXUS_ENABLE_P5_DIVERSITY_SELECTION"] = "1"
    os.environ["NEXUS_ENABLE_P4_COMMITTEE_ROUTED_TOOL"] = "1"
    req_on = CommitteeRoutedToolRequest(**base)
    result_on = evaluate_and_execute(req_on, candidate_producer=producer)

    os.environ.pop("NEXUS_ENABLE_P5_DIVERSITY_SELECTION", None)
    os.environ.pop("NEXUS_ENABLE_P4_COMMITTEE_ROUTED_TOOL", None)

    return result_off, result_on


def _make_raw(patch, model="qwen", safety_flags=(), target_file="foo.py"):
    raw_hash = __import__("hashlib").sha256(patch.encode("utf-8")).hexdigest()
    return {
        "candidate_patch": patch,
        "format": "UNIFIED_DIFF",
        "model": model,
        "candidate_id": raw_hash[:16],
    }


def test_counterfactual_first_bad_second_good():
    """V1 Scenario A: first bad, second good → P5 selects second."""
    raw = [
        _make_raw("x", model="bad-model"),
        _make_raw("--- a/foo.py\n+++ b/foo.py\n@@ -1 +1 @@\n-a\n+b", model="good-model"),
    ]
    off, on = _run_counterfactual(raw)

    # P5 off: first-valid (index 0)
    assert off.winner_found is True
    # P5 on: should select higher-quality candidate (index 1)
    assert on.winner_found is True
    assert on.receipt_fragment.get("p5_selected_candidate_index") == 1
    assert on.receipt_fragment.get("p5_diversity_selector_used") is True


def test_counterfactual_duplicate_unsafe_majority():
    """V1 Scenario B: duplicate unsafe majority + safer unique → P5 selects unique."""
    raw = [
        _make_raw("x = 1", model="qwen"),
        _make_raw("x = 1", model="qwen"),  # duplicate of 0
        _make_raw("--- a/bar.py\n+++ b/bar.py\n@@ -1 +1 @@\n-a\n+b", model="deepseek"),
    ]
    off, on = _run_counterfactual(raw)

    # P5 off: first-valid (index 0)
    assert off.winner_found is True
    # P5 on: should detect trap and select unique safer candidate
    assert on.winner_found is True
    assert on.receipt_fragment.get("p5_popularity_trap_detected") is True
    assert on.receipt_fragment.get("p5_selected_candidate_index") == 2


def test_counterfactual_all_unsafe_fail_closed():
    """V1 Scenario C: all unsafe → P5 on fail_closed, P5 off first-valid."""
    raw = [
        _make_raw("x", model="qwen"),
        _make_raw("y", model="deepseek"),
    ]
    off, on = _run_counterfactual(raw)

    # P5 off: first-valid (index 0, no safety check)
    assert off.winner_found is True
    # P5 on: all candidates have safety_penalty=0.3 → final_score negative → fail_closed
    assert on.winner_found is False
    assert on.receipt_fragment.get("p5_fail_closed") is True
    assert "p5_selection_failed:all_candidates_unsafe" in on.failure_reasons
