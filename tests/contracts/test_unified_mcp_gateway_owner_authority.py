"""Characterization tests for the gateway's owner authority (big-file split G9b).

These pin the owner-effect authority check (``_require_owner_effect_authority``,
``_owner_effect_key``, ``_standing_key``), the Owner standing-grant issuance with its host
confirmation and audit (``_owner_standing_grant_issue``, ``_confirm_with_owner``,
``_append_owner_confirmation_audit``) and the task-card authority switch/restore
(``_task_card_authority_switch``, ``_task_card_authority_restore``) of ``UnifiedMCPGateway``
before they move out of the facade class into a mixin.

The authority collaborators (``bootstrap_agent_authority``, ``_current_controller_binding``,
``authorize_durable_standing_grant_effect``, the standing-grant store reads and writes,
``StandingGrantContext`` / ``StandingGrantReceipt`` issuance, ``OwnerConfirmationRequest``,
``switch_task_card_authority`` / ``restore_task_card_authority`` and ``_text``) are replaced
on the gateway facade module with recording probes that delegate to the real code against
an isolated store. The tests therefore pin the order of owner identity checks, grant
validation, store reads and writes, key derivation, host confirmation and audit receipts on
every success and denial path, and that facade patches keep reaching the moved code.
"""

from __future__ import annotations

import json
import os
import stat
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest

import nexus.orchestrator.standing_grant_store as sg_store
from nexus.contracts.autonomy_goal import AutonomyActionClass, StandingGrantContext
from nexus.orchestrator import bootstrap_agent_authority as real_bootstrap
from nexus.orchestrator import unified_mcp_gateway as gateway_module
from nexus.orchestrator.owner_confirmation import (
    OwnerConfirmationError,
    OwnerConfirmationEvidence,
    OwnerConfirmationRequest,
)
from nexus.orchestrator.standing_grant_store import (
    StandingGrantKey,
    StandingGrantReceipt,
    StandingGrantReceiptError,
)
from nexus.orchestrator.unified_mcp_gateway import (
    GITHUB_REPOSITORY,
    GatewayInputError,
    UnifiedMCPGateway,
)

REPO = "James3014/Nexus-new"
DURABLE = {"schema": "nexus.standing_grant_effect_authorization.v1", "authorization_hash": "d" * 64}
AGENT = {"schema": real_bootstrap.AUTHORIZATION_SCHEMA, "record_hash": "e" * 64}
SWITCHED = {"status": "SWITCHED", "temporary_receipt_hash": "7" * 64}
RESTORED = {"status": "RESTORED"}
H64 = "a" * 64


@pytest.fixture
def events() -> list[tuple]:
    return []


@pytest.fixture
def authority_dir(monkeypatch, tmp_path) -> Path:
    directory = tmp_path / "authority"
    monkeypatch.setattr(sg_store, "DEFAULT_RECEIPT_PATH", directory / "standing-grant.json")
    monkeypatch.setattr(sg_store, "DEFAULT_TRANSITIONS_DIR", directory / "transitions")
    return directory


@pytest.fixture
def probes(monkeypatch, events, authority_dir):
    """Replace the authority collaborators on the gateway facade with recording probes."""
    ctx = SimpleNamespace(
        delegation=None,
        agent_error=None,
        durable_error=None,
        structural=None,
        readback=None,
        write_error=None,
        switch_error=None,
        restore_error=None,
        calls={},
    )
    real_text = gateway_module._text
    real_binding = gateway_module._current_controller_binding

    def text(value, field, *, max_length=4096):
        events.append(("_text", field, max_length))
        return real_text(value, field, max_length=max_length)

    def binding():
        events.append(("_current_controller_binding",))
        return real_binding()

    def delegation_context(action, *, source_root, controller_binding, expected_source_head):
        events.append(("bootstrap.delegation_context", action.value))
        ctx.calls["delegation_context"] = dict(
            source_root=source_root,
            controller_binding=controller_binding,
            expected_source_head=expected_source_head,
        )
        return ctx.delegation

    def authorize_agent(**kwargs):
        events.append(("bootstrap.authorize_bootstrap_agent_effect", kwargs["action"].value))
        ctx.calls["authorize_bootstrap_agent_effect"] = kwargs
        if ctx.agent_error is not None:
            raise ctx.agent_error
        return dict(AGENT)

    def authorize_durable(**kwargs):
        events.append(("authorize_durable_standing_grant_effect", kwargs["action"].value))
        ctx.calls["authorize_durable_standing_grant_effect"] = kwargs
        if ctx.durable_error is not None:
            raise ctx.durable_error
        return dict(DURABLE)

    def load_structural(key):
        events.append(("store.load_keyed_standing_grant_receipt_structural", key.goal_id))
        if ctx.structural is not None:
            return ctx.structural
        return sg_store.load_keyed_standing_grant_receipt_structural(key)

    def write(receipt, *, expected_receipt_hash=None):
        events.append(("store.write_keyed_standing_grant_receipt", expected_receipt_hash))
        if ctx.write_error is not None:
            raise ctx.write_error
        return sg_store.write_keyed_standing_grant_receipt(
            receipt, expected_receipt_hash=expected_receipt_hash
        )

    def load(key, *, now=None):
        events.append(("store.load_keyed_standing_grant_receipt", key.goal_id))
        if ctx.readback is not None:
            return ctx.readback(key, now)
        return sg_store.load_keyed_standing_grant_receipt(key, now=now)

    def context_issue(**kwargs):
        events.append(("StandingGrantContext.issue", kwargs["goal_id"]))
        return StandingGrantContext.issue(**kwargs)

    def receipt_issue(**kwargs):
        events.append(("StandingGrantReceipt.issue", kwargs["grant_id"][:6]))
        return StandingGrantReceipt.issue(**kwargs)

    def request_build(**kwargs):
        events.append(("OwnerConfirmationRequest.build", kwargs["tool"]))
        ctx.calls["build"] = kwargs
        return OwnerConfirmationRequest.build(**kwargs)

    def switch(**kwargs):
        events.append(("store.switch_task_card_authority", kwargs["attempt_key"]))
        ctx.calls["switch"] = kwargs
        if ctx.switch_error is not None:
            raise ctx.switch_error
        return dict(SWITCHED)

    def restore(**kwargs):
        events.append(("store.restore_task_card_authority", kwargs["attempt_key"]))
        ctx.calls["restore"] = kwargs
        if ctx.restore_error is not None:
            raise ctx.restore_error
        return dict(RESTORED)

    monkeypatch.setattr(gateway_module, "_text", text)
    monkeypatch.setattr(gateway_module, "_current_controller_binding", binding)
    monkeypatch.setattr(
        gateway_module,
        "bootstrap_agent_authority",
        SimpleNamespace(
            delegation_context=delegation_context,
            authorize_bootstrap_agent_effect=authorize_agent,
            BootstrapAgentAuthorityError=real_bootstrap.BootstrapAgentAuthorityError,
        ),
    )
    monkeypatch.setattr(
        gateway_module, "authorize_durable_standing_grant_effect", authorize_durable
    )
    monkeypatch.setattr(
        gateway_module, "load_keyed_standing_grant_receipt_structural", load_structural
    )
    monkeypatch.setattr(gateway_module, "write_keyed_standing_grant_receipt", write)
    monkeypatch.setattr(gateway_module, "load_keyed_standing_grant_receipt", load)
    monkeypatch.setattr(
        gateway_module, "StandingGrantContext", SimpleNamespace(issue=context_issue)
    )
    monkeypatch.setattr(
        gateway_module, "StandingGrantReceipt", SimpleNamespace(issue=receipt_issue)
    )
    monkeypatch.setattr(
        gateway_module, "OwnerConfirmationRequest", SimpleNamespace(build=request_build)
    )
    monkeypatch.setattr(gateway_module, "switch_task_card_authority", switch)
    monkeypatch.setattr(gateway_module, "restore_task_card_authority", restore)
    return ctx


