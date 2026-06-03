import os
from typing import List, Optional, Dict, Any
from nexus.committee.registry import CandidateRegistry
from nexus.committee.adapter import ProposerAdapter
from nexus.verifiers.registry import VerifierRegistry
from nexus.committee.score_aggregator import ScoreAggregator
from nexus.committee.winner_policy import WinnerPolicy
from nexus.committee.models import CommitteeReceipt
from nexus.verifiers.models import VerifierVerdict

class CommitteeControllerV263:
    def __init__(self, task_id: str):
        self.enabled = os.getenv("NEXUS_USE_COMMITTEE", "0") == "1"
        self.task_id = task_id
        self.registry = CandidateRegistry(task_id)
        self.adapter = ProposerAdapter()
        self.verifiers = VerifierRegistry.get_all_verifiers()
        self.aggregator = ScoreAggregator()
        self.policy = WinnerPolicy()

    def process_proposals(self, raw_proposals: List[Dict[str, Any]]) -> CommitteeReceipt:
        if not self.enabled:
            # 若未啟用，則降級為 Single-run 模擬
            p = raw_proposals[0]
            candidate = self.adapter.create_candidate(self.task_id, p['model'], p['attempt'], p['raw_label'], [])
            return CommitteeReceipt(self.task_id, 1, [candidate], [], candidate.candidate_id, 'feature_disabled_fallback')

        for p in raw_proposals:
            candidate = self.adapter.create_candidate(
                self.task_id, p['model'], p['attempt'], p['raw_label'], p.get('artifacts', [])
            )
            self.registry.register(candidate)
        
        candidates = self.registry.get_all()
        all_verdicts = []
        
        for c in candidates:
            patch_content = c.artifact_refs[0] if c.artifact_refs else ''
            for v in self.verifiers:
                all_verdicts.append(v.evaluate(c.candidate_id, patch_content))
            
        scores = self.aggregator.aggregate(all_verdicts)
        winner_id, final_confidence = self.policy.determine_winner(scores, 0.7)
        
        failure_bucket = None
        if not winner_id:
            failure_bucket = 'selection_abstain_failure' if candidates else 'coverage_failure'
            
        return CommitteeReceipt(
            task_id=self.task_id,
            k=len(candidates),
            candidates=candidates,
            verdicts=all_verdicts,
            winner_id=winner_id,
            failure_bucket=failure_bucket,
            total_cost=len(candidates) * 0.05
        )
