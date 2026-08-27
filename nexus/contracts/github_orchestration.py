"""Strict, immutable evidence contracts for GitHub merge-intent preparation."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Mapping, Protocol

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictInt,
    StrictStr,
    field_validator,
    model_validator,
)

SHA40 = re.compile(r"^[0-9a-f]{40}$")
SHA64 = re.compile(r"^[0-9a-f]{64}$")


def _sha(v: str, n: str, size: int = 64) -> str:
    if not isinstance(v, str) or not (SHA40 if size == 40 else SHA64).fullmatch(v):
        raise ValueError(f"{n.upper()}_INVALID")
    return v


def canonical_hash(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(
            dict(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()
    ).hexdigest()


class ReadOnlyGitHubProvider(Protocol):
    def snapshot(
        self, repository: str, issue_number: int, pull_request_number: int
    ) -> Mapping[str, Any]: ...


class _Frozen(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)


class CheckResult(_Frozen):
    name: StrictStr
    status: StrictStr
    conclusion: StrictStr
    terminal: StrictBool = True
    subject_kind: StrictStr | None = None
    subject_sha: StrictStr | None = None
    generation: StrictInt | None = None

    @field_validator("subject_sha")
    @classmethod
    def check_sha(cls, v, info):
        return None if v is None else _sha(v, info.field_name, 40)

    @model_validator(mode="after")
    def valid(self):
        if (
            not self.name.strip()
            or not self.terminal
            or self.status.lower() not in {"completed", "success", "passed"}
            or self.conclusion.lower() not in {"success", "passed"}
        ):
            raise ValueError("CHECK_NONTERMINAL_OR_FAILED")
        return self


class ReviewResult(_Frozen):
    reviewer: StrictStr
    state: StrictStr
    unresolved_threads: StrictInt = Field(default=0, ge=0)

    @model_validator(mode="after")
    def valid(self):
        if (
            self.state.upper() in {"CHANGES_REQUESTED", "REQUESTED_CHANGES"}
            or self.unresolved_threads
        ):
            raise ValueError("REVIEW_UNRESOLVED")
        return self


class CandidateLineage(_Frozen):
    task_id: StrictStr
    attempt_id: StrictStr
    contract_hash: StrictStr
    card_hash: StrictStr
    candidate_commit_sha: StrictStr
    candidate_tree_sha: StrictStr
    candidate_state_hash: StrictStr
    verified_receipt_hash: StrictStr
    independent_acceptance_hash: StrictStr
    reviewer: StrictStr
    implementer: StrictStr
    candidate_diff_hash: StrictStr | None = None

    def acceptance_binding_hash(self) -> str:
        return compute_candidate_acceptance_binding_hash(self)

    def binding_hash(self) -> str:
        return compute_source_candidate_binding_hash(self)

    @field_validator(
        "contract_hash",
        "card_hash",
        "candidate_state_hash",
        "verified_receipt_hash",
        "independent_acceptance_hash",
    )
    @classmethod
    def h(cls, v, info):
        return _sha(v, info.field_name)

    @field_validator("candidate_diff_hash")
    @classmethod
    def opt_hash(cls, v, info):
        return None if v is None else _sha(v, info.field_name)

    @field_validator("candidate_commit_sha", "candidate_tree_sha")
    @classmethod
    def g(cls, v, info):
        return _sha(v, info.field_name, 40)


class ImpactResult(_Frozen):
    classification: StrictStr
    known: StrictBool
    regression_free: StrictBool

    @model_validator(mode="after")
    def valid(self):
        if (
            not self.known
            or not self.regression_free
            or self.classification.upper() in {"UNKNOWN", "NEW_REGRESSION", "REGRESSION"}
        ):
            raise ValueError("IMPACT_UNKNOWN_OR_REGRESSION")
        return self


class CandidateBlobEquivalenceEntry(_Frozen):
    path: StrictStr
    source_blob_sha: StrictStr = Field(alias="accepted_blob_sha")
    integration_blob_sha: StrictStr

    @property
    def accepted_blob_sha(self) -> str:
        return self.source_blob_sha

    @field_validator("source_blob_sha", "integration_blob_sha", mode="before")
    @classmethod
    def blob_sha(cls, v, info):
        return _sha(v, info.field_name, 40)

    @field_validator("path")
    @classmethod
    def safe_path(cls, v):
        if not isinstance(v, str) or not v or v.startswith("/") or ".." in v.split("/"):
            raise ValueError("PATH_INVALID")
        return v

    @model_validator(mode="after")
    def valid(self):
        if self.source_blob_sha != self.integration_blob_sha:
            raise ValueError("CANDIDATE_BLOBS_CHANGED_ACCEPTANCE_REUSE_REJECTED")
        return self


def compute_blob_equivalence_hash(
    entries: tuple[CandidateBlobEquivalenceEntry, ...] | list[CandidateBlobEquivalenceEntry],
) -> str:
    return canonical_hash({
        "blobs": [
            {
                "integration_blob_sha": e.integration_blob_sha,
                "path": e.path,
                "source_blob_sha": e.source_blob_sha,
            }
            for e in entries
        ]
    })


def compute_candidate_acceptance_binding_hash(candidate: CandidateLineage) -> str:
    """Deterministic independent acceptance binding hash for CandidateLineage."""
    payload = {
        "schema": "nexus.candidate_acceptance_binding.v1",
        "attempt_id": candidate.attempt_id,
        "candidate_commit_sha": candidate.candidate_commit_sha,
        "candidate_diff_hash": candidate.candidate_diff_hash or "",
        "candidate_state_hash": candidate.candidate_state_hash,
        "candidate_tree_sha": candidate.candidate_tree_sha,
        "card_hash": candidate.card_hash,
        "contract_hash": candidate.contract_hash,
        "implementer": candidate.implementer,
        "reviewer": candidate.reviewer,
        "task_id": candidate.task_id,
        "verified_receipt_hash": candidate.verified_receipt_hash,
    }
    return canonical_hash(payload)


def compute_source_candidate_binding_hash(candidate: CandidateLineage) -> str:
    """Deterministic binding hash for the accepted source Candidate identity."""
    payload = {
        "schema": "nexus.source_candidate_binding.v1",
        "attempt_id": candidate.attempt_id,
        "candidate_commit_sha": candidate.candidate_commit_sha,
        "candidate_diff_hash": candidate.candidate_diff_hash or "",
        "candidate_state_hash": candidate.candidate_state_hash,
        "candidate_tree_sha": candidate.candidate_tree_sha,
        "card_hash": candidate.card_hash,
        "contract_hash": candidate.contract_hash,
        "implementer": candidate.implementer,
        "independent_acceptance_hash": candidate.independent_acceptance_hash,
        "reviewer": candidate.reviewer,
        "task_id": candidate.task_id,
        "verified_receipt_hash": candidate.verified_receipt_hash,
    }
    return canonical_hash(payload)


class IntegrationBinding(_Frozen):
    """Immutable binding for an integration/check subject produced after main drift."""

    schema: StrictStr = "nexus.integration_binding.v1"
    base_sha: StrictStr
    integration_head_sha: StrictStr
    integration_tree_sha: StrictStr
    source_candidate_commit_sha: StrictStr
    source_candidate_tree_sha: StrictStr
    source_candidate_diff_hash: StrictStr
    source_candidate_binding_hash: StrictStr
    generation: StrictInt = Field(ge=1)
    check_subject_generation: StrictInt = Field(ge=1)
    requalification_hash: StrictStr
    check_subject_kind: StrictStr = "INTEGRATION_HEAD"
    check_subject_sha: StrictStr
    candidate_blobs_equivalent: StrictBool = True
    blob_proof: tuple[CandidateBlobEquivalenceEntry, ...] = ()
    blob_equivalence_hash: StrictStr
    acceptance_reused: StrictBool = True
    source_candidate_state_hash: StrictStr | None = None
    source_candidate_acceptance_hash: StrictStr | None = None

    @field_validator(
        "base_sha",
        "integration_head_sha",
        "integration_tree_sha",
        "check_subject_sha",
        "source_candidate_commit_sha",
        "source_candidate_tree_sha",
    )
    @classmethod
    def git_sha(cls, v, info):
        return _sha(v, info.field_name, 40)

    @field_validator(
        "requalification_hash",
        "blob_equivalence_hash",
        "source_candidate_diff_hash",
        "source_candidate_binding_hash",
    )
    @classmethod
    def digests(cls, v, info):
        return _sha(v, info.field_name)

    @field_validator(
        "source_candidate_state_hash",
        "source_candidate_acceptance_hash",
    )
    @classmethod
    def opt_digests(cls, v, info):
        return None if v is None else _sha(v, info.field_name)

    @model_validator(mode="after")
    def valid(self):
        if self.check_subject_kind != "INTEGRATION_HEAD":
            raise ValueError("INTEGRATION_CHECK_SUBJECT_KIND_INVALID")
        if self.check_subject_sha != self.integration_head_sha:
            raise ValueError("INTEGRATION_CHECK_SUBJECT_SHA_MISMATCH")
        if self.check_subject_generation != self.generation:
            raise ValueError("INTEGRATION_CHECK_GENERATION_MISMATCH")
        if self.source_candidate_commit_sha == self.integration_head_sha:
            raise ValueError("INTEGRATION_CANNOT_REPLACE_SOURCE_CANDIDATE")
        if self.acceptance_reused:
            if not self.blob_proof:
                raise ValueError("BLOB_PROOF_EMPTY_FOR_ACCEPTANCE_REUSE")
            if not self.candidate_blobs_equivalent:
                raise ValueError("CANDIDATE_BLOBS_CHANGED_ACCEPTANCE_REUSE_REJECTED")
            for entry in self.blob_proof:
                if entry.source_blob_sha != entry.integration_blob_sha:
                    raise ValueError("CANDIDATE_BLOBS_CHANGED_ACCEPTANCE_REUSE_REJECTED")
        if self.blob_proof:
            proof_paths = tuple(e.path for e in self.blob_proof)
            if proof_paths != tuple(sorted(set(proof_paths))):
                raise ValueError("BLOB_PROOF_PATHS_NOT_SORTED_UNIQUE")
            expected_blob_hash = compute_blob_equivalence_hash(self.blob_proof)
            if self.blob_equivalence_hash != expected_blob_hash:
                raise ValueError("BLOB_EQUIVALENCE_HASH_MISMATCH")
        return self


class GitHubOrchestrationEvidence(_Frozen):
    schema: StrictStr = "nexus.github_orchestration_evidence.v2"
    repository: StrictStr
    issue_number: StrictInt = Field(gt=0)
    pull_request_number: StrictInt = Field(gt=0)
    base_sha: StrictStr
    head_sha: StrictStr
    tree_sha: StrictStr
    current_main_sha: StrictStr
    diff_hash: StrictStr
    checks_hash: StrictStr
    reviews_hash: StrictStr
    task_attempt_contract_hash: StrictStr
    candidate_hash: StrictStr
    verifier_hash: StrictStr
    independent_acceptance_hash: StrictStr
    impact_hash: StrictStr
    observed_at: AwareDatetime
    fresh_until: AwareDatetime
    allowed_paths: tuple[StrictStr, ...]
    changed_paths: tuple[StrictStr, ...]
    required_checks: tuple[CheckResult, ...]
    reviews: tuple[ReviewResult, ...]
    candidate: CandidateLineage
    impact: ImpactResult
    integration: IntegrationBinding | None = None
    checks_passed: StrictBool = True
    reviews_resolved: StrictBool = True
    regression_free: StrictBool = True
    impact_known: StrictBool = True
    independent_acceptance: StrictBool = True

    @field_validator("base_sha", "head_sha", "tree_sha", "current_main_sha")
    @classmethod
    def git(cls, v, info):
        return None if v is None else _sha(v, info.field_name, 40)

    @field_validator(
        "diff_hash",
        "checks_hash",
        "reviews_hash",
        "task_attempt_contract_hash",
        "candidate_hash",
        "verifier_hash",
        "independent_acceptance_hash",
        "impact_hash",
    )
    @classmethod
    def hashes(cls, v, info):
        return _sha(v, info.field_name)

    @field_validator("allowed_paths", "changed_paths")
    @classmethod
    def paths(cls, v, info):
        vals = tuple(v)
        if vals != tuple(sorted(set(vals))) or any(
            not isinstance(x, str) or not x or x.startswith("/") or ".." in x.split("/")
            for x in vals
        ):
            raise ValueError("PATHS_NOT_SORTED_UNIQUE_OR_INVALID")
        return vals

    @model_validator(mode="after")
    def valid(self):
        if self.fresh_until <= self.observed_at:
            raise ValueError("FRESHNESS_INVALID")
        if not set(self.changed_paths).issubset(self.allowed_paths):
            raise ValueError("DIFF_OUT_OF_SCOPE")
        if len(set(c.name for c in self.required_checks)) != len(self.required_checks):
            raise ValueError("CHECKS_DUPLICATE")
        if self.repository != "James3014/Nexus-new":
            raise ValueError("REPOSITORY_IDENTITY_INVALID")
        if self.current_main_sha != self.base_sha:
            raise ValueError("CURRENT_MAIN_SHA_MISMATCH")
        if self.integration is None:
            if (
                self.candidate.candidate_commit_sha != self.head_sha
                or self.candidate.candidate_tree_sha != self.tree_sha
            ):
                raise ValueError("CANDIDATE_LINEAGE_MISMATCH")
            if (
                self.candidate.candidate_diff_hash is not None
                and self.candidate.candidate_diff_hash != self.diff_hash
            ):
                raise ValueError("CANDIDATE_DIFF_HASH_MISMATCH")
        else:
            if self.candidate.candidate_commit_sha != self.integration.source_candidate_commit_sha:
                raise ValueError("SOURCE_CANDIDATE_COMMIT_SHA_MISMATCH")
            if self.candidate.candidate_tree_sha != self.integration.source_candidate_tree_sha:
                raise ValueError("SOURCE_CANDIDATE_TREE_SHA_MISMATCH")
            if (
                self.candidate.candidate_diff_hash is None
                or self.candidate.candidate_diff_hash != self.integration.source_candidate_diff_hash
            ):
                raise ValueError("SOURCE_CANDIDATE_DIFF_HASH_MISMATCH")
            if self.integration.acceptance_reused:
                expected_acceptance_hash = self.candidate.acceptance_binding_hash()
                if self.candidate.independent_acceptance_hash != expected_acceptance_hash:
                    raise ValueError("SOURCE_CANDIDATE_ACCEPTANCE_HASH_MISMATCH")
                if self.independent_acceptance_hash != expected_acceptance_hash:
                    raise ValueError("SOURCE_CANDIDATE_ACCEPTANCE_HASH_MISMATCH")
            if self.candidate.binding_hash() != self.integration.source_candidate_binding_hash:
                raise ValueError("SOURCE_CANDIDATE_BINDING_HASH_MISMATCH")
            if (
                self.integration.source_candidate_state_hash is not None
                and self.candidate.candidate_state_hash != self.integration.source_candidate_state_hash
            ):
                raise ValueError("SOURCE_CANDIDATE_STATE_HASH_MISMATCH")
            if (
                self.integration.source_candidate_acceptance_hash is not None
                and self.candidate.independent_acceptance_hash != self.integration.source_candidate_acceptance_hash
            ):
                raise ValueError("SOURCE_CANDIDATE_ACCEPTANCE_HASH_MISMATCH")
            if self.candidate.candidate_commit_sha == self.integration.integration_head_sha:
                raise ValueError("INTEGRATION_CANNOT_REPLACE_SOURCE_CANDIDATE")
            if self.integration.integration_head_sha != self.head_sha:
                raise ValueError("INTEGRATION_HEAD_SHA_MISMATCH")
            if self.integration.integration_tree_sha != self.tree_sha:
                raise ValueError("INTEGRATION_TREE_SHA_MISMATCH")
            if self.integration.base_sha != self.base_sha:
                raise ValueError("INTEGRATION_BASE_SHA_MISMATCH")
            if not self.integration.candidate_blobs_equivalent:
                raise ValueError("CANDIDATE_BLOBS_CHANGED_ACCEPTANCE_REUSE_REJECTED")
            if self.integration.acceptance_reused:
                proof_paths = tuple(e.path for e in self.integration.blob_proof)
                if proof_paths != self.changed_paths:
                    raise ValueError("BLOB_PROOF_PATHS_MISMATCH_CHANGED_PATHS")
            for c in self.required_checks:
                if c.generation is None or c.generation != self.integration.generation:
                    raise ValueError("CHECK_GENERATION_MISMATCH")
                if c.subject_sha is None or c.subject_sha != self.integration.integration_head_sha:
                    raise ValueError("CHECK_SUBJECT_SHA_MISMATCH")
                if c.subject_kind is None or c.subject_kind != self.integration.check_subject_kind:
                    raise ValueError("CHECK_SUBJECT_KIND_MISMATCH")
        if self.candidate.reviewer.strip() == self.candidate.implementer.strip():
            raise ValueError("REVIEWER_IMPLEMENTER_MUST_DIFFER")
        if not self.reviews:
            raise ValueError("REVIEW_INDEPENDENT_MISSING")
        reviewers = {r.reviewer.strip() for r in self.reviews}
        if self.candidate.implementer.strip() in reviewers:
            raise ValueError("REVIEWER_IMPLEMENTER_MUST_DIFFER")
        if not self.checks_passed:
            raise ValueError("CHECKS_FAILED_OR_MISSING")
        if not self.required_checks:
            raise ValueError("CHECK_FAILED_OR_MISSING")
        if not all(
            c.terminal and c.conclusion.lower() in {"success", "passed"}
            for c in self.required_checks
        ):
            raise ValueError("CHECKS_SUMMARY_CONTRADICTS_DETAIL")
        if not self.reviews_resolved or not all(
            not r.unresolved_threads
            and r.state.upper() not in {"CHANGES_REQUESTED", "REQUESTED_CHANGES"}
            for r in self.reviews
        ):
            raise ValueError("REVIEWS_SUMMARY_CONTRADICTS_DETAIL")
        if (
            not self.impact_known
            or not self.regression_free
            or not self.impact.known
            or not self.impact.regression_free
        ):
            raise ValueError("IMPACT_SUMMARY_CONTRADICTS_DETAIL")
        if self.candidate.contract_hash != self.task_attempt_contract_hash:
            raise ValueError("TASK_ATTEMPT_LINEAGE_MISMATCH")
        if self.candidate.candidate_state_hash != self.candidate_hash:
            raise ValueError("CANDIDATE_HASH_LINEAGE_MISMATCH")
        if self.candidate.verified_receipt_hash != self.verifier_hash:
            raise ValueError("VERIFIER_HASH_LINEAGE_MISMATCH")
        if self.candidate.independent_acceptance_hash != self.independent_acceptance_hash:
            raise ValueError("ACCEPTANCE_HASH_LINEAGE_MISMATCH")
        if not self.independent_acceptance:
            raise ValueError("INDEPENDENT_ACCEPTANCE_MISSING")
        if self.reviews_hash != canonical_hash({
            "reviews": [r.model_dump(mode="json") for r in self.reviews]
        }):
            raise ValueError("REVIEWS_HASH_MISMATCH")
        if self.required_checks and self.checks_hash != canonical_hash({
            "checks": [c.model_dump(mode="json") for c in self.required_checks]
        }):
            raise ValueError("CHECKS_HASH_MISMATCH")
        if self.impact_hash != canonical_hash(self.impact.model_dump(mode="json")):
            raise ValueError("IMPACT_HASH_MISMATCH")
        if len(set(c.name for c in self.required_checks)) != len(self.required_checks):
            raise ValueError("CHECKS_DUPLICATE")
        return self


class MergeIntent(_Frozen):
    schema: StrictStr = "nexus.github_merge_intent.v2"
    kind: StrictStr = "MERGE_INTENT"
    evidence: GitHubOrchestrationEvidence
    grant_outcome: StrictStr
    mutation_authorized: StrictBool = False
    claim_ceiling: StrictStr = "m4_merge_eligible_and_intent_ready_only"
    intent_hash: StrictStr

    @model_validator(mode="after")
    def bound(self):
        if self.mutation_authorized or self.intent_hash != canonical_hash(
            self.model_dump(mode="json", exclude={"intent_hash"})
        ):
            raise ValueError("INTENT_HASH_INVALID_OR_MUTATION_FORBIDDEN")
        return self


GitHubSnapshot = GitHubOrchestrationEvidence


class MainMovementEvidence(_Frozen):
    """Immutable inputs for dimension-scoped main-movement requalification.

    This is a projection over an already verified GitHub evidence packet.  It
    deliberately contains no merge or approval authority.
    """

    old_main_sha: StrictStr
    old_main_tree_sha: StrictStr
    new_main_sha: StrictStr
    new_main_tree_sha: StrictStr
    candidate_head_sha: StrictStr
    candidate_tree_sha: StrictStr
    candidate_diff_hash: StrictStr
    candidate_changed_paths: tuple[StrictStr, ...]
    changed_main_paths: tuple[StrictStr, ...]
    prior_impact_hash: StrictStr
    prior_verifier_hash: StrictStr

    @field_validator(
        "old_main_sha",
        "old_main_tree_sha",
        "new_main_sha",
        "new_main_tree_sha",
        "candidate_head_sha",
        "candidate_tree_sha",
    )
    @classmethod
    def git_sha(cls, value, info):
        return _sha(value, info.field_name, 40)

    @field_validator("candidate_diff_hash", "prior_impact_hash", "prior_verifier_hash")
    @classmethod
    def digest(cls, value, info):
        return _sha(value, info.field_name)

    @field_validator("candidate_changed_paths", "changed_main_paths")
    @classmethod
    def safe_paths(cls, value, info):
        values = tuple(value)
        if values != tuple(sorted(set(values))) or any(
            not item or item.startswith("/") or ".." in item.split("/") for item in values
        ):
            raise ValueError(f"{info.field_name.upper()}_INVALID")
        return values

    @model_validator(mode="after")
    def bound(self):
        if self.old_main_sha == self.new_main_sha:
            raise ValueError("MAIN_MOVEMENT_SHA_UNCHANGED")
        if (
            self.old_main_tree_sha == self.new_main_tree_sha
            and self.old_main_sha != self.new_main_sha
        ):
            raise ValueError("MAIN_MOVEMENT_TREE_SHA_BINDING_INVALID")
        if not self.candidate_changed_paths:
            raise ValueError("CANDIDATE_PATH_MAP_MISSING")
        if not self.changed_main_paths:
            raise ValueError("MAIN_MOVEMENT_PATHS_MISSING")
        return self


class MainMovementDimensionResult(_Frozen):
    dimension: StrictStr
    classification: StrictStr
    action: StrictStr
    reasons: tuple[StrictStr, ...] = ()

    @model_validator(mode="after")
    def valid(self):
        if self.action not in {"REUSE_UNAFFECTED", "RECHECK_AFFECTED", "IMPACT_UNKNOWN"}:
            raise ValueError("REQUALIFICATION_ACTION_INVALID")
        if self.classification not in {
            "SOURCE_IDENTITY_DRIFT",
            "SEMANTIC_OVERLAP",
            "TEST_IMPACT",
            "AUTHORITY_DRIFT",
            "TRANSPORT_DRIFT",
            "IRRELEVANT_MAIN_MOVEMENT",
            "IMPACT_UNKNOWN",
        }:
            raise ValueError("REQUALIFICATION_CLASSIFICATION_INVALID")
        return self


class MainMovementRequalification(_Frozen):
    """Fail-closed evidence reuse projection; never merge authority."""

    schema: StrictStr = "nexus.main_movement_requalification.v1"
    old_main_sha: StrictStr
    new_main_sha: StrictStr
    candidate_head_sha: StrictStr
    candidate_tree_sha: StrictStr
    dimensions: tuple[MainMovementDimensionResult, ...]
    blocked: StrictBool
    claim_ceiling: StrictStr = "COMPLETION_PATH_COMPRESSION_TARGET_B_CANDIDATE_ONLY"

    @model_validator(mode="after")
    def valid(self):
        expected = {
            "SOURCE_IDENTITY",
            "SEMANTIC_OVERLAP",
            "TEST_IMPACT",
            "AUTHORITY_DRIFT",
            "TRANSPORT_DRIFT",
            "IRRELEVANT_MAIN_MOVEMENT",
        }
        if {item.dimension for item in self.dimensions} != expected:
            raise ValueError("REQUALIFICATION_DIMENSIONS_INCOMPLETE")
        if any(item.action == "IMPACT_UNKNOWN" for item in self.dimensions) and not self.blocked:
            raise ValueError("UNKNOWN_IMPACT_MUST_BLOCK")
        return self
