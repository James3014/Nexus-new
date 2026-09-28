from __future__ import annotations

import json
import stat
from pathlib import Path

import pytest

from nexus.services.external_worker_runtime import (
    AccountBinding,
    ClineExecutionAdapter,
    CodexExecutionAdapter,
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


def _codex_request(
    tmp_path: Path,
    *,
    mode: str = "plan",
    auto_approve: bool = False,
    require_free: bool = False,
    thinking: str = "medium",
) -> WorkerRequest:
    return WorkerRequest(
        provider="codex",
        model="gpt-6-sol",
        prompt="codex test",
        cwd=str(tmp_path),
        mode=mode,
        auto_approve=auto_approve,
        timeout_seconds=60,
        require_free=require_free,
        thinking=thinking,
    )


def _fake_codex_binary(
    path: Path,
    *,
    login_status: str = "Logged in using ChatGPT",
    supports_no_daemon: bool = True,
    models: tuple[str, ...] = ("gpt-6-astra", "gpt-6-sol"),
) -> None:
    no_daemon_help = "      --no-daemon" if supports_no_daemon else ""
    model_json = json.dumps({"models": [{"slug": model} for model in models]})
    path.write_text(
        f"""#!/bin/sh
if [ "$1" = "--version" ]; then
  echo "codex-cli 0.157.1"
  exit 0
fi
if [ "$1" = "--help" ]; then
  echo "{no_daemon_help}"
  exit 0
fi
if [ "$1" = "login" ] && [ "$2" = "status" ]; then
  echo "{login_status}"
  exit 0
fi
if [ "$1" = "debug" ] && [ "$2" = "models" ]; then
  printf '%s\n' '{model_json}'
  exit 0
fi
exit 99
""",
        encoding="utf-8",
    )
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def test_codex_default_model_prefers_live_catalog_astra(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = tmp_path / "codex"
    _fake_codex_binary(fake)
    monkeypatch.setenv("NEXUS_CODEX_BIN", str(fake))
    monkeypatch.delenv("NEXUS_CODEX_MODEL", raising=False)

    assert CodexExecutionAdapter().default_model() == "gpt-6-astra"


def test_codex_default_or_explicit_model_must_exist_in_catalog(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = tmp_path / "codex"
    _fake_codex_binary(fake, models=("gpt-6-astra",))
    monkeypatch.setenv("NEXUS_CODEX_BIN", str(fake))
    monkeypatch.setenv("NEXUS_CODEX_MODEL", "gpt-6-sol")
    adapter = CodexExecutionAdapter()

    with pytest.raises(ExternalWorkerRuntimeError, match="CODEX_MODEL_UNAVAILABLE"):
        adapter.default_model()

    monkeypatch.delenv("NEXUS_CODEX_MODEL", raising=False)
    with pytest.raises(ExternalWorkerRuntimeError, match="CODEX_MODEL_UNAVAILABLE"):
        adapter.compile(
            _codex_request(tmp_path),
            binding=AccountBinding(provider="codex"),
        )


def test_codex_compile_requires_chatgpt_auth_and_strips_api_billing_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = tmp_path / "codex"
    _fake_codex_binary(fake)
    monkeypatch.setenv("NEXUS_CODEX_BIN", str(fake))
    monkeypatch.setenv("OPENAI_API_KEY", "must-not-delegate")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://example.invalid")
    monkeypatch.setenv("CODEX_ACCESS_TOKEN", "must-not-delegate")

    command = CodexExecutionAdapter().compile(
        _codex_request(tmp_path),
        binding=AccountBinding(provider="codex"),
    )

    argv = list(command.argv)
    assert argv[:5] == [str(fake.resolve()), "--no-daemon", "-a", "never", "exec"]
    assert "--json" in argv
    assert "--ephemeral" in argv
    assert "--ignore-user-config" in argv
    assert argv[argv.index("-m") + 1] == "gpt-6-sol"
    assert argv[argv.index("-s") + 1] == "read-only"
    assert argv[argv.index("-C") + 1] == str(tmp_path)
    assert 'model_reasoning_effort="medium"' in argv
    assert command.cli_version == "codex-cli 0.157.1"
    assert command.auth_mode == "chatgpt"
    assert "OPENAI_API_KEY" not in command.env
    assert "OPENAI_BASE_URL" not in command.env
    assert "CODEX_ACCESS_TOKEN" not in command.env


def test_codex_compile_omits_no_daemon_when_cli_does_not_support_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = tmp_path / "codex"
    _fake_codex_binary(fake, supports_no_daemon=False)
    monkeypatch.setenv("NEXUS_CODEX_BIN", str(fake))

    command = CodexExecutionAdapter().compile(
        _codex_request(tmp_path),
        binding=AccountBinding(provider="codex"),
    )

    assert "--no-daemon" not in command.argv
    assert list(command.argv)[:4] == [str(fake.resolve()), "-a", "never", "exec"]


def test_codex_compile_rejects_non_chatgpt_auth(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = tmp_path / "codex"
    _fake_codex_binary(fake, login_status="Logged in using API key")
    monkeypatch.setenv("NEXUS_CODEX_BIN", str(fake))

    with pytest.raises(ExternalWorkerRuntimeError, match="CODEX_CHATGPT_AUTH_REQUIRED"):
        CodexExecutionAdapter().compile(
            _codex_request(tmp_path),
            binding=AccountBinding(provider="codex"),
        )


def test_codex_compile_rejects_free_contract_and_unapproved_act(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = tmp_path / "codex"
    _fake_codex_binary(fake)
    monkeypatch.setenv("NEXUS_CODEX_BIN", str(fake))
    adapter = CodexExecutionAdapter()

    with pytest.raises(
        ExternalWorkerRuntimeError,
        match="CODEX_FREE_MODEL_CONTRACT_UNSUPPORTED",
    ):
        adapter.compile(
            _codex_request(tmp_path, require_free=True),
            binding=AccountBinding(provider="codex"),
        )

    with pytest.raises(
        ExternalWorkerRuntimeError,
        match="CODEX_ACT_REQUIRES_AUTO_APPROVE",
    ):
        adapter.compile(
            _codex_request(tmp_path, mode="act", auto_approve=False),
            binding=AccountBinding(provider="codex"),
        )


def test_codex_act_uses_workspace_write_without_bypass(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = tmp_path / "codex"
    _fake_codex_binary(fake)
    monkeypatch.setenv("NEXUS_CODEX_BIN", str(fake))

    command = CodexExecutionAdapter().compile(
        _codex_request(tmp_path, mode="act", auto_approve=True),
        binding=AccountBinding(provider="codex"),
    )
    argv = list(command.argv)
    assert argv[argv.index("-s") + 1] == "workspace-write"
    assert "--dangerously-bypass-approvals-and-sandbox" not in argv


def test_codex_success_uses_turn_receipt_and_counts_tool_events(tmp_path: Path) -> None:
    request = _codex_request(tmp_path)
    stdout = "\n".join([
        json.dumps({"type": "thread.started", "thread_id": "thread-1"}),
        json.dumps({"type": "turn.started"}),
        json.dumps({
            "type": "item.completed",
            "item": {
                "id": "item-0",
                "type": "command_execution",
                "command": "cat fixture.txt",
                "exit_code": 0,
                "status": "completed",
            },
        }),
        json.dumps({
            "type": "item.completed",
            "item": {
                "id": "item-1",
                "type": "agent_message",
                "text": "done",
            },
        }),
        json.dumps({
            "type": "turn.completed",
            "usage": {
                "input_tokens": 10,
                "output_tokens": 2,
            },
        }),
    ])
    result = CodexExecutionAdapter().interpret(
        request,
        exit_code=0,
        stdout_text=stdout,
        stderr_text="",
    )
    assert result.status == "COMPLETED"
    assert result.failure_kind is None
    assert result.observed_provider == "openai-chatgpt"
    assert result.observed_model is None
    assert (
        result.details["attestation"]
        == "catalog-listed+explicit-model-arg+chatgpt-login+turn-completed"
    )
    assert result.provider_session_id == "thread-1"
    assert result.tool_event_count == 1
    assert result.total_cost is None
    assert result.retry_permitted is False


def test_codex_incomplete_or_quota_failure_never_grants_retry(tmp_path: Path) -> None:
    request = _codex_request(tmp_path)
    incomplete = CodexExecutionAdapter().interpret(
        request,
        exit_code=0,
        stdout_text=json.dumps({"type": "thread.started", "thread_id": "thread-1"}),
        stderr_text="",
    )
    assert incomplete.status == "FAILED"
    assert incomplete.failure_kind == "UNKNOWN"
    assert incomplete.retry_permitted is False

    quota = CodexExecutionAdapter().interpret(
        request,
        exit_code=1,
        stdout_text="",
        stderr_text="usage limit reached",
    )
    assert quota.status == "FAILED"
    assert quota.failure_kind == "QUOTA_EXHAUSTED"
    assert quota.retry_permitted is False
