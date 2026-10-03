"""Unit tests for Mode B — Local Worker execution substrate."""

from __future__ import annotations

from pathlib import Path

from nexus.services.m5_local.contracts import (
    LOCAL_MODEL_IDENTITY_MISMATCH,
    LOCAL_ROLE_NOT_QUALIFIED,
    LOCAL_TIMEOUT,
    LocalWorkerRequest,
)
from nexus.services.m5_local.host_inventory import ModelInventoryItem
from nexus.services.m5_local.runtimes import (
    LocalInferenceRuntime,
    MockLocalRuntime,
    RuntimeExecutionResult,
)
from nexus.services.m5_local.worker_adapter import LocalWorkerService


def test_worker_write_denied_without_authorities(tmp_path: Path):
    svc = LocalWorkerService(runtime=MockLocalRuntime())
    # write_permitted=True but missing claim_receipt_ref and conflict_token
    req = LocalWorkerRequest(
        task_id="t1",
        attempt_id="att-1",
        operation_id="op-1",
        repo_path=str(tmp_path),
        task_instruction="edit file",
        requested_runtime="mock",
        requested_model="test-model",
        write_permitted=True,  # Request write
        claim_receipt_ref=None,  # Missing #129
        conflict_admission_token=None,  # Missing #98
        workspace_root=str(tmp_path),
    )
    res = svc.execute(req)
    assert res.status == "REJECTED_DENIED"
    assert res.escalation_reason == LOCAL_ROLE_NOT_QUALIFIED
    assert not res.write_performed


def test_worker_write_denied_without_isolated_workspace(tmp_path: Path):
    svc = LocalWorkerService(runtime=MockLocalRuntime())
    req = LocalWorkerRequest(
        task_id="t2",
        attempt_id="att-2",
        operation_id="op-2",
        repo_path=str(tmp_path),
        task_instruction="edit file",
        requested_runtime="mock",
        requested_model="test-model",
        write_permitted=True,
        claim_receipt_ref="urn:nexus:claim:test-claim-1",
        conflict_admission_token="token-conflict-1",
        workspace_root="/nonexistent/workspace/dir",
    )
    res = svc.execute(req)
    assert res.status == "REJECTED_DENIED"
    assert not res.write_performed


def test_worker_read_only_execution_substrate(tmp_path: Path):
    mock_rt = MockLocalRuntime(output_text="Execution complete", observed_model="test-model")
    svc = LocalWorkerService(runtime=mock_rt)
    req = LocalWorkerRequest(
        task_id="t3",
        attempt_id="att-3",
        operation_id="op-3",
        repo_path=str(tmp_path),
        task_instruction="inspect state",
        requested_runtime="mock",
        requested_model="test-model",
        write_permitted=False,
    )
    res = svc.execute(req)
    assert res.status == "COMPLETED"
    assert res.stdout == "Execution complete"
    assert res.exit_code == 0
    assert not res.write_performed


def test_worker_timeout():
    mock_rt = MockLocalRuntime(simulate_timeout=True)
    svc = LocalWorkerService(runtime=mock_rt)
    req = LocalWorkerRequest(
        task_id="t4",
        attempt_id="att-4",
        operation_id="op-4",
        repo_path="/tmp",
        task_instruction="long computation",
        requested_runtime="mock",
        requested_model="test-model",
        timeout_seconds=0.1,
    )
    res = svc.execute(req)
    assert res.status == "TIMEOUT"
    assert res.escalation_reason == LOCAL_TIMEOUT


class RealRuntimeWitness(LocalInferenceRuntime):
    """Witness runtime simulating real physical execution output."""

    def __init__(
        self,
        *,
        observed_model: str,
        physical_model_path: str,
        physical_model_size_bytes: int,
        output_text: str = "Real-style execution output",
    ):
        self._observed_model = observed_model
        self._physical_model_path = physical_model_path
        self._physical_model_size_bytes = physical_model_size_bytes
        self._output_text = output_text

    def is_available(self) -> bool:
        return True

    def run_inference(
        self,
        *,
        model_id: str,
        prompt: str,
        max_tokens: int = 512,
        temperature: float = 0.0,
        timeout_seconds: float = 30.0,
        context_limit: int | None = None,
    ) -> RuntimeExecutionResult:
        return RuntimeExecutionResult(
            requested_runtime="llama.cpp",
            observed_runtime="llama.cpp",
            requested_model=model_id,
            observed_model=self._observed_model,
            physical_model_path=self._physical_model_path,
            physical_model_size_bytes=self._physical_model_size_bytes,
            output_text=self._output_text,
            stdout=self._output_text,
            stderr="",
            exit_code=0,
            elapsed_ms=100,
            rss_bytes=1024 * 1024 * 50,
        )


