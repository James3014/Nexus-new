from typing import Any, Dict, List, Optional, Tuple
import os
from pathlib import Path
from nexus.engine.phases.base import BasePhaseHandler
from nexus.core.state_contracts import NexusState
from scripts.engine.intent_classifier import IntentClassifier
from nexus.services.implementation_pack import ImplementationPackGenerator
from nexus.services.readability_hud import ReadabilityHUD
from nexus.refactor_governance import RefactorGovernance
from nexus.core.dependency_probe import DependencyProbe

class PlannerPhaseHandler(BasePhaseHandler):
    """
    🔮 Phase P: Planning
    執行風險預判演算法。
    """
    def __init__(self, project_root: Any, run_dir: Any, predictor=None):
        super().__init__(project_root, run_dir, name="P", priority=100)
        from nexus.services.predictor import Predictor
        self.predictor = predictor or Predictor()

    def run(self, state: NexusState, context: Dict[str, Any]) -> Dict[str, Any]:
        task = context.get("task", "")
        print(f"🔮 [Nexus:Predict] Scanning environment for task: {task}")

        # 🎯 P2: 意圖預分類 (Intent Classification)
        classifier = IntentClassifier()
        intent_data = classifier.classify(task)
        intent = intent_data["intent"]
        context["intent"] = intent
        
        # 🛡️ Work Order 1: [SPEC_MODE] Interview
        if intent_data.get("mode") == "spec_mode":
            print(f"\n{ReadabilityHUD.CYAN}🚫 SPEC_MODE ACTIVATED: Interview Required{ReadabilityHUD.RESET}")
            answers = {}
            for q in intent_data["questionnaire"]:
                # User 指令：CLI 現場 input()
                try:
                    ans = input(f"❓ {q} ")
                except EOFError:
                    ans = "auto-filled-by-system"
                answers[q] = ans
            
            context["spec_answers"] = answers
            print(f"{ReadabilityHUD.GREEN}✅ Spec Captured. Proceeding to compilation...{ReadabilityHUD.RESET}\n")

        if intent == "refactor_template":
            print("🖋️ [Refactor:Bias] Applying Linus Mode Governance...")
            context["refactor_plan"] = RefactorGovernance.generate_refactor_plan(
                state.task_id if hasattr(state, "task_id") else "TASK_001", 
                str(self.project_root)
            )
            context["system_bias"] = RefactorGovernance.get_linus_bias()

        # 🛡️ Trinity Intent Guard (PHA-010)
        intent_pass, refusal_reason = self._guard_intent(task)
        if not intent_pass:
            print(f"🛑 [IntentGuard] Refused: {refusal_reason}")
            return {
                "intent_pass": False,
                "refusal_reason": refusal_reason,
                "risk_score": 1.0,
                "risk_level": "BLOCK"
            }

        # 🛰️ P5.2: 依賴圖探針 (DepProbe) 掃描
        # 針對計畫中的 target_files 進行物理依賴感應
        probe = DependencyProbe(str(self.project_root))
        probe.build_index()
        
        # 假設從 context 中取得預計修改的檔案清單 (Mocked targets for P)
        target_files = context.get("target_files", ["main.py"]) 
        impact_map = {}
        max_risk = "LOW"
        
        for t in target_files:
            impact = probe.full_impact(t)
            impact_map[t] = impact
            if impact["risk_level"] == "HIGH":
                max_risk = "HIGH"
                print(f"⚠️ [DepProbe:HIGH] Critical dependency found for {t}. Force RESEARCH.")

        state.metadata["impact_map"] = impact_map
        state.metadata["max_risk_level"] = max_risk
        
        # 🛰️ [NSP:Dispatch] Optimized Node Selection: node_id
        # ...
        node_id = self.route_to_node(task, context.get("codebase", ""))
        print(f"🛰️ [NSP:Dispatch] Optimized Node Selection: {node_id}")

        # 🔮 P10.2 VectorRAG Context Injection (Respect Ablation Switch)
        memory_state = os.environ.get("NEXUS_MEMORY_STATE", "ON")
        if memory_state == "ON":
            try:
                from nexus.core.vector_rag import VectorRAG
                rag = VectorRAG()
                history_hits = rag.query(task, k=5)
                experience_block = rag.format_for_prompt(history_hits)
                if experience_block:
                    print(f"🧠 [RAG:Inject] Context Found. Boosting Pattern Reuse.")
                    context["experience_context"] = experience_block
            except Exception as e:
                print(f"⚠️ [RAG:Fail] Could not inject context: {e}")

            # 🧬 P1-F: Hardened Consensus Lesson Retrieval (Swarm Wisdom)
            try:
                from nexus.services.lesson_retrieval import retrieve_with_resolution
                from nexus.services.planner_enhancer import enhance_planner_context
                resolution = retrieve_with_resolution(
                    Path(self.project_root), 
                    task, 
                    diagnosis=context.get("diagnosis"),
                    use_federated=True
                )
                
                # P2-B: 提取 Hybrid 檢索元數據
                backend = resolution.get("backend_used", "legacy")
                count = resolution.get("metadata", {}).get("candidate_count", 0)
                score = resolution.get("consensus_score", 0.0)
                
                if resolution["status"] == "high_consensus":
                    print(f"🧬 [Consensus:OK] Backend: {backend} | Candidates: {count} | Score: {score:.2f}")
                    context["lesson_context"] = resolution["prompt_context"]
                    state.metadata["lesson_resolution"] = {
                        **resolution.get("metadata", {}),
                        "backend_used": backend,
                        "candidate_count": count,
                        "consensus_status": "high"
                    }
                else:
                    print(f"🧬 [Consensus:Fallback] {resolution['prompt_context']} (Backend: {backend})")
                    state.metadata["lesson_resolution"] = {
                        "status": "low_consensus",
                        "backend_used": backend,
                        "candidate_count": count
                    }
                
                # P2-C: 健康洞察與相似 Bug 修復增強
                if context.get("diagnosis"):
                    from nexus.services.planner_enhancer import enhance_planner_context
                    from scripts.learning.compute_route_weights import load_mock_candidates
                    from nexus.services.swarm_router import select_best_route
                    
                    enhancement = enhance_planner_context(Path(self.project_root), context["diagnosis"], resolution)
                    
                    # P3 Swarm Routing (Gated Mode - P3 Day 2)
                    from nexus.services.policy_gate import apply_policy_gate
                    candidates = load_mock_candidates(Path(self.project_root), self.name)
                    route_decision = select_best_route(candidates)
                    
                    # 執行 Policy Gating (對應 P3 Day 2)
                    health_data = enhancement["health_insights"]
                    # 如果有 metrics 子字典則提取，否則用原字典 (相容模式)
                    actual_metrics = health_data.get("metrics", health_data)
                    
                    gate_decision = apply_policy_gate(
                        route_id=route_decision.selected_route,
                        original_score=route_decision.score,
                        phase=self.name,
                        health_metrics=actual_metrics,
                        repo_root=Path(self.project_root),
                    )
                    
                    # 注入 Prompt Context
                    context["health_enhancement"] = enhancement["prompt_context"]
                    # 豐富化 Metadata 供 P3 審核
                    state.metadata.update({
                        "health_insights": enhancement["health_insights"],
                        "repair_recommendations": enhancement["repair_recommendations"],
                        "swarm_routing": {
                            "selected_route": gate_decision.route_id,
                            "gated_score": gate_decision.gated_score,
                            "decision": gate_decision.decision.value,
                            "signals": [s.__dict__ for s in gate_decision.signals],
                            "backend_used": route_decision.backend_used,
                        },
                        **enhancement["planner_metadata"]
                    })
                    print(f"🌡️ [Health:Alert] Score: {enhancement['planner_metadata']['phase_health_score']:.2f} | 🛡️ Gate: {gate_decision.decision.value.upper()} ({gate_decision.gated_score})")
            except Exception as e:
                print(f"⚠️ [Consensus:Fail] Could not resolve lessons: {e}")
        else:
            print(f"⚪ [RAG:Off] Running Baseline (Ablation Mode).")

        prediction = self.predictor.predict(task, context)
        
        # 🛡️ Work Order B: [Plan-to-Build Compiler] Hook
        # 將預測結果轉化為 6-JSON 硬性施工包 (I-Pack)
        try:
            task_id = state.task_id if hasattr(state, "task_id") else "TASK_UNBOUND"
            generator = ImplementationPackGenerator(Path(self.project_root), task_id)
            print(f"📡 [Compiler:Hook] Compiling Implementation Pack for {task_id}...")
            
            # 將預測中的 goal/models/criteria 整理傳入
            compile_in = {
                "goal": task,
                "data_models": prediction.get("data_models", []),
                "deliverables": prediction.get("deliverables", []),
                "acceptance_criteria": prediction.get("acceptance_criteria", [])
            }
            
            pack_results = generator.generate(compile_in)
            readability_score = pack_results["audit"]["readability_score"]
            
            # ⚖️ [Planner:Handoff] Implementation Readiness Check
            handoff_readiness = readability_score # 基礎分數來自稽核
            if not prediction.get("deliverables"): handoff_readiness -= 20
            if pack_results["audit"]["jargon_count"] > 0: handoff_readiness -= 10
            
            # 啟動帝國 HUD 顯示
            hud = ReadabilityHUD(pack_results["audit"])
            hud.display()
            
            if handoff_readiness < 85:
                msg = f"🛑 [Handoff:REJECTED] Readiness score too low ({handoff_readiness}/100). "
                msg += "Implementation Pack is incomplete or ambiguous. Interview Required."
                return {
                    "intent_pass": False,
                    "refusal_reason": msg,
                    "handoff_readiness": handoff_readiness,
                    "risk_level": "BLOCK"
                }
            
            context["handoff_readiness"] = handoff_readiness
            
        except Exception as e:
            print(f"⚠️ [Compiler:Hook] Failed to generate I-Pack: {e}")

        return {
            "intent_pass": True,
            "best_node": node_id,
            "handoff_readiness": context.get("handoff_readiness", 100),
            "risk_score": prediction["risk_score"], 
            "risks": prediction["reasons"], 
            "risk_level": prediction["risk_level"],
            "tokens_used": prediction.get("tokens_used", 0)
        }

    def route_to_node(self, task_desc: str, codebase: str = "") -> str:
        """🛰️ 執行高維調度。"""
        try:
            from nexus.autopilot.v2_dispatcher import HighDimDispatcher
            dispatcher = HighDimDispatcher(self.project_root)
            return dispatcher.dispatch(task_desc, codebase)
        except Exception as e:
            print(f"⚠️ [Dispatcher] Fallback to LOCAL due to: {e}")
            return "LOCAL_HARDENED"

    def calculate_ambiguity_score(self, task: str) -> float:
        """⚖️ 計算指令歧義性 (Claude-Code Absorption)"""
        score = 0.0
        # 1. 缺乏路徑或檔案名稱
        if "/" not in task and not any(ext in task for ext in [".py", ".ts", ".js", ".md"]):
            score += 0.4
        
        # 2. 包含極度模糊的動詞
        fuzzy_verbs = ["改一下", "修一下", "調整", "處理", "fix", "update", "change"]
        if any(v in task.lower() for v in fuzzy_verbs):
            score += 0.3
        
        # 3. 指令過短
        if len(task) < 15:
            score += 0.2
            
        return min(1.0, score)

    def _guard_intent(self, task: str) -> tuple[bool, str]:
        """🛡️ Clarification Gate: 攔截歧義指令"""
        ambiguity = self.calculate_ambiguity_score(task)
        
        if ambiguity > 0.7:
            msg = f"🛑 [ClarificationGate] 指令歧義度過高 ({ambiguity:.2f})。\n"
            msg += "   Interview Required: 請回答：1. 具體檔案？ 2. 預期輸入輸出？ 3. 測試案例？"
            return False, msg
        
        # 如果是明確的基準測試任務 ID，直接放行
        if task.startswith("OFF-") or task.startswith("FEAT-"):
            return True, ""
            
        return True, ""
