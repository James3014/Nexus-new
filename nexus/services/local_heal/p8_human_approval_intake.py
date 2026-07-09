from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


REQUIRED_APPROVAL_FIELDS = frozenset({
    "approval_version",
    "human_approved",
    "approver",
    "approval_timestamp_utc",
    "approval_scope",
    "provider_kind",
    "model_name",
    "max_network_calls",
    "max_cost_usd",
    "timeout_seconds",
    "synthetic_prompt_only",
    "prompt_redaction_required",
    "api_key_logging_allowed",
    "raw_prompt_logging_allowed",
    "raw_response_logging_allowed",
    "retry_allowed",
    "streaming_allowed",
    "tool_call_allowed",
    "patch_apply_allowed",
    "runtime_behavior_change_allowed",
    "solved_claim_allowed",
    "claim_eligible_allowed",
    "public_claim_allowed",
    "production_ready",
    "p2_hash_truth_required",
    "p2_anchor_truth_required",
    "p4_verifier_required",
    "p4_claim_gate_required",
})


@dataclass(frozen=True)
class P8HumanApprovalIntakeResult:
    """P8-B1: Human approval artifact intake."""
    intake_version: str
    approval_artifact_path: str
    approval_artifact_exists: bool
    approval_valid: bool
    human_approved: bool
    approver: str
    approval_scope: str
    provider_kind: str
    model_name: str
    max_network_calls: int
    max_cost_usd: float
    timeout_seconds: float
    blocked_reasons: list[str] = field(default_factory=list)


DEFAULT_APPROVAL_PATH = Path("artifacts/effect_reports/p8_human_approval_artifact_v0.json")


def validate_p8_human_approval(
    approval_path: str | Path | None = None,
) -> P8HumanApprovalIntakeResult:
    """Validate human approval artifact for one network smoke."""
    path = Path(approval_path) if approval_path else DEFAULT_APPROVAL_PATH
    blocked_reasons: list[str] = []

    if not path.exists():
        return P8HumanApprovalIntakeResult(
            intake_version="1.0",
            approval_artifact_path=str(path),
            approval_artifact_exists=False,
            approval_valid=False,
            human_approved=False,
            approver="",
            approval_scope="",
            provider_kind="",
            model_name="",
            max_network_calls=0,
            max_cost_usd=0.0,
            timeout_seconds=0.0,
            blocked_reasons=["approval_artifact_missing"],
        )

    try:
        with open(path) as f:
            artifact = json.load(f)
    except Exception:
        return P8HumanApprovalIntakeResult(
            intake_version="1.0",
            approval_artifact_path=str(path),
            approval_artifact_exists=True,
            approval_valid=False,
            human_approved=False,
            approver="",
            approval_scope="",
            provider_kind="",
            model_name="",
            max_network_calls=0,
            max_cost_usd=0.0,
            timeout_seconds=0.0,
            blocked_reasons=["approval_artifact_unreadable"],
        )

    for field_name in REQUIRED_APPROVAL_FIELDS:
        if field_name not in artifact:
            blocked_reasons.append(f"missing_field:{field_name}")

    human_approved = bool(artifact.get("human_approved", False))
    if not human_approved:
        blocked_reasons.append("human_approved_false")

    approver = str(artifact.get("approver", "") or "")
    if not approver:
        blocked_reasons.append("approver_missing")

    approval_scope = str(artifact.get("approval_scope", "") or "")
    if approval_scope != "P8_ONE_NETWORK_SMOKE_NO_APPLY":
        blocked_reasons.append(f"wrong_approval_scope:{approval_scope}")

    provider_kind = str(artifact.get("provider_kind", "") or "")
    if not provider_kind:
        blocked_reasons.append("provider_kind_missing")

    model_name = str(artifact.get("model_name", "") or "")
    if not model_name:
        blocked_reasons.append("model_name_missing")

    max_network_calls = int(artifact.get("max_network_calls", 0) or 0)
    if max_network_calls != 1:
        blocked_reasons.append(f"max_network_calls_not_1:{max_network_calls}")

    max_cost_usd = float(artifact.get("max_cost_usd", 0) or 0)
    if max_cost_usd <= 0 or max_cost_usd > 1.00:
        blocked_reasons.append(f"max_cost_usd_out_of_range:{max_cost_usd}")

    timeout_seconds = float(artifact.get("timeout_seconds", 0) or 0)
    if timeout_seconds <= 0 or timeout_seconds > 30:
        blocked_reasons.append(f"timeout_seconds_out_of_range:{timeout_seconds}")

    unsafe_flags = {
        "api_key_logging_allowed": True,
        "raw_prompt_logging_allowed": True,
        "raw_response_logging_allowed": True,
        "retry_allowed": True,
        "streaming_allowed": True,
        "tool_call_allowed": True,
        "patch_apply_allowed": True,
        "runtime_behavior_change_allowed": True,
        "solved_claim_allowed": True,
        "public_claim_allowed": True,
        "production_ready": True,
    }
    for flag, expected in unsafe_flags.items():
        val = artifact.get(flag, not expected)
        if val == expected:
            blocked_reasons.append(f"unsafe_flag:{flag}={val}")

    required_true = {
        "synthetic_prompt_only": True,
        "prompt_redaction_required": True,
        "p2_hash_truth_required": True,
        "p2_anchor_truth_required": True,
        "p4_verifier_required": True,
        "p4_claim_gate_required": True,
    }
    for flag, expected in required_true.items():
        val = artifact.get(flag, not expected)
        if val != expected:
            blocked_reasons.append(f"required_flag_wrong:{flag}={val}")

    approval_valid = len(blocked_reasons) == 0

    return P8HumanApprovalIntakeResult(
        intake_version="1.0",
        approval_artifact_path=str(path),
        approval_artifact_exists=True,
        approval_valid=approval_valid,
        human_approved=human_approved,
        approver=approver,
        approval_scope=approval_scope,
        provider_kind=provider_kind,
        model_name=model_name,
        max_network_calls=max_network_calls,
        max_cost_usd=max_cost_usd,
        timeout_seconds=timeout_seconds,
        blocked_reasons=blocked_reasons,
    )


def p8_human_approval_intake_to_dict(result: P8HumanApprovalIntakeResult) -> dict[str, Any]:
    return {
        "p8_intake_version": result.intake_version,
        "p8_approval_artifact_path": result.approval_artifact_path,
        "p8_approval_artifact_exists": result.approval_artifact_exists,
        "p8_approval_valid": result.approval_valid,
        "p8_human_approved": result.human_approved,
        "p8_approver": result.approver,
        "p8_approval_scope": result.approval_scope,
        "p8_provider_kind": result.provider_kind,
        "p8_model_name": result.model_name,
        "p8_max_network_calls": result.max_network_calls,
        "p8_max_cost_usd": result.max_cost_usd,
        "p8_timeout_seconds": result.timeout_seconds,
        "p8_blocked_reasons": result.blocked_reasons,
    }