class _Channel:
    """Host double: accepts, refuses, or answers for another request."""

    def __init__(self, events: list[tuple], mode: str = "accept") -> None:
        self.events = events
        self.mode = mode
        self.requests: list[OwnerConfirmationRequest] = []

    def confirm(self, request: OwnerConfirmationRequest) -> OwnerConfirmationEvidence:
        self.events.append(("channel.confirm", request.tool))
        self.requests.append(request)
        if self.mode == "refuse":
            raise OwnerConfirmationError("OWNER_CONFIRMATION_DECLINED")
        return OwnerConfirmationEvidence(
            schema="nexus.owner_confirmation_evidence.v1",
            assurance_level="TEST_DOUBLE",
            channel="test",
            tool=request.tool,
            draft_hash="0" * 64 if self.mode == "other-draft" else request.draft_hash,
            message_sha256="0" * 64,
            request_id="other" if self.mode == "other-request" else request.request_id,
            nonce=request.nonce,
            requested_at=request.requested_at.isoformat(),
            responded_at=request.requested_at.isoformat(),
            deadline=request.deadline.isoformat(),
            action="accept",
            protocol_version="2025-06-18",
            client_info={},
            local_principal="test",
        )


def _gateway(events: list[tuple], mode: str = "accept") -> UnifiedMCPGateway:
    gateway = UnifiedMCPGateway(
        service=MagicMock(), owner_confirmation_channel=_Channel(events, mode)
    )
    real_confirm = gateway._confirm_with_owner
    real_audit = gateway._append_owner_confirmation_audit
    real_standing_key = gateway._standing_key

    def confirm(**kwargs):
        events.append(("self._confirm_with_owner", kwargs["tool"]))
        return real_confirm(**kwargs)

    def audit(record):
        events.append(("self._append_owner_confirmation_audit", record.get("schema")))
        return real_audit(record)

    def standing_key(goal_id, thread_id):
        events.append(("self._standing_key", goal_id, thread_id))
        return real_standing_key(goal_id, thread_id)

    gateway._confirm_with_owner = confirm  # type: ignore[method-assign]
    gateway._append_owner_confirmation_audit = audit  # type: ignore[method-assign]
    gateway._standing_key = standing_key  # type: ignore[method-assign]
    return gateway


def _names(events: list[tuple]) -> list[str]:
    return [event[0] for event in events]


def _audit_lines(directory: Path) -> list[dict[str, Any]]:
    path = directory / "owner-confirmations.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _key(goal: str = "goal-g9", scope: str = "thread-g9") -> StandingGrantKey:
    return StandingGrantKey(GITHUB_REPOSITORY, goal, scope)


# --- _owner_effect_key / _standing_key -----------------------------------------------------


def test_owner_effect_key_reads_the_explicit_goal_and_scope(events, probes) -> None:
    key = UnifiedMCPGateway._owner_effect_key({
        "authority_goal_id": " goal-g9 ",
        "authority_coordination_scope_id": "thread-g9",
    })
    assert key == _key()
    assert key.repository is GITHUB_REPOSITORY
    assert events == [
        ("_text", "authority_goal_id", 128),
        ("_text", "authority_coordination_scope_id", 128),
    ]


@pytest.mark.parametrize(
    ("arguments", "message"),
    [
        ({}, "^OWNER_AUTHORITY_KEY_REQUIRED:authority_goal_id is required$"),
        (
            {"authority_goal_id": "g"},
            "^OWNER_AUTHORITY_KEY_REQUIRED:authority_coordination_scope_id is required$",
        ),
        (
            {"authority_goal_id": "g" * 129, "authority_coordination_scope_id": "t"},
            "^OWNER_AUTHORITY_KEY_REQUIRED:authority_goal_id exceeds 128 characters$",
        ),
        (
            {"authority_goal_id": "bad goal", "authority_coordination_scope_id": "t"},
            "^OWNER_AUTHORITY_KEY_REQUIRED:",
        ),
        (
            {"authority_goal_id": "g", "authority_coordination_scope_id": "-lead"},
            "^OWNER_AUTHORITY_KEY_REQUIRED:",
        ),
    ],
)
def test_owner_effect_key_denials(events, probes, arguments, message) -> None:
    with pytest.raises(GatewayInputError, match=message):
        UnifiedMCPGateway._owner_effect_key(arguments)


def test_standing_key_builds_the_repository_key() -> None:
    assert UnifiedMCPGateway._standing_key("goal-g9", "thread-g9") == _key()


@pytest.mark.parametrize(("goal", "thread"), [("bad goal", "t"), ("g", ""), ("g", " t")])
def test_standing_key_maps_invalid_ids(goal, thread) -> None:
    with pytest.raises(GatewayInputError, match="^OWNER_AUTHORITY_KEY_REQUIRED:"):
        UnifiedMCPGateway._standing_key(goal, thread)


# --- _require_owner_effect_authority ------------------------------------------------------


EFFECT = {"campaign_id": "c", "task_id": "t"}


def test_authority_without_delegation_uses_the_durable_grant(events, probes, monkeypatch) -> None:
    monkeypatch.setattr(gateway_module, "LOADED_SOURCE_ROOT", "/probe/loaded")
    monkeypatch.setattr(gateway_module, "SERVER_REPO_HEAD_AT_START", "b" * 40)
    result = UnifiedMCPGateway._require_owner_effect_authority(
        AutonomyActionClass.TASK_CARD_CREATE, EFFECT, key=_key()
    )
    assert result == DURABLE
    assert events == [
        ("_current_controller_binding",),
        ("bootstrap.delegation_context", "TASK_CARD_CREATE"),
        ("authorize_durable_standing_grant_effect", "TASK_CARD_CREATE"),
    ]
    assert probes.calls["delegation_context"] == {
        "source_root": Path("/probe/loaded"),
        "controller_binding": gateway_module._current_controller_binding(),
        "expected_source_head": "b" * 40,
    }
    assert probes.calls["authorize_durable_standing_grant_effect"] == {
        "repository": GITHUB_REPOSITORY,
        "action": AutonomyActionClass.TASK_CARD_CREATE,
        "effect": EFFECT,
        "key": _key(),
    }


