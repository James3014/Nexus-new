"""Fail-closed registry for the governed multi-worker surface."""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, Optional

from nexus.executors.cli_worker import (
    CliWorkerRequest,
    CliWorkerResult,
    CliWorkerStatus,
    run_cli_worker,
)
from nexus.executors.codex_executor import CodexCliExecutor
from nexus.executors.worker_contract import (
    SUPPORTED_WORKER_PROVIDERS,
    WorkerAdapter,
    WorkerExecutionReceipt,
    WorkerOutcome,
    WorkerPreflight,
    WorkerProviderUnavailable,
)
from nexus.services.external_account_pool import (
    AccountFailureKind,
    AccountLease,
    is_rotation_eligible,
)
from nexus.services.unified_runtime import resolve_registered_provider_executable


class CodexWorkerAdapter:
    provider = "codex"

    def __init__(self, executor: Optional[CodexCliExecutor] = None):
        self.executor = executor or CodexCliExecutor()

    def preflight(self) -> WorkerPreflight:
        try:
            resolved = resolve_registered_provider_executable(self.provider)
            reason = "ready"
        except ValueError as exc:
            resolved = None
            reason = str(exc)
        return WorkerPreflight(
            provider=self.provider,
            executable=resolved,
            executable_available=resolved is not None,
            authorized=resolved is not None,
            implementation_status="IMPLEMENTED",
            ready=resolved is not None,
            reason=reason,
        )

    def invoke(
        self,
        contract: Any,
        lease: Any,
        *,
        prompt: str,
        timeout_seconds: Optional[float] = None,
        on_process_group: Any = None,
        model: Optional[str] = None,
    ) -> WorkerExecutionReceipt:
        preflight = self.preflight()
        if not preflight.ready:
            raise WorkerProviderUnavailable(f"{self.provider}: {preflight.reason}")
        executor = self.executor
        if (
            timeout_seconds is not None
            or on_process_group is not None
            or (
                hasattr(self.executor, "executable")
                and preflight.executable != getattr(self.executor, "executable", None)
            )
        ):
            executor = CodexCliExecutor(
                executable=preflight.executable or getattr(self.executor, "executable", "codex"),
                timeout_seconds=timeout_seconds or getattr(self.executor, "timeout_seconds", 900.0),
                model=model or getattr(self.executor, "model", None),
                reasoning_effort=getattr(self.executor, "reasoning_effort", None),
                on_process_group=on_process_group,
            )
        if model is None:
            receipt = executor.invoke(contract, lease, prompt=prompt)
        else:
            receipt = executor.invoke(contract, lease, prompt=prompt, model=model)
        if receipt.worker_status == CliWorkerStatus.TIMED_OUT.value:
            outcome = WorkerOutcome.INCOMPLETE
        elif receipt.worker_status != CliWorkerStatus.COMPLETED.value or receipt.exit_code != 0:
            outcome = WorkerOutcome.FAILED
        else:
            outcome = WorkerOutcome.EXECUTION_COMPLETED
        return WorkerExecutionReceipt(
            provider=receipt.provider,
            task_id=receipt.task_id,
            target_worktree=receipt.target_worktree,
            worker_status=receipt.worker_status,
            outcome=outcome.value,
            exit_code=receipt.exit_code,
            executable_identity=receipt.executable_identity,
            argv=receipt.argv,
            stdout_sha256=receipt.stdout_sha256,
            stderr_sha256=receipt.stderr_sha256,
            wall_time_ms=receipt.wall_time_ms,
            process_group_id=receipt.process_group_id,
            process_group_killed=False,
            timed_out=receipt.worker_status == CliWorkerStatus.TIMED_OUT.value,
            provider_calls=receipt.provider_calls,
            evidence_complete=outcome == WorkerOutcome.EXECUTION_COMPLETED,
            commit_created=receipt.commit_created,
            merge_performed=receipt.merge_performed,
            push_performed=False,
            failure_reason=None if outcome == WorkerOutcome.EXECUTION_COMPLETED else "Codex execution did not complete successfully",
            provider_attempt_count=getattr(receipt, "provider_attempt_count", None),
        )


