"""Thin transport-neutral continuity evaluation over existing direct-operation journals.

This module consumes durable operation facts. It does not persist a second store and
does not own routing, retry authority, completion truth, Candidate acceptance, merge,
release, deployment, or production activation.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from nexus.services.direct_operation_journal import (
    ACTIVE_STATES,
    TERMINAL_STATES,
    DirectOperationJournal,
)

OPERATION_CONTINUITY_SCHEMA = "nexus.operation_continuity.v1"
OPERATION_CONTINUITY_CLAIM_CEILING = (
    "NEXUS_TRANSPORT_NEUTRAL_OPERATION_CONTINUITY_SOURCE_VERIFIED"
)

DISPOSITION_CONTINUE = "CONTINUE"
DISPOSITION_RECONCILE = "RECONCILE"
DISPOSITION_STOP = "STOP"
DISPOSITION_BLOCKED = "BLOCKED"

_RECONCILE_RESULTS = frozenset({
    "OUTCOME_UNKNOWN",
    "ACTIVE_STALE_HEARTBEAT",
    "PROVIDER_PROCESS_STILL_RUNNING",
    "RECONCILE_REQUIRED",
})


@dataclass(frozen=True)
class ContinuityExpectation:
    """Controller-owned identity/evidence expectations for one logical operation."""

    operation_id: str
    attempt_id: str
    repository: str | None = None
    expected_base_head: str | None = None
    predecessor_operation_id: str | None = None
    predecessor_attempt_id: str | None = None
    transition_role: str | None = None
    continuation_role: str | None = None
    handoff_hash: str | None = None
    first_pass_receipt_linkage: str | None = None
    required_evidence_refs: tuple[str, ...] = ()
    expected_paths: tuple[str, ...] = ()


@dataclass(frozen=True)
class ContinuityDecision:
    """Read-only continuity classification; never a retry or completion grant."""

    schema: str
    claim_ceiling: str
    operation_id: str
    attempt_id: str
    disposition: str
    terminal: bool
    retry_permitted: bool
    reason: str
    details: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "claim_ceiling": self.claim_ceiling,
            "operation_id": self.operation_id,
            "attempt_id": self.attempt_id,
            "disposition": self.disposition,
            "terminal": self.terminal,
            "retry_permitted": self.retry_permitted,
            "reason": self.reason,
            "details": dict(self.details),
        }


def _decision(
    expectation: ContinuityExpectation,
    *,
    disposition: str,
    terminal: bool,
    reason: str,
    details: Mapping[str, Any] | None = None,
) -> ContinuityDecision:
    return ContinuityDecision(
        schema=OPERATION_CONTINUITY_SCHEMA,
        claim_ceiling=OPERATION_CONTINUITY_CLAIM_CEILING,
        operation_id=expectation.operation_id,
        attempt_id=expectation.attempt_id,
        disposition=disposition,
        terminal=terminal,
        retry_permitted=False,
        reason=reason,
        details=details or {},
    )


def _repo_matches(expected: str, observed: str) -> bool:
    left = str(expected or "").strip().rstrip("/")
    right = str(observed or "").strip().rstrip("/")
    if not left or not right:
        return False
    if left == right:
        return True
    left_path = Path(left).expanduser()
    right_path = Path(right).expanduser()
    if not left_path.is_absolute() or not right_path.is_absolute():
        return False
    try:
        return os.path.samefile(left_path, right_path)
    except OSError:
        return left_path.resolve() == right_path.resolve()


def _valid_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(ch in "0123456789abcdef" for ch in value)
    )


def _path_allowed(path: str, allowed: tuple[str, ...]) -> bool:
    if not allowed:
        return True
    candidate = Path(path)
    if candidate.is_absolute() or ".." in candidate.parts:
        return False
    candidate_text = candidate.as_posix().rstrip("/")
    for raw in allowed:
        scope = Path(raw)
        if scope.is_absolute() or ".." in scope.parts:
            continue
        scope_text = scope.as_posix().rstrip("/")
        if candidate_text == scope_text or candidate_text.startswith(scope_text + "/"):
            return True
    return False


def _transport_evidence(record: Mapping[str, Any]) -> dict[str, Any]:
    """Project observational transport facts without using them as ownership."""
    return {
        "host_id": record.get("host_id"),
        "provider": record.get("provider"),
        "model": record.get("model"),
        "observed_provider": record.get("observed_provider"),
        "observed_model": record.get("observed_model"),
        "provider_session_id": record.get("provider_session_id"),
        "account_alias_hash": record.get("account_alias_hash"),
    }


def evaluate_operation_continuity(
    expectation: ContinuityExpectation,
    record: Mapping[str, Any],
) -> ContinuityDecision:
    """Evaluate continuity from one durable operation record.

    The evaluator is intentionally conservative: it never grants retry permission.
    A future controller may create a new attempt only after its own authoritative
    reconciliation and authorization gates.
    """

    if record.get("operation_id") != expectation.operation_id:
        return _decision(
            expectation,
            disposition=DISPOSITION_BLOCKED,
            terminal=False,
            reason="OPERATION_ID_MISMATCH",
        )
    if record.get("attempt_id") != expectation.attempt_id:
        return _decision(
            expectation,
            disposition=DISPOSITION_BLOCKED,
            terminal=False,
            reason="ATTEMPT_ID_MISMATCH",
        )

    observed_repository = str(record.get("repo_root") or record.get("repository") or "")
    if expectation.repository and not _repo_matches(expectation.repository, observed_repository):
        return _decision(
            expectation,
            disposition=DISPOSITION_BLOCKED,
            terminal=False,
            reason="REPOSITORY_MISMATCH",
        )

    if expectation.expected_base_head and record.get("base_head") != expectation.expected_base_head:
        return _decision(
            expectation,
            disposition=DISPOSITION_BLOCKED,
            terminal=False,
            reason="BASE_HEAD_MISMATCH",
        )

    predecessor_operation_id = record.get("predecessor_operation_id")
    predecessor_attempt_id = record.get("predecessor_attempt_id")
    if bool(predecessor_operation_id) != bool(predecessor_attempt_id):
        return _decision(
            expectation,
            disposition=DISPOSITION_BLOCKED,
            terminal=False,
            reason="PREDECESSOR_IDENTITY_INCOMPLETE",
        )
    if predecessor_operation_id:
        if record.get("transition_role") in (None, "") or record.get("continuation_role") in (
            None,
            "",
        ):
            return _decision(
                expectation,
                disposition=DISPOSITION_BLOCKED,
                terminal=False,
                reason="PREDECESSOR_PROVENANCE_INCOMPLETE",
            )

    expected_pairs = (
        ("predecessor_operation_id", expectation.predecessor_operation_id),
        ("predecessor_attempt_id", expectation.predecessor_attempt_id),
        ("transition_role", expectation.transition_role),
        ("continuation_role", expectation.continuation_role),
        ("handoff_hash", expectation.handoff_hash),
        ("first_pass_receipt_linkage", expectation.first_pass_receipt_linkage),
    )
    for field_name, expected in expected_pairs:
        if expected is not None and record.get(field_name) != expected:
            return _decision(
                expectation,
                disposition=DISPOSITION_BLOCKED,
                terminal=False,
                reason=f"{field_name.upper()}_MISMATCH",
            )

    for field_name in ("handoff_hash", "first_pass_receipt_linkage"):
        value = record.get(field_name)
        if value is not None and not _valid_sha256(value):
            return _decision(
                expectation,
                disposition=DISPOSITION_BLOCKED,
                terminal=False,
                reason=f"{field_name.upper()}_INVALID",
            )

    evidence_refs = record.get("evidence_refs", [])
    if not isinstance(evidence_refs, list) or any(
        not isinstance(ref, str) or not ref.strip() for ref in evidence_refs
    ):
        return _decision(
            expectation,
            disposition=DISPOSITION_BLOCKED,
            terminal=False,
            reason="EVIDENCE_REFS_INVALID",
        )
    missing_refs = sorted(set(expectation.required_evidence_refs) - set(evidence_refs))
    if missing_refs:
        return _decision(
            expectation,
            disposition=DISPOSITION_BLOCKED,
            terminal=False,
            reason="REQUIRED_EVIDENCE_MISSING",
            details={"missing_evidence_refs": missing_refs},
        )

    scope_violations = record.get("scope_violations") or []
    if record.get("scope_validation_state") == "VIOLATION_OUT_OF_SCOPE" or scope_violations:
        return _decision(
            expectation,
            disposition=DISPOSITION_BLOCKED,
            terminal=False,
            reason="MUTATION_OUTSIDE_ALLOWED_PATHS",
            details={"scope_violations": list(scope_violations)},
        )
    observed_paths = record.get("observed_changed_paths") or []
    if not isinstance(observed_paths, list) or any(not isinstance(path, str) for path in observed_paths):
        return _decision(
            expectation,
            disposition=DISPOSITION_BLOCKED,
            terminal=False,
            reason="OBSERVED_PATHS_INVALID",
        )
    unexpected_paths = [
        path for path in observed_paths if not _path_allowed(path, expectation.expected_paths)
    ]
    if expectation.expected_paths and unexpected_paths:
        return _decision(
            expectation,
            disposition=DISPOSITION_BLOCKED,
            terminal=False,
            reason="MUTATION_OUTSIDE_EXPECTED_PATHS",
            details={"unexpected_paths": unexpected_paths},
        )

    status = str(record.get("status") or "")
    phase = str(record.get("phase") or "")
    reconciliation = record.get("reconciliation")
    reconciliation_result = (
        reconciliation.get("result") if isinstance(reconciliation, Mapping) else None
    )
    details = {
        "transport_evidence": _transport_evidence(record),
        "continuity": {
            "predecessor_operation_id": predecessor_operation_id,
            "predecessor_attempt_id": predecessor_attempt_id,
            "transition_role": record.get("transition_role"),
            "continuation_role": record.get("continuation_role"),
            "evidence_refs": list(evidence_refs),
            "handoff_hash": record.get("handoff_hash"),
            "first_pass_receipt_linkage": record.get("first_pass_receipt_linkage"),
        },
    }

    if bool(record.get("has_unresolved_external_effect")):
        return _decision(
            expectation,
            disposition=DISPOSITION_RECONCILE,
            terminal=False,
            reason="UNRESOLVED_EXTERNAL_EFFECT_REQUIRES_RECONCILIATION",
            details=details,
        )
    if (
        status == "OUTCOME_UNKNOWN"
        or phase == "RECONCILE_REQUIRED"
        or reconciliation_result in _RECONCILE_RESULTS
    ):
        return _decision(
            expectation,
            disposition=DISPOSITION_RECONCILE,
            terminal=False,
            reason="EFFECT_REQUIRES_RECONCILIATION",
            details=details,
        )
    if status == "COMPLETED":
        return _decision(
            expectation,
            disposition=DISPOSITION_STOP,
            terminal=True,
            reason="TERMINAL_PHYSICAL_EFFECT_COMPLETED",
            details=details,
        )
    if status in TERMINAL_STATES:
        return _decision(
            expectation,
            disposition=DISPOSITION_STOP,
            terminal=True,
            reason="TERMINAL_PHYSICAL_EFFECT_FAILED_OR_CANCELLED",
            details=details,
        )
    if status in ACTIVE_STATES:
        return _decision(
            expectation,
            disposition=DISPOSITION_CONTINUE,
            terminal=False,
            reason="PHYSICAL_EFFECT_ACTIVE",
            details=details,
        )
    return _decision(
        expectation,
        disposition=DISPOSITION_BLOCKED,
        terminal=False,
        reason="OPERATION_STATUS_UNKNOWN",
        details=details,
    )


def evaluate_journal_operation(
    journal: DirectOperationJournal,
    expectation: ContinuityExpectation,
) -> ContinuityDecision:
    """Read the existing durable journal and evaluate without creating new state."""
    return evaluate_operation_continuity(expectation, journal.read(expectation.operation_id))
