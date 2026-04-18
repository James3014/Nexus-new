from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional
import logging
import re
import json
from pathlib import Path
from nexus.core.state_contracts import NexusState

logger = logging.getLogger(__name__)

@dataclass
class ExecutionPlan:
    mode: str
    reason: str
    confidence: float
    skill_id: Optional[str] = None
    matched_policies: List[str] = field(default_factory=list)

class AutonomicRouter:
    """
    🧠 Nexus Autonomic Router (v4.12 Final Production Ready)
    核心技術：Stemming-aware Matching.
    """
    # 領域錨點
    ANCHORS = {'glass', 'determinis', 'api', 'idempotent', 'idempotency', 'auth', 'git', 'ansible', 'token', 'state', 'import', 'audit', 'depend', 'permiss', 'health', 'bug', 'fix', 'error', 'secur', 'leak', 'vault', 'skill', 'optimiz'}
    
    BILINGUAL_MAP = {
        '玻璃': 'glass', '確定': 'determinis', '修復': 'fix', '自動': 'auto',
        '權限': 'permiss', '依賴': 'depend', '健康': 'health', '狀態': 'state', 
        '導入': 'import', '安全': 'secur', '優化': 'optimiz', '令牌': 'token', '冪等': 'idempotent'
    }

    STOP_WORDS = { 'applying', 'effects', 'in', 'of', 'to', 'with', 'by', 'the', 'is', 'are', 'for', 'on' }

    def __init__(self, project_root: str = ".", memory_service=None, config: Optional[Dict] = None, mem_palace=None):
        self.project_root = Path(project_root).resolve()

    def _stem(self, word: str) -> str:
        """簡單詞幹化，取前 6 碼確保 security/secure, idempotent/idempotency 對位"""
        return word.lower()[:6]

    def route(self, task_desc: str, state: NexusState, forecast: Dict[str, Any], pre_routing: Optional[Dict] = None) -> ExecutionPlan:
        desc_lower = task_desc.lower()
        raw_words = set(re.findall(r"\w+", desc_lower))
        
        # 詞幹化處理
        task_stems = {self._stem(w) for w in raw_words}
        for zh, en_stem in self.BILINGUAL_MAP.items():
            if zh in desc_lower: task_stems.add(en_stem)
            
        matched_policies = []
        if self.project_root:
            p_path = self.project_root / "nexus/knowledge/policy_memory.jsonl"
            if p_path.exists():
                with open(p_path, "r") as f:
                    for line in f:
                        if not line.strip(): continue
                        try:
                            p = json.loads(line)
                            pool = set(re.findall(r"\w+", p.get("condition", ""))) | set(re.findall(r"\w+", p.get("rule_id", "")))
                            pool_stems = {self._stem(w) for w in pool if w.lower() not in self.STOP_WORDS}
                            
                            overlap = pool_stems & task_stems
                            if not overlap: continue
                            
                            ratio = len(overlap) / len(pool_stems)
                            has_anchor = any(s in overlap and s in self.ANCHORS for s in task_stems)
                            
                            if has_anchor or ratio >= 0.45:
                                matched_policies.append(p.get("rule_id"))
                        except: continue

        matched_policies = sorted(list(set(matched_policies)))
        mode = "research_first" if any(k in desc_lower for k in ["research", "研究"]) else "swarm" if len(matched_policies) > 12 else "standard"
        return ExecutionPlan(mode=mode, reason=f"Stem-Audit: {len(matched_policies)} matches.", confidence=1.0, matched_policies=matched_policies)
