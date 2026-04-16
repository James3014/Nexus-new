#!/usr/bin/env python3
"""
🧠 Nexus L3 Project Planner & Strategic Router (Campaign-Architect & Guard-Reviewer)
負責將 P 階段意圖轉化為 D/R 階段的全生命週期執行策略，並整合五位一體靈魂支柱。
"""

import os
import json
import logging
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field
from pathlib import Path

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("nexus.planner")

@dataclass
class SwarmAllocation:
    scout: bool = False
    consensus: bool = False
    gladiators: int = 1
    audit: bool = True
    roles: List[str] = field(default_factory=lambda: ["coder", "tester"])

@dataclass
class CampaignStrategy:
    flow_type: str  # baseline, hyper_sprint, nightshift, skill_only
    swarm_config: SwarmAllocation = field(default_factory=SwarmAllocation)
    required_skills: List[str] = field(default_factory=list)
    risk_level: str = "LOW"
    beliefs_to_validate: List[str] = field(default_factory=list)
    explanation: str = ""

class ProjectPlanner:
    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.memory_path = project_root / ".nexus" / "memory"
        self.beliefs_path = project_root / ".nexusknowledge" / "beliefs.jsonl"
        self.max_consensus_loops = 3

    def build_campaign(self, intent_bundle: Dict[str, Any]) -> CampaignStrategy:
        """
        [D] Design Phase: 戰略路由核心邏輯。
        """
        task = intent_bundle.get("task", "").lower()
        dimensions = intent_bundle.get("dimensions", {})
        
        # 1. 呼叫 Campaign-Architect 生成初步提案
        proposal = self._architect_propose(task, dimensions)
        
        # 2. 呼叫 Guard-Reviewer 進行衝突與倫理審查 (Consensus Loop)
        final_strategy = self._consensus_check(proposal, intent_bundle)
        
        return final_strategy

    def _architect_propose(self, task: str, dimensions: Dict[str, Any]) -> CampaignStrategy:
        """
        [Architect] 提出戰術分配。
        """
        # 強化風險關鍵字與維度判斷
        high_risk_keywords = ["race condition", "deadlock", "auth", "security", "refactor", "migration"]
        is_high_risk = any(kw in task for kw in high_risk_keywords)
        
        # 偵測維度模糊性 (eXtract 必要性)
        is_unknown = dimensions.get("logic_scope") == "[待定]" or not dimensions.get("affected_files")
        
        if is_high_risk or is_unknown:
            # 優先路由至更穩健的引擎
            flow = "nightshift" if "night" in task else "hyper_sprint"
            risk = "HIGH"
            swarm = SwarmAllocation(
                scout=is_unknown, 
                consensus=True, 
                gladiators=3, 
                roles=["scout", "architect", "coder", "tester", "reviewer"]
            )
            explanation = f"High complexity detected (keywords: {[kw for kw in high_risk_keywords if kw in task]}). Escalating to {flow}."
        else:
            flow = "baseline"
            risk = "LOW"
            swarm = SwarmAllocation(gladiators=1)
            explanation = "Task identified as standard maintenance. Routing to baseline."

        # 技能提取 (Skill Routing)
        skills = self._map_skills(task, dimensions)

        return CampaignStrategy(
            flow_type=flow,
            swarm_config=swarm,
            required_skills=skills,
            risk_level=risk,
            explanation=explanation
        )


    def _consensus_check(self, strategy: CampaignStrategy, intent: Dict[str, Any]) -> CampaignStrategy:
        """
        [Reviewer] 模擬門下省封駁邏輯 (Consensus Gate)。
        """
        # TODO: 這裡未來將對接 MemPalace 與實體 Reviewer Agent
        # 目前實作硬性邊界守衛
        if strategy.risk_level == "HIGH" and not strategy.swarm_config.consensus:
            logger.warning("Guard-Reviewer: VETO - High risk task must have consensus swarm.")
            strategy.swarm_config.consensus = True
            strategy.explanation += " [REVIED BY GUARD: Forced Consensus]"
            
        return strategy

    def _map_skills(self, task: str, dimensions: Dict[str, Any]) -> List[str]:
        """
        🚀 Nexus 封裝技能映射 (Encapsulated Skill Mapping)
        僅掃描專案內部技能目錄，確保系統自治。
        """
        found = []
        # 僅限 Nexus 專案內部路徑
        internal_skills_roots = [
            self.project_root / "skills",
            self.project_root / "nexus" / "skills",
            self.project_root / "nexus" / "research" / "skills"
        ]
        
        all_available_skills = []
        for root in internal_skills_roots:
            if root.exists():
                all_available_skills.extend([d.name for d in root.iterdir() if d.is_dir()])
                # 同時檢查單個 json 設定檔（如 war-armor）
                all_available_skills.extend([f.stem for f in root.glob("*.json")])

        if not all_available_skills:
            return []

        # 1. Nexus 戰甲技能匹配 (Nexus Armor Priority)
        for skill_id in all_available_skills:
            if skill_id in task.lower() or any(p in task.lower() for p in skill_id.split("-")):
                found.append(skill_id)
        
        # 2. 核心動作映射 (Core Action Mapping)
        hard_mapping = {
            "scout": "scout",
            "idea": "idea",
            "fix": "baseline",
            "experiment": "experiment",
            "graph": "graphify",
            "analyze": "analysis",
            "armor": "war-armor"
        }
        for kw, skill in hard_mapping.items():
            if kw in task.lower() and any(skill in s for s in all_available_skills):
                found.append(skill)
                
        return list(set(found))[:5]



if __name__ == "__main__":
    # 測試腳本
    planner = ProjectPlanner(Path("."))
    test_intent = {
        "task": "Fix race condition in auth and update docs",
        "dimensions": {"logic_scope": "[待定]"}
    }
    res = planner.build_campaign(test_intent)
    print(f"Final Campaign Strategy:\n{json.dumps(res.__dict__, default=lambda o: o.__dict__, indent=2)}")
