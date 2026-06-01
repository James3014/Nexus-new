import difflib
import inspect
from pathlib import Path
from typing import Any, Dict

from nexus.engine.local_model_policy import LocalModelPolicy
from nexus.services.local_heal.corrector import SelfCorrector
from nexus.services.local_heal.interface import IPhase, PhaseResult
from nexus.services.local_heal.parser import SearchReplaceParser
from nexus.services.local_heal.patcher import Patcher, PatchResult
from nexus.services.local_heal.validator import validate_syntax, validate_effective_change, validate_name_sanity
from nexus.services.local_heal.context import HealContext
from nexus.services.local_heal.errors import PatchError, PatchErrorKind

class PatchSynthesisPhase(IPhase):
    """Phase 4: Targeted edit synthesis and physical patch application."""

    def __init__(
        self,
        parser: SearchReplaceParser,
        patcher: Patcher,
        model_client: Any,
        corrector: SelfCorrector | None = None,
    ):
        self.parser = parser
        self.patcher = patcher
        self.model_client = model_client
        self.corrector = corrector or SelfCorrector()

    def execute(self, ctx: HealContext) -> PhaseResult:
        self._ensure_prompts(ctx)

        while ctx.op.attempt <= ctx.op.max_tries:
            ctx.op.errors.clear()
            decision = self._select_model(ctx)
            response = self._call_model(
                ctx.op.system_prompt,
                ctx.op.user_prompt,
                model_name=decision["model"],
                timeout_seconds=decision["timeout_seconds"],
            )
            if not response:
                return self._fail(ctx, "patch_synthesis", "MODEL_EMPTY_RESPONSE")

            blocks = self.parser.parse_blocks(response)
            if not blocks:
                if not self._retry(ctx, PatchError(PatchErrorKind.NO_BLOCKS_FOUND, "No SEARCH/REPLACE blocks found.")):
                    return self._fail(ctx, "patch_synthesis", self._latest_error(ctx))
                continue

            applied_diffs: list[str] = []
            error = self._apply_blocks(ctx, blocks, applied_diffs)
            if error:
                if not self._retry(ctx, error):
                    return self._fail(ctx, "patch_synthesis", self._latest_error(ctx))
                continue

            ctx.op.final_patch = "\n".join(applied_diffs).strip()
            return PhaseResult(success=True)

        return self._fail(ctx, "patch_synthesis", self._latest_error(ctx))

    def _ensure_prompts(self, ctx: HealContext) -> None:
        if not ctx.op.system_prompt:
            ctx.op.system_prompt = (
                "You are a senior software engineer. Output only valid SEARCH/REPLACE blocks. "
                "Prefer the smallest existing function that directly computes the wrong value."
            )
        if ctx.op.user_prompt:
            return

        file_ctx = "\n\n".join(
            f"=== FILE: {name} ===\n{content}" for name, content in ctx.op.localized_files
        )
        ctx.op.user_prompt = (
            f"Bug Report:\n{ctx.op.problem_statement[:1500]}\n\n"
            f"Source Code:\n{file_ctx}\n\n"
            f"### [NEXUS STRATEGIC PLAN]\n{ctx.op.plan.get('repair_strategy', 'N/A')}\n\n"
            f"### [REPRODUCTION EVIDENCE]\n```\n{ctx.op.repro_evidence[:1000]}\n```\n\n"
            "Output SEARCH/REPLACE block(s):"
        )

    def _select_model(self, ctx: HealContext) -> Dict[str, Any]:
        decision = LocalModelPolicy.select_model(
            task_type="swe_repair",
            phase="patch",
            context={
                "reasoning_mode": ctx.op.reasoning_mode,
                "file_count": len(ctx.op.localized_files) or 1,
            },
        )
        ctx.op.model_decisions.append({"phase": "patch", **decision})
        return decision

    def _call_model(self, system_prompt: str, user_prompt: str, *, model_name: str, timeout_seconds: int) -> str:
        try:
            sig = inspect.signature(self.model_client)
            kwargs: dict[str, Any] = {}
            if "model" in sig.parameters:
                kwargs["model"] = model_name
            if "timeout" in sig.parameters:
                kwargs["timeout"] = timeout_seconds
            return self.model_client(system_prompt, user_prompt, **kwargs)
        except (TypeError, ValueError):
            return self.model_client(system_prompt, user_prompt)

    def _apply_blocks(
        self,
        ctx: HealContext,
        blocks: list[dict[str, Any]],
        applied_diffs: list[str],
    ) -> PatchError | None:
        for block in blocks:
            if block.get("has_placeholder"):
                return PatchError(PatchErrorKind.SEARCH_HAS_PLACEHOLDER, "SEARCH/REPLACE contains placeholders.")

            target_path = self._resolve_target_path(ctx, block["file"])
            if not target_path.exists():
                return PatchError(PatchErrorKind.FILE_NOT_FOUND, f"File not found: {block['file']}", file_path=block["file"])

            file_content = target_path.read_text(encoding="utf-8", errors="replace")
            patch_res = self.patcher.apply_patch(
                file_content,
                block["search"],
                block["replace"],
                context_hints=ctx.op.plan.get("search_symbols", []),
            )
            if not patch_res.success:
                return PatchError(
                    PatchErrorKind.SEARCH_MISMATCH,
                    patch_res.error_message,
                    file_path=block["file"],
                    failed_search_text=block["search"],
                )

            validation_error = self._validate_patch(block["file"], file_content, patch_res)
            if validation_error:
                return validation_error

            target_path.write_text(patch_res.new_content, encoding="utf-8")
            applied_diffs.append(self._build_file_diff(block["file"], file_content, patch_res.new_content))
        return None

    def _resolve_target_path(self, ctx: HealContext, relative_path: str) -> Path:
        target_path = ctx.op.repo_dir / relative_path
        if target_path.exists():
            return target_path
        found = list(ctx.op.repo_dir.rglob(Path(relative_path).name))
        return found[0] if found else target_path

    def _validate_patch(self, file_path: str, old_content: str, patch_res: PatchResult) -> PatchError | None:
        is_valid, syntax_err = validate_syntax(patch_res.new_content)
        if not is_valid:
            return PatchError(PatchErrorKind.SYNTAX_ERROR, syntax_err, file_path=file_path)

        is_effective, effective_err = validate_effective_change(old_content, patch_res.new_content)
        if not is_effective:
            return PatchError(PatchErrorKind.NO_EFFECTIVE_CODE_CHANGE, effective_err, file_path=file_path)

        is_sane, sanity_err = validate_name_sanity(patch_res.new_content)
        if not is_sane:
            return PatchError(PatchErrorKind.SYNTAX_ERROR, sanity_err, file_path=file_path)
        return None

    def _build_file_diff(self, relative_path: str, old_content: str, new_content: str) -> str:
        return "".join(
            difflib.unified_diff(
                old_content.splitlines(keepends=True),
                new_content.splitlines(keepends=True),
                fromfile=f"a/{relative_path}",
                tofile=f"b/{relative_path}",
                lineterm="\n",
            )
        )

    def _retry(self, ctx: HealContext, error: PatchError) -> bool:
        ctx.op.errors.append(error)
        ctx.op.attempt += 1
        if ctx.op.attempt > ctx.op.max_tries:
            return False
        ctx.op.user_prompt = self.corrector.build_retry_prompt(ctx.op.user_prompt, error)
        return True

    def _latest_error(self, ctx: HealContext) -> str:
        if not ctx.op.errors:
            return "NO_PATCH"
        latest = ctx.op.errors[-1]
        kind = getattr(latest.kind, "name", str(latest.kind))
        message = str(latest.message or "").strip()
        return f"{kind}:{message}" if message else kind

    def _fail(self, ctx: HealContext, exit_layer: str, reason: str) -> PhaseResult:
        ctx.op.failure_reason = reason
        ctx.op.final_patch = ""
        return PhaseResult(success=False, exit_layer=exit_layer, error_reason=reason)
