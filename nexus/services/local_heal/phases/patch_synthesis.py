from typing import Any, List, Tuple, Dict
from pathlib import Path
import difflib
from nexus.services.local_heal.interface import IPhase, PhaseResult, PatchSynthesisInput, PatchSynthesisOutput
from nexus.services.local_heal.protocol import SolidSearchReplaceProtocol, SyntaxGate
from nexus.services.local_heal.patcher import Patcher
from nexus.services.local_heal.validator import validate_effective_change, validate_name_sanity
from nexus.services.local_heal.context import HealContext
from nexus.services.local_heal.errors import PatchError, PatchErrorKind
from nexus.services.local_heal.model_result import classify_model_exception, classify_model_text
from nexus.engine.local_model_policy import LocalModelPolicy
from nexus.services.local_heal.prompt_builder import PromptBuilder
from nexus.services.local_heal.llm_client import ILLMClient, OllamaLLMClient

class PatchSynthesisPhase(IPhase):
    """Phase 4: Targeted Edit (Solid SEARCH/REPLACE Protocol Implementation)"""
    def __init__(
        self,
        parser: SolidSearchReplaceProtocol,
        patcher: Patcher,
        ollama_generate_fn: Any | None = None,
        *,
        model_client: Any | None = None,
        llm_client: ILLMClient | None = None,
    ):
        self.parser = parser
        self.patcher = patcher
        if llm_client:
            self.llm_client = llm_client
        elif ollama_generate_fn or model_client:
            self.llm_client = OllamaLLMClient(ollama_generate_fn or model_client)
        else:
            self.llm_client = None

    def run(self, input_data: PatchSynthesisInput) -> PatchSynthesisOutput:
        """Stateless, decoupled TDD-ready execution logic."""
        model_decisions = []
        system_prompt = input_data.system_prompt
        user_prompt = input_data.user_prompt

        # 若是重試且前次為 SEARCH_MISMATCH，則改以完整文件內容作為 context 重建 user_prompt
        if input_data.attempt > 1 and input_data.failure_reason and "SEARCH_MISMATCH" in input_data.failure_reason:
            marker = "\n\n⚠️ [NEXUS BATTLESUIT HUD: CRITICAL WARNING - PREVIOUS ATTEMPT FAILED]"
            hud_retry_info = ""
            if user_prompt and marker in user_prompt:
                hud_retry_info = marker + user_prompt.split(marker)[1]

            fallback_localized_files = []
            for rel_path, _ in input_data.localized_files:
                target_path = input_data.repo_dir / rel_path
                if not target_path.exists():
                    found = list(input_data.repo_dir.rglob(Path(rel_path).name))
                    if found: target_path = found[0]
                if target_path.exists():
                    try:
                        full_content = target_path.read_text(encoding="utf-8", errors="replace")
                        # 幫完整檔案內容加上行號標記
                        lines = full_content.splitlines()
                        annotated_lines = []
                        for i, line in enumerate(lines):
                            annotated_lines.append(f"{i + 1:4d} | {line}")
                        annotated_content = (
                            "# NOTE: Line numbers shown for reference. Your SEARCH block must use verbatim code WITHOUT line numbers.\n"
                            + "\n".join(annotated_lines)
                        )
                        fallback_localized_files.append((rel_path, annotated_content))
                    except Exception:
                        pass
            
            if fallback_localized_files:
                user_prompt = PromptBuilder.build_patch_user_prompt(
                    input_data.problem_statement,
                    input_data.repro_evidence,
                    input_data.plan,
                    fallback_localized_files,
                    reasoning_mode=input_data.reasoning_mode
                )
                if hud_retry_info:
                    user_prompt += hud_retry_info

        # 1. 準備治理化 Prompt
        if not system_prompt:
            system_prompt = PromptBuilder.build_patch_system_prompt()
        if not user_prompt:
            user_prompt = PromptBuilder.build_patch_user_prompt(
                input_data.problem_statement,
                input_data.repro_evidence,
                input_data.plan,
                input_data.localized_files,
                reasoning_mode=input_data.reasoning_mode
            )

        # 2. 模型分流與生成
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

        # 3. [FormatGate] 協議解析與拒答偵測
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

        # 4. 逐一應用補丁並執行嚴格驗證
        applied_diffs = []
        syntax_gate_passed = True
        for intent in intents_or_error:
            target_path = input_data.repo_dir / intent.file_path
            
            # 輔助：處理相對路徑與模糊匹配
            if not target_path.exists():
                found = list(input_data.repo_dir.rglob(Path(intent.file_path).name))
                if found: target_path = found[0]

            if not target_path.exists():
                model_decisions[-1]["status"] = f"FILE_NOT_FOUND:{intent.file_path}"
                return PatchSynthesisOutput(
                    success=False,
                    final_patch="",
                    model_decisions=model_decisions,
                    error_reason=f"FILE_NOT_FOUND:{intent.file_path}"
                )

            source_text = target_path.read_text(encoding="utf-8", errors="replace")

            # A. [MatchGate] 逐字匹配與占位符阻斷
            match_res = self.parser.validate(intent, source_text)
            if not match_res.is_valid:
                model_decisions[-1]["status"] = match_res.error.kind.name
                return PatchSynthesisOutput(
                    success=False,
                    final_patch="",
                    model_decisions=model_decisions,
                    error_reason=match_res.error.kind.name
                )

            # B. [SyntaxGate] 語法編譯檢查 (ast.parse)
            syntax_res = SyntaxGate.check(intent, source_text)
            syntax_gate_passed = syntax_res.is_valid
            if not syntax_res.is_valid:
                model_decisions[-1]["status"] = syntax_res.error.kind.name
                return PatchSynthesisOutput(
                    success=False,
                    final_patch="",
                    model_decisions=model_decisions,
                    error_reason=syntax_res.error.kind.name,
                    syntax_gate_passed=False
                )

            # C. [SemanticsGate] 語意安全檢查（空改動 / NameSanity）
            patched_content = source_text.replace(intent.search, intent.replace)
            
            is_effective, eff_err = validate_effective_change(source_text, patched_content)
            if not is_effective:
                model_decisions[-1]["status"] = "NO_EFFECTIVE_CHANGE"
                return PatchSynthesisOutput(
                    success=False,
                    final_patch="",
                    model_decisions=model_decisions,
                    error_reason="NO_EFFECTIVE_CHANGE"
                )

            is_sane, sane_err = validate_name_sanity(patched_content)
            if not is_sane:
                model_decisions[-1]["status"] = "NAME_SANITY_ERROR"
                return PatchSynthesisOutput(
                    success=False,
                    final_patch="",
                    model_decisions=model_decisions,
                    error_reason="NAME_SANITY_ERROR"
                )

            # D. 寫入檔案與紀錄 Diff
            target_path.write_text(patched_content, encoding="utf-8")
            applied_diffs.append(self._build_file_diff(intent.file_path, source_text, patched_content))

        final_patch = "\n".join(applied_diffs).strip()
        model_decisions[-1]["status"] = "SUCCESS"
        return PatchSynthesisOutput(
            success=True,
            final_patch=final_patch,
            model_decisions=model_decisions,
            syntax_gate_passed=syntax_gate_passed
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

    def _build_file_diff(self, relative_path: str, old_content: str, new_content: str) -> str:
        return "".join(difflib.unified_diff(
            old_content.splitlines(keepends=True),
            new_content.splitlines(keepends=True),
            fromfile=f"a/{relative_path}",
            tofile=f"b/{relative_path}",
            lineterm="\n",
        ))
