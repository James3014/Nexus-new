"""Parent-boundary preservation validation — S4.5"""

import re
from dataclasses import dataclass, field
from typing import List


@dataclass
class ParentBoundaryResult:
    parent_boundary_detected: bool
    parent_boundary_in_search: bool
    parent_signature_mutated: bool
    wrapper_added: bool
    duplicate_parent_detected: bool
    validation_errors: List[str] = field(default_factory=list)
    validation_warnings: List[str] = field(default_factory=list)
    m0_allowed: bool = True


def validate_parent_boundary(canonical_search: str, model_output: str,
                              source_file_content: str = "") -> ParentBoundaryResult:
    """Validate parent-boundary preservation."""

    errors = []
    warnings = []

    # Detect parent boundary lines
    parent_patterns = [
        (r'^(\s*def\s+\w+)', "function_signature"),
        (r'^(\s*class\s+\w+)', "class_declaration"),
        (r'^(\s*if\s+)', "if_header"),
        (r'^(\s*elif\s+)', "elif_header"),
        (r'^(\s*for\s+)', "for_header"),
        (r'^(\s*while\s+)', "while_header"),
    ]

    # Check canonical search for parent boundaries
    search_parent_lines = []
    for pattern, kind in parent_patterns:
        matches = re.findall(pattern, canonical_search, re.MULTILINE)
        if matches:
            search_parent_lines.extend([(m, kind) for m in matches])

    parent_in_search = len(search_parent_lines) > 0

    # Check model output for parent boundary mutations
    output_def_lines = re.findall(r'^(\s*def\s+\w+)', model_output, re.MULTILINE)
    output_class_lines = re.findall(r'^(\s*class\s+\w+)', model_output, re.MULTILINE)

    # Check if model changed def signature
    search_def_lines = re.findall(r'^(\s*def\s+\w+)', canonical_search, re.MULTILINE)
    signature_mutated = False
    if search_def_lines and output_def_lines:
        if set(output_def_lines) != set(search_def_lines):
            signature_mutated = True
            errors.append("parent_signature_mutated")

    # Check for wrapper additions
    wrapper_added = False
    if output_def_lines and not search_def_lines:
        wrapper_added = True
        errors.append("wrapper_added")

    # Check for duplicate parent
    duplicate = False
    if output_def_lines and search_def_lines:
        if len(output_def_lines) > len(search_def_lines):
            duplicate = True
            errors.append("duplicate_parent_detected")

    # If canonical SEARCH doesn't include parent, model output shouldn't either
    if not parent_in_search:
        if output_def_lines:
            errors.append("model_output_contains_def_not_in_search")
        if output_class_lines:
            errors.append("model_output_contains_class_not_in_search")

    return ParentBoundaryResult(
        parent_boundary_detected=len(search_parent_lines) > 0,
        parent_boundary_in_search=parent_in_search,
        parent_signature_mutated=signature_mutated,
        wrapper_added=wrapper_added,
        duplicate_parent_detected=duplicate,
        validation_errors=errors,
        validation_warnings=warnings,
        m0_allowed=len(errors) == 0,
    )
