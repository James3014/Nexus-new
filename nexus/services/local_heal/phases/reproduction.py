from pathlib import Path
import re
import subprocess
from typing import Any, Dict
from nexus.services.local_heal.interface import IPhase, PhaseResult, ReproductionInput, ReproductionOutput
from nexus.services.local_heal.reproduction import ReproductionRunner
from nexus.services.local_heal.env_denoiser import EnvDenoiser
from nexus.services.local_heal.env_recipe_registry import EnvRecipeRegistry
from nexus.services.local_heal.workspace_provision import WorkspaceProvisionChecker
from nexus.services.local_heal.context import HealContext
from nexus.engine.local_model_policy import LocalModelPolicy
from nexus.services.local_heal.model_result import classify_model_exception
from nexus.services.local_heal.llm_client import ILLMClient, OllamaLLMClient
from nexus.services.local_heal.evidence_compactor import EvidenceCompactor

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
        """Stateless TDD-ready execution logic with self-correction retry loop."""
        repro_script = input_data.repro_script
        model_decision: Dict[str, Any] = {}
        env_denoise_receipt: Dict[str, Any] = {}
        success = False
        evidence = ""

        # 1. 產生重現腳本 (含 Self-Correction Retry Loop)
        if not repro_script:
            decision = LocalModelPolicy.select_model(task_type="swe_repair", phase="reproduction", context={})
            model_decision = {"phase": "reproduction", **decision}

            base_prompt = (
                f"Please generate a Python script to reproduce the following issue:\n\n"
                f"{input_data.problem_statement}\n\n"
                f"CRITICAL REQUIREMENTS:\n"
                f"1. The script MUST contain an `assert` statement that fails (raises AssertionError) if the bug is present.\n"
                f"2. Or, if the bug is an exception, catch the exception, print it, and explicitly call `sys.exit(1)`.\n"
                f"3. If the bug is fixed/absent, the script MUST exit cleanly with code 0.\n"
                f"4. Be very careful with imports. Only import modules that are mentioned in the issue or standard library.\n"
                f"5. Output ONLY the Python script content enclosed in ```python...```.\n"
            )

            if not self.llm_client:
                model_decision["status"] = "NO_LLM_CLIENT"
                return ReproductionOutput(success=False, reproduced=False, repro_evidence="", error_reason="NO_LLM_CLIENT", model_decision=model_decision)

            max_retries = 2 # 減少重試次數以節省時間
            current_prompt = base_prompt
            last_error = ""

            for attempt in range(max_retries):
                try:
                    response = self.llm_client.generate(
                        system_prompt="You are a QA engineer. Your ONLY goal is to write a Python script that reproduces the bug described.",
                        user_prompt=current_prompt,
                        model=decision["model"],
                        timeout=decision["timeout_seconds"],
                        options=decision.get("ollama_options"),
                        phase="reproduction"
                    )
                    if not response:
                        continue

                    clean_script = response
                    if "```" in response:
                        match = re.search(r"```[a-zA-Z0-9]*\n(.*?)\n```", response, re.DOTALL)
                        if match:
                            clean_script = match.group(1)
                        else:
                            clean_script = response.replace("```", "")
                    repro_script = clean_script

                    # 測試執行生成的腳本
                    success, evidence = self.repro_runner.run_repro(repro_script)

                    # 如果成功 (Return code != 0, 觸發 assert 或 exception)，跳出迴圈
                    if success:
                        break

                    # 如果失敗，判斷是否為腳本本身的語法或匯入錯誤
                    if "ImportError" in evidence or "ModuleNotFoundError" in evidence or "SyntaxError" in evidence or "NameError" in evidence:
                        # 將錯誤反饋給模型，要求修正
                        current_prompt = (
                            f"{base_prompt}\n\n"
                            f"Your previous script failed with the following error:\n"
                            f"```\n{evidence[-1000:]}\n```\n\n"
                            f"Please fix the imports or syntax errors and provide the corrected script."
                        )
                        last_error = evidence
                        continue
                    else:
                        # 如果不是明顯的腳本錯誤，跳出交給後續的 EnvDenoiser 或判定
                        break

                except Exception as e:
                    reason = classify_model_exception(e)
                    model_decision["status"] = reason
                    model_decision["detail"] = str(e)[:500]
                    return ReproductionOutput(success=False, reproduced=False, repro_evidence="", error_reason=reason, model_decision=model_decision)

            if not repro_script:
                model_decision["status"] = "NO_REPRO_SCRIPT"
                return ReproductionOutput(success=False, reproduced=False, repro_evidence=last_error, error_reason="NO_REPRO_SCRIPT", model_decision=model_decision)
        else:
            # 如果輸入已經有腳本，則執行一次
            success, evidence = self.repro_runner.run_repro(repro_script)

        # 3. Deterministic recipe-based env fix (NEW: S1-A)
        recipe_registry = EnvRecipeRegistry()
        recipe_attempts = 0
        max_recipe_attempts = 2
        
        if not success and repro_script and recipe_attempts < max_recipe_attempts:
            # Extract signals from evidence for recipe matching
            signals = []
            evidence_lower = evidence.lower() if evidence else ""
            for kw in ["ImportError", "ModuleNotFoundError", "numpy", "scipy", 
                       "setuptools", "gcc", "compilation", "version", "drift",
                       "sympy", "django", "pytest", "requests",
                       "collections", "Mapping", "MutableMapping",
                       "cannot import name", "mpmath"]:
                if kw.lower() in evidence_lower:
                    signals.append(kw)
            
            recipe = recipe_registry.match(signals)
            if recipe:
                recipe_attempts += 1
                venv_python = str(input_data.repo_dir / ".venv" / "bin" / "python3")
                pip_python = venv_python if Path(venv_python).exists() else "python3"
                
                # Extract package name from evidence
                missing_pkg = None
                pkg_match = re.search(r"No module named '(\w+)'", evidence)
                if pkg_match:
                    missing_pkg = pkg_match.group(1)
                
                for action in recipe.allowed_actions:
                    if "pip install" in action:
                        pkg = missing_pkg or action.replace("pip install ", "").strip("'\"")
                        if pkg and "<" not in pkg:
                            for py in [pip_python, "python3"]:
                                try:
                                    subprocess.run(
                                        ["uv", "pip", "install", pkg, "--python", py],
                                        capture_output=True, text=True, timeout=60
                                    )
                                except Exception:
                                    pass
                    elif "collections" in action.lower() and "shim" in action.lower():
                        # Collections compatibility shim — inject into repro script
                        shim = (
                            "import collections, collections.abc\n"
                            "collections.Mapping = collections.abc.Mapping\n"
                            "collections.MutableMapping = collections.abc.MutableMapping\n"
                        )
                        repro_script = shim + repro_script
                    elif "mock" in action.lower():
                        pass
                    elif "mock" in action.lower():
                        pass
                
                # Re-try reproduction after recipe fix
                success, evidence = self.repro_runner.run_repro(repro_script)
                
                # Record recipe execution in env_denoise_receipt
                env_denoise_receipt = {
                    "recipe_id": recipe.id,
                    "recipe_actions": recipe.allowed_actions,
                    "recipe_succeeded": success,
                    "recipe_attempt": recipe_attempts,
                }
        
        # 4. Legacy env_denoiser auto-heal (existing path)
        if (
            not success
            and repro_script
            and auto_heal_enabled
            and getattr(self, "env_denoiser", None)
        ):
            denoise_result = self.env_denoiser.prepare_from_evidence(evidence)
            if hasattr(denoise_result, "to_receipt"):
                env_denoise_receipt = dict(denoise_result.to_receipt())
            else:
                env_denoise_receipt = {
                    "attempted": getattr(denoise_result, "attempted", False),
                    "succeeded": getattr(denoise_result, "succeeded", False),
                    "reason": getattr(denoise_result, "reason", "")
                }
            if denoise_result.succeeded:
                python_executable = getattr(denoise_result, "python_executable", "")
                if python_executable:
                    self.repro_runner.python_executable = python_executable
                # 換環境後重跑
                success, evidence = self.repro_runner.run_repro(repro_script)

        if not success or not evidence or len(evidence.strip()) < 10:
            if self.repro_runner.is_environment_failure(evidence):
                reason = "REPRO_ENVIRONMENT_FAILURE"
            elif not success and evidence and ("ALREADY_FIXED" in evidence or "exit code 0" in evidence.lower()):
                reason = "ALREADY_FIXED"
            elif not success:
                reason = "REPRO_NOT_REPRODUCED"
            else:
                reason = "REPRO_EVIDENCE_TOO_SHORT"

            # 結構化壓縮證據
            truncated_evidence = EvidenceCompactor.compact(evidence, limit=3000)
            return ReproductionOutput(success=False, reproduced=False, repro_evidence=truncated_evidence, error_reason=reason, env_denoise=env_denoise_receipt, model_decision=model_decision)

        # 成功重現時也壓縮證據以防 Context 爆炸
        truncated_evidence = EvidenceCompactor.compact(evidence, limit=3000)
        return ReproductionOutput(success=True, reproduced=True, repro_evidence=truncated_evidence, env_denoise=env_denoise_receipt, model_decision=model_decision)

    def execute(self, ctx: HealContext) -> PhaseResult:
        if ctx.op.repro_evidence:
            ctx.op.reproduced = True
            return PhaseResult(success=True)

        # P0: SWE-bench mode — skip unreliable LLM reproduction, use issue description as evidence
        if ctx.op.skip_reproduction:
            ctx.op.repro_evidence = ctx.op.problem_statement[:3000]
            ctx.op.reproduced = True
            return PhaseResult(success=True)

        # S3: Workspace provisioning check
        provision = WorkspaceProvisionChecker.check(ctx.op.repo_dir, ctx.op.instance_id)
        if not provision.ready:
            return PhaseResult(
                success=False,
                exit_layer="reprorunner",
                failure_reason=provision.failure_reason or "REPRO_WORKSPACE_MISSING",
            )

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
        if output.env_denoise:
            ctx.op.env_denoise = output.env_denoise
        if output.model_decision:
            ctx.op.model_decisions.append(output.model_decision)

        if not output.success:
            return PhaseResult(success=False, exit_layer="repro_runner", failure_reason=output.failure_reason)

        return PhaseResult(success=True)
