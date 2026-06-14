"""PACT: Protocol for Actionable Compact Tuples — compact advisor records."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Optional, Any


@dataclass(frozen=True)
class PACTRecord:
    """Compact action-state record for 3B advisor output.
    
    Strict schema: no verifier verdicts, no delivery-critical overrides.
    """
    task_id: str = ""
    route_risk_tier: str = ""  # "low", "medium", "high"
    candidate_ids: List[str] = field(default_factory=list)
    recommended_candidate_id: Optional[str] = None
    selection_reason_codes: List[str] = field(default_factory=list)
    evidence_refs: List[str] = field(default_factory=list)
    skill_hints: List[str] = field(default_factory=list)
    memory_hints: List[str] = field(default_factory=list)
    abstain_reason: str = ""
    observation_only: bool = True
    advisor_version: str = "pact-v1"
    
    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "route_risk_tier": self.route_risk_tier,
            "candidate_ids": self.candidate_ids,
            "recommended_candidate_id": self.recommended_candidate_id,
            "selection_reason_codes": self.selection_reason_codes,
            "evidence_refs": self.evidence_refs,
            "skill_hints": self.skill_hints,
            "memory_hints": self.memory_hints,
            "abstain_reason": self.abstain_reason,
            "observation_only": self.observation_only,
            "advisor_version": self.advisor_version,
        }
    
    def token_estimate(self) -> int:
        """Rough token estimate for the record."""
        # JSON serialization + overhead
        return len(json.dumps(self.to_dict())) // 4 + 10


import json


def validate_pact_record(record: dict) -> List[str]:
    """Validate a PACT record. Returns list of errors (empty = valid)."""
    errors = []
    
    # Required fields
    for key in ["task_id", "route_risk_tier", "candidate_ids", "recommended_candidate_id"]:
        if key not in record:
            errors.append(f"Missing required field: {key}")
    
    # Risk tier validation
    valid_tiers = {"low", "medium", "high"}
    if record.get("route_risk_tier") not in valid_tiers:
        errors.append(f"Invalid route_risk_tier: {record.get('route_risk_tier')}")
    
    # Forbidden fields (governance authority)
    forbidden = {"verdict", "claimability", "delivery_override", "trust_score"}
    for field in forbidden:
        if field in record:
            errors.append(f"Forbidden field present: {field}")
    
    # observation_only must be True for low-risk
    if record.get("route_risk_tier") == "low" and not record.get("observation_only", True):
        errors.append("Low-risk must be observation_only=True")
    
    return errors


def pact_from_advisor_output(
    task_id: str,
    risk_tier: str,
    candidates: list,
    advisor_output: dict,
    skill_hints: List[str] = None,
    memory_hints: List[str] = None,
) -> PACTRecord:
    """Convert advisor output to PACT record."""
    candidate_ids = [c.candidate_id if hasattr(c, "candidate_id") else c.get("id", "") for c in candidates]
    
    return PACTRecord(
        task_id=task_id,
        route_risk_tier=risk_tier,
        candidate_ids=candidate_ids,
        recommended_candidate_id=advisor_output.get("selected_candidate_id"),
        selection_reason_codes=advisor_output.get("selection_reason_codes", []),
        evidence_refs=[],
        skill_hints=skill_hints or [],
        memory_hints=memory_hints or [],
        abstain_reason=advisor_output.get("abstain_reason", ""),
        observation_only=True,
    )
