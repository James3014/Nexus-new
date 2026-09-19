from nexus.governance.capability_gate import (
    CAPABILITY_GATE_AUTHORITY_BOUNDARY,
    CAPABILITY_GATE_ISSUES_EFFECT_AUTHORITY,
    CapabilityGate,
)


def test_legacy_capability_gate_is_explicitly_non_authoritative():
    metadata = CapabilityGate.authority_metadata()

    assert CAPABILITY_GATE_AUTHORITY_BOUNDARY == "LEGACY_COMPATIBILITY_PROJECTION_ONLY"
    assert CAPABILITY_GATE_ISSUES_EFFECT_AUTHORITY is False
    assert metadata == {
        "authority_boundary": "LEGACY_COMPATIBILITY_PROJECTION_ONLY",
        "issues_effect_authority": False,
        "effect_authorization_schema": None,
        "tool_projection_schema": None,
    }


def test_legacy_tool_projection_behavior_remains_backward_compatible():
    gate = CapabilityGate()

    repair_tools = gate.get_tools("repair")
    assert "write_to_file" in repair_tools
    assert gate.managed_toolsets("R") == repair_tools
    assert gate.build_tools_json("repair")["available_tools"] == repair_tools
