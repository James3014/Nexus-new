from dataclasses import dataclass, field
import inspect
from pathlib import Path
import difflib
import os
from typing import List, Tuple, Dict, Any, Optional

from nexus.services.local_heal.localizer import Localizer
from nexus.services.local_heal.parser import SearchReplaceParser
from nexus.services.local_heal.patcher import Patcher, PatchResult
from nexus.services.local_heal.validator import validate_syntax, validate_effective_change, validate_name_sanity
from nexus.services.local_heal.corrector import SelfCorrector
from nexus.services.local_heal.context_budget import ContextBudgetManager
from nexus.services.local_heal.errors import PatchError, PatchErrorKind
from nexus.services.local_heal.reproduction import ReproductionRunner
from nexus.services.local_heal.planner import Planner
from nexus.services.local_heal.repomap import RepoMap
from nexus.services.local_heal.evaluation_gate import EvaluationGate
from nexus.services.local_heal.receipt import write_repair_receipt
from nexus.services.local_heal.env_denoiser import EnvDenoiser
from nexus.services.local_heal.model_result import classify_model_exception, classify_model_text
from nexus.engine.local_model_policy import LocalModelPolicy


@dataclass
class HealContext:
    """管線狀態上下文封裝 (Algebraic Reasoning / Evidence-Driven)"""
    instance_id: str
    repo_dir: Path
    problem_statement: str
    localized_files: List[Tuple[str, str]] = field(default_factory=list)
    system_prompt: str = ""
    user_prompt: str = ""
    attempt: int = 1
    max_tries: int = 3
    final_patch: str = ""
    errors: List[PatchError] = field(default_factory=list)

    # --- 新增證據產物 (Artifacts) ---
    repro_script: str = ""
    repro_evidence: str = ""
    reproduced: bool = False
    failure_reason: str = ""
    plan: Dict[str, Any] = field(default_factory=dict)
    evaluation_report: str = ""
    hidden_verifier_passed: bool = False
    runner_completed: bool = False
    solve_eligible: bool = False
    receipt_path: str = ""
    model_decisions: List[Dict[str, Any]] = field(default_factory=list)
    env_denoise: Dict[str, Any] = field(default_factory=dict)
    env_resolution: Dict[str, Any] = field(default_factory=dict)
    python_executable: str = ""
    auto_heal_enabled: bool = False
    expected_stop_layer: str = "verification"
    expected_reason_family: str = "SOLVED"

    # Phase 3 Algebraic Alignment
    reasoning_mode: str = "INTUITIVE"
    violated_invariants: List[str] = field(default_factory=list)
    rewrite_trace: List[str] = field(default_factory=list)
    risk_delta: float = 0.0



