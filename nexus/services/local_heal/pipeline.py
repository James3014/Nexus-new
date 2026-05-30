from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Tuple, Dict, Any, Optional

from nexus.services.local_heal.localizer import Localizer
from nexus.services.local_heal.parser import SearchReplaceParser
from nexus.services.local_heal.patcher import Patcher, PatchResult
from nexus.services.local_heal.validator import validate_syntax, validate_effective_change
from nexus.services.local_heal.corrector import SelfCorrector
from nexus.services.local_heal.context_budget import ContextBudgetManager
from nexus.services.local_heal.errors import PatchError, PatchErrorKind


@dataclass
class HealContext:
    """管線狀態上下文封裝"""
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


class HealPipeline:
    """固定 5 階段管線，將流程控制與工具完全解耦 (SRP / SOTA Schedulers)"""

    def __init__(self, ollama_generate_fn: Any):
        self.localizer = Localizer()
        self.parser = SearchReplaceParser()
        self.patcher = Patcher()
        self.corrector = SelfCorrector()
        self.budget_manager = ContextBudgetManager()
        self.ollama_generate = ollama_generate_fn

    def run(self, ctx: HealContext) -> HealContext:
        # Stage 1: 定位相關檔案
        ctx = self._localize(ctx)
        if not ctx.localized_files:
            return ctx

        # 初始化 System Prompt 與原始 User Prompt
        ctx.system_prompt = (
            "You are an expert software engineer.\n"
            "Output exact SEARCH/REPLACE blocks to fix the bug.\n"
            "Every block MUST start with 'FILE: path/to/file.py' followed by standard search/replace format:\n"
            "<<<<<<< SEARCH\n"
            "[exact original code]\n"
            "=======\n"
            "[new code]\n"
            ">>>>>>> REPLACE\n"
            "Make minimum impact changes to resolve the issue. Output ONLY blocks. No conversational text.\n"
            "NEVER apologize. NEVER say you cannot help. NEVER ask the user for clarification.\n"
            "You have ALL the source code needed. Output ONLY SEARCH/REPLACE blocks."
        )
        
        file_ctx = "\n\n".join(f"=== FILE: {fname} ===\n{content}" for fname, content in ctx.localized_files)
        ctx.user_prompt = f"Bug Report:\n{ctx.problem_statement[:1500]}\n\nSource Code:\n{file_ctx}\n\nOutput SEARCH/REPLACE block(s):"

        # 迭代重試自癒循環
        while ctx.attempt <= ctx.max_tries:
            ctx.errors.clear()
            
            # 還原 git 所有修改與未追蹤檔案，確保每次 Attempt 都基於絕對乾淨的 pristine 基線
            import subprocess
            subprocess.run(["git", "checkout", "--", "."], cwd=str(ctx.repo_dir), capture_output=True)
            subprocess.run(["git", "clean", "-fd"], cwd=str(ctx.repo_dir), capture_output=True)
            
            # Stage 2: 呼叫 LLM 生成 Patch
            response = self._generate_patch(ctx)
            if not response:
                break

            # Stage 3: 解析與責任鏈匹配替換
            blocks = self.parser.parse_blocks(response)
            if not blocks:
                err = PatchError(
                    kind=PatchErrorKind.NO_BLOCKS_FOUND, 
                    message="LLM output no SEARCH/REPLACE blocks. You must format your response strictly using SEARCH/REPLACE blocks."
                )
                ctx.errors.append(err)
                ctx = self._handle_retry(ctx, err)
                continue

            applied_diffs = []
            has_error = False

            for b in blocks:
                target_path = ctx.repo_dir / b["file"]
                if not target_path.exists():
                    found_files = list(ctx.repo_dir.rglob(Path(b["file"]).name))
                    if found_files:
                        target_path = found_files[0]
                    else:
                        err = PatchError(
                            kind=PatchErrorKind.FILE_NOT_FOUND,
                            message=f"Target file not found: {b['file']}",
                            file_path=b["file"]
                        )
                        ctx.errors.append(err)
                        has_error = True
                        break

                # 讀取當前內容並嘗試套用 Patcher
                file_content = target_path.read_text(encoding="utf-8", errors="replace")
                patch_res = self.patcher.apply_patch(file_content, b["search"], b["replace"])

                if not patch_res.success:
                    # 提供最相似片段作為自癒 HUD 提示
                    from nexus.services.local_heal.closest_snippet import find_closest_snippet
                    closest_snippet = find_closest_snippet(file_content, b["search"])
                        
                    err = PatchError(
                        kind=PatchErrorKind.SEARCH_MISMATCH,
                        message=patch_res.error_message or "Verbatim mismatch",
                        file_path=b["file"],
                        closest_match=closest_snippet
                    )
                    ctx.errors.append(err)
                    has_error = True
                    break

                # Stage 4: 靜態 AST 語法檢測
                is_valid, syntax_err = validate_syntax(patch_res.new_content)
                if not is_valid:
                    err = PatchError(
                        kind=PatchErrorKind.SYNTAX_ERROR,
                        message=syntax_err,
                        file_path=b["file"]
                    )
                    ctx.errors.append(err)
                    has_error = True
                    break

                # 4.5: 靜態 AST 邏輯有效性檢驗 (防堵投機修改 docstring 假綠燈)
                is_effective, effective_err = validate_effective_change(file_content, patch_res.new_content)
                if not is_effective:
                    err = PatchError(
                        kind=PatchErrorKind.NO_EFFECTIVE_CODE_CHANGE,
                        message=effective_err,
                        file_path=b["file"]
                    )
                    ctx.errors.append(err)
                    has_error = True
                    break

                # 套用成功，暫存變更並更新檔案
                target_path.write_text(patch_res.new_content, encoding="utf-8")
                applied_diffs.append(patch_res.diff)

            if not has_error:
                ctx.final_patch = "\n".join(applied_diffs).strip()
                break  # 成功，跳出循環
            else:
                # Stage 5: 錯誤自癒引導 (HUD分流與重試Prompt重建)
                latest_err = ctx.errors[-1]
                ctx = self._handle_retry(ctx, latest_err)


        return ctx

    def _localize(self, ctx: HealContext) -> HealContext:
        ranked = self.localizer.rank_files(ctx.problem_statement, ctx.repo_dir, max_files=3)
        raw_files = self.localizer.extract_relevant_code(ranked)
        
        # 整合 AST FunctionLocalizer 對大檔案進行緊湊裁剪
        from nexus.services.local_heal.function_localizer import FunctionLocalizer
        fn_localizer = FunctionLocalizer()
        
        reduced_files = []
        for path, content in raw_files:
            focused = fn_localizer.build_focused_context(path, content, ctx.problem_statement)
            reduced_files.append((path, focused))
            
        # 整合 Context Budget Manager 進行硬性預算限制與自適應裁剪
        ctx.localized_files = self.budget_manager.enforce_hard_limit(reduced_files)
        return ctx

    def _generate_patch(self, ctx: HealContext) -> str:
        try:
            response = self.ollama_generate(ctx.system_prompt, ctx.user_prompt)
            # 寫入 LLM 除錯日誌
            from pathlib import Path
            log_dir = Path("/Users/jameschen/Workspace/nexus/scratch")
            log_dir.mkdir(parents=True, exist_ok=True)
            log_file = log_dir / "llm_trace.log"
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(f"\n\n=== ATTEMPT {ctx.attempt} FOR {ctx.instance_id} ===\n")
                f.write(f"--- SYSTEM PROMPT ---\n{ctx.system_prompt}\n")
                f.write(f"--- USER PROMPT ---\n{ctx.user_prompt}\n")
                f.write(f"--- RESPONSE ---\n{response}\n")
                f.write("="*80 + "\n")
            return response
        except Exception as e:
            from pathlib import Path
            log_dir = Path("/Users/jameschen/Workspace/nexus/scratch")
            log_dir.mkdir(parents=True, exist_ok=True)
            with open(log_dir / "llm_trace.log", "a", encoding="utf-8") as f:
                f.write(f"\n\n=== EXCEPTION FOR {ctx.instance_id} ===\n{str(e)}\n")
            return ""

    def _handle_retry(self, ctx: HealContext, error: PatchError) -> HealContext:
        # 自適應 Context 預算縮減：如果是空區塊錯誤且 localized 檔案太多，主動把 context 減小至 top-1 檔案
        if error.kind == PatchErrorKind.NO_BLOCKS_FOUND and len(ctx.localized_files) > 1:
            ctx.localized_files = ctx.localized_files[:1]
            file_ctx = "\n\n".join(f"=== FILE: {fname} ===\n{content}" for fname, content in ctx.localized_files)
            ctx.user_prompt = f"Bug Report:\n{ctx.problem_statement[:1500]}\n\nSource Code:\n{file_ctx}\n\nOutput SEARCH/REPLACE block(s):"

        # 首先進行重試 Prompt 壓縮去重，防堵線性膨脹
        compressed_base = self.budget_manager.compress_retry_prompt(ctx.user_prompt, error.message)
        # 用 HUD 分流器構建精確的引導提示
        ctx.user_prompt = self.corrector.build_retry_prompt(compressed_base, error)
        ctx.attempt += 1
        return ctx

