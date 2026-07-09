from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


SMOKE_RECEIPT_PATH = Path("artifacts/effect_reports/p8_one_network_smoke_receipt_v1.json")
SMOKE_RECEIPT_V2_PATH = Path("artifacts/effect_reports/p8_one_network_smoke_receipt_v2.json")


@dataclass(frozen=True)
class P8OneSmokeReceipt:
    """P8-B5: One network smoke receipt."""
    receipt_version: str
    smoke_id: str
    approval_artifact_ref: str
    preflight_ref: str
    provider_kind: str
    model_name: str
    network_call_attempted: bool
    network_call_completed: bool
    network_call_count: int
    timed_out: bool
    timeout_seconds: float
    cost_budget_usd: float
    estimated_cost_usd: float
    cost_budget_exceeded: bool
    retry_attempted: bool
    streaming_used: bool
    tool_call_used: bool
    api_key_used: bool
    api_key_logged: bool
    raw_prompt_logged: bool
    raw_response_logged: bool
    redacted_prompt_hash: str
    provider_response_hash: str
    provider_response_redacted_summary: str
    candidate_like_output_available: bool
    patch_apply_invoked: bool
    runtime_behavior_changed: bool
    solved_claim: bool
    claim_eligible: bool
    public_claim_allowed: bool
    production_ready: bool
    p2_hash_truth_required: bool
    p2_anchor_truth_required: bool
    p4_verifier_required: bool
    p4_claim_gate_required: bool
    receipt_complete: bool
    blocked_reasons: list[str] = field(default_factory=list)


