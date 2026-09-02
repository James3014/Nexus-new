import hashlib
from pathlib import Path

import pytest

from nexus.contracts.lifecycle_action import (
    ApprovalScope,
    ContractKind,
    ExternalCandidateAdoptionRequest,
    HistoricalEpbTaskCardProjection,
    LifecycleActionType,
    MutationDomain,
    PermissionProfile,
    build_action_envelope,
    canonical_request_hash,
    parse_historical_epb_task_card,
)

HEAD = "a" * 40
MANIFEST = "b" * 64


def _adoption_request(**overrides):
    payload = {
        "schema": "nexus.external_candidate_adoption_request.v1",
        "repository": "James3014/Nexus-new",
        "task_id": "TASK-EPB-001-R1",
        "attempt_id": "attempt-adopt-1",
        "action_id": "action-adopt-1",
        "idempotency_key": "TASK-EPB-001-R1:adopt-1",
        "task_card_path": "tasks/evidence-producer-bridge-20260830/01-evidence-producer-bridge-r1.md",
        "task_card_hash": "c" * 64,
        "controller_revision": "d" * 40,
        "tool_manifest_hash": MANIFEST,
        "full_tool_schema_hash": "3" * 64,
        "permission_policy_hash": "4" * 64,
        "lifecycle_revision": "nexus.lifecycle.gateway.v2",
        "server_instance_id": "server-test-1",
        "target_base_revision": "e" * 40,
        "candidate_commit_sha": "f" * 40,
        "candidate_tree_sha": "1" * 40,
        "candidate_diff_sha256": "2" * 64,
        "validation_receipt_sha256": hashlib.sha256(b"{}").hexdigest(),
        "acceptance_receipt_sha256": hashlib.sha256(b"{}").hexdigest(),
        "validation_receipt_b64": "e30=",
        "acceptance_receipt_b64": "e30=",
        "allowed_files": ("nexus/example.py",),
        "forbidden_files": (),
        "authorized_deletions": (),
        "verifier_commands": ("git diff --check",),
        "protected_contracts": (),
    }
    payload.update(overrides)
    semantic_hash = ExternalCandidateAdoptionRequest.semantic_hash_for(payload)
    payload["action"] = build_action_envelope(
        task_id=payload["task_id"],
        action_type=LifecycleActionType.CANDIDATE_ADOPT_EXTERNAL,
        request={"adoption_request_hash": semantic_hash},
        tool_manifest_hash=payload["tool_manifest_hash"],
        expected_head=payload["controller_revision"],
        allowed_paths=payload["allowed_files"],
        mutation=True,
        mutation_domain=MutationDomain.CANDIDATE_REF,
        permission_profile=PermissionProfile.CANDIDATE,
        task_card_path=payload["task_card_path"],
        task_card_hash=payload["task_card_hash"],
        contract_kind=ContractKind.TRACKED_TASK_CARD,
        attempt_id=payload["attempt_id"],
        action_id=payload["action_id"],
        idempotency_key=payload["idempotency_key"],
    )
    return payload


def test_external_candidate_adoption_request_is_closed_and_exactly_bound():
    request = ExternalCandidateAdoptionRequest(**_adoption_request())
    assert request.action.action_type is LifecycleActionType.CANDIDATE_ADOPT_EXTERNAL
    assert request.action.mutation_domain is MutationDomain.CANDIDATE_REF
    assert request.action.permission_profile is PermissionProfile.CANDIDATE
    assert request.action.verify_request({"adoption_request_hash": request.semantic_hash()})


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("candidate_commit_sha", "HEAD"),
        ("candidate_tree_sha", "0" * 39),
        ("candidate_diff_sha256", "0" * 63),
        ("validation_receipt_b64", "not base64!"),
        ("acceptance_receipt_b64", ""),
    ],
)
def test_external_candidate_adoption_request_rejects_malformed_bindings(field, value):
    with pytest.raises(ValueError):
        ExternalCandidateAdoptionRequest(**_adoption_request(**{field: value}))


def test_external_candidate_adoption_request_rejects_authority_or_semantic_drift():
    request = _adoption_request()
    request["candidate_tree_sha"] = "9" * 40
    with pytest.raises(ValueError, match="request hash"):
        ExternalCandidateAdoptionRequest(**request)
    with pytest.raises(ValueError):
        ExternalCandidateAdoptionRequest(**{**_adoption_request(), "approved_binding": {}})


