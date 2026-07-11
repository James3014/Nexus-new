from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any

from nexus.services.local_heal.local_model_provider import (
    InertLocalModelProvider,
    LocalModelProviderRequest,
    OllamaLocalModelProvider,
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
    advisor_recommendation: str = ""
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
        advisor_recommendation="",
    )


DIAGNOSIS_PROMPT_TEMPLATE = """You are a 3B software repair advisor. Analyze the following diagnosis context and provide a repair recommendation.

Task difficulty: {task_difficulty}
Target file: {target_file}
Target symbol: {target_symbol}
Line span: {line_span}
Failure class: {failure_class}

Respond in JSON format with exactly one field:
{{"advisor_recommendation": "your concise recommendation here"}}
"""


def _build_diagnosis_prompt(skeleton: dict[str, Any]) -> str:
    return DIAGNOSIS_PROMPT_TEMPLATE.format(
        task_difficulty=skeleton.get("p3_task_difficulty", "unknown"),
        target_file=skeleton.get("p3_target_file", ""),
        target_symbol=skeleton.get("p3_target_symbol", ""),
        line_span=skeleton.get("p3_line_span", ""),
        failure_class=skeleton.get("p3_failure_class", ""),
    )


def _parse_advisor_response(raw_text: str) -> str:
    if not raw_text:
        return ""
    text = raw_text.strip()
    # Try to extract JSON block
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1:
        try:
            parsed = json.loads(text[start:end+1])
            rec = parsed.get("advisor_recommendation", "")
            return str(rec).strip() if rec else ""
        except (json.JSONDecodeError, TypeError):
            pass
    # Fallback: use raw text truncated
    return text[:200]


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

        try:
            provider = OllamaLocalModelProvider()
            prompt = _build_diagnosis_prompt(skeleton)
            request = LocalModelProviderRequest(
                task_id=skeleton.get("task_id", ""),
                prompt=prompt,
                evidence_refs=(),
                model_name=self.MODEL_NAME,
                api_type="generate",
                phase=skeleton.get("phase", "planning"),
                attempt_id=skeleton.get("attempt_id", "attempt-1"),
                execution_profile=skeleton.get("execution_profile", "FULL"),
            )
            response = provider.generate(request)
            recommendation = _parse_advisor_response(response.output_text)
        except Exception:
            recommendation = ""

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
            advisor_recommendation=recommendation,
            cloud_call_invoked=True,
            runtime_behavior_changed=True,
        )


def compute_p3_local_diagnosis_runtime(
    skeleton: dict[str, Any],
    anchor: dict[str, Any],
) -> P3LocalDiagnosisRuntimeReceipt:
    diag = RealLocalDiagnosis()
    return diag.compute_p3_local_diagnosis_runtime(skeleton, anchor)