def test_authority_with_delegation_uses_the_bootstrap_agent_record(
    events, probes, monkeypatch
) -> None:
    probes.delegation = {"operating_mode": {"mode": "BOOTSTRAP"}}
    monkeypatch.setattr(gateway_module, "SERVER_INSTANCE_ID", "probe-instance")
    result = UnifiedMCPGateway._require_owner_effect_authority(
        AutonomyActionClass.TASK_CARD_COMMIT, EFFECT, key=_key()
    )
    assert result == AGENT
    assert events == [
        ("_current_controller_binding",),
        ("bootstrap.delegation_context", "TASK_CARD_COMMIT"),
        ("bootstrap.authorize_bootstrap_agent_effect", "TASK_CARD_COMMIT"),
    ]
    assert probes.calls["authorize_bootstrap_agent_effect"] == {
        "repository": GITHUB_REPOSITORY,
        "action": AutonomyActionClass.TASK_CARD_COMMIT,
        "effect": EFFECT,
        "key": _key(),
        "context": probes.delegation,
        "record_directory": sg_store.DEFAULT_RECEIPT_PATH.parent,
        "server_instance_id": "probe-instance",
    }


def test_authority_bootstrap_refusal_never_falls_back_to_the_grant(events, probes) -> None:
    probes.delegation = {"operating_mode": {"mode": "BOOTSTRAP"}}
    probes.agent_error = real_bootstrap.BootstrapAgentAuthorityError("RECORD_WRITE_FAILED")
    with pytest.raises(GatewayInputError, match="^OWNER_AUTHORITY_REQUIRED:RECORD_WRITE_FAILED$"):
        UnifiedMCPGateway._require_owner_effect_authority(
            AutonomyActionClass.TASK_CARD_CREATE, EFFECT, key=_key()
        )
    assert "authorize_durable_standing_grant_effect" not in _names(events)


def test_authority_durable_refusal_is_mapped(events, probes) -> None:
    probes.durable_error = StandingGrantReceiptError("NO_RECEIPT")
    with pytest.raises(GatewayInputError, match="^OWNER_AUTHORITY_REQUIRED:NO_RECEIPT$"):
        UnifiedMCPGateway._require_owner_effect_authority(
            AutonomyActionClass.CANDIDATE_APPROVE, EFFECT, key=_key()
        )
    assert _names(events)[-1] == "authorize_durable_standing_grant_effect"


def test_authority_other_errors_propagate_unmapped(events, probes) -> None:
    probes.durable_error = RuntimeError("store exploded")
    with pytest.raises(RuntimeError, match="^store exploded$"):
        UnifiedMCPGateway._require_owner_effect_authority(
            AutonomyActionClass.TASK_CARD_CREATE, EFFECT, key=_key()
        )


def test_authority_real_delegation_context_keeps_the_grant_path_when_not_separate(
    events, probes, monkeypatch
) -> None:
    calls = []

    def real_context(action, **kwargs):
        calls.append(action)
        return real_bootstrap.delegation_context(action, **kwargs)

    gateway_module.bootstrap_agent_authority.delegation_context = real_context
    monkeypatch.setattr(gateway_module, "CONTROLLER_IS_SEPARATE", False)
    monkeypatch.setattr(gateway_module, "CONTROLLER_BINDING_PROBLEM", None)
    assert (
        UnifiedMCPGateway._require_owner_effect_authority(
            AutonomyActionClass.TASK_CARD_CREATE, EFFECT, key=_key()
        )
        == DURABLE
    )
    assert calls == [AutonomyActionClass.TASK_CARD_CREATE]


def test_authority_is_reached_from_the_public_task_card_tool(
    events, probes, monkeypatch, tmp_path
) -> None:
    monkeypatch.setattr(gateway_module, "CANONICAL_SOURCE_ROOT", tmp_path)
    monkeypatch.setattr(
        gateway_module, "_require_bound_controller", lambda expected_head=None: None
    )
    monkeypatch.setattr(gateway_module, "_git", lambda *args, **kwargs: "c" * 40 + "\n")
    probes.durable_error = StandingGrantReceiptError("NO_RECEIPT")
    response = UnifiedMCPGateway(service=MagicMock()).handle({
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": "nexus_task_card_create",
            "arguments": {
                "authority_goal_id": "goal-g9",
                "authority_coordination_scope_id": "thread-g9",
                "owner_confirmation": True,
                "campaign_id": "c",
                "task_id": "t",
                "objective": "o",
                "allowed_files": ["README.md"],
                "verifier_commands": ["true"],
            },
        },
    })
    assert response is not None
    assert response["result"]["isError"] is True
    assert "OWNER_AUTHORITY_REQUIRED:NO_RECEIPT" in response["result"]["structuredContent"]["error"]
    assert not (tmp_path / "tasks").exists()
    assert ("authorize_durable_standing_grant_effect", "TASK_CARD_CREATE") in events


# --- _owner_standing_grant_issue ----------------------------------------------------------


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _issue_args(**overrides: Any) -> dict[str, Any]:
    arguments: dict[str, Any] = {
        "repository": REPO,
        "coordinatorId": "coord-g9",
        "goalId": "goal-g9",
        "coordinationScopeId": "thread-g9",
        "allowedActions": ["TASK_SUBMIT", "REPOSITORY_PUSH"],
        "ttlMinutes": 30,
        "issuedAt": (_now() - timedelta(minutes=1)).isoformat(),
    }
    arguments.update(overrides)
    return {key: value for key, value in arguments.items() if value is not _DROP}


_DROP = object()
ISSUE_PREFIX = [
    ("_text", "coordinatorId", 128),
    ("_text", "goalId", 128),
    ("_text", "coordinationScopeId", 128),
    ("_text", "issuedAt", 64),
]
ISSUE_THROUGH_RECEIPT = ISSUE_PREFIX + [
    ("StandingGrantContext.issue", "goal-g9"),
    ("StandingGrantReceipt.issue", "owner-"),
    ("store.load_keyed_standing_grant_receipt_structural", "goal-g9"),
]
ASK = [
    ("self._confirm_with_owner", "nexus_owner_standing_grant_issue"),
    ("OwnerConfirmationRequest.build", "nexus_owner_standing_grant_issue"),
    ("channel.confirm", "nexus_owner_standing_grant_issue"),
    ("self._append_owner_confirmation_audit", "nexus.owner_confirmation_evidence.v1"),
]


