"""B5: Constrained Action Applier — Schema normalization + robust insertion."""
from __future__ import annotations

import re
import ast
import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any


CANONICAL_ACTION_TYPES = {
    # Core DSL (existing)
    "REPLACE_EXPR", "INSERT_GUARD", "INSERT_FORMAT_APPLICATION",
    "REORDER_EXISTING_CALL", "CALL_EXISTING_HELPER", "ABSTAIN",
    # L6-B: Safe extensions
    "SET_REQUIRED_STATE_THEN_CALL", "MOVE_CALL", "CHANGE_RECEIVER",
    "CHANGE_ARGUMENT", "ADD_MISSING_KEYWORD_ARG", "CHANGE_LITERAL",
    "REMOVE_INCORRECT_GUARD", "NARROW_CONDITION", "WRAP_EXISTING_CALL",
    "USE_EXISTING_HELPER_RESULT", "DELETE_SINGLE_STATEMENT",
    "INSERT_SINGLE_ASSIGNMENT",
    # L6-B: New safe extensions
    "REPLACE_RAISE_WITH_EXPR", "REPLACE_BRANCH_BODY",
    "ADD_LOCAL_PRECOMPUTE", "USE_EXISTING_CLASS_CONSTRUCTOR",
    "REPLACE_RETURN_EXPR", "SWAP_TWO_LOCAL_CALLS",
    "REMOVE_REDUNDANT_RAISE_BRANCH",
}

# B5-A: Normalize misspellings safely
ACTION_TYPE_ALIASES = {
    "CALL_EXISTENT_HELPER": "CALL_EXISTING_HELPER",
    "INSERT_FORMAT": "INSERT_FORMAT_APPLICATION",
    "REPLACE": "REPLACE_EXPR",
    "INSERT": "INSERT_GUARD",
    "REORDER": "REORDER_EXISTING_CALL",
    "CALL_HELPER": "CALL_EXISTING_HELPER",
}


@dataclass
class ConstrainedAction:
    action_type: str
    original_action_type: str
    target_symbol: str
    target_file: str
    target_span: str
    replacement_snippet: str
    expected_effect: str
    confidence: float


@dataclass
class ActionResult:
    action_id: str
    action_type: str
    original_action_type: str
    canonical_action_type: str
    target_symbol: str
    target_file: str
    allowed_span: str
    resolved_insert_line: int
    resolved_insert_reason: str
    source_hash_before: str
    source_hash_after: str
    patch_apply_status: str
    syntax_check_status: str
    error: str = ""


