"""EA-R10: Fuzzy Reward Calibration Pack Tests."""
from __future__ import annotations

import json
import pytest
from nexus.services.local_heal.fuzzy_functions import evaluate as fuzzy_evaluate, list_functions


def _load_calibration():
    with open("artifacts/effect_fixtures/fuzzy_reward_calibration_v0.json") as f:
        return json.load(f)


def test_calibration_case_count():
    """EA-R10: calibration_case_count >= 25."""
    cases = _load_calibration()
    assert len(cases) >= 25


def test_functions_covered():
    """EA-R10: All 5 functions covered in calibration."""
    cases = _load_calibration()
    functions = set(c["function"] for c in cases)
    assert "candidate_quality_v1" in functions
    assert "duplicate_similarity_v1" in functions
    assert "popularity_trap_risk_v1" in functions
    assert "memory_usefulness_v1" in functions
    assert "quota_degradation_risk_v1" in functions


def test_deterministic_replay_stable():
    """EA-R10: Deterministic replay is stable."""
    cases = _load_calibration()
    for case in cases:
        result = fuzzy_evaluate(case["function"], **case["input"])
        assert result.deterministic is True
        assert result.backend == "deterministic"
        # Score within range (with tolerance for floating point)
        assert case["expected_score_min"] - 0.01 <= result.score <= case["expected_score_max"] + 0.01, \
            f"{case['function']}: score={result.score} not in [{case['expected_score_min']}, {case['expected_score_max']}]"
        assert result.label == case["expected_label"]


def test_unknown_function_fail_closed():
    """EA-R10: Unknown function raises KeyError."""
    with pytest.raises(KeyError):
        fuzzy_evaluate("nonexistent_function")


def test_function_version_present():
    """EA-R10: All functions have version."""
    functions = list_functions()
    for f in functions:
        assert f.version != ""


def test_quota_degradation_risk_v1_exists():
    """EA-R10: quota_degradation_risk_v1 is registered."""
    functions = list_functions()
    names = [f.name for f in functions]
    assert "quota_degradation_risk_v1" in names


def test_no_model_call():
    """EA-R10: No model call in fuzzy function implementations."""
    import inspect
    from nexus.services.local_heal import fuzzy_functions
    # Check implementation functions only (not dataclass fields)
    for name in dir(fuzzy_functions):
        if name.startswith("_") and name.endswith("_impl"):
            func = getattr(fuzzy_functions, name)
            source = inspect.getsource(func)
            assert "ollama" not in source.lower(), f"{name} contains ollama"
            assert "generate(" not in source, f"{name} contains generate()"
