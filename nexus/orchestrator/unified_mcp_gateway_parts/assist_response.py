"""Assist job refresh and response projection of ``UnifiedMCPGateway``.

Big-file split G5 (Issue #2447). ``_AssistResponseMixin`` holds ``_assist_refresh``,
``_assist_patch_is_substantive`` (with its four ``_ASSIST_*_RE`` class patterns),
``_assist_action`` and ``_assist_response``, moved out of
``nexus/orchestrator/unified_mcp_gateway.py``. Their source lines are verbatim, except that
``CANONICAL_SOURCE_ROOT`` (patched on the gateway module by tests) and ``UnifiedMCPGateway``
(defined by the gateway) are resolved at call time through ``_gateway()``.
``UnifiedMCPGateway`` inherits the mixin, so every member keeps its name, descriptor kind
and signature on the gateway class.
"""

from __future__ import annotations

import hashlib
import importlib
import os
import re
import shutil
import signal
import threading
import time
import weakref
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Mapping, Optional

from nexus.core.argv_command import kill_group_if_exited

if TYPE_CHECKING:
    import subprocess

    # Typing only: the probe/decode helpers this mixin calls through ``self``.
    from nexus.orchestrator.unified_mcp_gateway_parts.assist_probe import (
        _AssistProbeMixin as _ResponseBase,
    )
else:
    _ResponseBase = object


def _gateway():
    # Late binding: the gateway imports this module at its top level, so its own
    # (and its patched) names are only resolved once a method runs.
    return importlib.import_module("nexus.orchestrator.unified_mcp_gateway")


# A running Agy model probe whose provider is still alive this long past its own
# ``--print-timeout`` (AGY_MODEL_PROBE_PRINT_TIMEOUT) has its process group killed (#3052).
MODEL_PROBE_PROVIDER_DEADLINE_GRACE_SECONDS = 60.0
# How long a SIGKILLed provider gets to exit before the cleanup counts as incomplete.
_PROVIDER_KILL_SETTLE_SECONDS = 2.0
_PRINT_TIMEOUT_RE = re.compile(r"([0-9]+)s")
# Providers whose group this module killed and reaped: a concurrent refresh of the same job
# then sees a clean exit, not a reap that happened elsewhere. One lock serializes the checks.
_GROUP_KILLED: weakref.WeakSet[subprocess.Popen[str]] = weakref.WeakSet()
_SETTLE_LOCK = threading.Lock()


def _provider_deadline_passed(job: Mapping[str, Any]) -> bool:
    """Whether a running Agy model probe is past its print timeout plus the grace period."""
    if job.get("job_kind") != "model_probe" or job.get("provider") != "agy":
        return False
    match = _PRINT_TIMEOUT_RE.fullmatch(str(_gateway().AGY_MODEL_PROBE_PRINT_TIMEOUT))
    if match is None or not job.get("started_at"):
        return False
    try:
        started = datetime.fromisoformat(str(job["started_at"])).timestamp()
    except (TypeError, ValueError):
        return False
    limit = int(match.group(1)) + MODEL_PROBE_PROVIDER_DEADLINE_GRACE_SECONDS
    return time.time() - started > limit


def _signal_group_and_settle(process: subprocess.Popen[str], sig: int, seconds: float) -> bool:
    """Send *sig* to the unreaped provider's process group (its pid still names the group), then
    wait up to *seconds* for the provider to exit; once it has, its group is SIGKILLed and it is
    reaped (True). False: still running, unreaped."""
    try:
        os.killpg(process.pid, sig)
    except OSError:
        pass
    deadline = time.monotonic() + seconds
    while not kill_group_if_exited(process):
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.05)
    _GROUP_KILLED.add(process)
    return True


def _settle_provider_group(
    job: Mapping[str, Any], process: subprocess.Popen[str]
) -> tuple[bool, bool, bool]:
    """Detect the provider's exit without reaping it, then SIGKILL its process group and reap it
    (#3052); past the model-probe deadline, SIGKILL the group first.

    Returns ``(exited, group_clean, deadline_killed)``. ``exited`` False: still running, nothing
    reaped. ``group_clean`` False: a group member survived SIGKILL, the group could not be
    listed, the provider was reaped elsewhere, or a deadline kill did not end it; its effects
    may still be in progress."""
    with _SETTLE_LOCK:
        if process in _GROUP_KILLED:
            return True, True, False
        try:
            if kill_group_if_exited(process):
                _GROUP_KILLED.add(process)
                return True, True, False
            if not _provider_deadline_passed(job):
                return False, True, False
            clean = _signal_group_and_settle(process, signal.SIGKILL, _PROVIDER_KILL_SETTLE_SECONDS)
            return True, clean, True
        except (ChildProcessError, PermissionError):
            return True, False, False


