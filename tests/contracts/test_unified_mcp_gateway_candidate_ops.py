"""Characterization tests for the gateway's candidate operations (Issue #2525, big-file split G10).

These pin ``_candidate_approve``, ``_candidate_adopt_external``,
``_validate_external_adoption_result``, ``_candidate_bind_integration`` and
``_candidate_dispose`` of ``UnifiedMCPGateway`` before they move out of the facade class
into a mixin. ``_candidate_integrate`` is not covered here: it stays in the facade.

The authority and permission collaborators (``_require_bound_controller``,
``resolve_contract_identity``, ``validate_approval_grant``, ``pre_action_guard``,
``ControlledIntegrationManager``, ``_git``) are replaced on the gateway facade module with
recording probes. The tests therefore pin both the order in which each operation calls them
and that facade patches keep reaching the moved code. ``_owner_effect_key`` and
``_require_owner_effect_authority`` are probed on the instance. The action envelope is the
real ``build_action_envelope`` result, checked where ``pre_action_guard`` receives it.
"""

from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from nexus.contracts.autonomy_goal import AutonomyActionClass
from nexus.contracts.lifecycle_action import (
    ApprovalScope,
    ContractKind,
    LifecycleActionType,
    MutationDomain,
    PermissionProfile,
    build_action_envelope,
    canonical_request_hash,
)
from nexus.contracts.target_integration_lifecycle import ExternalAcceptanceReceipt
from nexus.orchestrator import unified_mcp_gateway as gateway_module
from nexus.orchestrator.self_hosted_task_service import SelfHostedTaskService
from nexus.orchestrator.unified_mcp_gateway import (
    FULL_TOOL_SCHEMA_HASH,
    LIFECYCLE_REVISION,
    PERMISSION_POLICY_HASH,
    SERVER_INSTANCE_ID,
    TOOL_MANIFEST_REVISION,
    GatewayInputError,
    UnifiedMCPGateway,
)

HEAD = "a" * 40
OTHER_HEAD = "9" * 40
AUTHORITY_ARGS = {"authority_goal_id": "goal-g10", "authority_coordination_scope_id": "thread-g10"}
PACKET = {
    "candidate_commit_sha": "1" * 40,
    "candidate_tree_sha": "2" * 40,
    "candidate_state_hash": "3" * 64,
    "verified_receipt_hash": "4" * 64,
}
IDENTITY = {
    "contract_kind": ContractKind.TRACKED_TASK_CARD.value,
    "contract_hash": "c" * 64,
    "task_card_hash": "d" * 64,
    "owner_inline_contract": None,
}


def _state(**overrides: Any) -> dict[str, Any]:
    state: dict[str, Any] = {
        "task_id": "cand-1",
        "status": "PENDING_HUMAN_APPROVAL",
        "attempt_id": "attempt-1",
        "controller_revision": HEAD,
        "contract": {"allowed_files": ["README.md", " "]},
        "promotion_packet": dict(PACKET),
    }
    state.update(overrides)
    return state


class _Service(SelfHostedTaskService):
    def __init__(self, state_dir: Path, events: list[tuple], state: Any) -> None:
        self.state_dir = state_dir
        self.events = events
        self.state = state
        self.calls: dict[str, tuple] = {}

    def get_task_snapshot(self, task_id, *, include_details=False) -> Any:
        self.events.append(("service.get_task_snapshot", task_id, include_details))
        return self.state

    def approve_promotion(self, task_id, **kwargs):
        self.events.append(("service.approve_promotion", task_id))
        self.calls["approve_promotion"] = (task_id, kwargs)
        return {"task_id": task_id, "status": "APPROVED", "attempt_id": "attempt-1"}

    def bind_candidate_integration_closure(self, task_id, **kwargs):
        self.events.append(("service.bind_candidate_integration_closure", task_id))
        self.calls["bind_candidate_integration_closure"] = (task_id, kwargs)
        return {"task_id": task_id, "status": "APPROVED"}

    def dispose_candidate(self, task_id, **kwargs):
        self.events.append(("service.dispose_candidate", task_id, kwargs["disposition"]))
        self.calls["dispose_candidate"] = (task_id, kwargs)
        return {"task_id": task_id, "status": kwargs["disposition"]}

    def adopt_external_candidate(self, raw_request):
        request: Any = raw_request  # the gateway hands over a validated ExternalCandidateAdoptionRequest
        self.events.append(("service.adopt_external_candidate", request.task_id))
        self.calls["adopt_external_candidate"] = (request,)
        return _adoption_result(request)


@pytest.fixture
def events() -> list[tuple]:
    return []


@pytest.fixture
def controller_root(tmp_path: Path) -> Path:
    root = (tmp_path / "controller").resolve()
    root.mkdir()
    return root


