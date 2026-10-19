"""Provider probe, Agy account-lease and model-probe submit of ``UnifiedMCPGateway``.

Big-file split G7a (Issue #2481). ``_ModelProbeMixin`` holds ``_provider_executable``,
``_provider_preflight``, ``_agy_probe_model_family``, ``_acquire_agy_probe_claim``,
``_release_assist_account_claim``, ``_abandon_assist_account_claim`` and
``_model_probe_submit``, moved out of ``nexus/orchestrator/unified_mcp_gateway.py``. Their
source lines are verbatim, except that ``_git``, ``get_account_pool_manager``,
``CrossProcessLeaseCoordinator`` and ``resolve_registered_provider_executable`` (patched on
the gateway module by tests) and ``GatewayInputError``, ``TOOL_MANIFEST_REVISION``, ``_text``
and ``AGY_MODEL_PROBE_PRINT_TIMEOUT`` (defined by the gateway) are resolved at call time
through ``_gateway()``. Lease, lock and process state stays on the gateway instance.
"""

from __future__ import annotations

import hashlib
import importlib
import json
import math
import os
import shutil
import signal
import subprocess
import tempfile
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any, Mapping, Optional
from uuid import uuid4

from nexus.contracts.lifecycle_action import (
    LifecycleActionType,
    PermissionProfile,
    build_action_envelope,
)
from nexus.executors.claude_measurement_worker import (
    CLAUDE_MEASUREMENT_PROVIDER,
    measurement_claude_enabled,
    measurement_claude_preflight,
)
from nexus.services.agy_account_pool import AgyAccountPoolBusyError, AgyAccountPoolExhaustedError
from nexus.services.unified_runtime import ONLINE_CLI_SPEC_REGISTRY

if TYPE_CHECKING:
    # Typing only: the assist job / response / probe helpers called through ``self``.
    from nexus.orchestrator.unified_mcp_gateway_parts.assist_jobs import (
        _AssistJobsMixin as _ModelProbeBase,
    )
else:
    _ModelProbeBase = object


# #2716: an Agy model probe waits a bounded time for a free account instead of
# failing on the first busy pass.  The wait runs on the submitting request
# thread (the Gateway uses ThreadingHTTPServer), so it is capped.
MODEL_PROBE_POOL_WAIT_ENV = "NEXUS_MODEL_PROBE_POOL_WAIT_SECONDS"
MODEL_PROBE_POOL_WAIT_DEFAULT_SECONDS = 90.0
MODEL_PROBE_POOL_WAIT_MAX_SECONDS = 300.0


def model_probe_pool_wait_seconds() -> float:
    """Bounded account-pool wait for one Agy model probe (env override, clamped)."""
    raw = os.getenv(MODEL_PROBE_POOL_WAIT_ENV, "").strip()
    if not raw:
        return MODEL_PROBE_POOL_WAIT_DEFAULT_SECONDS
    try:
        value = float(raw)
    except ValueError:
        return MODEL_PROBE_POOL_WAIT_DEFAULT_SECONDS
    if not math.isfinite(value):
        return MODEL_PROBE_POOL_WAIT_DEFAULT_SECONDS
    return min(max(value, 0.0), MODEL_PROBE_POOL_WAIT_MAX_SECONDS)


def _gateway():
    # Late binding: the gateway imports this module at its top level, so its own
    # (and its patched) names are only resolved once a method runs.
    return importlib.import_module("nexus.orchestrator.unified_mcp_gateway")


