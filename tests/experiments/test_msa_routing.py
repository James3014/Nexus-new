import pytest
import os
import json
from pydantic import ValidationError

from nexus.experiments.msa_routing.msa_router_contract import MSARouter, MemoryCandidate, RoutingResult
from nexus.experiments.msa_routing.msa_quarantine import MSAQuarantine
from nexus.experiments.msa_routing.msa_lifecycle import MSALifecycle

def test_invalid_type_raises_validation_error():
    with pytest.raises(ValidationError):
        MemoryCandidate(
            id="test-fail",
            content="bad",
            type="invalid_type",  # type: ignore
            score=0.5,
            version_id="v1",
            source_hash="hash"
        )

def test_invalid_score_raises_validation_error():
    with pytest.raises(ValidationError):
        MemoryCandidate(
            id="test-fail",
            content="bad",
            type="code",
            score=1.5,  # out of bounds
            version_id="v1",
            source_hash="hash"
        )

def test_quarantine_gate_failures():
    quarantine = MSAQuarantine()
    item_id = "test-fail-item"
    quarantine.add_to_quarantine(item_id, {"data": "test"})
    
    # hallucination=PARTIAL -> promote=False
    assert quarantine.promote(item_id, "PASS", "PARTIAL") is False
    
    # hallucination=REJECTED -> promote=False
    assert quarantine.promote(item_id, "PASS", "REJECTED") is False
    
    # acceptance=FAIL -> promote=False
    assert quarantine.promote(item_id, "FAIL", "VERIFIED") is False

def test_kill_switch_triggered_fails():
    lifecycle = MSALifecycle()
    baseline = {"precision": 0.8, "unknown_correct_rate": 0.96, "regression_rate": 0.05, "cost_per_success": 1.0}
    
    # Simulate a failing benchmark
    bad_results = {"precision": 0.7, "unknown_correct_rate": 0.98, "regression_rate": 0.04, "cost_per_success": 0.85}
    
    eval_res = lifecycle.evaluate_kill_switch(bad_results, baseline)
    assert eval_res["triggered"] is True
    assert "Precision degraded (0.7 < 0.8)" in eval_res["reasons"]

def test_router_fail_closed():
    router = MSARouter(confidence_threshold=0.8)
    candidates = [
        MemoryCandidate(id="test3", content="c3", type="code", score=0.5, version_id="v1", source_hash="h3"),
    ]
    result = router.route("query-456", candidates)
    assert result.status == "UNKNOWN"
    assert result.reject_reason is not None

def test_hash_drift():
    lifecycle = MSALifecycle(decay_rate=0.5)
    
    entry = {"id": "nonexistent.md", "source_hash": "old_hash", "confidence_decay": 1.0}
    # For a nonexistent file, the current hash will be ""
    # Our logic in msa_lifecycle only decays if current_hash and stored_hash both exist and differ.
    # Let's mock the get_file_hash to return a new hash.
    
    import nexus.experiments.msa_routing.msa_lifecycle as lifecycle_module
    original_get_file_hash = lifecycle_module.get_file_hash
    
    def mock_get_file_hash(filepath: str) -> str:
        return "new_hash"
        
    lifecycle_module.get_file_hash = mock_get_file_hash
    
    try:
        decayed_entry = lifecycle.check_drift_and_decay(".", entry)
        assert decayed_entry["confidence_decay"] == 0.5
    finally:
        lifecycle_module.get_file_hash = original_get_file_hash
