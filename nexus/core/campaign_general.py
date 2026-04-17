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
    指揮官層級：負責史詩級 DAG 規劃與 L3 並行調度。
    """
    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.campaign_map: Dict[str, TaskNode] = {}
        self.max_nodes = 25  # 史詩級任務上限

    def decompose_intent(self, macro_intent: str) -> List[TaskNode]:
        """
        [P] Plan: 史詩級拆解引擎 (L4 DecompositionAgent)
        調用專業 Agent 進行全域掃描與任務爆破。
        """
        logger.info(f"🧠 [L4:Decomposer] Performing epic-level decomposition for: {macro_intent}")
        
        # 🛡️ 實戰對位：這裡模擬調用專門的 L4 拆解 Prompt 或 X-Ray 掃描
        # 在正式版中，這會生成一個具備 10-20 個節點的複雜圖結構
        
        # 建立一個史詩級範例：重構、實作、文檔與安全掃描的連動 DAG
        nodes = [
            TaskNode("T1-XRAY", "Perform full-system impact analysis", impact_files=["nexus/"]),
            TaskNode("T2-STORAGE-CORE", "Refactor core storage with thread-safety", dependencies=["T1-XRAY"], impact_files=["nexus/core/storage.py"]),
            TaskNode("T3-AUTH-SVC", "Implement BFT-aware auth provider", dependencies=["T2-STORAGE-CORE"], impact_files=["nexus/services/auth.py"]),
            TaskNode("T4-EVENT-BUS", "Optimize distributed event bus latency", dependencies=["T2-STORAGE-CORE"], impact_files=["nexus/core/events.py"]),
            TaskNode("T5-BFT-VALIDATOR", "Implement Byzantine validator nodes", dependencies=["T3-AUTH-SVC", "T4-EVENT-BUS"], impact_files=["nexus/core/bft.py"]),
            TaskNode("T6-DOC-COMPLETE", "Crystallize technical spec into documentation", dependencies=["T5-BFT-VALIDATOR"], impact_files=["docs/arch/"])
        ]
        
        # 為 T3 與 T4 標註為可並行（因為它們都只依賴 T2 且 impact_files 隔離）
        for node in nodes:
            node.envelope = StrategicEnvelope(
                macro_intent=macro_intent,
                read_only_files=["MUSE_PROTO.md"]
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
