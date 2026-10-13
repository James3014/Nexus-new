import json
from pathlib import Path

from nexus.core.belief_contracts import CapabilityReceipt as CoreReceipt
from nexus.core.policy_drift import DualGateVerifier
from nexus.engine.capability_contracts import CapabilityReceipt as EngineReceipt


def test_evidence_replay_artifact_generation(tmp_path):
    """
    TDD Phase (RED): Verify DualGateVerifier correctly generates a physical
    replay artifact containing repro_command, timeout_sec, cwd, and pass_fail_evidence.
    """
    verifier = DualGateVerifier()

    # DualGateVerifier writes the replay artifact to <evidence dir>/../.nexus/reports when that
    # directory exists. Keep everything under tmp_path so the test never touches a developer-specific
    # or repo path (the verifier otherwise falls back to a hardcoded /Users/jameschen/... directory).
    evidence_dir = tmp_path / "evidence"
    evidence_dir.mkdir()
    (tmp_path / ".nexus" / "reports").mkdir(parents=True)
    workspace_cwd = str(tmp_path / "workspace")

    # We write a dummy mock log file to act as physical evidence (Gate 1)
    mock_path = evidence_dir / "mock_evidence.log"
    mock_path.write_text("Execution success! AST optimized. Elapsed: 120ms.", encoding="utf-8")

    # Run verify_receipt with a mock intent
    res = verifier.verify_receipt(
        evidence_path=mock_path,
        intent="AST optimized",
        repro_command="uv run pytest tests/test_ast.py",
        timeout_sec=30,
        cwd=workspace_cwd,
    )

    # Verify the returned dict structure
    assert res["physical_gate_passed"] is True
    assert res["semantic_gate_passed"] is True
    assert res["evidence_bundle_referenced"] is True
    assert res["contract_repro_valid"] is True
    assert "replay_artifact_path" in res

    replay_path = Path(res["replay_artifact_path"])
    assert replay_path.exists()
    assert replay_path.resolve().is_relative_to(tmp_path.resolve())

    # Verify the physical replay contract via DualGateVerifier
    assert verifier.validate_replay_contract(replay_path) is True

    # Verify the physical replay artifact contents
    replay_data = json.loads(replay_path.read_text(encoding="utf-8"))
    assert replay_data["repro_command"] == "uv run pytest tests/test_ast.py"
    assert replay_data["timeout_sec"] == 30
    assert replay_data["cwd"] == workspace_cwd
    assert replay_data["pass_fail_evidence"]["physical_gate_passed"] is True
    assert replay_data["pass_fail_evidence"]["semantic_gate_passed"] is True


def test_receipt_telemetry_and_claimability():
    """
    TDD Phase (RED): Verify CapabilityReceipt restricts is_claimable and
    public_claim_safe unless full telemetries (wall, token, cost, overhead) are present.
    """
    # 1. CoreReceipt eligibility check
    rcpt_incomplete = CoreReceipt(
        capability_name="test_cap",
        selected=True,
        invoked=True,
        evidence_id="ev_123",
        gate_passed=True,
        telemetries={"wall_time_ms": 0},  # incomplete telemetry
    )
    # incomplete telemetries should mark is_claimable as False
    assert rcpt_incomplete.is_claimable is False

    rcpt_complete = CoreReceipt(
        capability_name="test_cap",
        selected=True,
        invoked=True,
        evidence_id="ev_123",
        gate_passed=True,
        telemetries={
            "wall_time_ms": 1200,
            "token_usage": 1420,
            "provider_costs": 0.05,
            "overhead_ms": 150,
        },
    )
    assert rcpt_complete.is_claimable is True

    # 2. EngineReceipt public_claim_safe check
    engine_incomplete = EngineReceipt(
        name="test_cap",
        selected=True,
        invoked=True,
        evidence_present=True,
        gate_passed=True,
        outcome_contributed=True,
        telemetries={},  # Empty telemetries
    )
    assert engine_incomplete.public_claim_safe is False

    engine_complete = EngineReceipt(
        name="test_cap",
        selected=True,
        invoked=True,
        evidence_present=True,
        gate_passed=True,
        outcome_contributed=True,
        telemetries={
            "wall_time_ms": 1200,
            "token_usage": 1420,
            "provider_costs": 0.05,
            "overhead_ms": 150,
        },
    )
    assert engine_complete.public_claim_safe is True
