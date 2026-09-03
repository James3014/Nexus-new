from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest

from nexus.contracts.learning_experience import (
    build_learning_policy_adoption,
    build_learning_policy_recommendation,
    build_learning_policy_rollback,
    build_nexus_learning_episode,
    evaluate_learning_policy_recommendation,
)
from nexus.engine.learning_policy_loader import merge_runtime_learning_policy


def _governed_adoption(source_revision: str = "rev-current") -> dict[str, Any]:
    episode = build_nexus_learning_episode(
        task_id="task-a",
        source="runtime_closure",
        terminal_outcome="SUCCESS",
        terminal_evidence={"verifier": "pytest", "receipt": "receipt-a", "verifier_status": "passed"},
        qualification={"repeatability": True, "prevention_rule": "preserve serialization", "authority_qualification": True},
        lesson_disposition="graduated",
        learning_write_succeeded=True,
    )
    recommendation = build_learning_policy_recommendation(
        source_episodes=[episode],
        source_evidence_refs=["receipt-a", "retrieval-receipt-a", "physical-consumption-a"],
        source_revision=source_revision,
        runtime_identity="local_model_executor",
        task_fingerprint="task-1",
        off_arm={"task_id": "task-1", "verifier_status": "failed", "receipt": "off-r"},
        on_arm={"task_id": "task-1", "verifier_status": "passed", "receipt": "on-r"},
        applicable_scope={"task_family": "record_serialization", "model_name": "qwen2.5-coder:7b", "runtime_identity": "local_model_executor"},
        recommended_policy_delta={"episodic_memory_injection": {"enabled": True, "scope": "record_serialization"}},
        current_policy={"episodic_memory_injection": {"enabled": False}},
        expected_effect="bounded memory use",
        rollback_target={"target_state": {"episodic_memory_injection": {"enabled": False}}, "trigger": "regression"},
    )
    validation = evaluate_learning_policy_recommendation(
        recommendation,
        validator_identity="independent-verifier",
        current_workspace_revision=source_revision,
        current_runtime_identity="local_model_executor",
    )
    return build_learning_policy_adoption(
        owner_authority_reference="owner:g20",
        recommendation=recommendation,
        validation=validation,
        source_revision=source_revision,
        adopted_scope={"task_family": "record_serialization", "model_name": "qwen2.5-coder:7b", "runtime_identity": "local_model_executor"},
        target_policy_delta={"episodic_memory_injection": {"enabled": True, "scope": "record_serialization"}},
        previous_policy={"episodic_memory_injection": {"enabled": False}},
        rollback_target={"target_state": {"episodic_memory_injection": {"enabled": False}}, "trigger": "regression"},
    )


class InMemoryLearningPolicyStore:
    def __init__(self, promoted: dict[str, Any] | None = None, json_payloads: dict[str, dict[str, Any]] | None = None) -> None:
        self.promoted = promoted or {}
        self.json_payloads = json_payloads or {}
        self.read_paths: list[str] = []

    def read_promoted_policy(self, path: Path) -> dict[str, Any]:
        self.read_paths.append(path.as_posix())
        return dict(self.promoted.get(path.name, {}))

    def read_json_policy(self, path: Path) -> dict[str, Any]:
        self.read_paths.append(path.as_posix())
        return dict(self.json_payloads.get(path.name, {}))


def test_merge_runtime_learning_policy_uses_store_interface(tmp_path: Path) -> None:
    store = InMemoryLearningPolicyStore(
        promoted={
            "promoted_learning_policy.json": {
                "schema_version": "nexus_promoted_learning_policy.v1",
                "source_experiences": ["static"],
                "promoted_capabilities": ["hyper"],
                "penalized_capabilities": [],
            },
            "promoted_route_cost_policy.json": {
                "schema_version": "nexus_promoted_route_cost_policy.v1",
                "source": "memory://route",
                "feature_rules": [{"id": "compact", "match": {"repo_kind": "fixture"}, "controls": {"max_rounds": 1}}],
            },
        },
        json_payloads={
            "dynamic_learning_policy.json": {
                "schema_version": "nexus_dynamic_learning_policy.v1",
                "status": "PASS",
                "source_experiences": ["dynamic"],
                "promoted_capabilities": ["research"],
                "penalized_capabilities": ["swarm"],
            },
            "promoted_s2t_policy_draft.json": {
                "schema": "nexus_promoted_s2t_policy_draft_v1",
                "status": "DRAFT_SHADOW_ONLY",
                "task_rules": {"task-a": {"route": "baseline"}},
            },
        },
    )

    merged = merge_runtime_learning_policy(tmp_path, store=store)

    assert merged["learning_policy"]["source_experiences"] == ["dynamic", "static"]
    assert merged["learning_policy"]["promoted_capabilities"] == ["hyper", "research"]
    assert merged["learning_policy"]["penalized_capabilities"] == ["swarm"]
    assert merged["route_cost_policy"]["source"] == "memory://route"
    assert merged["s2t_policy_draft"]["task_rules"] == {"task-a": {"route": "baseline"}}
    assert any(path.endswith("dynamic_learning_policy.json") for path in store.read_paths)


