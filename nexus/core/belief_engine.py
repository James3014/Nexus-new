import json
from pathlib import Path
from typing import Dict, Any

from nexus.core.belief_contracts import AuditOutcome
from nexus.telemetry.tracer import NexusTracer

class BeliefEngine:
    """維護當前的邏輯假設與信心度 (Subjective Trust)。"""
    def __init__(self, state_file: Path = Path(".nexus/belief_state.json")):
        self.state_file = state_file
        self.beliefs = {}
        self._load()

    def _load(self):
        if self.state_file.exists():
            with open(self.state_file, "r") as f:
                self.beliefs = json.load(f)

    def assess_confidence(self, task_id: str, assumption: str = "") -> float:
        """根據歷史證據評估信心。"""
        # 簡單模型：若有歷史相同假設則提高，否則基準為 0.7
        key = assumption or task_id
        return self.beliefs.get(key, {}).get("confidence", 0.7)

    def get_confidence(self, task_id: str, assumption: str = "") -> float:
        return self.assess_confidence(task_id, assumption)

    def update_belief(self, task_id: str, assumption: str, confidence: float, evidence_id: str):
        self.beliefs[assumption] = {
            "confidence": confidence,
            "evidence": evidence_id,
            "task_id": task_id
        }
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.state_file, "w") as f:
            json.dump(self.beliefs, f, indent=2)

    def process_audit_outcome(self, outcome: AuditOutcome) -> dict[str, Any]:
        """Process a structured audit outcome without leaking confidence policy."""
        old_confidence = self.assess_confidence(outcome.task_id, outcome.assumption)
        confidence = outcome.confidence
        if confidence is None:
            confidence = 0.9 if outcome.passed else 0.1
        confidence = max(0.0, min(1.0, float(confidence)))
        self.update_belief(
            task_id=outcome.task_id,
            assumption=outcome.assumption,
            confidence=confidence,
            evidence_id=outcome.evidence_id,
        )
        self.beliefs[outcome.assumption]["last_audit_passed"] = bool(outcome.passed)
        self.beliefs[outcome.assumption]["reason"] = outcome.reason
        self.beliefs[outcome.assumption]["metadata"] = dict(outcome.metadata)
        with open(self.state_file, "w") as f:
            json.dump(self.beliefs, f, indent=2)
        NexusTracer.record_belief_shift(outcome.task_id, old_confidence, confidence)
        return {
            "task_id": outcome.task_id,
            "assumption": outcome.assumption,
            "confidence": confidence,
            "evidence_id": outcome.evidence_id,
            "accepted": bool(outcome.passed),
        }
