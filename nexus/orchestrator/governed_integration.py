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
from nexus.orchestrator.worktree_manager import get_canonical_git_hooks_dir

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
    staging_commit_sha: str | None = None
    post_apply_verified: bool = False
    post_apply_error: str | None = None
    acceptance_receipt_hash: str | None = None
    authorization_hash: str | None = None
    task_card_hash: str | None = None
    candidate_tree_sha: str | None = None
    candidate_state_hash: str | None = None
    verified_receipt_hash: str | None = None


class ControlledIntegrationManager:
    def __init__(self, *, integration_root: str | Path):
        self.integration_root = Path(integration_root).expanduser().resolve()

    @staticmethod
    def _git(args: Sequence[str], cwd: str | Path) -> str:
        git_env = os.environ.copy()
        git_env["GIT_CONFIG_NOSYSTEM"] = "1"
        git_env["GIT_CONFIG_GLOBAL"] = "/dev/null"
        hooks_dir = get_canonical_git_hooks_dir(Path(cwd))
        git_cmd = ["git", "-c", f"core.hooksPath={hooks_dir}", *args]
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

    def integrate_authorized_task_state(
        self,
        state: Mapping[str, Any],
        *,
        integration_branch: str,
        staging_root: str | Path,
        apply: bool = True,
        post_apply_commands: Sequence[Sequence[str]] = (),
    ) -> IntegrationReceipt:
        """Stage and apply one already authorized Candidate through this authority.

        This is intentionally the only new Git execution seam.  Callers provide
        persisted lifecycle state; the manager rechecks exact identity, clean
        worktree state, branch head, staging ancestry, and post-apply state.
        """
        self._validate_branch(integration_branch)
        contract = state.get("contract") or {}
        packet = state.get("promotion_packet") or {}
        authorization = state.get("integration_authorization") or {}
        acceptance = state.get("external_acceptance") or {}
        candidate_sha = str(packet.get("candidate_commit_sha") or packet.get("candidate_commit") or "")
        task_id = str(state.get("task_id") or contract.get("task_id") or "")
        controller_root = Path(str(contract.get("controller_repo_root", ""))).expanduser().resolve()
        expected_head = str(authorization.get("expected_canonical_head") or "")
        if not task_id or not candidate_sha or not expected_head:
            raise RuntimeError("authorized integration identity is incomplete")
        if not acceptance.get("passed"):
            raise RuntimeError("external acceptance is required before integration")
        if not authorization.get("cleanup_requested") and "CLEANUP_OWNED_TARGET" in (authorization.get("action_set") or []):
            raise RuntimeError("authorization cleanup binding is inconsistent")
        if "INTEGRATION_STAGING" not in (authorization.get("action_set") or []) or "APPLY_VERIFIED_INTEGRATION" not in (authorization.get("action_set") or []):
            raise RuntimeError("Owner authorization does not include integration actions")
        if str(authorization.get("canonical_branch") or "") != integration_branch:
            raise RuntimeError("authorization integration branch drift")
        if str(authorization.get("canonical_root") or "") != str(controller_root):
            raise RuntimeError("authorization integration root drift")
        if self._git(["rev-parse", f"{candidate_sha}^{{commit}}"], controller_root) != candidate_sha:
            raise RuntimeError("candidate commit is not present in controller repository")
        branch_head = self._git(["rev-parse", f"{integration_branch}^{{commit}}"], controller_root)
        if branch_head != expected_head:
            raise RuntimeError("integration branch HEAD drift")
        if self._git(["status", "--porcelain=v1", "--untracked-files=all"], controller_root):
            raise RuntimeError("canonical/integration worktree must be clean before apply")

        staging_path = Path(staging_root).expanduser().resolve() / task_id
        if staging_path.exists():
            raise RuntimeError("integration staging Target already exists")
        staging_path.parent.mkdir(parents=True, exist_ok=True)
        self._git(["worktree", "add", "--detach", str(staging_path), expected_head], controller_root)
        staging_sha = ""
        applied = False
        try:
            self._git(["merge", "--no-ff", "--no-edit", candidate_sha], staging_path)
            verifier_commands = state.get("verifier_argv_commands") or contract.get("verifier_commands") or ()
            for command in verifier_commands:
                tokens = tuple(command) if isinstance(command, (list, tuple)) else tuple(shlex.split(str(command)))
                if len(tokens) < 1:
                    raise RuntimeError(f"invalid staging verifier command: {command}")
                result = subprocess.run(tokens, cwd=staging_path, capture_output=True, text=True)
                if result.returncode != 0:
                    raise RuntimeError(f"staging verifier failed: {command}")
            staging_sha = self._git(["rev-parse", "HEAD"], staging_path)
            if apply:
                if self._git(["rev-parse", f"{integration_branch}^{{commit}}"], controller_root) != expected_head:
                    raise RuntimeError("integration branch HEAD drift before apply")
                if self._git(["status", "--porcelain=v1", "--untracked-files=all"], controller_root):
                    raise RuntimeError("canonical/integration worktree must be clean before apply")
                current_branch = self._git(["branch", "--show-current"], controller_root)
                if current_branch == integration_branch:
                    self._git(["merge", "--ff-only", staging_sha], controller_root)
                else:
                    self._git(["update-ref", f"refs/heads/{integration_branch}", staging_sha, expected_head], controller_root)
                applied = True
                exact_head = self._git(["rev-parse", f"{integration_branch}^{{commit}}"], controller_root)
                if exact_head != staging_sha:
                    raise RuntimeError("applied HEAD is not the verified staging commit")
                if self._git(["merge-base", "--is-ancestor", candidate_sha, exact_head], controller_root) is not None:
                    pass
                if self._git(["status", "--porcelain=v1", "--untracked-files=all"], controller_root):
                    raise RuntimeError("canonical/integration worktree is dirty after apply")
                for command in post_apply_commands:
                    result = subprocess.run(tuple(command), cwd=controller_root, capture_output=True, text=True)
                    if result.returncode != 0:
                        raise RuntimeError(f"post-apply verification failed: {' '.join(command)}")
        except Exception:
            subprocess.run(["git", "merge", "--abort"], cwd=staging_path, capture_output=True, text=True)
            raise
        finally:
            if staging_path.exists():
                self._git(["worktree", "remove", "--force", str(staging_path)], controller_root)
                self._git(["worktree", "prune"], controller_root)
        final_head = self._git(["rev-parse", f"{integration_branch}^{{commit}}"], controller_root)
        return IntegrationReceipt(
            schema="nexus.integration_receipt.v1", task_id=task_id,
            integration_branch=integration_branch,
            source_branch=str((state.get("lease") or {}).get("target_branch") or ""),
            candidate_commit_sha=candidate_sha,
            integration_base_sha=expected_head,
            integration_commit_sha=final_head,
            verifier_passed=True,
            merge_performed=applied,
            push_performed=False,
            worktree_removed=True,
            staging_commit_sha=staging_sha,
            post_apply_verified=bool(applied),
            acceptance_receipt_hash=str(authorization.get("acceptance_receipt_hash") or acceptance.get("receipt_hash") or "") or None,
            authorization_hash=str(authorization.get("authorization_hash") or "") or None,
            task_card_hash=str(authorization.get("task_card_hash") or "") or None,
            candidate_tree_sha=str(authorization.get("candidate_tree_sha") or "") or None,
            candidate_state_hash=str(authorization.get("candidate_state_hash") or "") or None,
            verified_receipt_hash=str(packet.get("verified_receipt_hash") or "") or None,
        )
