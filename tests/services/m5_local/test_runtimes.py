"""Unit tests for local runtime adapters (llama.cpp, MLX, mock)."""

from __future__ import annotations

from nexus.services.m5_local.contracts import (
    LOCAL_RUNTIME_UNAVAILABLE,
    LOCAL_TIMEOUT,
)
from nexus.services.m5_local.runtimes import (
    LlamaCppRuntime,
    MockLocalRuntime,
)


def test_mock_runtime_success():
    rt = MockLocalRuntime(output_text="Test response", observed_model="test-model")
    res = rt.run_inference(model_id="test-model", prompt="Hello")
    assert res.output_text == "Test response"
    assert res.observed_model == "test-model"
    assert res.exit_code == 0
    assert not res.timed_out
    assert res.error is None


def test_mock_runtime_timeout():
    rt = MockLocalRuntime(simulate_timeout=True)
    res = rt.run_inference(model_id="test-model", prompt="Hello", timeout_seconds=1.5)
    assert res.timed_out is True
    assert res.escalation_reason == LOCAL_TIMEOUT
    assert res.exit_code is None


def test_mock_runtime_cancel():
    rt = MockLocalRuntime(simulate_cancel=True)
    res = rt.run_inference(model_id="test-model", prompt="Hello")
    assert res.cancelled is True
    assert res.exit_code == -15


def test_mock_runtime_error():
    rt = MockLocalRuntime(simulate_error="Custom simulation error", simulate_exit_code=2)
    res = rt.run_inference(model_id="test-model", prompt="Hello")
    assert res.exit_code == 2
    assert "Custom simulation error" in res.stderr


def test_mock_runtime_model_mismatch():
    rt = MockLocalRuntime(simulate_model_mismatch=True)
    res = rt.run_inference(model_id="requested-foo", prompt="Hello")
    assert res.requested_model == "requested-foo"
    assert res.observed_model == "mismatch-model-detected"
    assert res.requested_model != res.observed_model


def test_llamacpp_missing_executable():
    rt = LlamaCppRuntime(executable_path="/nonexistent/llama-cli")
    res = rt.run_inference(model_id="qwen36-35b-q4", prompt="Hello")
    assert res.exit_code == -1
    assert res.escalation_reason == LOCAL_RUNTIME_UNAVAILABLE


def test_llamacpp_missing_model():
    rt = LlamaCppRuntime()
    res = rt.run_inference(model_id="nonexistent-model-xyz", prompt="Hello")
    assert res.exit_code == -1
    assert res.escalation_reason == LOCAL_RUNTIME_UNAVAILABLE


def test_mlx_runtime_reports_model_not_bound():
    from nexus.services.m5_local.runtimes import MlxRuntime

    rt = MlxRuntime()
    res = rt.run_inference(model_id="any-model", prompt="Hello")
    assert res.observed_model == "UNKNOWN"
    assert res.escalation_reason == LOCAL_RUNTIME_UNAVAILABLE
    assert "MLX" in (res.error or "")


def test_llamacpp_attestation_fields(monkeypatch, tmp_path):
    import subprocess
    from unittest.mock import MagicMock

    from nexus.services.m5_local.host_inventory import ModelInventoryItem

    # Create dummy model file
    dummy_model = tmp_path / "test-model.gguf"
    dummy_model.write_bytes(b"GGUF" + b"\x00" * 100)

    monkeypatch.setattr(
        "nexus.services.m5_local.runtimes.inspect_models",
        lambda: {
            "test-model": ModelInventoryItem(
                model_id="test-model",
                file_path=str(dummy_model),
                size_bytes=104,
                format="GGUF",
                context_limit=4096,
                classification="AVAILABLE_EXACT",
                runtime_runnable=True,
                role_qualifications={},
            )
        },
    )

    fake_proc = MagicMock()
    fake_proc.returncode = 0
    fake_proc.stdout = "generated tokens"
    fake_proc.stderr = ""
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: fake_proc)

    rt = LlamaCppRuntime(executable_path="/bin/echo")
    res = rt.run_inference(model_id="test-model", prompt="hi")
    assert res.exit_code == 0
    assert res.physical_model_path == str(dummy_model)
    assert res.physical_model_size_bytes == 104
    assert res.observed_model == "test-model.gguf:104B"
    assert res.runtime_command is not None
    assert "/bin/echo" in res.runtime_command
