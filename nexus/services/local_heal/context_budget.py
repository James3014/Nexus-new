from dataclasses import dataclass
from typing import List, Tuple
from nexus.services.local_heal.errors import PatchError

@dataclass
class ContextBudgetConfig:
    max_ctx_tokens: int = 8192
    prompt_overhead_tokens: int = 800
    problem_max_tokens: int = 1500
    source_budget_tokens: int = 3000
    chars_per_token: float = 3.5  # 粗略轉換率


class ContextBudgetManager:
    """動態 Token 預算管理器，防止 Context 溢出與重試 Prompt 膨脹 (SWE-agent / Agentless)"""

    def __init__(self, config: ContextBudgetConfig = None):
        self.config = config or ContextBudgetConfig()

    def fit_source_files(self, files: List[Tuple[str, str]]) -> List[Tuple[str, str]]:
        """
        根據 source_budget_tokens 動態裁切定位到的原始碼檔案。
        若超出預算，優先保留高相關性檔案的完整上下文，依序剔除低相關性（後面的）檔案。
        如果最核心的檔案也超出 budget，則對其進行截斷。
        """
        max_chars = int(self.config.source_budget_tokens * self.config.chars_per_token)
        
        total_chars = sum(len(content) for _, content in files)
        if total_chars <= max_chars:
            return files

        fitted_files = []
        current_chars = 0
        
        for name, content in files:
            file_len = len(content)
            if current_chars + file_len <= max_chars:
                fitted_files.append((name, content))
                current_chars += file_len
            else:
                if not fitted_files:
                    # 第一個檔案就超額，對其截斷
                    truncated_len = max(5, max_chars - 25)
                    truncated_content = content[:truncated_len] + "\n... [truncated for context window limits]"
                    fitted_files.append((name, truncated_content))
                    current_chars += len(truncated_content)
                elif file_len <= 10:
                    # 容許極小檔案滑入，避免因前述截斷後的後綴長度超額而直接丟棄重要小檔案
                    fitted_files.append((name, content))
                    current_chars += file_len
                else:
                    break

        return fitted_files

    def enforce_hard_limit(self, files: List[Tuple[str, str]]) -> List[Tuple[str, str]]:
        """硬性執行 Context 預算限制"""
        return self.fit_source_files(files)

    def compress_retry_prompt(self, original_user_prompt: str, error_log: str) -> str:
        """
        重試時，對歷次堆疊的錯誤 log 進行壓縮與摘要去重，防止 Prompt 隨重試次數呈線性或指數級膨脹。
        """
        if "⚠️ [NEXUS BATTLESUIT HUD" in original_user_prompt:
            original_user_prompt = original_user_prompt.split("⚠️ [NEXUS BATTLESUIT HUD")[0].strip()
        return original_user_prompt

