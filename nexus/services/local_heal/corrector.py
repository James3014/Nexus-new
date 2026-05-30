from nexus.services.local_heal.errors import PatchError, PatchErrorKind

class SelfCorrector:
    """管理與 LLM 互動的自我糾錯循環 (Self-Correction Loop)，實現 HUDFeedbackRouter 精確分流"""

    def build_retry_prompt(self, original_user_prompt: str, error: Any) -> str:
        """
        結合原始 User Prompt 與錯誤類型，分流生成最精確的重試引導 Prompt
        """
        # 為了舊版測試相容性，若傳入 string error，包裝為強類型 PatchError
        if isinstance(error, str):
            if "SyntaxError" in error:
                error = PatchError(kind=PatchErrorKind.SYNTAX_ERROR, message=error)
            else:
                error = PatchError(kind=PatchErrorKind.SEARCH_MISMATCH, message=error)

        header = "\n\n⚠️ [NEXUS BATTLESUIT HUD: CRITICAL WARNING - PREVIOUS ATTEMPT FAILED]\n"
        
        if error.kind == PatchErrorKind.SYNTAX_ERROR:
            retry_instruction = (
                f"Your previous patch caused a syntax compilation error in Python:\n"
                f"--> {error.message}\n\n"
                f"Please do the following:\n"
                f"1. Carefully inspect your REPLACE block for missing brackets, commas, quotes, or incorrect indentation.\n"
                f"2. Keep the SEARCH block EXACTLY the same, and only fix the Python syntax inside the REPLACE block.\n"
                f"Output the fully corrected SEARCH/REPLACE block with perfect Python syntax."
            )
        elif error.kind == PatchErrorKind.SEARCH_MISMATCH:
            # 如果有戰甲模糊匹配找到的最接近片段，提供給模型直接複寫
            closest_hint = ""
            if error.closest_match:
                closest_hint = (
                    f"The battlesuit found the closest code block in the codebase is:\n"
                    f"```python\n{error.closest_match}\n```\n\n"
                )
            
            retry_instruction = (
                f"Your previous SEARCH block did not match the original code in the file.\n"
                f"--> {error.message}\n\n"
                f"{closest_hint}"
                f"Please ensure you copy the target source code EXACTLY character-for-character into your SEARCH block, "
                f"including all whitespaces, comments, and line indentations, and output the SEARCH/REPLACE block again."
            )
        elif error.kind == PatchErrorKind.NO_BLOCKS_FOUND:
            retry_instruction = (
                f"CRITICAL ERROR: Your previous response contained ZERO SEARCH/REPLACE blocks!\n"
                f"You MUST use the exact `<<<<<<< SEARCH` and `>>>>>>> REPLACE` block format to suggest edits.\n\n"
                f"Rules you MUST follow:\n"
                f"1. Do NOT write conversational text or explanations. Only output code blocks.\n"
                f"2. Do NOT apologize or ask the user to provide the target code. You have all the source code you need in the prompt.\n"
                f"3. Make sure to specify the file name clearly, e.g., 'FILE: path/to/file.py' right before the SEARCH/REPLACE block.\n"
                f"4. You must find the code to change in the provided file contents and output a valid SEARCH/REPLACE block now."
            )
        elif error.kind == PatchErrorKind.NO_EFFECTIVE_CODE_CHANGE:
            retry_instruction = (
                f"CRITICAL ERROR: Your previous patch only modified docstrings, comments, or formatting, but made NO functional code logic changes!\n"
                f"--> {error.message}\n\n"
                f"Please do the following:\n"
                f"1. You MUST modify the actual Python logic/statements/functions to fix the described bug.\n"
                f"2. Changing docstrings or typos in comments will NOT solve the issue and will be rejected.\n"
                f"Output a valid SEARCH/REPLACE block that implements functional code changes."
            )
        else:
            retry_instruction = (
                f"Your previous attempt encountered an issue:\n"
                f"--> {error.message}\n\n"
                f"Please output a corrected and verified SEARCH/REPLACE block now."
            )

        return original_user_prompt + header + retry_instruction

