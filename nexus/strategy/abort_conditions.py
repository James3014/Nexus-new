"""Abort condition evaluator — trace-only, never blocks in S0."""

from typing import List
from .strategy_envelope import StrategyEnvelope


class AbortConditionEvaluator:
    """Evaluate abort conditions. In S0, emits telemetry only."""

    STANDARD_ABORTS = [
        "target_file_missing",
        "canonical_search_unlocked",
        "source_snapshot_missing",
        "model_generated_search_required",
        "no_effective_change",
        "verification_unavailable",
        "public_claim_boundary_missing",
    ]

    def evaluate(self, envelope: StrategyEnvelope,
                 target_file_exists: bool = True,
                 canonical_search_locked: bool = True,
                 source_snapshot_present: bool = True,
                 model_generated_search_required: bool = False,
                 effective_change: bool = True,
                 verification_available: bool = True,
                 public_claim_boundary_present: bool = True,
                 attribution_ambiguous: bool = False,
                 ) -> dict:
        """Evaluate abort conditions. Never blocks in S0."""

        triggered = []

        if not target_file_exists and "target_file_missing" in envelope.abort_conditions:
            triggered.append("target_file_missing")

        if not canonical_search_locked and "canonical_search_unlocked" in envelope.abort_conditions:
            triggered.append("canonical_search_unlocked")

        if not source_snapshot_present and "source_snapshot_missing" in envelope.abort_conditions:
            triggered.append("source_snapshot_missing")

        if model_generated_search_required and "model_generated_search_required" in envelope.abort_conditions:
            triggered.append("model_generated_search_required")

        if not effective_change and "no_effective_change" in envelope.abort_conditions:
            triggered.append("no_effective_change")

        if not verification_available and "verification_unavailable" in envelope.abort_conditions:
            triggered.append("verification_unavailable")

        if not public_claim_boundary_present and "public_claim_boundary_missing" in envelope.abort_conditions:
            triggered.append("public_claim_boundary_missing")

        if attribution_ambiguous:
            triggered.append("attribution_ambiguous")

        return {
            "abort_condition_triggered": len(triggered) > 0,
            "triggered_abort_conditions": triggered,
            "would_abort": len(triggered) > 0,
            "enforcement_action": "none",
            "trace_only": True,
        }
