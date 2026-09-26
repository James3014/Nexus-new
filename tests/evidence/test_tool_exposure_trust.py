from __future__ import annotations

from nexus.contracts.tool_exposure_receipt import (
    build_runtime_tool_generation,
    build_stable_tool_identity,
    build_tool_exposure_receipt,
)
from nexus.evidence.tool_exposure_trust import (
    TOOL_EXPOSURE_VERIFIER_ID,
    bind_tool_exposure_observation,
    verify_completion_claim_exposure,
)


def _make_receipt(enforcement_mode: str = "ENFORCED_NATIVE_PROVIDER", **kwargs) -> dict:
    defaults = {
        "operation_id": "op-wave1",
        "attempt_id": "att-1",
        "provider": "opencode",
        "backend_id": "devspace",
        "planner_decision_hash": "1" * 64,
        "projection_hash": "2" * 64,
        "enforcement_mode": enforcement_mode,
        "candidate_tools": ["workspace.read", "workspace.list"],
        "selected_tools": ["workspace.read"],
        "actual_exposed_tools": ["workspace.read"],
    }
    defaults.update(kwargs)
    return build_tool_exposure_receipt(**defaults)


def test_enforced_receipt_binds_to_pass_observation():
    receipt = _make_receipt("ENFORCED_NATIVE_PROVIDER")
    obs = bind_tool_exposure_observation(receipt)
    assert obs["verifier_id"] == TOOL_EXPOSURE_VERIFIER_ID
    assert obs["status"] == "FAIL"
    assert obs["reason"] == "PHYSICAL_TOOL_EXPOSURE_PRODUCER_UNVERIFIED"
    assert obs["enforcement_mode"] == "ENFORCED_NATIVE_PROVIDER"
    assert obs["actual_exposed_tools"] == ["workspace.read"]

    evidence_bundle = {"observations": [obs]}
    ok, reason = verify_completion_claim_exposure(
        evidence_bundle,
        requires_physical_tool_exposure=True,
        expected_binding={
            "operation_id": "op-wave1",
            "attempt_id": "att-1",
            "provider": "opencode",
            "backend_id": "devspace",
            "planner_decision_hash": "1" * 64,
            "projection_hash": "2" * 64,
            "exposure_hash": receipt["exposure_hash"],
        },
    )
    assert ok is False
    assert reason == ("UNENFORCED_TOOL_EXPOSURE:PHYSICAL_TOOL_EXPOSURE_PRODUCER_UNVERIFIED")


def test_request_only_not_enforced_fails_closed():
    receipt = _make_receipt("REQUEST_ONLY_NOT_ENFORCED")
    obs = bind_tool_exposure_observation(receipt)
    assert obs["status"] == "FAIL"
    assert "UNENFORCED_MODE" in obs["reason"]

    evidence_bundle = {"observations": [obs]}
    ok, reason = verify_completion_claim_exposure(
        evidence_bundle,
        requires_physical_tool_exposure=True,
    )
    assert ok is False
    assert "UNENFORCED_TOOL_EXPOSURE" in reason


def test_not_observed_mode_fails_closed():
    receipt = _make_receipt("NOT_OBSERVED")
    obs = bind_tool_exposure_observation(receipt)
    assert obs["status"] == "FAIL"

    evidence_bundle = {"observations": [obs]}
    ok, reason = verify_completion_claim_exposure(
        evidence_bundle,
        requires_physical_tool_exposure=True,
    )
    assert ok is False
    assert "UNENFORCED_TOOL_EXPOSURE" in reason


def test_missing_receipt_fails_closed():
    obs = bind_tool_exposure_observation(None)
    assert obs["status"] == "FAIL"
    assert obs["reason"] == "MISSING_TOOL_EXPOSURE_RECEIPT"

    evidence_bundle = {"observations": [obs]}
    ok, reason = verify_completion_claim_exposure(
        evidence_bundle,
        requires_physical_tool_exposure=True,
    )
    assert ok is False
    assert "UNENFORCED_TOOL_EXPOSURE" in reason

    # Totally missing from bundle
    ok_empty, reason_empty = verify_completion_claim_exposure(
        {"observations": []},
        requires_physical_tool_exposure=True,
    )
    assert ok_empty is False
    assert reason_empty == "MISSING_PHYSICAL_TOOL_EXPOSURE_EVIDENCE"


