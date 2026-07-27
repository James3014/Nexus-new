"""Deterministic Cheap -> Strong worker escalation policy."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from nexus.executors.worker_contract import WorkerExecutionReceipt, WorkerOutcome


@dataclass(frozen=True)
class EscalationDecision:
    action: str
    next_provider: str | None
    reason: str


@dataclass(frozen=True)
class WorkerEscalationPolicy:
    cheap_provider: str
    strong_provider: str

    def decide(self, attempts: Sequence[WorkerExecutionReceipt]) -> EscalationDecision:
        if not attempts:
            return EscalationDecision("RUN_CHEAP", self.cheap_provider, "no worker attempt exists")
        latest = attempts[-1]
        if latest.commit_created or latest.merge_performed or latest.push_performed:
            return EscalationDecision(
                "BLOCK",
                None,
                "worker attempted a forbidden repository mutation",
            )
        if latest.outcome == WorkerOutcome.PROVEN.value and latest.evidence_complete:
            return EscalationDecision("ACCEPT", None, "worker produced complete proof")
        if len(attempts) == 1 and latest.provider == self.cheap_provider:
            return EscalationDecision(
                "ESCALATE",
                self.strong_provider,
                f"cheap worker did not prove success: {latest.outcome}",
            )
        return EscalationDecision(
            "BLOCK",
            None,
            "strong worker did not produce complete proof",
        )
