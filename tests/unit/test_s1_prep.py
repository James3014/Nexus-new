"""T2.0 tests: S2T Export Guard + StrategyTrace-only."""
from __future__ import annotations

import json
from pathlib import Path

from nexus.evidence.s2t_export_guard import evaluate_s2t_export_guard


# ============================================================
# 1. StrategyTrace-only Receipt Tests
# ============================================================

def test_receipt_has_strategy_trace_block():
    """Receipt includes strategy_trace block with trace_only=true."""
    from nexus.services.local_heal.receipt import build_repair_receipt
    from types import SimpleNamespace

    ctx = SimpleNamespace(
        instance_id="test-001", repo_dir=Path("/tmp"), problem_statement="test",
        final_patch="", evaluation_report="", reproduced=False, solve_eligible=False,
        failure_reason="TEST", model_decisions=[], attempt=1, reasoning_mode="INTUITIVE",
        env_denoise={}, env_resolution={}, token_telemetry_status="not_applicable",
        token_total_estimated=0, preflight_telemetry={}, closest_snippet="",
        closest_snippet_similarity=0.0, resolved_span="", _semantic_retry_telemetry={},
        _latency_ledger=None, runner_completed=False, repro_script="",
        python_executable="python3", hidden_verifier_required=False,
        hidden_verifier_passed=False, syntax_gate_passed=True, prompt_variant_id="default",
        refusal_detected=False, empty_response=False, expected_stop_layer="verification",
        expected_reason_family="SOLVED", wall_time_sec=0.0, initial_ctx_len=0,
        final_ctx_len=0, resolved_span_len=0, local_mode=False,
    )
    ctx.op = ctx
    ctx.gov = SimpleNamespace(expected_stop_layer="verification", expected_reason_family="SOLVED")
    receipt = build_repair_receipt(ctx)

    assert "strategy_trace" in receipt
    st = receipt["strategy_trace"]
    assert st["strategy_trace_only"] is True
    assert "canonical_span_confidence" in st
    assert "ast_fallback_reward" in st
    assert "model_calls" in st
    assert "claim_eligible" in st
    assert "public_claim_allowed" in st


# ============================================================
# 2. S2T Export Guard — Rule 1: model_calls=0
# ============================================================

def test_model_calls_zero_blocks_model_patch_success():
    """model_calls=0 → model_patch_reward=0.0, export_as_model_patch_success=false."""
    guard = evaluate_s2t_export_guard(model_calls=0, llm_replace_success=True, claim_eligible=True)
    assert guard.model_patch_reward == 0.0
    assert guard.export_as_model_patch_success is False
    assert guard.export_as_public_claim is False


def test_model_calls_zero_with_llm_success():
    """model_calls=0 even with llm_replace_success → still blocked."""
    guard = evaluate_s2t_export_guard(model_calls=0, llm_replace_success=True, claim_eligible=True)
    assert guard.model_patch_reward == 0.0
    assert guard.can_enter_chosen_pair is False


# ============================================================
# 3. S2T Export Guard — Rule 2: deterministic_fallback
# ============================================================

def test_deterministic_fallback_blocks_chosen_pair():
    """deterministic_fallback_used=true blocks chosen-pair entry."""
    guard = evaluate_s2t_export_guard(deterministic_fallback_used=True, model_calls=5, claim_eligible=True)
    assert guard.model_patch_reward == 0.0
    assert guard.deterministic_fallback_reward == 1.0
    assert guard.can_enter_chosen_pair is False
    assert guard.can_enter_tool_demonstration is True
    assert guard.export_as_model_patch_success is False
    assert guard.block_reason == "deterministic_fallback_used"


# ============================================================
# 4. S2T Export Guard — Rule 3: ast_boundary + model_calls=0
# ============================================================

def test_ast_boundary_model_calls_zero():
    """canonical_span_source=ast_boundary with model_calls=0 → ast_fallback_reward=1.0."""
    guard = evaluate_s2t_export_guard(
        canonical_span_source="ast_boundary", model_calls=0, claim_eligible=True,
    )
    assert guard.model_patch_reward == 0.0
    assert guard.ast_fallback_reward == 1.0
    assert guard.export_as_model_patch_success is False
    assert guard.export_as_canonical_recovery_success is True
    assert guard.can_enter_chosen_pair is False
    assert guard.block_reason == "ast_boundary_deterministic"


# ============================================================
# 5. S2T Export Guard — Rule 4: llm_success + model_calls>0
# ============================================================

def test_llm_success_model_calls_positive():
    """llm_replace_success=true + model_calls>0 → model_patch_reward may be 1.0."""
    guard = evaluate_s2t_export_guard(
        llm_replace_success=True, model_calls=3, claim_eligible=True,
    )
    assert guard.model_patch_reward == 1.0
    assert guard.export_as_model_patch_success is True
    assert guard.can_enter_chosen_pair is True
    assert guard.block_reason == ""


def test_llm_success_claim_not_eligible():
    """llm_replace_success=true but claim_eligible=false → blocks chosen-pair."""
    guard = evaluate_s2t_export_guard(
        llm_replace_success=True, model_calls=3, claim_eligible=False,
    )
    assert guard.model_patch_reward == 1.0
    assert guard.can_enter_chosen_pair is False
    assert guard.export_as_model_patch_success is False
    assert guard.block_reason == "claim_not_eligible"


# ============================================================
# 6. S2T Export Guard — Rule 6: claim_eligible=false
# ============================================================

def test_claim_not_eligible_blocks_public_claim():
    """claim_eligible=false → public_claim_allowed=false."""
    guard = evaluate_s2t_export_guard(model_calls=5, llm_replace_success=True, claim_eligible=False)
    assert guard.export_as_public_claim is False
    assert guard.can_enter_chosen_pair is False


# ============================================================
# 7. S2T Export Guard — Roundtrip
# ============================================================

def test_export_guard_roundtrip():
    """Export guard to_dict has all fields."""
    guard = evaluate_s2t_export_guard(deterministic_fallback_used=True, model_calls=5, claim_eligible=True)
    d = guard.to_dict()
    assert "export_as_model_patch_success" in d
    assert "export_as_canonical_recovery_success" in d
    assert "export_as_public_claim" in d
    assert "ast_fallback_reward" in d
    assert "canonical_span_source" in d
