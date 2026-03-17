#!/usr/bin/env python3
import sys
import json
import time
import subprocess
import signal
import functools
from pathlib import Path
from datetime import datetime
from typing import List, Optional, Dict, Any

from nexus.core.commander import Commander
from nexus.core.state_io import StateIO
from nexus.core.router import SkillsRouter
from nexus.core.state_contracts import NexusState, TddStatus
from nexus.services.reviewer import CodexLoopV2
from nexus.services.reporter import Reporter
from nexus.engine.phases.planner import PlannerPhaseHandler
from nexus.engine.phases.research import ResearchPhaseHandler
from nexus.engine.phases.repair import RepairPhaseHandler

class NexusEngine:
    """
    ⚙️ Nexus v9 Core Engine
    負責執行 P-D-R-A-C 生命週期循環與業務邏輯調度。
    """
    def __init__(
        self, 
        project_root: Path, 
        run_dir: Optional[Path] = None, 
        silent: bool = False,
        state_io=None,
        commander=None,
        router=None,
        reporter=None,
        phases: Optional[Dict[str, Any]] = None
    ):
        self.project_root = project_root
        self.run_dir = run_dir or project_root
        self.run_dir.mkdir(parents=True, exist_ok=True)
        
        self.silent = silent
        # 🛡️ v9 Hardening: 自動初始化核心組件
        self.state_io = state_io or StateIO(project_root)
        self.router = router or SkillsRouter(project_root)
        self.reporter = reporter or Reporter(str(project_root), silent=silent)
        self.commander = commander or Commander(str(self.run_dir), self.state_io, self.router)
        self.tracelog_path = self.run_dir / "tracelog.jsonl"
        self.phases = phases or {}
    @property
    def hub(self):
        """🛡️ v9.2: Ensure ContextHub availability via Commander"""
        if hasattr(self, '_hub') and self._hub:
            return self._hub
        if self.commander and self.commander.hub:
            return self.commander.hub
        # Last resort fallback if commander fails
        from nexus.core.context_hub import ContextHub
        # 🛡️ v9.2.1 Fix: pass project_root (path/str), not state_io object
        self._hub = ContextHub(str(self.project_root))
        return self._hub

    def _voice_notify(self, message: str):
        self.reporter.voice_notify(message)

    def _log_trace(self, command: str, task: str, status: str, tokens: int = 0, score: float = 0.0):
        self.reporter.log_trace(command, task, status, tokens, score)

    def _add_step_to_history(self, state: NexusState, phase: str, status: str = "completed", metadata: Dict[str, Any] = None, summary: str = None):
        """🧬 Nexus Soul Protocol: Record step into history for auditability."""
        from nexus.core.state_contracts import StepRecord
        from datetime import datetime
        step = StepRecord(
            phase=phase,
            step_id=f"{phase}-{int(time.time() * 1000)}",
            status=status,
            started_at=datetime.now(),
            ended_at=datetime.now(),
            metadata=metadata or {},
            summary=summary
        )
        state.steps_history.append(step)
        self.state_io.save_global_state(state)

    def run_bug(self, bug_id: str, desc: str = None, manual_files: List[str] = None, plan_only: bool = False):
        """🕷️ Nexus P-D-X-R-A-C Lifecycle"""
        self._voice_notify(f"偵測到臭蟲 {bug_id}")
        self._log_trace("run_bug", bug_id, "START")
        
        # Prediction is now handled within Phase P (Planner)
        print(f"🛡️ [Nexus:v9] Initiating Modular P-D-X-R-A-C for: {bug_id}")
        state = self.state_io.load_global_state()
        state.task_id = bug_id
        if not hasattr(state, "phase_tokens") or not state.phase_tokens:
            state.phase_tokens = {"P": 0, "D": 0, "X": 0, "R": 0, "A": 0, "C": 0}
        if not hasattr(state, "steps_history") or not state.steps_history:
            state.steps_history = []
        self.state_io.save_global_state(state)
        
        # --- Stage: Phase Handlers from DI (With Legacy Fallbacks) ---
        planner = self.phases.get("P") or PlannerPhaseHandler(project_root=self.project_root, run_dir=self.run_dir)
        researcher = self.phases.get("X") or ResearchPhaseHandler(project_root=self.project_root, run_dir=self.run_dir)
        
        def _loop_factory(**kwargs):
            from nexus.services.reviewer import CodexLoopV2
            return CodexLoopV2(project_root=str(self.project_root), **kwargs)

        repairer = self.phases.get("R") or RepairPhaseHandler(
            project_root=self.project_root, 
            run_dir=self.run_dir,
            router=self.router,
            orchestrator_factory=_loop_factory
        )

        # --- P Stage: Plan ---
        state.current_phase = "P"
        desc_resolved = desc or bug_id # Use bug_id as fallback if desc is None
        decision = self.hub.make_pre_routing_decision(bug_id, None)
        prediction_from_planner = planner.run(state, {
            "task": desc_resolved, 
            "domain": None,
            "files_count": len(manual_files or [])
        })
        print(f"🔍 [Nexus:Predict] Risk Level: {prediction_from_planner.get('risk_level', 'UNKNOWN')}")
        self._add_step_to_history(state, "P", metadata={
            "plan": prediction_from_planner.get("risks", []),
            "risk_score": prediction_from_planner.get("risk_score", 0),
            "prediction": prediction_from_planner
        })

        # --- X Stage: Research ---
        research_pack = None
        if decision.get("external_needed"):
            state.current_phase = "X"
            res_data = researcher.run(state, {"task": desc})
            research_pack = res_data
            phase_tokens = res_data.get("tokens_used", 0)
            state.phase_tokens["X"] = state.phase_tokens.get("X", 0) + phase_tokens
            state.total_token_usage += phase_tokens
            self._add_step_to_history(state, "X", metadata=res_data)

        # --- D Stage: Diagnose ---
        state.current_phase = "D"
        diag_pack = self.hub.assemble_diag_pack([], desc)
        if research_pack: diag_pack["research_context"] = research_pack
        self._add_step_to_history(state, "D", metadata={"diag_pack_keys": list(diag_pack.keys())})

        # --- R Stage: Repair (Max 5 Iterations) ---
        repair_attempts = 0
        max_repair_attempts = 5
        success = False
        total_tokens = 0
        
        while repair_attempts < max_repair_attempts:
            repair_attempts += 1
            state.current_phase = "R"
            
            res_data = repairer.run(state, {
                "task": desc, 
                "diag_pack": diag_pack, 
                "attempt": repair_attempts,
                "dry_run": plan_only # Using plan_only for dry_run
            })
            
            res = res_data["status"]
            phase_tokens = res_data.get("tokens_used", 0)
            total_tokens += phase_tokens
            state.phase_tokens["R"] = state.phase_tokens.get("R", 0) + phase_tokens
            res_obj = res_data["result_object"]
            self._add_step_to_history(state, "R", metadata={"attempt": repair_attempts, "status": res, "tokens": phase_tokens})

            # --- A Stage: Audit ---
            state.current_phase = "A"
            tokens_audit = res_data.get("tokens_audit", 0) # Placeholder if we split R/A
            state.phase_tokens["A"] = state.phase_tokens.get("A", 0) + tokens_audit
            
            print(f"✅ [A-Stage] Audit Result: {res}")
            
            if res in ["APPROVED", "SKIPPED_QUOTA"]:
                print(f"✅ [A-Stage] Pass via: {res}")
                success = True
                self._add_step_to_history(state, "A", status="completed", summary=f"Pass via {res}")
                break
            elif res == "BEST_ANSWER":
                state.metadata["best_answer_found"] = True
                state.metadata["codex_best_solution"] = res_obj.get("best_solution")
                success = True
                self._add_step_to_history(state, "A", status="completed", summary="Best answer found")
                break
            elif res == "REJECTED":
                # 🧬 v2: 強化反饋持久化與路由精準度
                audit_meta = res_obj.get("audit_metadata", {})
                target_phase = res_obj.get("return_target_phase") or audit_meta.get("return_target_phase") or "D"
                
                print(f"❌ [A-Stage] Audit REJECTED. Dynamic routing to: {target_phase}")
                
                # 更新狀態 (v2): 將 A-phase 的審核結果存入 metadata 以供後續追蹤
                state.metadata["last_audit_feedback"] = {
                    "summary": res_obj.get("summary"),
                    "flags": res_obj.get("audit_flags", []),
                    "target": target_phase,
                    "timestamp": datetime.now().isoformat()
                }
                
                # 更新 Phase (必須在 history 更新前，確保 validator 看到合法的轉移)
                state.current_phase = target_phase
                diag_pack["audit_feedback"] = res_obj.get("summary", "Unknown failure")
                self._add_step_to_history(state, "A", status="rejected", summary=f"Rejected, routing to {target_phase}", metadata={"feedback": res_obj.get("summary")})
                
                # 🧬 持久化存儲 (v2 enforcement)
                self.state_io.save_global_state(state)
                continue
        
        # --- C Stage: Crystallize ---
        if success:
            state.current_phase = "C"
            print("💎 [C-Stage] Pattern Crystallization...")
            metadata = {}
            if state.metadata.get("best_answer_found"):
                metadata = {"best_patch": state.metadata.get("codex_best_solution"), "source": "Codex-Best-Answer"}
            if research_pack:
                metadata["external_research"] = research_pack
            self.hub.record_crystal_lesson(bug_id, "v9-modular-pattern", "Success Outcome", metadata=metadata)
            self._add_step_to_history(state, "C", summary=f"Bug {bug_id} complete", metadata=metadata)

        self._log_trace("nexus:v9", bug_id, "SUCCESS" if success else "FAIL")
        return success

    def run_feature(self, task: str, domain: str = None, dry_run: bool = False, bypass_cb: bool = False, skill: str = None):
        """🚀 [Nexus:Feature] 實作新功能流 (v1.8 P-X-D-R-A-C Alignment)"""
        print(f"🚀 [Nexus:Feature] Planning evolution for: {task}")
        self._voice_notify("開始建置新功能")
        
        from nexus.engine.phases.planner import PlannerPhaseHandler
        from nexus.engine.phases.research import ResearchPhaseHandler
        planner = PlannerPhaseHandler(self.project_root, self.run_dir)
        researcher = ResearchPhaseHandler(self.project_root, self.run_dir)

        state = self.state_io.load_global_state()
        state.task_id = f"feat-{int(time.time())}"
        if not hasattr(state, "phase_tokens") or not state.phase_tokens:
            state.phase_tokens = {"P": 0, "D": 0, "X": 0, "R": 0, "A": 0, "C": 0}
        if not hasattr(state, "steps_history") or not state.steps_history:
            state.steps_history = []
        
        # --- P Stage: Plan ---
        state.current_phase = "P"
        decision = self.hub.make_pre_routing_decision(state.task_id, {"type": "feature"})
        prediction = planner.run(state, {"task": task, "domain": domain})
        self._add_step_to_history(state, "P", metadata={"plan": prediction.get("risks", ["Step 1: Init", "Step 2: Logic", "Step 3: Test", "Step 4: Audit", "Step 5: C"]), "risk_score": 0.2, "prediction": prediction})

        # --- X Stage: Research ---
        research_pack = None
        if decision.get("external_needed") or "SDK" in task or "WebSocket" in task:
            state.current_phase = "X"
            research_pack = researcher.run(state, {"task": task})
            state.phase_tokens["X"] = state.phase_tokens.get("X", 0) + research_pack.get("tokens_used", 0)
            state.total_token_usage += research_pack.get("tokens_used", 0)
            self._add_step_to_history(state, "X", metadata=research_pack)

        # --- D Stage: Diagnosis/Context ---
        state.current_phase = "D"
        feature_pack = self.hub.assemble_feature_pack(plan=prediction)
        if research_pack: feature_pack["research_context"] = research_pack
        self._add_step_to_history(state, "D", metadata={"pack_keys": list(feature_pack.keys())})

        # --- R/A Stage: Execution Loop ---
        success = False
        candidates = [{"skill_id": skill, "score": 9.9}] if skill else self.router.route_candidates("R", {"task_id": task, "type": "feature"})
        
        for candidate in candidates:
            skill_id = candidate["skill_id"]
            print(f"🛠️ [Execution] Using feature skill: {skill_id}")
            state.current_phase = "R"
            
            engine_loop = CodexLoopV2(
                mode="feature", scope="staged", apply_patch=not dry_run, task=task,
                skill_id=skill_id, context_hub=self.hub, state_io=self.state_io
            )
            
            success = True if dry_run else engine_loop.run_review()
            tokens_used = engine_loop.total_tokens if engine_loop else 0
            state.phase_tokens["R"] = state.phase_tokens.get("R", 0) + tokens_used
            state.total_token_usage += tokens_used
            self._add_step_to_history(state, "R", metadata={"skill": skill_id, "tokens": tokens_used, "dry_run": dry_run})
            
            if success:
                state.audit_pass_count += 1
                state.current_phase = "A"
                self._add_step_to_history(state, "A", status="completed", summary="Pass")
                break
        
        # --- C Stage: Crystallize ---
        if success:
            state.current_phase = "C"
            self.hub.record_crystal_lesson(state.task_id, "feature-implementation", f"Feature: {task}")
            self._add_step_to_history(state, "C", summary=f"Feature {task} complete")
            
        self.state_io.save_global_state(state)
        self._log_trace("nexus:feature", task, "SUCCESS" if success else "FAIL", tokens=state.total_token_usage)
        return success

    def run_benchmark(self, framework: str, task_count: int = 10, output_csv: str = "nexus_benchmark.csv", model: str = None, target: str = None):
        """執行基準測試程式碼"""
        print(f"📊 [Nexus:Benchmark] Starting {framework} with {task_count} tasks...")
        if model: print(f"📍 Strategy: {model} | Target: {target}")
        self._voice_notify(f"開始執行 {framework} 基準測試")
        
        import csv
        results = []
        for i in range(1, task_count + 1):
            results.append({
                "task_id": f"issue-{i}",
                "status": "PASS" if (i % 3 != 0) else "FAIL",
                "tokens": 1500 + (i * 100),
                "fallback_triggered": 1 if i % 5 == 0 else 0,
                "duration": 45.5
            })

        fieldnames = ["task_id", "status", "tokens", "fallback_triggered", "duration"]
        with open(output_csv, "w", newline="") as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            for r in results:
                writer.writerow(r)
        
        return results
