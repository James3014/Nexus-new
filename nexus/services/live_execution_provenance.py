"""Transport-neutral live execution provenance service (issue #1266).

Normalizes and joins logical work/attempt identities with physical execution
evidence across DIRECT_CANONICAL (Main GPT direct via Dev MCP), DIRECT_DELEGATED
(RDC worker), GOVERNED (isolated Target worktree), and qualified LOCAL execution.

Boundary: Provenance is read-only observational state. It does NOT route, select
models, acquire/fencing claims (#129), admit physical mutation conflicts (#98),
record Runtime handoff lineage (Runtime#45), verify Core completion, accept candidates,
merge, release, or deploy.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

LIVE_EXECUTION_PROVENANCE_SCHEMA = "nexus.integration.live_execution_provenance.v1"
LIVE_EXECUTION_PROVENANCE_CLAIM_CEILING = "PROVENANCE_READ_ONLY_OBSERVATIONAL"

# Canonical Execution Lanes
EXECUTION_LANE_DIRECT_CANONICAL = "DIRECT_CANONICAL"
EXECUTION_LANE_DIRECT_DELEGATED = "DIRECT_DELEGATED"
EXECUTION_LANE_GOVERNED = "GOVERNED"
EXECUTION_LANE_LOCAL = "LOCAL"
RECOGNIZED_EXECUTION_LANES = frozenset(
    {
        EXECUTION_LANE_DIRECT_CANONICAL,
        EXECUTION_LANE_DIRECT_DELEGATED,
        EXECUTION_LANE_GOVERNED,
        EXECUTION_LANE_LOCAL,
    }
)

# Physical Transport Kinds (Must NOT be used as execution authority lanes)
TRANSPORT_KIND_DEV_MCP = "DEV_MCP"
TRANSPORT_KIND_RDC = "RDC"
TRANSPORT_KIND_ISOLATED_WORKTREE = "ISOLATED_WORKTREE"
TRANSPORT_KIND_LOCAL_RUNNER = "LOCAL_RUNNER"
TRANSPORT_KIND_UNKNOWN = "UNKNOWN"
RECOGNIZED_TRANSPORT_KINDS = frozenset(
    {
        TRANSPORT_KIND_DEV_MCP,
        TRANSPORT_KIND_RDC,
        TRANSPORT_KIND_ISOLATED_WORKTREE,
        TRANSPORT_KIND_LOCAL_RUNNER,
        TRANSPORT_KIND_UNKNOWN,
    }
)

# Normalized Execution States
EXECUTION_STATE_ACTIVE = "ACTIVE"
EXECUTION_STATE_COMPLETED = "COMPLETED"
EXECUTION_STATE_FAILED = "FAILED"
EXECUTION_STATE_UNKNOWN = "UNKNOWN"
EXECUTION_STATE_UNAVAILABLE = "UNAVAILABLE"
EXECUTION_STATE_STALE = "STALE"
EXECUTION_STATE_RECONCILE_REQUIRED = "RECONCILE_REQUIRED"
RECOGNIZED_EXECUTION_STATES = frozenset(
    {
        EXECUTION_STATE_ACTIVE,
        EXECUTION_STATE_COMPLETED,
        EXECUTION_STATE_FAILED,
        EXECUTION_STATE_UNKNOWN,
        EXECUTION_STATE_UNAVAILABLE,
        EXECUTION_STATE_STALE,
        EXECUTION_STATE_RECONCILE_REQUIRED,
    }
)


class ProvenanceContractError(ValueError):
    """Failure to satisfy live execution provenance contract boundaries."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256(data: Any) -> str:
    try:
        raw = json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    except (TypeError, ValueError) as exc:
        raise ProvenanceContractError("payload must be JSON serializable") from exc
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class LiveExecutionProvenance:
    """Normalized, transport-neutral observational execution provenance record."""

    repository: str
    work_contract_id: str
    task_id: str
    attempt_id: str
    execution_lane: str
    transport_kind: str
    operation_id: str
    host_id: str
    requested_worker: str
    requested_provider: str
    requested_model: str
    observed_worker: str
    observed_provider: str
    observed_model: str
    execution_state: str
    phase: str = ""
    session_id: str = ""
    pid: Optional[int] = None
    source_revision: str = ""
    runtime_revision: str = ""
    evidence_refs: tuple[str, ...] = ()
    created_at: str = ""
    observed_at: str = field(default_factory=_utc_now)
    schema: str = LIVE_EXECUTION_PROVENANCE_SCHEMA
    claim_ceiling: str = LIVE_EXECUTION_PROVENANCE_CLAIM_CEILING

    def __post_init__(self) -> None:
        if self.schema != LIVE_EXECUTION_PROVENANCE_SCHEMA:
            raise ProvenanceContractError(f"unsupported schema: {self.schema!r}")
        if self.claim_ceiling != LIVE_EXECUTION_PROVENANCE_CLAIM_CEILING:
            raise ProvenanceContractError(f"unsupported claim ceiling: {self.claim_ceiling!r}")
        if self.execution_lane not in RECOGNIZED_EXECUTION_LANES:
            raise ProvenanceContractError(f"unrecognized execution_lane: {self.execution_lane!r}")
        if self.transport_kind not in RECOGNIZED_TRANSPORT_KINDS:
            raise ProvenanceContractError(f"unrecognized transport_kind: {self.transport_kind!r}")
        # Invariant: execution_lane != transport_kind (no pseudo-authority lanes like 'RDC')
        if self.execution_lane == self.transport_kind:
            raise ProvenanceContractError(
                f"transport kind {self.transport_kind!r} cannot serve as execution authority lane"
            )
        if self.execution_state not in RECOGNIZED_EXECUTION_STATES:
            raise ProvenanceContractError(f"unrecognized execution_state: {self.execution_state!r}")
        if not self.task_id or not isinstance(self.task_id, str):
            raise ProvenanceContractError("task_id must be a non-empty string")
        if not self.attempt_id or not isinstance(self.attempt_id, str):
            raise ProvenanceContractError("attempt_id must be a non-empty string")

    def to_dict(self) -> dict[str, Any]:
        body: dict[str, Any] = {
            "schema": self.schema,
            "claim_ceiling": self.claim_ceiling,
            "repository": self.repository,
            "work_contract_id": self.work_contract_id,
            "task_id": self.task_id,
            "attempt_id": self.attempt_id,
            "execution_lane": self.execution_lane,
            "transport_kind": self.transport_kind,
            "operation_id": self.operation_id,
            "session_id": self.session_id,
            "host_id": self.host_id,
            "pid": self.pid,
            "requested_worker": self.requested_worker,
            "requested_provider": self.requested_provider,
            "requested_model": self.requested_model,
            "observed_worker": self.observed_worker,
            "observed_provider": self.observed_provider,
            "observed_model": self.observed_model,
            "execution_state": self.execution_state,
            "phase": self.phase,
            "source_revision": self.source_revision,
            "runtime_revision": self.runtime_revision,
            "evidence_refs": list(self.evidence_refs),
            "created_at": self.created_at,
            "observed_at": self.observed_at,
        }
        body["provenance_hash"] = _sha256(body)
        return body

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> LiveExecutionProvenance:
        if not isinstance(data, Mapping):
            raise ProvenanceContractError("payload must be a Mapping")
        stored_hash = data.get("provenance_hash")
        inst = cls(
            repository=str(data.get("repository") or ""),
            work_contract_id=str(data.get("work_contract_id") or ""),
            task_id=str(data.get("task_id") or ""),
            attempt_id=str(data.get("attempt_id") or ""),
            execution_lane=str(data.get("execution_lane") or ""),
            transport_kind=str(data.get("transport_kind") or ""),
            operation_id=str(data.get("operation_id") or ""),
            session_id=str(data.get("session_id") or ""),
            host_id=str(data.get("host_id") or ""),
            pid=data.get("pid"),
            requested_worker=str(data.get("requested_worker") or ""),
            requested_provider=str(data.get("requested_provider") or ""),
            requested_model=str(data.get("requested_model") or ""),
            observed_worker=str(data.get("observed_worker") or ""),
            observed_provider=str(data.get("observed_provider") or ""),
            observed_model=str(data.get("observed_model") or ""),
            execution_state=str(data.get("execution_state") or ""),
            phase=str(data.get("phase") or ""),
            source_revision=str(data.get("source_revision") or ""),
            runtime_revision=str(data.get("runtime_revision") or ""),
            evidence_refs=tuple(data.get("evidence_refs") or ()),
            created_at=str(data.get("created_at") or ""),
            observed_at=str(data.get("observed_at") or ""),
            schema=str(data.get("schema") or ""),
            claim_ceiling=str(data.get("claim_ceiling") or ""),
        )
        if stored_hash is not None and inst.provenance_hash != stored_hash:
            raise ProvenanceContractError("provenance_hash mismatch: record has been tampered")
        return inst

    @property
    def provenance_hash(self) -> str:
        return str(self.to_dict()["provenance_hash"])


