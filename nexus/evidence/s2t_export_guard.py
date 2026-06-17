"""
S2T Export Guard: Prevents deterministic fallback success from being
counted as 14B patch success in training data.

Rules:
- model_calls=0: model_patch_reward=0.0, export_as_model_patch_success=false
- deterministic_fallback_used=true: model_patch_reward=0.0, cannot enter chosen-pair
- canonical_span_source=ast_boundary with model_calls=0: ast_fallback_reward=1.0
- llm_replace_success=true, deterministic_fallback_used=false, model_calls>0: model_patch_reward may be 1.0
- claim_eligible=false: no public claim
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class S2TExportGuard:
    """Guard for S2T/training export attribution."""
    deterministic_fallback_used: bool = False
    llm_replace_success: bool = False
    canonical_span_source: str = ""
    model_calls: int = 0
    model_patch_reward: float = 0.0
    deterministic_fallback_reward: float = 0.0
    ast_fallback_reward: float = 0.0
    claim_eligible: bool = False
    can_enter_chosen_pair: bool = False
    can_enter_tool_demonstration: bool = False
    export_as_model_patch_success: bool = False
    export_as_canonical_recovery_success: bool = False
    export_as_public_claim: bool = False
    block_reason: str = ""

    def evaluate(self) -> None:
        """Apply export guard rules. Order matters — most restrictive first."""
        # Rule 1: model_calls=0 → never model patch success
        if self.model_calls == 0:
            self.model_patch_reward = 0.0
            self.export_as_model_patch_success = False
            self.export_as_public_claim = False

        # Rule 2: deterministic_fallback_used
        if self.deterministic_fallback_used:
            self.model_patch_reward = 0.0
            self.deterministic_fallback_reward = 1.0
            self.ast_fallback_reward = 0.0
            self.can_enter_chosen_pair = False
            self.can_enter_tool_demonstration = True
            self.export_as_model_patch_success = False
            self.export_as_canonical_recovery_success = False
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
            self.block_reason = "ast_boundary_deterministic"

        # Rule 4: llm_replace_success + model_calls>0
        elif self.llm_replace_success and not self.deterministic_fallback_used and self.model_calls > 0:
            self.model_patch_reward = 1.0
            self.deterministic_fallback_reward = 0.0
            self.ast_fallback_reward = 0.0
            self.can_enter_chosen_pair = self.claim_eligible
            self.can_enter_tool_demonstration = True
            self.export_as_model_patch_success = self.claim_eligible
            self.export_as_canonical_recovery_success = False
            self.block_reason = ""

        # Rule 5: llm failed or no model calls
        else:
            self.model_patch_reward = 0.0
            self.deterministic_fallback_reward = 0.0
            self.ast_fallback_reward = 0.0
            self.can_enter_chosen_pair = False
            self.can_enter_tool_demonstration = False
            self.export_as_model_patch_success = False
            self.export_as_canonical_recovery_success = False
            self.block_reason = "llm_replace_failed" if not self.model_calls else "model_calls_zero"

        # Rule 6: claim_eligible=false blocks public claim
        if not self.claim_eligible:
            self.can_enter_chosen_pair = False
            self.export_as_public_claim = False
            if not self.block_reason:
                self.block_reason = "claim_not_eligible"

    def to_dict(self) -> dict:
        return {
            "deterministic_fallback_used": self.deterministic_fallback_used,
            "llm_replace_success": self.llm_replace_success,
            "canonical_span_source": self.canonical_span_source,
            "model_calls": self.model_calls,
            "model_patch_reward": self.model_patch_reward,
            "deterministic_fallback_reward": self.deterministic_fallback_reward,
            "ast_fallback_reward": self.ast_fallback_reward,
            "claim_eligible": self.claim_eligible,
            "can_enter_chosen_pair": self.can_enter_chosen_pair,
            "can_enter_tool_demonstration": self.can_enter_tool_demonstration,
            "export_as_model_patch_success": self.export_as_model_patch_success,
            "export_as_canonical_recovery_success": self.export_as_canonical_recovery_success,
            "export_as_public_claim": self.export_as_public_claim,
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
