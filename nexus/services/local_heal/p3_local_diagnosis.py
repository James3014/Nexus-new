from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class P3LocalDiagnosis:
    """P3-B: Deterministic local diagnosis compact prompt builder.

    Shadow-only: produces compact cloud-ready prompt without calling cloud.
    No runtime behavior change. No cloud API client. No network call.
    """
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
    cloud_call_invoked: bool
    runtime_behavior_changed: bool
    claim_eligible: bool
    public_claim_allowed: bool
    reason: str


def _estimate_tokens(text: str) -> int:
    """Rough token estimate: ~4 chars per token for English code."""
    return max(1, len(text) // 4)


def _build_compact_prompt(
    task_id: str,
    task_difficulty: str,
    target_file: str,
    target_symbol: str,
    failure_class: str,
    failure_summary: str,
    verifier_summary: str,
    anchor_status: str,
    line_span: str = "",
    old_block_hash: str = "",
) -> str:
    """Build compact prompt for cloud candidate generation.

    Budget: ≤500 chars. Includes task summary, failure, anchor, verifier.
    """
    parts = []

    parts.append(f"Task: {task_id[:50]}")
    parts.append(f"Difficulty: {task_difficulty}")

    if target_file:
        parts.append(f"File: {target_file}")
    if target_symbol:
        parts.append(f"Symbol: {target_symbol}")
    if line_span:
        parts.append(f"Span: {line_span}")
    if old_block_hash:
        parts.append(f"Hash: {old_block_hash[:16]}")

    if failure_class:
        parts.append(f"Failure: {failure_class}")
    if failure_summary:
        parts.append(f"Error: {failure_summary[:100]}")
    if verifier_summary:
        parts.append(f"Verifier: {verifier_summary[:100]}")

    parts.append(f"Anchor: {anchor_status}")

    prompt = " | ".join(parts)[:500]
    return prompt


def compute_p3_local_diagnosis(
    request_metadata: dict[str, Any],
    p3_skeleton: dict[str, Any] | None = None,
    anchor_metadata: dict[str, Any] | None = None,
    hash_chain_metadata: dict[str, Any] | None = None,
    failure_metadata: dict[str, Any] | None = None,
) -> P3LocalDiagnosis:
    """Compute P3 local diagnosis compact prompt from request metadata.

    Shadow-only mode: no cloud calls, no runtime behavior change.
    """
    task_id = str(request_metadata.get("task_id", "") or "")
    task_difficulty = str(p3_skeleton.get("p3_task_difficulty", "medium") if p3_skeleton else "medium")

    anchor = anchor_metadata or {}
    target_file = str(anchor.get("target_file", "") or "")
    target_symbol = str(anchor.get("target_symbol", "") or "")
    line_span = str(anchor.get("line_span", "") or "")
    old_block_hash = str(anchor.get("old_block_hash", "") or "")

    has_anchor = bool(target_file)
    anchor_status = "available" if has_anchor else "missing"

    hashes = hash_chain_metadata or {}
    raw_hash = str(hashes.get("raw_output_hash", "") or "")
    norm_hash = str(hashes.get("normalized_patch_hash", "") or "")
    applied_hash = str(hashes.get("applied_patch_hash", "") or "")
    hash_chain_status = "complete" if (raw_hash and norm_hash and applied_hash) else "incomplete"

    failures = failure_metadata or {}
    failure_class = str(failures.get("failure_class", "") or "")
    failure_summary = str(failures.get("failure_summary", "") or "")
    verifier_summary = str(failures.get("verifier_summary", "") or "")

    compact_prompt = _build_compact_prompt(
        task_id=task_id,
        task_difficulty=task_difficulty,
        target_file=target_file,
        target_symbol=target_symbol,
        failure_class=failure_class,
        failure_summary=failure_summary,
        verifier_summary=verifier_summary,
        anchor_status=anchor_status,
        line_span=line_span,
        old_block_hash=old_block_hash,
    )

    compact_prompt_hash = hashlib.sha256(compact_prompt.encode("utf-8")).hexdigest()
    compact_prompt_token_estimate = _estimate_tokens(compact_prompt)

    cloud_ready = has_anchor and hash_chain_status == "complete"

    reason_parts = []
    if not has_anchor:
        reason_parts.append("missing_anchor")
    if hash_chain_status != "complete":
        reason_parts.append("incomplete_hash_chain")
    if not reason_parts:
        reason_parts.append("diagnosis_complete")
    reason = ";".join(reason_parts)

    return P3LocalDiagnosis(
        enabled=True,
        authority="shadow_only",
        task_id=task_id,
        task_difficulty=task_difficulty,
        target_file=target_file,
        target_symbol=target_symbol,
        line_span=line_span,
        old_block_hash=old_block_hash,
        failure_class=failure_class,
        failure_summary=failure_summary,
        verifier_summary=verifier_summary,
        anchor_status=anchor_status,
        hash_chain_status=hash_chain_status,
        compact_prompt=compact_prompt,
        compact_prompt_hash=compact_prompt_hash,
        compact_prompt_token_estimate=compact_prompt_token_estimate,
        source_context_included=has_anchor,
        cloud_ready=cloud_ready,
        cloud_call_invoked=False,
        runtime_behavior_changed=False,
        claim_eligible=False,
        public_claim_allowed=False,
        reason=reason,
    )


def p3_diagnosis_to_dict(diag: P3LocalDiagnosis) -> dict[str, Any]:
    """Convert P3LocalDiagnosis to JSON-serializable dict for receipt metadata."""
    return {
        "p3_local_diagnosis_enabled": diag.enabled,
        "p3_local_diagnosis_authority": diag.authority,
        "p3_diagnosis_task_id": diag.task_id,
        "p3_diagnosis_task_difficulty": diag.task_difficulty,
        "p3_diagnosis_target_file": diag.target_file,
        "p3_diagnosis_target_symbol": diag.target_symbol,
        "p3_diagnosis_line_span": diag.line_span,
        "p3_diagnosis_old_block_hash": diag.old_block_hash,
        "p3_diagnosis_failure_class": diag.failure_class,
        "p3_diagnosis_failure_summary": diag.failure_summary,
        "p3_diagnosis_verifier_summary": diag.verifier_summary,
        "p3_diagnosis_anchor_status": diag.anchor_status,
        "p3_diagnosis_hash_chain_status": diag.hash_chain_status,
        "p3_diagnosis_compact_prompt": diag.compact_prompt,
        "p3_diagnosis_compact_prompt_hash": diag.compact_prompt_hash,
        "p3_diagnosis_compact_prompt_token_estimate": diag.compact_prompt_token_estimate,
        "p3_diagnosis_source_context_included": diag.source_context_included,
        "p3_diagnosis_cloud_ready": diag.cloud_ready,
        "p3_diagnosis_cloud_call_invoked": diag.cloud_call_invoked,
        "p3_diagnosis_runtime_behavior_changed": diag.runtime_behavior_changed,
        "p3_diagnosis_claim_eligible": diag.claim_eligible,
        "p3_diagnosis_public_claim_allowed": diag.public_claim_allowed,
        "p3_diagnosis_reason": diag.reason,
    }
