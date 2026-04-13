#!/usr/bin/env python3
import json
from dataclasses import dataclass, asdict
from typing import List, Optional

@dataclass
class VerificationCard:
    """🛡️ Nexus v23.13 Verification Card (Standard Gate)"""
    claim_state: str  # IDEA, VERIFIED, etc.
    evidence_count: int
    missing_evidence: List[str]
    sanitizer_coverage: bool # ASAN/TSAN
    repro_status: bool
    confidence: str # HIGH, MEDIUM, LOW
    
    def validate(self) -> bool:
        """判定卡片是否允許提交。"""
        if self.claim_state == "VERIFIED":
            if self.confidence != "HIGH" or self.evidence_count < 3 or not self.sanitizer_coverage:
                return False
        if self.claim_state == "CANDIDATE_PATCH" and self.evidence_count < 1:
            return False
        return True

    def render_markdown(self) -> str:
        status = "✅ PASS" if self.validate() else "❌ REJECTED"
        return f"""
### 🛡️ Nexus Verification Card
- **Status**: {status}
- **Claim State**: {self.claim_state}
- **Confidence**: {self.confidence}
- **Evidence Count**: {self.evidence_count}
- **Sanitizer Coverage**: {"✅" if self.sanitizer_coverage else "❌"}
- **Missing**: {", ".join(self.missing_evidence) if self.missing_evidence else "None"}
"""
