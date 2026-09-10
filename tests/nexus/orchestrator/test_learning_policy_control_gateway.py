from __future__ import annotations

from nexus.contracts.autonomy_goal import AutonomyActionClass
from nexus.orchestrator import unified_mcp_gateway as gateway_module
from nexus.orchestrator.unified_mcp_gateway import GatewayInputError, UnifiedMCPGateway


def _arguments():
    return {
        "artifact": {"nested": {"value": "before"}},
        "recommendation": {"source": "recommendation"},
        "validation": {"source": "validation"},
        "expected_current_digest": "a" * 64,
        "operation_id": "op-1",
        "idempotency_key": "idem-1",
        "source_revision": "rev-1",
        "task_family": "family",
        "model_name": "model",
        "runtime_identity": "runtime",
        "authority_goal_id": "goal",
        "authority_coordination_scope_id": "scope",
    }


def test_gateway_closed_schema_and_full_effect_binding(monkeypatch):
    gateway = object.__new__(UnifiedMCPGateway)
    captured = {}
    arguments_ref = {}

    def authorize(action, effect, *, key):
        captured.update({"action": action, "effect": effect})
        arguments_ref["arguments"]["artifact"]["nested"]["value"] = "mutated-during-authority"
        return {"decision": "allowed"}

    gateway._require_owner_effect_authority = authorize

    def fake_apply(**kwargs):
        captured["apply"] = kwargs
        return {"status": "APPLIED"}

    monkeypatch.setattr(gateway_module, "apply_learning_policy_effect", fake_apply)
    arguments = _arguments()
    arguments_ref["arguments"] = arguments
    original = arguments["artifact"]["nested"]["value"]
    result = gateway._learning_policy_control(
        arguments, action=AutonomyActionClass.LEARNING_POLICY_ADOPT
    )
    assert result["status"] == "APPLIED"
    assert captured["action"] is AutonomyActionClass.LEARNING_POLICY_ADOPT
    assert captured["effect"]["expected_current_digest"] == "a" * 64
    assert captured["effect"]["recommendation_input_hash"]
    assert captured["effect"]["validation_input_hash"]
    assert captured["effect"]["artifact_hash"]
    assert captured["effect"]["target_path"].endswith(
        ".nexus/policy/governed_learning_policy_adoption.json"
    )
    assert captured["apply"]["artifact"]["nested"]["value"] == original
    arguments["artifact"]["nested"]["value"] = "after"
    assert captured["apply"]["artifact"]["nested"]["value"] == original

    arguments = _arguments()
    arguments["unexpected"] = True
    try:
        gateway._learning_policy_control(
            arguments, action=AutonomyActionClass.LEARNING_POLICY_ADOPT
        )
    except GatewayInputError as exc:
        assert str(exc) == "LEARNING_POLICY_CONTROL_SCHEMA_CLOSED"
    else:  # pragma: no cover
        raise AssertionError("closed schema accepted an unknown field")


def test_gateway_denies_tampered_artifact_before_write(monkeypatch, tmp_path):
    gateway = object.__new__(UnifiedMCPGateway)
    monkeypatch.setattr(gateway_module, "CANONICAL_SOURCE_ROOT", tmp_path)
    gateway._require_owner_effect_authority = lambda action, effect, *, key: {"decision": "allowed"}
    arguments = _arguments()
    arguments["artifact"] = {"schema": "tampered"}
    try:
        gateway._learning_policy_control(
            arguments, action=AutonomyActionClass.LEARNING_POLICY_ADOPT
        )
    except GatewayInputError:
        pass
    else:  # pragma: no cover
        raise AssertionError("tampered artifact was accepted")
    assert not (tmp_path / ".nexus/policy/governed_learning_policy_adoption.json").exists()