@pytest.fixture
def probes(monkeypatch, events, controller_root):
    """Replace the authority/permission collaborators on the gateway facade."""
    ctx = SimpleNamespace(identity_error=None, guard_error=None, separate_head=HEAD, git_heads=[HEAD], branch="main")
    monkeypatch.setattr(gateway_module, "CANONICAL_SOURCE_ROOT", controller_root)

    def require_bound_controller(expected_head=None):
        events.append(("_require_bound_controller",))

    def resolve_contract_identity(state, *, expected_task_id, expected_head):
        events.append(("resolve_contract_identity", expected_task_id, expected_head))
        if ctx.identity_error:
            raise RuntimeError(ctx.identity_error)
        return dict(IDENTITY)

    def validate_approval_grant(grant, **kwargs):
        events.append(("validate_approval_grant", kwargs["action_type"], kwargs["task_card_hash"]))
        ctx.approval_kwargs = kwargs
        return {"approval_receipt": "ok", "grant": dict(grant or {})}

    def guard(action, *, request, current_head, tool_manifest_hash):
        events.append(("pre_action_guard", action.action_type.value, current_head))
        ctx.action = action
        ctx.guard_request = request
        ctx.guard_manifest = tool_manifest_hash
        if ctx.guard_error:
            raise ctx.guard_error
        return {"gate_passed": True, "head": current_head}

    class _Integration:
        @staticmethod
        def separate_controller_integration_head(root, branch):
            events.append(("separate_controller_integration_head", Path(root) == controller_root, branch))
            if isinstance(ctx.separate_head, Exception):
                raise ctx.separate_head
            return ctx.separate_head

    def git(*args, **kwargs):
        events.append(("_git",) + args)
        if args[:2] == ("branch", "--show-current"):
            return ctx.branch + "\n"
        return (ctx.git_heads.pop(0) if len(ctx.git_heads) > 1 else ctx.git_heads[0]) + "\n"

    monkeypatch.setattr(gateway_module, "_require_bound_controller", require_bound_controller)
    monkeypatch.setattr(gateway_module, "resolve_contract_identity", resolve_contract_identity)
    monkeypatch.setattr(gateway_module, "validate_approval_grant", validate_approval_grant)
    monkeypatch.setattr(gateway_module, "pre_action_guard", guard)
    monkeypatch.setattr(gateway_module, "ControlledIntegrationManager", _Integration)
    monkeypatch.setattr(gateway_module, "_git", git)
    return ctx


def _gateway(tmp_path: Path, events: list[tuple], state: Any = None) -> UnifiedMCPGateway:
    gateway = UnifiedMCPGateway(service=_Service(tmp_path / "state", events, _state() if state is None else state))

    def owner_effect_key(arguments):
        events.append(("_owner_effect_key", arguments.get("authority_goal_id")))
        if not arguments.get("authority_goal_id"):
            raise GatewayInputError("OWNER_AUTHORITY_KEY_REQUIRED:probe")
        return "KEY"

    def require_owner_effect_authority(action, effect, *, key):
        events.append(("_require_owner_effect_authority", action.value, key))
        vars(gateway)["owner_effect"] = dict(effect)
        return {"authority": "OWNER", "action": action.value}

    gateway._owner_effect_key = owner_effect_key  # type: ignore[method-assign]
    gateway._require_owner_effect_authority = require_owner_effect_authority  # type: ignore[method-assign]
    return gateway


def _service(gateway: UnifiedMCPGateway) -> _Service:
    assert isinstance(gateway.service, _Service)
    return gateway.service


def _owner_effect(gateway: UnifiedMCPGateway) -> dict[str, Any]:
    return vars(gateway)["owner_effect"]


def _names(events: list[tuple]) -> list[str]:
    return [event[0] for event in events]


# --- _candidate_approve -----------------------------------------------------------------


def _approve_args(**overrides: Any) -> dict[str, Any]:
    arguments: dict[str, Any] = {"task_id": "cand-1", **PACKET, "approval": {"grant_id": "g-1"}}
    arguments.update(overrides)
    return arguments


def test_approve_call_order_and_payload(tmp_path, events, probes) -> None:
    gateway = _gateway(tmp_path, events)
    payload = gateway._call_tool("nexus_candidate_approve", _approve_args())
    assert events == [
        ("_require_bound_controller",),
        ("service.get_task_snapshot", "cand-1", True),
        ("resolve_contract_identity", "cand-1", HEAD),
        ("validate_approval_grant", LifecycleActionType.CANDIDATE_APPROVE.value, "d" * 64),
        ("pre_action_guard", LifecycleActionType.CANDIDATE_APPROVE.value, HEAD),
        ("service.approve_promotion", "cand-1"),
    ]
    kwargs = probes.approval_kwargs
    assert kwargs["attempt_id"] == "attempt-1"
    assert kwargs["contract_kind"] == ContractKind.TRACKED_TASK_CARD.value
    assert (kwargs["tool_manifest_hash"], kwargs["full_tool_schema_hash"], kwargs["permission_policy_hash"]) == (
        TOOL_MANIFEST_REVISION, FULL_TOOL_SCHEMA_HASH, PERMISSION_POLICY_HASH)
    assert (kwargs["lifecycle_revision"], kwargs["server_instance_id"]) == (LIFECYCLE_REVISION, SERVER_INSTANCE_ID)
    action = probes.action
    assert action.task_id == "cand-1" and action.expected_head == HEAD
    assert action.permission_profile is PermissionProfile.CANDIDATE
    assert action.mutation_domain is MutationDomain.LIFECYCLE_STATE
    assert action.allowed_paths == () and action.mutation is True
    assert action.tool_manifest_hash == probes.guard_manifest == TOOL_MANIFEST_REVISION
    assert action.request_hash == canonical_request_hash(
        {**_approve_args(), "source_attempt_id": "attempt-1", "candidate_binding": PACKET}
    )
    assert probes.guard_request == {}
    task_id, call = _service(gateway).calls["approve_promotion"]
    assert {key: call[key] for key in PACKET} == PACKET
    assert call["approval_context"] == {"grant_id": "g-1", "validation_receipt": payload["approval_receipt"]}
    assert payload["operation"] == "candidate_approve"
    assert payload["guard_receipt"] == {"gate_passed": True, "head": HEAD}
    assert payload["approval_receipt"]["approval_receipt"] == "ok"
    assert payload["state"]["status"] == "APPROVED"


def test_approve_binding_falls_back_to_state_fields(tmp_path, events, probes) -> None:
    gateway = _gateway(tmp_path, events, _state(promotion_packet=None, **PACKET))
    gateway._candidate_approve(_approve_args())
    assert probes.action.request_hash == canonical_request_hash(
        {**_approve_args(), "source_attempt_id": "attempt-1", "candidate_binding": PACKET}
    )


