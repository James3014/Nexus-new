from __future__ import annotations

from contextlib import contextmanager
import hashlib

import pytest

from scripts.bench.direct_provider_runner import (
    build_direct_provider_prompt,
    direct_prompt_attribution,
    direct_provider_for_mode,
    normalize_direct_provider_response,
    run_direct_provider_attempts,
)


class TaskView:
    id = "task-a"
    trial_index = 3
    task_desc = "Fix text normalization"


def _clock(values: list[float]):
    iterator = iter(values)
    return lambda: next(iterator)


def test_build_direct_provider_prompt_uses_stable_session_boundary_and_hashes():
    prompt = build_direct_provider_prompt(
        task=TaskView(),
        provider="gemini",
        source="def normalize(text):\n    return text\n",
        tests="def test_normalize():\n    assert normalize(' A ') == 'a'\n",
        env={"NEXUS_DIRECT_GEMINI_MODEL": "gemini-test-model"},
    )

    assert prompt.provider == "gemini"
    assert prompt.model_label == "gemini-test-model"
    assert prompt.prompt_actor == "gemini-test-model running without Nexus orchestration"
    assert "NEXUS_BENCH_SESSION_BOUNDARY_V1 task_id=task-a trial_index=3" in prompt.prompt
    assert "[CURRENT SOURCE]\ndef normalize(text):" in prompt.prompt
    assert "[CURRENT TESTS]\ndef test_normalize():" in prompt.prompt
    assert prompt.reset_boundary_hash == hashlib.sha256(prompt.reset_boundary.encode("utf-8")).hexdigest()
    assert prompt.prompt_sha256 == hashlib.sha256(prompt.prompt.encode("utf-8")).hexdigest()


def test_build_direct_provider_prompt_uses_provider_specific_model_fallbacks():
    codex_prompt = build_direct_provider_prompt(
        task=TaskView(),
        provider="codex",
        source="source",
        tests="tests",
        env={"NEXUS_CODEX_MODEL_NAME": "gpt-test"},
    )
    gemini_prompt = build_direct_provider_prompt(
        task=TaskView(),
        provider="gemini",
        source="source",
        tests="tests",
        env={"NEXUS_GEMINI_MODEL_NAME": "gemini-fallback"},
    )

    assert codex_prompt.model_label == "gpt-test"
    assert gemini_prompt.model_label == "gemini-fallback"


def test_direct_prompt_attribution_keeps_telemetry_buckets_stable():
    prompt = "system\nTASK\nsource\ntests"

    out = direct_prompt_attribution(
        prompt=prompt,
        task_desc="TASK",
        source="source",
        tests="tests",
        patch="patch",
        nexus_control_chars=7,
        governance_contract_chars=11,
    )

    assert out == {
        "prompt_system_instruction_chars": 0,
        "prompt_task_constraint_chars": len("TASK"),
        "prompt_source_payload_chars": len("source"),
        "prompt_test_payload_chars": len("tests"),
        "prompt_candidate_payload_chars": len("patch"),
        "prompt_nexus_control_chars": 7,
        "prompt_governance_contract_chars": 11,
    }


def test_direct_provider_for_mode_rejects_non_direct_modes():
    assert direct_provider_for_mode("gemini") == "gemini"
    assert direct_provider_for_mode("codex") == "codex"
    with pytest.raises(ValueError, match="direct provider mode"):
        direct_provider_for_mode("service")


def test_normalize_direct_provider_response_preserves_measured_tokens():
    result = normalize_direct_provider_response(
        out={
            "patch": "patched",
            "tokens_used": "123",
            "token_capture_status": "measured",
            "model_name": "gemini-test",
            "model_patch_generated": True,
        },
        raw="raw-patch",
        prompt="prompt",
    )

    assert result.model_calls == 1
    assert result.patch == "patched"
    assert result.gateway_error_category == ""
    assert result.model_name == "gemini-test"
    assert result.model_patch_generated is True
    assert result.total_tokens == 123
    assert result.token_capture_status == "measured"