class UnimplementedWorkerAdapter:
    def __init__(self, provider: str, executable: str):
        self.provider = provider
        self.executable = executable

    def preflight(self) -> WorkerPreflight:
        resolved = shutil.which(self.executable)
        return WorkerPreflight(
            provider=self.provider,
            executable=str(Path(resolved).resolve()) if resolved else None,
            executable_available=resolved is not None,
            authorized=False,
            implementation_status="UNIMPLEMENTED",
            ready=False,
            reason="provider adapter is not implemented; binary presence is not execution proof",
        )

    def invoke(self, contract: Any, lease: Any, *, prompt: str, **options: Any) -> WorkerExecutionReceipt:
        raise WorkerProviderUnavailable(
            f"{self.provider}: provider adapter is not implemented; refusing execution"
        )


class DirectCliWorkerAdapter:
    """Direct CLI adapter enabled only with explicit external-runtime authorization."""

    def __init__(self, provider: str, executable: str, model_env: str, default_model: str, argv_builder):
        self.provider = provider
        self.executable = executable
        self.model_env = model_env
        self.default_model = default_model
        self.argv_builder = argv_builder

    def preflight(self) -> WorkerPreflight:
        resolved = shutil.which(self.executable)
        authorized = os.getenv("NEXUS_EXTERNAL_RUNTIME_AUTHORIZED", "0") == "1"
        if not authorized:
            reason = "NEXUS_EXTERNAL_RUNTIME_AUTHORIZED=1 is required"
        elif resolved is None:
            reason = f"executable not found: {self.executable}"
        else:
            reason = "ready"
        return WorkerPreflight(
            provider=self.provider,
            executable=str(Path(resolved).resolve()) if resolved else None,
            executable_available=resolved is not None,
            authorized=authorized,
            implementation_status="IMPLEMENTED",
            ready=resolved is not None and authorized,
            reason=reason,
        )

    def invoke(
        self,
        contract: Any,
        lease: Any,
        *,
        prompt: str,
        timeout_seconds: Optional[float] = None,
        on_process_group: Any = None,
        model: Optional[str] = None,
    ) -> WorkerExecutionReceipt:
        preflight = self.preflight()
        if not preflight.ready:
            raise WorkerProviderUnavailable(f"{self.provider}: {preflight.reason}")
        request = CliWorkerRequest(
            executable=self.executable,
            argv=self.argv_builder(prompt, model or os.getenv(self.model_env, self.default_model)),
            cwd=str(Path(lease.target_worktree).resolve()),
            timeout_seconds=timeout_seconds or 900.0,
        )
        result = run_cli_worker(request, on_process_group=on_process_group)
        if result.status is CliWorkerStatus.TIMED_OUT:
            outcome = WorkerOutcome.INCOMPLETE
        elif result.status is not CliWorkerStatus.COMPLETED or result.exit_code != 0:
            outcome = WorkerOutcome.FAILED
        else:
            outcome = WorkerOutcome.EXECUTION_COMPLETED
        return WorkerExecutionReceipt(
            provider=self.provider,
            task_id=contract.task_id,
            target_worktree=str(Path(lease.target_worktree).resolve()),
            worker_status=result.status.value,
            outcome=outcome.value,
            exit_code=result.exit_code,
            executable_identity=result.executable_identity,
            argv=result.argv,
            stdout_sha256=result.stdout_sha256,
            stderr_sha256=result.stderr_sha256,
            wall_time_ms=result.wall_time_ms,
            process_group_id=result.process_group_id,
            process_group_killed=result.process_group_killed,
            timed_out=result.timed_out,
            provider_calls=1,
            evidence_complete=outcome == WorkerOutcome.EXECUTION_COMPLETED,
            commit_created=False,
            merge_performed=False,
            push_performed=False,
            failure_reason=None if outcome == WorkerOutcome.EXECUTION_COMPLETED else f"{self.provider} execution did not complete successfully",
        )


