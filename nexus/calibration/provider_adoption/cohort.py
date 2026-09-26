"""G3 Frozen Evaluation Cohort module for Provider Adoption Experiments.

Schemas:
- nexus.provider_experiment.cohort.v1
- nexus.provider_experiment.evaluation_result.v1

False-Green Defense:
1. Invariant 6.5 (Cohort Provenance):
   - Cohort types are strictly distinguished: FIXTURE_COHORT, BENCHMARK_COHORT, PHYSICAL_HISTORICAL_COHORT.
   - Synthetic fixture strings must never claim to be verified historical receipts.
   - If ground truth is not ready: cohort evaluation is blocked with GROUND_TRUTH_NOT_READY.
2. Invariant 6.6 (Single Run Identity):
   - Every case result binds to a single stable run_id throughout the entire run.
   - Regenerating run_id inside case loops is strictly forbidden.
3. Leakage Defense:
   - Evaluates that candidate prompt does not leak the ground truth.
   - Ground truth and candidate execution are strictly segregated.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Sequence

from nexus.calibration.provider_adoption.canonical_json import canonical_json_hash
from nexus.calibration.provider_adoption.contracts import CohortType

COHORT_SCHEMA = "nexus.provider_experiment.cohort.v1"
EVALUATION_RESULT_SCHEMA = "nexus.provider_experiment.evaluation_result.v1"


class QualityVerdict(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    UNCERTAIN = "UNCERTAIN"


class EvidenceLevel(str, Enum):
    FIXTURE = "FIXTURE"
    SIMULATED = "SIMULATED"
    PHYSICAL = "PHYSICAL"


@dataclass(frozen=True)
class CohortCase:
    case_id: str
    task_class: str
    input_prompt: str
    ground_truth: str
    acceptable_variants: tuple[str, ...] = field(default_factory=tuple)
    forbidden_outputs: tuple[str, ...] = field(default_factory=tuple)
    difficulty: str = "medium"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "task_class": self.task_class,
            "input_prompt": self.input_prompt,
            "ground_truth": self.ground_truth,
            "acceptable_variants": list(self.acceptable_variants),
            "forbidden_outputs": list(self.forbidden_outputs),
            "difficulty": self.difficulty,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class FrozenCohort:
    schema: str
    cohort_id: str
    cohort_revision: int
    cohort_type: str
    cases: tuple[CohortCase, ...]
    cohort_sha256: str
    ground_truth_revision: int
    ground_truth_sha256: str
    ground_truth_ready: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "cohort_id": self.cohort_id,
            "cohort_revision": self.cohort_revision,
            "cohort_type": self.cohort_type,
            "cases": [c.to_dict() for c in self.cases],
            "cohort_sha256": self.cohort_sha256,
            "ground_truth_revision": self.ground_truth_revision,
            "ground_truth_sha256": self.ground_truth_sha256,
            "ground_truth_ready": self.ground_truth_ready,
        }


@dataclass(frozen=True)
class EvaluationResult:
    schema: str
    experiment_id: str
    run_id: str
    case_id: str
    candidate_identity_digest: str
    input_digest: str
    output_text: str
    output_digest: str
    schema_valid: bool
    quality_result: QualityVerdict
    failure_class: str | None
    latency_ms: int
    retry_count: int
    started_at: str
    completed_at: str
    evaluator_identity: str
    evidence_level: EvidenceLevel

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "experiment_id": self.experiment_id,
            "run_id": self.run_id,
            "case_id": self.case_id,
            "candidate_identity_digest": self.candidate_identity_digest,
            "input_digest": self.input_digest,
            "output_text": self.output_text,
            "output_digest": self.output_digest,
            "schema_valid": self.schema_valid,
            "quality_result": self.quality_result.value,
            "failure_class": self.failure_class,
            "latency_ms": self.latency_ms,
            "retry_count": self.retry_count,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "evaluator_identity": self.evaluator_identity,
            "evidence_level": self.evidence_level.value,
        }


def compute_cohort_hashes(cases: Sequence[CohortCase]) -> tuple[str, str]:
    """Compute separate cohort content hash and ground truth hash."""
    cohort_inputs = [
        {"case_id": c.case_id, "task_class": c.task_class, "input_prompt": c.input_prompt}
        for c in cases
    ]
    gt_inputs = [
        {
            "case_id": c.case_id,
            "ground_truth": c.ground_truth,
            "acceptable_variants": list(c.acceptable_variants),
            "forbidden_outputs": list(c.forbidden_outputs),
        }
        for c in cases
    ]
    return canonical_json_hash(cohort_inputs), canonical_json_hash(gt_inputs)


def audit_cohort_leakage(cohort: FrozenCohort) -> tuple[bool, list[str]]:
    """Audit cohort for prompt leakage and invalid ground truth segregation.

    Returns (is_clean, issues).
    """
    issues: list[str] = []
    for case in cohort.cases:
        gt_lower = case.ground_truth.strip().lower()
        if len(gt_lower) > 3 and gt_lower in case.input_prompt.lower():
            issues.append(
                f"Case {case.case_id} leaks ground truth '{case.ground_truth}' in input prompt."
            )
    return len(issues) == 0, issues


def create_frozen_cohort(
    *,
    cohort_id: str,
    cohort_revision: int,
    cohort_type: CohortType,
    cases: Sequence[CohortCase],
    ground_truth_revision: int = 1,
    ground_truth_ready: bool = True,
) -> FrozenCohort:
    cohort_sha256, gt_sha256 = compute_cohort_hashes(cases)
    return FrozenCohort(
        schema=COHORT_SCHEMA,
        cohort_id=cohort_id,
        cohort_revision=cohort_revision,
        cohort_type=cohort_type.value,
        cases=tuple(cases),
        cohort_sha256=cohort_sha256,
        ground_truth_revision=ground_truth_revision,
        ground_truth_sha256=gt_sha256,
        ground_truth_ready=ground_truth_ready,
    )