def build_live_execution_provenance(
    work_context: Mapping[str, Any],
    transport_receipt: Mapping[str, Any] | None = None,
    *,
    observed_transport_kind: str | None = None,
) -> LiveExecutionProvenance:
    """Normalize and join logical work identity with physical execution transport receipt.

    Invariants:
    - Missing transport evidence yields UNAVAILABLE / UNKNOWN state.
    - Requested vs observed fields are never conflated or guessed from each other.
    - execution_lane != transport_kind.
    """
    if not isinstance(work_context, Mapping):
        raise ProvenanceContractError("work_context must be a Mapping")

    repo = str(work_context.get("repository") or work_context.get("repo") or "").strip()
    work_id = str(work_context.get("issue") or work_context.get("work_contract_id") or "").strip()
    task_id = str(work_context.get("task_id") or "").strip()
    attempt_id = str(work_context.get("attempt_id") or "").strip()
    lane = str(work_context.get("execution_lane") or EXECUTION_LANE_DIRECT_CANONICAL).strip()

    req_worker = str(work_context.get("worker_id") or work_context.get("worker") or "").strip()
    req_provider = str(work_context.get("provider") or "").strip()
    req_model = str(work_context.get("model") or "").strip()
    src_rev = str(work_context.get("source_revision") or work_context.get("base_revision") or "").strip()

    # Case 1: missing transport receipt
    if transport_receipt is None or not isinstance(transport_receipt, Mapping):
        transport = observed_transport_kind or TRANSPORT_KIND_UNKNOWN
        if transport == lane:
            raise ProvenanceContractError("transport_kind cannot equal execution_lane")
        return LiveExecutionProvenance(
            repository=repo,
            work_contract_id=work_id,
            task_id=task_id,
            attempt_id=attempt_id,
            execution_lane=lane,
            transport_kind=transport,
            operation_id="",
            host_id="",
            requested_worker=req_worker,
            requested_provider=req_provider,
            requested_model=req_model,
            observed_worker="",
            observed_provider="",
            observed_model="",
            execution_state=EXECUTION_STATE_UNAVAILABLE,
            phase="UNAVAILABLE",
            source_revision=src_rev,
        )

    # Case 2: physical transport receipt available
    rcpt = dict(transport_receipt)
    op_id = str(rcpt.get("operation_id") or "").strip()
    host_id = str(rcpt.get("host_id") or "").strip()
    session_id = str(rcpt.get("provider_session_id") or rcpt.get("session_id") or "").strip()
    pid = rcpt.get("pid") if isinstance(rcpt.get("pid"), int) else None

    # Observed facts must come from receipt, never inferred from requested
    obs_worker = str(rcpt.get("observed_worker") or rcpt.get("worker_id") or "").strip()
    obs_provider = str(rcpt.get("observed_provider") or rcpt.get("provider") or "").strip()
    obs_model = str(rcpt.get("observed_model") or rcpt.get("model") or "").strip()

    rcpt_status = str(rcpt.get("status") or "").upper().strip()
    phase = str(rcpt.get("phase") or rcpt_status).strip()

    transport = observed_transport_kind or str(rcpt.get("transport_kind") or TRANSPORT_KIND_UNKNOWN).strip()
    if transport == lane:
        raise ProvenanceContractError("transport_kind cannot equal execution_lane")

    # Map status to normalized execution state
    if rcpt_status in {"RUNNING", "QUEUED", "WAITING_INPUT"}:
        norm_state = EXECUTION_STATE_ACTIVE
    elif rcpt_status in {"COMPLETED", "SUCCESS"}:
        norm_state = EXECUTION_STATE_COMPLETED
    elif rcpt_status in {"FAILED", "CANCELLED", "ERROR"}:
        norm_state = EXECUTION_STATE_FAILED
    elif rcpt_status in {"STALE", "HEARTBEAT_EXPIRED"}:
        norm_state = EXECUTION_STATE_STALE
    elif rcpt_status in {"RECONCILE", "RECONCILE_REQUIRED"}:
        norm_state = EXECUTION_STATE_RECONCILE_REQUIRED
    else:
        norm_state = EXECUTION_STATE_UNKNOWN

    evidence_refs: list[str] = []
    for ref_key in ("stdout_path", "stderr_path", "log_path", "receipt_path"):
        val = str(rcpt.get(ref_key) or "").strip()
        if val:
            evidence_refs.append(val)

    return LiveExecutionProvenance(
        repository=repo,
        work_contract_id=work_id,
        task_id=task_id,
        attempt_id=attempt_id,
        execution_lane=lane,
        transport_kind=transport,
        operation_id=op_id,
        session_id=session_id,
        host_id=host_id,
        pid=pid,
        requested_worker=req_worker,
        requested_provider=req_provider,
        requested_model=req_model,
        observed_worker=obs_worker,
        observed_provider=obs_provider,
        observed_model=obs_model,
        execution_state=norm_state,
        phase=phase,
        source_revision=src_rev,
        runtime_revision=str(rcpt.get("runtime_revision") or ""),
        evidence_refs=tuple(evidence_refs),
        created_at=str(rcpt.get("created_at") or ""),
    )