class AgyWorkerAdapter:
    """Governed Antigravity CLI adapter with explicit external-runtime gates and account-pool failover."""

    provider = "agy"

    def __init__(
        self,
        executable_env: str = "NEXUS_AGY_EXECUTABLE",
        project_id_env: str = "NEXUS_AGY_PROJECT_ID",
        model_env: str = "NEXUS_AGY_WORKER_MODEL",
        default_model: str = "gemini-3.6-flash-high",
        account_pool: Optional[Any] = None,
    ):
        self.executable_env = executable_env
        self.project_id_env = project_id_env
        self.model_env = model_env
        self.default_model = default_model
        self._injected_account_pool = account_pool

    def _configured_executable(self) -> str:
        try:
            return resolve_registered_provider_executable("agy")
        except ValueError:
            # Preserve a deterministic diagnostic path for preflight while
            # keeping alias mismatch/non-executable states fail closed.
            configured = os.getenv(self.executable_env, "").strip()
            if configured:
                return str(Path(configured).expanduser())
            discovered = shutil.which("agy")
            if discovered:
                return str(Path(discovered).resolve())
            home = os.getenv("HOME")
            return str((Path(home).expanduser() if home else Path.home()) / ".local/bin/agy")

    def _project_id(self) -> str:
        return os.getenv(self.project_id_env, "").strip()

    def _model(self) -> str:
        return os.getenv(self.model_env, self.default_model).strip() or self.default_model

    @staticmethod
    def _timeout_arg(timeout_seconds: float) -> str:
        seconds = round(float(timeout_seconds), 3)
        value = str(int(seconds)) if seconds.is_integer() else str(seconds)
        return f"{value}s"

    def _get_account_pool(self) -> Optional[Any]:
        if self._injected_account_pool is not None:
            return self._injected_account_pool
        enabled_val = os.getenv("NEXUS_AGY_ACCOUNT_POOL_ENABLED", "").strip().lower()
        if enabled_val in ("1", "true", "yes"):
            from nexus.services.agy_account_pool import get_account_pool_manager
            return get_account_pool_manager()
        return None

    @staticmethod
    def _classify_failure_static(status: CliWorkerStatus, exit_code: Optional[int], stdout: bytes, stderr: bytes) -> AccountFailureKind:
        if status is CliWorkerStatus.TIMED_OUT:
            return AccountFailureKind.TIMEOUT
        text = (stdout.decode("utf-8", errors="replace") + "\n" + stderr.decode("utf-8", errors="replace")).lower()
        if any(kw in text for kw in ("quota", "resource_exhausted", "exceeded your current quota", "insufficient_quota")):
            return AccountFailureKind.QUOTA_EXHAUSTED
        if any(kw in text for kw in ("429", "rate limit", "ratelimit")):
            return AccountFailureKind.RATE_LIMITED
        if any(kw in text for kw in ("unauthorized", "authenticated", "authentication", "invalid api key", "invalid_api_key", "401", "token expired", "invalid token", "login required")):
            if "expired" in text:
                return AccountFailureKind.TOKEN_EXPIRED
            return AccountFailureKind.AUTH_OR_SESSION_INVALID
        if "refresh failed" in text or "token refresh" in text:
            return AccountFailureKind.TOKEN_REFRESH_FAILED
        if "403" in text or "forbidden" in text:
            return AccountFailureKind.PERMISSION_OR_SCOPE_ERROR
        if any(kw in text for kw in ("unavailable", "503", "service unavailable")):
            return AccountFailureKind.ACCOUNT_UNAVAILABLE
        if "disabled" in text:
            return AccountFailureKind.ACCOUNT_DISABLED
        if exit_code == 2:
            return AccountFailureKind.SYNTAX_OR_IMPLEMENTATION_ERROR
        return AccountFailureKind.UNKNOWN

    def _classify_failure(self, status: CliWorkerStatus, exit_code: Optional[int], stdout: bytes, stderr: bytes) -> AccountFailureKind:
        return self._classify_failure_static(status, exit_code, stdout, stderr)

    @staticmethod
    def _is_auth_or_quota_failure(status: CliWorkerStatus, exit_code: Optional[int], stdout: bytes, stderr: bytes) -> bool:
        kind = AgyWorkerAdapter._classify_failure_static(status, exit_code, stdout, stderr)
        return is_rotation_eligible(kind)

    def preflight(self) -> WorkerPreflight:
        executable = self._configured_executable()
        resolved = shutil.which(executable)
        authorized = (
            os.getenv("NEXUS_AGY_RUNTIME_AUTHORIZED", "0") == "1"
            or os.getenv("NEXUS_EXTERNAL_RUNTIME_AUTHORIZED", "0") == "1"
        )
        if not authorized:
            reason = "NEXUS_AGY_RUNTIME_AUTHORIZED=1 is required"
        elif resolved is None:
            reason = f"executable not found: {executable}"
        else:
            reason = "ready"
        return WorkerPreflight(
            provider=self.provider,
            executable=str(Path(resolved).resolve()) if resolved else None,
            executable_available=resolved is not None,
            authorized=authorized,
            implementation_status="IMPLEMENTED",
            ready=resolved is not None and authorized,
            reason=reason,
        )

    def invoke(
        self,
        contract: Any,
        lease: Any,
        *,
        prompt: str,
        timeout_seconds: Optional[float] = None,
        on_process_group: Any = None,
        model: Optional[str] = None,
    ) -> WorkerExecutionReceipt:
        started_at = time.monotonic()
        preflight = self.preflight()
        if not preflight.ready:
            raise WorkerProviderUnavailable(f"{self.provider}: {preflight.reason}")
        target = str(Path(lease.target_worktree).resolve())
        timeout = 900.0 if timeout_seconds is None else max(0.0, float(timeout_seconds))
        executable = preflight.executable or self._configured_executable()
        raw_budget = getattr(contract, "maximum_provider_calls", 1)
        provider_call_budget = max(0, int(1 if raw_budget is None else raw_budget))

        def build_argv(call_timeout: float, current_prompt: str) -> tuple[str, ...]:
            return (
                "--new-project",
                "--add-dir",
                target,
                "--dangerously-skip-permissions",
                "--mode",
                "accept-edits",
                "--model",
                model or self._model(),
                "--print-timeout",
                self._timeout_arg(call_timeout),
                "--print",
                current_prompt,
            )

        argv = build_argv(timeout, prompt)

        if provider_call_budget == 0:
            return WorkerExecutionReceipt(
                provider=self.provider,
                task_id=contract.task_id,
                target_worktree=target,
                worker_status=CliWorkerStatus.START_FAILED.value,
                outcome=WorkerOutcome.FAILED.value,
                exit_code=1,
                executable_identity=executable,
                argv=argv,
                stdout_sha256=CliWorkerResult.hash_bytes(b""),
                stderr_sha256=CliWorkerResult.hash_bytes(b""),
                wall_time_ms=int((time.monotonic() - started_at) * 1000),
                process_group_id=None,
                process_group_killed=False,
                timed_out=False,
                provider_calls=0,
                evidence_complete=False,
                commit_created=False,
                merge_performed=False,
                push_performed=False,
                failure_reason="maximum_provider_calls is 0",
                account_alias_hash=None,
                provider_attempt_count=0,
            )

        def get_remaining_seconds() -> float:
            if timeout <= 0.0:
                return 0.0
            elapsed = time.monotonic() - started_at
            if elapsed < 0.005:  # Avoid micro elapsed time causing 41.999s regression
                elapsed = 0.0
            return timeout - elapsed

        pool = self._get_account_pool()

        if pool is None:
            remaining_seconds = get_remaining_seconds()
            if remaining_seconds <= 0:
                return WorkerExecutionReceipt(
                    provider=self.provider,
                    task_id=contract.task_id,
                    target_worktree=target,
                    worker_status=CliWorkerStatus.START_FAILED.value,
                    outcome=WorkerOutcome.FAILED.value,
                    exit_code=1,
                    executable_identity=executable,
                    argv=argv,
                    stdout_sha256=CliWorkerResult.hash_bytes(b""),
                    stderr_sha256=CliWorkerResult.hash_bytes(b""),
                    wall_time_ms=int((time.monotonic() - started_at) * 1000),
                    process_group_id=None,
                    process_group_killed=False,
                    timed_out=False,
                    provider_calls=0,
                    evidence_complete=False,
                    commit_created=False,
                    merge_performed=False,
                    push_performed=False,
                    failure_reason="shared wall-time budget exhausted",
                    account_alias_hash=None,
                    provider_attempt_count=0,
                )

            request = CliWorkerRequest(
                executable=executable,
                argv=build_argv(remaining_seconds, prompt),
                cwd=target,
                timeout_seconds=remaining_seconds,
            )
            result = run_cli_worker(request, on_process_group=on_process_group)
            if result.status is CliWorkerStatus.TIMED_OUT:
                outcome = WorkerOutcome.INCOMPLETE
            elif result.status is not CliWorkerStatus.COMPLETED or result.exit_code != 0:
                outcome = WorkerOutcome.FAILED
            else:
                outcome = WorkerOutcome.EXECUTION_COMPLETED
            return WorkerExecutionReceipt(
                provider=self.provider,
                task_id=contract.task_id,
                target_worktree=target,
                worker_status=result.status.value,
                outcome=outcome.value,
                exit_code=result.exit_code,
                executable_identity=result.executable_identity,
                argv=result.argv,
                stdout_sha256=result.stdout_sha256,
                stderr_sha256=result.stderr_sha256,
                wall_time_ms=max(result.wall_time_ms, int((time.monotonic() - started_at) * 1000)),
                process_group_id=result.process_group_id,
                process_group_killed=result.process_group_killed,
                timed_out=result.timed_out,
                provider_calls=1,
                evidence_complete=outcome == WorkerOutcome.EXECUTION_COMPLETED,
                commit_created=False,
                merge_performed=False,
                push_performed=False,
                failure_reason=None if outcome == WorkerOutcome.EXECUTION_COMPLETED else f"{self.provider} execution did not complete successfully",
                account_alias_hash=None,
                provider_attempt_count=1,
            )

        max_subprocesses = min(3, provider_call_budget)
        actual_calls = 0
        total_wall_time_ms = 0
        last_result = None
        last_account_hash = None
        previous_account_hash = None
        last_failure_kind = None
        failure_reason = None
        current_prompt = prompt

        has_lease_api = pool is not None and hasattr(pool, "acquire")
        current_lease: Optional[AccountLease] = None
        if has_lease_api and pool is not None:
            try:
                current_lease = pool.acquire(consumer_id=contract.task_id)
            except Exception as exc:
                failure_reason = f"account pool lease acquire failed: {exc}"

        if failure_reason is None:
            try:
                for attempt in range(max_subprocesses):
                    if has_lease_api and current_lease is not None:
                        active_hash = current_lease.account_alias_hash
                        sub_env = dict(current_lease.execution_env)
                    else:
                        try:
                            if pool is not None and hasattr(pool, "ensure_active"):
                                active_acc = pool.ensure_active(target_worktree=target)
                            elif pool is not None and hasattr(pool, "get_active_account"):
                                active_acc = pool.get_active_account()
                            else:
                                active_acc = getattr(pool, "active_account", None)
                        except Exception as exc:
                            failure_reason = f"account pool active account error: {exc}"
                            break

                        if pool is not None and hasattr(pool, "active_account_alias_hash") and pool.active_account_alias_hash:
                            active_hash = pool.active_account_alias_hash
                        elif active_acc is not None and hasattr(active_acc, "alias_hash"):
                            active_hash = getattr(active_acc, "alias_hash")
                        elif isinstance(active_acc, dict) and "alias_hash" in active_acc:
                            active_hash = active_acc["alias_hash"]
                        elif active_acc is not None and hasattr(active_acc, "alias"):
                            import hashlib
                            active_hash = hashlib.sha256(str(getattr(active_acc, "alias")).encode("utf-8")).hexdigest()[:12]
                        else:
                            active_hash = "unknown"

                        if pool is not None and hasattr(pool, "build_isolated_env"):
                            sub_env = pool.build_isolated_env()
                        elif active_acc is not None and hasattr(active_acc, "home_dir"):
                            from nexus.services.agy_account_pool import build_isolated_env
                            sub_env = build_isolated_env(home_dir=getattr(active_acc, "home_dir"))
                        else:
                            from nexus.services.agy_account_pool import build_isolated_env
                            sub_env = build_isolated_env()

                    last_account_hash = active_hash

                    if attempt > 0 and previous_account_hash and last_failure_kind:
                        # Add structured continuation handoff metadata without raw credentials
                        current_prompt = (
                            f"[Continuation Handoff]\n"
                            f"Task ID: {contract.task_id}\n"
                            f"Attempt: {attempt + 1}\n"
                            f"Previous Account Hash: {previous_account_hash}\n"
                            f"New Account Hash: {active_hash}\n"
                            f"Failure Kind: {last_failure_kind.value}\n"
                            f"Original Instruction: {prompt}\n\n"
                            f"Please re-inspect the current worktree, code changes, diffs, and run tests to proceed with the task."
                        )

                    remaining_seconds = get_remaining_seconds()
                    if remaining_seconds <= 0:
                        failure_reason = "shared wall-time budget exhausted"
                        break

                    request = CliWorkerRequest(
                        executable=executable,
                        argv=build_argv(remaining_seconds, current_prompt),
                        cwd=target,
                        env=sub_env,
                        timeout_seconds=remaining_seconds,
                    )

                    keys_to_restore = {}
                    for k in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "GOOGLE_GENAI_API_KEY"):
                        if k in os.environ:
                            keys_to_restore[k] = os.environ.pop(k)

                    try:
                        actual_calls += 1
                        result = run_cli_worker(request, on_process_group=on_process_group)
                    finally:
                        for k, v in keys_to_restore.items():
                            os.environ[k] = v

                    total_wall_time_ms += result.wall_time_ms
                    last_result = result

                    if result.status is CliWorkerStatus.TIMED_OUT:
                        last_failure_kind = AccountFailureKind.TIMEOUT
                        break
                    elif result.status is CliWorkerStatus.COMPLETED and result.exit_code == 0:
                        break
                    else:
                        failure_kind = self._classify_failure(result.status, result.exit_code, result.stdout, result.stderr)
                        last_failure_kind = failure_kind

                        if is_rotation_eligible(failure_kind):
                            remaining_after_call = timeout - (time.monotonic() - started_at)
                            if remaining_after_call <= 0:
                                failure_reason = "shared wall-time budget exhausted"
                                break
                            if attempt < max_subprocesses - 1:
                                try:
                                    previous_account_hash = active_hash
                                    if has_lease_api and current_lease is not None and pool is not None:
                                        next_lease = pool.report_failure(current_lease, failure_kind)
                                        if next_lease is None:
                                            failure_reason = "account pool rotation returned no replacement lease"
                                            break
                                        current_lease = next_lease
                                    else:
                                        if pool is not None and hasattr(pool, "rotate_account"):
                                            pool.rotate_account(reason=failure_kind.value, failed_account_hash=active_hash)
                                        elif pool is not None and hasattr(pool, "rotate"):
                                            pool.rotate(reason=failure_kind.value, failed_account_hash=active_hash)
                                        else:
                                            failure_reason = "account pool does not support rotation"
                                            break
                                except Exception as exc:
                                    failure_reason = f"account pool rotation failed: {exc}"
                                    break
                            else:
                                break
                        else:
                            # Non-eligible failures abort execution loop directly without rotation
                            failure_reason = f"non-eligible account failure: {failure_kind.value}"
                            break
            finally:
                if has_lease_api and pool is not None and current_lease is not None:
                    try:
                        pool.release(current_lease)
                    except Exception:
                        pass

        if actual_calls == 0 or last_result is None:
            return WorkerExecutionReceipt(
                provider=self.provider,
                task_id=contract.task_id,
                target_worktree=target,
                worker_status=CliWorkerStatus.START_FAILED.value,
                outcome=WorkerOutcome.FAILED.value,
                exit_code=1,
                executable_identity=executable,
                argv=argv,
                stdout_sha256=CliWorkerResult.hash_bytes(b""),
                stderr_sha256=CliWorkerResult.hash_bytes(b""),
                wall_time_ms=int((time.monotonic() - started_at) * 1000),
                process_group_id=None,
                process_group_killed=False,
                timed_out=False,
                provider_calls=0,
                evidence_complete=False,
                commit_created=False,
                merge_performed=False,
                push_performed=False,
                failure_reason=failure_reason or "ensure-active failed before first subprocess call",
                account_alias_hash=last_account_hash,
                provider_attempt_count=0,
            )

        if last_result.status is CliWorkerStatus.TIMED_OUT:
            outcome_val = WorkerOutcome.INCOMPLETE.value
        elif last_result.status is CliWorkerStatus.COMPLETED and last_result.exit_code == 0:
            outcome_val = WorkerOutcome.EXECUTION_COMPLETED.value
        else:
            outcome_val = WorkerOutcome.FAILED.value

        return WorkerExecutionReceipt(
            provider=self.provider,
            task_id=contract.task_id,
            target_worktree=target,
            worker_status=last_result.status.value,
            outcome=outcome_val,
            exit_code=last_result.exit_code,
            executable_identity=last_result.executable_identity,
            argv=last_result.argv,
            stdout_sha256=last_result.stdout_sha256,
            stderr_sha256=last_result.stderr_sha256,
            wall_time_ms=max(total_wall_time_ms, int((time.monotonic() - started_at) * 1000)),
            process_group_id=last_result.process_group_id,
            process_group_killed=last_result.process_group_killed,
            timed_out=last_result.timed_out,
            provider_calls=actual_calls,
            evidence_complete=outcome_val == WorkerOutcome.EXECUTION_COMPLETED.value,
            commit_created=False,
            merge_performed=False,
            push_performed=False,
            failure_reason=None if outcome_val == WorkerOutcome.EXECUTION_COMPLETED.value else (failure_reason or f"{self.provider} execution did not complete successfully"),
            account_alias_hash=last_account_hash,
            provider_attempt_count=actual_calls,
        )