class _ModelProbeMixin(_ModelProbeBase):
    """Mixin base of ``UnifiedMCPGateway``; never instantiated on its own."""

    if TYPE_CHECKING:  # provided by UnifiedMCPGateway
        _assist_account_claims: dict[str, Any]

    # fmt: off
    def _provider_executable(self, provider: str) -> tuple[dict[str, str], Optional[str]]:
        metadata = ONLINE_CLI_SPEC_REGISTRY.get(provider)
        if metadata is None:
            return {}, None
        try:
            executable = _gateway().resolve_registered_provider_executable(provider)
        except ValueError as exc:
            if provider != "agy" or str(exc) != "provider_binary_not_found":
                return metadata, None
            candidate = Path.home() / ".local/bin/agy"
            if not candidate.is_file() or not os.access(candidate, os.X_OK):
                return metadata, None
            fallback_env = dict(os.environ)
            fallback_env["NEXUS_AGY_BIN"] = str(candidate)
            fallback_env["NEXUS_AGY_EXECUTABLE"] = str(candidate)
            try:
                executable = _gateway().resolve_registered_provider_executable(
                    provider,
                    environ=fallback_env,
                )
            except ValueError:
                return metadata, None
        return metadata, str(Path(executable).resolve())

    def _provider_preflight(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        provider = str(arguments.get("provider") or "cline").strip().lower()
        requested_model = str(arguments.get("model") or arguments.get("preferred_model") or "").strip()
        if provider == CLAUDE_MEASUREMENT_PROVIDER and measurement_claude_enabled():
            # #2721: measurement Gateway only; never reached on the live Gateway.
            return measurement_claude_preflight(requested_model)
        if provider == "cline" and not requested_model:
            requested_model = "glm-5.2"
        metadata, executable = self._provider_executable(provider)
        resolved_model = requested_model
        if provider == "cline" and resolved_model and "/" not in resolved_model:
            resolved_model = f"cline-pass/{resolved_model}"
        result: dict[str, Any] = {
            "schema": "nexus.provider_preflight.v1",
            "provider": provider,
            "requested_model": requested_model,
            "resolved_model": resolved_model,
            "requested_model_verified": False,
            "resolved_model_evidence": None,
            "binary_found": bool(executable),
            "binary_path": executable,
            "binary_sha256": None,
            "cli_version": None,
            "authenticated": False,
            "authentication_required": self._provider_requires_authentication(provider),
            "model_reachable": False,
            "probe_requested": bool(arguments.get("probe", False)),
            "probe_latency_ms": 0,
            "exit_code": None,
            "stdout_sha256": None,
            "stderr_sha256": None,
            "status": "BLOCKED",
            "blocker": None,
            "next_action": None,
        }
        if not metadata:
            result["blocker"] = "ASSIST_PROVIDER_NOT_REGISTERED"
            return result
        if not executable:
            result["blocker"] = "ASSIST_PROVIDER_UNAVAILABLE"
            return result
        try:
            result["binary_sha256"] = self._hash_file(Path(executable))
        except OSError:
            result["blocker"] = "ASSIST_PROVIDER_BINARY_UNREADABLE"
            return result
        version_started = time.perf_counter()
        version_root = Path(tempfile.mkdtemp(prefix=f"nexus-preflight-{provider}-", dir="/tmp"))
        try:
            version = subprocess.run([executable, "--version"], cwd=version_root, capture_output=True, text=True, timeout=5, check=False)
        except (OSError, subprocess.TimeoutExpired) as exc:
            result["blocker"] = "ASSIST_PROVIDER_VERSION_FAILED"
            result["provider_error"] = str(exc)
            shutil.rmtree(version_root, ignore_errors=True)
            return result
        shutil.rmtree(version_root, ignore_errors=True)
        result["cli_version"] = (version.stdout or version.stderr).strip()[:512]
        result["cli_version_sha256"] = hashlib.sha256(result["cli_version"].encode()).hexdigest()
        result["version_latency_ms"] = max(0, int((time.perf_counter() - version_started) * 1000))
        if version.returncode != 0:
            result["exit_code"] = version.returncode
            result["blocker"] = "ASSIST_PROVIDER_VERSION_FAILED"
            return result
        # Model/auth execution is intentionally never synchronous here.  A
        # caller asking for probe=true receives a bounded handoff to the
        # isolated async model-probe surface, so ChatGPT request lifetimes and
        # the canonical checkout are not part of provider probing.
        evidence = self._read_probe_evidence(provider=provider, requested_model=requested_model, resolved_model=resolved_model, executable=executable, binary_sha256=result["binary_sha256"], cli_version=result["cli_version"])
        evidence_auth_ready = evidence is not None and (not self._provider_requires_authentication(provider) or evidence.get("authenticated") is True)
        if evidence_auth_ready:
            result.update({
                "status": "VERSION_VERIFIED",
                "blocker": None,
                "next_action": None,
                "readiness_status": "MODEL_VERIFIED",
                "execution_ready": True,
                "model_reachable": True,
                "requested_model_verified": True,
                "authenticated": evidence.get("authenticated") is True,  # pyright: ignore[reportOptionalMemberAccess]
                "authentication_evidence": evidence.get("authentication_evidence"),  # pyright: ignore[reportOptionalMemberAccess]
                "probe_evidence_hash": evidence.get("evidence_hash"),  # pyright: ignore[reportOptionalMemberAccess]
                "probe_expires_at": evidence.get("expires_at"),  # pyright: ignore[reportOptionalMemberAccess]
            })
        elif bool(arguments.get("probe", False)):
            result.update({
                "status": "VERSION_VERIFIED",
                "blocker": "MODEL_PROBE_ASYNC_REQUIRED",
                "next_action": "nexus_model_probe",
                "probe_mode": "deferred_async_isolated",
            })
        else:
            result.update({"status": "VERSION_VERIFIED", "blocker": "MODEL_PROBE_REQUIRED", "next_action": "nexus_model_probe"})
        result.setdefault("readiness_status", "VERSION_VERIFIED")
        result.setdefault("execution_ready", False)
        return result

    @staticmethod
    def _agy_probe_model_family(model: str) -> str:
        value = str(model or "").strip().lower()
        if value.startswith("gemini-"):
            return "gemini"
        if value.startswith("claude-") or value.startswith("gpt-"):
            return "claude_gpt"
        raise _gateway().GatewayInputError("AGY_MODEL_FAMILY_UNSUPPORTED")

    def _model_probe_inflight(self) -> set[str]:
        """Task ids whose probe submit is still between job write and launch (#2716)."""
        with self._assist_lock:
            inflight = getattr(self, "_model_probe_inflight_ids", None)
            if inflight is None:
                inflight = set()
                self._model_probe_inflight_ids = inflight
            return inflight

    def _acquire_agy_probe_claim(self, *, task_id: str, model: str, wait_timeout: Optional[float] = None):
        manager = _gateway().get_account_pool_manager()
        coordinator = _gateway().CrossProcessLeaseCoordinator(manager)
        try:
            return coordinator.acquire_claim(
                consumer_id=f"model-probe:{task_id}",
                wait_timeout=model_probe_pool_wait_seconds() if wait_timeout is None else wait_timeout,
                model_family=self._agy_probe_model_family(model),
            )
        except AgyAccountPoolBusyError as exc:
            raise _gateway().GatewayInputError("AGY_ACCOUNT_POOL_BUSY") from exc
        except AgyAccountPoolExhaustedError as exc:
            raise _gateway().GatewayInputError("AGY_ACCOUNT_POOL_EXHAUSTED") from exc

    def _release_assist_account_claim(self, task_id: str, job: dict[str, Any]) -> bool:
        with self._assist_lock:
            claim = self._assist_account_claims.pop(task_id, None)
        if claim is None:
            if job.get("account_lease_id_hash"):
                job["account_lease_released"] = False
                job["account_lease_cleanup_status"] = "RECONCILIATION_REQUIRED"
                return False
            return True
        try:
            claim.release()
        except Exception:
            job["account_lease_released"] = False
            job["account_lease_cleanup_status"] = "RELEASE_FAILED"
            return False
        job["account_lease_released"] = True
        job["account_lease_cleanup_status"] = "RELEASED"
        return True

    def _abandon_assist_account_claim(self, task_id: str, job: dict[str, Any]) -> None:
        with self._assist_lock:
            claim = self._assist_account_claims.pop(task_id, None)
        if claim is not None:
            claim.abandon_parent_reference()
        job["account_lease_released"] = False
        job["account_lease_cleanup_status"] = "RECONCILIATION_REQUIRED"
        job["reconciliation_required"] = True

    def _model_probe_submit(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        registered: list[str] = []
        try:
            return self._model_probe_submit_guarded(arguments, registered)
        finally:
            # Leave the in-flight set only after the final job record is written,
            # so a concurrent refresh never projects a stale pre-launch record.
            if registered:
                inflight = self._model_probe_inflight()
                with self._assist_lock:
                    for registered_task_id in registered:
                        inflight.discard(registered_task_id)

    def _model_probe_submit_guarded(self, arguments: Mapping[str, Any], registered: list[str]) -> dict[str, Any]:
        provider = str(arguments.get("provider") or "cline").strip().lower()
        metadata, executable = self._provider_executable(provider)
        if not metadata:
            raise _gateway().GatewayInputError("ASSIST_PROVIDER_NOT_REGISTERED")
        if not executable:
            raise _gateway().GatewayInputError("ASSIST_PROVIDER_UNAVAILABLE")
        model = str(arguments.get("model") or metadata.get("default_model") or "").strip()
        requested_model = model
        resolved_model = f"cline-pass/{model}" if provider == "cline" and "/" not in model else model
        prompt = _gateway()._text(arguments.get("prompt"), "prompt", max_length=16000)
        schema = arguments.get("output_schema") or {"type": "object"}
        if not isinstance(schema, Mapping) or len(json.dumps(schema, ensure_ascii=False)) > 16000:
            raise _gateway().GatewayInputError("output_schema must be a bounded object")
        workspace_mode = str(arguments.get("workspace_mode") or "isolated").strip().lower()
        if workspace_mode != "isolated":
            raise _gateway().GatewayInputError("MODEL_PROBE_REQUIRES_ISOLATED_WORKSPACE")
        task_id = self._task_id(arguments, prompt, provider, ["model_probe"])
        existing = self._assist_read(task_id)
        if existing is not None:
            semantics = self._canonical_hash({"provider": provider, "model": model, "prompt": prompt, "output_schema": schema})
            if existing.get("probe_semantics_hash") != semantics:
                raise _gateway().GatewayInputError("MODEL_PROBE_TASK_ID_CONFLICT")
            return self._assist_response(self._assist_refresh(task_id) or existing, operation="submit")
        # Resolve and attest the exact executable/version before creating an
        # isolated workspace or invoking Popen.  A failed preflight leaves no
        # probe workspace or provider process behind.
        version_root = Path(tempfile.mkdtemp(prefix=f"nexus-probe-preflight-{provider}-", dir="/tmp"))
        try:
            binary_sha256 = self._hash_file(Path(executable))
            version = subprocess.run(
                [executable, "--version"],
                cwd=version_root,
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            cli_version = (version.stdout or version.stderr).strip()[:512]
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise _gateway().GatewayInputError("ASSIST_PROVIDER_VERSION_FAILED") from exc
        finally:
            shutil.rmtree(version_root, ignore_errors=True)
        if version.returncode != 0 or not cli_version:
            raise _gateway().GatewayInputError("ASSIST_PROVIDER_VERSION_FAILED")
        action = build_action_envelope(
            task_id=task_id,
            action_type=LifecycleActionType.TASK_RUN,
            request={"task_id": task_id, "provider": provider, "model": model, "prompt": prompt, "output_schema": schema, "context_arm": arguments.get("context_arm")},
            tool_manifest_hash=_gateway().TOOL_MANIFEST_REVISION,
            expected_head=_gateway()._git("rev-parse", "HEAD").strip(),
            allowed_paths=[],
            mutation=False,
            permission_profile=PermissionProfile.VERIFY,
        ).model_dump(mode="json")
        job_id = f"probe-{uuid4().hex}"
        root = self._assist_root()
        stdout_path = root / f"{job_id}.stdout"
        stderr_path = root / f"{job_id}.stderr"
        inflight = self._model_probe_inflight()
        with self._assist_lock:
            if task_id in inflight:
                raise _gateway().GatewayInputError("MODEL_PROBE_SUBMIT_IN_PROGRESS")
            inflight.add(task_id)
            registered.append(task_id)
        workspace_root = Path(tempfile.mkdtemp(prefix=f"nexus-probe-{task_id}-", dir="/tmp"))
        probe_prompt = f"{prompt}\nReturn JSON matching this schema exactly: {json.dumps(schema, ensure_ascii=False)}"
        command = self._assist_command(
            executable=executable,
            provider=provider,
            model=model,
            prompt=probe_prompt,
            agy_print_timeout=_gateway().AGY_MODEL_PROBE_PRINT_TIMEOUT,
        )
        job: dict[str, Any] = {
            "schema": "nexus.assisted_provider_job.v1",
            "job_kind": "model_probe",
            "task_id": task_id,
            "job_id": job_id,
            "attempt_history": [],
            "action_id": action["action_id"],
            "attempt_id": action["attempt_id"],
            "status": "SUBMITTED",
            "execution_lane": "ASSISTED_CANONICAL",
            "candidate_only": True,
            "apply_requested": False,
            "provider": provider,
            "model": model,
            "requested_model": requested_model,
            "resolved_model": resolved_model,
            "binary_path": executable,
            "binary_sha256": binary_sha256,
            "cli_version": cli_version,
            "cli_version_sha256": hashlib.sha256(cli_version.encode("utf-8")).hexdigest(),
            "context_arm": arguments.get("context_arm"),
            "context_arm_applied": False,
            "context_arm_semantics": "record_only_not_applied",
            "requested_tools_policy": list(arguments.get("tools_allowed") or []),
            "tool_policy_enforcement": "cline_plan_auto_approve_false_allowlist_not_enforced",
            "workspace_mode": workspace_mode,
            "workspace_root": str(workspace_root),
            "filesystem_before": self._snapshot_workspace(workspace_root),
            "output_schema": dict(schema),
            "command_hash": hashlib.sha256(json.dumps(command, separators=(",", ":")).encode("utf-8")).hexdigest(),
            "probe_prompt_hash": self._canonical_hash(probe_prompt),
            "probe_semantics_hash": self._canonical_hash({"provider": provider, "model": model, "prompt": prompt, "output_schema": schema}),
            "action_request_hash": action["request_hash"],
            "command": command,
            "submitted_at": self._utc_now(),
            "started_at": None,
            "finished_at": None,
            "provider_time_ms": 0,
            "stdout_artifact": str(stdout_path),
            "stderr_artifact": str(stderr_path),
            "result_artifact": str(self._assist_path(task_id)),
            "action": action,
            "connector_disconnected_at": None,
            "reconnected_at": None,
        }
        self._assist_write(job)
        # Re-resolve and re-attest immediately before launch.  This closes the
        # avoidable gap between the initial evidence packet and the executable
        # actually handed to Popen.
        launch_root = Path(tempfile.mkdtemp(prefix=f"nexus-probe-launch-{provider}-", dir="/tmp"))
        launch_identity_matches = False
        launch_stat_identity: Optional[tuple[int, int, int, int]] = None
        try:
            _, launch_executable = self._provider_executable(provider)
            if launch_executable:
                launch_path = Path(launch_executable)
                launch_stat = launch_path.stat()
                launch_stat_identity = (
                    launch_stat.st_dev,
                    launch_stat.st_ino,
                    launch_stat.st_size,
                    launch_stat.st_mtime_ns,
                )
                launch_binary_sha256 = self._hash_file(launch_path)
                launch_version = subprocess.run(
                    [launch_executable, "--version"],
                    cwd=launch_root,
                    capture_output=True,
                    text=True,
                    timeout=5,
                    check=False,
                )
                launch_cli_version = (launch_version.stdout or launch_version.stderr).strip()[:512]
                launch_identity_matches = bool(
                    launch_version.returncode == 0
                    and launch_executable == executable
                    and launch_binary_sha256 == binary_sha256
                    and launch_cli_version == cli_version
                )
        except (OSError, subprocess.TimeoutExpired):
            launch_identity_matches = False
        finally:
            shutil.rmtree(launch_root, ignore_errors=True)
        if not launch_identity_matches:
            shutil.rmtree(workspace_root, ignore_errors=True)
            job.update({
                "status": "FAILED",
                "finished_at": self._utc_now(),
                "blocker": "ASSIST_PROVIDER_IDENTITY_DRIFT",
                "provider_error": "provider executable identity changed before launch",
                "model_response_verified": False,
                "process_cleanup": True,
            })
            return self._assist_response(self._assist_write(job), operation="submit")
        provider_env = None
        account_claim = None
        if provider == "agy":
            pool_wait_budget = model_probe_pool_wait_seconds()
            job["account_pool_wait_budget_seconds"] = pool_wait_budget
            job["account_pool_wait_started_at"] = self._utc_now()
            self._assist_write(job)
            pool_wait_started = time.monotonic()
            try:
                account_claim = self._acquire_agy_probe_claim(task_id=task_id, model=model, wait_timeout=pool_wait_budget)
            except _gateway().GatewayInputError as exc:
                job["account_pool_wait_ms"] = int((time.monotonic() - pool_wait_started) * 1000)
                shutil.rmtree(workspace_root, ignore_errors=True)
                job.update({
                    "status": "FAILED",
                    "finished_at": self._utc_now(),
                    "blocker": str(exc),
                    "provider_error": "Agy account pool unavailable for model probe",
                    "model_response_verified": False,
                    "process_cleanup": True,
                })
                return self._assist_response(self._assist_write(job), operation="submit")
            job["account_pool_wait_ms"] = int((time.monotonic() - pool_wait_started) * 1000)
            provider_env = dict(account_claim.lease.execution_env)
            job["account_alias_hash"] = account_claim.account_alias_hash
            job["account_lease_id_hash"] = account_claim.lease_id_hash
            job["account_lease_owner_pid"] = os.getpid()
            job["account_lease_released"] = False
            job["account_lease_cleanup_status"] = "HELD"
            with self._assist_lock:
                self._assist_account_claims[task_id] = account_claim
            self._assist_write(job)
        stdout_handle = None
        stderr_handle = None
        try:
            stdout_handle = stdout_path.open("w", encoding="utf-8")
            stderr_handle = stderr_path.open("w", encoding="utf-8")
            pass_fds: tuple[int, ...] = ()
            if account_claim is not None:
                if account_claim.lock_file_obj is None:
                    raise RuntimeError("AGY_ACCOUNT_LEASE_LOCK_MISSING_BEFORE_LAUNCH")
                pass_fds = (account_claim.lock_file_obj.fileno(),)
            process = subprocess.Popen(
                command,
                cwd=workspace_root,
                stdout=stdout_handle,
                stderr=stderr_handle,
                text=True,
                start_new_session=True,
                env=provider_env,
                pass_fds=pass_fds,
            )
        except Exception:
            if stdout_handle is not None:
                stdout_handle.close()
            if stderr_handle is not None:
                stderr_handle.close()
            if account_claim is not None:
                self._release_assist_account_claim(task_id, job)
            shutil.rmtree(workspace_root, ignore_errors=True)
            job.update({"status": "FAILED", "finished_at": self._utc_now(), "blocker": "ASSIST_PROVIDER_FAILED", "provider_error": "provider process could not start"})
            return self._assist_response(self._assist_write(job), operation="submit")
        stdout_handle.close()
        stderr_handle.close()
        post_launch_identity_matches = False
        try:
            _, post_launch_executable = self._provider_executable(provider)
            if post_launch_executable:
                post_launch_path = Path(post_launch_executable)
                post_launch_stat = post_launch_path.stat()
                post_launch_stat_identity = (
                    post_launch_stat.st_dev,
                    post_launch_stat.st_ino,
                    post_launch_stat.st_size,
                    post_launch_stat.st_mtime_ns,
                )
                post_launch_identity_matches = bool(
                    post_launch_executable == executable
                    and post_launch_stat_identity == launch_stat_identity
                    and self._hash_file(post_launch_path) == binary_sha256
                )
        except OSError:
            post_launch_identity_matches = False
        if not post_launch_identity_matches:
            terminated = False
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except OSError:
                pass
            try:
                process.wait(timeout=2)
                terminated = True
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except OSError:
                    pass
                try:
                    process.wait(timeout=2)
                    terminated = True
                except subprocess.TimeoutExpired:
                    terminated = False
            if terminated:
                shutil.rmtree(workspace_root, ignore_errors=True)
                if account_claim is not None:
                    self._release_assist_account_claim(task_id, job)
            elif account_claim is not None:
                self._abandon_assist_account_claim(task_id, job)
            job.update({
                "status": "FAILED" if terminated else "UNKNOWN_REQUIRES_RECONCILE",
                "finished_at": self._utc_now(),
                "blocker": (
                    "ASSIST_PROVIDER_IDENTITY_DRIFT"
                    if terminated
                    else "ASSIST_PROVIDER_IDENTITY_DRIFT_CLEANUP_INCOMPLETE"
                ),
                "provider_error": "provider executable identity changed during launch",
                "model_response_verified": False,
                "process_cleanup": terminated,
                "pid": process.pid,
                "pgid": process.pid,
            })
            return self._assist_response(self._assist_write(job), operation="submit")
        job.update({"status": "RUNNING", "pid": process.pid, "pgid": process.pid, "started_at": self._utc_now()})
        with self._assist_lock:
            self._assist_processes[task_id] = process
        return self._assist_response(self._assist_write(job), operation="submit")
    # fmt: on
