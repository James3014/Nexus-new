from __future__ import annotations

import json

from nexus.services.external_worker_runtime import (
    ClaudeExecutionAdapter,
    WorkerRequest,
)

SUCCESS_STDOUT = json.dumps({
    "type": "result",
    "subtype": "success",
    "is_error": False,
    "session_id": "s1",
    "total_cost_usd": 0.01,
})


def _make_request() -> WorkerRequest:
    return WorkerRequest(
        provider="claude",
        model="sonnet",
        prompt="p",
        cwd=".",
        mode="plan",
        auto_approve=False,
        timeout_seconds=60,
        require_free=False,
        thinking="none",
    )


def test_exit_code_0_gives_completed():
    adapter = ClaudeExecutionAdapter()
    outcome = adapter.interpret(
        _make_request(),
        exit_code=0,
        stdout_text=SUCCESS_STDOUT,
        stderr_text="",
    )
    assert outcome.status == "COMPLETED"


def test_exit_code_1_does_not_give_completed_and_gives_outcome_unknown():
    adapter = ClaudeExecutionAdapter()
    outcome = adapter.interpret(
        _make_request(),
        exit_code=1,
        stdout_text=SUCCESS_STDOUT,
        stderr_text="",
    )
    assert outcome.status != "COMPLETED"
    assert outcome.status == "OUTCOME_UNKNOWN"
    assert outcome.retry_permitted is False
    assert outcome.details["exit_code"] == 1
    assert outcome.details.get("unknown_outcome") is True


def test_exit_code_137_gives_outcome_unknown():
    adapter = ClaudeExecutionAdapter()
    outcome = adapter.interpret(
        _make_request(),
        exit_code=137,
        stdout_text=SUCCESS_STDOUT,
        stderr_text="",
    )
    assert outcome.status != "COMPLETED"
    assert outcome.status == "OUTCOME_UNKNOWN"
    assert outcome.retry_permitted is False
    assert outcome.details["exit_code"] == 137
    assert outcome.details.get("unknown_outcome") is True


def test_empty_stdout_with_exit_code_0_gives_outcome_unknown():
    adapter = ClaudeExecutionAdapter()
    outcome = adapter.interpret(
        _make_request(),
        exit_code=0,
        stdout_text="",
        stderr_text="",
    )
    assert outcome.status == "OUTCOME_UNKNOWN"
