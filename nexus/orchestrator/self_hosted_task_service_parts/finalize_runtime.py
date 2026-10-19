"""Finalize-runtime members of ``SelfHostedTaskService``.

Big-file split S11 (Issue #2710). ``_FinalizeRuntimeMixin`` holds, moved out of
``nexus/orchestrator/self_hosted_task_service.py``:

* ``_promotion_authority_error``: whether a production-bound task may become promotable
  (ephemeral rehearsal state, the canonical state root, a durable Controller that is its
  own repository at the contract's Controller revision);
* the static ``_run_fail_to_pass_probe``: the contract verifiers on a clean detached
  checkout of the base revision (#2274 / #2387);
* ``_finalize_runtime_candidate``: capture, verification, Core, attempt resolution, the
  Track-1 mirror, the promotion authority, the fail-to-pass gate, the Candidate commit,
  the protected Candidate ref and the Target cleanup of a completed attempt, each step
  written through the caller's ``update``;
* ``_finalize_runtime_failure``: the terminal write of a failed or timed-out attempt
  (verified-uncommitted retention, or cleanup / salvage / task-branch restore) through
  ``_checkpoint``;
* the worker-process helpers ``_run_owned_task``, ``_wait_for_owner``, ``_launch_worker``,
  the static ``_pid_alive`` and ``_terminate_owned_processes``.

Their source lines are verbatim, except that every facade-module name they load at run
time (the collaborators ``WorktreeManager``, ``SelfHostedDevelopmentController``,
``CandidateVerifier``, ``CandidateCommitter`` and ``resolve_attempt``; ``replace``,
``AmbientCoreVerdictBlocked``, ``AttemptResolutionVerdict``, ``CliWorkerStatus``,
``FAIL_TO_PASS_EVIDENCE_TOKEN``, ``FAIL_TO_PASS_PROBE_SCHEMA``,
``_base_run_collected_nothing``, ``_fail_to_pass_blocked``, ``_temporary_state_roots``,
``_utc_now``; the modules ``shutil``, ``signal``, ``subprocess``, ``tempfile`` and ``time``)
is resolved at call time through ``_service_module()``, so patches on the facade keep
taking effect; ``os`` (already loaded by bare name in other parts), ``Path``,
``SimpleNamespace`` and the typing names are imported by the part itself.  So is
``__file__``: ``_launch_worker`` passes
``Path(__file__).resolve().parents[2]`` (the repository root) to the worker launch as its
source root, and that must stay the facade's file.

This is not read-only code: the finalize members write task state through ``update`` /
``_checkpoint`` (state lock, then the runtime store's atomic replace; a terminal status
also records the terminal Core record), create the Candidate commit and its protected ref,
remove or salvage the Target worktree and run git and the contract verifiers in a
temporary base checkout; ``_launch_worker`` / ``_run_owned_task`` hand the attempt to
``RuntimeCoordinationBridge``, ``_pid_alive`` reaps a finished child of this process and
``_terminate_owned_processes`` signals the task's recorded process groups.  Members are
reached through ``self``.
"""

from __future__ import annotations

import importlib
import os
from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, Callable, Mapping, Optional, cast

if TYPE_CHECKING:
    from nexus.executors.worker_contract import WorkerExecutionReceipt
    from nexus.orchestrator.candidate_verifier import VerifiedCandidateReceipt
    from nexus.orchestrator.self_hosted_controller import SelfHostedDevelopmentController
    from nexus.orchestrator.task_contract import ArchitectTaskContract
    from nexus.orchestrator.worktree_manager import TargetWorktreeLease


def _service_module():
    # Late binding: the service imports this module at its top level, so its own
    # (and its patched) names are only resolved once a method runs.
    return importlib.import_module("nexus.orchestrator.self_hosted_task_service")


