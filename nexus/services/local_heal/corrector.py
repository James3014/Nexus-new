from typing import Dict, Any

class SelfCorrector:
    """
    管理與 LLM 互動的自我糾錯循環 (Self-Correction Loop)。
    在套用 Diff 或 AST 靜態編譯發生語法錯誤時，自動構造引導式補救 Prompt。
    """
    
    def build_retry_prompt(self, original_user_prompt: str, error_log: str) -> str:
        """
        結合原始 User Prompt 與編譯/語法錯誤日誌，生成帶有語意邊界約束的重試 Prompt。
        """
        retry_instruction = (
            f"\n\n⚠️ 【自癒引擎警告：前一次嘗試發生了語法或編譯錯誤】\n"
            f"錯誤日誌：\n{error_log}\n\n"
            f"請務必修正上述語法錯誤（例如未閉合的括號、格式錯亂或截斷）。\n"
            f"請重新輸出完整的、語法正確的 SEARCH/REPLACE 區塊。"
        )
        return original_user_prompt + retry_instruction
