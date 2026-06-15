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
    """Hardened receipt verifier: schema + SHA-256 hash + evidence completeness."""
    import hashlib
    binary_path = Path("/Users/jameschen/Workspace/nexus/nexus-core-rs/target/release/nexus-core-rs")
    if not binary_path.exists():
        pytest.skip("Rust binary not found.")

    adapter = RustKernelAdapter(binary_path)

    # 1. Valid receipt with hash
    valid_payload = {
        "schema": "S2TStrictDecision.v1",
        "task_id": "ipc-test-001",
        "selected_candidate_id": "cand-1",
        "eval_metrics": {"pass_rate": 0.95, "total_tests": 10},
        "evidence_bundle": {"receipt_id": "r-001", "timestamp": "2026-06-15T00:00:00Z"}
    }
    # Compute hash via Python canonical JSON (sorted keys, no whitespace)
    import json as _json
    payload_for_hash = {k: v for k, v in valid_payload.items() if k != "receipt_hash"}
    canonical = _json.dumps(payload_for_hash, sort_keys=True, separators=(",", ":"))
    receipt_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    valid_payload["receipt_hash"] = receipt_hash

    result = adapter._call_kernel("VerifyReceipt", {
        "receipt_payload": valid_payload,
        "expected_schema": "S2TStrictDecision.v1",
        "expected_hash": receipt_hash
    })
    assert result["success"] is True
    assert result["payload"]["claimability_confirmed"] is True
    assert result["payload"]["hash_match"] is True
    assert result["payload"]["schema_match"] is True
    assert result["payload"]["evidence_complete"] is True

    # 2. Tampered payload → hash mismatch → claimability denied
    tampered_payload = valid_payload.copy()
    tampered_payload["selected_candidate_id"] = "TAMPERED"
    result = adapter._call_kernel("VerifyReceipt", {
        "receipt_payload": tampered_payload,
        "expected_schema": "S2TStrictDecision.v1",
        "expected_hash": receipt_hash  # original hash, won't match tampered
    })
    assert result["success"] is True
    assert result["payload"]["hash_match"] is False
    assert result["payload"]["claimability_confirmed"] is False
    assert result["payload"]["error_code"] == "HASH_MISMATCH"

    # 3. Schema mismatch → claimability denied
    result = adapter._call_kernel("VerifyReceipt", {
        "receipt_payload": valid_payload,
        "expected_schema": "WrongSchema.v1",
        "expected_hash": receipt_hash
    })
    assert result["success"] is True
    assert result["payload"]["schema_match"] is False
    assert result["payload"]["claimability_confirmed"] is False
    assert result["payload"]["error_code"] == "SCHEMA_MISMATCH"

    # 4. Missing eval_metrics → evidence incomplete → claimability denied
    incomplete_payload = {
        "schema": "S2TStrictDecision.v1",
        "task_id": "ipc-test-002"
        # no eval_metrics, no evidence_bundle
    }
    result = adapter._call_kernel("VerifyReceipt", {
        "receipt_payload": incomplete_payload,
        "expected_schema": "S2TStrictDecision.v1",
        "expected_hash": "dummy"
    })
    assert result["success"] is True
    assert result["payload"]["evidence_complete"] is False
    assert result["payload"]["claimability_confirmed"] is False

    # 5. PUBLIC CLAIM CANNOT BYPASS VERIFIER
    # Simulate: agent tries to claim "solved" with a fake receipt
    fake_receipt = {
        "schema": "S2TStrictDecision.v1",
        "task_id": "attacker-001",
        "selected_candidate_id": "fake-cand",
        "eval_metrics": {"pass_rate": 1.0},  # fake perfect score
        "evidence_bundle": {"receipt_id": "fake-r"}
    }
    # No valid hash provided
    result = adapter._call_kernel("VerifyReceipt", {
        "receipt_payload": fake_receipt,
        "expected_schema": "S2TStrictDecision.v1",
        "expected_hash": "0000000000000000000000000000000000000000000000000000000000000000"
    })
    # Even with perfect-looking metrics, hash mismatch prevents claim
    assert result["payload"]["claimability_confirmed"] is False
    assert result["payload"]["hash_match"] is False

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
