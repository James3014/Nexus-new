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
    🧠 Nexus Autonomic Router (v4.16 Target-Fix Final)
    核心技術：4碼詞幹壓縮 (4-char Stemming).
    """
    def __init__(self, project_root: str = ".", memory_service=None, config: Optional[Dict] = None, mem_palace=None):
        self.project_root = Path(project_root).resolve()
        
        # 🧪 使用 4 碼詞幹錨點
        raw_anchors = {
            'glassmorphism', 'deterministic', 'api', 'idempotent', 'idempotency', 
            'auth', 'git', 'ansible', 'token', 'state', 'import', 'audit', 
            'dependency', 'permission', 'health', 'bug', 'fix', 'error', 'secure',
            'skill', 'optimize', 'validation', 'vault', 'circular', 'security', 'leak', 
            'credential', 'probe', 'package'
        }
        raw_map = {
            '玻璃': 'glass', '確定': 'deter', '修復': 'fix', '自動': 'auto',
            '權限': 'permi', '依賴': 'depen', '健康': 'healt', '狀態': 'state', 
            '導入': 'impor', '安全': 'secur', '優化': 'optim', '令牌': 'token', 
            '冪等': 'idemp', '洩漏': 'leak', '憑據': 'crede'
        }

        self.ANCHORS = {self._stem(w) for w in raw_anchors}
        self.BILINGUAL_MAP = {zh: self._stem(en) for zh, en in raw_map.items()}
        self.STOP_WORDS = {self._stem(w) for w in ['applying', 'effects', 'in', 'of', 'to', 'with', 'by', 'the', 'is', 'are', 'for', 'on', 'execution', 'high', 'pattern', 'results']}

    def _stem(self, word: str) -> str:
        """採用 4 碼詞幹，極大化跨語系重合機率"""
        return word.lower()[:4]

    def route(self, task_desc: str, state: NexusState, forecast: Dict[str, Any], pre_routing: Optional[Dict] = None) -> ExecutionPlan:
        desc_lower = task_desc.lower()
        
        task_stems = set()
        for w in re.findall(r"\w+", desc_lower): task_stems.add(self._stem(w))
        for zh, en_stem in self.BILINGUAL_MAP.items():
            if zh in desc_lower: task_stems.add(en_stem)
            
        matched_policies = set()
        if self.project_root:
            p_path = self.project_root / "nexus/knowledge/policy_memory.jsonl"
            if p_path.exists():
                with open(p_path, "r") as f:
                    for line in f:
                        if not line.strip(): continue
                        try:
                            p = json.loads(line)
                            pool = p.get("rule_id", "").lower() + " " + p.get("condition", "").lower()
                            pool_stems = {self._stem(w) for w in re.findall(r"\w+", pool)}
                            
                            overlap = pool_stems & task_stems
                            if not overlap: continue
                            
                            # 🛡️ 只要命中了 4 碼錨點詞幹，即導通
                            if any(s in overlap and s in self.ANCHORS for s in task_stems):
                                matched_policies.add(p.get("rule_id"))
                        except: continue

        final_policies = sorted(list(matched_policies))
        mode = "research_first" if "research" in desc_lower or "研究" in desc_lower else "swarm" if len(final_policies) > 15 else "standard"
        return ExecutionPlan(mode=mode, reason=f"H-v4: {len(final_policies)} hits.", confidence=1.0, matched_policies=final_policies)
