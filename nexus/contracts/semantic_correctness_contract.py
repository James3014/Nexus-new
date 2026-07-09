from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SemanticCorrectnessAssertion:
    post_state_must_contain: tuple[str, ...] = ()
    post_state_must_not_contain: tuple[str, ...] = ()
    function_signature_invariant: str = ""
    removed_symbols: tuple[str, ...] = ()
    added_symbols: tuple[str, ...] = ()


@dataclass(frozen=True)
class SemanticCorrectnessCheck:
    assertion_coverage: float = 0.0
    replacement_references_buggy_symbol: bool = False
    expected_post_state_hash: str = ""
    passed: bool = False
    failure_reasons: tuple[str, ...] = ()


def _field_satisfied(field_value: object) -> bool:
    if isinstance(field_value, tuple):
        return len(field_value) > 0
    if isinstance(field_value, str):
        return bool(field_value)
    return False


def compute_assertion_coverage(
    assertion: SemanticCorrectnessAssertion, applied_diff: str
) -> float:
    fields = [
        ("post_state_must_contain", assertion.post_state_must_contain),
        ("post_state_must_not_contain", assertion.post_state_must_not_contain),
        ("function_signature_invariant", assertion.function_signature_invariant),
        ("removed_symbols", assertion.removed_symbols),
        ("added_symbols", assertion.added_symbols),
    ]

    non_empty = [(name, val) for name, val in fields if _field_satisfied(val)]

    if not non_empty:
        return 1.0

    satisfied = 0
    for name, val in non_empty:
        if isinstance(val, tuple) and name == "post_state_must_contain":
            if all(item in applied_diff for item in val):
                satisfied += 1
        elif isinstance(val, tuple) and name == "post_state_must_not_contain":
            if not any(item in applied_diff for item in val):
                satisfied += 1
        elif isinstance(val, tuple) and name in ("removed_symbols", "added_symbols"):
            if all(item in applied_diff for item in val):
                satisfied += 1
        elif isinstance(val, str) and val in applied_diff:
            satisfied += 1

    return satisfied / len(non_empty)
