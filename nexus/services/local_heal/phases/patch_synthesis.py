from typing import Any, List, Tuple, Dict
from pathlib import Path
from nexus.services.local_heal.interface import IPhase, PhaseResult, PatchSynthesisInput, PatchSynthesisOutput
from nexus.services.local_heal.protocol import SolidSearchReplaceProtocol
from nexus.services.local_heal.patcher import Patcher
from nexus.services.local_heal.context import HealContext
from nexus.services.local_heal.errors import PatchError, PatchErrorKind
from nexus.services.local_heal.model_result import classify_model_exception, classify_model_text
from nexus.engine.local_model_policy import LocalModelPolicy
from nexus.services.local_heal.prompt_builder import PromptBuilder
from nexus.services.local_heal.llm_client import ILLMClient, OllamaLLMClient
from nexus.services.local_heal.surgical_context import SurgicalContextBuilder
from nexus.services.local_heal.patch_applier import PatchApplier

class PatchSynthesisPhase(IPhase):
    """Phase 4: Targeted Edit (Solid SEARCH/REPLACE Protocol Implementation) - Refactored according to Clean Code & Linus principles"""
    
    def __init__(
        self,
        parser: SolidSearchReplaceProtocol,
        patcher: Patcher,
        ollama_generate_fn: Any | None = None,
        *,
        model_client: Any | None = None,
        llm_client: ILLMClient | None = None,
        context_builder: SurgicalContextBuilder | None = None,
        patch_applier: PatchApplier | None = None,
    ):
        self.parser = parser
        self.patcher = patcher
        if llm_client:
            self.llm_client = llm_client
        elif ollama_generate_fn or model_client:
            self.llm_client = OllamaLLMClient(ollama_generate_fn or model_client)
        else:
            self.llm_client = None

        self.context_builder = context_builder or SurgicalContextBuilder()
        self.patch_applier = patch_applier or PatchApplier(parser, patcher)

    def run(self, input_data: PatchSynthesisInput) -> PatchSynthesisOutput:
        """Stateless, decoupled TDD-ready execution logic."""
        model_decisions = []
        user_prompt = input_data.user_prompt
        system_prompt = input_data.system_prompt

        # 1. 外科手術級 Localized Context 準備
        surgical_files = []
        for rel_path, content in input_data.localized_files:
            target_path = input_data.repo_dir / rel_path
            if not target_path.exists():
                found = list(input_data.repo_dir.rglob(Path(rel_path).name))
                if found:
                    target_path = found[0]

            source_text = content
            if target_path.exists():
                try:
                    source_text = target_path.read_text(encoding="utf-8", errors="replace")
                except Exception:
                    pass

            annotated = self.context_builder.build_annotated_context(
                repo_dir=input_data.repo_dir,
                rel_path=rel_path,
                source_text=source_text,
                attempt=input_data.attempt,
                failure_reason=input_data.failure_reason or "",
                plan=input_data.plan,
                user_prompt=input_data.user_prompt or user_prompt
            )
            surgical_files.append((rel_path, annotated))

        # 2. 模型分流與生成選擇
        patch_decision = LocalModelPolicy.select_model(
            task_type="swe_repair",
            phase="patch",
            context={
                "reasoning_mode": input_data.reasoning_mode,
                "file_count": len(input_data.localized_files) or 1,
                "attempt": input_data.attempt,
                "failure_reason": input_data.failure_reason,
            },
        )
        model_decisions.append({"phase": "patch", **patch_decision})

        # 3. 準備治理化 Prompt — use interleaved mode if planning was LLM-based
        use_interleaved = not input_data.plan.get("repair_strategy", "").startswith("FAST_MODE")
        if not system_prompt:
            system_prompt = PromptBuilder.build_patch_system_prompt(
                patch_decision["model"], 
                interleaved=use_interleaved
            )

        # 追加上一輪失敗的 HUD 警告資訊
        hud_retry_info = ""
        marker = "\n\n⚠️ [NEXUS BATTLESUIT HUD: CRITICAL WARNING - PREVIOUS ATTEMPT FAILED]"
        if input_data.user_prompt and marker in input_data.user_prompt:
            hud_retry_info = marker + input_data.user_prompt.split(marker)[1]

        user_prompt = PromptBuilder.build_patch_user_prompt(
            input_data.problem_statement,
            input_data.repro_evidence,
            input_data.plan,
            surgical_files,
            reasoning_mode=input_data.reasoning_mode,
            failure_reason=input_data.failure_reason or "",
            attempt=input_data.attempt,
            project_root=input_data.repo_dir,
        )
        if hud_retry_info:
            user_prompt += hud_retry_info

        if not self.llm_client:
            return PatchSynthesisOutput(
                success=False,
                final_patch="",
                model_decisions=model_decisions,
                error_reason="NO_LLM_CLIENT"
            )

        try:
            response = self.llm_client.generate(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                model=patch_decision["model"],
                timeout=patch_decision["timeout_seconds"],
                options=patch_decision.get("ollama_options"),
                api_type=patch_decision.get("api_type", "generate")
            )
        except Exception as e:
            reason = classify_model_exception(e)
            model_decisions[-1]["status"] = reason
            model_decisions[-1]["detail"] = f"{type(e).__name__}: {e}"[:500]
            return PatchSynthesisOutput(
                success=False,
                final_patch="",
                model_decisions=model_decisions,
                error_reason=reason
            )

        if not response:
            model_decisions[-1]["status"] = "MODEL_EMPTY_RESPONSE"
            return PatchSynthesisOutput(
                success=False,
                final_patch="",
                model_decisions=model_decisions,
                error_reason="MODEL_EMPTY_RESPONSE"
            )

        model_text_reason = classify_model_text(response)
        if model_text_reason:
            model_decisions[-1]["status"] = model_text_reason
            return PatchSynthesisOutput(
                success=False,
                final_patch="",
                model_decisions=model_decisions,
                error_reason=model_text_reason,
                refusal_detected=(model_text_reason == "REFUSAL_DETECTED")
            )

        # 4. [FormatGate] 協議解析與拒答偵測
        intents_or_error = self.parser.parse(response)
        if isinstance(intents_or_error, PatchError):
            model_decisions[-1]["status"] = intents_or_error.kind.name
            return PatchSynthesisOutput(
                success=False,
                final_patch="",
                model_decisions=model_decisions,
                error_reason=intents_or_error.kind.name,
                refusal_detected=(intents_or_error.kind == PatchErrorKind.REFUSAL_DETECTED)
            )

        # 5. 逐一應用補丁並執行嚴格驗證 (透過解耦後的 PatchApplier)
        apply_res = self.patch_applier.apply_and_validate(
            intents=intents_or_error,
            repo_dir=input_data.repo_dir,
            localized_files=input_data.localized_files
        )

        model_decisions[-1]["status"] = "SUCCESS" if apply_res.success else apply_res.error_reason
        return PatchSynthesisOutput(
            success=apply_res.success,
            final_patch="\n".join(apply_res.applied_diffs).strip() if apply_res.success else "",
            model_decisions=model_decisions,
            error_reason=apply_res.error_reason or "",
            syntax_gate_passed=apply_res.syntax_gate_passed
        )

    def execute(self, ctx: HealContext) -> PhaseResult:
        input_data = PatchSynthesisInput(
            instance_id=ctx.op.instance_id,
            problem_statement=ctx.op.problem_statement,
            repro_evidence=ctx.op.repro_evidence,
            plan=ctx.op.plan,
            localized_files=ctx.op.localized_files,
            repo_dir=ctx.op.repo_dir,
            reasoning_mode=ctx.op.reasoning_mode,
            attempt=ctx.op.attempt,
            max_tries=ctx.op.max_tries,
            system_prompt=ctx.op.system_prompt,
            user_prompt=ctx.op.user_prompt,
            failure_reason=ctx.op.failure_reason
        )

        output = self.run(input_data)

        ctx.op.model_decisions.extend(output.model_decisions)
        ctx.op.final_patch = output.final_patch
        ctx.op.syntax_gate_passed = output.syntax_gate_passed
        ctx.op.refusal_detected = output.refusal_detected
        ctx.op.empty_response = output.empty_response

        if not output.success:
            ctx.op.failure_reason = output.error_reason
            return PhaseResult(success=False, exit_layer="patcher", error_reason=output.error_reason)

        return PhaseResult(success=True)
