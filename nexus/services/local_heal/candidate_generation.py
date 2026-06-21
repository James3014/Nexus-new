"""P14: Candidate Generation Rework — Narrow-Span, ABSTAIN-Enabled

Reduces semantic burden on local model by generating smaller, safer,
leaf-level replacement candidates with explicit ABSTAIN support.
"""
from __future__ import annotations

import ast
import hashlib
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class ReplacementSpanKind(Enum):
    """Classification of replacement span size/type."""
    SINGLE_RETURN = "single_return"
    SINGLE_ASSIGNMENT = "single_assignment"
    ONE_IF_BRANCH = "one_if_branch"
    ONE_CALL_ARG_LIST = "one_call_arg_list"
    LOCALIZED_BLOCK = "localized_block"
    LEAF_METHOD_BODY = "leaf_method_body"
    BROAD_METHOD = "broad_method"  # rejected
    WHOLE_CLASS = "whole_class"  # rejected
    WHOLE_FILE = "whole_file"  # rejected


class CandidateParserStatus(Enum):
    ACCEPTED = "accepted"
    REJECTED_PROSE = "rejected_prose"
    REJECTED_MARKDOWN = "rejected_markdown"
    REJECTED_SYNTAX = "rejected_syntax"
    REJECTED_SCOPE = "rejected_scope"
    REJECTED_DUPLICATE = "rejected_duplicate"
    ABSTAIN = "abstain"
    EMPTY = "empty"


class CandidatePatchStatus(Enum):
    NOT_ATTEMPTED = "not_attempted"
    APPLIED = "applied"
    APPLY_FAILED = "apply_failed"
    VERIFIER_PASS = "verifier_pass"
    VERIFIER_FAIL = "verifier_fail"


@dataclass
class NarrowSpanCandidate:
    """A candidate from narrow-span generation."""
    candidate_id: str
    model: str
    prompt_variant: int
    replacement_span_kind: ReplacementSpanKind
    parser_status: CandidateParserStatus
    patch_status: CandidatePatchStatus
    compliance_status: str = "pending"
    failure_stage: str = ""
    selected: bool = False
    replacement_text: str = ""
    replacement_hash: str = ""
    anchor_id: str = ""
    span_lines: int = 0
    reasoning: str = ""  # advisory intent, not success


@dataclass
class CandidateGenerationResult:
    """Result of narrow-span candidate generation."""
    task_id: str
    model: str
    candidates: list[NarrowSpanCandidate]
    selected: NarrowSpanCandidate | None
    abstain_count: int
    parser_reject_count: int
    patch_apply_count: int
    verifier_pass_count: int
    total_candidates: int
    status: str


# ── ABSTAIN detection ────────────────────────────────────────────────────────
ABSTAIN_PATTERN = re.compile(r'^\s*ABSTAIN\s*$', re.IGNORECASE)


def is_abstain(response: str) -> bool:
    """Check if model response is exactly ABSTAIN."""
    return bool(ABSTAIN_PATTERN.match(response.strip()))


# ── Span classification ──────────────────────────────────────────────────────
def classify_replacement_span(replacement: str, anchor_text: str) -> ReplacementSpanKind:
    """Classify the replacement span type."""
    stripped = replacement.strip()
    lines = [l for l in stripped.splitlines() if l.strip()]

    if not lines:
        return ReplacementSpanKind.LOCALIZED_BLOCK

    # Single return expression
    if len(lines) == 1 and lines[0].strip().startswith("return"):
        return ReplacementSpanKind.SINGLE_RETURN

    # Single assignment
    if len(lines) == 1 and "=" in lines[0] and not lines[0].strip().startswith("return"):
        return ReplacementSpanKind.SINGLE_ASSIGNMENT

    # One if-branch body (check if anchor contains if/else)
    if "if " in anchor_text and len(lines) <= 6:
        return ReplacementSpanKind.ONE_IF_BRANCH

    # One function call argument list
    if len(lines) <= 3 and any("(" in l for l in lines):
        return ReplacementSpanKind.ONE_CALL_ARG_LIST

    # Localized block under 12 lines
    if len(lines) <= 12:
        return ReplacementSpanKind.LOCALIZED_BLOCK

    # Leaf method body (under 20 lines)
    if len(lines) <= 20 and any(kw in stripped for kw in ["def ", "return", "if ", "for "]):
        return ReplacementSpanKind.LEAF_METHOD_BODY

    # Broad method (rejected)
    return ReplacementSpanKind.BROAD_METHOD


def is_span_acceptable(kind: ReplacementSpanKind, *, strict_leaf: bool = False) -> bool:
    """Check if replacement span is acceptable."""
    if strict_leaf:
        return kind in {
            ReplacementSpanKind.SINGLE_RETURN,
            ReplacementSpanKind.SINGLE_ASSIGNMENT,
            ReplacementSpanKind.ONE_IF_BRANCH,
            ReplacementSpanKind.ONE_CALL_ARG_LIST,
            ReplacementSpanKind.LOCALIZED_BLOCK,
            ReplacementSpanKind.LEAF_METHOD_BODY,
        }
    return kind != ReplacementSpanKind.BROAD_METHOD


