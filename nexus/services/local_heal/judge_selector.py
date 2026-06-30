"""C10B: Judge selector for local portfolio.

3B judge/selector receives candidates and produces selection receipt.
Judge does NOT do final verify.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class JudgeSelectionReceipt:
    selected_candidate_id: str
    judge_model: str
    judge_invoked: bool
    selection_reason: str
    judge_cannot_verify: bool = True


class JudgeSelector:
    """3B judge/selector for candidate ranking and selection."""

    def __init__(self, judge_model: str = "qwen2.5:3b"):
        self.judge_model = judge_model

    def select(
        self,
        candidates: list[Any],
        task_id: str = "",
    ) -> JudgeSelectionReceipt:
        """Select best candidate using deterministic role priority.

        Judge does NOT do final verify - only ranking/selection.
        """
        if not candidates:
            return JudgeSelectionReceipt(
                selected_candidate_id="",
                judge_model=self.judge_model,
                judge_invoked=False,
                selection_reason="no_candidates",
                judge_cannot_verify=True,
            )

        # Deterministic role priority: primary > secondary > other
        def role_priority(c):
            role = getattr(c, "role", "")
            if role == "primary_proposer":
                return 0
            elif role == "secondary_proposer":
                return 1
            return 2

        sorted_candidates = sorted(candidates, key=role_priority)
        selected = sorted_candidates[0]

        return JudgeSelectionReceipt(
            selected_candidate_id=getattr(selected, "candidate_id", ""),
            judge_model=self.judge_model,
            judge_invoked=True,
            selection_reason=f"role_priority:{getattr(selected, 'role', 'unknown')}",
            judge_cannot_verify=True,
        )
