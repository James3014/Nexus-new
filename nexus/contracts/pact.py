from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import List, Optional, Dict, Any
from nexus.contracts.s2t_policy import S2TCandidate

@dataclass
class PACTRecord:
    action_type: str
    affected_scope: List[str]
    risk_level: str
    evidence_refs: List[str]
    next_step: str
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

def pact_from_advisor_output(
    task_id: str,
    risk_tier: str,
    candidates: List[S2TCandidate],
    result: Dict[str, Any],
    skill_hints: Optional[List[str]] = None,
    memory_hints: Optional[List[str]] = None,
) -> PACTRecord:
    selected_id = result.get("selected_candidate_id")
    abstain_reason = result.get("abstain_reason")

    # Find matching candidate
    matched_cand = None
    if selected_id and candidates:
        matched_cand = next((c for c in candidates if str(c.candidate_id) == str(selected_id)), None)

    if abstain_reason:
        action_type = "abstain"
        affected_scope = []
        evidence_refs = []
        next_step = f"fallback_rule_selector: {abstain_reason}"
    elif selected_id:
        action_type = "select_route"
        affected_scope = [str(selected_id)]
        evidence_refs = matched_cand.evidence_refs if matched_cand else []
        req_verifier = result.get("required_verifier") or "pytest"
        next_step = f"run_verifier: {req_verifier}"
    else:
        action_type = "bypass"
        affected_scope = []
        evidence_refs = []
        next_step = "fallback_rule_selector"

    # Compile metadata for observation
    metadata = {
        "task_id": task_id,
        "skill_hints": skill_hints or [],
        "memory_hints": memory_hints or [],
        "selection_reason_codes": result.get("selection_reason_codes", []),
    }
    if "_overhead_stats" in result:
        metadata["overhead_stats"] = result["_overhead_stats"]

    return PACTRecord(
        action_type=action_type,
        affected_scope=affected_scope,
        risk_level=risk_tier,
        evidence_refs=evidence_refs,
        next_step=next_step,
        metadata=metadata,
    )
