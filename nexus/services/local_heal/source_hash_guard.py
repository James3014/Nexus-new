"""Source hash guard for line-span patch protocol."""

import ast
import hashlib
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional


class SourceHashGuardErrorKind(Enum):
    FILE_NOT_FOUND = "FILE_NOT_FOUND"
    SPAN_OUT_OF_RANGE = "SPAN_OUT_OF_RANGE"
    SOURCE_STALE = "SOURCE_STALE"
    AST_INVALID = "AST_INVALID"
    WRITE_DISABLED = "WRITE_DISABLED"
    IO_ERROR = "IO_ERROR"


@dataclass
class SourceHashGuardResult:
    ok: bool
    error_kind: Optional[SourceHashGuardErrorKind]
    message: Optional[str]
    file_path: str
    span_start: int
    span_end: int
    expected_hash: Optional[str]
    actual_hash: Optional[str]
    ast_valid: Optional[bool]
    preview_content_hash: Optional[str]
    wrote_file: bool


def _compute_hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def _read_lines(file_path: str) -> list[str] | None:
    try:
        return Path(file_path).read_text().splitlines(keepends=True)
    except FileNotFoundError:
        return None
    except Exception:
        return None


def compute_span_hash(lines: list[str], span_start: int, span_end: int) -> str:
    span_lines = lines[span_start - 1:span_end]
    return _compute_hash("".join(span_lines))


def verify_span_hash(file_path: str, span_start: int, span_end: int, expected_hash: str) -> SourceHashGuardResult:
    lines = _read_lines(file_path)
    if lines is None:
        return SourceHashGuardResult(False, SourceHashGuardErrorKind.FILE_NOT_FOUND, f"file not found: {file_path}", file_path, span_start, span_end, expected_hash, None, None, None, False)

    if span_start < 1 or span_end > len(lines) or span_start > span_end:
        return SourceHashGuardResult(False, SourceHashGuardErrorKind.SPAN_OUT_OF_RANGE, f"span {span_start}-{span_end} out of range (1-{len(lines)})", file_path, span_start, span_end, expected_hash, None, None, None, False)

    actual_hash = compute_span_hash(lines, span_start, span_end)
    if actual_hash != expected_hash:
        return SourceHashGuardResult(False, SourceHashGuardErrorKind.SOURCE_STALE, f"hash mismatch: expected {expected_hash}, got {actual_hash}", file_path, span_start, span_end, expected_hash, actual_hash, None, None, False)

    return SourceHashGuardResult(True, None, None, file_path, span_start, span_end, expected_hash, actual_hash, None, None, False)


def preview_line_span_replacement(file_path: str, span_start: int, span_end: int, replacement: str) -> SourceHashGuardResult:
    lines = _read_lines(file_path)
    if lines is None:
        return SourceHashGuardResult(False, SourceHashGuardErrorKind.FILE_NOT_FOUND, f"file not found: {file_path}", file_path, span_start, span_end, None, None, None, None, False)

    if span_start < 1 or span_end > len(lines) or span_start > span_end:
        return SourceHashGuardResult(False, SourceHashGuardErrorKind.SPAN_OUT_OF_RANGE, f"span {span_start}-{span_end} out of range", file_path, span_start, span_end, None, None, None, None, False)

    new_lines = lines[:span_start - 1] + [replacement] + lines[span_end:]
    new_content = "".join(new_lines)

    if file_path.endswith(".py"):
        try:
            ast.parse(new_content)
            ast_valid = True
        except SyntaxError:
            ast_valid = False
            return SourceHashGuardResult(False, SourceHashGuardErrorKind.AST_INVALID, "replacement produces invalid AST", file_path, span_start, span_end, None, None, False, _compute_hash(new_content), False)
    else:
        ast_valid = True

    return SourceHashGuardResult(True, None, None, file_path, span_start, span_end, None, None, ast_valid, _compute_hash(new_content), False)


def apply_line_span_replacement(file_path: str, span_start: int, span_end: int, expected_hash: str, replacement: str, write: bool = False) -> SourceHashGuardResult:
    lines = _read_lines(file_path)
    if lines is None:
        return SourceHashGuardResult(False, SourceHashGuardErrorKind.FILE_NOT_FOUND, f"file not found: {file_path}", file_path, span_start, span_end, expected_hash, None, None, None, False)

    if span_start < 1 or span_end > len(lines) or span_start > span_end:
        return SourceHashGuardResult(False, SourceHashGuardErrorKind.SPAN_OUT_OF_RANGE, f"span {span_start}-{span_end} out of range", file_path, span_start, span_end, expected_hash, None, None, None, False)

    actual_hash = compute_span_hash(lines, span_start, span_end)
    if actual_hash != expected_hash:
        return SourceHashGuardResult(False, SourceHashGuardErrorKind.SOURCE_STALE, f"hash mismatch", file_path, span_start, span_end, expected_hash, actual_hash, None, None, False)

    new_lines = lines[:span_start - 1] + [replacement] + lines[span_end:]
    new_content = "".join(new_lines)

    if file_path.endswith(".py"):
        try:
            ast.parse(new_content)
            ast_valid = True
        except SyntaxError:
            return SourceHashGuardResult(False, SourceHashGuardErrorKind.AST_INVALID, "replacement produces invalid AST", file_path, span_start, span_end, expected_hash, actual_hash, False, _compute_hash(new_content), False)
    else:
        ast_valid = True

    if not write:
        return SourceHashGuardResult(True, None, None, file_path, span_start, span_end, expected_hash, actual_hash, ast_valid, _compute_hash(new_content), False)

    try:
        Path(file_path).write_text(new_content)
        return SourceHashGuardResult(True, None, None, file_path, span_start, span_end, expected_hash, actual_hash, ast_valid, _compute_hash(new_content), True)
    except Exception as e:
        return SourceHashGuardResult(False, SourceHashGuardErrorKind.IO_ERROR, str(e), file_path, span_start, span_end, expected_hash, actual_hash, ast_valid, None, False)
