"""T1.6/T1.8: Canonical search span extraction with hybrid strategy.

Strategy order:
  a. locked previous canonical SEARCH
  b. unified diff extraction
  c. AST symbol boundary fallback
  d. line/traceback window fallback

Records canonical_span_source to track which strategy was used.
"""

import ast
import re
import difflib
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class CanonicalSpanResult:
    """Result of canonical span extraction."""
    span: str
    source: str  # "locked_search" | "unified_diff" | "ast_boundary" | "traceback_window"
    file_path: str = ""
    start_line: int = 0
    end_line: int = 0
    confidence: float = 1.0
    telemetry: dict = field(default_factory=dict)


def get_canonical_search_span(
    *,
    locked_search: str = "",
    patch_diff: str = "",
    source_file: Path | None = None,
    target_symbol: str = "",
    failed_search_text: str = "",
    traceback_lines: list[str] | None = None,
) -> Optional[CanonicalSpanResult]:
    """Extract canonical SEARCH span using hybrid strategy.

    Strategy order:
      a. locked_search — previous canonical SEARCH (highest confidence)
      b. unified_diff — extract from last applied patch diff
      c. ast_boundary — AST-based symbol extraction from source file
      d. traceback_window — extract from traceback/stack trace lines

    Returns CanonicalSpanResult or None if all strategies fail.
    """
    telemetry = {"strategies_tried": []}

    # Strategy a: locked previous canonical SEARCH
    if locked_search and locked_search.strip():
        telemetry["strategies_tried"].append({"strategy": "locked_search", "found": True})
        return CanonicalSpanResult(
            span=locked_search.strip(),
            source="locked_search",
            confidence=1.0,
            telemetry=telemetry,
        )

    # Strategy b: unified diff extraction
    diff_result = _extract_from_unified_diff(patch_diff)
    if diff_result:
        telemetry["strategies_tried"].append({"strategy": "unified_diff", "found": True})
        diff_result.telemetry = telemetry
        return diff_result
    telemetry["strategies_tried"].append({"strategy": "unified_diff", "found": False})

    # Strategy c: AST symbol boundary fallback
    if source_file and source_file.exists() and target_symbol:
        ast_result = _extract_by_ast_boundary(source_file, target_symbol)
        if ast_result:
            telemetry["strategies_tried"].append({"strategy": "ast_boundary", "found": True})
            ast_result.telemetry = telemetry
            return ast_result
        telemetry["strategies_tried"].append({"strategy": "ast_boundary", "found": False})

    # Strategy d: traceback window fallback
    if traceback_lines and failed_search_text:
        tb_result = _extract_from_traceback_window(traceback_lines, failed_search_text, source_file)
        if tb_result:
            telemetry["strategies_tried"].append({"strategy": "traceback_window", "found": True})
            tb_result.telemetry = telemetry
            return tb_result
        telemetry["strategies_tried"].append({"strategy": "traceback_window", "found": False})

    return None


def _extract_from_unified_diff(patch_diff: str) -> Optional[CanonicalSpanResult]:
    """Extract SEARCH block from unified diff (lines prefixed with -)."""
    if not patch_diff:
        return None

    lines = patch_diff.splitlines()
    search_lines = []
    target_file = ""

    for line in lines:
        if line.startswith("+++ b/"):
            target_file = line[6:]
        elif line.startswith("-") and not line.startswith("---"):
            search_lines.append(line[1:])
        elif line.startswith("+") or line.startswith("@@"):
            if search_lines:
                break

    if not search_lines:
        return None

    span = "\n".join(search_lines)
    return CanonicalSpanResult(
        span=span,
        source="unified_diff",
        file_path=target_file,
        confidence=0.9,
    )


def _extract_by_ast_boundary(source_file: Path, target_symbol: str) -> Optional[CanonicalSpanResult]:
    """Extract code block by AST symbol boundary.

    Uses Python ast module to parse the source file and find the exact
    AST node for the target symbol, then extracts the full block.
    """
    try:
        source_text = source_file.read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(source_text)
    except (SyntaxError, OSError):
        return None

    lines = source_text.splitlines()

    # Find the AST node for the target symbol
    for node in ast.walk(tree):
        node_name = getattr(node, "name", None)
        if node_name != target_symbol:
            continue

        # Get the full block (including decorators, docstring, etc.)
        start_line = getattr(node, "lineno", 0)
        end_line = getattr(node, "end_lineno", start_line)

        # Extend to include decorators
        if hasattr(node, "decorator_list") and node.decorator_list:
            first_decorator = node.decorator_list[0]
            if hasattr(first_decorator, "lineno"):
                start_line = first_decorator.lineno

        # Extend to include docstring at the top
        # Docstring is already included in the node range from ast

        # Extract the block
        if start_line > 0 and end_line <= len(lines):
            block_lines = lines[start_line - 1:end_line]
            span = "\n".join(block_lines)

            # Verify the span is a valid substring of the source
            if span in source_text:
                return CanonicalSpanResult(
                    span=span,
                    source="ast_boundary",
                    file_path=str(source_file),
                    start_line=start_line,
                    end_line=end_line,
                    confidence=0.8,
                )

    # Fallback: search for the symbol as a class/function definition
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith(f"def {target_symbol}(") or stripped.startswith(f"class {target_symbol}"):
            # Found definition — extract the block
            start_line = i + 1
            base_indent = len(line) - len(line.lstrip())
            end_line = start_line

            # Find the end of the block (next dedent or blank line)
            for j in range(i + 1, len(lines)):
                next_line = lines[j]
                if not next_line.strip():
                    end_line = j + 1
                    break
                next_indent = len(next_line) - len(next_line.lstrip())
                if next_indent <= base_indent and next_line.strip():
                    end_line = j
                    break
                end_line = j + 1

            block_lines = lines[start_line - 1:end_line]
            span = "\n".join(block_lines)

            if span in source_text:
                return CanonicalSpanResult(
                    span=span,
                    source="ast_boundary",
                    file_path=str(source_file),
                    start_line=start_line,
                    end_line=end_line,
                    confidence=0.7,
                )

    return None


def _extract_from_traceback_window(
    traceback_lines: list[str],
    failed_search_text: str,
    source_file: Path | None = None,
) -> Optional[CanonicalSpanResult]:
    """Extract canonical span from traceback window.

    Parses traceback to find file:line references, then extracts
    a window of code around the referenced line.
    """
    if not traceback_lines or not source_file or not source_file.exists():
        return None

    try:
        source_text = source_file.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None

    lines = source_text.splitlines()

    # Parse traceback for file:line references
    for tb_line in traceback_lines:
        match = re.search(r'File "([^"]+)", line (\d+)', tb_line)
        if not match:
            continue

        tb_file = match.group(1)
        tb_line_num = int(match.group(2))

        # Check if this file matches our target
        if source_file.name not in tb_file:
            continue

        # Extract window around the referenced line
        start = max(0, tb_line_num - 5)
        end = min(len(lines), tb_line_num + 5)

        # Try to extend to natural boundaries
        while start > 0 and lines[start - 1].strip():
            start -= 1
        while end < len(lines) and lines[end].strip():
            end += 1

        candidate = "\n".join(lines[start:end])
        if candidate in source_text:
            return CanonicalSpanResult(
                span=candidate,
                source="traceback_window",
                file_path=str(source_file),
                start_line=start + 1,
                end_line=end,
                confidence=0.6,
            )

    return None