def test_issue_call_order_receipt_and_audit(events, probes, authority_dir) -> None:
    gateway = _gateway(events)
    arguments = _issue_args()
    payload = gateway._call_tool("nexus_owner_standing_grant_issue", arguments)
    assert events == ISSUE_THROUGH_RECEIPT + ASK + [
        ("store.write_keyed_standing_grant_receipt", None),
        ("store.load_keyed_standing_grant_receipt", "goal-g9"),
        ("self._append_owner_confirmation_audit", "nexus.owner_confirmation_outcome.v1"),
    ]
    stored = sg_store.load_keyed_standing_grant_receipt(_key())
    assert stored is not None and stored.receipt_hash == payload["receipt_hash"]
    assert stored.context.owner_id == "James3014"
    assert stored.context.coordinator_id == "coord-g9"
    issued = datetime.fromisoformat(arguments["issuedAt"]).astimezone(timezone.utc)
    request_identity = {
        "repository": REPO,
        "coordinatorId": "coord-g9",
        "goalId": "goal-g9",
        "coordinationScopeId": "thread-g9",
        "allowedActions": ["REPOSITORY_PUSH", "TASK_SUBMIT"],
        "issuedAt": issued.isoformat(),
        "expiresAt": (issued + timedelta(minutes=30)).isoformat(),
        "expectedCurrentReceiptHash": None,
    }
    import hashlib

    request_hash = hashlib.sha256(
        json.dumps(
            request_identity, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode()
    ).hexdigest()
    confirmation = payload.pop("owner_confirmation")
    assert payload == {
        "schema": "nexus.owner_standing_grant_issuance.v1",
        "status": "ISSUED",
        "repository": REPO,
        "grant_id": f"owner-{request_hash[:24]}",
        "receipt_hash": stored.receipt_hash,
        "key_digest": _key().digest,
        "goal_id": "goal-g9",
        "coordination_scope_id": "thread-g9",
        "coordinator_id": "coord-g9",
        "allowed_actions": ["REPOSITORY_PUSH", "TASK_SUBMIT"],
        "issued_at": issued.isoformat(),
        "expires_at": (issued + timedelta(minutes=30)).isoformat(),
        "supersedes_grant_hash": None,
        "request_hash": request_hash,
        "idempotent_replay": False,
        "merge_performed": False,
        "claim_ceiling": "STANDING_GRANT_ISSUED_ONLY",
    }
    assert confirmation["draft"] == {
        **request_identity,
        "ownerId": "James3014",
        "receiptHash": stored.receipt_hash,
    }
    build = probes.calls["build"]
    assert build["summary_lines"] == (
        f"Repository: {REPO}",
        "Goal: goal-g9",
        "Coordination scope: thread-g9",
        "Coordinator: coord-g9",
        "Allowed actions: REPOSITORY_PUSH, TASK_SUBMIT",
        f"Valid: {issued.isoformat()} -> {(issued + timedelta(minutes=30)).isoformat()}",
        "Supersedes: none",
    )
    assert build["not_after"] == issued + timedelta(minutes=30)
    lines = _audit_lines(authority_dir)
    assert [line.get("schema") for line in lines] == [
        "nexus.owner_confirmation_evidence.v1",
        "nexus.owner_confirmation_outcome.v1",
    ]
    assert lines[0] == confirmation
    assert lines[1] == {
        "schema": "nexus.owner_confirmation_outcome.v1",
        "evidence_hash": confirmation["evidence_hash"],
        "outcome": "ISSUED",
        "receipt_hash": stored.receipt_hash,
    }


def test_issue_replay_asks_nobody_and_writes_nothing(events, probes, authority_dir) -> None:
    gateway = _gateway(events)
    arguments = _issue_args()
    first = gateway._owner_standing_grant_issue(arguments)
    events.clear()
    replay = gateway._owner_standing_grant_issue(arguments)
    assert events == ISSUE_THROUGH_RECEIPT
    assert replay["status"] == "REPLAYED" and replay["idempotent_replay"] is True
    assert replay["receipt_hash"] == first["receipt_hash"]
    assert replay["owner_confirmation"] is None
    assert len(_audit_lines(authority_dir)) == 2


def test_issue_successor_requires_and_binds_the_predecessor(events, probes, authority_dir) -> None:
    gateway = _gateway(events)
    first = gateway._owner_standing_grant_issue(_issue_args())
    events.clear()
    successor = gateway._owner_standing_grant_issue(
        _issue_args(
            allowedActions=["TASK_SUBMIT"], expectedCurrentReceiptHash=first["receipt_hash"].upper()
        )
    )
    assert events == ISSUE_PREFIX + [
        ("_text", "expectedCurrentReceiptHash", 64),
        ("StandingGrantContext.issue", "goal-g9"),
        ("StandingGrantReceipt.issue", "owner-"),
        ("store.load_keyed_standing_grant_receipt_structural", "goal-g9"),
        *ASK,
        ("store.write_keyed_standing_grant_receipt", first["receipt_hash"]),
        ("store.load_keyed_standing_grant_receipt", "goal-g9"),
        ("self._append_owner_confirmation_audit", "nexus.owner_confirmation_outcome.v1"),
    ]
    assert successor["supersedes_grant_hash"] == first["receipt_hash"]
    assert successor["status"] == "ISSUED"
    assert probes.calls["build"]["summary_lines"][-1] == f"Supersedes: {first['receipt_hash']}"


@pytest.mark.parametrize("value", [True, False, None])
def test_issue_refuses_a_model_supplied_confirmation_first(events, probes, value) -> None:
    with pytest.raises(GatewayInputError, match="^OWNER_CONFIRMATION_PARAMETER_REMOVED$"):
        _gateway(events)._owner_standing_grant_issue({
            **_issue_args(),
            "ownerConfirmation": value,
            "shell": "x",
        })
    assert events == []


@pytest.mark.parametrize(
    ("overrides", "message", "last"),
    [
        ({"shell": "x", "argv": 1}, "^unknown arguments: argv, shell$", None),
        ({"repository": "James3014/other"}, "^STANDING_GRANT_REPOSITORY_MISMATCH$", None),
        ({"repository": _DROP}, "^STANDING_GRANT_REPOSITORY_MISMATCH$", None),
        ({"coordinatorId": ""}, "^coordinatorId is required$", ("_text", "coordinatorId", 128)),
        ({"goalId": "g" * 129}, "^goalId exceeds 128 characters$", ("_text", "goalId", 128)),
        (
            {"coordinationScopeId": None},
            "^coordinationScopeId is required$",
            ("_text", "coordinationScopeId", 128),
        ),
        (
            {"allowedActions": "TASK_SUBMIT"},
            "^allowedActions must contain between 1 and 8 actions$",
            ("_text", "coordinationScopeId", 128),
        ),
        (
            {"allowedActions": []},
            "^allowedActions must contain between 1 and 8 actions$",
            ("_text", "coordinationScopeId", 128),
        ),
        (
            {"allowedActions": ["TASK_SUBMIT"] * 9},
            "^allowedActions must contain between 1 and 8 actions$",
            ("_text", "coordinationScopeId", 128),
        ),
        (
            {"allowedActions": ["NOT_AN_ACTION"]},
            "^STANDING_GRANT_ACTION_INVALID:NOT_AN_ACTION$",
            ("_text", "coordinationScopeId", 128),
        ),
        (
            {"allowedActions": ["TASK_SUBMIT", "TASK_SUBMIT"]},
            "^STANDING_GRANT_ACTION_DUPLICATE$",
            ("_text", "coordinationScopeId", 128),
        ),
        (
            {"allowedActions": ["TASK_SUBMIT", "GITHUB_MERGE"]},
            "^STANDING_GRANT_ACTION_REQUIRES_SCOPE_ENFORCEMENT:GITHUB_MERGE$",
            ("_text", "coordinationScopeId", 128),
        ),
        (
            {"allowedActions": ["CANDIDATE_INTEGRATE"]},
            "^STANDING_GRANT_ACTION_REQUIRES_SCOPE_ENFORCEMENT:CANDIDATE_INTEGRATE$",
            ("_text", "coordinationScopeId", 128),
        ),
        (
            {"allowedActions": ["PRODUCTION_RELEASE"]},
            "^STANDING_GRANT_ACTION_REQUIRES_SCOPE_ENFORCEMENT:PRODUCTION_RELEASE$",
            ("_text", "coordinationScopeId", 128),
        ),
        (
            {"allowedActions": ["RUNTIME_ACTIVATE"]},
            "^STANDING_GRANT_ACTION_REQUIRES_SCOPE_ENFORCEMENT:RUNTIME_ACTIVATE$",
            ("_text", "coordinationScopeId", 128),
        ),
        (
            {"allowedActions": ["OWNER_REPRESENTATION_GRANT_ISSUE"]},
            "^STANDING_GRANT_ACTION_REQUIRES_SCOPE_ENFORCEMENT:OWNER_REPRESENTATION_GRANT_ISSUE$",
            ("_text", "coordinationScopeId", 128),
        ),
        (
            {"ttlMinutes": True},
            "^ttlMinutes must be an integer between 1 and 60$",
            ("_text", "coordinationScopeId", 128),
        ),
        (
            {"ttlMinutes": "30"},
            "^ttlMinutes must be an integer between 1 and 60$",
            ("_text", "coordinationScopeId", 128),
        ),
        (
            {"ttlMinutes": 0},
            "^ttlMinutes must be an integer between 1 and 60$",
            ("_text", "coordinationScopeId", 128),
        ),
        (
            {"ttlMinutes": 61},
            "^ttlMinutes must be an integer between 1 and 60$",
            ("_text", "coordinationScopeId", 128),
        ),
        (
            {"ttlMinutes": _DROP},
            "^ttlMinutes must be an integer between 1 and 60$",
            ("_text", "coordinationScopeId", 128),
        ),
        ({"issuedAt": ""}, "^issuedAt is required$", ("_text", "issuedAt", 64)),
        (
            {"issuedAt": "yesterday"},
            "^STANDING_GRANT_ISSUED_AT_INVALID$",
            ("_text", "issuedAt", 64),
        ),
        (
            {"issuedAt": "2026-10-17T00:00:00"},
            "^STANDING_GRANT_ISSUED_AT_TIMEZONE_REQUIRED$",
            ("_text", "issuedAt", 64),
        ),
        (
            {"issuedAt": (_now() + timedelta(minutes=5)).isoformat()},
            "^STANDING_GRANT_ISSUED_AT_FUTURE$",
            ("_text", "issuedAt", 64),
        ),
        (
            {"issuedAt": (_now() - timedelta(minutes=31)).isoformat()},
            "^STANDING_GRANT_REQUEST_EXPIRED$",
            ("_text", "issuedAt", 64),
        ),
        (
            {"expectedCurrentReceiptHash": "abc"},
            "^expectedCurrentReceiptHash must be a lowercase 64-hex SHA-256$",
            ("_text", "expectedCurrentReceiptHash", 64),
        ),
        (
            {"expectedCurrentReceiptHash": "a" * 65},
            "^expectedCurrentReceiptHash exceeds 64 characters$",
            ("_text", "expectedCurrentReceiptHash", 64),
        ),
        (
            {"expectedCurrentReceiptHash": ""},
            "^expectedCurrentReceiptHash is required$",
            ("_text", "expectedCurrentReceiptHash", 64),
        ),
    ],
)
def test_issue_argument_denials_stop_before_any_store_access(
    events, probes, authority_dir, overrides, message, last
) -> None:
    with pytest.raises(GatewayInputError, match=message):
        _gateway(events)._owner_standing_grant_issue(_issue_args(**overrides))
    assert (events[-1] if events else None) == last
    assert not any(
        name.startswith(("store.", "Standing", "self._", "channel")) for name in _names(events)
    )
    assert _audit_lines(authority_dir) == []


def test_issue_accepts_a_zulu_timestamp(events, probes) -> None:
    issued = (_now() - timedelta(minutes=2)).isoformat().replace("+00:00", "Z")
    assert (
        _gateway(events)._owner_standing_grant_issue(_issue_args(issuedAt=issued))["status"]
        == "ISSUED"
    )


def test_issue_invalid_identity_fails_in_grant_validation_before_the_store(events, probes) -> None:
    with pytest.raises(Exception) as caught:
        _gateway(events)._owner_standing_grant_issue(_issue_args(goalId="bad goal"))
    assert not isinstance(caught.value, GatewayInputError)
    assert _names(events)[-1] == "StandingGrantContext.issue"


@pytest.mark.parametrize(
    ("expected", "message"),
    [
        (H64, "^EXPECTED_PREDECESSOR_MISSING$"),
    ],
)
def test_issue_missing_predecessor(events, probes, authority_dir, expected, message) -> None:
    with pytest.raises(GatewayInputError, match=message):
        _gateway(events)._owner_standing_grant_issue(
            _issue_args(expectedCurrentReceiptHash=expected)
        )
    assert _names(events)[-1] == "store.load_keyed_standing_grant_receipt_structural"
    assert _audit_lines(authority_dir) == []


@pytest.mark.parametrize(
    ("expected", "message"),
    [(None, "^CURRENT_RECEIPT_EXISTS_CAS_REQUIRED$"), ("b" * 64, "^CAS_MISMATCH$")],
)
def test_issue_cas_denials_ask_nobody(events, probes, authority_dir, expected, message) -> None:
    gateway = _gateway(events)
    gateway._owner_standing_grant_issue(_issue_args())
    events.clear()
    with pytest.raises(GatewayInputError, match=message):
        gateway._owner_standing_grant_issue(
            _issue_args(
                allowedActions=["TASK_SUBMIT"],
                expectedCurrentReceiptHash=expected if expected else _DROP,
            )
        )
    assert _names(events)[-1] == "store.load_keyed_standing_grant_receipt_structural"
    assert len(_audit_lines(authority_dir)) == 2


@pytest.mark.parametrize(
    ("current", "message"),
    [
        (
            SimpleNamespace(
                context=SimpleNamespace(
                    revoked_at=datetime.now(timezone.utc), issued_at=datetime.now(timezone.utc)
                ),
                receipt_hash=H64,
            ),
            "^REVOKED$",
        ),
        (
            SimpleNamespace(
                context=SimpleNamespace(
                    revoked_at=None, issued_at=datetime.now(timezone.utc) + timedelta(hours=1)
                ),
                receipt_hash=H64,
            ),
            "^NOT_YET_VALID$",
        ),
    ],
)
def test_issue_refuses_an_unusable_structural_predecessor(
    events, probes, authority_dir, current, message
) -> None:
    probes.structural = current
    with pytest.raises(GatewayInputError, match=message):
        _gateway(events)._owner_standing_grant_issue(_issue_args(expectedCurrentReceiptHash=H64))
    assert _names(events)[-1] == "store.load_keyed_standing_grant_receipt_structural"
    assert "channel.confirm" not in _names(events)


@pytest.mark.parametrize("mode", ["refuse", "other-draft", "other-request"])
def test_issue_without_a_clean_owner_confirmation_writes_nothing(
    events, probes, authority_dir, mode
) -> None:
    message = (
        "^OWNER_CONFIRMATION_DECLINED$"
        if mode == "refuse"
        else "^OWNER_CONFIRMATION_BINDING_MISMATCH$"
    )
    with pytest.raises(GatewayInputError, match=message):
        _gateway(events, mode)._owner_standing_grant_issue(_issue_args())
    assert _names(events)[-1] == "channel.confirm"
    assert "store.write_keyed_standing_grant_receipt" not in _names(events)
    assert _audit_lines(authority_dir) == []
    assert sg_store.load_keyed_standing_grant_receipt_structural(_key()) is None


def test_issue_audit_failure_writes_no_grant(events, probes, authority_dir, monkeypatch) -> None:
    def unsafe(directory, *, create):
        raise sg_store.StandingGrantReceiptError("UNSAFE_DIR")

    monkeypatch.setattr(sg_store, "_assert_dir_chain_safe", unsafe)
    with pytest.raises(GatewayInputError, match="^OWNER_CONFIRMATION_AUDIT_WRITE_FAILED$"):
        _gateway(events)._owner_standing_grant_issue(_issue_args(goalId="goal-audit"))
    assert _names(events)[-1] == "self._append_owner_confirmation_audit"
    assert "store.write_keyed_standing_grant_receipt" not in _names(events)


def test_issue_store_write_refusal_is_mapped(events, probes, authority_dir) -> None:
    probes.write_error = StandingGrantReceiptError("CAS_MISMATCH")
    with pytest.raises(GatewayInputError, match="^CAS_MISMATCH$"):
        _gateway(events)._owner_standing_grant_issue(_issue_args())
    assert _names(events)[-1] == "store.write_keyed_standing_grant_receipt"
    assert [line["schema"] for line in _audit_lines(authority_dir)] == [
        "nexus.owner_confirmation_evidence.v1"
    ]


@pytest.mark.parametrize(
    "readback", [lambda key, now: None, lambda key, now: SimpleNamespace(receipt_hash="0" * 64)]
)
def test_issue_readback_must_be_the_issued_receipt(events, probes, authority_dir, readback) -> None:
    probes.readback = readback
    with pytest.raises(GatewayInputError, match="^ISSUANCE_READBACK_MISMATCH$"):
        _gateway(events)._owner_standing_grant_issue(_issue_args())
    assert _names(events)[-1] == "store.load_keyed_standing_grant_receipt"
    assert [line["schema"] for line in _audit_lines(authority_dir)] == [
        "nexus.owner_confirmation_evidence.v1"
    ]


def test_issue_without_a_host_channel_fails_closed(events, probes, authority_dir) -> None:
    gateway = UnifiedMCPGateway(service=MagicMock())
    with pytest.raises(GatewayInputError):
        gateway._owner_standing_grant_issue(_issue_args())
    assert "store.write_keyed_standing_grant_receipt" not in _names(events)
    assert sg_store.load_keyed_standing_grant_receipt_structural(_key()) is None


def test_issue_public_tool_reports_denials_as_tool_errors(events, probes) -> None:
    response = _gateway(events).handle({
        "jsonrpc": "2.0",
        "id": 3,
        "method": "tools/call",
        "params": {
            "name": "nexus_owner_standing_grant_issue",
            "arguments": {**_issue_args(), "shell": "x"},
        },
    })
    assert response is not None
    assert response["result"]["isError"] is True
    assert "unknown arguments: shell" in response["result"]["structuredContent"]["error"]
    assert events == []


# --- _confirm_with_owner / _append_owner_confirmation_audit --------------------------------


def test_confirm_with_owner_builds_the_request_and_records_the_answer(
    events, probes, authority_dir
) -> None:
    gateway = _gateway(events)
    now = _now()
    record = UnifiedMCPGateway._confirm_with_owner(
        gateway,
        tool="probe_tool",
        draft={"b": 1, "a": 2},
        summary_lines=("line",),
        now=now,
        not_after=now + timedelta(seconds=30),
    )
    assert events == [
        ("OwnerConfirmationRequest.build", "probe_tool"),
        ("channel.confirm", "probe_tool"),
        ("self._append_owner_confirmation_audit", "nexus.owner_confirmation_evidence.v1"),
    ]
    channel = gateway._owner_confirmation_channel
    assert isinstance(channel, _Channel)
    request = channel.requests[0]
    assert request.deadline == now + timedelta(seconds=30)
    assert record["draft"] == {"b": 1, "a": 2}
    assert record["draft_hash"] == request.draft_hash and record["request_id"] == request.request_id
    evidence = OwnerConfirmationEvidence(**{
        k: v for k, v in record.items() if k not in ("evidence_hash", "draft")
    })
    assert record["evidence_hash"] == evidence.evidence_hash
    assert _audit_lines(authority_dir) == [record]


@pytest.mark.parametrize("mode", ["refuse", "other-draft", "other-request"])
def test_confirm_with_owner_denials_record_nothing(events, probes, authority_dir, mode) -> None:
    now = _now()
    with pytest.raises(GatewayInputError):
        UnifiedMCPGateway._confirm_with_owner(
            _gateway(events, mode),
            tool="t",
            draft={},
            summary_lines=(),
            now=now,
            not_after=now + timedelta(minutes=1),
        )
    assert _audit_lines(authority_dir) == []
    assert "self._append_owner_confirmation_audit" not in _names(events)


def test_audit_appends_sorted_json_lines_with_owner_only_mode(authority_dir) -> None:
    UnifiedMCPGateway._append_owner_confirmation_audit({"b": 2, "a": "é"})
    UnifiedMCPGateway._append_owner_confirmation_audit({"c": 3})
    path = authority_dir / "owner-confirmations.jsonl"
    assert path.read_text(encoding="utf-8") == '{"a": "é", "b": 2}\n{"c": 3}\n'
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600
    assert stat.S_IMODE(os.stat(authority_dir).st_mode) == 0o700


def test_audit_refuses_a_symlinked_log(authority_dir, tmp_path) -> None:
    UnifiedMCPGateway._append_owner_confirmation_audit({"seed": True})
    path = authority_dir / "owner-confirmations.jsonl"
    path.unlink()
    target = tmp_path / "elsewhere.jsonl"
    target.write_text("", encoding="utf-8")
    path.symlink_to(target)
    with pytest.raises(GatewayInputError, match="^OWNER_CONFIRMATION_AUDIT_WRITE_FAILED$"):
        UnifiedMCPGateway._append_owner_confirmation_audit({"x": 1})
    assert target.read_text(encoding="utf-8") == ""


def test_audit_refuses_an_unsafe_directory(authority_dir, tmp_path) -> None:
    authority_dir.parent.mkdir(parents=True, exist_ok=True)
    authority_dir.mkdir(mode=0o777)
    os.chmod(authority_dir, 0o777)
    with pytest.raises(GatewayInputError, match="^OWNER_CONFIRMATION_AUDIT_WRITE_FAILED$"):
        UnifiedMCPGateway._append_owner_confirmation_audit({"x": 1})
    assert not (authority_dir / "owner-confirmations.jsonl").exists()


# --- _task_card_authority_switch -----------------------------------------------------------


def _switch_args(**overrides: Any) -> dict[str, Any]:
    arguments: dict[str, Any] = {
        "attemptKey": "attempt-g9",
        "expectedCurrentReceiptHash": H64.upper(),
        "expectedCurrentGoalId": "goal-g9",
        "expectedCurrentThreadId": "thread-g9",
        "successorGoalId": "goal-next",
        "successorThreadId": "thread-next",
        "ttlMinutes": 15,
    }
    arguments.update(overrides)
    return {key: value for key, value in arguments.items() if value is not _DROP}


SWITCH_TEXT = [
    ("_text", "attemptKey", 128),
    ("_text", "expectedCurrentReceiptHash", 64),
    ("_text", "expectedCurrentGoalId", 128),
    ("_text", "expectedCurrentThreadId", 128),
    ("_text", "successorGoalId", 128),
    ("_text", "successorThreadId", 128),
]


def test_switch_call_order_confirmation_and_store_call(events, probes, authority_dir) -> None:
    gateway = _gateway(events)
    result = gateway._call_tool("nexus_task_card_authority_switch", _switch_args())
    assert result == SWITCHED
    assert events == SWITCH_TEXT + [
        ("self._confirm_with_owner", "nexus_task_card_authority_switch"),
        ("OwnerConfirmationRequest.build", "nexus_task_card_authority_switch"),
        ("channel.confirm", "nexus_task_card_authority_switch"),
        ("self._append_owner_confirmation_audit", "nexus.owner_confirmation_evidence.v1"),
        ("self._standing_key", "goal-g9", "thread-g9"),
        ("store.switch_task_card_authority", "attempt-g9"),
    ]
    assert probes.calls["switch"] == {
        "current_key": _key(),
        "attempt_key": "attempt-g9",
        "expected_current_receipt_hash": H64,
        "expected_current_goal_id": "goal-g9",
        "successor_goal_id": "goal-next",
        "successor_thread_id": "thread-next",
        "ttl_minutes": 15,
        "owner_confirmation": True,
    }
    build = probes.calls["build"]
    assert build["draft"] == {
        "repository": REPO,
        "attemptKey": "attempt-g9",
        "expectedCurrentReceiptHash": H64,
        "expectedCurrentGoalId": "goal-g9",
        "expectedCurrentThreadId": "thread-g9",
        "successorGoalId": "goal-next",
        "successorThreadId": "thread-next",
        "allowedActions": ["TASK_CARD_COMMIT", "TASK_CARD_CREATE"],
        "ttlMinutes": 15,
    }
    assert build["summary_lines"] == (
        f"Repository: {REPO}",
        f"From grant: {H64} (goal goal-g9)",
        "New task-card scope: goal goal-next, thread thread-next",
        "Allowed actions: TASK_CARD_COMMIT, TASK_CARD_CREATE",
        "Valid for: 15 minutes (never beyond the current grant)",
    )
    assert build["not_after"] - build["now"] == timedelta(minutes=15)
    assert len(_audit_lines(authority_dir)) == 1


@pytest.mark.parametrize("value", [True, False])
def test_switch_refuses_a_model_supplied_confirmation_first(events, probes, value) -> None:
    with pytest.raises(GatewayInputError, match="^OWNER_CONFIRMATION_PARAMETER_REMOVED$"):
        _gateway(events)._task_card_authority_switch({
            **_switch_args(),
            "ownerConfirmation": value,
            "x": 1,
        })
    assert events == []


@pytest.mark.parametrize(
    ("overrides", "message", "last"),
    [
        ({"argv": 1}, "^unknown arguments: argv$", None),
        ({"attemptKey": ""}, "^attemptKey is required$", ("_text", "attemptKey", 128)),
        (
            {"expectedCurrentReceiptHash": "xyz"},
            "^expectedCurrentReceiptHash must be a lowercase 64-hex SHA-256$",
            ("_text", "expectedCurrentReceiptHash", 64),
        ),
        (
            {"expectedCurrentReceiptHash": "a" * 65},
            "^expectedCurrentReceiptHash exceeds 64 characters$",
            ("_text", "expectedCurrentReceiptHash", 64),
        ),
        (
            {"expectedCurrentGoalId": _DROP},
            "^expectedCurrentGoalId is required$",
            ("_text", "expectedCurrentGoalId", 128),
        ),
        (
            {"expectedCurrentThreadId": "t" * 129},
            "^expectedCurrentThreadId exceeds 128 characters$",
            ("_text", "expectedCurrentThreadId", 128),
        ),
        (
            {"successorGoalId": None},
            "^successorGoalId is required$",
            ("_text", "successorGoalId", 128),
        ),
        (
            {"successorThreadId": ""},
            "^successorThreadId is required$",
            ("_text", "successorThreadId", 128),
        ),
        ({"ttlMinutes": _DROP}, "^ttlMinutes is required$", ("_text", "successorThreadId", 128)),
        ({"ttlMinutes": None}, "^ttlMinutes is required$", ("_text", "successorThreadId", 128)),
        (
            {"ttlMinutes": True},
            "^ttlMinutes must be an integer between 1 and 30$",
            ("_text", "successorThreadId", 128),
        ),
        (
            {"ttlMinutes": 0},
            "^ttlMinutes must be an integer between 1 and 30$",
            ("_text", "successorThreadId", 128),
        ),
        (
            {"ttlMinutes": 31},
            "^ttlMinutes must be an integer between 1 and 30$",
            ("_text", "successorThreadId", 128),
        ),
        (
            {"ttlMinutes": 1.5},
            "^ttlMinutes must be an integer between 1 and 30$",
            ("_text", "successorThreadId", 128),
        ),
    ],
)
def test_switch_argument_denials_ask_nobody(events, probes, overrides, message, last) -> None:
    with pytest.raises(GatewayInputError, match=message):
        _gateway(events)._task_card_authority_switch(_switch_args(**overrides))
    assert (events[-1] if events else None) == last


@pytest.mark.parametrize("mode", ["refuse", "other-draft"])
def test_switch_without_a_clean_confirmation_never_reaches_the_store(events, probes, mode) -> None:
    with pytest.raises(GatewayInputError):
        _gateway(events, mode)._task_card_authority_switch(_switch_args())
    assert _names(events)[-1] == "channel.confirm"
    assert "store.switch_task_card_authority" not in _names(events)


def test_switch_invalid_current_key_is_refused_after_confirmation(events, probes) -> None:
    with pytest.raises(GatewayInputError, match="^OWNER_AUTHORITY_KEY_REQUIRED:"):
        _gateway(events)._task_card_authority_switch(_switch_args(expectedCurrentGoalId="bad goal"))
    assert _names(events)[-2:] == ["self._append_owner_confirmation_audit", "self._standing_key"]
    assert "store.switch_task_card_authority" not in _names(events)


def test_switch_store_refusal_is_mapped(events, probes) -> None:
    probes.switch_error = StandingGrantReceiptError("SWITCH_CAS_MISMATCH")
    with pytest.raises(GatewayInputError, match="^SWITCH_CAS_MISMATCH$"):
        _gateway(events)._task_card_authority_switch(_switch_args())
    assert _names(events)[-1] == "store.switch_task_card_authority"


# --- _task_card_authority_restore ----------------------------------------------------------


def _restore_args(**overrides: Any) -> dict[str, Any]:
    arguments: dict[str, Any] = {
        "ownerConfirmation": True,
        "attemptKey": "attempt-r",
        "switchOperationId": "op-1",
        "expectedTemporaryReceiptHash": H64.upper(),
        "expectedCurrentGoalId": "goal-g9",
        "expectedCurrentThreadId": "thread-g9",
    }
    arguments.update(overrides)
    return {key: value for key, value in arguments.items() if value is not _DROP}


RESTORE_TEXT = [
    ("_text", "attemptKey", 128),
    ("_text", "switchOperationId", 128),
    ("_text", "expectedTemporaryReceiptHash", 64),
    ("_text", "expectedCurrentGoalId", 128),
    ("_text", "expectedCurrentThreadId", 128),
]


def test_restore_call_order_and_store_call(events, probes, authority_dir) -> None:
    result = _gateway(events)._call_tool("nexus_task_card_authority_restore", _restore_args())
    assert result == RESTORED
    assert events == RESTORE_TEXT + [
        ("self._standing_key", "goal-g9", "thread-g9"),
        ("store.restore_task_card_authority", "attempt-r"),
    ]
    assert probes.calls["restore"] == {
        "current_key": _key(),
        "attempt_key": "attempt-r",
        "switch_operation_id": "op-1",
        "expected_temporary_receipt_hash": H64,
        "owner_confirmation": True,
    }
    assert _audit_lines(authority_dir) == []


@pytest.mark.parametrize(
    ("overrides", "message", "last"),
    [
        ({"argv": 1, "shell": 2}, "^unknown arguments: argv, shell$", None),
        ({"ownerConfirmation": _DROP}, "^OWNER_CONFIRMATION_REQUIRED$", None),
        ({"ownerConfirmation": "true"}, "^OWNER_CONFIRMATION_REQUIRED$", None),
        ({"ownerConfirmation": 1}, "^OWNER_CONFIRMATION_REQUIRED$", None),
        ({"attemptKey": _DROP}, "^attemptKey is required$", ("_text", "attemptKey", 128)),
        (
            {"switchOperationId": "s" * 129},
            "^switchOperationId exceeds 128 characters$",
            ("_text", "switchOperationId", 128),
        ),
        (
            {"expectedTemporaryReceiptHash": ""},
            "^expectedTemporaryReceiptHash is required$",
            ("_text", "expectedTemporaryReceiptHash", 64),
        ),
        (
            {"expectedCurrentGoalId": None},
            "^expectedCurrentGoalId is required$",
            ("_text", "expectedCurrentGoalId", 128),
        ),
        (
            {"expectedCurrentThreadId": ""},
            "^expectedCurrentThreadId is required$",
            ("_text", "expectedCurrentThreadId", 128),
        ),
        (
            {"expectedTemporaryReceiptHash": "abc"},
            "^expectedTemporaryReceiptHash must be a lowercase 64-hex SHA-256$",
            ("_text", "expectedCurrentThreadId", 128),
        ),
    ],
)
def test_restore_argument_denials_never_reach_the_store(
    events, probes, overrides, message, last
) -> None:
    with pytest.raises(GatewayInputError, match=message):
        _gateway(events)._task_card_authority_restore(_restore_args(**overrides))
    assert (events[-1] if events else None) == last


def test_restore_invalid_current_key(events, probes) -> None:
    with pytest.raises(GatewayInputError, match="^OWNER_AUTHORITY_KEY_REQUIRED:"):
        _gateway(events)._task_card_authority_restore(_restore_args(expectedCurrentThreadId="-x"))
    assert _names(events)[-1] == "self._standing_key"


def test_restore_store_refusal_is_mapped(events, probes) -> None:
    probes.restore_error = StandingGrantReceiptError("RESTORE_OPERATION_UNKNOWN")
    with pytest.raises(GatewayInputError, match="^RESTORE_OPERATION_UNKNOWN$"):
        _gateway(events)._task_card_authority_restore(_restore_args())
    assert _names(events)[-1] == "store.restore_task_card_authority"


def test_restore_public_tool_reports_denials_as_tool_errors(events, probes) -> None:
    response = _gateway(events).handle({
        "jsonrpc": "2.0",
        "id": 4,
        "method": "tools/call",
        "params": {
            "name": "nexus_task_card_authority_restore",
            "arguments": _restore_args(ownerConfirmation=False),
        },
    })
    assert response is not None
    assert response["result"]["isError"] is True
    assert "OWNER_CONFIRMATION_REQUIRED" in response["result"]["structuredContent"]["error"]
    assert events == []
