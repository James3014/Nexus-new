import pytest
from nexus.learning.cycle_analyzer import analyze_cycle

def test_analyze_cycle_empty():
    res = analyze_cycle([])
    assert res["cycle_count"] == 0
    assert res["root_cause"] == ""

def test_analyze_cycle_phantom_proof():
    history = [
        "phantom:missing_physical_proof",
        "rejected:REJECTED",
        "phantom:fake_test_passed"
    ]
    res = analyze_cycle(history)
    assert res["cycle_count"] == 3
    assert res["root_cause"] == "phantom_proof"

def test_analyze_cycle_patch_apply_fail():
    history = [
        "rejected:REJECTED",
        "patch_apply_fail:hunk_failed",
    ]
    res = analyze_cycle(history)
    assert res["cycle_count"] == 2
    assert res["root_cause"] == "patch_apply_fail"

def test_analyze_cycle_insufficient_diag():
    history = [
        "rejected:REJECTED",
        "rejected:REJECTED",
        "rejected:REJECTED"
    ]
    res = analyze_cycle(history)
    assert res["cycle_count"] == 3
    assert res["root_cause"] == "insufficient_diag"

def test_analyze_cycle_scope_drift():
    history = [
        "rejected:REJECTED"
    ]
    res = analyze_cycle(history)
    assert res["cycle_count"] == 1
    assert res["root_cause"] == "scope_drift"
