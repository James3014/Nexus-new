"""Fail-closed registry for the governed multi-worker surface."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import re
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
    AGY_RUN_HOME_COPIED_FILES,
    CLINE_ADMITTED_TOOLS,
    CLINE_RUN_HOME_PROTECTED_PATHS,
    CLINE_RUN_HOME_WRITABLE_PATHS,
    CLINE_SUPPORTED_VERSIONS,
    CLINE_TARGET_CUSTOMIZATION_PATHS,
    KEYCHAIN_NOT_APPLICABLE,
    CredentialPathOverlapError,
    agy_child_env,
    agy_delivery_failure,
    agy_model_shape_ok,
    agy_permission_bypass_flags,
    agy_tool_trace_root,
    build_seatbelt_profile,
    checkout_fingerprint,
    escaping_symlinks,
    fingerprint_roots,
    leased_target_failure,
    materialize_cline_run_home,
    materialize_run_home,
    paths_overlap,
    preserve_agy_tool_trace,
    protected_checkout_plan,
    run_home_keychain_state,
    run_home_settings_sha256,
    target_git_entry_state,
    top_level_json_objects,
    worker_home,
    write_cline_run_config,
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
    redacted_output_tail,
)
from nexus.services.agy_failure_signals import (
    AGY_UPSTREAM_UNAVAILABLE,
    agy_error_text,
    agy_login_required,
    classify_agy_account_failure,
    is_account_global_retirement,
    max_account_retirements,
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
            failure_reason=None
            if outcome == WorkerOutcome.EXECUTION_COMPLETED
            else (
                getattr(receipt, "failure_reason", None)
                or "Codex execution did not complete successfully"
            ),
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
_CLINE_DENIAL_MARKERS = (
    "execution-denied",
    "execution denied",
    "denied by user",
    "-- not a tool or system failure",
)
# #2332: only the file tools in ``CLINE_ADMITTED_TOOLS`` exist in the run and
# they are auto-approved; every other tool is disabled by the run settings.
CLINE_PERMISSION_MODE = "file_tools_auto_approved"
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
# Every cline 3.0.69 tool skip reason ("Tool approval requires an interactive
# session ...", "Tool was not executed", "User rejected the tool call", the TTY
# text above) ends with this fixed suffix (#2332).
_CLINE_SKIP_SUFFIX = "-- not a tool or system failure"
# Reason prefixes, so a reason whose suffix was cut off still counts (#2335).
_CLINE_SKIP_REASONS = (
    "tool approval requires an interactive session",
    "tool was not executed",
    "user rejected the tool call",
)
_CLINE_DENIED_TYPES = frozenset({"execution-denied"})
# Only a finish reason observed from cline 3.0.69 as a clean end counts as
# delivery; any other, unknown or missing value is non-delivery.  ``completed``
# is the end of a real successful edit run (#2332, 2026-10-17); an all-denied
# run can also end ``completed``, which the denial check above catches.
_CLINE_DELIVERED_FINISH_REASONS = frozenset({"stop", "completed"})
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
    # A structured error object carries its text in ``message`` (#2335 review).
    for item in list(candidates):
        if isinstance(item, dict):
            candidates += [item.get("error"), item.get("message")]
    return any(
        isinstance(item, str)
        and (
            _CLINE_APPROVAL_REQUIRED in item.lower()
            or _CLINE_SKIP_SUFFIX in item.lower()
            or item.strip().lower().startswith(_CLINE_SKIP_REASONS)
        )
        for item in candidates
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


def _cline_tool_events(value: Any) -> list[dict[str, Any]]:
    """The tool events in one cline ``--json`` line (#2332).

    Only structural tool events count: ``content_start``/``content_end``
    with ``contentType: tool``, at any nesting depth, never inside
    model-authored tool arguments.
    """
    events: list[dict[str, Any]] = []
    if isinstance(value, list):
        for item in value:
            events += _cline_tool_events(item)
        return events
    if not isinstance(value, dict):
        return events
    if value.get("type") in ("content_start", "content_end") and value.get("contentType") == "tool":
        events.append(value)
    for key, item in value.items():
        if key not in _CLINE_MODEL_ARGUMENT_KEYS:
            events += _cline_tool_events(item)
    return events


def _cline_tool_names(value: Any) -> set[str]:
    """Tool names of the tool events in one cline ``--json`` line (#2332)."""
    names: set[str] = set()
    for event in _cline_tool_events(value):
        name = event.get("toolName")
        names.add(name if isinstance(name, str) else "")
    return names


def _cline_rejected_before_execution(event: dict[str, Any]) -> bool:
    """A ``content_end`` cline itself skipped before running the tool.

    cline 3.0.69 emits ``Tool call <name> was rejected before execution: ...``
    as the tool error when the model calls a tool that does not exist in the
    run (``AI_NoSuchToolError``) or with unparseable input; the tool never
    executes.  Only cline's own error field is read, never model text.
    """
    if event.get("type") != "content_end":
        return False
    name = event.get("toolName")
    if not isinstance(name, str) or not name:
        return False
    prefix = f"Tool call {name} was rejected before execution:"
    output = event.get("output")
    errors = [output.get("error")] if isinstance(output, dict) else []
    if "result" in (output if isinstance(output, dict) else {}) or event.get("isError") is False:
        return False
    return any(isinstance(item, str) and item.startswith(prefix) for item in errors)


def cline_delivery_failure(stdout: bytes, stderr: bytes) -> Optional[str]:
    """Typed non-delivery reason for a Cline run that exited 0, else ``None``.

    Delivery requires a JSON ``run_result`` event whose ``finishReason`` is
    in ``_CLINE_DELIVERED_FINISH_REASONS``; any denied tool action makes the
    run non-delivery (#2195), and so does any tool outside
    ``CLINE_ADMITTED_TOOLS`` (#2332).  A denial is a text marker on stderr or
    a structured stdout event; model text that merely quotes a marker is not
    a denial.
    """
    err = stderr.decode("utf-8", errors="replace").lower()
    if any(marker in err for marker in _CLINE_DENIAL_MARKERS):
        return "cline_permission_denied"
    # Strict decode (#2459 Codex r2): a replaced byte could break a key such
    # as ``contentType`` and hide a tool event.
    try:
        text = stdout.decode("utf-8")
    except UnicodeDecodeError:
        return "cline_output_unparseable"
    results: list[dict[str, Any]] = []
    denied = False
    unadmitted: set[str] = set()
    refused_calls: set[str] = set()
    unparseable = False
    for line in text.splitlines():
        if not line.strip():
            continue
        # #2332: cline's --json stdout is one JSON object per line; a line
        # that is not one could hide a tool event, so it is never delivery.
        try:
            value = json.loads(line)
        except ValueError:
            unparseable = True
            continue
        if not isinstance(value, dict):
            unparseable = True
            continue
        denied = denied or _cline_structured_denial(value)
        for event in _cline_tool_events(value):
            name = event.get("toolName")
            if isinstance(name, str) and name in CLINE_ADMITTED_TOOLS:
                continue
            call_id = event.get("toolCallId")
            key = call_id if isinstance(call_id, str) and call_id else f"#{len(unadmitted)}"
            if _cline_rejected_before_execution(event):
                refused_calls.add(key)
            else:
                unadmitted.add(key)
                # Any end that is not cline's rejection is a tool that ran
                # (#2459 Codex r3: one rejected end must not mask it).
                if event.get("type") != "content_start":
                    unadmitted.add("#ran:" + key)
        if value.get("type") == "run_result":
            results.append(value)
    # An unadmitted tool call is tolerated only when every event of that call
    # is cline's own "rejected before execution" end (a model that called a
    # tool the run does not have); anything else is never delivery.
    if unadmitted - refused_calls or any(key.startswith("#") for key in unadmitted):
        return "cline_unadmitted_tool"
    if denied:
        return "cline_permission_denied"
    if unparseable or not results:
        return "cline_output_unparseable"
    finish = str(results[-1].get("finishReason") or "").lower()
    if finish not in _CLINE_DELIVERED_FINISH_REASONS:
        return "cline_status_not_success"
    return None


# cline 3.0.69 rejects a bare model id ("Expected format: modelType/model");
# this one was used for the #2328 and #2332 real runs.
CLINE_DEFAULT_MODEL = "cline-free/mimo-v2.6-flash"
# Cline flag spellings, named once so the #1912/#2195 scan sees one site each.
CLINE_AUTO_APPROVE_FLAG = "--auto-approve"


CLINE_YOLO_FLAG = "--yolo"


def cline_permission_bypass(argv: tuple[str, ...]) -> bool:
    """True when a Cline argv leaves the admitted approval shape (#2195, #2332).

    Since #2332 the admitted shape is exactly one ``CLINE_YOLO_FLAG`` and no
    ``CLINE_AUTO_APPROVE_FLAG`` in any spelling (and no ``-y``): yolo mode gives
    cline its smallest built-in tool set (no sub-agents or teams), and the
    adapter's run settings disable every tool outside
    ``CLINE_ADMITTED_TOOLS``, so only file tools run, inside the Seatbelt.
    Any other approval spelling is refused.  Every element is scanned, the
    trailing prompt included; the adapter refuses a prompt that starts with
    ``-`` before launch so it is never a flag.
    """
    options = list(argv)
    if any(
        item == "-y"
        or item == CLINE_AUTO_APPROVE_FLAG
        or item.startswith(CLINE_AUTO_APPROVE_FLAG + "=")
        or item.startswith("--autoapprove")
        for item in options
    ):
        return True
    return options.count(CLINE_YOLO_FLAG) != 1


_MACHO_MAGICS = (b"\xcf\xfa\xed\xfe", b"\xce\xfa\xed\xfe", b"\xca\xfe\xba\xbe")
# Only an ``exec`` line of a shell wrapper names the binary (never a comment).
_CLINE_PLATFORM_BINARY = re.compile(
    r"^\s*exec\s+(?:/usr/bin/arch\s+-arm64\s+)?(/[^\s\"']*/@cline/cli-darwin-[a-z0-9]+/bin/cline)\s",
    re.MULTILINE,
)
# The version probe runs the selected binary before the run's own Seatbelt
# exists, so it gets one that allows no write and no subprocess (#2459 r3).
_CLINE_PROBE_SEATBELT = (
    '(version 1)(allow default)(deny file-write*)(allow file-write* (literal "/dev/null"))'
    "(deny process-fork)"
)


def _is_macho(path: Path) -> bool:
    try:
        with path.open("rb") as handle:
            return handle.read(4) in _MACHO_MAGICS
    except OSError:
        return False


def cline_launch_binary(resolved: Optional[str]) -> Optional[str]:
    """The native cline binary behind ``resolved``; ``None`` when not found (#2332).

    The cline Seatbelt profile denies process-fork, and both installed
    launchers start the native binary through a child process (the npm
    ``bin/cline`` node wrapper spawns it) or an exec chain, so the adapter
    launches the native binary itself.  Accepted: the binary itself, the npm
    package's node wrapper (sibling ``node_modules/@cline/cli-darwin-*``), or
    a small shell wrapper naming the binary by absolute path.
    """
    if not resolved:
        return None
    real = Path(os.path.realpath(resolved))
    if _is_macho(real):
        return str(real)
    candidates: list[Path] = []
    if real.name == "cline" and real.parent.name == "bin":
        candidates += sorted((real.parent.parent / "node_modules" / "@cline").glob("cli-darwin-*/bin/cline"))
    try:
        if real.stat().st_size <= 4096:
            text = real.read_text(encoding="utf-8", errors="replace")
            candidates += [Path(match) for match in _CLINE_PLATFORM_BINARY.findall(text)]
    except OSError:
        pass
    for candidate in candidates:
        native = Path(os.path.realpath(candidate))
        if _is_macho(native):
            return str(native)
    return None


def cline_version_probe(executable: str) -> Optional[str]:
    """``cline --version`` output, stripped; ``None`` when it cannot be read."""
    from nexus.executors.agy_write_admission import SANDBOX_EXEC_PATH, seatbelt_available

    if not seatbelt_available():
        return None
    try:
        completed = subprocess.run(
            [SANDBOX_EXEC_PATH, "-p", _CLINE_PROBE_SEATBELT, executable, "--version"],
            capture_output=True,
            timeout=30,
            check=False,
            stdin=subprocess.DEVNULL,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if completed.returncode != 0:
        return None
    return completed.stdout.decode("utf-8", errors="replace").strip()


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
        super().__init__(
            "cline", "cline", "NEXUS_CLINE_WORKER_MODEL", CLINE_DEFAULT_MODEL, _cline_args
        )
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
        # The tool restriction and the denial/finish parsing are pinned to the
        # probed cline version; an unknown version could add a tool or change
        # the event shape (#2332 item 1).
        launch_binary = cline_launch_binary(preflight.executable)
        if launch_binary is None:
            return failed("cline_native_binary_unavailable")
        if cline_version_probe(launch_binary) not in CLINE_SUPPORTED_VERSIONS:
            return failed("cline_version_unsupported")
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
        # #2332: the run settings (tool restriction, empty MCP list) live
        # outside every Seatbelt-writable path, so the worker cannot change
        # them mid-run.
        try:
            config_tmp = Path(os.path.realpath(tempfile.mkdtemp(prefix="nexus-cline-cfg-")))
        except OSError:
            shutil.rmtree(run_tmp, ignore_errors=True)
            return failed("cline_run_config_unavailable")
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
                run_env.update(write_cline_run_config(config_tmp))
            except OSError:
                return failed("cline_run_config_unavailable")
            try:
                seatbelt = build_seatbelt_profile(
                    run_root=run_tmp,
                    writable_target=target_path,
                    extra_protected_target_names=CLINE_TARGET_CUSTOMIZATION_PATHS,
                    source_home=worker_home(None),
                    extra_protected_paths=tuple(
                        run_home / path for path in CLINE_RUN_HOME_PROTECTED_PATHS
                    ),
                    extra_reallowed_paths=tuple(
                        run_home / path for path in CLINE_RUN_HOME_WRITABLE_PATHS
                    ),
                    # #2332: no subprocess at all, so a command tool cannot run
                    # even if the run settings failed to load (cline's file
                    # tools run in-process; probed with 3.0.69).
                    deny_process_fork=True,
                )
            except CredentialPathOverlapError:
                return failed("cline_target_inside_credential_path")
            except ValueError:
                return failed("cline_seatbelt_profile_unrepresentable")
            seatbelt_sha256 = hashlib.sha256(seatbelt.encode("utf-8")).hexdigest()
            request = CliWorkerRequest(
                executable=launch_binary,
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
            shutil.rmtree(config_tmp, ignore_errors=True)
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


# #2403: agy's interactive OAuth login prompt markers live in
# nexus.services.agy_failure_signals.AGY_LOGIN_PROMPT_MARKERS (#2433).
AGY_AUTHENTICATION_REQUIRED = "agy_authentication_required"
AGY_CREDENTIALS_UNAVAILABLE = "agy_credentials_unavailable"
_POOL_SWITCH_ON = ("1", "true", "yes")
_POOL_SWITCH_OFF = ("0", "false", "no")


def _agy_login_required(result: CliWorkerResult) -> bool:
    # #2415: agy's own text only (stderr, envelope ``error``), not the reply.
    return agy_login_required(
        result.stdout.decode("utf-8", errors="replace"),
        result.stderr.decode("utf-8", errors="replace"),
        stdout_is_envelope=True,
    )


def _installed_agy_account_pool() -> Optional[Any]:
    """The host's real Agy account pool manager when it is installed, else ``None``."""
    from nexus.services.agy_account_pool import AgyAccountPoolManager, get_account_pool_manager

    manager_path = AgyAccountPoolManager.resolve_manager_path()
    if not manager_path or not Path(manager_path).is_file():
        return None
    return get_account_pool_manager()


AGY_POOL_EXHAUSTED = "agy_pool_exhausted"
AGY_POOL_BUSY = "agy_pool_busy"
AGY_ACCOUNT_RETIREMENT_UNSAFE = "agy_account_retirement_unsafe"
_AGY_RESET_IN_RE = re.compile(r"[Rr]esets in\s+((?:\d+\s*[dhms]\s*)+)")
_AGY_DURATION_PART_RE = re.compile(r"(\d+)\s*([dhms])")
_AGY_DURATION_UNITS = {"d": 86400, "h": 3600, "m": 60, "s": 1}


def _agy_model_family(model: str) -> Optional[str]:
    value = str(model or "").strip().lower()
    if value.startswith("gemini-"):
        return "gemini"
    if value.startswith(("claude-", "gpt-")):
        return "claude_gpt"
    return None


def _agy_quota_reset_seconds(result: CliWorkerResult) -> Optional[int]:
    """Seconds until the quota resets, from agy's "Resets in 64h23m29s" text.

    #2415: read from agy's own error text, never from the model's reply.
    """
    text = agy_error_text(
        result.stdout.decode("utf-8", errors="replace"),
        result.stderr.decode("utf-8", errors="replace"),
        stdout_is_envelope=True,
    )
    match = _AGY_RESET_IN_RE.search(text)
    if match is None:
        return None
    return sum(
        int(amount) * _AGY_DURATION_UNITS[unit]
        for amount, unit in _AGY_DURATION_PART_RE.findall(match.group(1))
    )


def _format_duration(seconds: int) -> str:
    hours, rest = divmod(max(0, int(seconds)), 3600)
    minutes, secs = divmod(rest, 60)
    return f"{hours}h{minutes:02d}m{secs:02d}s"


def _agy_attempt_had_model_output(result: CliWorkerResult) -> bool:
    """Whether a failed attempt did model work (so it spends the provider-call budget).

    agy's JSON envelope reports token usage; a quota or login rejection reports
    zero output and thinking tokens.  Anything unparseable counts as model work.
    """
    envelopes = top_level_json_objects(result.stdout.decode("utf-8", errors="replace"))
    if not envelopes:
        return True
    for envelope in envelopes:
        usage = envelope.get("usage")
        response = envelope.get("response")
        if not isinstance(usage, dict) or (isinstance(response, str) and response.strip()):
            return True
        for key in ("output_tokens", "thinking_tokens"):
            value = usage.get(key)
            # A missing or non-integer count is not proof of zero work.
            if not isinstance(value, int) or isinstance(value, bool) or value != 0:
                return True
    return False


def _earliest_family_reset_seconds(coordinator: Any, model_family: Optional[str]) -> Optional[int]:
    """Seconds until the earliest durable model-family cooldown ends, if any."""
    if model_family is None:
        return None
    now = time.time()
    earliest: Optional[float] = None
    try:
        for path in Path(coordinator.leases_dir).glob(f"*.family-unavailable.{model_family}.json"):
            try:
                until = float(json.loads(path.read_text(encoding="utf-8"))["unavailable_until"])
            except (OSError, ValueError, KeyError, TypeError):
                continue
            if until > now and (earliest is None or until < earliest):
                earliest = until
    except OSError:
        return None
    return None if earliest is None else int(round(earliest - now))


def _supports_cross_process_claims(pool: Any) -> bool:
    from nexus.services.agy_account_pool import AgyAccountPoolManager

    return isinstance(pool, AgyAccountPoolManager)


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
        use_installed_account_pool: bool = False,
        result_observer: Optional[Any] = None,
        require_account_pool: bool = False,
    ):
        self.executable_env = executable_env
        self.project_id_env = project_id_env
        self.model_env = model_env
        self.default_model = default_model
        self._injected_account_pool = account_pool
        self._canonical_root = Path(canonical_root) if canonical_root is not None else None
        # #2403: the production registry takes Agy credentials from the host's
        # account pool (as ``nexus_model_probe`` does) whenever the pool
        # manager is installed, without depending on an env switch.
        self._use_installed_account_pool = use_installed_account_pool
        # #2528: an optional callable that receives every raw CliWorkerResult
        # (full stdout/stderr) this adapter produced.  The receipt keeps only
        # hashes and redacted tails; a caller that must read the model's
        # answer (the real-world bench) matches a result to the receipt by
        # ``stdout_sha256``.  It never changes the receipt or the rotation; it
        # must not raise (an exception propagates out of ``invoke``).
        self._result_observer = result_observer
        # #2528: with ``require_account_pool`` the adapter never runs agy
        # unless the installed pool's cross-process claim route is taken: no
        # pool (or a pool without claims) refuses as
        # ``agy_credentials_unavailable`` instead of using the process HOME.
        self._require_account_pool = require_account_pool

    def _observe(self, result: CliWorkerResult) -> CliWorkerResult:
        if self._result_observer is not None:
            # A shallow copy: the observer cannot alter the result the
            # receipt and the rotation are decided from (bytes are immutable).
            self._result_observer(copy.copy(result))
        return result

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
        if enabled_val in _POOL_SWITCH_ON:
            from nexus.services.agy_account_pool import get_account_pool_manager
            return get_account_pool_manager()
        if self._use_installed_account_pool and enabled_val not in _POOL_SWITCH_OFF:
            return _installed_agy_account_pool()
        return None

    @staticmethod
    def _classify_failure_static(status: CliWorkerStatus, exit_code: Optional[int], stdout: bytes, stderr: bytes) -> AccountFailureKind:
        # #2415: account-level kinds come only from agy's own error channel
        # (AGY_ERROR line, the JSON envelope's ``error``, else stderr text),
        # never from the model's reply.
        if status is CliWorkerStatus.TIMED_OUT:
            return AccountFailureKind.TIMEOUT
        kind = classify_agy_account_failure(
            stdout.decode("utf-8", errors="replace"),
            stderr.decode("utf-8", errors="replace"),
            stdout_is_envelope=True,
        )
        if kind is not None:
            return kind
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
            if self._use_installed_account_pool and not all(
                (source_home / rel).is_file() for rel in AGY_RUN_HOME_COPIED_FILES
            ):
                # #2403: without the OAuth token (no pool account, or a pool
                # account without one) agy can only show its interactive
                # login prompt and time out after 60 s.
                return AGY_CREDENTIALS_UNAVAILABLE, {}, ""
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
                    target_root=target_path,
                )
            except CredentialPathOverlapError:
                return "agy_target_inside_credential_path", run_env, ""
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
                model_family=_agy_model_family(selected_model),
            )
            profile_tampered = any(
                run_home_settings_sha256(home) != digest for home, digest in run_homes
            )
        finally:
            # #2721: opt-in (NEXUS_AGY_KEEP_TOOL_TRACE=1) copy of the
            # conversation databases before the run HOME is deleted.
            trace_root = agy_tool_trace_root()
            if trace_root is not None:
                preserve_agy_tool_trace(
                    [home for home, _ in run_homes],
                    task_id=str(getattr(contract, "task_id", "") or ""),
                    run_id=run_tmp.name,
                    root=trace_root,
                )
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
        model_family: Optional[str] = None,
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
        claims_route = (
            self._use_installed_account_pool
            and self._injected_account_pool is None
            and _supports_cross_process_claims(pool)
        )
        if self._require_account_pool and not claims_route:
            return _agy_claim_receipt(
                self.provider, contract, target=target, executable=executable, argv=argv,
                started_at=started_at, result=None, outcome=WorkerOutcome.FAILED.value,
                failure_reason=AGY_CREDENTIALS_UNAVAILABLE,
                provider_calls=0, rotations=0, attempts=0, account_alias_hash=None,
            )

        if claims_route:
            return self._invoke_with_claims(
                pool,
                contract,
                prompt=prompt,
                started_at=started_at,
                target=target,
                timeout=timeout,
                executable=executable,
                build_argv=build_argv,
                on_process_group=on_process_group,
                admit_request=admit_request,
                sweep_roots=sweep_roots,
                model_family=model_family,
                provider_call_budget=provider_call_budget,
            )

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
            result = self._observe(run_cli_worker(request, on_process_group=on_process_group))
            delivery_failure: Optional[str] = None
            if result.status is CliWorkerStatus.TIMED_OUT:
                outcome = WorkerOutcome.INCOMPLETE
            elif result.status is not CliWorkerStatus.COMPLETED or result.exit_code != 0:
                outcome = WorkerOutcome.FAILED
                if result.stderr == b"seatbelt_unavailable":
                    delivery_failure = "agy_seatbelt_unavailable"
                elif _agy_login_required(result):
                    delivery_failure = AGY_AUTHENTICATION_REQUIRED
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
                stdout_tail=redacted_output_tail(result.stdout),
                stderr_tail=redacted_output_tail(result.stderr),
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
                        result = self._observe(run_cli_worker(request, on_process_group=on_process_group))
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
            if _agy_login_required(last_result):
                failure_reason = (
                    f"{AGY_AUTHENTICATION_REQUIRED}: {failure_reason}"
                    if failure_reason
                    else AGY_AUTHENTICATION_REQUIRED
                )

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
            stdout_tail=redacted_output_tail(last_result.stdout),
            stderr_tail=redacted_output_tail(last_result.stderr),
        )


    def _invoke_with_claims(
        self,
        pool: Any,
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
        sweep_roots: tuple[str, ...],
        model_family: Optional[str],
        provider_call_budget: int,
    ) -> WorkerExecutionReceipt:
        """Run agy under cross-process pool claims, rotating past unusable accounts (#2403).

        Each account is held under the same per-account flock claim as
        ``nexus_model_probe`` and ``nexus-agy-dispatch``.  An attempt rejected
        for quota, rate limit or authentication (or an account without an OAuth
        token) retires that account through the pool's own semantics (quota:
        model-family cooldown until the reported reset; others: the manager's
        bad/cooldown state) and claims the next healthy one.  Rejections that
        did no model work are ``account_rotation_attempts``; only attempts with
        model output spend ``maximum_provider_calls``.  The loop is bounded by
        the pool size; when no account is left the run fails as
        ``agy_pool_exhausted`` with the earliest known reset.
        """
        from nexus.services.agy_account_pool import (
            AgyAccountPoolBusyError,
            AgyAccountPoolExhaustedError,
            CrossProcessLeaseCoordinator,
        )

        argv = build_argv(timeout, prompt)
        consumer_id = f"worker:{contract.task_id}"
        try:
            coordinator = CrossProcessLeaseCoordinator(pool)
            pool_size = len(pool._ensure_pool()._accounts)
        except Exception as exc:
            return _agy_claim_receipt(
                self.provider, contract, target=target, executable=executable, argv=argv,
                started_at=started_at, result=None, outcome=WorkerOutcome.FAILED.value,
                failure_reason=f"account pool unavailable: {type(exc).__name__}",
                provider_calls=0, rotations=0, attempts=0, account_alias_hash=None,
            )

        excluded: set[str] = set()
        real_calls = 0
        rotations = 0
        attempts = 0
        earliest_reset: Optional[int] = None
        last_result: Optional[CliWorkerResult] = None
        last_hash: Optional[str] = None
        failure_reason: Optional[str] = None
        outcome = WorkerOutcome.FAILED.value
        current_prompt = prompt
        previous_hash: Optional[str] = None
        previous_kind: Optional[AccountFailureKind] = None

        credential_refusals = 0
        # #2415: account-wide retirements this run made (not quota cooldowns,
        # not token-less accounts); at the cap the failure is host-wide.
        account_retirements = 0
        retirement_cap = max_account_retirements()
        upstream_outage: Optional[AccountFailureKind] = None
        quota_failures = 0
        # The account whose attempt produced ``last_result`` (#2415): a later
        # token-less account must not take over the receipt's tails.
        last_result_hash: Optional[str] = None

        retirement_unsafe = False

        def exhausted_reason() -> str:
            # Accounts other processes already cooled down count too: a known
            # reset means the pool is only temporarily exhausted.
            known = [
                value
                for value in (earliest_reset, _earliest_family_reset_seconds(coordinator, model_family))
                if value is not None
            ]
            if known:
                return f"{AGY_POOL_EXHAUSTED}: earliest reset in {_format_duration(min(known))}"
            if attempts == 0 and credential_refusals:
                # No account in the pool could authenticate at all.
                return AGY_CREDENTIALS_UNAVAILABLE
            return AGY_POOL_EXHAUSTED

        # Each pass claims an account not tried yet, so pool_size + 1 passes
        # always end in success, a final failure or an exhausted pool.
        for _ in range(pool_size + 1):
            if retirement_unsafe or upstream_outage is not None:
                break
            remaining = timeout - (time.monotonic() - started_at) if timeout > 0 else 0.0
            if remaining <= 0:
                failure_reason = "shared wall-time budget exhausted"
                break
            try:
                claim = coordinator.acquire_claim(
                    consumer_id=consumer_id,
                    exclude_hashes=set(excluded),
                    wait_timeout=min(15.0, max(0.0, remaining)),
                    model_family=model_family,
                )
            except AgyAccountPoolExhaustedError:
                failure_reason = exhausted_reason()
                break
            except AgyAccountPoolBusyError:
                failure_reason = AGY_POOL_BUSY
                if quota_failures:
                    # #2415: say the busy pool came after quota exhaustion.
                    failure_reason += (
                        f": after quota exhaustion on {quota_failures} account(s)"
                    )
                    if earliest_reset is not None:
                        failure_reason += (
                            f", earliest reset in {_format_duration(earliest_reset)}"
                        )
                break
            except Exception as exc:
                failure_reason = f"account pool lease acquire failed: {type(exc).__name__}"
                break
            last_hash = claim.account_alias_hash
            retire_kind: Optional[AccountFailureKind] = None
            reset_seconds: Optional[int] = None
            try:
                refusal, run_env, seatbelt = admit_request(dict(claim.lease.execution_env))
                if refusal == AGY_CREDENTIALS_UNAVAILABLE:
                    # This account cannot authenticate: retire it and rotate.
                    rotations += 1
                    credential_refusals += 1
                    retire_kind = AccountFailureKind.AUTH_OR_SESSION_INVALID
                    failure_reason = AGY_CREDENTIALS_UNAVAILABLE
                    continue
                if refusal is not None:
                    failure_reason = refusal
                    break
                if attempts and previous_hash and previous_kind and real_calls:
                    current_prompt = (
                        f"[Continuation Handoff]\n"
                        f"Task ID: {contract.task_id}\n"
                        f"Attempt: {attempts + 1}\n"
                        f"Previous Account Hash: {previous_hash}\n"
                        f"New Account Hash: {claim.account_alias_hash}\n"
                        f"Failure Kind: {previous_kind.value}\n"
                        f"Original Instruction: {prompt}\n\n"
                        "Please re-inspect the current worktree and its file changes, then continue "
                        "the task with file edits only; shell commands are not available."
                    )
                argv_seconds = max(1, int(round(remaining)))
                request = CliWorkerRequest(
                    executable=executable,
                    argv=build_argv(argv_seconds, current_prompt),
                    cwd=target,
                    env=run_env,
                    timeout_seconds=remaining,
                    seatbelt_profile=seatbelt,
                    sweep_descendants_on_exit=True,
                    sweep_roots=sweep_roots,
                    exact_env=True,
                )
                attempts += 1
                result = self._observe(run_cli_worker(request, on_process_group=on_process_group))
                last_result = result
                last_result_hash = claim.account_alias_hash
                if result.status is CliWorkerStatus.TIMED_OUT:
                    real_calls += 1
                    outcome = WorkerOutcome.INCOMPLETE.value
                    failure_reason = f"{self.provider} execution did not complete successfully"
                    break
                if result.status is CliWorkerStatus.COMPLETED and result.exit_code == 0:
                    real_calls += 1
                    delivery_failure = _agy_result_failure(result)
                    if delivery_failure:
                        failure_reason = delivery_failure
                    else:
                        outcome = WorkerOutcome.EXECUTION_COMPLETED.value
                        failure_reason = None
                    break
                kind = self._classify_failure(
                    result.status, result.exit_code, result.stdout, result.stderr
                )
                login = _agy_login_required(result)
                if result.stderr == b"seatbelt_unavailable":
                    real_calls += 1
                    failure_reason = "agy_seatbelt_unavailable"
                    break
                if not is_rotation_eligible(kind):
                    real_calls += 1
                    failure_reason = f"non-eligible account failure: {kind.value}"
                    break
                # A rate limit is transient: rotate away for this run without
                # retiring the account for everyone else.  (#2433 N2: unlike
                # nexus-agy-dispatch, which retires it through the pool and
                # counts it toward the outage cap; documented, not aligned.)
                retire_kind = None if kind is AccountFailureKind.RATE_LIMITED else kind
                excluded.add(claim.account_alias_hash)
                if kind is AccountFailureKind.QUOTA_EXHAUSTED:
                    quota_failures += 1
                    reset_seconds = _agy_quota_reset_seconds(result)
                    if reset_seconds is not None and (
                        earliest_reset is None or reset_seconds < earliest_reset
                    ):
                        earliest_reset = reset_seconds
                failure_reason = (
                    AGY_AUTHENTICATION_REQUIRED
                    if login
                    else f"{self.provider} execution did not complete successfully"
                )
                previous_hash, previous_kind = claim.account_alias_hash, kind
                if _agy_attempt_had_model_output(result):
                    real_calls += 1
                    if real_calls >= provider_call_budget:
                        break
                else:
                    rotations += 1
            finally:
                if (
                    retire_kind is not None
                    and attempts
                    and last_result_hash == claim.account_alias_hash
                    and is_account_global_retirement(retire_kind, model_family)
                ):
                    # A provider-reported account-wide failure (a token-less
                    # account is a local fact and does not count).
                    account_retirements += 1
                    if account_retirements >= retirement_cap:
                        upstream_outage = retire_kind
                if retire_kind is not None:
                    excluded.add(claim.account_alias_hash)
                    try:
                        coordinator.retire_failed_claim(
                            claim,
                            retire_kind,
                            model_family=model_family,
                            unavailable_until=(
                                time.time() + reset_seconds if reset_seconds else None
                            ),
                        )
                    except Exception:
                        # Fail closed like nexus-agy-dispatch: an account whose
                        # failure is not durably recorded is not rotated past.
                        retirement_unsafe = True
                claim.release()
        else:
            if not retirement_unsafe and upstream_outage is None:
                failure_reason = exhausted_reason()
        if upstream_outage is not None and not retirement_unsafe:
            failure_reason = (
                f"{AGY_UPSTREAM_UNAVAILABLE}: {account_retirements} accounts failed "
                f"account-wide in one run (last: {upstream_outage.value}); "
                "no further accounts retired"
            )
        if retirement_unsafe:
            failure_reason = AGY_ACCOUNT_RETIREMENT_UNSAFE

        if outcome != WorkerOutcome.EXECUTION_COMPLETED.value and last_result is not None:
            if _agy_login_required(last_result) and failure_reason and not failure_reason.startswith(
                AGY_AUTHENTICATION_REQUIRED
            ):
                failure_reason = f"{AGY_AUTHENTICATION_REQUIRED}: {failure_reason}"
        return _agy_claim_receipt(
            self.provider, contract, target=target, executable=executable, argv=argv,
            started_at=started_at, result=last_result, outcome=outcome,
            failure_reason=failure_reason, provider_calls=real_calls, rotations=rotations,
            attempts=attempts,
            account_alias_hash=last_result_hash if last_result is not None else last_hash,
        )


