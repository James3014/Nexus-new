from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
import os
from typing import List, Tuple, Dict, Any, Optional

from nexus.services.local_heal.context import HealContext as HealContextV2, OperationalContext, GovernanceContext
from nexus.services.local_heal.interface import IPhase, PhaseResult
from nexus.services.local_heal.orchestrator import HealOrchestrator
from nexus.services.local_heal.committee_orchestrator import CommitteeOrchestrator
from nexus.services.local_heal.governance_gate import GovernanceGate
from nexus.services.local_heal.receipt import write_repair_receipt
from nexus.evidence.abort_receipt import write_abort_receipt

# 導入各個 Phase 實作
from nexus.services.local_heal.phases.reproduction import ReproductionPhase
from nexus.services.local_heal.phases.planning import PlanningPhase
from nexus.services.local_heal.phases.localization import LocalizationPhase
from nexus.services.local_heal.phases.patch_synthesis import PatchSynthesisPhase
from nexus.services.local_heal.phases.verification import VerificationPhase

# 導入工具組
from nexus.services.local_heal.granular_localizer import GranularMethodLocalizer
from nexus.services.local_heal.protocol import SolidSearchReplaceProtocol
from nexus.services.local_heal.patcher import Patcher
from nexus.services.local_heal.reproduction import ReproductionRunner
from nexus.services.local_heal.planner import Planner
from nexus.services.local_heal.evaluation_gate import EvaluationGate
from nexus.services.local_heal.env_denoiser import EnvDenoiser
from nexus.services.local_heal.context_budget import ContextBudgetManager

# 舊版 HealContext 保持存在以供相容性
@dataclass
class HealContext:
    """管線狀態上下文封裝 (Legacy Wrapper for Compatibility)"""
    instance_id: str
    repo_dir: Path
    problem_statement: str
    localized_files: List[Tuple[str, str]] = field(default_factory=list)
    system_prompt: str = ""
    user_prompt: str = ""
    attempt: int = 1
    max_tries: int = 3
    final_patch: str = ""
    errors: List[Any] = field(default_factory=list)

    # --- 證據產物 ---
    repro_script: str = ""
    repro_evidence: str = ""
    reproduced: bool = False
    failure_reason: str = ""
    plan: Dict[str, Any] = field(default_factory=dict)
    evaluation_report: str = ""
    hidden_verifier_passed: bool = False
    runner_completed: bool = False
    solve_eligible: bool = False
    receipt_path: str = ""
    model_decisions: List[Dict[str, Any]] = field(default_factory=list)
    env_denoise: Dict[str, Any] = field(default_factory=dict)
    env_resolution: Dict[str, Any] = field(default_factory=dict)
    python_executable: str = ""
    auto_heal_enabled: bool = False
    skip_reproduction: bool = False
    wall_time_sec: float = 0.0
    token_telemetry_status: str = "not_applicable"
    token_total_estimated: int = 0
    syntax_gate_passed: bool = True
    prompt_variant_id: str = "default"
    refusal_detected: bool = False
    empty_response: bool = False
    expected_stop_layer: str = "verification"
    expected_reason_family: str = "SOLVED"

    reasoning_mode: str = "INTUITIVE"
    violated_invariants: List[str] = field(default_factory=list)
    rewrite_trace: List[str] = field(default_factory=list)
    risk_delta: float = 0.0
    run_group: str = ""
    route_context: Dict[str, Any] = field(default_factory=dict)

    def to_v2(self) -> HealContextV2:
        op = OperationalContext(
            instance_id=self.instance_id,
            repo_dir=self.repo_dir,
            problem_statement=self.problem_statement,
            localized_files=self.localized_files,
            system_prompt=self.system_prompt,
            user_prompt=self.user_prompt,
            attempt=self.attempt,
            max_tries=self.max_tries,
            final_patch=self.final_patch,
            repro_script=self.repro_script,
            repro_evidence=self.repro_evidence,
            reproduced=self.reproduced,
            plan=self.plan,
            evaluation_report=self.evaluation_report,
            hidden_verifier_passed=self.hidden_verifier_passed,
            runner_completed=self.runner_completed,
            solve_eligible=self.solve_eligible,
            failure_reason=self.failure_reason,
            receipt_path=self.receipt_path,
            model_decisions=self.model_decisions,
            env_denoise=self.env_denoise,
            env_resolution=self.env_resolution,
            python_executable=self.python_executable,
            auto_heal_enabled=self.auto_heal_enabled,
            wall_time_sec=self.wall_time_sec,
            token_telemetry_status=self.token_telemetry_status,
            token_total_estimated=self.token_total_estimated,
            syntax_gate_passed=self.syntax_gate_passed,
            prompt_variant_id=self.prompt_variant_id,
            refusal_detected=self.refusal_detected,
            empty_response=self.empty_response,
            reasoning_mode=self.reasoning_mode,
            skip_reproduction=self.skip_reproduction,
            run_group=self.run_group,
            route_context=self.route_context,
        )
        gov = GovernanceContext(
            expected_stop_layer=self.expected_stop_layer,
            expected_reason_family=self.expected_reason_family,
        )
        return HealContextV2(op=op, gov=gov)

    def sync_from_v2(self, v2: HealContextV2) -> None:
        """將 V2 Context 的狀態同步回目前實例 (In-place)"""
        for attr, value in v2.op.__dict__.items():
            if hasattr(self, attr):
                setattr(self, attr, value)
        self.expected_stop_layer = v2.gov.expected_stop_layer
        self.expected_reason_family = v2.gov.expected_reason_family

    @staticmethod
    def from_v2(v2: HealContextV2) -> HealContext:
        ctx = HealContext(
            instance_id=v2.op.instance_id,
            repo_dir=v2.op.repo_dir,
            problem_statement=v2.op.problem_statement,
        )
        ctx.sync_from_v2(v2)
        return ctx


