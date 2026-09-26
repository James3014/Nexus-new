from __future__ import annotations

import pytest

from nexus.contracts.tool_exposure_receipt import (
    PHYSICALLY_ENFORCED_MODES,
    TOOL_EXPOSURE_RECEIPT_SCHEMA,
    ToolExposureError,
    ToolExposureIdentityError,
    ToolExposureWidenedError,
    build_tool_exposure_receipt,
    validate_tool_exposure_receipt,
)


def _sample_receipt(
    *,
    enforcement_mode: str = "ENFORCED_MANAGED_BRIDGE",
    candidate_tools: tuple[str, ...] = ("workspace.read", "workspace.search_text", "workspace.list"),
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
    with pytest.raises(ToolExposureWidenedError, match="ACTUAL_EXPOSED_TOOLS_EXCEED_SELECTED_TOOLS"):
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