def _agy_claim_receipt(
    provider: str,
    contract: Any,
    *,
    target: str,
    executable: str,
    argv: tuple[str, ...],
    started_at: float,
    result: Optional[CliWorkerResult],
    outcome: str,
    failure_reason: Optional[str],
    provider_calls: int,
    rotations: int,
    attempts: int,
    account_alias_hash: Optional[str],
) -> WorkerExecutionReceipt:
    wall = int((time.monotonic() - started_at) * 1000)
    if result is None:
        return WorkerExecutionReceipt(
            provider=provider,
            task_id=contract.task_id,
            target_worktree=target,
            worker_status=CliWorkerStatus.START_FAILED.value,
            outcome=WorkerOutcome.FAILED.value,
            exit_code=1,
            executable_identity=executable,
            argv=argv,
            stdout_sha256=CliWorkerResult.hash_bytes(b""),
            stderr_sha256=CliWorkerResult.hash_bytes(b""),
            wall_time_ms=wall,
            process_group_id=None,
            process_group_killed=False,
            timed_out=False,
            provider_calls=0,
            evidence_complete=False,
            commit_created=False,
            merge_performed=False,
            push_performed=False,
            failure_reason=failure_reason or f"{provider} execution did not start",
            account_alias_hash=account_alias_hash,
            provider_attempt_count=attempts,
            account_rotation_attempts=rotations,
        )
    return WorkerExecutionReceipt(
        provider=provider,
        task_id=contract.task_id,
        target_worktree=target,
        worker_status=result.status.value,
        outcome=outcome,
        exit_code=result.exit_code,
        executable_identity=result.executable_identity,
        argv=result.argv,
        stdout_sha256=result.stdout_sha256,
        stderr_sha256=result.stderr_sha256,
        wall_time_ms=max(result.wall_time_ms, wall),
        process_group_id=result.process_group_id,
        process_group_killed=result.process_group_killed,
        timed_out=result.timed_out,
        provider_calls=provider_calls,
        evidence_complete=outcome == WorkerOutcome.EXECUTION_COMPLETED.value,
        commit_created=False,
        merge_performed=False,
        push_performed=False,
        failure_reason=None if outcome == WorkerOutcome.EXECUTION_COMPLETED.value else failure_reason,
        account_alias_hash=account_alias_hash,
        provider_attempt_count=attempts,
        provider_env_keys_sha256=result.env_keys_sha256 or None,
        stdout_tail=redacted_output_tail(result.stdout),
        stderr_tail=redacted_output_tail(result.stderr),
        account_rotation_attempts=rotations,
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
    """Run Cline non-interactively with only file tools, auto-approved (#2332).

    Yolo mode auto-approves the tools that exist in the run; the adapter's
    run settings leave only ``CLINE_ADMITTED_TOOLS`` enabled.
    """
    return ("--json", CLINE_YOLO_FLAG, "--model", model, prompt)


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
                "agy": AgyWorkerAdapter(use_installed_account_pool=True),
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
