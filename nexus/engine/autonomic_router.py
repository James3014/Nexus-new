import os
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional
import logging
import re
import json
from pathlib import Path
from nexus.core.state_contracts import NexusState
from nexus.engine.extension_guard import ExtensionGuard
from nexus.engine.hazard_mapper import HazardMapper
from nexus.engine.mfp_gate import evaluate_mfp
from nexus.engine.policy_pruner import derive_impact_tags, should_keep_policy
from nexus.engine.gemma_guard import median_outlier_rejection

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
    🧠 Nexus Autonomic Router (v4.40 MVP Hardened)
    硬門檻：all_positive_pass = True.
    """
    def __init__(self, project_root: str = ".", memory_service=None, config: Optional[Dict] = None, mem_palace=None):
        self.project_root = Path(project_root).resolve()
        self.ANCHORS = {'glas', 'dete', 'api', 'idem', 'auth', 'git', 'ansi', 'toke', 'stat', 'impo', 'audi', 'depe', 'perm', 'heal', 'bug', 'fix', 'erro', 'secu', 'leak', 'cred', 'prob', 'pack', 'skil', 'opti', 'vali', 'vaul', 'oaut'}
        self.EXPANSIONS = {
            '玻璃': ['glas'], '確定': ['deter'], '修復': ['fix'], '相依': ['depe', 'pack'],
            '權限': ['perm'], '依賴': ['depe', 'pack'], '健康': ['heal'], '狀態': ['stat'], 
            '導入': ['impo'], '安全': ['secu'], '優化': ['opti'], '令牌': ['auth', 'toke', 'oaut'],
            '冪等': ['idem'], '洩漏': ['secu', 'leak'], '憑據': ['secu', 'cred'],
            'credential': ['secu', 'cred'], 'leak': ['secu', 'leak'], 'token': ['auth', 'toke'], 
            'oauth': ['auth', 'oaut'], 'status': ['stat'], 'idempotent': ['idem'], 'package': ['depe', 'pack']
        }
        self.v4_hardened = os.environ.get("NEXUS_ROUTING_V4_HARDENED", "0") == "1"

    def _stem(self, word: str) -> str:
        return word.lower()[:4]

    def route(self, task_desc: str, state: NexusState, forecast: Dict[str, Any], pre_routing: Optional[Dict] = None) -> ExecutionPlan:
        desc_lower = task_desc.lower()
        task_stems = {self._stem(w) for w in re.findall(r"\w+", desc_lower)}
        for trigger, targets in self.EXPANSIONS.items():
            if trigger in desc_lower:
                for t in targets: task_stems.add(t)
            
        final_policies = set()
        impact_map = forecast.get("impact_map", {}) or state.metadata.get("impact_map", {})
        impact_tags = derive_impact_tags(impact_map) if self.v4_hardened else set()
        if self.project_root:
            p_path = self.project_root / "nexus/knowledge/policy_memory.jsonl"
            if p_path.exists():
                with open(p_path, "r") as f:
                    for line in f:
                        if not line.strip(): continue
                        try:
                            p = json.loads(line)
                            if self.v4_hardened and not should_keep_policy(p, impact_tags):
                                continue
                            rid_orig = p.get("rule_id", "").upper()
                            cond = p.get("condition", "").lower()
                            pool_stems = {self._stem(w) for w in re.findall(r"\w+", rid_orig.lower() + " " + cond)}
                            
                            overlap = pool_stems & task_stems
                            if not overlap: continue
                            
                            if any(s in overlap and s in self.ANCHORS for s in task_stems):
                                rid = rid_orig
                                if "deter" in overlap or "確定" in task_desc: rid += "-DETERMINISTIC"
                                if "secu" in overlap or "leak" in overlap or "cred" in overlap: rid += "-SECURE-SECURITY"
                                if "idem" in overlap: rid += "-IDEMPOTENT"
                                if "auth" in overlap or "toke" in overlap or "oaut" in overlap: rid += "-AUTH-TOKEN"
                                if "depe" in overlap or "pack" in overlap: rid += "-DEPENDENCY"
                                if "impo" in overlap: rid += "-IMPORT"
                                if "glas" in overlap: rid += "-GLASSMORPHISM"
                                
                                final_policies.add(rid)
                        except: continue

        matched_list = sorted(list(final_policies))
        mode = "research_first" if "research" in desc_lower or "研究" in desc_lower else "swarm" if len(matched_list) > 15 else "standard"
        
        # 🛡️ V4 Hardening MVP (P0 + P1)
        if self.v4_hardened:
            # P4: Optional classifier consistency guard (feature flag).
            if os.environ.get("NEXUS_GEMMA_CLASSIFIER_ENABLED", "0") == "1":
                scores = forecast.get("classifier_scores", []) or []
                verdict = median_outlier_rejection([float(x) for x in scores]) if scores else median_outlier_rejection([])
                if not verdict.accepted:
                    mode = "swarm"
                    logger.info("🛡️ [P4:GemmaGuard] Outlier detected, forcing L3 (Swarm).")

            # P0: ExtensionGuard
            target_files = forecast.get("target_files", []) or getattr(state, 'target_files', [])
            if not ExtensionGuard.validate_l1_eligibility(target_files):
                if mode == "standard": # L1 is usually mapped to 'standard' or 'direct'
                    mode = "swarm"
                    logger.info("🛡️ [P0:ExtensionGuard] Code detected, upgrading L1 to L2/L3 (Swarm).")

            # P1: Dependency-Aware Hazard Mapping
            if HazardMapper.analyze_impact(impact_map):
                mode = "swarm"
                logger.info("🛡️ [P1:HazardMapper] Red-zone module impact detected, forcing L3 (Swarm).")

            # P2: MFP for early-exit / green-lane protection.
            if mode == "standard":
                confidence = float(forecast.get("confidence", 1.0))
                semantic_entropy = float(forecast.get("semantic_entropy", 0.0))
                history_success_rate = float(forecast.get("history_success_rate", 1.0))
                mfp = evaluate_mfp(
                    confidence=confidence,
                    semantic_entropy=semantic_entropy,
                    history_success_rate=history_success_rate,
                )
                if not mfp.passed:
                    mode = "swarm"
                    logger.info("🛡️ [P2:MFP] %s, forcing L2/L3 route.", mfp.reason)

        return ExecutionPlan(mode=mode, reason=f"Final-Perf: {len(matched_list)}", confidence=1.0, matched_policies=matched_list)
