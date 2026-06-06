from typing import Any, List, Tuple, Dict
from pathlib import Path
import difflib
import inspect
from nexus.services.local_heal.interface import IPhase, PhaseResult
from nexus.services.local_heal.protocol import SolidSearchReplaceProtocol, SyntaxGate
from nexus.services.local_heal.patcher import Patcher, PatchResult
from nexus.services.local_heal.validator import validate_effective_change, validate_name_sanity
from nexus.services.local_heal.context import HealContext
from nexus.services.local_heal.errors import PatchError, PatchErrorKind
from nexus.services.local_heal.model_result import classify_model_exception, classify_model_text
from nexus.engine.local_model_policy import LocalModelPolicy
from nexus.services.local_heal.prompt_builder import PromptBuilder

class PatchSynthesisPhase(IPhase):
    """Phase 4: Targeted Edit (Solid SEARCH/REPLACE Protocol Implementation)"""
    def __init__(
        self,
        parser: SolidSearchReplaceProtocol,
        patcher: Patcher,
        ollama_generate_fn: Any | None = None,
        *,
        model_client: Any | None = None,
    ):
        self.parser = parser
        self.patcher = patcher
        self.ollama_generate = ollama_generate_fn or model_client

    def execute(self, ctx: HealContext) -> PhaseResult:
        # 1. 準備治理化 Prompt
        if not ctx.op.system_prompt:
            ctx.op.system_prompt = PromptBuilder.build_patch_system_prompt()
        if not ctx.op.user_prompt:
            ctx.op.user_prompt = PromptBuilder.build_patch_user_prompt(
                ctx.op.problem_statement,
                ctx.op.repro_evidence,
                ctx.op.plan,
                ctx.op.localized_files,
                reasoning_mode=ctx.op.reasoning_mode
            )

        # 2. 模型分流與生成
        patch_decision = self._select_model(ctx, phase="patch")
        response = self._generate_patch(
            ctx,
            model_name=patch_decision["model"],
            timeout_seconds=patch_decision["timeout_seconds"],
            options=patch_decision.get("ollama_options"),
            api_type=patch_decision.get("api_type", "generate"),
        )
        if not response:
            return PhaseResult(success=False, exit_layer="patcher", error_reason=ctx.op.failure_reason or "MODEL_EMPTY_RESPONSE")

        # 3. [FormatGate] 協議解析與拒答偵測
        intents_or_error = self.parser.parse(response)
        if isinstance(intents_or_error, PatchError):
            ctx.op.failure_reason = intents_or_error.kind.name
            self._record_model_status(ctx, ctx.op.failure_reason, phase="patch")
            if intents_or_error.kind == PatchErrorKind.REFUSAL_DETECTED:
                ctx.op.refusal_detected = True
            return PhaseResult(success=False, exit_layer="patcher", error_reason=ctx.op.failure_reason)

        # 4. 逐一應用補丁並執行嚴格驗證
        applied_diffs = []
        for intent in intents_or_error:
            target_path = ctx.op.repo_dir / intent.file_path
            
            # 輔助：處理相對路徑與模糊匹配
            if not target_path.exists():
                found = list(ctx.op.repo_dir.rglob(Path(intent.file_path).name))
                if found: target_path = found[0]

            if not target_path.exists():
                return PhaseResult(success=False, exit_layer="patcher", error_reason=f"FILE_NOT_FOUND:{intent.file_path}")

            source_text = target_path.read_text(encoding="utf-8", errors="replace")

            # A. [MatchGate] 逐字匹配與占位符阻斷
            match_res = self.parser.validate(intent, source_text)
            if not match_res.is_valid:
                return PhaseResult(
                    success=False, 
                    exit_layer="patcher", 
                    error_reason=match_res.error.kind.name,
                    error_metadata={"failed_search_text": intent.search, "file_path": intent.file_path}
                )

            # B. [SyntaxGate] 語法編譯檢查 (ast.parse)
            syntax_res = SyntaxGate.check(intent, source_text)
            ctx.op.syntax_gate_passed = syntax_res.is_valid
            if not syntax_res.is_valid:
                return PhaseResult(
                    success=False, 
                    exit_layer="patcher", 
                    error_reason=syntax_res.error.kind.name,
                    error_metadata={"message": syntax_res.error.message}
                )

            # C. 物理審計：有效變更與命名衛生
            patched_content = source_text.replace(intent.search, intent.replace)
            
            is_effective, eff_err = validate_effective_change(source_text, patched_content)
            if not is_effective:
                return PhaseResult(success=False, exit_layer="patcher", error_reason=f"NO_EFFECTIVE_CHANGE")

            is_sane, sane_err = validate_name_sanity(patched_content)
            if not is_sane:
                return PhaseResult(success=False, exit_layer="patcher", error_reason=f"NAME_SANITY_ERROR", error_metadata={"message": sane_err})

            # D. 寫入檔案與紀錄 Diff
            target_path.write_text(patched_content, encoding="utf-8")
            applied_diffs.append(self._build_file_diff(intent.file_path, source_text, patched_content))

        ctx.op.final_patch = "\n".join(applied_diffs).strip()
        return PhaseResult(success=True)

    def _select_model(self, ctx: HealContext, *, phase: str) -> Dict[str, Any]:
        decision = LocalModelPolicy.select_model(
            task_type="swe_repair",
            phase=phase,
            context={
                "reasoning_mode": ctx.op.reasoning_mode,
                "file_count": len(ctx.op.localized_files) or 1,
                "attempt": ctx.op.attempt,
                "failure_reason": ctx.op.failure_reason,
            },
        )
        ctx.op.model_decisions.append({"phase": phase, **decision})
        return decision

    def _generate_patch(self, ctx: HealContext, *, model_name: str, timeout_seconds: int, options: dict | None = None, api_type: str = "generate") -> str:
        try:
            response = self._call_model(
                ctx.op.system_prompt,
                ctx.op.user_prompt,
                model_name=model_name,
                timeout_seconds=timeout_seconds,
                options=options,
                api_type=api_type,
            )
            model_text_reason = classify_model_text(response)
            if model_text_reason:
                ctx.op.failure_reason = model_text_reason
                self._record_model_status(ctx, model_text_reason, phase="patch")
                return ""
            return response
        except Exception as e:
            reason = classify_model_exception(e)
            ctx.op.failure_reason = reason
            self._record_model_status(ctx, reason, detail=f"{type(e).__name__}: {e}", phase="patch")
            return ""

    def _record_model_status(self, ctx: HealContext, status: str, detail: str = "", *, phase: str | None = None) -> None:
        for decision in reversed(ctx.op.model_decisions):
            if phase is None or decision.get("phase") == phase:
                decision["status"] = status
                if detail:
                    decision["detail"] = detail[:500]
                return

    def _call_model(self, system_prompt: str, user_prompt: str, *, model_name: str, timeout_seconds: int | None = None, options: dict | None = None, api_type: str = "generate") -> str:
        try:
            sig = inspect.signature(self.ollama_generate)
            kwargs = {}
            if "model" in sig.parameters:
                kwargs["model"] = model_name
            if "timeout" in sig.parameters and timeout_seconds is not None:
                kwargs["timeout"] = timeout_seconds
            if "options" in sig.parameters and options is not None:
                kwargs["options"] = options
            if "api_type" in sig.parameters:
                kwargs["api_type"] = api_type
            if kwargs:
                return self.ollama_generate(system_prompt, user_prompt, **kwargs)
        except (TypeError, ValueError):
            pass
        return self.ollama_generate(system_prompt, user_prompt)

    def _build_file_diff(self, relative_path: str, old_content: str, new_content: str) -> str:
        return "".join(difflib.unified_diff(
            old_content.splitlines(keepends=True),
            new_content.splitlines(keepends=True),
            fromfile=f"a/{relative_path}",
            tofile=f"b/{relative_path}",
            lineterm="\n",
        ))
