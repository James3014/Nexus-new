from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class P8NetworkSmokeExecutorResult:
    executor_version: str = "1.0"
    dry_run: bool = True
    approval_valid: bool = False
    boundary_valid: bool = False
    redaction_passed: bool = False
    execution_allowed: bool = False
    network_call_attempted: bool = False
    network_call_completed: bool = False
    network_call_count: int = 0
    provider_kind: str = ""
    model_name: str = ""
    redacted_prompt_hash: str = ""
    provider_response_hash: str = ""
    candidate_like_output_available: bool = False
    receipt_complete: bool = False
    blocked_reasons: list[str] = field(default_factory=list)


def dry_run_smoke(
    *,
    approval_valid: bool,
    boundary_valid: bool,
    redaction_passed: bool,
    provider_kind: str = "",
    model_name: str = "",
    redacted_prompt_hash: str = "",
) -> P8NetworkSmokeExecutorResult:
    blocked = []
    if not approval_valid: blocked.append("approval_invalid")
    if not boundary_valid: blocked.append("boundary_invalid")
    if not redaction_passed: blocked.append("redaction_failed")
    allowed = len(blocked) == 0
    return P8NetworkSmokeExecutorResult(
        approval_valid=approval_valid,
        boundary_valid=boundary_valid,
        redaction_passed=redaction_passed,
        execution_allowed=allowed,
        provider_kind=provider_kind,
        model_name=model_name,
        redacted_prompt_hash=redacted_prompt_hash,
        receipt_complete=allowed,
        blocked_reasons=blocked,
    )
