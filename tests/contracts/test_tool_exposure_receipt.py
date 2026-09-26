from __future__ import annotations

import pytest

from nexus.contracts.tool_exposure_receipt import (
    PHYSICALLY_ENFORCED_MODES,
    RUNTIME_TOOL_GENERATION_SCHEMA,
    STABLE_TOOL_IDENTITY_SCHEMA,
    TOOL_EXPOSURE_RECEIPT_SCHEMA,
    ToolExposureError,
    ToolExposureIdentityError,
    ToolExposureWidenedError,
    build_runtime_tool_generation,
    build_stable_tool_identity,
    build_tool_exposure_receipt,
    validate_runtime_tool_generation,
    validate_stable_tool_identity,
    validate_tool_exposure_receipt,
)


def _sample_receipt(
    *,
    enforcement_mode: str = "ENFORCED_MANAGED_BRIDGE",
    candidate_tools: tuple[str, ...] = (
        "workspace.read",
        "workspace.search_text",
        "workspace.list",
    ),
    selected_tools: tuple[str, ...] = ("workspace.read", "workspace.search_text"),
    actual_exposed_tools: tuple[str, ...] = ("workspace.read",),
) -> dict:
    return build_tool_exposure_receipt(
        operation_id="op-12345",
        attempt_id="att-67890",
        provider="opencode",
        backend_id="devspace",
        planner_decision_hash="0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
        projection_hash="abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789",
        enforcement_mode=enforcement_mode,
        candidate_tools=candidate_tools,
        selected_tools=selected_tools,
        actual_exposed_tools=actual_exposed_tools,
    )


def test_build_and_validate_tool_exposure_receipt_success():
    receipt = _sample_receipt()
    validated = validate_tool_exposure_receipt(
        receipt,
        expected_operation_id="op-12345",
        expected_attempt_id="att-67890",
        expected_planner_decision_hash="0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
        expected_projection_hash="abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789",
        expected_provider="opencode",
        expected_backend_id="devspace",
    )
    assert validated["schema"] == TOOL_EXPOSURE_RECEIPT_SCHEMA
    assert validated["enforcement_mode"] in PHYSICALLY_ENFORCED_MODES
    assert validated["actual_exposed_tools"] == ["workspace.read"]
    assert validated["actual_exposed_tool_count"] == 1


def test_selected_tools_exceed_candidate_fails_closed():
    with pytest.raises(ToolExposureWidenedError, match="SELECTED_TOOLS_EXCEED_CANDIDATE_TOOLS"):
        _sample_receipt(
            candidate_tools=("workspace.read",),
            selected_tools=("workspace.read", "workspace.mutate"),
            actual_exposed_tools=("workspace.read",),
        )


def test_actual_exposed_tools_exceed_selected_fails_closed():
    with pytest.raises(
        ToolExposureWidenedError, match="ACTUAL_EXPOSED_TOOLS_EXCEED_SELECTED_TOOLS"
    ):
        _sample_receipt(
            candidate_tools=("workspace.read", "workspace.mutate"),
            selected_tools=("workspace.read",),
            actual_exposed_tools=("workspace.read", "workspace.mutate"),
        )


def test_tampered_receipt_hash_fails_closed():
    receipt = _sample_receipt()
    receipt["actual_exposed_tools"].append("workspace.search_text")
    receipt["actual_exposed_tool_count"] = len(receipt["actual_exposed_tools"])
    with pytest.raises(ToolExposureError, match="TOOL_EXPOSURE_HASH_MISMATCH"):
        validate_tool_exposure_receipt(receipt)


def test_identity_mismatch_fails_closed():
    receipt = _sample_receipt()
    with pytest.raises(ToolExposureIdentityError, match="TOOL_EXPOSURE_OPERATION_MISMATCH"):
        validate_tool_exposure_receipt(receipt, expected_operation_id="different-op")

    with pytest.raises(ToolExposureIdentityError, match="TOOL_EXPOSURE_ATTEMPT_MISMATCH"):
        validate_tool_exposure_receipt(receipt, expected_attempt_id="different-att")

    with pytest.raises(ToolExposureIdentityError, match="TOOL_EXPOSURE_PROVIDER_MISMATCH"):
        validate_tool_exposure_receipt(receipt, expected_provider="codex")


def test_invalid_enforcement_mode_fails_closed():
    with pytest.raises(ToolExposureError, match="enforcement_mode_invalid"):
        build_tool_exposure_receipt(
            operation_id="op-1",
            attempt_id="att-1",
            provider="opencode",
            backend_id="devspace",
            planner_decision_hash="0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
            projection_hash="abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789",
            enforcement_mode="FAKE_MODE",
            candidate_tools=["read"],
            selected_tools=["read"],
            actual_exposed_tools=["read"],
        )


def test_stable_tool_identity_creation_and_deterministic_hash():
    ident = build_stable_tool_identity(
        server_origin="mcp://file-server",
        tool_name="read_file",
        input_schema={"type": "object", "properties": {"path": {"type": "string"}}},
        description="Read file contents securely",
    )
    assert ident["schema"] == STABLE_TOOL_IDENTITY_SCHEMA
    assert ident["server_origin"] == "mcp://file-server"
    assert ident["tool_name"] == "read_file"
    assert len(ident["input_schema_hash"]) == 64
    assert len(ident["description_hash"]) == 64
    assert len(ident["stable_tool_id"]) == 64

    validated = validate_stable_tool_identity(ident)
    assert validated == ident


