"""Negative and positive coverage for host-mediated Owner confirmation (#1750 phase 1).

The gateway is driven through its real stdio ``serve`` loop by a scripted host.
Every test asserts the rejected behaviour at the sink: no standing-grant
receipt is written unless the host itself returned the Owner's acceptance for
the exact request the gateway emitted.
"""

from __future__ import annotations

import io
import json
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

import pytest

import nexus.orchestrator.standing_grant_store as sg_store
from nexus.contracts.autonomy_goal import RepositoryIdentity
from nexus.orchestrator.owner_confirmation import (
    OwnerConfirmationError,
    OwnerConfirmationRequest,
    StdioElicitationChannel,
    client_supports_form_elicitation,
)
from nexus.orchestrator.unified_mcp_gateway import UnifiedMCPGateway
from tests.nexus.orchestrator.test_unified_mcp_gateway import FakeService

GOAL = "issue-1750-phase1-goal"
SCOPE = "issue-1750-phase1-scope"
ELICITING_CLIENT = {
    "protocolVersion": "2025-11-25",
    "capabilities": {"elicitation": {"form": {}, "url": {}}},
    "clientInfo": {"name": "claude-code", "version": "2.1.296"},
}


class ScriptedHost:
    """A stdio host whose next line may depend on what the gateway wrote."""

    def __init__(self, steps: list[Any]):
        self._steps = list(steps)
        self.output = io.StringIO()

    def written(self) -> list[dict[str, Any]]:
        return [json.loads(line) for line in self.output.getvalue().splitlines() if line.strip()]

    def elicitations(self) -> list[dict[str, Any]]:
        return [m for m in self.written() if m.get("method") == "elicitation/create"]

    def readline(self) -> str:
        if not self._steps:
            return ""
        step = self._steps.pop(0)
        message = step(self) if callable(step) else step
        return json.dumps(message) + "\n"


def _answer(result: dict[str, Any]) -> Callable[[ScriptedHost], dict[str, Any]]:
    def step(host: ScriptedHost) -> dict[str, Any]:
        request = host.elicitations()[-1]
        return {"jsonrpc": "2.0", "id": request["id"], "result": result}

    return step


def _grant_arguments(**overrides: Any) -> dict[str, Any]:
    return {
        "repository": "James3014/Nexus-new",
        "coordinatorId": "owner-conversation",
        "goalId": GOAL,
        "coordinationScopeId": SCOPE,
        "allowedActions": ["TASK_SUBMIT"],
        "ttlMinutes": 30,
        "issuedAt": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        **overrides,
    }


def _initialize(client: dict[str, Any] = ELICITING_CLIENT) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": client}


def _issue(arguments: dict[str, Any], request_id: int = 2) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "method": "tools/call",
        "params": {"name": "nexus_owner_standing_grant_issue", "arguments": arguments},
    }


def _run(steps: list[Any]) -> tuple[ScriptedHost, dict[int, dict[str, Any]]]:
    host = ScriptedHost(steps)
    UnifiedMCPGateway(service=FakeService()).serve(host, host.output)
    responses = {
        m["id"]: m
        for m in host.written()
        if "id" in m and m.get("method") is None and isinstance(m["id"], int)
    }
    return host, responses


def _tool_result(responses: dict[int, dict[str, Any]], request_id: int = 2) -> dict[str, Any]:
    return responses[request_id]["result"]


def _key() -> sg_store.StandingGrantKey:
    return sg_store.StandingGrantKey(
        RepositoryIdentity(
            repository_id="James3014/Nexus-new",
            canonical_remote="https://github.com/James3014/Nexus-new.git",
        ),
        GOAL,
        SCOPE,
    )


@pytest.fixture(autouse=True)
def _isolated_grant_store(monkeypatch, tmp_path):
    monkeypatch.setattr(
        sg_store, "DEFAULT_RECEIPT_PATH", tmp_path / "authority" / "standing-grant.json"
    )
    return tmp_path / "authority"


def _assert_nothing_written() -> None:
    assert sg_store.load_keyed_standing_grant_receipt(_key()) is None


