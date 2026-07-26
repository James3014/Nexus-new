"""Fail-closed gates for converting a raw candidate diff into verified evidence."""

from __future__ import annotations

from dataclasses import dataclass
import shlex
from pathlib import Path
from typing import Mapping, Optional

from nexus.executors.cli_worker import CliWorkerRequest, CliWorkerStatus, run_cli_worker
from nexus.orchestrator.task_contract import SelfHostedTaskContract
from nexus.orchestrator.worktree_manager import CandidateDiffReceipt, TargetWorktreeLease, WorktreeManager


@dataclass(frozen=True)
class VerifierEvidence:
    command: str
    status: str
    exit_code: Optional[int]
    stdout_sha256: str
    stderr_sha256: str
    wall_time_ms: int


@dataclass(frozen=True)
class VerifiedCandidateReceipt:
    schema: str
    task_id: str
    contract_hash: str
    lease_id: str
    candidate_state_hash: str
    scope_gate_passed: bool
    deletion_gate_passed: bool
    controller_gate_passed: bool
    protected_contract_gate_passed: bool
    verifier_gate_passed: bool
    verified: bool
    public_claim_allowed: bool
    failure_reasons: list[str]
    verifier_evidence: tuple[VerifierEvidence, ...]
    candidate_commit_created: bool
    merge_performed: bool


class CandidateVerifier:
    def __init__(self, worktree_manager: WorktreeManager):
        self.worktree_manager = worktree_manager

    @staticmethod
    def _protected_gate(
        candidate: CandidateDiffReceipt,
        protected_paths: Mapping[str, str],
    ) -> tuple[bool, list[str]]:
        candidate_paths = set(candidate.changed_files) | set(candidate.untracked_files) | set(candidate.deleted_files)
        failures = [
            f"protected_contract_changed:{path}"
            for path in sorted(candidate_paths)
            if path in protected_paths
        ]
        return not failures, failures

    @staticmethod
    def _run_verifiers(contract: SelfHostedTaskContract, target: str) -> tuple[bool, tuple[VerifierEvidence, ...], list[str]]:
        evidence: list[VerifierEvidence] = []
        failures: list[str] = []
        for command in contract.verifier_commands:
            try:
                tokens = tuple(shlex.split(command))
                if len(tokens) < 2:
                    raise ValueError("verifier command must contain executable and argv")
                result = run_cli_worker(
                    CliWorkerRequest(
                        executable=tokens[0],
                        argv=tokens[1:],
                        cwd=target,
                        timeout_seconds=300.0,
                        env={"PYTHONDONTWRITEBYTECODE": "1"},
                    )
                )
                evidence.append(
                    VerifierEvidence(
                        command=command,
                        status=result.status.value,
                        exit_code=result.exit_code,
                        stdout_sha256=result.stdout_sha256,
                        stderr_sha256=result.stderr_sha256,
                        wall_time_ms=result.wall_time_ms,
                    )
                )
                if result.status is not CliWorkerStatus.COMPLETED or result.exit_code != 0:
                    failures.append(f"verifier_failed:{command}")
            except (OSError, ValueError) as exc:
                failures.append(f"verifier_invalid:{command}:{exc}")
        return not failures, tuple(evidence), failures

    def verify(
        self,
        contract: SelfHostedTaskContract,
        lease: TargetWorktreeLease,
        candidate: CandidateDiffReceipt,
        *,
        protected_paths: Optional[Mapping[str, str]] = None,
    ) -> VerifiedCandidateReceipt:
        current = self.worktree_manager.capture_candidate(contract, lease)
        if current.candidate_state_hash != candidate.candidate_state_hash:
            raise RuntimeError("candidate state changed before verification")
        scope_passed = current.allowed_scope_passed
        deletion_passed = not current.deleted_files
        controller_passed = current.controller_unchanged
        protected_passed, protected_failures = self._protected_gate(current, protected_paths or {})
        verifier_passed, verifier_evidence, verifier_failures = self._run_verifiers(
            contract,
            lease.target_worktree,
        )
        failures: list[str] = []
        if not scope_passed:
            failures.append("scope_gate_failed")
        if not deletion_passed:
            failures.append("deletion_gate_failed")
        if not controller_passed:
            failures.append("controller_gate_failed")
        failures.extend(protected_failures)
        failures.extend(verifier_failures)
        verified = not failures
        return VerifiedCandidateReceipt(
            schema="nexus.verified_candidate_receipt.v1",
            task_id=contract.task_id,
            contract_hash=contract.contract_hash,
            lease_id=lease.lease_id,
            candidate_state_hash=current.candidate_state_hash,
            scope_gate_passed=scope_passed,
            deletion_gate_passed=deletion_passed,
            controller_gate_passed=controller_passed,
            protected_contract_gate_passed=protected_passed,
            verifier_gate_passed=verifier_passed,
            verified=verified,
            public_claim_allowed=verified,
            failure_reasons=failures,
            verifier_evidence=verifier_evidence,
            candidate_commit_created=False,
            merge_performed=False,
        )
