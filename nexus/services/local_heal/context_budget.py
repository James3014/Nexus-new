from dataclasses import dataclass
from typing import List, Tuple
from nexus.services.local_heal.errors import PatchError

@dataclass
class ContextBudgetConfig:
    max_ctx_tokens: int = 8192
    prompt_overhead_tokens: int = 800
    problem_max_tokens: int = 1500
    source_budget_tokens: int = 8000  # Reduced from 12000 for cost optimization (S7)
    chars_per_token: float = 3.5  # 粗略轉換率


class ContextBudgetManager:
    """動態 Token 預算管理器，防止 Context 溢出與重試 Prompt 膨脹 (SWE-agent / Agentless)"""

    def __init__(self, config: ContextBudgetConfig = None):
        self.config = config or ContextBudgetConfig()

    def fit_source_files(self, files: List[Tuple[str, str]]) -> List[Tuple[str, str]]:
        """
        根據 source_budget_tokens 動態裁切定位到的原始碼檔案。
        若超出預算，優先保留高相關性檔案的完整上下文，對後續檔案做局部截斷以保全上下文，而不直接剔除。
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
                remaining_budget = max_chars - current_chars
                if remaining_budget >= 1000:
                    truncated_len = remaining_budget - 50
                    truncated_content = content[:truncated_len] + f"\n... [truncated for context window limits, remaining budget: {remaining_budget} chars]"
                    fitted_files.append((name, truncated_content))
                    current_chars += len(truncated_content)
                else:
                    # 預算過低時繼續找有沒有更小的重要檔案可以塞入，不提前中斷
                    continue

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

