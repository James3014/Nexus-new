from __future__ import annotations

from pathlib import Path
from typing import Any

from nexus.engine.s2t_policy_loader import (
    load_s2t_policy_draft_budget,
    merge_runtime_s2t_policy_draft,
    s2t_promotion_gate_passed,
)


class InMemoryJsonPolicyStore:
    def __init__(self, payloads: dict[str, dict[str, Any]]) -> None:
        self.payloads = payloads

    def read_json_policy(self, path: Path) -> dict[str, Any]:
        return dict(self.payloads.get(path.name, {}))


def test_load_s2t_policy_draft_budget_accepts_shadow_only_rules(tmp_path: Path):
    store = InMemoryJsonPolicyStore(
        {
            "promoted_s2t_policy_draft.json": {
                "schema": "nexus_promoted_s2t_policy_draft_v1",
                "status": "DRAFT_SHADOW_ONLY",
                "source_schema": "nexus_s2t_shadow_report_v1",
                "trace_event_schema": "nexus_s2t_trace_event_v1",
                "task_rules": {"task-a": {"recommended_action": "try_standard_with_cost_cap"}},
            }
        }
    )

    budget = load_s2t_policy_draft_budget(tmp_path / "promoted_s2t_policy_draft.json", store=store)

    assert budget["s2t_policy_draft"]["status"] == "DRAFT_SHADOW_ONLY"
    assert budget["s2t_policy_draft"]["runtime_promotable"] is False
    assert budget["s2t_policy_draft"]["task_rules"]["task-a"]["recommended_action"] == "try_standard_with_cost_cap"


def test_load_s2t_policy_draft_budget_requires_gate_for_runtime_promotion(tmp_path: Path):
    blocked_store = InMemoryJsonPolicyStore(
        {
            "promoted_s2t_policy_draft.json": {
                "schema": "nexus_promoted_s2t_policy_draft_v1",
                "status": "PROMOTED_RUNTIME",
                "promotion_gate": {"passed": False, "trust_mismatch_rate": 0, "sample_count": 5, "rollback_policy": "disable"},
                "task_rules": {"task-a": {"recommended_action": "try_lite_with_defensive_gate"}},
            }
        }
    )
    promoted_store = InMemoryJsonPolicyStore(
        {
            "promoted_s2t_policy_draft.json": {
                "schema": "nexus_promoted_s2t_policy_draft_v1",
                "status": "PROMOTED_RUNTIME",
                "promotion_gate": {
                    "passed": True,
                    "trust_mismatch_rate": 0,
                    "sample_count": 5,
                    "rollback_policy": "set NEXUS_DISABLE_S2T_POLICY_DRAFT=1",
                },
                "task_rules": {"task-a": {"recommended_action": "try_lite_with_defensive_gate"}},
            }
        }
    )

    assert load_s2t_policy_draft_budget(tmp_path / "promoted_s2t_policy_draft.json", store=blocked_store) == {}
    budget = load_s2t_policy_draft_budget(tmp_path / "promoted_s2t_policy_draft.json", store=promoted_store)
    assert budget["s2t_policy_draft"]["runtime_promotable"] is True


def test_merge_runtime_s2t_policy_draft_preserves_existing_budget(tmp_path: Path):
    existing = {"s2t_policy_draft": {"status": "EXISTING"}}

    assert merge_runtime_s2t_policy_draft(tmp_path, existing) == existing


def test_s2t_promotion_gate_passed_requires_clean_trust_sample_and_rollback():
    assert s2t_promotion_gate_passed(
        {"promotion_gate": {"passed": True, "trust_mismatch_rate": 0, "sample_count": 1, "rollback_policy": "disable"}}
    ) is True
    assert s2t_promotion_gate_passed(
        {"promotion_gate": {"passed": True, "trust_mismatch_rate": 0.1, "sample_count": 1, "rollback_policy": "disable"}}
    ) is False
    assert s2t_promotion_gate_passed(
        {"promotion_gate": {"passed": True, "trust_mismatch_rate": 0, "sample_count": 0, "rollback_policy": "disable"}}
    ) is False
    assert s2t_promotion_gate_passed(
        {"promotion_gate": {"passed": True, "trust_mismatch_rate": 0, "sample_count": 1, "rollback_policy": ""}}
    ) is False
