from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class OutputFormat(str, Enum):
    SEARCH_REPLACE = "SEARCH_REPLACE"
    FENCED_SEARCH_REPLACE = "FENCED_SEARCH_REPLACE"
    UNIFIED_DIFF = "UNIFIED_DIFF"
    PARTIAL_DIFF = "PARTIAL_DIFF"
    LINE_SPAN_EDIT = "LINE_SPAN_EDIT"
    FUNCTION_REPLACEMENT = "FUNCTION_REPLACEMENT"
    NATURAL_LANGUAGE_REPAIR_INTENT = "NATURAL_LANGUAGE_REPAIR_INTENT"
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
    # P2-1: Anchor fields
    target_file: str = ""
    target_symbol: str = ""
    line_span: str = ""
    old_block_hash: str = ""
    # P2: Applied patch hash for hash chain completeness
    applied_patch_hash: str = ""
    claim_eligible: bool = True


@dataclass(frozen=True)
class OutputUnderstandingResult:
    success: bool
    candidate: CanonicalPatchCandidate | None
    detected_format: str
    failure_reason: str
    metadata: dict[str, Any] = field(default_factory=dict)


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def compute_applied_patch_hash(applied_diff: str) -> str:
    """Compute hash of the actual applied patch diff for hash chain completeness."""
    return _sha256(applied_diff)


def verify_hash_chain(
    raw_output_hash: str,
    normalized_patch_hash: str,
    applied_patch_hash: str,
) -> bool:
    """Verify that the hash chain is complete and consistent."""
    if not raw_output_hash or not normalized_patch_hash or not applied_patch_hash:
        return False
    return True


def verify_selected_candidate_matches_applied(
    selected_candidate_hash: str,
    applied_patch_hash: str,
) -> bool:
    """Verify that the selected candidate hash matches the applied patch hash."""
    if not selected_candidate_hash or not applied_patch_hash:
        return False
    return selected_candidate_hash == applied_patch_hash


def check_claim_eligibility(
    candidate: CanonicalPatchCandidate,
    selected_candidate_hash: str = "",
    applied_patch_hash: str = "",
    selected_candidate_hash_matches_applied: bool = False,
) -> bool:
    """Check if a candidate is eligible for claim based on hash chain and match."""
    if not candidate.raw_output_hash or not candidate.normalized_patch_hash:
        return False
    
    if selected_candidate_hash and applied_patch_hash:
        if not selected_candidate_hash_matches_applied:
            return False
    
    return candidate.claim_eligible


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
        has_context_lines = any(
            line.startswith(" ") and line.strip()
            for line in raw.splitlines()
            if not line.startswith(("---", "+++", "@@"))
        )
        if has_diff_headers and not has_context_lines:
            return OutputFormat.PARTIAL_DIFF
        return OutputFormat.UNIFIED_DIFF

    has_search = "<<<<<<< SEARCH" in raw
    has_replace = ">>>>>>> REPLACE" in raw
    if has_search and has_replace:
        if "```" in raw:
            return OutputFormat.FENCED_SEARCH_REPLACE
        return OutputFormat.SEARCH_REPLACE

    line_span_pattern = re.compile(r'(?m)^@@\s*-?\d+.*\+\d+.*@@.*$')
    if line_span_pattern.search(raw) and ("def " in raw or "class " in raw or "return " in raw):
        return OutputFormat.LINE_SPAN_EDIT

    func_pattern = re.compile(r'(?m)^(def|class)\s+\w+')
    if func_pattern.search(raw) and ("return " in raw or "raise " in raw or "pass" in raw):
        return OutputFormat.FUNCTION_REPLACEMENT

    repair_intent_keywords = [
        "fix the", "change the", "update the", "modify the",
        "should be", "needs to be", "replace with", "add error handling",
        "remove the", "rename the", "refactor the",
    ]
    if any(kw in lower_raw for kw in repair_intent_keywords):
        return OutputFormat.NATURAL_LANGUAGE_REPAIR_INTENT

    code_keywords = ["def ", "import ", "class ", "return ", "const ", "let ", "function ", "var ", "sys.", "os.", "print("]
    if any(kw in raw for kw in code_keywords) or ("=" in raw and len(raw.splitlines()) > 1):
        return OutputFormat.MALFORMED_OUTPUT

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
    match = re.search(replace_pattern, raw, re.DOTALL)
    if match:
        replacement = match.group(2).strip()
        steps.append("extract_replacement_from_search_replace")
        return replacement, steps
    return "", steps


def _normalize_partial_diff(raw: str) -> str:
    lines = raw.splitlines()
    normalized = []
    for line in lines:
        if line.startswith("--- a/") or line.startswith("+++ b/"):
            continue
        if line.startswith("@@ "):
            continue
        normalized.append(line)
    return "\n".join(normalized).strip()


def _normalize_line_span_edit(raw: str) -> str:
    lines = raw.splitlines()
    normalized = []
    for line in lines:
        if line.startswith("@@ "):
            continue
        if line.startswith("--- ") or line.startswith("+++ "):
            continue
        normalized.append(line)
    return "\n".join(normalized).strip()


