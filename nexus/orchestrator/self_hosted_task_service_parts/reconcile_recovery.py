"""Reconcile-recovery members of ``SelfHostedTaskService``.

Big-file split S12 (Issue #2728). ``_ReconcileRecoveryMixin`` holds, moved out of
``nexus/orchestrator/self_hosted_task_service.py``:

* ``_reconcile_direct_action``: an interrupted Direct canonical action (DIRECT_STARTED /
  APPLIED / VERIFIED / COMMITTED) is classified by read-only git probes of the Controller
  and recorded as UNKNOWN_REQUIRES_RECONCILE, never replayed;
* ``_reconcile_direct_failure``: a DIRECT_RECONCILE_REQUIRED task is closed as FINAL_BLOCK
  (NO_MUTATION_OBSERVED) only when the git probes prove that no allowed path moved and no
  Target or Candidate exists, otherwise it stays RETAINED_FOR_REVIEW;
* the static ``_projected_pre_apply_recovery_evidence`` and
  ``_reconcile_projected_pre_apply_failure``: an exact, fully bound lost PRE_APPLY
  projection is restored to the native INTEGRATION_FAILED_PRE_APPLY status;
* ``_resume_external_adoption``, ``_read_adoption_artifact`` and
  ``_validate_persisted_external_adoption``: a crash-interrupted ADOPTING record is
  replayed from the service-owned evidence artifacts, and an adoption replay is accepted
  only when every durable binding still holds.

Their source lines are verbatim, except that every facade-module name they load at run
time (``CANONICAL_SOURCE_ROOT``, ``LifecycleActionType``,
``_EXTERNAL_ADOPTION_CLAIM_CEILING``, ``_jsonable``, ``_utc_now`` and the module
``subprocess``) is resolved at call time through ``_service_module()``, so patches on the
facade keep taking effect; ``base64``, ``hashlib``, ``json``, ``os``, ``re``, ``stat``,
``Path`` and the typing names are imported by the part itself.  Issue #2727 later
changed ``_reconcile_direct_failure`` (it is no longer verbatim): an allowed entry covers
everything below it as a directory, untracked files and both sides of a rename are
probed, names are read NUL-separated, and a malformed allowed entry or a failing listing
probe keeps the task retained (helpers ``_within_allowed_boundary`` and
``_invalid_allowed_boundary``).

This is not read-only code: the Direct members write task state through
``_record_direct_failure`` / ``_checkpoint`` and the PRE_APPLY restore through
``_mutate_state`` (state lock, then the runtime store's atomic replace);
``_resume_external_adoption`` hands the rebuilt request to ``adopt_external_candidate``.
The git probes and the artifact reads themselves change nothing.  Members are reached
through ``self``.
"""

from __future__ import annotations

import base64
import hashlib
import importlib
import json
import os
import re
import stat
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Mapping, Optional

if TYPE_CHECKING:
    from nexus.contracts.lifecycle_action import ExternalCandidateAdoptionRequest


def _service_module():
    # Late binding: the service imports this module at its top level, so its own
    # (and its patched) names are only resolved once a method runs.
    return importlib.import_module("nexus.orchestrator.self_hosted_task_service")


class _ListingProbeFailed(Exception):
    """A Direct-failure listing probe exited non-zero (its output is not evidence)."""


def _invalid_allowed_boundary(boundary: str) -> bool:
    """True unless ``boundary`` (trailing "/" removed) is a normalized repo-relative path."""
    return (
        not boundary
        or boundary.startswith("/")
        or "\\" in boundary
        or any(part in ("", ".", "..") for part in boundary.split("/"))
    )


def _within_allowed_boundary(path: str, boundary: str) -> bool:
    """``path`` is the allowed entry itself or strictly below it as a directory.

    The trailing "/" of a declared directory entry is removed before comparison, so both
    ``docs/`` and ``docs`` cover ``docs`` and ``docs/x.md``, never ``docs2/x.md``.  Used
    only to detect a mutation, so covering more is the fail-closed direction.
    """
    return path == boundary or path.startswith(boundary + "/")


