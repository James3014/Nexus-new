from __future__ import annotations

import os
from dataclasses import dataclass
from nexus.services.local_heal.candidate_envelope import CandidateEnvelope
from nexus.services.local_heal.local_model_capability_context import (
    LocalModelCapabilityContext,
    CapabilityExecutionResult,
)


@dataclass(frozen=True)
class CandidateDecisionResponse:
    selected_candidate_id: str
    selected_candidate_patch: str
    ranking_trace: list[str]
    selected_by: str
    decision_evidence_refs: tuple[str, ...]
    final_authority: str = "NexusVerifier"
    ddtree_result: CapabilityExecutionResult | None = None
    autoreason_result: CapabilityExecutionResult | None = None


class CandidateDecisionAdapter:
    @staticmethod
    def select_candidate(
        candidates: list[CandidateEnvelope],
        selected_capabilities: tuple[str, ...] = (),
        ctx: LocalModelCapabilityContext | None = None,
    ) -> CandidateDecisionResponse:
        # Env var → capabilities fallback (tests set env var, not selected_capabilities)
        if not selected_capabilities:
            _caps: list[str] = []
            if os.environ.get("NEXUS_ENABLE_DDTREE") == "1":
                _caps.append("ddtree")
            if os.environ.get("NEXUS_ENABLE_AUTOREASON") == "1":
                _caps.append("autoreason")
            selected_capabilities = tuple(_caps)

        # Validate that all active candidates have evidence_refs
        for c in candidates:
            if not c.evidence_refs:
                raise ValueError(f"Candidate {c.candidate_id} is missing evidence_refs")

        # Filter out abstained/blocked candidates
        active_candidates = [
            c for c in candidates
            if not c.abstained and not any("forbidden" in flag or "blocked" in flag for flag in c.risk_flags)
        ]

        ranking_trace: list[str] = []
        ddtree_result: CapabilityExecutionResult | None = None
        autoreason_result: CapabilityExecutionResult | None = None

        # 1. DDTree Pruning Layer — risk-flag filtering + real runtime call
        if "ddtree" in selected_capabilities:
            # Risk-flag pruning: candidates with invalid_dependency but no verifier_pass are pruned
            before_pruning = len(active_candidates)
            pruned_candidates = []
            kept_candidates = []
            for c in active_candidates:
                has_invalid = "invalid_dependency" in c.risk_flags
                has_verifier_pass = "verifier_pass" in c.risk_flags
                if has_invalid and not has_verifier_pass:
                    pruned_candidates.append(c)
                else:
                    kept_candidates.append(c)
            active_candidates = kept_candidates
            for c in pruned_candidates:
                ranking_trace.append(f"DDTree pruned {c.candidate_id} due to invalid dependency")

            from nexus.services.local_heal.local_model_capability_executors import DDTreeLocalExecutor
            executor = DDTreeLocalExecutor()
            ddtree_result = executor.execute(ctx or LocalModelCapabilityContext(
                task_id="", source_root="", problem_statement="",
                target_file="", target_symbol="", selected_capabilities=selected_capabilities,
                execution_topology="", evidence_refs=(),
                candidate_pool=active_candidates,
            ))

        # 2. Autoreason Ranking Layer — real runtime call
        if "autoreason" in selected_capabilities:
            from nexus.services.local_heal.local_model_capability_executors import AutoreasonLocalExecutor
            executor = AutoreasonLocalExecutor()
            autoreason_result = executor.execute(ctx or LocalModelCapabilityContext(
                task_id="", source_root="", problem_statement="",
                target_file="", target_symbol="", selected_capabilities=selected_capabilities,
                execution_topology="", evidence_refs=(),
                candidate_pool=active_candidates,
            ))
            if autoreason_result.invoked:
                winner = autoreason_result.telemetries.get("winner")
                borda_scores = autoreason_result.telemetries.get("borda_scores", {})
                if winner and borda_scores:
                    # Sort by borda score descending
                    active_candidates = sorted(
                        active_candidates,
                        key=lambda c: borda_scores.get(c.candidate_id, 0),
                        reverse=True,
                    )
                    ranking_trace.append("Autoreason ranked candidates by score")
                else:
                    ranking_trace.append("Autoreason returned no ranking")
            else:
                ranking_trace.append(f"Autoreason not invoked: {autoreason_result.failure_reason}")

        # 3. Decision Logic — C6V: output-quality-aware selection
        # Prefer candidates with better output class (VALID_SEARCH_REPLACE > FENCED > UNIFIED_DIFF)
        # Fallback to role priority when output classes are equal
        selected_candidate = None
        selected_by = "deterministic_fallback"

        if active_candidates:
            def output_quality_priority(c):
                # Higher priority = better output quality
                oc = getattr(c, "output_class", "")
                if oc == "VALID_SEARCH_REPLACE":
                    return 0
                elif oc == "FENCED_SEARCH_REPLACE":
                    return 1
                elif oc == "SEARCH_REPLACE_SEARCH_MISMATCH":
                    return 2
                elif oc == "UNIFIED_DIFF":
                    return 3
                return 4  # Unknown or empty

            def role_priority(c):
                if c.role == "external_primary":
                    return 0
                elif c.role == "primary_proposer":
                    return 1
                elif c.role == "secondary_proposer":
                    return 2
                return 3

            # Sort by output quality first, then role priority as tiebreaker
            active_candidates = sorted(
                active_candidates,
                key=lambda c: (output_quality_priority(c), role_priority(c))
            )

            if active_candidates[0].role == "external_primary":
                selected_by = "external_primary_policy"
            elif active_candidates[0].role == "primary_proposer":
                selected_by = "candidate_policy"
            elif active_candidates[0].role == "secondary_proposer":
                selected_by = "candidate_policy_fallback"

            selected_candidate = active_candidates[0]
            ranking_trace.append(f"Selected {selected_candidate.role}: {selected_candidate.candidate_id} via {selected_by}")
        else:
            ranking_trace.append("No active candidates available")

        if selected_candidate:
            return CandidateDecisionResponse(
                selected_candidate_id=selected_candidate.candidate_id,
                selected_candidate_patch=selected_candidate.candidate_patch,
                ranking_trace=ranking_trace,
                selected_by=selected_by,
                decision_evidence_refs=selected_candidate.evidence_refs,
                ddtree_result=ddtree_result,
                autoreason_result=autoreason_result,
            )
        else:
            return CandidateDecisionResponse(
                selected_candidate_id="",
                selected_candidate_patch="",
                ranking_trace=ranking_trace,
                selected_by="none_available",
                decision_evidence_refs=(),
                ddtree_result=ddtree_result,
                autoreason_result=autoreason_result,
            )