def _normalize_function_replacement(raw: str) -> str:
    lines = raw.splitlines()
    normalized = []
    in_func = False
    for line in lines:
        if re.match(r'^(def|class)\s+\w+', line):
            in_func = True
        if in_func:
            normalized.append(line)
    return "\n".join(normalized).strip() if normalized else raw.strip()


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

    if fmt == OutputFormat.PARTIAL_DIFF:
        normalized_patch = _normalize_partial_diff(raw_output)
        if normalized_patch != raw_output:
            normalization_steps.append("partial_diff_normalized")

    if fmt == OutputFormat.LINE_SPAN_EDIT:
        normalized_patch = _normalize_line_span_edit(raw_output)
        if normalized_patch != raw_output:
            normalization_steps.append("line_span_edit_normalized")

    if fmt == OutputFormat.FUNCTION_REPLACEMENT:
        normalized_patch = _normalize_function_replacement(raw_output)
        if normalized_patch != raw_output:
            normalization_steps.append("function_replacement_normalized")

    if fmt == OutputFormat.NATURAL_LANGUAGE_REPAIR_INTENT:
        return OutputUnderstandingResult(
            success=False,
            candidate=None,
            detected_format=fmt.value,
            failure_reason="natural_language_repair_intent_not_actionable",
        )

    raw_hash = _sha256(raw_output)
    normalized_hash = _sha256(normalized_patch)

    candidate = CanonicalPatchCandidate(
        source_format=fmt.value,
        raw_output=raw_output,
        raw_output_hash=raw_hash,
        normalized_patch=normalized_patch,
        normalized_patch_hash=normalized_hash,
        normalization_steps=tuple(normalization_steps),
        safety_flags=tuple(safety_flags),
        claim_eligible=bool(raw_hash and normalized_hash),
    )

    return OutputUnderstandingResult(
        success=True,
        candidate=candidate,
        detected_format=fmt.value,
        failure_reason="",
    )


# --- Legacy compatibility for committee_orchestrator ---

@dataclass(frozen=True)
class _LegacyPatchCandidate:
    candidate_id: str
    model_name: str
    source_format: str
    target_file: str
    target_symbol: str
    patch_text: str
    patch_hash: str
    extraction_confidence: float = 0.0
    safety_flags: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class _LegacyUnderstandingResult:
    source_format: str
    normalization_steps: tuple[str, ...] = ()
    anchor_status: str = "unknown"
    parser_error_kind: str = ""
    rejection_reason: str = ""
    candidate: _LegacyPatchCandidate | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        if self.candidate is not None:
            payload["candidate"] = self.candidate.to_dict()
        return payload


def _legacy_derive_source_format(output_class: str, conversion_status: str) -> str:
    oc = str(output_class or "").upper()
    cs = str(conversion_status or "").lower()
    if oc in {"VALID_SEARCH_REPLACE", "FENCED_SEARCH_REPLACE", "MALFORMED_SEARCH_REPLACE"}:
        return "search_replace"
    if oc == "UNIFIED_DIFF":
        return "unified_diff_converted" if cs and cs != "none" else "unified_diff"
    if oc in {"MARKDOWN_FENCED", "PLAIN_TEXT", "NATURAL_LANGUAGE"}:
        return "natural_language"
    if oc == "EMPTY":
        return "empty"
    if oc:
        return oc.lower()
    return "unknown"


def build_output_understanding_result(
    *,
    candidate_id: str,
    expected_model: str,
    invoked_model: str,
    target_file: str,
    target_symbol: str,
    patch_text: str,
    patch_hash: str,
    model_decision: dict[str, Any],
) -> _LegacyUnderstandingResult:
    output_class = str(model_decision.get("output_class", "") or "")
    parser_error_kind = str(model_decision.get("parser_error_kind", "") or "")
    conversion_status = str(model_decision.get("conversion_status", "") or "none")
    source_format = _legacy_derive_source_format(output_class, conversion_status)

    normalization_steps: list[str] = []
    if conversion_status and conversion_status != "none":
        normalization_steps.append(conversion_status)
    if bool(model_decision.get("contains_markdown_fence", False)):
        normalization_steps.append("markdown_fence_detected")
    if bool(model_decision.get("target_file_correct", True)) is False:
        normalization_steps.append("target_file_mismatch")

    safety_flags: list[str] = []
    if expected_model != invoked_model:
        safety_flags.append("model_mismatch")
    if parser_error_kind and parser_error_kind.lower() != "none":
        safety_flags.append("parser_error")

    rejection_reason = ""
    if parser_error_kind and parser_error_kind.lower() != "none":
        rejection_reason = parser_error_kind
    elif source_format == "empty":
        rejection_reason = "empty_output"

    anchor_status = "target_declared" if target_file else "unknown"
    candidate = None
    if patch_text:
        candidate = _LegacyPatchCandidate(
            candidate_id=candidate_id,
            model_name=invoked_model or expected_model,
            source_format=source_format,
            target_file=target_file,
            target_symbol=target_symbol,
            patch_text=patch_text,
            patch_hash=patch_hash,
            extraction_confidence=1.0 if invoked_model == expected_model and not rejection_reason else 0.5,
            safety_flags=tuple(safety_flags),
        )

    return _LegacyUnderstandingResult(
        source_format=source_format,
        normalization_steps=tuple(normalization_steps),
        anchor_status=anchor_status,
        parser_error_kind=parser_error_kind,
        rejection_reason=rejection_reason,
        candidate=candidate,
    )


def enrich_candidate_with_anchor(
    candidate: CanonicalPatchCandidate,
    *,
    target_file: str = "",
    target_symbol: str = "",
    line_span: str = "",
    old_block_hash: str = "",
    applied_patch_hash: str = "",
    claim_eligible: bool | None = None,
) -> CanonicalPatchCandidate:
    """P2-1: Produce a new candidate with anchor fields filled.

    Uses dataclasses.replace() to preserve all original fields.
    """
    from dataclasses import replace
    kwargs = dict(
        target_file=target_file,
        target_symbol=target_symbol,
        line_span=line_span,
        old_block_hash=old_block_hash,
    )
    if applied_patch_hash:
        kwargs["applied_patch_hash"] = applied_patch_hash
    if claim_eligible is not None:
        kwargs["claim_eligible"] = claim_eligible
    return replace(candidate, **kwargs)
