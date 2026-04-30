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
    vector_similarity: float = 0.0
    claim_confidence: float = 0.0
    version_id: str
    source_hash: str
    ttl: int = -1
    confidence_decay: float = 1.0
    retrieval_source: Literal["lancedb", "fallback", "unknown"] = "unknown"

    @field_validator('score', 'vector_similarity', 'claim_confidence', 'confidence_decay')
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
        self.sot_weight = {
            "code": 1.0,
            "rule": 0.95,
            "artifact": 0.9,
            "belief": 0.8,
        }

    def _hybrid_score(self, candidate: MemoryCandidate) -> float:
        if candidate.retrieval_source != "lancedb":
            return min(candidate.score, self.confidence_threshold - 0.01)
        evidence_weight = self.sot_weight.get(candidate.type, 0.75)
        semantic_score = candidate.vector_similarity or candidate.score
        score = semantic_score * candidate.claim_confidence * candidate.confidence_decay * evidence_weight
        return max(0.0, min(1.0, score))

    def route(self, query_id: str, retrieved_candidates: List[MemoryCandidate], query_type: str = "default") -> RoutingResult:
        if not retrieved_candidates:
            return RoutingResult(
                query_id=query_id,
                status="UNKNOWN",
                reject_reason="no_candidates_retrieved"
            )

        for candidate in retrieved_candidates:
            candidate.score = self._hybrid_score(candidate)
        sorted_candidates = sorted(retrieved_candidates, key=lambda c: c.score, reverse=True)
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