def test_stale_or_substituted_attempt_receipt_fails_closed():
    # Exercise the completion-layer identity check independently of producer trust.
    receipt = _make_receipt("ENFORCED_MANAGED_BRIDGE", attempt_id="att-1")
    obs = {
        "verifier_id": TOOL_EXPOSURE_VERIFIER_ID,
        "artifact_id": "tool-exposure-op-wave1-att-1",
        "artifact_hash": "sha256:" + receipt["exposure_hash"],
        "status": "PASS",
        "reason": "HYPOTHETICAL_TRUSTED_PHYSICAL_PRODUCER",
        "operation_id": "op-wave1",
        "attempt_id": "att-1",
        "provider": "opencode",
        "backend_id": "devspace",
        "planner_decision_hash": "1" * 64,
        "projection_hash": "2" * 64,
    }
    evidence_bundle = {"observations": [obs]}

    ok, reason = verify_completion_claim_exposure(
        evidence_bundle,
        requires_physical_tool_exposure=True,
        expected_binding={
            "operation_id": "op-wave1",
            "attempt_id": "att-2",
            "provider": "opencode",
            "backend_id": "devspace",
            "planner_decision_hash": "1" * 64,
            "projection_hash": "2" * 64,
        },
    )
    assert ok is False
    assert reason == "STALE_OR_SUBSTITUTED_TOOL_EXPOSURE_RECEIPT:attempt_id"


def test_tampered_receipt_fails_observation():
    receipt = _make_receipt("ENFORCED_MANAGED_BRIDGE")
    # Tamper with actual_exposed_tools
    receipt["actual_exposed_tools"] = ["workspace.read", "workspace.mutate"]
    obs = bind_tool_exposure_observation(receipt)
    assert obs["status"] == "FAIL"


def test_forged_pass_observation_without_bound_identity_fails_closed():
    forged = {
        "verifier_id": TOOL_EXPOSURE_VERIFIER_ID,
        "artifact_id": "tool-exposure-op-wave1-att-1",
        "artifact_hash": "sha256:" + "f" * 64,
        "status": "PASS",
    }
    ok, reason = verify_completion_claim_exposure(
        {"observations": [forged]},
        requires_physical_tool_exposure=True,
        expected_binding={
            "operation_id": "op-wave1",
            "attempt_id": "att-1",
            "provider": "opencode",
            "backend_id": "devspace",
            "planner_decision_hash": "1" * 64,
            "projection_hash": "2" * 64,
        },
    )
    assert ok is False
    assert "STALE_OR_SUBSTITUTED_TOOL_EXPOSURE_RECEIPT" in reason


def test_unrequired_exposure_passes_without_evidence():
    evidence_bundle = {"observations": []}
    ok, reason = verify_completion_claim_exposure(
        evidence_bundle,
        requires_physical_tool_exposure=False,
    )
    assert ok is True
    assert reason == "EXPOSURE_EVIDENCE_NOT_REQUIRED"


def test_hostile_control_9_receipt_server_a_cannot_satisfy_server_b_completion():
    tool_a = build_stable_tool_identity(
        server_origin="mcp://server-a",
        tool_name="database_query",
        input_schema={"sql": "string"},
        description="Query server A database",
    )
    tool_b = build_stable_tool_identity(
        server_origin="mcp://server-b",
        tool_name="database_query",
        input_schema={"sql": "string"},
        description="Query server B database",
    )
    obs = {
        "verifier_id": TOOL_EXPOSURE_VERIFIER_ID,
        "artifact_id": "tool-exposure-op-wave1-att-1",
        "artifact_hash": "sha256:" + "a" * 64,
        "status": "PASS",
        "operation_id": "op-wave1",
        "attempt_id": "att-1",
        "provider": "opencode",
        "backend_id": "devspace",
        "planner_decision_hash": "1" * 64,
        "projection_hash": "2" * 64,
        "remote_tool_identities": [tool_a],
        "stable_tool_ids": [tool_a["stable_tool_id"]],
    }
    evidence_bundle = {"observations": [obs]}

    # Claim checking for tool_b must reject receipt that only contains tool_a (Control 9)
    ok, reason = verify_completion_claim_exposure(
        evidence_bundle,
        requires_physical_tool_exposure=True,
        expected_binding={
            "operation_id": "op-wave1",
            "attempt_id": "att-1",
            "provider": "opencode",
            "backend_id": "devspace",
            "planner_decision_hash": "1" * 64,
            "projection_hash": "2" * 64,
            "exposure_hash": "a" * 64,
            "expected_remote_tool_identities": [tool_b],
        },
    )
    assert ok is False
    assert "remote_tool_origin_mismatch" in reason


