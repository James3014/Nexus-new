import sys
import os
import re
import json
import hashlib
import random
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
UV_BIN = "uv"

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
                errors.append("  MISSING: executor (benchmark mode requires a valid ExecutorAdapter)")
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

        print("✅ [Preflight] Core contract satisfied.")
        return True

    def _print_escalation_decision(self, decision):
        print(
            f"🧭 [Escalation] next_action={decision.action} actor={decision.actor} reasons={','.join(decision.reason_codes)}"
        )

    def _print_action_brief(self, brief):
        print(f"📝 [Action Brief] {brief.title}")
        print(f"   actor={brief.actor}")
        print(f"   instructions={brief.instructions}")
        if brief.context:
            for key, value in brief.context.items():
                if value:
                    print(f"   {key}={value}")

    def _apply_persona_profile(self, mode):
        # [V5 Steel] Benchmark Lock
        is_benchmark = getattr(self, "executor", None) is not None
        
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
            
        if is_benchmark:
            self.max_strikes = 1
            print("🔒 [Steel Discipline] Benchmark mode detected. Strikes locked to 1.")

    def _determine_final_tier(
        self,
        *,
        patch_generated: bool,
        patch_apply_failed: bool,
        verification_passed: bool,
        reviewer_status: str,  # "passed", "rejected", "unavailable", "disabled"
        is_contaminated: bool = False
    ) -> str:
        """
        🧬 V5 Steel Tier 判定規則 (寫死於 Core)。
        """
        if is_contaminated:
            return "BENCHMARK_CONTAMINATED"

        # 1. HARD_PASS
        if (
            patch_generated
            and not patch_apply_failed
            and verification_passed
            and self.reviewer_mode == "codex"
            and reviewer_status == "passed"
        ):
            return "HARD_PASS"

        # 2. SOFT_PASS
        if (
            patch_generated
            and not patch_apply_failed
            and verification_passed
            and (self.reviewer_mode == "none" or reviewer_status == "unavailable" or reviewer_status == "disabled")
        ):
            return "SOFT_PASS"

        # 3. CONTINUITY_PASS
        if not patch_generated and not patch_apply_failed and verification_passed:
            return "CONTINUITY_PASS"

        # 4. FAIL (預設)
        return "FAIL"

    def _verify_work(self, code_files: List[str], touched_files: List[str] = None) -> bool:
        """
        🧬 [Core Orchestration] 主動驗證。
        即使 Executor 回報成功，Core 仍需執行 Linter 與測試稽核。
        """
        print("🧪 [Verifier] Core-driven verification initiated...")
        
        # 掃描目標檔案與 Executor 觸碰到的檔案
        scan_scope = list(set(code_files + (touched_files or [])))
        linter_json = self.linter.scan(scan_scope)
        
        # 如果 Linter 有錯誤且非忽略項目，則視為不通過
        if isinstance(linter_json, list) and len(linter_json) > 0:
            print(f"   ❌ Linter failed: {len(linter_json)} issues in {scan_scope}")
            return False
        
        return True

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
        # [Security] Subprocess disabled in V5 Steel
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

    def run_review(self, manual_files=None, self_test=False):
        """
        🧬 [Phase 1] Engage Preflight and Route.
        """
        if self_test:
            return self.run_self_test()

        self.init_preflight_check(benchmark_mode=bool(self.executor))
        
        if self.isolated:
            return self._run_isolated_review(manual_files)
        return self._do_review(manual_files)

    def run_self_test(self) -> bool:
        """
        🛡️ [Pre-Trial Validation] 執行 L1-L5 系統完整性自檢。
        """
        print("\n" + "="*50)
        print("🚀 [Nexus Self-Test] Starting 5-Level Integrity Check...")
        print("="*50)
        
        from unittest.mock import MagicMock
        from nexus.executors.protocol import ExecutorOutput, ExecutorStatusEnum, ProviderErrorType
        
        # 備份原始組件
        orig_executor = self.executor
        orig_llm = self.llm
        orig_patcher = self.patcher
        orig_linter = self.linter
        
        results = []
        
        try:
            # --- L1: Executor Dry Run (Mock Patch) ---
            print("\n🔹 [Level 1] Executor Dry Run (Mock Patch)")
            self.executor = MagicMock()
            self.executor.execute.return_value = ExecutorOutput(
                executor_name="mock_l1", phase="P", status=ExecutorStatusEnum.SUCCESS,
                patch_generated=True, patch_diff="--- a/dummy.txt\n+++ b/dummy.txt\n@@\n-test\n+test",
                files_touched=["dummy.txt"], evidence_present=True, raw_exit_code=0,
                summary="L1 Success", meta={"tokens_output": 100}
            )
            self.patcher = MagicMock()
            self.patcher.apply.return_value = True
            self.linter = MagicMock()
            self.linter.scan.return_value = []
            self.reviewer_mode = "none"
            
            tier = self._do_review(manual_files=["dummy.txt"])
            l1_pass = tier == "SOFT_PASS"
            results.append(("L1: Dry Run", l1_pass))
            print(f"   Result Tier: {tier} -> {'✅ PASS' if l1_pass else '❌ FAIL'}")

            # --- L2: No-Patch Continuity ---
            print("\n🔹 [Level 2] No-Patch Continuity")
            self.executor.execute.return_value = ExecutorOutput(
                executor_name="mock_l2", phase="P", status=ExecutorStatusEnum.SUCCESS,
                patch_generated=False, files_touched=[], evidence_present=True, raw_exit_code=0,
                summary="L2 Success", meta={"tokens_output": 50}
            )
            tier = self._do_review()
            l2_pass = tier == "CONTINUITY_PASS"
            results.append(("L2: Continuity", l2_pass))
            print(f"   Result Tier: {tier} -> {'✅ PASS' if l2_pass else '❌ FAIL'}")

            # --- L3: Reviewer Gate (Mock 429) ---
            print("\n🔹 [Level 3] Reviewer Gate (Mock 429)")
            self.reviewer_mode = "codex"
            self.executor.execute.return_value = ExecutorOutput(
                executor_name="mock_l3", phase="P", status=ExecutorStatusEnum.SUCCESS,
                patch_generated=True, patch_diff="diff", files_touched=["test.py"],
                evidence_present=True, raw_exit_code=0, summary="L3", meta={"tokens_output": 10}
            )
            self.llm = MagicMock()
            self.llm.ask.side_effect = Exception("Quota exhausted (429)")
            tier = self._do_review(manual_files=["test.py"])
            l3_pass = tier == "SOFT_PASS"
            results.append(("L3: Reviewer Gate", l3_pass))
            print(f"   Result Tier: {tier} -> {'✅ PASS' if l3_pass else '❌ FAIL'}")

            # --- L4: Contamination Trap ---
            print("\n🔹 [Level 4] Contamination Trap")
            self.executor.execute.return_value = ExecutorOutput(
                executor_name="mock_l4", phase="P", status=ExecutorStatusEnum.SUCCESS,
                patch_generated=True, patch_diff="diff",
                files_touched=["nexus/core/orchestrator.py"], # Contamination!
                evidence_present=True, raw_exit_code=0, summary="L4", meta={"tokens_output": 10}
            )
            tier = self._do_review(manual_files=["test.py"])
            l4_pass = tier == "BENCHMARK_CONTAMINATED"
            results.append(("L4: Contamination", l4_pass))
            print(f"   Result Tier: {tier} -> {'✅ PASS' if l4_pass else '❌ FAIL'}")

            # --- L5: Executor Swap (Semantic Sync) ---
            print("\n🔹 [Level 5] Executor Swap (Gemini vs Antigravity Semantic Sync)")
            # 這裡主要測的是 _do_review 邏輯在不同 executor 下是否一致觸發相同的 Tier 規則
            # 實際上 L1-L4 已經在測 Core 的 Tier 判定，L5 則是確保 AntigravityStub 也能跑通
            from nexus.executors.antigravity import AntigravityExecutor
            self.executor = AntigravityExecutor()
            tier = self._do_review(manual_files=["test.py"])
            l5_pass = tier in ["SOFT_PASS", "FAIL", "CONTINUITY_PASS"] # 只要能合法結束
            results.append(("L5: Executor Swap", l5_pass))
            print(f"   Antigravity Tier: {tier} -> {'✅ PASS' if l5_pass else '❌ FAIL'}")

        finally:
            # 還原
            self.executor = orig_executor
            self.llm = orig_llm
            self.patcher = orig_patcher
            self.linter = orig_linter
        
        print("\n" + "="*50)
        print("📊 [Self-Test Summary]")
        overall_pass = True
        for name, success in results:
            print(f"   {name:20}: {'✅ OK' if success else '❌ FAILED'}")
            if not success: overall_pass = False
        print("="*50)
        return overall_pass

    def _run_isolated_review(self, manual_files):
        task_id, branch, sandbox_path = self.workspace.lease()
        if not task_id: return False
        try:
            self.workspace.sync_staged_to_sandbox(sandbox_path)
            sandbox_engine = CodexLoopV2(
                mode=self.mode, 
                scope="all", 
                apply_patch=self.apply_patch, 
                base_ref="HEAD",
                executor=self.executor,
                reviewer_mode=self.reviewer_mode,
                task=self.task
            )
            original_cwd = os.getcwd()
            os.chdir(sandbox_path)
            try:
                passed = sandbox_engine._do_review(manual_files)
            finally:
                os.chdir(original_cwd)
            if passed: return self.workspace.harvest(branch, sandbox_path)
            return False
        finally:
            self.workspace.cleanup(task_id, branch)

    def _do_review(self, manual_files=None) -> str:
        print(f"🔍 [v2.0] Mode: {self.mode} | Scope: {self.scope}")
        original_cwd = os.getcwd()
        os.chdir(self.git.project_root)
        
        # --- 狀態追蹤變數 (V5 Steel) ---
        patch_generated = False
        patch_apply_failed = False
        verification_passed = False
        is_contaminated = False
        reviewer_status = "disabled" # 預設值
        final_tier = "FAIL"          # 預先定義以防 UnboundLocalError
        last_data = {"status": "FAIL", "summary": "No rounds executed."}

        action_brief_instr = ""
        try:
            for strike in range(1, self.max_strikes + 1):
                print(f"🚀 [Round {strike}/{self.max_strikes}] Initiating Audit...")

                # P-Stage Hook
                if self.task and strike == 1:
                    print(f"🎯 [Task Mode] Goal: {self.task}")
                    self._run_v5_p_stage(self.skill_id or "writing-plans", {"summary": self.task})

                # Context Gathering
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

                # 提早結束條件 (No changes)
                if not code_files and (not diff_text or not diff_text.strip()):
                    print("✅ [SKIPPED] No significant changes found.")
                    verification_passed = True
                    break

                # Diagnostic & Prompt Prep
                linter_json = self.linter.scan(code_files)
                lessons = self._get_lessons(query=diff_text)
                aesthetic_hint = self._get_aesthetic_rules(manual_files or files)
                full_prompt = f"{self.persona_hint}\n{aesthetic_hint}\nLESSONS:\n{lessons}\nLINTER:\n{linter_json}\n"

                # --- Execution ---
                if self.executor:
                    # [V5 Barrier] 物理封鎖 Legacy llm.ask
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
                        instruction=TaskInstruction(
                            task_id="review-task", 
                            objective=f"{self.task or 'Review code'}\nFEEDBACK: {action_brief_instr}"
                        )
                    )
                    
                    print(f"🧠 [Invariant] Calling Executor. Context Size: {len(context_files)} files.")
                    exec_output = self.executor.execute(exec_input)
                    
                    # [V5] Contamination Guard (Strict Check)
                    touched = [str((Path(self.git.project_root)/f).resolve()) for f in exec_output.files_touched]
                    core_roots = [
                        str(Path(self.git.project_root)/'nexus'), 
                        str(Path(self.git.project_root)/'scripts'),
                        str(Path(self.git.project_root)/'nexus_benchmark.sh')
                    ]
                    if any(str(f).startswith(tuple(core_roots)) for f in touched) and not self.allow_core_mutation:
                        print(f"❌ [DISCIPLINE] Core mutation detected: {touched}. CONTAMINATED.")
                        is_contaminated = True
                        break

                    # [V5] 映射歸一化數據 (禁止解析 Raw Text)
                    violations = []
                    main_file = exec_output.files_touched[0] if exec_output.files_touched else "unknown"
                    if exec_output.patch_generated and exec_output.patch_diff:
                        # 優先使用 Executor 回報的 files_touched 分群
                        violations = [{"patch": exec_output.patch_diff, "file": main_file}]
                    
                    last_data = {
                        "status": "PASS" if exec_output.status.name == "SUCCESS" else "FAIL",
                        "summary": exec_output.summary,
                        "violations": violations,
                        "tokens_used": exec_output.meta.get("tokens_output", 0),
                        "provider_error_type": exec_output.provider_error_type.name if exec_output.provider_error_type else None
                    }
                    
                    if exec_output.patch_generated:
                        patch_generated = True

                    if exec_output.status.name == "SUCCESS":
                        # [v5] 如果有補丁，先套用再驗證
                        if patch_generated and self.apply_patch:
                            print(f"🛠️ [v5 Orchestration] Applying executor patch to {main_file}...")
                            if self.patcher.apply(violations):
                                verification_passed = self._verify_work(code_files, touched_files=exec_output.files_touched)
                            else:
                                patch_apply_failed = True
                        else:
                            # 無補丁但回報成功 -> 代表現況已通過
                            verification_passed = self._verify_work(code_files, touched_files=exec_output.files_touched)

                            if verification_passed:
                                # [V5] Reviewer Optional Gate
                                if patch_generated and not patch_apply_failed:
                                    if self.reviewer_mode == "none":
                                        reviewer_status = "disabled"
                                    elif self.reviewer_mode == "codex":
                                        print("🔍 [Reviewer] Engaging optional Codex reviewer for Tier verification...")
                                        try:
                                            # TODO: Ensure LLMClient does not use sub-processes
                                            rev_prompt = f"Review Task: {self.task}\nReview actual logic. Reply JSON: {{\"status\": \"PASS\" | \"FAIL\"}}"
                                            rev_data, _ = self.llm.ask(rev_prompt, None, phase="Review")
                                            reviewer_status = "passed" if rev_data.get("status") == "PASS" else "rejected"
                                        except Exception as e:
                                            print(f"⚠️ [Reviewer] Unavailable: {e}. Degrading Tier.")
                                            reviewer_status = "unavailable"
                                break
                    else:
                        print("❌ [EXECUTION_FAIL] Executor returned failure status.")
                        # [V5] Allowing fall-through to escalation logic

                # --- Post-round Processing ---
                self.total_tokens += (last_data.get("tokens_used", 0) or 0)
                suggestions_hash = hashlib.md5(json.dumps(last_data.get("violations", []), sort_keys=True).encode()).hexdigest()
                if suggestions_hash in self.history_hashes:
                    print(f"⚠️ [STUCK] Strike {strike}. Breaking.")
                    break
                self.history_hashes.add(suggestions_hash)

                if last_data.get("status") == "FAIL":
                    task_md = derive_task_metadata(files, diff_text)
                    decision = self.escalation_policy.decide(
                        attempt=strike, task=task_md, failure_summary=last_data.get("summary", ""), repeated_failure=strike > 1
                    )
                    self._print_escalation_decision(decision)
                    
                    # [Escalation Pipeline] Build Action Brief (V5 Steel)
                    brief = build_action_brief(
                        decision=decision,
                        task=task_md,
                        failure_summary=last_data.get("summary", ""),
                        files=files,
                        violations=last_data.get("violations", [])
                    )
                    action_brief_instr = brief.instructions
                    print(f"📝 [Escalation] Action Brief Generated: {brief.title}")
                    
                    self._export_report({**last_data, "action_brief": brief.title})

                    if self.max_strikes == 1:
                        print("🏁 [Strike Lock] Single round mode active. Stopping.")
                        break

                    if self.apply_patch:
                        print("🛠️ Applying auto-patches...")
                        try:
                            if self.patcher.apply(last_data.get("violations", [])):
                                # 套用成功但不代表驗證通過，交由下一輪
                                pass
                            else:
                                patch_apply_failed = True
                                break
                        except Exception as e:
                            print(f"❌ Patch failed: {e}")
                            patch_apply_failed = True
                            break
                    else:
                        # 非 Patch 模式（如 Audit）若 FAIL 且允許多輪，則持續反饋
                        pass

            # --- Final Tier Determination (V5 Steel) ---
            final_tier = self._determine_final_tier(
                patch_generated=patch_generated,
                patch_apply_failed=patch_apply_failed,
                verification_passed=verification_passed,
                reviewer_status=reviewer_status,
                is_contaminated=is_contaminated
            )

            print(f"\n🏁 [Final Result] Tier: {final_tier}")
            self._export_report({**last_data, "assurance_tier": final_tier})
            return final_tier

        finally:
            if self.total_tokens > 0: print(f"📊 [Usage] Total Session Tokens: {self.total_tokens:,}")
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
    parser.add_argument("--self-test", action="store_true", help="Run 5-level system integrity validation")
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
    sys.exit(0 if engine.run_review(args.files, self_test=args.self_test) else 1)
