import pytest
from pathlib import Path
from nexus.bridge.rust_kernel import RustKernelAdapter

def test_rust_kernel_smoke_echo():
    binary_path = Path("/Users/jameschen/Workspace/nexus/nexus-core-rs/target/release/nexus-core-rs")
    if not binary_path.exists():
        pytest.skip("Rust binary not found. Please run 'cargo build --release' in nexus-core-rs.")

    adapter = RustKernelAdapter(binary_path)
    result = adapter.smoke_test("Hello Nexus")
    
    assert result["success"] is True
    assert result["payload"]["echo"] == "Hello Nexus"
    assert "Rust Kernel Active" in result["payload"]["status"]

def test_rust_kernel_flow_decision_stub():
    binary_path = Path("/Users/jameschen/Workspace/nexus/nexus-core-rs/target/release/nexus-core-rs")
    if not binary_path.exists():
        pytest.skip("Rust binary not found.")

    adapter = RustKernelAdapter(binary_path)
    result = adapter._call_kernel("ValidateTransition", {"current": "INTAKE", "next": "PLAN"})
    
    assert result["success"] is True
    assert result["payload"]["is_valid"] is True

def test_rust_kernel_ast_scan_logic():
    binary_path = Path("/Users/jameschen/Workspace/nexus/nexus-core-rs/target/release/nexus-core-rs")
    if not binary_path.exists():
        pytest.skip("Rust binary not found.")

    adapter = RustKernelAdapter(binary_path)
    
    # Create a temp file
    temp_file = Path("temp_test.py")
    temp_file.write_text("class MyClass:\n    def my_method(self):\n        pass")
    
    rules = [
        {"name": "class_count", "pattern": "class"},
        {"name": "def_count", "pattern": "def"}
    ]
    
    try:
        result = adapter._call_kernel("AstScan", {"path": str(temp_file.absolute()), "rules": rules})
        assert result["success"] is True
        assert result["payload"]["matches"]["class_count"] == 1
        assert result["payload"]["matches"]["def_count"] == 1
        assert "wall_time_ms" in result["payload"]
    finally:
        if temp_file.exists():
            temp_file.unlink()

def test_rust_kernel_receipt_verification():
    binary_path = Path("/Users/jameschen/Workspace/nexus/nexus-core-rs/target/release/nexus-core-rs")
    if not binary_path.exists():
        pytest.skip("Rust binary not found.")

    adapter = RustKernelAdapter(binary_path)
    
    # 1. Valid receipt
    valid_payload = {
        "schema": "nexus.local_heal.repair_receipt.v1",
        "eval_metrics": {"status": "success"}
    }
    result = adapter._call_kernel("VerifyReceipt", {
        "receipt_payload": valid_payload,
        "expected_schema": "nexus.local_heal.repair_receipt.v1"
    })
    assert result["success"] is True
    assert result["payload"]["is_valid"] is True
    assert result["payload"]["claimability_confirmed"] is True

    # 2. Schema mismatch
    result = adapter._call_kernel("VerifyReceipt", {
        "receipt_payload": valid_payload,
        "expected_schema": "wrong_schema"
    })
    assert result["success"] is True
    assert result["payload"]["is_valid"] is False
    assert "SCHEMA_MISMATCH" in result["payload"]["error_message"]

def test_rust_kernel_flow_transition_validation():
    binary_path = Path("/Users/jameschen/Workspace/nexus/nexus-core-rs/target/release/nexus-core-rs")
    if not binary_path.exists():
        pytest.skip("Rust binary not found.")

    adapter = RustKernelAdapter(binary_path)
    
    # 1. Valid transition
    result = adapter._call_kernel("ValidateTransition", {"current": "INTAKE", "next": "PLAN"})
    assert result["success"] is True
    assert result["payload"]["is_valid"] is True

    # 2. Invalid transition
    result = adapter._call_kernel("ValidateTransition", {"current": "INTAKE", "next": "EXECUTE"})
    assert result["success"] is True
    assert result["payload"]["is_valid"] is False

def test_rust_kernel_pattern_matching():
    binary_path = Path("/Users/jameschen/Workspace/nexus/nexus-core-rs/target/release/nexus-core-rs")
    if not binary_path.exists():
        pytest.skip("Rust binary not found.")

    adapter = RustKernelAdapter(binary_path)
    
    content = "The quick brown fox jumps over the lazy dog."
    pattern = "quick brown"
    
    result = adapter._call_kernel("MatchPattern", {
        "content": content,
        "pattern": pattern,
        "is_regex": False
    })
    
    assert result["success"] is True
    assert result["payload"]["found"] is True
    assert result["payload"]["start_idx"] == 4
    assert result["payload"]["end_idx"] == 15

def test_rust_kernel_replay_verification():
    adapter = RustKernelAdapter(Path("/Users/jameschen/Workspace/nexus/nexus-core-rs/target/release/nexus-core-rs"))
    
    result = adapter._call_kernel("VerifyReplay", {
        "task_id": "t1",
        "original_result": "output A",
        "replay_output": "output A"
    })
    assert result["success"] is True
    assert result["payload"]["identical"] is True

    result = adapter._call_kernel("VerifyReplay", {
        "task_id": "t1",
        "original_result": "output A",
        "replay_output": "output B"
    })
    assert result["payload"]["identical"] is False

def test_rust_kernel_slice_validation():
    adapter = RustKernelAdapter(Path("/Users/jameschen/Workspace/nexus/nexus-core-rs/target/release/nexus-core-rs"))
    
    # 1. Horizontal slice detected
    result = adapter._call_kernel("ValidateSlice", {"outline_text": "Finish all API endpoints first."})
    assert result["payload"]["is_valid"] is False
    assert "HORIZONTAL_SLICE_DETECTED" in result["payload"]["error_code"]

    # 2. Valid vertical slice
    result = adapter._call_kernel("ValidateSlice", {"outline_text": "Implement API + Service slice. Verify with pytest."})
    assert result["payload"]["is_valid"] is True

def test_rust_kernel_contamination_check():
    adapter = RustKernelAdapter(Path("/Users/jameschen/Workspace/nexus/nexus-core-rs/target/release/nexus-core-rs"))
    
    # 1. Contamination detected
    result = adapter._call_kernel("CheckContamination", {"content": "We should fix the bug.", "level": "L2"})
    assert result["payload"]["passed"] is False
    assert "fix" in result["payload"]["detected_terms"]

    # 2. Facts only pass
    result = adapter._call_kernel("CheckContamination", {"content": "Observed a timeout in auth service.", "level": "L2"})
    assert result["payload"]["passed"] is True
