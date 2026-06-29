import os
from dataclasses import dataclass
from nexus.services.local_heal.candidate_envelope import CandidateEnvelope


@dataclass(frozen=True)
class CandidateDecisionResponse:
    selected_candidate_id: str
    selected_candidate_patch: str
    ranking_trace: list[str]
    selected_by: str
    decision_evidence_refs: tuple[str, ...]
    final_authority: str = "NexusVerifier"


class CandidateDecisionAdapter:
    @staticmethod
    def select_candidate(candidates: list[CandidateEnvelope]) -> CandidateDecisionResponse:
        # Validate that all active candidates have evidence_refs
        for c in candidates:
            if not c.evidence_refs:
                raise ValueError(f"Candidate {c.candidate_id} is missing evidence_refs")

        # Filter out abstained/blocked candidates
        active_candidates = [
            c for c in candidates 
            if not c.abstained and not any("forbidden" in flag or "blocked" in flag for flag in c.risk_flags)
        ]
        
        ranking_trace = []
        
        # 1. DDTree Pruning Layer
        enable_ddtree = os.environ.get("NEXUS_ENABLE_DDTREE") == "1"
        if enable_ddtree:
            pruned = []
            for c in active_candidates:
                # Never prune the only candidate or any candidate marked with verifier pass
                is_passing = "verifier_pass" in c.risk_flags
                if "invalid_dependency" in c.risk_flags and not is_passing:
                    ranking_trace.append(f"DDTree pruned {c.candidate_id} due to invalid dependency")
                else:
                    pruned.append(c)
            active_candidates = pruned

        # 2. Autoreason Ranking Layer
        enable_autoreason = os.environ.get("NEXUS_ENABLE_AUTOREASON") == "1"
        if enable_autoreason:
            def get_score(c):
                if c.role == "external_primary":
                    return 20
                elif c.role == "primary_proposer":
                    return 10
                elif c.role == "secondary_proposer":
                    return 5
                return 1
            active_candidates = sorted(active_candidates, key=get_score, reverse=True)
            ranking_trace.append("Autoreason ranked candidates by score")

        selected_candidate = None
        selected_by = "deterministic_fallback"
        
        # 3. Decision Logic
        if active_candidates:
            if not enable_autoreason:
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
                ranking_trace.append(f"Selected external_primary: {selected_candidate.candidate_id}")
            elif selected_candidate.role == "primary_proposer":
                selected_by = "candidate_policy"
                ranking_trace.append(f"Selected primary_proposer: {selected_candidate.candidate_id}")
            elif selected_candidate.role == "secondary_proposer":
                selected_by = "candidate_policy_fallback"
                ranking_trace.append(f"Selected secondary_proposer: {selected_candidate.candidate_id}")
            else:
                ranking_trace.append(f"Selected fallback candidate: {selected_candidate.candidate_id}")
        else:
            ranking_trace.append("No active candidates available")
                
        if selected_candidate:
            return CandidateDecisionResponse(
                selected_candidate_id=selected_candidate.candidate_id,
                selected_candidate_patch=selected_candidate.candidate_patch,
                ranking_trace=ranking_trace,
                selected_by=selected_by,
                decision_evidence_refs=selected_candidate.evidence_refs,
            )
        else:
            return CandidateDecisionResponse(
                selected_candidate_id="",
                selected_candidate_patch="",
                ranking_trace=ranking_trace,
                selected_by="none_available",
                decision_evidence_refs=(),
            )
