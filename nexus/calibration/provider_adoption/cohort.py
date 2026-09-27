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

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Sequence

from nexus.calibration.provider_adoption.canonical_json import canonical_json_hash
from nexus.calibration.provider_adoption.contracts import CohortType, ExperimentContract

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
        {
            "case_id": c.case_id,
            "task_class": c.task_class,
            "input_prompt": c.input_prompt,
            "difficulty": c.difficulty,
            "metadata": dict(c.metadata),
        }
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


_CLASSIFICATION_TASK_CLASSES: frozenset[str] = frozenset(
    {
        "classification",
        "multiple_choice",
        "multiple-choice",
        "categorization",
        "single_choice",
        "single-choice",
        "choice",
    }
)

_EXTRACTION_TASK_CLASSES: frozenset[str] = frozenset(
    {
        "extraction",
        "simple_extraction",
        "simple-extraction",
        "extract",
    }
)

SUPPORTED_LEAKAGE_POLICY_REVISIONS: tuple[int, ...] = (1,)

_OPTIONS_HEADER_RE = re.compile(
    r"(?i)\b(?:options|option|choices|choice|candidate labels|candidate classes|"
    r"candidate categories|allowed labels|allowed classes|categories|category|"
    r"classes|class|labels|label)\s*(?::|are:|\s+are:?|\s+include:?)\s*",
)

_BULLET_LINE_RE = re.compile(
    r"^\s*(?:[-*•]|\(?\d+[.)\]]|\(?[a-zA-Z][.)\]])\s+(.+)$",
)


def _clean_option_token(token: str) -> str:
    """Clean an option token by stripping bullets, delimiters, quotes, and punctuation."""
    t = token.strip()
    t = re.sub(r"^[-*•]\s*", "", t)
    t = re.sub(r"^(?:or|and|nor)\s+", "", t, flags=re.IGNORECASE)
    t = t.strip("\"'`()[]{}")
    t = t.rstrip(".,;:")
    return t.strip()


def _text_contains_token(text: str, token: str) -> bool:
    """Check if token appears in text as a distinct word/token."""
    token_lower = token.lower()
    text_lower = text.lower()
    if token_lower not in text_lower:
        return False
    pattern = r"(?<![a-zA-Z0-9_])" + re.escape(token_lower) + r"(?![a-zA-Z0-9_])"
    return bool(re.search(pattern, text_lower))


def _extract_options_from_prompt(prompt: str) -> list[tuple[list[str], int, int]]:
    """Extract candidate option lists and their character spans from a prompt.

    Returns a list of tuples: (options, start_char_index, end_char_index).
    """
    found: list[tuple[list[str], int, int]] = []
    for match in _OPTIONS_HEADER_RE.finditer(prompt):
        header_start = match.start()
        header_end = match.end()
        rest = prompt[header_end:]
        if not rest.strip():
            continue

        lines_with_breaks = rest.splitlines(keepends=True)
        bullet_options: list[str] = []
        multiline_offset = 0
        has_bullets = False

        for line in lines_with_breaks:
            stripped = line.strip()
            if not stripped:
                multiline_offset += len(line)
                continue
            b_match = _BULLET_LINE_RE.match(stripped)
            if b_match:
                has_bullets = True
                opt = _clean_option_token(b_match.group(1))
                if opt:
                    bullet_options.append(opt)
                multiline_offset += len(line)
            else:
                break

        if has_bullets and len(bullet_options) >= 2:
            span_end = header_end + multiline_offset
            found.append((bullet_options, header_start, span_end))
            continue

        first_line = lines_with_breaks[0] if lines_with_breaks else rest
        first_line_clean = first_line.rstrip("\r\n")

        bracket_match = re.match(r"^\s*(\[|\()([^\]\)]+)(\]|\))", first_line_clean)
        if bracket_match:
            inner = bracket_match.group(2)
            raw_tokens = re.split(r"[,;|/]", inner)
            cleaned = [_clean_option_token(t) for t in raw_tokens if _clean_option_token(t)]
            if len(cleaned) >= 2:
                span_end = header_end + bracket_match.end()
                found.append((cleaned, header_start, span_end))
                continue

        inline_text = first_line_clean
        if "," in inline_text:
            delims = ","
        elif ";" in inline_text:
            delims = ";"
        elif "|" in inline_text:
            delims = "|"
        elif "/" in inline_text:
            delims = "/"
        elif re.search(r"\s+or\s+", inline_text, re.IGNORECASE):
            delims = r"\s+or\s+"
        else:
            delims = None

        if delims:
            if delims == r"\s+or\s+":
                raw_parts = re.split(delims, inline_text, flags=re.IGNORECASE)
            else:
                raw_parts = inline_text.split(delims)

            if len(raw_parts) >= 2:
                last_part = raw_parts[-1]
                trailing_idx = -1
                sent_match = re.search(r"\.\s+[A-Z]", last_part)
                if sent_match:
                    raw_parts[-1] = last_part[: sent_match.start()]
                    trailing_idx = sent_match.start()

                cleaned_parts = [
                    _clean_option_token(p) for p in raw_parts if _clean_option_token(p)
                ]
                if len(cleaned_parts) >= 2:
                    if sent_match and trailing_idx >= 0:
                        char_len = len(inline_text) - (len(last_part) - trailing_idx)
                        span_end = header_end + char_len
                    else:
                        span_end = header_end + len(first_line_clean)
                    found.append((cleaned_parts, header_start, span_end))

    return found