@pytest.mark.parametrize(
    "overrides",
    [
        {"schema": "nexus.external_candidate_adoption_request.v2"},
        {"repository": ""},
        {"validation_receipt_sha256": "0" * 64},
        {"forbidden_files": ("nexus/example.py",)},
        {"authorized_deletions": ("outside.py",)},
    ],
)
def test_external_candidate_adoption_request_rejects_cross_field_authority_widening(overrides):
    with pytest.raises(ValueError):
        ExternalCandidateAdoptionRequest(**_adoption_request(**overrides))


def test_external_candidate_adoption_request_rejects_action_scope_drift():
    payload = _adoption_request()
    payload["action"] = payload["action"].model_copy(update={"allowed_paths": ("outside.py",)})
    with pytest.raises(ValueError, match="identity mismatch"):
        ExternalCandidateAdoptionRequest(**payload)


@pytest.mark.parametrize(
    "field",
    ["tool_manifest_hash", "full_tool_schema_hash", "permission_policy_hash"],
)
def test_external_candidate_adoption_request_rejects_runtime_hash_drift(field):
    with pytest.raises(ValueError):
        ExternalCandidateAdoptionRequest(**_adoption_request(**{field: "not-a-sha"}))


def test_external_candidate_adoption_request_binds_action_tool_manifest():
    payload = _adoption_request()
    payload["action"] = payload["action"].model_copy(update={"tool_manifest_hash": "9" * 64})
    with pytest.raises(ValueError, match="identity mismatch"):
        ExternalCandidateAdoptionRequest(**payload)


def test_action_envelope_round_trips_and_hashes_canonically():
    request = {"what": "bounded", "allowed_files": ["README.md"]}
    envelope = build_action_envelope(
        task_id="task-1",
        action_type=LifecycleActionType.TASK_RUN,
        request=request,
        tool_manifest_hash=MANIFEST,
        expected_head=HEAD,
        allowed_paths=["README.md"],
        mutation=True,
        permission_profile=PermissionProfile.MUTATE_BOUNDED,
        task_card_path="tasks/campaign/card.md",
        task_card_hash=MANIFEST,
    )
    assert envelope.schema == "nexus.lifecycle_action.v1"
    assert envelope.verify_request({"allowed_files": ["README.md"], "what": "bounded"})
    assert envelope.request_hash == canonical_request_hash(request)
    assert envelope.model_dump()["approval_scope"] == ApprovalScope.ALLOW_ACTION_ONCE


@pytest.mark.parametrize(
    "payload",
    [
        {"task_id": "../bad"},
        {"expected_head": "HEAD"},
        {"allowed_paths": ["../escape"]},
        {"task_card_path": "/tmp/card.md"},
    ],
)
def test_action_envelope_rejects_malformed_identity(payload):
    base = {
        "task_id": "task-1",
        "attempt_id": "attempt-1",
        "action_id": "action-1",
        "idempotency_key": "key-1",
        "action_type": LifecycleActionType.TASK_RUN,
        "tool_manifest_hash": MANIFEST,
        "request_hash": MANIFEST,
        "expected_head": HEAD,
        "allowed_paths": ("README.md",),
        "permission_profile": PermissionProfile.MUTATE_BOUNDED,
        "mutation": True,
    }
    base.update(payload)
    with pytest.raises(ValueError):
        from nexus.contracts.lifecycle_action import LifecycleActionEnvelope

        LifecycleActionEnvelope(**base)


def test_same_idempotency_key_with_different_request_hash_is_detectable():
    first = build_action_envelope(
        task_id="task-1",
        action_type=LifecycleActionType.TASK_RUN,
        request={"value": 1},
        tool_manifest_hash=MANIFEST,
        expected_head=HEAD,
        allowed_paths=["README.md"],
        mutation=True,
        idempotency_key="stable-key",
        permission_profile=PermissionProfile.MUTATE_BOUNDED,
    )
    second = build_action_envelope(
        task_id="task-1",
        action_type=LifecycleActionType.TASK_RUN,
        request={"value": 2},
        tool_manifest_hash=MANIFEST,
        expected_head=HEAD,
        allowed_paths=["README.md"],
        mutation=True,
        idempotency_key="stable-key",
        permission_profile=PermissionProfile.MUTATE_BOUNDED,
    )
    assert first.idempotency_key == second.idempotency_key
    assert first.request_hash != second.request_hash
    assert not first.verify_request({"value": 2})


def test_mutation_domain_separates_repository_and_lifecycle_state():
    state_action = build_action_envelope(
        task_id="task-state",
        action_type=LifecycleActionType.CANDIDATE_APPROVE,
        request={"task_id": "task-state"},
        tool_manifest_hash=MANIFEST,
        expected_head=HEAD,
        allowed_paths=[],
        mutation=True,
        mutation_domain=MutationDomain.LIFECYCLE_STATE,
        permission_profile=PermissionProfile.CANDIDATE,
    )
    assert state_action.mutation_domain == MutationDomain.LIFECYCLE_STATE


