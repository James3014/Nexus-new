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
