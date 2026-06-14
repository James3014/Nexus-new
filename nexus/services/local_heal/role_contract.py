"""Local Hybrid Role Contract: define and enforce model role boundaries."""
from enum import Enum
from typing import Dict, Any, Optional
from dataclasses import dataclass


class ModelRole(str, Enum):
    """Defined roles for each model in the local hybrid pipeline."""
    SELECTOR = "selector"      # 3B: candidate selection, reranking, budget policy
    SEARCHER = "searcher"      # 7B: search, localization, planning
    PATCHER = "patcher"        # 14B: patch synthesis, complex repair
    GOVERNANCE = "governance"  # Nexus: gates, receipts, verification


class PhaseRole(Enum):
    """Expected model role for each pipeline phase."""
    REPRODUCTION = ModelRole.SEARCHER     # 7B
    PLANNING = ModelRole.SEARCHER        # 7B (or deterministic)
    LOCALIZATION = ModelRole.SEARCHER    # 7B (or deterministic)
    PATCH_SYNTHESIS = ModelRole.PATCHER  # 14B (or 7B for simple)
    VERIFICATION = ModelRole.GOVERNANCE  # Nexus


# Phase → expected model role mapping
PHASE_ROLE_CONTRACT: Dict[str, ModelRole] = {
    "reproduction": ModelRole.SEARCHER,
    "planning": ModelRole.SEARCHER,
    "localization": ModelRole.SEARCHER,
    "patch": ModelRole.PATCHER,
    "verification": ModelRole.GOVERNANCE,
}


@dataclass
class RoleReceipt:
    """Receipt fields for role tracking."""
    phase: str
    selected_model_role: str
    invoked_model_role: str
    reason_code: str
    fallback_reason: str = ""
    role_drift_detected: bool = False


def check_role_drift(phase: str, model_name: str) -> Optional[str]:
    """Check if a model invocation violates the role contract.
    
    Returns drift reason string if drift detected, None if OK.
    """
    expected_role = PHASE_ROLE_CONTRACT.get(phase)
    if expected_role is None:
        return None  # Unknown phase, no contract
    
    # Determine actual role from model name
    actual_role = _model_name_to_role(model_name)
    if actual_role is None:
        return None  # Unknown model, can't check
    
    if actual_role != expected_role:
        return f"ROLE_DRIFT: phase={phase} expected={expected_role.value} got={actual_role.value} model={model_name}"
    
    return None


def _model_name_to_role(model_name: str) -> Optional[ModelRole]:
    """Map model name to its defined role."""
    name_lower = model_name.lower()
    if "3b" in name_lower or "s2t" in name_lower:
        return ModelRole.SELECTOR
    elif "7b" in name_lower:
        return ModelRole.SEARCHER
    elif "14b" in name_lower:
        return ModelRole.PATCHER
    return None


def build_role_receipt(phase: str, model_name: str, reason_code: str = "", fallback_reason: str = "") -> RoleReceipt:
    """Build a role receipt for a phase execution."""
    expected_role = PHASE_ROLE_CONTRACT.get(phase, ModelRole.GOVERNANCE)
    actual_role = _model_name_to_role(model_name) or ModelRole.GOVERNANCE
    drift = check_role_drift(phase, model_name)
    
    return RoleReceipt(
        phase=phase,
        selected_model_role=expected_role.value,
        invoked_model_role=actual_role.value,
        reason_code=reason_code,
        fallback_reason=fallback_reason,
        role_drift_detected=drift is not None,
    )
