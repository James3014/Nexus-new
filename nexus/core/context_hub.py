import os
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime
from dataclasses import dataclass
from nexus.contracts.context_assembly import build_context_assembly_contract
from nexus.contracts.context_budget import ContextBudgetSource, build_context_budget_receipt
from nexus.core.state_contracts import NexusDiagnosis, NexusResearch, NexusState
from nexus.core.state_io import StateIO
from nexus.services.memory import MemoryService
from nexus.core.brain_de_entropy import prune_dialogue


from nexus.core.context_compression import ToonRenderer, ContextScorer

logger = logging.getLogger("nexus.context_hub")


@dataclass(frozen=True)
class StateView:
    metadata: Dict[str, Any]
    conversation_metadata: Dict[str, Any] | None = None
    route_receipts: List[Dict[str, Any]] | None = None
    report_receipts: List[Dict[str, Any]] | None = None

    def get_conversation_metadata(self) -> Dict[str, Any]:
        return dict(self.conversation_metadata or {})

    def receipt_summary(self) -> Dict[str, int]:
        receipts = list(self.route_receipts or []) + list(self.report_receipts or [])
        return {
            "selected": sum(1 for item in receipts if isinstance(item, dict) and item.get("selected")),
            "invoked": sum(1 for item in receipts if isinstance(item, dict) and item.get("invoked")),
            "evidence": sum(1 for item in receipts if isinstance(item, dict) and item.get("evidence_present")),
            "gate": sum(1 for item in receipts if isinstance(item, dict) and item.get("gate_passed")),
        }


