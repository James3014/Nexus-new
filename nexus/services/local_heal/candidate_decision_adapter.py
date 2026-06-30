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

        # 1. DDTree Pruning Layer — real runtime call
        if "ddtree" in selected_capabilities:
            from nexus.services.local_heal.local_model_capability_executors import DDTreeLocalExecutor
            executor = DDTreeLocalExecutor()
            ddtree_result = executor.execute(ctx or LocalModelCapabilityContext(
                task_id="", source_root="", problem_statement="",
                target_file="", target_symbol="", selected_capabilities=selected_capabilities,
                execution_topology="", evidence_refs=(),
            ))
            if ddtree_result.invoked:
                selected_ids = ddtree_result.telemetries.get("selected_candidate_ids", [])
                if selected_ids:
                    before_count = len(active_candidates)
                    active_candidates = [c for c in active_candidates if c.candidate_id in selected_ids]
                    saved = before_count - len(active_candidates)
                    ranking_trace.append(f"DDTree pruned {saved} candidates, kept {len(active_candidates)}")
                else:
                    ranking_trace.append("DDTree returned no candidates")
            else:
                ranking_trace.append(f"DDTree not invoked: {ddtree_result.failure_reason}")

        # 2. Autoreason Ranking Layer — real runtime call
        if "autoreason" in selected_capabilities:
            from nexus.services.local_heal.local_model_capability_executors import AutoreasonLocalExecutor
            executor = AutoreasonLocalExecutor()
            autoreason_result = executor.execute(ctx or LocalModelCapabilityContext(
                task_id="", source_root="", problem_statement="",
                target_file="", target_symbol="", selected_capabilities=selected_capabilities,
                execution_topology="", evidence_refs=(),
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
                    ranking_trace.append(f"Autoreason ranked by borda, winner={winner}")
                else:
                    ranking_trace.append("Autoreason returned no ranking")
            else:
                ranking_trace.append(f"Autoreason not invoked: {autoreason_result.failure_reason}")

        # 3. Decision Logic — deterministic role priority
        selected_candidate = None
        selected_by = "deterministic_fallback"

        if active_candidates:
            def role_priority(c):
                if c.role == "external_primary":
                    return 0
                elif c.role == "primary_proposer":
                    return 1
                elif c.role == "secondary_proposer":
                    return 2
                return 3
            active_candidates = sorted(active_candidates, key=role_priority)

            selected_candidate = active_candidates[0]
            if selected_candidate.role == "external_primary":
                selected_by = "external_primary_policy"
            elif selected_candidate.role == "primary_proposer":
                selected_by = "candidate_policy"
            elif selected_candidate.role == "secondary_proposer":
                selected_by = "candidate_policy_fallback"
            ranking_trace.append(f"Selected {selected_candidate.role}: {selected_candidate.candidate_id}")
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
