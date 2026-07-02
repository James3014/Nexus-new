from typing import Any, Callable, List
from pathlib import Path
import subprocess
from nexus.services.local_heal.interface import IPhase, PhaseResult, RepairPlan
from nexus.services.local_heal.context import HealContext
from nexus.services.local_heal.governance_gate import GovernanceGate
from nexus.services.local_heal.corrector import SelfCorrector
from nexus.services.local_heal.errors import PatchError, PatchErrorKind
from nexus.services.local_heal.evidence_compactor import EvidenceCompactor
from nexus.services.local_heal.latency_ledger import LatencyLedger
from nexus.services.local_heal.role_contract import build_role_receipt, RoleReceipt
from nexus.evidence.abort_receipt import write_abort_receipt

from nexus.services.local_heal.failure_analyzer import FailureAnalyzer
from nexus.services.local_heal.context_guard import ContextGuard
from nexus.services.local_heal.phase_runner import PhaseRunner

class HealOrchestrator:
    """🛡️ Nexus Heal Orchestrator (Refactored: Modular / Strategy-Driven / Fail-Closed)"""
    
    def __init__(
        self,
        phases: List[IPhase],
        governance_gate: GovernanceGate,
        receipt_writer: Callable[[HealContext], Any] | None = None,
    ):
        # 預期 phases 順序: [Reproduction, Planning, Localization, PatchSynthesis, Verification]
        self._initialize_phases(phases)
        self.governance_gate = governance_gate
        self.receipt_writer = receipt_writer
        
        # Dependency Injection (Internal)
        self.corrector = SelfCorrector()
        self.failure_analyzer = FailureAnalyzer()
        self.context_guard = ContextGuard()
        self.phase_runner = PhaseRunner()

    def _initialize_phases(self, phases: List[IPhase]) -> None:
        self.repro_phase = None
        self.plan_phase = None
        self.loc_phase = None
        self.patch_phase = None
        self.verify_phase = None
        
        # (Rest of phase detection logic moved here to keep constructor clean)
        if len(phases) == 5:
            self.repro_phase, self.plan_phase, self.loc_phase, self.patch_phase, self.verify_phase = phases
        else:
            unmatched = []
            for phase in phases:
                name = phase.__class__.__name__
                if "Reproduction" in name: self.repro_phase = phase
                elif "Planning" in name: self.plan_phase = phase
                elif "Localization" in name: self.loc_phase = phase
                elif "Patch" in name: self.patch_phase = phase
                elif "Verification" in name: self.verify_phase = phase
                else: unmatched.append(phase)
            if unmatched and not any((self.repro_phase, self.plan_phase, self.loc_phase, self.patch_phase, self.verify_phase)):
                slots = ["repro_phase", "plan_phase", "loc_phase", "patch_phase", "verify_phase"]
                for slot, phase in zip(slots, unmatched):
                    setattr(self, slot, phase)

    def run(self, ctx: HealContext) -> HealContext:
        """核心修復工作流：線性啟動 -> 迭代修復 -> 審計結算。"""
        import time
        start_wall = time.time()
        
        ledger = LatencyLedger(
            task_id=getattr(ctx.op, "task_id", ""),
            instance_id=getattr(ctx.op, "instance_id", ""),
            wall_start=time.monotonic(),
        )
        ctx.op._latency_ledger = ledger
        ctx.op._role_receipts = []
        
        try:
            # 1. 啟動階段 (P1-3)
            if not self._run_linear_phases(ctx, ledger):
                return ctx

            # 2. 上下文保護 (Linus: Do it once, do it right)
            self._normalize_legacy_context(ctx)
            self.context_guard.protect(ctx)

            # 3. 迭代修復迴圈 (P4-5)
            self._run_repair_loop(ctx, ledger)

            ctx.op.runner_completed = True
            return ctx
            
        finally:
            self._finalize_run(ctx, ledger, start_wall)

    def _normalize_legacy_context(self, ctx: HealContext) -> None:
        plan = ctx.op.plan
        if isinstance(plan, dict):
            ctx.op.plan = RepairPlan(
                search_symbols=list(plan.get("search_symbols", []) or []),
                repair_strategy=str(plan.get("repair_strategy", "") or ""),
                violated_invariants=list(plan.get("violated_invariants", []) or []),
            )

    def _run_linear_phases(self, ctx: HealContext, ledger: LatencyLedger) -> bool:
        """執行再現、規劃與定位。任何階段失敗即終止。"""
        phases = [
            ("reproduction", self.repro_phase),
            ("planning", self.plan_phase),
            ("localization", self.loc_phase),
        ]
        for name, phase in phases:
            if not phase: continue
            res = self.phase_runner.run_phase(phase, name, ctx, ledger)
            if not res.success:
                ctx.gov.gate_exit = res.exit_layer or name
                ctx.op.failure_reason = res.failure_reason
                ctx.op.runner_completed = True
                self._write_abort_receipt_on_failure(ctx, name, res.failure_reason)
                return False
            
            self._record_role_receipt(ctx, name)
        return True

    def _run_repair_loop(self, ctx: HealContext, ledger: LatencyLedger) -> None:
        """執行 Patch 合成與驗證的迭代迴圈。"""
        import os
        while ctx.op.attempt <= ctx.op.max_tries:
            self._reset_workspace(ctx)
            
            # Step 4: Patch Synthesis
            if not self.patch_phase: break
            
            # Seam 整合：若使用 local_qwen_backend
            if getattr(ctx.op, "use_local_qwen_backend", False) or os.environ.get("NEXUS_LOCAL_QWEN_BACKEND") == "1":
                from nexus.services.local_heal.backends.local_patch_synthesis_backend import LocalPatchSynthesisBackend
                backend = LocalPatchSynthesisBackend()
                
                previous_feedback = None
                if ctx.op.attempt > 1:
                    from nexus.services.local_heal.failure_feedback_builder import build_failure_feedback
                    stdout_tail = getattr(ctx.op, "last_stdout_tail", "")
                    stderr_tail = getattr(ctx.op, "last_stderr_tail", "")
                    previous_feedback = build_failure_feedback(
                        task_id=getattr(ctx.op, "task_id", "t_unknown"),
                        failure_class=getattr(ctx.op, "last_failure_class", "VERIFIER_FAIL"),
                        target_file=ctx.op.localized_files[0].path if ctx.op.localized_files else "f.py",
                        target_symbol=ctx.op.plan.search_symbols[0] if ctx.op.plan and ctx.op.plan.search_symbols else "func",
                        locked_search=getattr(ctx.op, "locked_search", ""),
                        previous_block_reason=ctx.op.failure_reason or "VERIFIER_FAIL",
                        verifier_status="fail",
                        stdout_tail=stdout_tail,
                        stderr_tail=stderr_tail,
                    )
                    
                target_file = ctx.op.localized_files[0].path if ctx.op.localized_files else "f.py"
                target_symbol = ctx.op.plan.search_symbols[0] if ctx.op.plan and ctx.op.plan.search_symbols else "func"
                
                resp = backend.generate_patch(
                    task_id=getattr(ctx.op, "task_id", "t_unknown"),
                    problem_statement=ctx.op.problem_statement,
                    target_file=target_file,
                    target_symbol=target_symbol,
                    locked_search=getattr(ctx.op, "locked_search", ""),
                    verifier_command=tuple(ctx.op.verifier_command) if hasattr(ctx.op, "verifier_command") else (),
                    attempt=ctx.op.attempt,
                    previous_feedback=previous_feedback,
                )
                
                ctx.op.final_patch = resp["candidate_text"]
                ctx.op.local_model_called = resp["local_model_called"]
                res = PhaseResult(success=True)
            else:
                res = self.phase_runner.run_phase(self.patch_phase, f"patch_attempt_{ctx.op.attempt}", ctx, ledger)
            
            if not res.success:
                if self._handle_patch_failure(ctx, res, ledger):
                    continue
                else:
                    break
            
            # Step 5: Verification
            if not self.verify_phase:
                ctx.op.solve_eligible = True
                break
                
            v_res = self.phase_runner.run_phase(self.verify_phase, f"verify_attempt_{ctx.op.attempt}", ctx, ledger)
            if v_res.success:
                ctx.gov.gate_exit = "verification"
                break
            else:
                if getattr(ctx.op, "use_local_qwen_backend", False) or os.environ.get("NEXUS_LOCAL_QWEN_BACKEND") == "1":
                    receipt = getattr(ctx.op, "verifier_receipt", None)
                    if receipt:
                        ctx.op.last_stdout_tail = getattr(receipt, "stdout_tail", "")
                        ctx.op.last_stderr_tail = getattr(receipt, "stderr_tail", "")
                    ctx.op.last_failure_class = "VERIFIER_FAIL"
                self._handle_verification_failure(ctx, v_res)

    def _handle_patch_failure(self, ctx: HealContext, res: PhaseResult, ledger: LatencyLedger) -> bool:
        """處理 Patch 生成失敗，判定是否重試。"""
        err_kind = self.failure_analyzer.classify_patch_failure(res.failure_reason)
        err = PatchError(kind=err_kind, message=res.failure_reason)
        
        # B4: Set last_failure_class for retry feedback
        ctx.op.last_failure_class = err_kind.name
        
        self._record_model_status(ctx, err_kind.name, detail=res.failure_reason, phase="patch")
        
        # 嘗試自動修復 SEARCH_MISMATCH (Fuzzy Match)
        if err_kind == PatchErrorKind.SEARCH_MISMATCH:
            self._attempt_fuzzy_healing(ctx, res, err)

        # 判定 Fail-fast
        if not self.failure_analyzer.should_retry(res.failure_reason):
            ctx.op.failure_reason = res.failure_reason
            return False

        ctx.op.failure_reason = f"{err_kind.name}:{res.failure_reason}"
        self._handle_retry(ctx, err, res=res)
        return True

    def _attempt_fuzzy_healing(self, ctx: HealContext, res: PhaseResult, err: PatchError) -> None:
        metadata = res.error_metadata or {}
        failed_text = metadata.get("failed_search_text")
        f_path = metadata.get("file_path")
        if failed_text and f_path:
            target_file = ctx.op.repo_dir / f_path
            if target_file.exists():
                from nexus.services.local_heal.closest_snippet import find_closest_snippet
                file_content = target_file.read_text(encoding="utf-8", errors="replace")
                search_symbols = ctx.op.plan.search_symbols if ctx.op.plan else []
                err.closest_match = find_closest_snippet(file_content, failed_text, context_hints=search_symbols)

    def _handle_verification_failure(self, ctx: HealContext, res: PhaseResult) -> None:
        """Handle verification failure with T1.6 semantic retry on first failure."""
        evaluation_report = getattr(ctx.op, "evaluation_report", "")
        failure_class = self._classify_verification_failure(ctx, res.failure_reason)

        # T1.6: Semantic retry eligible on first verification failure
        semantic_retry_eligible = (
            ctx.op.attempt == 1
            and failure_class in ("semantic_wrong", "LOGIC_REGRESSION", "VERIFICATION_FAILED")
            and evaluation_report
            and getattr(ctx.op, "final_patch", "")
        )

        if semantic_retry_eligible:
            semantic_ok = self._attempt_semantic_retry(ctx, evaluation_report, failure_class)
            if semantic_ok:
                # Semantic retry succeeded — skip normal retry loop
                return

        # Normal path: clear patch and retry
        ctx.op.final_patch = ""
        ctx.op.failure_reason = f"LOGIC_REGRESSION:{res.failure_reason}"
        err = PatchError(kind=PatchErrorKind.LOGIC_REGRESSION, message=res.failure_reason)
        self._handle_retry(ctx, err)

    def _classify_verification_failure(self, ctx: HealContext, failure_reason: str) -> str:
        """Classify verification failure into semantic categories."""
        report = getattr(ctx.op, "evaluation_report", "")
        if "BUG PRESENT" in report:
            return "semantic_wrong"
        if "LOGIC_REGRESSION" in failure_reason:
            return "LOGIC_REGRESSION"
        return "VERIFICATION_FAILED"

    def _attempt_semantic_retry(
        self, ctx: HealContext, evaluation_report: str, failure_class: str
    ) -> bool:
        """T1.6: Attempt verification-guided semantic retry.

        Locks the canonical SEARCH span from the last patch, feeds verifier
        failure into the prompt, and asks the LLM to rewrite only REPLACE.
        Returns True if retry succeeded (patch applied + verification passed).
        """
        import re
        import json
        import hashlib
        from nexus.services.local_heal.prompt_builder import PromptBuilder
        from nexus.services.local_heal.protocol import SolidSearchReplaceProtocol
        from nexus.services.local_heal.patcher import Patcher
        from nexus.services.local_heal.patch_applier import PatchApplier
        from nexus.services.local_heal.interface import LocalizedFile
        from nexus.services.local_heal.model_result import classify_model_exception
        from nexus.engine.local_model_policy import LocalModelPolicy
        from nexus.services.local_heal.canonical_span import get_canonical_search_span

        # 1. Extract canonical SEARCH span using hybrid strategy
        final_patch = getattr(ctx.op, "final_patch", "")
        target_symbol = self._extract_target_symbol(ctx)
        source_file = self._resolve_target_file(ctx)

        canonical_result = get_canonical_search_span(
            locked_search="",
            patch_diff=final_patch,
            source_file=source_file,
            target_symbol=target_symbol,
            failed_search_text="",
        )

        if not canonical_result:
            return False

        canonical_search = canonical_result.span
        canonical_source = canonical_result.source

        # 2. Extract target file from patch
        target_file_match = re.search(r"^\+\+\+ b/(.+)$", final_patch, re.MULTILINE)
        if not target_file_match:
            return False
        target_file = target_file_match.group(1)

        # 3. Extract verifier failure text
        verifier_failure = evaluation_report

        # 4. Build semantic retry prompt
        original_prompt = getattr(ctx.op, "user_prompt", "")
        semantic_prompt = PromptBuilder.build_verification_guided_retry_prompt(
            original_user_prompt=original_prompt,
            verification_report=verifier_failure,
            canonical_search_span=canonical_search,
            target_file=target_file,
            retry_count=1,
        )

        # 5. Select model for patch (Qwen14B only)
        patch_decision = LocalModelPolicy.select_model(
            task_type="swe_repair",
            phase="patch",
            context={
                "reasoning_mode": getattr(ctx.op, "reasoning_mode", "INTUITIVE"),
                "file_count": 1,
                "attempt": ctx.op.attempt,
                "failure_reason": f"SEMANTIC_RETRY:{failure_class}",
            },
        )
        ctx.op.model_decisions.append({"phase": "semantic_retry_patch", **patch_decision})

        # 6. Call LLM
        from nexus.services.local_heal.llm_client import OllamaLLMClient
        llm_client = OllamaLLMClient(None)
        try:
            response = llm_client.generate(
                system_prompt=PromptBuilder.build_patch_system_prompt(patch_decision["model"]),
                user_prompt=semantic_prompt,
                model=patch_decision["model"],
                timeout=patch_decision["timeout_seconds"],
                options=patch_decision.get("ollama_options"),
            )
        except Exception as e:
            reason = classify_model_exception(e)
            ctx.op.model_decisions[-1]["status"] = reason
            return False

        if not response:
            ctx.op.model_decisions[-1]["status"] = "MODEL_EMPTY_RESPONSE"
            return False

        # 7. Parse SEARCH/REPLACE from response
        parser = SolidSearchReplaceProtocol()
        intents_or_error = parser.parse(response)
        if hasattr(intents_or_error, "kind"):
            ctx.op.model_decisions[-1]["status"] = intents_or_error.kind.name
            return False

        # 8. Lock canonical SEARCH span — replace any SEARCH from LLM
        locked_intents = []
        for intent in intents_or_error:
            locked_intent = type(intent)(
                file_path=intent.file_path,
                search=canonical_search,
                replace=intent.replace,
                operation=intent.operation,
            )
            locked_intents.append(locked_intent)

        # 9. Re-apply patch with locked SEARCH
        patcher = Patcher()
        patch_applier = PatchApplier(parser, patcher)
        apply_res = patch_applier.apply_and_validate(
            intents=locked_intents,
            repo_dir=ctx.op.repo_dir,
            localized_files=list(getattr(ctx.op, "localized_files", [])),
        )

        if not apply_res.success:
            ctx.op.model_decisions[-1]["status"] = apply_res.error_reason
            return False

        ctx.op.model_decisions[-1]["status"] = "SUCCESS"
        ctx.op.final_patch = "\n".join(apply_res.applied_diffs).strip()

        # 10. Re-run verification
        v_res = self.phase_runner.run_phase(
            self.verify_phase, f"verify_semantic_retry", ctx, ctx.op._latency_ledger
        )

        # 11. Write semantic retry telemetry
        ctx.op._semantic_retry_telemetry = {
            "semantic_retry_count": 1,
            "same_span_retry": True,
            "original_verification_failure": verifier_failure[:500],
            "observed_behavior": verifier_failure[:300],
            "behavior_delta_verified": v_res.success,
            "verifier_result_after_retry": "PASS" if v_res.success else f"FAIL: {getattr(ctx.op, 'evaluation_report', '')[:200]}",
            "search_locked": True,
            "replace_rewritten": True,
            "canonical_search_hash": hashlib.sha256(canonical_search.encode()).hexdigest()[:16],
            "target_file": target_file,
            # T1.6a: Attribution fields
            "semantic_retry_mode": "llm_replace_rewrite",
            "llm_replace_success": v_res.success,
            "deterministic_fallback_used": False,
            "fallback_rule_id": "",
            "fallback_rule_scope": "",
            "fallback_rule_reason": "",
            "model_patch_reward": 1.0 if v_res.success else 0.0,
            "deterministic_fallback_reward": 0.0,
        }

        if v_res.success:
            ctx.gov.gate_exit = "verification"
            ctx.op.solve_eligible = True
            return True

        return False

    def _extract_target_symbol(self, ctx: HealContext) -> str:
        """Extract target symbol from plan or localized files."""
        plan = getattr(ctx.op, "plan", None)
        if plan and hasattr(plan, "search_symbols") and plan.search_symbols:
            return plan.search_symbols[0]
        return ""

    def _resolve_target_file(self, ctx: HealContext) -> Path | None:
        """Resolve the target file path from localized files."""
        localized = getattr(ctx.op, "localized_files", [])
        if not localized:
            return None
        for loc in localized:
            if hasattr(loc, "path") and loc.path:
                target = ctx.op.repo_dir / loc.path
                if target.exists():
                    return target
        return None

    def _finalize_run(self, ctx: HealContext, ledger: LatencyLedger, start_wall: float) -> None:
        import time
        ctx.op.wall_time_sec = time.time() - start_wall
        ledger.wall_end = time.monotonic()
        ledger.retry_count = max(0, ctx.op.attempt - 1)
        ledger.finalize()
        ctx.op._latency_ledger = ledger
        self._attach_memory_influence_trace(ctx)
        self._run_capability_bridges(ctx)
        self.governance_gate.audit(ctx)

        # RRL3: Attach evidence harness (write-only observability)
        self._attach_evidence_harness(ctx)

        # EVAL-SUBSTRATE-1B: Live full-loop artifact capture
        self._attach_live_full_loop_artifacts(ctx)

        if self.receipt_writer:
            try:
                receipt_path = self.receipt_writer(ctx, run_group=getattr(ctx.op, "run_group", ""))
            except TypeError:
                receipt_path = self.receipt_writer(ctx)
            ctx.op.receipt_path = str(receipt_path)
            self._write_learning_closure(ctx)

    def _run_capability_bridges(self, ctx: HealContext) -> None:
        errors = []
        try:
            from nexus.services.local_heal.reasoning_advisory_bridge import apply_autoreason_advisory, apply_belief_update

            apply_autoreason_advisory(ctx)
            apply_belief_update(ctx)
        except Exception as exc:
            errors.append(exc.__class__.__name__)
        try:
            from nexus.services.local_heal.claim_delivery_gate import validate_context_claim_delivery

            validate_context_claim_delivery(ctx)
        except Exception as exc:
            errors.append(exc.__class__.__name__)
            ctx.op._claim_delivery_gate = {
                "schema": "nexus.local_heal.claim_delivery_gate.v1",
                "claim_gate_passed": False,
                "delivery_gate_passed": False,
                "failure_reasons": ["capability_bridge_error", exc.__class__.__name__],
                "evidence_refs": [],
                "receipt_only_claim_impossible": True,
                "public_claim_allowed": False,
                "production_ready": False,
                "internal_only": True,
            }
        if errors:
            ctx.op._capability_bridge_error = ";".join(errors)

    def _attach_memory_influence_trace(self, ctx: HealContext) -> None:
        if getattr(ctx.op, "_memory_influence_trace", None):
            return
        # MEMORY-EVAL-3: Check memory_enabled flag
        if not getattr(ctx.op, "memory_enabled", True):
            from nexus.services.local_heal.memory_trace import get_empty_trace
            ctx.op._memory_influence_trace = get_empty_trace()
            return
        try:
            from nexus.services.local_heal.memory_retrieval_adapter import MemoryRetrievalAdapter
            from nexus.services.local_heal.memory_trace import build_memory_trace_from_adapter, get_empty_trace

            target_symbol = self._extract_target_symbol(ctx)
            target_file = self._resolve_target_file(ctx)
            target_file_text = ""
            if target_file is not None:
                try:
                    target_file_text = str(target_file.relative_to(ctx.op.repo_dir))
                except ValueError:
                    target_file_text = target_file.name
            query = " ".join(
                part
                for part in (
                    str(getattr(ctx.op, "problem_statement", "") or "")[:500],
                    target_symbol,
                    target_file_text,
                )
                if part
            )
            if not query:
                ctx.op._memory_influence_trace = get_empty_trace()
                return
            adapter = MemoryRetrievalAdapter(memory_arm=getattr(ctx.op, "memory_arm", ""))
            adapter.retrieve_reranked(
                query_text=query,
                anchor_symbol=target_symbol,
                anchor_file=target_file_text,
                limit=3,
                task_id=getattr(ctx.op, "instance_id", "") or getattr(ctx.op, "task_id", ""),
            )
            adapter.last_metadata["evidence_packet_included"] = False
            adapter.last_metadata["prompt_included"] = False
            adapter.last_metadata["verifier_status"] = "PASS" if getattr(ctx.op, "solve_eligible", False) else "FAIL"
            ctx.op._memory_influence_trace = build_memory_trace_from_adapter(adapter.last_metadata)
        except Exception as exc:
            try:
                from nexus.services.local_heal.memory_trace import get_empty_trace

                trace = get_empty_trace()
                trace.no_memory_match = True
                trace.verifier_status = "TRACE_ATTACH_FAILED"
                ctx.op._memory_influence_trace = trace
            except Exception:
                ctx.op._memory_influence_trace = {
                    "available": False,
                    "trace_status": "TRACE_MISSING",
                    "no_memory_match": True,
                    "verifier_status": "TRACE_ATTACH_FAILED",
                    "internal_only": True,
                }
            ctx.op._memory_influence_trace_error = exc.__class__.__name__

    def _write_learning_closure(self, ctx: HealContext) -> None:
        try:
            from nexus.services.local_heal.learning_closure_bridge import write_learning_closure

            write_learning_closure(ctx)
        except Exception as exc:
            ctx.op._learning_closure = {
                "schema": "nexus.local_heal.learning_closure.v1",
                "writeback_status": "failed_non_blocking",
                "failure_reason": exc.__class__.__name__,
                "training_export_allowed": False,
                "internal_only": True,
            }

    def _attach_evidence_harness(self, ctx: HealContext) -> None:
        """RRL3: Attach evidence harness (write-only observability)."""
        try:
            from nexus.services.local_heal.evidence_harness import EvidenceHarness
            from pathlib import Path

            harness = EvidenceHarness(
                output_dir=Path("artifacts/runtime/rrl3_runs")
            )
            op = ctx.op if hasattr(ctx, "op") else ctx
            # Use instance_id as task_id (OperationalContext has instance_id, not task_id)
            task_id = str(getattr(op, "instance_id", "unknown"))
            bundle = harness.start_task(
                task_id=task_id,
                repo=str(getattr(op, "repo_dir", "")),
                issue_summary=str(getattr(op, "failure_reason", "")),
                task_class=str(getattr(op, "task_class", "")),
                difficulty=str(getattr(op, "difficulty", "")),
            )
            # Fill opportunistic fields from available ctx/op data
            bundle.patch_produced = bool(getattr(op, "final_patch", ""))
            bundle.patch_applied = bool(getattr(op, "patch_applied", False))
            bundle.patch_len = len(str(getattr(op, "final_patch", "")))
            bundle.verifier_status = "PASS" if getattr(op, "solve_eligible", False) else "FAIL"
            bundle.route_selected = str(getattr(op, "route_selected", ""))
            bundle.model_name = str(getattr(op, "model_name", ""))
            bundle.failure_reason = str(getattr(op, "failure_reason", ""))
            bundle.claim_eligible = bool(getattr(op, "claim_eligible", False))
            bundle.gate_passed = bool(getattr(op, "solve_eligible", False))
            # Finalize (writes artifacts)
            harness.finalize(bundle)
        except Exception:
            pass  # Write-only observability: never fail the repair loop

    def _attach_live_full_loop_artifacts(self, ctx: HealContext) -> None:
        """EVAL-SUBSTRATE-1B: Live full-loop artifact capture (runtime wiring)."""
        try:
            from nexus.services.local_heal.live_artifact_collector import LiveArtifactCollector
            from pathlib import Path

            op = ctx.op if hasattr(ctx, "op") else ctx
            task_id = str(getattr(op, "instance_id", "unknown"))

            # MEMORY-EVAL-3B: Explicit arm from ctx.op.memory_arm, else trace-based
            explicit_arm = getattr(op, "memory_arm", "")
            memory_enabled = getattr(op, "memory_enabled", True)
            mem_trace = getattr(op, "_memory_influence_trace", None)
            if explicit_arm in {"nexus_memory_on", "nexus_memory_off"}:
                arm = explicit_arm
            elif memory_enabled and mem_trace and getattr(mem_trace, "trace_status", "") == "TRACE_AVAILABLE":
                arm = "nexus_memory_on"
            else:
                arm = "nexus_memory_off"

            # MEMORY-EVAL-3B: Configurable output root from ctx.op
            output_root = Path(getattr(op, "artifact_output_root", "artifacts/runtime/eval_substrate_1b_runtime_wiring_v0/runs"))

            collector = LiveArtifactCollector(
                task_id=task_id,
                arm=arm,
                output_dir=output_root,
            )

            # Capture from runtime ctx/op fields
            collector.capture_input_manifest(
                task_id=task_id,
                repo=str(getattr(op, "repo_dir", "")),
                issue_summary=str(getattr(op, "failure_reason", "")),
                task_class=str(getattr(op, "task_class", "")),
            )

            # Memory trace from existing trace
            mem_trace = getattr(op, "_memory_influence_trace", None)
            if mem_trace and hasattr(mem_trace, "to_dict"):
                collector.capture_memory_trace(mem_trace.to_dict())
            else:
                collector.capture_memory_trace({"available": False, "trace_status": "NOT_USED"})

            # Evidence packet (from native_evidence_packet if available)
            evidence = getattr(op, "_evidence_packet", None)
            collector.capture_evidence_packet(evidence if evidence else {"unavailable": True})

            # Prompt manifest
            prompt_len = len(str(getattr(op, "system_prompt", ""))) + len(str(getattr(op, "user_prompt", "")))
            # MEMORY-EVAL-3: Check if memory was actually retrieved (not just trace exists)
            memory_actually_retrieved = (
                memory_enabled
                and mem_trace
                and getattr(mem_trace, "trace_status", "") == "TRACE_AVAILABLE"
                and getattr(mem_trace, "retrieved_count", 0) > 0
            )
            collector.capture_prompt_manifest({
                "prompt_length_chars": prompt_len,
                "memory_section_included": memory_actually_retrieved,
                "repair_attempt_id": task_id,
            })

            # Model output
            collector.capture_model_output({
                "model_name": str(getattr(op, "model_name", "")),
                "output_length_chars": len(str(getattr(op, "final_patch", ""))),
                "patch_produced": bool(getattr(op, "final_patch", "")),
                "repair_attempt_id": task_id,
            })

            # Patch apply
            collector.capture_patch_apply({
                "patch_applied": bool(getattr(op, "patch_applied", False)),
                "patch_len": len(str(getattr(op, "final_patch", ""))),
                "repair_attempt_id": task_id,
            })

            # Verifier result
            collector.capture_verifier_result({
                "status": "PASS" if getattr(op, "solve_eligible", False) else "FAIL",
                "repair_attempt_id": task_id,
            })

            # Receipt
            collector.capture_receipt({
                "receipt_path": str(getattr(op, "receipt_path", "")),
                "claim_eligible": bool(getattr(op, "claim_eligible", False)),
                "gate_passed": bool(getattr(op, "solve_eligible", False)),
                "repair_attempt_id": task_id,
            })

            # Evidence bundle
            collector.capture_evidence_bundle({
                "task_id": task_id,
                "final_status": "SOLVED" if getattr(op, "solve_eligible", False) else "FAIL",
                "repair_attempt_id": task_id,
            })

            # Bottleneck
            collector.capture_bottleneck({
                "final_status": "SOLVED" if getattr(op, "solve_eligible", False) else "FAIL",
                "primary_bottleneck": "none" if getattr(op, "solve_eligible", False) else "unknown",
                "repair_attempt_id": task_id,
            })

            # Arm result
            collector.capture_arm_result({
                "task_id": task_id,
                "arm": arm,
                "solved": bool(getattr(op, "solve_eligible", False)),
                "verifier_status": "PASS" if getattr(op, "solve_eligible", False) else "FAIL",
                "repair_attempt_id": task_id,
            })

            # Write all artifacts
            collector.write_all()

            # Store collector reference on ctx for test verification
            ctx.op._live_artifact_collector = collector

        except Exception:
            pass  # Write-only observability: never fail the repair loop

    def _record_role_receipt(self, ctx: HealContext, phase_name: str) -> None:
        model_name = self._get_model_for_phase(ctx, phase_name)
        if model_name:
            role_receipt = build_role_receipt(phase_name, model_name)
            ctx.op._role_receipts.append(role_receipt)

    def _reset_workspace(self, ctx: HealContext) -> None:
        # P1-3: Portable root detection — use env var or fall back to detecting via git
        import os
        nexus_root_env = os.environ.get("NEXUS_ROOT", "")
        if nexus_root_env:
            current_root = Path(nexus_root_env).resolve()
        else:
            # Detect project root as the nearest ancestor with a .git
            candidate = Path(__file__).resolve()
            current_root = candidate
            for _ in range(8):
                if (candidate / ".git").exists():
                    current_root = candidate
                    break
                candidate = candidate.parent

        if ctx.op.repo_dir.resolve() == current_root:
            return

        if not ctx.op.repo_dir or not (ctx.op.repo_dir / ".git").exists():
            return
        subprocess.run(["git", "checkout", "--", "."], cwd=str(ctx.op.repo_dir), capture_output=True)
        subprocess.run(["git", "clean", "-fd"], cwd=str(ctx.op.repo_dir), capture_output=True)

    def _build_patch_failure_structured_packet(
        self,
        ctx: HealContext,
        error: PatchError,
        res: PhaseResult,
    ):
        from nexus.services.local_heal.evidence_compactor import StructuredPacket

        metadata = dict(res.error_metadata or {})
        if error.kind == PatchErrorKind.SYNTAX_ERROR:
            repro_command = ""
            if ctx.op.plan and getattr(ctx.op.plan, "verifier_command", ""):
                repro_command = str(ctx.op.plan.verifier_command)
            syntax_error_msg = str(metadata.get("syntax_error_msg", "") or error.message or "")[:200]
            syntax_error_line = 0
            raw_line = metadata.get("syntax_error_line", 0)
            try:
                syntax_error_line = int(raw_line or 0)
            except (TypeError, ValueError):
                syntax_error_line = 0
            relevant_source_span = str(metadata.get("failed_search_text", "") or "")[:500]
            return StructuredPacket(
                exception_type=error.kind.name,
                exception_message=syntax_error_msg,
                top_failing_file=str(metadata.get("file_path", "") or error.file_path or ""),
                top_failing_line=syntax_error_line,
                repro_command=repro_command,
                relevant_source_span=relevant_source_span,
                env_failure_reason="",
                omitted_bytes=0,
                raw_artifact_ref="patch_synthesis.syntax_error",
            )

        if error.kind != PatchErrorKind.SEARCH_MISMATCH:
            return None

        canonical = dict(metadata.get("canonical_span", {}) or {})
        closest_info = dict(metadata.get("closest_match_info", {}) or {})
        relevant_source_span = (
            str(error.closest_match or "")
            or str(closest_info.get("resolved_span", "") or "")
            or str(metadata.get("failed_search_text", "") or "")
        )[:500]

        top_failing_line = 0
        for key in ("canonical_line_start", "start_line", "canonical_span_start_line"):
            raw_value = canonical.get(key, metadata.get(key, 0))
            if raw_value:
                try:
                    top_failing_line = int(raw_value)
                    break
                except (TypeError, ValueError):
                    pass

        repro_command = ""
        if ctx.op.plan and getattr(ctx.op.plan, "verifier_command", ""):
            repro_command = str(ctx.op.plan.verifier_command)

        return StructuredPacket(
            exception_type=error.kind.name,
            exception_message=str(error.message or "")[:200],
            top_failing_file=str(metadata.get("file_path", "") or error.file_path or ""),
            top_failing_line=top_failing_line,
            repro_command=repro_command,
            relevant_source_span=relevant_source_span,
            env_failure_reason="",
            omitted_bytes=0,
            raw_artifact_ref="patch_synthesis.search_mismatch",
        )

    def _handle_retry(self, ctx: HealContext, error: PatchError, res: PhaseResult | None = None) -> HealContext:
        _PATCH_BLACKLIST = {"reproduce_bug.py", "repro.py", "test_repro.py"}
        targeted_files = ", ".join([
            f.path for f in getattr(ctx.op, "localized_files", [])
            if Path(f.path).name not in _PATCH_BLACKLIST
        ])
        
        sp = None
        if error.kind in (PatchErrorKind.LOGIC_REGRESSION, PatchErrorKind.SEARCH_MISMATCH, PatchErrorKind.SYNTAX_ERROR):
            from nexus.services.local_heal.evidence_compactor import EvidenceCompactor
            if res is not None:
                sp = self._build_patch_failure_structured_packet(ctx, error, res)
            if sp is None:
                evaluation_report = getattr(ctx.op, "evaluation_report", "") or error.message or ""
                repro_command = ""
                if ctx.op.plan and getattr(ctx.op.plan, "verifier_command", ""):
                    repro_command = ctx.op.plan.verifier_command
                env_failure_reason = ""
                env_resolution = getattr(ctx.op, "env_resolution", None)
                if env_resolution and not getattr(env_resolution, "ready", True):
                    env_failure_reason = getattr(env_resolution, "failure_reason", "") or ""
                sp = EvidenceCompactor.compact_structured(
                    evidence=evaluation_report,
                    raw_artifact_ref="verification_report.txt",
                    repro_command=repro_command,
                    env_failure_reason=env_failure_reason,
                )
            error.structured_packet = sp
            
        ctx.op.user_prompt = self.corrector.build_retry_prompt(ctx.op.user_prompt, error, targeted_files=targeted_files, structured_packet=sp)
        ctx.op.attempt += 1
        return ctx
    
    def _get_model_for_phase(self, ctx: HealContext, phase_name: str) -> str:
        """Extract the model name used for a given phase from model_decisions."""
        for decision in reversed(ctx.op.model_decisions):
            if decision.get("phase") == phase_name:
                return decision.get("model", "")
        return ""

    def _record_model_status(self, ctx: HealContext, status: str, detail: str = "", *, phase: str | None = None) -> None:
        for decision in reversed(ctx.op.model_decisions):
            if phase is None or decision.get("phase") == phase:
                decision["status"] = status
                if detail:
                    decision["detail"] = detail[:500]
                return

    def _write_abort_receipt_on_failure(self, ctx: HealContext, phase_name: str, failure_reason: str) -> None:
        """P0.1b: Write abort receipt when a phase fails."""
        try:
            from pathlib import Path
            nexus_root = Path(__file__).resolve().parents[3]
            output_dir = nexus_root / ".nexus/reports/local_heal" / _safe_id(ctx.op.instance_id)
            write_abort_receipt(
                output_dir=output_dir,
                task_id=getattr(ctx.op, "task_id", ctx.op.instance_id),
                instance_id=ctx.op.instance_id,
                failure_class="workspace_provisioning" if "repro" in phase_name.lower() else "phase_failure",
                failure_reason=failure_reason,
                failure_subclass=_map_failure_subclass(failure_reason),
                workspace_path=str(ctx.op.repo_dir),
                repo_root=str(ctx.op.repo_dir),
                target_path="",
                path_subclass="",
                model_calls=len(ctx.op.model_decisions),
                stop_layer=phase_name,
            )
        except Exception:
            pass


def _safe_id(instance_id: str) -> str:
    import re
    return re.sub(r"[^A-Za-z0-9_.-]+", "__", instance_id).strip("_") or "unknown"


def _map_failure_subclass(reason: str) -> str:
    if "REPO_NOT_MOUNTED" in reason or "repo_root" in reason.lower():
        return "REPO_NOT_MOUNTED"
    if "NOT_WRITABLE" in reason or "writable" in reason.lower():
        return "WORKSPACE_NOT_WRITABLE"
    if "TARGET_PATH" in reason:
        return "TARGET_PATH_UNRESOLVED"
    if "MANIFEST" in reason:
        return "MANIFEST_MISSING_TARGET"
    if "REPRO" in reason:
        return "WRONG_REPRO_PATH"
    if "STALE" in reason:
        return "STALE_MODEL_PATH"
    return "PHASE_FAILURE"
