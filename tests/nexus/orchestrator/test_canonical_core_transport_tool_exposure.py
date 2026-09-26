from __future__ import annotations

import tempfile
from pathlib import Path

from nexus.contracts.tool_exposure_receipt import build_tool_exposure_receipt
from nexus.orchestrator.canonical_core_transport import CanonicalNexusCoreTransportPort


def _create_receipt(enforcement_mode: str = "ENFORCED_NATIVE_PROVIDER", op_id: str = "op-test-1", att_id: str = "att-1") -> dict:
    return build_tool_exposure_receipt(
        operation_id=op_id,
        attempt_id=att_id,
        provider="opencode",
        backend_id="devspace",
        planner_decision_hash="a" * 64,
        projection_hash="b" * 64,
        enforcement_mode=enforcement_mode,
        candidate_tools=["workspace.read", "workspace.list"],
        selected_tools=["workspace.read"],
        actual_exposed_tools=["workspace.read"],
    )


def test_transport_binds_enforced_tool_exposure_receipt_success():
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "test_sessions.db"
        port = CanonicalNexusCoreTransportPort(db_path=str(db_path))
        session_id = "test-session-enforced"
        operation_id = "op-test-enforced"

        receipt = _create_receipt("ENFORCED_NATIVE_PROVIDER", op_id=operation_id, att_id="att-1")

        projection = port.verify_candidate(
            preparation={
                "session_id": session_id,
                "operation_id": operation_id,
                "attempt_id": "att-1",
                "binding_hash": "0" * 64,
            },
            request={"verifier_commands": ["git diff --check", "tool_exposure"]},
            candidate_state_hash="1" * 64,
            tool_exposure_receipt=receipt,
            attempt_id="att-1",
            planner_decision_hash="a" * 64,
            projection_hash="b" * 64,
            provider="opencode",
            backend_id="devspace",
        )

        observations = projection["raw_core_request"]["evidence_bundle"]["observations"]
        tool_obs = next(obs for obs in observations if obs["verifier_id"] == "tool_exposure")
        assert tool_obs["status"] == "PASS"
        assert tool_obs["artifact_hash"].startswith("sha256:")
        assert receipt["exposure_hash"] in tool_obs["artifact_hash"]


def test_transport_fails_closed_on_unenforced_mode():
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "test_sessions.db"
        port = CanonicalNexusCoreTransportPort(db_path=str(db_path))
        session_id = "test-session-unenforced"
        operation_id = "op-test-unenforced"

        # REQUEST_ONLY_NOT_ENFORCED must fail
        receipt = _create_receipt("REQUEST_ONLY_NOT_ENFORCED", op_id=operation_id, att_id="att-1")

        projection = port.verify_candidate(
            preparation={
                "session_id": session_id,
                "operation_id": operation_id,
                "attempt_id": "att-1",
                "binding_hash": "0" * 64,
            },
            request={"verifier_commands": ["git diff --check", "tool_exposure"]},
            candidate_state_hash="1" * 64,
            tool_exposure_receipt=receipt,
            attempt_id="att-1",
            planner_decision_hash="a" * 64,
            projection_hash="b" * 64,
            provider="opencode",
            backend_id="devspace",
        )

        observations = projection["raw_core_request"]["evidence_bundle"]["observations"]
        tool_obs = next(obs for obs in observations if obs["verifier_id"] == "tool_exposure")
        assert tool_obs["status"] == "FAIL"

        core_resp = projection["raw_core_response"]
        assert core_resp["verification"]["status"] != "VERIFIED"


def test_transport_fails_closed_on_missing_receipt_when_required():
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "test_sessions.db"
        port = CanonicalNexusCoreTransportPort(db_path=str(db_path))
        session_id = "test-session-missing"

        projection = port.verify_candidate(
            preparation={
                "session_id": session_id,
                "operation_id": "op-test-missing",
                "attempt_id": "att-1",
                "binding_hash": "0" * 64,
            },
            request={"verifier_commands": ["git diff --check", "tool_exposure"]},
            candidate_state_hash="1" * 64,
            tool_exposure_receipt=None,
            attempt_id="att-1",
        )

        observations = projection["raw_core_request"]["evidence_bundle"]["observations"]
        tool_obs = next(obs for obs in observations if obs["verifier_id"] == "tool_exposure")
        assert tool_obs["status"] == "FAIL"

        core_resp = projection["raw_core_response"]
        assert core_resp["verification"]["status"] != "VERIFIED"


def test_transport_rejects_session_id_substituted_for_operation_id():
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "test_sessions.db"
        port = CanonicalNexusCoreTransportPort(db_path=str(db_path))
        session_id = "test-session-operation-mismatch"
        operation_id = "op-real-operation"
        receipt = _create_receipt(
            "ENFORCED_NATIVE_PROVIDER",
            op_id=session_id,
            att_id="att-1",
        )

        projection = port.verify_candidate(
            preparation={
                "session_id": session_id,
                "operation_id": operation_id,
                "attempt_id": "att-1",
                "binding_hash": "0" * 64,
            },
            request={"verifier_commands": ["git diff --check", "tool_exposure"]},
            candidate_state_hash="1" * 64,
            tool_exposure_receipt=receipt,
            planner_decision_hash="a" * 64,
            projection_hash="b" * 64,
            provider="opencode",
            backend_id="devspace",
        )

        observations = projection["raw_core_request"]["evidence_bundle"]["observations"]
        tool_obs = next(obs for obs in observations if obs["verifier_id"] == "tool_exposure")
        assert tool_obs["status"] == "FAIL"
        assert projection["raw_core_response"]["verification"]["status"] != "VERIFIED"
