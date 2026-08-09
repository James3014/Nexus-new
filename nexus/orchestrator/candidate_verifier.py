"""Fail-closed gates for converting a raw candidate diff into verified evidence."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
import shlex
import time
from pathlib import Path
from typing import Mapping, Optional

from nexus.executors.cli_worker import (
    CliWorkerRequest,
    CliWorkerResult,
    CliWorkerStatus,
    bounded_environment_receipt,
    run_cli_worker,
)
from nexus.orchestrator.repository_contract_gate import (
    RepositoryContractFinding,
    RepositoryContractGate,
)
from nexus.orchestrator.task_contract import SelfHostedTaskContract
from nexus.orchestrator.worktree_manager import CandidateDiffReceipt, TargetWorktreeLease, WorktreeManager


_VERIFIER_ENV_ALLOWLIST = frozenset({"PYTHONDONTWRITEBYTECODE"})


@dataclass(frozen=True)
class VerifierEvidence:
    command: str
    status: str
    exit_code: Optional[int]
    stdout_sha256: str
    stderr_sha256: str
    wall_time_ms: int
    executable_identity: str = ""
    executable_sha256: str = ""
    argv: tuple[str, ...] = ()
    env: tuple[tuple[str, str], ...] = ()
    cwd: str = ""
    process_group_id: Optional[int] = None
    process_group_killed: bool = False
    timed_out: bool = False


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
    candidate_commit_allowed: bool
    public_claim_allowed: bool
    production_ready: bool
    failure_reasons: list[str]
    verifier_evidence: tuple[VerifierEvidence, ...]
    candidate_commit_created: bool
    merge_performed: bool
    authorized_deletions: tuple[str, ...] = ()
    authorized_deletions_hash: str = ""
    repository_contract_gate_passed: bool = True
    repository_contract_mode: str = "enforced"
    repository_contract_policy_revision_hash: str = ""
    repository_contract_findings: tuple[RepositoryContractFinding, ...] = ()
    verifier_manifest_sha256: str = ""
    verification_wall_time_ms: int = 0
    authority_change_required: bool = False
    authority_findings_sha256: str = ""


class CandidateVerifier:
    VERIFIER_TIMEOUT_SECONDS = 300.0

    def __init__(self, worktree_manager: WorktreeManager):
        self.worktree_manager = worktree_manager

    @staticmethod
    def validate_static_contract(contract: SelfHostedTaskContract, target: str = ".") -> None:
        """Validate verifier/contract inputs without touching the candidate or invoking a provider.

        This is intentionally a pure preflight gate.  In particular, command
        tokenization is performed here so malformed shlex input (including an
        unmatched quote) fails before a worker subprocess can be started.
        """
        allowed = getattr(contract, "allowed_files", None)
        if not isinstance(allowed, (list, tuple)) or not allowed or any(
            not isinstance(path, str) or not path.strip() for path in allowed
        ):
            raise ValueError("invalid task contract allowed_files")
        commands = getattr(contract, "verifier_commands", None)
        if not isinstance(commands, (list, tuple)):
            raise ValueError("invalid verifier command manifest")
        try:
            deduplicated = CandidateVerifier._deduplicate_verifier_commands(tuple(str(item) for item in commands))
            request_target = target if Path(target).is_dir() else "."
            for command in deduplicated:
                CandidateVerifier._build_verifier_request(command, request_target)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"invalid verifier contract: {exc}") from exc

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
    def _build_verifier_request(command: str, target: str) -> CliWorkerRequest:
        try:
            lexer = shlex.shlex(command, posix=True, punctuation_chars=";&|<>")
            lexer.whitespace_split = True
            tokens = tuple(lexer)
        except ValueError as exc:
            raise ValueError(f"malformed verifier command: {exc}") from exc
        if not tokens:
            raise ValueError("verifier command must contain an executable")
        assignments: dict[str, str] = {}
        assignment_pattern = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)=(.*)$")
        index = 0
        while index < len(tokens):
            token = tokens[index]
            match = assignment_pattern.fullmatch(token)
            if match is None:
                if "=" in token and index == 0:
                    raise ValueError("malformed environment assignment")
                break
            name, value = match.groups()
            if any(char in value for char in "\x00\r\n;&|<>()$`"):
                raise ValueError("invalid environment assignment value")
            if name not in _VERIFIER_ENV_ALLOWLIST:
                raise ValueError(f"unsupported verifier environment variable: {name}")
            if name in assignments and assignments[name] != value:
                raise ValueError(f"conflicting duplicate environment assignment: {name}")
            assignments[name] = value
            index += 1
        if index >= len(tokens):
            raise ValueError("verifier command must contain an executable")
        executable = tokens[index]
        if (
            executable in {";", "&&", "||", "|", "<", ">"}
            or not executable.strip()
            or executable.startswith("-")
        ):
            raise ValueError("verifier command must contain a safe executable")
        executable_path = Path(executable)
        if ".." in executable_path.parts:
            raise ValueError("verifier executable path traversal is not allowed")
        if not executable_path.is_absolute() and len(executable_path.parts) > 1:
            executable = str(Path(target).resolve() / executable_path)
        if any(token in {";", "&&", "||", "|", "<", ">"} for token in tokens[index + 1:]):
            raise ValueError("shell operators are not allowed in verifier command")
        verifier_args = tokens[index + 1 :]
        for arg_index, token in enumerate(verifier_args):
            if re.search(r"[\x00\r\n]", token):
                raise ValueError("invalid verifier argument")
            if any(char in token for char in ";&|<>()$`") and not (
                arg_index > 0 and verifier_args[arg_index - 1] == "-c"
            ):
                raise ValueError("shell metacharacters are not allowed in verifier arguments")
        for token in verifier_args:
            if assignment_pattern.fullmatch(token):
                raise ValueError("environment assignments must precede executable")
        if "PYTHONDONTWRITEBYTECODE" in assignments and assignments["PYTHONDONTWRITEBYTECODE"] != "1":
            raise ValueError("PYTHONDONTWRITEBYTECODE must be 1")
        assignments.setdefault("PYTHONDONTWRITEBYTECODE", "1")
        return CliWorkerRequest(
            executable=executable,
            argv=tokens[index + 1 :],
            cwd=target,
            timeout_seconds=CandidateVerifier.VERIFIER_TIMEOUT_SECONDS,
            env=assignments,
        )

    @staticmethod
    def _executable_sha256(executable_identity: str) -> str:
        return hashlib.sha256(Path(executable_identity).read_bytes()).hexdigest()

    @staticmethod
    def _evidence_consistency_failures(
        request: CliWorkerRequest,
        result: CliWorkerResult,
    ) -> list[str]:
        failures: list[str] = []
        if result.executable_identity != request.executable:
            failures.append("executable_identity_mismatch")
        if not result.executable_sha256:
            failures.append("executable_sha256_missing")
        else:
            try:
                expected_sha256 = CandidateVerifier._executable_sha256(request.executable)
            except OSError:
                failures.append("executable_sha256_unreadable")
            else:
                if result.executable_sha256 != expected_sha256:
                    failures.append("executable_sha256_mismatch")
        if result.argv != request.argv:
            failures.append("argv_mismatch")
        expected_env = bounded_environment_receipt(request.env)
        if result.env != expected_env:
            failures.append("env_mismatch")
        if result.cwd != request.cwd:
            failures.append("cwd_mismatch")
        if result.timed_out != (result.status is CliWorkerStatus.TIMED_OUT):
            failures.append("timeout_status_mismatch")
        if result.status is CliWorkerStatus.TIMED_OUT and not result.process_group_killed:
            failures.append("timeout_without_process_group_kill")
        if result.status is CliWorkerStatus.COMPLETED and result.process_group_killed:
            failures.append("process_group_killed_without_timeout")
        if result.status is not CliWorkerStatus.START_FAILED and result.process_group_id is None:
            failures.append("process_group_id_missing")
        return failures

    @staticmethod
    def _run_verifiers(contract: SelfHostedTaskContract, target: str) -> tuple[bool, tuple[VerifierEvidence, ...], list[str]]:
        evidence: list[VerifierEvidence] = []
        failures: list[str] = []
        for command in CandidateVerifier._deduplicate_verifier_commands(contract.verifier_commands):
            try:
                request = CandidateVerifier._build_verifier_request(command, target)
                result = run_cli_worker(request)
                evidence.append(
                    VerifierEvidence(
                        command=command,
                        status=result.status.value,
                        exit_code=result.exit_code,
                        stdout_sha256=result.stdout_sha256,
                        stderr_sha256=result.stderr_sha256,
                        wall_time_ms=result.wall_time_ms,
                        executable_identity=result.executable_identity,
                        executable_sha256=result.executable_sha256,
                        argv=result.argv,
                        env=result.env,
                        cwd=result.cwd,
                        process_group_id=result.process_group_id,
                        process_group_killed=result.process_group_killed,
                        timed_out=result.timed_out,
                    )
                )
                consistency_failures = CandidateVerifier._evidence_consistency_failures(request, result)
                if consistency_failures:
                    failures.append(f"verifier_evidence_inconsistent:{command}:{','.join(consistency_failures)}")
                if result.status is not CliWorkerStatus.COMPLETED or result.exit_code != 0:
                    failures.append(f"verifier_failed:{command}")
            except (OSError, ValueError) as exc:
                failures.append(f"verifier_invalid:{command}:{exc}")
        return not failures, tuple(evidence), failures

    @staticmethod
    def _deduplicate_verifier_commands(commands: tuple[str, ...]) -> tuple[str, ...]:
        """Merge overlapping pytest manifests while preserving other commands."""
        ordered: list[tuple[str, object]] = []
        pytest_groups: dict[tuple[str, ...], list[str]] = {}
        for command in commands:
            tokens = shlex.split(command)
            try:
                module_index = tokens.index("-m")
                if tokens[module_index + 1] != "pytest":
                    raise ValueError
            except (ValueError, IndexError):
                ordered.append(("plain", command))
                continue
            tail = tokens[module_index + 2:]
            first_test = next(
                (
                    index for index, token in enumerate(tail)
                    if token.startswith("tests/") or ("/tests/" in token and token.endswith(".py"))
                ),
                None,
            )
            if first_test is None:
                ordered.append(("plain", command))
                continue
            prefix = tuple(tokens[:module_index + 2]) + tuple(tail[:first_test])
            test_paths = tuple(tail[first_test:])
            if prefix not in pytest_groups:
                pytest_groups[prefix] = []
                ordered.append(("pytest", prefix))
            for path in test_paths:
                if path not in pytest_groups[prefix]:
                    pytest_groups[prefix].append(path)
        rendered: list[str] = []
        for kind, value in ordered:
            if kind == "plain":
                rendered.append(str(value))
            else:
                prefix = value  # type: ignore[assignment]
                rendered.append(" ".join(shlex.quote(token) for token in (*prefix, *pytest_groups[prefix])))
        return tuple(rendered)

    def verify(
        self,
        contract: SelfHostedTaskContract,
        lease: TargetWorktreeLease,
        candidate: CandidateDiffReceipt,
        *,
        protected_paths: Optional[Mapping[str, str]] = None,
    ) -> VerifiedCandidateReceipt:
        verification_started = time.monotonic()
        if candidate.contract_hash != contract.contract_hash:
            raise RuntimeError("candidate contract hash does not match current authorization contract")
        current = self.worktree_manager.capture_candidate(contract, lease)
        if current.candidate_state_hash != candidate.candidate_state_hash:
            raise RuntimeError("candidate state changed before verification")
        verifier_passed, verifier_evidence, verifier_failures = self._run_verifiers(
            contract,
            lease.target_worktree,
        )
        post_verifier = self.worktree_manager.capture_candidate(contract, lease)
        verifier_state_failures: list[str] = []
        if post_verifier.candidate_state_hash != current.candidate_state_hash:
            verifier_state_failures.append("verifier_mutated_candidate_state")

        scope_passed = post_verifier.allowed_scope_passed
        authorized_deletions = tuple(sorted(set(contract.authorized_deletions)))
        unauthorized_deletions = sorted(
            set(post_verifier.deleted_files) - set(authorized_deletions)
        )
        deletion_failures = [f"undeclared_deletion:{path}" for path in unauthorized_deletions]
        deletion_passed = not deletion_failures
        controller_passed = post_verifier.controller_unchanged
        protected_passed, protected_failures = self._protected_gate(
            post_verifier,
            protected_paths or {},
        )
        repository_contract = RepositoryContractGate(self.worktree_manager).evaluate(
            contract=contract,
            lease=lease,
            candidate=candidate,
            current=post_verifier,
        )
        failures: list[str] = []
        if not scope_passed:
            failures.append("scope_gate_failed")
        if not deletion_passed:
            failures.extend(deletion_failures)
            failures.append("deletion_gate_failed")
        if not controller_passed:
            failures.append("controller_gate_failed")
        failures.extend(protected_failures)
        failures.extend(verifier_failures)
        failures.extend(verifier_state_failures)
        failures.extend(repository_contract.blocking_reasons)
        verified = not failures
        verifier_manifest = tuple(CandidateVerifier._deduplicate_verifier_commands(contract.verifier_commands))
        return VerifiedCandidateReceipt(
            schema="nexus.verified_candidate_receipt.v1",
            task_id=contract.task_id,
            contract_hash=contract.contract_hash,
            lease_id=lease.lease_id,
            candidate_state_hash=post_verifier.candidate_state_hash,
            scope_gate_passed=scope_passed,
            deletion_gate_passed=deletion_passed,
            controller_gate_passed=controller_passed,
            protected_contract_gate_passed=protected_passed,
            verifier_gate_passed=verifier_passed,
            verified=verified,
            candidate_commit_allowed=verified,
            public_claim_allowed=False,
            production_ready=False,
            failure_reasons=failures,
            verifier_evidence=verifier_evidence,
            candidate_commit_created=False,
            merge_performed=False,
            authorized_deletions=authorized_deletions,
            authorized_deletions_hash=hashlib.sha256(
                json.dumps(authorized_deletions, separators=(",", ":")).encode("utf-8")
            ).hexdigest(),
            repository_contract_gate_passed=repository_contract.passed,
            repository_contract_mode=repository_contract.mode,
            repository_contract_policy_revision_hash=repository_contract.policy_revision_hash,
            repository_contract_findings=repository_contract.findings,
            authority_change_required=repository_contract.authority_change_required,
            authority_findings_sha256=repository_contract.authority_findings_sha256,
            verifier_manifest_sha256=hashlib.sha256(
                json.dumps(verifier_manifest, separators=(",", ":")).encode("utf-8")
            ).hexdigest(),
            verification_wall_time_ms=max(0, int((time.monotonic() - verification_started) * 1000)),
        )
