import pytest
from nexus.engine.contracts.execution import ExecutionPhase, PhaseTiming, DeferredCheckSpec
from nexus.engine.execution.receipt_augmenter import ExecutionReceiptAugmenter

def test_receipt_contains_timeout_phase_and_budget_profile():
    augmenter = ExecutionReceiptAugmenter()
    base = {"task_id": "t1"}
    
    timings = {
        ExecutionPhase.MODEL_CALL: PhaseTiming(ExecutionPhase.MODEL_CALL, wall_time_sec=10.0, status="COMPLETED"),
        ExecutionPhase.PATCH_PARSE: PhaseTiming(ExecutionPhase.PATCH_PARSE, wall_time_sec=0.5, status="TIMEOUT")
    }
    
    deferred = [
        DeferredCheckSpec("c1", "AST", "h1", 0.0)
    ]
    
    aug = augmenter.augment(base, timings, deferred, "TRUNCATED_OUTPUT")
    
    assert aug["timeout_phase"] == "PATCH_PARSE"
    assert aug["patch_health"] == "TRUNCATED_OUTPUT"
    assert aug["execution_timings"]["MODEL_CALL"] == 10.0
    assert len(aug["deferred_checks"]) == 1
    assert aug["deferred_checks"][0]["type"] == "AST"
