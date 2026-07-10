from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from nexus.services.local_heal.local_model_provider import (
    InertLocalModelProvider,
    LocalModelProviderRequest,
)
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


def _compute_p3_local_diagnosis_runtime(
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


class RealLocalDiagnosis:
    MODEL_NAME = "qwen2.5-s2t-advisor:3b"
    PROVIDER_NAME = "OllamaLocalModelProvider"

    def __init__(self) -> None:
        self.ollama_enabled = os.environ.get("NEXUS_OLLAMA_ENABLED") == "1"

    def compute_p3_local_diagnosis_runtime(
        self, skeleton: dict[str, Any], anchor: dict[str, Any]
    ) -> P3LocalDiagnosisRuntimeReceipt:
        if not self.ollama_enabled:
            return _compute_p3_local_diagnosis_runtime(skeleton, anchor)

        provider = InertLocalModelProvider()
        request = LocalModelProviderRequest(
            task_id=skeleton.get("task_id", ""),
            prompt=skeleton.get("p3_failure_summary", ""),
            evidence_refs=(),
            model_name=self.MODEL_NAME,
        )
        provider.generate(request)
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
            cloud_call_invoked=True,
            runtime_behavior_changed=True,
        )


def compute_p3_local_diagnosis_runtime(
    skeleton: dict[str, Any],
    anchor: dict[str, Any],
) -> P3LocalDiagnosisRuntimeReceipt:
    return _compute_p3_local_diagnosis_runtime(skeleton, anchor)
