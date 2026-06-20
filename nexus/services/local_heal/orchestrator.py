from typing import Any, Callable, List
from pathlib import Path
import subprocess
from nexus.services.local_heal.interface import IPhase, PhaseResult
from nexus.services.local_heal.context import HealContext
from nexus.services.local_heal.governance_gate import GovernanceGate
from nexus.services.local_heal.corrector import SelfCorrector
from nexus.services.local_heal.errors import PatchError, PatchErrorKind
from nexus.services.local_heal.evidence_compactor import EvidenceCompactor
from nexus.services.local_heal.latency_ledger import LatencyLedger
from nexus.services.local_heal.role_contract import build_role_receipt, RoleReceipt
from nexus.evidence.abort_receipt import write_abort_receipt

from nexus.services.local_heal.failure_analyzer import FailureAnalyzer
from nexus.services.local_heal.context_guard import ContextGuard
from nexus.services.local_heal.phase_runner import PhaseRunner

class HealOrchestrator:
    """🛡️ Nexus Heal Orchestrator (Refactored: Modular / Strategy-Driven / Fail-Closed)"""
    
    def __init__(
        self,
        phases: List[IPhase],
        governance_gate: GovernanceGate,
        receipt_writer: Callable[[HealContext], Any] | None = None,
    ):
        # 預期 phases 順序: [Reproduction, Planning, Localization, PatchSynthesis, Verification]
        self._initialize_phases(phases)
        self.governance_gate = governance_gate
        self.receipt_writer = receipt_writer
        
        # Dependency Injection (Internal)
        self.corrector = SelfCorrector()
        self.failure_analyzer = FailureAnalyzer()
        self.context_guard = ContextGuard()
        self.phase_runner = PhaseRunner()

    def _initialize_phases(self, phases: List[IPhase]) -> None:
        self.repro_phase = None
        self.plan_phase = None
        self.loc_phase = None
        self.patch_phase = None
        self.verify_phase = None
        
        # (Rest of phase detection logic moved here to keep constructor clean)
        if len(phases) == 5:
            self.repro_phase, self.plan_phase, self.loc_phase, self.patch_phase, self.verify_phase = phases
        else:
            for phase in phases:
                name = phase.__class__.__name__
                if "Reproduction" in name: self.repro_phase = phase
                elif "Planning" in name: self.plan_phase = phase
                elif "Localization" in name: self.loc_phase = phase
                elif "Patch" in name: self.patch_phase = phase
                elif "Verification" in name: self.verify_phase = phase

    def run(self, ctx: HealContext) -> HealContext:
        """核心修復工作流：線性啟動 -> 迭代修復 -> 審計結算。"""
        import time
        start_wall = time.time()
        
        ledger = LatencyLedger(
            task_id=getattr(ctx.op, "task_id", ""),
            instance_id=getattr(ctx.op, "instance_id", ""),
            wall_start=time.monotonic(),
        )
        ctx.op._latency_ledger = ledger
        ctx.op._role_receipts = []
        
        try:
            # 1. 啟動階段 (P1-3)
            if not self._run_linear_phases(ctx, ledger):
                return ctx

            # 2. 上下文保護 (Linus: Do it once, do it right)
            self.context_guard.protect(ctx)

            # 3. 迭代修復迴圈 (P4-5)
            self._run_repair_loop(ctx, ledger)

            ctx.op.runner_completed = True
            return ctx
            
        finally:
            self._finalize_run(ctx, ledger, start_wall)

    def _run_linear_phases(self, ctx: HealContext, ledger: LatencyLedger) -> bool:
        """執行再現、規劃與定位。任何階段失敗即終止。"""
        phases = [
            ("reproduction", self.repro_phase),
            ("planning", self.plan_phase),
            ("localization", self.loc_phase),
        ]
        for name, phase in phases:
            if not phase: continue
            res = self.phase_runner.run_phase(phase, name, ctx, ledger)
            if not res.success:
                ctx.gov.gate_exit = res.exit_layer or name
                ctx.op.failure_reason = res.failure_reason
                ctx.op.runner_completed = True
                self._write_abort_receipt_on_failure(ctx, name, res.failure_reason)
                return False
            
            self._record_role_receipt(ctx, name)
        return True

    def _run_repair_loop(self, ctx: HealContext, ledger: LatencyLedger) -> None:
        """執行 Patch 合成與驗證的迭代迴圈。"""
        while ctx.op.attempt <= ctx.op.max_tries:
            self._reset_workspace(ctx)
            
            # Step 4: Patch Synthesis
            if not self.patch_phase: break
            res = self.phase_runner.run_phase(self.patch_phase, f"patch_attempt_{ctx.op.attempt}", ctx, ledger)
            
            if not res.success:
                if self._handle_patch_failure(ctx, res, ledger):
                    continue
                else:
                    break
            
            # Step 5: Verification
            if not self.verify_phase:
                ctx.op.solve_eligible = True
                break
                
            v_res = self.phase_runner.run_phase(self.verify_phase, f"verify_attempt_{ctx.op.attempt}", ctx, ledger)
            if v_res.success:
                ctx.gov.gate_exit = "verification"
                break
            else:
                self._handle_verification_failure(ctx, v_res)

    def _handle_patch_failure(self, ctx: HealContext, res: PhaseResult, ledger: LatencyLedger) -> bool:
        """處理 Patch 生成失敗，判定是否重試。"""
        err_kind = self.failure_analyzer.classify_patch_failure(res.failure_reason)
        err = PatchError(kind=err_kind, message=res.failure_reason)
        
        self._record_model_status(ctx, err_kind.name, detail=res.failure_reason, phase="patch")
        
        # 嘗試自動修復 SEARCH_MISMATCH (Fuzzy Match)
        if err_kind == PatchErrorKind.SEARCH_MISMATCH:
            self._attempt_fuzzy_healing(ctx, res, err)

        # 判定 Fail-fast
        if not self.failure_analyzer.should_retry(res.failure_reason):
            ctx.op.failure_reason = res.failure_reason
            return False

        ctx.op.failure_reason = f"{err_kind.name}:{res.failure_reason}"
        self._handle_retry(ctx, err)
        return True

    def _attempt_fuzzy_healing(self, ctx: HealContext, res: PhaseResult, err: PatchError) -> None:
        metadata = res.error_metadata or {}
        failed_text = metadata.get("failed_search_text")
        f_path = metadata.get("file_path")
        if failed_text and f_path:
            target_file = ctx.op.repo_dir / f_path
            if target_file.exists():
                from nexus.services.local_heal.closest_snippet import find_closest_snippet
                file_content = target_file.read_text(encoding="utf-8", errors="replace")
                search_symbols = ctx.op.plan.search_symbols if ctx.op.plan else []
                err.closest_match = find_closest_snippet(file_content, failed_text, context_hints=search_symbols)

    def _handle_verification_failure(self, ctx: HealContext, res: PhaseResult) -> None:
        """Handle verification failure with T1.6 semantic retry on first failure."""
        evaluation_report = getattr(ctx.op, "evaluation_report", "")
        failure_class = self._classify_verification_failure(ctx, res.failure_reason)

        # T1.6: Semantic retry eligible on first verification failure
        semantic_retry_eligible = (
            ctx.op.attempt == 1
            and failure_class in ("semantic_wrong", "LOGIC_REGRESSION", "VERIFICATION_FAILED")
            and evaluation_report
            and getattr(ctx.op, "final_patch", "")
        )

        if semantic_retry_eligible:
            semantic_ok = self._attempt_semantic_retry(ctx, evaluation_report, failure_class)
            if semantic_ok:
                # Semantic retry succeeded — skip normal retry loop
                return

        # Normal path: clear patch and retry
        ctx.op.final_patch = ""
        ctx.op.failure_reason = f"LOGIC_REGRESSION:{res.failure_reason}"
        err = PatchError(kind=PatchErrorKind.LOGIC_REGRESSION, message=res.failure_reason)
        self._handle_retry(ctx, err)

    def _classify_verification_failure(self, ctx: HealContext, failure_reason: str) -> str:
        """Classify verification failure into semantic categories."""
        report = getattr(ctx.op, "evaluation_report", "")
        if "BUG PRESENT" in report:
            return "semantic_wrong"
        if "LOGIC_REGRESSION" in failure_reason:
            return "LOGIC_REGRESSION"
        return "VERIFICATION_FAILED"

    def _attempt_semantic_retry(
        self, ctx: HealContext, evaluation_report: str, failure_class: str
    ) -> bool:
        """T1.6: Attempt verification-guided semantic retry.

        Locks the canonical SEARCH span from the last patch, feeds verifier
        failure into the prompt, and asks the LLM to rewrite only REPLACE.
        Returns True if retry succeeded (patch applied + verification passed).
        """
        import re
        import json
        import hashlib
        from nexus.services.local_heal.prompt_builder import PromptBuilder
        from nexus.services.local_heal.protocol import SolidSearchReplaceProtocol
        from nexus.services.local_heal.patcher import Patcher
        from nexus.services.local_heal.patch_applier import PatchApplier
        from nexus.services.local_heal.interface import LocalizedFile
        from nexus.services.local_heal.model_result import classify_model_exception
        from nexus.engine.local_model_policy import LocalModelPolicy
        from nexus.services.local_heal.canonical_span import get_canonical_search_span

        # 1. Extract canonical SEARCH span using hybrid strategy
        final_patch = getattr(ctx.op, "final_patch", "")
        target_symbol = self._extract_target_symbol(ctx)
        source_file = self._resolve_target_file(ctx)

        canonical_result = get_canonical_search_span(
            locked_search="",
            patch_diff=final_patch,
            source_file=source_file,
            target_symbol=target_symbol,
            failed_search_text="",
        )

        if not canonical_result:
            return False

        canonical_search = canonical_result.span
        canonical_source = canonical_result.source

        # 2. Extract target file from patch
        target_file_match = re.search(r"^\+\+\+ b/(.+)$", final_patch, re.MULTILINE)
        if not target_file_match:
            return False
        target_file = target_file_match.group(1)

        # 3. Extract verifier failure text
        verifier_failure = evaluation_report

        # 4. Build semantic retry prompt
        original_prompt = getattr(ctx.op, "user_prompt", "")
        semantic_prompt = PromptBuilder.build_verification_guided_retry_prompt(
            original_user_prompt=original_prompt,
            verification_report=verifier_failure,
            canonical_search_span=canonical_search,
            target_file=target_file,
            retry_count=1,
        )

        # 5. Select model for patch (Qwen14B only)
        patch_decision = LocalModelPolicy.select_model(
            task_type="swe_repair",
            phase="patch",
            context={
                "reasoning_mode": getattr(ctx.op, "reasoning_mode", "INTUITIVE"),
                "file_count": 1,
                "attempt": ctx.op.attempt,
                "failure_reason": f"SEMANTIC_RETRY:{failure_class}",
            },
        )
        ctx.op.model_decisions.append({"phase": "semantic_retry_patch", **patch_decision})

        # 6. Call LLM
        from nexus.services.local_heal.llm_client import OllamaLLMClient
        llm_client = OllamaLLMClient(None)
        try:
            response = llm_client.generate(
                system_prompt=PromptBuilder.build_patch_system_prompt(patch_decision["model"]),
                user_prompt=semantic_prompt,
                model=patch_decision["model"],
                timeout=patch_decision["timeout_seconds"],
                options=patch_decision.get("ollama_options"),
            )
        except Exception as e:
            reason = classify_model_exception(e)
            ctx.op.model_decisions[-1]["status"] = reason
            return False

        if not response:
            ctx.op.model_decisions[-1]["status"] = "MODEL_EMPTY_RESPONSE"
            return False

        # 7. Parse SEARCH/REPLACE from response
        parser = SolidSearchReplaceProtocol()
        intents_or_error = parser.parse(response)
        if hasattr(intents_or_error, "kind"):
            ctx.op.model_decisions[-1]["status"] = intents_or_error.kind.name
            return False

        # 8. Lock canonical SEARCH span — replace any SEARCH from LLM
        locked_intents = []
        for intent in intents_or_error:
            locked_intent = type(intent)(
                file_path=intent.file_path,
                search=canonical_search,
                replace=intent.replace,
                operation=intent.operation,
            )
            locked_intents.append(locked_intent)

        # 9. Re-apply patch with locked SEARCH
        patcher = Patcher()
        patch_applier = PatchApplier(parser, patcher)
        apply_res = patch_applier.apply_and_validate(
            intents=locked_intents,
            repo_dir=ctx.op.repo_dir,
            localized_files=list(getattr(ctx.op, "localized_files", [])),
        )

        if not apply_res.success:
            ctx.op.model_decisions[-1]["status"] = apply_res.error_reason
            return False

        ctx.op.model_decisions[-1]["status"] = "SUCCESS"
        ctx.op.final_patch = "\n".join(apply_res.applied_diffs).strip()

        # 10. Re-run verification
        v_res = self.phase_runner.run_phase(
            self.verify_phase, f"verify_semantic_retry", ctx, ctx.op._latency_ledger
        )

        # 11. Write semantic retry telemetry
        ctx.op._semantic_retry_telemetry = {
            "semantic_retry_count": 1,
            "same_span_retry": True,
            "original_verification_failure": verifier_failure[:500],
            "observed_behavior": verifier_failure[:300],
            "behavior_delta_verified": v_res.success,
            "verifier_result_after_retry": "PASS" if v_res.success else f"FAIL: {getattr(ctx.op, 'evaluation_report', '')[:200]}",
            "search_locked": True,
            "replace_rewritten": True,
            "canonical_search_hash": hashlib.sha256(canonical_search.encode()).hexdigest()[:16],
            "target_file": target_file,
            # T1.6a: Attribution fields
            "semantic_retry_mode": "llm_replace_rewrite",
            "llm_replace_success": v_res.success,
            "deterministic_fallback_used": False,
            "fallback_rule_id": "",
            "fallback_rule_scope": "",
            "fallback_rule_reason": "",
            "model_patch_reward": 1.0 if v_res.success else 0.0,
            "deterministic_fallback_reward": 0.0,
        }

        if v_res.success:
            ctx.gov.gate_exit = "verification"
            ctx.op.solve_eligible = True
            return True

        return False

    def _extract_target_symbol(self, ctx: HealContext) -> str:
        """Extract target symbol from plan or localized files."""
        plan = getattr(ctx.op, "plan", None)
        if plan and hasattr(plan, "search_symbols") and plan.search_symbols:
            return plan.search_symbols[0]
        return ""

    def _resolve_target_file(self, ctx: HealContext) -> Path | None:
        """Resolve the target file path from localized files."""
        localized = getattr(ctx.op, "localized_files", [])
        if not localized:
            return None
        for loc in localized:
            if hasattr(loc, "path") and loc.path:
                target = ctx.op.repo_dir / loc.path
                if target.exists():
                    return target
        return None

    def _finalize_run(self, ctx: HealContext, ledger: LatencyLedger, start_wall: float) -> None:
        import time
        ctx.op.wall_time_sec = time.time() - start_wall
        ledger.wall_end = time.monotonic()
        ledger.retry_count = max(0, ctx.op.attempt - 1)
        ledger.finalize()
        ctx.op._latency_ledger = ledger
        self.governance_gate.audit(ctx)
        if self.receipt_writer:
            ctx.op.receipt_path = str(self.receipt_writer(ctx, run_group=getattr(ctx.op, "run_group", "")))

    def _record_role_receipt(self, ctx: HealContext, phase_name: str) -> None:
        model_name = self._get_model_for_phase(ctx, phase_name)
        if model_name:
            role_receipt = build_role_receipt(phase_name, model_name)
            ctx.op._role_receipts.append(role_receipt)

    def _reset_workspace(self, ctx: HealContext) -> None:
        # P1-3: Portable root detection — use env var or fall back to detecting via git
        import os
        nexus_root_env = os.environ.get("NEXUS_ROOT", "")
        if nexus_root_env:
            current_root = Path(nexus_root_env).resolve()
        else:
            # Detect project root as the nearest ancestor with a .git
            candidate = Path(__file__).resolve()
            current_root = candidate
            for _ in range(8):
                if (candidate / ".git").exists():
                    current_root = candidate
                    break
                candidate = candidate.parent

        if ctx.op.repo_dir.resolve() == current_root:
            return

        if not ctx.op.repo_dir or not (ctx.op.repo_dir / ".git").exists():
            return
        subprocess.run(["git", "checkout", "--", "."], cwd=str(ctx.op.repo_dir), capture_output=True)
        subprocess.run(["git", "clean", "-fd"], cwd=str(ctx.op.repo_dir), capture_output=True)

    def _handle_retry(self, ctx: HealContext, error: PatchError) -> HealContext:
        _PATCH_BLACKLIST = {"reproduce_bug.py", "repro.py", "test_repro.py"}
        targeted_files = ", ".join([
            f.path for f in getattr(ctx.op, "localized_files", [])
            if Path(f.path).name not in _PATCH_BLACKLIST
        ])
        
        sp = None
        if error.kind in (PatchErrorKind.LOGIC_REGRESSION, PatchErrorKind.SEARCH_MISMATCH, PatchErrorKind.SYNTAX_ERROR):
            from nexus.services.local_heal.evidence_compactor import EvidenceCompactor
            evaluation_report = getattr(ctx.op, "evaluation_report", "") or error.message or ""
            repro_command = ""
            if ctx.op.plan and getattr(ctx.op.plan, "verifier_command", ""):
                repro_command = ctx.op.plan.verifier_command
            env_failure_reason = ""
            env_resolution = getattr(ctx.op, "env_resolution", None)
            if env_resolution and not getattr(env_resolution, "ready", True):
                env_failure_reason = getattr(env_resolution, "failure_reason", "") or ""
            sp = EvidenceCompactor.compact_structured(
                evidence=evaluation_report,
                raw_artifact_ref="verification_report.txt",
                repro_command=repro_command,
                env_failure_reason=env_failure_reason,
            )
            error.structured_packet = sp
            
        ctx.op.user_prompt = self.corrector.build_retry_prompt(ctx.op.user_prompt, error, targeted_files=targeted_files, structured_packet=sp)
        ctx.op.attempt += 1
        return ctx
    
    def _get_model_for_phase(self, ctx: HealContext, phase_name: str) -> str:
        """Extract the model name used for a given phase from model_decisions."""
        for decision in reversed(ctx.op.model_decisions):
            if decision.get("phase") == phase_name:
                return decision.get("model", "")
        return ""

    def _record_model_status(self, ctx: HealContext, status: str, detail: str = "", *, phase: str | None = None) -> None:
        for decision in reversed(ctx.op.model_decisions):
            if phase is None or decision.get("phase") == phase:
                decision["status"] = status
                if detail:
                    decision["detail"] = detail[:500]
                return

    def _write_abort_receipt_on_failure(self, ctx: HealContext, phase_name: str, failure_reason: str) -> None:
        """P0.1b: Write abort receipt when a phase fails."""
        try:
            from pathlib import Path
            nexus_root = Path(__file__).resolve().parents[3]
            output_dir = nexus_root / ".nexus/reports/local_heal" / _safe_id(ctx.op.instance_id)
            write_abort_receipt(
                output_dir=output_dir,
                task_id=getattr(ctx.op, "task_id", ctx.op.instance_id),
                instance_id=ctx.op.instance_id,
                failure_class="workspace_provisioning" if "repro" in phase_name.lower() else "phase_failure",
                failure_reason=failure_reason,
                failure_subclass=_map_failure_subclass(failure_reason),
                workspace_path=str(ctx.op.repo_dir),
                repo_root=str(ctx.op.repo_dir),
                target_path="",
                path_subclass="",
                model_calls=len(ctx.op.model_decisions),
                stop_layer=phase_name,
            )
        except Exception:
            pass


def _safe_id(instance_id: str) -> str:
    import re
    return re.sub(r"[^A-Za-z0-9_.-]+", "__", instance_id).strip("_") or "unknown"


def _map_failure_subclass(reason: str) -> str:
    if "REPO_NOT_MOUNTED" in reason or "repo_root" in reason.lower():
        return "REPO_NOT_MOUNTED"
    if "NOT_WRITABLE" in reason or "writable" in reason.lower():
        return "WORKSPACE_NOT_WRITABLE"
    if "TARGET_PATH" in reason:
        return "TARGET_PATH_UNRESOLVED"
    if "MANIFEST" in reason:
        return "MANIFEST_MISSING_TARGET"
    if "REPRO" in reason:
        return "WRONG_REPRO_PATH"
    if "STALE" in reason:
        return "STALE_MODEL_PATH"
    return "PHASE_FAILURE"