@pytest.mark.parametrize("kwargs", [{"task_card_path": "tasks/card.md"}, {"task_card_hash": MANIFEST}])
def test_task_card_binding_pair_is_required(kwargs):
    with pytest.raises(ValueError, match="task_card_path and task_card_hash"):
        build_action_envelope(
            task_id="task-pair",
            action_type=LifecycleActionType.TASK_RUN,
            request={"value": 1},
            tool_manifest_hash=MANIFEST,
            expected_head=HEAD,
            allowed_paths=["README.md"],
            mutation=True,
            permission_profile=PermissionProfile.MUTATE_BOUNDED,
            **kwargs,
        )


_HISTORICAL_CARD = """# Task Card: TASK-EPB-001-R1

`AUTO_CHAIN=false`

## Allowed repository paths

Production paths, maximum `6`:

- `nexus/foo.py`
- `tests/test_foo.py`

## Forbidden scope

- `nexus/private.py`
- Task4 and release.

## Exact verification commands

- `uv run pytest -q tests/test_foo.py`
- `git diff --check`
"""


def test_historical_epb_card_parser_extracts_only_frozen_sections():
    projection = parse_historical_epb_task_card(_HISTORICAL_CARD.encode("utf-8"))

    assert projection == HistoricalEpbTaskCardProjection(
        allowed_repository_paths=("nexus/foo.py", "tests/test_foo.py"),
        forbidden_scope=("nexus/private.py", "Task4 and release."),
        exact_verification_commands=("uv run pytest -q tests/test_foo.py", "git diff --check"),
        auto_chain=False,
        forbidden_repository_paths=("nexus/private.py",),
    )


def test_historical_epb_card_parser_classifies_forbidden_repository_tokens():
    projection = parse_historical_epb_task_card(_HISTORICAL_CARD.encode("utf-8"))

    assert projection.forbidden_repository_paths == ("nexus/private.py",)
    assert projection.forbidden_repository_patterns == ()


def test_historical_epb_card_parser_classifies_actual_card_paths_and_patterns():
    card = _HISTORICAL_CARD.replace(
        "- `nexus/private.py`",
        "- `nexus/evidence/*`\n- `product/**`",
    ).encode("utf-8")

    projection = parse_historical_epb_task_card(card)

    assert projection.forbidden_repository_paths == ()
    assert projection.forbidden_repository_patterns == ("nexus/evidence/*", "product/**")


def test_historical_epb_card_parser_rejects_current_card_fixture():
    card = Path(
        "tasks/evidence-producer-bridge-current-main-20260902/01-core-external-candidate-adoption.md"
    ).read_bytes()

    with pytest.raises(ValueError, match="ADOPTION_CARD_CONTRACT_UNRESOLVABLE"):
        parse_historical_epb_task_card(card)


@pytest.mark.parametrize("token", ["nexus//bad", "nexus/evidence/*/bad", "nexus/evidence/**/bad"])
def test_historical_epb_card_parser_rejects_malformed_path_like_forbidden_tokens(token):
    card = _HISTORICAL_CARD.replace("- `nexus/private.py`", f"- `{token}`")

    with pytest.raises(ValueError, match="ADOPTION_CARD_CONTRACT_UNRESOLVABLE"):
        parse_historical_epb_task_card(card.encode("utf-8"))


@pytest.mark.parametrize(
    "card",
    [
        _HISTORICAL_CARD.replace("## Forbidden scope", "## Forbidden scope\n## Forbidden scope"),
        _HISTORICAL_CARD.replace("- `git diff --check`", "git diff --check"),
        _HISTORICAL_CARD.replace("`AUTO_CHAIN=false`", "AUTO_CHAIN=true"),
        _HISTORICAL_CARD.replace("## Allowed repository paths", "## Missing allowed paths"),
        _HISTORICAL_CARD.replace("- `nexus/foo.py`", "- nexus/foo.py"),
    ],
)
def test_historical_epb_card_parser_fails_closed_on_ambiguous_or_malformed_input(card):
    with pytest.raises(ValueError, match="ADOPTION_CARD_CONTRACT_UNRESOLVABLE"):
        parse_historical_epb_task_card(card.encode("utf-8"))


def test_historical_epb_card_parser_requires_exact_bytes_input():
    with pytest.raises(ValueError, match="ADOPTION_CARD_CONTRACT_UNRESOLVABLE"):
        parse_historical_epb_task_card(_HISTORICAL_CARD)
