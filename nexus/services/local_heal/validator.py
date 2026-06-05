import ast
import re
from typing import Tuple

def validate_syntax(code: str) -> Tuple[bool, str]:
    """在記憶體中利用 AST 靜態編譯代碼，驗證其是否包含語法錯誤。"""
    try:
        ast.parse(code)
        return True, ""
    except SyntaxError as e:
        return False, f"SyntaxError: {e.msg} at line {e.lineno}, col {e.offset}"
    except Exception as e:
        return False, f"SyntaxError: {str(e)}"

def validate_name_sanity(code: str) -> Tuple[bool, str]:
    """
    檢查代碼中是否存在常見的 LLM 佔位符或拼寫錯誤 (Spirit Alignment)。
    """
    duplicate_name = _find_duplicate_top_level_definition(code)
    if duplicate_name:
        return False, f"Name sanity failed: Duplicate top-level definition '{duplicate_name}'"

    scan_code = _code_without_docstrings_or_comments(code)
    slop_patterns = [
        r'placeholder', r'your_code_here', r'modify_this',
        r'\.\.\.', r'FIXME', r'TODO: implementation'
    ]
    for pattern in slop_patterns:
        if re.search(pattern, scan_code, re.IGNORECASE):
            return False, f"Name sanity failed: Found disallowed placeholder pattern '{pattern}'"
    return True, ""


def _find_duplicate_top_level_definition(code: str) -> str:
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return ""

    seen = set()
    for node in tree.body:
        if not isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        key = (type(node), node.name)
        if key in seen:
            return node.name
        seen.add(key)
    return ""


def _code_without_docstrings_or_comments(code: str) -> str:
    try:
        tree = ast.parse(code)
        tree = _strip_docstrings_and_comments(tree)
        return ast.unparse(tree)
    except Exception:
        return code

def _strip_docstrings_and_comments(node):
    """遞迴移除 AST 節點中的 docstrings。"""
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
    """取得代碼移除 docstring 後的 AST dump 字串。"""
    try:
        tree = ast.parse(code)
        tree = _strip_docstrings_and_comments(tree)
        return ast.dump(tree, include_attributes=False)
    except Exception:
        return ""

def validate_effective_change(old_code: str, new_code: str) -> Tuple[bool, str]:
    """判斷新代碼相較於舊代碼是否包含實質邏輯代碼變更。"""
    old_dump = _get_logical_ast_dump(old_code)
    new_dump = _get_logical_ast_dump(new_code)
    
    if old_dump == new_dump:
        return False, "The patch only modified docstrings, comments, or formatting. No functional code logic was changed."
    return True, ""
