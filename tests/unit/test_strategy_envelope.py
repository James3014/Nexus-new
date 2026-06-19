"""Tests for strategy_envelope module."""

import pytest
from nexus.strategy.strategy_envelope import (
    create_strategy_envelope,
    StrategyEnvelope,
    StrategyEnvelopeError,
)


VALID_KWARGS = {
    "strategy_family": "source_anchor_retry",
    "repair_strategy": "line_span_replace",
    "search_policy": "REPLACE_only",
    "model_roles": {"patcher": "14B", "locator": "7B"},
    "target_symbols": ["_is_unitless"],
    "forbidden_paths": ["tests/"],
    "invariants": ["no_fuzzy_write"],
    "abort_conditions": ["source_stale"],
    "context_budget": 4000,
}


def test_valid_envelope():
    env = create_strategy_envelope(**VALID_KWARGS)
    assert isinstance(env, StrategyEnvelope)
    assert env.trace_only is True
    assert len(env.strategy_id) == 16


def test_deterministic_strategy_id():
    e1 = create_strategy_envelope(**VALID_KWARGS)
    e2 = create_strategy_envelope(**VALID_KWARGS)
    assert e1.strategy_id == e2.strategy_id


def test_different_payload_different_id():
    e1 = create_strategy_envelope(**VALID_KWARGS)
    e2 = create_strategy_envelope(**{**VALID_KWARGS, "context_budget": 8000})
    assert e1.strategy_id != e2.strategy_id


def test_missing_family():
    with pytest.raises(StrategyEnvelopeError):
        create_strategy_envelope(**{**VALID_KWARGS, "strategy_family": ""})


def test_absolute_forbidden_path():
    with pytest.raises(StrategyEnvelopeError):
        create_strategy_envelope(**{**VALID_KWARGS, "forbidden_paths": ["/absolute"]})


def test_parent_traversal_forbidden_path():
    with pytest.raises(StrategyEnvelopeError):
        create_strategy_envelope(**{**VALID_KWARGS, "forbidden_paths": ["../escape"]})


def test_invalid_model_roles():
    with pytest.raises(StrategyEnvelopeError):
        create_strategy_envelope(**{**VALID_KWARGS, "model_roles": "not_a_dict"})


def test_negative_context_budget():
    with pytest.raises(StrategyEnvelopeError):
        create_strategy_envelope(**{**VALID_KWARGS, "context_budget": -1})


def test_to_dict():
    env = create_strategy_envelope(**VALID_KWARGS)
    d = env.to_dict()
    assert isinstance(d, dict)
    assert d["trace_only"] is True
    assert d["strategy_id"] == env.strategy_id


def test_serialization_roundtrip():
    env = create_strategy_envelope(**VALID_KWARGS)
    d = env.to_dict()
    import json
    serialized = json.dumps(d)
    deserialized = json.loads(serialized)
    assert deserialized["strategy_id"] == env.strategy_id
