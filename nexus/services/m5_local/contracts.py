"""Canonical contracts, schemas, and typed boundaries for M5 RDC Local integration.

Owns the data models and invariants for:
- Mode A: Local Assist (read-only repository intelligence and assistance).
- Mode B: Local Worker (execution substrate; write disabled by default).
- Predecessor-successor handoff lineage (compatible with runtime#45).
- Resource, memory safety, and learning telemetry.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

# Schemas
M5_LOCAL_ASSIST_REQUEST_SCHEMA = "nexus.m5_local.assist_request.v1"
M5_LOCAL_ASSIST_RESPONSE_SCHEMA = "nexus.m5_local.assist_response.v1"
M5_LOCAL_WORKER_REQUEST_SCHEMA = "nexus.m5_local.worker_request.v1"
M5_LOCAL_WORKER_RESPONSE_SCHEMA = "nexus.m5_local.worker_response.v1"
M5_LOCAL_BOUNDED_PACKET_SCHEMA = "nexus.m5_local.deterministic_fallback_packet.v1"
M5_LOCAL_HANDOFF_SCHEMA = "nexus.m5_local.handoff_input.v1"
M5_LOCAL_TELEMETRY_SCHEMA = "nexus.m5_local.telemetry.v1"
M5_LOCAL_HOST_INVENTORY_SCHEMA = "nexus.m5_local.host_inventory.v1"

# Invariants & Claim Ceilings
M5_LOCAL_CLAIM_CEILING = "LOCAL_NON_AUTHORITATIVE_EVIDENCE_ONLY"
LOCAL_WRITE_DEFAULT = "DENY_UNQUALIFIED"
LOCAL_ASSIST_MUTATION_AUTHORITY = False

# Transport & Service Mode constants (reusing authorized execution lanes per #1266)
SERVICE_MODE_LOCAL = "LOCAL"
TRANSPORT_KIND_RDC = "RDC"
TRANSPORT_KIND_LOCAL_RUNNER = "LOCAL_RUNNER"

# Role Definitions
ROLE_REPO_RANKING = "repo_ranking"
ROLE_TYPED_DECISION = "typed_decision"
ROLE_READ_ONLY_ASSIST = "read_only_assist"
ROLE_BOUNDED_CODE_PATCH = "bounded_code_patch"

RECOGNIZED_ROLES = frozenset({
    ROLE_REPO_RANKING,
    ROLE_TYPED_DECISION,
    ROLE_READ_ONLY_ASSIST,
    ROLE_BOUNDED_CODE_PATCH,
})

# Qualification Statuses
QUALIFICATION_RUNNABLE = "RUNTIME_RUNNABLE"
QUALIFICATION_QUALIFIED = "ROLE_QUALIFIED"
QUALIFICATION_NOT_QUALIFIED = "NOT_QUALIFIED"

# Host Asset Classifications
HOST_CLASSIFICATION_AVAILABLE_EXACT = "AVAILABLE_EXACT"
HOST_CLASSIFICATION_PARTIAL = "PARTIAL"
HOST_CLASSIFICATION_NOT_INSTALLED = "NOT_INSTALLED"
HOST_CLASSIFICATION_UNKNOWN = "UNKNOWN"

RECOGNIZED_HOST_CLASSIFICATIONS = frozenset({
    HOST_CLASSIFICATION_AVAILABLE_EXACT,
    HOST_CLASSIFICATION_PARTIAL,
    HOST_CLASSIFICATION_NOT_INSTALLED,
    HOST_CLASSIFICATION_UNKNOWN,
})

# Typed Escalation Reasons (Section 15)
LOCAL_RUNTIME_UNAVAILABLE = "LOCAL_RUNTIME_UNAVAILABLE"
LOCAL_MODEL_IDENTITY_MISMATCH = "LOCAL_MODEL_IDENTITY_MISMATCH"
LOCAL_ROLE_NOT_QUALIFIED = "LOCAL_ROLE_NOT_QUALIFIED"
LOCAL_CONTEXT_LIMIT = "LOCAL_CONTEXT_LIMIT"
LOCAL_TIMEOUT = "LOCAL_TIMEOUT"
LOCAL_RESOURCE_PRESSURE = "LOCAL_RESOURCE_PRESSURE"
LOCAL_RESULT_INSUFFICIENT = "LOCAL_RESULT_INSUFFICIENT"

RECOGNIZED_ESCALATION_REASONS = frozenset({
    LOCAL_RUNTIME_UNAVAILABLE,
    LOCAL_MODEL_IDENTITY_MISMATCH,
    LOCAL_ROLE_NOT_QUALIFIED,
    LOCAL_CONTEXT_LIMIT,
    LOCAL_TIMEOUT,
    LOCAL_RESOURCE_PRESSURE,
    LOCAL_RESULT_INSUFFICIENT,
})


class LocalBridgeError(Exception):
    """Base exception for all M5 Local Bridge contract violations."""


class LocalAssistMutationAttemptedError(LocalBridgeError):
    """Raised when Local Assist attempts any filesystem or repository write."""


class LocalWorkerDeniedError(LocalBridgeError):
    """Raised when Local Worker mutation is requested without qualification or external authorities."""


class ModelIdentityMismatchError(LocalBridgeError):
    """Raised when requested model identity differs from observed physical model identity."""


class ResourcePressureError(LocalBridgeError):
    """Raised when host memory, swap, or CPU pressure prevents safe execution."""


class HandoffContractError(LocalBridgeError):
    """Raised when handoff lineage or packet boundaries are violated."""


class StaleBaseError(LocalBridgeError):
    """Raised when execution base does not match current repository head/base."""


def utc_now() -> str:
    """Return ISO 8601 UTC timestamp."""
    return datetime.now(timezone.utc).isoformat()


def sha256_json(data: Any) -> str:
    """Return deterministic SHA-256 for a JSON-serializable structure."""
    raw = json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class CandidatePathEntry:
    """A localized repository path candidate with entry rationale."""

    path: str
    reason: str
    line_count: int = 0
    score: float = 0.0


@dataclass(frozen=True)
class SourceExcerpt:
    """A bounded excerpt from a candidate file."""

    path: str
    start_line: int
    end_line: int
    content: str


@dataclass(frozen=True)
class BoundedEvidencePacket:
    """Input evidence packet for Local Assist produced by deterministic local fallback search.

    Note: This is a bounded deterministic local fallback and explicitly not a reimplementation
    of or equivalent to the Repository Intelligence Engine (RIE).
    """

    schema: str = M5_LOCAL_BOUNDED_PACKET_SCHEMA
    producer: str = "nexus.m5_local.deterministic_fallback.v1"
    task_id: str = ""
    query: str = ""
    repo_identity: str = ""
    base_sha: str = ""
    candidate_paths: list[CandidatePathEntry] = field(default_factory=list)
    source_excerpts: list[SourceExcerpt] = field(default_factory=list)
    test_candidates: list[str] = field(default_factory=list)
    known_decisions_or_contracts: list[str] = field(default_factory=list)
    known_failures: list[str] = field(default_factory=list)
    evidence_provenance: dict[str, Any] = field(default_factory=dict)
    omitted_files_notice: str = (
        "A file omitted from retrieval must never be interpreted as proof that it does not exist."
    )
    created_at: str = field(default_factory=utc_now)

    def packet_hash(self) -> str:
        return sha256_json({
            "task_id": self.task_id,
            "query": self.query,
            "repo_identity": self.repo_identity,
            "base_sha": self.base_sha,
            "candidate_paths": [asdict(p) for p in self.candidate_paths],
            "source_excerpts": [asdict(e) for e in self.source_excerpts],
            "test_candidates": self.test_candidates,
            "known_decisions_or_contracts": self.known_decisions_or_contracts,
        })


@dataclass(frozen=True)
class LocalAssistRequest:
    """Request for Mode A — Local Assist."""

    schema: str = M5_LOCAL_ASSIST_REQUEST_SCHEMA
    task_id: str = ""
    work_id: str = ""
    query: str = ""
    repo_path: str = ""
    base_sha: str = ""
    candidate_hints: list[str] = field(default_factory=list)
    role: str = ROLE_READ_ONLY_ASSIST
    requested_runtime: Optional[str] = None
    requested_model: Optional[str] = None
    max_tokens: int = 1024
    timeout_seconds: float = 30.0
    allow_inference: bool = True


@dataclass(frozen=True)
class LocalAssistResponse:
    """Evidence-backed response from Mode A — Local Assist."""

    schema: str = M5_LOCAL_ASSIST_RESPONSE_SCHEMA
    task_id: str = ""
    status: str = "SUCCESS"  # SUCCESS, ESCALATED, FAILED
    findings: str = ""
    candidate_files: list[str] = field(default_factory=list)
    suggested_tests: list[str] = field(default_factory=list)
    evidence_refs: list[str] = field(default_factory=list)
    claims_linked_to_evidence: bool = True
    escalation_reason: Optional[str] = None
    requested_runtime: Optional[str] = None
    observed_runtime: Optional[str] = None
    requested_model: Optional[str] = None
    observed_model: Optional[str] = None
    evidence_packet_hash: str = ""
    telemetry: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_now)


@dataclass(frozen=True)
class LocalWorkerRequest:
    """Request for Mode B — Local Worker (execution substrate)."""

    schema: str = M5_LOCAL_WORKER_REQUEST_SCHEMA
    task_id: str = ""
    work_id: str = ""
    attempt_id: str = ""
    operation_id: str = ""
    repo_path: str = ""
    base_sha: str = ""
    allowed_scope: list[str] = field(default_factory=list)
    task_instruction: str = ""
    role: str = ROLE_BOUNDED_CODE_PATCH
    requested_runtime: str = ""
    requested_model: str = ""
    claim_receipt_ref: Optional[str] = None
    conflict_admission_token: Optional[str] = None
    workspace_root: str = ""
    write_permitted: bool = False
    timeout_seconds: float = 60.0


@dataclass(frozen=True)
class LocalWorkerResponse:
    """Result of bounded Local Worker execution."""

    schema: str = M5_LOCAL_WORKER_RESPONSE_SCHEMA
    task_id: str = ""
    attempt_id: str = ""
    operation_id: str = ""
    status: str = "COMPLETED"  # COMPLETED, REJECTED_DENIED, FAILED, TIMEOUT, CANCELLED
    diff: str = ""
    touched_paths: list[str] = field(default_factory=list)
    stdout: str = ""
    stderr: str = ""
    exit_code: Optional[int] = 0
    escalation_reason: Optional[str] = None
    write_performed: bool = False
    requested_runtime: str = ""
    observed_runtime: str = ""
    requested_model: str = ""
    observed_model: str = ""
    telemetry: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_now)


@dataclass(frozen=True)
class HandoffPacket:
    """Ephemeral handoff input packet when Local cannot complete and escalates to Online.

    Note: This object is an ephemeral projection (handoff input) to be consumed by the
    external coordinator / canonical Runtime #45 handoff authority. It does NOT constitute
    canonical durable handoff state on its own.
    """

    schema: str = M5_LOCAL_HANDOFF_SCHEMA
    durability: str = "EPHEMERAL_PROJECTION"
    nature: str = "HANDOFF_INPUT"
    task_id: str = ""
    work_id: str = ""
    predecessor_attempt_id: str = ""
    predecessor_operation_id: str = ""
    transition_type: str = "LOCAL_TO_ONLINE"
    repo_identity: str = ""
    base_sha: str = ""
    inspected_paths: list[str] = field(default_factory=list)
    evidence_refs: list[str] = field(default_factory=list)
    tests_executed: list[str] = field(default_factory=list)
    diff: str = ""
    unknown_effects: list[str] = field(default_factory=list)
    unresolved_questions: list[str] = field(default_factory=list)
    escalation_reason: str = ""
    remaining_gate: str = "ONLINE_REASONING_REQUIRED"
    created_at: str = field(default_factory=utc_now)

    def handoff_hash(self) -> str:
        return sha256_json({
            "task_id": self.task_id,
            "predecessor_attempt_id": self.predecessor_attempt_id,
            "repo_identity": self.repo_identity,
            "base_sha": self.base_sha,
            "inspected_paths": sorted(self.inspected_paths),
            "evidence_refs": sorted(self.evidence_refs),
            "diff": self.diff,
            "escalation_reason": self.escalation_reason,
        })


@dataclass(frozen=True)
class TelemetryRecord:
    """Resource and economics telemetry record."""

    schema: str = M5_LOCAL_TELEMETRY_SCHEMA
    task_family: str = ""
    local_role: str = ""
    host: str = ""
    runtime: str = ""
    model: str = ""
    elapsed_ms: int = 0
    rss_bytes: int = 0
    swap_used_bytes: int = 0
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    context_limit: int = 0
    exit_reason: str = "SUCCESS"
    escalation_occurred: bool = False
    escalation_reason: Optional[str] = None
    repeated_acquisition_avoided: bool = False
    created_at: str = field(default_factory=utc_now)
