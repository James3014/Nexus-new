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
from nexus.services.local_heal.micro_verifier import MicroVerifier

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
        # Filter out repro/test scripts — they are not patch targets (created/deleted by verification)
        _PATCH_BLACKLIST = {"reproduce_bug.py", "repro.py", "test_repro.py"}
        patchable_files = [
            (loc_file.path, loc_file.content)
            for loc_file in input_data.localized_files
            if Path(loc_file.path).name not in _PATCH_BLACKLIST
        ]
        surgical_files = []
        for rel_path, content in patchable_files:
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

            from nexus.services.local_heal.interface import LocalizedFile
            annotated = self.context_builder.build_annotated_context(
                repo_dir=input_data.repo_dir,
                rel_path=rel_path,
                source_text=source_text,
                attempt=input_data.attempt,
                failure_reason=input_data.failure_reason or "",
                plan=input_data.plan,
                user_prompt=input_data.user_prompt or user_prompt
            )
            surgical_files.append(LocalizedFile(path=rel_path, content=annotated))

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
        if input_data.committee_model_override:
            patch_decision = {
                **patch_decision,
                "model": input_data.committee_model_override,
                "reason_code": "committee_explicit_proposer_override",
                "ollama_options": LocalModelPolicy.select_model(
                    task_type="swe_repair",
                    phase="patch",
                    context={
                        "reasoning_mode": input_data.reasoning_mode,
                        "file_count": len(input_data.localized_files) or 1,
                        "attempt": input_data.attempt,
                        "failure_reason": input_data.failure_reason,
                    },
                ).get("ollama_options"),
            }
        model_decisions.append({"phase": "patch", **patch_decision})

        # 3. [Specification-Centric Repair] 生成修復規格 (若尚未存在)
        repair_spec = getattr(input_data, "repair_specification", "")
        if not repair_spec and patch_decision["model"] != "deterministic":
            spec_decision = LocalModelPolicy.select_model(task_type="swe_repair", phase="planning", context={"mode": "spec_gen"})
            spec_prompt = f"Based on the problem and localized code, output a concise logical specification of the fix (Intents only, no code blocks):\n\nProblem: {input_data.problem_statement[:1000]}\nPlan: {input_data.plan.repair_strategy if input_data.plan else ''}"
            try:
                repair_spec = self.llm_client.generate(
                    system_prompt="You are a senior engineer. Define the exact logical change needed.",
                    user_prompt=spec_prompt,
                    model=spec_decision["model"],
                    timeout=spec_decision["timeout_seconds"],
                    options=spec_decision.get("ollama_options")
                )
                model_decisions.append({"phase": "repair_spec", **spec_decision, "status": "SUCCESS"})
            except Exception:
                repair_spec = "Apply surgical fix as planned."

        # 4. 準備治理化 Prompt — use interleaved mode if planning was LLM-based
        plan = input_data.plan
        repair_strat = getattr(plan, "repair_strategy", "")
        use_interleaved = not repair_strat.startswith("FAST_MODE")
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

        # 計算 Prompt Token Budget: 保留至少 2048 給生成
        ollama_options = patch_decision.get("ollama_options") or {}
        num_ctx = ollama_options.get("num_ctx", 8192)
        safe_prompt_budget = max(2048, num_ctx - 2048)

        user_prompt = PromptBuilder.build_patch_user_prompt(
            input_data.problem_statement,
            input_data.repro_evidence,
            input_data.plan,
            surgical_files,
            reasoning_mode=input_data.reasoning_mode,
            failure_reason=input_data.failure_reason or "",
            attempt=input_data.attempt,
            project_root=input_data.repo_dir,
            max_prompt_tokens=safe_prompt_budget,
            repair_specification=repair_spec
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

        # S4 Patch Protocol Guard
        import os
        protocol_mode = os.getenv("NEXUS_PROTOCOL_MODE", "standard")
        if (
            input_data.attempt > 1
            and protocol_mode == "control_plane_search_model_replace"
            and hasattr(input_data, "last_search_anchors")
            and input_data.last_search_anchors
        ):
            for intent in intents_or_error:
                matched_previous = False
                for prev_search in input_data.last_search_anchors:
                    if intent.search.strip() == prev_search.strip():
                        matched_previous = True
                        break
                if not matched_previous:
                    model_decisions[-1]["status"] = "SEARCH_MODIFIED_GUARD_BLOCKED"
                    return PatchSynthesisOutput(
                        success=False,
                        final_patch="",
                        model_decisions=model_decisions,
                        error_reason="SEARCH_MISMATCH",
                        errors=[PatchError(
                            kind=PatchErrorKind.SEARCH_MISMATCH,
                            message="SEARCH anchor modified during retry under control_plane_search_model_replace policy",
                            file_path=intent.file_path,
                            failed_search_text=intent.search
                        )]
                    )

        # P4 Behavior Collapse Guard
        if (
            input_data.attempt > 1
            and hasattr(input_data, "last_replacement_texts")
            and input_data.last_replacement_texts
            and not isinstance(intents_or_error, PatchError)
        ):
            for intent in intents_or_error:
                if intent.replace.strip() in [r.strip() for r in input_data.last_replacement_texts]:
                    model_decisions[-1]["status"] = "BEHAVIOR_COLLAPSE_GUARD_BLOCKED"
                    return PatchSynthesisOutput(
                        success=False,
                        final_patch="",
                        model_decisions=model_decisions,
                        error_reason="BEHAVIOR_COLLAPSE",
                        errors=[PatchError(
                            kind=PatchErrorKind.LOGIC_REGRESSION,
                            message="Behavior collapse: LLM output repeated identical candidate in retry.",
                            file_path=intent.file_path,
                            failed_search_text=intent.search
                        )]
                    )

        # 5. 逐一應用補丁並執行嚴格驗證 (透過解耦後的 PatchApplier)
        apply_res = self.patch_applier.apply_and_validate(
            intents=intents_or_error,
            repo_dir=input_data.repo_dir,
            localized_files=input_data.localized_files
        )

        model_decisions[-1]["status"] = "SUCCESS" if apply_res.success else apply_res.error_reason
        
        # 5.5 Micro-verifier: lightweight check before full verification
        micro_result = None
        if apply_res.success and apply_res.applied_diffs:
            patched_files = []
            for diff_text in apply_res.applied_diffs:
                for line in diff_text.splitlines():
                    if line.startswith("+++ b/"):
                        patched_files.append(line[6:])
            if patched_files:
                micro_result = MicroVerifier.verify(
                    apply_res.applied_diffs[0],
                    input_data.repo_dir,
                    patched_files,
                    verifier_env_metadata={"interpreter": input_data.python_executable}
                )
                if not micro_result.passed:
                    if micro_result.error_message == "ENV_BLOCKED":
                        # MicroVerifier is pre-verifier only — env_blocked means
                        # interpreter unavailable, not patch incorrect.
                        # Record telemetry but do not block patch application.
                        model_decisions[-1]["status"] = f"MICRO_VERIFY_{micro_result.error_message}_BYPASSED"
                        model_decisions[-1]["micro_verify_classifications"] = micro_result.classifications
                    else:
                        model_decisions[-1]["status"] = f"MICRO_VERIFY_{micro_result.error_message}"
                        return PatchSynthesisOutput(
                            success=False,
                            final_patch="",
                            model_decisions=model_decisions,
                            error_reason=f"MICRO_VERIFY_{micro_result.error_message}:{micro_result.details[:200]}"
                        )
        
        return PatchSynthesisOutput(
            success=apply_res.success,
            final_patch="\n".join(apply_res.applied_diffs).strip() if apply_res.success else "",
            model_decisions=model_decisions,
            error_reason=apply_res.error_reason or "",
            syntax_gate_passed=apply_res.syntax_gate_passed,
            preflight_telemetry=apply_res.preflight_telemetry,
            errors=apply_res.errors,
            last_search_anchors=[intent.search for intent in intents_or_error] if apply_res.success and not isinstance(intents_or_error, PatchError) else [],
            last_replacement_texts=[intent.replace for intent in intents_or_error] if apply_res.success and not isinstance(intents_or_error, PatchError) else []
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
            failure_reason=ctx.op.failure_reason,
            python_executable=ctx.op.python_executable,
            last_search_anchors=getattr(ctx.op, "last_search_anchors", []),
            last_replacement_texts=getattr(ctx.op, "last_replacement_texts", []),
            committee_model_override=str(getattr(ctx.op, "committee_proposer_model", "") or ""),
        )

        output = self.run(input_data)

        ctx.op.model_decisions.extend(output.model_decisions)
        ctx.op.final_patch = output.final_patch
        ctx.op.syntax_gate_passed = output.syntax_gate_passed
        ctx.op.refusal_detected = output.refusal_detected
        ctx.op.empty_response = output.empty_response

        # T1.2: Forward PatchError objects for telemetry extraction
        if output.errors:
            ctx.op.errors.extend(output.errors)

        if not output.success:
            ctx.op.failure_reason = output.failure_reason
            return PhaseResult(success=False, exit_layer="patcher", failure_reason=output.failure_reason)

        ctx.op.last_search_anchors = output.last_search_anchors
        ctx.op.last_replacement_texts = output.last_replacement_texts
        return PhaseResult(success=True)
