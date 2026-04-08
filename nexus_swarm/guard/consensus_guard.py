# 🛡️ Nexus Consensus Guard Orchestrator
# [ARCH-EVO: v23 WISDOM EDITION GUARD]

from pathlib import Path
from typing import Dict, Any, List
from .validator import DeterministicValidator
from .approver import ConsensusApprover

class ConsensusGuard:
    def __init__(self, repo_root: Path = Path(str(__import__("pathlib").Path(__file__).resolve().parents[2]))):
        self.validator = DeterministicValidator(repo_root)
        self.approver = ConsensusApprover()
        from nexus_swarm.wisdom.feedback_api import FeedbackAPI
        self.feedback_api = FeedbackAPI()

    def submit_feedback(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """🛡️ Proxy feedback to Wisdom API (P8.3 Integration)"""
        return self.feedback_api.submit_feedback(event)

    def validate_scenario(self, task_id: str, executor_result: Dict[str, Any], risk_score_prior: float = 0.4) -> Dict[str, Any]:
        """
        🛡️ Full Consensus Guard Flow:
        1. Extract patterns from executor_result
        2. Run Deterministic Validator
        3. Merge risk scores
        4. Apply Approver decision
        """
        # 1. Validation
        validation_res = self.validator.validate_action(executor_result)
        
        # 2. Risk Calculation
        final_risk_score = risk_score_prior + validation_res["risk_score_penalty"]
        # Limit to 1.0
        final_risk_score = min(1.0, final_risk_score)
        
        # 3. Approval Outcome
        outcome_res = self.approver.determine_outcome(
            executor_result, 
            validation_res["checks"], 
            final_risk_score
        )
        
        return {
            "task_id": task_id,
            "validation": validation_res,
            "outcome": outcome_res,
            "consensus_pass": outcome_res["outcome"] != "safe_fallback"
        }

if __name__ == "__main__":
    # Test Orchestration
    guard = ConsensusGuard()
    mock_res = {"target_file": "scripts/engine/nexus_cli_NONEXISTENT.py"}
    res = guard.validate_scenario("T-100", mock_res, risk_score_prior=0.3)
    import json
    print(json.dumps(res, indent=2))