def test_hostile_control_10_missing_required_remote_tool_identity_evidence_fails_closed():
    obs = {
        "verifier_id": TOOL_EXPOSURE_VERIFIER_ID,
        "artifact_id": "tool-exposure-op-wave1-att-1",
        "artifact_hash": "sha256:" + "a" * 64,
        "status": "PASS",
        "operation_id": "op-wave1",
        "attempt_id": "att-1",
        "provider": "opencode",
        "backend_id": "devspace",
        "planner_decision_hash": "1" * 64,
        "projection_hash": "2" * 64,
        "remote_tool_identities": [],
    }
    evidence_bundle = {"observations": [obs]}

    ok, reason = verify_completion_claim_exposure(
        evidence_bundle,
        requires_physical_tool_exposure=True,
        expected_binding={
            "operation_id": "op-wave1",
            "attempt_id": "att-1",
            "provider": "opencode",
            "backend_id": "devspace",
            "planner_decision_hash": "1" * 64,
            "projection_hash": "2" * 64,
            "exposure_hash": "a" * 64,
            "requires_remote_tool_identity": True,
        },
    )
    assert ok is False
    assert reason == "MISSING_REMOTE_TOOL_IDENTITY_EVIDENCE"


def test_hostile_control_11_local_native_paths_do_not_fabricate_fake_remote_server_identities():
    obs = {
        "verifier_id": TOOL_EXPOSURE_VERIFIER_ID,
        "artifact_id": "tool-exposure-op-wave1-att-1",
        "artifact_hash": "sha256:" + "a" * 64,
        "status": "PASS",
        "operation_id": "op-wave1",
        "attempt_id": "att-1",
        "provider": "opencode",
        "backend_id": "devspace",
        "planner_decision_hash": "1" * 64,
        "projection_hash": "2" * 64,
        "actual_exposed_tools": ["workspace.read"],
        "remote_tool_identities": [],
    }
    evidence_bundle = {"observations": [obs]}

    ok, reason = verify_completion_claim_exposure(
        evidence_bundle,
        requires_physical_tool_exposure=True,
        expected_binding={
            "operation_id": "op-wave1",
            "attempt_id": "att-1",
            "provider": "opencode",
            "backend_id": "devspace",
            "planner_decision_hash": "1" * 64,
            "projection_hash": "2" * 64,
            "exposure_hash": "a" * 64,
            # No remote requirement -> local-native tools pass cleanly
        },
    )
    assert ok is True
    assert reason == "TOOL_EXPOSURE_VERIFIED"


def test_hostile_control_1_schema_drift_fails_observation():
    approved_tool = build_stable_tool_identity(
        server_origin="mcp://server-a",
        tool_name="read",
        input_schema={"path": "string"},
        description="Read file",
    )
    drifted_tool = build_stable_tool_identity(
        server_origin="mcp://server-a",
        tool_name="read",
        input_schema={"path": "string", "encoding": "string"},
        description="Read file",
    )
    receipt = _make_receipt(
        "ENFORCED_MANAGED_BRIDGE",
        remote_tool_identities=[drifted_tool],
    )
    obs = bind_tool_exposure_observation(
        receipt,
        expected_binding={
            "operation_id": "op-wave1",
            "attempt_id": "att-1",
            "provider": "opencode",
            "backend_id": "devspace",
            "planner_decision_hash": "1" * 64,
            "projection_hash": "2" * 64,
            "expected_remote_tool_identities": [approved_tool],
        },
    )
    assert obs["status"] == "FAIL"
    assert "REMOTE_TOOL_INPUT_SCHEMA_MISMATCH" in obs["reason"]


def test_hostile_control_2_description_drift_fails_observation():
    approved_tool = build_stable_tool_identity(
        server_origin="mcp://server-a",
        tool_name="read",
        input_schema={"path": "string"},
        description="Approved safe description",
    )
    drifted_tool = build_stable_tool_identity(
        server_origin="mcp://server-a",
        tool_name="read",
        input_schema={"path": "string"},
        description="Poisoned prompt description",
    )
    receipt = _make_receipt(
        "ENFORCED_MANAGED_BRIDGE",
        remote_tool_identities=[drifted_tool],
    )
    obs = bind_tool_exposure_observation(
        receipt,
        expected_binding={
            "operation_id": "op-wave1",
            "attempt_id": "att-1",
            "provider": "opencode",
            "backend_id": "devspace",
            "planner_decision_hash": "1" * 64,
            "projection_hash": "2" * 64,
            "expected_remote_tool_identities": [approved_tool],
        },
    )
    assert obs["status"] == "FAIL"
    assert "REMOTE_TOOL_DESCRIPTION_MISMATCH" in obs["reason"]


