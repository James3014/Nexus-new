from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path
from typing import Any

import pytest

import nexus.orchestrator.canonical_core_transport as core_transport
from nexus.contracts.tool_exposure_receipt import (
    build_stable_tool_identity,
    build_tool_exposure_receipt,
)
from nexus.orchestrator.canonical_core_transport import CanonicalNexusCoreTransportPort


def _portable_hash(value: Any) -> str:
    payload = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


@pytest.fixture(autouse=True)
def portable_core_boundary(monkeypatch: pytest.MonkeyPatch):
    """Exercise transport wiring without depending on a host-local nexus-core checkout."""

    monkeypatch.setattr(core_transport, "CORE_AVAILABLE", True)
    for name in (
        "acceptance_contract_hash",
        "change_manifest_hash",
        "change_set_hash",
        "evidence_bundle_hash",
        "verification_plan_hash",
    ):
        monkeypatch.setattr(core_transport, name, _portable_hash, raising=False)

    def fake_verify_generic_changeset(request: dict[str, Any]):
        observations = request["evidence_bundle"]["observations"]
        verified = all(obs["status"] == "PASS" for obs in observations)
        response = {
            "schema": core_transport.GENERIC_VERIFICATION_RESPONSE_SCHEMA_ID,
            "protocol_version": core_transport.PUBLIC_PROTOCOL_VERSION,
            "verification": {
                "status": "VERIFIED" if verified else "FAILED_VERIFICATION",
                "reason_codes": [] if verified else ["EVIDENCE_FAILED"],
                "integrity": "VALID" if verified else "INVALID",
            },
            "hashes": {
                "acceptance_contract_hash": _portable_hash(request["acceptance_contract"]),
                "change_set_hash": _portable_hash(request["change_set"]),
                "verification_plan_hash": _portable_hash(request["verification_plan"]),
                "evidence_bundle_hash": _portable_hash(request["evidence_bundle"]),
                "change_manifest_hash": _portable_hash(request["change_manifest"]),
            },
            "certification": None,
        }
        return 200, response

    monkeypatch.setattr(
        core_transport,
        "verify_generic_changeset",
        fake_verify_generic_changeset,
        raising=False,
    )


def _create_receipt(
    enforcement_mode: str = "ENFORCED_NATIVE_PROVIDER",
    op_id: str = "op-test-1",
    att_id: str = "att-1",
) -> dict:
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
        assert tool_obs["status"] == "FAIL"
        assert tool_obs["artifact_hash"].startswith("sha256:")
        assert receipt["exposure_hash"] in tool_obs["artifact_hash"]
        assert projection["raw_core_response"]["verification"]["status"] != "VERIFIED"


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


# -----------------------------------------------------------------------------
# NAB-E3 Issue #1144: 11 Mandatory Hostile Controls Tests
# -----------------------------------------------------------------------------


def test_matching_remote_identity_still_fails_without_canonical_physical_producer():
    """Matching E3 identity evidence cannot self-mint physical producer trust."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "test_sessions.db"
        port = CanonicalNexusCoreTransportPort(db_path=str(db_path))
        tool = build_stable_tool_identity(
            server_origin="mcp://server-a",
            tool_name="db_query",
            input_schema={"sql": "string"},
            description="Query server A",
        )
        receipt = build_tool_exposure_receipt(
            operation_id="op-producer-unverified",
            attempt_id="att-1",
            provider="opencode",
            backend_id="devspace",
            planner_decision_hash="a" * 64,
            projection_hash="b" * 64,
            enforcement_mode="ENFORCED_MANAGED_BRIDGE",
            candidate_tools=["db_query"],
            selected_tools=["db_query"],
            actual_exposed_tools=["db_query"],
            remote_tool_identities=[tool],
        )
        projection = port.verify_candidate(
            preparation={
                "session_id": "test-session-producer-unverified",
                "operation_id": "op-producer-unverified",
                "attempt_id": "att-1",
                "binding_hash": "0" * 64,
            },
            request={"verifier_commands": ["git diff --check", "tool_exposure"]},
            candidate_state_hash="1" * 64,
            tool_exposure_receipt=receipt,
            expected_remote_tool_identities=[tool],
            requires_remote_tool_identity=True,
            planner_decision_hash="a" * 64,
            projection_hash="b" * 64,
            provider="opencode",
            backend_id="devspace",
        )
        observations = projection["raw_core_request"]["evidence_bundle"]["observations"]
        tool_obs = next(obs for obs in observations if obs["verifier_id"] == "tool_exposure")
        assert tool_obs["status"] == "FAIL"
        assert tool_obs["reason"] == "PHYSICAL_TOOL_EXPOSURE_PRODUCER_UNVERIFIED"
        assert projection["raw_core_response"]["verification"]["status"] != "VERIFIED"


def test_hostile_control_9_receipt_tool_server_a_cannot_satisfy_tool_server_b_completion():
    """Hostile Control 9: receipt from tool/server A cannot satisfy tool/server B completion."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "test_sessions.db"
        port = CanonicalNexusCoreTransportPort(db_path=str(db_path))

        tool_a = build_stable_tool_identity(
            server_origin="mcp://server-a",
            tool_name="db_query",
            input_schema={"sql": "string"},
            description="Query server A",
        )
        tool_b = build_stable_tool_identity(
            server_origin="mcp://server-b",
            tool_name="db_query",
            input_schema={"sql": "string"},
            description="Query server B",
        )
        # Receipt only contains tool_a
        receipt = build_tool_exposure_receipt(
            operation_id="op-test-9",
            attempt_id="att-1",
            provider="opencode",
            backend_id="devspace",
            planner_decision_hash="a" * 64,
            projection_hash="b" * 64,
            enforcement_mode="ENFORCED_MANAGED_BRIDGE",
            candidate_tools=["db_query"],
            selected_tools=["db_query"],
            actual_exposed_tools=["db_query"],
            remote_tool_identities=[tool_a],
        )

        # Candidate verification requiring tool_b
        projection = port.verify_candidate(
            preparation={
                "session_id": "test-session-9",
                "operation_id": "op-test-9",
                "attempt_id": "att-1",
                "binding_hash": "0" * 64,
            },
            request={"verifier_commands": ["git diff --check", "tool_exposure"]},
            candidate_state_hash="1" * 64,
            tool_exposure_receipt=receipt,
            expected_remote_tool_identities=[tool_b],
            requires_remote_tool_identity=True,
            attempt_id="att-1",
            planner_decision_hash="a" * 64,
            projection_hash="b" * 64,
            provider="opencode",
            backend_id="devspace",
        )
        observations = projection["raw_core_request"]["evidence_bundle"]["observations"]
        tool_obs = next(obs for obs in observations if obs["verifier_id"] == "tool_exposure")
        assert tool_obs["status"] == "FAIL"
        assert "REMOTE_TOOL_IDENTITY_NOT_FOUND" in tool_obs.get("reason", "")
        assert projection["raw_core_response"]["verification"]["status"] != "VERIFIED"


