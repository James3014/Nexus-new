"""Transport-neutral operation continuity and reconciliation service (#1350).

Makes durable Nexus logical operations independent of MCP session, connector,
OAuth client, provider, and executor transport.

Invariants:
- Transport identity is evidence, NEVER durable operation ownership (R1, R4).
- Execution transport returns physical facts, NOT authority (R2).
- OUTCOME_UNKNOWN != retry permission remains binding (R3).
- Nexus owns retry / reconcile / stop classification (R3).
- Continuation binds work identity, operation identity, and exact effect evidence (R5).
- Candidate / verification / acceptance / merge authorities remain strictly separate.
- Reuses existing Runtime and #1266 / #98 journal surfaces; no second durable store.
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from nexus.services.direct_operation_journal import (
    ACTIVE_STATES,
    DirectOperationJournal,
    _process_alive,
)
from nexus.services.live_execution_provenance import (
    EXECUTION_LANE_UNKNOWN,
    PRODUCER_SCHEMA_DEV_MCP_V1,
    RECOGNIZED_EXECUTION_LANES,
    RECOGNIZED_TRANSPORT_KINDS,
    TRANSPORT_KIND_DEV_MCP,
    TRANSPORT_KIND_UNKNOWN,
    VerifiedProducerRecord,
    read_operation_journal_evidence,
)

OPERATION_CONTINUITY_SCHEMA = "nexus.operation_continuity.v1"
OPERATION_CONTINUITY_CLAIM_CEILING = "NEXUS_TRANSPORT_NEUTRAL_OPERATION_CONTINUITY_SOURCE_VERIFIED"

# Canonical Continuity Dispositions
DISPOSITION_CONTINUE = "CONTINUE"
DISPOSITION_RECONCILE = "RECONCILE"
DISPOSITION_STOP = "STOP"
DISPOSITION_BLOCKED = "BLOCKED"
RECOGNIZED_DISPOSITIONS = frozenset({
    DISPOSITION_CONTINUE,
    DISPOSITION_RECONCILE,
    DISPOSITION_STOP,
    DISPOSITION_BLOCKED,
})

# Canonical Effect Kinds
EFFECT_KIND_READ_ONLY = "READ_ONLY"
EFFECT_KIND_LOCAL_MUTATION = "LOCAL_MUTATION"
EFFECT_KIND_GIT_COMMIT = "GIT_COMMIT"
EFFECT_KIND_EXTERNAL_PUBLICATION = "EXTERNAL_PUBLICATION"
RECOGNIZED_EFFECT_KINDS = frozenset({
    EFFECT_KIND_READ_ONLY,
    EFFECT_KIND_LOCAL_MUTATION,
    EFFECT_KIND_GIT_COMMIT,
    EFFECT_KIND_EXTERNAL_PUBLICATION,
})

_SHA40 = re.compile(r"^[0-9a-f]{40}$")


class ContinuityError(RuntimeError):
    """Base exception for operation continuity failures."""


class ContinuityContractViolation(ContinuityError):
    """Operation contract or cross-binding boundary violation."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _repo_matches(repo_a: str, repo_b: str) -> bool:
    val_a = str(repo_a or "").strip().rstrip("/")
    val_b = str(repo_b or "").strip().rstrip("/")
    if not val_a or not val_b:
        return False
    if val_a == val_b:
        return True
    try:
        path_a = Path(val_a).expanduser().resolve()
        path_b = Path(val_b).expanduser().resolve()
        return path_a == path_b or path_b in path_a.parents or path_a in path_b.parents
    except Exception:
        return False


@dataclass(frozen=True)
class TransportEvidence:
    """Observational transport facts only. Never operation ownership (R2, R4)."""

    transport_kind: str
    connector_session_id: str = ""  # ChatGPT conversation_id or MCP session id
    client_id: str = ""  # OAuth client id or tool caller id
    host_id: str = ""
    pid: int | None = None
    observed_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "transport_kind": self.transport_kind,
            "connector_session_id": self.connector_session_id,
            "client_id": self.client_id,
            "host_id": self.host_id,
            "pid": self.pid,
            "observed_at": self.observed_at,
        }


