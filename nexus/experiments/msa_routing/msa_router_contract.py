"""
msa_router_contract.py
Defines the strictly-typed schemas for MSA routing.
"""
import uuid
from typing import List, Optional
try:
    from typing import Literal
except ImportError:
    from typing_extensions import Literal
from pydantic import BaseModel, Field, field_validator, ConfigDict

class MemoryCandidate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    id: str
    content: str
    type: Literal["code", "belief", "artifact", "rule"]
    score: float = 0.0
    version_id: str
    source_hash: str
    ttl: int = -1
    confidence_decay: float = 1.0

    @field_validator('score', 'confidence_decay')
    @classmethod
    def validate_range(cls, v):
        if not (0.0 <= v <= 1.0):
            raise ValueError("Must be between 0.0 and 1.0")
        return v

class RoutingResult(BaseModel):
    model_config = ConfigDict(extra='forbid')
    query_id: str
    candidates: List[MemoryCandidate] = Field(default_factory=list)
    score: float = 0.0
    selected: List[MemoryCandidate] = Field(default_factory=list)
    reject_reason: Optional[str] = None
    status: Literal["ANSWERED", "UNKNOWN", "CONFLICT"]

class MSARouter:
    def __init__(self, confidence_threshold: float = 0.75):
        self.confidence_threshold = confidence_threshold

    def route(self, query_id: str, retrieved_candidates: List[MemoryCandidate]) -> RoutingResult:
        if not retrieved_candidates:
            return RoutingResult(
                query_id=query_id,
                status="UNKNOWN",
                reject_reason="no_candidates_retrieved"
            )

        for c in retrieved_candidates:
            c.score = c.score * c.confidence_decay

        sorted_candidates = sorted(retrieved_candidates, key=lambda x: x.score, reverse=True)
        best_candidate = sorted_candidates[0]

        if best_candidate.score < self.confidence_threshold:
            return RoutingResult(
                query_id=query_id,
                candidates=sorted_candidates,
                score=best_candidate.score,
                status="UNKNOWN",
                reject_reason=f"best_score_{best_candidate.score}_below_threshold_{self.confidence_threshold}"
            )

        selected = [c for c in sorted_candidates if c.score >= self.confidence_threshold]

        return RoutingResult(
            query_id=query_id,
            candidates=sorted_candidates,
            score=best_candidate.score,
            selected=selected,
            status="ANSWERED"
        )