# ── Duplicate detection ──────────────────────────────────────────────────────
def is_duplicate(replacement: str, seen_hashes: set[str]) -> bool:
    """Check if replacement is a duplicate (normalized by whitespace)."""
    normalized = " ".join(replacement.strip().split())
    h = hashlib.sha256(normalized.encode()).hexdigest()[:16]
    if h in seen_hashes:
        return True
    seen_hashes.add(h)
    return False


# ── Narrow-span prompt builder ───────────────────────────────────────────────
def build_narrow_span_prompt(
    *,
    problem: str,
    anchor_text: str,
    anchor_intent: str,
    symbol: str,
    source_context: str,
    variant: int,
    retry_feedback: str = "",
    max_replacement_lines: int = 12,
) -> tuple[str, str]:
    """Build a prompt that encourages narrow, precise replacements."""
    system = (
        "You are fixing a Python bug with a MINIMAL, PRECISE change.\n\n"
        "RULES:\n"
        f"1. Output ONLY raw Python code (max {max_replacement_lines} lines)\n"
        "2. NEVER wrap in ```python ... ``` fences\n"
        "3. NEVER add explanation before/after code\n"
        "4. Preserve exact indentation from the anchor\n"
        "5. Change ONLY what is needed to fix the bug\n"
        "6. If you cannot fix with a small change, output: ABSTAIN\n\n"
        "REJECTED (will be discarded):\n"
        "- Markdown fences: ```python ... ```\n"
        "- Explanation: 'Here is the fix:'\n"
        "- Broad refactor touching many lines\n"
        "- Code unrelated to the bug\n\n"
        "ACCEPTED (will be used):\n"
        "- Raw Python code, 1-12 lines\n"
        "- Exact indentation match\n"
        "- Minimal change to fix the bug"
    )

    retry_section = ""
    if retry_feedback:
        retry_section = f"\n\nPREVIOUS REJECTED: {retry_feedback}\nOutput ONLY raw code or ABSTAIN.\n"

    user = (
        f"Bug: {problem[:300]}\n\n"
        f"Symbol: {symbol}\n"
        f"Fix intent: {anchor_intent}\n\n"
        f"Code to replace:\n{anchor_text}\n\n"
        f"Output ONLY the replacement code (max {max_replacement_lines} lines, raw Python, no markdown):{retry_section}"
    )
    return system, user


# ── Intent-first micro-plan ──────────────────────────────────────────────────
def build_intent_prompt(
    *,
    problem: str,
    anchor_text: str,
    symbol: str,
) -> tuple[str, str]:
    """Ask model for structured intent before replacement."""
    system = (
        "Analyze the bug and output a structured intent (no code).\n"
        "Format (max 5 lines):\n"
        "TARGET: what behavior to change\n"
        "EDIT_TYPE: return/assignment/if-branch/call-args/block\n"
        "SYMBOLS: list of symbols involved\n"
        "SPAN: estimated lines to change\n"
        "RISK: low/medium/high"
    )
    user = (
        f"Bug: {problem[:300]}\n"
        f"Symbol: {symbol}\n"
        f"Code: {anchor_text[:500]}\n\n"
        "Structured intent (no code):"
    )
    return system, user