def test_governed_adoption_projects_through_existing_runtime_store(tmp_path: Path) -> None:
    adoption = _governed_adoption()
    store = InMemoryLearningPolicyStore(
        promoted={
            "promoted_learning_policy.json": {
                "schema_version": "nexus_promoted_learning_policy.v1",
                "source_experiences": ["legacy-evidence"],
                "promoted_capabilities": ["hyper"],
                "penalized_capabilities": [],
            }
        },
        json_payloads={"governed_learning_policy_adoption.json": adoption},
    )

    budget = merge_runtime_learning_policy(
        tmp_path,
        store=store,
        task_desc="repair record_serialization for user profile",
        target_model="qwen2.5-coder:7b",
        runtime_identity="local_model_executor",
        source_revision="rev-current",
    )

    policy = budget["learning_policy"]
    assert policy["episodic_memory_injection"] == {"enabled": True, "scope": "record_serialization"}
    assert policy["adoption_lineage"]["adoption_id"] == adoption["adoption_id"]
    assert policy["adoption_lineage"]["status"] == "ACTIVE_CANDIDATE"
    assert policy["promoted_capabilities"] == ["hyper"]
    assert policy["source_experiences"] == ["legacy-evidence"]
    assert any(path.endswith("governed_learning_policy_adoption.json") for path in store.read_paths)


def test_governed_adoption_fails_closed_when_source_is_stale(tmp_path: Path) -> None:
    adoption = _governed_adoption("rev-old")
    store = InMemoryLearningPolicyStore(json_payloads={"governed_learning_policy_adoption.json": adoption})

    budget = merge_runtime_learning_policy(
        tmp_path,
        store=store,
        task_desc="repair record_serialization",
        target_model="qwen2.5-coder:7b",
        runtime_identity="local_model_executor",
        source_revision="rev-current",
    )

    policy = budget["learning_policy"]
    assert policy["episodic_memory_injection"]["enabled"] is False
    assert policy["adoption_lineage"]["status"] == "STALE_SOURCE"


def test_governed_adoption_scope_mismatch_stays_inactive(tmp_path: Path) -> None:
    adoption = _governed_adoption()
    store = InMemoryLearningPolicyStore(json_payloads={"governed_learning_policy_adoption.json": adoption})

    budget = merge_runtime_learning_policy(
        tmp_path,
        store=store,
        task_desc="unrelated database optimization",
        target_model="qwen2.5-coder:7b",
        runtime_identity="local_model_executor",
        source_revision="rev-current",
    )

    policy = budget["learning_policy"]
    assert policy["episodic_memory_injection"]["enabled"] is False
    assert policy["adoption_lineage"]["status"] == "OUT_OF_SCOPE"


def test_governed_rollback_reconstructs_inactive_policy(tmp_path: Path) -> None:
    adoption = _governed_adoption()
    rollback = build_learning_policy_rollback(adoption=adoption, reason="g20 rollback witness")
    store = InMemoryLearningPolicyStore(
        json_payloads={
            "governed_learning_policy_adoption.json": adoption,
            "governed_learning_policy_rollback.json": rollback,
        }
    )

    budget = merge_runtime_learning_policy(
        tmp_path,
        store=store,
        task_desc="repair record_serialization",
        target_model="qwen2.5-coder:7b",
        runtime_identity="local_model_executor",
        source_revision="rev-current",
    )

    policy = budget["learning_policy"]
    assert policy["episodic_memory_injection"]["enabled"] is False
    assert policy["adoption_lineage"]["status"] == "ROLLED_BACK"
    assert policy["adoption_lineage"]["rollback_id"] == rollback["rollback_id"]


def test_tampered_governed_adoption_blocks_runtime_projection(tmp_path: Path) -> None:
    adoption = _governed_adoption()
    tampered = copy.deepcopy(adoption)
    tampered["target_policy_delta"]["episodic_memory_injection"]["enabled"] = False
    store = InMemoryLearningPolicyStore(json_payloads={"governed_learning_policy_adoption.json": tampered})

    with pytest.raises(ValueError, match="ADOPTION_CONTENT_ADDRESS_MISMATCH"):
        merge_runtime_learning_policy(
            tmp_path,
            store=store,
            task_desc="repair record_serialization",
            target_model="qwen2.5-coder:7b",
            runtime_identity="local_model_executor",
            source_revision="rev-current",
        )
