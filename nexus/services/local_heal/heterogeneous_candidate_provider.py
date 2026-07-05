"""C10B: Heterogeneous candidate provider for local portfolio.

Supports bucket-specific primary proposer and disagreement-triggered second proposer.
Not fixed dual-run Qwen+DeepSeek.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class HeterogeneousCandidate:
    candidate_id: str
    model_name: str
    role: str  # "primary_proposer" | "secondary_proposer" | "judge"
    candidate_patch_hash: str
    source_anchor_hash: str
    evidence_refs: tuple[str, ...]
    provider_invoked: bool = False
    provider_error: str = ""
    bucket: str = ""
    trigger_reason: str = ""


class HeterogeneousCandidateProvider:
    """Provides candidates from multiple models with bucket-specific logic."""

    def __init__(
        self,
        primary_model: str | None = None,
        secondary_model: str | None = None,
        judge_model: str | None = None,
    ):
        if not primary_model:
            raise ValueError("primary_model is required — must be provided by planner/signal_snapshot")
        self.primary_model = primary_model
        self.secondary_model = secondary_model or ""
        self.judge_model = judge_model or ""

    def generate_candidates(
        self,
        task_id: str,
        problem_statement: str,
        target_file: str,
        target_symbol: str,
        locked_search: str,
        evidence_refs: tuple[str, ...],
        disagreement_detected: bool = False,
        high_uncertainty: bool = False,
    ) -> list[HeterogeneousCandidate]:
        """Generate candidates based on task characteristics.

        Primary proposer always runs.
        Secondary proposer only runs if disagreement or high uncertainty triggers.
        """
        candidates = []

        # Primary proposer always runs
        candidates.append(HeterogeneousCandidate(
            candidate_id=f"{task_id}#primary",
            model_name=self.primary_model,
            role="primary_proposer",
            candidate_patch_hash="",
            source_anchor_hash=hashlib.sha256(locked_search.encode()).hexdigest() if locked_search else "",
            evidence_refs=evidence_refs,
            bucket="default",
            trigger_reason="always",
        ))

        # Secondary proposer only on disagreement/uncertainty trigger
        if disagreement_detected or high_uncertainty:
            candidates.append(HeterogeneousCandidate(
                candidate_id=f"{task_id}#secondary",
                model_name=self.secondary_model,
                role="secondary_proposer",
                candidate_patch_hash="",
                source_anchor_hash=hashlib.sha256(locked_search.encode()).hexdigest() if locked_search else "",
                evidence_refs=evidence_refs,
                bucket="disagreement" if disagreement_detected else "uncertainty",
                trigger_reason="disagreement" if disagreement_detected else "high_uncertainty",
            ))

        return candidates