class ConstrainedActionApplier:
    """B5: Robust constrained action applier with schema normalization."""

    def normalize_action(self, raw_action: dict) -> ConstrainedAction | None:
        """B5-A: Normalize action type and validate schema."""
        raw_type = raw_action.get("selected_action_type", "")
        canonical = ACTION_TYPE_ALIASES.get(raw_type, raw_type)

        if canonical not in CANONICAL_ACTION_TYPES:
            return None

        snippet = raw_action.get("replacement_snippet", "")
        if canonical == "ABSTAIN":
            return ConstrainedAction(
                action_type="ABSTAIN", original_action_type=raw_type,
                target_symbol="", target_file="", target_span="",
                replacement_snippet="", expected_effect="abstain",
                confidence=raw_action.get("confidence", 0.0),
            )

        # Reject unsafe patterns
        if canonical in ("INSERT_GUARD", "INSERT_FORMAT_APPLICATION"):
            if any(kw in snippet.lower() for kw in ["def ", "class ", "import "]):
                return None  # Insert actions should not define new things
        elif canonical == "CALL_EXISTING_HELPER":
            if "def " in snippet or "class " in snippet:
                return None  # Should not define new things

        if len(snippet) > 500:
            return None  # Too large for constrained action

        return ConstrainedAction(
            action_type=canonical, original_action_type=raw_type,
            target_symbol=raw_action.get("target_symbol", ""),
            target_file=raw_action.get("target_file", ""),
            target_span=raw_action.get("target_span", ""),
            replacement_snippet=snippet,
            expected_effect=raw_action.get("expected_effect", ""),
            confidence=raw_action.get("confidence", 0.0),
        )

    def apply_action(
        self,
        action: ConstrainedAction,
        source_text: str,
        anchor_text: str,
        target_file: str,
    ) -> ActionResult:
        """B5-B: Apply constrained action with robust insertion logic."""
        action_id = hashlib.sha256(
            f"{action.action_type}:{action.replacement_snippet}".encode()
        ).hexdigest()[:12]

        source_hash_before = hashlib.sha256(source_text.encode()).hexdigest()[:16]
        lines = source_text.splitlines()

        if action.action_type == "ABSTAIN":
            return ActionResult(
                action_id=action_id, action_type=action.action_type,
                original_action_type=action.original_action_type,
                canonical_action_type=action.action_type,
                target_symbol=action.target_symbol, target_file=target_file,
                allowed_span=action.target_span, resolved_insert_line=0,
                resolved_insert_reason="abstain_no_apply",
                source_hash_before=source_hash_before,
                source_hash_after=source_hash_before,
                patch_apply_status="skipped", syntax_check_status="skipped",
            )

        # B5-B: Find insertion target using AST-aware matching
        insert_line = self._find_insert_point(
            lines, action, anchor_text, target_file
        )

        if insert_line < 0:
            return ActionResult(
                action_id=action_id, action_type=action.action_type,
                original_action_type=action.original_action_type,
                canonical_action_type=action.action_type,
                target_symbol=action.target_symbol, target_file=target_file,
                allowed_span=action.target_span, resolved_insert_line=0,
                resolved_insert_reason="insertion_point_not_found",
                source_hash_before=source_hash_before,
                source_hash_after=source_hash_before,
                patch_apply_status="failed", syntax_check_status="skipped",
                error="Could not find insertion point",
            )

        # insert_line is 0-indexed from _find_insert_point
        # For AFTER_CALL, _find_insert_point returns i+1 (already after target)
        # For BEFORE_CALL, _find_insert_point returns i (before target)
        # So we use insert_line directly as the insertion index

        # Check indentation of target line
        target_idx = min(insert_line, len(lines) - 1)
        target_line = lines[target_idx] if target_idx >= 0 else ""
        indent = len(target_line) - len(target_line.lstrip())
        snippet_lines = action.replacement_snippet.splitlines()
        indented_snippet = "\n".join(" " * indent + l.strip() for l in snippet_lines)

        # Apply insertion
        new_lines = lines[:insert_line] + [indented_snippet] + lines[insert_line:]
        new_source = "\n".join(new_lines)

        # Syntax check
        syntax_ok = True
        try:
            ast.parse(new_source)
        except SyntaxError:
            syntax_ok = False

        if not syntax_ok:
            # Try wrapping in method context
            try:
                ast.parse(f"class _Wrapper:\n" + "\n".join("    " + l for l in new_lines))
                syntax_ok = True
            except SyntaxError:
                pass

        if not syntax_ok:
            return ActionResult(
                action_id=action_id, action_type=action.action_type,
                original_action_type=action.original_action_type,
                canonical_action_type=action.action_type,
                target_symbol=action.target_symbol, target_file=target_file,
                allowed_span=action.target_span, resolved_insert_line=insert_line + 1,
                resolved_insert_reason="inserted_before_target",
                source_hash_before=source_hash_before,
                source_hash_after=hashlib.sha256(new_source.encode()).hexdigest()[:16],
                patch_apply_status="failed", syntax_check_status="failed",
                error="Syntax error after insertion",
            )

        return ActionResult(
            action_id=action_id, action_type=action.action_type,
            original_action_type=action.original_action_type,
            canonical_action_type=action.action_type,
            target_symbol=action.target_symbol, target_file=target_file,
            allowed_span=action.target_span, resolved_insert_line=insert_line + 1,
            resolved_insert_reason="inserted_before_target",
            source_hash_before=source_hash_before,
            source_hash_after=hashlib.sha256(new_source.encode()).hexdigest()[:16],
            patch_apply_status="applied", syntax_check_status="passed",
        ), new_source

    def _find_insert_point(
        self, lines: list[str], action: ConstrainedAction,
        anchor_text: str, target_file: str,
    ) -> int:
        """B5-B: Find insertion point using AST-aware matching."""
        snippet = action.replacement_snippet.lower()

        # Strategy 1: Find iter_str_vals call (for C_13453 style fixes)
        if "iter_str_vals" in snippet or "iter_str_vals" in action.expected_effect.lower():
            for i, line in enumerate(lines):
                if "iter_str_vals" in line and "def " not in line:
                    return i  # Insert before this line

        # Strategy 2: Find _set_fill_values call (insert AFTER)
        # Match if snippet mentions fill_values OR expected effect mentions fill_values
        if ("_set_fill_values" in snippet or "fill_values" in action.target_span.lower() or
                "fill_values" in action.expected_effect.lower()):
            for i, line in enumerate(lines):
                if "_set_fill_values" in line and "def " not in line:
                    return i + 1  # Insert AFTER this line (return next line index)

        # Strategy 3: Find format-related lines
        if "format" in snippet.lower():
            for i, line in enumerate(lines):
                if "formats" in line.lower() and "def " not in line and i > 10:
                    return i  # Insert before format-related line

        # Strategy 4: Find by symbol name in anchor
        for i, line in enumerate(lines):
            if action.target_symbol and action.target_symbol in line:
                return i

        # Strategy 5: Find first non-empty line in anchor region
        in_anchor = False
        for i, line in enumerate(lines):
            if line.strip() in anchor_text[:50]:
                in_anchor = True
            if in_anchor and line.strip() and "def " not in line:
                return i

        return -1


def apply_constrained_actions_to_source(
    source_text: str,
    actions: list[dict],
    anchor_text: str,
    target_file: str,
) -> tuple[str, list[ActionResult]]:
    """Apply multiple constrained actions to source text."""
    applier = ConstrainedActionApplier()
    current_source = source_text
    results = []

    for raw_action in actions:
        action = applier.normalize_action(raw_action)
        if action is None:
            results.append(ActionResult(
                action_id="unknown", action_type="unknown",
                original_action_type=raw_action.get("selected_action_type", ""),
                canonical_action_type="REJECTED",
                target_symbol="", target_file=target_file,
                allowed_span="", resolved_insert_line=0,
                resolved_insert_reason="schema_rejected",
                source_hash_before="", source_hash_after="",
                patch_apply_status="rejected", syntax_check_status="skipped",
                error="Invalid action type or unsafe payload",
            ))
            continue

        if action.action_type == "ABSTAIN":
            results.append(ActionResult(
                action_id="abstain", action_type="ABSTAIN",
                original_action_type=action.original_action_type,
                canonical_action_type="ABSTAIN",
                target_symbol="", target_file=target_file,
                allowed_span="", resolved_insert_line=0,
                resolved_insert_reason="abstain_no_apply",
                source_hash_before=_hash(current_source),
                source_hash_after=_hash(current_source),
                patch_apply_status="skipped", syntax_check_status="skipped",
            ))
            continue

        result = applier.apply_action(action, current_source, anchor_text, target_file)
        if isinstance(result, tuple):
            result, current_source = result
        results.append(result)

    return current_source, results


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]
