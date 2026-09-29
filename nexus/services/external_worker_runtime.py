"""Provider adapters for durable direct external-worker execution.

This module owns transport compilation and output interpretation only. It does
not choose routes/models, approve work, merge code, or own production state.
Account management is a separate adapter seam so providers such as Grok can
use multi-account leases without changing operation lifecycle semantics.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping, Protocol

from nexus.services.external_account_pool import AccountFailureKind, is_rotation_eligible


class ExternalWorkerRuntimeError(RuntimeError):
    """Provider adapter or external-worker runtime contract failure."""


@dataclass(frozen=True)
class AccountBinding:
    """Opaque execution binding supplied by a provider-specific account adapter."""

    provider: str
    execution_env: Mapping[str, str] = field(default_factory=dict, repr=False)
    account_alias_hash: str | None = None
    lease_id_hash: str | None = None


class AccountAdapter(Protocol):
    """Account seam for single-account and multi-account providers."""

    def acquire(self, operation_id: str) -> AccountBinding: ...

    def release(self, binding: AccountBinding) -> None: ...

    def report_failure(
        self,
        binding: AccountBinding,
        failure_kind: AccountFailureKind,
    ) -> AccountBinding | None: ...


class NoopAccountAdapter:
    """Single-account/no-rotation adapter used when the CLI owns its own auth."""

    def __init__(self, provider: str) -> None:
        self.provider = provider

    def acquire(self, operation_id: str) -> AccountBinding:
        if not operation_id:
            raise ExternalWorkerRuntimeError("OPERATION_ID_REQUIRED")
        return AccountBinding(provider=self.provider)

    def release(self, binding: AccountBinding) -> None:
        if binding.provider != self.provider:
            raise ExternalWorkerRuntimeError("ACCOUNT_BINDING_PROVIDER_MISMATCH")

    def report_failure(
        self,
        binding: AccountBinding,
        failure_kind: AccountFailureKind,
    ) -> AccountBinding | None:
        self.release(binding)
        return None


@dataclass(frozen=True)
class WorkerRequest:
    provider: str
    model: str
    prompt: str
    cwd: str
    mode: str
    auto_approve: bool
    timeout_seconds: int
    require_free: bool = False
    thinking: str = "none"


@dataclass(frozen=True)
class WorkerCommand:
    argv: tuple[str, ...]
    env: Mapping[str, str]
    cli_version: str | None


@dataclass(frozen=True)
class WorkerOutcome:
    status: str
    failure_kind: str | None
    observed_provider: str | None
    observed_model: str | None
    finish_reason: str | None
    total_cost: float | None
    provider_session_id: str | None
    tool_event_count: int
    retry_permitted: bool
    details: Mapping[str, object] = field(default_factory=dict)


class ExecutionAdapter(Protocol):
    provider: str

    def default_model(self) -> str: ...

    def compile(
        self,
        request: WorkerRequest,
        *,
        binding: AccountBinding,
    ) -> WorkerCommand: ...

    def interpret(
        self,
        request: WorkerRequest,
        *,
        exit_code: int,
        stdout_text: str,
        stderr_text: str,
    ) -> WorkerOutcome: ...


def _resolve_executable(env_name: str, binary: str) -> str:
    configured = os.getenv(env_name, "").strip()
    value = configured or shutil.which(binary)
    if not value:
        raise ExternalWorkerRuntimeError(f"EXTERNAL_WORKER_BINARY_MISSING:{binary}")
    path = Path(value).expanduser()
    if not path.is_file():
        raise ExternalWorkerRuntimeError(f"EXTERNAL_WORKER_BINARY_INVALID:{binary}")
    return str(path.resolve())


def _cli_version(executable: str) -> str | None:
    proc = subprocess.run(
        [executable, "--version"],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    if proc.returncode != 0:
        return None
    value = (proc.stdout or proc.stderr or "").strip().splitlines()
    return value[0].strip() if value else None


def _jsonl_events(text: str) -> list[dict[str, object]]:
    events: list[dict[str, object]] = []
    for line in text.splitlines():
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            events.append(value)
    return events


class ClineExecutionAdapter:
    provider = "cline"

    def default_model(self) -> str:
        return os.getenv(
            "NEXUS_CLINE_FREE_MODEL",
            "cline-free/mimo-v2.6-flash",
        ).strip()

    def compile(
        self,
        request: WorkerRequest,
        *,
        binding: AccountBinding,
    ) -> WorkerCommand:
        if binding.provider != self.provider:
            raise ExternalWorkerRuntimeError("ACCOUNT_BINDING_PROVIDER_MISMATCH")
        if request.provider != self.provider:
            raise ExternalWorkerRuntimeError("WORKER_REQUEST_PROVIDER_MISMATCH")
        if request.mode not in {"plan", "act"}:
            raise ExternalWorkerRuntimeError("CLINE_MODE_INVALID")
        if request.require_free and not request.model.startswith("cline-free/"):
            raise ExternalWorkerRuntimeError("CLINE_FREE_MODEL_REQUIRED")

        executable = _resolve_executable("NEXUS_CLINE_BIN", "cline")
        argv = [
            executable,
            "--json",
            "--auto-approve",
            "true" if request.auto_approve else "false",
            "--provider",
            "cline",
            "--model",
            request.model,
            "--cwd",
            request.cwd,
            "--timeout",
            str(request.timeout_seconds),
        ]
        if request.thinking:
            argv += ["--thinking", request.thinking]
        if request.mode == "plan":
            argv.append("--plan")
        argv.append(request.prompt)

        env = dict(os.environ)
        env.update(dict(binding.execution_env))
        return WorkerCommand(
            argv=tuple(argv),
            env=env,
            cli_version=_cli_version(executable),
        )

    def interpret(
        self,
        request: WorkerRequest,
        *,
        exit_code: int,
        stdout_text: str,
        stderr_text: str,
    ) -> WorkerOutcome:
        events = _jsonl_events(stdout_text)
        starts = [
            event
            for event in events
            if event.get("type") == "run_start" and event.get("providerId") == "cline"
        ]
        results = [event for event in events if event.get("type") == "run_result"]
        result = results[-1] if results else {}
        start = starts[-1] if starts else {}

        observed_provider: str | None = None
        observed_model: str | None = None
        provider_session_id: str | None = None

        model_value = result.get("model")
        if isinstance(model_value, dict):
            provider_raw = model_value.get("provider")
            model_raw = model_value.get("id")
            observed_provider = str(provider_raw) if provider_raw else None
            observed_model = str(model_raw) if model_raw else None
        if observed_provider is None and start.get("providerId"):
            observed_provider = str(start["providerId"])
        if observed_model is None and start.get("modelId"):
            observed_model = str(start["modelId"])
        for key in ("taskId", "sessionId", "id"):
            value = result.get(key) or start.get(key)
            if value:
                provider_session_id = str(value)
                break

        finish_reason = (
            str(result.get("finishReason")) if result.get("finishReason") is not None else None
        )
        usage = result.get("usage")
        total_cost: float | None = None
        if isinstance(usage, dict) and isinstance(usage.get("totalCost"), (int, float)):
            total_cost = float(usage["totalCost"])

        tool_event_count = 0
        for event in events:
            if event.get("type") != "agent_event":
                continue
            nested = event.get("event")
            if not isinstance(nested, dict):
                continue
            nested_type = str(nested.get("type") or "").lower()
            if "tool" in nested_type or any(
                key in nested for key in ("toolName", "tool", "toolUse")
            ):
                tool_event_count += 1

        attested = observed_provider == "cline" and observed_model == request.model
        if request.require_free:
            free_attested = (
                request.model.startswith("cline-free/")
                and observed_model is not None
                and observed_model.startswith("cline-free/")
                and total_cost == 0.0
            )
        else:
            free_attested = True

        if exit_code == 0 and finish_reason and finish_reason.lower() != "error":
            if not attested:
                return WorkerOutcome(
                    status="FAILED",
                    failure_kind="PROVIDER_ATTESTATION_MISMATCH",
                    observed_provider=observed_provider,
                    observed_model=observed_model,
                    finish_reason=finish_reason,
                    total_cost=total_cost,
                    provider_session_id=provider_session_id,
                    tool_event_count=tool_event_count,
                    retry_permitted=False,
                )
            if not free_attested:
                return WorkerOutcome(
                    status="FAILED",
                    failure_kind="FREE_MODEL_ATTESTATION_FAILED",
                    observed_provider=observed_provider,
                    observed_model=observed_model,
                    finish_reason=finish_reason,
                    total_cost=total_cost,
                    provider_session_id=provider_session_id,
                    tool_event_count=tool_event_count,
                    retry_permitted=False,
                )
            return WorkerOutcome(
                status="COMPLETED",
                failure_kind=None,
                observed_provider=observed_provider,
                observed_model=observed_model,
                finish_reason=finish_reason,
                total_cost=total_cost,
                provider_session_id=provider_session_id,
                tool_event_count=tool_event_count,
                retry_permitted=False,
            )

        failure_text = (stderr_text + "\n" + stdout_text).lower()
        if "quota" in failure_text or "rate limit" in failure_text:
            failure_kind = AccountFailureKind.QUOTA_EXHAUSTED.value
        elif "auth" in failure_text or "unauthorized" in failure_text:
            failure_kind = AccountFailureKind.AUTH_OR_SESSION_INVALID.value
        elif "timeout" in failure_text:
            failure_kind = AccountFailureKind.TIMEOUT.value
        else:
            failure_kind = AccountFailureKind.UNKNOWN.value

        return WorkerOutcome(
            status="FAILED",
            failure_kind=failure_kind,
            observed_provider=observed_provider,
            observed_model=observed_model,
            finish_reason=finish_reason,
            total_cost=total_cost,
            provider_session_id=provider_session_id,
            tool_event_count=tool_event_count,
            retry_permitted=False,
            details={"exit_code": exit_code},
        )


class OpenCodeExecutionAdapter:
    provider = "opencode"

    def default_model(self) -> str:
        return os.getenv(
            "NEXUS_OPENCODE_FREE_MODEL",
            "opencode/mimo-v2.6-flash-free",
        ).strip()

    @staticmethod
    def _model_parts(model: str) -> tuple[str, str]:
        provider_id, sep, model_id = model.partition("/")
        if not sep or not provider_id or not model_id:
            raise ExternalWorkerRuntimeError("OPENCODE_MODEL_INVALID")
        return provider_id, model_id

    def compile(
        self,
        request: WorkerRequest,
        *,
        binding: AccountBinding,
    ) -> WorkerCommand:
        if binding.provider != self.provider:
            raise ExternalWorkerRuntimeError("ACCOUNT_BINDING_PROVIDER_MISMATCH")
        if request.provider != self.provider:
            raise ExternalWorkerRuntimeError("WORKER_REQUEST_PROVIDER_MISMATCH")
        if request.mode not in {"plan", "act"}:
            raise ExternalWorkerRuntimeError("OPENCODE_MODE_INVALID")

        provider_id, model_id = self._model_parts(request.model)
        if provider_id != "opencode":
            raise ExternalWorkerRuntimeError("OPENCODE_PROVIDER_MODEL_REQUIRED")
        if request.require_free and not model_id.endswith("-free"):
            raise ExternalWorkerRuntimeError("OPENCODE_FREE_MODEL_REQUIRED")

        executable = _resolve_executable("NEXUS_OPENCODE_BIN", "opencode")
        argv = [
            executable,
            "run",
            "--pure",
            "--dir",
            request.cwd,
            "--agent",
            "plan" if request.mode == "plan" else "build",
            "--model",
            request.model,
            "--format",
            "json",
        ]
        if request.auto_approve:
            argv.append("--auto")
        if request.thinking and request.thinking != "none":
            argv += ["--variant", request.thinking]
        argv.append(request.prompt)

        env = dict(os.environ)
        env.update(dict(binding.execution_env))
        return WorkerCommand(
            argv=tuple(argv),
            env=env,
            cli_version=_cli_version(executable),
        )

    def interpret(
        self,
        request: WorkerRequest,
        *,
        exit_code: int,
        stdout_text: str,
        stderr_text: str,
    ) -> WorkerOutcome:
        events = _jsonl_events(stdout_text)
        errors = [event for event in events if event.get("type") == "error"]
        tool_event_count = sum(1 for event in events if event.get("type") == "tool_use")
        finishes = [
            event
            for event in events
            if event.get("type") == "step_finish" and isinstance(event.get("part"), dict)
        ]

        session_ids = [
            str(event["sessionID"])
            for event in events
            if isinstance(event.get("sessionID"), str) and event.get("sessionID")
        ]
        provider_session_id = session_ids[-1] if session_ids else None

        costs: list[float] = []
        for event in finishes:
            part = event.get("part")
            if not isinstance(part, dict):
                continue
            cost = part.get("cost")
            if isinstance(cost, (int, float)):
                costs.append(float(cost))
        total_cost = sum(costs) if costs else None

        final_part = finishes[-1].get("part") if finishes else {}
        finish_reason = (
            str(final_part.get("reason"))
            if isinstance(final_part, dict) and final_part.get("reason") is not None
            else None
        )
        provider_id, model_id = self._model_parts(request.model)
        observed_provider = provider_id if finishes else None
        observed_model = request.model if finishes else None

        terminal_success = (
            exit_code == 0
            and not errors
            and bool(finishes)
            and finish_reason not in {"error", "abort", "cancelled"}
        )
        free_attested = (
            provider_id == "opencode" and model_id.endswith("-free") and total_cost == 0.0
        )

        if terminal_success:
            if request.require_free and not free_attested:
                return WorkerOutcome(
                    status="FAILED",
                    failure_kind="FREE_MODEL_ATTESTATION_FAILED",
                    observed_provider=observed_provider,
                    observed_model=observed_model,
                    finish_reason=finish_reason,
                    total_cost=total_cost,
                    provider_session_id=provider_session_id,
                    tool_event_count=tool_event_count,
                    retry_permitted=False,
                    details={"attestation": "explicit-model-arg+terminal-cost"},
                )
            return WorkerOutcome(
                status="COMPLETED",
                failure_kind=None,
                observed_provider=observed_provider,
                observed_model=observed_model,
                finish_reason=finish_reason,
                total_cost=total_cost,
                provider_session_id=provider_session_id,
                tool_event_count=tool_event_count,
                retry_permitted=False,
                details={"attestation": "explicit-model-arg+terminal-cost"},
            )

        failure_text = (stderr_text + "\n" + stdout_text).lower()
        if "quota" in failure_text or "rate limit" in failure_text:
            failure_kind = AccountFailureKind.QUOTA_EXHAUSTED.value
        elif (
            "auth" in failure_text or "unauthorized" in failure_text or "forbidden" in failure_text
        ):
            failure_kind = AccountFailureKind.AUTH_OR_SESSION_INVALID.value
        elif "timeout" in failure_text:
            failure_kind = AccountFailureKind.TIMEOUT.value
        else:
            failure_kind = AccountFailureKind.UNKNOWN.value

        return WorkerOutcome(
            status="FAILED",
            failure_kind=failure_kind,
            observed_provider=observed_provider,
            observed_model=observed_model,
            finish_reason=finish_reason,
            total_cost=total_cost,
            provider_session_id=provider_session_id,
            tool_event_count=tool_event_count,
            retry_permitted=False,
            details={"exit_code": exit_code, "event_error_count": len(errors)},
        )


class CodexExecutionAdapter:
    provider = "codex"

    def default_model(self) -> str:
        return os.getenv("NEXUS_CODEX_WORKER_MODEL", "gpt-5.6-luna").strip()

    def compile(
        self,
        request: WorkerRequest,
        *,
        binding: AccountBinding,
    ) -> WorkerCommand:
        if binding.provider != self.provider:
            raise ExternalWorkerRuntimeError("ACCOUNT_BINDING_PROVIDER_MISMATCH")
        if request.provider != self.provider:
            raise ExternalWorkerRuntimeError("WORKER_REQUEST_PROVIDER_MISMATCH")
        if request.mode not in {"plan", "act"}:
            raise ExternalWorkerRuntimeError("CODEX_MODE_INVALID")
        effort = request.thinking
        if effort in {"", "none"}:
            effort = os.getenv("NEXUS_CODEX_REASONING_EFFORT", "medium").strip() or "medium"
        if effort not in {"low", "medium", "high", "xhigh"}:
            raise ExternalWorkerRuntimeError("CODEX_REASONING_EFFORT_INVALID")

        executable = _resolve_executable("NEXUS_CODEX_BIN", "codex")
        argv = [
            executable,
            "exec",
            "--json",
            "--ephemeral",
            "--skip-git-repo-check",
            "--sandbox",
            "read-only" if request.mode == "plan" else "workspace-write",
            "-m",
            request.model,
            "-c",
            f'model_reasoning_effort="{effort}"',
            "-C",
            request.cwd,
        ]
        if request.mode == "act" and request.auto_approve:
            argv.append("--approve-for-me")
        argv.append(request.prompt)
        env = dict(os.environ)
        env.update(dict(binding.execution_env))
        return WorkerCommand(
            argv=tuple(argv),
            env=env,
            cli_version=_cli_version(executable),
        )

    def interpret(
        self,
        request: WorkerRequest,
        *,
        exit_code: int,
        stdout_text: str,
        stderr_text: str,
    ) -> WorkerOutcome:
        events = _jsonl_events(stdout_text)
        event_types = [str(event.get("type") or "") for event in events]
        thread_id = None
        if events and events[0].get("type") == "thread.started":
            raw = events[0].get("thread_id")
            thread_id = str(raw) if raw else None
        ordered = False
        try:
            thread_index = event_types.index("thread.started")
            turn_index = event_types.index("turn.started", thread_index + 1)
            completed_index = event_types.index("turn.completed", turn_index + 1)
            ordered = completed_index > turn_index
        except ValueError:
            turn_index = -1
            completed_index = -1

        messages = []
        tool_event_count = 0
        if ordered:
            for event in events[turn_index + 1 : completed_index]:
                if event.get("type") != "item.completed":
                    continue
                item = event.get("item")
                if not isinstance(item, dict):
                    continue
                if item.get("type") == "agent_message":
                    if isinstance(item.get("text"), str):
                        messages.append(item["text"])
                else:
                    tool_event_count += 1

        if exit_code == 0 and ordered and messages:
            return WorkerOutcome(
                status="COMPLETED",
                failure_kind=None,
                observed_provider="codex",
                observed_model=None,
                finish_reason="turn.completed",
                total_cost=None,
                provider_session_id=thread_id,
                tool_event_count=tool_event_count,
                retry_permitted=False,
                details={
                    "model_binding": "explicit_command_argument",
                    "model_attestation": "NOT_EMITTED_BY_CODEX_JSONL",
                },
            )

        failure_text = (stderr_text + "\n" + stdout_text).lower()
        if "quota" in failure_text or "rate limit" in failure_text:
            failure_kind = AccountFailureKind.QUOTA_EXHAUSTED.value
        elif any(x in failure_text for x in ("auth", "unauthorized", "login required")):
            failure_kind = AccountFailureKind.AUTH_OR_SESSION_INVALID.value
        elif "timeout" in failure_text:
            failure_kind = AccountFailureKind.TIMEOUT.value
        else:
            failure_kind = AccountFailureKind.UNKNOWN.value
        return WorkerOutcome(
            status="FAILED",
            failure_kind=failure_kind,
            observed_provider="codex",
            observed_model=None,
            finish_reason=None,
            total_cost=None,
            provider_session_id=thread_id,
            tool_event_count=tool_event_count,
            retry_permitted=False,
            details={"exit_code": exit_code},
        )


class GrokExecutionAdapter:
    provider = "grok"

    def default_model(self) -> str:
        return os.getenv("NEXUS_GROK_WORKER_MODEL", "grok-4.5").strip()

    def compile(
        self,
        request: WorkerRequest,
        *,
        binding: AccountBinding,
    ) -> WorkerCommand:
        if binding.provider != self.provider:
            raise ExternalWorkerRuntimeError("ACCOUNT_BINDING_PROVIDER_MISMATCH")
        if request.provider != self.provider:
            raise ExternalWorkerRuntimeError("WORKER_REQUEST_PROVIDER_MISMATCH")
        if request.mode not in {"plan", "act"}:
            raise ExternalWorkerRuntimeError("GROK_MODE_INVALID")
        executable = _resolve_executable("NEXUS_GROK_BIN", "grok")
        if request.mode == "plan":
            permission_mode = "plan"
        elif request.auto_approve:
            permission_mode = "auto"
        else:
            permission_mode = "acceptEdits"
        argv = [
            executable,
            "--model",
            request.model,
            "--single",
            request.prompt,
            "--output-format",
            "json",
            "--no-alt-screen",
            "--cwd",
            request.cwd,
            "--permission-mode",
            permission_mode,
            "--no-subagents",
        ]
        if request.thinking and request.thinking != "none":
            argv += ["--reasoning-effort", request.thinking]
        env = dict(binding.execution_env)
        return WorkerCommand(
            argv=tuple(argv),
            env=env,
            cli_version=_cli_version(executable),
        )

    @staticmethod
    def _json_document(text: str) -> dict[str, object]:
        try:
            value = json.loads(text.strip())
        except (json.JSONDecodeError, TypeError):
            return {}
        return value if isinstance(value, dict) else {}

    @staticmethod
    def _find_scalar(value: object, keys: tuple[str, ...]) -> object | None:
        if isinstance(value, dict):
            for key in keys:
                if key in value and value[key] not in (None, ""):
                    return value[key]
            for nested in value.values():
                found = GrokExecutionAdapter._find_scalar(nested, keys)
                if found not in (None, ""):
                    return found
        elif isinstance(value, list):
            for nested in value:
                found = GrokExecutionAdapter._find_scalar(nested, keys)
                if found not in (None, ""):
                    return found
        return None

    def interpret(
        self,
        request: WorkerRequest,
        *,
        exit_code: int,
        stdout_text: str,
        stderr_text: str,
    ) -> WorkerOutcome:
        payload = self._json_document(stdout_text)
        model_raw = self._find_scalar(payload, ("model", "modelId", "model_id"))
        session_raw = self._find_scalar(payload, ("session_id", "sessionId", "session"))
        finish_raw = self._find_scalar(payload, ("finish_reason", "finishReason", "stop_reason"))
        cost_raw = self._find_scalar(payload, ("totalCost", "total_cost", "cost"))
        observed_model = str(model_raw) if isinstance(model_raw, str) else None
        provider_session_id = str(session_raw) if isinstance(session_raw, str) else None
        finish_reason = str(finish_raw) if finish_raw not in (None, "") else None
        total_cost = float(cost_raw) if isinstance(cost_raw, (int, float)) else None

        serialized = json.dumps(payload, sort_keys=True).lower() if payload else ""
        tool_event_count = serialized.count('"tool_use"') + serialized.count('"toolcall"')
        failure_text = stderr_text + "\n" + stdout_text
        from nexus.services.grok_account_pool import classify_grok_failure

        failure_kind = classify_grok_failure(failure_text)
        model_mismatch = observed_model is not None and observed_model != request.model
        explicit_failure = any(
            marker in failure_text.lower()
            for marker in (
                "not authenticated",
                "authentication failed",
                "unauthorized",
                "quota",
                "rate limit",
                "error",
            )
        )
        if exit_code == 0 and payload and not model_mismatch and not explicit_failure:
            return WorkerOutcome(
                status="COMPLETED",
                failure_kind=None,
                observed_provider="grok",
                observed_model=observed_model,
                finish_reason=finish_reason or "completed",
                total_cost=total_cost,
                provider_session_id=provider_session_id,
                tool_event_count=tool_event_count,
                retry_permitted=False,
                details={
                    "model_binding": (
                        "provider_output"
                        if observed_model is not None
                        else "explicit_command_argument"
                    )
                },
            )
        if model_mismatch:
            kind = "PROVIDER_ATTESTATION_MISMATCH"
            retry = False
        else:
            kind = failure_kind.value
            retry = is_rotation_eligible(failure_kind) and tool_event_count == 0
        return WorkerOutcome(
            status="FAILED",
            failure_kind=kind,
            observed_provider="grok",
            observed_model=observed_model,
            finish_reason=finish_reason,
            total_cost=total_cost,
            provider_session_id=provider_session_id,
            tool_event_count=tool_event_count,
            retry_permitted=retry,
            details={"exit_code": exit_code},
        )


class GrokAccountAdapter:
    max_failover_retries = 1

    def __init__(self) -> None:
        from nexus.services.grok_account_pool import get_grok_account_pool_manager

        self.manager = get_grok_account_pool_manager()
        self._leases: dict[str, object] = {}

    @staticmethod
    def _lease_hash(lease_id: str) -> str:
        import hashlib

        return hashlib.sha256(lease_id.encode("utf-8")).hexdigest()[:16]

    def acquire(self, operation_id: str) -> AccountBinding:
        lease = self.manager.acquire(operation_id)
        lease_hash = self._lease_hash(lease.lease_id)
        self._leases[lease_hash] = lease
        return AccountBinding(
            provider="grok",
            execution_env=lease.execution_env,
            account_alias_hash=lease.account_alias_hash,
            lease_id_hash=lease_hash,
        )

    def _lease_for(self, binding: AccountBinding):
        lease_hash = binding.lease_id_hash or ""
        lease = self._leases.get(lease_hash)
        if lease is None:
            raise ExternalWorkerRuntimeError("GROK_ACCOUNT_BINDING_NOT_OWNED")
        return lease

    def release(self, binding: AccountBinding) -> None:
        lease = self._lease_for(binding)
        self.manager.release(lease)
        self._leases.pop(binding.lease_id_hash or "", None)

    def report_failure(
        self,
        binding: AccountBinding,
        failure_kind: AccountFailureKind,
    ) -> AccountBinding | None:
        lease = self._lease_for(binding)
        try:
            replacement = self.manager.report_failure(lease, failure_kind)
        except Exception as exc:
            if type(exc).__name__ == "GrokAccountPoolExhaustedError":
                self._leases.pop(binding.lease_id_hash or "", None)
            raise
        self._leases.pop(binding.lease_id_hash or "", None)
        if replacement is None:
            return None
        lease_hash = self._lease_hash(replacement.lease_id)
        self._leases[lease_hash] = replacement
        return AccountBinding(
            provider="grok",
            execution_env=replacement.execution_env,
            account_alias_hash=replacement.account_alias_hash,
            lease_id_hash=lease_hash,
        )


def get_execution_adapter(provider: str) -> ExecutionAdapter:
    key = str(provider).strip().lower()
    if key == "cline":
        return ClineExecutionAdapter()
    if key == "opencode":
        return OpenCodeExecutionAdapter()
    if key == "codex":
        return CodexExecutionAdapter()
    if key == "grok":
        return GrokExecutionAdapter()
    raise ExternalWorkerRuntimeError(f"EXTERNAL_WORKER_PROVIDER_UNSUPPORTED:{key}")


def get_account_adapter(provider: str) -> AccountAdapter:
    key = str(provider).strip().lower()
    if key in {"cline", "opencode", "codex"}:
        return NoopAccountAdapter(key)
    if key == "grok":
        return GrokAccountAdapter()
    raise ExternalWorkerRuntimeError(f"EXTERNAL_ACCOUNT_ADAPTER_UNSUPPORTED:{key}")