class HealPipeline:
    """固定 5 階段管線，將流程控制與工具完全解耦 (SRP / SOTA Schedulers)"""

    def __init__(self, ollama_generate_fn: Any, hidden_verifier: bool = False):
        self.localizer = Localizer()
        self.parser = SearchReplaceParser()
        self.patcher = Patcher()
        self.corrector = SelfCorrector()
        self.budget_manager = ContextBudgetManager()
        self.planner = Planner(ollama_generate_fn=ollama_generate_fn)
        self.ollama_generate = ollama_generate_fn
        self.hidden_verifier_required = hidden_verifier

    def _write_trace(self, ctx: HealContext, message: str) -> None:
        log_dir = Path("/Users/jameschen/Workspace/nexus/scratch")
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / "llm_trace.log"
        try:
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(f"\n[{ctx.instance_id}] {message}\n")
        except Exception:
            pass

    def run(self, ctx: HealContext) -> HealContext:
        self._write_trace(ctx, f"=== NEXUS ORCHESTRATION START {ctx.instance_id} ===")

        # 延遲初始化環境感知的服務
        self.repro_runner = self._make_reproduction_runner(ctx.repo_dir)
        self.env_denoiser = self._make_env_denoiser(ctx.repo_dir)
        if ctx.python_executable:
            self.repro_runner.python_executable = ctx.python_executable
            self.env_denoiser.python_executable = ctx.python_executable
        self.repo_map = RepoMap(ctx.repo_dir)
        self.eval_gate = EvaluationGate(ctx.repo_dir)

        # --- Phase 1: Reproduction (建立物理證據) ---
        self._write_trace(ctx, "[Phase 1] Building physical evidence...")
        if ctx.repro_evidence:
            success, evidence = True, ctx.repro_evidence
        else:
            if not ctx.repro_script:
                repro_decision = self._select_model(ctx, phase="reproduction")
                self.repro_runner = ReproductionRunner(
                    ctx.repo_dir,
                    generate_fn=self.ollama_generate,
                    model_name=repro_decision["model"],
                    timeout_seconds=repro_decision["timeout_seconds"],
                    python_executable=ctx.python_executable or "python3",
                )
                try:
                    ctx.repro_script = self.repro_runner.generate_repro_script(ctx.problem_statement)
                except Exception as exc:
                    return self._fail_closed_model_call(ctx, exc, phase="reproduction")
            success, evidence = self.repro_runner.run_repro(ctx.repro_script)
            if (
                not success
                and ctx.repro_script
                and ctx.auto_heal_enabled
                and self.repro_runner.is_environment_failure(evidence)
            ):
                denoise_result = self.env_denoiser.prepare_from_evidence(evidence)
                ctx.env_denoise = denoise_result.to_receipt()
                self._write_trace(
                    ctx,
                    (
                        "Env denoise attempted="
                        f"{denoise_result.attempted} succeeded={denoise_result.succeeded} "
                        f"reason={denoise_result.reason}"
                    ),
                )
                if denoise_result.succeeded:
                    python_executable = getattr(denoise_result, "python_executable", "")
                    if python_executable:
                        self.repro_runner.python_executable = python_executable
                    success, evidence = self.repro_runner.run_repro(ctx.repro_script)
        ctx.reproduced = bool(success)

        # [Fail-closed] 如果沒有重現或完全沒有捕獲到物理證據，拒絕繼續
        if not success or not evidence or len(evidence.strip()) < 10:
            self._write_trace(ctx, "❌ FAIL-CLOSED: Bug was not physically reproduced. Aborting.")
            ctx.runner_completed = True
            ctx.solve_eligible = False
            ctx.repro_evidence = evidence
            if not ctx.repro_script:
                ctx.failure_reason = "NO_REPRO_SCRIPT"
            elif self.repro_runner.is_environment_failure(evidence):
                ctx.failure_reason = "REPRO_ENVIRONMENT_FAILURE"
            elif not success:
                ctx.failure_reason = "REPRO_NOT_REPRODUCED"
            else:
                ctx.failure_reason = "REPRO_EVIDENCE_TOO_SHORT"
            ctx.receipt_path = str(write_repair_receipt(ctx))
            return ctx

        ctx.repro_evidence = evidence
        self._write_trace(ctx, f"Reproduction success={success}, evidence_len={len(evidence)}")

        # --- Phase 2: Planning (戰略規劃) ---
        self._write_trace(ctx, "[Phase 2] Strategic planning...")
        planning_decision = self._select_model(ctx, phase="planning")
        try:
            ctx.plan = self.planner.create_plan(
                ctx.problem_statement,
                ctx.repro_evidence,
                model_name=planning_decision["model"],
                timeout_seconds=planning_decision["timeout_seconds"],
            )
        except Exception as exc:
            return self._fail_closed_model_call(ctx, exc, phase="planning")
        self._write_trace(ctx, f"Plan symbols: {ctx.plan.get('search_symbols')}")

        # Phase 4 Alignment: 代數推理模式判定
        if "astropy" in ctx.problem_statement.lower() or "astropy" in str(ctx.repo_dir).lower():
            ctx.reasoning_mode = "ALGEBRAIC"
        else:
            ctx.reasoning_mode = "INTUITIVE"

        ctx.violated_invariants = ctx.plan.get("violated_invariants", [])
        self._write_trace(ctx, f"Reasoning mode: {ctx.reasoning_mode}, Invariants found: {len(ctx.violated_invariants)}")

        # --- Phase 3: Localization (深度定位) ---
        self._write_trace(ctx, "[Phase 3] Locating fix targets...")
        if not ctx.localized_files:
            ctx = self._localize(ctx)
        if not ctx.localized_files:
            self._write_trace(ctx, "=== PIPELINE END localized_files=empty ===")
            ctx.runner_completed = True
            ctx.solve_eligible = False
            ctx.failure_reason = "LOCALIZATION_EMPTY"
            ctx.receipt_path = str(write_repair_receipt(ctx))
            return ctx

        # 初始化 System Prompt 與原始 User Prompt
        ctx.system_prompt = (
            "You are a Senior Principal Software Engineer at Nexus.\n"
            "Principles:\n"
            "1. BE EXPLICIT: Never use placeholders. Copy ALL code exactly.\n"
            "2. LOGIC ONLY: Fix the bug/race condition in the CLASS or FUNCTION implementation.\n"
            "3. DO NOT TOUCH TESTS: Never change the testing code, asserts, or thread counts. Keep the existing test_challenge() function UNTOUCHED.\n"
            "4. INTEGRITY: Ensure indentation and logic flow are perfect.\n"
            "5. CANONICAL REWRITE: For Python logic changes (like try/except blocks), ALWAYS provide a full function rewrite in the REPLACE block to avoid splicing errors.\n\n"
            "6. SMALL ROOT CAUSE: Prefer the smallest existing helper/function that directly computes the wrong value. For operator-dispatch code, inspect the concrete operator helper before changing the dispatcher or adding framework methods.\n\n"
            "Format:\n"
            "Every block MUST start with 'FILE: path/to/file.py' followed by standard SEARCH/REPLACE format."
        )

        file_ctx = "\n\n".join(f"=== FILE: {fname} ===\n{content}" for fname, content in ctx.localized_files)
        base_user_prompt = f"Bug Report:\n{ctx.problem_statement[:1500]}\n\nSource Code:\n{file_ctx}\n\nOutput SEARCH/REPLACE block(s):"

        # 注入代數產物到 Prompt
        ctx.user_prompt = (
            f"{base_user_prompt}\n\n"
            f"### [NEXUS STRATEGIC PLAN]\n{ctx.plan.get('repair_strategy', 'N/A')}\n\n"
            f"### [REPRODUCTION EVIDENCE]\n```\n{ctx.repro_evidence[:1000]}\n```"
        )

        # --- Phase 4: Targeted Edit (迭代修復) ---
        while ctx.attempt <= ctx.max_tries:
            ctx.errors.clear()
            self._reset_workspace(ctx)

            patch_decision = self._select_model(ctx, phase="patch")
            response = self._generate_patch(
                ctx,
                model_name=patch_decision["model"],
                timeout_seconds=patch_decision["timeout_seconds"],
            )
            if not response:
                if not ctx.failure_reason:
                    ctx.failure_reason = "MODEL_EMPTY_RESPONSE"
                    self._record_model_status(ctx, ctx.failure_reason)
                break

            blocks = self.parser.parse_blocks(response)
            if not blocks:
                err = PatchError(kind=PatchErrorKind.NO_BLOCKS_FOUND, message="No SEARCH/REPLACE blocks found.")
                ctx = self._handle_retry(ctx, err)
                continue

            if any(b.get("has_placeholder") for b in blocks):
                err = PatchError(kind=PatchErrorKind.SEARCH_HAS_PLACEHOLDER, message="SEARCH/REPLACE contains placeholders.")
                ctx = self._handle_retry(ctx, err)
                continue

            applied_diffs = []
            has_error = False

            for b in blocks:
                target_path = ctx.repo_dir / b["file"]
                if b.get("operation") == "create":
                    create_res = self._apply_create_file(ctx, b, target_path)
                    self._write_trace(ctx, f"Patcher: create success={create_res.success}")
                    if not create_res.success:
                        err = PatchError(
                            kind=PatchErrorKind.SEARCH_MISMATCH,
                            message=create_res.error_message or "Create-file operation failed",
                            file_path=b["file"],
                        )
                        ctx.errors.append(err)
                        has_error = True
                        break
                    applied_diffs.append(create_res.diff)
                    continue

                if not target_path.exists():
                    found = list(ctx.repo_dir.rglob(Path(b["file"]).name))
                    target_path = found[0] if found else target_path

                if not target_path.exists():
                    err = PatchError(kind=PatchErrorKind.FILE_NOT_FOUND, message=f"File not found: {b['file']}")
                    ctx.errors.append(err)
                    has_error = True
                    break

                file_content = target_path.read_text(encoding="utf-8", errors="replace")

                # Phase 1 Alignment: 帶入戰略符號提示以防止漂移
                context_hints = ctx.plan.get("search_symbols", [])
                patch_res = self.patcher.apply_patch(file_content, b["search"], b["replace"], context_hints=context_hints)

                self._write_trace(ctx, f"Patcher: success={patch_res.success}, strategy={patch_res.strategy_used}")

                if not patch_res.success:
                    err = PatchError(
                        kind=PatchErrorKind.SEARCH_MISMATCH,
                        message=patch_res.error_message,
                        file_path=b["file"],
                        failed_search_text=b["search"]
                    )
                    ctx.errors.append(err)
                    has_error = True
                    break

                # 物理審計
                is_valid, syntax_err = validate_syntax(patch_res.new_content)
                if not is_valid:
                    err = PatchError(kind=PatchErrorKind.SYNTAX_ERROR, message=syntax_err, file_path=b["file"])
                    ctx.errors.append(err)
                    has_error = True
                    break

                is_effective, effective_err = validate_effective_change(file_content, patch_res.new_content)
                if not is_effective:
                    err = PatchError(kind=PatchErrorKind.NO_EFFECTIVE_CODE_CHANGE, message=effective_err, file_path=b["file"])
                    ctx.errors.append(err)
                    has_error = True
                    break

                is_sane, sanity_err = validate_name_sanity(patch_res.new_content)
                if not is_sane:
                    err = PatchError(kind=PatchErrorKind.SYNTAX_ERROR, message=sanity_err, file_path=b["file"])
                    ctx.errors.append(err)
                    has_error = True
                    break

                target_path.write_text(patch_res.new_content, encoding="utf-8")
                applied_diffs.append(self._build_file_diff(b["file"], file_content, patch_res.new_content))

            if not has_error:
                ctx.final_patch = "\n".join(applied_diffs).strip()

                # --- Phase 5: Verification (代數驗證) ---
                self._write_trace(ctx, "[Phase 5] Algebraic verification...")
                repro_path = ctx.repo_dir / "reproduce_bug.py"
                repro_path.write_text(ctx.repro_script, encoding="utf-8")

                try:
                    verification_python = ctx.python_executable or "python3"
                    visible_results = self.eval_gate.run_visible_tests([[verification_python, "reproduce_bug.py"]])
                    hidden_results = []
                    if self.hidden_verifier_required:
                        hidden_results = self.eval_gate.run_hidden_verifier([])

                    ctx.hidden_verifier_passed = all(r.passed for r in visible_results + hidden_results)
                    ctx.evaluation_report = self.eval_gate.get_redacted_report(visible_results, hidden_results)

                    if ctx.hidden_verifier_passed:
                        ctx.solve_eligible = True
                        self._write_trace(ctx, "✅ SUCCESS: All tests passed.")
                        break
                finally:
                    if repro_path.exists():
                        try: os.remove(repro_path)
                        except OSError: pass

                ctx.solve_eligible = False
                ctx.final_patch = ""
                self._reset_workspace(ctx)
                err = PatchError(kind=PatchErrorKind.NO_EFFECTIVE_CODE_CHANGE, message=f"Tests failed:\n{ctx.evaluation_report}")
                ctx = self._handle_retry(ctx, err)
            else:
                ctx = self._handle_retry(ctx, ctx.errors[-1])

        ctx.runner_completed = True
        ctx.solve_eligible = bool(ctx.final_patch) and bool(ctx.hidden_verifier_passed)
        if not ctx.solve_eligible and not ctx.failure_reason:
            ctx.failure_reason = self._latest_patch_error_reason(ctx)
        ctx.receipt_path = str(write_repair_receipt(ctx))
        self._write_trace(ctx, f"=== PIPELINE END patch_len={len(ctx.final_patch)} attempt={ctx.attempt} solve_eligible={ctx.solve_eligible} ===")
        return ctx

    def _reset_workspace(self, ctx: HealContext) -> None:
        # 安全加固：如果工作目錄是 Nexus 根目錄，禁止執行毀滅性清理
        current_root = Path("/Users/jameschen/Workspace/nexus").resolve()
        if ctx.repo_dir.resolve() == current_root:
            self._write_trace(ctx, "Safety Lock: Skipping git reset on Nexus root directory.")
            return

        if not ctx.repo_dir or not (ctx.repo_dir / ".git").exists(): return
        import subprocess
        subprocess.run(["git", "checkout", "--", "."], cwd=str(ctx.repo_dir), capture_output=True)
        subprocess.run(["git", "clean", "-fd"], cwd=str(ctx.repo_dir), capture_output=True)

    def _make_reproduction_runner(self, repo_dir: Path) -> ReproductionRunner:
        return ReproductionRunner(repo_dir)

    def _make_env_denoiser(self, repo_dir: Path) -> EnvDenoiser:
        return EnvDenoiser(repo_dir)

    def _localize(self, ctx: HealContext) -> HealContext:
        rank_query = self.localizer.build_query(
            ctx.problem_statement,
            search_symbols=ctx.plan.get("search_symbols", []),
        )
        refine_query = self.localizer.build_query(
            ctx.problem_statement,
            search_symbols=ctx.plan.get("search_symbols", []),
            evidence=ctx.repro_evidence,
        )
        search_symbols = ctx.plan.get("search_symbols", [])
        ranked = self.localizer.rank_files(rank_query, ctx.repo_dir, search_symbols=search_symbols)
        for _, doc in ranked:
            doc["issue_desc"] = refine_query
        raw_files = self.localizer.extract_relevant_code(ranked, query=refine_query)
        ctx.localized_files = self.budget_manager.enforce_hard_limit(raw_files)
        file_names = ", ".join(name for name, _ in ctx.localized_files)
        self._write_trace(ctx, f"Localized files: {file_names} chars={sum(len(c) for _, c in ctx.localized_files)}")
        return ctx

    def _build_file_diff(self, relative_path: str, old_content: str, new_content: str) -> str:
        return "".join(difflib.unified_diff(
            old_content.splitlines(keepends=True),
            new_content.splitlines(keepends=True),
            fromfile=f"a/{relative_path}",
            tofile=f"b/{relative_path}",
            lineterm="\n",
        ))

    def _apply_create_file(self, ctx: HealContext, block: Dict[str, Any], target_path: Path) -> PatchResult:
        try:
            target_path.resolve().relative_to(ctx.repo_dir.resolve())
        except ValueError:
            return PatchResult(False, "", "", "Create-file path escapes the repository root")

        if target_path.exists():
            return PatchResult(False, target_path.read_text(encoding="utf-8", errors="replace"), "", "Target file already exists")

        new_content = block["replace"]
        if new_content and not new_content.endswith("\n"):
            new_content += "\n"
        if target_path.suffix == ".py":
            is_valid, syntax_err = validate_syntax(new_content)
            if not is_valid:
                return PatchResult(False, "", "", syntax_err)
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

    def _generate_patch(self, ctx: HealContext, *, model_name: str, timeout_seconds: int) -> str:
        try:
            response = self._call_model(
                ctx.system_prompt,
                ctx.user_prompt,
                model_name=model_name,
                timeout_seconds=timeout_seconds,
            )
            model_text_reason = classify_model_text(response)
            if model_text_reason:
                ctx.failure_reason = model_text_reason
                self._record_model_status(ctx, model_text_reason, phase="patch")
                self._write_trace(ctx, f"MODEL_OUTPUT_REJECTED: {model_text_reason}")
                if model_text_reason != "MODEL_EMPTY_RESPONSE":
                    self._write_model_response_trace(ctx, response)
                return ""
            # Trace 日誌
            self._write_model_response_trace(ctx, response)
            return response
        except Exception as e:
            reason = classify_model_exception(e)
            ctx.failure_reason = reason
            self._record_model_status(ctx, reason, f"{type(e).__name__}: {e}", phase="patch")
            self._write_trace(ctx, f"GENERATE_EXCEPTION: {reason}: {str(e)}")
            return ""

    def _write_model_response_trace(self, ctx: HealContext, response: str) -> None:
        log_file = Path("/Users/jameschen/Workspace/nexus/scratch/llm_trace.log")
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(f"\n\n=== ATTEMPT {ctx.attempt} FOR {ctx.instance_id} ===\n")
            f.write(f"--- RESPONSE ---\n{response}\n")
            f.write("="*80 + "\n")

    def _fail_closed_model_call(self, ctx: HealContext, exc: BaseException, *, phase: str) -> HealContext:
        reason = classify_model_exception(exc)
        ctx.failure_reason = reason
        ctx.runner_completed = True
        ctx.solve_eligible = False
        self._record_model_status(ctx, reason, f"{type(exc).__name__}: {exc}", phase=phase)
        self._write_trace(ctx, f"MODEL_PHASE_EXCEPTION phase={phase}: {reason}: {str(exc)}")
        ctx.receipt_path = str(write_repair_receipt(ctx))
        return ctx

    def _record_model_status(self, ctx: HealContext, status: str, detail: str = "", *, phase: str | None = None) -> None:
        for decision in reversed(ctx.model_decisions):
            if phase is None or decision.get("phase") == phase:
                decision["status"] = status
                if detail:
                    decision["detail"] = detail[:500]
                return

    def _latest_patch_error_reason(self, ctx: HealContext) -> str:
        if not ctx.errors:
            return "NO_PATCH"
        latest = ctx.errors[-1]
        kind = getattr(latest.kind, "name", str(latest.kind))
        message = str(latest.message or "").strip()
        return f"{kind}:{message}" if message else kind

    def _select_model(self, ctx: HealContext, *, phase: str) -> Dict[str, Any]:
        decision = LocalModelPolicy.select_model(
            task_type="swe_repair",
            phase=phase,
            context={
                "reasoning_mode": ctx.reasoning_mode,
                "file_count": len(ctx.localized_files) or 1,
            },
        )
        ctx.model_decisions.append({"phase": phase, **decision})
        self._write_trace(
            ctx,
            (
                f"Model decision phase={phase} model={decision['model']} "
                f"timeout={decision['timeout_seconds']} reason={decision['reason_code']}"
            ),
        )
        return decision

    def _call_model(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        model_name: str,
        timeout_seconds: int | None = None,
    ) -> str:
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

    def _handle_retry(self, ctx: HealContext, error: PatchError) -> HealContext:
        if not ctx.errors or ctx.errors[-1] is not error:
            ctx.errors.append(error)
        # Phase 2 Alignment: 使用 SelfCorrector 產生高品質重試 Prompt
        # 如果是 Mismatch，嘗試找最近片段
        if error.kind == PatchErrorKind.SEARCH_MISMATCH and error.file_path and error.failed_search_text:
            target_path = ctx.repo_dir / error.file_path
            if target_path.exists():
                file_content = target_path.read_text(encoding="utf-8", errors="replace")
                # 這裡也要帶入 context_hints 以確保 retry 時提供的原文也是準的
                context_hints = ctx.plan.get("search_symbols", [])
                from nexus.services.local_heal.closest_snippet import find_closest_snippet
                error.closest_match = find_closest_snippet(file_content, error.failed_search_text, context_hints=context_hints)

        ctx.user_prompt = self.corrector.build_retry_prompt(ctx.user_prompt, error)
        ctx.attempt += 1
        self._write_trace(ctx, f"Retrying... Attempt {ctx.attempt}")
        return ctx
