import pytest
from scripts.ops import nexus_acceptance_check

def test_phantom_fp_fail_when_over_threshold():
    # 50% blocked rate, threshold 3%
    rows = [
        {"phantom_blocked": True},
        {"phantom_blocked": False}
    ]
    res = nexus_acceptance_check._evaluate_phantom_false_positive(rows, window=10, fp_max=3.0)
    assert res.passed is False
    assert res.detail["status"] == "FAIL"
    assert res.detail["recent_false_positive_rate"] == 50.0

def test_phantom_fp_pass_when_below_threshold():
    # 0% blocked rate, threshold 3%
    rows = [
        {"phantom_blocked": False},
        {"phantom_blocked": False}
    ]
    res = nexus_acceptance_check._evaluate_phantom_false_positive(rows, window=10, fp_max=3.0)
    assert res.passed is True
    assert res.detail["status"] == "PASS"

def test_phantom_fp_unverified_on_empty_data():
    rows = []
    res = nexus_acceptance_check._evaluate_phantom_false_positive(rows, window=10, fp_max=3.0)
    assert res.passed is False
    assert res.detail["status"] == "UNVERIFIED"
