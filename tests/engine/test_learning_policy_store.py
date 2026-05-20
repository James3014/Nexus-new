from __future__ import annotations

from pathlib import Path
from typing import Any

from nexus.engine.learning_policy_loader import merge_runtime_learning_policy


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