@dataclass(frozen=True)
class LogicalOperation:
    """Durable Nexus logical operation independent of transport (R1, R4)."""

    operation_id: str
    attempt_id: str
    repository: str
    work_contract_id: str  # task_id, issue number, or goal identity
    execution_lane: str  # DIRECT_CANONICAL, DIRECT_DELEGATED, GOVERNED, LOCAL
    expected_base_head: str | None = None
    expected_paths: tuple[str, ...] = ()
    effect_kind: str = EFFECT_KIND_LOCAL_MUTATION
    created_at: str = ""
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.operation_id or not self.operation_id.strip():
            raise ContinuityContractViolation("LogicalOperation requires non-empty operation_id")
        if not self.attempt_id or not self.attempt_id.strip():
            raise ContinuityContractViolation("LogicalOperation requires non-empty attempt_id")
        if not self.repository or not self.repository.strip():
            raise ContinuityContractViolation("LogicalOperation requires non-empty repository")
        if not self.work_contract_id or not self.work_contract_id.strip():
            raise ContinuityContractViolation(
                "LogicalOperation requires non-empty work_contract_id"
            )
        lane = self.execution_lane.strip() if self.execution_lane else ""
        if lane not in RECOGNIZED_EXECUTION_LANES or lane == EXECUTION_LANE_UNKNOWN:
            raise ContinuityContractViolation(
                f"unrecognized or missing execution_lane: {self.execution_lane!r}"
            )
        if self.effect_kind not in RECOGNIZED_EFFECT_KINDS:
            raise ContinuityContractViolation(f"unrecognized effect_kind: {self.effect_kind!r}")
        if self.expected_base_head and not _SHA40.fullmatch(self.expected_base_head):
            raise ContinuityContractViolation(
                f"expected_base_head must be 40-character lowercase hex: {self.expected_base_head!r}"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "operation_id": self.operation_id,
            "attempt_id": self.attempt_id,
            "repository": self.repository,
            "work_contract_id": self.work_contract_id,
            "execution_lane": self.execution_lane,
            "expected_base_head": self.expected_base_head,
            "expected_paths": list(self.expected_paths),
            "effect_kind": self.effect_kind,
            "created_at": self.created_at,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class PhysicalExecutionReceipt:
    """Physical facts returned by execution layer (R2)."""

    transport_kind: str
    operation_id: str
    attempt_id: str = ""
    repository: str = ""
    status: str = ""  # RUNNING, COMPLETED, FAILED, OUTCOME_UNKNOWN
    phase: str = ""
    exit_code: int | None = None
    base_head: str | None = None
    current_head: str | None = None
    observed_changed_paths: tuple[str, ...] = ()
    has_unresolved_external_effect: bool = False
    transport_evidence: TransportEvidence = field(
        default_factory=lambda: TransportEvidence(transport_kind=TRANSPORT_KIND_UNKNOWN)
    )
    command_stdout: str = ""
    command_stderr: str = ""
    schema: str = ""
    raw_payload: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "transport_kind": self.transport_kind,
            "operation_id": self.operation_id,
            "attempt_id": self.attempt_id,
            "repository": self.repository,
            "status": self.status,
            "phase": self.phase,
            "exit_code": self.exit_code,
            "base_head": self.base_head,
            "current_head": self.current_head,
            "observed_changed_paths": list(self.observed_changed_paths),
            "has_unresolved_external_effect": self.has_unresolved_external_effect,
            "transport_evidence": self.transport_evidence.to_dict(),
            "command_stdout": self.command_stdout,
            "command_stderr": self.command_stderr,
            "raw_payload": dict(self.raw_payload),
        }


