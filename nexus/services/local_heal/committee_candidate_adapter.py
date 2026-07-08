from __future__ import annotations

import hashlib
from typing import Any

from nexus.services.local_heal.output_understanding import (
    CanonicalPatchCandidate,
    OutputFormat,
    understand_output,
)


def adapt_committee_candidate(
    raw_candidate: dict[str, Any],
    target_file: str,
    target_symbol: str = "",
) -> tuple[CanonicalPatchCandidate | None, list[str]]:
    """Convert a raw committee candidate dict to CanonicalPatchCandidate.

    Returns (candidate, [warnings]) or (None, [errors]) on failure.
    """
    warnings = []
    errors = []

    # Extract fields from raw candidate
    candidate_patch = str(raw_candidate.get("candidate_patch", "") or "")
    raw_text = str(raw_candidate.get("raw_text", "") or raw_candidate.get("output", "") or "")
    source_format = str(raw_candidate.get("format", "") or raw_candidate.get("source_format", "") or "")
    model_name = str(raw_candidate.get("model", "") or raw_candidate.get("model_name", "") or "")
    candidate_id = str(raw_candidate.get("candidate_id", "") or "")

    # Use candidate_patch if available, else try raw_text
    patch_content = candidate_patch if candidate_patch.strip() else raw_text

    # Empty check
    if not patch_content.strip():
        errors.append("empty_candidate")
        return None, errors

    # Refusal check
    refusal_keywords = ["i apologize", "i cannot", "i'm sorry", "sorry", "as an ai", "unfortunately"]
    lower_patch = patch_content.lower()
    if any(kw in lower_patch for kw in refusal_keywords) and "<<<<<<< SEARCH" not in patch_content:
        errors.append("refusal_detected")
        return None, errors

    # Determine source format
    if not source_format:
        understanding = understand_output(patch_content)
        if understanding.success and understanding.candidate:
            source_format = understanding.candidate.source_format
        else:
            # Try to detect from content
            if "--- a/" in patch_content and "+++ b/" in patch_content:
                source_format = "UNIFIED_DIFF"
            elif "<<<<<<< SEARCH" in patch_content and ">>>>>>> REPLACE" in patch_content:
                source_format = "SEARCH_REPLACE"
            else:
                errors.append("unknown_format")
                return None, errors

    # Build normalized patch
    if source_format == "SEARCH_REPLACE":
        # Extract replacement from SEARCH/REPLACE block
        import re
        match = re.search(r'<<<<<<< SEARCH\s*\n.*?\n=======\n(.*?)\n>>>>>>> REPLACE', patch_content, re.DOTALL)
        if match:
            normalized_patch = match.group(1).strip()
        else:
            normalized_patch = patch_content
    elif source_format == "UNIFIED_DIFF":
        normalized_patch = patch_content
    else:
        normalized_patch = patch_content

    # Compute hashes
    raw_hash = hashlib.sha256(patch_content.encode("utf-8")).hexdigest()
    normalized_hash = hashlib.sha256(normalized_patch.encode("utf-8")).hexdigest() if normalized_patch != patch_content else ""

    # Safety flags
    safety_flags = []
    if target_file and target_file not in patch_content:
        warnings.append("target_file_not_in_patch")
        safety_flags.append("target_file_mismatch")

    # Build candidate
    candidate = CanonicalPatchCandidate(
        source_format=source_format,
        raw_output=patch_content,
        raw_output_hash=raw_hash,
        normalized_patch=normalized_patch,
        normalized_patch_hash=normalized_hash,
        normalization_steps=("adapt_committee_candidate",),
        safety_flags=tuple(safety_flags),
        target_file=target_file,
        target_symbol=target_symbol,
        line_span="",
        old_block_hash="",
    )

    return candidate, warnings


def adapt_committee_candidates(
    raw_candidates: list[dict[str, Any]],
    target_file: str,
    target_symbol: str = "",
) -> tuple[list[CanonicalPatchCandidate], list[dict]]:
    """Batch adapt. Returns (valid_candidates, rejection_details)."""
    valid = []
    rejections = []

    for idx, raw in enumerate(raw_candidates):
        candidate, issues = adapt_committee_candidate(raw, target_file, target_symbol)
        if candidate is not None:
            valid.append(candidate)
        else:
            rejections.append({
                "index": idx,
                "reason": issues[0] if issues else "unknown",
                "details": issues,
                "candidate_id": raw.get("candidate_id", f"candidate_{idx}"),
            })

    return valid, rejections