@pytest.mark.parametrize(("field", "value"), [
    ("candidate_commit_sha", "A" * 40),
    ("candidate_tree_sha", "a" * 39),
    ("candidate_state_hash", "b" * 40),
    ("verified_receipt_hash", None),
])
def test_approve_rejects_inexact_hashes_before_reading_state(tmp_path, events, probes, field, value) -> None:
    gateway = _gateway(tmp_path, events)
    with pytest.raises(GatewayInputError, match=field):
        gateway._candidate_approve(_approve_args(**{field: value}))
    assert _names(events) == ["_require_bound_controller"]


@pytest.mark.parametrize(("state", "code"), [
    (None, "^CANDIDATE_TASK_STATE_REQUIRED$"),
    (_state(controller_revision="abc"), "^CANDIDATE_CONTROLLER_REVISION_REQUIRED$"),
])
def test_approve_rejects_missing_state_or_revision(tmp_path, events, probes, state, code) -> None:
    gateway = _gateway(tmp_path, events, state if state is not None else "missing")
    with pytest.raises(GatewayInputError, match=code):
        gateway._candidate_approve(_approve_args())
    assert "service.approve_promotion" not in _names(events)


def test_approve_maps_identity_errors(tmp_path, events, probes) -> None:
    probes.identity_error = "CONTRACT_HASH_MISMATCH:probe"
    gateway = _gateway(tmp_path, events)
    with pytest.raises(GatewayInputError, match="^CONTRACT_HASH_MISMATCH:probe$"):
        gateway._candidate_approve(_approve_args())
    assert _names(events)[-1] == "resolve_contract_identity"


@pytest.mark.parametrize(("identity", "code"), [
    ({"task_card_hash": "short"}, "^CANDIDATE_TASK_CARD_HASH_REQUIRED$"),
    ({"contract_kind": ContractKind.OWNER_INLINE.value, "contract_hash": ""}, "^CANDIDATE_OWNER_INLINE_CONTRACT_REQUIRED$"),
])
def test_approve_requires_contract_hashes(tmp_path, events, probes, monkeypatch, identity, code) -> None:
    monkeypatch.setitem(IDENTITY, "contract_kind", identity.get("contract_kind", IDENTITY["contract_kind"]))
    for key in ("task_card_hash", "contract_hash"):
        if key in identity:
            monkeypatch.setitem(IDENTITY, key, identity[key])
    gateway = _gateway(tmp_path, events)
    with pytest.raises(GatewayInputError, match=code):
        gateway._candidate_approve(_approve_args())
    assert "validate_approval_grant" not in _names(events)


def test_approve_guard_failure_stops_before_the_service(tmp_path, events, probes) -> None:
    probes.guard_error = GatewayInputError("HEAD_DRIFT")
    gateway = _gateway(tmp_path, events)
    with pytest.raises(GatewayInputError, match="^HEAD_DRIFT$"):
        gateway._candidate_approve(_approve_args())
    assert _names(events)[-1] == "pre_action_guard"


def test_approve_requires_a_bound_controller_first(tmp_path, events, monkeypatch) -> None:
    monkeypatch.setattr(gateway_module, "CONTROLLER_BINDING_PROBLEM", "probe")
    gateway = _gateway(tmp_path, events)
    with pytest.raises(GatewayInputError, match="^CONTROLLER_BINDING_INVALID:DEGRADED:probe$"):
        gateway._candidate_approve(_approve_args())
    assert events == []


# --- _candidate_bind_integration ---------------------------------------------------------


def _bind_args(**overrides: Any) -> dict[str, Any]:
    arguments: dict[str, Any] = {
        "task_id": "cand-1",
        "expected_canonical_head": HEAD,
        "external_acceptance": dict(ACCEPTANCE),
        "approval": {"grant_id": "g-2"},
    }
    arguments.update(overrides)
    return arguments


ACCEPTANCE = {
    "schema": "nexus.external_acceptance_receipt.v1",
    "task_id": "cand-1",
    "attempt_id": "attempt-1",
    "candidate_commit": "1" * 40,
    "receipt_hash": "5" * 64,
    "reviewer_id": "independent-reviewer",
    "passed": True,
    "verifier_artifact": "artifacts/verify.json",
}


def test_bind_call_order_and_payload(tmp_path, events, probes) -> None:
    gateway = _gateway(tmp_path, events)
    payload = gateway._call_tool("nexus_candidate_bind_integration", _bind_args())
    assert events == [
        ("_require_bound_controller",),
        ("service.get_task_snapshot", "cand-1", True),
        ("resolve_contract_identity", "cand-1", HEAD),
        ("separate_controller_integration_head", True, "nexus/integration/main"),
        ("pre_action_guard", LifecycleActionType.CANDIDATE_INTEGRATE.value, HEAD),
        ("service.bind_candidate_integration_closure", "cand-1"),
    ]
    action = probes.action
    assert action.task_id == "cand-1" and action.expected_head == HEAD
    assert action.permission_profile is PermissionProfile.INTEGRATE
    assert action.mutation_domain is MutationDomain.LIFECYCLE_STATE
    assert action.allowed_paths == ("README.md",) and action.mutation is True
    assert action.request_hash == canonical_request_hash({
        "task_id": "cand-1", "integration_branch": "nexus/integration/main", "expected_canonical_head": HEAD,
        "external_acceptance": ACCEPTANCE, "approval": {"grant_id": "g-2"}, "source_attempt_id": "attempt-1",
        "candidate_binding": PACKET,
    })
    assert probes.guard_request == {"allowed_files": ["README.md"]}
    _, call = _service(gateway).calls["bind_candidate_integration_closure"]
    assert isinstance(call["external_acceptance"], ExternalAcceptanceReceipt)
    assert call["external_acceptance"].to_dict() == ACCEPTANCE
    assert call["approval"] == {"grant_id": "g-2"}
    assert call["expected_canonical_head"] == HEAD and call["integration_branch"] == "nexus/integration/main"
    assert call["runtime_identity"] == {
        **IDENTITY,
        "tool_manifest_hash": TOOL_MANIFEST_REVISION,
        "full_tool_schema_hash": FULL_TOOL_SCHEMA_HASH,
        "permission_policy_hash": PERMISSION_POLICY_HASH,
        "lifecycle_revision": LIFECYCLE_REVISION,
        "server_instance_id": SERVER_INSTANCE_ID,
    }
    assert payload["operation"] == "candidate_bind_integration"
    assert payload["integration_performed"] is False
    assert payload["guard_receipt"]["gate_passed"] is True


