from __future__ import annotations

from collections import Counter
from typing import Any, Iterable, Mapping

OBSERVATION_SCHEMA = "nexus.core_effectiveness.attempt_observation.v1"
REPORT_SCHEMA = "nexus.core_effectiveness.g0_coverage_report.v1"

ELIGIBLE = "ELIGIBLE_MUTATION_ATTEMPT"
IDENTITY_GAP = "ATTEMPT_IDENTITY_GAP"
NO_MUTATION = "NO_MUTATION_EFFECT"
RETROACTIVE = "RETROACTIVE_ONLY_NOT_PRIMARY"

PRIMARY_DISPOSITIONS = frozenset({ELIGIBLE, IDENTITY_GAP})

ENROLLMENT_FIELDS = (
    "repository",
    "work_item_id",
    "attempt_id",
    "attempt_index",
    "enrolled_at",
    "source_revision",
    "source_tree",
    "task_family",
    "risk_class",
    "execution_lane",
    "transport",
)

TERMINAL_FIELDS = (
    "target_revision",
    "target_tree",
    "core_invoked",
    "core_verdict",
    "core_reason",
    "receipt_hash",
    "baseline_result",
    "terminal_outcome",
    "t_core_detection",
    "t_baseline_detection",
    "t_terminal_result",
    "core_orchestration_runtime_ms",
    "verifier_runtime_ms",
    "duplicate_verifier_runtime_ms",
    "reviewer_calls",
    "manual_interventions",
    "attempts_to_green",
)


class ObservabilityContractError(ValueError):
    """Raised when a G0 observation would make the denominator ambiguous."""


def _present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    return True


def _missing_fields(row: Mapping[str, Any], fields: Iterable[str]) -> list[str]:
    explicit = row.get("missingness")
    explicit_missing = set(explicit) if isinstance(explicit, Mapping) else set()
    return sorted(
        field for field in fields if not _present(row.get(field)) or field in explicit_missing
    )


