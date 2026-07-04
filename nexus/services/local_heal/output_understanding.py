from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class CanonicalPatchCandidate:
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
class OutputUnderstandingResult:
    source_format: str
    normalization_steps: tuple[str, ...] = ()
    anchor_status: str = "unknown"
    parser_error_kind: str = ""
    rejection_reason: str = ""
    candidate: CanonicalPatchCandidate | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        if self.candidate is not None:
            payload["candidate"] = self.candidate.to_dict()
        return payload


def _derive_source_format(output_class: str, conversion_status: str) -> str:
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
) -> OutputUnderstandingResult:
    output_class = str(model_decision.get("output_class", "") or "")
    parser_error_kind = str(model_decision.get("parser_error_kind", "") or "")
    conversion_status = str(model_decision.get("conversion_status", "") or "none")
    source_format = _derive_source_format(output_class, conversion_status)

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
        candidate = CanonicalPatchCandidate(
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

    return OutputUnderstandingResult(
        source_format=source_format,
        normalization_steps=tuple(normalization_steps),
        anchor_status=anchor_status,
        parser_error_kind=parser_error_kind,
        rejection_reason=rejection_reason,
        candidate=candidate,
    )
