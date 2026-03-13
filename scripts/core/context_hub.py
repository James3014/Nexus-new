from typing import List, Dict, Any
from pathlib import Path
from core.state_contracts import NexusDiagnosis, NexusPlan, AuditResult
from core.state_io import StateIO

class ContextHub:
    """
    🧠 Nexus Context Hub
    負責收集、組裝與壓縮上下文，為 Agent 提供乾淨的 P-D-X-R-A-C 視圖。
    """
    def __init__(self, project_root: str):
        self.project_root = Path(project_root)
        self.state_io = StateIO(project_root)

    def assemble_diag_pack(self, violations: List[Dict], summary: str) -> Dict[str, Any]:
        """組裝診斷階段所需的 Context Pack。"""
        state = self.state_io.load_global_state()
        pack = {
            "task_id": state.task_id,
            "failure_summary": summary,
            "violations": violations[:10],  # 截斷以保持 token 效率
            "hotspots": list(set([v.get("file") for v in violations if v.get("file")])),
            "history_summary": [steps.summary for steps in state.steps_history[-3:]],
            "contract_version": "1.5.2"
        }
        return pack

    def assemble_research_pack(self, query: str, results: List[Dict]) -> Dict[str, Any]:
        """組裝研究階段所需的 Context Pack。"""
        return {
            "query": query,
            "results": results,
            "fact_count": len(results),
            "relevance_gate": True
        }

    def assemble_repair_pack(self, diagnosis: NexusDiagnosis, reflections: List[Dict], research: Optional[NexusResearch] = None) -> Dict[str, Any]:
        """組裝修復階段所需的 Context Pack (對齊 v5)。"""
        return {
            "root_cause": diagnosis.summary,
            "repair_strategy": diagnosis.pseudo_flows,
            "target_files": diagnosis.hotspots,
            "recent_reflections": reflections,
            "external_research": research.key_findings if research else [],
            "logic_guard": True
        }
