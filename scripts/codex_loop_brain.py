#!/usr/bin/env python3
import sys
import os
import re
import json
import hashlib
import random
import subprocess
import shutil
import time
from pathlib import Path
from datetime import datetime
from typing import List, Optional, Dict, Any

# 導入拆分後的核心模組
from nexus.services.git import GitManager
from nexus.services.llm import LLMClient
from nexus.services.linter import Linter
from nexus.services.patcher import SafePatcher
from nexus.services.reporter import Reporter
from nexus.services.workspace import WorkspaceManager
from nexus.core.escalation import EscalationPolicy, derive_task_metadata
from nexus.core.action_brief import build_action_brief
from nexus.core.router import SkillsRouter
from nexus.core.commander import Commander
from nexus.core.context_hub import ContextHub
from nexus.core.state_io import StateIO
from nexus.core.state_contracts import StepRecord
from nexus.core.orchestrator import NexusOrchestrator

# 配置
REPO_ROOT = Path(__file__).resolve().parents[1]
KB_DIR = os.getenv("MUSE_CORE_KB_DIR", str(REPO_ROOT))
PROMPT_TEMPLATE = REPO_ROOT / "scripts/Templates/developer_prompt_v2.md"
if not PROMPT_TEMPLATE.exists():
    PROMPT_TEMPLATE = Path(KB_DIR) / "01_Operations/Templates/developer_prompt_v2.md"

BRAIN_SEARCH_BIN = os.getenv("MUSE_CORE_BRAIN_SEARCH", "/usr/local/bin/brain_search")
UV_BIN = shutil.which("uv") or "uv"