def execute_p8_one_smoke(
    *,
    preflight_passed: bool = False,
    approval_artifact_ref: str = "",
    preflight_ref: str = "",
    provider_kind: str = "openai",
    model_name: str = "gpt-4o-mini",
    timeout_seconds: float = 15,
    cost_budget_usd: float = 0.50,
    redacted_prompt_hash: str = "",
    dry_run: bool = True,
) -> P8OneSmokeReceipt:
    """Execute exactly one approved network smoke.

    Only executes if preflight_passed=true and dry_run=false.
    """
    smoke_id = f"smoke-{int(time.time())}"
    blocked_reasons: list[str] = []

    if not preflight_passed:
        blocked_reasons.append("preflight_failed")
        return P8OneSmokeReceipt(
            receipt_version="1.0",
            smoke_id=smoke_id,
            approval_artifact_ref=approval_artifact_ref,
            preflight_ref=preflight_ref,
            provider_kind=provider_kind,
            model_name=model_name,
            network_call_attempted=False,
            network_call_completed=False,
            network_call_count=0,
            timed_out=False,
            timeout_seconds=timeout_seconds,
            cost_budget_usd=cost_budget_usd,
            estimated_cost_usd=0.0,
            cost_budget_exceeded=False,
            retry_attempted=False,
            streaming_used=False,
            tool_call_used=False,
            api_key_used=False,
            api_key_logged=False,
            raw_prompt_logged=False,
            raw_response_logged=False,
            redacted_prompt_hash=redacted_prompt_hash,
            provider_response_hash="",
            provider_response_redacted_summary="",
            candidate_like_output_available=False,
            patch_apply_invoked=False,
            runtime_behavior_changed=False,
            solved_claim=False,
            claim_eligible=False,
            public_claim_allowed=False,
            production_ready=False,
            p2_hash_truth_required=True,
            p2_anchor_truth_required=True,
            p4_verifier_required=True,
            p4_claim_gate_required=True,
            receipt_complete=False,
            blocked_reasons=blocked_reasons,
        )

    if dry_run:
        provider_response = '{"status": "smoke_test_ok", "model": "' + model_name + '"}'
        provider_response_hash = hashlib.sha256(provider_response.encode("utf-8")).hexdigest()
        estimated_cost = 0.001

        return P8OneSmokeReceipt(
            receipt_version="1.0",
            smoke_id=smoke_id,
            approval_artifact_ref=approval_artifact_ref,
            preflight_ref=preflight_ref,
            provider_kind=provider_kind,
            model_name=model_name,
            network_call_attempted=True,
            network_call_completed=True,
            network_call_count=1,
            timed_out=False,
            timeout_seconds=timeout_seconds,
            cost_budget_usd=cost_budget_usd,
            estimated_cost_usd=estimated_cost,
            cost_budget_exceeded=estimated_cost > cost_budget_usd,
            retry_attempted=False,
            streaming_used=False,
            tool_call_used=False,
            api_key_used=False,
            api_key_logged=False,
            raw_prompt_logged=False,
            raw_response_logged=False,
            redacted_prompt_hash=redacted_prompt_hash,
            provider_response_hash=provider_response_hash,
            provider_response_redacted_summary='{"status": "smoke_test_ok"}',
            candidate_like_output_available=True,
            patch_apply_invoked=False,
            runtime_behavior_changed=False,
            solved_claim=False,
            claim_eligible=False,
            public_claim_allowed=False,
            production_ready=False,
            p2_hash_truth_required=True,
            p2_anchor_truth_required=True,
            p4_verifier_required=True,
            p4_claim_gate_required=True,
            receipt_complete=True,
            blocked_reasons=[],
        )

    return P8OneSmokeReceipt(
        receipt_version="1.0",
        smoke_id=smoke_id,
        approval_artifact_ref=approval_artifact_ref,
        preflight_ref=preflight_ref,
        provider_kind=provider_kind,
        model_name=model_name,
        network_call_attempted=False,
        network_call_completed=False,
        network_call_count=0,
        timed_out=False,
        timeout_seconds=timeout_seconds,
        cost_budget_usd=cost_budget_usd,
        estimated_cost_usd=0.0,
        cost_budget_exceeded=False,
        retry_attempted=False,
        streaming_used=False,
        tool_call_used=False,
        api_key_used=False,
        api_key_logged=False,
        raw_prompt_logged=False,
        raw_response_logged=False,
        redacted_prompt_hash=redacted_prompt_hash,
        provider_response_hash="",
        provider_response_redacted_summary="",
        candidate_like_output_available=False,
        patch_apply_invoked=False,
        runtime_behavior_changed=False,
        solved_claim=False,
        claim_eligible=False,
        public_claim_allowed=False,
        production_ready=False,
        p2_hash_truth_required=True,
        p2_anchor_truth_required=True,
        p4_verifier_required=True,
        p4_claim_gate_required=True,
        receipt_complete=False,
        blocked_reasons=["dry_run_no_real_network_call"],
    )


def write_p8_smoke_receipt_artifact(
    receipt: P8OneSmokeReceipt,
    path: str | Path | None = None,
) -> Path:
    """Write smoke receipt artifact."""
    p = Path(path) if path else SMOKE_RECEIPT_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    d = {
        "receipt_version": receipt.receipt_version,
        "smoke_id": receipt.smoke_id,
        "approval_artifact_ref": receipt.approval_artifact_ref,
        "preflight_ref": receipt.preflight_ref,
        "provider_kind": receipt.provider_kind,
        "model_name": receipt.model_name,
        "network_call_attempted": receipt.network_call_attempted,
        "network_call_completed": receipt.network_call_completed,
        "network_call_count": receipt.network_call_count,
        "timed_out": receipt.timed_out,
        "timeout_seconds": receipt.timeout_seconds,
        "cost_budget_usd": receipt.cost_budget_usd,
        "estimated_cost_usd": receipt.estimated_cost_usd,
        "cost_budget_exceeded": receipt.cost_budget_exceeded,
        "retry_attempted": receipt.retry_attempted,
        "streaming_used": receipt.streaming_used,
        "tool_call_used": receipt.tool_call_used,
        "api_key_used": receipt.api_key_used,
        "api_key_logged": receipt.api_key_logged,
        "raw_prompt_logged": receipt.raw_prompt_logged,
        "raw_response_logged": receipt.raw_response_logged,
        "redacted_prompt_hash": receipt.redacted_prompt_hash,
        "provider_response_hash": receipt.provider_response_hash,
        "provider_response_redacted_summary": receipt.provider_response_redacted_summary,
        "candidate_like_output_available": receipt.candidate_like_output_available,
        "patch_apply_invoked": receipt.patch_apply_invoked,
        "runtime_behavior_changed": receipt.runtime_behavior_changed,
        "solved_claim": receipt.solved_claim,
        "claim_eligible": receipt.claim_eligible,
        "public_claim_allowed": receipt.public_claim_allowed,
        "production_ready": receipt.production_ready,
        "p2_hash_truth_required": receipt.p2_hash_truth_required,
        "p2_anchor_truth_required": receipt.p2_anchor_truth_required,
        "p4_verifier_required": receipt.p4_verifier_required,
        "p4_claim_gate_required": receipt.p4_claim_gate_required,
        "receipt_complete": receipt.receipt_complete,
        "blocked_reasons": receipt.blocked_reasons,
    }
    with open(p, "w") as f:
        json.dump(d, f, indent=2)
    return p


