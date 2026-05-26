from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True)
class AuditOutcome:
    """Structured audit result consumed by belief gates."""

    task_id: str
    assumption: str
    passed: bool
    evidence_id: str
    confidence: float | None = None
    reason: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


class BeliefGate(Protocol):
    """Minimal interface Orchestrator needs from belief governance."""

    def process_audit_outcome(self, outcome: AuditOutcome) -> dict[str, Any]:
        ...


@dataclass(frozen=True)
class HealingArtifact:
    """Portable self-healing recommendation contract for swarm transport."""

    task_id: str
    artifact_id: str
    artifact_type: str
    created_at: str
    evidence_id: str
    summary: str
    metadata: dict[str, Any] = field(default_factory=dict)
    signature: str = ""
    signature_key_id: str = ""


@dataclass(frozen=True)
class SkillReceipt:
    """Portable receipt confirming the actual injection, usage and outcome of a specific Skill."""

    skill_id: str
    selected: bool
    used: bool
    evidence_id: str
    outcome: dict[str, Any] = field(default_factory=dict)
    timestamp: str = ""


@dataclass(frozen=True)
class CapabilityReceipt:
    """Rigorous artifact confirming that a capability was active, backed by concrete evidence & gates."""

    capability_name: str
    selected: bool
    invoked: bool
    evidence_id: str
    gate_passed: bool
    outcome: dict[str, Any] = field(default_factory=dict)
    skill_receipts: list[SkillReceipt] = field(default_factory=list)
    timestamp: str = ""


@dataclass(frozen=True)
class SkillSlot:
    """Rigorous HEEP/EMAS Role slot indicating how a skill is deployed within a capability."""

    role: str  # 'SCOUT', 'LOGIC', 'AUDIT'
    skill_id: str
    injected: bool = False
    used: bool = False


@dataclass(frozen=True)
class CapabilityExecutionPlan:
    """A serialized DAG of capability phases to be executed with fallback & replan logic."""

    plan_id: str
    task_id: str
    phases: list[str] = field(default_factory=list)  # Ordered sublist of S,P,X,D,R,A,C
    required_capabilities: list[str] = field(default_factory=list)
    skill_slots: dict[str, list[SkillSlot]] = field(default_factory=dict)  # cap_name -> list[SkillSlot]
    constraints: dict[str, Any] = field(default_factory=dict)
    timestamp: str = ""


