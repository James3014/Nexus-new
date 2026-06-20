"""T2.1: Workspace failure claim/export guard.

Ensures workspace failures are not counted as patcher/model failures.
Ensures model_calls=0 and deterministic/AST fallback are not exported as model patch success.
"""

from typing import Any


# Workspace failure classes that should NOT count as patcher/model failure
WORKSPACE_FAILURE_CLASSES = frozenset({
    "workspace_not_configured",
    "workspace_provisioning",
    "repo_not_mounted",
    "import_error",
    "target_path_unresolved",
    "file_not_found",
    "env_fixable_by_agent",
    "DEPENDENCY_MISMATCH",
    "TOOLCHAIN_MISSING",
})


def is_workspace_failure(failure_class: str) -> bool:
    """Check if failure_class represents a workspace/infra failure."""
    return failure_class in WORKSPACE_FAILURE_CLASSES


def should_export_as_model_patch_success(
    *,
    model_calls: int,
    model_patch_reward: float,
    deterministic_fallback_used: bool,
    ast_fallback_used: bool,
    canonical_span_source: str,
    failure_class: str,
) -> bool:
    """Determine if result should be exported as model patch success.

    Returns False if:
    - model_calls=0 (no LLM contribution)
    - deterministic_fallback_used (not model-generated)
    - ast_fallback_used (not model-generated)
    - workspace failure (infra issue, not patcher)
    - model_patch_reward=0.0 (no reward)
    """
    if is_workspace_failure(failure_class):
        return False
    if model_calls == 0:
        return False
    if model_patch_reward <= 0.0:
        return False
    if deterministic_fallback_used:
        return False
    if ast_fallback_used:
        return False
    return True


def should_export_as_canonical_recovery_success(
    *,
    canonical_span_source: str,
    model_calls: int,
    solved: bool,
) -> bool:
    """Determine if result should be exported as canonical recovery success.

    Returns True if solved via canonical span extraction (not model-generated patch).
    """
    if not solved:
        return False
    if canonical_span_source in ("ast_boundary", "unified_diff", "locked_search"):
        return True
    return False


def should_export_as_internal_infra_failure(
    *,
    failure_class: str,
) -> bool:
    """Determine if result should be exported as internal infra failure."""
    return is_workspace_failure(failure_class)


def get_export_eligibility(
    *,
    solved: bool,
    model_calls: int,
    model_patch_reward: float,
    deterministic_fallback_used: bool,
    ast_fallback_used: bool,
    canonical_span_source: str,
    failure_class: str,
    claim_eligible: bool,
) -> dict:
    """Get complete export eligibility for a task result.

    Returns dict with all export flags.
    """
    is_ws_failure = is_workspace_failure(failure_class)
    is_model_patch = should_export_as_model_patch_success(
        model_calls=model_calls,
        model_patch_reward=model_patch_reward,
        deterministic_fallback_used=deterministic_fallback_used,
        ast_fallback_used=ast_fallback_used,
        canonical_span_source=canonical_span_source,
        failure_class=failure_class,
    )
    is_canonical_recovery = should_export_as_canonical_recovery_success(
        canonical_span_source=canonical_span_source,
        model_calls=model_calls,
        solved=solved,
    )
    is_infra_failure = should_export_as_internal_infra_failure(
        failure_class=failure_class,
    )

    return {
        "export_as_model_patch_success": is_model_patch,
        "export_as_canonical_recovery_success": is_canonical_recovery,
        "export_as_internal_infra_failure": is_infra_failure,
        "export_as_public_claim": claim_eligible and solved,
        "count_as_patcher_failure": not is_ws_failure and not solved,
        "count_as_model_failure": not is_ws_failure and model_calls > 0 and not solved,
    }


def apply_export_guard(receipt: dict) -> dict:
    """Apply export guard to a receipt.

    Modifies receipt in-place and returns it.
    Ensures workspace failures and fallback successes are correctly classified.
    """
    telemetry = receipt.get("telemetry", {})
    failure_class = telemetry.get("failure_class", "")
    model_calls = telemetry.get("model_calls", 0)
    model_patch_reward = telemetry.get("model_patch_reward", 0.0)
    deterministic_fallback_used = telemetry.get("deterministic_fallback_used", False)
    ast_fallback_used = telemetry.get("ast_fallback_reward", "") != ""
    canonical_span_source = telemetry.get("canonical_span_source", "")
    solved = telemetry.get("solved", False)
    claim_eligible = receipt.get("claim_eligible", False)

    eligibility = get_export_eligibility(
        solved=solved,
        model_calls=model_calls,
        model_patch_reward=model_patch_reward,
        deterministic_fallback_used=deterministic_fallback_used,
        ast_fallback_used=ast_fallback_used,
        canonical_span_source=canonical_span_source,
        failure_class=failure_class,
        claim_eligible=claim_eligible,
    )

    # Apply guard
    receipt["claim_eligible"] = False  # Focused regression never claimable
    receipt["public_claim_allowed"] = False
    receipt["export_as_model_patch_success"] = eligibility["export_as_model_patch_success"]
    receipt["export_as_canonical_recovery_success"] = eligibility["export_as_canonical_recovery_success"]
    receipt["export_as_internal_infra_failure"] = eligibility["export_as_internal_infra_failure"]
    receipt["export_as_public_claim"] = False
    receipt["count_as_patcher_failure"] = eligibility["count_as_patcher_failure"]
    receipt["count_as_model_failure"] = eligibility["count_as_model_failure"]

    return receipt