def test_worker_physical_identity_binding_success(tmp_path: Path):
    """Section 8: Real-runtime-style result with valid physical identity binding completes."""
    model_file = tmp_path / "test-model.gguf"
    model_file.write_bytes(b"x" * 104)

    item = ModelInventoryItem(
        model_id="test-model",
        file_path=str(model_file),
        size_bytes=104,
        format="GGUF",
        context_limit=4096,
        classification="AVAILABLE_EXACT",
        runtime_runnable=True,
        role_qualifications={},
    )

    rt = RealRuntimeWitness(
        observed_model="test-model.gguf:104B",
        physical_model_path=str(model_file),
        physical_model_size_bytes=104,
    )
    svc = LocalWorkerService(runtime=rt, models={"test-model": item})
    req = LocalWorkerRequest(
        task_id="t-phys-success",
        attempt_id="att-phys-1",
        operation_id="op-phys-1",
        repo_path=str(tmp_path),
        task_instruction="real runtime execution test",
        requested_runtime="llama.cpp",
        requested_model="test-model",
        write_permitted=False,
    )
    res = svc.execute(req)

    assert res.status == "COMPLETED"
    assert res.exit_code == 0
    assert not res.write_performed
    assert res.requested_model == "test-model"
    assert res.observed_model == "test-model.gguf:104B"
    assert res.stdout == "Real-style execution output"


def test_worker_physical_identity_mismatch_wrong_path(tmp_path: Path):
    """Section 8 negative control: Wrong physical path fails with LOCAL_MODEL_IDENTITY_MISMATCH."""
    file_a = tmp_path / "A.gguf"
    file_a.write_bytes(b"a" * 104)
    file_b = tmp_path / "B.gguf"
    file_b.write_bytes(b"b" * 104)

    item = ModelInventoryItem(
        model_id="test-model",
        file_path=str(file_a),
        size_bytes=104,
        format="GGUF",
        context_limit=4096,
        classification="AVAILABLE_EXACT",
        runtime_runnable=True,
        role_qualifications={},
    )

    # Runtime executed B.gguf instead of expected A.gguf
    rt = RealRuntimeWitness(
        observed_model="B.gguf:104B",
        physical_model_path=str(file_b),
        physical_model_size_bytes=104,
    )
    svc = LocalWorkerService(runtime=rt, models={"test-model": item})
    req = LocalWorkerRequest(
        task_id="t-phys-wrong-path",
        attempt_id="att-phys-2",
        operation_id="op-phys-2",
        repo_path=str(tmp_path),
        task_instruction="path mismatch test",
        requested_runtime="llama.cpp",
        requested_model="test-model",
        write_permitted=False,
    )
    res = svc.execute(req)

    assert res.status == "FAILED"
    assert res.escalation_reason == LOCAL_MODEL_IDENTITY_MISMATCH
    assert "mismatch" in res.stderr.lower()


def test_worker_physical_identity_mismatch_wrong_size(tmp_path: Path):
    """Section 8 negative control: Wrong byte size fails with LOCAL_MODEL_IDENTITY_MISMATCH."""
    model_file = tmp_path / "test-model.gguf"
    model_file.write_bytes(b"x" * 104)

    item = ModelInventoryItem(
        model_id="test-model",
        file_path=str(model_file),
        size_bytes=104,
        format="GGUF",
        context_limit=4096,
        classification="AVAILABLE_EXACT",
        runtime_runnable=True,
        role_qualifications={},
    )

    # Observed byte count 105 instead of expected 104
    rt = RealRuntimeWitness(
        observed_model="test-model.gguf:104B",
        physical_model_path=str(model_file),
        physical_model_size_bytes=105,
    )
    svc = LocalWorkerService(runtime=rt, models={"test-model": item})
    req = LocalWorkerRequest(
        task_id="t-phys-wrong-size",
        attempt_id="att-phys-3",
        operation_id="op-phys-3",
        repo_path=str(tmp_path),
        task_instruction="size mismatch test",
        requested_runtime="llama.cpp",
        requested_model="test-model",
        write_permitted=False,
    )
    res = svc.execute(req)

    assert res.status == "FAILED"
    assert res.escalation_reason == LOCAL_MODEL_IDENTITY_MISMATCH
    assert "mismatch" in res.stderr.lower()


def test_worker_physical_identity_unknown_fails_closed(tmp_path: Path):
    """Section 8 negative control: UNKNOWN identity fails closed."""
    model_file = tmp_path / "test-model.gguf"
    model_file.write_bytes(b"x" * 104)

    item = ModelInventoryItem(
        model_id="test-model",
        file_path=str(model_file),
        size_bytes=104,
        format="GGUF",
        context_limit=4096,
        classification="AVAILABLE_EXACT",
        runtime_runnable=True,
        role_qualifications={},
    )

    rt = RealRuntimeWitness(
        observed_model="UNKNOWN",
        physical_model_path=str(model_file),
        physical_model_size_bytes=104,
    )
    svc = LocalWorkerService(runtime=rt, models={"test-model": item})
    req = LocalWorkerRequest(
        task_id="t-phys-unknown",
        attempt_id="att-phys-4",
        operation_id="op-phys-4",
        repo_path=str(tmp_path),
        task_instruction="unknown identity test",
        requested_runtime="llama.cpp",
        requested_model="test-model",
        write_permitted=False,
    )
    res = svc.execute(req)

    assert res.status == "FAILED"
    assert res.escalation_reason == LOCAL_MODEL_IDENTITY_MISMATCH
    assert "unknown" in res.stderr.lower()
