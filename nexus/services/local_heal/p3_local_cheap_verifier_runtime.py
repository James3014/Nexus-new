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
from nexus.services.local_heal.p3_local_cheap_verifier import (
    P3LocalCheapVerifierResult,
    compute_p3_cheap_verifier,
)


@dataclass(frozen=True)
class P3CheapVerifierRuntimeReceipt:
    """Runtime twin of P3LocalCheapVerifierResult with invoked=True."""
    enabled: bool
    authority: str
    candidate_available: bool
    canonical_candidate_hash: str
    cheap_verifier_planned: bool
    cheap_verifier_result: str
    cheap_verifier_confidence: float
    full_verifier_required: bool
    claim_gate_required: bool
    solved_claim_allowed: bool
    public_claim_allowed: bool
    blocked_reason: str
    reason: str
    cheap_verifier_invoked: bool = True
    runtime_behavior_changed: bool = True


def _compute_p3_cheap_verifier_runtime(
    cloud_stub_metadata: dict[str, Any],
) -> P3CheapVerifierRuntimeReceipt:
    base = compute_p3_cheap_verifier(cloud_stub_metadata)

    return P3CheapVerifierRuntimeReceipt(
        enabled=base.enabled,
        authority="runtime_enabled",
        candidate_available=base.candidate_available,
        canonical_candidate_hash=base.canonical_candidate_hash,
        cheap_verifier_planned=base.cheap_verifier_planned,
        cheap_verifier_invoked=True,
        cheap_verifier_result="runtime_invoked",
        cheap_verifier_confidence=0.0,
        full_verifier_required=base.full_verifier_required,
        claim_gate_required=base.claim_gate_required,
        solved_claim_allowed=base.solved_claim_allowed,
        public_claim_allowed=base.public_claim_allowed,
        runtime_behavior_changed=True,
        blocked_reason="",
        reason=base.reason,
    )


CHEAP_VERIFIER_PROMPT_TEMPLATE = """You are a 9B cheap verifier. Assess whether the following candidate patch is correct.

Target file: {target_file}
Problem: {problem}
Candidate patch: {candidate_patch}

Respond in JSON format:
{{"verdict": "pass" or "fail", "confidence": 0.0-1.0, "reason": "brief explanation"}}
"""


def _build_verifier_prompt(metadata: dict[str, Any]) -> str:
    return CHEAP_VERIFIER_PROMPT_TEMPLATE.format(
        target_file=metadata.get("p3_target_file", ""),
        problem=metadata.get("p3_problem_description", ""),
        candidate_patch=metadata.get("p3_candidate_patch", ""),
    )


def _parse_verifier_response(raw_text: str) -> tuple[str, float]:
    if not raw_text:
        return "fail", 0.0
    text = raw_text.strip()
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1:
        try:
            parsed = json.loads(text[start:end+1])
            verdict = str(parsed.get("verdict", "fail")).strip()
            confidence = float(parsed.get("confidence", 0.0))
            if verdict not in ("pass", "fail"):
                verdict = "fail"
            confidence = max(0.0, min(1.0, confidence))
            return verdict, confidence
        except (json.JSONDecodeError, TypeError, ValueError):
            pass
    return "fail", 0.0


class RealLocalCheapVerifier:
    MODEL_NAME = "ornith:9b"
    PROVIDER_NAME = "OllamaLocalModelProvider"

    def __init__(self) -> None:
        self.ollama_enabled = os.environ.get("NEXUS_OLLAMA_ENABLED") == "1"

    def compute_p3_cheap_verifier_runtime(
        self, cloud_stub_metadata: dict[str, Any]
    ) -> P3CheapVerifierRuntimeReceipt:
        if not self.ollama_enabled:
            return _compute_p3_cheap_verifier_runtime(cloud_stub_metadata)

        try:
            provider = OllamaLocalModelProvider()
            prompt = _build_verifier_prompt(cloud_stub_metadata)
            request = LocalModelProviderRequest(
                task_id=cloud_stub_metadata.get("task_id", ""),
                prompt=prompt,
                evidence_refs=(),
                model_name=self.MODEL_NAME,
                api_type="generate",
            )
            response = provider.generate(request)
            verdict, confidence = _parse_verifier_response(response.output_text)
        except Exception:
            verdict, confidence = "fail", 0.0

        base = compute_p3_cheap_verifier(cloud_stub_metadata)
        return P3CheapVerifierRuntimeReceipt(
            enabled=base.enabled,
            authority="runtime_enabled",
            candidate_available=base.candidate_available,
            canonical_candidate_hash=base.canonical_candidate_hash,
            cheap_verifier_planned=base.cheap_verifier_planned,
            cheap_verifier_invoked=True,
            cheap_verifier_result=verdict,
            cheap_verifier_confidence=confidence,
            full_verifier_required=base.full_verifier_required,
            claim_gate_required=base.claim_gate_required,
            solved_claim_allowed=base.solved_claim_allowed,
            public_claim_allowed=base.public_claim_allowed,
            runtime_behavior_changed=True,
            blocked_reason="",
            reason=base.reason,
        )


def compute_p3_cheap_verifier_runtime(
    cloud_stub_metadata: dict[str, Any],
) -> P3CheapVerifierRuntimeReceipt:
    verifier = RealLocalCheapVerifier()
    return verifier.compute_p3_cheap_verifier_runtime(cloud_stub_metadata)
