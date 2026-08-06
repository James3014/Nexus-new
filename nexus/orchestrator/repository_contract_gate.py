"""Deterministic repository-policy evidence for verified candidates."""

from __future__ import annotations

import ast
import hashlib
import json
from dataclasses import dataclass, field
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
    AUTHORITY_CHANGE_MARKER = "repository-authority-change.v1"
    EFFECTIVE_ROUTE_TOKENS = (
        "agent", "router", "wrapper", "planner", "controller", "gateway",
        "selector", "dispatcher",
    )
    AUTHORITY_PATH_TOKENS = (
        "orchestrator", "route", "router", "planner", "controller", "gateway",
        "selector", "dispatcher", "execution",
    )
    AUTHORITY_BRANCH_TOKENS = (
        "fallback", "dispatch", "routing", "route", "execution_lane",
        "execution_topology", "world", "routemode", "canonical_root",
        "state_root", "workspace_root", "source_root",
    )

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
        route_findings, route_blocking = self._effective_route_findings(
            target=target,
            contract=contract,
            candidate_paths=candidate_paths,
            current=current,
        )
        findings.extend(route_findings)
        blocking_reasons.extend(route_blocking)

        for field_name in ("target_head", "candidate_state_hash"):
            if getattr(candidate, field_name) != getattr(current, field_name):
                reason = f"integration_identity_recheck:{field_name}"
                blocking_reasons.append(reason)
                findings.append(
                    RepositoryContractFinding(
                        kind="integration_identity_recheck",
                        severity="blocking",
                        message="candidate identity changed between capture and integration-time recheck",
                        evidence={
                            "field": field_name,
                            "candidate": str(getattr(candidate, field_name)),
                            "current": str(getattr(current, field_name)),
                        },
                    )
                )

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

        freeze_findings, freeze_blocking = self._freeze_findings(
            target=target,
            contract=contract,
            candidate_paths=candidate_paths,
            deleted_files=list(current.deleted_files),
        )
        findings.extend(freeze_findings)
        blocking_reasons.extend(freeze_blocking)

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

    def evaluate_committed_candidate(
        self,
        *,
        contract: SelfHostedTaskContract,
        candidate_commit: str,
        candidate_tree_sha: str,
        expected_policy_revision_hash: str,
    ) -> RepositoryContractGateReceipt:
        """Re-evaluate the exact committed tree immediately before integration."""
        target = Path(contract.controller_repo_root).resolve()
        findings: list[RepositoryContractFinding] = []
        blocking_reasons: list[str] = []
        try:
            actual_commit = self.worktree_manager._run_git(
                ["rev-parse", f"{candidate_commit}^{{commit}}"], cwd=target
            )
            actual_tree = self.worktree_manager._run_git(
                ["rev-parse", f"{candidate_commit}^{{tree}}"], cwd=target
            )
        except RuntimeError:
            actual_commit = ""
            actual_tree = ""
        if actual_commit != candidate_commit or actual_tree != candidate_tree_sha:
            blocking_reasons.append("integration_candidate_identity_mismatch")
            findings.append(
                RepositoryContractFinding(
                    kind="integration_candidate_identity_mismatch",
                    severity="blocking",
                    message="integration candidate commit/tree no longer matches the verified packet",
                    evidence={
                        "expected_commit": candidate_commit,
                        "actual_commit": actual_commit,
                        "expected_tree": candidate_tree_sha,
                        "actual_tree": actual_tree,
                    },
                )
            )

        base_inputs = self._policy_input_hashes(target, contract.target_base_revision)
        policy_revision_hash = self._policy_revision_hash(
            contract.target_base_revision, base_inputs
        )
        if not expected_policy_revision_hash or policy_revision_hash != expected_policy_revision_hash:
            blocking_reasons.append("integration_repository_policy_revision_drift")
            findings.append(
                RepositoryContractFinding(
                    kind="integration_repository_policy_revision_drift",
                    severity="blocking",
                    message="repository contract policy revision differs from verification",
                    evidence={
                        "expected": expected_policy_revision_hash,
                        "actual": policy_revision_hash,
                    },
                )
            )

        try:
            name_status = self.worktree_manager._run_git(
                [
                    "diff",
                    "--find-renames",
                    "--find-copies",
                    "--name-status",
                    contract.target_base_revision,
                    candidate_commit,
                    "--",
                ],
                cwd=target,
            )
        except RuntimeError:
            name_status = ""
            blocking_reasons.append("integration_candidate_diff_unreadable")
        candidate_paths: list[str] = []
        deleted_files: list[str] = []
        for line in name_status.splitlines():
            parts = line.split("\t")
            if len(parts) < 2 or not parts[0]:
                blocking_reasons.append("integration_candidate_diff_malformed")
                continue
            status = parts[0]
            status_code = status[0]
            if status_code in {"R", "C"}:
                if len(parts) != 3:
                    blocking_reasons.append("integration_candidate_diff_malformed")
                    continue
                source_path, destination_path = parts[1], parts[2]
                candidate_paths.extend((source_path, destination_path))
                blocking_reasons.append(
                    "integration_candidate_rename_copy_forbidden:"
                    f"{source_path}->{destination_path}"
                )
                continue
            if len(parts) != 2 or status_code not in {"A", "D", "M", "T", "U", "X", "B"}:
                blocking_reasons.append("integration_candidate_diff_malformed")
                continue
            path = parts[1]
            candidate_paths.append(path)
            if status_code == "D":
                deleted_files.append(path)
        candidate_paths = sorted(set(candidate_paths))
        deleted_files = sorted(set(deleted_files))

        deleted_set = set(deleted_files)
        for path in candidate_paths:
            if path in deleted_set:
                continue
            try:
                self.worktree_manager._run_git(
                    ["cat-file", "-e", f"{candidate_commit}:{path}"], cwd=target
                )
            except RuntimeError:
                blocking_reasons.append(
                    f"integration_candidate_content_unreadable:{path}"
                )
                continue
            if path.endswith((".py", ".json", ".toml", ".yaml", ".yml")) and self._candidate_text(
                target=target,
                path=path,
                candidate_revision=candidate_commit,
            ) is None:
                blocking_reasons.append(
                    f"integration_candidate_content_unreadable:{path}"
                )

        out_of_scope = [
            path
            for path in candidate_paths
            if not self.worktree_manager._matches_any(path, contract.allowed_files)
            or self.worktree_manager._matches_any(path, contract.forbidden_files)
        ]
        for path in out_of_scope:
            blocking_reasons.append(f"integration_candidate_out_of_scope:{path}")
        for path in sorted(set(deleted_files) - set(contract.authorized_deletions)):
            blocking_reasons.append(f"integration_undeclared_deletion:{path}")

        findings.extend(self._authority_drift_findings(candidate_paths, base_inputs))
        route_findings, route_blocking = self._effective_route_findings(
            target=target,
            contract=contract,
            candidate_paths=candidate_paths,
            current=None,
            candidate_revision=candidate_commit,
        )
        findings.extend(route_findings)
        blocking_reasons.extend(route_blocking)
        freeze_findings, freeze_blocking = self._freeze_findings(
            target=target,
            contract=contract,
            candidate_paths=candidate_paths,
            deleted_files=deleted_files,
            candidate_revision=candidate_commit,
        )
        findings.extend(freeze_findings)
        blocking_reasons.extend(freeze_blocking)
        for path in candidate_paths:
            if path in base_inputs and self._is_policy_path(path):
                blocking_reasons.append(f"repository_contract_self_modification:{path}")

        return RepositoryContractGateReceipt(
            passed=not blocking_reasons,
            mode=self.MODE,
            policy_revision_hash=policy_revision_hash,
            findings=tuple(sorted(findings, key=self._finding_sort_key)),
            blocking_reasons=tuple(sorted(set(blocking_reasons))),
        )

    def _freeze_findings(
        self,
        target: Path,
        contract: SelfHostedTaskContract,
        candidate_paths: list[str],
        deleted_files: list[str],
        candidate_revision: str | None = None,
    ) -> tuple[list[RepositoryContractFinding], list[str]]:
        findings: list[RepositoryContractFinding] = []
        blocking_reasons: list[str] = []
        deleted_set = set(deleted_files)

        for path in candidate_paths:
            if path in deleted_set:
                continue

            is_new = not self._base_path_exists(target, contract.target_base_revision, path)

            # (1), (2), (3) Markdown Freeze Checks
            if path.lower().endswith(".md") and is_new:
                if path.startswith("tasks/"):
                    if path not in contract.allowed_files:
                        reason = f"new_persistent_markdown_frozen:{path}"
                        blocking_reasons.append(reason)
                        findings.append(
                            RepositoryContractFinding(
                                kind="new_persistent_markdown_frozen",
                                severity="blocking",
                                path=path,
                                message="newly created markdown file under tasks/ is not in contract.allowed_files",
                                evidence={
                                    "target_base_revision": contract.target_base_revision,
                                },
                            )
                        )
                else:
                    reason = f"new_persistent_markdown_frozen:{path}"
                    blocking_reasons.append(reason)
                    findings.append(
                        RepositoryContractFinding(
                            kind="new_persistent_markdown_frozen",
                            severity="blocking",
                            path=path,
                            message="newly created persistent markdown file outside tasks/ is frozen",
                            evidence={
                                "target_base_revision": contract.target_base_revision,
                            },
                        )
                    )

            # Production Python Checks
            if path.endswith(".py") and (path.startswith("nexus/") or path.startswith("scripts/")):
                stem = Path(path).stem.lower()

                # (4) Newly created production Python module whose basename denotes agent, router, or wrapper
                if is_new and any(k in stem for k in ("agent", "router", "wrapper")):
                    reason = f"new_component_module_frozen:{path}"
                    blocking_reasons.append(reason)
                    findings.append(
                        RepositoryContractFinding(
                            kind="new_component_module_frozen",
                            severity="blocking",
                            path=path,
                            message="newly created production python module denoting agent, router, or wrapper is frozen",
                            evidence={
                                "stem": Path(path).stem,
                                "target_base_revision": contract.target_base_revision,
                            },
                        )
                    )

                # (5) & (6) AST class checks for class names ending with Agent, Router, or Wrapper
                cand_code = self._candidate_text(
                    target=target,
                    path=path,
                    candidate_revision=candidate_revision,
                )
                if cand_code is not None:
                    try:
                        tree_cand = ast.parse(cand_code, filename=path)
                        cand_classes = {
                            node.name
                            for node in ast.walk(tree_cand)
                            if isinstance(node, ast.ClassDef)
                            and node.name.endswith(("Agent", "Router", "Wrapper"))
                        }
                    except (SyntaxError, UnicodeDecodeError):
                        cand_classes = set()

                    if cand_classes:
                        base_classes: set[str] = set()
                        if not is_new:
                            try:
                                base_code = self.worktree_manager._run_git(
                                    ["show", f"{contract.target_base_revision}:{path}"],
                                    cwd=target,
                                )
                                tree_base = ast.parse(base_code, filename=path)
                                base_classes = {
                                    node.name
                                    for node in ast.walk(tree_base)
                                    if isinstance(node, ast.ClassDef)
                                    and node.name.endswith(("Agent", "Router", "Wrapper"))
                                }
                            except (RuntimeError, SyntaxError):
                                base_classes = set()

                        new_classes = sorted(cand_classes - base_classes)
                        for class_name in new_classes:
                            reason = f"new_component_class_frozen:{path}:{class_name}"
                            blocking_reasons.append(reason)
                            findings.append(
                                RepositoryContractFinding(
                                    kind="new_component_class_frozen",
                                    severity="blocking",
                                    path=path,
                                    message=f"new class '{class_name}' ending with Agent, Router, or Wrapper is frozen",
                                    evidence={
                                        "class_name": class_name,
                                        "target_base_revision": contract.target_base_revision,
                                    },
                                )
                            )

        return findings, blocking_reasons

    def _effective_route_findings(
        self,
        *,
        target: Path,
        contract: SelfHostedTaskContract,
        candidate_paths: list[str],
        current: CandidateDiffReceipt | None,
        candidate_revision: str | None = None,
    ) -> tuple[list[RepositoryContractFinding], list[str]]:
        findings: list[RepositoryContractFinding] = []
        blocking_reasons: list[str] = []
        marked = self.AUTHORITY_CHANGE_MARKER in set(contract.protected_contracts)

        def add(path: str, message: str, evidence: Mapping[str, str]) -> None:
            kind = "authority_change_pending_human_verification" if marked else "effective_route_authority_change"
            reason = f"{kind}:{path}"
            blocking_reasons.append(reason)
            findings.append(
                RepositoryContractFinding(
                    kind=kind,
                    severity="blocking",
                    path=path,
                    message=message,
                    evidence={**evidence, "authority_change_marker": str(marked).lower()},
                )
            )

        for path in candidate_paths:
            if not (path.startswith("nexus/") or path.startswith("scripts/")):
                continue
            stem = Path(path).stem.lower()
            is_new = not self._base_path_exists(target, contract.target_base_revision, path)
            if path.endswith(".py") and is_new and any(token in stem for token in self.EFFECTIVE_ROUTE_TOKENS):
                # Preserve the legacy reason for the original three checks.
                if not any(token in stem for token in ("agent", "router", "wrapper")):
                    add(path, "new production module name can become a second control-plane authority", {"stem": stem})
            candidate_text = self._candidate_text(
                target=target,
                path=path,
                candidate_revision=candidate_revision,
            )
            if path.endswith(".py") and is_new and candidate_text is not None:
                try:
                    tree = ast.parse(candidate_text, filename=path)
                except SyntaxError:
                    tree = None
                if tree is not None:
                    for node in ast.walk(tree):
                        if not isinstance(node, ast.ClassDef):
                            continue
                        class_name = node.name.lower()
                        if any(token in class_name for token in self.EFFECTIVE_ROUTE_TOKENS):
                            if not class_name.endswith(("agent", "router", "wrapper")):
                                add(f"{path}:{node.name}", "new production class name can become a second control-plane authority", {"class_name": node.name})
            if is_new:
                added = candidate_text or ""
            else:
                try:
                    args = ["diff", "--unified=0", contract.target_base_revision]
                    if candidate_revision:
                        args.append(candidate_revision)
                    args.extend(["--", path])
                    diff = self.worktree_manager._run_git(args, cwd=target)
                except RuntimeError:
                    if candidate_revision:
                        reason = f"integration_candidate_diff_unreadable:{path}"
                        blocking_reasons.append(reason)
                        findings.append(
                            RepositoryContractFinding(
                                kind="integration_candidate_diff_unreadable",
                                severity="blocking",
                                path=path,
                                message="candidate route-sensitive diff could not be read",
                            )
                        )
                    continue
                added = "\n".join(line[1:] for line in diff.splitlines() if line.startswith("+") and not line.startswith("+++"))
            if not any(token in path.lower() for token in self.AUTHORITY_PATH_TOKENS) and not (
                path.startswith("nexus/config/") or any(token in path.lower() for token in self.AUTHORITY_BRANCH_TOKENS)
            ):
                continue
            lowered = added.lower()
            matched = sorted(token for token in self.AUTHORITY_BRANCH_TOKENS if token in lowered)
            if matched:
                add(path, "existing authority-sensitive file adds an effective route/fallback branch", {"matched_tokens": ",".join(matched)})

        return findings, blocking_reasons

    def _candidate_text(
        self,
        *,
        target: Path,
        path: str,
        candidate_revision: str | None,
    ) -> str | None:
        if candidate_revision:
            try:
                return self.worktree_manager._run_git(
                    ["show", f"{candidate_revision}:{path}"], cwd=target
                )
            except RuntimeError:
                return None
        file_path = target / path
        if not file_path.exists():
            return None
        try:
            return file_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return None


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
