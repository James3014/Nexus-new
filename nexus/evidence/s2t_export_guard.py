"""
S2T Export Guard v2: Prevents deterministic fallback success from being
counted as 14B patch success in training data.

Rules:
- model_calls=0: model_patch_reward=0.0, export_as_model_patch_success=false
- deterministic_fallback_used=true: model_patch_reward=0.0, cannot enter chosen-pair
- canonical_span_source=ast_boundary with model_calls=0: ast_fallback_reward=1.0
- llm_replace_success=true, deterministic_fallback_used=false, model_calls>0: model_patch_reward may be 1.0
- claim_eligible=false: no public claim
- workspace failure: export_as_internal_infra_failure=true, count_as_model_failure=false
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class S2TExportGuard:
    """Guard for S2T/training export attribution (v2)."""
    deterministic_fallback_used: bool = False
    llm_replace_success: bool = False
    canonical_span_source: str = ""
    model_calls: int = 0
    recovery_rule_id: str = ""
    recovery_rule_type: str = ""
    repro_failure: bool = False
    bug_reproduced_before_patch: bool = True
    repro_failure_subclass: str = ""
    verification_failed: bool = False
    repro_script_issue: bool = False
    unstable_reproduction: bool = False
    test_harness_error: bool = False
    model_patch_reward: float = 0.0
    deterministic_fallback_reward: float = 0.0
    ast_fallback_reward: float = 0.0
    repro_recovery_reward: float = 0.0
    workspace_recovery_reward: float = 0.0
    claim_eligible: bool = False
    can_enter_chosen_pair: bool = False
    can_enter_tool_demonstration: bool = False
    export_as_model_patch_success: bool = False
    export_as_canonical_recovery_success: bool = False
    export_as_tool_demonstration: bool = False
    export_as_internal_diagnostic: bool = False
    export_as_internal_infra_failure: bool = False
    export_as_public_claim: bool = False
    requires_human_review_before_training: bool = True
    count_as_model_failure: bool = False
    count_as_patcher_failure: bool = False
    block_reason: str = ""

    def evaluate(self) -> None:
        """Apply export guard rules. Order matters — most restrictive first."""
        # Rule 1: model_calls=0 → never model patch success
        if self.model_calls == 0:
            self.model_patch_reward = 0.0
            self.export_as_model_patch_success = False
            self.export_as_public_claim = False
            self.export_as_canonical_recovery_success = True if self.canonical_span_source == "ast_boundary" else False

        # Rule 2: deterministic_fallback_used
        if self.deterministic_fallback_used:
            self.model_patch_reward = 0.0
            self.deterministic_fallback_reward = 1.0
            self.ast_fallback_reward = 0.0
            self.can_enter_chosen_pair = False
            self.can_enter_tool_demonstration = True
            self.export_as_model_patch_success = False
            self.export_as_canonical_recovery_success = False
            self.export_as_tool_demonstration = True
            self.requires_human_review_before_training = True
            self.block_reason = "deterministic_fallback_used"

        # Rule 3: ast_boundary + model_calls=0
        elif self.canonical_span_source == "ast_boundary" and self.model_calls == 0:
            self.model_patch_reward = 0.0
            self.deterministic_fallback_reward = 0.0
            self.ast_fallback_reward = 1.0
            self.can_enter_chosen_pair = False
            self.can_enter_tool_demonstration = True
            self.export_as_model_patch_success = False
            self.export_as_canonical_recovery_success = True
            self.export_as_tool_demonstration = True
            self.requires_human_review_before_training = True
            self.block_reason = "ast_boundary_deterministic"

        # Rule 4: repro_failure / repro_script_issue / unstable_reproduction / test_harness_error — infra failure
        elif self.repro_failure or self.repro_script_issue or self.unstable_reproduction or self.test_harness_error:
            self.model_patch_reward = 0.0
            self.deterministic_fallback_reward = 0.0
            self.ast_fallback_reward = 0.0
            self.repro_recovery_reward = 1.0 if self.repro_failure_subclass in ("env_noise", "test_harness", "workspace_config", "repro_script_dependency_issue") else 0.0
            self.can_enter_chosen_pair = False
            self.can_enter_tool_demonstration = False
            self.export_as_model_patch_success = False
            self.export_as_canonical_recovery_success = False
            self.export_as_internal_infra_failure = True
            self.count_as_model_failure = False
            self.count_as_patcher_failure = False
            self.requires_human_review_before_training = True
            self.block_reason = "repro_failure_infra"

        # Rule 5: verification_failed — can count as patcher failure only if stable repro + patch applied
        elif self.verification_failed:
            self.model_patch_reward = 0.0
            self.deterministic_fallback_reward = 0.0
            self.ast_fallback_reward = 0.0
            self.can_enter_chosen_pair = False
            self.can_enter_tool_demonstration = False
            self.export_as_model_patch_success = False
            self.export_as_canonical_recovery_success = False
            self.count_as_model_failure = self.model_calls > 0
            self.count_as_patcher_failure = True
            self.requires_human_review_before_training = True
            self.block_reason = "verification_failed"

        # Rule 6: llm_replace_success + model_calls>0
        elif self.llm_replace_success and not self.deterministic_fallback_used and self.model_calls > 0:
            self.model_patch_reward = 1.0
            self.deterministic_fallback_reward = 0.0
            self.ast_fallback_reward = 0.0
            self.can_enter_chosen_pair = self.claim_eligible
            self.can_enter_tool_demonstration = True
            self.export_as_model_patch_success = self.claim_eligible
            self.export_as_canonical_recovery_success = False
            self.export_as_tool_demonstration = True
            self.requires_human_review_before_training = False
            self.block_reason = ""

        # Rule 7: llm failed or no model calls
        else:
            self.model_patch_reward = 0.0
            self.deterministic_fallback_reward = 0.0
            self.ast_fallback_reward = 0.0
            self.can_enter_chosen_pair = False
            self.can_enter_tool_demonstration = False
            self.export_as_model_patch_success = False
            self.export_as_canonical_recovery_success = False
            self.block_reason = "llm_replace_failed" if not self.model_calls else "model_calls_zero"

        # Rule 8: claim_eligible=false blocks public claim
        if not self.claim_eligible:
            self.can_enter_chosen_pair = False
            self.export_as_public_claim = False
            self.export_as_internal_diagnostic = True
            if not self.block_reason:
                self.block_reason = "claim_not_eligible"

    def to_dict(self) -> dict:
        return {
            "deterministic_fallback_used": self.deterministic_fallback_used,
            "llm_replace_success": self.llm_replace_success,
            "canonical_span_source": self.canonical_span_source,
            "model_calls": self.model_calls,
            "recovery_rule_id": self.recovery_rule_id,
            "recovery_rule_type": self.recovery_rule_type,
            "model_patch_reward": self.model_patch_reward,
            "deterministic_fallback_reward": self.deterministic_fallback_reward,
            "ast_fallback_reward": self.ast_fallback_reward,
            "claim_eligible": self.claim_eligible,
            "can_enter_chosen_pair": self.can_enter_chosen_pair,
            "can_enter_tool_demonstration": self.can_enter_tool_demonstration,
            "export_as_model_patch_success": self.export_as_model_patch_success,
            "export_as_canonical_recovery_success": self.export_as_canonical_recovery_success,
            "export_as_tool_demonstration": self.export_as_tool_demonstration,
            "export_as_internal_diagnostic": self.export_as_internal_diagnostic,
            "export_as_internal_infra_failure": self.export_as_internal_infra_failure,
            "export_as_public_claim": self.export_as_public_claim,
            "requires_human_review_before_training": self.requires_human_review_before_training,
            "count_as_model_failure": self.count_as_model_failure,
            "count_as_patcher_failure": self.count_as_patcher_failure,
            "block_reason": self.block_reason,
        }


def evaluate_s2t_export_guard(
    *,
    deterministic_fallback_used: bool = False,
    llm_replace_success: bool = False,
    canonical_span_source: str = "",
    model_calls: int = 0,
    claim_eligible: bool = False,
) -> S2TExportGuard:
    """Convenience function to evaluate S2T export guard."""
    guard = S2TExportGuard(
        deterministic_fallback_used=deterministic_fallback_used,
        llm_replace_success=llm_replace_success,
        canonical_span_source=canonical_span_source,
        model_calls=model_calls,
        claim_eligible=claim_eligible,
    )
    guard.evaluate()
    return guard
