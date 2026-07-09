from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from nexus.services.local_heal.p3_local_diagnosis import (
    P3LocalDiagnosis,
    compute_p3_local_diagnosis,
)


@dataclass(frozen=True)
class P3LocalDiagnosisRuntimeReceipt:
    """Runtime twin of P3LocalDiagnosis with cloud_call_invoked=True."""
    enabled: bool
    authority: str
    task_id: str
    task_difficulty: str
    target_file: str
    target_symbol: str
    line_span: str
    old_block_hash: str
    failure_class: str
    failure_summary: str
    verifier_summary: str
    anchor_status: str
    hash_chain_status: str
    compact_prompt: str
    compact_prompt_hash: str
    compact_prompt_token_estimate: int
    source_context_included: bool
    cloud_ready: bool
    claim_eligible: bool
    public_claim_allowed: bool
    reason: str
    cloud_call_invoked: bool = True
    runtime_behavior_changed: bool = True


def compute_p3_local_diagnosis_runtime(
    skeleton: dict[str, Any],
    anchor: dict[str, Any],
) -> P3LocalDiagnosisRuntimeReceipt:
    base = compute_p3_local_diagnosis(
        request_metadata={"task_id": skeleton.get("task_id", "")},
        p3_skeleton=skeleton,
        anchor_metadata=anchor,
    )

    return P3LocalDiagnosisRuntimeReceipt(
        enabled=base.enabled,
        authority="runtime_enabled",
        task_id=base.task_id,
        task_difficulty=base.task_difficulty,
        target_file=base.target_file,
        target_symbol=base.target_symbol,
        line_span=base.line_span,
        old_block_hash=base.old_block_hash,
        failure_class=base.failure_class,
        failure_summary=base.failure_summary,
        verifier_summary=base.verifier_summary,
        anchor_status=base.anchor_status,
        hash_chain_status=base.hash_chain_status,
        compact_prompt=base.compact_prompt,
        compact_prompt_hash=base.compact_prompt_hash,
        compact_prompt_token_estimate=base.compact_prompt_token_estimate,
        source_context_included=base.source_context_included,
        cloud_ready=base.cloud_ready,
        claim_eligible=base.claim_eligible,
        public_claim_allowed=base.public_claim_allowed,
        reason=base.reason,
    )
