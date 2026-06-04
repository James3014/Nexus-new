from dataclasses import dataclass, field
from typing import List, Optional

@dataclass(frozen=True)
class EvidenceRef:
    """[NEXUS v26.4] 局部驗證證據引用"""
    source_file: str
    line_number: Optional[int] = None
    snippet: Optional[str] = None

@dataclass(frozen=True)
class FailureTag:
    """[NEXUS v26.4] 驗證失敗標籤"""
    code: str
    description: str

@dataclass(frozen=True)
class VerifierVerdict:
    """
    [NEXUS v26.4] 統一驗證裁決契約 (T5)
    所有的領域驗證器都必須遵守此輸出格式，讓 Controller 可以盲目消費。
    """
    verifier_name: str
    candidate_id: str
    passed: bool
    score: float  # -100.0 to 100.0
    evidence_refs: List[EvidenceRef] = field(default_factory=list)
    failure_tags: List[FailureTag] = field(default_factory=list)
    confidence: float = 1.0
