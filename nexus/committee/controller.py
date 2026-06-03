import os
from typing import List, Optional, Dict, Any
from nexus.committee.registry import CandidateRegistry
from nexus.committee.adapter import ProposerAdapter
from nexus.verifiers.registry import VerifierRegistry
from nexus.verifiers.contracts import VerifierVerdict
from nexus.selection.calibrator import ConfidenceCalibrator
from nexus.selection.decision_policy import DecisionPolicy
from nexus.committee.models import CommitteeReceipt

class CommitteeControllerV263:
    """
    🎮 [NEXUS v26.5] 微型化委員會控制器
    職責: 協調 Search -> Verifier -> Selection (Score -> Decision) 全管線。
    """
    def __init__(self, task_id: str):
        self.enabled = os.getenv("NEXUS_USE_COMMITTEE", "0") == "1"
        self.task_id = task_id
        self.registry = CandidateRegistry(task_id)
        self.adapter = ProposerAdapter()
        self.calibrator = ConfidenceCalibrator()
        self.decision_policy = DecisionPolicy()

    def process_proposals(self, raw_proposals: List[Dict[str, Any]]) -> CommitteeReceipt:
        if not self.enabled:
            p = raw_proposals[0]
            candidate = self.adapter.create_candidate(self.task_id, p['model'], p['attempt'], p['raw_label'], [])
            return CommitteeReceipt(self.task_id, 1, [candidate], [], candidate.candidate_id, 'feature_disabled_fallback')

        # 1. Ingress
        for p in raw_proposals:
            candidate = self.adapter.create_candidate(
                self.task_id, p["model"], p["attempt"], p["raw_label"], p.get("artifacts", [])
            )
            self.registry.register(candidate)
        
        candidates = self.registry.get_all()
        all_verdicts = []
        
        # 2. Verification (Plugin-based)
        for c in candidates:
            patch_content = c.artifact_refs[0] if c.artifact_refs else ''
            for v in VerifierRegistry.get_all_verifiers():
                all_verdicts.append(v.evaluate(c.candidate_id, patch_content))
            
        # 3. Selection (Two-layer Split)
        # Layer 1: Score & Calibrate
        calibrated_data = self.calibrator.calibrate(all_verdicts)
        
        # Layer 2: Decision
        selection_res = self.decision_policy.evaluate_and_decide(calibrated_data, 0.7)
        
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