@dataclass(frozen=True)
class ContinuityDecision:
    """Durable Nexus decision on whether to continue, reconcile, or stop (R3)."""

    schema: str
    claim_ceiling: str
    operation_id: str
    attempt_id: str
    repository: str
    execution_lane: str
    transport_kind: str
    disposition: str  # CONTINUE, RECONCILE, STOP, BLOCKED
    retry_permitted: bool  # STRICT: False by default; OUTCOME_UNKNOWN != retry permission
    terminal: bool
    reason: str
    details: Mapping[str, Any]
    evaluated_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "claim_ceiling": self.claim_ceiling,
            "operation_id": self.operation_id,
            "attempt_id": self.attempt_id,
            "repository": self.repository,
            "execution_lane": self.execution_lane,
            "transport_kind": self.transport_kind,
            "disposition": self.disposition,
            "retry_permitted": self.retry_permitted,
            "terminal": self.terminal,
            "reason": self.reason,
            "details": dict(self.details),
            "evaluated_at": self.evaluated_at,
        }


def build_devspace_execution_receipt(
    tool_output: Mapping[str, Any],
    *,
    operation_id: str,
    attempt_id: str = "",
    repository: str = "",
    conversation_id: str = "",
    client_id: str = "",
    host_id: str = "",
    base_head: str | None = None,
) -> PhysicalExecutionReceipt:
    """Build a PhysicalExecutionReceipt from a DevSpace execution tool response.

    Direct Coding in DevSpace produces plain tool outputs (exitCode, stdout,
    commitSha, pushedSha, etc.) without an ambient Core mutation session.
    """
    data = dict(tool_output)
    exit_code = data.get("exitCode")
    if exit_code is None and "exit_code" in data:
        exit_code = data.get("exit_code")

    commit_sha = data.get("commitSha") or data.get("commit_sha") or data.get("current_head")
    pushed_sha = data.get("pushedSha") or data.get("pushed_sha")
    is_error = bool(data.get("isError") or data.get("error"))

    if is_error:
        status = "FAILED"
        phase = "TOOL_ERROR"
    elif data.get("created") or commit_sha:
        status = "COMPLETED"
        phase = "GIT_COMMIT_CREATED"
    elif data.get("pushed") or pushed_sha:
        status = "COMPLETED"
        phase = "GIT_PUSHED"
    elif exit_code is not None:
        status = "COMPLETED" if exit_code == 0 else "FAILED"
        phase = "PROCESS_TERMINATED"
    else:
        status = "COMPLETED"
        phase = "TOOL_SUCCESS"

    has_unresolved_external = bool(
        data.get("has_unresolved_external_effect") or data.get("unresolved_external_effect")
    )
    changed = data.get("paths") or data.get("observed_changed_paths") or ()

    return PhysicalExecutionReceipt(
        schema=PRODUCER_SCHEMA_DEV_MCP_V1,
        transport_kind=TRANSPORT_KIND_DEV_MCP,
        operation_id=operation_id,
        attempt_id=attempt_id,
        repository=repository,
        status=status,
        phase=phase,
        exit_code=exit_code if isinstance(exit_code, int) else None,
        base_head=base_head or data.get("expectedHead"),
        current_head=commit_sha or pushed_sha,
        observed_changed_paths=tuple(str(p) for p in changed),
        has_unresolved_external_effect=has_unresolved_external,
        transport_evidence=TransportEvidence(
            transport_kind=TRANSPORT_KIND_DEV_MCP,
            connector_session_id=str(conversation_id or data.get("conversationId") or ""),
            client_id=str(client_id or data.get("clientId") or ""),
            host_id=str(host_id or ""),
            observed_at=_utc_now(),
        ),
        command_stdout=str(data.get("stdout") or ""),
        command_stderr=str(data.get("stderr") or ""),
        raw_payload=data,
    )


