"""AST-based symbol locator for line-span patch protocol."""

import ast
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional


class ASTLocatorErrorKind(Enum):
    FILE_NOT_FOUND = "FILE_NOT_FOUND"
    AST_PARSE_ERROR = "AST_PARSE_ERROR"
    SYMBOL_NOT_FOUND = "SYMBOL_NOT_FOUND"
    AMBIGUOUS_SYMBOL = "AMBIGUOUS_SYMBOL"
    UNSUPPORTED_SYMBOL_KIND = "UNSUPPORTED_SYMBOL_KIND"


@dataclass
class ASTLocatorResult:
    ok: bool
    error_kind: Optional[ASTLocatorErrorKind]
    message: Optional[str]
    file_path: str
    symbol_name: str
    kind: Optional[str]
    span_start: Optional[int]
    span_end: Optional[int]
    source_hash: Optional[str]
    ambiguous_matches: list


def _read_file(file_path: str) -> str | None:
    try:
        return Path(file_path).read_text()
    except Exception:
        return None


def _get_line_number(node: ast.AST, source_lines: list[str]) -> int:
    return getattr(node, "lineno", 0)


def _locate_in_module(tree: ast.Module, symbol_name: str, source_lines: list[str]) -> list[dict]:
    matches = []
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.FunctionDef) or isinstance(node, ast.AsyncFunctionDef):
            if node.name == symbol_name:
                matches.append({
                    "kind": "function",
                    "start": _get_line_number(node, source_lines),
                    "end": getattr(node, "end_lineno", _get_line_number(node, source_lines)),
                })
        elif isinstance(node, ast.ClassDef):
            if node.name == symbol_name:
                matches.append({
                    "kind": "class",
                    "start": _get_line_number(node, source_lines),
                    "end": getattr(node, "end_lineno", _get_line_number(node, source_lines)),
                })
            for item in ast.iter_child_nodes(node):
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    qualified = f"{node.name}.{item.name}"
                    if qualified == symbol_name or item.name == symbol_name:
                        matches.append({
                            "kind": "method",
                            "start": _get_line_number(item, source_lines),
                            "end": getattr(item, "end_lineno", _get_line_number(item, source_lines)),
                        })
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == symbol_name:
                    matches.append({
                        "kind": "assignment",
                        "start": _get_line_number(node, source_lines),
                        "end": getattr(node, "end_lineno", _get_line_number(node, source_lines)),
                    })
    return matches


def locate_symbol(file_path: str, symbol_name: str) -> ASTLocatorResult:
    source = _read_file(file_path)
    if source is None:
        return ASTLocatorResult(False, ASTLocatorErrorKind.FILE_NOT_FOUND, f"file not found: {file_path}", file_path, symbol_name, None, None, None, None, [])

    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        return ASTLocatorResult(False, ASTLocatorErrorKind.AST_PARSE_ERROR, f"syntax error: {e}", file_path, symbol_name, None, None, None, None, [])

    source_lines = source.splitlines()
    matches = _locate_in_module(tree, symbol_name, source_lines)

    if not matches:
        return ASTLocatorResult(False, ASTLocatorErrorKind.SYMBOL_NOT_FOUND, f"symbol not found: {symbol_name}", file_path, symbol_name, None, None, None, None, [])

    if len(matches) > 1:
        return ASTLocatorResult(False, ASTLocatorErrorKind.AMBIGUOUS_SYMBOL, f"ambiguous: {len(matches)} matches for {symbol_name}", file_path, symbol_name, None, None, None, None, matches)

    m = matches[0]
    span_text = "".join(source_lines[m["start"] - 1:m["end"]])
    import hashlib
    source_hash = hashlib.sha256(span_text.encode()).hexdigest()[:16]

    return ASTLocatorResult(True, None, None, file_path, symbol_name, m["kind"], m["start"], m["end"], source_hash, [])


def locate_function_or_class(file_path: str, symbol_name: str) -> ASTLocatorResult:
    return locate_symbol(file_path, symbol_name)
