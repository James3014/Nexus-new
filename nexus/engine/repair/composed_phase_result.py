from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ComposedRepairResult:
    """Normalized output from a composed R phase."""

    status: str
    result_object: dict
    mutations: dict
    current_decision_id: str
    current_skill_id: str


@dataclass
class ComposedAuditResult:
    """Normalized output from a composed A phase."""

    status: str
    mutations: dict
    current_decision_id: str
    current_skill_id: str
    rejection_reason: str
