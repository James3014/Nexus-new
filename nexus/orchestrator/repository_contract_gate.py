"""Deterministic repository-policy evidence for verified candidates."""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path
from typing import Mapping, Optional

from nexus.orchestrator.task_contract import SelfHostedTaskContract
from nexus.orchestrator.worktree_manager import (
    CandidateDiffReceipt,
    TargetWorktreeLease,
    WorktreeManager,
)


@dataclass(frozen=True)
class RepositoryContractFinding:
    kind: str
    severity: str
    path: str = ""
    message: str = ""
    evidence: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class RepositoryContractGateReceipt:
    passed: bool
    mode: str
    policy_revision_hash: str
    findings: tuple[RepositoryContractFinding, ...]
    blocking_reasons: tuple[str, ...] = ()


class RepositoryContractGate:
    """Shadow repository contract gate with fail-closed policy self-modification."""

    MODE = "shadow"
    POLICY_SCHEMA = "nexus.repository_contract_policy.v1"
    AGENT_AUTHORITY_PATHS = ("AGENTS.md", "MUSE_PROTO.md")
    GENERATED_FACTS_PATH = "docs/arch/module-inventory.generated.json"
    CI_WORKFLOW_PREFIX = ".github/workflows/"

    def __init__(self, worktree_manager: WorktreeManager):
        self.worktree_manager = worktree_manager

    def evaluate(
        self,
        contract: SelfHostedTaskContract,
        lease: TargetWorktreeLease,
        candidate: CandidateDiffReceipt,
        current: CandidateDiffReceipt,
    ) -> RepositoryContractGateReceipt:
        target = Path(lease.target_worktree).resolve()
        base_inputs = self._policy_input_hashes(target, contract.target_base_revision)
        policy_revision_hash = self._policy_revision_hash(
            contract.target_base_revision,
            base_inputs,
        )
        findings: list[RepositoryContractFinding] = []
        blocking_reasons: list[str] = []
        candidate_paths = sorted(
            set(current.changed_files)
            | set(current.untracked_files)
            | set(current.deleted_files)
        )

        findings.extend(self._authority_drift_findings(candidate_paths, base_inputs))

        if not contract.verifier_commands:
            findings.append(
                RepositoryContractFinding(
                    kind="declared_test_verifier_absent",
                    severity="shadow",
                    message="contract.verifier_commands is empty",
                    evidence={
                        "task_id": contract.task_id,
                        "contract_hash": contract.contract_hash,
                    },
                )
            )

        for path in current.deleted_files:
            findings.append(
                RepositoryContractFinding(
                    kind="tracked_deletion",
                    severity="shadow",
                    path=path,
                    message="candidate deletes a tracked base-revision path",
                    evidence={
                        "candidate_state_hash": current.candidate_state_hash,
                        "target_base_revision": contract.target_base_revision,
                    },
                )
            )

        findings.extend(
            self._lineage_mismatch_findings(
                contract=contract,
                lease=lease,
                candidate=candidate,
                current=current,
            )
        )

        for path in candidate_paths:
            if path in base_inputs and self._is_policy_path(path):
                reason = f"repository_contract_self_modification:{path}"
                blocking_reasons.append(reason)
                findings.append(
                    RepositoryContractFinding(
                        kind="policy_self_modification",
                        severity="blocking",
                        path=path,
                        message=(
                            "candidate modifies a base-revision policy input "
                            "used for verification"
                        ),
                        evidence={
                            "policy_revision_hash": policy_revision_hash,
                            "target_base_revision": contract.target_base_revision,
                            "base_input_sha256": base_inputs[path],
                        },
                    )
                )

        return RepositoryContractGateReceipt(
            passed=not blocking_reasons,
            mode=self.MODE,
            policy_revision_hash=policy_revision_hash,
            findings=tuple(sorted(findings, key=self._finding_sort_key)),
            blocking_reasons=tuple(sorted(blocking_reasons)),
        )

    def _policy_input_hashes(self, target: Path, base_revision: str) -> dict[str, str]:
        paths: set[str] = set()
        for path in (*self.AGENT_AUTHORITY_PATHS, self.GENERATED_FACTS_PATH):
            if self._base_path_exists(target, base_revision, path):
                paths.add(path)
        for path in self._base_workflow_paths(target, base_revision):
            paths.add(path)
        return {
            path: hashlib.sha256(
                self.worktree_manager._run_git_bytes(
                    ["show", f"{base_revision}:{path}"],
                    cwd=target,
                )
            ).hexdigest()
            for path in sorted(paths)
        }

    def _base_path_exists(self, target: Path, base_revision: str, path: str) -> bool:
        try:
            self.worktree_manager._run_git(
                ["cat-file", "-e", f"{base_revision}:{path}"],
                cwd=target,
            )
        except RuntimeError:
            return False
        return True

    def _base_workflow_paths(self, target: Path, base_revision: str) -> tuple[str, ...]:
        try:
            output = self.worktree_manager._run_git(
                [
                    "ls-tree",
                    "-r",
                    "--name-only",
                    base_revision,
                    "--",
                    self.CI_WORKFLOW_PREFIX,
                ],
                cwd=target,
            )
        except RuntimeError:
            return ()
        return tuple(path for path in output.splitlines() if path)

    def _policy_revision_hash(
        self,
        base_revision: str,
        base_inputs: Mapping[str, str],
    ) -> str:
        payload = {
            "schema": self.POLICY_SCHEMA,
            "target_base_revision": base_revision,
            "policy_inputs": [
                {"path": path, "sha256": base_inputs[path]}
                for path in sorted(base_inputs)
            ],
        }
        canonical = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(canonical).hexdigest()

    def _authority_drift_findings(
        self,
        candidate_paths: list[str],
        base_inputs: Mapping[str, str],
    ) -> tuple[RepositoryContractFinding, ...]:
        findings: list[RepositoryContractFinding] = []
        for path in candidate_paths:
            kind = self._drift_kind(path)
            if kind is None:
                continue
            findings.append(
                RepositoryContractFinding(
                    kind=kind,
                    severity="shadow",
                    path=path,
                    message="candidate changes repository authority surface",
                    evidence={
                        "base_policy_input": str(path in base_inputs).lower(),
                        "base_input_sha256": base_inputs.get(path, ""),
                    },
                )
            )
        return tuple(findings)

    def _lineage_mismatch_findings(
        self,
        *,
        contract: SelfHostedTaskContract,
        lease: TargetWorktreeLease,
        candidate: CandidateDiffReceipt,
        current: CandidateDiffReceipt,
    ) -> tuple[RepositoryContractFinding, ...]:
        expected = {
            "task_id": contract.task_id,
            "contract_hash": contract.contract_hash,
            "lease_id": lease.lease_id,
            "controller_revision": contract.controller_revision,
            "target_base_revision": contract.target_base_revision,
            "target_head": current.target_head,
            "candidate_state_hash": current.candidate_state_hash,
        }
        actual = {
            "task_id": candidate.task_id,
            "contract_hash": candidate.contract_hash,
            "lease_id": candidate.lease_id,
            "controller_revision": candidate.controller_revision,
            "target_base_revision": candidate.target_base_revision,
            "target_head": candidate.target_head,
            "candidate_state_hash": candidate.candidate_state_hash,
        }
        return tuple(
            RepositoryContractFinding(
                kind="candidate_lineage_mismatch",
                severity="shadow",
                message=f"candidate receipt field mismatch: {field_name}",
                evidence={
                    "field": field_name,
                    "expected": expected_value,
                    "actual": actual[field_name],
                },
            )
            for field_name, expected_value in sorted(expected.items())
            if actual[field_name] != expected_value
        )

    @classmethod
    def _drift_kind(cls, path: str) -> Optional[str]:
        if path in cls.AGENT_AUTHORITY_PATHS:
            return "agent_instruction_authority_drift"
        if path.startswith(cls.CI_WORKFLOW_PREFIX):
            return "ci_workflow_authority_drift"
        if path == cls.GENERATED_FACTS_PATH:
            return "generated_facts_authority_drift"
        return None

    @classmethod
    def _is_policy_path(cls, path: str) -> bool:
        return cls._drift_kind(path) is not None

    @staticmethod
    def _finding_sort_key(finding: RepositoryContractFinding) -> tuple[str, str, str]:
        return (
            finding.kind,
            finding.path,
            json.dumps(dict(finding.evidence), sort_keys=True),
        )