class CodexLoopV2(NexusOrchestrator):
    """
    🧬 Codex-Loop v2.0: Modular Intelligence Orchestrator (V5 Steel Edition)
    """
    def __init__(self, **kwargs):
        git = kwargs.get("git") or GitManager(project_root=str(REPO_ROOT))
        llm = kwargs.get("llm") or LLMClient()
        linter = kwargs.get("linter") or Linter()
        patcher = kwargs.get("patcher") or SafePatcher(lock_dir="/tmp", project_root=str(REPO_ROOT))
        reporter = kwargs.get("reporter") or Reporter()
        workspace = kwargs.get("workspace") or WorkspaceManager(project_root=str(REPO_ROOT))
        router = kwargs.get("router") or SkillsRouter(project_root=str(REPO_ROOT))
        context_hub = kwargs.get("context_hub") or ContextHub(project_root=str(REPO_ROOT))
        state_io = kwargs.get("state_io") or StateIO(project_root=str(REPO_ROOT))
        commander = kwargs.get("commander") or Commander(run_dir=str(REPO_ROOT), state_io=state_io, router=router, context_hub=context_hub)
        escalation_policy = kwargs.get("escalation_policy") or EscalationPolicy()

        super().__init__(
            task=kwargs.get("task", ""),
            skill_id=kwargs.get("skill_id", "writing-plans"),
            mode=kwargs.get("mode", "developer"),
            git=git,
            llm=llm,
            linter=linter,
            patcher=patcher,
            reporter=reporter,
            workspace=workspace,
            router=router,
            commander=commander,
            context_hub=context_hub,
            state_io=state_io
        )
        self.escalation_policy = escalation_policy
        self.apply_patch = kwargs.get("apply_patch", False)
        self.isolated = kwargs.get("isolated", False)
        self.bypass_circuit_breaker = kwargs.get("bypass_circuit_breaker", False)
        self.executor = kwargs.get("executor")
        self.legacy_path_enabled = kwargs.get("legacy_path_enabled", True)
        self.reviewer_mode = kwargs.get("reviewer_mode", "codex")
        self.allow_core_mutation = kwargs.get("allow_core_mutation", False)
        self.privileged_context_files = kwargs.get("initial_files", [])

        # 模式鎖
        if self.executor:
            self.legacy_path_enabled = False
            print("🛡️ [Hardening] Executor mode active. Legacy path lock: ENGAGED.")
        
        if self.skill_id == "core-repair":
            self.allow_core_mutation = True
            print("💎 [Privilege] Core mutation enabled for core-repair skill.")

        self.history_hashes = set()
        self.total_tokens = 0
        self.scope = kwargs.get("scope", "staged")
        self.base_ref = kwargs.get("base_ref", "main")
        self.report_file = self.project_root / "logs/report.md"
        self.action_file = self.project_root / "logs/action.json"
        self.transcripts_dir = self.project_root / "logs/transcripts"
        self.transcripts_dir.mkdir(parents=True, exist_ok=True)
        self.skills_router = self.router
        self._apply_persona_profile(self.mode)

    def init_preflight_check(self, benchmark_mode: bool = False) -> bool:
        """
        [Phase 1 Gate] 在 run_review() 之前驗證所有必要依賴。
        如果任何必要欄位缺失，立即 raise RuntimeError('INIT_CONTRACT_ERROR')。
        """
        errors = []

        # 必要欄位（所有模式）
        required = {
            "git": self.git,
            "project_root": getattr(self, "project_root", None),
            "skills_router": getattr(self, "skills_router", None),
            "persona_hint": getattr(self, "persona_hint", None),
            "transcripts_dir": getattr(self, "transcripts_dir", None),
            "action_file": getattr(self, "action_file", None),
            "escalation_policy": getattr(self, "escalation_policy", None),
        }
        for name, val in required.items():
            if val is None:
                errors.append(f"  MISSING: {name}")

        # Benchmark 模式額外要求
        if benchmark_mode:
            if self.executor is None:
                errors.append("  MISSING: executor (benchmark mode requires GeminiExecutor)")
            if not self.legacy_path_enabled is False:
                # 這裡檢查時要小心 boolean 邏輯，在 __init__ 中 executor 存在時會設 False
                if self.legacy_path_enabled:
                    errors.append("  VIOLATION: legacy_path_enabled must be False in benchmark mode")
            if not getattr(self.git, "project_root", None):
                errors.append("  SERVICE_WIRING_ERROR: git.project_root is None")

        if errors:
            msg = "INIT_CONTRACT_ERROR — Missing required fields:\n" + "\n".join(errors)
            print(f"❌ [Preflight] {msg}")
            raise RuntimeError(msg)

        print(f"✅ [Preflight] All dependency contracts satisfied. benchmark_mode={benchmark_mode}")
        return True

    def _apply_persona_profile(self, mode):
        if mode == "safe-commit":
            self.max_strikes = 2
            self.persona_hint = "👤 MODE: SAFE-COMMIT"
        elif mode == "agent-shield":
            self.max_strikes = 3
            self.apply_patch = True
            self.persona_hint = "👤 MODE: AGENT-SHIELD"
        elif mode == "audit":
            self.max_strikes = 1
            self.persona_hint = "👤 MODE: FINAL-AUDIT"
        else:
            self.max_strikes = 3
            self.persona_hint = "👤 MODE: DEVELOPER"

    def _get_lessons(self, query=None):
        lessons = []
        sub_file = Path(KB_DIR) / "00_System_Knowledge/01_Operations/04_Subconscious_Memory.md"
        if sub_file.exists():
            content = sub_file.read_text(encoding="utf-8")
            if "<muse_subconscious>" in content:
                extracted = content.split("<muse_subconscious>")[1].split("</muse_subconscious>")[0]
                lessons.append(f"--- Global Subconscious ---\n{extracted.strip()}")
        
        local_lessons = Path(self.git.project_root) / ".codex_lessons.md"
        if local_lessons.exists():
            lessons.append(f"--- Project Lessons ---\n{local_lessons.read_text(encoding='utf-8')}")

        if query and os.path.exists(BRAIN_SEARCH_BIN):
            dynamic = self._get_dynamic_lessons(query)
            if dynamic: lessons.append(dynamic)
        return "\n\n".join(lessons)

    def _get_dynamic_lessons(self, query):
        try:
            cmd = [UV_BIN, "run", "--with", "lancedb", "--with", "pandas", BRAIN_SEARCH_BIN, query[:200]]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            if res.returncode == 0: return f"--- Dynamic Experience Recall ---\n{res.stdout.strip()}"
        except Exception: pass
        return None

    def _get_aesthetic_rules(self, files):
        ui_exts = {".html", ".css", ".js", ".ts", ".tsx", ".jsx", ".vue"}
        if not any(Path(f).suffix in ui_exts for f in files): return ""
        ui_taste_path = Path(KB_DIR) / "00_System_Knowledge/02_Arsenal/Skills_Library/ui_taste.md"
        if ui_taste_path.exists():
            return f"\n🎨 **[AESTHETIC SHIELD] UI Detected!**\n{ui_taste_path.read_text()}\n"
        return ""

    def _is_reviewable(self, file_path):
        if file_path.endswith(".py"): return True
        if not file_path.endswith(".md"): return False
        kb_marker = os.path.join(self.git.project_root, "知識庫")
        if not os.path.isdir(kb_marker): return True
        brain_prefixes = ["00_System_Knowledge/", "01_Operations/", "02_Arsenal/"]
        return any(file_path.startswith(p) or "/"+p in file_path for p in brain_prefixes)

    def _export_report(self, data):
        try:
            self.reporter.write_markdown_report(self.report_file, data, total_tokens=self.total_tokens)
            self.reporter.write_action_sidecar(self.action_file, data)
        except Exception: pass

    def run_review(self, manual_files=None):
        if self.isolated:
            return self._run_isolated_review(manual_files)
        return self._do_review(manual_files)

    def _run_isolated_review(self, manual_files):
        task_id, branch, sandbox_path = self.workspace_manager.lease()
        if not task_id: return False
        try:
            self.workspace_manager.sync_staged_to_sandbox(sandbox_path)
            sandbox_engine = CodexLoopV2(mode=self.mode, scope="all", apply_patch=self.apply_patch, base_ref="HEAD")
            original_cwd = os.getcwd()
            os.chdir(sandbox_path)
            try:
                passed = sandbox_engine._do_review(manual_files)
            finally:
                os.chdir(original_cwd)
            if passed: return self.workspace_manager.harvest(branch, sandbox_path)
            return False
        finally:
            self.workspace_manager.cleanup(task_id, branch)

    def _do_review(self, manual_files=None) -> str:
        print(f"🔍 [v2.0] Mode: {self.mode} | Scope: {self.scope}")
        original_cwd = os.getcwd()
        os.chdir(self.git.project_root)
        strike = 0
        any_patch_generated = False
        patch_apply_failed = False
        final_tier = "FAIL" 

        try:
            for strike in range(1, self.max_strikes + 1):
                print(f"🚀 [Round {strike}/{self.max_strikes}] Initiating Audit...")

                if self.task and strike == 1:
                    print(f"🎯 [Task Mode] Goal: {self.task}")
                    self._run_v5_p_stage(self.skill_id or "writing-plans", {"summary": self.task})

                privileged_abs = [str(Path(x).resolve()) for x in self.privileged_context_files if Path(x).is_file()]
                if manual_files:
                    diff_discovered_files = [str(Path(f).resolve()) for f in manual_files if Path(f).is_file()]
                    diff_text = "Manual Review Mode"
                else:
                    files_raw, diff_text = self.git.get_changes(self.scope, self.base_ref)
                    diff_discovered_files = [str(Path(self.git.project_root).joinpath(f).resolve()) for f in (files_raw or [])]
                
                all_candidates = list(set(privileged_abs + diff_discovered_files))
                files = [f for f in all_candidates if self._is_reviewable(f)]
                code_files = [f for f in files if f.endswith(".py")]

                if not code_files and (not diff_text or not diff_text.strip()):
                    print("✅ [SKIPPED] No significant changes found.")
                    return "CONTINUITY_PASS"

                linter_json = self.linter.scan(code_files)
                lessons = self._get_lessons(query=diff_text)
                aesthetic_hint = self._get_aesthetic_rules(manual_files or files)
                full_prompt = f"{self.persona_hint}\n{aesthetic_hint}\nLESSONS:\n{lessons}\nLINTER:\n{linter_json}\n"

                data = {}
                raw_output = ""

                if self.executor:
                    from nexus.executors.protocol import ExecutorInput, ContextPackSchema, TaskInstruction
                    context_files = {str(Path(f).resolve()): Path(f).read_text(errors="ignore") for f in files if Path(f).is_file()}
                    
                    if isinstance(linter_json, str):
                        l_errors = json.loads(linter_json) if linter_json.startswith("[") else []
                    else:
                        l_errors = linter_json if isinstance(linter_json, list) else []

                    exec_input = ExecutorInput(
                        task_id=getattr(self, "task_id", "nexus-v5"),
                        phase="R" if strike > 1 or self.task else "P",
                        workspace_root=str(self.git.project_root),
                        context_pack=ContextPackSchema(files=context_files, linter_errors=l_errors, history=list(self.history_hashes)),
                        instruction=TaskInstruction(task_id="review-task", objective=self.task or "Review code")
                    )
                    
                    print(f"🧠 [Invariant] Calling Executor. Context Size: {len(context_files)} files.")
                    exec_output = self.executor.execute(exec_input)
                    
                    # Contamination Guard
                    touched = [str(Path(f).resolve()) for f in exec_output.files_touched]
                    core_roots = [str(Path(self.git.project_root)/'nexus'), str(Path(self.git.project_root)/'scripts')]
                    if any(f.startswith(tuple(core_roots)) for f in touched) and not self.allow_core_mutation:
                        raise RuntimeError("BENCHMARK_CONTAMINATED")

                    exec_status = exec_output.status.name
                    has_patch = exec_output.patch_generated
                    p_diff = exec_output.patch_diff
                    
                    data = {
                        "status": "PASS" if exec_status == "SUCCESS" else "FAIL",
                        "summary": exec_output.summary,
                        "violations": [{"patch": p_diff}] if has_patch else [],
                        "tokens_used": exec_output.meta.get("tokens_output", 0),
                        "provider_error_type": exec_output.provider_error_type.name if exec_output.provider_error_type else None
                    }

                    if exec_status == "SUCCESS":
                        if has_patch: any_patch_generated = True
                        
                        if not has_patch:
                            if any_patch_generated and not patch_apply_failed:
                                reviewer_status = "unavailable"
                                if self.reviewer_mode == "none": reviewer_status = "disabled"
                                elif self.reviewer_mode == "codex":
                                    print("🔍 [Reviewer] Engaging optional Codex reviewer for Tier verification...")
                                    try:
                                        rev_prompt = f"Review Task: {self.task}\nReview patch. Reply JSON: {{\"status\": \"PASS\" | \"FAIL\"}}"
                                        rev_data, _ = self.llm.ask(rev_prompt, None, phase="Review")
                                        reviewer_status = "passed" if rev_data.get("status") == "PASS" else "rejected"
                                    except Exception as e:
                                        print(f"⚠️ [Reviewer] Error: {e}. Degrading to SOFT_PASS.")
                                        reviewer_status = "unavailable"
                                
                                if reviewer_status == "passed": final_tier = "HARD_PASS"
                                elif reviewer_status == "rejected": final_tier = "FAIL"
                                else: final_tier = "SOFT_PASS"
                            else:
                                final_tier = "CONTINUITY_PASS"
                            
                            data["assurance_tier"] = final_tier
                            break # Successful termination
                        else:
                            final_tier = "FAIL"
                    else:
                         final_tier = "FAIL"
                    
                    data["assurance_tier"] = final_tier
                    raw_output = exec_output.summary
                else:
                    if self.executor: raise RuntimeError("Barrier: Legacy path blocked.")
                    print(f"🧠 Calling LLM for Cognitive Review (Strike {strike})...")
                    data, raw_output = self.llm.ask(full_prompt, diff_text, phase="P")
                    if data.get("status") == "PASS":
                        final_tier = "SOFT_PASS"
                        break

                self.total_tokens += data.get("tokens_used", 0)
                suggestions_hash = hashlib.md5(json.dumps(data.get("violations", []), sort_keys=True).encode()).hexdigest()
                if suggestions_hash in self.history_hashes:
                    print(f"⚠️ [STUCK] Strike {strike}. Breaking.")
                    self._export_report(data)
                    return "FAIL"
                self.history_hashes.add(suggestions_hash)

                if data.get("status") == "FAIL":
                    task = derive_task_metadata(files, diff_text)
                    decision = self.escalation_policy.decide(
                        attempt=strike, 
                        task=task, 
                        failure_summary=data.get("summary", ""),
                        repeated_failure=strike > 1
                    )
                    brief = build_action_brief(
                        decision=decision, 
                        task=task, 
                        failure_summary=data.get("summary", ""), 
                        files=files,
                        violations=data.get("violations", [])
                    )
                    
                    self._print_escalation_decision(decision)
                    self._export_report(data)

                    if self.apply_patch:
                        print("🛠️ Applying auto-patches...")
                        try:
                            self.patcher.apply(data.get("violations", []))
                        except Exception as e:
                            print(f"❌ Patch failed: {e}")
                            patch_apply_failed = True
                            return "FAIL"
                        continue
                    else:
                        return "FAIL"

            print(f"🎉 [PASSED] Cognitive security check cleared. Final Tier: {final_tier}")
            return final_tier
        finally:
            if self.total_tokens > 0: print(f"\n📊 [Usage] Total Session Tokens: {self.total_tokens:,}")
            os.chdir(original_cwd)

    def _run_v5_p_stage(self, skill_path: str, context: dict):
        print(f"🧬 [v5 P-stage] Initializing {skill_path}...")
        plan_data = {"plan_id": f"nexus-{int(time.time())}", "goal": context.get("summary"), "metadata": {"skill": skill_path}}
        plan_file = Path(self.git.project_root) / "plan.json"
        with open(plan_file, "w", encoding="utf-8") as f: json.dump(plan_data, f, indent=4)
        print(f"📝 [v5 Pilot] plan.json crystallized.")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("files", nargs="*", help="Files to review")
    parser.add_argument("--mode", default="developer", choices=["developer", "safe-commit", "agent-shield", "audit"])
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--isolated", action="store_true")
    parser.add_argument("--base", default="HEAD")
    parser.add_argument("--task", default=None)
    parser.add_argument("--benchmark", action="store_true")
    parser.add_argument("--reviewer", default="codex", choices=["codex", "none"])
    parser.add_argument("--executor", default="gemini", choices=["gemini", "antigravity"])
    args = parser.parse_args()

    executor = None
    if args.benchmark:
        if args.executor == "gemini":
            from nexus.executors.gemini import GeminiExecutor
            executor = GeminiExecutor()
        elif args.executor == "antigravity":
            from nexus.executors.antigravity import AntigravityExecutor
            executor = AntigravityExecutor()

    engine = CodexLoopV2(mode=args.mode, apply_patch=args.apply, isolated=args.isolated, base_ref=args.base, task=args.task, executor=executor, reviewer_mode=args.reviewer)
    sys.exit(0 if engine.run_review(args.files) else 1)
