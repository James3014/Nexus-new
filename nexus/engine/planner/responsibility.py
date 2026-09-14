"""Planner responsibility classification without changing selection behavior.

This contract separates system-enforced obligations from replaceable cognitive
strategy. It is descriptive/guardrail metadata for Planner evolution; current
CapabilityPlanner routing and capability-selection semantics remain unchanged.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

PLANNER_RESPONSIBILITY_SCHEMA = "nexus.planner.responsibility.v1"
PLANNER_AUTHORITY_OWNER = "James3014/Nexus-new"

HARD_OBLIGATIONS: tuple[str, ...] = (
    "authority_constraints",
    "resource_effect_and_path_scope",
    "risk_floors",
    "required_evidence",
    "required_verifiers",
    "stop_conditions",
    "replan_authorization",
    "effect_identity_and_retry_constraints",
)

SOFT_STRATEGIES: tuple[str, ...] = (
    "task_decomposition",
    "multi_agent_or_swarm_topology",
    "committee_or_judge_strategy",
    "research_strategy",
    "context_compression",
    "repair_strategy",
)


@dataclass(frozen=True, slots=True)
class PlannerResponsibilityContract:
    schema: str = PLANNER_RESPONSIBILITY_SCHEMA
    authority_owner: str = PLANNER_AUTHORITY_OWNER
    hard_obligations: tuple[str, ...] = HARD_OBLIGATIONS
    soft_strategies: tuple[str, ...] = SOFT_STRATEGIES
    soft_may_override_hard: bool = False
    selection_behavior_changed: bool = False

    def __post_init__(self) -> None:
        if self.schema != PLANNER_RESPONSIBILITY_SCHEMA:
            raise ValueError(f"invalid_planner_responsibility_schema:{self.schema}")
        if self.authority_owner != PLANNER_AUTHORITY_OWNER:
            raise ValueError("planner_authority_owner_mismatch")
        if not self.hard_obligations or not self.soft_strategies:
            raise ValueError("planner_responsibility_groups_required")
        if set(self.hard_obligations) & set(self.soft_strategies):
            raise ValueError("planner_responsibility_overlap")
        if self.soft_may_override_hard is not False:
            raise ValueError("soft_strategy_cannot_override_hard_obligation")
        if self.selection_behavior_changed is not False:
            raise ValueError("responsibility_contract_cannot_change_selection_behavior")

    def to_dict(self) -> dict[str, object]:
        return asdict(self) | {
            "hard_obligations": list(self.hard_obligations),
            "soft_strategies": list(self.soft_strategies),
        }


def planner_responsibility_contract() -> PlannerResponsibilityContract:
    """Return the frozen Wave-2 Planner responsibility boundary."""
    return PlannerResponsibilityContract()
