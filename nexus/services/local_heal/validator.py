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


def _strip_docstrings_and_comments(node):
    """
    遞迴移除 AST 節點中的 docstrings/expression strings 還有字串常量。
    """
    if isinstance(node, (ast.FunctionDef, ast.ClassDef, ast.Module)):
        if (node.body and 
            isinstance(node.body[0], ast.Expr) and 
            isinstance(node.body[0].value, ast.Constant) and 
            isinstance(node.body[0].value.value, str)):
            node.body = node.body[1:]
            
    for child in ast.iter_child_nodes(node):
        _strip_docstrings_and_comments(child)
        
    return node


def _get_logical_ast_dump(code: str) -> str:
    """
    取得代碼移除 docstring 後的 AST dump 字串。
    """
    try:
        tree = ast.parse(code)
        tree = _strip_docstrings_and_comments(tree)
        # include_attributes=False 能防止行號/列號等排版變動影響比對
        return ast.dump(tree, include_attributes=False)
    except Exception:
        return ""


def validate_effective_change(old_code: str, new_code: str) -> Tuple[bool, str]:
    """
    判斷新代碼相較於舊代碼是否包含實質邏輯代碼變更。
    """
    old_dump = _get_logical_ast_dump(old_code)
    new_dump = _get_logical_ast_dump(new_code)
    
    if old_dump == new_dump:
        return False, "The patch only modified docstrings, comments, formatting, or comments. No functional code logic was changed."
    return True, ""