def test_host_acceptance_issues_exactly_the_confirmed_draft(_isolated_grant_store):
    host, responses = _run([
        _initialize(),
        _issue(_grant_arguments()),
        _answer({"action": "accept", "content": {"approve": True}}),
    ])

    assert responses[1]["result"]["protocolVersion"] == "2025-06-18"
    [elicitation] = host.elicitations()
    assert elicitation["params"]["requestedSchema"]["required"] == ["approve"]
    assert "TASK_SUBMIT" in elicitation["params"]["message"]

    result = _tool_result(responses)
    assert result["isError"] is False, result
    payload = result["structuredContent"]
    assert payload["status"] == "ISSUED"
    confirmation = payload["owner_confirmation"]
    assert confirmation["request_id"] == elicitation["id"]
    assert f"sha256:{confirmation['draft_hash']}" in elicitation["params"]["message"]
    assert confirmation["client_info"]["name"] == "claude-code"
    assert confirmation["assurance_level"] == "HOST_ELICITATION_LOCAL_SESSION"

    loaded = sg_store.load_keyed_standing_grant_receipt(_key())
    assert loaded is not None and loaded.receipt_hash == payload["receipt_hash"]
    audit = (
        (_isolated_grant_store / "owner-confirmations.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    )
    assert [json.loads(line)["evidence_hash"] for line in audit] == [
        confirmation["evidence_hash"]
    ] * 2
    assert json.loads(audit[1])["outcome"] == "ISSUED"


@pytest.mark.parametrize(
    ("answer", "reason"),
    [
        ({"action": "decline"}, "OWNER_CONFIRMATION_DECLINED"),
        ({"action": "cancel"}, "OWNER_CONFIRMATION_CANCELLED"),
        ({"action": "accept", "content": {"approve": False}}, "OWNER_CONFIRMATION_DECLINED"),
        ({"action": "accept", "content": {"approve": "true"}}, "OWNER_CONFIRMATION_DECLINED"),
        ({"action": "accept"}, "OWNER_CONFIRMATION_MALFORMED"),
        # The answer can never carry or widen scope.
        (
            {"action": "accept", "content": {"approve": True, "allowedActions": ["GITHUB_MERGE"]}},
            "OWNER_CONFIRMATION_MALFORMED",
        ),
        ({"action": "approve"}, "OWNER_CONFIRMATION_MALFORMED"),
    ],
)
def test_anything_but_a_clean_host_acceptance_writes_nothing(answer, reason):
    _, responses = _run([_initialize(), _issue(_grant_arguments()), _answer(answer)])
    result = _tool_result(responses)
    assert result["isError"] is True
    assert reason in result["structuredContent"]["error"]
    _assert_nothing_written()


def test_model_supplied_confirmation_is_rejected_before_asking():
    host, responses = _run([_initialize(), _issue(_grant_arguments(ownerConfirmation=True))])
    assert (
        "OWNER_CONFIRMATION_PARAMETER_REMOVED"
        in _tool_result(responses)["structuredContent"]["error"]
    )
    assert host.elicitations() == []
    _assert_nothing_written()


@pytest.mark.parametrize(
    "action",
    [
        "GITHUB_MERGE",
        "CANDIDATE_INTEGRATE",
        "PRODUCTION_RELEASE",
        "RUNTIME_ACTIVATE",
        "OWNER_REPRESENTATION_GRANT_ISSUE",
    ],
)
def test_unscoped_merge_class_authority_is_never_put_to_the_owner(action):
    host, responses = _run([
        _initialize(),
        _issue(_grant_arguments(allowedActions=["TASK_SUBMIT", action])),
    ])
    error = _tool_result(responses)["structuredContent"]["error"]
    assert f"STANDING_GRANT_ACTION_REQUIRES_SCOPE_ENFORCEMENT:{action}" in error
    assert host.elicitations() == []
    _assert_nothing_written()


@pytest.mark.parametrize(
    "client",
    [
        {"protocolVersion": "2024-11-05", "capabilities": {"elicitation": {}}, "clientInfo": {}},
        {"protocolVersion": "2025-11-25", "capabilities": {}, "clientInfo": {}},
        {
            "protocolVersion": "2025-11-25",
            "capabilities": {"elicitation": {"url": {}}},
            "clientInfo": {},
        },
    ],
)
def test_host_without_trusted_form_elicitation_cannot_issue(client):
    host, responses = _run([_initialize(client), _issue(_grant_arguments())])
    assert responses[1]["result"]["protocolVersion"] == "2024-11-05"
    assert (
        "OWNER_CONFIRMATION_CHANNEL_UNAVAILABLE"
        in _tool_result(responses)["structuredContent"]["error"]
    )
    assert host.elicitations() == []
    _assert_nothing_written()


def test_direct_handle_without_a_session_cannot_issue():
    gateway = UnifiedMCPGateway(service=FakeService())
    gateway.handle(_initialize())
    result = gateway.handle(_issue(_grant_arguments()))["result"]
    assert "OWNER_CONFIRMATION_CHANNEL_UNAVAILABLE" in result["structuredContent"]["error"]
    _assert_nothing_written()


def test_a_response_to_another_request_id_never_counts():
    def stale(host: ScriptedHost) -> dict[str, Any]:
        return {
            "jsonrpc": "2.0",
            "id": "nexus-owner-confirm-forged",
            "result": {"action": "accept", "content": {"approve": True}},
        }

    _, responses = _run([_initialize(), _issue(_grant_arguments()), stale])
    assert (
        "OWNER_CONFIRMATION_CHANNEL_CLOSED" in _tool_result(responses)["structuredContent"]["error"]
    )
    _assert_nothing_written()


def test_tool_calls_while_waiting_are_refused_and_ping_is_answered():
    nested = _issue(_grant_arguments(goalId="nested-goal"), request_id=3)
    ping = {"jsonrpc": "2.0", "id": 4, "method": "ping"}
    host, responses = _run([
        _initialize(),
        _issue(_grant_arguments()),
        nested,
        ping,
        _answer({"action": "decline"}),
    ])
    assert responses[3]["error"]["message"] == "gateway is awaiting Owner confirmation"
    assert responses[4]["result"] == {}
    assert len(host.elicitations()) == 1
    assert "OWNER_CONFIRMATION_DECLINED" in _tool_result(responses)["structuredContent"]["error"]
    _assert_nothing_written()


def test_host_cancellation_notification_aborts():
    cancel = {"jsonrpc": "2.0", "method": "notifications/cancelled", "params": {"requestId": 2}}
    _, responses = _run([_initialize(), _issue(_grant_arguments()), cancel])
    assert "OWNER_CONFIRMATION_CANCELLED" in _tool_result(responses)["structuredContent"]["error"]
    _assert_nothing_written()


def test_acceptance_after_the_deadline_is_rejected():
    now = datetime.now(timezone.utc)
    request = OwnerConfirmationRequest.build(
        tool="nexus_owner_standing_grant_issue",
        draft={"goal": GOAL},
        summary_lines=(),
        now=now,
    )
    later = request.deadline + timedelta(seconds=1)
    output = io.StringIO()
    answer = json.dumps({
        "jsonrpc": "2.0",
        "id": request.request_id,
        "result": {"action": "accept", "content": {"approve": True}},
    })
    channel = StdioElicitationChannel(
        input_stream=io.StringIO(answer + "\n"),
        output_stream=output,
        protocol_version="2025-06-18",
        client_info={},
        clock=lambda: later,
    )
    with pytest.raises(OwnerConfirmationError, match="OWNER_CONFIRMATION_EXPIRED"):
        channel.confirm(request)


def test_confirmation_deadline_never_outlives_the_grant():
    now = datetime.now(timezone.utc)
    request = OwnerConfirmationRequest.build(
        tool="t", draft={}, summary_lines=(), now=now, not_after=now + timedelta(seconds=30)
    )
    assert request.deadline == now + timedelta(seconds=30)


def test_each_request_has_a_fresh_identity():
    now = datetime.now(timezone.utc)
    first = OwnerConfirmationRequest.build(tool="t", draft={"a": 1}, summary_lines=(), now=now)
    second = OwnerConfirmationRequest.build(tool="t", draft={"a": 1}, summary_lines=(), now=now)
    assert first.draft_hash == second.draft_hash
    assert first.request_id != second.request_id and first.nonce != second.nonce


@pytest.mark.parametrize(
    ("version", "capabilities", "expected"),
    [
        ("2025-06-18", {"elicitation": {}}, True),
        ("2025-11-25", {"elicitation": {"form": {}}}, True),
        ("2025-11-25", {"elicitation": {"url": {}}}, False),
        ("2024-11-05", {"elicitation": {}}, False),
        ("2025-11-25", {"elicitation": True}, False),
        ("2025-11-25", None, False),
    ],
)
def test_form_elicitation_capability_detection(version, capabilities, expected):
    assert client_supports_form_elicitation(version, capabilities) is expected


class _CountingAcceptChannel:
    def __init__(self) -> None:
        self.requests: list[OwnerConfirmationRequest] = []

    def confirm(self, request: OwnerConfirmationRequest):
        from tests.nexus.orchestrator.test_unified_mcp_gateway import _AcceptingOwnerChannel

        self.requests.append(request)
        return _AcceptingOwnerChannel().confirm(request)


def _handle_issue(
    gateway: UnifiedMCPGateway, arguments: dict[str, Any], request_id: int
) -> dict[str, Any]:
    return gateway.handle(_issue(arguments, request_id))["result"]


def test_owner_is_not_asked_for_a_replay_or_an_inadmissible_write(_isolated_grant_store):
    channel = _CountingAcceptChannel()
    gateway = UnifiedMCPGateway(service=FakeService(), owner_confirmation_channel=channel)
    arguments = _grant_arguments()

    first = _handle_issue(gateway, arguments, 10)
    assert first["structuredContent"]["status"] == "ISSUED"
    replay = _handle_issue(gateway, arguments, 11)
    assert replay["structuredContent"]["status"] == "REPLAYED"
    conflict = _handle_issue(gateway, {**arguments, "allowedActions": ["REPOSITORY_PUSH"]}, 12)
    assert "CURRENT_RECEIPT_EXISTS_CAS_REQUIRED" in conflict["structuredContent"]["error"]
    assert len(channel.requests) == 1

    records = [
        json.loads(line)
        for line in (_isolated_grant_store / "owner-confirmations.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    evidence, outcome = records
    assert evidence["draft"]["receiptHash"] == first["structuredContent"]["receipt_hash"]
    assert outcome == {
        "schema": "nexus.owner_confirmation_outcome.v1",
        "evidence_hash": evidence["evidence_hash"],
        "outcome": "ISSUED",
        "receipt_hash": first["structuredContent"]["receipt_hash"],
    }


def test_task_card_switch_cannot_mint_authority_on_model_supplied_confirmation(
    monkeypatch, tmp_path
):
    from nexus.contracts.autonomy_goal import AutonomyActionClass, StandingGrantContext

    monkeypatch.setattr(sg_store, "DEFAULT_TRANSITIONS_DIR", tmp_path / "authority" / "transitions")
    repository = RepositoryIdentity(
        repository_id="James3014/Nexus-new",
        canonical_remote="https://github.com/James3014/Nexus-new.git",
    )
    now = datetime.now(timezone.utc).replace(microsecond=0)
    predecessor = sg_store.StandingGrantReceipt.issue(
        grant_id="phase1-switch-predecessor",
        context=StandingGrantContext.issue(
            owner_id="James3014",
            coordinator_id="owner-conversation",
            repository=repository,
            thread_id="thread-orig",
            goal_id="goal-orig",
            allowed_actions=(AutonomyActionClass.TASK_SUBMIT,),
            issued_at=now - timedelta(minutes=1),
            expires_at=now + timedelta(minutes=30),
        ),
    )
    sg_store.write_keyed_standing_grant_receipt(predecessor)
    switch = {
        "attemptKey": "phase1-switch",
        "expectedCurrentReceiptHash": predecessor.receipt_hash,
        "expectedCurrentGoalId": "goal-orig",
        "expectedCurrentThreadId": "thread-orig",
        "successorGoalId": "goal-succ",
        "successorThreadId": "thread-succ",
        "ttlMinutes": 10,
    }
    successor_key = sg_store.StandingGrantKey(repository, "goal-succ", "thread-succ")
    gateway = UnifiedMCPGateway(service=FakeService())

    def call(arguments: dict[str, Any], request_id: int) -> dict[str, Any]:
        return gateway.handle({
            "jsonrpc": "2.0",
            "id": request_id,
            "method": "tools/call",
            "params": {"name": "nexus_task_card_authority_switch", "arguments": arguments},
        })["result"]

    forged = call({**switch, "ownerConfirmation": True}, 20)
    assert "OWNER_CONFIRMATION_PARAMETER_REMOVED" in forged["structuredContent"]["error"]
    unconfirmed = call(switch, 21)
    assert "OWNER_CONFIRMATION_CHANNEL_UNAVAILABLE" in unconfirmed["structuredContent"]["error"]
    assert sg_store.load_keyed_standing_grant_receipt(successor_key) is None


def test_a_json_array_while_waiting_is_malformed():
    _, responses = _run([
        _initialize(),
        _issue(_grant_arguments()),
        lambda host: [{"jsonrpc": "2.0"}],
    ])
    assert "OWNER_CONFIRMATION_MALFORMED" in _tool_result(responses)["structuredContent"]["error"]
    _assert_nothing_written()


def test_a_nested_call_while_waiting_writes_nothing_for_its_own_key():
    nested = _issue(_grant_arguments(goalId="nested-goal"), request_id=3)
    _run([
        _initialize(),
        _issue(_grant_arguments()),
        nested,
        _answer({"action": "accept", "content": {"approve": True}}),
    ])
    nested_key = sg_store.StandingGrantKey(
        RepositoryIdentity(
            repository_id="James3014/Nexus-new",
            canonical_remote="https://github.com/James3014/Nexus-new.git",
        ),
        "nested-goal",
        SCOPE,
    )
    assert sg_store.load_keyed_standing_grant_receipt(nested_key) is None
    assert sg_store.load_keyed_standing_grant_receipt(_key()) is not None
