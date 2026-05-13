from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from nexus.contracts.s2t_policy import S2TCandidate


S2T_TRACE_SCHEMA_VERSION = "s2t.v1"
S2T_EPISODE_SCHEMA_VERSION = "s2t_episode.v1"

_ALLOWED_TRACE_FIELDS = {
    "schema_version",
    "task_id",
    "run_id",
    "model",
    "mode",
    "phase",
    "risk_tier",
    "route_decision_ref",
    "candidate_set_id",
    "candidates",
    "selected_candidate_id",
    "selection_reason_codes",
    "verifier_name",
    "verifier_result",
    "verifier_evidence_ref",
    "repair_attempted",
    "repair_candidate_id",
    "repair_result",
    "semantic_verified",
    "trust_mismatch",
    "delivery_gate",
    "secret_values",
    "private_paths",
}


@dataclass(frozen=True)
class S2TTraceEvent:
    task_id: str
    run_id: str
    model: str
    mode: str
    phase: str
    risk_tier: str
    candidate_set_id: str
    candidates: list[S2TCandidate]
    selected_candidate_id: str
    schema_version: str = S2T_TRACE_SCHEMA_VERSION
    route_decision_ref: str = ""
    selection_reason_codes: list[str] = field(default_factory=list)
    verifier_name: str = ""
    verifier_result: str = "not_run"
    verifier_evidence_ref: str = ""
    repair_attempted: bool = False
    repair_candidate_id: str = ""
    repair_result: str = "not_run"
    semantic_verified: bool = False
    trust_mismatch: bool = False
    delivery_gate: str = "not_run"
    secret_values: dict[str, str] = field(default_factory=dict)
    private_paths: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        for field_name in (
            "task_id",
            "run_id",
            "model",
            "mode",
            "phase",
            "risk_tier",
            "candidate_set_id",
        ):
            if not str(getattr(self, field_name)).strip():
                raise ValueError(f"{field_name} is required")
        if self.verifier_result not in {"pass", "fail", "not_run"}:
            raise ValueError("verifier_result must be pass, fail, or not_run")
        if self.semantic_verified and self.verifier_result != "pass":
            raise ValueError("semantic_verified requires verifier_result=pass")

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["candidates"] = [candidate.to_dict() for candidate in self.candidates]
        return payload

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "S2TTraceEvent":
        extra = set(payload) - _ALLOWED_TRACE_FIELDS
        if extra:
            raise ValueError(f"unknown S2TTraceEvent fields: {sorted(extra)}")
        normalized = dict(payload)
        normalized["candidates"] = [
            item if isinstance(item, S2TCandidate) else S2TCandidate.from_dict(item)
            for item in payload.get("candidates", [])
        ]
        return cls(**normalized)


@dataclass(frozen=True)
class S2TDecisionSpan:
    """One S2T decision node inside a runtime episode."""

    node: str
    phase: str
    candidate_set_id: str
    selected_candidate_id: str
    gate_passed: bool
    verifier_result: str = "not_run"
    reason_codes: list[str] = field(default_factory=list)
    reward: float = 0.0

    def __post_init__(self) -> None:
        for field_name in ("node", "phase", "candidate_set_id", "selected_candidate_id"):
            if not str(getattr(self, field_name)).strip():
                raise ValueError(f"{field_name} is required")
        if self.verifier_result not in {"pass", "fail", "not_run"}:
            raise ValueError("verifier_result must be pass, fail, or not_run")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class S2TEpisodeTrace:
    """Compact training-facing envelope for S2T runtime decisions."""

    episode_id: str
    task_id: str
    model: str
    mode: str
    spans: list[S2TDecisionSpan]
    schema_version: str = S2T_EPISODE_SCHEMA_VERSION
    benchmark_split: str = ""
    cost: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for field_name in ("episode_id", "task_id", "model", "mode"):
            if not str(getattr(self, field_name)).strip():
                raise ValueError(f"{field_name} is required")

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["spans"] = [span.to_dict() for span in self.spans]
        return payload


class S2TTraceWriter:
    """Append-only JSONL writer for S2T trace events."""

    def __init__(self, path: str | Path):
        self.path = Path(path)

    def append(self, event: S2TTraceEvent) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(event.to_dict(), ensure_ascii=False, sort_keys=True) + "\n")


def redact_s2t_event(event: S2TTraceEvent) -> dict[str, Any]:
    from nexus.contracts.s2t_export import redact_s2t_event as _redact_s2t_event

    return _redact_s2t_event(event)


def export_agent_lightning_preferences(events: list[S2TTraceEvent]) -> dict[str, Any]:
    from nexus.contracts.s2t_export import export_agent_lightning_preferences as _export_preferences

    return _export_preferences(events)


def export_model_training_v2(
    events: list[S2TTraceEvent],
    experiences: list[Any] | None = None,
    quality_rows: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    from nexus.contracts.s2t_export import export_model_training_v2 as _export_model_training_v2

    return _export_model_training_v2(events, experiences, quality_rows)


def export_model_training_v3(
    events: list[S2TTraceEvent],
    experiences: list[Any] | None = None,
    quality_rows: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    from nexus.contracts.s2t_export import export_model_training_v3 as _export_model_training_v3

    return _export_model_training_v3(events, experiences, quality_rows)
