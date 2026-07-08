"""PAW-F1: Fuzzy Function Spec Registry Tests."""
from __future__ import annotations

import json
import pytest
from nexus.services.local_heal.fuzzy_spec_registry import (
    FuzzyFunctionSpec,
    get_fuzzy_function_spec,
    list_fuzzy_function_specs,
    FUZZY_FUNCTION_SPECS,
)


def test_all_functions_registered():
    """PAW-F1: All 5 functions registered."""
    specs = list_fuzzy_function_specs()
    assert len(specs) == 5
    names = [s.function_name for s in specs]
    assert "candidate_quality_v1" in names
    assert "duplicate_similarity_v1" in names
    assert "popularity_trap_risk_v1" in names
    assert "memory_usefulness_v1" in names
    assert "quota_degradation_risk_v1" in names


def test_spec_has_nl_spec():
    """PAW-F1: Each spec has natural_language_spec."""
    specs = list_fuzzy_function_specs()
    for spec in specs:
        assert spec.natural_language_spec != ""


def test_spec_has_schemas():
    """PAW-F1: Each spec has input_schema and output_schema."""
    specs = list_fuzzy_function_specs()
    for spec in specs:
        assert len(spec.input_schema) > 0
        assert len(spec.output_schema) > 0


def test_spec_has_deterministic_backend():
    """PAW-F1: Each spec has deterministic_backend."""
    specs = list_fuzzy_function_specs()
    for spec in specs:
        assert spec.deterministic_backend != ""


def test_paw_backend_not_available():
    """PAW-F1: PAW backend is not available by default."""
    specs = list_fuzzy_function_specs()
    for spec in specs:
        assert spec.paw_backend_available is False
        assert spec.paw_runtime_allowed is False


def test_spec_has_calibration_fixture():
    """PAW-F1: Each spec has calibration_fixture."""
    specs = list_fuzzy_function_specs()
    for spec in specs:
        assert spec.calibration_fixture != ""


def test_spec_has_safety_scope():
    """PAW-F1: Each spec has safety_scope."""
    specs = list_fuzzy_function_specs()
    for spec in specs:
        assert spec.safety_scope != ""


def test_get_spec_by_name():
    """PAW-F1: get_fuzzy_function_spec returns correct spec."""
    spec = get_fuzzy_function_spec("candidate_quality_v1")
    assert spec is not None
    assert spec.function_name == "candidate_quality_v1"


def test_get_spec_unknown_returns_none():
    """PAW-F1: Unknown function returns None."""
    spec = get_fuzzy_function_spec("nonexistent")
    assert spec is None


def test_spec_json_serializable():
    """PAW-F1: Specs are JSON-serializable."""
    specs = list_fuzzy_function_specs()
    for spec in specs:
        d = {
            "function_name": spec.function_name,
            "version": spec.version,
            "natural_language_spec": spec.natural_language_spec,
            "input_schema": spec.input_schema,
            "output_schema": spec.output_schema,
            "deterministic_backend": spec.deterministic_backend,
        }
        json_str = json.dumps(d)
        assert len(json_str) > 0