def test_stable_tool_identity_rejects_schema_and_description_drift():
    ident = build_stable_tool_identity(
        server_origin="mcp://file-server",
        tool_name="read_file",
        input_schema={"type": "object", "properties": {"path": {"type": "string"}}},
        description="Original description",
    )

    # Schema drift check (Hostile Control 1)
    with pytest.raises(ToolExposureIdentityError, match="REMOTE_TOOL_INPUT_SCHEMA_MISMATCH"):
        validate_stable_tool_identity(
            ident,
            expected_input_schema_hash="0" * 64,
        )

    # Description drift check (Hostile Control 2)
    with pytest.raises(ToolExposureIdentityError, match="REMOTE_TOOL_DESCRIPTION_MISMATCH"):
        validate_stable_tool_identity(
            ident,
            expected_description_hash="0" * 64,
        )


def test_runtime_tool_generation_evidence_creation_and_validation():
    gen = build_runtime_tool_generation(
        server_origin="mcp://file-server",
        server_instance_id="inst-1",
        source_commit="a" * 40,
        build_id="devspace-build-1",
        capability_manifest_sha256="b" * 64,
        catalog_generation=1,
    )
    assert gen["schema"] == RUNTIME_TOOL_GENERATION_SCHEMA
    assert gen["server_origin"] == "mcp://file-server"
    assert gen["server_instance_id"] == "inst-1"
    assert gen["source_commit"] == "a" * 40
    assert gen["build_id"] == "devspace-build-1"
    assert gen["capability_manifest_sha256"] == "b" * 64
    assert gen["catalog_generation"] == 1
    assert len(gen["generation_hash"]) == 64

    validated = validate_runtime_tool_generation(gen)
    assert validated == gen

    with pytest.raises(
        ToolExposureIdentityError, match="RUNTIME_GENERATION_SERVER_INSTANCE_MISMATCH"
    ):
        validate_runtime_tool_generation(gen, expected_server_instance_id="inst-2")

    with pytest.raises(ToolExposureIdentityError, match="RUNTIME_GENERATION_BUILD_ID_MISMATCH"):
        validate_runtime_tool_generation(gen, expected_build_id="devspace-build-2")


def test_receipt_with_remote_tool_identities_tampered_fails_closed():
    ident = build_stable_tool_identity(
        server_origin="mcp://file-server",
        tool_name="read_file",
        input_schema={"path": "string"},
        description="Read file",
    )
    gen = build_runtime_tool_generation(
        server_origin="mcp://file-server",
        server_instance_id="inst-1",
        source_commit="a" * 40,
        build_id="devspace-build-1",
        capability_manifest_sha256="b" * 64,
        catalog_generation=1,
    )
    receipt = build_tool_exposure_receipt(
        operation_id="op-remote-1",
        attempt_id="att-remote-1",
        provider="opencode",
        backend_id="devspace",
        planner_decision_hash="0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
        projection_hash="abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789",
        enforcement_mode="ENFORCED_MANAGED_BRIDGE",
        candidate_tools=["read_file"],
        selected_tools=["read_file"],
        actual_exposed_tools=["read_file"],
        remote_tool_identities=[ident],
        runtime_tool_generations=[gen],
    )
    validated = validate_tool_exposure_receipt(
        receipt,
        expected_remote_tool_identities=[ident],
        expected_runtime_tool_generations=[gen],
    )
    assert len(validated["remote_tool_identities"]) == 1

    # Tamper with remote tool identity in receipt
    tampered = dict(receipt)
    tampered["remote_tool_identities"] = [{**ident, "tool_name": "tampered_tool"}]
    with pytest.raises(ToolExposureError, match="TOOL_EXPOSURE_HASH_MISMATCH"):
        validate_tool_exposure_receipt(tampered)


def test_partial_expected_remote_identity_fails_closed():
    identity = build_stable_tool_identity(
        server_origin="mcp://server-a",
        tool_name="db_query",
        input_schema={"sql": "string", "danger": "bool"},
        description="Unapproved dangerous semantics",
    )
    receipt = build_tool_exposure_receipt(
        operation_id="op-partial-remote",
        attempt_id="att-1",
        provider="opencode",
        backend_id="devspace",
        planner_decision_hash="a" * 64,
        projection_hash="b" * 64,
        enforcement_mode="ENFORCED_MANAGED_BRIDGE",
        candidate_tools=["db_query"],
        selected_tools=["db_query"],
        actual_exposed_tools=["db_query"],
        remote_tool_identities=[identity],
    )
    with pytest.raises(ToolExposureError, match="STABLE_TOOL_IDENTITY_FIELDS_INVALID"):
        validate_tool_exposure_receipt(
            receipt,
            expected_remote_tool_identities=[
                {"server_origin": "mcp://server-a", "tool_name": "db_query"}
            ],
            require_remote_tool_identity=True,
        )


def test_partial_expected_runtime_generation_fails_closed():
    generation = build_runtime_tool_generation(
        server_origin="mcp://server-a",
        server_instance_id="server-instance-1",
        source_commit="c" * 40,
        build_id="build-1",
        capability_manifest_sha256="d" * 64,
        catalog_generation="catalog-1",
    )
    receipt = build_tool_exposure_receipt(
        operation_id="op-partial-generation",
        attempt_id="att-1",
        provider="opencode",
        backend_id="devspace",
        planner_decision_hash="a" * 64,
        projection_hash="b" * 64,
        enforcement_mode="ENFORCED_MANAGED_BRIDGE",
        candidate_tools=["db_query"],
        selected_tools=["db_query"],
        actual_exposed_tools=["db_query"],
        runtime_tool_generations=[generation],
    )
    with pytest.raises(ToolExposureError, match="RUNTIME_TOOL_GENERATION_FIELDS_INVALID"):
        validate_tool_exposure_receipt(
            receipt,
            expected_runtime_tool_generations=[{"server_origin": "mcp://server-a"}],
        )
