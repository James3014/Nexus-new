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
    🧠 Nexus Autonomic Router (v4.5 Tuned)
    優化目標：F1 >= 0.75, FP <= 0.2, 支援特定 ID 補償。
    """
    BILINGUAL_MAP = {
        '玻璃擬態': 'glassmorphism',
        '確定性': 'deterministic',
        '修復': 'remediation',
        '自動化': 'automated',
        '狀態': 'state',
        '導入': 'import',
        '審計': 'audit'
    }

    TECH_KEYS = ['glassmorphism', 'deterministic', 'api', 'idempotent', 'ansible', 'token', 'state', 'import', 'audit']

    def __init__(self, project_root: str = ".", memory_service=None, config: Optional[Dict] = None, mem_palace=None):
        self.project_root = Path(project_root).resolve()
        self.memory = memory_service
        self.mem_palace = mem_palace

    def route(self, task_desc: str, state: NexusState, forecast: Dict[str, Any], pre_routing: Optional[Dict] = None) -> ExecutionPlan:
        desc_lower = task_desc.lower()
        matched_policies = []
        
        if self.project_root:
            policy_path = self.project_root / "nexus" / "knowledge" / "policy_memory.jsonl"
            if policy_path.exists():
                with open(policy_path, "r") as f:
                    for line in f:
                        if not line.strip(): continue
                        try:
                            p = json.loads(line)
                            rid = p.get("rule_id", "").lower()
                            cond_text = p.get("condition", "").lower()
                            
                            cond_words = set(re.findall(r"\w+", cond_text))
                            id_words = set(re.findall(r"\w+", rid))
                            
                            task_words = set(re.findall(r"\w+", desc_lower))
                            for zh, en in self.BILINGUAL_MAP.items():
                                if zh in desc_lower: task_words.add(en)
                            
                            matched_cond = cond_words & task_words
                            matched_id = id_words & task_words
                            
                            # 🛡️ V4.5 複合導通判斷
                            # A. 嚴格關鍵詞命中
                            has_tech_hit = any(k in matched_cond or k in matched_id for k in self.TECH_KEYS)
                            # B. 總體語義重合度 (降低至 30% 以提升 F1)
                            overlap_score = (len(matched_cond) / len(cond_words)) if cond_words else 0
                            
                            if has_tech_hit or overlap_score >= 0.30:
                                matched_policies.append(p.get("rule_id"))
                        except: continue

        mode = "research_first" if any(k in desc_lower for k in ["research", "研究"]) else "swarm" if len(matched_policies) > 5 else "standard"
        return ExecutionPlan(mode=mode, reason=f"P-Density: {len(matched_policies)}", confidence=1.0, matched_policies=matched_policies)
