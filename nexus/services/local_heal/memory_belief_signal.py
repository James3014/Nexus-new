from __future__ import annotations

from dataclasses import dataclass


@dataclass
class MemoryBeliefSignal:
    """Read-only memory confidence signal for BeliefEngine consumption."""
    memory_confidence_signal: float
    source: str
    used_for_selection: bool = False  # always False in read-only mode
    used_for_public_claim: bool = False  # always False


def compute_memory_belief_signal(
    *,
    copyability_score: float,
    decision_eligibility: str,
    decision_allowed: bool,
) -> MemoryBeliefSignal:
    """Compute memory confidence signal for BeliefEngine consumption.

    Read-only mode: does NOT change P5 selected_index or solved_by_committee.
    """
    # Normalize confidence signal
    if decision_allowed and decision_eligibility == "decision_eligible":
        confidence = copyability_score
    elif decision_eligibility == "audit_only":
        confidence = copyability_score * 0.5
    else:
        confidence = 0.0

    return MemoryBeliefSignal(
        memory_confidence_signal=confidence,
        source="shadow_memory_ranking",
        used_for_selection=False,  # read-only mode
        used_for_public_claim=False,  # always False
    )
