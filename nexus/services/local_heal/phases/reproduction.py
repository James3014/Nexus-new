from pathlib import Path
import re
from typing import Any, Dict
from nexus.services.local_heal.interface import IPhase, PhaseResult, ReproductionInput, ReproductionOutput
from nexus.services.local_heal.reproduction import ReproductionRunner
from nexus.services.local_heal.env_denoiser import EnvDenoiser
from nexus.services.local_heal.context import HealContext
from nexus.engine.local_model_policy import LocalModelPolicy
from nexus.services.local_heal.model_result import classify_model_exception
from nexus.services.local_heal.llm_client import ILLMClient, OllamaLLMClient

class ReproductionPhase(IPhase):
    """Phase 1: Reproduction (建立物理證據)"""
    def __init__(
        self,
        repro_runner: ReproductionRunner,
        env_denoiser: EnvDenoiser,
        ollama_generate_fn: Any | None = None,
        llm_client: ILLMClient | None = None
    ):
        self.repro_runner = repro_runner
        self.env_denoiser = env_denoiser
        if llm_client:
            self.llm_client = llm_client
        elif ollama_generate_fn:
            self.llm_client = OllamaLLMClient(ollama_generate_fn)
        else:
            self.llm_client = None

    def run(self, input_data: ReproductionInput, auto_heal_enabled: bool = False) -> ReproductionOutput:
        """Stateless TDD-ready execution logic."""
        repro_script = input_data.repro_script
        
        # 1. 產生重現腳本
        if not repro_script:
            decision = LocalModelPolicy.select_model(task_type="swe_repair", phase="reproduction", context={})
            prompt = f"Please generate a Python script to reproduce the following issue:\n\n{input_data.problem_statement}\n\nOutput ONLY the script content."
            if not self.llm_client:
                return ReproductionOutput(success=False, reproduced=False, repro_evidence="", error_reason="NO_LLM_CLIENT")
            try:
                response = self.llm_client.generate(
                    system_prompt="You are a QA engineer.",
                    user_prompt=prompt,
                    model=decision["model"],
                    timeout=decision["timeout_seconds"],
                    options=decision.get("ollama_options")
                )
                if not response:
                    return ReproductionOutput(success=False, reproduced=False, repro_evidence="", error_reason="NO_REPRO_SCRIPT")
                
                clean_script = response
                if "```" in response:
                    match = re.search(r"```[a-zA-Z0-9]*\n(.*?)\n```", response, re.DOTALL)
                    if match:
                        clean_script = match.group(1)
                    else:
                        clean_script = response.replace("```", "")
                repro_script = clean_script
            except Exception as e:
                reason = classify_model_exception(e)
                return ReproductionOutput(success=False, reproduced=False, repro_evidence="", error_reason="NO_REPRO_SCRIPT")

        # 2. 執行重現
        success, evidence = self.repro_runner.run_repro(repro_script)
        
        # 3. 自動環境自癒
        if (
            not success
            and repro_script
            and auto_heal_enabled
            and self.repro_runner.is_environment_failure(evidence)
        ):
            denoise_result = self.env_denoiser.prepare_from_evidence(evidence)
            if denoise_result.succeeded:
                python_executable = getattr(denoise_result, "python_executable", "")
                if python_executable:
                    self.repro_runner.python_executable = python_executable
                success, evidence = self.repro_runner.run_repro(repro_script)

        if not success or not evidence or len(evidence.strip()) < 10:
            if self.repro_runner.is_environment_failure(evidence):
                reason = "REPRO_ENVIRONMENT_FAILURE"
            elif not success:
                reason = "REPRO_NOT_REPRODUCED"
            else:
                reason = "REPRO_EVIDENCE_TOO_SHORT"
            return ReproductionOutput(success=False, reproduced=False, repro_evidence=evidence, error_reason=reason)

        return ReproductionOutput(success=True, reproduced=True, repro_evidence=evidence)

    def execute(self, ctx: HealContext) -> PhaseResult:
        if ctx.op.repro_evidence:
            ctx.op.reproduced = True
            return PhaseResult(success=True)

        input_data = ReproductionInput(
            instance_id=ctx.op.instance_id,
            repo_dir=ctx.op.repo_dir,
            problem_statement=ctx.op.problem_statement,
            repro_script=ctx.op.repro_script,
            python_executable=ctx.op.python_executable
        )

        output = self.run(input_data, auto_heal_enabled=ctx.op.auto_heal_enabled)
        
        ctx.op.repro_evidence = output.repro_evidence
        ctx.op.reproduced = output.reproduced
        
        if not output.success:
            return PhaseResult(success=False, exit_layer="repro_runner", error_reason=output.error_reason)

        return PhaseResult(success=True)
