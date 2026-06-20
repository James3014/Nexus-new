"""Tests for Recovery Rule Registry + Export Guard v2."""
from __future__ import annotations

import json
from pathlib import Path

from nexus.evidence.recovery_rule_registry import (
    RecoveryRuleRegistry,
    get_recovery_rule,
    RECOVERY_RULES,
)
from nexus.evidence.s2t_export_guard import evaluate_s2t_export_guard


# ============================================================
# 1. Recovery Rule Registry Tests
# ============================================================

def test_registry_has_t2_1_rules():
    """Registry contains all T2.1 known rules."""
    registry = RecoveryRuleRegistry()
    rules = registry.list_rules()
    rule_ids = [r.rule_id for r in rules]
    assert "AST_SYMBOL_FIX" in rule_ids
    assert "REMOVE_BLOCK" in rule_ids
    assert "AST_BOUNDARY_EXTRACT" in rule_ids
    assert "locked_search_reuse" in rule_ids
    assert "unified_diff_reuse" in rule_ids


def test_rule_attribution():
    """Rules have correct reward attribution."""
    ast_rule = get_recovery_rule("AST_SYMBOL_FIX")
    assert ast_rule is not None
    assert ast_rule.model_patch_reward == 0.0
    assert ast_rule.ast_fallback_reward == 1.0
    assert ast_rule.export_as_model_patch_success is False
    assert ast_rule.export_as_canonical_recovery_success is True

    remove_rule = get_recovery_rule("REMOVE_BLOCK")
    assert remove_rule is not None
    assert remove_rule.model_patch_reward == 0.0
    assert remove_rule.deterministic_fallback_reward == 1.0
    assert remove_rule.export_as_model_patch_success is False


def test_registry_save_load(tmp_path):
    """Registry can be saved and loaded."""
    registry = RecoveryRuleRegistry()
    path = tmp_path / "rules.json"
    registry.save(path)
    
    loaded = RecoveryRuleRegistry.load(path)
    assert len(loaded.list_rules()) == len(registry.list_rules())
    assert loaded.get_rule("AST_SYMBOL_FIX") is not None


def test_get_recovery_rule_convenience():
    """Convenience function works."""
    rule = get_recovery_rule("AST_SYMBOL_FIX")
    assert rule is not None
    assert rule.rule_id == "AST_SYMBOL_FIX"
    
    assert get_recovery_rule("NONEXISTENT") is None


# ============================================================
# 2. Export Guard v2 Tests
# ============================================================

def test_export_guard_v2_has_new_fields():
    """Export guard v2 has recovery_rule_id and new export fields."""
    guard = evaluate_s2t_export_guard(model_calls=0, claim_eligible=True)
    d = guard.to_dict()
    assert "recovery_rule_id" in d
    assert "recovery_rule_type" in d
    assert "export_as_tool_demonstration" in d
    assert "export_as_internal_diagnostic" in d
    assert "export_as_internal_infra_failure" in d
    assert "requires_human_review_before_training" in d
    assert "count_as_model_failure" in d
    assert "count_as_patcher_failure" in d


def test_export_guard_v2_model_calls_zero():
    """model_calls=0 blocks model patch success, allows canonical recovery."""
    guard = evaluate_s2t_export_guard(
        model_calls=0, canonical_span_source="ast_boundary", claim_eligible=True,
    )
    assert guard.model_patch_reward == 0.0
    assert guard.export_as_model_patch_success is False
    assert guard.export_as_canonical_recovery_success is True
    assert guard.export_as_tool_demonstration is True


def test_export_guard_v2_deterministic_fallback():
    """deterministic_fallback_used blocks model patch success."""
    guard = evaluate_s2t_export_guard(
        deterministic_fallback_used=True, model_calls=5, claim_eligible=True,
    )
    assert guard.model_patch_reward == 0.0
    assert guard.export_as_model_patch_success is False
    assert guard.export_as_tool_demonstration is True
    assert guard.requires_human_review_before_training is True


def test_export_guard_v2_llm_success():
    """llm_replace_success with model_calls>0 allows model patch success."""
    guard = evaluate_s2t_export_guard(
        llm_replace_success=True, model_calls=5, claim_eligible=True,
    )
    assert guard.model_patch_reward == 1.0
    assert guard.export_as_model_patch_success is True
    assert guard.requires_human_review_before_training is False


def test_export_guard_v2_claim_not_eligible():
    """claim_eligible=false blocks public claim and marks internal diagnostic."""
    guard = evaluate_s2t_export_guard(
        llm_replace_success=True, model_calls=5, claim_eligible=False,
    )
    assert guard.export_as_public_claim is False
    assert guard.export_as_internal_diagnostic is True
    assert guard.can_enter_chosen_pair is False
