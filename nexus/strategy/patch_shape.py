"""Patch shape detection and taxonomy — S4.3"""

from dataclasses import dataclass
from typing import List, Optional


@dataclass
class PatchShapeResult:
    patch_shape: str
    patch_shape_confidence: float
    detection_signals: List[str]
    m0_execution_allowed: bool
    prompt_contract_id: str
    unsupported_reason: str = ""


SINGLE_LINE_SHAPES = ["single_line_replacement", "indentation_normalized_replacement"]
SIMPLE_SHAPES = SINGLE_LINE_SHAPES + ["small_local_replacement"]
BLOCK_SHAPES = ["multi_line_block_replacement", "function_body_insertion", "conditional_branch_replacement", "loop_body_replacement", "class_or_method_body_replacement", "import_or_setup_block_update"]


def detect_patch_shape(canonical_search_lines: int = 1,
                       has_function_boundary: bool = False,
                       has_block_boundary: bool = False,
                       issue_requires_insertion: bool = False,
                       source_context_lines: int = 1) -> PatchShapeResult:
    """Detect patch shape from task metadata."""

    signals = []

    if canonical_search_lines == 1 and not issue_requires_insertion:
        signals.append("single_canonical_line")
        return PatchShapeResult(
            patch_shape="single_line_replacement",
            patch_shape_confidence=0.9,
            detection_signals=signals,
            m0_execution_allowed=True,
            prompt_contract_id="replace_only_v1",
        )

    if canonical_search_lines <= 5 and not has_block_boundary:
        signals.append("small_local_block")
        return PatchShapeResult(
            patch_shape="small_local_replacement",
            patch_shape_confidence=0.8,
            detection_signals=signals,
            m0_execution_allowed=True,
            prompt_contract_id="replace_only_v1",
        )

    if has_function_boundary and issue_requires_insertion:
        signals.append("function_body_insertion")
        return PatchShapeResult(
            patch_shape="function_body_insertion",
            patch_shape_confidence=0.7,
            detection_signals=signals,
            m0_execution_allowed=False,
            prompt_contract_id="",
            unsupported_reason="function_body_insertion requires block-aware prompt contract",
        )

    if has_block_boundary:
        signals.append("block_replacement")
        return PatchShapeResult(
            patch_shape="multi_line_block_replacement",
            patch_shape_confidence=0.6,
            detection_signals=signals,
            m0_execution_allowed=False,
            prompt_contract_id="",
            unsupported_reason="block replacement requires context-aware prompt contract",
        )

    signals.append("unknown_complex")
    return PatchShapeResult(
        patch_shape="unsupported_complex_shape",
        patch_shape_confidence=0.3,
        detection_signals=signals,
        m0_execution_allowed=False,
        prompt_contract_id="",
        unsupported_reason="unknown complex shape",
    )
