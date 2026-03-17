import json
from typing import List, Dict, Any, Optional
from pathlib import Path
from datetime import datetime
from nexus.core.state_contracts import NexusDiagnosis, NexusResearch
from nexus.core.state_io import StateIO
from nexus.services.memory import MemoryService


class ContextHub:
    """
    🧠 Nexus Context Hub
    負責收集、組裝與壓縮上下文，為 Agent 提供乾淨的 P-D-X-R-A-C 視圖。
    """

    def __init__(self, project_root: str, memory_service: Optional[Any] = None):
        self.project_root = Path(project_root)
        self.state_io = StateIO(project_root)
        self.memory_service = memory_service or MemoryService(project_root)
        
        from nexus.services.prompt_builder import PromptBuilder
        self.prompt_builder = PromptBuilder(project_root)

    def load_program_rules(self, md_path: str = "program.md") -> str:
        """讀取 AutoResearch 規則文件。"""
        path = Path(md_path)
        if not path.exists():
            return "# Default: Optimize target file, metric FlashJudge > prev_score"
        try:
            return path.read_text(encoding="utf-8")
        except Exception as e:
            return f"# Error loading rules: {e}"

    def make_pre_routing_decision(self, task_id: str, context: Optional[Dict] = None) -> Dict[str, Any]:
        """🧠 Pre-routing: 決定是否需要外部研究或特定模式。"""
        # 簡單邏輯：包含 'bug' 或 'error' 且描述較長時，建議開啟外部研究
        context = context or {}
        external_needed = False
        task_lower = task_id.lower()
        if any(kw in task_lower for kw in ["fix", "error", "bug", "issue"]):
            external_needed = True
            
        return {
            "external_needed": external_needed,
            "mode": "standard",
            "priority": "normal"
        }

    def _inject_memory_reminders(self, phase: str) -> Dict[str, Any]:
        """🔌 Hook: 呼叫 MemoryService 取得 per-round 記憶。"""
        try:
            return self.memory_service.cached_search(f"memory_v9_{phase}")
        except Exception as e:
            print(f"⚠️ [MemoryHook] Injection failed: {e}")
        return {"reminders": [], "total_sources": 0}

    def assemble_diag_pack(
        self, violations: List[Dict], summary: str
    ) -> Dict[str, Any]:
        """組裝診斷階段所需的 Context Pack。"""
        state = self.state_io.load_global_state()
        pack = {
            "task_id": state.task_id,
            "failure_summary": summary,
            "violations": violations[:10],  # 截斷以保持 token 效率
            "hotspots": list(set([v.get("file") for v in violations if v.get("file")])),
            "history_summary": [steps.summary for steps in state.steps_history[-3:]],
            "contract_version": "1.5.2",
            "memory_reminders": self._inject_memory_reminders("D")
        }
        return pack

    def assemble_research_pack(self, query: str, results: List[Dict]) -> Dict[str, Any]:
        """組裝研究階段所需的 Context Pack。"""
        return {
            "query": query,
            "results": results,
            "fact_count": len(results),
            "relevance_gate": True,
            "memory_reminders": self._inject_memory_reminders("X") # Added memory for research phase
        }

    def assemble_repair_pack(
        self,
        diagnosis: NexusDiagnosis,
        reflections: List[Dict],
        research: Optional[NexusResearch] = None,
    ) -> Dict[str, Any]:
        """組裝修復階段所需的 Context Pack (整合 Superpowers v5.0.2)。"""
        state = self.state_io.load_global_state()
        
        # --- Context Compact: 壓縮 reflection 與歷史以提高 token 效率 (1.2x tokens) ---
        compact_reflections = reflections[-2:] # 只保留最近 2 輪以防冗餘
        
        pack = {
            "root_cause": diagnosis.summary,
            "repair_strategy": diagnosis.pseudo_flows,
            "target_files": diagnosis.hotspots,
            "recent_reflections": compact_reflections,
            "external_research": research.key_findings if research else [],
            
            # Superpowers 擴展
            "superpowers_plan": getattr(state, "superpowers_plan", {}),
            "tdd_status": state.tdd_status,
            "worktree_uuid": state.metadata.get("worktree_uuid", "main-branch"),
            
            "memory_reminders": self._inject_memory_reminders("R")
        }
        return pack

    def record_crystal_lesson(
        self, failure_signature: str, root_cause: str, lesson: str, metadata: Optional[Dict] = None
    ):
        """💾 Phase 5: 記錄失敗案例用於 Active Learning。"""
        lesson_file = self.project_root / "obsidian/crystal_lessons.jsonl"
        lesson_file.parent.mkdir(parents=True, exist_ok=True)

        entry = {
            "timestamp": datetime.now().isoformat(),
            "signature": failure_signature,
            "cause": root_cause,
            "lesson": lesson,
            "metadata": metadata or {},
            "recall_accuracy": 0.0,  # 初始準確度佔位
        }
        with open(lesson_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
        print(f"🧠 [ActiveLearning] Crystal Lesson recorded: {failure_signature}")
