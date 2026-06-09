import pytest
from nexus.engine.contracts.execution import ExecutionPhase
from nexus.engine.execution.budget_policy import ExecutionBudgetPolicy, DeferredVerificationQueue

def test_budget_policy_marks_heavy_ast_as_deferred_under_core20_profile():
    policy = ExecutionBudgetPolicy("core20")
    # VERIFY_HEAVY budget is 0.0 in core20, so it should be deferred
    assert policy.should_defer(ExecutionPhase.VERIFY_HEAVY) is True
    
    # Other phases like VERIFY_LIGHT should not be deferred (budget -1.0 means no hard defer)
    assert policy.should_defer(ExecutionPhase.VERIFY_LIGHT) is False

def test_fail_closed_checks_remain_synchronous():
    policy = ExecutionBudgetPolicy("core20")
    # Fail-closed checks are part of VERIFY_LIGHT or APPLY_EXECUTE
    assert policy.should_defer(ExecutionPhase.APPLY_EXECUTE) is False

def test_deferred_verification_cannot_mutate_primary_verdict():
    queue = DeferredVerificationQueue()
    queue.enqueue("ast_check_1", "HeavyASTVerifier", "hash123")
    
    pending = queue.get_pending()
    assert len(pending) == 1
    assert pending[0].check_id == "ast_check_1"
    
    # Queue doesn't provide any method to overwrite primary verdict
    assert not hasattr(queue, "overwrite_verdict")