class _FinalizeRuntimeMixin:
    """Mixin base of ``SelfHostedTaskService``; never instantiated on its own."""

    if TYPE_CHECKING:  # provided by SelfHostedTaskService and its other bases
        ephemeral: bool
        state_dir: Path
        _custom_runner: Optional[Callable[..., dict[str, Any]]]

        @staticmethod
        def canonical_state_dir() -> Path: ...

        def build_contract(self, request: Mapping[str, Any]) -> ArchitectTaskContract: ...

        def _read_state(self, task_id: str) -> Optional[dict[str, Any]]: ...

        def _checkpoint(
            self,
            task_id: str,
            status: str,
            values: Optional[Mapping[str, Any]] = None,
            *,
            attempt_id: Optional[str] = None,
        ) -> Optional[dict[str, Any]]: ...

        def _bridge_validate_claim(
            self,
            task_id: str,
            attempt_id: str | None = None,
            *,
            operation: str = "MUTATION",
        ) -> Optional[dict[str, Any]]: ...

        def _lease_from_state(self, state: Mapping[str, Any]) -> TargetWorktreeLease: ...

        def _capture_resumed_candidate(
            self,
            contract: ArchitectTaskContract,
            controller: SelfHostedDevelopmentController,
            lease: TargetWorktreeLease,
            state: Mapping[str, Any],
        ) -> Any: ...

        @staticmethod
        def _receipt_from_state(value: Any) -> Optional[WorkerExecutionReceipt]: ...

        def _ambient_core_required(self, contract: Any, request: Mapping[str, Any]) -> bool: ...

        def _verify_ambient_core_candidate(
            self,
            *,
            contract: Any,
            request: Mapping[str, Any],
            lease: Any,
            state: Mapping[str, Any],
            candidate: Any,
            verified: VerifiedCandidateReceipt,
        ) -> VerifiedCandidateReceipt: ...

        def _record_track1_verified_outcome(
            self,
            *,
            contract: Any,
            lease: Any,
            state: Mapping[str, Any],
            candidate: Any,
            verified: VerifiedCandidateReceipt,
            execution: WorkerExecutionReceipt,
        ) -> dict[str, Any]: ...

    # fmt: off
    def _promotion_authority_error(
        self,
        *,
        contract: Optional[ArchitectTaskContract] = None,
        request: Optional[Mapping[str, Any]] = None,
    ) -> Optional[str]:
        """Return a fail-closed reason when a task cannot become promotable.

        Ephemeral services are test/rehearsal surfaces.  A production-bound
        task (one with a task card or lifecycle identity requirement) must be
        backed by the canonical state root and a durable, existing Controller.
        This prevents a temporary rehearsal receipt from becoming an
        approval/integration authority by accident.
        """
        req = request or {}
        production_bound = bool(
            req.get("task_card_required") or req.get("lifecycle_identity_required")
        )
        if self.ephemeral and production_bound:
            return "EPHEMERAL_PROMOTION_FORBIDDEN: rehearsal state cannot become a promotable Candidate"
        if not production_bound or contract is None:
            return None
        if self.state_dir != self.canonical_state_dir():
            return "CANONICAL_STATE_REQUIRED: production Candidate must use the canonical state root"
        controller = Path(contract.controller_repo_root).expanduser().resolve()
        if not controller.is_dir():
            return f"CONTROLLER_MISSING: {controller}"
        temporary_roots = _service_module()._temporary_state_roots()
        if any(controller == root or root in controller.parents for root in temporary_roots):
            return f"DURABLE_CONTROLLER_REQUIRED: temporary Controller is not promotable: {controller}"
        try:
            result = _service_module().subprocess.run(
                ["git", "rev-parse", "--show-toplevel"],
                cwd=controller,
                capture_output=True,
                text=True,
                check=False,
            )
        except OSError as exc:
            return f"CONTROLLER_PROBE_FAILED: {exc}"
        if result.returncode != 0 or Path(result.stdout.strip()).resolve() != controller:
            return f"CONTROLLER_NOT_A_REPOSITORY: {controller}"
        try:
            current_revision = _service_module().subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=controller,
                capture_output=True,
                text=True,
                check=False,
            ).stdout.strip()
        except OSError as exc:
            return f"CONTROLLER_REVISION_PROBE_FAILED: {exc}"
        if contract.controller_revision and current_revision != contract.controller_revision:
            return (
                "CONTROLLER_REVISION_MISMATCH: "
                f"expected {contract.controller_revision}, got {current_revision}"
            )
        return None

    @staticmethod
    def _run_fail_to_pass_probe(manager, contract) -> dict[str, Any]:
        """Run the contract verifiers on a clean detached checkout of the base.

        A repair task must fail its verifiers on ``target_base_revision`` and
        pass them on the candidate.  The checkout is a fresh temporary git
        worktree (never the candidate Target nor the Controller working tree)
        and is always removed.  Any infrastructure problem fails closed as
        BASE_NOT_PHYSICAL_FAIL.  The code_integrity_v1 internal check inspects
        the candidate diff and has no base meaning, so it is not re-run.
        """
        base_revision = str(contract.target_base_revision)
        probe: dict[str, Any] = {
            "schema": _service_module().FAIL_TO_PASS_PROBE_SCHEMA,
            "status": "BASE_NOT_PHYSICAL_FAIL",
            "base_revision": base_revision,
            "base_exit_codes": [],
            "required": True,
        }
        scratch = Path(_service_module().tempfile.mkdtemp(prefix="nexus-f2p-base-"))
        checkout = scratch / "base"
        added = False
        try:
            commands = [
                command
                for command in contract.verifier_commands
                if isinstance(command, str) and command.strip() and command != "code_integrity_v1"
            ]
            if not commands:
                return probe
            controller_root = str(Path(contract.controller_repo_root).resolve())
            manager._run_git(
                ["worktree", "add", "--detach", str(checkout), base_revision],
                cwd=controller_root,
            )
            added = True
            passed, evidence, failures = _service_module().CandidateVerifier._run_verifiers(
                # Only verifier_commands is read; code_integrity_v1 is excluded above.
                cast(Any, SimpleNamespace(verifier_commands=commands)), str(checkout), None
            )
            exit_codes = [item.exit_code for item in evidence]
            probe["base_exit_codes"] = exit_codes
            expected = len(_service_module().CandidateVerifier.effective_verifier_manifest(commands))
            normal = bool(evidence) and len(evidence) == expected and all(
                item.status == _service_module().CliWorkerStatus.COMPLETED.value and item.exit_code is not None
                for item in evidence
            )
            inconsistent = any(
                f.startswith(("verifier_invalid", "verifier_evidence_inconsistent")) for f in failures
            )
            if not normal or inconsistent:
                # Every base command must have run to a normal exit; a timeout or
                # start failure is not evidence that base fails.
                probe["status"] = "BASE_NOT_PHYSICAL_FAIL"
            elif passed:
                probe["status"] = "BASE_ALREADY_PASS"
            elif (nothing_ran := _service_module()._base_run_collected_nothing(evidence, checkout)) is not None:
                probe["status"] = "BASE_NOT_PHYSICAL_FAIL"
                probe["reason"] = nothing_ran
            elif any(item.exit_code != 0 for item in evidence):
                probe["status"] = "VERIFIED"
        except Exception as exc:  # noqa: BLE001 - infrastructure errors fail closed
            probe["status"] = "BASE_NOT_PHYSICAL_FAIL"
            probe["error"] = str(exc)[:500]
        finally:
            if added:
                try:
                    manager._run_git(
                        ["worktree", "remove", "--force", str(checkout)],
                        cwd=str(Path(contract.controller_repo_root).resolve()),
                    )
                except Exception as exc:  # noqa: BLE001 - cleanup failure fails closed
                    probe["status"] = "BASE_NOT_PHYSICAL_FAIL"
                    probe["cleanup_error"] = str(exc)[:500]
            _service_module().shutil.rmtree(scratch, ignore_errors=True)
            if added:
                try:
                    manager._run_git(
                        ["worktree", "prune"],
                        cwd=str(Path(contract.controller_repo_root).resolve()),
                    )
                except Exception:  # noqa: BLE001
                    pass
        return probe

    def _finalize_runtime_candidate(
        self, contract, request, lease, state, attempts, update, *, execution, status
    ):
        task_id = contract.task_id
        attempt_id = state.get("attempt_id") if isinstance(state, Mapping) else None
        self._bridge_validate_claim(task_id, attempt_id, operation="FINALIZE_CANDIDATE")
        manager = _service_module().WorktreeManager(root_dir=contract.target_worktree_root)
        controller = _service_module().SelfHostedDevelopmentController(worktree_manager=manager)
        if status == "WORKER_COMPLETED":
            candidate = self._capture_resumed_candidate(contract, controller, lease, state)
            update("CANDIDATE_CAPTURED", {"candidate": candidate})
            state = self._read_state(task_id) or {}
            status = "CANDIDATE_CAPTURED"
        else:
            candidate = self._capture_resumed_candidate(contract, controller, lease, state)

        verified = _service_module().CandidateVerifier(manager).verify(
            contract,
            lease,
            candidate,
            protected_paths=request.get("protected_paths") or {},
        )
        if self._ambient_core_required(contract, request):
            # CandidateVerifier remains a repository-local evidence producer.
            # The host, not the verifier, owns the requirement to obtain Core
            # physical verification before this receipt can authorize commit.
            verified = _service_module().replace(
                verified,
                core_provenance_required=True,
                candidate_commit_allowed=False,
            )
        try:
            verified = self._verify_ambient_core_candidate(
                contract=contract,
                request=request,
                lease=lease,
                state=self._read_state(task_id) or state,
                candidate=candidate,
                verified=verified,
            )
        except _service_module().AmbientCoreVerdictBlocked as core_blocked:
            # The blocked verdict is persisted with the receipt below; the
            # unverified receipt then fails the attempt (#2181).
            verified = core_blocked.receipt
        latest_execution = attempts[-1] if attempts else self._receipt_from_state(execution)
        if latest_execution is None:
            raise RuntimeError("worker execution receipt is missing for attempt resolution")
        resolution = _service_module().resolve_attempt(latest_execution, candidate, verified)
        self._record_track1_verified_outcome(
            contract=contract,
            lease=lease,
            state=self._read_state(task_id) or state,
            candidate=candidate,
            verified=verified,
            execution=latest_execution,
        )

        acceptance_profile = getattr(contract, "acceptance_profile", None)
        fail_to_pass_required = _service_module().FAIL_TO_PASS_EVIDENCE_TOKEN in tuple(
            getattr(acceptance_profile, "required_evidence", ()) or ()
        )
        verified_values: dict[str, Any] = {
            "verified_receipt": verified,
            "attempt_resolution": resolution,
        }
        if not fail_to_pass_required:
            # Visibility only: a general task never proved fail-to-pass (#2274).
            verified_values["fail_to_pass"] = {
                "schema": _service_module().FAIL_TO_PASS_PROBE_SCHEMA,
                "status": "UNPROVEN",
                "reason": "fail_to_pass_unproven",
                "required": False,
            }
        else:
            # Blocks verified-candidate recovery until the probe records VERIFIED.
            verified_values["fail_to_pass"] = {
                "schema": _service_module().FAIL_TO_PASS_PROBE_SCHEMA,
                "status": "PENDING",
                "required": True,
            }
        update("VERIFIED", verified_values)

        if resolution.verdict != _service_module().AttemptResolutionVerdict.PROVEN.value:
            reasons = ", ".join(resolution.failure_reasons) or f"verdict is {resolution.verdict}"
            raise RuntimeError(f"candidate verification failed: {reasons}")

        authority_error = self._promotion_authority_error(
            contract=contract,
            request=request,
        )
        if authority_error:
            cleanup = manager.cleanup_terminal_target(contract, lease)
            cleanup_ok = cleanup.decision in {"REMOVED", "ALREADY_REMOVED", "TARGET_CLEANED"}
            terminal_status = (
                "REHEARSAL_VERIFIED"
                if self.ephemeral and cleanup_ok
                else "RETAINED_FOR_REVIEW"
                if cleanup.decision == "BLOCKED_BY_UNSAVED_CHANGES"
                else "FINAL_BLOCK"
            )
            update(
                terminal_status,
                {
                    "error": authority_error,
                    "candidate_status": "REHEARSAL_VERIFIED"
                    if self.ephemeral and cleanup_ok
                    else terminal_status,
                    "promotion_status": "NOT_CREATED",
                    "promotion_eligible": False,
                    "verification_verdict": "PROVEN" if self.ephemeral and cleanup_ok else "FAILED",
                    "verified_receipt": verified,
                    "attempt_resolution": resolution,
                    "cleanup_decision": cleanup.decision,
                    "cleanup_blocker": cleanup.blocker,
                    "cleanup_performed": cleanup.performed,
                    "cleanup_performed_at": _service_module()._utc_now() if cleanup.performed else None,
                    "cleanup_eligible": cleanup.eligible,
                    "terminal_status": terminal_status,
                    "state_retention_status": "TERMINAL",
                    "archive_eligible": False,
                },
            )
            return {
                "execution": execution,
                "candidate": candidate,
                "verified_receipt": verified,
                "attempt_resolution": resolution,
                "candidate_status": "REHEARSAL_VERIFIED"
                if self.ephemeral and cleanup_ok
                else terminal_status,
                "promotion_status": "NOT_CREATED",
                "promotion_eligible": False,
                "cleanup_decision": cleanup.decision,
                "cleanup_performed": cleanup.performed,
                "terminal_status": terminal_status,
                "error": authority_error,
            }

        if fail_to_pass_required:
            probe = self._run_fail_to_pass_probe(manager, contract)
            update("VERIFIED", {"fail_to_pass": probe})
            if probe["status"] != "VERIFIED":
                # Raised after the probe is persisted; _finalize_runtime_failure
                # treats a blocked probe as an unverified candidate, so the
                # verified-recovery route cannot commit it.
                raise RuntimeError(
                    f"fail_to_pass gate failed: {probe['status']} "
                    f"(base exit codes {probe['base_exit_codes']})"
                )

        commit_started = _service_module().time.perf_counter()
        packet = _service_module().CandidateCommitter(manager).create_candidate_commit(contract, lease, verified)
        commit_hook_time_ms = max(0, int((_service_module().time.perf_counter() - commit_started) * 1000))
        candidate_values = {
            "execution": execution,
            "candidate": candidate,
            "verified_receipt": verified,
            "attempt_resolution": resolution,
            "promotion_packet": packet,
            "promotion_status": packet.promotion_status,
            "candidate_commit_created": packet.candidate_commit_created,
            "public_claim_allowed": packet.public_claim_allowed,
            "production_ready": packet.production_ready,
            "merge_performed": packet.merge_performed,
            "push_performed": packet.push_performed,
            "telemetry": {"commit_hook_time_ms": commit_hook_time_ms},
        }
        update("CANDIDATE_COMMITTED", candidate_values)
        try:
            candidate_ref = manager.protect_candidate(contract, lease, packet.candidate_commit_sha)
            update("CANDIDATE_REF_PROTECTED", {"candidate_ref": candidate_ref})
        except Exception as exc:
            update(
                "RETAINED_FOR_REVIEW",
                {
                    "error": f"candidate ref protection failed: {exc}",
                    "promotion_status": "NOT_CREATED",
                    "candidate_status": "RETAINED_FOR_REVIEW",
                    "terminal_status": "RETAINED_FOR_REVIEW",
                    "state_retention_status": "ACTIVE",
                    "recovery_action": "recover_retained_candidate",
                },
            )
            raise RuntimeError(f"candidate ref protection failed: {exc}")
        cleanup_started = _service_module().time.perf_counter()
        cleanup = manager.cleanup_terminal_target(
            contract,
            lease,
            candidate_commit=packet.candidate_commit_sha,
            candidate_ref=candidate_ref,
        )
        cleanup_time_ms = max(0, int((_service_module().time.perf_counter() - cleanup_started) * 1000))
        if cleanup.decision != "REMOVED":
            raise RuntimeError(f"candidate Target cleanup failed: {cleanup.decision}")
        update(
            "TARGET_CLEANED",
            {
                "cleanup_eligible": cleanup.eligible,
                "cleanup_decision": cleanup.decision,
                "cleanup_blocker": cleanup.blocker,
                "cleanup_performed": cleanup.performed,
                "cleanup_performed_at": _service_module()._utc_now(),
                "telemetry": {"cleanup_time_ms": cleanup_time_ms},
            },
        )
        result = {
            **candidate_values,
            "candidate_ref": candidate_ref,
            "candidate_status": "PENDING_HUMAN_APPROVAL",
            "cleanup_decision": cleanup.decision,
            "cleanup_blocker": cleanup.blocker,
            "cleanup_performed": cleanup.performed,
            "cleanup_performed_at": _service_module()._utc_now(),
            "terminal_status": "PENDING_HUMAN_APPROVAL",
            "cleanup_eligible": cleanup.eligible,
            "state_retention_status": "ACTIVE",
            "archive_eligible": False,
        }
        return result

    def _finalize_runtime_failure(self, task_id, attempt_id, exc):
        current = self._read_state(task_id) or {}
        verified_rcpt = current.get("verified_receipt") or {}
        attempt_res = current.get("attempt_resolution") or {}
        is_verified = bool(verified_rcpt.get("verified")) and attempt_res.get("verdict") == "PROVEN"
        if is_verified and _service_module()._fail_to_pass_blocked(current):
            # A candidate that failed the fail-to-pass gate is not a recoverable
            # verified candidate (#2274).
            is_verified = False

        if is_verified:
            self._checkpoint(
                task_id,
                "RETAINED_FOR_REVIEW",
                {
                    "error": str(exc),
                    "promotion_status": "NOT_CREATED",
                    "terminal_status": "RETAINED_FOR_REVIEW",
                    "state_retention_status": "ACTIVE",
                    "recovery_action": "recover_verified_uncommitted_candidate",
                    "cleanup_eligible": False,
                    "cleanup_performed": False,
                    "cleanup_decision": "PRESERVED_FOR_REVIEW",
                },
                attempt_id=attempt_id,
            )
        else:
            cleanup_values: dict[str, Any] = {
                "cleanup_decision": "ALREADY_REMOVED",
                "cleanup_blocker": None,
                "cleanup_performed": False,
                "terminal_status": "FINAL_BLOCK",
                "state_retention_status": "TERMINAL",
            }
            if current.get("lease"):
                try:
                    contract = self.build_contract(current["request"])
                    lease = self._lease_from_state(current)
                    manager = _service_module().WorktreeManager(root_dir=contract.target_worktree_root)
                    cleanup = manager.cleanup_terminal_target(contract, lease)
                    cleanup_values.update(
                        {
                            "cleanup_decision": cleanup.decision,
                            "cleanup_blocker": cleanup.blocker,
                            "cleanup_performed": cleanup.performed,
                            "cleanup_performed_at": _service_module()._utc_now() if cleanup.performed else None,
                        }
                    )
                    cleanup_values["cleanup_eligible"] = cleanup.eligible
                    if cleanup.decision == "BLOCKED_BY_UNSAVED_CHANGES":
                        cleanup_values["terminal_status"] = "RETAINED_FOR_REVIEW"
                        try:
                            salvage = manager.create_salvage_snapshot(contract, lease, attempt_id)
                            salvage_commit = str(salvage.get("salvage_commit_sha", "") or "")
                            salvage_ref = str(salvage.get("salvage_ref", "") or "")
                            cleanup = manager.cleanup_terminal_target(
                                contract,
                                lease,
                                salvage_commit=salvage_commit,
                                salvage_ref=salvage_ref,
                            )
                            cleanup_values.update(
                                {
                                    "cleanup_decision": cleanup.decision,
                                    "cleanup_blocker": cleanup.blocker,
                                    "cleanup_performed": cleanup.performed,
                                    "cleanup_performed_at": _service_module()._utc_now()
                                    if cleanup.performed
                                    else None,
                                    **salvage,
                                }
                            )
                            if (
                                cleanup.decision in {"REMOVED", "ALREADY_REMOVED"}
                                and salvage_commit
                                and salvage_ref
                            ):
                                try:
                                    restore_result = manager.restore_task_branch_for_retry(
                                        contract,
                                        lease,
                                        salvage_commit,
                                        salvage_ref,
                                    )
                                    cleanup_values.update(
                                        {
                                            "task_branch_restore_decision": restore_result[
                                                "decision"
                                            ],
                                            "task_branch_restored_to": restore_result[
                                                "restored_to"
                                            ],
                                            "task_branch_restore_performed": True,
                                            "task_branch_restore_verified": True,
                                            "terminal_status": "FINAL_BLOCK",
                                            "state_retention_status": "TERMINAL",
                                        }
                                    )
                                except Exception as restore_exc:  # noqa: F841
                                    cleanup_values.update(
                                        {
                                            "task_branch_restore_decision": "RESTORE_BLOCKED",
                                            "task_branch_restore_performed": False,
                                            "task_branch_restore_verified": False,
                                            "terminal_status": "RETAINED_FOR_REVIEW",
                                        }
                                    )
                        except Exception as salvage_exc:
                            cleanup_values.update(
                                {
                                    "cleanup_decision": "CLEANUP_BLOCKED",
                                    "cleanup_blocker": str(salvage_exc),
                                    "cleanup_performed": False,
                                    "cleanup_eligible": False,
                                }
                            )
                except Exception as cleanup_exc:
                    cleanup_values.update(
                        {
                            "cleanup_decision": "CLEANUP_BLOCKED",
                            "cleanup_blocker": str(cleanup_exc),
                        }
                    )
            self._checkpoint(
                task_id,
                str(cleanup_values["terminal_status"]),
                {"error": str(exc), "promotion_status": "NOT_CREATED", **cleanup_values},
                attempt_id=attempt_id,
            )

    def _run_owned_task(self, task_id: str, attempt_id: str) -> None:
        from nexus.orchestrator.runtime_coordination_bridge import RuntimeCoordinationBridge

        return RuntimeCoordinationBridge(self).run_owned_attempt(
            task_id, attempt_id, self._custom_runner
        )

    def _wait_for_owner(self, task_id: str, attempt_id: str, pid: int) -> bool:
        deadline = _service_module().time.monotonic() + 10.0
        while _service_module().time.monotonic() < deadline:
            state = self._read_state(task_id)
            if state is None or state.get("attempt_id") != attempt_id:
                return False
            if state.get("worker_pid") == pid:
                return True
            _service_module().time.sleep(0.05)
        return False

    def _launch_worker(self, task_id: str, attempt_id: str) -> Optional[dict[str, Any]]:
        from nexus.orchestrator.runtime_coordination_bridge import RuntimeCoordinationBridge

        return RuntimeCoordinationBridge(self).launch(  # pyright: ignore[reportReturnType]
            task_id,
            attempt_id,
            custom_runner=self._custom_runner,
            state_dir=str(self.state_dir),
            source_root=str(Path(_service_module().__file__).resolve().parents[2]),  # pyright: ignore[reportArgumentType]
        )

    @staticmethod
    def _pid_alive(pid: int) -> bool:
        # os.kill(pid, 0) succeeds on a zombie. Worker children are launched
        # via a Popen that nobody waits on, so reap a finished child of ours
        # here; otherwise cancel sees it as running until the next Popen (#2646).
        # pid <= 0 would make waitpid reap any child of a process group.
        if pid > 0:
            try:
                reaped_pid, _status = os.waitpid(pid, os.WNOHANG)
            except OSError:  # ChildProcessError: not our child
                pass
            else:
                if reaped_pid == pid:
                    return False
        try:
            os.kill(pid, 0)
        except PermissionError:
            return True
        except (OSError, ProcessLookupError):
            return False
        return True

    def _terminate_owned_processes(self, task_id: str, *, exclude_pid: Optional[int] = None) -> None:
        state = self._read_state(task_id) or {}
        current_pgid = os.getpgrp()
        for raw_pgid in (state.get("worker_child_pgid"), state.get("worker_pgid")):
            if not raw_pgid:
                continue
            pgid = int(raw_pgid)
            if pgid in {current_pgid, exclude_pid}:
                continue
            try:
                os.killpg(pgid, _service_module().signal.SIGTERM)
                _service_module().time.sleep(0.05)
                os.killpg(pgid, _service_module().signal.SIGKILL)
            except (PermissionError, ProcessLookupError):
                continue
    # fmt: on
