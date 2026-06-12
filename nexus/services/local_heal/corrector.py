from typing import Any

from nexus.services.local_heal.errors import PatchError, PatchErrorKind

class SelfCorrector:
    """管理與 LLM 互動的自我糾錯循環 (Self-Correction Loop)，實現 HUDFeedbackRouter 精確分流"""

    def build_retry_prompt(self, original_user_prompt: str, error: Any, targeted_files: str = "") -> str:
        """
        結合原始 User Prompt 與錯誤類型，分流生成最精確的重試引導 Prompt
        """
        # 為了舊版測試相容性，若傳入 string error，包裝為強類型 PatchError
        if isinstance(error, str):
            if "SyntaxError" in error:
                error = PatchError(kind=PatchErrorKind.SYNTAX_ERROR, message=error)
            else:
                error = PatchError(kind=PatchErrorKind.SEARCH_MISMATCH, message=error)

        # Strip any existing HUD warnings to prevent prompt accumulation and bloat
        marker = "\n\n⚠️ [NEXUS BATTLESUIT HUD: CRITICAL WARNING - PREVIOUS ATTEMPT FAILED]"
        if marker in original_user_prompt:
            original_user_prompt = original_user_prompt.split(marker)[0]

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
            # Phase 4 Upgrade: Authoritative Canonical Copy-Paste
            closest_hint = ""
            if error.closest_match:
                closest_hint = (
                    f"### [NEXUS CANONICAL SOURCE CODE FOUND]\n"
                    f"The battlesuit has located the EXACT section in the file. You MUST copy the code below CHARACTER-FOR-CHARACTER into your SEARCH block:\n"
                    f"```python\n{error.closest_match}\n```\n\n"
                    f"CONTRACT:\n"
                    f"1. Copy the canonical snippet above exactly. Do NOT fix typos or change formatting in the SEARCH block.\n"
                    f"2. Apply your intended fix ONLY in the REPLACE block.\n"
                )
            else:
                closest_hint = (
                    f"### [NEXUS WARNING: CANONICAL SNIPPET NOT FOUND]\n"
                    f"The battlesuit could not verify your SEARCH block in the file. Please carefully check the [SOURCE CONTEXT] below in the prompt and ensure your SEARCH block matches the file content character-for-character, including indentation and newlines.\n"
                )
            
            retry_instruction = (
                f"CRITICAL ERROR: Your previous SEARCH block did not match the file content.\n"
                f"--> {error.message}\n\n"
                f"{closest_hint}"
                f"Output the corrected SEARCH/REPLACE block now."
            )
        elif error.kind == PatchErrorKind.REFUSAL_DETECTED:
             retry_instruction = (
                f"CRITICAL DIRECTIVE: You previously apologized or refused to provide a fix.\n"
                f"As a Senior Nexus Engineer, you ARE capable of this task. All necessary source code and context are provided.\n"
                f"Do NOT apologize. Do NOT state limitations. Simply analyze the logic and provide the SEARCH/REPLACE block now."
            )
        elif error.kind == PatchErrorKind.EMPTY_RESPONSE:
            retry_instruction = (
                f"CRITICAL ERROR: Your previous response was EMPTY!\n"
                f"You MUST provide a fix using the SEARCH/REPLACE format. If you need more information, assume the provided code context is sufficient."
            )
        elif error.kind == PatchErrorKind.NO_BLOCKS_FOUND:
            file_hint = f"Focus ONLY on modifying the following files: {targeted_files}\n" if targeted_files else ""
            retry_instruction = (
                f"CRITICAL ERROR: Your previous response contained ZERO SEARCH/REPLACE blocks (or you modified a non-existent file)!\n"
                f"You MUST use the exact `<<<<<<< SEARCH` and `>>>>>>> REPLACE` format.\n\n"
                f"{file_hint}"
                f"Rules:\n"
                f"1. NO conversation. NO explanations. NO examples.\n"
                f"2. Specify the file clearly: 'FILE: path/to/file.py' before the block. Use ONLY files provided in the context.\n"
                f"Output a valid SEARCH/REPLACE block now."
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
        elif error.kind == PatchErrorKind.NAME_SANITY_ERROR:
            retry_instruction = (
                f"CRITICAL ERROR: Your previous patch failed Nexus code sanity checks.\n"
                f"--> {error.message}\n\n"
                f"Please do the following:\n"
                f"1. Do NOT create or redefine a top-level class or function that already exists in the file.\n"
                f"2. Modify the existing definition in place using one precise SEARCH/REPLACE block.\n"
                f"3. Keep unrelated imports, classes, functions, and tests unchanged.\n"
                f"Output the corrected SEARCH/REPLACE block now."
            )
        else:
            retry_instruction = (
                f"Your previous attempt encountered an issue:\n"
                f"--> {error.message}\n\n"
                f"Please output a corrected and verified SEARCH/REPLACE block now."
            )

        return original_user_prompt + header + retry_instruction
