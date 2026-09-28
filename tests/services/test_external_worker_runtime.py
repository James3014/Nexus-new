from __future__ import annotations

import json
import stat
from pathlib import Path

import pytest

from nexus.services.external_worker_runtime import (
    AccountBinding,
    ClineExecutionAdapter,
    ExternalWorkerRuntimeError,
    NoopAccountAdapter,
    OpenCodeExecutionAdapter,
    WorkerRequest,
)


def _request(tmp_path: Path, *, model: str = "cline-free/mimo-v2.6-flash") -> WorkerRequest:
    return WorkerRequest(
        provider="cline",
        model=model,
        prompt="test prompt",
        cwd=str(tmp_path),
        mode="plan",
        auto_approve=False,
        timeout_seconds=60,
        require_free=True,
        thinking="none",
    )


def test_noop_account_adapter_is_provider_bound() -> None:
    adapter = NoopAccountAdapter("cline")
    binding = adapter.acquire("clineop_" + "a" * 32)
    assert binding.provider == "cline"
    assert dict(binding.execution_env) == {}
    adapter.release(binding)
    with pytest.raises(ExternalWorkerRuntimeError, match="ACCOUNT_BINDING_PROVIDER_MISMATCH"):
        adapter.release(AccountBinding(provider="grok"))


