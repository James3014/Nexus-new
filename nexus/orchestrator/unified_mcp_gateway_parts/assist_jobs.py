"""Assist job submit / wait / cancel / retry of ``UnifiedMCPGateway``.

Big-file split G6 (Issue #2449). ``_AssistJobsMixin`` holds ``_assist_submit``,
``_assist_wait``, ``_cleanup_assist_workspace``, ``_assist_record_stream_artifacts``,
``_assist_cancel`` and ``_assist_retry``, moved out of
``nexus/orchestrator/unified_mcp_gateway.py``. Their source lines are verbatim, except that
``_git``, ``pre_action_guard`` and ``CANONICAL_SOURCE_ROOT`` (patched on the gateway module
by tests) and ``GatewayInputError``, ``TOOL_MANIFEST_REVISION`` and ``_safe_relative_path``
(defined by the gateway) are resolved at call time through ``_gateway()``. Process,
lock and lease state stays on the gateway instance (``self._assist_processes``,
``self._assist_lock``); the account-lease helpers stay in the gateway class.
"""

from __future__ import annotations

import contextlib
import hashlib
import importlib
import json
import os
import shutil
import signal
import subprocess
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Mapping, Optional
from uuid import uuid4

from nexus.contracts.lifecycle_action import (
    LifecycleActionEnvelope,
    LifecycleActionType,
    PermissionProfile,
    build_action_envelope,
)
from nexus.core.argv_command import require_child_stays_unreaped
from nexus.orchestrator.lifecycle_guards import LifecycleGuardError
from nexus.orchestrator.unified_mcp_gateway_parts.assist_response import (
    _assist_workspace_removable,
    _provider_group_gone,
    _remove_assist_workspace,
    _terminate_provider_group,
    assist_workspace_parent,
)
from nexus.services.unified_runtime import ONLINE_CLI_SPEC_REGISTRY

if TYPE_CHECKING:
    # Typing only: the response (and, through it, probe) helpers called through ``self``.
    from nexus.orchestrator.unified_mcp_gateway_parts.assist_response import (
        _AssistResponseMixin as _JobsBase,
    )
else:
    _JobsBase = object


def _gateway():
    # Late binding: the gateway imports this module at its top level, so its own
    # (and its patched) names are only resolved once a method runs.
    return importlib.import_module("nexus.orchestrator.unified_mcp_gateway")


# Cancel after a gateway restart: how long the provider's group gets, after SIGTERM and again
# after SIGKILL, to show no live member before the cleanup counts as incomplete (#3076).
_UNOWNED_GROUP_SETTLE_SECONDS = 2.0


