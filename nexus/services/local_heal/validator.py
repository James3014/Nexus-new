import ast
from typing import Tuple

def validate_syntax(code: str) -> Tuple[bool, str]:
    """
    在記憶體中利用 AST 靜態編譯代碼，驗證其是否包含語法錯誤。
    """
    try:
        ast.parse(code)
        return True, ""
    except SyntaxError as e:
        return False, f"SyntaxError: {e.msg} at line {e.lineno}, col {e.offset}"
    except Exception as e:
        return False, f"SyntaxError: {str(e)}"
