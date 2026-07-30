"""Local-only integration of one verified candidate into a non-protected branch."""

from __future__ import annotations

import os
import re
import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from nexus.executors.cli_worker import CliWorkerRequest, CliWorkerStatus, run_cli_worker

_SHA = re.compile(r"^[0-9a-f]{40}$")
_PROTECTED_BRANCHES = frozenset({"main", "master", "develop", "production"})


@dataclass(frozen=True)
class IntegrationReceipt:
    schema: str
    task_id: str
    integration_branch: str
    source_branch: str
    candidate_commit_sha: str
    integration_base_sha: str
    integration_commit_sha: str
    verifier_passed: bool
    merge_performed: bool
    push_performed: bool
    worktree_removed: bool
    failure_reason: str | None = None


class ControlledIntegrationManager:
    def __init__(self, *, integration_root: str | Path):
        self.integration_root = Path(integration_root).expanduser().resolve()

    @staticmethod
    def _git(args: Sequence[str], cwd: str | Path) -> str:
        git_env = os.environ.copy()
        git_env["GIT_CONFIG_NOSYSTEM"] = "1"
        git_env["GIT_CONFIG_GLOBAL"] = "/dev/null"
        empty_hooks = Path("/private/tmp/nexus-empty-git-hooks")
        empty_hooks.mkdir(parents=True, exist_ok=True)
        git_cmd = ["git", "-c", f"core.hooksPath={empty_hooks}", *args]
        result = subprocess.run(
            git_cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            env=git_env,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"git {' '.join(args)} failed: {result.stderr.strip()}"
            )
        return result.stdout.strip()

    @staticmethod
    def _validate_branch(branch: str) -> None:
        if branch in _PROTECTED_BRANCHES or branch.startswith("refs/"):
            raise ValueError(f"protected integration branch: {branch}")
        if branch != "nexus/integration" and not branch.startswith("nexus/integration/"):
            raise ValueError("integration branch must be nexus/integration or nexus/integration/*")

    def _verify_commands(self, commands: Sequence[str], cwd: Path) -> tuple[bool, str | None]:
        for command in commands:
            try:
                tokens = tuple(shlex.split(command))
                if len(tokens) < 2:
                    return False, f"invalid verifier command: {command}"
                result = run_cli_worker(
                    CliWorkerRequest(
                        executable=tokens[0],
                        argv=tokens[1:],
                        cwd=str(cwd),
                        timeout_seconds=300.0,
                        env={"PYTHONDONTWRITEBYTECODE": "1"},
                    )
                )
            except (OSError, ValueError) as exc:
                return False, f"invalid verifier command: {command}: {exc}"
            if result.status is not CliWorkerStatus.COMPLETED or result.exit_code != 0:
                return False, f"integration verifier failed: {command}"
        return True, None

    def integrate_task_state(
        self,
        state: Mapping[str, Any],
        *,
        integration_branch: str = "nexus/integration",
    ) -> IntegrationReceipt:
        self._validate_branch(integration_branch)
        contract = state.get("contract") or {}
        packet = state.get("promotion_packet") or {}
        lease = state.get("lease") or {}
        task_id = str(state.get("task_id") or contract.get("task_id") or "")
        controller_root = Path(str(contract.get("controller_repo_root", ""))).expanduser().resolve()
        target_base_revision = str(contract.get("target_base_revision", ""))
        candidate_sha = str(packet.get("candidate_commit_sha", ""))
        source_branch = str(
            state.get("candidate_ref")
            if lease.get("target_detached")
            else lease.get("target_branch", "")
        )
        if state.get("status") not in {"CANDIDATE_COMMITTED", "APPROVED", "INTEGRATING", "INTEGRATION_FAILED"}:
            raise RuntimeError("only a terminal candidate task can be integrated")
        approved = state.get("approved_binding") or {}
        binding_fields = (
            "candidate_commit_sha", "candidate_tree_sha",
            "candidate_state_hash", "verified_receipt_hash",
        )
        if not approved or not packet or state.get("promotion_status") not in {"APPROVED", "INTEGRATION_FAILED"} or any(
            approved.get(field) != packet.get(field) for field in binding_fields
        ):
            raise RuntimeError("exact approved binding is required")
        if not _SHA.fullmatch(candidate_sha) or not _SHA.fullmatch(target_base_revision):
            raise RuntimeError("candidate and target base revisions must be exact Git SHAs")
        if not source_branch:
            raise RuntimeError("candidate source branch is missing")
        if not controller_root.is_dir():
            raise RuntimeError("controller repository root is missing")
        if self._git(["rev-parse", "--verify", f"{candidate_sha}^{{commit}}"], controller_root) != candidate_sha:
            raise RuntimeError("candidate commit is not present in controller repository")
        if self._git(["rev-parse", source_branch], controller_root) != candidate_sha:
            raise RuntimeError("candidate source branch does not bind to promotion commit")
        actual_tree = self._git(["rev-parse", f"{candidate_sha}^{{tree}}"], controller_root)
        if actual_tree != str(packet.get("candidate_tree_sha", "")):
            raise RuntimeError("candidate tree does not bind to promotion packet")
        if self._git(["rev-parse", f"{target_base_revision}^{{commit}}"], controller_root) != target_base_revision:
            raise RuntimeError("target base revision is not present")

        self.integration_root.mkdir(parents=True, exist_ok=True)
        integration_path = self.integration_root / task_id
        controller_branch = self._git(["branch", "--show-current"], controller_root)
        reuse_controller_worktree = controller_branch == integration_branch
        if integration_path.exists():
            raise RuntimeError("integration worktree path already exists")
        branch_exists = subprocess.run(
            ["git", "rev-parse", "--verify", integration_branch],
            cwd=controller_root,
            capture_output=True,
            text=True,
        ).returncode == 0
        if not branch_exists:
            raise RuntimeError("governed integration branch must already exist")
        if reuse_controller_worktree:
            integration_path = controller_root
        else:
            add_args = ["worktree", "add", str(integration_path), integration_branch]
            self._git(add_args, controller_root)
        removed = False
        integration_base_sha = self._git(["rev-parse", "HEAD"], integration_path)
        try:
            self._git(["merge", "--no-ff", "--no-edit", candidate_sha], integration_path)
            passed, reason = self._verify_commands(
                list(contract.get("verifier_commands") or []), integration_path
            )
            if not passed:
                self._git(["reset", "--merge", integration_base_sha], integration_path)
                raise RuntimeError(reason or "integration verifier failed")
            integration_sha = self._git(["rev-parse", "HEAD"], integration_path)
        except Exception:
            subprocess.run(["git", "merge", "--abort"], cwd=integration_path, capture_output=True, text=True)
            subprocess.run(["git", "reset", "--merge", integration_base_sha], cwd=integration_path, capture_output=True, text=True)
            if not reuse_controller_worktree:
                self._git(["worktree", "remove", str(integration_path)], controller_root)
            raise
        if not reuse_controller_worktree:
            self._git(["worktree", "remove", str(integration_path)], controller_root)
        removed = True
        return IntegrationReceipt(
            schema="nexus.integration_receipt.v1",
            task_id=task_id,
            integration_branch=integration_branch,
            source_branch=source_branch,
            candidate_commit_sha=candidate_sha,
            integration_base_sha=integration_base_sha,
            integration_commit_sha=integration_sha,
            verifier_passed=True,
            merge_performed=True,
            push_performed=False,
            worktree_removed=removed,
        )
