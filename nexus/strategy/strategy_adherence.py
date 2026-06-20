"""Strategy adherence checker — trace-only, emits telemetry only."""

from typing import List, Tuple
from .strategy_envelope import StrategyEnvelope


class StrategyAdherenceChecker:
    """Evaluate execution trace consistency with StrategyEnvelope."""

    def check(self, envelope: StrategyEnvelope,
              modified_files: List[str] = None,
              source_snapshot_present: bool = True,
              canonical_search_locked: bool = True,
              effective_change: bool = True,
              verification_result: str = "",
              public_claim_allowed: bool = False,
              model_generated_search_used: bool = False,
              truth_patch_used: bool = False,
              manual_patch_used: bool = False,
              deterministic_fallback_used: bool = False,
              ) -> dict:
        """Check adherence. Never blocks execution in S0."""

        violations = []
        warnings = []

        if modified_files and envelope.forbidden_paths:
            for f in modified_files:
                for fp in envelope.forbidden_paths:
                    if f.startswith(fp):
                        violations.append(f"forbidden_path: {f}")

        if modified_files and envelope.allowed_paths:
            for f in modified_files:
                if not any(f.startswith(ap) for ap in envelope.allowed_paths):
                    warnings.append(f"outside_allowed_paths: {f}")

        if envelope.require_canonical_search_lock and not canonical_search_locked:
            warnings.append("canonical_search_not_locked")

        if envelope.require_source_snapshot and not source_snapshot_present:
            warnings.append("source_snapshot_missing")

        if envelope.require_effective_change and not effective_change:
            warnings.append("no_effective_change")

        if public_claim_allowed:
            violations.append("public_claim_allowed")

        if model_generated_search_used:
            violations.append("model_generated_search_used")

        if truth_patch_used:
            violations.append("truth_patch_used")

        if manual_patch_used:
            violations.append("manual_patch_used")

        if deterministic_fallback_used:
            warnings.append("deterministic_fallback_used")

        status = "pass"
        if violations:
            status = "violation"
        elif warnings:
            status = "warning"

        return {
            "adherence_status": status,
            "adherence_violations": violations,
            "adherence_warnings": warnings,
            "trace_only": True,
            "enforcement_action": "none",
        }