class OllamaPatchWorkerAdapter:
    """Local Ollama worker using a governed unified-diff output contract."""

    provider = "ollama"

    def __init__(self, executable: str = "ollama", model_env: str = "NEXUS_OLLAMA_WORKER_MODEL"):
        self.executable = executable
        self.model_env = model_env

    def preflight(self) -> WorkerPreflight:
        resolved = shutil.which(self.executable)
        authorized = os.getenv("NEXUS_LOCAL_MODEL_CALL_ALLOWED", "0") == "1"
        if not authorized:
            reason = "NEXUS_LOCAL_MODEL_CALL_ALLOWED=1 is required"
        elif resolved is None:
            reason = f"executable not found: {self.executable}"
        else:
            reason = "ready"
        return WorkerPreflight(
            provider=self.provider,
            executable=str(Path(resolved).resolve()) if resolved else None,
            executable_available=resolved is not None,
            authorized=authorized,
            implementation_status="IMPLEMENTED",
            ready=resolved is not None and authorized,
            reason=reason,
        )

    @staticmethod
    def _extract_patch(stdout: bytes) -> Optional[bytes]:
        marker = b"diff --git "
        index = stdout.find(marker)
        if index < 0:
            return None
        patch = stdout[index:]
        return patch if b"\n" in patch else None

    def invoke(
        self,
        contract: Any,
        lease: Any,
        *,
        prompt: str,
        timeout_seconds: Optional[float] = None,
        on_process_group: Any = None,
        model: Optional[str] = None,
    ) -> WorkerExecutionReceipt:
        preflight = self.preflight()
        if not preflight.ready:
            raise WorkerProviderUnavailable(f"{self.provider}: {preflight.reason}")
        model = model or os.getenv(self.model_env, "qwen2.5-coder:7b")
        request = CliWorkerRequest(
            executable=self.executable,
            argv=("run", model, prompt + "\nReturn only a unified git diff beginning with diff --git."),
            cwd=str(Path(lease.target_worktree).resolve()),
            timeout_seconds=timeout_seconds or 900.0,
        )
        result = run_cli_worker(request, on_process_group=on_process_group)
        patch = self._extract_patch(result.stdout)
        applied = False
        failure_reason = None
        if result.status is CliWorkerStatus.COMPLETED and result.exit_code == 0 and patch:
            target = str(Path(lease.target_worktree).resolve())
            check = subprocess.run(
                ["git", "apply", "--check", "--binary", "--whitespace=nowarn", "-"],
                cwd=target,
                input=patch,
                capture_output=True,
            )
            if check.returncode == 0:
                applied_result = subprocess.run(
                    ["git", "apply", "--binary", "--whitespace=nowarn", "-"],
                    cwd=target,
                    input=patch,
                    capture_output=True,
                )
                applied = applied_result.returncode == 0
                if not applied:
                    failure_reason = applied_result.stderr.decode("utf-8", errors="replace")
            else:
                failure_reason = check.stderr.decode("utf-8", errors="replace")
        else:
            failure_reason = "Ollama did not return a usable unified diff"
        outcome = WorkerOutcome.EXECUTION_COMPLETED if applied else WorkerOutcome.FAILED
        return WorkerExecutionReceipt(
            provider=self.provider,
            task_id=contract.task_id,
            target_worktree=str(Path(lease.target_worktree).resolve()),
            worker_status=result.status.value,
            outcome=outcome.value,
            exit_code=result.exit_code,
            executable_identity=result.executable_identity,
            argv=result.argv,
            stdout_sha256=result.stdout_sha256,
            stderr_sha256=result.stderr_sha256,
            wall_time_ms=result.wall_time_ms,
            process_group_id=result.process_group_id,
            process_group_killed=result.process_group_killed,
            timed_out=result.timed_out,
            provider_calls=1,
            evidence_complete=outcome == WorkerOutcome.EXECUTION_COMPLETED,
            commit_created=False,
            merge_performed=False,
            push_performed=False,
            failure_reason=None if outcome == WorkerOutcome.EXECUTION_COMPLETED else failure_reason,
        )