def test_normalize_direct_provider_response_estimates_tokens_only_without_gateway_error():
    result = normalize_direct_provider_response(
        out={"patch": "patched", "tokens_used": 0, "token_capture_status": "missing_gateway_stats"},
        raw="",
        prompt="12345678",
    )
    timeout = normalize_direct_provider_response(
        out={"error_category": "timeout", "patch": "", "tokens_used": 0},
        raw="timeout",
        prompt="12345678",
    )

    assert result.total_tokens == 3
    assert result.token_capture_status == "estimated"
    assert result.model_calls == 1
    assert timeout.total_tokens == 0
    assert timeout.model_calls == 0
    assert timeout.gateway_error_category == "timeout"


def test_normalize_direct_provider_response_handles_binary_missing_as_no_model_call():
    result = normalize_direct_provider_response(
        out={"error_category": "binary_missing", "patch": "ignored", "tokens_used": "bad-int"},
        raw="raw-output",
        prompt="prompt",
    )

    assert result.model_calls == 0
    assert result.patch == "ignored"
    assert result.total_tokens == 0
    assert result.token_capture_status == "unknown"


def test_run_direct_provider_attempts_uses_socket_guard_and_remaining_timeout():
    calls = []
    guard_entries = 0

    @contextmanager
    def socket_guard():
        nonlocal guard_entries
        guard_entries += 1
        yield

    def ask(*, prompt: str, timeout_sec: int):
        calls.append((prompt, timeout_sec))
        return {"patch": "ok"}, "raw"

    result = run_direct_provider_attempts(
        provider="gemini",
        prompt="PROMPT",
        direct_ask=ask,
        remaining_timeout=lambda: 9,
        retry_limit=2,
        retryable_failure=lambda _out, _raw: (False, ""),
        socket_guard=socket_guard,
        clock=_clock([1.0, 1.2]),
    )

    assert calls == [("PROMPT", 9)]
    assert guard_entries == 1
    assert result.out == {"patch": "ok"}
    assert result.raw == "raw"
    assert result.retry_count == 0
    assert result.retry_wall_sec == 0.0
    assert result.retry_reasons == []
    assert result.retry_raw_tails == []


def test_run_direct_provider_attempts_records_retry_wall_and_raw_tail():
    responses = [
        ({"error_category": "cli_error"}, "bad raw"),
        ({"patch": "fixed"}, "good raw"),
    ]

    def ask(*, prompt: str, timeout_sec: int):
        return responses.pop(0)

    def retryable(_out, raw: str):
        return (raw == "bad raw", "cli_error_without_tokens")

    result = run_direct_provider_attempts(
        provider="gemini",
        prompt="PROMPT",
        direct_ask=ask,
        remaining_timeout=lambda: 5,
        retry_limit=1,
        retryable_failure=retryable,
        clock=_clock([10.0, 10.25, 10.3, 10.6]),
    )

    assert result.out == {"patch": "fixed"}
    assert result.raw == "good raw"
    assert result.retry_count == 1
    assert result.retry_wall_sec == 0.25
    assert result.retry_reasons == ["cli_error_without_tokens"]
    assert result.retry_raw_tails == ["bad raw"]


def test_run_direct_provider_attempts_resets_gemini_invalid_session_before_retry():
    responses = [
        ({"gemini_session_id": "session-a"}, "invalid session"),
        ({"patch": "fixed"}, "ok"),
    ]
    reset_calls: list[str] = []

    def ask(*, prompt: str, timeout_sec: int):
        return responses.pop(0)

    def retryable(_out, raw: str):
        return (raw == "invalid session", "gemini_invalid_session_identifier")

    result = run_direct_provider_attempts(
        provider="gemini",
        prompt="PROMPT",
        direct_ask=ask,
        remaining_timeout=lambda: 5,
        retry_limit=1,
        retryable_failure=retryable,
        reset_gemini_session=reset_calls.append,
        clock=_clock([1.0, 1.1, 1.2, 1.3]),
    )

    assert reset_calls == ["session-a"]
    assert result.raw == "ok"
