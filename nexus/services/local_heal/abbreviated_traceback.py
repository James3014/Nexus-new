"""Abbreviated traceback formatter for verifier-guided retry."""

import re
from dataclasses import dataclass
from enum import Enum
from typing import Optional


class AbbreviatedTracebackErrorKind(Enum):
    EMPTY_TRACEBACK = "EMPTY_TRACEBACK"
    INVALID_FAILURE_CLASS = "INVALID_FAILURE_CLASS"


@dataclass
class AbbreviatedTraceback:
    error_type: str
    message: str
    minimized_stack: str
    target_file: Optional[str]
    target_lines: Optional[list[str]]
    assertion_diff: Optional[str]
    recent_patch_diff: Optional[str]
    verifier_verdict: str
    failure_class: str
    truncated: bool
    char_count: int


def _extract_error_type(traceback: str) -> str:
    for line in traceback.splitlines():
        line = line.strip()
        for pattern in [r"(\w+Error):", r"(\w+Exception):", r"(AssertionError):", r"(FAILED)"]:
            m = re.search(pattern, line)
            if m:
                return m.group(1)
    return "UnknownError"


def _extract_message(traceback: str) -> str:
    for line in traceback.splitlines():
        line = line.strip()
        m = re.search(r"(?:Error|Exception|FAILED):\s*(.+)", line)
        if m:
            return m.group(1)[:200]
    return traceback.splitlines()[0][:200] if traceback.splitlines() else "unknown"


def _extract_target_file(traceback: str) -> Optional[str]:
    for line in traceback.splitlines():
        m = re.search(r'File "([^"]+\.py)"', line)
        if m:
            return m.group(1)
    return None


def _extract_assertion_diff(traceback: str) -> Optional[str]:
    lines = traceback.splitlines()
    diff_lines = []
    capture = False
    for line in lines:
        if "AssertionError" in line or "assert" in line.lower():
            capture = True
        if capture:
            diff_lines.append(line)
            if len(diff_lines) > 5:
                break
    return "\n".join(diff_lines) if diff_lines else None


def _minimize_stack(traceback: str) -> str:
    lines = traceback.splitlines()
    minimized = []
    skip_long = False
    for line in lines:
        if "site-packages" in line or "venv" in line:
            skip_long = True
            continue
        if skip_long and line.startswith(" "):
            continue
        skip_long = False
        minimized.append(line)
    return "\n".join(minimized[:30])


def format_abbreviated_traceback(
    full_traceback: str,
    failure_class: str,
    target_file: Optional[str] = None,
    target_lines: Optional[list[str]] = None,
    recent_patch_diff: Optional[str] = None,
    max_chars: int = 1800,
) -> AbbreviatedTraceback:
    if not full_traceback.strip():
        return AbbreviatedTraceback(
            error_type="EmptyTraceback",
            message="empty traceback provided",
            minimized_stack="",
            target_file=target_file,
            target_lines=target_lines,
            assertion_diff=None,
            recent_patch_diff=recent_patch_diff,
            verifier_verdict="UNKNOWN",
            failure_class=failure_class,
            truncated=False,
            char_count=0,
        )

    error_type = _extract_error_type(full_traceback)
    message = _extract_message(full_traceback)
    minimized = _minimize_stack(full_traceback)
    extracted_target = _extract_target_file(full_traceback) or target_file
    assertion_diff = _extract_assertion_diff(full_traceback)

    parts = [f"Error: {error_type}", f"Message: {message}", f"Stack: {minimized}"]
    if extracted_target:
        parts.append(f"Target: {extracted_target}")
    if assertion_diff:
        parts.append(f"Diff: {assertion_diff}")
    if recent_patch_diff:
        parts.append(f"Patch: {recent_patch_diff}")

    combined = "\n".join(parts)
    truncated = len(combined) > max_chars
    if truncated:
        combined = combined[:max_chars]
        combined += "\n... (truncated)"

    return AbbreviatedTraceback(
        error_type=error_type,
        message=message,
        minimized_stack=minimized,
        target_file=extracted_target,
        target_lines=target_lines,
        assertion_diff=assertion_diff,
        recent_patch_diff=recent_patch_diff,
        verifier_verdict="VERIFIER_REJECTED" if failure_class != "verified_solve" else "VERIFIED_SOLVE",
        failure_class=failure_class,
        truncated=truncated,
        char_count=len(combined),
    )