def test_bind_uses_the_contract_controller_root_and_git_head_without_separate_controller(
    tmp_path, events, probes, monkeypatch,
) -> None:
    other_root = (tmp_path / "other-controller").resolve()
    other_root.mkdir()
    probes.separate_head = None
    runs: list[tuple] = []

    def run(argv, *, cwd, capture_output, text, check):
        runs.append((tuple(argv), Path(cwd)))
        return SimpleNamespace(returncode=0, stdout=OTHER_HEAD + "\n")

    monkeypatch.setattr(gateway_module.subprocess, "run", run)
    gateway = _gateway(tmp_path, events, _state(contract={"allowed_files": ["a.py"], "controller_repo_root": str(other_root)}))
    gateway._candidate_bind_integration(_bind_args(expected_canonical_head=OTHER_HEAD, integration_branch=" feature/x "))
    assert runs == [(("git", "rev-parse", "HEAD"), other_root)]
    assert ("separate_controller_integration_head", False, "feature/x") in events
    assert probes.action.expected_head == OTHER_HEAD
    assert probes.action.allowed_paths == ("a.py",)


@pytest.mark.parametrize(("returncode", "stdout"), [(1, HEAD), (0, OTHER_HEAD)])
def test_bind_refuses_head_drift(tmp_path, events, probes, monkeypatch, returncode, stdout) -> None:
    probes.separate_head = None
    monkeypatch.setattr(gateway_module.subprocess, "run", lambda *a, **k: SimpleNamespace(returncode=returncode, stdout=stdout))
    gateway = _gateway(tmp_path, events)
    with pytest.raises(GatewayInputError, match="^CANDIDATE_BIND_HEAD_DRIFT$"):
        gateway._candidate_bind_integration(_bind_args())
    assert "pre_action_guard" not in _names(events)


def test_bind_maps_separate_controller_errors_and_drift(tmp_path, events, probes) -> None:
    gateway = _gateway(tmp_path, events)
    probes.separate_head = RuntimeError("SEPARATE_CONTROLLER_PROBE")
    with pytest.raises(GatewayInputError, match="^SEPARATE_CONTROLLER_PROBE$"):
        gateway._candidate_bind_integration(_bind_args())
    probes.separate_head = OTHER_HEAD
    with pytest.raises(GatewayInputError, match="^CANDIDATE_BIND_HEAD_DRIFT$"):
        gateway._candidate_bind_integration(_bind_args())
    assert "pre_action_guard" not in _names(events)


@pytest.mark.parametrize(("overrides", "code"), [
    ({"integration_authorization": {}}, "^CLOSURE_SCHEMA_CLOSED$"),
    ({"shell": "x"}, "^CLOSURE_SCHEMA_CLOSED$"),
    ({"expected_canonical_head": "abc"}, "^expected_canonical_head is invalid$"),
    ({"integration_branch": "-x"}, "^integration_branch is invalid$"),
    ({"integration_branch": "a\nb"}, "^integration_branch is invalid$"),
    ({"approval": "yes"}, "^typed external_acceptance and approval are required$"),
    ({"external_acceptance": {**ACCEPTANCE, "passed": False}}, "^EXTERNAL_ACCEPTANCE_INVALID: only a passed external acceptance may authorize integration$"),
    ({"external_acceptance": {**ACCEPTANCE, "extra": 1}}, "^EXTERNAL_ACCEPTANCE_INVALID: "),
])
def test_bind_rejects_bad_requests_before_reading_state(tmp_path, events, probes, overrides, code) -> None:
    gateway = _gateway(tmp_path, events)
    with pytest.raises(GatewayInputError, match=code):
        gateway._candidate_bind_integration(_bind_args(**overrides))
    assert _names(events) == ["_require_bound_controller"]


@pytest.mark.parametrize(("state", "code"), [
    ("missing", "^CANDIDATE_TASK_STATE_REQUIRED$"),
    (_state(controller_revision=""), "^CANDIDATE_CONTROLLER_REVISION_REQUIRED$"),
    (_state(contract={"allowed_files": [" "]}), "^CANDIDATE_ALLOWED_PATHS_REQUIRED$"),
])
def test_bind_rejects_unusable_state(tmp_path, events, probes, state, code) -> None:
    gateway = _gateway(tmp_path, events, state)
    with pytest.raises(GatewayInputError, match=code):
        gateway._candidate_bind_integration(_bind_args())
    assert "service.bind_candidate_integration_closure" not in _names(events)


def test_bind_maps_identity_errors(tmp_path, events, probes) -> None:
    probes.identity_error = "CONTRACT_HASH_MISMATCH:bind"
    gateway = _gateway(tmp_path, events)
    with pytest.raises(GatewayInputError, match="^CONTRACT_HASH_MISMATCH:bind$"):
        gateway._candidate_bind_integration(_bind_args())
    assert _names(events)[-1] == "resolve_contract_identity"


# --- _candidate_dispose ------------------------------------------------------------------


