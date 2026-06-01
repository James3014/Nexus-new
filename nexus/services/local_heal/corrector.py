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
            # Phase 2: 強化 HUD 提示契約 (Literal Copy Mode)
            closest_hint = ""
            if error.closest_match:
                # 判斷是否為高品質匹配 (由 Patcher/Matcher 標記或在此推斷)
                # 這裡暫時以提示內容存在作為基礎
                closest_hint = (
                    f"### [NEXUS CANONICAL SOURCE CODE FOUND]\n"
                    f"The battlesuit has located the EXACT section you likely intended to change:\n"
                    f"```python\n{error.closest_match}\n```\n\n"
                    f"CRITICAL CONTRACT:\n"
                    f"1. You MUST copy the code above CHARACTER-FOR-CHARACTER into your SEARCH block.\n"
                    f"2. Do NOT change variable names, quotes, or indentation in the SEARCH block.\n"
                    f"3. Only apply your logic changes inside the REPLACE block.\n"
                )
            
            retry_instruction = (
                f"Your previous SEARCH block did not match the original code in the file.\n"
                f"--> {error.message}\n\n"
                f"{closest_hint}"
                f"Please output a corrected SEARCH/REPLACE block now, ensuring perfect literal alignment with the source."
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
            message = str(error.message or "")
            if message.startswith("Tests failed:"):
                retry_instruction = (
                    f"CRITICAL ERROR: Your previous patch compiled and changed code, but visible verification still failed.\n"
                    f"--> {error.message}\n\n"
                    f"Please do the following:\n"
                    f"1. Compare the expected and actual outputs in the verification report before editing again.\n"
                    f"2. Do NOT repeat the same patch or add broad new framework methods unless the source already exposes that extension point.\n"
                    f"3. Prefer the smallest existing function/helper that directly computes the wrong value.\n"
                    f"4. Output a valid SEARCH/REPLACE block with the corrected root-cause logic."
                )
            else:
                retry_instruction = (
                    f"CRITICAL ERROR: Your previous patch only modified docstrings, comments, or formatting, but made NO functional code logic changes!\n"
                    f"--> {error.message}\n\n"
                    f"Please do the following:\n"
                    f"1. You MUST modify the actual Python logic/statements/functions to fix the described bug.\n"
                    f"2. Changing docstrings or typos in comments will NOT solve the issue and will be rejected.\n"
                    f"Output a valid SEARCH/REPLACE block that implements functional code changes."
                )
        elif error.kind == PatchErrorKind.SEARCH_HAS_PLACEHOLDER:
            retry_instruction = (
                f"CRITICAL ERROR: Your previous SEARCH/REPLACE block contains placeholder comments (such as '# ...', '# ... existing code ...', or '...')!\n"
                f"--> {error.message}\n\n"
                f"Please do the following:\n"
                f"1. You MUST copy the target code character-for-character, completely and exactly, into your SEARCH block.\n"
                f"2. NEVER use '# ...' or other comments to skip existing code in either SEARCH or REPLACE blocks.\n"
                f"Output the fully written SEARCH/REPLACE block without any placeholder shortcuts."
            )
        else:
            retry_instruction = (
                f"Your previous attempt encountered an issue:\n"
                f"--> {error.message}\n\n"
                f"Please output a corrected and verified SEARCH/REPLACE block now."
            )

        return original_user_prompt + header + retry_instruction
