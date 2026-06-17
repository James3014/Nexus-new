"""Tests for StrategyEnvelope schema-only."""
from __future__ import annotations

import json

from nexus.strategy.strategy_envelope import (
    StrategyEnvelope,
    STRATEGY_ENVELOPE_SCHEMA,
    REQUIRED_FIELDS,
)


def test_strategy_envelope_has_all_required_fields():
    """Envelope contains all required fields."""
    env = StrategyEnvelope(
        task_goal="fix time handling",
        bug_hypothesis="incorrect UTC offset",
        repair_strategy="adjust offset calculation",
        target_symbols=["astropy.time.core"],
        allowed_paths=["astropy/time/"],
        forbidden_paths=["astropy/tests/"],
        context_budget_tokens=4000,
        invariants=["no breaking API changes"],
        abort_conditions=["failing tests after patch"],
        created_by="agent-p0.1",
    )
    d = env.to_dict()
    for field in REQUIRED_FIELDS:
        assert field in d


def test_strategy_id_is_hash_based():
    """strategy_id is computed from content hash."""
    env1 = StrategyEnvelope(
        task_goal="fix time handling",
        bug_hypothesis="incorrect UTC offset",
        repair_strategy="adjust offset calculation",
    )
    env2 = StrategyEnvelope(
        task_goal="fix time handling",
        bug_hypothesis="incorrect UTC offset",
        repair_strategy="adjust offset calculation",
    )
    assert env1.strategy_id == env2.strategy_id
    assert len(env1.strategy_id) == 16


def test_strategy_id_changes_with_different_content():
    """Different content produces different strategy_id."""
    env1 = StrategyEnvelope(task_goal="fix A", bug_hypothesis="hypothesis A")
    env2 = StrategyEnvelope(task_goal="fix B", bug_hypothesis="hypothesis B")
    assert env1.strategy_id != env2.strategy_id


def test_strategy_envelope_validate_passes_with_all_fields():
    """validate() returns empty list when all fields present."""
    env = StrategyEnvelope(
        task_goal="fix time",
        bug_hypothesis="hypothesis",
        repair_strategy="strategy",
        context_budget_tokens=4000,
        created_by="test",
    )
    assert env.validate() == []
    assert env.is_valid() is True


def test_strategy_envelope_validate_fails_missing_fields():
    """validate() returns errors when required fields missing."""
    env = StrategyEnvelope()
    errors = env.validate()
    assert len(errors) > 0
    assert any("task_goal" in e for e in errors)
    assert any("context_budget_tokens" in e for e in errors)


def test_strategy_envelope_forbidden_paths_check():
    """check_paths rejects forbidden paths."""
    env = StrategyEnvelope(
        forbidden_paths=["astropy/tests/", "astropy/_dev/"],
        allowed_paths=["astropy/"],
    )
    assert env.check_paths("astropy/time/core.py") is True
    assert env.check_paths("astropy/tests/test_time.py") is False
    assert env.check_paths("astropy/_dev/debug.py") is False


def test_strategy_envelope_allowed_paths_check():
    """check_paths requires allowed paths when set."""
    env = StrategyEnvelope(allowed_paths=["astropy/time/"])
    assert env.check_paths("astropy/time/core.py") is True
    assert env.check_paths("astropy/io/fits.py") is False


def test_strategy_envelope_serialize_deserialize():
    """Roundtrip serialize/deserialize."""
    env = StrategyEnvelope(
        task_goal="fix",
        bug_hypothesis="hypothesis",
        repair_strategy="strategy",
        context_budget_tokens=4000,
    )
    json_str = env.to_json()
    env2 = StrategyEnvelope.from_json(json_str)
    assert env2.task_goal == env.task_goal
    assert env2.strategy_id == env.strategy_id
    assert env2.context_budget_tokens == env.context_budget_tokens


def test_strategy_envelope_not_connected_to_execution():
    """Envelope does not reference CampaignGeneral, SurgicalPacker, or prompt_builder."""
    env = StrategyEnvelope(task_goal="test")
    d = env.to_dict()
    for key in d:
        assert "campaign" not in key.lower()
        assert "surgical" not in key.lower()
        assert "prompt" not in key.lower()


def test_strategy_envelope_schema_version():
    """Schema version is correct."""
    assert STRATEGY_ENVELOPE_SCHEMA == "nexus.strategy.strategy_envelope.v1"
