from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from datetime import datetime

@dataclass(frozen=True)
class ProposalCandidate:
    """[NEXUS v26] 提案候選者 DTO"""
    candidate_id: str
    source_model: str
    attempt_id: int
    raw_label: str
    normalized_phase: str
    artifact_refs: List[str]
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

@dataclass(frozen=True)
class CriticVerdict:
    """[NEXUS v26] 驗證器裁決 DTO"""
    critic_name: str
    candidate_id: str
    passed: bool
    score: float
    evidence_ref: str
    blocker_code: Optional[str] = None

@dataclass(frozen=True)
class ComparatorVote:
    """[NEXUS v26] 排序器投票 DTO"""
    voter_name: str
    rank_list: List[str] # 候選者 ID 列表，依優序排列
    winner_id: Optional[str]
    confidence: float

@dataclass(frozen=True)
class CommitteeReceipt:
    """[NEXUS v26] 委員會決策收據"""
    task_id: str
    k: int
    candidates: List[ProposalCandidate]
    verdicts: List[CriticVerdict]
    winner_id: Optional[str]
    failure_bucket: Optional[str] = None # coverage/selection/verifier/integration
    wall_time_ms: float = 0.0
    total_cost: float = 0.0