def evaluate_operation_continuity(
    operation: LogicalOperation,
    receipt: PhysicalExecutionReceipt | VerifiedProducerRecord | Mapping[str, Any],
    *,
    max_staleness_seconds: float = 120.0,
    now_ts: float | None = None,
) -> ContinuityDecision:
    """Evaluate durable Nexus operation continuity over transport-neutral execution facts.

    Invariants strictly enforced:
    1. Operation identity survives transport replacement (R1, R4).
    2. Transport identity appears only as evidence, never durable operation ownership (R4).
    3. Execution transport returns facts, not authority (R2).
    4. Missing or tampered operation/effect identity fails closed to BLOCKED (R5).
    5. OUTCOME_UNKNOWN != retry permission (R3).
    6. Unresolved external effects require reconciliation and cannot be blindly replayed (R5).
    7. Terminal synchronous local effects are recognized directly without transport-owner choreography (AC 6).
    """
    now = _utc_now()
    now_time = now_ts if now_ts is not None else datetime.now(timezone.utc).timestamp()

    # 1. Normalize receipt into PhysicalExecutionReceipt
    if isinstance(receipt, VerifiedProducerRecord):
        rec = dict(receipt.record)
        transport_kind = receipt.transport_kind
        status = str(rec.get("status") or "").upper().strip()
        phase = str(rec.get("phase") or status).strip()
        exit_code = rec.get("exit_code") if isinstance(rec.get("exit_code"), int) else None
        base_head = rec.get("base_head")
        current_head = rec.get("current_head") or rec.get("candidate_head")
        changed = rec.get("observed_changed_paths") or ()
        session_id = str(rec.get("provider_session_id") or rec.get("session_id") or "")
        client_id = str(rec.get("account_alias_hash") or rec.get("client_id") or "")
        host_id = str(rec.get("host_id") or "")
        pid = rec.get("pid") if isinstance(rec.get("pid"), int) else None
        obs_at = str(rec.get("last_heartbeat_at") or rec.get("created_at") or "")
        norm_receipt = PhysicalExecutionReceipt(
            schema=str(rec.get("schema") or ""),
            transport_kind=transport_kind,
            operation_id=str(rec.get("operation_id") or ""),
            attempt_id=str(rec.get("attempt_id") or ""),
            repository=str(rec.get("repo_root") or rec.get("repository") or ""),
            status=status,
            phase=phase,
            exit_code=exit_code,
            base_head=base_head,
            current_head=current_head,
            observed_changed_paths=tuple(str(p) for p in changed),
            has_unresolved_external_effect=bool(rec.get("has_unresolved_external_effect", False)),
            transport_evidence=TransportEvidence(
                transport_kind=transport_kind,
                connector_session_id=session_id,
                client_id=client_id,
                host_id=host_id,
                pid=pid,
                observed_at=obs_at,
            ),
            raw_payload=rec,
        )
    elif isinstance(receipt, PhysicalExecutionReceipt):
        norm_receipt = receipt
    elif isinstance(receipt, Mapping):
        data = dict(receipt)
        t_kind = str(data.get("transport_kind") or TRANSPORT_KIND_UNKNOWN).strip()
        evidence_dict = data.get("transport_evidence")
        if isinstance(evidence_dict, Mapping):
            tev = TransportEvidence(
                transport_kind=str(evidence_dict.get("transport_kind") or t_kind),
                connector_session_id=str(evidence_dict.get("connector_session_id") or ""),
                client_id=str(evidence_dict.get("client_id") or ""),
                host_id=str(evidence_dict.get("host_id") or ""),
                pid=evidence_dict.get("pid") if isinstance(evidence_dict.get("pid"), int) else None,
                observed_at=str(evidence_dict.get("observed_at") or ""),
            )
        else:
            tev = TransportEvidence(
                transport_kind=t_kind,
                connector_session_id=str(
                    data.get("connector_session_id") or data.get("conversation_id") or ""
                ),
                client_id=str(data.get("client_id") or ""),
                host_id=str(data.get("host_id") or ""),
                pid=data.get("pid") if isinstance(data.get("pid"), int) else None,
                observed_at=str(data.get("observed_at") or data.get("timestamp") or ""),
            )
        changed = data.get("observed_changed_paths") or data.get("paths") or ()
        norm_receipt = PhysicalExecutionReceipt(
            schema=str(data.get("schema") or ""),
            transport_kind=t_kind,
            operation_id=str(data.get("operation_id") or ""),
            attempt_id=str(data.get("attempt_id") or ""),
            repository=str(data.get("repository") or data.get("repo_root") or ""),
            status=str(data.get("status") or "").upper().strip(),
            phase=str(data.get("phase") or "").strip(),
            exit_code=data.get("exit_code") if isinstance(data.get("exit_code"), int) else None,
            base_head=data.get("base_head") or data.get("expectedHead"),
            current_head=data.get("current_head") or data.get("commitSha"),
            observed_changed_paths=tuple(str(p) for p in changed),
            has_unresolved_external_effect=bool(data.get("has_unresolved_external_effect", False)),
            transport_evidence=tev,
            command_stdout=str(data.get("stdout") or data.get("command_stdout") or ""),
            command_stderr=str(data.get("stderr") or data.get("command_stderr") or ""),
            raw_payload=data,
        )
    else:
        raise ContinuityContractViolation("receipt must be PhysicalExecutionReceipt or Mapping")

    transport = norm_receipt.transport_kind
    if transport not in RECOGNIZED_TRANSPORT_KINDS:
        transport = TRANSPORT_KIND_UNKNOWN

    # 2. Strict Boundary: transport_kind cannot equal execution_lane (R2)
    if operation.execution_lane != EXECUTION_LANE_UNKNOWN and transport == operation.execution_lane:
        return ContinuityDecision(
            schema=OPERATION_CONTINUITY_SCHEMA,
            claim_ceiling=OPERATION_CONTINUITY_CLAIM_CEILING,
            operation_id=operation.operation_id,
            attempt_id=operation.attempt_id,
            repository=operation.repository,
            execution_lane=operation.execution_lane,
            transport_kind=transport,
            disposition=DISPOSITION_BLOCKED,
            retry_permitted=False,
            terminal=True,
            reason="TRANSPORT_KIND_CANNOT_SERVE_AS_EXECUTION_LANE",
            details={
                "error": f"transport kind {transport!r} cannot serve as execution authority lane"
            },
            evaluated_at=now,
        )

    # 3. Cross-Binding Integrity Checks (R5)
    # Operation ID must match exactly; missing/tampered fails closed
    if not norm_receipt.operation_id or norm_receipt.operation_id != operation.operation_id:
        return ContinuityDecision(
            schema=OPERATION_CONTINUITY_SCHEMA,
            claim_ceiling=OPERATION_CONTINUITY_CLAIM_CEILING,
            operation_id=operation.operation_id,
            attempt_id=operation.attempt_id,
            repository=operation.repository,
            execution_lane=operation.execution_lane,
            transport_kind=transport,
            disposition=DISPOSITION_BLOCKED,
            retry_permitted=False,
            terminal=True,
            reason="CROSS_BINDING_MISMATCH: operation_id mismatch",
            details={
                "expected_operation_id": operation.operation_id,
                "observed_operation_id": norm_receipt.operation_id,
            },
            evaluated_at=now,
        )

    # Repository must match
    if norm_receipt.repository and not _repo_matches(norm_receipt.repository, operation.repository):
        return ContinuityDecision(
            schema=OPERATION_CONTINUITY_SCHEMA,
            claim_ceiling=OPERATION_CONTINUITY_CLAIM_CEILING,
            operation_id=operation.operation_id,
            attempt_id=operation.attempt_id,
            repository=operation.repository,
            execution_lane=operation.execution_lane,
            transport_kind=transport,
            disposition=DISPOSITION_BLOCKED,
            retry_permitted=False,
            terminal=True,
            reason=f"CROSS_BINDING_MISMATCH: repository mismatch ({operation.repository} vs {norm_receipt.repository})",
            details={
                "expected_repository": operation.repository,
                "observed_repository": norm_receipt.repository,
            },
            evaluated_at=now,
        )

    # Attempt ID must match if both present
    if (
        norm_receipt.attempt_id
        and operation.attempt_id
        and norm_receipt.attempt_id != operation.attempt_id
    ):
        return ContinuityDecision(
            schema=OPERATION_CONTINUITY_SCHEMA,
            claim_ceiling=OPERATION_CONTINUITY_CLAIM_CEILING,
            operation_id=operation.operation_id,
            attempt_id=operation.attempt_id,
            repository=operation.repository,
            execution_lane=operation.execution_lane,
            transport_kind=transport,
            disposition=DISPOSITION_BLOCKED,
            retry_permitted=False,
            terminal=True,
            reason="CROSS_BINDING_MISMATCH: attempt_id mismatch",
            details={
                "expected_attempt_id": operation.attempt_id,
                "observed_attempt_id": norm_receipt.attempt_id,
            },
            evaluated_at=now,
        )

    # Base head must match if both present
    if (
        norm_receipt.base_head
        and operation.expected_base_head
        and norm_receipt.base_head != operation.expected_base_head
    ):
        return ContinuityDecision(
            schema=OPERATION_CONTINUITY_SCHEMA,
            claim_ceiling=OPERATION_CONTINUITY_CLAIM_CEILING,
            operation_id=operation.operation_id,
            attempt_id=operation.attempt_id,
            repository=operation.repository,
            execution_lane=operation.execution_lane,
            transport_kind=transport,
            disposition=DISPOSITION_BLOCKED,
            retry_permitted=False,
            terminal=True,
            reason="CROSS_BINDING_MISMATCH: base_head mismatch",
            details={
                "expected_base_head": operation.expected_base_head,
                "observed_base_head": norm_receipt.base_head,
            },
            evaluated_at=now,
        )

    # Record transport evidence as observations only (R4)
    details: dict[str, Any] = {
        "transport_evidence": norm_receipt.transport_evidence.to_dict(),
        "observed_phase": norm_receipt.phase,
    }

    # 4. Scope and Changed Paths Containment (if paths are specified)
    if operation.expected_paths and norm_receipt.observed_changed_paths:
        allowed_set = {p.strip().lstrip("/") for p in operation.expected_paths if p.strip()}
        escaped = [
            p
            for p in norm_receipt.observed_changed_paths
            if p.strip().lstrip("/") not in allowed_set
        ]
        if escaped:
            return ContinuityDecision(
                schema=OPERATION_CONTINUITY_SCHEMA,
                claim_ceiling=OPERATION_CONTINUITY_CLAIM_CEILING,
                operation_id=operation.operation_id,
                attempt_id=operation.attempt_id,
                repository=operation.repository,
                execution_lane=operation.execution_lane,
                transport_kind=transport,
                disposition=DISPOSITION_BLOCKED,
                retry_permitted=False,
                terminal=True,
                reason="MUTATION_OUTSIDE_ALLOWED_PATHS",
                details={
                    "escaped_paths": escaped,
                    "allowed_paths": list(operation.expected_paths),
                },
                evaluated_at=now,
            )

    # 5. Disposition Evaluation (R2, R3, R5)
    # Check A: Unresolved external effect (R5, AC 5)
    if norm_receipt.has_unresolved_external_effect:
        details["unresolved_external_effect"] = True
        return ContinuityDecision(
            schema=OPERATION_CONTINUITY_SCHEMA,
            claim_ceiling=OPERATION_CONTINUITY_CLAIM_CEILING,
            operation_id=operation.operation_id,
            attempt_id=operation.attempt_id,
            repository=operation.repository,
            execution_lane=operation.execution_lane,
            transport_kind=transport,
            disposition=DISPOSITION_RECONCILE,
            retry_permitted=False,  # BLIND REPLAY FORBIDDEN!
            terminal=False,
            reason="UNRESOLVED_EXTERNAL_EFFECT_REQUIRES_RECONCILIATION",
            details=details,
            evaluated_at=now,
        )

    # Check B: Outcome Unknown (R3: OUTCOME_UNKNOWN != retry permission)
    if norm_receipt.status in {"OUTCOME_UNKNOWN", "UNKNOWN"}:
        details["outcome_unknown"] = True
        return ContinuityDecision(
            schema=OPERATION_CONTINUITY_SCHEMA,
            claim_ceiling=OPERATION_CONTINUITY_CLAIM_CEILING,
            operation_id=operation.operation_id,
            attempt_id=operation.attempt_id,
            repository=operation.repository,
            execution_lane=operation.execution_lane,
            transport_kind=transport,
            disposition=DISPOSITION_RECONCILE,
            retry_permitted=False,  # OUTCOME_UNKNOWN != retry permission
            terminal=False,
            reason="OUTCOME_UNKNOWN_REQUIRES_RECONCILIATION",
            details=details,
            evaluated_at=now,
        )

    # Check C: Terminal success (COMPLETED / SUCCESS) (AC 6)
    if norm_receipt.status in {"COMPLETED", "SUCCESS"}:
        # For GIT_COMMIT effect, verify current_head is valid SHA-40
        if operation.effect_kind == EFFECT_KIND_GIT_COMMIT:
            if not norm_receipt.current_head or not _SHA40.fullmatch(norm_receipt.current_head):
                return ContinuityDecision(
                    schema=OPERATION_CONTINUITY_SCHEMA,
                    claim_ceiling=OPERATION_CONTINUITY_CLAIM_CEILING,
                    operation_id=operation.operation_id,
                    attempt_id=operation.attempt_id,
                    repository=operation.repository,
                    execution_lane=operation.execution_lane,
                    transport_kind=transport,
                    disposition=DISPOSITION_RECONCILE,
                    retry_permitted=False,
                    terminal=False,
                    reason="COMMIT_EFFECT_MISSING_HEAD_HASH",
                    details=details,
                    evaluated_at=now,
                )
            details["candidate_commit_sha"] = norm_receipt.current_head

        details["exit_code"] = norm_receipt.exit_code
        details["observed_changed_paths"] = list(norm_receipt.observed_changed_paths)
        return ContinuityDecision(
            schema=OPERATION_CONTINUITY_SCHEMA,
            claim_ceiling=OPERATION_CONTINUITY_CLAIM_CEILING,
            operation_id=operation.operation_id,
            attempt_id=operation.attempt_id,
            repository=operation.repository,
            execution_lane=operation.execution_lane,
            transport_kind=transport,
            disposition=DISPOSITION_STOP,
            retry_permitted=False,
            terminal=True,
            reason="TERMINAL_LOCAL_EFFECT_COMPLETED",
            details=details,
            evaluated_at=now,
        )

    # Check D: Terminal failure (FAILED / ERROR / CANCELLED)
    if norm_receipt.status in {"FAILED", "ERROR", "CANCELLED"}:
        details["exit_code"] = norm_receipt.exit_code
        return ContinuityDecision(
            schema=OPERATION_CONTINUITY_SCHEMA,
            claim_ceiling=OPERATION_CONTINUITY_CLAIM_CEILING,
            operation_id=operation.operation_id,
            attempt_id=operation.attempt_id,
            repository=operation.repository,
            execution_lane=operation.execution_lane,
            transport_kind=transport,
            disposition=DISPOSITION_STOP,
            retry_permitted=False,  # No automatic retry
            terminal=True,
            reason=f"TERMINAL_{norm_receipt.status}",
            details=details,
            evaluated_at=now,
        )

    # Check E: Active states (RUNNING / QUEUED / WAITING_INPUT)
    if norm_receipt.status in ACTIVE_STATES or norm_receipt.status == "RUNNING":
        # Check staleness
        heartbeat_str = (
            norm_receipt.transport_evidence.observed_at
            or str(norm_receipt.raw_payload.get("last_heartbeat_at") or "")
            or str(norm_receipt.raw_payload.get("created_at") or "")
        ).strip()

        stale = False
        heartbeat_age: float | None = None
        if heartbeat_str:
            try:
                hb_clean = heartbeat_str.replace("Z", "+00:00")
                hb_dt = datetime.fromisoformat(hb_clean)
                heartbeat_age = max(0.0, now_time - hb_dt.timestamp())
                if (
                    isinstance(max_staleness_seconds, (int, float))
                    and math.isfinite(float(max_staleness_seconds))
                    and float(max_staleness_seconds) > 0
                ):
                    stale = heartbeat_age > float(max_staleness_seconds)
            except Exception:
                stale = True
        else:
            stale = True

        details["heartbeat_age_seconds"] = heartbeat_age

        # Check process liveness if local pid is available
        pid = norm_receipt.transport_evidence.pid
        if pid is not None and not _process_alive(pid):
            details["pid_alive"] = False
            return ContinuityDecision(
                schema=OPERATION_CONTINUITY_SCHEMA,
                claim_ceiling=OPERATION_CONTINUITY_CLAIM_CEILING,
                operation_id=operation.operation_id,
                attempt_id=operation.attempt_id,
                repository=operation.repository,
                execution_lane=operation.execution_lane,
                transport_kind=transport,
                disposition=DISPOSITION_RECONCILE,
                retry_permitted=False,
                terminal=False,
                reason="PROCESS_NOT_RUNNING_WITHOUT_TERMINAL_RECEIPT",
                details=details,
                evaluated_at=now,
            )

        if stale:
            return ContinuityDecision(
                schema=OPERATION_CONTINUITY_SCHEMA,
                claim_ceiling=OPERATION_CONTINUITY_CLAIM_CEILING,
                operation_id=operation.operation_id,
                attempt_id=operation.attempt_id,
                repository=operation.repository,
                execution_lane=operation.execution_lane,
                transport_kind=transport,
                disposition=DISPOSITION_RECONCILE,
                retry_permitted=False,
                terminal=False,
                reason="ACTIVE_STALE_HEARTBEAT",
                details=details,
                evaluated_at=now,
            )

        return ContinuityDecision(
            schema=OPERATION_CONTINUITY_SCHEMA,
            claim_ceiling=OPERATION_CONTINUITY_CLAIM_CEILING,
            operation_id=operation.operation_id,
            attempt_id=operation.attempt_id,
            repository=operation.repository,
            execution_lane=operation.execution_lane,
            transport_kind=transport,
            disposition=DISPOSITION_CONTINUE,
            retry_permitted=False,
            terminal=False,
            reason="ACTIVE_IN_PROGRESS",
            details=details,
            evaluated_at=now,
        )

    # Fall-through: unrecognized state fails closed to RECONCILE
    return ContinuityDecision(
        schema=OPERATION_CONTINUITY_SCHEMA,
        claim_ceiling=OPERATION_CONTINUITY_CLAIM_CEILING,
        operation_id=operation.operation_id,
        attempt_id=operation.attempt_id,
        repository=operation.repository,
        execution_lane=operation.execution_lane,
        transport_kind=transport,
        disposition=DISPOSITION_RECONCILE,
        retry_permitted=False,
        terminal=False,
        reason=f"UNRECOGNIZED_RECEIPT_STATUS: {norm_receipt.status!r}",
        details=details,
        evaluated_at=now,
    )


