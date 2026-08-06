import os
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
        # N30R-V2.1-OPT: NEXUS_DISABLE_SPEC_GEN=1 跳過 spec_gen LLM 呼叫，節省 ~5s/task。
        # 當 planning 已提供 repair_strategy 時，spec_gen 是冗餘的第二次推理。
        # 啟用條件：local model latency 優先、plan 已含完整 repair_strategy。
        controls = (getattr(input_data, "route_context", None) or {}).get("local_armor_controls") or {}
        spec_gen_allowed = controls.get("spec_gen_allowed", True)
        _spec_gen_disabled = (
            os.environ.get("NEXUS_DISABLE_SPEC_GEN", "0") == "1"
            or not spec_gen_allowed
        )
        repair_spec = getattr(input_data, "repair_specification", "")
        if not repair_spec and patch_decision["model"] != "deterministic" and not _spec_gen_disabled:
            spec_decision = LocalModelPolicy.select_model(task_type="swe_repair", phase="planning", context={"mode": "spec_gen"})
            spec_prompt = f"Based on the problem and localized code, output a concise logical specification of the fix (Intents only, no code blocks):\n\nProblem: {input_data.problem_statement[:1000]}\nPlan: {input_data.plan.repair_strategy if input_data.plan else ''}"
            try:
                repair_spec = self.llm_client.generate(
                    system_prompt="You are a senior engineer. Define the exact logical change needed.",
                    user_prompt=spec_prompt,
                    model=spec_decision["model"],
                    timeout=spec_decision["timeout_seconds"],
                    options=spec_decision.get("ollama_options"),
                    phase="spec_gen",
                )
                # C15-5H: Record spec_gen telemetry inline in the patch decision dict to avoid
                # shifting model_decisions[-1] index. Appending a separate decision here would
                # cause all subsequent model_decisions[-1] references (L198, L216-247, etc.)
                # to target the repair_spec decision instead of the patch decision, resulting
                # in conversion_status remaining "none" and rejection_reason "unified_diff_malformed".
                model_decisions[-1]["repair_spec_model"] = spec_decision.get("model", "")
                model_decisions[-1]["repair_spec_status"] = "SUCCESS"
            except Exception:
                repair_spec = "Apply surgical fix as planned."
        elif _spec_gen_disabled:
            model_decisions[-1]["repair_spec_status"] = "SKIPPED_NEXUS_DISABLE_SPEC_GEN"


        # 4. 準備治理化 Prompt — use interleaved mode if planning was LLM-based
        plan = input_data.plan
        repair_strat = getattr(plan, "repair_strategy", "")
        use_interleaved = (
            not repair_strat.startswith("FAST_MODE")
            and input_data.attempt <= 1
            and not (input_data.failure_reason or "").strip()
        )
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
            primary_phase = "retry" if input_data.attempt > 1 else "patch"
            response = self.llm_client.generate(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                model=patch_decision["model"],
                timeout=patch_decision["timeout_seconds"],
                options=patch_decision.get("ollama_options"),
                api_type=patch_decision.get("api_type", "generate"),
                phase=primary_phase,
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

        # C5D: Record output excerpt and length IMMEDIATELY after LLM call
        model_decisions[-1]["output_len"] = len(response) if response else 0
        model_decisions[-1]["output_excerpt"] = (response or "")[:500]

        # C7: Output Classification
        output_len = len(response) if response else 0
        import hashlib
        output_hash = hashlib.sha256(response.encode("utf-8")).hexdigest() if response else ""
        output_excerpt = (response or "")[:500]

        contains_search = "<<<<<<< SEARCH" in (response or "")
        contains_replace = ">>>>>>> REPLACE" in (response or "")
        contains_fence = "```" in (response or "")
        contains_diff = ("--- a/" in (response or "") and "+++ b/" in (response or ""))

        # Determine output_class using robust static classifier
        output_class = self.parser.classify_format(response)

        # C15-5F: Initialize conversion telemetry default values
        model_decisions[-1]["conversion_status"] = "none"
        model_decisions[-1]["conversion_source_hash_before"] = ""
        model_decisions[-1]["conversion_candidate_hash"] = ""
        model_decisions[-1]["target_file_correct"] = True
        model_decisions[-1]["preimage_match_status"] = "not_applicable"

        # C15-5E Path B: Unified-Diff-to-SSRP Converter
        conv_status = "none"
        if output_class == "UNIFIED_DIFF" and response:
            expected_target = ""
            source_text = ""
            if input_data.localized_files:
                loc_file = input_data.localized_files[0]
                expected_target = loc_file.path
                target_path = input_data.repo_dir / expected_target
                if target_path.exists():
                    try:
                        source_text = target_path.read_text(encoding="utf-8", errors="replace")
                    except Exception:
                        pass
                if not source_text:
                    source_text = loc_file.content
            else:
                import re
                plus_headers = re.findall(r'^\+\+\+ (?:a/|b/)?([^\n]+)', response, re.MULTILINE)
                if plus_headers:
                    parsed_target = plus_headers[0].split('\t')[0].strip()
                    if parsed_target.startswith("a/") or parsed_target.startswith("b/"):
                        parsed_target = parsed_target[2:]
                    expected_target = parsed_target
                    target_path = input_data.repo_dir / expected_target
                    if target_path.exists():
                        try:
                            source_text = target_path.read_text(encoding="utf-8", errors="replace")
                        except Exception:
                            pass
                            
            if expected_target and source_text:
                from nexus.services.local_heal.diff_to_ssrp import DiffToSSRPConverter
                converted_ssrp, conv_status, conv_tele = DiffToSSRPConverter.convert(
                    raw_diff=response,
                    expected_target_file=expected_target,
                    source_text=source_text
                )
                model_decisions[-1]["conversion_status"] = conv_status
                model_decisions[-1]["conversion_source_hash_before"] = conv_tele.get("source_hash_before", "")
                model_decisions[-1]["conversion_candidate_hash"] = conv_tele.get("candidate_hash", "")
                model_decisions[-1]["target_file_correct"] = conv_tele.get("target_file_correct", True)
                model_decisions[-1]["preimage_match_status"] = conv_tele.get("preimage_match_status", "none")
                
                if conv_status == "unified_diff_to_ssrp_converted" and converted_ssrp:
                    response = converted_ssrp
                else:
                    # If conversion failed, overwrite response so parser fails
                    response = ""
            else:
                # If cannot resolve target or source text, fail conversion
                conv_status = "unified_diff_target_mismatch"
                model_decisions[-1]["conversion_status"] = conv_status
                response = ""

        # Parser check (run parser to get potential errors)
        parser_error_kind = "none"
        parser_error_message = "none"
        if response:
            intents_or_error = self.parser.parse(response)
            if isinstance(intents_or_error, PatchError):
                parser_error_kind = intents_or_error.kind.name if hasattr(intents_or_error.kind, "name") else str(intents_or_error.kind)
                parser_error_message = intents_or_error.message
        elif conv_status != "none":
            parser_error_kind = "PATCH_FORMAT_INVALID"
            parser_error_message = f"Unified diff conversion failed: {conv_status}"


        # Record these in the current model decision
        model_decisions[-1]["output_hash"] = output_hash
        model_decisions[-1]["output_class"] = output_class
        model_decisions[-1]["output_excerpt"] = output_excerpt
        model_decisions[-1]["parser_error_kind"] = parser_error_kind
        model_decisions[-1]["parser_error_message"] = parser_error_message
        model_decisions[-1]["contains_search_marker"] = contains_search
        model_decisions[-1]["contains_replace_marker"] = contains_replace
        model_decisions[-1]["contains_markdown_fence"] = contains_fence
        model_decisions[-1]["contains_unified_diff_header"] = contains_diff
        model_decisions[-1]["contains_natural_language_only"] = (output_class == "NATURAL_LANGUAGE")

        output_classification_telemetry = {
            "output_hash": output_hash,
            "output_class": output_class,
            "output_excerpt_first_500": output_excerpt,
            "parser_error_kind": parser_error_kind,
            "parser_error_message": parser_error_message,
            "contains_search_marker": contains_search,
            "contains_replace_marker": contains_replace,
            "contains_markdown_fence": contains_fence,
            "contains_unified_diff_header": contains_diff,
            "contains_natural_language_only": output_class == "NATURAL_LANGUAGE",
        }

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

        # A headerless SEARCH/REPLACE block has no physical file identity.  Bind
        # it only when localization leaves exactly one bounded source target (or
        # the canonical target hint selects one of those localized files).
        localized_paths = list(
            dict.fromkeys(
                loc_file.path
                for loc_file in input_data.localized_files
                if Path(loc_file.path).name not in _PATCH_BLACKLIST
            )
        )
        route_context = getattr(input_data, "route_context", {})
        target_hint = (
            str(route_context.get("target_file") or "")
            if isinstance(route_context, dict)
            else ""
        )
        bound_target = (
            target_hint
            if target_hint in localized_paths
            else localized_paths[0]
            if len(localized_paths) == 1
            else ""
        )
        if bound_target:
            intents_or_error = [
                type(intent)(
                    file_path=bound_target
                    if intent.file_path == "UNKNOWN_PENDING"
                    else intent.file_path,
                    search=intent.search,
                    replace=intent.replace,
                    operation=intent.operation,
                )
                for intent in intents_or_error
            ]

        # S4 Patch Protocol Guard
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

        # C12: Post-apply output classification update for SEARCH_MISMATCH
        search_mismatch = False
        search_block_len = 0
        locked_search_len = 0
        if not apply_res.success and apply_res.errors:
            for err in apply_res.errors:
                if hasattr(err, "kind") and err.kind == PatchErrorKind.SEARCH_MISMATCH:
                    search_mismatch = True
                    if hasattr(err, "failed_search_text") and err.failed_search_text:
                        search_block_len = len(err.failed_search_text)
                    break
        if search_mismatch:
            output_class = "SEARCH_REPLACE_SEARCH_MISMATCH"
            model_decisions[-1]["output_class"] = output_class
            model_decisions[-1]["search_mismatch"] = True
            model_decisions[-1]["search_block_len"] = search_block_len
            locked_search_text = getattr(input_data, "route_context", {}).get("locked_search", "") if hasattr(input_data, "route_context") else ""
            locked_search_len = len(locked_search_text) if locked_search_text else 0
            model_decisions[-1]["locked_search_len"] = locked_search_len
            output_classification_telemetry["output_class"] = output_class
            output_classification_telemetry["search_mismatch"] = True
            output_classification_telemetry["search_block_len"] = search_block_len
            output_classification_telemetry["locked_search_len"] = locked_search_len
        
        # Keep micro verification behavior unchanged during C7 recovery.
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
                        model_decisions[-1]["status"] = f"MICRO_VERIFY_{micro_result.error_message}_BYPASSED"
                        model_decisions[-1]["micro_verify_classifications"] = micro_result.classifications
                    else:
                        model_decisions[-1]["status"] = f"MICRO_VERIFY_{micro_result.error_message}"
                        preflight_telemetry = dict(apply_res.preflight_telemetry)
                        preflight_telemetry.update(output_classification_telemetry)
                        return PatchSynthesisOutput(
                            success=False,
                            final_patch="",
                            model_decisions=model_decisions,
                            error_reason=f"MICRO_VERIFY_{micro_result.error_message}:{micro_result.details[:200]}",
                            preflight_telemetry=preflight_telemetry
                        )
        preflight_telemetry = dict(apply_res.preflight_telemetry)
        preflight_telemetry.update(output_classification_telemetry)
        
        return PatchSynthesisOutput(
            success=apply_res.success,
            final_patch="\n".join(apply_res.applied_diffs).strip() if apply_res.success else "",
            model_decisions=model_decisions,
            error_reason=apply_res.error_reason or "",
            syntax_gate_passed=apply_res.syntax_gate_passed,
            preflight_telemetry=preflight_telemetry,
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
        object.__setattr__(input_data, "route_context", getattr(ctx.op, "route_context", {}))

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
            return PhaseResult(
                success=False,
                exit_layer="patcher",
                failure_reason=output.failure_reason,
                error_metadata=self._build_error_metadata(output),
            )

        ctx.op.last_search_anchors = output.last_search_anchors
        ctx.op.last_replacement_texts = output.last_replacement_texts
        return PhaseResult(success=True)

    @staticmethod
    def _build_error_metadata(output: PatchSynthesisOutput) -> dict:
        metadata = {
            "error_reason": output.failure_reason,
            "preflight_telemetry": dict(output.preflight_telemetry or {}),
        }
        for err in reversed(output.errors or []):
            kind = getattr(getattr(err, "kind", None), "name", "")
            if kind == "SYNTAX_ERROR":
                err_telemetry = dict(getattr(err, "telemetry", None) or {})
                preflight_checks = list(err_telemetry.get("preflight_checks", []) or [])
                syntax_check = next(
                    (
                        check
                        for check in reversed(preflight_checks)
                        if check.get("check") == "replace_syntax" and check.get("passed") is False
                    ),
                    {},
                )
                metadata.update(
                    {
                        "file_path": getattr(err, "file_path", "") or "",
                        "failed_search_text": getattr(err, "failed_search_text", "") or "",
                        "syntax_error_message": str(getattr(err, "message", "") or ""),
                        "syntax_error_line": syntax_check.get("syntax_error_line", 0),
                        "syntax_error_offset": syntax_check.get("syntax_error_offset", 0),
                        "syntax_error_msg": syntax_check.get("syntax_error_msg", ""),
                        "indentation_base": syntax_check.get("indentation_base", ""),
                    }
                )
                break
            if kind != "SEARCH_MISMATCH":
                continue

            err_telemetry = dict(getattr(err, "telemetry", None) or {})
            canonical = dict(err_telemetry.get("canonical_span", {}) or {})
            closest = dict(err_telemetry.get("closest_match", {}) or {})

            metadata.update(
                {
                    "file_path": getattr(err, "file_path", "") or "",
                    "failed_search_text": getattr(err, "failed_search_text", "") or "",
                    "closest_match": getattr(err, "closest_match", "") or "",
                    "canonical_span": canonical,
                    "closest_match_info": closest,
                    "requires_authority": bool(err_telemetry.get("requires_authority", False)),
                    "canonical_span_source": canonical.get("correction", "") or err_telemetry.get("canonical_span_source", ""),
                    "auto_corrected_search": bool(canonical.get("auto_corrected", False)),
                }
            )
            break
        return metadata