def normalize_observation(raw: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize one research-only attempt observation without inventing evidence."""

    if raw.get("schema") != OBSERVATION_SCHEMA:
        raise ObservabilityContractError("observation_schema_mismatch")

    disposition = str(raw.get("eligibility_disposition") or "")
    if disposition not in {ELIGIBLE, IDENTITY_GAP, NO_MUTATION, RETROACTIVE}:
        raise ObservabilityContractError("invalid_eligibility_disposition")

    missingness = raw.get("missingness", {})
    if not isinstance(missingness, Mapping):
        raise ObservabilityContractError("missingness_must_be_mapping")

    row = dict(raw)
    row["missingness"] = {str(key): str(value) for key, value in missingness.items()}
    row["eligible"] = disposition in PRIMARY_DISPOSITIONS
    row["prospective"] = bool(raw.get("prospective", False))
    row["terminal"] = bool(raw.get("terminal", False))

    attempt_index = raw.get("attempt_index")
    if attempt_index is not None and (
        isinstance(attempt_index, bool) or not isinstance(attempt_index, int) or attempt_index < 1
    ):
        raise ObservabilityContractError("attempt_index_must_be_positive_integer")

    for counter_field in (
        "reviewer_calls",
        "manual_interventions",
        "attempts_to_green",
        "core_orchestration_runtime_ms",
        "verifier_runtime_ms",
        "duplicate_verifier_runtime_ms",
    ):
        value = raw.get(counter_field)
        if value is not None and (
            isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0
        ):
            raise ObservabilityContractError(f"{counter_field}_must_be_non_negative")

    if disposition == IDENTITY_GAP:
        required_gap_reasons = {"attempt_id", "enrolled_at"}
        if not required_gap_reasons.issubset(row["missingness"]):
            raise ObservabilityContractError(
                "identity_gap_requires_attempt_id_and_enrolled_at_missingness"
            )

    if disposition == RETROACTIVE and row["prospective"]:
        raise ObservabilityContractError("retroactive_observation_cannot_be_prospective")

    return row


def from_devspace_core_session(
    *,
    repository: str,
    work_item_id: str,
    attempt_index: int,
    task_family: str,
    risk_class: str,
    execution_lane: str,
    session: Mapping[str, Any],
    transport: str = "DEVSPACE",
) -> dict[str, Any]:
    """Project an already-authoritative pre-effect Core session into the study schema."""

    return normalize_observation({
        "schema": OBSERVATION_SCHEMA,
        "repository": repository,
        "work_item_id": work_item_id,
        "attempt_id": session.get("attemptId"),
        "attempt_index": attempt_index,
        "enrolled_at": session.get("createdAt"),
        "source_revision": session.get("sourceHead"),
        "source_tree": session.get("sourceTree"),
        "task_family": task_family,
        "risk_class": risk_class,
        "execution_lane": execution_lane,
        "transport": transport,
        "eligibility_disposition": ELIGIBLE,
        "prospective": not bool(session.get("firstEffectAt")),
        "terminal": False,
        "operation_id": session.get("operationId"),
        "workspace_session_id": session.get("workspaceSessionId"),
        "binding_id": session.get("bindingId"),
        "binding_hash": session.get("bindingHash"),
        "missingness": {},
    })


def identity_gap(
    *,
    repository: str,
    work_item_id: str,
    reason: str,
    task_family: str = "UNKNOWN",
    risk_class: str = "UNKNOWN",
    execution_lane: str = "UNKNOWN",
    transport: str = "UNKNOWN",
) -> dict[str, Any]:
    """Keep a mutation-bearing work item in the denominator when pre-effect identity is lost."""

    reason = str(reason).strip()
    if not reason:
        raise ObservabilityContractError("identity_gap_reason_required")
    return normalize_observation({
        "schema": OBSERVATION_SCHEMA,
        "repository": repository,
        "work_item_id": work_item_id,
        "attempt_id": None,
        "attempt_index": None,
        "enrolled_at": None,
        "source_revision": None,
        "source_tree": None,
        "task_family": task_family,
        "risk_class": risk_class,
        "execution_lane": execution_lane,
        "transport": transport,
        "eligibility_disposition": IDENTITY_GAP,
        "prospective": False,
        "terminal": False,
        "missingness": {
            "attempt_id": reason,
            "attempt_index": reason,
            "enrolled_at": reason,
            "source_revision": reason,
            "source_tree": reason,
        },
    })


def build_g0_coverage_report(
    observations: Iterable[Mapping[str, Any]],
    *,
    target: float = 0.95,
) -> dict[str, Any]:
    """Measure prospective enrollment and terminal adjudication completeness.

    This projection is observational only. It never changes eligibility, repairs
    missing evidence, or upgrades authority.
    """

    if not (0.0 < target <= 1.0):
        raise ObservabilityContractError("coverage_target_out_of_range")

    rows = [normalize_observation(row) for row in observations]

    identities: set[tuple[str, str, str]] = set()
    for row in rows:
        attempt_id = row.get("attempt_id")
        if not _present(attempt_id):
            continue
        identity = (
            str(row.get("repository") or ""),
            str(row.get("work_item_id") or ""),
            str(attempt_id),
        )
        if identity in identities:
            raise ObservabilityContractError("duplicate_attempt_identity")
        identities.add(identity)

    primary = [row for row in rows if row["eligibility_disposition"] in PRIMARY_DISPOSITIONS]
    complete_enrollment: list[dict[str, Any]] = []
    enrollment_missing = Counter()
    for row in primary:
        missing = _missing_fields(row, ENROLLMENT_FIELDS)
        for field in missing:
            enrollment_missing[field] += 1
        if row["eligibility_disposition"] == ELIGIBLE and row["prospective"] and not missing:
            complete_enrollment.append(row)

    denominator = len(primary)
    enrollment_coverage = len(complete_enrollment) / denominator if denominator else None

    terminal = [row for row in primary if row["terminal"]]
    complete_terminal: list[dict[str, Any]] = []
    terminal_missing = Counter()
    for row in terminal:
        missing = _missing_fields(row, ENROLLMENT_FIELDS + TERMINAL_FIELDS)
        for field in missing:
            terminal_missing[field] += 1
        if row["eligibility_disposition"] == ELIGIBLE and row["prospective"] and not missing:
            complete_terminal.append(row)

    terminal_coverage = len(complete_terminal) / len(terminal) if terminal else None

    gap_counts = Counter(row["eligibility_disposition"] for row in rows)
    if denominator == 0:
        gate = "NO_ELIGIBLE_ATTEMPTS_OBSERVED"
    elif enrollment_coverage is not None and enrollment_coverage >= target:
        gate = "G0_COVERAGE_TARGET_MET"
    else:
        gate = "G0_COVERAGE_INSUFFICIENT"

    return {
        "schema": REPORT_SCHEMA,
        "authority": "RESEARCH_OBSERVATION_ONLY",
        "claim_ceiling": "G0_OBSERVABILITY_ONLY_NO_UTILITY_CLAIM",
        "coverage_target": target,
        "row_count": len(rows),
        "eligible_denominator": denominator,
        "complete_prospective_enrollment_count": len(complete_enrollment),
        "prospective_enrollment_coverage": enrollment_coverage,
        "terminal_eligible_count": len(terminal),
        "adjudication_complete_count": len(complete_terminal),
        "adjudication_completeness": terminal_coverage,
        "dispositions": dict(sorted(gap_counts.items())),
        "enrollment_missing_by_field": dict(sorted(enrollment_missing.items())),
        "terminal_missing_by_field": dict(sorted(terminal_missing.items())),
        "gate": gate,
        "small_n_zero_error_is_not_fleet_proof": True,
        "retroactive_primary_enrollment_allowed": False,
    }
