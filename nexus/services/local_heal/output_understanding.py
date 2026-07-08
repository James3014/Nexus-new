from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class OutputFormat(str, Enum):
    SEARCH_REPLACE = "SEARCH_REPLACE"
    FENCED_SEARCH_REPLACE = "FENCED_SEARCH_REPLACE"
    UNIFIED_DIFF = "UNIFIED_DIFF"
    EMPTY_OR_REFUSAL = "EMPTY_OR_REFUSAL"
    MALFORMED_OUTPUT = "MALFORMED_OUTPUT"


@dataclass(frozen=True)
class CanonicalPatchCandidate:
    source_format: str
    raw_output: str
    raw_output_hash: str
    normalized_patch: str
    normalized_patch_hash: str
    normalization_steps: tuple[str, ...]
    safety_flags: tuple[str, ...]


@dataclass(frozen=True)
class OutputUnderstandingResult:
    success: bool
    candidate: CanonicalPatchCandidate | None
    detected_format: str
    failure_reason: str
    metadata: dict[str, Any] = field(default_factory=dict)


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _detect_format(raw: str) -> OutputFormat:
    if not raw or not raw.strip():
        return OutputFormat.EMPTY_OR_REFUSAL

    refusal_keywords = [
        "i apologize", "i cannot", "i'm sorry", "sorry",
        "as an ai", "unfortunately", "llm refused fix", "cannot fulfill",
    ]
    lower_raw = raw.lower()
    if any(kw in lower_raw for kw in refusal_keywords) and "<<<<<<< SEARCH" not in raw:
        return OutputFormat.EMPTY_OR_REFUSAL

    has_diff_headers = ("--- a/" in raw and "+++ b/" in raw)
    has_hunk = "@@ " in raw
    if has_diff_headers or (has_hunk and ("---" in raw or "+++" in raw)):
        return OutputFormat.UNIFIED_DIFF

    has_search = "<<<<<<< SEARCH" in raw
    has_replace = ">>>>>>> REPLACE" in raw
    if has_search and has_replace:
        if "```" in raw:
            return OutputFormat.FENCED_SEARCH_REPLACE
        return OutputFormat.SEARCH_REPLACE

    return OutputFormat.MALFORMED_OUTPUT


def _unwrap_fenced_search_replace(raw: str) -> tuple[str, list[str]]:
    steps: list[str] = []
    stripped = raw.strip()

    if not stripped.startswith("```"):
        return raw, steps

    lines = stripped.splitlines()
    if len(lines) < 3 or not lines[-1].strip().startswith("```"):
        return raw, steps

    inner = "\n".join(lines[1:-1]).strip()
    if "<<<<<<< SEARCH" in inner and ">>>>>>> REPLACE" in inner:
        steps.append("unwrap_outer_markdown_fence")
        return inner, steps

    return raw, steps


def _extract_replacement_from_search_replace(raw: str) -> tuple[str, list[str]]:
    steps: list[str] = []
    replace_pattern = r'<<<<<<< SEARCH\s*\n(.*?)\n=======\n(.*?)\n>>>>>>> REPLACE'
    import re
    match = re.search(replace_pattern, raw, re.DOTALL)
    if match:
        replacement = match.group(2).strip()
        steps.append("extract_replacement_from_search_replace")
        return replacement, steps
    return "", steps


def understand_output(raw_output: str) -> OutputUnderstandingResult:
    fmt = _detect_format(raw_output)

    if fmt == OutputFormat.EMPTY_OR_REFUSAL:
        return OutputUnderstandingResult(
            success=False,
            candidate=None,
            detected_format=fmt.value,
            failure_reason="empty_or_refusal",
        )

    if fmt == OutputFormat.MALFORMED_OUTPUT:
        return OutputUnderstandingResult(
            success=False,
            candidate=None,
            detected_format=fmt.value,
            failure_reason="malformed_output",
        )

    normalization_steps: list[str] = []
    safety_flags: list[str] = []
    normalized_patch = raw_output

    if fmt == OutputFormat.FENCED_SEARCH_REPLACE:
        unwrapped, steps = _unwrap_fenced_search_replace(raw_output)
        normalization_steps.extend(steps)
        normalized_patch = unwrapped

    if fmt in (OutputFormat.SEARCH_REPLACE, OutputFormat.FENCED_SEARCH_REPLACE):
        replacement, steps = _extract_replacement_from_search_replace(normalized_patch)
        normalization_steps.extend(steps)
        if replacement:
            normalized_patch = replacement
        else:
            return OutputUnderstandingResult(
                success=False,
                candidate=None,
                detected_format=fmt.value,
                failure_reason="search_replace_parse_failed",
            )

    raw_hash = _sha256(raw_output)
    normalized_hash = _sha256(normalized_patch) if normalized_patch != raw_output else ""

    candidate = CanonicalPatchCandidate(
        source_format=fmt.value,
        raw_output=raw_output,
        raw_output_hash=raw_hash,
        normalized_patch=normalized_patch,
        normalized_patch_hash=normalized_hash,
        normalization_steps=tuple(normalization_steps),
        safety_flags=tuple(safety_flags),
    )

    return OutputUnderstandingResult(
        success=True,
        candidate=candidate,
        detected_format=fmt.value,
        failure_reason="",
    )
