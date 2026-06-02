import os
from typing import List, Optional, Dict, Any
from nexus.committee.registry import CandidateRegistry
from nexus.committee.adapter import ProposerAdapter
from nexus.committee.critics import SyntaxCritic, ContractCritic
from nexus.committee.comparator import BordaComparator
from nexus.committee.models import CommitteeReceipt, CriticVerdict

class CommitteeController:
    """
    🎮 Task T10: Committee Controller
    職責: 協調 Proposer -> Critic -> Comparator -> Receipt 全流程。
    """
    def __init__(self, task_id: str):
        self.enabled = os.getenv("NEXUS_USE_COMMITTEE", "0") == "1"
        self.task_id = task_id
        self.registry = CandidateRegistry(task_id)
        self.adapter = ProposerAdapter()
        self.critics = [SyntaxCritic(), ContractCritic()]
        self.comparator = BordaComparator()

    def process_proposals(self, raw_proposals: List[Dict[str, Any]]) -> CommitteeReceipt:
        if not self.enabled:
            # 若未啟用，則降級為 Single-run 模擬 (取第一個)
            print(f"⚠️ [Committee] Feature flag disabled. Falling back to Single-run.")
            p = raw_proposals[0]
            candidate = self.adapter.create_candidate(
                self.task_id, p["model"], p["attempt"], p["raw_label"], p.get("artifacts", [])
            )
            return CommitteeReceipt(
                task_id=self.task_id, 
                k=1, 
                candidates=[candidate], 
                verdicts=[], 
                winner_id=candidate.candidate_id, 
                failure_bucket="feature_disabled_fallback"
            )

        # 1. 註冊候選者
        for p in raw_proposals:
            candidate = self.adapter.create_candidate(
                self.task_id, p["model"], p["attempt"], p["raw_label"], p.get("artifacts", [])
            )
            self.registry.register(candidate)
        
        candidates = self.registry.get_all()
        all_verdicts = []
        
        # 2. 執行驗證管線
        for c in candidates:
            # 這裡模擬對 content/payload 的驗證
            # 在真實系統中，這些資料會從 artifact_refs 載入
            all_verdicts.append(self.critics[0].evaluate(c.candidate_id, "pass # mock code"))
            all_verdicts.append(self.critics[1].evaluate(c.candidate_id, {"root_cause": "x", "target_modules": []}))
            
        # 3. 排序與選優
        winner_id = self.comparator.select_winner(candidates, all_verdicts)
        
        # 4. 判定失敗桶
        failure_bucket = None
        if not winner_id:
            failure_bucket = "selection_failure" if candidates else "coverage_failure"
            
        return CommitteeReceipt(
            task_id=self.task_id,
            k=len(candidates),
            candidates=candidates,
            verdicts=all_verdicts,
            winner_id=winner_id,
            failure_bucket=failure_bucket
        )
