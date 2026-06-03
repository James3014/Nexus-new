import os
from typing import List, Optional, Dict, Any
from nexus.committee.registry import CandidateRegistry
from nexus.committee.adapter import ProposerAdapter
from nexus.verifiers.registry import VerifierRegistry
from nexus.verifiers.packs.registry import PackRegistry
from nexus.verifiers.contracts import VerifierVerdict
from nexus.selection.calibrator import ConfidenceCalibrator
from nexus.selection.decision_policy import DecisionPolicy
from nexus.feedback.router import FeedbackRouter
from nexus.retry_policy.policy import RetryPolicy
from nexus.committee.models import CommitteeReceipt

class CommitteeControllerV263:
    """
    🎮 [NEXUS v26.7] 資料流精修版控制器
    職責: 透過明確的 Bounded Contexts 驅動解題管線，消除特殊分支。
    """
    def __init__(self, task_id: str, domains: List[str] = None):
        self.enabled = os.getenv("NEXUS_USE_COMMITTEE", "0") == "1"
        self.packs_enabled = os.getenv("NEXUS_USE_PACKS", "0") == "1"
        self.task_id = task_id
        self.domains = domains or ["astropy"]
        
        self.registry = CandidateRegistry(task_id)
        self.adapter = ProposerAdapter()
        self.calibrator = ConfidenceCalibrator()
        self.decision_policy = DecisionPolicy()

    def process_proposals(self, raw_proposals: List[Dict[str, Any]]) -> CommitteeReceipt:
        if not self.enabled:
            return self._fallback_receipt(raw_proposals)

        # 1. Ingress
        for p in raw_proposals:
            candidate = self.adapter.create_candidate(self.task_id, p["model"], p["attempt"], p["raw_label"], p.get("artifacts", []))
            self.registry.register(candidate)
        
        candidates = self.registry.get_all()
        all_verdicts = []
        
        # 2. Verification
        for c in candidates:
            patch = c.artifact_refs[0] if c.artifact_refs else ''
            # Pack 驗證
            if self.packs_enabled:
                for pack in PackRegistry.get_enabled_packs(self.domains):
                    all_verdicts.extend(pack.evaluate_all(c.candidate_id, patch))
            # 基礎驗證 (Fallback if no pack)
            if not all_verdicts:
                for v in VerifierRegistry.get_all_verifiers():
                    all_verdicts.append(v.evaluate(c.candidate_id, patch))
            
        # 3. Calibration & Decision
        calibrated_data = self.calibrator.calibrate(all_verdicts, 0.7)
        selection_res = self.decision_policy.evaluate_and_decide(calibrated_data, calibrated_data["calibrated_confidence"])
        
        # 4. Feedback & Retry (Decoupled Data-Flow)
        if selection_res.abstained:
            # Stage 1: Map (Mapper)
            patterns = FeedbackRouter.map_verdicts(all_verdicts)
            # Stage 2: Decide (Decider)
            retry_action = RetryPolicy.decide(patterns, len(candidates))
            
            if retry_action.action != "ABSTAIN":
                print(f"🔄 [Feedback] Action: {retry_action.action} | Patterns: {[p.pattern_code for p in patterns]}")
        
        return CommitteeReceipt(
            task_id=self.task_id,
            k=len(candidates),
            candidates=candidates,
            verdicts=all_verdicts,
            winner_id=selection_res.winner_id,
            failure_bucket=selection_res.failure_bucket,
            confidence=selection_res.confidence,
            verifier_gap=selection_res.gap,
            total_cost=len(candidates) * 0.05
        )

    def _fallback_receipt(self, raw_proposals):
        p = raw_proposals[0]
        candidate = self.adapter.create_candidate(self.task_id, p['model'], p['attempt'], p['raw_label'], [])
        return CommitteeReceipt(self.task_id, 1, [candidate], [], candidate.candidate_id, 'feature_disabled_fallback')
