"""Local Hybrid Role Contract: define and enforce model role boundaries."""
from dataclasses import dataclass
from enum import Enum
from typing import Dict, Optional, Sequence


class ModelRole(str, Enum):
    """Defined roles for each model in the local hybrid pipeline."""
    SELECTOR = "selector"      # 3B: candidate selection, reranking, budget policy
    JUDGE = "judge"            # 3B manual route: ranking / gate judgement
    SEARCHER = "searcher"      # 7B: search, localization, planning
    PROPOSER = "proposer"      # 7B manual route: candidate proposal
    SECONDARY_PROPOSER = "secondary_proposer"  # 6.7B manual route: secondary candidate proposal
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

# Explicit opt-in route roles for historical/manual route replay.
ROUTE_ROLE_CONTRACT: Dict[str, ModelRole] = {
    "judge": ModelRole.JUDGE,
    "proposer": ModelRole.PROPOSER,
    "secondary_proposer": ModelRole.SECONDARY_PROPOSER,
}

ROLE_CONTRACT: Dict[str, ModelRole] = {**PHASE_ROLE_CONTRACT, **ROUTE_ROLE_CONTRACT}

MODEL_ROLE_ALIASES: Dict[str, tuple[ModelRole, ...]] = {
    "qwen2.5:3b": (ModelRole.SELECTOR, ModelRole.JUDGE),
    "qwen2.5-coder:7b": (ModelRole.SEARCHER, ModelRole.PROPOSER),
    "deepseek-coder:6.7b-instruct": (ModelRole.SECONDARY_PROPOSER,),
    "qwen2.5-coder:14b-instruct-q3_K_M": (ModelRole.PATCHER,),
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
    expected_role = ROLE_CONTRACT.get(phase)
    if expected_role is None:
        return None  # Unknown phase, no contract

    actual_roles = _model_name_to_roles(model_name)
    if actual_roles is None:
        return None  # Unknown model, can't check

    if expected_role not in actual_roles:
        return (
            f"ROLE_DRIFT: phase={phase} expected={expected_role.value} "
            f"got={_model_name_to_role(model_name).value} model={model_name}"
        )

    return None


def _model_name_to_roles(model_name: str) -> Optional[tuple[ModelRole, ...]]:
    """Map model name to its declared role aliases."""
    name_lower = model_name.lower()
    if name_lower in MODEL_ROLE_ALIASES:
        return MODEL_ROLE_ALIASES[name_lower]
    if "3b" in name_lower or "s2t" in name_lower:
        return (ModelRole.SELECTOR,)
    if "7b" in name_lower:
        return (ModelRole.SEARCHER,)
    if "14b" in name_lower:
        return (ModelRole.PATCHER,)
    return None


def _model_name_to_role(model_name: str) -> Optional[ModelRole]:
    """Map model name to its primary defined role."""
    roles = _model_name_to_roles(model_name)
    if roles is None:
        return None
    return roles[0]


def _resolve_invoked_role(phase: str, model_name: str) -> ModelRole:
    expected_role = ROLE_CONTRACT.get(phase)
    roles = _model_name_to_roles(model_name)
    if expected_role is not None and roles is not None and expected_role in roles:
        return expected_role
    return _model_name_to_role(model_name) or ModelRole.GOVERNANCE


def build_role_receipt(phase: str, model_name: str, reason_code: str = "", fallback_reason: str = "") -> RoleReceipt:
    """Build a role receipt for a phase execution."""
    expected_role = ROLE_CONTRACT.get(phase, ModelRole.GOVERNANCE)
    actual_role = _resolve_invoked_role(phase, model_name)
    drift = check_role_drift(phase, model_name)

    return RoleReceipt(
        phase=phase,
        selected_model_role=expected_role.value,
        invoked_model_role=actual_role.value,
        reason_code=reason_code,
        fallback_reason=fallback_reason,
        role_drift_detected=drift is not None,
    )
