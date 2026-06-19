"""Tests for patch_intent module."""

import pytest
from nexus.services.local_heal.patch_intent import (
    parse_patch_intent,
    validate_patch_intent,
    PatchIntent,
    PatchIntentErrorKind,
)


VALID_PAYLOAD = {
    "file_path": "sympy/core/basic.py",
    "span_start": 10,
    "span_end": 15,
    "original_hash": "abc123",
    "replacement": "def foo(): pass",
    "fallback_strategy": "reject",
}


def test_valid_patch_intent():
    result = parse_patch_intent(VALID_PAYLOAD)
    assert isinstance(result, PatchIntent)
    assert result.file_path == "sympy/core/basic.py"
    assert result.span_start == 10
    assert result.span_end == 15


def test_missing_field():
    payload = {k: v for k, v in VALID_PAYLOAD.items() if k != "file_path"}
    result = parse_patch_intent(payload)
    assert isinstance(result, PatchIntentErrorKind) or hasattr(result, "kind")
    assert result.kind == PatchIntentErrorKind.MISSING_FIELD


def test_absolute_path_rejected():
    payload = {**VALID_PAYLOAD, "file_path": "/absolute/path.py"}
    result = parse_patch_intent(payload)
    assert result.kind == PatchIntentErrorKind.INVALID_PATH


def test_parent_traversal_rejected():
    payload = {**VALID_PAYLOAD, "file_path": "../escape.py"}
    result = parse_patch_intent(payload)
    assert result.kind == PatchIntentErrorKind.INVALID_PATH


def test_invalid_span():
    payload = {**VALID_PAYLOAD, "span_start": 20, "span_end": 10}
    result = parse_patch_intent(payload)
    assert result.kind == PatchIntentErrorKind.INVALID_SPAN


def test_empty_replacement():
    payload = {**VALID_PAYLOAD, "replacement": ""}
    result = parse_patch_intent(payload)
    assert result.kind == PatchIntentErrorKind.EMPTY_REPLACEMENT


def test_invalid_fallback_strategy():
    payload = {**VALID_PAYLOAD, "fallback_strategy": "magic_fix"}
    result = parse_patch_intent(payload)
    assert result.kind == PatchIntentErrorKind.INVALID_FALLBACK_STRATEGY


def test_invalid_field_type():
    payload = {**VALID_PAYLOAD, "span_start": "not_int"}
    result = parse_patch_intent(payload)
    assert result.kind == PatchIntentErrorKind.INVALID_FIELD_TYPE


def test_validate_patch_intent_errors():
    intent = PatchIntent(
        file_path="test.py",
        symbol_name=None,
        span_start=1,
        span_end=5,
        original_hash="abc",
        replacement="x = 1",
        expected_ast_valid=True,
        fallback_strategy="reject",
    )
    errors = validate_patch_intent(intent)
    assert len(errors) == 0
