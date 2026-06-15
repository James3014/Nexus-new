import os
import json
import pytest
from pathlib import Path
from nexus.bridge.rust_kernel import RustKernelAdapter

# Python reference implementation (must match Rust exactly)
LEGAL_TRANSITIONS = {
    "INTAKE": {"CLARIFY", "OUTLINE", "PLAN"},
    "CLARIFY": {"OUTLINE", "RESEARCH", "ESCALATE"},
    "OUTLINE": {"PLAN", "RESEARCH", "REPLAN"},
    "RESEARCH": {"DESIGN", "OUTLINE", "PLAN"},
    "DESIGN": {"PLAN", "REPLAN"},
    "PLAN": {"EXECUTE", "REPLAN", "HUMAN_REVIEW"},
    "EXECUTE": {"VERIFY", "ESCALATE", "BLOCKED_BUDGET", "BLOCKED_POLICY"},
    "VERIFY": {"CLOSE", "REPLAN", "ESCALATE"},
    "CLOSE": set(),  # Terminal
    "REPLAN": {"PLAN", "ESCALATE", "BLOCKED_BUDGET", "BLOCKED_POLICY"},
    "ESCALATE": {"HUMAN_REVIEW", "BLOCKED_POLICY", "INTAKE"},
    "HUMAN_REVIEW": {"PLAN", "EXECUTE", "CLOSE", "BLOCKED_POLICY"},
    "BLOCKED_BUDGET": {"HUMAN_REVIEW", "ESCALATE"},
    "BLOCKED_POLICY": {"HUMAN_REVIEW", "ESCALATE"},
}

ALL_STATES = list(LEGAL_TRANSITIONS.keys())

def python_validate_transition(current: str, next_state: str) -> bool:
    """Python reference: fail-closed, same as Rust."""
    if current == next_state:
        return True
    return next_state in LEGAL_TRANSITIONS.get(current, set())

BINARY_PATH = Path("/Users/jameschen/Workspace/nexus/nexus-core-rs/target/release/nexus-core-rs")

@pytest.fixture
def adapter():
    if not BINARY_PATH.exists():
        pytest.skip("Rust binary not found. Run 'cargo build --release' in nexus-core-rs.")
    return RustKernelAdapter(BINARY_PATH)

@pytest.fixture
def mismatch_ledger(tmp_path):
    return tmp_path / "rust_mismatch_ledger.jsonl"

def test_dual_run_all_transitions(adapter, mismatch_ledger):
    """Exhaustive dual-run: all 14×14=196 transitions, mismatch rate must be 0."""
    mismatches = []

    for current in ALL_STATES:
        for next_state in ALL_STATES:
            # Python result
            py_result = python_validate_transition(current, next_state)

            # Rust result via IPC
            rust_response = adapter._call_kernel("ValidateTransition", {
                "current": current,
                "next": next_state
            })
            assert rust_response["success"], f"Rust kernel failed: {rust_response}"
            rust_result = rust_response["payload"]["is_valid"]

            if py_result != rust_result:
                mismatches.append({
                    "module": "flow_machine",
                    "input": f"{current} -> {next_state}",
                    "python_output": py_result,
                    "rust_output": rust_result,
                    "diff_reason": "OUTPUT_VALUE_MISMATCH"
                })

    # Write mismatch ledger if any
    if mismatches:
        with open(mismatch_ledger, "w") as f:
            for m in mismatches:
                f.write(json.dumps(m) + "\n")

    assert len(mismatches) == 0, (
        f"Dual-run mismatch rate > 0 ({len(mismatches)} mismatches). "
        f"Ledger: {mismatch_ledger}"
    )

def test_dual_run_legal_counts_match(adapter):
    """Verify legal transition counts match Python reference."""
    for state in ALL_STATES:
        py_count = len(LEGAL_TRANSITIONS.get(state, set()))
        # Rust returns legal transitions (excluding self-loop)
        rust_response = adapter._call_kernel("ValidateTransition", {
            "current": state,
            "next": state  # self-loop = always valid
        })
        assert rust_response["success"]
        # Count all valid transitions for this state
        rust_legal = sum(
            1 for s in ALL_STATES
            if s != state and adapter._call_kernel("ValidateTransition", {
                "current": state, "next": s
            })["payload"]["is_valid"]
        )
        assert rust_legal == py_count, (
            f"State {state}: Python has {py_count} legal transitions, Rust has {rust_legal}"
        )

def test_fail_closed_on_unknown_transition(adapter):
    """Verify fail-closed: any undefined transition returns false."""
    # INTAKE -> EXECUTE is not in LEGAL_TRANSITIONS
    result = adapter._call_kernel("ValidateTransition", {
        "current": "INTAKE", "next": "EXECUTE"
    })
    assert result["payload"]["is_valid"] is False

    # CLOSE -> anything should fail (terminal state)
    for target in ["INTAKE", "PLAN", "EXECUTE", "VERIFY"]:
        result = adapter._call_kernel("ValidateTransition", {
            "current": "CLOSE", "next": target
        })
        assert result["payload"]["is_valid"] is False

def test_flow_transition_ipc_basic(adapter):
    """Basic IPC test for flow transitions."""
    # Valid: INTAKE -> PLAN
    result = adapter._call_kernel("ValidateTransition", {
        "current": "INTAKE", "next": "PLAN"
    })
    assert result["success"] is True
    assert result["payload"]["is_valid"] is True

    # Invalid: INTAKE -> EXECUTE
    result = adapter._call_kernel("ValidateTransition", {
        "current": "INTAKE", "next": "EXECUTE"
    })
    assert result["success"] is True
    assert result["payload"]["is_valid"] is False
