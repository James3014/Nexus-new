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
        environ={},
    )
    assert decision.online_policy == "auto"
    assert decision.online_execution_authorized is True
    assert decision.physical_invocation_allowed is True
    assert decision.online_authorization_source == "workspace_policy"
    assert decision.preflight_status == ONLINE_READY


def test_env_override_is_only_emergency_source(tmp_path: Path) -> None:
    # No workspace policy file → deny default, env elevates to auto.
    decision = resolve_online_execution_decision(
        task_online_policy="",
        project_root=tmp_path,
        planner_online_needed=True,
        requested_provider="gemini",
        environ={"NEXUS_EXTERNAL_RUNTIME_AUTHORIZED": "1"},
    )
    assert decision.online_execution_authorized is True
    assert decision.online_authorization_source == "operator_environment_override"


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
        environ={"NEXUS_EXTERNAL_RUNTIME_AUTHORIZED": "1"},
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