def _terminate_provider_group(process: subprocess.Popen[str]) -> bool:
    """Cancel: SIGTERM, then SIGKILL, the provider's process group while the provider is
    unreaped, each step bounded; True once it exited and its group was SIGKILLed and reaped
    (#3052). False: a group member survived, the group could not be listed, the provider was
    reaped elsewhere (never signalled then) or it did not exit."""
    with _SETTLE_LOCK:
        if process in _GROUP_KILLED:
            return True
        if process.returncode is not None:
            return False
        try:
            return _signal_group_and_settle(
                process, signal.SIGTERM, _PROVIDER_KILL_SETTLE_SECONDS
            ) or _signal_group_and_settle(process, signal.SIGKILL, _PROVIDER_KILL_SETTLE_SECONDS)
        except (ChildProcessError, PermissionError):
            return False


class _AssistResponseMixin(_ResponseBase):
    """Mixin base of ``UnifiedMCPGateway``; never instantiated on its own."""

    if TYPE_CHECKING:  # provided by UnifiedMCPGateway
        _assist_processes: dict[str, subprocess.Popen[str]]
        _assist_lock: threading.RLock

        @staticmethod
        def _utc_now() -> str: ...

        @staticmethod
        def _assist_record_stream_artifacts(job: dict[str, Any]) -> None: ...

        def _release_assist_account_claim(self, task_id: str, job: dict[str, Any]) -> bool: ...

        def _abandon_assist_account_claim(self, task_id: str, job: dict[str, Any]) -> None: ...

    # fmt: off
    def _assist_refresh(self, task_id: str) -> Optional[dict[str, Any]]:
        job = self._assist_read(task_id)
        if job is None:
            return None
        if job.get("status") == "SUBMITTED":
            # #2716: a model-probe submit may wait for an Agy account while its
            # SUBMITTED record is on disk; that thread owns the record until it
            # writes its final state.  It registers in the in-flight set (under
            # this lock) before the first write and leaves only after the last,
            # so re-reading under the lock never sees a stale pre-launch record.
            with self._assist_lock:
                inflight_ids = getattr(self, "_model_probe_inflight_ids", None)
                if inflight_ids and task_id in inflight_ids:
                    return job
                job = self._assist_read(task_id)
                if job is None:
                    return None
                if (
                    job.get("status") == "SUBMITTED"
                    and job.get("job_kind") == "model_probe"
                    and job.get("provider") == "agy"
                    and job.get("account_pool_wait_started_at")
                    and not job.get("account_alias_hash")
                    and not job.get("pid")
                ):
                    # The submit that owned this record ended (e.g. a Gateway
                    # restart) while it waited for an account: no account was
                    # leased and no provider was started, so the probe failed
                    # without any effect.
                    # Only the probe's own workspace (created by the submit as
                    # /tmp/nexus-probe-*) is removed; this compares a recorded
                    # path, it creates nothing in /tmp.
                    probe_parents = {"/tmp", "/private/tmp"}  # nosec B108
                    workspace_root = os.path.realpath(str(job.get("workspace_root") or ""))
                    if os.path.dirname(workspace_root) in probe_parents and os.path.basename(
                        workspace_root
                    ).startswith("nexus-probe-"):
                        shutil.rmtree(workspace_root, ignore_errors=True)
                    job.update({
                        "status": "FAILED",
                        "finished_at": self._utc_now(),
                        "blocker": "AGY_ACCOUNT_POOL_WAIT_INTERRUPTED",
                        "provider_error": "Agy account pool wait ended before a model probe launched",
                        "model_response_verified": False,
                        "process_cleanup": True,
                    })
                    return self._assist_write(job)
        if job.get("status") in {"COMPLETED", "FAILED", "CANCELLED"}:
            return job
        if job.get("blocker") == "ASSIST_PROVIDER_GROUP_CLEANUP_INCOMPLETE":
            # Settled as needing reconciliation: a later refresh must not finish the job.
            return job
        with self._assist_lock:
            process = self._assist_processes.get(task_id)
        returncode = None
        group_clean, deadline_killed = True, False
        if process is not None:
            # Not poll(): it reaps, after which the provider's group can no longer be
            # signalled safely; a descendant left in the group is killed first (#3052).
            exited, group_clean, deadline_killed = _settle_provider_group(job, process)
            if exited:
                returncode = process.returncode
                job["durable_exit_marker"] = True
                job["durable_exit_code"] = returncode
        if process is not None and not group_clean:
            # A provider group member may still be running on the account and the workspace:
            # keep both (no release, no removal) and require reconciliation.
            self._assist_record_stream_artifacts(job)
            if job.get("account_lease_id_hash"):
                self._abandon_assist_account_claim(task_id, job)
            with self._assist_lock:
                self._assist_processes.pop(task_id, None)
            job.update({
                "status": "UNKNOWN_REQUIRES_RECONCILE",
                "finished_at": self._utc_now(),
                "exit_code": returncode,
                "blocker": "ASSIST_PROVIDER_GROUP_CLEANUP_INCOMPLETE",
                "reconciliation_required": True,
                "model_response_verified": False,
                "process_cleanup": False,
            })
            return self._assist_write(job)
        if process is None and job.get("pid"):
            try:
                os.kill(int(job["pid"]), 0)
                return job
            except (OSError, ValueError):
                # A restarted Gateway may retain artifacts but no durable exit
                # marker.  Output alone is not completion evidence: fail closed
                # and require an explicit reconciliation decision.
                if not job.get("durable_exit_marker"):
                    job.update({
                        "status": "UNKNOWN_REQUIRES_RECONCILE",
                        "blocker": "ASSIST_PROVIDER_PROCESS_LOST",
                        "reconciliation_required": True,
                        "last_polled_at": self._utc_now(),
                    })
                    return self._assist_write(job)
                returncode = job.get("exit_code")
        if returncode is None:
            job["status"] = "RUNNING"
            job["last_polled_at"] = self._utc_now()
            return self._assist_write(job)
        stdout_path = Path(str(job.get("stdout_artifact") or ""))
        stderr_path = Path(str(job.get("stderr_artifact") or ""))
        stdout = stdout_path.read_text(encoding="utf-8", errors="replace") if stdout_path.exists() else ""
        stderr = stderr_path.read_text(encoding="utf-8", errors="replace") if stderr_path.exists() else ""
        provider = str(job.get("provider") or "")
        stderr_lower = stderr.lower()
        agy_print_timed_out = (
            provider == "agy"
            and "[agy] print timeout after" in stderr_lower
            and "turn in progress" in stderr_lower
        )
        is_model_probe = str(job.get("job_kind") or "assist") == "model_probe"
        response_provenance: Optional[str] = None
        if is_model_probe:
            parsed, response_provenance = self._decode_model_probe_payload(
                stdout,
                provider,
                str(job.get("resolved_model") or ""),
            )
        else:
            parsed = self._decode_assist_payload(
                stdout,
                provider,
                require_patch=True,
            )
        if agy_print_timed_out:
            parsed = None
            response_provenance = None
            schema_valid, schema_error = False, ""
        else:
            schema_valid, schema_error = self._validate_output_schema(parsed, job.get("output_schema"))
        started_at = job.get("started_at")
        provider_time_ms = 0
        if started_at:
            try:
                provider_time_ms = max(0, int((time.time() - datetime.fromisoformat(str(started_at)).timestamp()) * 1000))
            except (TypeError, ValueError):
                provider_time_ms = 0
        model_response_verified = bool(
            is_model_probe
            and not agy_print_timed_out
            and returncode == 0
            and parsed is not None
            and schema_valid
            and response_provenance
        )
        provider_error_sha256 = (
            hashlib.sha256(stderr.encode("utf-8")).hexdigest()
            if stderr and (returncode != 0 or agy_print_timed_out)
            else None
        )
        if agy_print_timed_out:
            status = "FAILED"
            blocker = "ASSIST_PROVIDER_PRINT_TIMEOUT"
            provider_error = "provider print timeout while turn remained in progress"
        else:
            degenerate_patch = bool(
                not is_model_probe
                and returncode == 0
                and parsed is not None
                and not self._assist_patch_is_substantive(parsed.get("patch"))
            )
            status = (
                "COMPLETED"
                if returncode == 0 and parsed is not None and schema_valid and not degenerate_patch
                else "FAILED"
            )
            blocker = (
                "ASSIST_PROVIDER_DEGENERATE_OUTPUT"
                if degenerate_patch
                else "ASSIST_PROVIDER_MALFORMED_OUTPUT"
                if returncode == 0 and (parsed is None or not schema_valid)
                else ("ASSIST_PROVIDER_FAILED" if returncode != 0 else None)
            )
            if degenerate_patch:
                parsed = None
                schema_error = "degenerate_patch"
            provider_error = "provider process failed" if returncode != 0 else ""
        if deadline_killed:
            status = "FAILED"
            blocker = "ASSIST_PROVIDER_DEADLINE_EXCEEDED"
            provider_error = "provider still running past the model probe deadline; process group killed"
        job.update({
            "status": status,
            "finished_at": self._utc_now(),
            "exit_code": returncode,
            "result": parsed,
            "model_response_verified": model_response_verified,
            "model_response_provenance": response_provenance,
            "blocker": blocker,
            "retry_required": blocker == "ASSIST_PROVIDER_DEGENERATE_OUTPUT",
            "schema_error": schema_error,
            "schema_validation_level": "bounded_subset",
            "provider_error": provider_error,
            "provider_error_sha256": provider_error_sha256,
            "provider_print_timeout": agy_print_timed_out,
            "provider_time_ms": provider_time_ms,
        })
        self._assist_record_stream_artifacts(job)
        lease_cleanup_ok = self._release_assist_account_claim(task_id, job)
        if is_model_probe and job.get("account_lease_id_hash") and not lease_cleanup_ok:
            job.update({
                "status": "UNKNOWN_REQUIRES_RECONCILE",
                "blocker": "ASSIST_ACCOUNT_LEASE_RECONCILIATION_REQUIRED",
                "reconciliation_required": True,
                "model_response_verified": False,
            })
        workspace_root = Path(str(job.get("workspace_root") or ""))
        if workspace_root.exists() and workspace_root != _gateway().CANONICAL_SOURCE_ROOT:
            after = self._snapshot_workspace(workspace_root)
            before = job.get("filesystem_before") if isinstance(job.get("filesystem_before"), Mapping) else {}
            job["filesystem_after"] = after
            job["filesystem_delta"] = {
                "created": sorted(set(after) - set(before)),  # pyright: ignore[reportArgumentType]
                "removed": sorted(set(before) - set(after)),  # pyright: ignore[reportArgumentType]
                "changed": sorted(path for path in set(before) & set(after) if before[path] != after[path]),  # pyright: ignore[reportArgumentType, reportOptionalSubscript]
            }
            try:
                shutil.rmtree(workspace_root)
                job["process_cleanup"] = True
            except OSError as exc:
                job["process_cleanup"] = False
                job["cleanup_error"] = str(exc)
        with self._assist_lock:
            self._assist_processes.pop(task_id, None)
        evidence = self._write_probe_evidence(job)
        if evidence is not None:
            job["probe_evidence_hash"] = evidence["evidence_hash"]
            job["probe_expires_at"] = evidence["expires_at"]
            job["authentication_evidence"] = evidence["authentication_evidence"]
            identity = self._probe_evidence_identity(evidence)
            job["probe_evidence_path"] = str(self._probe_evidence_read_root() / (identity + ".json"))
        return self._assist_write(job)

    _ASSIST_HUNK_HEADER_RE = re.compile(r"^@@ -\d{1,9}(?:,(\d{1,9}))? \+\d{1,9}(?:,(\d{1,9}))? @@")

    _ASSIST_GIT_HEADER_RE = re.compile(r"^diff --git \S.* \S.*$")
    # Git extended header lines. The first group needs no hunk to be a real change.

    _ASSIST_GIT_CHANGE_RE = re.compile(
        r"^(new file mode [0-7]{6}|deleted file mode [0-7]{6}|old mode [0-7]{6}|new mode [0-7]{6}|"
        r"rename from \S.*|rename to \S.*|Binary files .* differ|GIT binary patch)$"
    )

    _ASSIST_GIT_OTHER_RE = re.compile(
        r"^(index \S+( [0-7]{6})?|similarity index \d+%|dissimilarity index \d+%|copy from \S.*|copy to \S.*)$"
    )

    @staticmethod
    def _assist_patch_is_substantive(patch: Any) -> bool:
        """A patch must be a structurally valid unified diff, never null/empty/refusal prose.

        Accepts a `--- `/`+++ ` file section with a hunk header followed by at least one
        `+`/`-` change line, or a `diff --git` section whose extended header needs no hunk
        (new/deleted file, rename, mode change, binary). Single linear pass.
        """
        if not isinstance(patch, str):
            return False
        cls = _gateway().UnifiedMCPGateway
        lines = patch.splitlines()
        count = len(lines)
        index = 0
        while index < count:
            line = lines[index]
            if line.startswith("--- ") and index + 1 < count and lines[index + 1].startswith("+++ "):
                index += 2
                while index < count:
                    header = cls._ASSIST_HUNK_HEADER_RE.match(lines[index])
                    if header is None:
                        break
                    # Consume the hunk by its header counts (like git apply), so removed or
                    # added lines that look like `--- `/`+++ ` are body, not file headers.
                    try:
                        old_left = 1 if header.group(1) is None else int(header.group(1))
                        new_left = 1 if header.group(2) is None else int(header.group(2))
                    except ValueError:
                        return False
                    index += 1
                    body_start = index
                    changed = False
                    counted = True
                    while old_left > 0 or new_left > 0:
                        if index >= count:
                            counted = False
                            break
                        body = lines[index]
                        marker = body[:1]
                        if marker == "\\":
                            index += 1
                            continue
                        if marker in ("", " ") and old_left > 0 and new_left > 0:
                            old_left -= 1
                            new_left -= 1
                        elif marker == "-" and old_left > 0:
                            old_left -= 1
                            changed = True
                        elif marker == "+" and new_left > 0:
                            new_left -= 1
                            changed = True
                        else:
                            counted = False
                            break
                        index += 1
                    if counted:
                        while index < count and lines[index].startswith("\\"):
                            index += 1
                    else:
                        # Counts not satisfied: the applier uses `git apply --recount`, so
                        # re-read this hunk by line shape up to the next real section header.
                        index = body_start
                        changed = False
                        while index < count:
                            body = lines[index]
                            if body.startswith(("diff --git ", "@@ ")) or (
                                body.startswith("--- ")
                                and index + 1 < count
                                and lines[index + 1].startswith("+++ ")
                            ):
                                break
                            marker = body[:1]
                            if marker in ("+", "-"):
                                changed = True
                            elif marker not in ("", " ", "\\"):
                                return False
                            index += 1
                    if changed:
                        return True
                continue
            if cls._ASSIST_GIT_HEADER_RE.match(line):
                index += 1
                while index < count:
                    header = lines[index]
                    if cls._ASSIST_GIT_CHANGE_RE.match(header):
                        return True
                    if not cls._ASSIST_GIT_OTHER_RE.match(header):
                        break
                    index += 1
                continue
            index += 1
        return False

    @staticmethod
    def _assist_action(job: Mapping[str, Any]) -> dict[str, Any]:
        """Project one Assisted job into current action and pending-count state."""
        status = str(job.get("status") or "UNKNOWN")
        terminal = status in {"COMPLETED", "FAILED", "CANCELLED"}
        reconciliation_required = status == "UNKNOWN_REQUIRES_RECONCILE" or bool(job.get("reconciliation_required"))
        cleanup_settled = job.get("process_cleanup") is True and not job.get("cleanup_error")
        settled_failure = (
            status in {"FAILED", "CANCELLED"}
            and not reconciliation_required
            and cleanup_settled
            and job.get("durable_exit_marker") is True
            and not job.get("uncertain_mutation")
        )
        if status == "UNKNOWN_REQUIRES_RECONCILE" or reconciliation_required:
            next_action = "nexus_task_reconcile"
        else:
            result_tool = "nexus_model_probe_result" if str(job.get("job_kind") or "assist") == "model_probe" else "nexus_assist_result"
            next_action = result_tool if not terminal else ("none" if status == "COMPLETED" else "nexus_task_retry")
        return {
            "attention_required": status == "UNKNOWN_REQUIRES_RECONCILE" or (status in {"FAILED", "CANCELLED"} and not settled_failure),
            "next_action": next_action,
            "recommended_tool": next_action,
            "pending": not terminal or status == "UNKNOWN_REQUIRES_RECONCILE",
        }

    def _assist_response(self, job: Mapping[str, Any], *, operation: str = "status") -> dict[str, Any]:
        status = str(job.get("status") or "UNKNOWN")
        action = self._assist_action(job)
        return {
            "schema": "nexus.assisted_provider_job.v1",
            "operation": operation,
            "task_id": job.get("task_id"),
            "job_id": job.get("job_id"),
            "action_id": job.get("action_id"),
            "attempt_id": job.get("attempt_id"),
            "attempt_history": job.get("attempt_history", []),
            "status": status,
            "retry_required": bool(job.get("retry_required")) or action["next_action"] == "nexus_task_retry",
            "execution_lane": "ASSISTED_CANONICAL",
            "candidate_only": True,
            "apply_requested": bool(job.get("apply_requested")),
            "apply_ignored": bool(job.get("apply_ignored", False)),
            "provider": job.get("provider"),
            "model": job.get("model"),
            "command_hash": job.get("command_hash"),
            "job_kind": job.get("job_kind", "assist"),
            "workspace_mode": job.get("workspace_mode", "isolated"),
            "workspace_root": job.get("workspace_root"),
            "pid": job.get("pid"),
            "pgid": job.get("pgid"),
            "started_at": job.get("started_at"),
            "finished_at": job.get("finished_at"),
            "exit_code": job.get("exit_code"),
            "provider_time_ms": job.get("provider_time_ms", 0),
            "provider_started": bool(job.get("started_at")),
            "binary_exec_started": job.get("started_at"),
            "last_stdout_at": job.get("last_stdout_at"),
            "last_stderr_at": job.get("last_stderr_at"),
            "stdout_sha256": job.get("stdout_sha256"),
            "stderr_sha256": job.get("stderr_sha256"),
            "stdout_bytes": job.get("stdout_bytes"),
            "stderr_bytes": job.get("stderr_bytes"),
            "model_response_verified": bool(job.get("model_response_verified", False)),
            "probe_evidence_hash": job.get("probe_evidence_hash"),
            "probe_expires_at": job.get("probe_expires_at"),
            "authentication_evidence": job.get("authentication_evidence"),
            "durable_exit_marker": bool(job.get("durable_exit_marker", False)),
            "reconciliation_required": bool(job.get("reconciliation_required", False)),
            "uncertain_mutation": bool(job.get("uncertain_mutation", False)),
            "context_arm": job.get("context_arm"),
            "context_arm_applied": bool(job.get("context_arm_applied", False)),
            "context_arm_semantics": job.get("context_arm_semantics", "record_only_not_applied"),
            "result": job.get("result") if status == "COMPLETED" else None,
            "blocker": job.get("blocker"),
            "provider_error": job.get("provider_error", ""),
            "provider_error_sha256": job.get("provider_error_sha256"),
            "schema_error": job.get("schema_error", ""),
            "schema_validation_level": job.get("schema_validation_level", "bounded_subset"),
            "requested_tools_policy": job.get("requested_tools_policy", []),
            "tool_policy_enforcement": job.get("tool_policy_enforcement", "not_enforced"),
            "filesystem_delta": job.get("filesystem_delta", {"created": [], "removed": [], "changed": []}),
            "account_alias_hash": job.get("account_alias_hash"),
            "account_lease_id_hash": job.get("account_lease_id_hash"),
            "account_lease_released": job.get("account_lease_released"),
            "account_lease_cleanup_status": job.get("account_lease_cleanup_status"),
            "account_pool_wait_budget_seconds": job.get("account_pool_wait_budget_seconds"),
            "account_pool_wait_ms": job.get("account_pool_wait_ms"),
            "process_cleanup": job.get("process_cleanup", False),
            "process_killed": bool(job.get("process_killed", False)),
            "stream_flush_status": job.get("stream_flush_status", "not_observed"),
            "connector_disconnected_at": job.get("connector_disconnected_at"),
            "reconnected_at": job.get("reconnected_at"),
            "artifacts": {"stdout": job.get("stdout_artifact"), "stderr": job.get("stderr_artifact")},
            "attention_required": action["attention_required"],
            "next_action": action["next_action"],
            "recommended_tool": action["recommended_tool"],
        }
    # fmt: on
