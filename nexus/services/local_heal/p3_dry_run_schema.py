from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


REQUIRED_P3_DRY_RUN_RECEIPT_FIELDS = frozenset({
    "p3_l_receipt_version",
    "p3_l_enabled",
    "p3_l_authority",
    "p3_l_runtime_state",
    "p3_l_env_guard_present",
    "p3_l_dry_run_only",
    "p3_l_intended_topology",
    "p3_l_task_difficulty",
    "p3_l_provider_request_built",
    "p3_l_provider_invoked",
    "p3_l_network_invoked",
    "p3_l_api_key_used",
    "p3_l_local_model_invoked",
    "p3_l_patch_apply_invoked",
    "p3_l_runtime_behavior_changed",
    "p3_l_full_verifier_required",
    "p3_l_claim_gate_required",
    "p3_l_claim_eligible",
    "p3_l_public_claim_allowed",
    "p3_l_production_ready",
    "p3_l_blocked_reasons",
    "p3_l_receipt_complete",
})

REQUIRED_BOOLEAN_FALSE_FIELDS = frozenset({
    "p3_l_provider_invoked",
    "p3_l_network_invoked",
    "p3_l_api_key_used",
    "p3_l_local_model_invoked",
    "p3_l_patch_apply_invoked",
    "p3_l_runtime_behavior_changed",
    "p3_l_claim_eligible",
    "p3_l_public_claim_allowed",
    "p3_l_production_ready",
})

REQUIRED_BOOLEAN_TRUE_FIELDS = frozenset({
    "p3_l_full_verifier_required",
    "p3_l_claim_gate_required",
    "p3_l_dry_run_only",
})

VALID_AUTHORITIES = frozenset({
    "shadow_only",
    "env_guarded_dry_run",
    "blocked",
    "rollback_required",
})


@dataclass(frozen=True)
class P3DryRunSchemaResult:
    """P3-M1: Strict schema validation result."""
    schema_version: str
    schema_passed: bool
    missing_fields: list[str]
    type_errors: list[str]
    value_errors: list[str]
    blocked_reasons: list[str]


def validate_p3_dry_run_schema(receipt: dict[str, Any]) -> P3DryRunSchemaResult:
    """Validate P3 dry-run receipt against strict required-field schema.

    Fails closed: any missing field, wrong type, or unsafe value fails.
    """
    missing_fields: list[str] = []
    type_errors: list[str] = []
    value_errors: list[str] = []
    blocked_reasons: list[str] = []

    for field_name in REQUIRED_P3_DRY_RUN_RECEIPT_FIELDS:
        if field_name not in receipt:
            missing_fields.append(field_name)
            blocked_reasons.append(f"missing:{field_name}")

    if "p3_l_blocked_reasons" in receipt:
        if not isinstance(receipt["p3_l_blocked_reasons"], list):
            type_errors.append("p3_l_blocked_reasons:not_list")
            blocked_reasons.append("type_error:p3_l_blocked_reasons")

    for field_name in REQUIRED_BOOLEAN_FALSE_FIELDS:
        if field_name in receipt:
            val = receipt[field_name]
            if not isinstance(val, bool):
                type_errors.append(f"{field_name}:not_bool")
                blocked_reasons.append(f"type_error:{field_name}")
            elif val is True:
                value_errors.append(f"{field_name}=true")
                blocked_reasons.append(f"unsafe_value:{field_name}=true")

    for field_name in REQUIRED_BOOLEAN_TRUE_FIELDS:
        if field_name in receipt:
            val = receipt[field_name]
            if not isinstance(val, bool):
                type_errors.append(f"{field_name}:not_bool")
                blocked_reasons.append(f"type_error:{field_name}")
            elif val is False:
                value_errors.append(f"{field_name}=false")
                blocked_reasons.append(f"unsafe_value:{field_name}=false")

    if "p3_l_authority" in receipt:
        authority = str(receipt["p3_l_authority"] or "")
        if authority not in VALID_AUTHORITIES:
            value_errors.append(f"p3_l_authority={authority}")
            blocked_reasons.append(f"invalid_authority:{authority}")

    schema_passed = (
        len(missing_fields) == 0
        and len(type_errors) == 0
        and len(value_errors) == 0
    )

    return P3DryRunSchemaResult(
        schema_version="1.0",
        schema_passed=schema_passed,
        missing_fields=missing_fields,
        type_errors=type_errors,
        value_errors=value_errors,
        blocked_reasons=blocked_reasons,
    )


def p3_dry_run_schema_to_dict(result: P3DryRunSchemaResult) -> dict[str, Any]:
    """Convert P3DryRunSchemaResult to JSON-serializable dict."""
    return {
        "p3_l_schema_version": result.schema_version,
        "p3_l_schema_passed": result.schema_passed,
        "p3_l_missing_fields": result.missing_fields,
        "p3_l_type_errors": result.type_errors,
        "p3_l_value_errors": result.value_errors,
        "p3_l_schema_blocked_reasons": result.blocked_reasons,
    }