def audit_cohort_leakage(
    cohort: FrozenCohort,
    policy_revision: int = 1,
) -> tuple[bool, list[str]]:
    """Audit cohort for prompt leakage and invalid ground truth segregation.

    Returns (is_clean, issues).

    Principles (Policy Revision 1):
    1. Fail-closed on unsupported policy revision.
    2. Extraction tasks: mere ground-truth presence in the source/input is EXPECTED
       and must not be called leakage by substring alone.
    3. Classification / multiple-choice tasks: ground truth may appear inside a
       recognized explicit option list (>=2 options), but appearance outside that
       option list is leakage.
    4. Other task classes: exact ground-truth token occurrence remains a conservative
       leakage signal.
    5. Options exemptions are strictly prompt-structural and task_class-governed
       (no metadata-based exemptions).
    """
    if policy_revision not in SUPPORTED_LEAKAGE_POLICY_REVISIONS:
        return False, [
            f"UNSUPPORTED_LEAKAGE_POLICY_REVISION: Revision {policy_revision} is not supported "
            f"(supported revisions: {list(SUPPORTED_LEAKAGE_POLICY_REVISIONS)})."
        ]

    issues: list[str] = []
    for case in cohort.cases:
        task_class_norm = case.task_class.strip().lower().replace("-", "_")

        # Extraction tasks: presence in source/input is expected, not leakage
        if task_class_norm in _EXTRACTION_TASK_CLASSES:
            continue

        gt_lower = case.ground_truth.strip().lower()
        if len(gt_lower) <= 3:
            continue

        if not _text_contains_token(case.input_prompt, gt_lower):
            continue

        is_classification = task_class_norm in _CLASSIFICATION_TASK_CLASSES
        is_legitimate_option = False

        if is_classification:
            extracted_blocks = _extract_options_from_prompt(case.input_prompt)
            for options, start_idx, end_idx in extracted_blocks:
                unique_opts = {o.lower() for o in options}
                if len(unique_opts) >= 2 and gt_lower in unique_opts:
                    prompt_outside = (
                        case.input_prompt[:start_idx] + " " + case.input_prompt[end_idx:]
                    )
                    if not _text_contains_token(prompt_outside, gt_lower):
                        is_legitimate_option = True
                        break

        if not is_legitimate_option:
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


def validate_contract_cohort_binding(
    contract: ExperimentContract,
    cohort: FrozenCohort,
) -> None:
    """Validate cross-binding between ExperimentContract.dataset and the supplied FrozenCohort.

    Enforces that contract.dataset and the supplied cohort strictly match:
    - cohort_id
    - cohort_revision
    - cohort_sha256
    - ground_truth_revision
    - ground_truth_sha256
    - cohort_type
    - ground_truth_ready consistency
    - cryptographic case hash integrity

    Fails closed with exact ValueError on any mismatch and prevents candidate inference.
    """
    ds = contract.dataset
    if ds.cohort_id != cohort.cohort_id:
        raise ValueError(
            f"DATASET_COHORT_MISMATCH: Contract cohort_id '{ds.cohort_id}' does not match cohort '{cohort.cohort_id}'."
        )
    if ds.cohort_revision != cohort.cohort_revision:
        raise ValueError(
            f"DATASET_COHORT_MISMATCH: Contract cohort_revision {ds.cohort_revision} does not match cohort {cohort.cohort_revision}."
        )
    if ds.cohort_sha256 != cohort.cohort_sha256:
        raise ValueError(
            f"DATASET_COHORT_MISMATCH: Contract cohort_sha256 '{ds.cohort_sha256}' does not match cohort '{cohort.cohort_sha256}'."
        )
    if ds.ground_truth_revision != cohort.ground_truth_revision:
        raise ValueError(
            f"DATASET_COHORT_MISMATCH: Contract ground_truth_revision {ds.ground_truth_revision} does not match cohort {cohort.ground_truth_revision}."
        )
    if ds.ground_truth_sha256 != cohort.ground_truth_sha256:
        raise ValueError(
            f"DATASET_COHORT_MISMATCH: Contract ground_truth_sha256 '{ds.ground_truth_sha256}' does not match cohort '{cohort.ground_truth_sha256}'."
        )
    if ds.cohort_type != cohort.cohort_type:
        raise ValueError(
            f"DATASET_COHORT_MISMATCH: Contract cohort_type '{ds.cohort_type}' does not match cohort '{cohort.cohort_type}'."
        )
    if ds.ground_truth_ready != cohort.ground_truth_ready:
        raise ValueError(
            f"DATASET_COHORT_MISMATCH: Contract ground_truth_ready ({ds.ground_truth_ready}) does not match cohort ({cohort.ground_truth_ready})."
        )
    computed_cohort_sha, computed_gt_sha = compute_cohort_hashes(cohort.cases)
    if cohort.cohort_sha256 != computed_cohort_sha:
        raise ValueError(
            f"DATASET_COHORT_MISMATCH: Cohort declared cohort_sha256 '{cohort.cohort_sha256}' does not match computed '{computed_cohort_sha}'."
        )
    if cohort.ground_truth_sha256 != computed_gt_sha:
        raise ValueError(
            f"DATASET_COHORT_MISMATCH: Cohort declared ground_truth_sha256 '{cohort.ground_truth_sha256}' does not match computed '{computed_gt_sha}'."
        )