def _dispose_args(**overrides: Any) -> dict[str, Any]:
    arguments: dict[str, Any] = {**AUTHORITY_ARGS, "task_id": "cand-1", "disposition": "rejected"}
    arguments.update(overrides)
    return arguments


def test_dispose_call_order_owner_effect_and_payload(tmp_path, events, probes) -> None:
    gateway = _gateway(tmp_path, events)
    payload = gateway._call_tool("nexus_candidate_dispose", _dispose_args())
    assert events == [
        ("_owner_effect_key", "goal-g10"),
        ("service.get_task_snapshot", "cand-1", True),
        ("resolve_contract_identity", "cand-1", HEAD),
        ("_require_owner_effect_authority", AutonomyActionClass.CANDIDATE_REJECT.value, "KEY"),
        ("pre_action_guard", LifecycleActionType.CANDIDATE_DISPOSE.value, HEAD),
        ("service.dispose_candidate", "cand-1", "REJECTED"),
    ]
    assert _owner_effect(gateway) == {
        "task_id": "cand-1",
        "attempt_id": "attempt-1",
        "controller_revision": HEAD,
        "contract_kind": IDENTITY["contract_kind"],
        "contract_hash": IDENTITY["contract_hash"],
        "task_card_hash": IDENTITY["task_card_hash"],
        "disposition": "REJECTED",
        "superseded_by": None,
        **PACKET,
    }
    action = probes.action
    assert action.action_type is LifecycleActionType.CANDIDATE_DISPOSE and action.expected_head == HEAD
    assert action.permission_profile is PermissionProfile.CANDIDATE
    assert action.mutation_domain is MutationDomain.CANDIDATE_REF
    assert action.allowed_paths == () and action.mutation is True
    assert action.request_hash == canonical_request_hash(
        {**_dispose_args(), "source_attempt_id": "attempt-1", "candidate_binding": PACKET}
    )
    assert _service(gateway).calls["dispose_candidate"] == ("cand-1", {"disposition": "REJECTED", "superseded_by": None})
    assert payload["operation"] == "candidate_dispose"
    assert payload["owner_authority"] == {"authority": "OWNER", "action": AutonomyActionClass.CANDIDATE_REJECT.value}
    assert payload["guard_receipt"]["gate_passed"] is True


def test_dispose_superseded_uses_the_supersede_authority(tmp_path, events, probes) -> None:
    gateway = _gateway(tmp_path, events)
    gateway._candidate_dispose(_dispose_args(disposition=" Superseded ", superseded_by="cand-2"))
    assert ("_require_owner_effect_authority", AutonomyActionClass.CANDIDATE_SUPERSEDE.value, "KEY") in events
    assert _owner_effect(gateway)["superseded_by"] == "cand-2"
    assert _service(gateway).calls["dispose_candidate"] == ("cand-1", {"disposition": "SUPERSEDED", "superseded_by": "cand-2"})


@pytest.mark.parametrize(("overrides", "code", "probed"), [
    ({"shell": "x"}, "^unknown arguments: shell$", []),
    ({"authority_goal_id": ""}, "^OWNER_AUTHORITY_KEY_REQUIRED:probe$", ["_owner_effect_key"]),
    ({"task_id": ""}, "^task_id is required$", ["_owner_effect_key"]),
    ({"disposition": "APPROVED"}, "^disposition must be REJECTED or SUPERSEDED$", ["_owner_effect_key"]),
    ({"disposition": "SUPERSEDED"}, "^superseded_by is required for SUPERSEDED$", ["_owner_effect_key"]),
    ({"disposition": "SUPERSEDED", "superseded_by": "../x"}, "superseded_by", ["_owner_effect_key"]),
])
def test_dispose_rejects_bad_requests_before_reading_state(tmp_path, events, probes, overrides, code, probed) -> None:
    gateway = _gateway(tmp_path, events)
    with pytest.raises(GatewayInputError, match=code):
        gateway._candidate_dispose(_dispose_args(**overrides))
    assert _names(events) == probed


@pytest.mark.parametrize(("state", "code"), [
    ("missing", "^CANDIDATE_TASK_STATE_REQUIRED$"),
    (_state(controller_revision="A" * 40), "^CANDIDATE_CONTROLLER_REVISION_REQUIRED$"),
])
def test_dispose_rejects_unusable_state_before_owner_authority(tmp_path, events, probes, state, code) -> None:
    gateway = _gateway(tmp_path, events, state)
    with pytest.raises(GatewayInputError, match=code):
        gateway._candidate_dispose(_dispose_args())
    assert "_require_owner_effect_authority" not in _names(events)


def test_dispose_maps_identity_errors_before_owner_authority(tmp_path, events, probes) -> None:
    probes.identity_error = "CONTRACT_HASH_MISMATCH:dispose"
    gateway = _gateway(tmp_path, events)
    with pytest.raises(GatewayInputError, match="^CONTRACT_HASH_MISMATCH:dispose$"):
        gateway._candidate_dispose(_dispose_args())
    assert _names(events)[-1] == "resolve_contract_identity"


def test_dispose_guard_failure_stops_before_the_service(tmp_path, events, probes) -> None:
    probes.guard_error = GatewayInputError("HEAD_DRIFT")
    gateway = _gateway(tmp_path, events)
    with pytest.raises(GatewayInputError, match="^HEAD_DRIFT$"):
        gateway._candidate_dispose(_dispose_args())
    assert _names(events)[-1] == "pre_action_guard"


# --- _candidate_adopt_external / _validate_external_adoption_result -----------------------