class _ReconcileRecoveryMixin:
    """Mixin base of ``SelfHostedTaskService``; never instantiated on its own."""

    if TYPE_CHECKING:  # provided by SelfHostedTaskService and its other bases
        state_dir: Path

        def _read_state(self, task_id: str) -> Optional[dict[str, Any]]: ...

        def _mutate_state(
            self, task_id: str, mutator: Callable[[dict[str, Any]], None]
        ) -> Optional[dict[str, Any]]: ...

        def _checkpoint(
            self,
            task_id: str,
            status: str,
            values: Optional[Mapping[str, Any]] = None,
            *,
            attempt_id: Optional[str] = None,
        ) -> Optional[dict[str, Any]]: ...

        def _record_direct_failure(
            self, task_id: str, blocker: str, error: str = ""
        ) -> Optional[dict[str, Any]]: ...

        def adopt_external_candidate(
            self,
            raw_request: ExternalCandidateAdoptionRequest | Mapping[str, Any],
        ) -> dict[str, Any]: ...

    # fmt: off
    def _reconcile_direct_action(self, task_id: str) -> Optional[dict[str, Any]]:
        """Classify an interrupted canonical action without replaying it."""
        state = self._read_state(task_id)
        if state is None:
            return None
        if state.get("status") == "DIRECT_INTENT_RECORDED":
            return state
        request = state.get("request") or {}
        controller_raw = request.get("controller_repo_root") or state.get("controller_worktree")
        controller = Path(str(controller_raw or _service_module().CANONICAL_SOURCE_ROOT)).expanduser().resolve()
        base = str(request.get("controller_revision") or state.get("controller_revision") or "")
        observed: dict[str, Any] = {
            "controller_repo_root": str(controller),
            "expected_head": base,
            "current_head": None,
            "dirty": None,
            "commits_since_base": [],
            "working_tree_changes": [],
        }
        try:
            observed["current_head"] = _service_module().subprocess.run(
                ["git", "rev-parse", "HEAD"], cwd=controller, capture_output=True, text=True, check=False,
            ).stdout.strip()
            observed["dirty"] = bool(_service_module().subprocess.run(
                ["git", "status", "--porcelain=v1"], cwd=controller, capture_output=True, text=True, check=False,
            ).stdout.strip())
            if len(base) == 40:
                observed["commits_since_base"] = _service_module().subprocess.run(
                    ["git", "diff", "--name-only", f"{base}..HEAD"], cwd=controller,
                    capture_output=True, text=True, check=False,
                ).stdout.splitlines()
            observed["working_tree_changes"] = _service_module().subprocess.run(
                ["git", "diff", "--name-only"], cwd=controller, capture_output=True, text=True, check=False,
            ).stdout.splitlines()
        except OSError as exc:
            observed["probe_error"] = str(exc)
        return self._record_direct_failure(
            task_id,
            "UNKNOWN_REQUIRES_RECONCILE",
            json.dumps(observed, sort_keys=True, separators=(",", ":")),
        )

    def _reconcile_direct_failure(self, task_id: str) -> Optional[dict[str, Any]]:
        """Close a no-mutation Direct failure without replaying its action."""
        state = self._read_state(task_id)
        if state is None:
            return None
        if state.get("status") != "DIRECT_RECONCILE_REQUIRED":
            return state
        request = state.get("request") if isinstance(state.get("request"), Mapping) else {}
        controller = Path(
            str(request.get("controller_repo_root") or state.get("controller_worktree") or _service_module().CANONICAL_SOURCE_ROOT)  # pyright: ignore[reportOptionalMemberAccess]
        ).expanduser().resolve()
        expected_head = str(request.get("controller_revision") or state.get("controller_revision") or "").strip()  # pyright: ignore[reportOptionalMemberAccess]
        allowed = {str(path).rstrip("/") for path in request.get("allowed_files") or () if str(path).strip()}  # pyright: ignore[reportOptionalMemberAccess]
        invalid_allowed = sorted(
            str(path) for path in request.get("allowed_files") or ()  # pyright: ignore[reportOptionalMemberAccess]
            if str(path).strip() and _invalid_allowed_boundary(str(path).rstrip("/"))
        )
        observed: dict[str, Any] = {
            "controller_repo_root": str(controller),
            "expected_head": expected_head,
            "current_head": None,
            "expected_head_is_ancestor": False,
            "commits_since_base": [],
            "working_tree_changes": [],
            "staged_changes": [],
            "untracked_changes": [],
            "allowed_paths": sorted(allowed),
            "invalid_allowed_paths": invalid_allowed,
            "target_created": bool(state.get("target_worktree") or state.get("lease")),
            "candidate_created": bool(state.get("candidate_ref") or state.get("candidate_commit_sha") or state.get("promotion_packet")),
        }

        def listing(*args: str) -> list[str]:
            # -z: names are NUL-separated and never C-quoted; --no-renames: a rename lists
            # both its source and its destination.  A failing probe is not evidence.
            result = _service_module().subprocess.run(
                ["git", *args], cwd=controller, capture_output=True, text=True, check=False,
            )
            if result.returncode != 0:
                raise _ListingProbeFailed(f"git {' '.join(args)} exited {result.returncode}")
            return [name for name in result.stdout.split("\0") if name]

        probe_error = ""
        try:
            observed["current_head"] = _service_module().subprocess.run(
                ["git", "rev-parse", "HEAD"], cwd=controller, capture_output=True, text=True, check=False,
            ).stdout.strip()
            if len(expected_head) == 40 and observed["current_head"]:
                ancestor = _service_module().subprocess.run(
                    ["git", "merge-base", "--is-ancestor", expected_head, str(observed["current_head"])],
                    cwd=controller, capture_output=True, text=True, check=False,
                )
                observed["expected_head_is_ancestor"] = ancestor.returncode == 0
                if observed["expected_head_is_ancestor"]:
                    observed["commits_since_base"] = listing(
                        "diff", "--name-only", "--no-renames", "-z", f"{expected_head}..HEAD",
                    )
            observed["working_tree_changes"] = listing("diff", "--name-only", "--no-renames", "-z")
            observed["staged_changes"] = listing("diff", "--cached", "--name-only", "--no-renames", "-z")
            # untracked, not ignored, named from the repository root like git diff
            observed["untracked_changes"] = sorted(listing(
                "ls-files", "--others", "--exclude-standard", "--full-name", "-z", "--", ":(top)",
            ))
        except (OSError, _ListingProbeFailed) as exc:
            probe_error = str(exc)
            observed["probe_error"] = probe_error

        touched = {
            str(path)
            for path in (
                list(observed.get("commits_since_base") or [])
                + list(observed.get("working_tree_changes") or [])
                + list(observed.get("staged_changes") or [])
                + list(observed.get("untracked_changes") or [])
            )
        }
        allowed_touched = sorted(
            path
            for path in touched
            if any(_within_allowed_boundary(path, boundary) for boundary in allowed)
        )
        observed["allowed_paths_touched"] = allowed_touched
        safe_no_mutation = bool(
            not probe_error
            and len(expected_head) == 40
            and bool(observed.get("current_head"))
            and observed.get("expected_head_is_ancestor") is True
            and not observed.get("target_created")
            and not observed.get("candidate_created")
            and not allowed_touched
            and not invalid_allowed
        )
        action = dict(state.get("canonical_action") or {})
        reconciliation = dict(action.get("reconciliation") or {})
        now = _service_module()._utc_now()
        if safe_no_mutation:
            reconciliation.update({
                "status": "RECONCILED",
                "decision": "NO_MUTATION_OBSERVED",
                "evidence": observed,
                "reconciled_at": now,
            })
            action["reconciliation"] = reconciliation
            return self._checkpoint(
                task_id,
                "FINAL_BLOCK",
                {
                    "canonical_action": action,
                    "reconciliation_status": "RECONCILED",
                    "reconciliation_decision": "NO_MUTATION_OBSERVED",
                    "reconciliation_evidence": observed,
                    "reconciliation_required": False,
                    "cleanup_decision": "ALREADY_REMOVED",
                    "cleanup_eligible": True,
                    "cleanup_performed": False,
                    "promotion_status": "NOT_CREATED",
                    "terminal_status": "FINAL_BLOCK",
                    "state_retention_status": "TERMINAL",
                    "archive_eligible": True,
                },
                attempt_id=state.get("attempt_id"),
            )

        reconciliation.update({
            "status": "REQUIRED",
            "decision": "RETAINED_FOR_REVIEW",
            "evidence": observed,
            "reconciled_at": now,
        })
        action["reconciliation"] = reconciliation
        return self._checkpoint(
            task_id,
            "DIRECT_RECONCILE_REQUIRED",
            {
                "canonical_action": action,
                "reconciliation_status": "REQUIRED",
                "reconciliation_decision": "RETAINED_FOR_REVIEW",
                "reconciliation_evidence": observed,
                "reconciliation_required": True,
            },
            attempt_id=state.get("attempt_id"),
        )

    @staticmethod
    def _projected_pre_apply_recovery_evidence(
        state: Mapping[str, Any],
    ) -> Optional[dict[str, Any]]:
        """Return bounded evidence for an exact lost pre-apply projection.

        Older reconciliation projected a non-applied integration failure to
        FINAL_BLOCK/NOT_CREATED while retaining the original PRE_APPLY packet.
        Only that exact, fully bound projection may be restored to the native
        pre-apply status for a fresh closure rebind.
        """
        if (
            state.get("status") != "FINAL_BLOCK"
            or state.get("promotion_status") != "NOT_CREATED"
            or state.get("terminal_status") != "INTEGRATION_FAILED_PRE_APPLY"
            or state.get("final_disposition") != "INTEGRATION_FAILED_PRE_APPLY"
            or state.get("integration_status") != "NOT_APPLIED"
            or state.get("merge_performed")
            or state.get("integration_result_sha")
            or state.get("integration_receipt")
        ):
            return None
        execution = state.get("integration_execution")
        closure = state.get("integration_closure_binding")
        grant = state.get("integration_approval_grant")
        acceptance = state.get("external_acceptance")
        preview = state.get("integration_preview")
        authorization = state.get("integration_authorization")
        packet = state.get("promotion_packet")
        approved = state.get("approved_binding")
        if not all(
            isinstance(value, Mapping) and bool(value)
            for value in (
                execution,
                closure,
                grant,
                acceptance,
                preview,
                authorization,
                packet,
                approved,
            )
        ):
            return None
        if (
            execution.get("stage") != "PRE_APPLY"  # pyright: ignore[reportOptionalMemberAccess]
            or execution.get("merge_performed") is not False  # pyright: ignore[reportOptionalMemberAccess]
            or execution.get("post_apply_verified") is not False  # pyright: ignore[reportOptionalMemberAccess]
            or execution.get("branch_head_before")  # pyright: ignore[reportOptionalMemberAccess]
            != execution.get("branch_head_after")  # pyright: ignore[reportOptionalMemberAccess]
            or not closure.get("binding_hash")  # pyright: ignore[reportOptionalMemberAccess]
            or not grant.get("approval_id")  # pyright: ignore[reportOptionalMemberAccess]
            or not grant.get("consumed_at")  # pyright: ignore[reportOptionalMemberAccess]
        ):
            return None
        identity = {
            "task_id": str(state.get("task_id") or ""),
            "attempt_id": str(state.get("attempt_id") or ""),
            "candidate_commit_sha": str(packet.get("candidate_commit_sha") or ""),  # pyright: ignore[reportOptionalMemberAccess]
            "candidate_tree_sha": str(packet.get("candidate_tree_sha") or ""),  # pyright: ignore[reportOptionalMemberAccess]
            "candidate_state_hash": str(packet.get("candidate_state_hash") or ""),  # pyright: ignore[reportOptionalMemberAccess]
            "verified_receipt_hash": str(packet.get("verified_receipt_hash") or ""),  # pyright: ignore[reportOptionalMemberAccess]
        }
        if not identity["task_id"] or not identity["attempt_id"] or any(
            not identity[key]
            for key in (
                "candidate_commit_sha",
                "candidate_tree_sha",
                "candidate_state_hash",
                "verified_receipt_hash",
            )
        ):
            return None
        status_history = state.get("status_history")
        if (
            not isinstance(status_history, list)
            or len(status_history) < 2
            or not all(isinstance(item, Mapping) for item in status_history[-2:])
            or [item.get("status") for item in status_history[-2:]]
            != ["INTEGRATION_FAILED_PRE_APPLY", "FINAL_BLOCK"]
            or not str(state.get("integration_error") or "").strip()
        ):
            return None
        for key, expected in identity.items():
            if key in closure and str(closure.get(key) or "") != expected:  # pyright: ignore[reportOperatorIssue, reportOptionalMemberAccess]
                return None
            if key.startswith("candidate_") or key == "verified_receipt_hash":
                if str(approved.get(key) or "") != expected:  # pyright: ignore[reportOptionalMemberAccess]
                    return None
        if str(execution.get("candidate_commit_sha") or identity["candidate_commit_sha"]) != identity["candidate_commit_sha"]:  # pyright: ignore[reportOptionalMemberAccess]
            return None
        acceptance_hash = str(closure.get("acceptance_receipt_hash") or "")  # pyright: ignore[reportOptionalMemberAccess]
        authorization_hash = str(closure.get("authorization_hash") or "")  # pyright: ignore[reportOptionalMemberAccess]
        if (
            str(grant.get("bound_task_id") or "") != identity["task_id"]  # pyright: ignore[reportOptionalMemberAccess]
            or str(grant.get("bound_attempt_id") or "") != identity["attempt_id"]  # pyright: ignore[reportOptionalMemberAccess]
            or str(grant.get("bound_action_type") or "")  # pyright: ignore[reportOptionalMemberAccess]
            != _service_module().LifecycleActionType.CANDIDATE_INTEGRATE.value
            or str(acceptance.get("task_id") or "") != identity["task_id"]  # pyright: ignore[reportOptionalMemberAccess]
            or str(acceptance.get("attempt_id") or "") != identity["attempt_id"]  # pyright: ignore[reportOptionalMemberAccess]
            or str(acceptance.get("candidate_commit") or "")  # pyright: ignore[reportOptionalMemberAccess]
            != identity["candidate_commit_sha"]
            or acceptance.get("passed") is not True  # pyright: ignore[reportOptionalMemberAccess]
            or str(acceptance.get("receipt_hash") or "") != acceptance_hash  # pyright: ignore[reportOptionalMemberAccess]
            or str(preview.get("task_id") or "") != identity["task_id"]  # pyright: ignore[reportOptionalMemberAccess]
            or str(preview.get("candidate_commit") or "")  # pyright: ignore[reportOptionalMemberAccess]
            != identity["candidate_commit_sha"]
            or str(preview.get("acceptance_receipt_hash") or "") != acceptance_hash  # pyright: ignore[reportOptionalMemberAccess]
            or str(authorization.get("task_id") or "") != identity["task_id"]  # pyright: ignore[reportOptionalMemberAccess]
            or str(authorization.get("attempt_id") or "") != identity["attempt_id"]  # pyright: ignore[reportOptionalMemberAccess]
            or str(authorization.get("candidate_commit") or "")  # pyright: ignore[reportOptionalMemberAccess]
            != identity["candidate_commit_sha"]
            or str(authorization.get("candidate_tree_sha") or "")  # pyright: ignore[reportOptionalMemberAccess]
            != identity["candidate_tree_sha"]
            or str(authorization.get("candidate_state_hash") or "")  # pyright: ignore[reportOptionalMemberAccess]
            != identity["candidate_state_hash"]
            or str(authorization.get("candidate_receipt_hash") or "")  # pyright: ignore[reportOptionalMemberAccess]
            != identity["verified_receipt_hash"]
            or str(authorization.get("acceptance_receipt_hash") or "")  # pyright: ignore[reportOptionalMemberAccess]
            != acceptance_hash
            or str(authorization.get("authorization_hash") or "")  # pyright: ignore[reportOptionalMemberAccess]
            != authorization_hash
        ):
            return None
        for key, expected in {
            "candidate_commit_sha": identity["candidate_commit_sha"],
            "candidate_tree_sha": identity["candidate_tree_sha"],
            "candidate_state_hash": identity["candidate_state_hash"],
            "verified_receipt_hash": identity["verified_receipt_hash"],
            "acceptance_receipt_hash": acceptance_hash,
        }.items():
            if str(grant.get(key) or "") != expected:  # pyright: ignore[reportOptionalMemberAccess]
                return None
        projection = {
            **identity,
            "closure_binding_hash": str(closure.get("binding_hash")),  # pyright: ignore[reportOptionalMemberAccess]
            "integration_approval_id": str(grant.get("approval_id")),  # pyright: ignore[reportOptionalMemberAccess]
            "integration_execution_sha256": hashlib.sha256(
                json.dumps(
                    _service_module()._jsonable(dict(execution)),  # pyright: ignore[reportArgumentType, reportCallIssue]
                    sort_keys=True,
                    separators=(",", ":"),
                    ensure_ascii=False,
                ).encode()
            ).hexdigest(),
        }
        projection["projection_sha256"] = hashlib.sha256(
            json.dumps(
                projection,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            ).encode()
        ).hexdigest()
        return projection

    def _reconcile_projected_pre_apply_failure(
        self,
        task_id: str,
        evidence: Mapping[str, Any],
    ) -> dict[str, Any]:
        now = _service_module()._utc_now()

        def mutate(current: dict[str, Any]) -> None:
            current_evidence = self._projected_pre_apply_recovery_evidence(current)
            if current_evidence is None or dict(current_evidence) != dict(evidence):
                raise RuntimeError("PRE_APPLY_RECONCILIATION_CONCURRENCY_DRIFT")
            history = current.get("integration_reconciliation_history")
            if "integration_reconciliation_history" in current and not isinstance(history, list):
                raise RuntimeError("PRE_APPLY_RECONCILIATION_HISTORY_MALFORMED")
            if history is None:
                history = []
                current["integration_reconciliation_history"] = history
            if history and history[-1].get("projection_sha256") == evidence.get("projection_sha256"):
                return
            history.append({
                "schema": "nexus.pre_apply_reconciliation.v1",
                **_service_module()._jsonable(dict(evidence)),
                "reconciled_at": now,
                "decision": "RESTORE_NATIVE_PRE_APPLY_STATUS",
            })
            current["status"] = "INTEGRATION_FAILED_PRE_APPLY"
            current["promotion_status"] = "INTEGRATION_FAILED_PRE_APPLY"
            current["terminal_status"] = "INTEGRATION_FAILED_PRE_APPLY"
            current["final_disposition"] = "INTEGRATION_FAILED_PRE_APPLY"
            current["reconciliation_status"] = "RECONCILED"
            current["reconciliation_decision"] = "RESTORE_NATIVE_PRE_APPLY_STATUS"
            current["state_retention_status"] = "ACTIVE"
            current["archive_eligible"] = False
            current["cleanup_eligible"] = False
            status_history = current.get("status_history")
            if not isinstance(status_history, list):
                raise RuntimeError("PRE_APPLY_RECONCILIATION_STATUS_HISTORY_MALFORMED")
            status_history.append({
                "at": now,
                "status": "INTEGRATION_FAILED_PRE_APPLY",
                "reason": "projected_pre_apply_reconciled",
            })
            current["updated_at"] = now

        persisted = self._mutate_state(task_id, mutate)
        if persisted is None:
            raise KeyError(f"unknown task_id: {task_id}")
        return persisted

    def _resume_external_adoption(
        self,
        task_id: str,
        state: Mapping[str, Any],
    ) -> dict[str, Any]:
        """Replay a crash-interrupted external adoption from durable evidence.

        The original request deliberately omits receipt payloads from the
        task state.  Only the service-owned artifact locators are accepted on
        restart, and both paths and content hashes are checked before the
        normal adoption verifier is called.  This keeps restart idempotent
        without granting a partially written ADOPTING state any authority.
        """
        request = state.get("request")
        if not isinstance(request, Mapping) or request.get("task_id") != task_id:
            raise RuntimeError("external adoption restart request is missing or mismatched")

        def load_artifact(field: str, digest_field: str) -> bytes:
            raw_locator = state.get(field)
            digest = str(request.get(digest_field) or "")
            if not isinstance(raw_locator, str) or not raw_locator or not re.fullmatch(r"[0-9a-f]{64}", digest):
                raise RuntimeError("external adoption restart evidence locator is missing")
            kind = {"validation_receipt_locator": "validation", "acceptance_receipt_locator": "acceptance"}.get(field)
            if kind is None:
                raise RuntimeError("external adoption restart evidence locator is unsupported")
            content = self._read_adoption_artifact(task_id, raw_locator, digest, kind)
            if hashlib.sha256(content).hexdigest() != digest:
                raise RuntimeError("external adoption restart evidence hash mismatch")
            return content

        replay = dict(request)
        replay["validation_receipt_b64"] = base64.b64encode(
            load_artifact("validation_receipt_locator", "validation_receipt_sha256")
        ).decode("ascii")
        replay["acceptance_receipt_b64"] = base64.b64encode(
            load_artifact("acceptance_receipt_locator", "acceptance_receipt_sha256")
        ).decode("ascii")
        return self.adopt_external_candidate(replay)

    def _read_adoption_artifact(
        self, task_id: str, raw_locator: str, digest: str, kind: str,
    ) -> bytes:
        """Read a service-owned adoption artifact without following symlinks."""
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", task_id):
            raise RuntimeError("adoption artifact task id is unsafe")
        if not re.fullmatch(r"[a-z][a-z0-9_-]*", kind) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise RuntimeError("adoption artifact locator is malformed")
        expected = self.state_dir / "adoption-artifacts" / task_id / f"{kind}-{digest}.json"
        try:
            if Path(raw_locator) != expected:
                raise RuntimeError("external adoption evidence locator is not canonical")
            nofollow = getattr(os, "O_NOFOLLOW", 0)
            root_fd = os.open(self.state_dir, os.O_RDONLY | os.O_DIRECTORY | nofollow)
            try:
                artifact_fd = os.open("adoption-artifacts", os.O_RDONLY | os.O_DIRECTORY | nofollow, dir_fd=root_fd)
                try:
                    task_fd = os.open(task_id, os.O_RDONLY | os.O_DIRECTORY | nofollow, dir_fd=artifact_fd)
                    try:
                        fd = os.open(expected.name, os.O_RDONLY | nofollow, dir_fd=task_fd)
                    finally:
                        os.close(task_fd)
                finally:
                    os.close(artifact_fd)
            finally:
                os.close(root_fd)
            try:
                if not stat.S_ISREG(os.fstat(fd).st_mode):
                    raise RuntimeError("external adoption restart evidence is not a regular file")
                content = os.read(fd, 1024 * 1024 + 1)
            finally:
                os.close(fd)
            if hashlib.sha256(content).hexdigest() != digest:
                raise RuntimeError("external adoption restart evidence hash mismatch")
            return content
        except RuntimeError:
            raise
        except OSError as exc:
            raise RuntimeError("external adoption restart evidence is unreadable or escaped service state") from exc

    def _validate_persisted_external_adoption(
        self, state: Mapping[str, Any], request: ExternalCandidateAdoptionRequest,
        semantic_hash: str, acceptance: Mapping[str, Any],
    ) -> None:
        """Validate every durable binding before returning an adoption replay."""
        receipt = state.get("adoption_receipt")
        packet = state.get("promotion_packet")
        verified = state.get("verified_receipt")
        if not isinstance(receipt, Mapping) or not isinstance(packet, Mapping) or not isinstance(verified, Mapping):
            raise RuntimeError("external adoption replay evidence is incomplete")
        def canonical(value: Any) -> str:
            return hashlib.sha256(json.dumps(
                _service_module()._jsonable(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False,
            ).encode("utf-8")).hexdigest()
        if state.get("status") != "PENDING_HUMAN_APPROVAL" or state.get("promotion_status") != "PENDING_HUMAN_APPROVAL":
            raise RuntimeError("external adoption replay status is invalid")
        if state.get("adoption_request_hash") != semantic_hash or state.get("action") != request.action.model_dump(mode="json"):
            raise RuntimeError("external adoption replay request binding mismatch")
        if (
            state.get("task_card_path") != request.task_card_path
            or state.get("task_card_hash") != request.task_card_hash
            or state.get("controller_revision") != request.controller_revision
            or state.get("target_initial_revision") != request.target_base_revision
            or state.get("candidate_commit_sha") != request.candidate_commit_sha
            or state.get("candidate_tree_sha") != request.candidate_tree_sha
        ):
            raise RuntimeError("external adoption replay state binding mismatch")
        candidate_identity = state.get("candidate")
        expected_candidate_identity = {
            "candidate_commit_sha": request.candidate_commit_sha,
            "candidate_tree_sha": request.candidate_tree_sha,
            "candidate_state_hash": state.get("candidate_state_hash"),
            "verified_receipt_hash": state.get("verified_receipt_hash"),
        }
        if (
            not isinstance(candidate_identity, Mapping)
            or dict(candidate_identity) != expected_candidate_identity
            or state.get("candidate_state_hash") != packet.get("candidate_state_hash")
            or state.get("candidate_state_hash") != receipt.get("candidate_state_hash")
        ):
            raise RuntimeError("external adoption replay candidate identity mismatch")
        contract_payload = state.get("contract")
        # Mirror SelfHostedTaskContract.contract_hash byte-for-byte: the
        # persisted dump carries an explicit expected_evidence null for
        # legacy contracts, while the hash rule drops a null universe so
        # legacy hashes stay byte-identical. Any add/drop/mutate of a
        # non-null universe still changes these bytes versus the stored
        # hash and fails closed below.
        contract_canonical = {
            key: value for key, value in contract_payload.items() if key != "contract_hash"
        } if isinstance(contract_payload, Mapping) else None
        if contract_canonical is not None and contract_canonical.get("expected_evidence") is None:
            contract_canonical.pop("expected_evidence", None)
        if contract_canonical is None or state.get("contract_hash") != canonical(contract_canonical):
            raise RuntimeError("external adoption replay contract binding mismatch")
        expected_receipt = {
            "schema": "nexus.external_candidate_adoption_receipt.v1", "task_id": request.task_id,
            "attempt_id": request.attempt_id, "action_id": request.action_id,
            "idempotency_key": request.idempotency_key, "adoption_request_hash": semantic_hash,
            "task_card_path": request.task_card_path, "task_card_hash": request.task_card_hash,
            "contract_hash": state.get("contract_hash"), "controller_revision": request.controller_revision,
            "target_base_revision": request.target_base_revision, "candidate_commit_sha": request.candidate_commit_sha,
            "candidate_tree_sha": request.candidate_tree_sha, "candidate_diff_sha256": request.candidate_diff_sha256,
            "candidate_state_hash": packet.get("candidate_state_hash"), "verified_receipt_hash": packet.get("verified_receipt_hash"),
            "validation_receipt_sha256": request.validation_receipt_sha256,
            "acceptance_receipt_sha256": request.acceptance_receipt_sha256, "reviewer_id": receipt.get("reviewer_id"),
            "repository_contract_policy_revision_hash": verified.get("repository_contract_policy_revision_hash"),
            "derived_contract_projection": state.get("derived_contract_projection"),
            "forbidden_repository_patterns": list((state.get("derived_contract_projection") or {}).get("forbidden_repository_patterns") or ()),
            "candidate_ref": state.get("candidate_ref"), "promotion_packet_hash": canonical(packet),
            "worker_invocations": 0, "candidate_rewritten": False, "approval_performed": False,
            "integration_performed": False, "merge_performed": False, "push_performed": False,
            "public_claim_allowed": False, "production_ready": False,
            "claim_ceiling": list(_service_module()._EXTERNAL_ADOPTION_CLAIM_CEILING),
            "issued_at": state.get("submitted_at"),
        }
        if any(receipt.get(key) != value for key, value in expected_receipt.items()):
            raise RuntimeError("external adoption replay receipt binding mismatch")
        if canonical(receipt) != canonical(expected_receipt):
            raise RuntimeError("external adoption replay receipt contains unexpected fields")
        if state.get("adoption_receipt_hash") != canonical(receipt):
            raise RuntimeError("external adoption replay receipt hash mismatch")
        if state.get("verified_receipt_hash") != packet.get("verified_receipt_hash") or canonical(verified) != packet.get("verified_receipt_hash"):
            raise RuntimeError("external adoption replay verified receipt binding mismatch")
        derived_projection = state.get("derived_contract_projection")
        if (
            not isinstance(derived_projection, Mapping)
            or derived_projection.get("repository_contract_policy_revision_hash")
            != verified.get("repository_contract_policy_revision_hash")
        ):
            raise RuntimeError("external adoption replay policy evidence binding mismatch")
        packet_fields = {
            "task_id": request.task_id, "contract_hash": state.get("contract_hash"),
            "controller_revision": request.controller_revision, "target_base_revision": request.target_base_revision,
            "candidate_state_hash": state.get("candidate_state_hash"), "candidate_commit_sha": request.candidate_commit_sha,
            "candidate_tree_sha": request.candidate_tree_sha, "verified_receipt_hash": state.get("verified_receipt_hash"),
            "candidate_commit_created": True, "promotion_status": "PENDING_HUMAN_APPROVAL",
            "public_claim_allowed": False, "production_ready": False, "merge_performed": False,
            "push_performed": False,
        }
        if any(packet.get(key) != value for key, value in packet_fields.items()):
            raise RuntimeError("external adoption replay promotion packet binding mismatch")
        for field in ("public_claim_allowed", "production_ready", "merge_performed", "push_performed", "candidate_commit_created"):
            if field == "candidate_commit_created":
                if verified.get(field) not in (None, False):
                    raise RuntimeError("external adoption replay verified receipt contains promotion authority")
            elif verified.get(field) not in (None, False):
                raise RuntimeError("external adoption replay verified receipt contains downstream authority")
        if verified.get("authority_change_required") not in (None, False):
            raise RuntimeError("external adoption replay verified receipt contains authority findings")
        expected_acceptance = {
            "schema": "nexus.external_candidate_acceptance.v1",
            "task_id": request.task_id,
            "candidate_commit_sha": request.candidate_commit_sha,
            "candidate_tree_sha": request.candidate_tree_sha,
            "candidate_diff_sha256": request.candidate_diff_sha256,
            "validation_receipt_sha256": request.validation_receipt_sha256,
            "disposition": "ACCEPT_CANDIDATE",
            "reviewer_id": acceptance.get("reviewer_id"),
        }
        if (
            dict(state.get("external_acceptance") or {}) != dict(acceptance)
            or any(acceptance.get(key) != value for key, value in expected_acceptance.items())
            or receipt.get("reviewer_id") != acceptance.get("reviewer_id")
        ):
            raise RuntimeError("external adoption replay acceptance binding mismatch")
        if any(state.get(key) not in (None, False) for key in ("approved_binding", "integration_authorization", "integration_receipt", "merge_performed", "push_performed", "public_claim_allowed", "production_ready")):
            raise RuntimeError("external adoption replay contains downstream authority")
    # fmt: on
