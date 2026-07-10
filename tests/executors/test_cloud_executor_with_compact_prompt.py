from __future__ import annotations

import os

import pytest
from nexus.executors.cloud_executor_with_compact_prompt import (
    CloudCandidateResponse,
    RealCloudExecutor,
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


class TestRealCloudExecutor:
    def test_no_api_key_returns_stub(self) -> None:
        if "NEXUS_CLOUD_API_KEY" in os.environ:
            del os.environ["NEXUS_CLOUD_API_KEY"]
        executor = RealCloudExecutor()
        response = executor.run_with_compact_prompt("hello", {"target_file": "a.py"})
        assert response.invoked is False
        assert response.error == "no_api_key"

    def test_with_api_key_returns_mock(self) -> None:
        os.environ["NEXUS_CLOUD_API_KEY"] = "test_key"
        executor = RealCloudExecutor()
        response = executor.run_with_compact_prompt("hello", {"target_file": "a.py"})
        assert response.invoked is True
        assert len(response.raw_output_hash) == 64
        del os.environ["NEXUS_CLOUD_API_KEY"]

    def test_log_warning_no_key(self, caplog: pytest.LogCaptureFixture) -> None:
        if "NEXUS_CLOUD_API_KEY" in os.environ:
            del os.environ["NEXUS_CLOUD_API_KEY"]
        with caplog.at_level("WARNING"):
            RealCloudExecutor()
        assert "NEXUS_CLOUD_API_KEY not set" in caplog.text

    def test_existing_still_works(self) -> None:
        response = run_with_compact_prompt("short prompt", {"target_file": "a.py"})
        assert response.invoked is False

    def test_max_tokens_respected(self) -> None:
        os.environ["NEXUS_CLOUD_API_KEY"] = "test_key"
        executor = RealCloudExecutor()
        long_prompt = "x" * 501
        with pytest.raises(ValueError, match="500 max"):
            executor.run_with_compact_prompt(long_prompt, {"target_file": "a.py"})
        del os.environ["NEXUS_CLOUD_API_KEY"]