def _adoption_receipt(request) -> dict[str, Any]:
    return {
        "schema": "nexus.external_candidate_adoption_receipt.v1",
        "task_id": request.task_id, "attempt_id": request.attempt_id,
        "action_id": request.action_id, "idempotency_key": request.idempotency_key,
        "adoption_request_hash": request.semantic_hash(),
        "task_card_path": request.task_card_path, "task_card_hash": request.task_card_hash,
        "contract_hash": "2" * 64, "controller_revision": request.controller_revision,
        "target_base_revision": request.target_base_revision,
        "candidate_commit_sha": request.candidate_commit_sha,
        "candidate_tree_sha": request.candidate_tree_sha,
        "candidate_diff_sha256": request.candidate_diff_sha256,
        "candidate_state_hash": "3" * 64, "verified_receipt_hash": "4" * 64,
        "validation_receipt_sha256": request.validation_receipt_sha256,
        "acceptance_receipt_sha256": request.acceptance_receipt_sha256,
        "repository_contract_policy_revision_hash": "5" * 64,
        "derived_contract_projection": {}, "forbidden_repository_patterns": [],
        "reviewer_id": "independent-reviewer",
        "candidate_ref": f"refs/nexus-candidates/{request.task_id}/{request.candidate_commit_sha}",
        "promotion_packet_hash": "6" * 64, "worker_invocations": 0,
        "candidate_rewritten": False, "approval_performed": False,
        "integration_performed": False, "merge_performed": False,
        "push_performed": False, "public_claim_allowed": False,
        "production_ready": False,
        "claim_ceiling": ["CANDIDATE_ADOPTED_PENDING_HUMAN_APPROVAL_ONLY"],
        "issued_at": "2026-10-17T00:00:00+00:00",
    }


