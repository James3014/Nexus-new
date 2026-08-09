"""Physical provenance gates for sanitized GitHub collaboration execution."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

if TYPE_CHECKING:
    from nexus.orchestrator.task_contract import SelfHostedTaskContract


class CollaborationRealmVerifier:
    """Verify that collaboration work descends from its bound sanitized clone."""

    @staticmethod
    def _git(root: Path, *args: str) -> str:
        env = os.environ.copy()
        env["GIT_CONFIG_NOSYSTEM"] = "1"
        # Private collaboration repositories rely on the Owner's configured
        # credential helper.  Keep that bounded machine credential surface,
        # but never permit an interactive credential prompt in orchestration.
        env["GIT_TERMINAL_PROMPT"] = "0"
        result = subprocess.run(
            ["git", *args],
            cwd=root,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            detail = result.stderr.strip() or result.stdout.strip() or str(result.returncode)
            raise RuntimeError(f"COLLABORATION_REALM_GIT_FAILED:{detail}")
        return result.stdout.strip()

    @classmethod
    def _top_level(cls, root: Path) -> Path:
        return Path(cls._git(root, "rev-parse", "--show-toplevel")).resolve()

    @classmethod
    def _common_git_dir(cls, root: Path) -> Path:
        raw = Path(cls._git(root, "rev-parse", "--git-common-dir"))
        return (raw if raw.is_absolute() else root / raw).resolve()

    @staticmethod
    def _binding(contract: SelfHostedTaskContract) -> Any:
        return getattr(contract, "collaboration_realm", None)

    @staticmethod
    def _remote_repository_id(remote: str) -> str:
        if remote.startswith("git@"):
            path = remote.split(":", 1)[1] if ":" in remote else ""
        else:
            path = urlparse(remote).path.lstrip("/")
        return path.removesuffix(".git").rstrip("/")

    @classmethod
    def verify_submission(cls, contract: SelfHostedTaskContract) -> dict[str, object]:
        binding = cls._binding(contract)
        if binding is None:
            return {}

        control_root = Path(binding.control_plane.repo_root).resolve()
        collaboration_root = Path(binding.collaboration.repo_root).resolve()
        execution_root = Path(binding.execution_root).resolve()
        base = binding.collaboration.base
        repository = binding.collaboration.repository
        remote_name = binding.collaboration.remote_name

        if Path(contract.controller_repo_root).resolve() != collaboration_root:
            raise RuntimeError("COLLABORATION_REALM_CONTROLLER_ROOT_MISMATCH")
        if Path(contract.target_worktree_root).resolve() != execution_root:
            raise RuntimeError("COLLABORATION_REALM_EXECUTION_ROOT_MISMATCH")
        if contract.controller_revision != base.head_sha:
            raise RuntimeError("COLLABORATION_REALM_CONTROLLER_REVISION_MISMATCH")
        if contract.target_base_revision != base.head_sha:
            raise RuntimeError("COLLABORATION_REALM_TARGET_BASE_MISMATCH")
        if binding.runtime_activation.activation_authorized is not False:
            raise RuntimeError("COLLABORATION_REALM_RUNTIME_ACTIVATION_FORBIDDEN")
        if cls._remote_repository_id(repository.canonical_remote) != repository.repository_id:
            raise RuntimeError("COLLABORATION_REALM_REPOSITORY_IDENTITY_MISMATCH")
        if not control_root.is_dir() or not collaboration_root.is_dir():
            raise RuntimeError("COLLABORATION_REALM_REPOSITORY_UNAVAILABLE")
        if cls._top_level(control_root) != control_root:
            raise RuntimeError("COLLABORATION_REALM_CONTROL_ROOT_MISMATCH")
        if cls._top_level(collaboration_root) != collaboration_root:
            raise RuntimeError("COLLABORATION_REALM_REPOSITORY_ROOT_MISMATCH")
        if cls._common_git_dir(control_root) == cls._common_git_dir(collaboration_root):
            raise RuntimeError("COLLABORATION_REALM_LOCAL_HISTORY_REJECTED")

        control_head = cls._git(control_root, "rev-parse", "HEAD^{commit}")
        if control_head != binding.control_plane.revision:
            raise RuntimeError("COLLABORATION_REALM_CONTROL_REVISION_DRIFT")
        collaboration_head = cls._git(collaboration_root, "rev-parse", "HEAD^{commit}")
        if collaboration_head != base.head_sha:
            raise RuntimeError("COLLABORATION_REALM_BASE_DRIFT")
        try:
            cls._git(collaboration_root, "cat-file", "-e", f"{base.head_sha}^{{commit}}")
        except RuntimeError as exc:
            raise RuntimeError("COLLABORATION_REALM_BASE_MISSING") from exc

        actual_fetch_remote = cls._git(
            collaboration_root,
            "remote",
            "get-url",
            remote_name,
        )
        actual_push_remote = cls._git(
            collaboration_root,
            "remote",
            "get-url",
            "--push",
            remote_name,
        )
        if (
            actual_fetch_remote != repository.canonical_remote
            or actual_push_remote != repository.canonical_remote
        ):
            raise RuntimeError("COLLABORATION_REALM_REMOTE_MISMATCH")
        remote_rows = cls._git(
            collaboration_root,
            "ls-remote",
            "--exit-code",
            remote_name,
            f"refs/heads/{base.branch}",
        ).splitlines()
        remote_shas = {row.split(maxsplit=1)[0] for row in remote_rows if row.strip()}
        if remote_shas != {base.head_sha}:
            raise RuntimeError("COLLABORATION_REALM_REMOTE_BASE_DRIFT")

        return {
            "schema": "nexus.collaboration_provenance.v1",
            "binding_hash": binding.binding_hash,
            "repository_id": repository.repository_id,
            "canonical_remote": repository.canonical_remote,
            "remote_name": remote_name,
            "base_branch": base.branch,
            "base_sha": base.head_sha,
            "control_plane_root": str(control_root),
            "control_plane_revision": binding.control_plane.revision,
            "collaboration_root": str(collaboration_root),
            "execution_root": str(execution_root),
            "remote_base_verified": True,
            "sanitized_ancestry_verified": False,
            "runtime_activation_authorized": False,
        }

    @classmethod
    def verify_target(
        cls,
        contract: SelfHostedTaskContract,
        target_path: str | Path,
        target_head: str,
    ) -> dict[str, object]:
        provenance = cls.verify_submission(contract)
        binding = cls._binding(contract)
        if binding is None:
            return provenance

        target = Path(target_path).resolve()
        execution_root = Path(binding.execution_root).resolve()
        collaboration_root = Path(binding.collaboration.repo_root).resolve()
        base_sha = binding.collaboration.base.head_sha
        if target == execution_root or execution_root not in target.parents:
            raise RuntimeError("COLLABORATION_REALM_TARGET_ROOT_MISMATCH")
        if not target.is_dir() or cls._top_level(target) != target:
            raise RuntimeError("COLLABORATION_REALM_TARGET_UNAVAILABLE")
        if cls._common_git_dir(target) != cls._common_git_dir(collaboration_root):
            raise RuntimeError("COLLABORATION_REALM_TARGET_REPOSITORY_MISMATCH")
        if cls._git(target, "rev-parse", "HEAD^{commit}") != target_head:
            raise RuntimeError("COLLABORATION_REALM_TARGET_HEAD_DRIFT")
        try:
            cls._git(target, "merge-base", "--is-ancestor", base_sha, target_head)
        except RuntimeError as exc:
            raise RuntimeError("COLLABORATION_REALM_TARGET_ANCESTRY_MISMATCH") from exc

        return {
            **provenance,
            "target_root": str(target),
            "target_head": target_head,
            "sanitized_ancestry_verified": True,
        }
