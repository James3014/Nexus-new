from __future__ import annotations

import pytest

from nexus.contracts.semantic_correctness_contract import (
    SemanticCorrectnessAssertion,
    SemanticCorrectnessCheck,
    compute_assertion_coverage,
)


def test_semantic_correctness_assertion_frozen() -> None:
    assertion = SemanticCorrectnessAssertion()
    with pytest.raises(AttributeError):
        assertion.post_state_must_contain = ("x",)


def test_semantic_correctness_check_frozen() -> None:
    check = SemanticCorrectnessCheck()
    with pytest.raises(AttributeError):
        check.passed = True


def test_compute_assertion_coverage_all_satisfied() -> None:
    assertion = SemanticCorrectnessAssertion(
        post_state_must_contain=("fix_a",),
        removed_symbols=("buggy_func",),
    )
    diff = "fix_a buggy_func removed"
    assert compute_assertion_coverage(assertion, diff) == 1.0


def test_compute_assertion_coverage_no_assertions() -> None:
    assertion = SemanticCorrectnessAssertion()
    assert compute_assertion_coverage(assertion, "any diff") == 1.0


def test_compute_assertion_coverage_partial() -> None:
    assertion = SemanticCorrectnessAssertion(
        post_state_must_contain=("fix_a",),
        removed_symbols=("gone_symbol",),
        added_symbols=("new_helper",),
    )
    diff = "+fix_a +gone_symbol"
    result = compute_assertion_coverage(assertion, diff)
    assert result == pytest.approx(2 / 3)
