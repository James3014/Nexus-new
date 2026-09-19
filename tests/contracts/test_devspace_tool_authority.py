from copy import deepcopy

import pytest

from nexus.contracts.devspace_tool_authority import (
    CANONICAL_TOOL_INTENTS,
    TOOL_AUTHORITY_SCHEMA,
    TOOL_INTENT_NAMESPACE,
    build_governed_tool_authority,
    build_tool_authority_fragment,
    build_tool_projection_manifest,
    canonicalize_tool_intents,
    hash_tool_authority_policy,
    tool_authority_policy,
    tool_authority_policy_hash,
)
from nexus.engine.canonical_task_seam import CanonicalDispatchEnvelope


def _envelope(*, decision: str = "a" * 64, plan: str = "b" * 64) -> dict:
    return {
        "schema": "nexus.canonical_dispatch_envelope.v1",
        "task_id": "issue-982-wave-b-canary",
        "attempt_id": "attempt-01",
        "planner_decision_hash": decision,
        "planner_plan_hash": plan,
    }


READ_ONLY = [
    "workspace.read",
    "workspace.search_text",
    "workspace.search_paths",
    "workspace.list",
]


def test_effect_ceiling_projection_is_exact_and_policy_bound() -> None:
    read_only = build_governed_tool_authority(_envelope(), "READ_ONLY")
    mutation = build_governed_tool_authority(_envelope(), "WORKSPACE_MUTATION")
    candidate = build_governed_tool_authority(_envelope(), "CANDIDATE")

    assert read_only["schema"] == TOOL_AUTHORITY_SCHEMA
    assert read_only["namespace"] == TOOL_INTENT_NAMESPACE
    assert read_only["authorizedToolCeiling"] == READ_ONLY
    assert mutation["authorizedToolCeiling"] == list(CANONICAL_TOOL_INTENTS)
    assert candidate["authorizedToolCeiling"] == list(CANONICAL_TOOL_INTENTS)
    assert read_only["policyHash"] == tool_authority_policy_hash()


def test_policy_hash_is_deterministic_and_changes_with_policy_content() -> None:
    policy = tool_authority_policy()
    assert hash_tool_authority_policy(policy) == hash_tool_authority_policy(deepcopy(policy))
    changed = deepcopy(policy)
    changed["effectCeilings"]["READ_ONLY"] = ["workspace.read"]
    assert hash_tool_authority_policy(changed) != hash_tool_authority_policy(policy)


def test_unknown_effect_and_malformed_intents_fail_closed() -> None:
    with pytest.raises(ValueError, match="effect_ceiling_unknown"):
        build_governed_tool_authority(_envelope(), "UNKNOWN")
    with pytest.raises(ValueError, match="candidate_tools_duplicate"):
        canonicalize_tool_intents(["workspace.read", "workspace.read"], field="candidate_tools")
    with pytest.raises(ValueError, match="candidate_tools_unknown"):
        canonicalize_tool_intents(["workspace.read", "provider.magic"], field="candidate_tools")


def test_manifest_binds_planner_identity_and_subset_relations() -> None:
    envelope = _envelope()
    authority = build_governed_tool_authority(envelope, "READ_ONLY")
    manifest = build_tool_projection_manifest(
        envelope,
        authority,
        candidate_tools=READ_ONLY,
        selected_tools=["workspace.read"],
    )
    assert manifest == {
        "schema": "devspace.tool_projection_manifest.v1",
        "namespace": "devspace.tool_intent.v1",
        "identity": {"taskId": "issue-982-wave-b-canary", "attemptId": "attempt-01"},
        "authority": {"mode": "NEXUS_GOVERNED", "issuer": "nexus"},
        "authorizedToolCeiling": READ_ONLY,
        "candidateTools": READ_ONLY,
        "selectedTools": ["workspace.read"],
        "orderingMode": "ORDER_INDEPENDENT",
    }
    assert build_tool_authority_fragment(authority) == {"toolAuthority": authority}

    with pytest.raises(ValueError, match="planner_decision_mismatch"):
        build_tool_projection_manifest(
            _envelope(decision="c" * 64),
            authority,
            candidate_tools=READ_ONLY,
            selected_tools=["workspace.read"],
        )
    with pytest.raises(ValueError, match="candidate_tools_exceed_authorized_ceiling"):
        build_tool_projection_manifest(
            envelope,
            authority,
            candidate_tools=[*READ_ONLY, "workspace.mutate"],
            selected_tools=["workspace.read"],
        )
    with pytest.raises(ValueError, match="selected_tools_exceed_candidate_tools"):
        build_tool_projection_manifest(
            envelope,
            authority,
            candidate_tools=["workspace.read"],
            selected_tools=["workspace.search_text"],
        )


def test_real_canonical_dispatch_envelope_binds_planner_identity() -> None:
    envelope = CanonicalDispatchEnvelope(
        schema="nexus.canonical_dispatch_envelope.v1",
        task_id="issue-982-wave-b-real-envelope",
        attempt_id="attempt-real-1",
        task_card_path="tasks/github-issue-982-wave-b-20260919/01-nexus-governed-tool-authority.md",
        task_card_hash="c" * 64,
        demand_id="demand-1",
        planner_decision_hash="d" * 64,
        planner_plan_hash="e" * 64,
        worker_id="worker-1",
        provider="opencode",
        model="opencode/big-pickle",
        policy_hash="f" * 64,
        binding_hash="1" * 64,
        aggregate_binding_hash="2" * 64,
    )
    authority = build_governed_tool_authority(envelope, "READ_ONLY")
    assert authority["plannerDecisionHash"] == envelope.planner_decision_hash
    assert authority["plannerPlanHash"] == envelope.planner_plan_hash
