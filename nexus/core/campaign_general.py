#!/usr/bin/env python3
"""
🧬 Nexus L4 Campaign-General (Macro-Planning & DAG Orchestration)
負責將模糊意圖拆解為任務圖 (DAG)，並管理 L4->L3 的神經銜接與環境屏障。
"""

import os
import json
import logging
from typing import Dict, List, Any, Optional, Set
from dataclasses import dataclass, field
from pathlib import Path

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("nexus.campaign")

@dataclass
class StrategicEnvelope:
    """隨附於任務節點的戰略封套，傳遞給 L3 ProjectPlanner。"""
    macro_intent: str
    read_only_files: List[str] = field(default_factory=list)
    global_constraints: List[str] = field(default_factory=list)
    upstream_artifacts: Dict[str, Any] = field(default_factory=dict)

@dataclass
class TaskNode:
    """戰役中的單一任務節點。"""
    node_id: str
    intent: str
    dependencies: List[str] = field(default_factory=list)
    impact_files: List[str] = field(default_factory=list)
    status: str = "PENDING"  # PENDING, EXECUTING, SUCCESS, FAIL, BURSTING
    envelope: Optional[StrategicEnvelope] = None
    result_path: Optional[str] = None

class CampaignGeneral:
    """
    指揮官層級：負責宏觀 DAG 規劃與 L3 調度。
    """
    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.campaign_map: Dict[str, TaskNode] = {}

    def decompose_intent(self, macro_intent: str) -> List[TaskNode]:
        """
        [P] Plan: 將宏觀意圖拆解為子任務圖。
        目前實作啟發式拆解，未來將對接 LLM 與靜態分析。
        """
        logger.info(f"🗺️ [Campaign:Decompose] Analyzing macro intent: {macro_intent}")
        
        # 模擬拆解邏輯：針對典型軟體開發任務進行拓樸預判
        nodes = []
        
        if "auth" in macro_intent.lower() or "security" in macro_intent.lower():
            n1 = TaskNode("T1-STORAGE", "Initialize secure credential storage", impact_files=["nexus/core/storage.py"])
            n2 = TaskNode("T2-AUTH-API", "Implement JWT token validation", dependencies=["T1-STORAGE"], impact_files=["nexus/app/auth.py"])
            n3 = TaskNode("T3-DOC", "Update security architecture documentation", dependencies=["T2-AUTH-API"], impact_files=["docs/security.md"])
            nodes = [n1, n2, n3]
        else:
            # 預設通用拆解
            nodes = [
                TaskNode("T1-ANALYSIS", f"Scout and analyze: {macro_intent}"),
                TaskNode("T2-CORE-IMPL", "Implement core logic based on T1", dependencies=["T1-ANALYSIS"]),
                TaskNode("T3-INTEGRATION-TEST", "Integrate and run system-wide tests", dependencies=["T2-CORE-IMPL"])
            ]
            
        for node in nodes:
            # 為每個節點封裝戰略封套
            node.envelope = StrategicEnvelope(
                macro_intent=macro_intent,
                read_only_files=["MUSE_PROTO.md", "AGENTS.md"] # 硬性保護核心
            )
            self.campaign_map[node.node_id] = node
            
        return nodes

    def get_executable_nodes(self) -> List[TaskNode]:
        """
        [D] Design: 根據拓樸排序尋找目前可執行的任務（入度為 0 且狀態為 PENDING）。
        """
        executable = []
        for node_id, node in self.campaign_map.items():
            if node.status != "PENDING":
                continue
            
            # 檢查所有依賴是否都已 SUCCESS
            all_deps_met = True
            for dep_id in node.dependencies:
                dep_node = self.campaign_map.get(dep_id)
                if not dep_node or dep_node.status != "SUCCESS":
                    all_deps_met = False
                    break
            
            if all_deps_met:
                executable.append(node)
                
        return executable

    def check_environment_fence(self, nodes: List[TaskNode]) -> List[List[TaskNode]]:
        """
        🛡️ 環境屏障：Codex 建議。檢查檔案衝突，將可安全並行的任務分組。
        """
        if not nodes: return []
        
        parallel_groups = []
        current_group = []
        seen_files: Set[str] = set()
        
        for node in nodes:
            # 檢查是否有檔案重疊
            conflict = any(f in seen_files for f in node.impact_files)
            
            if conflict:
                # 產生衝突，需強制分組（序列化執行）
                if current_group:
                    parallel_groups.append(current_group)
                current_group = [node]
                seen_files = set(node.impact_files)
            else:
                current_group.append(node)
                seen_files.update(node.impact_files)
                
        if current_group:
            parallel_groups.append(current_group)
            
        return parallel_groups

if __name__ == "__main__":
    # 原型測試
    commander = CampaignGeneral(Path("."))
    intent = "Implement a new authenticated storage service for the nexus core"
    nodes = commander.decompose_intent(intent)
    
    print(f"Campaign DAG created with {len(nodes)} nodes.")
    ready = commander.get_executable_nodes()
    print(f"Nodes ready for dispatch: {[n.node_id for n in ready]}")
    
    groups = commander.check_environment_fence(ready)
    print(f"Parallel Execution Groups: {[[n.node_id for n in g] for g in groups]}")
