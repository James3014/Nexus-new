from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, field
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
    # P2-1: Anchor fields
    target_file: str = ""
    target_symbol: str = ""
    line_span: str = ""
    old_block_hash: str = ""


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
) -> CanonicalPatchCandidate:
    """P2-1: Produce a new candidate with anchor fields filled.

    Uses dataclasses.replace() to preserve all original fields.
    """
    from dataclasses import replace
    return replace(
        candidate,
        target_file=target_file,
        target_symbol=target_symbol,
        line_span=line_span,
        old_block_hash=old_block_hash,
    )