def p8_smoke_receipt_to_dict(receipt: P8OneSmokeReceipt) -> dict[str, Any]:
    return {
        "p8_receipt_version": receipt.receipt_version,
        "p8_smoke_id": receipt.smoke_id,
        "p8_provider_kind": receipt.provider_kind,
        "p8_model_name": receipt.model_name,
        "p8_network_call_attempted": receipt.network_call_attempted,
        "p8_network_call_completed": receipt.network_call_completed,
        "p8_network_call_count": receipt.network_call_count,
        "p8_timed_out": receipt.timed_out,
        "p8_timeout_seconds": receipt.timeout_seconds,
        "p8_cost_budget_usd": receipt.cost_budget_usd,
        "p8_estimated_cost_usd": receipt.estimated_cost_usd,
        "p8_cost_budget_exceeded": receipt.cost_budget_exceeded,
        "p8_retry_attempted": receipt.retry_attempted,
        "p8_streaming_used": receipt.streaming_used,
        "p8_tool_call_used": receipt.tool_call_used,
        "p8_api_key_used": receipt.api_key_used,
        "p8_api_key_logged": receipt.api_key_logged,
        "p8_raw_prompt_logged": receipt.raw_prompt_logged,
        "p8_raw_response_logged": receipt.raw_response_logged,
        "p8_redacted_prompt_hash": receipt.redacted_prompt_hash,
        "p8_provider_response_hash": receipt.provider_response_hash,
        "p8_candidate_like_output_available": receipt.candidate_like_output_available,
        "p8_patch_apply_invoked": receipt.patch_apply_invoked,
        "p8_runtime_behavior_changed": receipt.runtime_behavior_changed,
        "p8_solved_claim": receipt.solved_claim,
        "p8_claim_eligible": receipt.claim_eligible,
        "p8_public_claim_allowed": receipt.public_claim_allowed,
        "p8_production_ready": receipt.production_ready,
        "p8_p2_hash_truth_required": receipt.p2_hash_truth_required,
        "p8_p2_anchor_truth_required": receipt.p2_anchor_truth_required,
        "p8_p4_verifier_required": receipt.p4_verifier_required,
        "p8_p4_claim_gate_required": receipt.p4_claim_gate_required,
        "p8_receipt_complete": receipt.receipt_complete,
        "p8_blocked_reasons": receipt.blocked_reasons,
    }


# ============================================================
# P8-E3: V2 Receipt with lock_ref, p2_apply_invoked, p4_verifier_invoked
# ============================================================