def test_hostile_control_10_missing_required_remote_tool_identity_fails_closed():
    """Hostile Control 10: missing required remote tool-identity evidence -> fail closed."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "test_sessions.db"
        port = CanonicalNexusCoreTransportPort(db_path=str(db_path))

        # Receipt without remote_tool_identities
        receipt = build_tool_exposure_receipt(
            operation_id="op-test-10",
            attempt_id="att-1",
            provider="opencode",
            backend_id="devspace",
            planner_decision_hash="a" * 64,
            projection_hash="b" * 64,
            enforcement_mode="ENFORCED_MANAGED_BRIDGE",
            candidate_tools=["some_tool"],
            selected_tools=["some_tool"],
            actual_exposed_tools=["some_tool"],
            remote_tool_identities=[],
        )

        projection = port.verify_candidate(
            preparation={
                "session_id": "test-session-10",
                "operation_id": "op-test-10",
                "attempt_id": "att-1",
                "binding_hash": "0" * 64,
            },
            request={"verifier_commands": ["git diff --check", "tool_exposure"]},
            candidate_state_hash="1" * 64,
            tool_exposure_receipt=receipt,
            requires_remote_tool_identity=True,
            attempt_id="att-1",
            planner_decision_hash="a" * 64,
            projection_hash="b" * 64,
            provider="opencode",
            backend_id="devspace",
        )
        observations = projection["raw_core_request"]["evidence_bundle"]["observations"]
        tool_obs = next(obs for obs in observations if obs["verifier_id"] == "tool_exposure")
        assert tool_obs["status"] == "FAIL"
        assert "MISSING_REMOTE_TOOL_IDENTITY_EVIDENCE" in tool_obs.get("reason", "")


def test_hostile_control_11_local_native_paths_no_fabricated_fake_identities():
    """Hostile Control 11: local-native/non-remote paths must not be forced to fabricate fake remote server identities."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "test_sessions.db"
        port = CanonicalNexusCoreTransportPort(db_path=str(db_path))

        # Local-native receipt: standard strings, no remote tool identities
        receipt = build_tool_exposure_receipt(
            operation_id="op-test-11",
            attempt_id="att-1",
            provider="opencode",
            backend_id="devspace",
            planner_decision_hash="a" * 64,
            projection_hash="b" * 64,
            enforcement_mode="ENFORCED_NATIVE_PROVIDER",
            candidate_tools=["workspace.read", "workspace.mutate"],
            selected_tools=["workspace.read"],
            actual_exposed_tools=["workspace.read"],
        )

        projection = port.verify_candidate(
            preparation={
                "session_id": "test-session-11",
                "operation_id": "op-test-11",
                "attempt_id": "att-1",
                "binding_hash": "0" * 64,
            },
            request={"verifier_commands": ["git diff --check", "tool_exposure"]},
            candidate_state_hash="1" * 64,
            tool_exposure_receipt=receipt,
            # requires_remote_tool_identity is False (default)
            attempt_id="att-1",
            planner_decision_hash="a" * 64,
            projection_hash="b" * 64,
            provider="opencode",
            backend_id="devspace",
        )
        observations = projection["raw_core_request"]["evidence_bundle"]["observations"]
        tool_obs = next(obs for obs in observations if obs["verifier_id"] == "tool_exposure")
        # Producer trust is unverified so status is FAIL, but NOT because of missing remote identity!
        assert tool_obs["reason"] == "PHYSICAL_TOOL_EXPOSURE_PRODUCER_UNVERIFIED"
