from typing import Any, List, Tuple, Dict
from pathlib import Path
import difflib
import inspect
from nexus.services.local_heal.interface import IPhase, PhaseResult
from nexus.services.local_heal.parser import SearchReplaceParser
from nexus.services.local_heal.patcher import Patcher, PatchResult
from nexus.services.local_heal.validator import validate_syntax, validate_effective_change, validate_name_sanity
from nexus.services.local_heal.context import HealContext
from nexus.services.local_heal.errors import PatchError, PatchErrorKind
from nexus.services.local_heal.model_result import classify_model_exception, classify_model_text
from nexus.engine.local_model_policy import LocalModelPolicy

from nexus.services.local_heal.prompt_builder import PromptBuilder

class PatchSynthesisPhase(IPhase):
    """Phase 4: Targeted Edit (單次補丁生成與套用)"""
    def __init__(self, parser: SearchReplaceParser, patcher: Patcher, ollama_generate_fn: Any):
        self.parser = parser
        self.patcher = patcher
        self.ollama_generate = ollama_generate_fn

    def execute(self, ctx: HealContext) -> PhaseResult:
        # 1. 準備 Prompt (如果尚未準備)
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

        # 2. 選擇模型與參數
        patch_decision = self._select_model(ctx, phase="patch")
        
        # 2. 生成補丁
        ctx.op.prompt_variant_id = "aider-strict-v1"
        response = self._generate_patch(
            ctx,
            model_name=patch_decision["model"],
            timeout_seconds=patch_decision["timeout_seconds"],
        )
        if not response:
            ctx.op.empty_response = True
            return PhaseResult(success=False, exit_layer="patcher", error_reason=ctx.op.failure_reason or "MODEL_EMPTY_RESPONSE")
        
        if "MODEL_REFUSAL" in (ctx.op.failure_reason or ""):
            ctx.op.refusal_detected = True

        # 3. 解析補丁塊
        blocks = self.parser.parse_blocks(response)
        if not blocks:
            err_reason = "NO_BLOCKS_FOUND"
            ctx.op.failure_reason = err_reason
            self._record_model_status(ctx, err_reason, phase="patch")
            return PhaseResult(success=False, exit_layer="patcher", error_reason=err_reason)

        if any(b.get("has_placeholder") for b in blocks):
            err_reason = "SEARCH_HAS_PLACEHOLDER"
            ctx.op.failure_reason = err_reason
            self._record_model_status(ctx, err_reason, phase="patch")
            return PhaseResult(success=False, exit_layer="patcher", error_reason=err_reason)

        # 4. 套用補丁並收集 Diff
        applied_diffs = []
        for b in blocks:
            target_path = ctx.op.repo_dir / b["file"]
            
            # 處理新增檔案
            if b.get("operation") == "create":
                create_res = self._apply_create_file(ctx, b, target_path)
                if not create_res.success:
                    return PhaseResult(
                        success=False, 
                        exit_layer="patcher", 
                        error_reason=f"CREATE_FILE_FAILED:{create_res.error_message}",
                        error_metadata={"syntax_gate_passed": create_res.syntax_gate_passed}
                    )
                applied_diffs.append(create_res.diff)
                continue

            # 處理路徑尋找 (如果路徑不完全匹配)
            if not target_path.exists():
                found = list(ctx.op.repo_dir.rglob(Path(b["file"]).name))
                target_path = found[0] if found else target_path

            if not target_path.exists():
                return PhaseResult(success=False, exit_layer="patcher", error_reason=f"FILE_NOT_FOUND:{b['file']}")

            file_content = target_path.read_text(encoding="utf-8", errors="replace")

            # 套用補丁 (開啟語法前檢)
            context_hints = ctx.op.plan.get("search_symbols", [])
            patch_res = self.patcher.apply_patch(file_content, b["search"], b["replace"], context_hints=context_hints, validate_syntax_gate=True)

            ctx.op.syntax_gate_passed = patch_res.syntax_gate_passed

            if not patch_res.success:
                return PhaseResult(
                    success=False, 
                    exit_layer="patcher", 
                    error_reason=patch_res.error_message or "SEARCH_MISMATCH",
                    error_metadata={
                        "failed_search_text": b["search"], 
                        "file_path": b["file"],
                        "syntax_gate_passed": patch_res.syntax_gate_passed
                    }
                )

            # 物理審計 (有效性、命名)
            is_effective, effective_err = validate_effective_change(file_content, patch_res.new_content)
            if not is_effective:
                return PhaseResult(success=False, exit_layer="patcher", error_reason=f"NO_EFFECTIVE_CHANGE:{effective_err}")

            is_sane, sanity_err = validate_name_sanity(patch_res.new_content)
            if not is_sane:
                return PhaseResult(success=False, exit_layer="patcher", error_reason=f"NAME_SANITY_ERROR:{sanity_err}")

            target_path.write_text(patch_res.new_content, encoding="utf-8")
            applied_diffs.append(self._build_file_diff(b["file"], file_content, patch_res.new_content))

        ctx.op.final_patch = "\n".join(applied_diffs).strip()
        return PhaseResult(success=True)

    def _select_model(self, ctx: HealContext, *, phase: str) -> Dict[str, Any]:
        decision = LocalModelPolicy.select_model(
            task_type="swe_repair",
            phase=phase,
            context={
                "reasoning_mode": ctx.op.reasoning_mode,
                "file_count": len(ctx.op.localized_files) or 1,
            },
        )
        ctx.op.model_decisions.append({"phase": phase, **decision})
        return decision

    def _generate_patch(self, ctx: HealContext, *, model_name: str, timeout_seconds: int) -> str:
        try:
            response = self._call_model(
                ctx.op.system_prompt,
                ctx.op.user_prompt,
                model_name=model_name,
                timeout_seconds=timeout_seconds,
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

    def _apply_create_file(self, ctx: HealContext, block: Dict[str, Any], target_path: Path) -> PatchResult:
        try:
            target_path.resolve().relative_to(ctx.op.repo_dir.resolve())
        except ValueError:
            return PatchResult(False, "", "", "Create-file path escapes the repository root")

        if target_path.exists():
            return PatchResult(False, target_path.read_text(encoding="utf-8", errors="replace"), "", "Target file already exists")

        new_content = block["replace"]
        if new_content and not new_content.endswith("\n"):
            new_content += "\n"
        
        # 語法前檢 (Syntax Preflight for Create)
        is_valid, syntax_err = validate_syntax(new_content)
        if not is_valid:
            return PatchResult(False, "", "", f"SYNTAX_ERROR:{syntax_err}", syntax_gate_passed=False)

        is_sane, sanity_err = validate_name_sanity(new_content)
        if not is_sane:
            return PatchResult(False, "", "", sanity_err)

        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text(new_content, encoding="utf-8")
        diff_body = "".join(difflib.unified_diff(
            [],
            new_content.splitlines(keepends=True),
            fromfile="/dev/null",
            tofile=f"b/{block['file']}",
            lineterm="\n",
        ))
        return PatchResult(
            True,
            new_content,
            f"diff --git a/{block['file']} b/{block['file']}\nnew file mode 100644\n{diff_body}",
        )

    def _build_file_diff(self, relative_path: str, old_content: str, new_content: str) -> str:
        return "".join(difflib.unified_diff(
            old_content.splitlines(keepends=True),
            new_content.splitlines(keepends=True),
            fromfile=f"a/{relative_path}",
            tofile=f"b/{relative_path}",
            lineterm="\n",
        ))
