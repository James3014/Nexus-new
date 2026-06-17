"""
S2T Export Guard: Prevents deterministic fallback success from being
counted as 14B patch success in training data.

Rules:
- deterministic_fallback_used=true: model_patch_reward=0.0, cannot enter chosen-pair
- llm_replace_success=true, deterministic_fallback_used=false: model_patch_reward=1.0
- claim_eligible=false: no public claim
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class S2TExportGuard:
    """Guard for S2T/training export attribution."""
    deterministic_fallback_used: bool = False
    llm_replace_success: bool = bool
    model_patch_reward: float = 0.0
    deterministic_fallback_reward: float = 0.0
    claim_eligible: bool = False
    can_enter_chosen_pair: bool = False
    can_enter_tool_demonstration: bool = False
    block_reason: str = ""

    def evaluate(self) -> None:
        """Apply export guard rules."""
        if self.deterministic_fallback_used:
            self.model_patch_reward = 0.0
            self.deterministic_fallback_reward = 1.0
            self.can_enter_chosen_pair = False
            self.can_enter_tool_demonstration = True
            self.block_reason = "deterministic_fallback_used"
        elif self.llm_replace_success and not self.deterministic_fallback_used:
            self.model_patch_reward = 1.0
            self.deterministic_fallback_reward = 0.0
            self.can_enter_chosen_pair = self.claim_eligible
            self.can_enter_tool_demonstration = True
            self.block_reason = ""
        else:
            self.model_patch_reward = 0.0
            self.deterministic_fallback_reward = 0.0
            self.can_enter_chosen_pair = False
            self.can_enter_tool_demonstration = False
            self.block_reason = "llm_replace_failed"

        if not self.claim_eligible:
            self.can_enter_chosen_pair = False
            if not self.block_reason:
                self.block_reason = "claim_not_eligible"

    def to_dict(self) -> dict:
        return {
            "deterministic_fallback_used": self.deterministic_fallback_used,
            "llm_replace_success": self.llm_replace_success,
            "model_patch_reward": self.model_patch_reward,
            "deterministic_fallback_reward": self.deterministic_fallback_reward,
            "claim_eligible": self.claim_eligible,
            "can_enter_chosen_pair": self.can_enter_chosen_pair,
            "can_enter_tool_demonstration": self.can_enter_tool_demonstration,
            "block_reason": self.block_reason,
        }


def evaluate_s2t_export_guard(
    *,
    deterministic_fallback_used: bool,
    llm_replace_success: bool,
    claim_eligible: bool,
) -> S2TExportGuard:
    """Convenience function to evaluate S2T export guard."""
    guard = S2TExportGuard(
        deterministic_fallback_used=deterministic_fallback_used,
        llm_replace_success=llm_replace_success,
        claim_eligible=claim_eligible,
    )
    guard.evaluate()
    return guard
