#!/usr/bin/env python3
"""
🧬 Nexus L4 Campaign-General (Macro-Planning & DAG Orchestration)
負責將模糊意圖拆解為任務圖 (DAG)，並管理 L4->L3 的神經銜接與環境屏障。
"""

import os
import json
import logging
import time
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
    criteria: Dict[str, Any] = field(default_factory=dict)
    criteria_passed: bool = False

class CampaignGeneral:
    """
    指揮官層級：負責史詩級 DAG 規劃與 L3 並行調度。
    """
    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.campaign_map: Dict[str, TaskNode] = {}
        self.max_nodes = 25  # 史詩級任務上限
        self.burst_count = 0

    def decompose_intent(self, macro_intent: str) -> List[TaskNode]:
        """
        [P] Plan: 史詩級拆解引擎 (L4 DecompositionAgent)
        根據 macro_intent 的複雜度與關鍵字，動態生成任務節點與依賴圖。
        """
        logger.info(f"🧠 [L4:Decomposer] Performing dynamic decomposition for: {macro_intent}")
        
        intent_lower = macro_intent.lower()
        nodes = []
        fallback_used = False
        reason = "Dynamic heuristic based on intent keywords"

        # 簡單的啟發式拆解邏輯
        if "refactor" in intent_lower or "core" in intent_lower:
            nodes = [
                TaskNode("T1-XRAY", f"Analyze system impact for: {macro_intent}", impact_files=["nexus/"]),
                TaskNode("T2-CORE", "Apply core logic refactoring", dependencies=["T1-XRAY"], impact_files=["nexus/core/"]),
                TaskNode("T3-VERIFY", "Verify refactored core integrity", dependencies=["T2-CORE"])
            ]
        elif "fix" in intent_lower or "bug" in intent_lower:
            nodes = [
                TaskNode("T1-REPRO", f"Reproduce failure for: {macro_intent}"),
                TaskNode("T2-FIX", "Implement bugfix and local validation", dependencies=["T1-REPRO"]),
                TaskNode("T3-REGRESSION", "Run full regression suite", dependencies=["T2-FIX"])
            ]
        elif "doc" in intent_lower or "wiki" in intent_lower:
            nodes = [
                TaskNode("T1-INGEST", f"Ingest context for documentation: {macro_intent}"),
                TaskNode("T2-WRITE", "Generate structured technical documentation", dependencies=["T1-INGEST"]),
                TaskNode("T3-REVIEW", "Perform peer-review on documentation", dependencies=["T2-WRITE"])
            ]
        else:
            # Fallback: 使用最小安全 DAG
            fallback_used = True
            reason = "No specific keywords matched, using minimal safety fallback"
            nodes = [
                TaskNode("T1-MIN-XRAY", "Perform minimal impact scan"),
                TaskNode("T2-MIN-EXEC", f"Execute core task: {macro_intent}", dependencies=["T1-MIN-XRAY"])
            ]

        logger.info(f"📊 [L4:Decomposer] DAG Generated. Nodes: {len(nodes)}, Fallback: {fallback_used}, Reason: {reason}")
        
        for node in nodes:
            node.envelope = StrategicEnvelope(
                macro_intent=macro_intent,
                read_only_files=["MUSE_PROTO.md"]
            )
            self.campaign_map[node.node_id] = node
            
        return nodes

    def trigger_burst(self, node_id: str):
        """
        🚀 [L4:Recursive-Bursting] 細胞分裂：將一個過於龐大的任務炸開為子圖。
        """
        if node_id not in self.campaign_map: return
        
        target = self.campaign_map[node_id]
        logger.info(f"💥 [L4:Bursting] Node {node_id} too complex. Splitting into sub-campaign.")
        
        # 建立子任務圖 (模擬分裂過程)
        self.burst_count += 1
        sub_n1 = TaskNode(f"{node_id}.1", f"Analyze bottleneck of {target.intent}", impact_files=target.impact_files)
        sub_n2 = TaskNode(f"{node_id}.2", f"Implement core fix for {node_id}", dependencies=[sub_n1.node_id], impact_files=target.impact_files)
        sub_n3 = TaskNode(f"{node_id}.3", f"Regression test for {node_id}", dependencies=[sub_n2.node_id])
        
        # 更新全域圖：繼承原始依賴
        sub_n1.dependencies = target.dependencies
        
        # 將下游任務的依賴重新指向子圖的末端
        for n in self.campaign_map.values():
            if node_id in n.dependencies:
                n.dependencies.remove(node_id)
                n.dependencies.append(sub_n3.node_id)
        
        # 移除原節點，注入新節點
        del self.campaign_map[node_id]
        for sub in [sub_n1, sub_n2, sub_n3]:
            sub.envelope = target.envelope
            self.campaign_map[sub.node_id] = sub
        
        logger.info(f"✅ [L4:Bursting] Node {node_id} replaced by {[sub_n1.node_id, sub_n2.node_id, sub_n3.node_id]}")

    def is_milestone_reached(self) -> bool:
        """
        🚧 [L4:Milestone] 里程碑檢查點。
        判斷當前已完成節點比例，必要時強制暫停等待審議。
        """
        completed = [n for n in self.campaign_map.values() if n.status == "SUCCESS"]
        ratio = len(completed) / max(1, len(self.campaign_map))
        if 0.4 < ratio < 0.6: # 50% 里程碑
            logger.warning(f"🚧 [L4:Milestone] 50% mission reached ({len(completed)} nodes). Requiring architect review.")
            return True
        return False



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

    def generate_evolution_report(self, output_dir: Path):
        """
        [L7:Evolution-Closure] 產生統一的演化報表。
        """
        output_dir.mkdir(parents=True, exist_ok=True)
        report_path = output_dir / "pipeline_evolution_report.json"
        
        nodes_summary = []
        for node in self.campaign_map.values():
            nodes_summary.append({
                "node_id": node.node_id,
                "intent": node.intent,
                "status": node.status,
                "criteria_passed": node.criteria_passed,
                "dependencies": node.dependencies
            })

        report_data = {
            "timestamp": time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
            "macro_intent": next(iter(self.campaign_map.values())).envelope.macro_intent if self.campaign_map else "unknown",
            "dag_summary": nodes_summary,
            "execution_outcome": "SUCCESS" if all(n.status == "SUCCESS" for n in self.campaign_map.values()) else "PARTIAL",
            "feedback_signals": ["automated_dag_generation_verified"],
            "next_evolution_plan": "Enhance L4 decomposition with actual LLM feedback loop"
        }

        report_path.write_text(json.dumps(report_data, indent=2), encoding="utf-8")
        logger.info(f"📜 [L7:Evolution] Unified report generated: {report_path}")

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
