"""Tests for AbortConditionEvaluator."""

import sys
sys.path.insert(0, "/Users/jameschen/Workspace/nexus")

from nexus.strategy import AbortConditionEvaluator
from nexus.strategy.strategy_envelope import create_strategy_envelope


def _make_envelope(**kwargs):
    defaults = dict(
        strategy_family="test",
        repair_strategy="fix bug",
        search_policy="verbatim",
        model_roles={"primary": "local"},
        target_symbols=[],
        forbidden_paths=[],
        invariants=[],
        abort_conditions=["target_file_missing", "canonical_search_unlocked"],
        context_budget=4096,
    )
    defaults.update(kwargs)
    return create_strategy_envelope(**defaults)


def test_no_abort_normal():
    e = _make_envelope()
    evaluator = AbortConditionEvaluator()
    result = evaluator.evaluate(e)
    assert result["would_abort"] is False
    assert result["enforcement_action"] == "none"
    assert result["trace_only"] is True


def test_abort_target_file_missing():
    e = _make_envelope()
    evaluator = AbortConditionEvaluator()
    result = evaluator.evaluate(e, target_file_exists=False)
    assert result["would_abort"] is True
    assert "target_file_missing" in result["triggered_abort_conditions"]
    assert result["enforcement_action"] == "none"  # S0: never blocks


def test_abort_canonical_search_unlocked():
    e = _make_envelope()
    evaluator = AbortConditionEvaluator()
    result = evaluator.evaluate(e, canonical_search_locked=False)
    assert result["would_abort"] is True
    assert "canonical_search_unlocked" in result["triggered_abort_conditions"]


if __name__ == "__main__":
    test_no_abort_normal()
    test_abort_target_file_missing()
    test_abort_canonical_search_unlocked()
    print("All AbortConditionEvaluator tests PASS")
