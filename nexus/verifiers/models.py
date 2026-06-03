from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any

@dataclass(frozen=True)
class VerifierVerdict:
    """[NEXUS v26.3] 統一驗證裁決 DTO"""
    verifier_name: str
    candidate_id: str
    passed: bool
    score: float # 0.0 to 1.0
    evidence_refs: List[str] = field(default_factory=list)
    blocker_code: Optional[str] = None
    confidence_delta: float = 0.0 # 對最終決策的信心影響
