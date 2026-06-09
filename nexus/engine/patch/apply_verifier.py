import ast
import hashlib
from typing import Tuple, Optional

class ApplyVerifier:
    """
    🛡️ ApplyVerifier: 套用驗證器
    驗證檔案是否真的變更、語法是否仍然合法。
    """
    def verify_change(self, old_content: str, new_content: str) -> Tuple[bool, str]:
        # 1. 檢查內容是否真的變更
        if old_content == new_content:
            return False, "FILE_UNCHANGED"
            
        # 2. 檢查 Python 語法是否合法
        try:
            ast.parse(new_content)
        except SyntaxError as e:
            return False, f"SYNTAX_ERROR_AFTER_APPLY: line {e.lineno}"
            
        return True, "SUCCESS"