def _receipt_hash(receipt: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(receipt, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def _adoption_result(request, **overrides: Any) -> dict[str, Any]:
    receipt = _adoption_receipt(request)
    result: dict[str, Any] = {
        "task_id": request.task_id, "status": "PENDING_HUMAN_APPROVAL",
        "promotion_status": "PENDING_HUMAN_APPROVAL",
        "candidate_commit_sha": request.candidate_commit_sha,
        "candidate_tree_sha": request.candidate_tree_sha,
        "candidate_state_hash": receipt["candidate_state_hash"],
        "verified_receipt_hash": receipt["verified_receipt_hash"],
        "candidate_ref": receipt["candidate_ref"],
        "approved_binding": None, "integration_authorization": None,
        "integration_receipt": None, "merge_performed": False,
        "push_performed": False, "public_claim_allowed": False,
        "production_ready": False, "adoption_receipt": receipt,
        "adoption_receipt_hash": _receipt_hash(receipt),
    }
    result.update(overrides)
    return result


def _adoption_arguments(controller_root: Path, **overrides: Any) -> dict[str, Any]:
    from nexus.contracts.lifecycle_action import ExternalCandidateAdoptionRequest

    validation = json.dumps({"schema": "validation"}).encode()
    acceptance_bytes = json.dumps({"schema": "acceptance"}).encode()
    base = {
        "schema": "nexus.external_candidate_adoption_request.v1",
        "repository": gateway_module.GITHUB_REPOSITORY.repository_id,
        "task_id": "adopt-g10", "attempt_id": "attempt-1", "action_id": "action-1",
        "idempotency_key": "idem-1", "task_card_path": "tasks/test/adopt-g10.md", "task_card_hash": "c" * 64,
        "controller_revision": HEAD, "tool_manifest_hash": TOOL_MANIFEST_REVISION,
        "full_tool_schema_hash": FULL_TOOL_SCHEMA_HASH, "permission_policy_hash": PERMISSION_POLICY_HASH,
        "lifecycle_revision": LIFECYCLE_REVISION, "server_instance_id": SERVER_INSTANCE_ID,
        "target_base_revision": "b" * 40, "candidate_commit_sha": "d" * 40, "candidate_tree_sha": "e" * 40,
        "candidate_diff_sha256": "1" * 64, "validation_receipt_sha256": hashlib.sha256(validation).hexdigest(),
        "acceptance_receipt_sha256": hashlib.sha256(acceptance_bytes).hexdigest(),
        "validation_receipt_b64": base64.b64encode(validation).decode(),
        "acceptance_receipt_b64": base64.b64encode(acceptance_bytes).decode(),
        "allowed_files": ("README.md",), "verifier_commands": ("git diff --check",),
        "forbidden_files": (), "authorized_deletions": (), "protected_contracts": (),
    }
    semantic_hash = ExternalCandidateAdoptionRequest.model_construct(**base, action=None).semantic_hash()
    action = build_action_envelope(
        task_id=base["task_id"], action_type=LifecycleActionType.CANDIDATE_ADOPT_EXTERNAL,
        request={"adoption_request_hash": semantic_hash}, tool_manifest_hash=TOOL_MANIFEST_REVISION,
        expected_head=HEAD, allowed_paths=["README.md"], mutation=True,
        task_card_path=base["task_card_path"], task_card_hash=base["task_card_hash"],
        contract_kind=ContractKind.TRACKED_TASK_CARD, permission_profile=PermissionProfile.CANDIDATE,
        approval_scope=ApprovalScope.ALLOW_ACTION_ONCE, mutation_domain=MutationDomain.CANDIDATE_REF,
        attempt_id=base["attempt_id"], action_id=base["action_id"], idempotency_key=base["idempotency_key"],
    ).model_dump(mode="json")
    arguments = {
        **base, **AUTHORITY_ARGS, "action": action,
        "controller_repo_root": str(controller_root), "controller_branch": "main", "controller_head": HEAD,
    }
    arguments.update(overrides)
    return arguments


def test_adopt_call_order_owner_effect_and_payload(tmp_path, events, probes, controller_root) -> None:
    gateway = _gateway(tmp_path, events)
    payload = gateway._call_tool("nexus_candidate_adopt_external", _adoption_arguments(controller_root))
    assert events == [
        ("_require_bound_controller",),
        ("_git", "branch", "--show-current"),
        ("_git", "rev-parse", "HEAD"),
        ("_owner_effect_key", "goal-g10"),
        ("_require_owner_effect_authority", AutonomyActionClass.CANDIDATE_ADOPT_EXTERNAL.value, "KEY"),
        ("_git", "branch", "--show-current"),
        ("_git", "rev-parse", "HEAD"),
        ("service.adopt_external_candidate", "adopt-g10"),
    ]
    (request,) = _service(gateway).calls["adopt_external_candidate"]
    effect = _owner_effect(gateway)
    assert effect["adoption_request_hash"] == request.semantic_hash()
    assert (effect["controller_repo_root"], effect["controller_branch"], effect["controller_head"]) == (
        str(controller_root), "main", HEAD)
    assert (effect["server_instance_id"], effect["lifecycle_revision"], effect["tool_manifest_hash"]) == (
        SERVER_INSTANCE_ID, LIFECYCLE_REVISION, TOOL_MANIFEST_REVISION)
    assert (effect["full_tool_schema_hash"], effect["permission_policy_hash"]) == (FULL_TOOL_SCHEMA_HASH, PERMISSION_POLICY_HASH)
    assert "campaign_id" not in effect
    assert payload["schema"] == "nexus.candidate_adoption_gateway_result.v1"
    assert payload["operation"] == "candidate_adopt_external"
    assert payload["status"] == payload["promotion_status"] == "PENDING_HUMAN_APPROVAL"
    assert payload["owner_authority"]["action"] == AutonomyActionClass.CANDIDATE_ADOPT_EXTERNAL.value
    assert payload["adoption_receipt_hash"] == _receipt_hash(payload["adoption_receipt"])
    assert payload["claim_ceiling"][0] == "CANDIDATE_ADOPTED_PENDING_HUMAN_APPROVAL_ONLY"


def test_adopt_legacy_metadata_is_bound_into_the_owner_effect(tmp_path, events, probes, controller_root) -> None:
    gateway = _gateway(tmp_path, events)
    legacy = {
        "campaign_id": gateway_module._LEGACY_EPB_CAMPAIGN_ID,
        "spec_id": gateway_module._LEGACY_EPB_SPEC_ID,
        "spec_sha256": gateway_module._LEGACY_EPB_SPEC_SHA256,
    }
    gateway._candidate_adopt_external(_adoption_arguments(controller_root, **legacy))
    assert {key: _owner_effect(gateway)[key] for key in legacy} == legacy


@pytest.mark.parametrize(("overrides", "code"), [
    ({"shell": "x"}, "^CANDIDATE_ADOPTION_SCHEMA_CLOSED$"),
    ({"server_instance_id": "other"}, "^CANDIDATE_ADOPTION_SERVER_INSTANCE_MISMATCH$"),
    ({"lifecycle_revision": "other"}, "^CANDIDATE_ADOPTION_LIFECYCLE_REVISION_MISMATCH$"),
    ({"full_tool_schema_hash": "other"}, "^CANDIDATE_ADOPTION_TOOL_SCHEMA_MISMATCH$"),
    ({"permission_policy_hash": "other"}, "^CANDIDATE_ADOPTION_PERMISSION_POLICY_MISMATCH$"),
    ({"campaign_id": "c"}, "^CANDIDATE_ADOPTION_LEGACY_METADATA_INCOMPLETE$"),
    ({"campaign_id": "c", "spec_id": "s", "spec_sha256": "0" * 64}, "^CANDIDATE_ADOPTION_LEGACY_METADATA_MISMATCH$"),
    ({"repository": "other/repo"}, "^CANDIDATE_ADOPTION_REPOSITORY_MISMATCH$"),
])
def test_adopt_rejects_runtime_binding_mismatches_before_git(tmp_path, events, probes, controller_root, overrides, code) -> None:
    gateway = _gateway(tmp_path, events)
    with pytest.raises(GatewayInputError, match=code):
        gateway._candidate_adopt_external(_adoption_arguments(controller_root, **overrides))
    assert _names(events) == ["_require_bound_controller"]


def test_adopt_requires_every_runtime_binding(tmp_path, events, probes, controller_root) -> None:
    arguments = _adoption_arguments(controller_root)
    for key in ("controller_branch", "authority_goal_id"):
        arguments.pop(key)
    gateway = _gateway(tmp_path, events)
    with pytest.raises(GatewayInputError, match="^CANDIDATE_ADOPTION_RUNTIME_BINDING_REQUIRED:authority_goal_id,controller_branch$"):
        gateway._candidate_adopt_external(arguments)


def test_adopt_rejects_controller_mismatches(tmp_path, events, probes, controller_root) -> None:
    gateway = _gateway(tmp_path, events)
    with pytest.raises(GatewayInputError, match="^CANDIDATE_ADOPTION_CONTROLLER_ROOT_MISMATCH$"):
        gateway._candidate_adopt_external(_adoption_arguments(controller_root, controller_repo_root=str(tmp_path)))
    assert _names(events) == ["_require_bound_controller"]
    with pytest.raises(GatewayInputError, match="^CANDIDATE_ADOPTION_CONTROLLER_BRANCH_MISMATCH$"):
        gateway._candidate_adopt_external(_adoption_arguments(controller_root, controller_branch="dev"))
    with pytest.raises(GatewayInputError, match="^CANDIDATE_ADOPTION_CONTROLLER_HEAD_MISMATCH$"):
        gateway._candidate_adopt_external(_adoption_arguments(controller_root, controller_head=OTHER_HEAD))
    with pytest.raises(GatewayInputError, match="^CANDIDATE_ADOPTION_CONTROLLER_REVISION_MISMATCH$"):
        gateway._candidate_adopt_external(_adoption_arguments(controller_root, controller_revision=OTHER_HEAD))
    assert "_require_owner_effect_authority" not in _names(events)


def test_adopt_rejects_invalid_requests_and_action_bindings(tmp_path, events, probes, controller_root, monkeypatch) -> None:
    gateway = _gateway(tmp_path, events)
    with pytest.raises(GatewayInputError, match="^CANDIDATE_ADOPTION_REQUEST_INVALID:"):
        gateway._candidate_adopt_external(_adoption_arguments(controller_root, candidate_commit_sha="nope"))
    arguments = _adoption_arguments(controller_root)
    arguments["action"] = {**arguments["action"], "expected_head": OTHER_HEAD}
    with pytest.raises(GatewayInputError, match="^CANDIDATE_ADOPTION_REQUEST_INVALID:"):
        gateway._candidate_adopt_external(arguments)
    # A gateway whose manifest moved under the request: the facade constant is read at call time.
    monkeypatch.setattr(gateway_module, "TOOL_MANIFEST_REVISION", "moved-manifest")
    with pytest.raises(GatewayInputError, match="^CANDIDATE_ADOPTION_ACTION_MANIFEST_MISMATCH$"):
        gateway._candidate_adopt_external(_adoption_arguments(controller_root))
    assert "_require_owner_effect_authority" not in _names(events)


def test_adopt_refuses_controller_drift_after_authority(tmp_path, events, probes, controller_root) -> None:
    probes.git_heads = [HEAD, OTHER_HEAD]
    gateway = _gateway(tmp_path, events)
    with pytest.raises(GatewayInputError, match="^CANDIDATE_ADOPTION_CONTROLLER_DRIFT_AFTER_AUTHORITY$"):
        gateway._candidate_adopt_external(_adoption_arguments(controller_root))
    assert _names(events)[-3:] == ["_require_owner_effect_authority", "_git", "_git"]
    assert "service.adopt_external_candidate" not in _names(events)


def test_adopt_validates_the_service_result(tmp_path, events, probes, controller_root, monkeypatch) -> None:
    gateway = _gateway(tmp_path, events)
    monkeypatch.setattr(_service(gateway), "adopt_external_candidate", lambda request: _adoption_result(request, merge_performed=True))
    with pytest.raises(GatewayInputError, match="^CANDIDATE_ADOPTION_SERVICE_RESULT_UNEXPECTED_DOWNSTREAM_FIELD$"):
        gateway._candidate_adopt_external(_adoption_arguments(controller_root))


def _request(controller_root: Path):
    from nexus.contracts.lifecycle_action import ExternalCandidateAdoptionRequest

    arguments = _adoption_arguments(controller_root)
    return ExternalCandidateAdoptionRequest.model_validate(
        {key: arguments[key] for key in ExternalCandidateAdoptionRequest.model_fields if key in arguments}
    )


def test_validate_adoption_result_accepts_a_pending_receipt(controller_root) -> None:
    request = _request(controller_root)
    assert UnifiedMCPGateway._validate_external_adoption_result(_adoption_result(request), request) is None
    assert UnifiedMCPGateway._validate_external_adoption_result(_adoption_result(request)) is None


def _mutate_receipt(request, **changes: Any) -> dict[str, Any]:
    receipt = {**_adoption_receipt(request), **changes}
    for key in [key for key, value in changes.items() if value is KeyError]:
        receipt.pop(key)
    return _adoption_result(request, adoption_receipt=receipt, adoption_receipt_hash=_receipt_hash(receipt))


@pytest.mark.parametrize(("build", "code"), [
    (lambda r: [], "RESULT_INVALID"),
    (lambda r: _adoption_result(r, status="APPROVED"), "RESULT_NOT_PENDING"),
    (lambda r: _adoption_result(r, adoption_receipt_hash="x"), "RESULT_RECEIPT_REQUIRED"),
    (lambda r: _adoption_result(r, adoption_receipt_hash="0" * 64), "RESULT_RECEIPT_HASH_MISMATCH"),
    (lambda r: _mutate_receipt(r, issued_at=KeyError), "RESULT_RECEIPT_FIELDS_INVALID"),
    (lambda r: _mutate_receipt(r, worker_invocations=1), "RESULT_RECEIPT_SEMANTICS_INVALID"),
    (lambda r: _mutate_receipt(r, task_id="other"), "RESULT_RECEIPT_SUBJECT_MISMATCH"),
    (lambda r: _mutate_receipt(r, contract_hash="short"), "RESULT_RECEIPT_HASH_FIELD_INVALID"),
    (lambda r: _adoption_result(r, candidate_ref="refs/other"), "RESULT_RECEIPT_STATE_MISMATCH"),
    (lambda r: _mutate_receipt(r, derived_contract_projection={"x": 1}, reviewer_id="r", forbidden_repository_patterns=["approved_x"]), None),
    (lambda r: _adoption_result(r, release_receipt={}), "RESULT_UNEXPECTED_DOWNSTREAM_FIELD"),
    (lambda r: _adoption_result(r, integration_receipt={"x": 1}), "RESULT_UNEXPECTED_DOWNSTREAM_FIELD"),
    (lambda r: _adoption_result(r, push_performed=None), "RESULT_DOWNSTREAM_EFFECT"),
    (lambda r: _adoption_result(r, claim_ceiling=["MERGE_READY"]), "RESULT_CLAIM_CEILING"),
    (lambda r: _adoption_result(r, claim_ceiling="NONE"), "RESULT_CLAIM_CEILING"),
])
def test_validate_adoption_result_error_codes(controller_root, build, code) -> None:
    request = _request(controller_root)
    if code is None:
        assert UnifiedMCPGateway._validate_external_adoption_result(build(request), request) is None
        return
    with pytest.raises(GatewayInputError, match=f"^CANDIDATE_ADOPTION_SERVICE_{code}$"):
        UnifiedMCPGateway._validate_external_adoption_result(build(request), request)