class _AssistJobsMixin(_JobsBase):
    """Mixin base of ``UnifiedMCPGateway``; never instantiated on its own."""

    if TYPE_CHECKING:  # provided by UnifiedMCPGateway

        @staticmethod
        def _assist_command(
            *,
            executable: str,
            provider: str,
            model: str,
            prompt: str,
            explicit_effort: str = ...,
            agy_print_timeout: str = ...,
        ) -> list[str]: ...

        @staticmethod
        def _assist_prompt(
            what: str, why: str, allowed: list[str], verifiers: list[str]
        ) -> str: ...

        @staticmethod
        def _task_id(
            arguments: Mapping[str, Any], what: str, why: str, allowed: list[str]
        ) -> str: ...

        def _abandon_assist_account_claim(self, task_id: str, job: dict[str, Any]) -> None: ...

        def _model_probe_inflight(self) -> set[str]: ...

    # fmt: off
    def _assist_submit(self, arguments: Mapping[str, Any], *, action: Optional[Mapping[str, Any]] = None) -> dict[str, Any]:
        task_id = self._task_id(arguments, str(arguments.get("what") or "assist"), str(arguments.get("why") or "assist"), [str(path) for path in arguments.get("allowed_files") or []])
        existing = self._assist_read(task_id)
        if existing is not None:
            return self._assist_response(self._assist_refresh(task_id) or existing, operation="submit")
        provider = str(arguments.get("provider") or arguments.get("preferred_worker") or "cline").strip().lower()
        model = str(arguments.get("model") or arguments.get("preferred_model") or "glm-5.2").strip()
        if provider != "cline":
            raise _gateway().GatewayInputError("ASSIST_ASYNC_PROVIDER_UNSUPPORTED")
        metadata = ONLINE_CLI_SPEC_REGISTRY.get(provider)
        if metadata is None:
            raise _gateway().GatewayInputError("ASSIST_PROVIDER_NOT_REGISTERED")
        binary_env = metadata.get("binary_env", "")
        configured = os.environ.get(binary_env, "").strip() if binary_env else ""
        executable = configured or shutil.which(metadata.get("binary_name", provider))
        if not executable or not Path(executable).is_file():
            raise _gateway().GatewayInputError("ASSIST_PROVIDER_UNAVAILABLE")
        allowed = [str(path).strip() for path in arguments.get("allowed_files") or [] if str(path).strip()]
        if not allowed or len(allowed) > 4:
            raise _gateway().GatewayInputError("allowed_files must contain 1-4 bounded paths")
        for path in allowed:
            _gateway()._safe_relative_path(path, "allowed_files")
        what = str(arguments.get("what") or "assist")
        why = str(arguments.get("why") or "assist")
        verifiers = [str(command).strip() for command in arguments.get("verifier_commands") or ["git diff --check"] if str(command).strip()]
        bound_action_request = {
            "task_id": task_id,
            "what": what,
            "why": why,
            "allowed_files": allowed,
            "verifier_commands": verifiers,
            "apply": False,
        }
        prompt = self._assist_prompt(what, why, allowed, verifiers)
        command = self._assist_command(executable=executable, provider=provider, model=model, prompt=prompt)
        job_id = f"assist-{uuid4().hex}"
        root = self._assist_root()
        stdout_path = root / f"{job_id}.stdout"
        stderr_path = root / f"{job_id}.stderr"
        workspace_root = Path(tempfile.mkdtemp(prefix=f"nexus-assist-{task_id}-", dir=assist_workspace_parent()))
        action_value = dict(action or {})
        if not action_value:
            base = _gateway()._git("rev-parse", "HEAD").strip()
            action_value = build_action_envelope(
                task_id=task_id,
                action_type=LifecycleActionType.TASK_RUN,
                request=bound_action_request,
                tool_manifest_hash=_gateway().TOOL_MANIFEST_REVISION,
                expected_head=base,
                allowed_paths=allowed,
                mutation=False,
                permission_profile=PermissionProfile.VERIFY,
            ).model_dump(mode="json")
        now = self._utc_now()
        job: dict[str, Any] = {
            "schema": "nexus.assisted_provider_job.v1",
            "job_kind": "assist",
            "task_id": task_id,
            "job_id": job_id,
            "attempt_history": [],
            "action_id": action_value.get("action_id") or f"action-{uuid4().hex}",
            "attempt_id": action_value.get("attempt_id") or f"attempt-{uuid4().hex}",
            "idempotency_key": action_value.get("idempotency_key"),
            "status": "SUBMITTED",
            "execution_lane": "ASSISTED_CANONICAL",
            "candidate_only": True,
            # ``apply`` is a legacy compatibility input.  It is deliberately
            # not carried into execution or authority receipts.
            "apply_requested": False,
            "apply_ignored": bool(arguments.get("apply", False)),
            "workspace_mode": "isolated",
            "workspace_root": str(workspace_root),
            "filesystem_before": self._snapshot_workspace(workspace_root),
            "filesystem_after": None,
            "filesystem_delta": {"created": [], "removed": [], "changed": []},
            "process_cleanup": False,
            "output_schema": {
                "type": "object",
                "required": ["patch"],
                "properties": {"patch": {"type": "string", "minLength": 1}},
            },
            "result_artifact": str(self._assist_path(task_id)),
            "provider": provider,
            "model": model if "/" in model else f"cline-pass/{model}",
            "command_hash": hashlib.sha256(json.dumps(command, separators=(",", ":")).encode("utf-8")).hexdigest(),
            "command": command,
            "submitted_at": now,
            "started_at": None,
            "finished_at": None,
            "provider_time_ms": 0,
            "stdout_artifact": str(stdout_path),
            "stderr_artifact": str(stderr_path),
            "action": action_value,
            "bound_action_request": bound_action_request,
            "connector_disconnected_at": None,
            "reconnected_at": None,
        }
        # Until its pid is written, a cancel finds this submit in flight and leaves a request
        # that the submit honours once the provider started, instead of removing the workspace
        # the provider is being started in (#3076).
        self._assist_launch_begin(task_id, job)
        try:
            self._assist_write(job)
            started = time.perf_counter()
            stdout_handle = stdout_path.open("w", encoding="utf-8")
            stderr_handle = stderr_path.open("w", encoding="utf-8")
            try:
                # The provider's process group is killed on exit before the workspace is removed (#3052).
                require_child_stays_unreaped()
                process = subprocess.Popen(command, cwd=workspace_root, stdout=stdout_handle, stderr=stderr_handle, text=True, start_new_session=True)
            except Exception:
                stdout_handle.close()
                stderr_handle.close()
                shutil.rmtree(workspace_root, ignore_errors=True)
                job.update({"status": "FAILED", "finished_at": self._utc_now(), "blocker": "ASSIST_PROVIDER_FAILED", "provider_error": "provider process could not start"})
                return self._assist_response(self._assist_write(job), operation="submit")
            stdout_handle.close()
            stderr_handle.close()
            job.update({"status": "RUNNING", "pid": process.pid, "pgid": process.pid, "started_at": self._utc_now(), "provider_start_ms": max(0, int((time.perf_counter() - started) * 1000))})
            return self._assist_publish_launch(task_id, job, process, operation="submit")
        finally:
            self._assist_launch_end(task_id, job_id)

    def _assist_cancel_requests(self) -> set[str]:
        """Task ids whose cancel arrived while their submit was still starting the provider."""
        with self._assist_lock:
            requests = getattr(self, "_assist_cancel_request_ids", None)
            if requests is None:
                requests = set()
                self._assist_cancel_request_ids = requests
            return requests

    def _assist_launch_owners(self) -> dict[str, str]:
        """Task id -> job id of the submit, retry or model probe that holds its in-flight entry."""
        with self._assist_lock:
            owners = getattr(self, "_assist_launch_owner_ids", None)
            if owners is None:
                owners = {}
                self._assist_launch_owner_ids = owners
            return owners

    def _assist_launch_begin(self, task_id: str, job: Mapping[str, Any], *, retried: Optional[Mapping[str, Any]] = None) -> None:
        """Enter the in-flight set (shared with the model probe, #2716) before the SUBMITTED
        record is written: until the pid is written, a cancel only leaves a request (#3076).

        As for the probe, the check and the entry are one step under the lock: a second submit or
        retry of the same task id is refused, before it writes or starts anything, while another
        launch is in flight or once another launch has recorded its job since this caller looked
        (a submit finds any record, a retry a record other than the job it retries). The refused
        launch's empty workspace is removed."""
        with self._assist_lock:
            inflight = self._model_probe_inflight()
            duplicate = task_id in inflight
            if not duplicate:
                current = self._assist_read(task_id)
                if retried is None:
                    duplicate = current is not None
                else:
                    duplicate = current is None or current.get("job_id") != retried.get("job_id")
            if not duplicate:
                inflight.add(task_id)
                self._assist_launch_owners()[task_id] = str(job.get("job_id"))
                return
        with contextlib.suppress(OSError):
            Path(str(job.get("workspace_root"))).rmdir()
        raise _gateway().GatewayInputError("ASSIST_DUPLICATE_LAUNCH_REFUSED")

    def _assist_launch_end(self, task_id: str, job_id: str) -> None:
        """Leave the in-flight set unless a later launch of the same task id holds it by now
        (this launch already left it when it wrote its pid); a cancel request the launch did
        not honour is dropped."""
        with self._assist_lock:
            owners = self._assist_launch_owners()
            if owners.get(task_id) != job_id:
                return
            del owners[task_id]
            self._model_probe_inflight().discard(task_id)
            self._assist_cancel_requests().discard(task_id)

    def _assist_publish_launch(self, task_id: str, job: dict[str, Any], process: subprocess.Popen[str], *, operation: str) -> dict[str, Any]:
        """Register the started provider and write its pid under the lock a cancel takes, then
        leave the in-flight set: a cancel sees either a submit still starting the provider, and
        leaves a request, or a registered provider. A request left meanwhile is honoured here,
        through the cancel path, once the provider can be terminated as a group (#3076)."""
        with self._assist_lock:
            self._assist_processes[task_id] = process
            written = self._assist_write(job)
            self._model_probe_inflight().discard(task_id)
            requests = self._assist_cancel_requests()
            cancel_requested = task_id in requests
            requests.discard(task_id)
        if cancel_requested:
            self._assist_cancel(task_id)
            written = self._assist_read(task_id) or written
        return self._assist_response(written, operation=operation)

    def _assist_wait(self, task_id: str, *, timeout_seconds: float = 10.0, poll_interval_seconds: float = 0.25) -> dict[str, Any]:
        deadline = time.monotonic() + max(0.0, min(60.0, timeout_seconds))
        while True:
            job = self._assist_refresh(task_id)
            if job is None:
                raise KeyError(f"unknown task_id: {task_id}")
            response = self._assist_response(job, operation="wait")
            if response["status"] in {"COMPLETED", "FAILED", "CANCELLED", "UNKNOWN_REQUIRES_RECONCILE"} or time.monotonic() >= deadline:
                return response
            time.sleep(max(0.01, min(5.0, poll_interval_seconds)))

    def _cleanup_assist_workspace(self, job: dict[str, Any]) -> None:
        _remove_assist_workspace(job, self._snapshot_workspace)

    @staticmethod
    def _assist_record_stream_artifacts(job: dict[str, Any]) -> None:
        """Record flushed stdout/stderr evidence after the child has exited.

        Cancellation must not report cleanup closure while leaving the durable
        receipt without the bytes that were already emitted.  Reading after a
        bounded wait/reap makes the hashes an observation of the final files,
        not a promise that the provider completed successfully.
        """
        streams = {
            "stdout": Path(str(job.get("stdout_artifact") or "")),
            "stderr": Path(str(job.get("stderr_artifact") or "")),
        }
        complete = True
        for name, path in streams.items():
            if not path.exists():
                complete = False
                job[f"{name}_sha256"] = None
                job[f"{name}_bytes"] = 0
                job[f"last_{name}_at"] = None
                continue
            try:
                data = path.read_bytes()
                stat = path.stat()
            except OSError:
                complete = False
                job[f"{name}_sha256"] = None
                job[f"{name}_bytes"] = 0
                job[f"last_{name}_at"] = None
                continue
            job[f"{name}_sha256"] = hashlib.sha256(data).hexdigest()
            job[f"{name}_bytes"] = len(data)
            job[f"last_{name}_at"] = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat()
        job["stream_flush_status"] = "FLUSHED" if complete else "PARTIAL_OR_MISSING"

    def _assist_cancel(self, task_id: str) -> dict[str, Any]:
        job = self._assist_refresh(task_id)
        if job is None:
            raise KeyError(f"unknown task_id: {task_id}")
        if job.get("status") == "UNKNOWN_REQUIRES_RECONCILE":
            self._assist_record_stream_artifacts(job)
            if _assist_workspace_removable(job):
                job.update({
                    "status": "CANCELLED",
                    "finished_at": self._utc_now(),
                    "blocker": "ASSIST_PROVIDER_PROCESS_LOST",
                    "process_killed": False,
                })
                self._cleanup_assist_workspace(job)
            else:
                # A provider group member may still use the workspace: keep it, and the job,
                # for reconciliation (#3076). This gateway does not hold the provider unreaped
                # here, so the group is not signalled.
                job.update({"reconciliation_required": True, "process_killed": False, "process_cleanup": False})
            self._assist_write(job)
        elif job.get("status") not in {"COMPLETED", "FAILED", "CANCELLED"}:
            pid = int(job.get("pid") or 0)
            process = None
            with self._assist_lock:
                process = self._assist_processes.get(task_id)
                if not pid:
                    # The submit writes the pid and registers the provider under this lock: re-read
                    # in case it did so after this cancel's refresh (#3076).
                    job = self._assist_read(task_id) or job
                    pid = int(job.get("pid") or 0)
                    starting = process is None and not pid and task_id in self._model_probe_inflight()
                    if starting:
                        # A submit in this gateway is still starting the provider in the
                        # workspace: removing it now would pull the cwd from under the provider,
                        # and the submit's later writes would drop the cancel. Leave a request
                        # that the submit honours once the pid is written (#3076).
                        self._assist_cancel_requests().add(task_id)
                        return self._assist_response({**job, "blocker": "ASSIST_CANCEL_PENDING_LAUNCH"}, operation="cancel")
            terminated = False
            if process is not None:
                # Not poll(): it reaps, after which the provider's group can no longer be
                # signalled safely; the group is SIGKILLed before the reap, so no descendant
                # outlives a lease release or the workspace removal below (#3052).
                terminated = _terminate_provider_group(process)
            elif pid:
                # A restarted gateway: the provider is not this process's child, so its exit
                # cannot be awaited without reaping it, and a leader gone after SIGTERM says
                # nothing about the rest of its group. The provider counts as terminated only
                # once a listing finds no live member of its group (#3076).
                for sig in (signal.SIGTERM, signal.SIGKILL):
                    try:
                        os.killpg(int(job.get("pgid") or pid), sig)
                    except OSError:
                        pass
                    deadline = time.monotonic() + _UNOWNED_GROUP_SETTLE_SECONDS
                    while not (terminated := _provider_group_gone(job)) and time.monotonic() < deadline:
                        time.sleep(0.1)
                    if terminated:
                        break
            job.update({
                "status": "CANCELLED",
                "finished_at": self._utc_now(),
                "blocker": "ASSIST_CANCELLED" if terminated else "ASSIST_CANCEL_CLEANUP_INCOMPLETE",
                "process_killed": terminated,
                "exit_code": process.returncode if process is not None else None,
            })
            self._assist_record_stream_artifacts(job)
            with self._assist_lock:
                self._assist_processes.pop(task_id, None)
            # No provider was ever started (no registered process, no pid): no group to wait for.
            provider_gone = terminated or (process is None and not pid)
            if provider_gone:
                self._cleanup_assist_workspace(job)
            if terminated:
                self._release_assist_account_claim(task_id, job)
            else:
                if job.get("account_lease_id_hash"):
                    self._abandon_assist_account_claim(task_id, job)
                    job["status"] = "UNKNOWN_REQUIRES_RECONCILE"
                    job["blocker"] = "ASSIST_CANCEL_CLEANUP_INCOMPLETE"
                if not provider_gone:
                    # The group is not known to be gone: keep the workspace and require
                    # reconciliation (#3076).
                    job.update({
                        "status": "UNKNOWN_REQUIRES_RECONCILE",
                        "blocker": "ASSIST_CANCEL_CLEANUP_INCOMPLETE",
                        "reconciliation_required": True,
                        "process_cleanup": False,
                    })
            self._assist_write(job)
        elif job.get("account_lease_id_hash") and not job.get("account_lease_released"):
            self._release_assist_account_claim(task_id, job)
            self._assist_write(job)
        return self._assist_response(job, operation="cancel")

    def _assist_retry(self, task_id: str) -> dict[str, Any]:
        job = self._assist_refresh(task_id)
        if job is None:
            raise KeyError(f"unknown task_id: {task_id}")
        if job.get("status") not in {"FAILED", "CANCELLED"}:
            raise _gateway().GatewayInputError("ASSIST_RETRY_REQUIRES_TERMINAL_FAILURE")
        if job.get("reconciliation_required"):
            raise _gateway().GatewayInputError("ASSIST_RETRY_REQUIRES_RECONCILIATION")
        if (
            job.get("account_lease_id_hash")
            and job.get("account_lease_cleanup_status") != "RELEASED"
        ):
            raise _gateway().GatewayInputError("ASSIST_RETRY_REQUIRES_AGY_LEASE_CLEANUP")

        action_dict = job.get("action")
        if not isinstance(action_dict, Mapping):
            raise LifecycleGuardError("ACTION_ENVELOPE_INVALID", "assisted job missing action envelope")
        try:
            original_action = LifecycleActionEnvelope.model_validate(action_dict)
        except Exception as exc:
            raise LifecycleGuardError(
                "ACTION_ENVELOPE_INVALID",
                "lifecycle action envelope is invalid",
                details={"error": str(exc)},
            ) from exc
        if original_action.task_id != task_id:
            raise LifecycleGuardError(
                "RETRY_SEMANTIC_TASK_MISMATCH",
                "action envelope task_id does not match retry task_id",
            )
        if original_action.action_type is not LifecycleActionType.TASK_RUN:
            raise LifecycleGuardError(
                "RETRY_SEMANTIC_ACTION_MISMATCH",
                "assisted retry requires an original TASK_RUN action",
            )

        live_head = _gateway()._git("rev-parse", "HEAD").strip()
        if original_action.tool_manifest_hash != _gateway().TOOL_MANIFEST_REVISION:
            raise LifecycleGuardError(
                "TOOL_MANIFEST_NAME_DRIFT",
                "action was created against a different public tool-name manifest",
                details={
                    "expected": _gateway().TOOL_MANIFEST_REVISION,
                    "received": original_action.tool_manifest_hash,
                    "definition_scope": "tool_names_only",
                },
            )
        if original_action.expected_head is not None and original_action.expected_head != live_head:
            raise LifecycleGuardError(
                "EXPECTED_HEAD_MISMATCH",
                "action expected a different repository HEAD",
                details={"expected": original_action.expected_head, "observed": live_head},
            )

        bound_request = job.get("bound_action_request")
        if not isinstance(bound_request, Mapping) or not bound_request:
            raise LifecycleGuardError(
                "BOUND_ACTION_REQUEST_MISSING",
                "assisted retry cannot re-authorize a legacy job without its exact bound request",
            )
        bound_request = dict(bound_request)
        if not original_action.verify_request(bound_request):
            raise LifecycleGuardError(
                "REQUEST_HASH_MISMATCH",
                "persisted action request hash does not match bound request",
            )
        requested_paths = [
            str(path).strip()
            for path in bound_request.get("allowed_files", ())
            if str(path).strip()
        ]
        if not requested_paths or len(requested_paths) > 4:
            raise _gateway().GatewayInputError("allowed_files must contain 1-4 bounded paths")
        for path in requested_paths:
            _gateway()._safe_relative_path(path, "allowed_files")
        if set(requested_paths) != set(original_action.allowed_paths):
            raise LifecycleGuardError(
                "ALLOWED_PATH_MISMATCH",
                "request paths exceed or differ from action envelope",
            )
        _gateway().pre_action_guard(
            original_action,
            request=bound_request,
            current_head=live_head,
            tool_manifest_hash=_gateway().TOOL_MANIFEST_REVISION,
        )

        provider = str(job.get("provider") or "cline").strip().lower()
        model = str(job.get("model") or "glm-5.2").strip()
        if provider != "cline":
            raise _gateway().GatewayInputError("ASSIST_ASYNC_PROVIDER_UNSUPPORTED")
        metadata = ONLINE_CLI_SPEC_REGISTRY.get(provider)
        if metadata is None:
            raise _gateway().GatewayInputError("ASSIST_PROVIDER_NOT_REGISTERED")
        binary_env = metadata.get("binary_env", "")
        configured = os.environ.get(binary_env, "").strip() if binary_env else ""
        executable = configured or shutil.which(metadata.get("binary_name", provider))
        if not executable or not Path(executable).is_file():
            raise _gateway().GatewayInputError("ASSIST_PROVIDER_UNAVAILABLE")
        what = str(bound_request.get("what") or "assist")
        why = str(bound_request.get("why") or "assist")
        verifiers = [
            str(command).strip()
            for command in bound_request.get("verifier_commands") or ["git diff --check"]
            if str(command).strip()
        ]
        prompt = self._assist_prompt(what, why, requested_paths, verifiers)
        canonical_command = self._assist_command(
            executable=executable,
            provider=provider,
            model=model,
            prompt=prompt,
        )
        stored_command = job.get("command")
        if not isinstance(stored_command, list) or not stored_command:
            raise _gateway().GatewayInputError("ASSIST_RETRY_COMMAND_NOT_RETAINED")
        if stored_command != canonical_command:
            raise LifecycleGuardError(
                "COMMAND_SUBSTITUTION_DETECTED",
                "persisted command bytes do not match reconstructed canonical command",
            )

        token = uuid4().hex
        new_attempt_id = f"attempt-{token}"
        new_action_id = f"action-{token}"
        previous_key = str(job.get("idempotency_key") or original_action.idempotency_key or task_id)
        base_key = previous_key.split(":retry-", 1)[0]
        suffix = f":retry-{token}"
        new_idempotency_key = f"{base_key[: max(1, 256 - len(suffix))]}{suffix}"
        retry_action = build_action_envelope(
            task_id=task_id,
            action_type=LifecycleActionType.TASK_RETRY,
            request=bound_request,
            tool_manifest_hash=_gateway().TOOL_MANIFEST_REVISION,
            expected_head=live_head,
            allowed_paths=requested_paths,
            mutation=False,
            task_card_path=original_action.task_card_path,
            task_card_hash=original_action.task_card_hash,
            contract_kind=original_action.contract_kind,
            contract_hash=original_action.contract_hash,
            attempt_id=new_attempt_id,
            action_id=new_action_id,
            idempotency_key=new_idempotency_key,
            permission_profile=original_action.permission_profile,
            approval_scope=original_action.approval_scope,
        ).model_dump(mode="json")
        _gateway().pre_action_guard(
            retry_action,
            request=bound_request,
            current_head=live_head,
            tool_manifest_hash=_gateway().TOOL_MANIFEST_REVISION,
        )

        history = list(job.get("attempt_history") or [])
        history.append({
            "job_id": job.get("job_id"),
            "attempt_id": job.get("attempt_id"),
            "status": job.get("status"),
            "exit_code": job.get("exit_code"),
            "result_artifact": job.get("result_artifact"),
        })
        new_job_id = f"{str(job.get('job_kind') or 'assist')}-{token}"
        root = self._assist_root()
        stdout_path = root / f"{new_job_id}.stdout"
        stderr_path = root / f"{new_job_id}.stderr"
        workspace_root = Path(tempfile.mkdtemp(prefix=f"nexus-retry-{task_id}-", dir=assist_workspace_parent()))
        new_job = dict(job)
        new_job.update({
            "job_id": new_job_id,
            "action_id": new_action_id,
            "attempt_id": new_attempt_id,
            "idempotency_key": new_idempotency_key,
            "attempt_history": history,
            "status": "SUBMITTED",
            "submitted_at": self._utc_now(),
            "started_at": None,
            "finished_at": None,
            "pid": None,
            "pgid": None,
            "exit_code": None,
            "blocker": None,
            "provider_error": "",
            "result": None,
            "command": canonical_command,
            "command_hash": hashlib.sha256(
                json.dumps(canonical_command, separators=(",", ":")).encode("utf-8")
            ).hexdigest(),
            "stdout_artifact": str(stdout_path),
            "stderr_artifact": str(stderr_path),
            "result_artifact": str(self._assist_path(task_id)),
            "workspace_root": str(workspace_root),
            "filesystem_before": self._snapshot_workspace(workspace_root),
            "filesystem_after": None,
            "filesystem_delta": {"created": [], "removed": [], "changed": []},
            "process_cleanup": False,
            "process_killed": False,
            "connector_disconnected_at": None,
            "reconnected_at": self._utc_now(),
            "action": retry_action,
            "bound_action_request": bound_request,
        })
        self._assist_launch_begin(task_id, new_job, retried=job)
        try:
            self._assist_write(new_job)
            stdout_handle = stdout_path.open("w", encoding="utf-8")
            stderr_handle = stderr_path.open("w", encoding="utf-8")
            try:
                # The provider's process group is killed on exit before the workspace is removed (#3052).
                require_child_stays_unreaped()
                process = subprocess.Popen(
                    canonical_command,
                    cwd=workspace_root,
                    stdout=stdout_handle,
                    stderr=stderr_handle,
                    text=True,
                    start_new_session=True,
                )
            except Exception:
                stdout_handle.close()
                stderr_handle.close()
                shutil.rmtree(workspace_root, ignore_errors=True)
                new_job.update({
                    "status": "FAILED",
                    "finished_at": self._utc_now(),
                    "blocker": "ASSIST_PROVIDER_FAILED",
                    "provider_error": "provider process could not start",
                })
                return self._assist_response(self._assist_write(new_job), operation="retry")
            stdout_handle.close()
            stderr_handle.close()
            new_job.update({
                "status": "RUNNING",
                "pid": process.pid,
                "pgid": process.pid,
                "started_at": self._utc_now(),
            })
            return self._assist_publish_launch(task_id, new_job, process, operation="retry")
        finally:
            self._assist_launch_end(task_id, new_job_id)
    # fmt: on