# ── High-level API ───────────────────────────────────────────────────────────
def generate_narrow_span_candidates(
    *,
    task_id: str,
    model_name: str,
    problem: str,
    anchor_text: str,
    anchor_intent: str,
    symbol: str,
    source_context: str,
    generate_fn,  # callable(system, user, variant_id) -> str
    verify_fn=None,  # callable(replacement) -> (bool, str)
    max_candidates: int = 5,
    max_replacement_lines: int = 12,
    strict_leaf: bool = False,
) -> CandidateGenerationResult:
    """Generate narrow-span candidates with ABSTAIN support."""
    candidates = []
    seen_hashes = set()
    abstain_count = 0
    parser_reject_count = 0
    patch_apply_count = 0
    verifier_pass_count = 0

    for i in range(max_candidates):
        variant_id = f"narrow_v{i+1}"
        sys_prompt, usr_prompt = build_narrow_span_prompt(
            problem=problem,
            anchor_text=anchor_text,
            anchor_intent=anchor_intent,
            symbol=symbol,
            source_context=source_context,
            variant=i,
            max_replacement_lines=max_replacement_lines,
        )

        response = generate_fn(sys_prompt, usr_prompt, variant_id)

        if not response:
            candidates.append(NarrowSpanCandidate(
                candidate_id=variant_id,
                model=model_name,
                prompt_variant=i,
                replacement_span_kind=ReplacementSpanKind.LOCALIZED_BLOCK,
                parser_status=CandidateParserStatus.EMPTY,
                patch_status=CandidatePatchStatus.NOT_ATTEMPTED,
                failure_stage="empty_response",
            ))
            continue

        # Check ABSTAIN
        if is_abstain(response):
            abstain_count += 1
            candidates.append(NarrowSpanCandidate(
                candidate_id=variant_id,
                model=model_name,
                prompt_variant=i,
                replacement_span_kind=ReplacementSpanKind.LOCALIZED_BLOCK,
                parser_status=CandidateParserStatus.ABSTAIN,
                patch_status=CandidatePatchStatus.NOT_ATTEMPTED,
                failure_stage="model_abstained",
            ))
            continue

        # Classify span
        span_kind = classify_replacement_span(response, anchor_text)

        # Check span acceptability
        if not is_span_acceptable(span_kind, strict_leaf=strict_leaf):
            candidates.append(NarrowSpanCandidate(
                candidate_id=variant_id,
                model=model_name,
                prompt_variant=i,
                replacement_span_kind=span_kind,
                parser_status=CandidateParserStatus.REJECTED_SCOPE,
                patch_status=CandidatePatchStatus.NOT_ATTEMPTED,
                failure_stage=f"span_rejected:{span_kind.value}",
            ))
            continue

        # Check duplicate
        if is_duplicate(response, seen_hashes):
            candidates.append(NarrowSpanCandidate(
                candidate_id=variant_id,
                model=model_name,
                prompt_variant=i,
                replacement_span_kind=span_kind,
                parser_status=CandidateParserStatus.REJECTED_DUPLICATE,
                patch_status=CandidatePatchStatus.NOT_ATTEMPTED,
                failure_stage="duplicate_replacement",
            ))
            continue

        # Check prose/markdown
        if response.strip().startswith("```"):
            candidates.append(NarrowSpanCandidate(
                candidate_id=variant_id,
                model=model_name,
                prompt_variant=i,
                replacement_span_kind=span_kind,
                parser_status=CandidateParserStatus.REJECTED_MARKDOWN,
                patch_status=CandidatePatchStatus.NOT_ATTEMPTED,
                failure_stage="markdown_fence",
            ))
            parser_reject_count += 1
            continue

        # Check prose patterns
        prose_patterns = [
            re.compile(r'(?i)^(here|this|the|note|see|consider|we|you|fix|patch)\b'),
        ]
        first_line = response.strip().splitlines()[0] if response.strip() else ""
        if any(p.match(first_line) for p in prose_patterns):
            candidates.append(NarrowSpanCandidate(
                candidate_id=variant_id,
                model=model_name,
                prompt_variant=i,
                replacement_span_kind=span_kind,
                parser_status=CandidateParserStatus.REJECTED_PROSE,
                patch_status=CandidatePatchStatus.NOT_ATTEMPTED,
                failure_stage="prose_contamination",
            ))
            parser_reject_count += 1
            continue

        # Accept candidate
        rep_hash = hashlib.sha256(response.strip().encode()).hexdigest()[:16]
        candidates.append(NarrowSpanCandidate(
            candidate_id=variant_id,
            model=model_name,
            prompt_variant=i,
            replacement_span_kind=span_kind,
            parser_status=CandidateParserStatus.ACCEPTED,
            patch_status=CandidatePatchStatus.APPLIED,
            replacement_text=response,
            replacement_hash=rep_hash,
            span_lines=len([l for l in response.strip().splitlines() if l.strip()]),
        ))
        patch_apply_count += 1

        # Run verifier if provided
        if verify_fn:
            ok, log = verify_fn(response)
            if ok:
                candidates[-1].patch_status = CandidatePatchStatus.VERIFIER_PASS
                candidates[-1].selected = True
                verifier_pass_count += 1
                break
            else:
                candidates[-1].patch_status = CandidatePatchStatus.VERIFIER_FAIL
                candidates[-1].failure_stage = f"verifier_fail:{log[:100]}"

    # Determine status
    selected = next((c for c in candidates if c.selected), None)
    if selected:
        status = "P14_VERIFIER_PASS_INTERNAL_ONLY"
    elif abstain_count == len(candidates):
        status = "P14_MODEL_ABSTAINED_ALL"
    elif patch_apply_count == 0:
        status = "P14_PARSER_REJECTED_ALL"
    elif verifier_pass_count == 0:
        status = "P14_PATCH_APPLIED_VERIFIER_FAILED"
    else:
        status = "P14_SEMANTIC_FAILURE"

    return CandidateGenerationResult(
        task_id=task_id,
        model=model_name,
        candidates=candidates,
        selected=selected,
        abstain_count=abstain_count,
        parser_reject_count=parser_reject_count,
        patch_apply_count=patch_apply_count,
        verifier_pass_count=verifier_pass_count,
        total_candidates=len(candidates),
        status=status,
    )
