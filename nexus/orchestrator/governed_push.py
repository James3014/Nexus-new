"""Explicitly authorized, allowlisted push for a governed integration branch."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import subprocess
from typing import Mapping, Optional


_SHA = re.compile(r"^[0-9a-f]{40}$")


@dataclass(frozen=True)
class PushReceipt:
    schema: str
    remote: str
    branch: str
    pushed_commit_sha: str
    remote_commit_sha: str
    push_performed: bool
    force_push: bool
    authorized: bool


class GovernedPushManager:
    def __init__(
        self,
        *,
        repo_root: str | Path,
        allowed_remotes: set[str] | frozenset[str],
        allowed_branch_prefix: str = "nexus/integration",
    ):
        self.repo_root = Path(repo_root).expanduser().resolve()
        self.allowed_remotes = frozenset(str(remote) for remote in allowed_remotes)
        self.allowed_branch_prefix = allowed_branch_prefix.rstrip("/")

    def _git(self, args: list[str]) -> str:
        result = subprocess.run(
            ["git", *args],
            cwd=self.repo_root,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
        return result.stdout.strip()

    def push(
        self,
        *,
        remote: str,
        branch: str,
        expected_sha: str,
        authorized: bool,
        integration_receipt: Optional[Mapping[str, object]] = None,
    ) -> PushReceipt:
        if not authorized:
            raise PermissionError("governed push requires explicit authorization")
        if remote not in self.allowed_remotes:
            raise PermissionError(f"remote is not allowlisted: {remote}")
        if branch == "main" or branch == "master" or not (
            branch == self.allowed_branch_prefix or branch.startswith(self.allowed_branch_prefix + "/")
        ):
            raise PermissionError(f"branch is not allowlisted for push: {branch}")
        if not _SHA.fullmatch(expected_sha):
            raise ValueError("expected_sha must be an exact lowercase Git SHA")
        if integration_receipt is not None:
            if integration_receipt.get("integration_branch") != branch:
                raise ValueError("push branch does not match integration receipt")
            if integration_receipt.get("integration_commit_sha") != expected_sha:
                raise ValueError("push SHA does not match integration receipt")
            if integration_receipt.get("merge_performed") is not True:
                raise ValueError("integration receipt is not merge-proven")
            if integration_receipt.get("push_performed") is True:
                raise ValueError("integration receipt already records a push")
        local_sha = self._git(["rev-parse", f"{branch}^{{commit}}"])
        if local_sha != expected_sha:
            raise RuntimeError("local integration branch changed after receipt")
        self._git(["push", "--porcelain", remote, f"{expected_sha}:refs/heads/{branch}"])
        remote_sha = self._git(["ls-remote", "--heads", remote, f"refs/heads/{branch}"]).split()[0]
        if remote_sha != expected_sha:
            raise RuntimeError("remote branch SHA does not match pushed integration commit")
        return PushReceipt(
            schema="nexus.governed_push_receipt.v1",
            remote=remote,
            branch=branch,
            pushed_commit_sha=expected_sha,
            remote_commit_sha=remote_sha,
            push_performed=True,
            force_push=False,
            authorized=True,
        )
