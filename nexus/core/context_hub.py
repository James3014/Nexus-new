from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import json
from datetime import datetime
from nexus.core.state_contracts import NexusDiagnosis, NexusResearch, NexusState
from nexus.core.state_io import StateIO
from nexus.services.memory import MemoryService
from scripts.brain_de_entropy import prune_dialogue


from nexus.core.context_compression import ToonRenderer, ContextScorer

class ContextHub:
    """
    🧠 Nexus Context Hub
    負責收集、組裝與壓縮上下文，為 Agent 提供乾淨的 P-D-X-R-A-C 視圖。
    """

    def __init__(
        self,
        project_root: str,
        memory_service: Optional[Any] = None,
        run_dir: Optional[str] = None,
    ):
        self.project_root = Path(project_root)
        self.run_dir = Path(run_dir) if (run_dir and str(run_dir) != "None") else None
        self.state_io = StateIO(project_root, run_dir=run_dir)
        self.memory_service = memory_service or MemoryService(
            project_root, run_dir=run_dir
        )

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
        """🧠 Pre-routing: 決定是否需要外部 research、特定模式或審核層級。"""
        context = context or {}
        if self._is_benchmark_run(context):
            return {"external_needed": False, "mode": "benchmark", "priority": "normal", "audit_level": "full"}
            
        state = self.state_io.load_global_state()
        task_type = state.metadata.get("task_type", "standard")
        
        decision = {
            "external_needed": self._determine_external_needed(task_id, context),
            "mode": task_type, "priority": "normal",
            "audit_level": self._determine_audit_level(task_type, state),
        }
        return decision

    def _is_benchmark_run(self, context: Dict) -> bool:
        return bool(context.get("benchmark_run"))

    def _determine_external_needed(self, task_id: str, context: Dict) -> bool:
        if context.get("force_external", False):
            return True
        task_lower = task_id.lower()
        return any(kw in task_lower for kw in ["fix", "error", "bug", "issue"]) or "sdk" in task_lower

    def _determine_audit_level(self, task_type: str, state: NexusState) -> str:
        if task_type != "conversation":
            return "full"
        conv_meta = state.get_conversation_metadata()
        if not conv_meta.get("key_context_facts") and not conv_meta.get("user_corrections"):
            return "skip"
        if not conv_meta.get("needs_research") and conv_meta.get("answer_draft_status") == "partial":
            return "light"
        return "full"

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
            "hotspots": list(set([
                (v.get("file") if isinstance(v, dict) else getattr(v, "file", None))
                for v in violations
            ])),
            "history_summary": [steps.summary for steps in state.steps_history[-3:]],
            "contract_version": "1.5.2",
            "memory_reminders": self._inject_memory_reminders("D"),
        }
        return pack

    def assemble_research_pack(self, query: str, results: List[Dict]) -> Dict[str, Any]:
        """組裝研究階段所需的 Context Pack。"""
        return {
            "query": query,
            "results": results,
            "fact_count": len(results),
            "relevance_gate": True,
            "memory_reminders": self._inject_memory_reminders(
                "X"
            ),  # Added memory for research phase
        }

    def assemble_feature_pack(self, plan: Optional[Dict] = None) -> Dict[str, Any]:
        """🧬 Phase 1: 為新功能建置組裝上下文 (含 TOON 壓縮)。"""
        state = self.state_io.load_global_state()
        memory = self.memory_service.aggregate_memory()
        
        # 🧪 TOON 語義壓縮生效
        toon_view = ToonRenderer.render(state)

        return {
            "task": state.task_id,
            "plan": plan or {},
            "TOON_SUMMARY": toon_view,
            "memory": memory,
            "rules": self.load_program_rules(),
            "timestamp": datetime.now().isoformat(),
        }

    def assemble_conversation_pack(self, audit_mode: bool = False) -> Dict[str, Any]:
        """組裝對話專用 Context Pack (v0.7 Spec)。"""
        state = self.state_io.load_global_state()
        conv_meta = state.get_conversation_metadata()
        
        pack = {
            "conversation_id": conv_meta.get("conversation_id"),
            "user_goal": conv_meta.get("user_goal"),
            "current_question": conv_meta.get("current_question"),
            "confirmed_constraints": conv_meta.get("confirmed_constraints", []),
            "key_context_facts": conv_meta.get("key_context_facts", {}),
            "user_corrections": conv_meta.get("user_corrections", []),
            "unresolved_points": conv_meta.get("unresolved_points", []),
            "answer_draft_status": conv_meta.get("answer_draft_status"),
            "steps_history_summary": self._summarize_steps_history(state, audit_mode),
            # 🧬 P2: 對話熵減 (v22 De-Entropy)
            "pruned_history": prune_dialogue(state.metadata.get("chat_history", [])),
            "memory_reminders": self._inject_memory_reminders("conversation"),
            "timestamp": datetime.now().isoformat(),
        }

        if "last_audit_feedback" in state.metadata:
            pack["prior_audit_feedback"] = state.metadata["last_audit_feedback"]

        self._inject_research_findings(state, conv_meta, pack, audit_mode)
        return pack

    def _summarize_steps_history(self, state: NexusState, audit_mode: bool) -> List:
        if audit_mode:
            return [{"phase": s.phase, "summary": s.summary} for s in state.steps_history[-2:]]
        return [s.summary for s in state.steps_history[-5:]]

    def _inject_research_findings(self, state: NexusState, conv_meta: Dict, pack: Dict, audit_mode: bool) -> None:
        if not audit_mode and conv_meta.get("needs_research") and state.steps_history:
            for step in reversed(state.steps_history):
                if step.phase == "X" and step.status == "completed":
                    pack["research_findings"] = step.metadata.get("findings", [])
                    break

    def assemble_repair_pack(
        self,
        diagnosis: NexusDiagnosis,
        reflections: List[Dict],
        research: Optional[NexusResearch] = None,
    ) -> Dict[str, Any]:
        """組裝修復階段所需的 Context Pack (整合 Superpowers v5.0.2)。"""
        state = self.state_io.load_global_state()

        # --- Context Compact: 壓縮 reflection 與歷史以提高 token 效率 (1.2x tokens) ---
        compact_reflections = reflections[-2:]  # 只保留最近 2 輪以防冗餘

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
            "memory_reminders": self._inject_memory_reminders("R"),
        }
        return pack

    def record_crystal_lesson(
        self,
        failure_signature: str,
        root_cause: str,
        lesson: str,
        metadata: Optional[Dict] = None,
    ):
        """💾 Phase 5: 記錄失敗案例用於 Active Learning。"""
        # Noise Governance: If run_dir exists, store there. Otherwise, global obsidian/ folder.
        if self.run_dir is not None:
            lesson_file = self.run_dir / "crystal_lessons.jsonl"
        else:
            # 🛡️ FIX-P1: Use a protected directory for knowledge baseline (not cleaned by nexus:clean)
            lesson_file = (
                self.project_root / ".nexus" / "knowledge" / "crystal_lessons.jsonl"
            )

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