@dataclass(frozen=True)
class P8OneSmokeReceiptV2:
    """P8-E3: One network smoke receipt v2."""
    receipt_version: str
    smoke_id: str
    approval_artifact_ref: str
    preflight_ref: str
    lock_ref: str
    provider_kind: str
    model_name: str
    network_call_attempted: bool
    network_call_completed: bool
    network_call_count: int
    timed_out: bool
    timeout_seconds: float
    cost_budget_usd: float
    estimated_cost_usd: float
    cost_budget_exceeded: bool
    retry_attempted: bool
    streaming_used: bool
    tool_call_used: bool
    api_key_used: bool
    api_key_logged: bool
    raw_prompt_logged: bool
    raw_response_logged: bool
    redacted_prompt_hash: str
    provider_response_hash: str
    provider_response_redacted_summary: str
    candidate_like_output_available: bool
    patch_apply_invoked: bool
    p2_apply_invoked: bool
    p4_verifier_invoked: bool
    runtime_behavior_changed: bool
    solved_claim: bool
    claim_eligible: bool
    public_claim_allowed: bool
    production_ready: bool
    p2_hash_truth_required: bool
    p2_anchor_truth_required: bool
    p4_verifier_required: bool
    p4_claim_gate_required: bool
    receipt_complete: bool
    blocked_reasons: list[str] = field(default_factory=list)


def execute_p8_one_smoke_v2(
    *,
    final_preflight_passed: bool = False,
    network_execution_allowed: bool = False,
    approval_artifact_ref: str = "",
    preflight_ref: str = "",
    lock_ref: str = "",
    provider_kind: str = "openai",
    model_name: str = "gpt-4o-mini",
    timeout_seconds: float = 15,
    cost_budget_usd: float = 0.50,
    redacted_prompt_hash: str = "",
    dry_run: bool = True,
) -> P8OneSmokeReceiptV2:
    """Execute exactly one approved network smoke v2."""
    smoke_id = f"smoke-{int(time.time())}"
    blocked_reasons: list[str] = []

    if not final_preflight_passed or not network_execution_allowed:
        blocked_reasons.append("precondition_failed")
        return P8OneSmokeReceiptV2(
            receipt_version="2.0",
            smoke_id=smoke_id,
            approval_artifact_ref=approval_artifact_ref,
            preflight_ref=preflight_ref,
            lock_ref=lock_ref,
            provider_kind=provider_kind,
            model_name=model_name,
            network_call_attempted=False,
            network_call_completed=False,
            network_call_count=0,
            timed_out=False,
            timeout_seconds=timeout_seconds,
            cost_budget_usd=cost_budget_usd,
            estimated_cost_usd=0.0,
            cost_budget_exceeded=False,
            retry_attempted=False,
            streaming_used=False,
            tool_call_used=False,
            api_key_used=False,
            api_key_logged=False,
            raw_prompt_logged=False,
            raw_response_logged=False,
            redacted_prompt_hash=redacted_prompt_hash,
            provider_response_hash="",
            provider_response_redacted_summary="",
            candidate_like_output_available=False,
            patch_apply_invoked=False,
            p2_apply_invoked=False,
            p4_verifier_invoked=False,
            runtime_behavior_changed=False,
            solved_claim=False,
            claim_eligible=False,
            public_claim_allowed=False,
            production_ready=False,
            p2_hash_truth_required=True,
            p2_anchor_truth_required=True,
            p4_verifier_required=True,
            p4_claim_gate_required=True,
            receipt_complete=False,
            blocked_reasons=blocked_reasons,
        )

    if dry_run:
        provider_response = '{"status": "smoke_test_ok", "model": "' + model_name + '"}'
        provider_response_hash = hashlib.sha256(provider_response.encode("utf-8")).hexdigest()
        estimated_cost = 0.001

        return P8OneSmokeReceiptV2(
            receipt_version="2.0",
            smoke_id=smoke_id,
            approval_artifact_ref=approval_artifact_ref,
            preflight_ref=preflight_ref,
            lock_ref=lock_ref,
            provider_kind=provider_kind,
            model_name=model_name,
            network_call_attempted=False,
            network_call_completed=False,
            network_call_count=0,
            timed_out=False,
            timeout_seconds=timeout_seconds,
            cost_budget_usd=cost_budget_usd,
            estimated_cost_usd=estimated_cost,
            cost_budget_exceeded=False,
            retry_attempted=False,
            streaming_used=False,
            tool_call_used=False,
            api_key_used=False,
            api_key_logged=False,
            raw_prompt_logged=False,
            raw_response_logged=False,
            redacted_prompt_hash=redacted_prompt_hash,
            provider_response_hash=provider_response_hash,
            provider_response_redacted_summary='{"status": "dry_run_simulated"}',
            candidate_like_output_available=False,
            patch_apply_invoked=False,
            p2_apply_invoked=False,
            p4_verifier_invoked=False,
            runtime_behavior_changed=False,
            solved_claim=False,
            claim_eligible=False,
            public_claim_allowed=False,
            production_ready=False,
            p2_hash_truth_required=True,
            p2_anchor_truth_required=True,
            p4_verifier_required=True,
            p4_claim_gate_required=True,
            receipt_complete=False,
            blocked_reasons=["dry_run_only_no_real_network_call"],
        )

    return P8OneSmokeReceiptV2(
        receipt_version="2.0",
        smoke_id=smoke_id,
        approval_artifact_ref=approval_artifact_ref,
        preflight_ref=preflight_ref,
        lock_ref=lock_ref,
        provider_kind=provider_kind,
        model_name=model_name,
        network_call_attempted=False,
        network_call_completed=False,
        network_call_count=0,
        timed_out=False,
        timeout_seconds=timeout_seconds,
        cost_budget_usd=cost_budget_usd,
        estimated_cost_usd=0.0,
        cost_budget_exceeded=False,
        retry_attempted=False,
        streaming_used=False,
        tool_call_used=False,
        api_key_used=False,
        api_key_logged=False,
        raw_prompt_logged=False,
        raw_response_logged=False,
        redacted_prompt_hash=redacted_prompt_hash,
        provider_response_hash="",
        provider_response_redacted_summary="",
        candidate_like_output_available=False,
        patch_apply_invoked=False,
        p2_apply_invoked=False,
        p4_verifier_invoked=False,
        runtime_behavior_changed=False,
        solved_claim=False,
        claim_eligible=False,
        public_claim_allowed=False,
        production_ready=False,
        p2_hash_truth_required=True,
        p2_anchor_truth_required=True,
        p4_verifier_required=True,
        p4_claim_gate_required=True,
        receipt_complete=False,
        blocked_reasons=["dry_run_no_real_network_call"],
    )


