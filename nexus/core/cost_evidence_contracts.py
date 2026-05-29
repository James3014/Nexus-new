from __future__ import annotations

from enum import Enum
from typing import Any


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
) -> CostEvidenceClass:
    """Core SSOT contract function to classify route cost evidence.

    Ensures consistent classification across the classifier, optimizer, evidence bundle,
    and persistent worker dashboard.
    """
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
        if model_calls > 0:
            if provider_token_measured:
                return CostEvidenceClass.RESCUE_WITH_MODEL_FALLBACK_MEASURED
            return CostEvidenceClass.RESCUE_WITH_MODEL_FALLBACK
        return CostEvidenceClass.RESCUE_ONLY_LOCAL_SUCCESS

    if not provider_token_measured or not token_reliable:
        return CostEvidenceClass.TOKEN_UNRELIABLE

    return CostEvidenceClass.NOT_CLEAN_MODEL_COST
