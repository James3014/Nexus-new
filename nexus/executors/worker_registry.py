"""Fail-closed registry for the governed multi-worker surface."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import time
from dataclasses import replace
from pathlib import Path
from typing import Any, Mapping, Optional

from nexus.executors.agy_write_admission import (
    AGY_IMPLEMENTATION_ROLES,
    AGY_PERMISSION_BYPASS_FLAGS,
    AGY_PERMISSION_MODE_ACCEPT_EDITS,
    AGY_PERMISSION_MODE_PLAN,
    AGY_READ_ONLY_ROLES,
    CLINE_TARGET_CUSTOMIZATION_PATHS,
    KEYCHAIN_NOT_APPLICABLE,
    agy_child_env,
    agy_delivery_failure,
    agy_model_shape_ok,
    agy_permission_bypass_flags,
    build_seatbelt_profile,
    checkout_fingerprint,
    escaping_symlinks,
    fingerprint_roots,
    leased_target_failure,
    materialize_cline_run_home,
    materialize_run_home,
    paths_overlap,
    protected_checkout_plan,
    run_home_keychain_state,
    run_home_settings_sha256,
    target_git_entry_state,
    worker_home,
)
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

__all__ = [
    "AGY_IMPLEMENTATION_ROLES",
    "AGY_PERMISSION_BYPASS_FLAGS",
    "AGY_PERMISSION_MODE_ACCEPT_EDITS",
    "AGY_PERMISSION_MODE_PLAN",
    "AGY_READ_ONLY_ROLES",
    "AgyWorkerAdapter",
    "ClineWorkerAdapter",
    "CodexWorkerAdapter",
    "DirectCliWorkerAdapter",
    "OllamaPatchWorkerAdapter",
    "UnimplementedWorkerAdapter",
    "WorkerRegistry",
    "agy_delivery_failure",
    "agy_permission_bypass_flags",
    "canonical_checkout_fingerprint",
    "cline_delivery_failure",
    "cline_permission_bypass",
]

# Backwards-compatible name for the single-checkout fingerprint.
canonical_checkout_fingerprint = checkout_fingerprint


def _default_canonical_checkout_root() -> Path:
    from nexus.orchestrator.canonical_source_root import CANONICAL_SOURCE_ROOT

    return Path(CANONICAL_SOURCE_ROOT)


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


# Cline reports a refused tool as ``execution-denied`` with the default
# reason "Tool execution denied by user." (observed in the cline 3.0.69 CLI).
# The text markers are trusted on stderr only (as for Agy's headless marker);
# stdout is read as JSON events and only structural keys are inspected.
_CLINE_DENIAL_MARKERS = ("execution-denied", "execution denied", "denied by user")
CLINE_PERMISSION_MODE = "auto_approve_false"
# Assumed structured shapes (cline 3.0.69 bundles the AI SDK tool-result
# model; the exact ``--json`` envelope is not pinned, so any nesting depth is
# searched):
#   {"type": "execution-denied", "reason": ...}             a denied tool output
#   {"type": "tool-approval-response", "approved": false}   a refused approval
#   {"is_error": true, "result": "Tool execution denied ..."} a provider-mapped
#       denied tool result (the default reasons below, prefix match only)
# Observed (cline 3.0.69, headless with tool auto-approval off, #2254): the denied
# tool surfaces as a tool ``content_end`` event whose ``error`` /
# ``output.error`` is ``Tool "<name>" requires approval in a TTY session -- ...``
# and the run may still end with ``finishReason: "stop"``.
_CLINE_APPROVAL_REQUIRED = "requires approval in a tty session"
_CLINE_DENIED_TYPES = frozenset({"execution-denied"})
# Only a finish reason observed from cline 3.0.69 as a clean end counts as
# delivery; any other, unknown or missing value is non-delivery.
_CLINE_DELIVERED_FINISH_REASONS = frozenset({"stop"})
_CLINE_DENIED_DEFAULT_REASONS = ("tool execution denied", "tool call execution denied")
# Model-authored tool arguments are never read as structure.
_CLINE_MODEL_ARGUMENT_KEYS = frozenset({"input", "args", "arguments", "params", "parameters"})


def _cline_tool_error_denied(event: dict[str, Any]) -> bool:
    """A tool result event whose *error* fields carry the headless approval refusal.

    Only the ``error`` and ``output.error`` strings of a tool result are read;
    a tool's successful ``result`` text (e.g. a file that quotes the phrase)
    and the model's own text are never inspected.
    """
    candidates = [event.get("error")]
    output = event.get("output")
    if isinstance(output, dict):
        candidates.append(output.get("error"))
    return any(
        isinstance(item, str) and _CLINE_APPROVAL_REQUIRED in item.lower() for item in candidates
    )


def _cline_structured_denial(value: Any) -> bool:
    if isinstance(value, list):
        return any(_cline_structured_denial(item) for item in value)
    if not isinstance(value, dict):
        return False
    kind = value.get("type")
    if kind in _CLINE_DENIED_TYPES:
        return True
    if kind == "content_end" and value.get("contentType") == "tool" and _cline_tool_error_denied(
        value
    ):
        return True
    if kind == "tool-approval-response" and value.get("approved") is False:
        return True
    result = value.get("result")
    if (
        value.get("is_error") is True
        and isinstance(result, str)
        and result.strip().lower().startswith(_CLINE_DENIED_DEFAULT_REASONS)
    ):
        return True
    return any(
        _cline_structured_denial(item)
        for key, item in value.items()
        if key not in _CLINE_MODEL_ARGUMENT_KEYS
    )


def cline_delivery_failure(stdout: bytes, stderr: bytes) -> Optional[str]:
    """Typed non-delivery reason for a Cline run that exited 0, else ``None``.

    Delivery requires a JSON ``run_result`` event whose ``finishReason`` is
    not ``error``; any denied tool action makes the run non-delivery (#2195).
    A denial is a text marker on stderr or a structured stdout event; model
    text that merely quotes a marker is not a denial.
    """
    err = stderr.decode("utf-8", errors="replace").lower()
    if any(marker in err for marker in _CLINE_DENIAL_MARKERS):
        return "cline_permission_denied"
    text = stdout.decode("utf-8", errors="replace")
    results: list[dict[str, Any]] = []
    denied = False
    for line in text.splitlines():
        try:
            value = json.loads(line)
        except ValueError:
            continue
        if not isinstance(value, dict):
            continue
        denied = denied or _cline_structured_denial(value)
        if value.get("type") == "run_result":
            results.append(value)
    if denied:
        return "cline_permission_denied"
    if not results:
        return "cline_output_unparseable"
    finish = str(results[-1].get("finishReason") or "").lower()
    if finish not in _CLINE_DELIVERED_FINISH_REASONS:
        return "cline_status_not_success"
    return None


# Cline flag spellings, named once so the #1912/#2195 scan sees one site each.
CLINE_AUTO_APPROVE_FLAG = "--auto-approve"
CLINE_YOLO_FLAGS = frozenset({"--yolo", "-y"})


def cline_permission_bypass(argv: tuple[str, ...]) -> bool:
    """True when a Cline argv auto-approves tools (#2195).

    Cline auto-approves by default, so the argv must carry exactly one
    explicit auto-approve flag set to ``false`` and no yolo flag.  Every
    element is scanned, the trailing prompt included; the adapter refuses a
    prompt that starts with ``-`` before launch so it is never a flag.
    """
    options = list(argv)
    if any(
        item in CLINE_YOLO_FLAGS or item.startswith(CLINE_AUTO_APPROVE_FLAG + "=")
        for item in options
    ):
        return True
    approvals = [
        options[index + 1] if index + 1 < len(options) else ""
        for index, item in enumerate(options)
        if item == CLINE_AUTO_APPROVE_FLAG
    ]
    return approvals != ["false"]


def _cline_target_args(prompt: str, model: str, target: str) -> tuple[str, ...]:
    return ("--cwd", target, *_cline_args(prompt, model))


class ClineWorkerAdapter(DirectCliWorkerAdapter):
    """Cline under the #1912 write-admission model (#2195, #2254).

    No auto-approval: Cline runs with tool auto-approval off in the leased
    target only.  It runs under the same boundary as Agy: a Seatbelt profile
    (only the target and the per-run root are writable; no sandbox-exec means
    the launcher refuses to start), a disposable HOME carrying only cline's
    auth file, an exact child env and a descendant sweep.  The protected
    checkouts are fingerprinted, and the target's symlinks and ``.git`` entry
    are compared, before and after the run; a denied tool action is
    non-delivery.
    """

    # The registry (production path) always binds the target to the lease.
    requires_leased_target = True

    def __init__(self, canonical_root: Optional[Path | str] = None):
        super().__init__("cline", "cline", "NEXUS_CLINE_WORKER_MODEL", "glm-5.2", _cline_args)
        self._canonical_root = Path(canonical_root) if canonical_root is not None else None

    def invoke(
        self,
        contract: Any,
        lease: Any,
        *,
        prompt: str,
        timeout_seconds: Optional[float] = None,
        on_process_group: Any = None,
        model: Optional[str] = None,
        require_leased_target: bool = False,
    ) -> WorkerExecutionReceipt:
        preflight = self.preflight()
        if not preflight.ready:
            raise WorkerProviderUnavailable(f"{self.provider}: {preflight.reason}")
        target_path = Path(lease.target_worktree).resolve()
        selected_model = str(model or os.getenv(self.model_env, self.default_model))
        argv = _cline_target_args(prompt, selected_model, str(target_path))

        def failed(reason: str) -> WorkerExecutionReceipt:
            return WorkerExecutionReceipt(
                provider=self.provider,
                task_id=contract.task_id,
                target_worktree=str(target_path),
                worker_status=CliWorkerStatus.START_FAILED.value,
                outcome=WorkerOutcome.FAILED.value,
                exit_code=1,
                executable_identity=preflight.executable or self.executable,
                argv=argv,
                stdout_sha256=CliWorkerResult.hash_bytes(b""),
                stderr_sha256=CliWorkerResult.hash_bytes(b""),
                wall_time_ms=0,
                process_group_id=None,
                process_group_killed=False,
                timed_out=False,
                provider_calls=0,
                evidence_complete=False,
                commit_created=False,
                merge_performed=False,
                push_performed=False,
                failure_reason=reason,
                provider_permission_mode=CLINE_PERMISSION_MODE,
            )

        # The prompt is the last positional argv element; one starting with
        # "-" could be parsed by Cline as a flag or subcommand.
        if prompt.startswith("-"):
            return failed("cline_prompt_shape_unsupported")
        if cline_permission_bypass(argv):
            return failed("cline_command_shape_unsupported")
        # Same rule as Agy: a required lease is never skipped because the
        # contract lacks the attribute (it then fails the lease check).
        if require_leased_target or hasattr(contract, "target_worktree_root"):
            lease_failure = leased_target_failure(contract, lease)
            if lease_failure is not None:
                return failed(lease_failure.replace("agy_", "cline_", 1))
        canonical = (
            self._canonical_root
            if self._canonical_root is not None
            else _default_canonical_checkout_root()
        )
        plan = protected_checkout_plan(
            target=target_path,
            controller_repo_root=getattr(contract, "controller_repo_root", None),
            canonical_source_root=canonical.resolve(),
        )
        if any(paths_overlap(target_path, root) for root, _ in plan):
            return failed("cline_target_overlaps_canonical_checkout")
        before = fingerprint_roots(plan)
        if before is None:
            return failed("canonical_checkout_snapshot_unavailable")
        symlinks_before = escaping_symlinks(target_path)
        git_entry_before = target_git_entry_state(target_path)

        # #2254: same boundary as Agy.  Seatbelt makes the target and the run
        # root the only writable paths (the canonical checkout, the real HOME
        # and ~/.ssh / ~/.config/gh stay read-only); the worker sees a
        # disposable HOME with only cline's auth file and an exact env.  With
        # no sandbox-exec the launcher refuses to start (fail closed).
        run_tmp = Path(os.path.realpath(tempfile.mkdtemp(prefix="nexus-cline-run-")))
        seatbelt_sha256 = ""
        try:
            run_home = run_tmp / "home"
            run_tmpdir = run_tmp / "tmp"
            run_tmpdir.mkdir(parents=True)
            run_env = agy_child_env(None, home=run_home, tmpdir=run_tmpdir)
            refusal = materialize_cline_run_home(worker_home(None), run_home)
            if refusal is not None:
                return failed(refusal)
            try:
                seatbelt = build_seatbelt_profile(
                    run_root=run_tmp,
                    writable_target=target_path,
                    extra_protected_target_names=CLINE_TARGET_CUSTOMIZATION_PATHS,
                    source_home=worker_home(None),
                )
            except ValueError:
                return failed("cline_seatbelt_profile_unrepresentable")
            seatbelt_sha256 = hashlib.sha256(seatbelt.encode("utf-8")).hexdigest()
            request = CliWorkerRequest(
                executable=self.executable,
                argv=argv,
                cwd=str(target_path),
                timeout_seconds=timeout_seconds or 900.0,
                env=run_env,
                seatbelt_profile=seatbelt,
                sweep_descendants_on_exit=True,
                sweep_roots=(str(target_path), str(run_tmp)),
                exact_env=True,
            )
            result = run_cli_worker(request, on_process_group=on_process_group)
        finally:
            shutil.rmtree(run_tmp, ignore_errors=True)
        failure_reason: Optional[str] = None
        if result.status is CliWorkerStatus.TIMED_OUT:
            outcome = WorkerOutcome.INCOMPLETE
            failure_reason = f"{self.provider} execution did not complete successfully"
        elif result.status is not CliWorkerStatus.COMPLETED or result.exit_code != 0:
            outcome = WorkerOutcome.FAILED
            failure_reason = f"{self.provider} execution did not complete successfully"
            if result.stderr == b"seatbelt_unavailable":
                failure_reason = "cline_seatbelt_unavailable"
        else:
            failure_reason = cline_delivery_failure(result.stdout, result.stderr)
            if failure_reason is None and result.descendants_swept is False:
                failure_reason = "cline_descendant_sweep_failed"
            outcome = WorkerOutcome.FAILED if failure_reason else WorkerOutcome.EXECUTION_COMPLETED
        after = fingerprint_roots(plan)
        if after is None:
            outcome, failure_reason = WorkerOutcome.FAILED, "canonical_snapshot_failed"
        elif after != before:
            outcome, failure_reason = (
                WorkerOutcome.FAILED,
                "canonical_checkout_integrity_violation",
            )
        elif target_git_entry_state(target_path) != git_entry_before:
            outcome, failure_reason = WorkerOutcome.FAILED, "cline_target_gitdir_tampered"
        elif escaping_symlinks(target_path) != symlinks_before:
            outcome, failure_reason = WorkerOutcome.FAILED, "cline_target_symlink_escape"
        return WorkerExecutionReceipt(
            provider=self.provider,
            task_id=contract.task_id,
            target_worktree=str(target_path),
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
            provider_permission_mode=CLINE_PERMISSION_MODE,
            provider_write_sandbox=f"seatbelt:{seatbelt_sha256};keychain:{KEYCHAIN_NOT_APPLICABLE}",
        )


def _agy_result_failure(result: CliWorkerResult) -> Optional[str]:
    """Non-delivery reason for an Agy process that exited 0, else ``None``."""
    reason = agy_delivery_failure(result.stdout, result.stderr)
    if reason is None and result.descendants_swept is False:
        reason = "agy_descendant_sweep_failed"
    return reason


class AgyWorkerAdapter:
    """Governed Antigravity CLI adapter with explicit external-runtime gates and account-pool failover."""

    provider = "agy"
    # The registry forwards ``worker_role`` only to role-aware adapters; Agy
    # refuses to run without an explicit, admitted role (#1912).
    accepts_worker_role = True

    def __init__(
        self,
        executable_env: str = "NEXUS_AGY_EXECUTABLE",
        project_id_env: str = "NEXUS_AGY_PROJECT_ID",
        model_env: str = "NEXUS_AGY_WORKER_MODEL",
        default_model: str = "gemini-3.8-flash-medium",
        account_pool: Optional[Any] = None,
        canonical_root: Optional[Path | str] = None,
    ):
        self.executable_env = executable_env
        self.project_id_env = project_id_env
        self.model_env = model_env
        self.default_model = default_model
        self._injected_account_pool = account_pool
        self._canonical_root = Path(canonical_root) if canonical_root is not None else None

    def _canonical_checkout_root(self) -> Path:
        root = (
            self._canonical_root
            if self._canonical_root is not None
            else _default_canonical_checkout_root()
        )
        return root.resolve()

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
        worker_role: Optional[str] = None,
        require_leased_target: bool = False,
    ) -> WorkerExecutionReceipt:
        """Run Agy under the #1912 write-admission model.

        The target must be a runtime-owned worktree outside the canonical
        checkout; the canonical checkout is fingerprinted before and after the
        run and any change fails the run closed (it is reported, never
        reverted). The candidate diff stays in the target worktree for the
        existing governed collect/verify/apply path.
        """
        started_at = time.monotonic()
        preflight = self.preflight()
        if not preflight.ready:
            raise WorkerProviderUnavailable(f"{self.provider}: {preflight.reason}")
        target_path = Path(lease.target_worktree).resolve()
        target = str(target_path)
        executable = preflight.executable or self._configured_executable()

        def refuse(
            reason: str, permission_mode: Optional[str], argv: tuple[str, ...] = ()
        ) -> WorkerExecutionReceipt:
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
                failure_reason=reason,
                account_alias_hash=None,
                provider_attempt_count=0,
                provider_permission_mode=permission_mode,
            )

        if worker_role is None or not str(worker_role).strip():
            return refuse("agy_worker_role_required", None)
        # The registry (production path) always requires a leased target; a
        # contract that carries a target root is always bound as well.
        if require_leased_target or hasattr(contract, "target_worktree_root"):
            lease_failure = leased_target_failure(contract, lease)
            if lease_failure is not None:
                return refuse(lease_failure, None)
        role = str(worker_role).strip().lower()
        if role in AGY_READ_ONLY_ROLES:
            read_only, permission_mode = True, AGY_PERMISSION_MODE_PLAN
        elif role in AGY_IMPLEMENTATION_ROLES:
            read_only, permission_mode = False, AGY_PERMISSION_MODE_ACCEPT_EDITS
        else:
            return refuse("agy_worker_role_unsupported", None)

        selected_model = str(model or self._model())
        timeout = 900.0 if timeout_seconds is None else max(0.0, float(timeout_seconds))
        mode_flags = ("--mode", "plan", "--sandbox") if read_only else ("--mode", "accept-edits")

        def build_argv(call_timeout: float, current_prompt: str) -> tuple[str, ...]:
            return (
                "--new-project",
                "--add-dir",
                target,
                *mode_flags,
                "--model",
                selected_model,
                "--output-format",
                "json",
                "--print-timeout",
                self._timeout_arg(call_timeout),
                "--print",
                current_prompt,
            )

        argv = build_argv(timeout, prompt)
        if not agy_model_shape_ok(selected_model) or agy_permission_bypass_flags(argv):
            return refuse("agy_command_shape_unsupported", permission_mode)

        plan = protected_checkout_plan(
            target=target_path,
            controller_repo_root=getattr(contract, "controller_repo_root", None),
            canonical_source_root=self._canonical_checkout_root(),
        )
        if any(paths_overlap(target_path, root) for root, _ in plan):
            return refuse("agy_target_overlaps_canonical_checkout", permission_mode, argv)
        before = fingerprint_roots(plan)
        if before is None:
            return refuse("canonical_checkout_snapshot_unavailable", permission_mode, argv)
        symlinks_before = escaping_symlinks(target_path)
        git_entry_before = target_git_entry_state(target_path)

        run_tmp = Path(os.path.realpath(tempfile.mkdtemp(prefix="nexus-agy-run-")))
        facts: dict[str, str] = {}
        run_homes: list[tuple[Path, str]] = []

        def admit_request(
            env: Optional[Mapping[str, str]],
        ) -> tuple[Optional[str], dict[str, str], str]:
            """Per-attempt disposable HOME, explicit settings and Seatbelt profile."""
            source_home = worker_home(env)
            attempt_root = Path(tempfile.mkdtemp(prefix="attempt-", dir=run_tmp))
            run_home = attempt_root / "home"
            run_tmpdir = attempt_root / "tmp"
            run_tmpdir.mkdir(parents=True)
            # Explicit allowlist: the pool/ambient env is never forwarded.
            run_env = agy_child_env(env, home=run_home, tmpdir=run_tmpdir)
            refusal, profile_sha256 = materialize_run_home(
                source_home, run_home, read_only=read_only
            )
            facts["profile_sha256"] = profile_sha256
            if refusal is not None:
                return refusal, run_env, ""
            # #2260: the run HOME has its own default keychain on macOS, so agy's
            # token store never raises the modal "no keychain" dialog.
            facts["keychain_state"] = run_home_keychain_state(run_home)
            run_homes.append((run_home, run_home_settings_sha256(run_home)))
            try:
                seatbelt = build_seatbelt_profile(
                    run_root=run_tmp,
                    writable_target=None if read_only else target_path,
                    run_home=run_home,
                    source_home=source_home,
                )
            except ValueError:
                return "agy_seatbelt_profile_unrepresentable", run_env, ""
            facts["seatbelt_sha256"] = hashlib.sha256(seatbelt.encode("utf-8")).hexdigest()
            return refusal, run_env, seatbelt

        try:
            # The shared provider wall-time budget starts after the integrity
            # snapshot so Git bookkeeping never eats into the provider deadline.
            receipt = self._invoke_admitted(
                contract,
                prompt=prompt,
                started_at=time.monotonic(),
                target=target,
                timeout=timeout,
                executable=executable,
                build_argv=build_argv,
                on_process_group=on_process_group,
                admit_request=admit_request,
                sweep_roots=(str(run_tmp),) if read_only else (str(target_path), str(run_tmp)),
            )
            profile_tampered = any(
                run_home_settings_sha256(home) != digest for home, digest in run_homes
            )
        finally:
            shutil.rmtree(run_tmp, ignore_errors=True)
        receipt = replace(
            receipt,
            provider_permission_mode=permission_mode,
            provider_permission_profile_sha256=facts.get("profile_sha256") or None,
            provider_write_sandbox=(
                f"seatbelt:{facts['seatbelt_sha256']}"
                f";keychain:{facts.get('keychain_state', KEYCHAIN_NOT_APPLICABLE)}"
                if facts.get("seatbelt_sha256")
                else None
            ),
        )
        after = fingerprint_roots(plan)
        post_failure: Optional[str] = None
        if after is None:
            post_failure = "canonical_snapshot_failed"
        elif after != before:
            post_failure = "canonical_checkout_integrity_violation"
        elif profile_tampered:
            post_failure = "agy_permission_profile_tampered"
        elif target_git_entry_state(target_path) != git_entry_before:
            post_failure = "agy_target_gitdir_tampered"
        elif escaping_symlinks(target_path) != symlinks_before:
            post_failure = "agy_target_symlink_escape"
        if post_failure is not None:
            receipt = replace(
                receipt,
                outcome=WorkerOutcome.FAILED.value,
                evidence_complete=False,
                failure_reason=post_failure,
            )
        return receipt

    def _invoke_admitted(
        self,
        contract: Any,
        *,
        prompt: str,
        started_at: float,
        target: str,
        timeout: float,
        executable: str,
        build_argv: Any,
        on_process_group: Any,
        admit_request: Any,
        sweep_roots: tuple[str, ...] = (),
    ) -> WorkerExecutionReceipt:
        raw_budget = getattr(contract, "maximum_provider_calls", 1)
        provider_call_budget = max(0, int(1 if raw_budget is None else raw_budget))
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

            argv_seconds = int(round(remaining_seconds))
            if argv_seconds < 1:
                argv_seconds = 1
            refusal, run_env, seatbelt = admit_request(None)
            if refusal is not None:
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
                    failure_reason=refusal,
                    account_alias_hash=None,
                    provider_attempt_count=0,
                )
            request = CliWorkerRequest(
                executable=executable,
                argv=build_argv(argv_seconds, prompt),
                cwd=target,
                env=run_env,
                timeout_seconds=remaining_seconds,
                seatbelt_profile=seatbelt,
                sweep_descendants_on_exit=True,
                sweep_roots=sweep_roots,
                exact_env=True,
            )
            result = run_cli_worker(request, on_process_group=on_process_group)
            delivery_failure: Optional[str] = None
            if result.status is CliWorkerStatus.TIMED_OUT:
                outcome = WorkerOutcome.INCOMPLETE
            elif result.status is not CliWorkerStatus.COMPLETED or result.exit_code != 0:
                outcome = WorkerOutcome.FAILED
                if result.stderr == b"seatbelt_unavailable":
                    delivery_failure = "agy_seatbelt_unavailable"
            else:
                delivery_failure = _agy_result_failure(result)
                outcome = (
                    WorkerOutcome.FAILED if delivery_failure else WorkerOutcome.EXECUTION_COMPLETED
                )
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
                failure_reason=None
                if outcome == WorkerOutcome.EXECUTION_COMPLETED
                else (
                    delivery_failure or f"{self.provider} execution did not complete successfully"
                ),
                account_alias_hash=None,
                provider_attempt_count=1,
                provider_env_keys_sha256=result.env_keys_sha256 or None,
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
                            "Please re-inspect the current worktree and its file changes, then continue "
                            "the task with file edits only; shell commands are not available."
                        )

                    remaining_seconds = get_remaining_seconds()
                    if remaining_seconds <= 0:
                        failure_reason = "shared wall-time budget exhausted"
                        break

                    argv_seconds = int(round(remaining_seconds))
                    if argv_seconds < 1:
                        argv_seconds = 1
                    refusal, run_env, seatbelt = admit_request(sub_env)
                    if refusal is not None:
                        failure_reason = refusal
                        break
                    request = CliWorkerRequest(
                        executable=executable,
                        argv=build_argv(argv_seconds, current_prompt),
                        cwd=target,
                        env=run_env,
                        timeout_seconds=remaining_seconds,
                        seatbelt_profile=seatbelt,
                        sweep_descendants_on_exit=True,
                        sweep_roots=sweep_roots,
                        exact_env=True,
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
            delivery_failure = _agy_result_failure(last_result)
            if delivery_failure:
                outcome_val = WorkerOutcome.FAILED.value
                failure_reason = delivery_failure
            else:
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
            provider_env_keys_sha256=last_result.env_keys_sha256 or None,
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
    """Run Cline non-interactively with tool auto-approval off (#2195)."""
    return ("--json", CLINE_AUTO_APPROVE_FLAG, "false", "--model", model, prompt)


def _grok_args(prompt: str, model: str) -> tuple[str, ...]:
    return ("--model", model, "--single", prompt, "--output-format", "json", "--no-alt-screen")


def _cline_adapter() -> DirectCliWorkerAdapter:
    # Typed as the base class so the pre-existing WorkerAdapter protocol
    # finding on the registry keeps its identity (#2195).
    return ClineWorkerAdapter()


class WorkerRegistry:
    def __init__(self, adapters: dict[str, WorkerAdapter]):
        adapters = dict(adapters)
        missing = set(SUPPORTED_WORKER_PROVIDERS) - set(adapters)
        if missing <= {"agy", "grok", "cline"}:
            adapters.setdefault("agy", AgyWorkerAdapter())  # pyright: ignore[reportArgumentType]  # pre-existing WorkerAdapter protocol mismatch, line-shifted by #1912
            adapters.setdefault(
                "grok",
                DirectCliWorkerAdapter("grok", "grok", "NEXUS_GROK_WORKER_MODEL", "grok-4.5", _grok_args),
            )
            adapters.setdefault("cline", _cline_adapter())
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
                "cline": _cline_adapter(),
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

        adapter = self.adapter(provider)
        worker_role = options.pop("worker_role", None)
        options.pop("require_leased_target", None)
        if bool(getattr(adapter, "accepts_worker_role", False)):
            options["worker_role"] = worker_role
            # Production entry: the target must be the contract's leased worktree.
            options["require_leased_target"] = True
        elif bool(getattr(adapter, "requires_leased_target", False)):
            options["require_leased_target"] = True
        effect_authorization = options.pop("effect_authorization", None)
        tool_projection_manifest = options.pop("tool_projection_manifest", None)
        if (effect_authorization is None) != (tool_projection_manifest is None):
            raise WorkerProviderUnavailable(
                f"{provider}: effect authorization and tool projection must be supplied together"
            )
        if effect_authorization is not None:
            if not bool(getattr(adapter, "supports_effect_projection", False)):
                raise WorkerProviderUnavailable(
                    f"{provider}: effect-authorized execution requires a projection-aware backend"
                )
            options["effect_authorization"] = effect_authorization
            options["tool_projection_manifest"] = tool_projection_manifest

        return adapter.invoke(contract, lease, prompt=prompt, **options)