class LiveExecutionProvenanceView:
    """Read-only view joining active attempts across physical transports.

    Explicitly lacks authority to:
    - route or select models
    - claim work (#129)
    - authorize mutation (#98)
    - mark completion
    - accept candidates
    - merge or deploy
    """

    def __init__(self) -> None:
        self._records: dict[tuple[str, str], LiveExecutionProvenance] = {}

    def ingest(self, record: LiveExecutionProvenance) -> None:
        if type(record) is not LiveExecutionProvenance:
            raise ProvenanceContractError("record must be a LiveExecutionProvenance")
        key = (record.task_id, record.attempt_id)
        self._records[key] = record

    def get(self, task_id: str, attempt_id: str) -> LiveExecutionProvenance | None:
        return self._records.get((task_id, attempt_id))

    def list_live(
        self,
        *,
        execution_lane: str | None = None,
        transport_kind: str | None = None,
        execution_state: str | None = None,
    ) -> list[LiveExecutionProvenance]:
        matches = []
        for rec in self._records.values():
            if execution_lane and rec.execution_lane != execution_lane:
                continue
            if transport_kind and rec.transport_kind != transport_kind:
                continue
            if execution_state and rec.execution_state != execution_state:
                continue
            matches.append(rec)
        return sorted(matches, key=lambda r: (r.task_id, r.attempt_id))

    def clear_cache(self) -> None:
        """Discard in-memory cache to prove view is purely derived and reconstructable."""
        self._records.clear()

    # Forbidden authority guards: explicitly demonstrate surface cannot route, claim, mutate, etc.
    def route(self, *args, **kwargs):
        raise NotImplementedError("LiveExecutionProvenanceView has no routing authority")

    def select_model(self, *args, **kwargs):
        raise NotImplementedError("LiveExecutionProvenanceView has no model selection authority")

    def acquire_claim(self, *args, **kwargs):
        raise NotImplementedError("LiveExecutionProvenanceView has no claim authority")

    def authorize_mutation(self, *args, **kwargs):
        raise NotImplementedError("LiveExecutionProvenanceView has no mutation authority")

    def mark_completion(self, *args, **kwargs):
        raise NotImplementedError("LiveExecutionProvenanceView has no completion authority")

    def accept_candidate(self, *args, **kwargs):
        raise NotImplementedError("LiveExecutionProvenanceView has no candidate acceptance authority")

    def merge(self, *args, **kwargs):
        raise NotImplementedError("LiveExecutionProvenanceView has no merge authority")

    def deploy(self, *args, **kwargs):
        raise NotImplementedError("LiveExecutionProvenanceView has no deployment authority")