def reconcile_journal_operation(
    journal: DirectOperationJournal,
    operation: LogicalOperation,
    *,
    transport_kind: str | None = None,
    heartbeat_stale_seconds: float = 120.0,
    now_ts: float | None = None,
) -> tuple[dict[str, Any], ContinuityDecision]:
    """Reconcile one durable operation using existing journal primitives without a second store."""
    reconciled_record = journal.reconcile(
        operation.operation_id,
        heartbeat_stale_seconds=heartbeat_stale_seconds,
    )
    evidence = read_operation_journal_evidence(
        journal,
        operation.operation_id,
        transport_kind=transport_kind,
    )
    decision = evaluate_operation_continuity(
        operation,
        evidence,
        max_staleness_seconds=heartbeat_stale_seconds,
        now_ts=now_ts,
    )
    return reconciled_record, decision


__all__ = (
    "DISPOSITION_BLOCKED",
    "DISPOSITION_CONTINUE",
    "DISPOSITION_RECONCILE",
    "DISPOSITION_STOP",
    "EFFECT_KIND_EXTERNAL_PUBLICATION",
    "EFFECT_KIND_GIT_COMMIT",
    "EFFECT_KIND_LOCAL_MUTATION",
    "EFFECT_KIND_READ_ONLY",
    "OPERATION_CONTINUITY_CLAIM_CEILING",
    "OPERATION_CONTINUITY_SCHEMA",
    "RECOGNIZED_DISPOSITIONS",
    "RECOGNIZED_EFFECT_KINDS",
    "ContinuityContractViolation",
    "ContinuityDecision",
    "ContinuityError",
    "LogicalOperation",
    "PhysicalExecutionReceipt",
    "TransportEvidence",
    "build_devspace_execution_receipt",
    "evaluate_operation_continuity",
    "reconcile_journal_operation",
)