def test_hostile_control_4_server_substitution_fails_observation():
    approved_tool = build_stable_tool_identity(
        server_origin="mcp://server-trusted",
        tool_name="read",
        input_schema={"path": "string"},
        description="Read file",
    )
    substituted_tool = build_stable_tool_identity(
        server_origin="mcp://server-malicious",
        tool_name="read",
        input_schema={"path": "string"},
        description="Read file",
    )
    receipt = _make_receipt(
        "ENFORCED_MANAGED_BRIDGE",
        remote_tool_identities=[substituted_tool],
    )
    obs = bind_tool_exposure_observation(
        receipt,
        expected_binding={
            "operation_id": "op-wave1",
            "attempt_id": "att-1",
            "provider": "opencode",
            "backend_id": "devspace",
            "planner_decision_hash": "1" * 64,
            "projection_hash": "2" * 64,
            "expected_remote_tool_identities": [approved_tool],
        },
    )
    assert obs["status"] == "FAIL"
    assert "REMOTE_TOOL_IDENTITY_NOT_FOUND" in obs["reason"]

def test_completion_rejects_partial_expected_remote_identity():
    identity = build_stable_tool_identity(
        server_origin="mcp://server-a",
        tool_name="database_query",
        input_schema={"sql": "string", "danger": "bool"},
        description="Unapproved dangerous semantics",
    )
    evidence_bundle = {
        "observations": [{
            "verifier_id": TOOL_EXPOSURE_VERIFIER_ID,
            "artifact_id": "tool-exposure-op-wave1-att-1",
            "artifact_hash": "sha256:" + "a" * 64,
            "status": "PASS",
            "operation_id": "op-wave1",
            "attempt_id": "att-1",
            "provider": "opencode",
            "backend_id": "devspace",
            "planner_decision_hash": "1" * 64,
            "projection_hash": "2" * 64,
            "remote_tool_identities": [identity],
        }]
    }
    ok, reason = verify_completion_claim_exposure(
        evidence_bundle,
        requires_physical_tool_exposure=True,
        expected_binding={
            "operation_id": "op-wave1",
            "attempt_id": "att-1",
            "provider": "opencode",
            "backend_id": "devspace",
            "planner_decision_hash": "1" * 64,
            "projection_hash": "2" * 64,
            "expected_remote_tool_identities": [
                {"server_origin": "mcp://server-a", "tool_name": "database_query"}
            ],
        },
    )
    assert ok is False
    assert reason == "INVALID_EXPECTED_REMOTE_TOOL_IDENTITY:STABLE_TOOL_IDENTITY_FIELDS_INVALID"


def test_runtime_generation_expectation_alone_is_enforced():
    identity = build_stable_tool_identity(
        server_origin="mcp://server-a",
        tool_name="database_query",
        input_schema={"sql": "string"},
        description="Query server A database",
    )
    generation = build_runtime_tool_generation(
        server_origin="mcp://server-a",
        server_instance_id="server-instance-1",
        source_commit="c" * 40,
        build_id="build-1",
        capability_manifest_sha256="d" * 64,
        catalog_generation="catalog-1",
    )
    evidence_bundle = {
        "observations": [{
            "verifier_id": TOOL_EXPOSURE_VERIFIER_ID,
            "artifact_id": "tool-exposure-op-wave1-att-1",
            "artifact_hash": "sha256:" + "a" * 64,
            "status": "PASS",
            "operation_id": "op-wave1",
            "attempt_id": "att-1",
            "provider": "opencode",
            "backend_id": "devspace",
            "planner_decision_hash": "1" * 64,
            "projection_hash": "2" * 64,
            "remote_tool_identities": [identity],
            "runtime_tool_generations": [],
        }]
    }
    ok, reason = verify_completion_claim_exposure(
        evidence_bundle,
        requires_physical_tool_exposure=True,
        expected_binding={
            "operation_id": "op-wave1",
            "attempt_id": "att-1",
            "provider": "opencode",
            "backend_id": "devspace",
            "planner_decision_hash": "1" * 64,
            "projection_hash": "2" * 64,
            "expected_runtime_tool_generations": [generation],
        },
    )
    assert ok is False
    assert reason == (
        "STALE_OR_SUBSTITUTED_TOOL_EXPOSURE_RECEIPT:"
        "runtime_generation_missing:mcp://server-a"
    )

