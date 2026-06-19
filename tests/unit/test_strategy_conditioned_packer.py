"""Tests for strategy_conditioned_packer module."""

import pytest
import json
from nexus.services.local_heal.strategy_conditioned_packer import (
    dry_run_strategy_pack,
    StrategyConditionedPackResult,
    StrategyConditionedPackerError,
)
from nexus.strategy.strategy_envelope import create_strategy_envelope


VALID_ENVELOPE = {
    "strategy_id": "abc123",
    "strategy_family": "source_anchor_retry",
    "repair_strategy": "line_span_replace",
    "search_policy": "REPLACE_only",
    "model_roles": {"patcher": "14B", "locator": "7B"},
    "target_symbols": ["_is_unitless"],
    "forbidden_paths": ["tests/"],
    "invariants": ["no_fuzzy_write"],
    "abort_conditions": ["source_stale"],
    "context_budget": 4000,
    "trace_only": True,
}


def test_valid_dry_run():
    result = dry_run_strategy_pack(VALID_ENVELOPE, "task_001")
    assert isinstance(result, StrategyConditionedPackResult)
    assert result.packer_mode == "dry_run"
    assert result.routing_changed is False
    assert result.execution_changed is False
    assert result.patch_apply_allowed is False
    assert len(result.blocker_flags) == 0


def test_strategy_id_preserved():
    result = dry_run_strategy_pack(VALID_ENVELOPE, "task_001")
    assert result.strategy_id == "abc123"


def test_missing_strategy():
    result = dry_run_strategy_pack({}, "task_001")
    assert isinstance(result, StrategyConditionedPackerError)


def test_forbidden_path_violation():
    env = {**VALID_ENVELOPE, "forbidden_paths": ["/absolute"]}
    result = dry_run_strategy_pack(env, "task_001")
    assert "FORBIDDEN_PATH_VIOLATION" in result.blocker_flags


def test_parent_traversal_violation():
    env = {**VALID_ENVELOPE, "forbidden_paths": ["../escape"]}
    result = dry_run_strategy_pack(env, "task_001")
    assert "FORBIDDEN_PATH_VIOLATION" in result.blocker_flags


def test_context_budget_exceeded():
    env = {**VALID_ENVELOPE, "context_budget": 10}
    result = dry_run_strategy_pack(env, "task_001")
    assert "CONTEXT_BUDGET_EXCEEDED" in result.blocker_flags


def test_target_symbols_preserved():
    result = dry_run_strategy_pack(VALID_ENVELOPE, "task_001")
    assert result.target_symbols == ["_is_unitless"]


def test_invariants_preserved():
    result = dry_run_strategy_pack(VALID_ENVELOPE, "task_001")
    assert result.invariants_checked == ["no_fuzzy_write"]


def test_abort_conditions_preserved():
    result = dry_run_strategy_pack(VALID_ENVELOPE, "task_001")
    assert result.abort_conditions_checked == ["source_stale"]


def test_model_roles_preserved():
    result = dry_run_strategy_pack(VALID_ENVELOPE, "task_001")
    assert result.blocker_flags == []


def test_no_llm_call():
    result = dry_run_strategy_pack(VALID_ENVELOPE, "task_001")
    assert result.packer_mode == "dry_run"
    assert result.patch_apply_allowed is False


def test_no_routing_change():
    result = dry_run_strategy_pack(VALID_ENVELOPE, "task_001")
    assert result.routing_changed is False


def test_strategy_id_in_result():
    result = dry_run_strategy_pack(VALID_ENVELOPE, "task_001")
    assert result.strategy_id == "abc123"


def test_serializable():
    result = dry_run_strategy_pack(VALID_ENVELOPE, "task_001")
    d = {
        "strategy_id": result.strategy_id,
        "task_id": result.task_id,
        "packer_mode": result.packer_mode,
        "routing_changed": result.routing_changed,
    }
    serialized = json.dumps(d)
    assert isinstance(serialized, str)
