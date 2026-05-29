from __future__ import annotations

from enum import Enum
from typing import Any

# SSOT constants for overhead redaction
RUNNER_AST_PARSER_OVERHEAD_MS = 150.0
MAX_COMMERCIAL_TOKEN_COST_RATIO = 1.2


class CostEvidenceClass(str, Enum):
    CLEAN_MODEL_COST = "clean_model_cost"
    RUNNER_OVERHEAD_POLLUTED = "runner_overhead_polluted"
    RESCUE_ONLY_NO_MODEL_CALL = "rescue_only_no_model_call"
    NO_MODEL_CALL = "no_model_call"
    RESCUE_WITH_MODEL_FALLBACK_MEASURED = "rescue_with_model_fallback_measured"
    RESCUE_WITH_MODEL_FALLBACK = "rescue_with_model_fallback"
    RESCUE_ONLY_LOCAL_SUCCESS = "rescue_only_local_success"
    TOKEN_UNRELIABLE = "token_unreliable"
    NOT_CLEAN_MODEL_COST = "not_clean_model_cost"


def derive_cost_evidence_class(
    *,
    model_calls: int,
    provider_token_measured: bool,
    token_reliable: bool,
    runner_overhead_polluted: bool,
    local_success: bool,
    nexus_internal_delivery_valid: bool = False,
    token_cost_ratio: float = 1.0,
    model_fallback_then_local_rescue: bool = False,
) -> CostEvidenceClass:
    """Core SSOT contract function to classify route cost evidence.

    Ensures consistent classification across the classifier, optimizer, evidence bundle,
    and persistent worker dashboard.

    Args:
        model_fallback_then_local_rescue: True when a model attempt was genuinely made but
            failed, and a local rescue path (e.g. bounded_nexus_rescue_used) then succeeded.
            Distinguishes from shadow-local wins (local_hidden_shadow) where the model call
            was only a shadow arm, not a true fallback attempt.
    """
    # 8R TDD Slice 1: Commercial Cost 降級閘門
    if token_cost_ratio > MAX_COMMERCIAL_TOKEN_COST_RATIO:
        return CostEvidenceClass.TOKEN_UNRELIABLE

    clean_model_cost_evidence = bool(
        model_calls > 0
        and provider_token_measured
        and token_reliable
        and not runner_overhead_polluted
        and not local_success
    )

    if clean_model_cost_evidence:
        return CostEvidenceClass.CLEAN_MODEL_COST

    if runner_overhead_polluted:
        return CostEvidenceClass.RUNNER_OVERHEAD_POLLUTED

    if model_calls <= 0:
        if local_success or nexus_internal_delivery_valid:
            return CostEvidenceClass.RESCUE_ONLY_NO_MODEL_CALL
        return CostEvidenceClass.NO_MODEL_CALL

    if local_success:
        # Distinguish two sub-cases:
        # 1. model_fallback_then_local_rescue=True: model was genuinely attempted (bounded
        #    rescue path), failed, then local rescue succeeded. Token evidence is from the
        #    real model attempt → RESCUE_WITH_MODEL_FALLBACK_MEASURED.
        # 2. Default (False): local-path shadow/preflight win (local_hidden_shadow etc.).
        #    The model call was a shadow arm, not a true fallback → RESCUE_ONLY_LOCAL_SUCCESS.
        if model_fallback_then_local_rescue:
            if provider_token_measured:
                return CostEvidenceClass.RESCUE_WITH_MODEL_FALLBACK_MEASURED
            return CostEvidenceClass.RESCUE_WITH_MODEL_FALLBACK
        return CostEvidenceClass.RESCUE_ONLY_LOCAL_SUCCESS

    if not provider_token_measured or not token_reliable:
        return CostEvidenceClass.TOKEN_UNRELIABLE

    return CostEvidenceClass.NOT_CLEAN_MODEL_COST


def calculate_adjusted_overhead(
    raw_overhead_ms: float,
    runner_ast_parser_overhead_ms: float = RUNNER_AST_PARSER_OVERHEAD_MS,
) -> float:
    """Calculate the runner overhead minus AST parser / JIT overhead, floored at 0."""
    return max(0.0, raw_overhead_ms - runner_ast_parser_overhead_ms)