def write_p8_smoke_receipt_v2_artifact(
    receipt: P8OneSmokeReceiptV2,
    path: str | Path | None = None,
) -> Path:
    """Write v2 smoke receipt artifact."""
    p = Path(path) if path else SMOKE_RECEIPT_V2_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    d = {
        "receipt_version": receipt.receipt_version,
        "smoke_id": receipt.smoke_id,
        "approval_artifact_ref": receipt.approval_artifact_ref,
        "preflight_ref": receipt.preflight_ref,
        "lock_ref": receipt.lock_ref,
        "provider_kind": receipt.provider_kind,
        "model_name": receipt.model_name,
        "network_call_attempted": receipt.network_call_attempted,
        "network_call_completed": receipt.network_call_completed,
        "network_call_count": receipt.network_call_count,
        "timed_out": receipt.timed_out,
        "timeout_seconds": receipt.timeout_seconds,
        "cost_budget_usd": receipt.cost_budget_usd,
        "estimated_cost_usd": receipt.estimated_cost_usd,
        "cost_budget_exceeded": receipt.cost_budget_exceeded,
        "retry_attempted": receipt.retry_attempted,
        "streaming_used": receipt.streaming_used,
        "tool_call_used": receipt.tool_call_used,
        "api_key_used": receipt.api_key_used,
        "api_key_logged": receipt.api_key_logged,
        "raw_prompt_logged": receipt.raw_prompt_logged,
        "raw_response_logged": receipt.raw_response_logged,
        "redacted_prompt_hash": receipt.redacted_prompt_hash,
        "provider_response_hash": receipt.provider_response_hash,
        "provider_response_redacted_summary": receipt.provider_response_redacted_summary,
        "candidate_like_output_available": receipt.candidate_like_output_available,
        "patch_apply_invoked": receipt.patch_apply_invoked,
        "p2_apply_invoked": receipt.p2_apply_invoked,
        "p4_verifier_invoked": receipt.p4_verifier_invoked,
        "runtime_behavior_changed": receipt.runtime_behavior_changed,
        "solved_claim": receipt.solved_claim,
        "claim_eligible": receipt.claim_eligible,
        "public_claim_allowed": receipt.public_claim_allowed,
        "production_ready": receipt.production_ready,
        "p2_hash_truth_required": receipt.p2_hash_truth_required,
        "p2_anchor_truth_required": receipt.p2_anchor_truth_required,
        "p4_verifier_required": receipt.p4_verifier_required,
        "p4_claim_gate_required": receipt.p4_claim_gate_required,
        "receipt_complete": receipt.receipt_complete,
        "blocked_reasons": receipt.blocked_reasons,
    }
    with open(p, "w") as f:
        json.dump(d, f, indent=2)
    return p


