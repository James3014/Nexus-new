"""Automatic main-drift completion loop caller for GitHub PR merge orchestration.

Composes existing pure reducer/preparer primitives, Gate A integration contracts,
and durable standing-grant authorization to automatically absorb safe main drift
and drive merge completion across monotonic integration generations (I1 -> I2 -> I3).
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Literal, Mapping, Protocol, Sequence

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictStr,
    field_validator,
    model_validator,
)

from nexus.contracts.github_orchestration import (
    CandidateBlobEquivalence,
    CheckResult,
    GitHubOrchestrationEvidence,
    IntegrationBinding,
    MainMovementEvidence,
    MergeIntent,
    ReviewResult,
    canonical_hash,
    compute_candidate_equivalence_proof_hash,
)
from nexus.orchestrator.autonomy_policy import (
    StandingGrantOutcome,
    StandingGrantRequest,
)
from nexus.orchestrator.github_orchestration import (
    requalify_main_movement,
    resolve_durable_merge_authorization,
)

MAX_INTEGRATION_GENERATIONS: int = 3
MAX_COMPLETION_ELAPSED_SECONDS: float = 2700.0

_GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_RECEIPT_HASH_RE = re.compile(r"^[0-9a-f]{64}$")


def _git_sha(value: str, name: str) -> str:
    if not isinstance(value, str) or not _GIT_SHA_RE.fullmatch(value):
        raise ValueError(f"{name}_invalid_git_sha: {value!r}")
    return value


def _receipt_hash(value: str, name: str) -> str:
    if not isinstance(value, str) or not _RECEIPT_HASH_RE.fullmatch(value):
        raise ValueError(f"{name}_invalid_receipt_hash: {value!r}")
    return value


class _FrozenModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", populate_by_name=True)


class CompletionLoopOutcome(str, Enum):
    COMPLETED = "COMPLETED"
    BLOCKED = "BLOCKED"
    DEFERRED_CONCURRENCY = "DEFERRED_CONCURRENCY"


class CasMergeStatus(str, Enum):
    SUCCESS = "SUCCESS"
    BASE_MOVED = "BASE_MOVED"
    HEAD_MISMATCH = "HEAD_MISMATCH"
    AMBIGUOUS_ACK = "AMBIGUOUS_ACK"
    CONFLICT = "CONFLICT"
    REJECTED = "REJECTED"


class DimensionRevalidationReceipt(_FrozenModel):
    schema: Literal["nexus.dimension_revalidation_receipt.v1"] = (
        "nexus.dimension_revalidation_receipt.v1"
    )
    dimension: StrictStr
    generation: int
    old_main_sha: StrictStr
    new_main_sha: StrictStr
    source_candidate_commit_sha: StrictStr
    source_candidate_tree_sha: StrictStr
    passed: StrictBool
    requires_fresh_candidate_acceptance: StrictBool = False
    details: Mapping[str, Any] = Field(default_factory=dict)
    receipt_hash: StrictStr

    @field_validator(
        "old_main_sha",
        "new_main_sha",
        "source_candidate_commit_sha",
        "source_candidate_tree_sha",
    )
    @classmethod
    def validate_git_hashes(cls, value: str, info) -> str:
        return _git_sha(value, info.field_name)

    @field_validator("receipt_hash")
    @classmethod
    def validate_receipt_hash_field(cls, value: str, info) -> str:
        return _receipt_hash(value, info.field_name)

    @model_validator(mode="after")
    def validate_receipt_hash(self) -> "DimensionRevalidationReceipt":
        payload = self.model_dump(mode="json", exclude={"receipt_hash"})
        expected = canonical_hash(payload)
        if self.receipt_hash != expected:
            raise ValueError(f"RECEIPT_HASH_MISMATCH: expected {expected}, got {self.receipt_hash}")
        return self


def make_dimension_revalidation_receipt(
    *,
    dimension: str,
    generation: int,
    old_main_sha: str,
    new_main_sha: str,
    source_candidate_commit_sha: str,
    source_candidate_tree_sha: str,
    passed: bool,
    requires_fresh_candidate_acceptance: bool = False,
    details: Mapping[str, Any] | None = None,
) -> DimensionRevalidationReceipt:
    """Construct a cryptographically bound DimensionRevalidationReceipt."""
    data = {
        "schema": "nexus.dimension_revalidation_receipt.v1",
        "dimension": dimension,
        "generation": generation,
        "old_main_sha": old_main_sha,
        "new_main_sha": new_main_sha,
        "source_candidate_commit_sha": source_candidate_commit_sha,
        "source_candidate_tree_sha": source_candidate_tree_sha,
        "passed": passed,
        "requires_fresh_candidate_acceptance": requires_fresh_candidate_acceptance,
        "details": dict(details or {}),
    }
    h = canonical_hash(data)
    return DimensionRevalidationReceipt(**data, receipt_hash=h)


class IntegrationMaterializationResult(_FrozenModel):
    schema: Literal["nexus.integration_materialization_result.v1"] = (
        "nexus.integration_materialization_result.v1"
    )
    success: StrictBool
    integration_head_sha: StrictStr | None = None
    integration_tree_sha: StrictStr | None = None
    conflict: StrictBool = False
    error: StrictStr | None = None

    @field_validator("integration_head_sha", "integration_tree_sha")
    @classmethod
    def validate_opt_git_hashes(cls, value: str | None, info) -> str | None:
        if value is not None:
            return _git_sha(value, info.field_name)
        return None


@dataclass(frozen=True)
class CasMergeResult:
    status: CasMergeStatus
    merged_sha: str | None = None
    reason: str | None = None


class PostMergeReconciliationResult(_FrozenModel):
    schema: Literal["nexus.post_merge_reconciliation_result.v1"] = (
        "nexus.post_merge_reconciliation_result.v1"
    )
    observed_main_commit_sha: StrictStr
    observed_main_tree_sha: StrictStr
    observed_parent_shas: tuple[StrictStr, ...]
    details: Mapping[str, Any] = Field(default_factory=dict)

    @field_validator("observed_main_commit_sha", "observed_main_tree_sha")
    @classmethod
    def validate_git_hashes(cls, value: str, info) -> str:
        return _git_sha(value, info.field_name)

    @field_validator("observed_parent_shas")
    @classmethod
    def validate_parents(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        for p in value:
            _git_sha(p, "observed_parent_sha")
        return value


@dataclass(frozen=True)
class CompletionLoopResult:
    outcome: CompletionLoopOutcome
    reason: str
    generation: int
    integration_head_sha: str | None = None
    merged_commit_sha: str | None = None
    evidence: GitHubOrchestrationEvidence | None = None
    intent: MergeIntent | None = None
    details: dict[str, Any] = field(default_factory=dict)


class GitHubCompletionPort(Protocol):
    def read_main_state(self) -> tuple[str, str]:
        """Return (main_head_sha, main_tree_sha)."""
        ...

    def get_tree_sha(self, commit_sha: str) -> str:
        """Return the git tree SHA for a given commit SHA."""
        ...

    def read_pr_head_sha(self) -> str:
        """Return current PR head SHA on remote."""
        ...

    def read_blob_sha(self, commit_or_tree_sha: str, path: str) -> str:
        """Return the physical git blob SHA for a given commit/tree and path."""
        ...

    def get_changed_main_paths(self, old_main_sha: str, new_main_sha: str) -> tuple[str, ...]:
        """Return paths changed on main between old_main_sha and new_main_sha."""
        ...

    def revalidate_affected_dimension(
        self,
        dimension: str,
        *,
        evidence: GitHubOrchestrationEvidence,
        movement: MainMovementEvidence,
        generation: int,
    ) -> DimensionRevalidationReceipt:
        """Execute revalidation hook for an affected dimension and return typed receipt."""
        ...

    def materialize_integration_head(
        self,
        *,
        base_sha: str,
        base_tree_sha: str,
        expected_pr_head_sha: str,
        candidate_tree_sha: str,
        generation: int,
    ) -> IntegrationMaterializationResult:
        """Materialize integration head combining PR branch state with current main."""
        ...

    def read_required_checks(
        self,
        *,
        head_sha: str,
        generation: int,
        timeout_seconds: float | None = None,
    ) -> Sequence[CheckResult]:
        """Wait/read required checks for exact head_sha and generation."""
        ...

    def read_reviews(self) -> Sequence[ReviewResult]:
        """Read current PR reviews."""
        ...

    def is_platform_approval_required(
        self,
        *,
        repository: str,
        pull_request_number: int,
    ) -> bool:
        """Observe whether platform approval is currently required for this repository/PR."""
        ...

    def cas_merge(
        self,
        *,
        repository: str,
        pull_request_number: int,
        expected_base_sha: str,
        expected_head_sha: str,
    ) -> CasMergeResult:
        """Execute one CAS merge operation bound to exact expected base and head."""
        ...

    def reconcile_post_merge(
        self,
        *,
        repository: str,
        pull_request_number: int,
        expected_base_sha: str,
        expected_head_sha: str,
    ) -> PostMergeReconciliationResult:
        """Confirm merged head/tree/lineage on main after merge or upon ambiguous ACK."""
        ...


def _validate_reconciliation_facts(
    recon: Any,
    *,
    expected_base_sha: str,
    expected_head_sha: str,
    expected_integration_tree_sha: str,
    cas_merged_sha: str | None = None,
) -> tuple[bool, str | None]:
    """Validate physical facts in PostMergeReconciliationResult."""
    if not isinstance(recon, PostMergeReconciliationResult):
        return False, "RECONCILIATION_RESULT_NOT_TYPED"

    # Check observed main commit SHA matches cas_merged_sha if provided
    if cas_merged_sha and recon.observed_main_commit_sha != cas_merged_sha:
        return (
            False,
            f"RECONCILIATION_MERGED_SHA_MISMATCH: expected {cas_merged_sha}, found {recon.observed_main_commit_sha}",
        )

    # Check observed main tree SHA strictly equals expected integration tree SHA
    if recon.observed_main_tree_sha != expected_integration_tree_sha:
        return (
            False,
            f"RECONCILIATION_TREE_SHA_MISMATCH: expected {expected_integration_tree_sha}, found {recon.observed_main_tree_sha}",
        )

    # Check parent lineage: both expected base and expected head must be in observed parents
    if expected_base_sha not in recon.observed_parent_shas:
        return (
            False,
            f"RECONCILIATION_MISSING_BASE_PARENT: {expected_base_sha} not in {recon.observed_parent_shas}",
        )
    if expected_head_sha not in recon.observed_parent_shas:
        return (
            False,
            f"RECONCILIATION_MISSING_INTEGRATION_PARENT: {expected_head_sha} not in {recon.observed_parent_shas}",
        )

    return True, None


def run_github_completion_loop(
    *,
    initial_evidence: GitHubOrchestrationEvidence,
    request: StandingGrantRequest | Mapping[str, Any],
    port: GitHubCompletionPort,
    max_generations: int = 3,
    max_elapsed_seconds: float = 2700.0,
    git_root: Path | None = None,
    now_provider: Callable[[], datetime] | None = None,
    monotonic_clock: Callable[[], float] | None = None,
) -> CompletionLoopResult:
    """Execute the bounded GitHub PR drift-completion loop.

    Absorbs ordinary safe main drift automatically up to max_generations (default 3)
    while failing closed on conflict, foreign push, check failure, authority drift,
    unknown impact, or standing grant mismatch.
    """
    # Enforce strict hard maxima on retry / time budgets before any port calls
    if not (1 <= max_generations <= MAX_INTEGRATION_GENERATIONS):
        return CompletionLoopResult(
            outcome=CompletionLoopOutcome.BLOCKED,
            reason=f"INVALID_GENERATION_BUDGET:{max_generations}",
            generation=0,
        )

    if not (0 < max_elapsed_seconds <= MAX_COMPLETION_ELAPSED_SECONDS):
        return CompletionLoopResult(
            outcome=CompletionLoopOutcome.BLOCKED,
            reason=f"INVALID_TIME_BUDGET:{max_elapsed_seconds}",
            generation=0,
        )

    now_fn = now_provider or (lambda: datetime.now(timezone.utc))
    clock_fn = monotonic_clock or time.monotonic

    start_monotonic = clock_fn()
    source_candidate = initial_evidence.candidate
    source_candidate_commit_sha = source_candidate.candidate_commit_sha
    source_candidate_tree_sha = source_candidate.candidate_tree_sha
    source_candidate_diff_hash = initial_evidence.diff_hash
    candidate_changed_paths = tuple(initial_evidence.changed_paths)

    if initial_evidence.repository != "James3014/Nexus-new":
        return CompletionLoopResult(
            outcome=CompletionLoopOutcome.BLOCKED,
            reason="REPOSITORY_IDENTITY_INVALID",
            generation=0,
        )

    current_evidence = initial_evidence
    current_generation = (
        initial_evidence.integration.generation if initial_evidence.integration else 0
    )
    last_produced_head_sha = initial_evidence.head_sha

    while True:
        # Check elapsed time budget
        if clock_fn() - start_monotonic > max_elapsed_seconds:
            return CompletionLoopResult(
                outcome=CompletionLoopOutcome.DEFERRED_CONCURRENCY,
                reason="TIME_BUDGET_EXHAUSTED",
                generation=current_generation,
                integration_head_sha=last_produced_head_sha,
                evidence=current_evidence,
            )

        # Check PR head on remote to detect foreign push / competing controller
        remote_pr_head = port.read_pr_head_sha()
        if remote_pr_head != last_produced_head_sha:
            return CompletionLoopResult(
                outcome=CompletionLoopOutcome.BLOCKED,
                reason=f"FOREIGN_PR_HEAD_MUTATION: expected {last_produced_head_sha}, found {remote_pr_head}",
                generation=current_generation,
                integration_head_sha=last_produced_head_sha,
                evidence=current_evidence,
            )

        # Read current main state
        current_main_sha, current_main_tree_sha = port.read_main_state()

        # Check if main moved
        if current_main_sha != current_evidence.base_sha:
            # Main has moved! Check generation budget
            if current_generation >= max_generations:
                return CompletionLoopResult(
                    outcome=CompletionLoopOutcome.DEFERRED_CONCURRENCY,
                    reason="GENERATION_BUDGET_EXHAUSTED",
                    generation=current_generation,
                    integration_head_sha=last_produced_head_sha,
                    evidence=current_evidence,
                )

            next_generation = current_generation + 1

            # Get changed paths on main
            changed_main_paths = port.get_changed_main_paths(
                current_evidence.base_sha, current_main_sha
            )
            if not changed_main_paths:
                return CompletionLoopResult(
                    outcome=CompletionLoopOutcome.BLOCKED,
                    reason="MAIN_MOVEMENT_PATHS_MISSING",
                    generation=current_generation,
                    evidence=current_evidence,
                )

            # Build candidate baseline evidence for requalification
            cand_base_dict = current_evidence.model_dump(mode="json")
            cand_base_dict["base_sha"] = current_evidence.base_sha
            cand_base_dict["current_main_sha"] = current_evidence.base_sha
            cand_base_dict["head_sha"] = source_candidate_commit_sha
            cand_base_dict["tree_sha"] = source_candidate_tree_sha
            cand_base_dict["integration"] = None
            cand_base_dict["required_checks"] = [
                {**c, "head_sha": source_candidate_commit_sha, "generation": None}
                for c in cand_base_dict.get("required_checks", [])
            ]
            cand_base_dict["checks_hash"] = canonical_hash({
                "checks": cand_base_dict["required_checks"]
            })
            try:
                base_cand_evidence = GitHubOrchestrationEvidence.model_validate(cand_base_dict)
            except Exception as exc:
                return CompletionLoopResult(
                    outcome=CompletionLoopOutcome.BLOCKED,
                    reason=f"BASELINE_CANDIDATE_EVIDENCE_INVALID:{exc}",
                    generation=current_generation,
                )

            old_tree_sha = port.get_tree_sha(current_evidence.base_sha)
            new_tree_sha = port.get_tree_sha(current_main_sha)

            try:
                movement = MainMovementEvidence(
                    old_main_sha=current_evidence.base_sha,
                    old_main_tree_sha=old_tree_sha,
                    new_main_sha=current_main_sha,
                    new_main_tree_sha=new_tree_sha,
                    candidate_head_sha=source_candidate_commit_sha,
                    candidate_tree_sha=source_candidate_tree_sha,
                    candidate_diff_hash=source_candidate_diff_hash,
                    candidate_changed_paths=candidate_changed_paths,
                    changed_main_paths=changed_main_paths,
                    prior_impact_hash=current_evidence.impact_hash,
                    prior_verifier_hash=current_evidence.verifier_hash,
                )
            except Exception as exc:
                return CompletionLoopResult(
                    outcome=CompletionLoopOutcome.BLOCKED,
                    reason=f"MAIN_MOVEMENT_EVIDENCE_INVALID:{exc}",
                    generation=current_generation,
                )

            # Call existing requalify_main_movement
            requalification = requalify_main_movement(base_cand_evidence, movement, root=git_root)

            if requalification.blocked:
                blocked_reasons = [
                    d.reasons for d in requalification.dimensions if d.action != "REUSE_UNAFFECTED"
                ]
                return CompletionLoopResult(
                    outcome=CompletionLoopOutcome.BLOCKED,
                    reason=f"REQUALIFICATION_BLOCKED:{blocked_reasons}",
                    generation=current_generation,
                    evidence=current_evidence,
                )

            if any(d.action == "IMPACT_UNKNOWN" for d in requalification.dimensions):
                return CompletionLoopResult(
                    outcome=CompletionLoopOutcome.BLOCKED,
                    reason="REQUALIFICATION_IMPACT_UNKNOWN",
                    generation=current_generation,
                    evidence=current_evidence,
                )

            # Execute affected dimensions through port revalidation hook
            revalidation_receipts: list[DimensionRevalidationReceipt] = []
            for dim in requalification.dimensions:
                if dim.action == "RECHECK_AFFECTED":
                    receipt = port.revalidate_affected_dimension(
                        dim.dimension,
                        evidence=current_evidence,
                        movement=movement,
                        generation=next_generation,
                    )
                    if not isinstance(receipt, DimensionRevalidationReceipt):
                        return CompletionLoopResult(
                            outcome=CompletionLoopOutcome.BLOCKED,
                            reason=f"INVALID_REVALIDATION_RECEIPT:{dim.dimension}",
                            generation=current_generation,
                            evidence=current_evidence,
                        )
                    if (
                        receipt.dimension != dim.dimension
                        or receipt.generation != next_generation
                        or receipt.old_main_sha != current_evidence.base_sha
                        or receipt.new_main_sha != current_main_sha
                        or receipt.source_candidate_commit_sha != source_candidate_commit_sha
                        or receipt.source_candidate_tree_sha != source_candidate_tree_sha
                    ):
                        return CompletionLoopResult(
                            outcome=CompletionLoopOutcome.BLOCKED,
                            reason=f"REVALIDATION_RECEIPT_CONTEXT_MISMATCH:{dim.dimension}",
                            generation=current_generation,
                            evidence=current_evidence,
                        )
                    if receipt.requires_fresh_candidate_acceptance:
                        return CompletionLoopResult(
                            outcome=CompletionLoopOutcome.BLOCKED,
                            reason=f"FRESH_CANDIDATE_ACCEPTANCE_REQUIRED:{dim.dimension}",
                            generation=current_generation,
                            evidence=current_evidence,
                        )
                    if not receipt.passed:
                        return CompletionLoopResult(
                            outcome=CompletionLoopOutcome.BLOCKED,
                            reason=f"DIMENSION_REVALIDATION_FAILED:{dim.dimension}",
                            generation=current_generation,
                            evidence=current_evidence,
                        )
                    revalidation_receipts.append(receipt)

            # Materialize integration head from CURRENT PR HEAD and current main
            mat_result = port.materialize_integration_head(
                base_sha=current_main_sha,
                base_tree_sha=new_tree_sha,
                expected_pr_head_sha=last_produced_head_sha,
                candidate_tree_sha=source_candidate_tree_sha,
                generation=next_generation,
            )

            if (
                not isinstance(mat_result, IntegrationMaterializationResult)
                or mat_result.conflict
                or not mat_result.success
                or not mat_result.integration_head_sha
                or not mat_result.integration_tree_sha
            ):
                err_detail = (
                    mat_result.error
                    if isinstance(mat_result, IntegrationMaterializationResult) and mat_result.error
                    else (
                        "conflict"
                        if isinstance(mat_result, IntegrationMaterializationResult)
                        and mat_result.conflict
                        else "unknown"
                    )
                )
                return CompletionLoopResult(
                    outcome=CompletionLoopOutcome.BLOCKED,
                    reason=f"INTEGRATION_MATERIALIZATION_FAILED:{err_detail}",
                    generation=current_generation,
                    evidence=current_evidence,
                )

            # Caller independently reads and verifies the actual physical git tree SHA of integration_head_sha
            try:
                observed_int_tree = port.get_tree_sha(mat_result.integration_head_sha)
            except Exception as exc:
                return CompletionLoopResult(
                    outcome=CompletionLoopOutcome.BLOCKED,
                    reason=f"GET_TREE_SHA_FAILED:{mat_result.integration_head_sha}:{exc}",
                    generation=current_generation,
                    integration_head_sha=mat_result.integration_head_sha,
                )

            if not isinstance(observed_int_tree, str) or not _GIT_SHA_RE.fullmatch(
                observed_int_tree
            ):
                return CompletionLoopResult(
                    outcome=CompletionLoopOutcome.BLOCKED,
                    reason=f"OBSERVED_INTEGRATION_TREE_MALFORMED:{observed_int_tree!r}",
                    generation=current_generation,
                    integration_head_sha=mat_result.integration_head_sha,
                )

            if observed_int_tree != mat_result.integration_tree_sha:
                return CompletionLoopResult(
                    outcome=CompletionLoopOutcome.BLOCKED,
                    reason=f"MATERIALIZED_TREE_SHA_MISMATCH: expected {mat_result.integration_tree_sha}, found {observed_int_tree}",
                    generation=current_generation,
                    integration_head_sha=mat_result.integration_head_sha,
                )

            # Caller independently observes changed path blobs from source Candidate C and integration head
            blob_equivalences: list[CandidateBlobEquivalence] = []
            for pth in candidate_changed_paths:
                try:
                    src_blob = port.read_blob_sha(source_candidate_commit_sha, pth)
                    int_blob = port.read_blob_sha(mat_result.integration_head_sha, pth)
                except Exception as exc:
                    return CompletionLoopResult(
                        outcome=CompletionLoopOutcome.BLOCKED,
                        reason=f"BLOB_READ_FAILED:{pth}:{exc}",
                        generation=current_generation,
                        integration_head_sha=mat_result.integration_head_sha,
                    )
                if (
                    not src_blob
                    or not int_blob
                    or not _GIT_SHA_RE.fullmatch(src_blob)
                    or not _GIT_SHA_RE.fullmatch(int_blob)
                ):
                    return CompletionLoopResult(
                        outcome=CompletionLoopOutcome.BLOCKED,
                        reason=f"BLOB_SHA_MALFORMED:{pth}",
                        generation=current_generation,
                        integration_head_sha=mat_result.integration_head_sha,
                    )
                if src_blob != int_blob:
                    return CompletionLoopResult(
                        outcome=CompletionLoopOutcome.BLOCKED,
                        reason=f"CANDIDATE_BLOB_SHA_MISMATCH:{pth}",
                        generation=current_generation,
                        integration_head_sha=mat_result.integration_head_sha,
                    )
                try:
                    blob_eq = CandidateBlobEquivalence(
                        path=pth,
                        source_blob_sha=src_blob,
                        integration_blob_sha=int_blob,
                    )
                    blob_equivalences.append(blob_eq)
                except Exception as exc:
                    return CompletionLoopResult(
                        outcome=CompletionLoopOutcome.BLOCKED,
                        reason=f"CANDIDATE_BLOB_EQUIVALENCE_INVALID:{pth}:{exc}",
                        generation=current_generation,
                        integration_head_sha=mat_result.integration_head_sha,
                    )

            last_produced_head_sha = mat_result.integration_head_sha
            current_generation = next_generation

            # Construct IntegrationBinding binding receipt hashes into requalification_hash
            combined_requal_data = {
                "requalification_hash": canonical_hash(requalification.model_dump(mode="json")),
                "revalidation_receipt_hashes": tuple(r.receipt_hash for r in revalidation_receipts),
            }
            combined_requal_hash = canonical_hash(combined_requal_data)

            proof_hash = compute_candidate_equivalence_proof_hash(
                source_candidate_commit_sha=source_candidate_commit_sha,
                source_candidate_tree_sha=source_candidate_tree_sha,
                source_candidate_diff_hash=source_candidate_diff_hash,
                integration_base_sha=current_main_sha,
                integration_head_sha=mat_result.integration_head_sha,
                integration_tree_sha=mat_result.integration_tree_sha,
                generation=current_generation,
                blob_equivalences=tuple(blob_equivalences),
            )

            try:
                integration_binding = IntegrationBinding(
                    source_candidate_commit_sha=source_candidate_commit_sha,
                    source_candidate_tree_sha=source_candidate_tree_sha,
                    source_contract_hash=source_candidate.contract_hash,
                    source_candidate_state_hash=source_candidate.candidate_state_hash,
                    source_verified_receipt_hash=source_candidate.verified_receipt_hash,
                    source_independent_acceptance_hash=source_candidate.independent_acceptance_hash,
                    source_candidate_diff_hash=source_candidate_diff_hash,
                    integration_base_sha=current_main_sha,
                    integration_head_sha=mat_result.integration_head_sha,
                    integration_tree_sha=mat_result.integration_tree_sha,
                    generation=current_generation,
                    requalification_hash=combined_requal_hash,
                    check_subject_kind="INTEGRATION_HEAD",
                    check_subject_sha=mat_result.integration_head_sha,
                    check_subject_tree_sha=mat_result.integration_tree_sha,
                    blob_equivalences=tuple(blob_equivalences),
                    candidate_equivalence_proof_hash=proof_hash,
                )
            except Exception as exc:
                return CompletionLoopResult(
                    outcome=CompletionLoopOutcome.BLOCKED,
                    reason=f"INTEGRATION_BINDING_REJECTED:{exc}",
                    generation=current_generation,
                    integration_head_sha=mat_result.integration_head_sha,
                )

            # Wait/read required checks for exact head_sha and generation with remaining time bound
            elapsed = clock_fn() - start_monotonic
            remaining = max(0.0, max_elapsed_seconds - elapsed)
            if remaining <= 0.0:
                return CompletionLoopResult(
                    outcome=CompletionLoopOutcome.DEFERRED_CONCURRENCY,
                    reason="TIME_BUDGET_EXHAUSTED",
                    generation=current_generation,
                    integration_head_sha=mat_result.integration_head_sha,
                    evidence=current_evidence,
                )

            try:
                checks = port.read_required_checks(
                    head_sha=mat_result.integration_head_sha,
                    generation=current_generation,
                    timeout_seconds=remaining,
                )
                if not checks:
                    return CompletionLoopResult(
                        outcome=CompletionLoopOutcome.BLOCKED,
                        reason="REQUIRED_CHECKS_MISSING",
                        generation=current_generation,
                        integration_head_sha=mat_result.integration_head_sha,
                    )
                for chk in checks:
                    if chk.head_sha != mat_result.integration_head_sha:
                        return CompletionLoopResult(
                            outcome=CompletionLoopOutcome.BLOCKED,
                            reason=f"CHECK_HEAD_SHA_MISMATCH: expected {mat_result.integration_head_sha}, found {chk.head_sha}",
                            generation=current_generation,
                            integration_head_sha=mat_result.integration_head_sha,
                        )
                    if chk.generation != current_generation:
                        return CompletionLoopResult(
                            outcome=CompletionLoopOutcome.BLOCKED,
                            reason=f"CHECK_GENERATION_MISMATCH: expected {current_generation}, found {chk.generation}",
                            generation=current_generation,
                            integration_head_sha=mat_result.integration_head_sha,
                        )
                    if not chk.terminal or chk.conclusion.lower() not in {"success", "passed"}:
                        return CompletionLoopResult(
                            outcome=CompletionLoopOutcome.BLOCKED,
                            reason=f"CHECK_FAILED_OR_NONTERMINAL:{chk.name}",
                            generation=current_generation,
                            integration_head_sha=mat_result.integration_head_sha,
                        )
            except Exception as exc:
                return CompletionLoopResult(
                    outcome=CompletionLoopOutcome.BLOCKED,
                    reason=f"REQUIRED_CHECKS_READ_FAILED:{exc}",
                    generation=current_generation,
                    integration_head_sha=mat_result.integration_head_sha,
                )

            # Read reviews
            try:
                reviews = port.read_reviews()
            except Exception as exc:
                return CompletionLoopResult(
                    outcome=CompletionLoopOutcome.BLOCKED,
                    reason=f"REVIEWS_READ_FAILED:{exc}",
                    generation=current_generation,
                    integration_head_sha=mat_result.integration_head_sha,
                )

            # Build new GitHubOrchestrationEvidence for this generation
            now_dt = now_fn()
            new_ev_payload = dict(
                repository=initial_evidence.repository,
                issue_number=initial_evidence.issue_number,
                pull_request_number=initial_evidence.pull_request_number,
                base_sha=current_main_sha,
                head_sha=mat_result.integration_head_sha,
                tree_sha=mat_result.integration_tree_sha,
                current_main_sha=current_main_sha,
                diff_hash=source_candidate_diff_hash,
                checks_hash=canonical_hash({"checks": [c.model_dump(mode="json") for c in checks]}),
                reviews_hash=canonical_hash({
                    "reviews": [r.model_dump(mode="json") for r in reviews]
                }),
                task_attempt_contract_hash=initial_evidence.task_attempt_contract_hash,
                candidate_hash=initial_evidence.candidate_hash,
                verifier_hash=initial_evidence.verifier_hash,
                independent_acceptance_hash=initial_evidence.independent_acceptance_hash,
                impact_hash=initial_evidence.impact_hash,
                observed_at=now_dt,
                fresh_until=now_dt + timedelta(hours=1),
                allowed_paths=initial_evidence.allowed_paths,
                changed_paths=initial_evidence.changed_paths,
                required_checks=tuple(checks),
                reviews=tuple(reviews),
                candidate=source_candidate,
                impact=initial_evidence.impact,
                integration=integration_binding,
                checks_passed=True,
                reviews_resolved=True,
                regression_free=True,
                impact_known=True,
                independent_acceptance=True,
            )

            try:
                current_evidence = GitHubOrchestrationEvidence.model_validate(new_ev_payload)
            except Exception as exc:
                return CompletionLoopResult(
                    outcome=CompletionLoopOutcome.BLOCKED,
                    reason=f"NEW_EVIDENCE_VALIDATION_FAILED:{exc}",
                    generation=current_generation,
                    integration_head_sha=mat_result.integration_head_sha,
                )

            # Re-read main state and PR head after check completion
            post_main_sha, post_main_tree_sha = port.read_main_state()
            post_pr_head = port.read_pr_head_sha()

            if post_pr_head != last_produced_head_sha:
                return CompletionLoopResult(
                    outcome=CompletionLoopOutcome.BLOCKED,
                    reason=f"FOREIGN_PR_HEAD_MUTATION_AFTER_CHECKS: expected {last_produced_head_sha}, found {post_pr_head}",
                    generation=current_generation,
                    integration_head_sha=last_produced_head_sha,
                    evidence=current_evidence,
                )

            if post_main_sha != current_main_sha:
                # Main moved again during checks! Loop to next generation.
                continue

        # At this point, current_evidence is aligned with current main.
        # Check merge intent and standing grant authorization
        intent_payload = {
            "schema": "nexus.github_merge_intent.v2",
            "kind": "MERGE_INTENT",
            "evidence": current_evidence.model_dump(mode="json"),
            "grant_outcome": "GRANT_MATCH",
            "mutation_authorized": False,
            "claim_ceiling": "m4_merge_eligible_and_intent_ready_only",
        }
        try:
            intent = MergeIntent.model_validate({
                **intent_payload,
                "intent_hash": canonical_hash(intent_payload),
            })
        except Exception as exc:
            return CompletionLoopResult(
                outcome=CompletionLoopOutcome.BLOCKED,
                reason=f"MERGE_INTENT_CREATION_FAILED:{exc}",
                generation=current_generation,
                integration_head_sha=last_produced_head_sha,
                evidence=current_evidence,
            )

        # Observe platform approval requirement fact from port
        try:
            plat_appr_req = port.is_platform_approval_required(
                repository=current_evidence.repository,
                pull_request_number=current_evidence.pull_request_number,
            )
        except Exception as exc:
            return CompletionLoopResult(
                outcome=CompletionLoopOutcome.BLOCKED,
                reason=f"PLATFORM_APPROVAL_OBSERVATION_FAILED:{exc}",
                generation=current_generation,
                integration_head_sha=last_produced_head_sha,
                evidence=current_evidence,
                intent=intent,
            )

        # Resolve durable merge authorization directly from imported authority function
        try:
            auth_decision = resolve_durable_merge_authorization(
                intent,
                request,
                current_evidence,
                platform_approval_required=plat_appr_req,
            )
        except Exception as exc:
            return CompletionLoopResult(
                outcome=CompletionLoopOutcome.BLOCKED,
                reason=f"MERGE_AUTHORIZATION_FAILED:{exc}",
                generation=current_generation,
                integration_head_sha=last_produced_head_sha,
                evidence=current_evidence,
                intent=intent,
            )

        if (
            auth_decision.outcome != StandingGrantOutcome.GRANT_MATCH
            or not auth_decision.mutation_authorized
        ):
            outcome_val = (
                auth_decision.outcome.value
                if hasattr(auth_decision.outcome, "value")
                else auth_decision.outcome
            )
            return CompletionLoopResult(
                outcome=CompletionLoopOutcome.BLOCKED,
                reason=f"MERGE_AUTHORIZATION_DENIED:{outcome_val}",
                generation=current_generation,
                integration_head_sha=last_produced_head_sha,
                evidence=current_evidence,
                intent=intent,
            )

        # Perform CAS merge operation
        cas_result = port.cas_merge(
            repository=current_evidence.repository,
            pull_request_number=current_evidence.pull_request_number,
            expected_base_sha=current_evidence.base_sha,
            expected_head_sha=current_evidence.head_sha,
        )

        if cas_result.status == CasMergeStatus.BASE_MOVED:
            # Main moved immediately before/during CAS merge!
            # Loop to absorb drift (if within generation budget)
            continue

        if cas_result.status == CasMergeStatus.AMBIGUOUS_ACK:
            # Lost/ambiguous ACK: reconcile physical merged state first
            try:
                recon = port.reconcile_post_merge(
                    repository=current_evidence.repository,
                    pull_request_number=current_evidence.pull_request_number,
                    expected_base_sha=current_evidence.base_sha,
                    expected_head_sha=current_evidence.head_sha,
                )
            except Exception as exc:
                return CompletionLoopResult(
                    outcome=CompletionLoopOutcome.BLOCKED,
                    reason=f"AMBIGUOUS_MERGE_RECONCILIATION_PORT_FAILED:{exc}",
                    generation=current_generation,
                    integration_head_sha=last_produced_head_sha,
                    evidence=current_evidence,
                    intent=intent,
                )

            valid_recon, recon_err = _validate_reconciliation_facts(
                recon,
                expected_base_sha=current_evidence.base_sha,
                expected_head_sha=current_evidence.head_sha,
                expected_integration_tree_sha=current_evidence.tree_sha,
                cas_merged_sha=cas_result.merged_sha,
            )
            if valid_recon:
                return CompletionLoopResult(
                    outcome=CompletionLoopOutcome.COMPLETED,
                    reason="AMBIGUOUS_ACK_RECONCILED_SUCCESS",
                    generation=current_generation,
                    integration_head_sha=last_produced_head_sha,
                    merged_commit_sha=recon.observed_main_commit_sha,
                    evidence=current_evidence,
                    intent=intent,
                )
            return CompletionLoopResult(
                outcome=CompletionLoopOutcome.BLOCKED,
                reason=f"AMBIGUOUS_MERGE_RECONCILIATION_FAILED:{recon_err}",
                generation=current_generation,
                integration_head_sha=last_produced_head_sha,
                evidence=current_evidence,
                intent=intent,
            )

        if cas_result.status == CasMergeStatus.SUCCESS:
            try:
                recon = port.reconcile_post_merge(
                    repository=current_evidence.repository,
                    pull_request_number=current_evidence.pull_request_number,
                    expected_base_sha=current_evidence.base_sha,
                    expected_head_sha=current_evidence.head_sha,
                )
            except Exception as exc:
                return CompletionLoopResult(
                    outcome=CompletionLoopOutcome.BLOCKED,
                    reason=f"POST_MERGE_RECONCILIATION_PORT_FAILED:{exc}",
                    generation=current_generation,
                    integration_head_sha=last_produced_head_sha,
                    evidence=current_evidence,
                    intent=intent,
                )

            valid_recon, recon_err = _validate_reconciliation_facts(
                recon,
                expected_base_sha=current_evidence.base_sha,
                expected_head_sha=current_evidence.head_sha,
                expected_integration_tree_sha=current_evidence.tree_sha,
                cas_merged_sha=cas_result.merged_sha,
            )
            if valid_recon:
                return CompletionLoopResult(
                    outcome=CompletionLoopOutcome.COMPLETED,
                    reason="MERGE_SUCCESS_AND_RECONCILED",
                    generation=current_generation,
                    integration_head_sha=last_produced_head_sha,
                    merged_commit_sha=recon.observed_main_commit_sha,
                    evidence=current_evidence,
                    intent=intent,
                )
            return CompletionLoopResult(
                outcome=CompletionLoopOutcome.BLOCKED,
                reason=f"POST_MERGE_RECONCILIATION_FAILED:{recon_err}",
                generation=current_generation,
                integration_head_sha=last_produced_head_sha,
                evidence=current_evidence,
                intent=intent,
            )

        # Any other CAS status is a rejection/conflict/failure
        return CompletionLoopResult(
            outcome=CompletionLoopOutcome.BLOCKED,
            reason=f"CAS_MERGE_REJECTED:{cas_result.status.value}:{cas_result.reason}",
            generation=current_generation,
            integration_head_sha=last_produced_head_sha,
            evidence=current_evidence,
            intent=intent,
        )
