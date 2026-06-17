"""T1.8 tests: Symbol-aware canonical span fallback."""
from __future__ import annotations

import ast
from pathlib import Path

from nexus.services.local_heal.patch_applier import PatchApplier
from nexus.services.local_heal.protocol import SolidSearchReplaceProtocol


def _make_applier() -> PatchApplier:
    return PatchApplier(parser=SolidSearchReplaceProtocol(), patcher=None)


def test_extract_target_symbol_from_def():
    """Extract function name from 'def separability_matrix(model):'"""
    applier = _make_applier()
    symbol = applier._extract_target_symbol("def separability_matrix(model):")
    assert symbol == "separability_matrix"


def test_extract_target_symbol_from_class():
    """Extract class name from 'class MyClass:'"""
    applier = _make_applier()
    symbol = applier._extract_target_symbol("class CompoundModel:")
    assert symbol == "CompoundModel"


def test_extract_target_symbol_from_call():
    """Extract function name from 'separability_matrix(model)'"""
    applier = _make_applier()
    symbol = applier._extract_target_symbol("separability_matrix(model)")
    assert symbol == "separability_matrix"


def test_extract_target_symbol_none():
    """Returns None for empty input."""
    applier = _make_applier()
    assert applier._extract_target_symbol("") is None
    assert applier._extract_target_symbol("  ") is None


def test_ast_symbol_fallback_finds_function():
    """AST fallback finds separability_matrix in separable.py source."""
    applier = _make_applier()

    source = '''\
def is_separable(transform):
    """Test."""
    return True

def separability_matrix(transform):
    """
    Compute the separability matrix.

    Parameters
    ----------
    transform : Model
        The model.

    Returns
    -------
    array_like
        A 2D array.
    """
    if not isinstance(transform, CompoundModel):
        return _separable(transform)
    return _cstack(transform)

def _helper():
    pass
'''

    failed_search = "def separability_matrix(model):\n    \"\"\"Compute.\"\"\""
    result = applier._ast_symbol_fallback(source, failed_search, "test.py")

    assert result is not None
    canonical_span, telemetry = result

    assert telemetry["target_symbol"] == "separability_matrix"
    assert telemetry["ast_symbol_found"] is True
    assert telemetry["ast_symbol_span_start"] == 5
    assert telemetry["ast_symbol_span_end"] == 21
    assert telemetry["ast_symbol_span_hash"] != ""

    # Verify canonical span is exact substring
    assert canonical_span in source
    assert "def separability_matrix(transform):" in canonical_span


def test_ast_symbol_fallback_not_found():
    """AST fallback returns (None, telemetry) when symbol not in source."""
    applier = _make_applier()

    source = 'def other_function():\n    pass\n'
    result = applier._ast_symbol_fallback(source, "def missing_func():", "test.py")

    assert result is not None
    _, telemetry = result
    assert telemetry["ast_symbol_found"] is False


def test_ast_symbol_fallback_syntax_error():
    """AST fallback handles syntax error gracefully."""
    applier = _make_applier()

    source = 'def broken(\n    invalid syntax'
    result = applier._ast_symbol_fallback(source, "def broken():", "test.py")

    assert result is not None
    _, telemetry = result
    assert telemetry["ast_symbol_found"] is False


def test_lookup_canonical_with_ast_fallback():
    """Full lookup returns valid result (AST fallback available as backup)."""
    applier = _make_applier()

    source = '''\
import numpy as np

def separability_matrix(transform):
    """Compute."""
    return _separable(transform)
'''

    failed_search = "def separability_matrix(model):\n    return compute(model)"

    canonical, telemetry = applier._lookup_canonical_search_span(source, failed_search, "test.py")

    # Should find canonical span (via any strategy)
    assert canonical is not None
    assert "def separability_matrix(transform):" in canonical
    assert "lookup_result" in telemetry


def test_telemetry_fields_complete():
    """T1.8 telemetry includes all required fields."""
    applier = _make_applier()

    source = 'def my_func(x):\n    return x\n'
    result = applier._ast_symbol_fallback(source, "def my_func(x):", "test.py")

    assert result is not None
    _, telemetry = result

    required_fields = [
        "target_symbol",
        "target_symbol_source",
        "target_symbol_confidence",
        "ast_symbol_found",
        "ast_symbol_span_start",
        "ast_symbol_span_end",
        "ast_symbol_span_hash",
    ]
    for field in required_fields:
        assert field in telemetry, f"Missing telemetry field: {field}"