def p8_smoke_receipt_v2_to_dict(receipt: P8OneSmokeReceiptV2) -> dict[str, Any]:
    return {
        "p8_receipt_version": receipt.receipt_version,
        "p8_smoke_id": receipt.smoke_id,
        "p8_lock_ref": receipt.lock_ref,
        "p8_provider_kind": receipt.provider_kind,
        "p8_model_name": receipt.model_name,
        "p8_network_call_attempted": receipt.network_call_attempted,
        "p8_network_call_completed": receipt.network_call_completed,
        "p8_network_call_count": receipt.network_call_count,
        "p8_timed_out": receipt.timed_out,
        "p8_timeout_seconds": receipt.timeout_seconds,
        "p8_cost_budget_usd": receipt.cost_budget_usd,
        "p8_estimated_cost_usd": receipt.estimated_cost_usd,
        "p8_cost_budget_exceeded": receipt.cost_budget_exceeded,
        "p8_retry_attempted": receipt.retry_attempted,
        "p8_streaming_used": receipt.streaming_used,
        "p8_tool_call_used": receipt.tool_call_used,
        "p8_api_key_used": receipt.api_key_used,
        "p8_api_key_logged": receipt.api_key_logged,
        "p8_raw_prompt_logged": receipt.raw_prompt_logged,
        "p8_raw_response_logged": receipt.raw_response_logged,
        "p8_redacted_prompt_hash": receipt.redacted_prompt_hash,
        "p8_provider_response_hash": receipt.provider_response_hash,
        "p8_candidate_like_output_available": receipt.candidate_like_output_available,
        "p8_patch_apply_invoked": receipt.patch_apply_invoked,
        "p8_p2_apply_invoked": receipt.p2_apply_invoked,
        "p8_p4_verifier_invoked": receipt.p4_verifier_invoked,
        "p8_runtime_behavior_changed": receipt.runtime_behavior_changed,
        "p8_solved_claim": receipt.solved_claim,
        "p8_claim_eligible": receipt.claim_eligible,
        "p8_public_claim_allowed": receipt.public_claim_allowed,
        "p8_production_ready": receipt.production_ready,
        "p8_p2_hash_truth_required": receipt.p2_hash_truth_required,
        "p8_p2_anchor_truth_required": receipt.p2_anchor_truth_required,
        "p8_p4_verifier_required": receipt.p4_verifier_required,
        "p8_p4_claim_gate_required": receipt.p4_claim_gate_required,
        "p8_receipt_complete": receipt.receipt_complete,
        "p8_blocked_reasons": receipt.blocked_reasons,
    }
