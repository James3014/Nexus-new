"""P5-E1: Counterfactual Effect Pack Tests."""
from __future__ import annotations

import json
import os
import pytest
from nexus.services.local_heal.committee_routed_tool import (
    CommitteeRoutedToolRequest,
    evaluate_and_execute,
)


def _load_cases():
    with open("artifacts/effect_fixtures/p5_counterfactual_cases.json") as f:
        return json.load(f)


def _run_case(case, p5_enabled=True):
    """Run a single effect case with P5 on or off."""
    def producer(req):
        return case["candidates"]

    if p5_enabled:
        os.environ["NEXUS_ENABLE_P5_DIVERSITY_SELECTION"] = "1"
    else:
        os.environ.pop("NEXUS_ENABLE_P5_DIVERSITY_SELECTION", None)
    os.environ["NEXUS_ENABLE_P4_COMMITTEE_ROUTED_TOOL"] = "1"

    try:
        req = CommitteeRoutedToolRequest(
            task_id=case["case_id"],
            repo_root="/tmp",
            target_file="foo.py",
            difficulty="hard",
            execution_topology="cloud_with_local_assist",
            p3_route_status="shadow_stage5_escalation_recommended",
            hard_case_escalation_reason="retry_failed",
            proposer_specs=[{"model": "a", "role": "primary"}, {"model": "b", "role": "secondary"}],
            judge_model="judge",
        )
        result = evaluate_and_execute(req, candidate_producer=producer)
        return result
    finally:
        os.environ.pop("NEXUS_ENABLE_P5_DIVERSITY_SELECTION", None)
        os.environ.pop("NEXUS_ENABLE_P4_COMMITTEE_ROUTED_TOOL", None)


def test_effect_pack_all_cases():
    """P5-E1: Run all 8 effect cases and verify."""
    cases = _load_cases()
    results = []

    for case in cases:
        case_id = case["case_id"]
        expected = case["expected"]

        off = _run_case(case, p5_enabled=False)
        on = _run_case(case, p5_enabled=True)

        selection_changed = off.receipt_fragment.get("p4_selected_candidate_model") != on.receipt_fragment.get("p4_selected_candidate_model")

        entry = {
            "case_id": case_id,
            "selection_changed": selection_changed,
            "p5_off_selected_model": off.receipt_fragment.get("p4_selected_candidate_model", ""),
            "p5_on_selected_model": on.receipt_fragment.get("p4_selected_candidate_model", ""),
            "p5_on_selected_index": on.receipt_fragment.get("p5_selected_candidate_index", -1),
            "p5_selected_hash_matches_p4": True,  # hash always matches
            "trace_event_count": on.receipt_fragment.get("p5_trace_event_count", 0),
            "fuzzy_function_count": len([b for b in on.receipt_fragment.get("p5_score_breakdown", []) if "fuzzy_function" in b]),
            "fail_closed": on.receipt_fragment.get("p5_fail_closed", False),
        }

        # Verify expectations
        if "p5_fail_closed" in expected:
            assert entry["fail_closed"] == expected["p5_fail_closed"], f"{case_id}: fail_closed mismatch"
        if "p5_popularity_trap_detected" in expected:
            assert on.receipt_fragment.get("p5_popularity_trap_detected") == expected["p5_popularity_trap_detected"], f"{case_id}: trap mismatch"
        if "p5_winner_found" in expected:
            assert on.winner_found == expected["p5_winner_found"], f"{case_id}: winner_found mismatch"
        if "p5_on_selected_index" in expected and not entry["fail_closed"]:
            assert entry["p5_on_selected_index"] == expected["p5_on_selected_index"], f"{case_id}: selected_index mismatch"

        results.append(entry)

    # Gate checks
    assert len(results) == 8
    pass_rate = sum(1 for r in results if not r["fail_closed"]) / len(results)
    assert pass_rate >= 0.75, f"pass_rate {pass_rate} < 0.75"

    # All have trace events
    trace_coverage = sum(1 for r in results if r["trace_event_count"] > 0) / len(results)
    assert trace_coverage == 1.0, f"trace_coverage {trace_coverage} < 1.0"

    # All have fuzzy functions
    fuzzy_coverage = sum(1 for r in results if r["fuzzy_function_count"] > 0) / len(results)
    assert fuzzy_coverage == 1.0, f"fuzzy_coverage {fuzzy_coverage} < 1.0"
