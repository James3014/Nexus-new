# 🛡️ Nexus Consensus Approver
# [ARCH-EVO: v23 WISDOM EDITION GUARD]

from typing import Dict, Any, List

class ConsensusApprover:
    def __init__(self, high_risk_threshold: float = 0.7):
        self.high_risk_threshold = high_risk_threshold

    def determine_outcome(self, executor_result: Dict[str, Any], validation_results: List[Dict[str, Any]], risk_score: float) -> Dict[str, Any]:
        """
        🛡️ Final Gatekeeper decision:
        - risk_score < 0.3: Approve
        - 0.3 <= risk_score < 0.7: Approve with Warning (Cautious)
        - risk_score >= 0.7: SAFE_FALLBACK (Manual Review Required)
        """
        # Overriding if validation failed
        validation_failed = any(not check["passed"] for check in validation_results)
        
        outcome = "approved"
        if validation_failed or risk_score >= self.high_risk_threshold:
            outcome = "safe_fallback"
        elif risk_score >= 0.3:
            outcome = "cautious_approve"
            
        return {
            "outcome": outcome,
            "risk_score": risk_score,
            "reason": "validation_failed" if validation_failed else "high_risk_assessment" if risk_score >= self.high_risk_threshold else "nominal",
            "suggested_action": "manual_review" if outcome == "safe_fallback" else "execute"
        }
