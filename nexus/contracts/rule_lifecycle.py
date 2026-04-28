from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum


class RuleLifecycleState(str, Enum):
    ACTIVE = "active"
    LIGHT = "light"
    DEPRECATED = "deprecated"
    REMOVED_CANDIDATE = "removed_candidate"


@dataclass(frozen=True)
class RuleLifecycleEvidence:
    """Evidence used to decide whether a Nexus rule still earns its cost."""

    rule_id: str
    current_state: RuleLifecycleState = RuleLifecycleState.ACTIVE
    sample_size: int = 0
    verified_lift_pp: float = 0.0
    trust_mismatch_delta_pp: float = 0.0
    cost_delta_pct: float = 0.0
    rationale: str = ""

    def __post_init__(self) -> None:
        if not self.rule_id.strip():
            raise ValueError("rule_id is required")
        if self.sample_size < 0:
            raise ValueError("sample_size must be >= 0")

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["current_state"] = self.current_state.value
        return payload


def recommend_rule_state(
    evidence: RuleLifecycleEvidence,
    *,
    min_sample_size: int = 3,
    meaningful_lift_pp: float = 5.0,
    neutral_lift_pp: float = 1.0,
) -> RuleLifecycleState:
    """Return a conservative lifecycle recommendation from benchmark evidence."""

    if evidence.sample_size < min_sample_size:
        return RuleLifecycleState.ACTIVE
    if evidence.trust_mismatch_delta_pp > 0:
        return RuleLifecycleState.ACTIVE
    if evidence.verified_lift_pp >= meaningful_lift_pp:
        return RuleLifecycleState.ACTIVE
    if evidence.verified_lift_pp > neutral_lift_pp:
        return RuleLifecycleState.LIGHT
    if evidence.verified_lift_pp >= -neutral_lift_pp and evidence.cost_delta_pct > 0:
        return RuleLifecycleState.REMOVED_CANDIDATE
    if evidence.verified_lift_pp < -neutral_lift_pp:
        return RuleLifecycleState.DEPRECATED
    return RuleLifecycleState.LIGHT
