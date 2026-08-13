"""Deterministic, privacy-safe task continuity projection.

This module is deliberately a projection over the existing task/attempt event
seam.  It carries summaries and evidence references only; it is not a task
state machine, router, verifier, or lifecycle authority.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from typing import Any, Iterable

SCHEMA = "nexus.task_continuity.v1"
EVENT_TYPES = frozenset({
    "PLAN_FORMED",
    "OBSERVATION_RECORDED",
    "HYPOTHESIS_REVISED",
    "STRATEGY_CHANGED",
    "VERIFICATION_RESULT",
    "ATTEMPT_REJECTED",
    "ESCALATED",
    "COMPLETED",
})
PROTECTED = (
    "task_id",
    "attempt_id",
    "rejected_strategies",
    "evidence_refs",
    "unresolved_risks",
    "next_action",
    "claim_ceiling",
)


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _clean_text(value: Any, name: str, *, required: bool = False) -> str:
    if not isinstance(value, str) or (required and not value.strip()):
        raise ValueError(
            f"{name} must be a non-empty string" if required else f"{name} must be a string"
        )
    return value.strip()


@dataclass(frozen=True)
class ContinuityEvent:
    task_id: str
    attempt_id: str
    sequence: int
    event_type: str
    summary: str
    action: str = ""
    observation: str = ""
    rationale: str = ""
    failure_reason: str = ""
    strategy_delta: str = ""
    do_not_repeat: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = ()
    unresolved_risks: tuple[str, ...] = ()
    unknowns: tuple[str, ...] = ()
    next_action: str = ""
    claim_ceiling: str = ""
    source_revision: str = ""
    contract_revision: str = ""
    previous_hash: str = ""
    event_hash: str = field(init=False)
    schema: str = SCHEMA

    def __post_init__(self) -> None:
        if self.schema != SCHEMA:
            raise ValueError("unsupported continuity schema")
        _clean_text(self.task_id, "task_id", required=True)
        _clean_text(self.attempt_id, "attempt_id", required=True)
        if (
            isinstance(self.sequence, bool)
            or not isinstance(self.sequence, int)
            or self.sequence < 1
        ):
            raise ValueError("sequence must be a positive integer")
        if self.event_type not in EVENT_TYPES:
            raise ValueError("unsupported continuity event type")
        for name in (
            "summary",
            "action",
            "observation",
            "rationale",
            "failure_reason",
            "strategy_delta",
            "next_action",
            "claim_ceiling",
            "source_revision",
            "contract_revision",
            "previous_hash",
        ):
            _clean_text(
                getattr(self, name), name, required=name in {"source_revision", "contract_revision"}
            )
        for name in ("do_not_repeat", "evidence_refs", "unresolved_risks", "unknowns"):
            values = getattr(self, name)
            if not isinstance(values, tuple) or any(
                not isinstance(v, str) or not v.strip() for v in values
            ):
                raise ValueError(f"{name} must contain non-empty strings")
        payload = {
            name: getattr(self, name) for name in self.__dataclass_fields__ if name != "event_hash"
        }
        object.__setattr__(self, "event_hash", _digest(payload))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self) | {
            "do_not_repeat": list(self.do_not_repeat),
            "evidence_refs": list(self.evidence_refs),
            "unresolved_risks": list(self.unresolved_risks),
            "unknowns": list(self.unknowns),
        }


@dataclass(frozen=True)
class ContinuitySnapshot:
    schema: str
    task_id: str
    attempt_id: str
    first_sequence: int
    last_sequence: int
    event_root: str
    source_revision: str
    contract_revision: str
    verified_facts: tuple[str, ...]
    active_hypotheses: tuple[str, ...]
    rejected_hypotheses: tuple[str, ...]
    strategy_changes: tuple[str, ...]
    applied_changes: tuple[str, ...]
    failed_attempts: tuple[str, ...]
    rejected_strategies: tuple[str, ...]
    unresolved_risks: tuple[str, ...]
    unknowns: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    next_action: str
    claim_ceiling: str
    _snapshot_digest: str = field(init=False, repr=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "_snapshot_digest", _digest(self._content_dict()))

    def _content_dict(self) -> dict[str, Any]:
        return {
            name: getattr(self, name)
            for name in self.__dataclass_fields__
            if name != "_snapshot_digest"
        }

    def to_dict(self) -> dict[str, Any]:
        return self._content_dict()

    @property
    def snapshot_hash(self) -> str:
        return self._snapshot_digest

    def validate_integrity(self) -> None:
        if self._snapshot_digest != _digest(self._content_dict()):
            raise ValueError("snapshot tampered")


@dataclass(frozen=True)
class ResumeContext:
    snapshot: ContinuitySnapshot
    next_action: str
    claim_ceiling: str
    do_not_repeat: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    unresolved_risks: tuple[str, ...]
    source_revision: str
    contract_revision: str


def _validate_chain(
    events: list[ContinuityEvent],
    task_id: str,
    attempt_id: str,
    *,
    start: int = 1,
    previous_hash: str = "",
) -> None:
    if not events:
        raise ValueError("continuity event stream is empty")
    previous = previous_hash
    expected = start
    for event in events:
        if event.task_id != task_id or event.attempt_id != attempt_id:
            raise ValueError("foreign task or attempt event")
        if event.sequence != expected:
            raise ValueError("continuity sequence gap")
        if event.previous_hash != previous:
            raise ValueError("continuity hash-chain mismatch")
        if event.event_hash != _digest({
            k: v for k, v in event.to_dict().items() if k != "event_hash"
        }):
            raise ValueError("continuity event tampered")
        previous, expected = event.event_hash, expected + 1


def project(events: Iterable[ContinuityEvent]) -> ContinuitySnapshot:
    ordered = list(events)
    first = ordered[0]
    _validate_chain(ordered, first.task_id, first.attempt_id)
    facts: list[str] = []
    active: list[str] = []
    rejected_hypotheses: list[str] = []
    strategy_changes: list[str] = []
    applied: list[str] = []
    failed: list[str] = []
    rejected: list[str] = []
    risks: list[str] = []
    unknowns: list[str] = []
    evidence: list[str] = []
    next_action = ""
    claim = ""
    source = first.source_revision
    contract = first.contract_revision
    for event in ordered:
        if event.source_revision != source or event.contract_revision != contract:
            raise ValueError("source or contract revision drift")
        if event.observation:
            facts.append(event.observation)
        if event.event_type in {"PLAN_FORMED", "HYPOTHESIS_REVISED"} and event.summary:
            active.append(event.summary)
        if event.event_type == "ATTEMPT_REJECTED":
            failed.append(event.summary)
            rejected.extend(event.do_not_repeat)
            rejected_hypotheses.append(event.summary)
        if event.strategy_delta:
            strategy_changes.append(event.strategy_delta)
        if event.action and event.event_type == "COMPLETED":
            applied.append(event.action)
        evidence.extend(event.evidence_refs)
        risks.extend(event.unresolved_risks)
        unknowns.extend(event.unknowns)
        next_action = event.next_action or next_action
        claim = event.claim_ceiling or claim
    return ContinuitySnapshot(
        schema=SCHEMA,
        task_id=first.task_id,
        attempt_id=first.attempt_id,
        first_sequence=first.sequence,
        last_sequence=ordered[-1].sequence,
        event_root=ordered[-1].event_hash,
        source_revision=source,
        contract_revision=contract,
        verified_facts=tuple(dict.fromkeys(facts)),
        active_hypotheses=tuple(dict.fromkeys(active)),
        rejected_hypotheses=tuple(dict.fromkeys(rejected_hypotheses)),
        strategy_changes=tuple(dict.fromkeys(strategy_changes)),
        applied_changes=tuple(dict.fromkeys(applied)),
        failed_attempts=tuple(dict.fromkeys(failed)),
        rejected_strategies=tuple(dict.fromkeys(rejected)),
        unresolved_risks=tuple(dict.fromkeys(risks)),
        unknowns=tuple(dict.fromkeys(unknowns)),
        evidence_refs=tuple(dict.fromkeys(evidence)),
        next_action=next_action,
        claim_ceiling=claim,
    )


def resume(
    snapshot: ContinuitySnapshot,
    tail: Iterable[ContinuityEvent],
    *,
    task_id: str,
    attempt_id: str,
    source_revision: str,
    contract_revision: str,
    snapshot_hash: str | None = None,
) -> ResumeContext:
    snapshot.validate_integrity()
    if (
        snapshot.schema != SCHEMA
        or snapshot.task_id != task_id
        or snapshot.attempt_id != attempt_id
    ):
        raise ValueError("snapshot identity mismatch")
    if snapshot_hash is not None and snapshot_hash != snapshot.snapshot_hash:
        raise ValueError("snapshot hash mismatch")
    if (
        snapshot.source_revision != source_revision
        or snapshot.contract_revision != contract_revision
    ):
        raise ValueError("snapshot source or contract is stale")
    tail_events = list(tail)
    if tail_events:
        if (
            tail_events[0].sequence != snapshot.last_sequence + 1
            or tail_events[0].previous_hash != snapshot.event_root
        ):
            raise ValueError("tail does not extend snapshot")
        _validate_chain(
            tail_events,
            task_id,
            attempt_id,
            start=snapshot.last_sequence + 1,
            previous_hash=snapshot.event_root,
        )
        merged = _project_tail(snapshot, tail_events)
    else:
        merged = snapshot
    return ResumeContext(
        merged,
        merged.next_action,
        merged.claim_ceiling,
        merged.rejected_strategies,
        merged.evidence_refs,
        merged.unresolved_risks,
        merged.source_revision,
        merged.contract_revision,
    )


def _project_tail(snapshot: ContinuitySnapshot, tail: list[ContinuityEvent]) -> ContinuitySnapshot:
    facts, active = list(snapshot.verified_facts), list(snapshot.active_hypotheses)
    rejected_hypotheses, strategy_changes = (
        list(snapshot.rejected_hypotheses),
        list(snapshot.strategy_changes),
    )
    applied, failed = list(snapshot.applied_changes), list(snapshot.failed_attempts)
    rejected, evidence = list(snapshot.rejected_strategies), list(snapshot.evidence_refs)
    risks, unknowns = list(snapshot.unresolved_risks), list(snapshot.unknowns)
    next_action, claim = snapshot.next_action, snapshot.claim_ceiling
    for event in tail:
        if event.observation:
            facts.append(event.observation)
        if event.event_type in {"PLAN_FORMED", "HYPOTHESIS_REVISED"} and event.summary:
            active.append(event.summary)
        if event.event_type == "ATTEMPT_REJECTED":
            failed.append(event.summary)
            rejected.extend(event.do_not_repeat)
            rejected_hypotheses.append(event.summary)
        if event.strategy_delta:
            strategy_changes.append(event.strategy_delta)
        if event.action and event.event_type == "COMPLETED":
            applied.append(event.action)
        evidence.extend(event.evidence_refs)
        next_action = event.next_action or next_action
        claim = event.claim_ceiling or claim
        risks.extend(event.unresolved_risks)
        unknowns.extend(event.unknowns)

    def unique(values: list[str]) -> tuple[str, ...]:
        return tuple(dict.fromkeys(values))

    return ContinuitySnapshot(
        schema=SCHEMA,
        task_id=snapshot.task_id,
        attempt_id=snapshot.attempt_id,
        first_sequence=snapshot.first_sequence,
        last_sequence=tail[-1].sequence,
        event_root=tail[-1].event_hash,
        source_revision=snapshot.source_revision,
        contract_revision=snapshot.contract_revision,
        verified_facts=unique(facts),
        active_hypotheses=unique(active),
        rejected_hypotheses=unique(rejected_hypotheses),
        strategy_changes=unique(strategy_changes),
        applied_changes=unique(applied),
        failed_attempts=unique(failed),
        rejected_strategies=unique(rejected),
        unresolved_risks=snapshot.unresolved_risks,
        unknowns=tuple(dict.fromkeys(unknowns)),
        evidence_refs=unique(evidence),
        next_action=next_action,
        claim_ceiling=claim,
    )
