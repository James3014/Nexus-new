from dataclasses import dataclass, field
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


@dataclass
class HealContext:
    """管線狀態上下文封裝 (Nexus v2.9 Hardened)"""
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
    
    # --- 證據與驗證欄位 ---
    repro_script: str = ""
    repro_evidence: str = ""
    plan: Dict[str, Any] = field(default_factory=dict)
    evaluation_report: str = ""
    hidden_verifier_passed: bool = False
    runner_completed: bool = False
    solve_eligible: bool = False


class HealPipeline:
    """固定 5 階段管線，將流程控制與工具完全解耦 (SRP / SOTA Schedulers)"""

    def __init__(self, ollama_generate_fn: Any, hidden_verifier: bool = False):
        self.localizer = Localizer()
        self.parser = SearchReplaceParser()
        self.patcher = Patcher()
        self.corrector = SelfCorrector()
        self.budget_manager = ContextBudgetManager()
        self.planner = Planner()
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
        self.repro_runner = ReproductionRunner(ctx.repo_dir)
        self.repo_map = RepoMap(ctx.repo_dir)
        self.eval_gate = EvaluationGate(ctx.repo_dir)

        # --- Phase 1: Reproduction (建立物理證據) ---
        self._write_trace(ctx, "[Phase 1] Building physical evidence...")
        if ctx.repro_evidence:
            success, evidence = True, ctx.repro_evidence
        else:
            if not ctx.repro_script:
                ctx.repro_script = self.repro_runner.generate_repro_script(ctx.problem_statement)
            success, evidence = self.repro_runner.run_repro(ctx.repro_script)

        # [Fail-closed] 如果完全沒有捕獲到物理證據，拒絕繼續
        if not evidence or len(evidence.strip()) < 10:
            self._write_trace(ctx, "❌ FAIL-CLOSED: No physical evidence captured. Aborting.")
            ctx.runner_completed = True
            ctx.solve_eligible = False
            return ctx

        ctx.repro_evidence = evidence
        self._write_trace(ctx, f"Reproduction success={success}, evidence_len={len(evidence)}")

        # --- Phase 2: Planning (戰略規劃) ---
        self._write_trace(ctx, "[Phase 2] Strategic planning...")
        ctx.plan = self.planner.create_plan(ctx.problem_statement, ctx.repro_evidence)
        self._write_trace(ctx, f"Plan symbols: {ctx.plan.get('search_symbols')}")

        # --- Phase 3: Localization (深度定位) ---
        self._write_trace(ctx, "[Phase 3] Locating fix targets...")
        if not ctx.localized_files:
            ctx = self._localize(ctx)
        if not ctx.localized_files:
            self._write_trace(ctx, "=== PIPELINE END localized_files=empty ===")
            ctx.runner_completed = True
            ctx.solve_eligible = False
            return ctx

        # 初始化 Prompt
        ctx.system_prompt = (
            "You are a Senior Principal Software Engineer at Nexus.\n"
            "Principles:\n"
            "1. BE EXPLICIT: Never use placeholders like '# ...' or '...'. Copy ALL code exactly.\n"
            "2. MODULARITY: Separate concerns. Fix the root cause with minimal side effects.\n"
            "3. INTEGRITY: Ensure indentation and logic flow are perfect.\n\n"
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

            response = self._generate_patch(ctx)
            if not response: break

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
                if not target_path.exists():
                    found = list(ctx.repo_dir.rglob(Path(b["file"]).name))
                    target_path = found[0] if found else target_path

                if not target_path.exists():
                    err = PatchError(kind=PatchErrorKind.FILE_NOT_FOUND, message=f"File not found: {b['file']}")
                    ctx.errors.append(err)
                    has_error = True
                    break

                file_content = target_path.read_text(encoding="utf-8", errors="replace")
                patch_res = self.patcher.apply_patch(file_content, b["search"], b["replace"])
                self._write_trace(ctx, f"Patcher: success={patch_res.success}, strategy={patch_res.strategy_used}")

                if not patch_res.success:
                    err = PatchError(kind=PatchErrorKind.SEARCH_MISMATCH, message=patch_res.error_message, file_path=b["file"])
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

                target_path.write_text(patch_res.new_content, encoding="utf-8")
                applied_diffs.append(patch_res.diff)

            if not has_error:
                ctx.final_patch = "\n".join(applied_diffs).strip()
                
                # --- Phase 5: Verification (代數驗證) ---
                self._write_trace(ctx, "[Phase 5] Algebraic verification...")
                repro_path = ctx.repo_dir / "reproduce_bug.py"
                repro_path.write_text(ctx.repro_script, encoding="utf-8")
                
                try:
                    visible_results = self.eval_gate.run_visible_tests([["python3", "reproduce_bug.py"]])
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

    def _localize(self, ctx: HealContext) -> HealContext:
        ranked = self.localizer.rank_files(ctx.problem_statement, ctx.repo_dir)
        raw_files = self.localizer.extract_relevant_code(ranked)
        ctx.localized_files = self.budget_manager.enforce_hard_limit(raw_files)
        return ctx

    def _generate_patch(self, ctx: HealContext) -> str:
        try:
            response = self.ollama_generate(ctx.system_prompt, ctx.user_prompt)
            # Trace 日誌
            log_file = Path("/Users/jameschen/Workspace/nexus/scratch/llm_trace.log")
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(f"\n\n=== ATTEMPT {ctx.attempt} FOR {ctx.instance_id} ===\n")
                f.write(f"--- RESPONSE ---\n{response}\n")
                f.write("="*80 + "\n")
            return response
        except Exception as e:
            self._write_trace(ctx, f"GENERATE_EXCEPTION: {str(e)}")
            return ""

    def _handle_retry(self, ctx: HealContext, error: PatchError) -> HealContext:
        ctx.errors.append(error)
        hud_warning = f"\n\n⚠️ [NEXUS BATTLESUIT HUD: CRITICAL WARNING]\nERROR: {error.message}\n"
        compressed_base = self.budget_manager.compress_retry_prompt(ctx.user_prompt, hud_warning)
        ctx.user_prompt = f"{compressed_base}{hud_warning}"
        ctx.attempt += 1
        return ctx