def _gemini_args(prompt: str, model: str) -> tuple[str, ...]:
    return ("--skip-trust", "--approval-mode", "auto_edit", "-m", model, "-p", prompt, "--output-format", "json")


def _opencode_args(prompt: str, model: str) -> tuple[str, ...]:
    return ("run", "--model", model, prompt)


def _mimo_args(prompt: str, model: str) -> tuple[str, ...]:
    return ("run", "--never-ask-questions", "--model", model, prompt)


def _cline_args(prompt: str, model: str) -> tuple[str, ...]:
    """Run Cline non-interactively against the isolated Target only."""
    return ("--json", "--yolo", "--model", model, prompt)


def _grok_args(prompt: str, model: str) -> tuple[str, ...]:
    return ("--model", model, "--prompt", prompt)


class WorkerRegistry:
    def __init__(self, adapters: dict[str, WorkerAdapter]):
        adapters = dict(adapters)
        missing = set(SUPPORTED_WORKER_PROVIDERS) - set(adapters)
        if missing <= {"agy", "grok", "cline"}:
            adapters.setdefault("agy", AgyWorkerAdapter())
            adapters.setdefault(
                "grok",
                DirectCliWorkerAdapter("grok", "grok", "NEXUS_GROK_WORKER_MODEL", "grok-4.5", _grok_args),
            )
            adapters.setdefault(
                "cline",
                DirectCliWorkerAdapter("cline", "cline", "NEXUS_CLINE_WORKER_MODEL", "glm-5.2", _cline_args),
            )
            missing = set()
        unknown = set(adapters) - set(SUPPORTED_WORKER_PROVIDERS)
        if unknown:
            raise ValueError(f"unknown worker providers: {sorted(unknown)}")
        if missing:
            raise ValueError(f"missing worker providers: {sorted(missing)}")
        self._adapters = dict(adapters)

    @classmethod
    def default(cls) -> "WorkerRegistry":
        return cls(
            {
                "codex": CodexWorkerAdapter(),
                "gemini": DirectCliWorkerAdapter("gemini", "gemini", "NEXUS_GEMINI_WORKER_MODEL", "gemini-2.5-flash", _gemini_args),
                "agy": AgyWorkerAdapter(),
                "opencode": DirectCliWorkerAdapter("opencode", "opencode", "NEXUS_OPENCODE_WORKER_MODEL", "opencode/big-pickle", _opencode_args),
                "mimo": DirectCliWorkerAdapter("mimo", "mimo", "NEXUS_MIMO_WORKER_MODEL", "xiaomi/mimo-v2.5", _mimo_args),
                "ollama": OllamaPatchWorkerAdapter(),
                "cline": DirectCliWorkerAdapter("cline", "cline", "NEXUS_CLINE_WORKER_MODEL", "glm-5.2", _cline_args),
                "grok": DirectCliWorkerAdapter("grok", "grok", "NEXUS_GROK_WORKER_MODEL", "grok-4.5", _grok_args),
            }
        )

    @property
    def providers(self) -> tuple[str, ...]:
        return SUPPORTED_WORKER_PROVIDERS

    def adapter(self, provider: str) -> WorkerAdapter:
        key = str(provider).strip().lower()
        try:
            return self._adapters[key]
        except KeyError as exc:
            raise ValueError(f"unknown worker provider: {provider}") from exc

    def preflight(self, provider: str) -> WorkerPreflight:
        return self.adapter(provider).preflight()

    def invoke(
        self,
        provider: str,
        contract: Any,
        lease: Any,
        *,
        prompt: str,
        **options: Any,
    ) -> WorkerExecutionReceipt:
        preflight = self.preflight(provider)
        if not preflight.ready:
            raise WorkerProviderUnavailable(f"{provider}: {preflight.reason}")
        return self.adapter(provider).invoke(contract, lease, prompt=prompt, **options)
