"""Owner-authorized, allowlisted push for a governed integration branch."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import subprocess
from typing import Mapping, Optional

from nexus.contracts.autonomy_goal import (
    AutonomyActionClass,
    RepositoryIdentity,
    canonical_autonomy_hash,
)
from nexus.orchestrator.standing_grant_store import (
    StandingGrantReceiptError,
    authorize_durable_standing_grant_effect,
)


_SHA = re.compile(r"^[0-9a-f]{40}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_GITHUB_REPOSITORY = RepositoryIdentity(
    repository_id="James3014/Nexus-new",
    canonical_remote="https://github.com/James3014/Nexus-new.git",
)


@dataclass(frozen=True)
class PushReceipt:
    schema: str
    remote: str
    branch: str
    pushed_commit_sha: str
    remote_commit_sha: str
    push_performed: bool
    push_attempted: bool
    push_acknowledged: bool
    effect_present: bool
    preexisting_effect: bool
    reconciled_after_uncertain_ack: bool
    force_push: bool
    authorized: bool
    authorization_hash: str
    authorization_effect_hash: str
    authorization_grant_receipt_hash: str


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

    def _remote_sha(self, *, remote: str, branch: str) -> str | None:
        output = self._git(["ls-remote", "--heads", remote, f"refs/heads/{branch}"])
        if not output:
            return None
        sha = output.split()[0]
        if not _SHA.fullmatch(sha):
            raise RuntimeError("remote branch returned an invalid SHA")
        return sha

    @staticmethod
    def _validate_owner_authority(
        authorization: Mapping[str, object],
        *,
        effect: Mapping[str, object],
    ) -> tuple[str, str, str]:
        if (
            authorization.get("schema") != "nexus.standing_grant_effect_authorization.v1"
            or authorization.get("action") != AutonomyActionClass.REPOSITORY_PUSH.value
            or authorization.get("mutation_authorized") is not True
            or authorization.get("repository") != _GITHUB_REPOSITORY.model_dump(mode="json")
            or authorization.get("effect") != dict(effect)
        ):
            raise PermissionError("governed push requires exact durable Owner authorization")
        effect_hash = str(authorization.get("effect_hash") or "")
        authorization_hash = str(authorization.get("authorization_hash") or "")
        grant_receipt_hash = str(authorization.get("grant_receipt_hash") or "")
        if (
            not _SHA256.fullmatch(effect_hash)
            or effect_hash != canonical_autonomy_hash(dict(effect))
            or not _SHA256.fullmatch(grant_receipt_hash)
        ):
            raise PermissionError("governed push authorization binding is invalid")
        unsigned = dict(authorization)
        unsigned.pop("authorization_hash", None)
        if (
            not _SHA256.fullmatch(authorization_hash)
            or authorization_hash != canonical_autonomy_hash(unsigned)
        ):
            raise PermissionError("governed push authorization hash is invalid")
        return authorization_hash, effect_hash, grant_receipt_hash

    def push(
        self,
        *,
        competition_id: str,
        winner_task_id: str,
        remote: str,
        branch: str,
        expected_sha: str,
        integration_receipt: Optional[Mapping[str, object]] = None,
    ) -> PushReceipt:
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

        effect = {
            "competition_id": str(competition_id),
            "winner_task_id": str(winner_task_id),
            "remote": remote,
            "branch": branch,
            "expected_sha": expected_sha,
        }
        try:
            owner_authority = authorize_durable_standing_grant_effect(
                repository=_GITHUB_REPOSITORY,
                action=AutonomyActionClass.REPOSITORY_PUSH,
                effect=effect,
            )
        except StandingGrantReceiptError as exc:
            raise PermissionError(f"governed push requires durable Owner authorization: {exc}") from exc
        authorization_hash, effect_hash, grant_receipt_hash = self._validate_owner_authority(
            owner_authority,
            effect=effect,
        )

        local_sha = self._git(["rev-parse", f"{branch}^{{commit}}"])
        if local_sha != expected_sha:
            raise RuntimeError("local integration branch changed after receipt")

        # Reconcile before every irreversible attempt. If a prior attempt reached
        # the remote but its acknowledgement was lost, retry is a no-op readback
        # rather than a blind second push.
        remote_before = self._remote_sha(remote=remote, branch=branch)
        if remote_before == expected_sha:
            return PushReceipt(
                schema="nexus.governed_push_receipt.v2",
                remote=remote,
                branch=branch,
                pushed_commit_sha=expected_sha,
                remote_commit_sha=expected_sha,
                push_performed=False,
                push_attempted=False,
                push_acknowledged=False,
                effect_present=True,
                preexisting_effect=True,
                reconciled_after_uncertain_ack=False,
                force_push=False,
                authorized=True,
                authorization_hash=authorization_hash,
                authorization_effect_hash=effect_hash,
                authorization_grant_receipt_hash=grant_receipt_hash,
            )

        try:
            self._git(["push", "--porcelain", remote, f"{expected_sha}:refs/heads/{branch}"])
        except RuntimeError as push_error:
            try:
                reconciled_sha = self._remote_sha(remote=remote, branch=branch)
            except RuntimeError as reconcile_error:
                raise RuntimeError(
                    "push outcome is uncertain and remote reconciliation failed"
                ) from reconcile_error
            if reconciled_sha != expected_sha:
                raise RuntimeError(
                    "push failed and remote state does not confirm the expected effect"
                ) from push_error
            return PushReceipt(
                schema="nexus.governed_push_receipt.v2",
                remote=remote,
                branch=branch,
                pushed_commit_sha=expected_sha,
                remote_commit_sha=expected_sha,
                push_performed=False,
                push_attempted=True,
                push_acknowledged=False,
                effect_present=True,
                preexisting_effect=False,
                reconciled_after_uncertain_ack=True,
                force_push=False,
                authorized=True,
                authorization_hash=authorization_hash,
                authorization_effect_hash=effect_hash,
                authorization_grant_receipt_hash=grant_receipt_hash,
            )

        remote_sha = self._remote_sha(remote=remote, branch=branch)
        if remote_sha != expected_sha:
            raise RuntimeError("remote branch SHA does not match pushed integration commit")
        return PushReceipt(
            schema="nexus.governed_push_receipt.v2",
            remote=remote,
            branch=branch,
            pushed_commit_sha=expected_sha,
            remote_commit_sha=remote_sha,
            push_performed=True,
            push_attempted=True,
            push_acknowledged=True,
            effect_present=True,
            preexisting_effect=False,
            reconciled_after_uncertain_ack=False,
            force_push=False,
            authorized=True,
            authorization_hash=authorization_hash,
            authorization_effect_hash=effect_hash,
            authorization_grant_receipt_hash=grant_receipt_hash,
        )
