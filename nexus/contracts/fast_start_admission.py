"""Pure contracts and data structures for Fast Start admission.

Deliberately read-only and deterministic.  #549 is ADVISORY_CACHE_ONLY.
Precedence: fresh current main/source > latest durable Issue contract > direct dependency / PR metadata > #549 advisory cache.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping


class FastStartDecision(str, Enum):
    DENY_BLOCKED = "DENY_BLOCKED"
    DENY_HOST_BOUND = "DENY_HOST_BOUND"
    DENY_NEEDS_DECISION = "DENY_NEEDS_DECISION"
    DENY_EVIDENCE_BLOCKED = "DENY_EVIDENCE_BLOCKED"
    ALLOW_READY = "ALLOW_READY"
    ALLOW_FULL_DISCOVERY = "ALLOW_FULL_DISCOVERY"


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha256_json(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class FastStartAdmissionRequest:
    issue_number: int | None
    repository: str = "James3014/Nexus-new"
    current_main_sha: str | None = None
    current_main_tree: str | None = None
    launch_kind: str = "managed_github_issue_codex"
    registry_snapshot: Mapping[str, Any] | None = None
    task_id: str | None = None
    context: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class FastStartAdmissionResult:
    schema: str = "nexus.fast_start_admission.v1"
    issue: int | None = None
    decision: FastStartDecision = FastStartDecision.ALLOW_FULL_DISCOVERY
    codex_launch_allowed: bool = True
    reason: str = ""
    registry_revision: int | None = None
    registry_hash: str | None = None
    observed_main_sha: str | None = None
    observed_main_tree: str | None = None
    observed_blockers: tuple[dict[str, Any], ...] = ()
    cache_disposition: str = "CACHE_MISS"
    dispatch_state: str | None = None
    fresh_rebind_evidence: dict[str, Any] = field(default_factory=dict)
    fence_digest: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "issue": self.issue,
            "decision": self.decision.value if isinstance(self.decision, Enum) else str(self.decision),
            "codex_launch_allowed": self.codex_launch_allowed,
            "reason": self.reason,
            "registry_revision": self.registry_revision,
            "registry_hash": self.registry_hash,
            "observed_main_sha": self.observed_main_sha,
            "observed_main_tree": self.observed_main_tree,
            "observed_blockers": list(self.observed_blockers),
            "cache_disposition": self.cache_disposition,
            "dispatch_state": self.dispatch_state,
            "fresh_rebind_evidence": dict(self.fresh_rebind_evidence),
            "fence_digest": self.fence_digest,
        }


class FastStartAdmissionDeniedError(RuntimeError):
    """Raised when Fast Start deterministic admission denies Codex worker launch."""

    def __init__(self, decision: FastStartAdmissionResult):
        self.decision = decision
        super().__init__(f"FAST_START_ADMISSION_DENIED: {decision.decision.value} - {decision.reason}")
