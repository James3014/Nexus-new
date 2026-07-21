"""Online execution authorization contract tests (shipped resolve path)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from nexus.services.online_execution_policy import (
    ONLINE_DENIED_BY_POLICY,
    ONLINE_NOT_REQUESTED,
    ONLINE_READY,
    build_online_execution_context_fields,
    normalize_online_policy,
    physical_online_authorized,
    resolve_online_execution_decision,
)


def test_normalize_online_policy_and_invalid() -> None:
    assert normalize_online_policy("auto") == "auto"
    assert normalize_online_policy("") == "deny"
    with pytest.raises(ValueError, match="invalid_online_policy"):
        normalize_online_policy("maybe")


def test_task_deny_overrides_workspace_allow(tmp_path: Path) -> None:
    policy_path = tmp_path / ".nexus" / "online_execution_policy.json"
    policy_path.parent.mkdir(parents=True)
    policy_path.write_text(
        json.dumps({"default_online_policy": "auto", "approved_online_providers": ["gemini"]}),
        encoding="utf-8",
    )
    decision = resolve_online_execution_decision(
        task_online_policy="deny",
        project_root=tmp_path,
        planner_online_needed=True,
        environ={},
    )
    assert decision.online_execution_authorized is False
    assert decision.preflight_status == ONLINE_DENIED_BY_POLICY
    assert decision.online_authorization_source == "cli_task_policy"
    assert decision.physical_invocation_allowed is False


def test_workspace_auto_authorizes_when_task_empty(tmp_path: Path) -> None:
    policy_path = tmp_path / ".nexus" / "online_execution_policy.json"
    policy_path.parent.mkdir(parents=True)
    policy_path.write_text(
        json.dumps({"default_online_policy": "auto", "approved_online_providers": ["gemini", "grok"]}),
        encoding="utf-8",
    )
    decision = resolve_online_execution_decision(
        task_online_policy="",
        project_root=tmp_path,
        planner_online_needed=True,
        requested_provider="gemini",
        environ={"GEMINI_API_KEY": "test-key"},
    )
    assert decision.online_policy == "auto"
    assert decision.online_execution_authorized is True
    assert decision.physical_invocation_allowed is True
    assert decision.online_authorization_source == "workspace_policy"
    assert decision.preflight_status == ONLINE_READY


def test_env_override_is_only_emergency_source_without_workspace_policy(tmp_path: Path) -> None:
    # No workspace policy file → deny default, env elevates to auto.
    decision = resolve_online_execution_decision(
        task_online_policy="",
        project_root=tmp_path,
        planner_online_needed=True,
        requested_provider="gemini",
        environ={"NEXUS_EXTERNAL_RUNTIME_AUTHORIZED": "1", "GEMINI_API_KEY": "x"},
    )
    assert decision.online_execution_authorized is True
    assert decision.online_authorization_source == "operator_environment_override"


def test_workspace_deny_not_broadened_by_env_override(tmp_path: Path) -> None:
    policy_path = tmp_path / ".nexus" / "online_execution_policy.json"
    policy_path.parent.mkdir(parents=True)
    policy_path.write_text(
        json.dumps({"default_online_policy": "deny", "approved_online_providers": ["gemini"]}),
        encoding="utf-8",
    )
    decision = resolve_online_execution_decision(
        task_online_policy="",
        project_root=tmp_path,
        planner_online_needed=True,
        requested_provider="gemini",
        environ={"NEXUS_EXTERNAL_RUNTIME_AUTHORIZED": "1", "GEMINI_API_KEY": "x"},
    )
    assert decision.online_execution_authorized is False
    assert decision.online_authorization_source == "workspace_policy"
    assert decision.preflight_status == ONLINE_DENIED_BY_POLICY


def test_require_fails_closed_for_unapproved_provider(tmp_path: Path) -> None:
    policy_path = tmp_path / ".nexus" / "online_execution_policy.json"
    policy_path.parent.mkdir(parents=True)
    policy_path.write_text(
        json.dumps({"default_online_policy": "deny", "approved_online_providers": ["gemini"]}),
        encoding="utf-8",
    )
    decision = resolve_online_execution_decision(
        task_online_policy="require",
        project_root=tmp_path,
        planner_online_needed=True,
        requested_provider="unknown-cloud",
        environ={},
    )
    assert decision.online_execution_requested is True
    assert decision.online_execution_authorized is False
    assert decision.physical_invocation_allowed is False


def test_require_without_provider_is_configuration_invalid(tmp_path: Path) -> None:
    from nexus.services.online_execution_policy import ONLINE_CONFIGURATION_INVALID

    decision = resolve_online_execution_decision(
        task_online_policy="require",
        project_root=tmp_path,
        planner_online_needed=True,
        requested_provider="",
        environ={},
    )
    assert decision.online_execution_authorized is False
    assert decision.preflight_status == ONLINE_CONFIGURATION_INVALID


def test_auto_not_requested_when_planner_says_no(tmp_path: Path) -> None:
    decision = resolve_online_execution_decision(
        task_online_policy="auto",
        project_root=tmp_path,
        planner_online_needed=False,
        environ={},
    )
    assert decision.online_execution_requested is False
    assert decision.preflight_status == ONLINE_NOT_REQUESTED


def test_injected_transport_authorizes_fixture_not_physical(tmp_path: Path) -> None:
    decision = resolve_online_execution_decision(
        task_online_policy="deny",  # even deny is overridden for fixture path after deny check...
        project_root=tmp_path,
        injected_transport=True,
        environ={},
    )
    # Task deny still wins over injected — product safety.
    assert decision.online_execution_authorized is False

    decision2 = resolve_online_execution_decision(
        task_online_policy="auto",
        project_root=tmp_path,
        injected_transport=True,
        environ={},
    )
    assert decision2.online_execution_authorized is True
    assert decision2.online_authorization_source == "injected_test_transport"
    assert decision2.physical_invocation_allowed is False
    assert physical_online_authorized(decision2.to_dict(), injected_transport=False) is False
    assert physical_online_authorized(decision2.to_dict(), injected_transport=True) is True


def test_credentials_do_not_imply_authorization(tmp_path: Path) -> None:
    # Presence of a binary path in env must not authorize.
    decision = resolve_online_execution_decision(
        task_online_policy="deny",
        project_root=tmp_path,
        requested_provider="gemini",
        environ={"NEXUS_GEMINI_BIN": "/usr/bin/gemini", "PATH": "/usr/bin"},
    )
    assert decision.online_execution_authorized is False
    assert decision.claim_boundary.get("credentials_do_not_imply_authorization") is True


def test_opencode_auto_authorizes_when_binary_present(tmp_path: Path) -> None:
    decision = resolve_online_execution_decision(
        task_online_policy="auto",
        project_root=tmp_path,
        planner_online_needed=True,
        requested_provider="opencode",
        environ={"PATH": "/usr/local/bin"},
    )
    assert decision.online_execution_authorized is True
    assert decision.preflight_status == "ONLINE_READY"
    assert "opencode" in decision.approved_online_providers


def test_opencode_deny_blocks_before_binary_check(tmp_path: Path) -> None:
    decision = resolve_online_execution_decision(
        task_online_policy="deny",
        project_root=tmp_path,
        planner_online_needed=True,
        requested_provider="opencode",
        environ={"PATH": "/usr/local/bin"},
    )
    assert decision.online_execution_authorized is False
    assert decision.preflight_status == ONLINE_DENIED_BY_POLICY


def test_build_online_execution_context_fields(tmp_path: Path) -> None:
    fields = build_online_execution_context_fields(
        online_policy="auto",
        project_root=tmp_path,
        task_id="t1",
        workspace_revision="rev",
    )
    assert fields["online_policy"] == "auto"
    assert "online_execution_decision" in fields
    assert fields["task_id"] == "t1"


def test_registered_cli_enforces_canonical_decision(tmp_path: Path, monkeypatch) -> None:
    from nexus.services.unified_runtime import build_registered_online_invoker

    monkeypatch.delenv("NEXUS_EXTERNAL_RUNTIME_AUTHORIZED", raising=False)
    invoker = build_registered_online_invoker(
        "grok",
        command=("/bin/echo", "should-not-run"),
    )
    # No decision + no env → deny
    result = invoker({"task_id": "auth-task", "task_statement": "x"})
    assert result["invoked"] is False
    assert result["error"] == "online_execution_not_authorized"

    # Explicit authorized decision allows physical path (still may fail process, but not auth)
    authorized = resolve_online_execution_decision(
        task_online_policy="auto",
        project_root=tmp_path,
        planner_online_needed=True,
        requested_provider="grok",
        environ={"NEXUS_EXTERNAL_RUNTIME_AUTHORIZED": "1", "XAI_API_KEY": "x"},
    )
    # With env override and no workspace file, authorized
    result2 = invoker(
        {
            "task_id": "auth-task-2",
            "task_statement": "x",
            "online_execution_decision": authorized.to_dict(),
        }
    )
    # echo may succeed as subprocess
    assert result2.get("error") != "online_execution_not_authorized" or result2.get("invoked") is True


def test_unified_runtime_task_deny_never_calls_online_invoker(tmp_path: Path) -> None:
    """Repair-style custom online_callable must not run under task deny."""
    from nexus.services.unified_runtime import UnifiedRuntime, UnifiedRuntimeRequest

    calls: list[str] = []

    def online_invoker(context):
        calls.append("invoked")
        return {
            "provider": "fixture",
            "task_id": str(context.get("task_id", "")),
            "invoked": True,
            "output_delivered": True,
            "gate_passed": True,
            "provider_call_count": 1,
            "response": {"patch": "should-not-happen"},
            "raw_response": "raw",
            "usage": {},
            "error": "",
            "evidence_refs": [],
        }

    def verifier(context):
        return {
            "task_id": "deny-e2e",
            "status": "pass",
            "gate_passed": True,
            "invoked": True,
            "evidence_refs": ["v"],
        }

    def learning(context):
        return {
            "task_id": "deny-e2e",
            "status": "pass",
            "gate_passed": True,
            "invoked": True,
            "evidence_refs": ["l"],
        }

    receipt = UnifiedRuntime().run(
        UnifiedRuntimeRequest(
            task_id="deny-e2e",
            workspace_revision="rev-deny",
            task_statement="bounded advisory",
            task_type="repair",
            route={
                "recommended_flow": "direct",
                "online_policy": "deny",
                "provider": "gemini",
                "workspace_root": str(tmp_path),
            },
            online_prompt="do not call online",
            online_payload="x",
        ),
        online_invoker=online_invoker,
        verifier=verifier,
        learning=learning,
    )
    assert calls == []
    assert receipt["online"]["invoked"] is False
    assert receipt["online"]["status"] == "FAILED"
    assert receipt["online"]["response"]["error"] == "online_execution_not_authorized"
    assert receipt["online_preflight"]["status"] == ONLINE_DENIED_BY_POLICY
    assert receipt["online_preflight"]["online_execution_authorized"] is False


def test_gateway_ask_structured_fails_closed_without_physical_auth(tmp_path: Path, monkeypatch) -> None:
    from nexus.services.gateway import BattlesuitGateway

    monkeypatch.delenv("NEXUS_EXTERNAL_RUNTIME_AUTHORIZED", raising=False)
    gateway = BattlesuitGateway(project_root=tmp_path)
    data, raw = gateway.ask_structured("prompt", "payload", phase="R")
    assert raw == "online_execution_not_authorized"
    assert isinstance(data, dict)
    assert data.get("error") == "online_execution_not_authorized"


def test_guard_physical_online_deny_blocks_and_binds(tmp_path: Path, monkeypatch) -> None:
    from nexus.services.online_execution_policy import guard_physical_online

    monkeypatch.delenv("NEXUS_EXTERNAL_RUNTIME_AUTHORIZED", raising=False)
    # Workspace allows auto, task denies — deny wins.
    policy_path = tmp_path / ".nexus" / "online_execution_policy.json"
    policy_path.parent.mkdir(parents=True)
    policy_path.write_text(
        json.dumps({"default_online_policy": "auto", "approved_online_providers": ["gemini"]}),
        encoding="utf-8",
    )

    class _GW:
        def __init__(self):
            self._online_execution_decision = None
            self.oauth_provider = "gemini"

        def bind_online_execution_decision(self, decision):
            self._online_execution_decision = decision

    gw = _GW()
    meta = {"online_policy": "deny", "task_id": "g1"}
    allowed, decision, denied = guard_physical_online(
        gw,
        meta,
        project_root=tmp_path,
        requested_provider="gemini",
        task_id="g1",
    )
    assert allowed is False
    assert denied is not None
    assert denied[1] == "online_execution_not_authorized"
    assert denied[0]["provider_call_count"] == 0
    assert decision.online_policy == "deny"
    assert gw._online_execution_decision is decision
    assert meta["online_execution_authorized"] is False


def test_guard_physical_online_auto_allows_under_workspace_deny(tmp_path: Path) -> None:
    from nexus.services.online_execution_policy import guard_physical_online

    policy_path = tmp_path / ".nexus" / "online_execution_policy.json"
    policy_path.parent.mkdir(parents=True)
    policy_path.write_text(
        json.dumps({"default_online_policy": "deny", "approved_online_providers": ["gemini"]}),
        encoding="utf-8",
    )

    class _GW:
        def __init__(self):
            self._online_execution_decision = None

        def bind_online_execution_decision(self, decision):
            self._online_execution_decision = decision

        def _online_physical_allowed(self):
            d = self._online_execution_decision
            return bool(d and d.online_execution_authorized and d.physical_invocation_allowed)

    gw = _GW()
    meta = {"online_policy": "auto", "task_id": "g2"}
    allowed, decision, denied = guard_physical_online(
        gw,
        meta,
        project_root=tmp_path,
        requested_provider="gemini",
        environ={"GEMINI_API_KEY": "k"},
        task_id="g2",
    )
    assert allowed is True
    assert denied is None
    assert decision.physical_invocation_allowed is True
    assert gw._online_physical_allowed() is True


def test_gateway_unbound_physical_always_false(tmp_path: Path, monkeypatch) -> None:
    from nexus.services.gateway import BattlesuitGateway

    monkeypatch.setenv("NEXUS_EXTERNAL_RUNTIME_AUTHORIZED", "1")
    # Workspace auto would previously re-resolve unbound — must not authorize alone.
    policy_path = tmp_path / ".nexus" / "online_execution_policy.json"
    policy_path.parent.mkdir(parents=True)
    policy_path.write_text(
        json.dumps({"default_online_policy": "auto", "approved_online_providers": ["gemini"]}),
        encoding="utf-8",
    )
    gateway = BattlesuitGateway(project_root=tmp_path)
    gateway._online_execution_decision = None
    assert gateway._online_physical_allowed() is False


def test_task_auto_binds_gateway_physical_under_workspace_deny(tmp_path: Path, monkeypatch) -> None:
    """CLI/task auto must authorize Gateway physical path when decision is bound.

    Workspace deny must not re-resolve and revoke a task auto grant.
    """
    from nexus.services.gateway import BattlesuitGateway
    from nexus.services.unified_runtime import UnifiedRuntime, UnifiedRuntimeRequest

    monkeypatch.delenv("NEXUS_EXTERNAL_RUNTIME_AUTHORIZED", raising=False)
    policy_path = tmp_path / ".nexus" / "online_execution_policy.json"
    policy_path.parent.mkdir(parents=True)
    policy_path.write_text(
        json.dumps({"default_online_policy": "deny", "approved_online_providers": ["gemini"]}),
        encoding="utf-8",
    )

    decision = resolve_online_execution_decision(
        task_online_policy="auto",
        project_root=tmp_path,
        planner_online_needed=True,
        requested_provider="gemini",
        environ={"GEMINI_API_KEY": "test-key"},
    )
    assert decision.online_execution_authorized is True
    assert decision.physical_invocation_allowed is True
    assert decision.online_authorization_source == "cli_task_policy"

    gateway = BattlesuitGateway(project_root=tmp_path)
    # Unbound: workspace deny → fail closed
    assert gateway._online_physical_allowed() is False
    # Bound task auto decision → physical allowed
    gateway.bind_online_execution_decision(decision)
    assert gateway._online_physical_allowed() is True

    # Repair-style: UR context decision must bind before Gateway callable.
    bound: list[object] = []

    def online_invoker(context):
        from nexus.services.online_execution_policy import decision_from_context

        d = decision_from_context(context)
        assert d is not None
        assert d.physical_invocation_allowed is True
        gateway.bind_online_execution_decision(d)
        bound.append(d)
        assert gateway._online_physical_allowed() is True
        return {
            "provider": "gemini",
            "task_id": str(context.get("task_id", "")),
            "invoked": True,
            "output_delivered": True,
            "gate_passed": True,
            "provider_call_count": 1,
            "response": {"status": "APPROVED", "patch": "ok"},
            "raw_response": "raw-ok",
            "usage": {},
            "error": "",
            "evidence_refs": [f"online:{context.get('task_id')}:bound"],
        }

    def verifier(context):
        return {
            "task_id": "auto-bind",
            "status": "pass",
            "gate_passed": True,
            "invoked": True,
            "evidence_refs": ["v"],
        }

    def learning(context):
        return {
            "task_id": "auto-bind",
            "status": "pass",
            "gate_passed": True,
            "invoked": True,
            "evidence_refs": ["l"],
        }

    receipt = UnifiedRuntime().run(
        UnifiedRuntimeRequest(
            task_id="auto-bind",
            workspace_revision="rev-auto",
            task_statement="bounded advisory",
            task_type="repair",
            route={
                "recommended_flow": "direct",
                "online_policy": "auto",
                "provider": "gemini",
                "workspace_root": str(tmp_path),
            },
            online_prompt="prompt",
            online_payload="payload",
        ),
        online_invoker=online_invoker,
        verifier=verifier,
        learning=learning,
    )
    assert bound, "online invoker must receive and bind decision"
    assert receipt["online"]["invoked"] is True
    assert receipt["online"]["status"] == "SUCCEEDED"
    assert receipt["online_preflight"]["online_execution_authorized"] is True
    assert receipt["online_preflight"]["physical_invocation_allowed"] is True
    assert receipt["online_preflight"]["online_authorization_source"] == "cli_task_policy"
