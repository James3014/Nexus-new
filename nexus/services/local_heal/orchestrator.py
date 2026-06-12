from typing import Any, Callable, List
from pathlib import Path
import subprocess
from nexus.services.local_heal.interface import IPhase, PhaseResult
from nexus.services.local_heal.context import HealContext
from nexus.services.local_heal.governance_gate import GovernanceGate
from nexus.services.local_heal.corrector import SelfCorrector
from nexus.services.local_heal.errors import PatchError, PatchErrorKind
from nexus.services.local_heal.evidence_compactor import EvidenceCompactor

class HealOrchestrator:
    """🛡️ Nexus Heal Orchestrator (Modular / Strategy-Driven / Fail-Closed)"""
    
    def __init__(
        self,
        phases: List[IPhase],
        governance_gate: GovernanceGate,
        receipt_writer: Callable[[HealContext], Any] | None = None,
    ):
        # 預期 phases 順序: [Reproduction, Planning, Localization, PatchSynthesis, Verification]
        self.repro_phase = None
        self.plan_phase = None
        self.loc_phase = None
        self.patch_phase = None
        self.verify_phase = None

        if len(phases) == 5:
            self.repro_phase = phases[0]
            self.plan_phase = phases[1]
            self.loc_phase = phases[2]
            self.patch_phase = phases[3]
            self.verify_phase = phases[4]
        else:
            # 相容性回退分類
            for phase in phases:
                name = phase.__class__.__name__
                if "Reproduction" in name:
                    self.repro_phase = phase
                elif "Planning" in name:
                    self.plan_phase = phase
                elif "Localization" in name:
                    self.loc_phase = phase
                elif "Patch" in name:
                    self.patch_phase = phase
                elif "Verification" in name:
                    self.verify_phase = phase
                else:
                    if not self.repro_phase:
                        self.repro_phase = phase
                    elif not self.plan_phase:
                        self.plan_phase = phase
                    elif not self.loc_phase:
                        self.loc_phase = phase
                    elif not self.patch_phase:
                        self.patch_phase = phase
                    elif not self.verify_phase:
                        self.verify_phase = phase

        self.governance_gate = governance_gate
        self.receipt_writer = receipt_writer
        self.corrector = SelfCorrector()

    def run(self, ctx: HealContext) -> HealContext:
        """
        執行 5 階段修復管線，含 Phase 4/5 迭代重試。
        """
        import time
        start_wall = time.time()
        try:
            # Phase 1-3: 前置準備 (Linear)
            for phase in [self.repro_phase, self.plan_phase, self.loc_phase]:
                if not phase:
                    continue
                try:
                    res = phase.execute(ctx)
                except Exception as exc:
                    ctx.gov.gate_exit = phase.__class__.__name__
                    ctx.op.failure_reason = f"{type(exc).__name__}:{exc}"
                    ctx.op.runner_completed = True
                    return ctx

                if not res.success:
                    ctx.gov.gate_exit = res.exit_layer or "unknown"
                    ctx.op.failure_reason = res.error_reason
                    ctx.op.runner_completed = True
                    return ctx

            # 結構化壓縮證據，防止 Phase 4-5 上下文爆炸
            ctx.op.repro_evidence = EvidenceCompactor.compact(ctx.op.repro_evidence, limit=3000)

            # 上下文容量保護：若定位檔案過多或過大，則動態縮減以防模型超時
            total_snippet_len = sum(len(f[1]) for f in ctx.op.localized_files)
            if total_snippet_len > 10000 and len(ctx.op.localized_files) > 3:
                # 僅保留前 3 個最重要的檔案 (Top-3)
                ctx.op.localized_files = ctx.op.localized_files[:3]

            # Phase 4-5: 迭代修復迴圈
            while ctx.op.attempt <= ctx.op.max_tries:
                self._reset_workspace(ctx)
                # Step 4: Patch Synthesis
                if not self.patch_phase:
                    break
                try:
                    patch_res = self.patch_phase.execute(ctx)
                except Exception as exc:
                    ctx.gov.gate_exit = "patcher"
                    ctx.op.failure_reason = f"PATCH_EXCEPTION:{type(exc).__name__}:{exc}"
                    ctx.op.final_patch = ""
                    break

                if not patch_res.success:
                    err_kind = PatchErrorKind.NO_BLOCKS_FOUND
                    # 這裡根據 patch_res.error_reason 分類 PatchErrorKind
                    if "SEARCH_MISMATCH" in patch_res.error_reason: 
                        err_kind = PatchErrorKind.SEARCH_MISMATCH
                    elif "SYNTAX_ERROR" in patch_res.error_reason: 
                        err_kind = PatchErrorKind.SYNTAX_ERROR
                    elif "MODEL_REFUSAL" in patch_res.error_reason or "REFUSAL_DETECTED" in patch_res.error_reason:
                        err_kind = PatchErrorKind.REFUSAL_DETECTED
                    elif "MODEL_EMPTY_RESPONSE" in patch_res.error_reason or "EMPTY_RESPONSE" in patch_res.error_reason:
                        err_kind = PatchErrorKind.EMPTY_RESPONSE
                    elif "NAME_SANITY_ERROR" in patch_res.error_reason:
                        err_kind = PatchErrorKind.NAME_SANITY_ERROR

                    err = PatchError(kind=err_kind, message=patch_res.error_reason)
                    
                    # 記錄本次失敗狀態
                    status_name = err_kind.name
                    if patch_res.error_reason == "MODEL_TIMEOUT":
                        status_name = "MODEL_TIMEOUT"
                    elif patch_res.error_reason == "MODEL_PROVIDER_ERROR":
                        status_name = "MODEL_PROVIDER_ERROR"
                    elif patch_res.error_reason == "MODEL_REFUSAL" or patch_res.error_reason == "REFUSAL_DETECTED":
                        status_name = "MODEL_REFUSAL"
                    
                    self._record_model_status(ctx, status_name, detail=patch_res.error_reason, phase="patch")
                    
                    # Phase 4 Upgrade: 尋找最接近的匹配項 (Canonical Copy-Paste)
                    if err_kind == PatchErrorKind.SEARCH_MISMATCH and patch_res.error_metadata.get("failed_search_text"):
                        failed_text = patch_res.error_metadata["failed_search_text"]
                        f_path = patch_res.error_metadata.get("file_path")
                        if f_path:
                            target_file = ctx.op.repo_dir / f_path
                            if target_file.exists():
                                from nexus.services.local_heal.closest_snippet import find_closest_snippet
                                file_content = target_file.read_text(encoding="utf-8", errors="replace")
                                context_hints = ctx.op.plan.get("search_symbols", [])
                                err.closest_match = find_closest_snippet(file_content, failed_text, context_hints=context_hints)

                    # 優化：如果是特定的模型錯誤，直接使用該錯誤碼
                    model_errors = ["MODEL_TIMEOUT", "MODEL_EMPTY_RESPONSE", "MODEL_PROVIDER_ERROR", "MODEL_REFUSAL"]
                    if any(me in patch_res.error_reason for me in model_errors):
                        ctx.op.failure_reason = patch_res.error_reason
                    else:
                        ctx.op.failure_reason = f"{err_kind.name}:{patch_res.error_reason}"

                    # Fail-fast: do not retry infrastructure or extreme timeout errors
                    if "MODEL_TIMEOUT" in patch_res.error_reason or "MODEL_PROVIDER_ERROR" in patch_res.error_reason:
                        break

                    ctx = self._handle_retry(ctx, err)
                    continue
                # Step 5: Verification
                if not self.verify_phase:
                    ctx.op.solve_eligible = True
                    ctx.gov.gate_exit = "verification"
                    break
                try:
                    verify_res = self.verify_phase.execute(ctx)
                except Exception as exc:
                    ctx.gov.gate_exit = "verification"
                    ctx.op.failure_reason = f"VERIFY_EXCEPTION:{type(exc).__name__}:{exc}"
                    ctx.op.final_patch = ""
                    break

                if verify_res.success:
                    ctx.gov.gate_exit = "verification"
                    break
                else:
                    ctx.op.final_patch = "" # 驗證失敗需清除補丁
                    err = PatchError(kind=PatchErrorKind.LOGIC_REGRESSION, message=f"Verification failed: {verify_res.error_reason}")
                    ctx.op.failure_reason = f"LOGIC_REGRESSION:{verify_res.error_reason}"
                    ctx = self._handle_retry(ctx, err)


            ctx.op.runner_completed = True
            if not ctx.op.solve_eligible:
                if not ctx.gov.gate_exit or ctx.gov.gate_exit == "unknown":
                    ctx.gov.gate_exit = "verification"
            return ctx
            
        finally:
            ctx.op.wall_time_sec = time.time() - start_wall
            # 執行審計與收據寫入 (保證不論如何都會執行)
            self.governance_gate.audit(ctx)
            if self.receipt_writer:
                ctx.op.receipt_path = str(self.receipt_writer(ctx))

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
        targeted_files = ", ".join([f[0] for f in getattr(ctx.op, "localized_files", [])])
        ctx.op.user_prompt = self.corrector.build_retry_prompt(ctx.op.user_prompt, error, targeted_files=targeted_files)
        ctx.op.attempt += 1
        return ctx

    def _record_model_status(self, ctx: HealContext, status: str, detail: str = "", *, phase: str | None = None) -> None:
        for decision in reversed(ctx.op.model_decisions):
            if phase is None or decision.get("phase") == phase:
                decision["status"] = status
                if detail:
                    decision["detail"] = detail[:500]
                return
