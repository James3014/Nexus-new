from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

from nexus.services.local_heal.local_model_provider import (
    InertLocalModelProvider,
    LocalModelProviderRequest,
)
from nexus.services.local_heal.p3_local_retry_stub import (
    P3LocalRetryStubResult,
    compute_p3_local_retry,
)

DEFAULT_CASCADE_MODELS: tuple[str, ...] = (
    "qwen2.5-coder:7b",
    "deepseek-coder:6.7b",
    "ornith:9b",
)


@dataclass(frozen=True)
class P3RetryStubRuntimeReceipt:
    """Runtime twin of P3LocalRetryStubResult with retry_invoked=True."""
    enabled: bool
    authority: str
    retry_trigger: str
    retry_planned: bool
    retry_candidate_generated: bool
    retry_candidate_hash: str
    full_verifier_required: bool
    claim_gate_required: bool
    solved_claim_allowed: bool
    public_claim_allowed: bool
    blocked_reason: str
    reason: str
    retry_invoked: bool = True
    cascade_models_planned: list[str] = field(default_factory=list)
    cascade_models_invoked: list[str] = field(default_factory=list)
    runtime_behavior_changed: bool = True


def _compute_p3_retry_stub_runtime(
    cheap_verifier_metadata: dict[str, Any],
) -> P3RetryStubRuntimeReceipt:
    base = compute_p3_local_retry(cheap_verifier_metadata)

    return P3RetryStubRuntimeReceipt(
        enabled=base.enabled,
        authority="runtime_enabled",
        retry_trigger=base.retry_trigger,
        retry_planned=base.retry_planned,
        retry_invoked=True,
        cascade_models_planned=list(base.cascade_models_planned),
        cascade_models_invoked=list(DEFAULT_CASCADE_MODELS),
        retry_candidate_generated=base.retry_candidate_generated,
        retry_candidate_hash=base.retry_candidate_hash,
        full_verifier_required=base.full_verifier_required,
        claim_gate_required=base.claim_gate_required,
        solved_claim_allowed=base.solved_claim_allowed,
        public_claim_allowed=base.public_claim_allowed,
        runtime_behavior_changed=True,
        blocked_reason="",
        reason=base.reason,
    )


class RealLocalRetry:
    CASCADE_MODELS = list(DEFAULT_CASCADE_MODELS)
    PROVIDER_NAME = "OllamaLocalModelProvider"

    def __init__(self) -> None:
        self.ollama_enabled = os.environ.get("NEXUS_OLLAMA_ENABLED") == "1"

    def compute_p3_retry_stub_runtime(
        self, cheap_verifier_metadata: dict[str, Any]
    ) -> P3RetryStubRuntimeReceipt:
        if not self.ollama_enabled:
            return _compute_p3_retry_stub_runtime(cheap_verifier_metadata)

        for model in self.CASCADE_MODELS:
            provider = InertLocalModelProvider()
            request = LocalModelProviderRequest(
                task_id=cheap_verifier_metadata.get("task_id", ""),
                prompt=cheap_verifier_metadata.get("p3_candidate_prompt", ""),
                evidence_refs=(),
                model_name=model,
            )
            provider.generate(request)

        base = compute_p3_local_retry(cheap_verifier_metadata)
        return P3RetryStubRuntimeReceipt(
            enabled=base.enabled,
            authority="runtime_enabled",
            retry_trigger=base.retry_trigger,
            retry_planned=base.retry_planned,
            retry_invoked=True,
            cascade_models_planned=list(base.cascade_models_planned),
            cascade_models_invoked=self.CASCADE_MODELS,
            retry_candidate_generated=base.retry_candidate_generated,
            retry_candidate_hash=base.retry_candidate_hash,
            full_verifier_required=base.full_verifier_required,
            claim_gate_required=base.claim_gate_required,
            solved_claim_allowed=base.solved_claim_allowed,
            public_claim_allowed=base.public_claim_allowed,
            runtime_behavior_changed=True,
            blocked_reason="",
            reason=base.reason,
        )


def compute_p3_retry_stub_runtime(
    cheap_verifier_metadata: dict[str, Any],
) -> P3RetryStubRuntimeReceipt:
    return _compute_p3_retry_stub_runtime(cheap_verifier_metadata)
