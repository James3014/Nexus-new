"""Provider-neutral contract for governed self-hosted workers."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional, Protocol, Any


SUPPORTED_WORKER_PROVIDERS = ("codex", "gemini", "agy", "opencode", "mimo", "ollama")


class WorkerOutcome(str, Enum):
    PROVEN = "PROVEN"
    EXECUTION_COMPLETED = "EXECUTION_COMPLETED"
    INCOMPLETE = "INCOMPLETE"
    FAILED = "FAILED"


class AttemptResolutionVerdict(str, Enum):
    PROVEN = "PROVEN"
    INCOMPLETE = "INCOMPLETE"
    FAILED = "FAILED"


@dataclass(frozen=True)
class AttemptResolutionReceipt:
    task_id: str
    provider: str
    execution_outcome: str
    candidate_state_hash: str
    verdict: str
    candidate_non_empty: bool
    execution_completed: bool
    evidence_complete: bool
    verified: bool
    scope_gate_passed: bool
    deletion_gate_passed: bool
    controller_gate_passed: bool
    protected_contract_gate_passed: bool
    verifier_gate_passed: bool
    escalation_allowed: bool
    failure_reasons: tuple[str, ...] = ()


def _is_candidate_non_empty(candidate: Any) -> bool:
    if hasattr(candidate, "is_empty") and candidate.is_empty is not None:
        return not bool(candidate.is_empty)
    if hasattr(candidate, "has_changes") and candidate.has_changes is not None:
        return bool(candidate.has_changes)
    changed = getattr(candidate, "changed_files", None)
    untracked = getattr(candidate, "untracked_files", None)
    deleted = getattr(candidate, "deleted_files", None)
    if changed is not None or untracked is not None or deleted is not None:
        return bool(
            (changed and len(changed) > 0)
            or (untracked and len(untracked) > 0)
            or (deleted and len(deleted) > 0)
        )
    return False



def resolve_attempt(
    execution: WorkerExecutionReceipt,
    candidate: Any,
    verified: Any,
) -> AttemptResolutionReceipt:
    execution_completed = (
        execution.outcome
        in (
            WorkerOutcome.EXECUTION_COMPLETED.value,
            WorkerOutcome.EXECUTION_COMPLETED,
        )
    )
    evidence_complete = bool(execution.evidence_complete)
    candidate_non_empty = _is_candidate_non_empty(candidate)

    verified_flag = bool(getattr(verified, "verified", False))
    scope_gate_passed = bool(getattr(verified, "scope_gate_passed", False))
    deletion_gate_passed = bool(getattr(verified, "deletion_gate_passed", False))
    controller_gate_passed = bool(getattr(verified, "controller_gate_passed", False))
    protected_contract_gate_passed = bool(
        getattr(verified, "protected_contract_gate_passed", False)
    )
    verifier_gate_passed = bool(getattr(verified, "verifier_gate_passed", False))

    reasons: list[str] = []

    is_timeout = bool(execution.timed_out) or execution.outcome in (
        WorkerOutcome.INCOMPLETE.value,
        WorkerOutcome.INCOMPLETE,
    )

    if not execution_completed:
        reasons.append(f"execution outcome is {execution.outcome}")
    if not evidence_complete:
        reasons.append("execution evidence is incomplete")
    if not candidate_non_empty:
        reasons.append("candidate diff is empty")
    if not verified_flag:
        reasons.append("candidate verification failed")

    vf_reasons = getattr(verified, "failure_reasons", ())
    if vf_reasons:
        for r in vf_reasons:
            if r not in reasons:
                reasons.append(str(r))

    if not scope_gate_passed and "scope_gate_failed" not in reasons:
        reasons.append("scope_gate_failed")
    if not deletion_gate_passed and "deletion_gate_failed" not in reasons:
        reasons.append("deletion_gate_failed")
    if not controller_gate_passed and "controller_gate_failed" not in reasons:
        reasons.append("controller_gate_failed")
    if not protected_contract_gate_passed and "protected_contract_gate_failed" not in reasons:
        reasons.append("protected_contract_gate_failed")
    if not verifier_gate_passed and "verifier_gate_failed" not in reasons:
        reasons.append("verifier_gate_failed")

    all_gates_pass = (
        execution_completed
        and evidence_complete
        and candidate_non_empty
        and verified_flag
        and scope_gate_passed
        and deletion_gate_passed
        and controller_gate_passed
        and protected_contract_gate_passed
        and verifier_gate_passed
    )

    if all_gates_pass:
        verdict = AttemptResolutionVerdict.PROVEN.value
        reasons = []
    elif is_timeout and not execution_completed:
        verdict = AttemptResolutionVerdict.INCOMPLETE.value
    else:
        verdict = AttemptResolutionVerdict.FAILED.value

    escalation_allowed = (verdict == AttemptResolutionVerdict.INCOMPLETE.value)

    return AttemptResolutionReceipt(
        task_id=str(getattr(execution, "task_id", "")),
        provider=str(getattr(execution, "provider", "")),
        execution_outcome=str(getattr(execution, "outcome", "")),
        candidate_state_hash=str(getattr(candidate, "candidate_state_hash", "")),
        verdict=verdict,
        candidate_non_empty=candidate_non_empty,
        execution_completed=execution_completed,
        evidence_complete=evidence_complete,
        verified=verified_flag,
        scope_gate_passed=scope_gate_passed,
        deletion_gate_passed=deletion_gate_passed,
        controller_gate_passed=controller_gate_passed,
        protected_contract_gate_passed=protected_contract_gate_passed,
        verifier_gate_passed=verifier_gate_passed,
        escalation_allowed=escalation_allowed,
        failure_reasons=tuple(reasons),
    )



@dataclass(frozen=True)
class WorkerPreflight:
    provider: str
    executable: Optional[str]
    executable_available: bool
    authorized: bool
    implementation_status: str
    ready: bool
    reason: str


@dataclass(frozen=True)
class WorkerExecutionReceipt:
    provider: str
    task_id: str
    target_worktree: str
    worker_status: str
    outcome: str
    exit_code: Optional[int]
    executable_identity: str
    argv: tuple[str, ...]
    stdout_sha256: str
    stderr_sha256: str
    wall_time_ms: int
    process_group_id: Optional[int]
    process_group_killed: bool
    timed_out: bool
    provider_calls: int
    evidence_complete: bool
    commit_created: bool
    merge_performed: bool
    push_performed: bool
    failure_reason: Optional[str] = None


class WorkerProviderUnavailable(RuntimeError):
    """Raised when a provider is known but cannot be invoked safely."""


class WorkerAdapter(Protocol):
    provider: str

    def preflight(self) -> WorkerPreflight:
        ...

    def invoke(
        self,
        contract: Any,
        lease: Any,
        *,
        prompt: str,
        **options: Any,
    ) -> WorkerExecutionReceipt:
        ...
