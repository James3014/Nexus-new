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

from nexus.services.external_account_pool import AccountFailureKind


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


def _worker_env(
    binding: AccountBinding,
    *,
    strip_openai_api_key: bool = False,
) -> dict[str, str]:
    """Build a delegated-worker environment without Owner GitHub credentials."""

    env = dict(os.environ)
    for key in ("GITHUB_TOKEN", "GH_TOKEN"):
        env.pop(key, None)
    if strip_openai_api_key:
        env.pop("OPENAI_API_KEY", None)
    env.update(dict(binding.execution_env))
    return env


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

        env = _worker_env(binding)
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


class CodexExecutionAdapter:
    provider = "codex"

    def default_model(self) -> str:
        model = os.getenv("NEXUS_CODEX_MODEL", "").strip()
        if not model:
            raise ExternalWorkerRuntimeError("CODEX_MODEL_REQUIRED")
        return model

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
        if request.require_free:
            raise ExternalWorkerRuntimeError("CODEX_FREE_MODEL_UNSUPPORTED")
        if not request.model.strip():
            raise ExternalWorkerRuntimeError("CODEX_MODEL_REQUIRED")
        if request.mode == "act" and not request.auto_approve:
            raise ExternalWorkerRuntimeError("CODEX_ACT_REQUIRES_AUTO_APPROVE")
        if request.thinking not in {"none", "low", "medium", "high", "xhigh"}:
            raise ExternalWorkerRuntimeError("CODEX_THINKING_INVALID")

        executable = _resolve_executable("NEXUS_CODEX_BIN", "codex")
        argv = [
            executable,
            "--ask-for-approval",
            "never",
            "exec",
            "--json",
            "--ephemeral",
            "--ignore-user-config",
            "--ignore-rules",
            "--skip-git-repo-check",
            "--sandbox",
            "read-only" if request.mode == "plan" else "workspace-write",
            "--model",
            request.model,
            "--cd",
            request.cwd,
            "--color",
            "never",
        ]
        if request.thinking != "none":
            argv += [
                "--config",
                f'model_reasoning_effort="{request.thinking}"',
            ]
        argv.append(request.prompt)

        return WorkerCommand(
            argv=tuple(argv),
            env=_worker_env(binding, strip_openai_api_key=True),
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
        threads = [
            event
            for event in events
            if event.get("type") == "thread.started" and isinstance(event.get("thread_id"), str)
        ]
        completed_turns = [event for event in events if event.get("type") == "turn.completed"]
        failed_turns = [event for event in events if event.get("type") == "turn.failed"]
        top_errors = [event for event in events if event.get("type") == "error"]
        item_errors = [
            event
            for event in events
            if event.get("type") == "item.completed"
            and isinstance(event.get("item"), dict)
            and event["item"].get("type") == "error"
        ]

        provider_session_id = str(threads[-1]["thread_id"]) if threads else None
        agent_messages = [
            event
            for event in events
            if event.get("type") == "item.completed"
            and isinstance(event.get("item"), dict)
            and event["item"].get("type") == "agent_message"
        ]
        non_message_items = [
            event
            for event in events
            if event.get("type") == "item.completed"
            and isinstance(event.get("item"), dict)
            and event["item"].get("type") not in {"agent_message", "error", "reasoning"}
        ]
        tool_event_count = len(non_message_items)

        terminal_success = (
            exit_code == 0
            and bool(completed_turns)
            and bool(agent_messages)
            and not failed_turns
            and not top_errors
            and not item_errors
        )
        if terminal_success:
            return WorkerOutcome(
                status="COMPLETED",
                failure_kind=None,
                observed_provider=None,
                observed_model=None,
                finish_reason="completed",
                total_cost=None,
                provider_session_id=provider_session_id,
                tool_event_count=tool_event_count,
                retry_permitted=False,
                details={
                    "attestation": "explicit-model-arg+codex-terminal-success",
                    "requested_model": request.model,
                },
            )

        failure_text = (stderr_text + "\n" + stdout_text).lower()
        if "quota" in failure_text or "rate limit" in failure_text:
            failure_kind = AccountFailureKind.QUOTA_EXHAUSTED.value
        elif (
            "logged in" in failure_text or "auth" in failure_text or "unauthorized" in failure_text
        ):
            failure_kind = AccountFailureKind.AUTH_OR_SESSION_INVALID.value
        elif "not supported" in failure_text or "model metadata" in failure_text:
            failure_kind = AccountFailureKind.MODEL_OR_TASK_ERROR.value
        elif "timeout" in failure_text:
            failure_kind = AccountFailureKind.TIMEOUT.value
        elif "permission" in failure_text or "sandbox" in failure_text:
            failure_kind = AccountFailureKind.PERMISSION_OR_SCOPE_ERROR.value
        else:
            failure_kind = AccountFailureKind.UNKNOWN.value

        return WorkerOutcome(
            status="FAILED",
            failure_kind=failure_kind,
            observed_provider=None,
            observed_model=None,
            finish_reason="failed" if failed_turns else None,
            total_cost=None,
            provider_session_id=provider_session_id,
            tool_event_count=tool_event_count,
            retry_permitted=False,
            details={
                "exit_code": exit_code,
                "requested_model": request.model,
                "top_error_count": len(top_errors),
                "item_error_count": len(item_errors),
            },
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

        env = _worker_env(binding)
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


def get_execution_adapter(provider: str) -> ExecutionAdapter:
    key = str(provider).strip().lower()
    if key == "cline":
        return ClineExecutionAdapter()
    if key == "opencode":
        return OpenCodeExecutionAdapter()
    if key == "codex":
        return CodexExecutionAdapter()
    raise ExternalWorkerRuntimeError(f"EXTERNAL_WORKER_PROVIDER_UNSUPPORTED:{key}")


def get_account_adapter(provider: str) -> AccountAdapter:
    """Return the current provider-specific account adapter.

    Cline currently lets the CLI own its authenticated account. Grok is expected
    to replace this no-op seam with a multi-account adapter backed by the
    existing ExternalAccountPool contract; that must be separately verified
    before Grok is admitted.
    """

    key = str(provider).strip().lower()
    if key == "cline":
        return NoopAccountAdapter("cline")
    if key == "opencode":
        return NoopAccountAdapter("opencode")
    if key == "codex":
        return NoopAccountAdapter("codex")
    raise ExternalWorkerRuntimeError(f"EXTERNAL_ACCOUNT_ADAPTER_UNSUPPORTED:{key}")
