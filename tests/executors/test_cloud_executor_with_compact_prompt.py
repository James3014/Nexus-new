from __future__ import annotations

import pytest
from nexus.executors.cloud_executor_with_compact_prompt import (
    CloudCandidateResponse,
    run_with_compact_prompt,
)


def test_run_with_compact_prompt_stub_returns_invoked_false() -> None:
    response = run_with_compact_prompt("short prompt", {"target_file": "a.py"})
    assert response.invoked is False
    assert response.error == "stub mode not real cloud"


def test_run_with_compact_prompt_rejects_long_prompt() -> None:
    long_prompt = "x" * 501
    with pytest.raises(ValueError, match="500 max"):
        run_with_compact_prompt(long_prompt, {"target_file": "a.py"})


def test_run_with_compact_prompt_accepts_500_chars() -> None:
    prompt_500 = "a" * 500
    response = run_with_compact_prompt(prompt_500, {"target_file": "a.py"})
    assert response.invoked is False


def test_run_with_compact_prompt_no_target_file_warns(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level("WARNING"):
        run_with_compact_prompt("short", {"target_file": ""})
    assert "anchor.target_file is empty" in caplog.text


def test_cloud_candidate_response_frozen() -> None:
    response = CloudCandidateResponse(
        raw_output="",
        raw_output_hash="",
        model_name="stub",
        invoked=False,
        error="",
        latency_ms=0,
    )
    with pytest.raises(AttributeError):
        response.invoked = True
