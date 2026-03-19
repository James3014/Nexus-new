import json
from typing import List, Dict, Any, Optional
from pathlib import Path
from datetime import datetime
from nexus.core.state_contracts import NexusDiagnosis, NexusResearch, NexusState
from nexus.core.state_io import StateIO
from nexus.services.memory import MemoryService


class ToonRenderer:
    """👾 TOON (Trinity Output Optimization Network) 語義壓縮器 (PHA-020)"""
    @staticmethod
    def render(state: NexusState) -> str:
        """將長篇歷史、日誌壓縮為 Markdown 表格摘要"""
        summary = ["| Phase | ID | Status | Summary |", "|---|---|---|---|"]
        
        # 只取最後 3 筆詳細記錄
        for step in state.steps_history[-3:]:
            summary.append(f"| {step.phase} | {step.step_id} | {step.status} | {step.summary or 'none'} |")
            
        # 其他補上計數
        if len(state.steps_history) > 3:
            summary.append(f"| ... | ({len(state.steps_history)-3} others) | ... | (Compressed) |")
            
        return "\n".join(summary)

class ContextScorer:
    """🎯 Trinity Context Scorer: 依階段決定檔案權重 (PHA-021)"""
    @staticmethod
    def get_relevance(phase: str, file_path: str) -> float:
        path = file_path.lower()
        if phase == "P":
            return 1.0 if any(k in path for k in ["index", "manifest", "todo"]) else 0.5
        if phase == "D":
            return 1.0 if any(k in path for k in ["test", "log", "trace"]) else 0.4
        if phase in ["R", "A"]:
            return 1.0 if path.endswith(".py") or path.endswith(".js") else 0.3
        return 0.5

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

    def make_pre_routing_decision(
        self, task_id: str, context: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """🧠 Pre-routing: 決定是否需要外部研究、特定模式或審核層級。"""
        context = context or {}
        state = self.state_io.load_global_state()
        task_type = state.metadata.get("task_type", "standard")

        external_needed = context.get("force_external", False)
        task_lower = task_id.lower()
        if (
            any(kw in task_lower for kw in ["fix", "error", "bug", "issue"])
            or "sdk" in task_lower
        ):
            external_needed = True

        decision = {
            "external_needed": external_needed,
            "mode": task_type,
            "priority": "normal",
            "audit_level": "full",  # Default
        }

        # 🧬 v0.7 Spec: Conversation Risk-Based Audit Level
        if task_type == "conversation":
            conv_meta = state.get_conversation_metadata()
            # 判斷風險等級 (skip | light | full)
            if not conv_meta.get("key_context_facts") and not conv_meta.get(
                "user_corrections"
            ):
                decision["audit_level"] = "skip"
            elif (
                not conv_meta.get("needs_research")
                and conv_meta.get("answer_draft_status") == "partial"
            ):
                decision["audit_level"] = "light"
            else:
                decision["audit_level"] = "full"

        return decision

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
        """
        組裝對話專用 Context Pack (v0.7 Spec)。
        audit_mode=True 時啟用壓縮策略，節省 A 階段 token 消耗。
        """
        state = self.state_io.load_global_state()
        conv_meta = state.get_conversation_metadata()

        # 🧬 v2: 壓縮策略
        if audit_mode:
            # 只保留最近 2 回合摘要，不含詳細內容
            steps_ctx = [
                {"phase": s.phase, "summary": s.summary}
                for s in state.steps_history[-2:]
            ]
        else:
            steps_ctx = [s.summary for s in state.steps_history[-5:]]

        pack = {
            "conversation_id": conv_meta.get("conversation_id"),
            "user_goal": conv_meta.get("user_goal"),
            "current_question": conv_meta.get("current_question"),
            "confirmed_constraints": conv_meta.get("confirmed_constraints", []),
            "key_context_facts": conv_meta.get("key_context_facts", {}),
            "user_corrections": conv_meta.get("user_corrections", []),
            "unresolved_points": conv_meta.get("unresolved_points", []),
            "answer_draft_status": conv_meta.get("answer_draft_status"),
            "steps_history_summary": steps_ctx,
            "memory_reminders": self._inject_memory_reminders("conversation"),
            "timestamp": datetime.now().isoformat(),
        }

        # 注入最近的審核反饋 (如果有)
        if "last_audit_feedback" in state.metadata:
            pack["prior_audit_feedback"] = state.metadata["last_audit_feedback"]

        # 注入研究結果 (非壓縮模式)
        if not audit_mode and conv_meta.get("needs_research") and state.steps_history:
            for step in reversed(state.steps_history):
                if step.phase == "X" and step.status == "completed":
                    pack["research_findings"] = step.metadata.get("findings", [])
                    break

        return pack

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
