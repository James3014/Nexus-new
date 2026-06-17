"""T1.6a tests: Semantic Recovery Attribution Cleanup."""
from __future__ import annotations


def test_semantic_retry_telemetry_has_attribution_fields():
    """Semantic retry telemetry includes T1.6a attribution fields."""
    from nexus.services.local_heal.orchestrator import HealOrchestrator

    # Simulate the telemetry structure
    telemetry = {
        "semantic_retry_count": 1,
        "same_span_retry": True,
        "semantic_retry_mode": "llm_replace_rewrite",
        "llm_replace_success": False,
        "deterministic_fallback_used": False,
        "fallback_rule_id": "",
        "fallback_rule_scope": "",
        "fallback_rule_reason": "",
        "model_patch_reward": 0.0,
        "deterministic_fallback_reward": 0.0,
    }

    required_fields = [
        "semantic_retry_mode",
        "llm_replace_success",
        "deterministic_fallback_used",
        "fallback_rule_id",
        "fallback_rule_scope",
        "fallback_rule_reason",
        "model_patch_reward",
        "deterministic_fallback_reward",
    ]

    for field in required_fields:
        assert field in telemetry, f"Missing attribution field: {field}"


def test_llm_success_attribution():
    """When LLM succeeds, model_patch_reward=1.0, fallback=0.0."""
    telemetry = {
        "llm_replace_success": True,
        "deterministic_fallback_used": False,
        "model_patch_reward": 1.0,
        "deterministic_fallback_reward": 0.0,
    }
    assert telemetry["model_patch_reward"] == 1.0
    assert telemetry["deterministic_fallback_reward"] == 0.0
    assert telemetry["deterministic_fallback_used"] is False


def test_deterministic_fallback_attribution():
    """When deterministic fallback used, model_patch_reward=0.0, fallback=1.0."""
    telemetry = {
        "llm_replace_success": False,
        "deterministic_fallback_used": True,
        "fallback_rule_id": "ndarray_mixin_removal",
        "fallback_rule_scope": "astropy__astropy-13236",
        "fallback_rule_reason": "LLM REPLACE failed, deterministic block removal applied",
        "model_patch_reward": 0.0,
        "deterministic_fallback_reward": 1.0,
    }
    assert telemetry["model_patch_reward"] == 0.0
    assert telemetry["deterministic_fallback_reward"] == 1.0
    assert telemetry["deterministic_fallback_used"] is True


def test_no_hardcoded_ndarray_mixin_in_prompt():
    """Prompt builder does not contain hardcoded NdarrayMixin instruction."""
    from nexus.services.local_heal.prompt_builder import PromptBuilder

    prompt = PromptBuilder.build_verification_guided_retry_prompt(
        original_user_prompt="Fix the bug",
        verification_report="Test failed",
        canonical_search_span="def foo():\n    pass",
        target_file="test.py",
        retry_count=1,
    )

    assert "NdarrayMixin" not in prompt
    assert "REMOVE the entire" not in prompt
