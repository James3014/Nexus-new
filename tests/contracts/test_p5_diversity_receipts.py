"""P5-I8: Receipt Contract and Explainability Tests."""
from __future__ import annotations

import json
import pytest
from nexus.services.local_heal.receipt import build_repair_receipt


def test_receipt_p5_fields_defaults():
    """P5-I8: Receipt includes P5 fields with defaults when absent."""
    class FakeCtx:
        instance_id = "p5-i8-test"

    receipt = build_repair_receipt(FakeCtx())
    assert receipt["p5_diversity_selector_used"] is False
    assert receipt["p5_selection_strategy"] == ""
    assert receipt["p5_candidate_count"] == 0
    assert receipt["p5_duplicate_group_count"] == 0
    assert receipt["p5_popularity_trap_detected"] is False
    assert receipt["p5_popularity_trap_reason"] == ""
    assert receipt["p5_selected_candidate_index"] == -1
    assert receipt["p5_selected_candidate_hash"] == ""
    assert receipt["p5_score_breakdown"] == []
    assert receipt["p5_rejected_by_diversity"] == []
    assert receipt["p5_fail_closed"] is False


def test_receipt_p5_fields_with_values():
    """P5-I8: Receipt includes P5 fields with values when ctx has P5 attributes."""
    class FakeCtx:
        instance_id = "p5-i8-test"
        p5_diversity_selector_used = True
        p5_selection_strategy = "diversity_v1"
        p5_candidate_count = 5
        p5_duplicate_group_count = 2
        p5_popularity_trap_detected = True
        p5_popularity_trap_reason = "model_homogeneity"
        p5_selected_candidate_index = 2
        p5_selected_candidate_hash = "abc123"
        p5_score_breakdown = [{"index": 0, "score": 0.8}]
        p5_rejected_by_diversity = []
        p5_fail_closed = False

    receipt = build_repair_receipt(FakeCtx())
    assert receipt["p5_diversity_selector_used"] is True
    assert receipt["p5_selection_strategy"] == "diversity_v1"
    assert receipt["p5_candidate_count"] == 5
    assert receipt["p5_duplicate_group_count"] == 2
    assert receipt["p5_popularity_trap_detected"] is True
    assert receipt["p5_popularity_trap_reason"] == "model_homogeneity"
    assert receipt["p5_selected_candidate_index"] == 2
    assert receipt["p5_selected_candidate_hash"] == "abc123"


def test_p5_score_breakdown_serializable():
    """P5-I8: p5_score_breakdown is JSON-serializable."""
    class FakeCtx:
        instance_id = "p5-i8-test"
        p5_score_breakdown = [
            {"index": 0, "score": 0.8, "reasons": ["syntax_score=1.0"]},
            {"index": 1, "score": 0.6, "reasons": ["syntax_score=0.5"]},
        ]

    receipt = build_repair_receipt(FakeCtx())
    json_str = json.dumps(receipt["p5_score_breakdown"])
    assert len(json_str) > 0


def test_p5_popularity_trap_detected_true():
    """P5-I8: p5_popularity_trap_detected=true path recorded."""
    class FakeCtx:
        instance_id = "p5-i8-test"
        p5_popularity_trap_detected = True
        p5_popularity_trap_reason = "dominant_group_has_low_syntax_score;model_homogeneity"

    receipt = build_repair_receipt(FakeCtx())
    assert receipt["p5_popularity_trap_detected"] is True
    assert "low_syntax_score" in receipt["p5_popularity_trap_reason"]


def test_p5_fail_closed_true():
    """P5-I8: p5_fail_closed=true path recorded."""
    class FakeCtx:
        instance_id = "p5-i8-test"
        p5_fail_closed = True

    receipt = build_repair_receipt(FakeCtx())
    assert receipt["p5_fail_closed"] is True


def test_public_claim_allowed_not_controlled_by_p5():
    """P5-I8: public_claim_allowed remains controlled by existing P2/P4 gates."""
    class FakeCtx:
        instance_id = "p5-i8-test"
        p5_diversity_selector_used = True
        p5_fail_closed = False

    receipt = build_repair_receipt(FakeCtx())
    assert receipt["public_claim_allowed"] is False
    assert receipt["production_ready"] is False
