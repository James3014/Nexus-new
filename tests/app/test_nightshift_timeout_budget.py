import pytest
from nexus.research.runtime.runtime_resilience import compute_adaptive_budget

def test_adaptive_budget_no_history():
    assert compute_adaptive_budget([], default_sec=60) == 60

def test_adaptive_budget_with_history():
    # Avg = 100, Target = 150
    assert compute_adaptive_budget([100, 100, 100], default_sec=60) == 150
    # Hard cap check
    assert compute_adaptive_budget([300, 300], default_sec=60, hard_cap=300) == 300
