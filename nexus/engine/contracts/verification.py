from enum import Enum, auto
from dataclasses import dataclass, asdict
from typing import Dict, Any, Optional

class VerifierType(str, Enum):
    SYNTAX = "SYNTAX"
    CONTRACT = "CONTRACT"
    SEMANTIC = "SEMANTIC"
    REGRESSION = "REGRESSION"
    RISK = "RISK"
    REFACTOR_GUARD = "REFACTOR_GUARD"

class Verdict(str, Enum):
    PASS = "PASS"
    SOFT_ADVISORY = "SOFT_ADVISORY"
    HARD_REJECT = "HARD_REJECT"

@dataclass
class VerificationResult:
    """
    🛡️ VerificationResult: 驗證結果契約
    所有 Verifier 必須統一輸出此結構，確保跨模組溝通的強型別與明確性。
    """
    verifier_type: VerifierType
    verdict: Verdict
    reason: str
    constraint_for_next_round: str = ""
    minimal_counterexample: str = ""
    
    def is_passed(self) -> bool:
        """是否允許放行 (Pass 或 Soft Advisory 皆可)。"""
        return self.verdict in {Verdict.PASS, Verdict.SOFT_ADVISORY}
        
    def should_rollback(self) -> bool:
        """是否必須阻斷並回滾。"""
        return self.verdict == Verdict.HARD_REJECT

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["verifier_type"] = self.verifier_type.value
        data["verdict"] = self.verdict.value
        return data