@dataclass(frozen=True)
class ContextDependencies:
    memory_service: Any | None = None
    wisdom_vault: Any | None = None
    belief_engine: Any | None = None
    knowledge_injector: Any | None = None
    prompt_builder: Any | None = None

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
        nexus_fs: Optional[Any] = None,
        skill_registry: Optional[Any] = None,
        mem_palace: Optional[Any] = None,
        deps: ContextDependencies | None = None,
        strict_deps: bool = False,
    ):
        strict_deps = bool(strict_deps or os.environ.get("NEXUS_CONTEXT_STRICT_DEPS") == "1")
        self.strict_deps = strict_deps
        self.project_root = Path(project_root)
        self.run_dir = Path(run_dir) if (run_dir and str(run_dir) != "None") else None
        self.state_io = StateIO(project_root, run_dir=run_dir)
        if strict_deps and deps is None:
            raise ValueError("strict_deps_requires_context_dependencies")
        deps = deps or ContextDependencies()
        self.memory_service = deps.memory_service or memory_service
        if self.memory_service is None and not strict_deps:
            self.memory_service = MemoryService(project_root, run_dir=run_dir)
        self.nexus_fs = nexus_fs
        self.skill_registry = skill_registry
        self.mem_palace = mem_palace
        self.wisdom_vault = deps.wisdom_vault  # Will be injected in coordinator or by DI
        if deps.prompt_builder is not None:
            self.prompt_builder = deps.prompt_builder
        elif strict_deps:
            self.prompt_builder = None
        else:
            from nexus.services.prompt_builder import PromptBuilder
            self.prompt_builder = PromptBuilder(project_root)
        
        # 🟢 [Fix-3] WisdomVault Auto-Injection
        if self.wisdom_vault is None and not strict_deps:
            try:
                from nexus.research.wisdom.wisdom_vault import WisdomVault
                db_path = str(self.project_root / ".nexus" / "knowledge" / "lancedb")
                self.wisdom_vault = WisdomVault(db_path=db_path)
            except Exception as e:
                logger.warning(f"⚠️ [ContextHub] WisdomVault auto-injection skipped: {e}")
                self.wisdom_vault = None
            
        # 🟢 [Fix-1] BeliefEngine Auto-Injection 
        self.belief_engine = deps.belief_engine
        if self.belief_engine is None and not strict_deps:
            try:
                from nexus.core.belief_engine import BeliefEngine
                self.belief_engine = BeliefEngine(self.project_root / ".nexus" / "belief_state.json")
            except Exception:
                self.belief_engine = None
            
        if deps.knowledge_injector is not None:
            self.knowledge_injector = deps.knowledge_injector
        elif strict_deps:
            self.knowledge_injector = None
        else:
            from nexus.core.knowledge_injector import KnowledgeInjector
            self.knowledge_injector = KnowledgeInjector(
                skill_registry=self.skill_registry,
                mem_palace=self.mem_palace,
                wisdom_vault=self.wisdom_vault
            )

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
        self,
        task_id: str,
        context: Optional[Dict] = None,
        *,
        state_view: StateView | NexusState | None = None,
    ) -> Dict[str, Any]:
        """🧠 Pre-routing: 決定是否需要外部 research、特定模式或審核層級。"""
        context = context or {}
        if self._is_benchmark_run(context):
            return {"external_needed": False, "mode": "benchmark", "priority": "normal", "audit_level": "full", "nas_autotune_needed": False}
            
        state = state_view or self.state_io.load_global_state()
        task_type = state.metadata.get("task_type", "standard")
        receipt_summary = self._receipt_summary(state)
        receipt_gap_reason = self._receipt_gap_reason(state, receipt_summary)
        
        # 🧪 [Wisdom Layer] 動態判斷是否需要 NAS 自動調優
        complexity_score = context.get("complexity_score", 0.0)
        autotune_needed = complexity_score > 0.7 or any(kw in task_id.lower() for kw in ["0-day", "blackhole", "critical", "hardest"])

        decision = {
            "external_needed": self._determine_external_needed(task_id, context),
            "mode": task_type, 
            "priority": "high" if autotune_needed else "normal",
            "audit_level": self._determine_audit_level(task_type, state),
            "nas_autotune_needed": autotune_needed,
            "receipt_summary": receipt_summary,
        }
        if receipt_gap_reason:
            decision["audit_level"] = "full"
            decision["receipt_gap_reason"] = receipt_gap_reason
        return decision

    def _receipt_summary(self, state: Any) -> Dict[str, int]:
        if hasattr(state, "receipt_summary"):
            try:
                summary = state.receipt_summary()
            except Exception:
                summary = {}
            if isinstance(summary, dict):
                return {key: int(summary.get(key, 0) or 0) for key in ("selected", "invoked", "evidence", "gate")}
        return {"selected": 0, "invoked": 0, "evidence": 0, "gate": 0}

    def _receipt_gap_reason(self, state: Any, summary: Dict[str, int]) -> str:
        receipts = list(getattr(state, "route_receipts", None) or []) + list(getattr(state, "report_receipts", None) or [])
        non_actionable = {"feature_flag_disabled", "recommended_without_invocation", "pending_executor"}
        for receipt in receipts:
            if not isinstance(receipt, dict):
                continue
            reason = str(receipt.get("failure_reason") or receipt.get("reason") or receipt.get("status_reason") or "")
            if reason in non_actionable:
                continue
            if bool(receipt.get("selected")) and not bool(receipt.get("invoked")):
                return "selected_without_invocation"
            if bool(receipt.get("invoked")) and not bool(receipt.get("evidence_present")):
                return "invoked_without_evidence"
            if bool(receipt.get("evidence_present")) and not bool(receipt.get("gate_passed")):
                return "evidence_without_gate"
        if receipts:
            return ""
        selected = int(summary.get("selected", 0) or 0)
        invoked = int(summary.get("invoked", 0) or 0)
        evidence = int(summary.get("evidence", 0) or 0)
        gate = int(summary.get("gate", 0) or 0)
        if selected > invoked:
            return "selected_without_invocation"
        if invoked > evidence:
            return "invoked_without_evidence"
        if evidence > gate:
            return "evidence_without_gate"
        return ""

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
        """🔌 Hook: 呼叫 NexusFS 或 MemoryService 取得 per-round 記憶。"""
        try:
            if self.memory_service and hasattr(self.memory_service, "cached_search"):
                return self.memory_service.cached_search(f"memory_v9_{phase}")
            if self.nexus_fs:
                return {"reminders": self.nexus_fs.search(f"memory_v9_{phase}"), "total_sources": -1}
        except Exception as e:
            logger.error(f"⚠️ [MemoryHook] Injection failed: {e}")
        return {"reminders": [], "total_sources": 0}

    def assemble_diag_pack(
        self, violations: List[Dict], summary: str
    ) -> Dict[str, Any]:
        """組裝診斷階段所需的 Context Pack。"""
        state = self.state_io.load_global_state()
        
        hotspots = list(set([
            str(v.get("file") if isinstance(v, dict) else getattr(v, "file", ""))
            for v in violations
        ]))
        hotspots = [h for h in hotspots if h and h != "None"]
        
        pack = {
            "task_id": state.task_id,
            "failure_summary": summary,
            "violations": violations[:10],  # 截斷以保持 token 效率
            "hotspots": hotspots,
            "history_summary": [steps.summary for steps in state.steps_history[-3:]],
            "contract_version": "1.5.2",
            "memory_reminders": self._inject_memory_reminders("D"),
        }
        pack["recommended_skills"] = self.knowledge_injector.recommend_skills(summary, hotspots[:5])
        pack["wisdom_prior"] = self.knowledge_injector.inject_wisdom_prior(summary, hotspots[:5])
        
        # [NEW: D-2] Inject Claims Diag Pack
        try:
            from nexus.research.learn_mode import LearnModeService
            from pathlib import Path
            root = getattr(self, "project_root", getattr(state, "project_root", "."))
            svc = LearnModeService(Path(root))
            diag_hints = svc.ask(topic="health-diagnostics", question=summary, top_k=3)
            if diag_hints.get("citations"):
                pack["claims_diag_hints"] = [c["claim"] for c in diag_hints["citations"]]
        except Exception:
            pass

        # 🟢 [Fix-1] Injects specific Audit Failure Beliefs into ContextHub Output
        if hasattr(self, "belief_engine") and self.belief_engine:
            task_belief = self.belief_engine.get_confidence(f"AUDIT_FAILURE_1")
            if task_belief < 0.5:
                pack["belief_warning"] = "⚠️ 低落的系統信心！之前的修復被稽核員駁回，請改變策略。"
                
        return pack

    def _get_l0_rules(self) -> str:
        """[L0] 治理根層：摘要化授權邊界與禁止行為"""
        return "L0: [BOUNDARIES: core, metrics] [PROHIBITED: delete-history, skip-verify]"

    def _load_last_handoff(self) -> Dict[str, Any]:
        """從 .nexus/state/last_handoff.json 載入跨回合狀態"""
        handoff_path = self.project_root / ".nexus" / "state" / "last_handoff.json"
        if handoff_path.exists():
            try:
                with open(handoff_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"⚠️ [ContextHub] Failed to load handoff: {e}")
        return {}

    def _get_l1_index(self) -> str:
        """[L1] 索引層：當前任務指針與狀態摘要 (Handoff Aligned)"""
        handoff = self._load_last_handoff()
        
        task_id = handoff.get("task_id", "New Task")
        phase = handoff.get("phase", os.environ.get("NEXUS_PHASE", "P"))
        token = handoff.get("state_token", "INITIAL")
        
        return f"L1: [TASK: {task_id}] [PHASE: {phase}] [TOKEN: {token}] [AOS: 131.5]"

    def build_context_budget_receipt(
        self,
        *,
        task_id: str,
        token_budget: int = 4000,
        state_view: StateView | NexusState | None = None,
        extra_sources: List[Dict[str, Any]] | None = None,
    ) -> Dict[str, Any]:
        """Build a read-only budget receipt for context assembly."""

        sources = self._context_budget_sources(state_view=state_view, extra_sources=extra_sources)
        receipt = build_context_budget_receipt(sources, token_budget=token_budget)
        payload = receipt.to_dict()
        payload["task_id"] = task_id
        return payload

    def build_context_assembly_contract(
        self,
        *,
        task_id: str,
        token_budget: int = 4000,
        state_view: StateView | NexusState | None = None,
        extra_sources: List[Dict[str, Any]] | None = None,
    ) -> Dict[str, Any]:
        """Build the audited context assembly contract used before deeper ContextHub rewrites."""

        sources = self._context_budget_sources(state_view=state_view, extra_sources=extra_sources)
        return build_context_assembly_contract(
            task_id=task_id,
            sources=[source.to_dict() if isinstance(source, ContextBudgetSource) else source for source in sources],
            token_budget=token_budget,
        )

    def build_runtime_context_adapter_receipt(
        self,
        *,
        task_id: str,
        token_budget: int = 4000,
        state_view: StateView | NexusState | None = None,
        extra_sources: List[Dict[str, Any]] | None = None,
    ) -> Dict[str, Any]:
        """Read-only preflight receipt before wiring ContextHub runtime behavior."""

        contract = self.build_context_assembly_contract(
            task_id=task_id,
            token_budget=token_budget,
            state_view=state_view,
            extra_sources=extra_sources,
        )
        blockers = list(contract.get("blockers", []) or [])
        return {
            "schema": "nexus.runtime_context_adapter_receipt.v1",
            "status": "PASS" if not blockers else "RETURN",
            "task_id": task_id,
            "context_assembly_status": contract.get("status"),
            "runtime_dispatch_changed": False,
            "public_benchmark_allowed": False,
            "runtime_update_allowed": False,
            "contract": contract,
            "blockers": blockers,
            "claim_boundary": [
                "Runtime context adapter receipts preflight context assembly only.",
                "They do not change ContextHub assembly, route dispatch, or public benchmark readiness.",
            ],
        }

    def _context_budget_sources(
        self,
        *,
        state_view: StateView | NexusState | None = None,
        extra_sources: List[Dict[str, Any]] | None = None,
    ) -> list[ContextBudgetSource | Dict[str, Any]]:
        state = state_view or self.state_io.load_global_state()
        l0 = self._get_l0_rules()
        l1 = self._get_l1_index()
        history = getattr(state, "metadata", {}).get("chat_history", []) if state is not None else []
        sources: list[ContextBudgetSource | Dict[str, Any]] = [
            ContextBudgetSource("L0:rules", "L0", self._estimate_context_tokens(l0), priority=0, required=True),
            ContextBudgetSource("L1:index", "L1", self._estimate_context_tokens(l1), priority=1, required=True),
        ]
        if history:
            sources.append(
                ContextBudgetSource(
                    "history:recent",
                    "history",
                    self._estimate_context_tokens(str(history[-5:])),
                    priority=20,
                )
            )
        sources.extend(extra_sources or [])
        return sources

    def _estimate_context_tokens(self, value: Any) -> int:
        return max(1, int(len(str(value)) / 3.8))

    def assemble_context(self, task_id: str, layers: List[int], budget: int = 4000, bayesian_params: Optional[Dict[str, Any]] = None) -> str:
        """
        🚀 19-layer Context Assembly Engine (v24.2 Hierarchical Hardened).
        """
        # 🧪 [v24.2] 優先從政策讀取全局元參數
        from nexus.core.policy_loader import PolicyLoader
        policy = PolicyLoader.load(self.project_root)
        
        nas_aggression = (bayesian_params or {}).get("nas_aggression")
        if nas_aggression is None:
            nas_aggression = policy.global_nas_aggression # 物理對接最高憲法
            
        l0 = self._get_l0_rules()
        l1 = self._get_l1_index()
        
        state = self.state_io.load_global_state()
        history = state.metadata.get("chat_history", [])
        
        # 🧪 [Bayesian-Guided Retrieval]
        memory_limit = 3 if nas_aggression > 0.8 else 10
        
        # 🧪 [TOON-2.0 Rendering]
        toon_summary = ToonRenderer.render(state, aggression=nas_aggression)

        # 🧪 [v25.0 Context-Compactor Integration]
        from nexus.core.context_compactor import ContextCompactor
        compactor = ContextCompactor(self.project_root)
        confidence = (bayesian_params or {}).get("confidence", 0.5)
        structured_summary = compactor.compact(state.to_dict() if hasattr(state, "to_dict") else vars(state), confidence=confidence)

        # 🧪 [Entropy Prediction] (AOS-131.5)
        # Estimate tokens using a more accurate heuristic for code-heavy contexts
        def predict_tokens(txt_list):
            return sum(len(str(t)) for t in txt_list) // 3.8

        estimated_total = predict_tokens([l0, l1, history, toon_summary, json.dumps(structured_summary)])
        threshold = budget * (1.0 - (nas_aggression * 0.2))

        if estimated_total > threshold:
            logger.info(f"✂️ [ContextHub:TOON-2.0] Predicted {estimated_total:.0f} tokens exceed {threshold:.0f}. Compacting...")
            compact_history = prune_dialogue(history, aggression=nas_aggression)
            context_parts = [
                l0, l1,
                "--- STRUCTURED CONTEXT (L5-Addressable) ---",
                json.dumps(structured_summary, indent=2),
                "--- TOON-2.0 SUMMARY ---",
                toon_summary,
                "--- COMPACT HISTORY ---",
                compact_history
            ]
        else:
            context_parts = [
                l0, l1,
                "--- STRUCTURED CONTEXT (L5-Addressable) ---",
                json.dumps(structured_summary, indent=2),
                "--- TOON-2.0 SUMMARY ---",
                toon_summary
            ]
            if history:
                context_parts.append(str(history[-5:])) # Balanced history depth

        logger.info(f"🛠️ [ContextHub:v25.0] Hybrid Context Assembled | Compactor: ACTIVE | Aggression: {nas_aggression:.2f}")
        return "\n".join(context_parts)

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
        pack["recommended_skills"] = self.knowledge_injector.recommend_skills(diagnosis.summary, diagnosis.hotspots)
        pack["wisdom_prior"] = self.knowledge_injector.inject_wisdom_prior(diagnosis.summary, diagnosis.hotspots)
        return pack



    def record_crystal_lesson(
        self,
        failure_signature: str,
        root_cause: str,
        lesson: str,
        metadata: Optional[Dict] = None,
    ):
        """💾 Phase 1+: 記錄結構化 FindingsCard (DeepScientist Spec)。"""
        from nexus.research.findings_memory import FindingsCard, FindingsMemoryStore
        
        store = FindingsMemoryStore(self.project_root)
        
        # 建立結構化記憶卡
        card = FindingsCard(
            task_id=(metadata or {}).get("task_id", failure_signature),
            kind="episodes",
            title=f"Failure: {failure_signature}",
            scope="task",
            tags=["failure-analysis", failure_signature.split(":")[0]],
            stage="unknown", 
            confidence="high",
            body=f"Root Cause: {root_cause}\nLesson: {lesson}",
            evidence_paths=[str(self.run_dir)] if self.run_dir else [],
            extra=metadata or {}
        )
        
        path = store.write(card)
        logger.info(f"🧠 [DeepScientist:Memory] Structured Lesson recorded: {path}")
