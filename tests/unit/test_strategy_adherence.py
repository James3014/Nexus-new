"""Tests for StrategyAdherenceChecker."""

import sys
sys.path.insert(0, "/Users/jameschen/Workspace/nexus")

from nexus.strategy import StrategyAdherenceChecker
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
        abort_conditions=[],
        context_budget=4096,
    )
    defaults.update(kwargs)
    return create_strategy_envelope(**defaults)


def test_adherence_pass():
    e = _make_envelope()
    checker = StrategyAdherenceChecker()
    result = checker.check(e, modified_files=["src/a.py"], effective_change=True)
    assert result["adherence_status"] == "pass"
    assert result["trace_only"] is True
    assert result["enforcement_action"] == "none"


def test_adherence_forbidden_path():
    e = _make_envelope(forbidden_paths=["src/secret/"])
    checker = StrategyAdherenceChecker()
    result = checker.check(e, modified_files=["src/secret/key.py"])
    assert result["adherence_status"] == "violation"
    assert any("forbidden_path" in v for v in result["adherence_violations"])


def test_adherence_public_claim():
    e = _make_envelope()
    checker = StrategyAdherenceChecker()
    result = checker.check(e, public_claim_allowed=True)
    assert result["adherence_status"] == "violation"


def test_adherence_emits_warning_not_block():
    e = _make_envelope()
    checker = StrategyAdherenceChecker()
    result = checker.check(e, effective_change=False)
    assert result["enforcement_action"] == "none"


if __name__ == "__main__":
    test_adherence_pass()
    test_adherence_forbidden_path()
    test_adherence_public_claim()
    test_adherence_emits_warning_not_block()
    print("All StrategyAdherenceChecker tests PASS")