class HealPipeline:
    """🛡️ Nexus Heal Pipeline (V3.0 Modular Orchestrator Shim)"""

    def __init__(self, ollama_generate_fn: Any, hidden_verifier: bool = False):
        self.ollama_generate = ollama_generate_fn
        self.hidden_verifier = hidden_verifier
        # 暴露屬性以供 monkeypatch 測試
        self.localizer = GranularMethodLocalizer()
        self.parser = SolidSearchReplaceProtocol()
        self.patcher = Patcher()
        self.planner = Planner(ollama_generate_fn=ollama_generate_fn)
        self.budget_manager = ContextBudgetManager()

    # --- Trace / Telemetry Helpers ---
    TRACE_LOG_PATH = Path("/Users/jameschen/Workspace/nexus/scratch/llm_trace.log")

    @classmethod
    def _write_trace(cls, message: str) -> None:
        try:
            cls.TRACE_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
            with open(cls.TRACE_LOG_PATH, "a", encoding="utf-8") as f:
                ts = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
                f.write(f"[{ts}] {message}\n")
        except Exception:
            pass

    def run(self, ctx: HealContext) -> HealContext:
        """
        將舊版 Context 轉換為 V2，透過 Orchestrator 執行，再轉回舊版回傳。
        """
        self._write_trace(f"=== PIPELINE START {ctx.instance_id} ===")
        v2_ctx = ctx.to_v2()
        
        # 初始化環境感知的服務 (使用 factory 以供測試 monkeypatch)
        repro_runner = self._make_reproduction_runner(v2_ctx.op.repo_dir)
        env_denoiser = self._make_env_denoiser(v2_ctx.op.repo_dir)
        if v2_ctx.op.python_executable:
            repro_runner.python_executable = v2_ctx.op.python_executable
            env_denoiser.python_executable = v2_ctx.op.python_executable
            
        phases: List[IPhase] = [
            ReproductionPhase(repro_runner=repro_runner, env_denoiser=env_denoiser, ollama_generate_fn=self.ollama_generate),
            PlanningPhase(planner=self.planner),
            LocalizationPhase(localizer=self.localizer, budget_manager=self.budget_manager),
            PatchSynthesisPhase(
                parser=self.parser,
                patcher=self.patcher,
                ollama_generate_fn=self.ollama_generate
            ),
            VerificationPhase(
                eval_gate=EvaluationGate(v2_ctx.op.repo_dir),
                hidden_required=self.hidden_verifier
            )
        ]
        
        orchestrator_cls = CommitteeOrchestrator if os.getenv("NEXUS_USE_COMMITTEE", "0") == "1" else HealOrchestrator
        
        orchestrator = orchestrator_cls(
            phases=phases,
            governance_gate=GovernanceGate(),
            receipt_writer=write_repair_receipt
        )
        
        # 執行編排 with abort receipt guarantee
        try:
            v2_result = orchestrator.run(v2_ctx)
        except Exception as exc:
            self._write_abort_receipt_on_exception(ctx, str(exc))
            raise
        
        # 同步回原 Context (In-place)
        ctx.sync_from_v2(v2_result)
        self._write_trace(f"=== PIPELINE END {ctx.instance_id} solve_eligible={ctx.solve_eligible} ===")
        return ctx

    def _write_abort_receipt_on_exception(self, ctx: HealContext, error_msg: str) -> None:
        """P0.1b: Write abort receipt when pipeline raises exception."""
        try:
            import re
            safe_id = re.sub(r"[^A-Za-z0-9_.-]+", "__", ctx.instance_id).strip("_") or "unknown"
            nexus_root = Path(__file__).resolve().parents[3]
            output_dir = nexus_root / ".nexus/reports/local_heal" / safe_id
            write_abort_receipt(
                output_dir=output_dir,
                task_id=ctx.instance_id,
                instance_id=ctx.instance_id,
                failure_class="workspace_provisioning",
                failure_reason=error_msg[:500],
                failure_subclass="REPO_NOT_MOUNTED",
                workspace_path=str(ctx.repo_dir),
                repo_root=str(ctx.repo_dir),
                target_path="",
                path_subclass="",
                model_calls=0,
                stop_layer="pipeline_exception",
            )
        except Exception:
            pass

    # --- Shim Methods for Testing Compatibility ---
    def _make_reproduction_runner(self, repo_dir: Path) -> ReproductionRunner:
        return ReproductionRunner(repo_dir)

    def _make_env_denoiser(self, repo_dir: Path) -> EnvDenoiser:
        return EnvDenoiser(repo_dir)

    def _localize(self, ctx: HealContext) -> HealContext:
        # 單獨調用定位階段 (供測試使用)
        v2_ctx = ctx.to_v2()
        try:
            phase = LocalizationPhase(localizer=self.localizer, budget_manager=self.budget_manager)
            phase.execute(v2_ctx)
        except Exception as exc:
            self._write_trace(f"LOCALIZE_EXCEPTION instance={ctx.instance_id} error={exc}")
            ctx.localized_files = []
            return ctx
        ctx.sync_from_v2(v2_ctx)
        return ctx
