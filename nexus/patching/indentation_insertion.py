"""Indentation-aware line insertion detection — S4.6"""

import re
from dataclasses import dataclass
from typing import Optional


@dataclass
class IndentationInsertionResult:
    insertion_shape: str
    insertion_shape_confidence: float
    base_indent: int
    child_indent: int
    indent_unit: int
    anchor_line: str
    m0_allowed: bool
    block_reason: str = ""


def detect_indentation_intent(canonical_search: str, source_context: str = "",
                               parent_in_search: bool = True) -> IndentationInsertionResult:
    """Detect indentation insertion intent from canonical search."""

    lines = canonical_search.split('\n')
    non_empty = [l for l in lines if l.strip()]

    if not non_empty:
        return IndentationInsertionResult("unsupported", 0.0, 0, 0, 4, "", False, "empty canonical search")

    # Detect indent unit from source
    indent_unit = 4
    for line in non_empty:
        stripped = line.lstrip()
        indent = len(line) - len(stripped)
        if indent > 0:
            # Check if source uses 2 or 4 space indent
            if source_context:
                source_lines = source_context.split('\n')
                for sl in source_lines:
                    if sl.strip() and sl != sl.lstrip():
                        source_indent = len(sl) - len(sl.lstrip())
                        if source_indent > 0:
                            indent_unit = source_indent
                            break
            break

    # Base indent from first canonical line
    first_line = non_empty[0]
    base_indent = len(first_line) - len(first_line.lstrip())

    # Child indent
    child_indent = base_indent + indent_unit

    # Detect insertion shape
    if len(non_empty) == 1:
        shape = "replace_existing_line"
        confidence = 0.9
    elif len(non_empty) <= 5:
        shape = "replace_existing_block"
        confidence = 0.8
    elif "pass" in canonical_search.lower() or "..." in canonical_search:
        shape = "replace_placeholder_body"
        confidence = 0.7
    else:
        shape = "insert_child_lines_after_anchor"
        confidence = 0.6

    return IndentationInsertionResult(
        insertion_shape=shape,
        insertion_shape_confidence=confidence,
        base_indent=base_indent,
        child_indent=child_indent,
        indent_unit=indent_unit,
        anchor_line=non_empty[0].strip(),
        m0_allowed=True,
    )
