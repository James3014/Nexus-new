from pathlib import Path
import re
from typing import Any, Dict
import inspect
from nexus.services.local_heal.interface import IPhase, PhaseResult
from nexus.services.local_heal.reproduction import ReproductionRunner
from nexus.services.local_heal.env_denoiser import EnvDenoiser
from nexus.services.local_heal.context import HealContext
from nexus.engine.local_model_policy import LocalModelPolicy
from nexus.services.local_heal.model_result import classify_model_exception

class ReproductionPhase(IPhase):
    """Phase 1: Reproduction (建立物理證據)"""
    def __init__(self, repro_runner: ReproductionRunner, env_denoiser: EnvDenoiser, ollama_generate_fn: Any):
        self.repro_runner = repro_runner
        self.env_denoiser = env_denoiser
        self.ollama_generate = ollama_generate_fn

    def execute(self, ctx: HealContext) -> PhaseResult:
        if ctx.op.repro_evidence:
            ctx.op.reproduced = True
            return PhaseResult(success=True)

        # 如果沒有重現腳本，嘗試生成一個
        if not ctx.op.repro_script:
            script_res = self._generate_repro_script(ctx)
            if not script_res.success:
                return script_res
            ctx.op.repro_script = script_res.error_reason # 這裡暫時借用 error_reason 傳遞生成的腳本

        success, evidence = self.repro_runner.run_repro(ctx.op.repro_script)
        
        if (
            not success
            and ctx.op.repro_script
            and ctx.op.auto_heal_enabled
            and self.repro_runner.is_environment_failure(evidence)
        ):
            denoise_result = self.env_denoiser.prepare_from_evidence(evidence)
            ctx.op.env_denoise = denoise_result.to_receipt()
            
            if denoise_result.succeeded:
                python_executable = getattr(denoise_result, "python_executable", "")
                if python_executable:
                    self.repro_runner.python_executable = python_executable
                success, evidence = self.repro_runner.run_repro(ctx.op.repro_script)

        ctx.op.repro_evidence = evidence
        ctx.op.reproduced = bool(success)

        if not success or not evidence or len(evidence.strip()) < 10:
            if self.repro_runner.is_environment_failure(evidence):
                reason = "REPRO_ENVIRONMENT_FAILURE"
            elif not success:
                reason = "REPRO_NOT_REPRODUCED"
            else:
                reason = "REPRO_EVIDENCE_TOO_SHORT"
            return PhaseResult(success=False, exit_layer="repro_runner", error_reason=reason)

        return PhaseResult(success=True)

    def _generate_repro_script(self, ctx: HealContext) -> PhaseResult:
        decision = LocalModelPolicy.select_model(task_type="swe_repair", phase="reproduction", context={})
        ctx.op.model_decisions.append({"phase": "reproduction", **decision})
        
        prompt = f"Please generate a Python script to reproduce the following issue:\n\n{ctx.op.problem_statement}\n\nOutput ONLY the script content."
        try:
            response = self._call_model(
                "You are a QA engineer.",
                prompt,
                model_name=decision["model"],
                timeout_seconds=decision["timeout_seconds"]
            )
            if not response:
                ctx.op.failure_reason = "MODEL_TIMEOUT" if decision["timeout_seconds"] < 10 else "NO_REPRO_SCRIPT"
                self._record_model_status(ctx, ctx.op.failure_reason, phase="reproduction")
                return PhaseResult(success=False, exit_layer="repro_runner", error_reason=ctx.op.failure_reason)
            
            # 清理 Markdown Code Block
            clean_script = response
            if "```" in response:
                match = re.search(r"```[a-zA-Z0-9]*\n(.*?)\n```", response, re.DOTALL)
                if match:
                    clean_script = match.group(1)
                else:
                    clean_script = response.replace("```", "")
            
            return PhaseResult(success=True, error_reason=clean_script) # 用來傳遞腳本
        except Exception as e:
            reason = classify_model_exception(e)
            ctx.op.failure_reason = reason
            self._record_model_status(ctx, reason, detail=f"{type(e).__name__}: {e}", phase="reproduction")
            return PhaseResult(success=False, exit_layer="repro_runner", error_reason="MODEL_TIMEOUT" if reason == "MODEL_TIMEOUT" else "NO_REPRO_SCRIPT")

    def _record_model_status(self, ctx: HealContext, status: str, detail: str = "", *, phase: str | None = None) -> None:
        for decision in reversed(ctx.op.model_decisions):
            if phase is None or decision.get("phase") == phase:
                decision["status"] = status
                if detail:
                    decision["detail"] = detail[:500]
                return

    def _call_model(self, system_prompt: str, user_prompt: str, *, model_name: str, timeout_seconds: int | None = None) -> str:
        try:
            sig = inspect.signature(self.ollama_generate)
            kwargs = {}
            if "model" in sig.parameters:
                kwargs["model"] = model_name
            if "timeout" in sig.parameters and timeout_seconds is not None:
                kwargs["timeout"] = timeout_seconds
            if kwargs:
                return self.ollama_generate(system_prompt, user_prompt, **kwargs)
        except (TypeError, ValueError):
            pass
        return self.ollama_generate(system_prompt, user_prompt)
