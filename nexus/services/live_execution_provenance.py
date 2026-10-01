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
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

LIVE_EXECUTION_PROVENANCE_SCHEMA = "nexus.integration.live_execution_provenance.v1"
LIVE_EXECUTION_PROVENANCE_CLAIM_CEILING = "PROVENANCE_READ_ONLY_OBSERVATIONAL"

# Canonical Execution Lanes
EXECUTION_LANE_DIRECT_CANONICAL = "DIRECT_CANONICAL"
EXECUTION_LANE_DIRECT_DELEGATED = "DIRECT_DELEGATED"
EXECUTION_LANE_GOVERNED = "GOVERNED"
EXECUTION_LANE_LOCAL = "LOCAL"
EXECUTION_LANE_UNKNOWN = "UNKNOWN"
RECOGNIZED_EXECUTION_LANES = frozenset(
    {
        EXECUTION_LANE_DIRECT_CANONICAL,
        EXECUTION_LANE_DIRECT_DELEGATED,
        EXECUTION_LANE_GOVERNED,
        EXECUTION_LANE_LOCAL,
        EXECUTION_LANE_UNKNOWN,
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

# Canonical producer schemas that already have repository-owned durable readers.
PRODUCER_SCHEMA_EXTERNAL_WORKER_V1 = "nexus.external_worker_operation.v1"
PRODUCER_SCHEMA_AGY_OPERATION_V1 = "nexus.agy_operation.v1"
TRUSTED_JOURNAL_SCHEMAS = frozenset(
    {
        PRODUCER_SCHEMA_EXTERNAL_WORKER_V1,
        PRODUCER_SCHEMA_AGY_OPERATION_V1,
    }
)

# Declared compatibility/fixture schemas are not producer proof by themselves.
PRODUCER_SCHEMA_OPERATION_V1 = "nexus.operation.v1"
PRODUCER_SCHEMA_DEV_MCP_V1 = "nexus.dev_mcp.receipt.v1"
PRODUCER_SCHEMA_RDC_V1 = "nexus.rdc.receipt.v1"
PRODUCER_SCHEMA_GOVERNED_TARGET_V1 = "nexus.target_ownership.v1"
SUPPORTED_PRODUCER_SCHEMAS = TRUSTED_JOURNAL_SCHEMAS

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
class VerifiedProducerRecord:
    """A record obtained from a repository-owned producer read API."""

    record: Mapping[str, Any]
    source_ref: str
    transport_kind: str

    def __post_init__(self) -> None:
        if not isinstance(self.record, Mapping):
            raise ProvenanceContractError("verified producer record must be a Mapping")
        schema = str(self.record.get("schema") or "")
        if schema not in TRUSTED_JOURNAL_SCHEMAS:
            raise ProvenanceContractError(f"producer schema is not trusted: {schema!r}")
        if self.transport_kind not in RECOGNIZED_TRANSPORT_KINDS:
            raise ProvenanceContractError(f"unrecognized transport_kind: {self.transport_kind!r}")
        if not self.source_ref:
            raise ProvenanceContractError("verified producer source_ref is required")
        object.__setattr__(self, "record", dict(self.record))


def read_operation_journal_evidence(
    journal: Any,
    operation_id: str,
    *,
    transport_kind: str = TRANSPORT_KIND_LOCAL_RUNNER,
) -> VerifiedProducerRecord:
    """Read one exact operation through its owning DirectOperationJournal API."""

    record = journal.read(operation_id)
    schema = str(record.get("schema") or "")
    if schema not in TRUSTED_JOURNAL_SCHEMAS:
        raise ProvenanceContractError(f"producer schema is not trusted: {schema!r}")
    return VerifiedProducerRecord(
        record=record,
        source_ref=f"operation-journal:{schema}:{operation_id}",
        transport_kind=transport_kind,
    )


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
    observed_at: str = ""
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
        if (
            self.execution_lane != EXECUTION_LANE_UNKNOWN
            and self.transport_kind != TRANSPORT_KIND_UNKNOWN
            and self.execution_lane == self.transport_kind
        ):
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


def make_dev_mcp_receipt(
    *,
    operation_id: str,
    session_id: str,
    host_id: str,
    pid: int | None = None,
    status: str = "RUNNING",
    phase: str = "",
    observed_worker: str = "",
    observed_provider: str = "",
    observed_model: str = "",
    timestamp: str | None = None,
    task_id: str = "",
    attempt_id: str = "",
    repository: str = "",
    evidence_refs: Sequence[str] = (),
) -> dict[str, Any]:
    """Produce a canonical Dev MCP execution receipt."""
    return {
        "schema": PRODUCER_SCHEMA_DEV_MCP_V1,
        "transport_kind": TRANSPORT_KIND_DEV_MCP,
        "operation_id": operation_id,
        "session_id": session_id,
        "host_id": host_id,
        "pid": pid,
        "status": status,
        "phase": phase or status,
        "observed_worker": observed_worker,
        "observed_provider": observed_provider,
        "observed_model": observed_model,
        "timestamp": timestamp or _utc_now(),
        "task_id": task_id,
        "attempt_id": attempt_id,
        "repository": repository,
        "evidence_refs": list(evidence_refs),
    }


def make_rdc_receipt(
    *,
    operation_id: str,
    session_id: str = "",
    host_id: str,
    pid: int | None = None,
    status: str = "RUNNING",
    phase: str = "",
    observed_worker: str = "",
    observed_provider: str = "",
    observed_model: str = "",
    timestamp: str | None = None,
    task_id: str = "",
    attempt_id: str = "",
    repository: str = "",
    evidence_refs: Sequence[str] = (),
) -> dict[str, Any]:
    """Produce a canonical RDC delegated worker receipt."""
    return {
        "schema": PRODUCER_SCHEMA_RDC_V1,
        "transport_kind": TRANSPORT_KIND_RDC,
        "operation_id": operation_id,
        "session_id": session_id,
        "host_id": host_id,
        "pid": pid,
        "status": status,
        "phase": phase or status,
        "observed_worker": observed_worker,
        "observed_provider": observed_provider,
        "observed_model": observed_model,
        "timestamp": timestamp or _utc_now(),
        "task_id": task_id,
        "attempt_id": attempt_id,
        "repository": repository,
        "evidence_refs": list(evidence_refs),
    }


def build_live_execution_provenance(
    work_context: Mapping[str, Any],
    transport_receipt: VerifiedProducerRecord | Mapping[str, Any] | None = None,
    *,
    observed_transport_kind: str | None = None,
    max_staleness_seconds: float = 300.0,
) -> LiveExecutionProvenance:
    """Normalize and join logical work identity with physical execution transport receipt.

    Invariants:
    - Missing or unrecognized execution lane fails closed to UNKNOWN/UNAVAILABLE.
    - Arbitrary/unrecognized receipts fail closed to UNKNOWN/REJECTED.
    - Missing transport evidence yields UNAVAILABLE / UNKNOWN state.
    - Requested vs observed fields are strictly isolated; never inferred or copied.
    - execution_lane != transport_kind.
    - Exact cross-binding between work context and receipt.
    - Freshness derived from producer evidence timestamp.
    - ACTIVE/COMPLETED requires physical operation, host, and session/pid identity.
    """
    if not isinstance(work_context, Mapping):
        raise ProvenanceContractError("work_context must be a Mapping")

    repo = str(work_context.get("repository") or work_context.get("repo") or "").strip()
    work_id = str(work_context.get("issue") or work_context.get("work_contract_id") or "").strip()
    task_id = str(work_context.get("task_id") or "").strip()
    attempt_id = str(work_context.get("attempt_id") or "").strip()

    raw_lane = work_context.get("execution_lane")
    lane = str(raw_lane).strip() if raw_lane else ""

    req_worker = str(work_context.get("worker_id") or work_context.get("worker") or "").strip()
    req_provider = str(work_context.get("provider") or "").strip()
    req_model = str(work_context.get("model") or "").strip()
    src_rev = str(work_context.get("source_revision") or work_context.get("base_revision") or "").strip()

    # D1: Missing or unrecognized execution lane must fail closed to UNKNOWN / UNAVAILABLE
    lane_missing = not lane or lane == EXECUTION_LANE_UNKNOWN or lane not in RECOGNIZED_EXECUTION_LANES
    if lane_missing:
        effective_lane = EXECUTION_LANE_UNKNOWN
        effective_state = EXECUTION_STATE_UNKNOWN
        phase = "MISSING_OR_UNRECOGNIZED_EXECUTION_LANE"
    else:
        effective_lane = lane
        effective_state = None
        phase = ""

    # D2: Missing transport receipt
    if transport_receipt is None:
        transport = observed_transport_kind or TRANSPORT_KIND_UNKNOWN
        if effective_lane != EXECUTION_LANE_UNKNOWN and transport == effective_lane:
            raise ProvenanceContractError("transport_kind cannot equal execution_lane")
        return LiveExecutionProvenance(
            repository=repo,
            work_contract_id=work_id,
            task_id=task_id,
            attempt_id=attempt_id,
            execution_lane=effective_lane,
            transport_kind=transport,
            operation_id="",
            host_id="",
            requested_worker=req_worker,
            requested_provider=req_provider,
            requested_model=req_model,
            observed_worker="",
            observed_provider="",
            observed_model="",
            execution_state=effective_state or EXECUTION_STATE_UNAVAILABLE,
            phase=phase or "UNAVAILABLE",
            source_revision=src_rev,
            observed_at="",
        )

    # Raw mappings are observations supplied by the caller, not producer proof.
    if not isinstance(transport_receipt, VerifiedProducerRecord):
        rcpt = dict(transport_receipt) if isinstance(transport_receipt, Mapping) else {}
        declared_transport = str(rcpt.get("transport_kind") or TRANSPORT_KIND_UNKNOWN).strip()
        if declared_transport not in RECOGNIZED_TRANSPORT_KINDS:
            declared_transport = TRANSPORT_KIND_UNKNOWN
        return LiveExecutionProvenance(
            repository=repo,
            work_contract_id=work_id,
            task_id=task_id,
            attempt_id=attempt_id,
            execution_lane=effective_lane,
            transport_kind=declared_transport,
            operation_id=str(rcpt.get("operation_id") or ""),
            host_id=str(rcpt.get("host_id") or ""),
            requested_worker=req_worker,
            requested_provider=req_provider,
            requested_model=req_model,
            observed_worker="",
            observed_provider="",
            observed_model="",
            execution_state=EXECUTION_STATE_UNKNOWN,
            phase="UNVERIFIED_PRODUCER_RECORD",
            source_revision=src_rev,
            observed_at="",
        )

    rcpt = dict(transport_receipt.record)
    transport = transport_receipt.transport_kind
    if observed_transport_kind and observed_transport_kind != transport:
        raise ProvenanceContractError(
            f"observed_transport_kind {observed_transport_kind!r} conflicts with verified producer transport {transport!r}"
        )

    op_id = str(rcpt.get("operation_id") or "").strip()
    host_id = str(rcpt.get("host_id") or "").strip()
    session_id = str(rcpt.get("provider_session_id") or rcpt.get("session_id") or "").strip()
    pid = rcpt.get("pid") if isinstance(rcpt.get("pid"), int) else None

    # D4: Observed facts must come strictly from observed fields, never copied from requested/config
    obs_worker = str(rcpt.get("observed_worker") or "").strip()
    obs_provider = str(rcpt.get("observed_provider") or "").strip()
    obs_model = str(rcpt.get("observed_model") or "").strip()

    rcpt_status = str(rcpt.get("status") or "").upper().strip()
    rcpt_phase = str(rcpt.get("phase") or rcpt_status).strip()

    # Transport kind comes from the verified producer adapter, never the payload.
    if transport not in RECOGNIZED_TRANSPORT_KINDS:
        transport = TRANSPORT_KIND_UNKNOWN

    if effective_lane != EXECUTION_LANE_UNKNOWN and transport == effective_lane:
        raise ProvenanceContractError(
            f"transport kind {transport!r} cannot serve as execution authority lane"
        )

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

    # D3: Exact cross-binding checks. Missing required identity is also a mismatch.
    rcpt_repo = str(rcpt.get("repository") or rcpt.get("repo_root") or "").strip()
    rcpt_task_id = str(rcpt.get("task_id") or "").strip()
    rcpt_attempt_id = str(rcpt.get("attempt_id") or "").strip()
    rcpt_op_id = str(rcpt.get("operation_id") or "").strip()
    work_op_id = str(work_context.get("operation_id") or "").strip()

    missing_bindings = []
    if not repo or not rcpt_repo:
        missing_bindings.append("repository")
    if not task_id or not rcpt_task_id:
        missing_bindings.append("task_id")
    if not attempt_id or not rcpt_attempt_id:
        missing_bindings.append("attempt_id")
    if not work_op_id or not rcpt_op_id:
        missing_bindings.append("operation_id")
    if missing_bindings:
        norm_state = EXECUTION_STATE_UNKNOWN
        rcpt_phase = "MISSING_CROSS_BINDING_IDENTITY: " + ",".join(missing_bindings)
    elif Path(rcpt_repo).name != Path(repo).name and rcpt_repo != repo:
        norm_state = EXECUTION_STATE_UNKNOWN
        rcpt_phase = f"CROSS_BINDING_MISMATCH: repository mismatch ({repo} vs {rcpt_repo})"
    elif rcpt_task_id != task_id:
        norm_state = EXECUTION_STATE_UNKNOWN
        rcpt_phase = f"CROSS_BINDING_MISMATCH: task_id mismatch ({task_id} vs {rcpt_task_id})"
    elif rcpt_attempt_id != attempt_id:
        norm_state = EXECUTION_STATE_UNKNOWN
        rcpt_phase = f"CROSS_BINDING_MISMATCH: attempt_id mismatch ({attempt_id} vs {rcpt_attempt_id})"
    elif work_op_id != rcpt_op_id:
        norm_state = EXECUTION_STATE_UNKNOWN
        rcpt_phase = f"CROSS_BINDING_MISMATCH: operation_id mismatch ({work_op_id} vs {rcpt_op_id})"

    # D6: ACTIVE/COMPLETED requires physical operation and host and (session_id or pid)
    has_physical_identity = bool(op_id and host_id and (session_id or pid is not None))
    if not has_physical_identity and norm_state in {
        EXECUTION_STATE_ACTIVE,
        EXECUTION_STATE_COMPLETED,
    }:
        norm_state = EXECUTION_STATE_UNKNOWN
        rcpt_phase = "UNVERIFIED_PHYSICAL_IDENTITY"

    # D5: Producer timestamp and Freshness
    producer_ts = str(
        rcpt.get("last_heartbeat_at")
        or rcpt.get("last_output_at")
        or rcpt.get("updated_at")
        or rcpt.get("timestamp")
        or rcpt.get("started_at")
        or rcpt.get("created_at")
        or ""
    ).strip()

    if not producer_ts:
        if norm_state in {EXECUTION_STATE_ACTIVE, EXECUTION_STATE_COMPLETED}:
            norm_state = EXECUTION_STATE_UNKNOWN
            rcpt_phase = "MISSING_PRODUCER_TIMESTAMP"
        observed_at = ""
    else:
        observed_at = producer_ts
        if norm_state == EXECUTION_STATE_ACTIVE and max_staleness_seconds > 0:
            try:
                ts_clean = producer_ts.replace("Z", "+00:00")
                dt = datetime.fromisoformat(ts_clean)
                now_dt = datetime.now(timezone.utc)
                diff = (now_dt - dt).total_seconds()
                if diff > max_staleness_seconds:
                    norm_state = EXECUTION_STATE_STALE
                    rcpt_phase = f"HEARTBEAT_EXPIRED: age {int(diff)}s > max {int(max_staleness_seconds)}s"
            except (TypeError, ValueError, OverflowError):
                norm_state = EXECUTION_STATE_UNKNOWN
                rcpt_phase = "INVALID_PRODUCER_TIMESTAMP"
                observed_at = ""

    if effective_state is not None:
        norm_state = effective_state
        rcpt_phase = phase

    evidence_refs: list[str] = [transport_receipt.source_ref]
    for ref_key in ("stdout_path", "stderr_path", "log_path", "receipt_path"):
        val = str(rcpt.get(ref_key) or "").strip()
        if val:
            evidence_refs.append(val)
    if isinstance(rcpt.get("evidence_refs"), (list, tuple)):
        for ref in rcpt["evidence_refs"]:
            if isinstance(ref, str) and ref.strip():
                evidence_refs.append(ref.strip())

    return LiveExecutionProvenance(
        repository=repo,
        work_contract_id=work_id,
        task_id=task_id,
        attempt_id=attempt_id,
        execution_lane=effective_lane,
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
        phase=rcpt_phase,
        source_revision=src_rev,
        runtime_revision=str(rcpt.get("runtime_revision") or ""),
        evidence_refs=tuple(evidence_refs),
        created_at=str(rcpt.get("created_at") or ""),
        observed_at=observed_at,
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
        self._records: dict[tuple[str, str, str], LiveExecutionProvenance] = {}

    def ingest(self, record: LiveExecutionProvenance) -> None:
        if type(record) is not LiveExecutionProvenance:
            raise ProvenanceContractError("record must be a LiveExecutionProvenance")
        key = (record.repository, record.task_id, record.attempt_id)
        self._records[key] = record

    def get(
        self,
        arg1: str,
        arg2: str,
        arg3: str | None = None,
    ) -> LiveExecutionProvenance | None:
        """Query record by (repository, task_id, attempt_id) or (task_id, attempt_id).

        If queried by (task_id, attempt_id) and records exist in multiple repositories,
        raises ProvenanceContractError to prevent cross-repository collisions.
        """
        if arg3 is not None:
            # get(repository, task_id, attempt_id)
            return self._records.get((arg1, arg2, arg3))
        # get(task_id, attempt_id)
        matches = [
            r for r in self._records.values() if r.task_id == arg1 and r.attempt_id == arg2
        ]
        if len(matches) > 1:
            raise ProvenanceContractError(
                f"ambiguous lookup: multiple repositories match task_id={arg1!r}, attempt_id={arg2!r}; repository is required"
            )
        return matches[0] if matches else None

    def list_live(
        self,
        *,
        repository: str | None = None,
        execution_lane: str | None = None,
        transport_kind: str | None = None,
        execution_state: str | None = None,
    ) -> list[LiveExecutionProvenance]:
        matches = []
        for rec in self._records.values():
            if repository and rec.repository != repository:
                continue
            if execution_lane and rec.execution_lane != execution_lane:
                continue
            if transport_kind and rec.transport_kind != transport_kind:
                continue
            if execution_state and rec.execution_state != execution_state:
                continue
            matches.append(rec)
        return sorted(matches, key=lambda r: (r.repository, r.task_id, r.attempt_id))

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
        raise NotImplementedError(
            "LiveExecutionProvenanceView has no candidate acceptance authority"
        )

    def merge(self, *args, **kwargs):
        raise NotImplementedError("LiveExecutionProvenanceView has no merge authority")

    def deploy(self, *args, **kwargs):
        raise NotImplementedError("LiveExecutionProvenanceView has no deployment authority")
