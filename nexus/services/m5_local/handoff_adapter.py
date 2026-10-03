"""Local-to-Online handoff adapter (reusing Runtime#45 and Issue#1266 semantics).

Generates an ephemeral handoff input projection when a local attempt cannot complete
and requires Online reasoning or escalation. Consumed by the external coordinator
and canonical Runtime #45 handoff authority.

Guarantees:
- Carries forward predecessor attempt, repo base, inspected paths, and evidence refs.
- Online successor does not need to re-discover the whole task from scratch.
- Missing predecessor evidence fails closed.
- Stale base or un-reconciled local effects block successor continuation.
"""

from __future__ import annotations

from typing import Optional, Sequence

from .contracts import (
    M5_LOCAL_HANDOFF_SCHEMA,
    HandoffContractError,
    HandoffPacket,
    LocalAssistResponse,
    LocalWorkerResponse,
)


def create_handoff_from_assist(
    *,
    task_id: str,
    work_id: str,
    predecessor_attempt_id: str,
    predecessor_operation_id: str,
    repo_identity: str,
    base_sha: str,
    assist_response: LocalAssistResponse,
    unresolved_question: str,
    remaining_gate: str = "ONLINE_REASONING_REQUIRED",
) -> HandoffPacket:
    """Create an ephemeral handoff input packet from an escalated or partial Local Assist attempt."""
    if not task_id or not predecessor_attempt_id:
        raise HandoffContractError("Handoff requires non-empty task_id and predecessor_attempt_id")
    if not repo_identity or not base_sha:
        raise HandoffContractError("Handoff requires valid repo_identity and base_sha")

    escalation_reason = assist_response.escalation_reason or "LOCAL_RESULT_INSUFFICIENT"

    return HandoffPacket(
        schema=M5_LOCAL_HANDOFF_SCHEMA,
        task_id=task_id,
        work_id=work_id,
        predecessor_attempt_id=predecessor_attempt_id,
        predecessor_operation_id=predecessor_operation_id,
        transition_type="LOCAL_TO_ONLINE",
        repo_identity=repo_identity,
        base_sha=base_sha,
        inspected_paths=list(assist_response.candidate_files),
        evidence_refs=list(assist_response.evidence_refs),
        tests_executed=[],
        diff="",
        unknown_effects=[],
        unresolved_questions=[unresolved_question] if unresolved_question else [],
        escalation_reason=escalation_reason,
        remaining_gate=remaining_gate,
    )


def create_handoff_from_worker(
    *,
    task_id: str,
    work_id: str,
    predecessor_attempt_id: str,
    predecessor_operation_id: str,
    repo_identity: str,
    base_sha: str,
    worker_response: LocalWorkerResponse,
    unresolved_question: str,
    tests_executed: Optional[Sequence[str]] = None,
    remaining_gate: str = "ONLINE_MUTATION_REQUIRED",
) -> HandoffPacket:
    """Create an ephemeral handoff input packet from an escalated Local Worker attempt."""
    if not task_id or not predecessor_attempt_id:
        raise HandoffContractError("Handoff requires non-empty task_id and predecessor_attempt_id")
    if not repo_identity or not base_sha:
        raise HandoffContractError("Handoff requires valid repo_identity and base_sha")

    # Invariant: If worker produced mutation, unresolved effects must be documented
    unknown_effects = []
    if worker_response.status in ("FAILED", "TIMEOUT") and worker_response.write_performed:
        unknown_effects.append(f"UNRESOLVED_WRITER_EFFECT:{predecessor_operation_id}")

    return HandoffPacket(
        schema=M5_LOCAL_HANDOFF_SCHEMA,
        task_id=task_id,
        work_id=work_id,
        predecessor_attempt_id=predecessor_attempt_id,
        predecessor_operation_id=predecessor_operation_id,
        transition_type="LOCAL_TO_ONLINE",
        repo_identity=repo_identity,
        base_sha=base_sha,
        inspected_paths=list(worker_response.touched_paths),
        evidence_refs=[f"op:{worker_response.operation_id}"],
        tests_executed=list(tests_executed or []),
        diff=worker_response.diff,
        unknown_effects=unknown_effects,
        unresolved_questions=[unresolved_question] if unresolved_question else [],
        escalation_reason=worker_response.escalation_reason or "LOCAL_WORKER_ESCALATED",
        remaining_gate=remaining_gate,
    )
