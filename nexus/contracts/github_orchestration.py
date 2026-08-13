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
    model_config = ConfigDict(extra="forbid", frozen=True)


class CheckResult(_Frozen):
    name: StrictStr
    status: StrictStr
    conclusion: StrictStr
    terminal: StrictBool = True

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


class GitHubOrchestrationEvidence(_Frozen):
    schema: StrictStr = "nexus.github_orchestration_evidence.v2"
    repository: StrictStr
    issue_number: StrictInt = Field(gt=0)
    pull_request_number: StrictInt = Field(gt=0)
    base_sha: StrictStr
    head_sha: StrictStr
    tree_sha: StrictStr
    current_main_sha: StrictStr | None = None
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
    required_checks: tuple[CheckResult, ...] = ()
    reviews: tuple[ReviewResult, ...] = ()
    candidate: CandidateLineage | None = None
    impact: ImpactResult | None = None
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
