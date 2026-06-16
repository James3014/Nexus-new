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
        ctx.op.final_patch = "" # 驗證失敗清除補丁
        ctx.op.failure_reason = f"LOGIC_REGRESSION:{res.failure_reason}"
        err = PatchError(kind=PatchErrorKind.LOGIC_REGRESSION, message=res.failure_reason)
        self._handle_retry(ctx, err)

    def _finalize_run(self, ctx: HealContext, ledger: LatencyLedger, start_wall: float) -> None:
        import time
        ctx.op.wall_time_sec = time.time() - start_wall
        ledger.wall_end = time.monotonic()
        ledger.retry_count = max(0, ctx.op.attempt - 1)
        ledger.finalize()
        ctx.op._latency_ledger = ledger
        self.governance_gate.audit(ctx)
        if self.receipt_writer:
            ctx.op.receipt_path = str(self.receipt_writer(ctx))

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
        targeted_files = ", ".join([f.path for f in getattr(ctx.op, "localized_files", [])])
        ctx.op.user_prompt = self.corrector.build_retry_prompt(ctx.op.user_prompt, error, targeted_files=targeted_files)
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