def test_cline_compile_requires_free_model_when_requested(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = tmp_path / "cline"
    fake.write_text("#!/bin/sh\necho 3.0.65\n", encoding="utf-8")
    fake.chmod(fake.stat().st_mode | stat.S_IXUSR)
    monkeypatch.setenv("NEXUS_CLINE_BIN", str(fake))

    adapter = ClineExecutionAdapter()
    with pytest.raises(ExternalWorkerRuntimeError, match="CLINE_FREE_MODEL_REQUIRED"):
        adapter.compile(
            _request(tmp_path, model="cline-pass/paid-model"),
            binding=AccountBinding(provider="cline"),
        )


def test_cline_compile_is_noninteractive_and_bounded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = tmp_path / "cline"
    fake.write_text("#!/bin/sh\necho 3.0.65\n", encoding="utf-8")
    fake.chmod(fake.stat().st_mode | stat.S_IXUSR)
    monkeypatch.setenv("NEXUS_CLINE_BIN", str(fake))

    command = ClineExecutionAdapter().compile(
        _request(tmp_path),
        binding=AccountBinding(provider="cline"),
    )

    argv = list(command.argv)
    assert "--json" in argv
    assert "--plan" in argv
    assert argv[argv.index("--auto-approve") + 1] == "false"
    assert argv[argv.index("--provider") + 1] == "cline"
    assert argv[argv.index("--model") + 1] == "cline-free/mimo-v2.6-flash"
    assert argv[argv.index("--timeout") + 1] == "60"
    assert command.cli_version == "3.0.65"


def test_cline_success_requires_exact_model_provider_and_zero_cost(tmp_path: Path) -> None:
    request = _request(tmp_path)
    stdout = "\n".join([
        json.dumps({
            "type": "run_start",
            "providerId": "cline",
            "modelId": request.model,
            "taskId": "task-1",
        }),
        json.dumps({
            "type": "run_result",
            "finishReason": "completed",
            "text": "ok",
            "model": {
                "provider": "cline",
                "id": request.model,
            },
            "usage": {"totalCost": 0},
            "taskId": "task-1",
        }),
    ])
    result = ClineExecutionAdapter().interpret(
        request,
        exit_code=0,
        stdout_text=stdout,
        stderr_text="",
    )
    assert result.status == "COMPLETED"
    assert result.failure_kind is None
    assert result.observed_model == request.model
    assert result.total_cost == 0.0
    assert result.provider_session_id == "task-1"
    assert result.retry_permitted is False


@pytest.mark.parametrize(
    ("provider", "model", "cost", "failure"),
    [
        ("wrong", "cline-free/mimo-v2.6-flash", 0, "PROVIDER_ATTESTATION_MISMATCH"),
        ("cline", "cline-free/other", 0, "PROVIDER_ATTESTATION_MISMATCH"),
        ("cline", "cline-free/mimo-v2.6-flash", 0.01, "FREE_MODEL_ATTESTATION_FAILED"),
    ],
)
def test_cline_success_fails_closed_on_attestation_mismatch(
    tmp_path: Path,
    provider: str,
    model: str,
    cost: float,
    failure: str,
) -> None:
    request = _request(tmp_path)
    stdout = json.dumps({
        "type": "run_result",
        "finishReason": "completed",
        "model": {"provider": provider, "id": model},
        "usage": {"totalCost": cost},
    })
    result = ClineExecutionAdapter().interpret(
        request,
        exit_code=0,
        stdout_text=stdout,
        stderr_text="",
    )
    assert result.status == "FAILED"
    assert result.failure_kind == failure
    assert result.retry_permitted is False


def test_cline_quota_failure_is_classified_but_not_auto_retryable(tmp_path: Path) -> None:
    request = _request(tmp_path)
    result = ClineExecutionAdapter().interpret(
        request,
        exit_code=1,
        stdout_text="",
        stderr_text="quota exhausted",
    )
    assert result.status == "FAILED"
    assert result.failure_kind == "QUOTA_EXHAUSTED"
    assert result.retry_permitted is False


def _opencode_request(
    tmp_path: Path,
    *,
    model: str = "opencode/mimo-v2.6-flash-free",
    mode: str = "plan",
    auto_approve: bool = False,
    thinking: str = "none",
) -> WorkerRequest:
    return WorkerRequest(
        provider="opencode",
        model=model,
        prompt="test prompt",
        cwd=str(tmp_path),
        mode=mode,
        auto_approve=auto_approve,
        timeout_seconds=60,
        require_free=True,
        thinking=thinking,
    )


def test_opencode_compile_uses_headless_safe_plan_contract(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = tmp_path / "opencode"
    fake.write_text("#!/bin/sh\necho 1.18.32\n", encoding="utf-8")
    fake.chmod(fake.stat().st_mode | stat.S_IXUSR)
    monkeypatch.setenv("NEXUS_OPENCODE_BIN", str(fake))

    command = OpenCodeExecutionAdapter().compile(
        _opencode_request(tmp_path),
        binding=AccountBinding(provider="opencode"),
    )

    argv = list(command.argv)
    assert argv[1] == "run"
    assert "--pure" in argv
    assert argv[argv.index("--dir") + 1] == str(tmp_path)
    assert argv[argv.index("--agent") + 1] == "plan"
    assert argv[argv.index("--model") + 1] == "opencode/mimo-v2.6-flash-free"
    assert argv[argv.index("--format") + 1] == "json"
    assert "--auto" not in argv
    assert "--variant" not in argv
    assert command.cli_version == "1.18.32"


def test_opencode_act_requires_explicit_auto_approve(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = tmp_path / "opencode"
    fake.write_text("#!/bin/sh\necho 1.18.32\n", encoding="utf-8")
    fake.chmod(fake.stat().st_mode | stat.S_IXUSR)
    monkeypatch.setenv("NEXUS_OPENCODE_BIN", str(fake))

    command = OpenCodeExecutionAdapter().compile(
        _opencode_request(
            tmp_path,
            mode="act",
            auto_approve=True,
            thinking="high",
        ),
        binding=AccountBinding(provider="opencode"),
    )

    argv = list(command.argv)
    assert argv[argv.index("--agent") + 1] == "build"
    assert "--auto" in argv
    assert argv[argv.index("--variant") + 1] == "high"


@pytest.mark.parametrize(
    "model",
    [
        "opencode/paid-model",
        "other/mimo-v2.6-flash-free",
        "mimo-v2.6-flash-free",
    ],
)
def test_opencode_compile_rejects_nonfree_or_wrong_provider_model(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    model: str,
) -> None:
    fake = tmp_path / "opencode"
    fake.write_text("#!/bin/sh\necho 1.18.32\n", encoding="utf-8")
    fake.chmod(fake.stat().st_mode | stat.S_IXUSR)
    monkeypatch.setenv("NEXUS_OPENCODE_BIN", str(fake))

    with pytest.raises(ExternalWorkerRuntimeError):
        OpenCodeExecutionAdapter().compile(
            _opencode_request(tmp_path, model=model),
            binding=AccountBinding(provider="opencode"),
        )


def test_opencode_success_uses_terminal_event_and_zero_cost_attestation(
    tmp_path: Path,
) -> None:
    request = _opencode_request(tmp_path)
    stdout = "\n".join([
        json.dumps({
            "type": "step_start",
            "sessionID": "ses_fixture",
            "part": {"type": "step-start"},
        }),
        json.dumps({
            "type": "text",
            "sessionID": "ses_fixture",
            "part": {"type": "text", "text": "ok"},
        }),
        json.dumps({
            "type": "step_finish",
            "sessionID": "ses_fixture",
            "part": {
                "type": "step-finish",
                "reason": "stop",
                "cost": 0,
            },
        }),
    ])

    result = OpenCodeExecutionAdapter().interpret(
        request,
        exit_code=0,
        stdout_text=stdout,
        stderr_text="",
    )

    assert result.status == "COMPLETED"
    assert result.failure_kind is None
    assert result.observed_provider == "opencode"
    assert result.observed_model == "opencode/mimo-v2.6-flash-free"
    assert result.total_cost == 0.0
    assert result.provider_session_id == "ses_fixture"
    assert result.tool_event_count == 0
    assert result.retry_permitted is False


def test_opencode_tool_events_are_counted_and_cost_is_summed(tmp_path: Path) -> None:
    request = _opencode_request(tmp_path)
    stdout = "\n".join([
        json.dumps({
            "type": "tool_use",
            "sessionID": "ses_fixture",
            "part": {"type": "tool", "tool": "read"},
        }),
        json.dumps({
            "type": "step_finish",
            "sessionID": "ses_fixture",
            "part": {
                "type": "step-finish",
                "reason": "tool-calls",
                "cost": 0,
            },
        }),
        json.dumps({
            "type": "step_finish",
            "sessionID": "ses_fixture",
            "part": {
                "type": "step-finish",
                "reason": "stop",
                "cost": 0,
            },
        }),
    ])

    result = OpenCodeExecutionAdapter().interpret(
        request,
        exit_code=0,
        stdout_text=stdout,
        stderr_text="",
    )

    assert result.status == "COMPLETED"
    assert result.tool_event_count == 1
    assert result.total_cost == 0.0


def test_opencode_free_mode_fails_closed_on_nonzero_cost(tmp_path: Path) -> None:
    request = _opencode_request(tmp_path)
    stdout = json.dumps({
        "type": "step_finish",
        "sessionID": "ses_fixture",
        "part": {
            "type": "step-finish",
            "reason": "stop",
            "cost": 0.01,
        },
    })

    result = OpenCodeExecutionAdapter().interpret(
        request,
        exit_code=0,
        stdout_text=stdout,
        stderr_text="",
    )

    assert result.status == "FAILED"
    assert result.failure_kind == "FREE_MODEL_ATTESTATION_FAILED"
    assert result.retry_permitted is False


def test_opencode_quota_failure_is_classified_without_retry_permission(
    tmp_path: Path,
) -> None:
    request = _opencode_request(tmp_path)
    result = OpenCodeExecutionAdapter().interpret(
        request,
        exit_code=1,
        stdout_text="",
        stderr_text="rate limit quota exhausted",
    )
    assert result.status == "FAILED"
    assert result.failure_kind == "QUOTA_EXHAUSTED"
    assert result.retry_permitted is False
