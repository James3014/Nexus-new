from typing import List, Dict, Optional
from nexus.committee.models import ProposalCandidate

class CandidateRegistry:
    """
    🗂️ Task T2: 候選註冊器
    職責: 保證每個候選提案具備唯一 ID 並可追溯來源。
    """
    def __init__(self, task_id: str):
        self.task_id = task_id
        self._pool: Dict[str, ProposalCandidate] = {}

    def register(self, candidate: ProposalCandidate):
        if candidate.candidate_id in self._pool:
            raise ValueError(f"Duplicate candidate ID: {candidate.candidate_id}")
        
        # 驗證必填欄位 (物理約束)
        if not candidate.source_model or not candidate.raw_label:
            raise ValueError("Incomplete candidate metadata")
            
        self._pool[candidate.candidate_id] = candidate
        return True

    def get_all(self) -> List[ProposalCandidate]:
        return list(self._pool.values())

    def get_by_id(self, cid: str) -> Optional[ProposalCandidate]:
        return self._pool.get(cid)

    def size(self) -> int:
        return len(self._pool)
