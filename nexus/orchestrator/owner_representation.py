"""Canonical Owner-representation publication seam.

This module is the single smallest canonical authorization commitment point for
external publication / Owner representation.  It consumes the pure policy
contracts in ``nexus/contracts/owner_representation.py`` and adds:

* fail-closed destination/effect classification,
* store-backed one-shot grant binding: the published grant must exist as a
  durable receipt in the canonical :class:`OwnerRepresentationGrantStore`
  (a worker/agent cannot make self-minted grant objects authoritative), with
  fresh revalidation of live revocation/supersession immediately before any
  effect,
* a durable per-operation state machine mirroring the proven EIA publication
  pattern (PREPARED -> DISPATCHING -> COMPLETED / OUTCOME_UNKNOWN), with
  readback reconciliation and a consumed-grant ledger that forbids replay,
* a single-writer flock around the send critical section so two concurrent
  dispatches of the same operation/grant resolve to exactly one winner.

No real third-party transport is ever invoked here; ``write_transport`` and
``readback_transport`` are injected callables, which keeps the seam testable
with fixtures/mocks and physically incapable of reaching a live external repo
on its own.
"""

from __future__ import annotations

import errno
import fcntl
import json
import os
import stat
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

from nexus.contracts.autonomy_goal import canonical_autonomy_hash
from nexus.contracts.owner_representation import (
    ExternalDestination,
    ExternalDestinationKind,
    ExternalPublicationEffect,
    ExternalPublicationProposal,
    InternalCollaborationBound,
    OwnerRepresentationBlocked,
    OwnerRepresentationDecision,
    OwnerRepresentationGrant,
    OwnerRepresentationOutcome,
    OwnerRepresentationReason,
    PublicationDerivation,
    classification,
    evaluate_owner_representation,
)
from nexus.orchestrator.owner_representation_store import (
    OwnerRepresentationGrantStore,
    OwnerRepresentationGrantStoreError,
)


class WriteOutcome:
    """Result of one physical external write (from an injected transport)."""

    __slots__ = ("status", "remote_marker", "detail")

    def __init__(self, status: str, remote_marker: str | None = None, detail: str = ""):
        self.status = status  # "ACK" | "OUTCOME_UNKNOWN" | "FAILED"
        self.remote_marker = remote_marker
        self.detail = detail

    def as_dict(self) -> Mapping[str, Any]:
        return {
            "status": self.status,
            "remote_marker": self.remote_marker,
            "detail": self.detail,
        }


class TransportDispatchedButUnacknowledged(RuntimeError):
    """Raised after a transport effect may already exist remotely."""


def _atomic_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = (json.dumps(dict(value), indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode(
        "utf-8"
    )
    fd, name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(name, path)
        # Persist the directory entry as well as the file contents.  Without
        # this second barrier, a crash can lose the rename while leaving the
        # caller with an apparently successful durable write.
        parent_fd = os.open(str(path.parent), os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(parent_fd)
        finally:
            os.close(parent_fd)
    finally:
        try:
            os.unlink(name)
        except FileNotFoundError:
            pass


def _load_json(path: Path) -> Mapping[str, Any] | None:
    if not path.exists():
        return None
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def classify_external_destination(
    destination: ExternalDestination,
    effect: ExternalPublicationEffect,
    boundary: tuple[InternalCollaborationBound, ...] = (),
) -> ExternalDestinationKind:
    """Fail-closed classification wrapper; UNKNOWN is treated as BLOCK."""
    kind = classification(destination, effect, boundary)
    if kind is ExternalDestinationKind.UNKNOWN:
        raise OwnerRepresentationBlocked("DESTINATION_UNKNOWN")
    return kind


def bind_external_publication(
    proposal: ExternalPublicationProposal,
    grant: OwnerRepresentationGrant | None = None,
    boundary: tuple[InternalCollaborationBound, ...] = (),
    now: datetime | None = None,
) -> OwnerRepresentationDecision:
    """Bind authority for one exact proposal, failing closed on ambiguity.

    * ``UNKNOWN`` destination -> BLOCK.
    * Internal collaboration bound -> passthrough record (no external write).
    * Third-party/external representation -> exact one-shot Owner grant is
      mandatory; inference derivations (``PUSH_DENIED``, ``TASK_COMPLETION``,
      ``WORKER_OUTPUT``, ``UNTYPED``) never substitute for it.
    """
    kind = classification(proposal.destination, proposal.effect, boundary)
    if kind is ExternalDestinationKind.UNKNOWN:
        return _decision_for(
            proposal,
            outcome=OwnerRepresentationOutcome.BLOCKED,
            reason_codes=(OwnerRepresentationReason.DESTINATION_UNKNOWN,),
            grant_hash=grant.grant_hash if grant is not None else None,
        )
    if kind is ExternalDestinationKind.OWNER_CONTROLLED_INTERNAL_COLLABORATION:
        return _decision_for(
            proposal,
            outcome=OwnerRepresentationOutcome.BLOCKED,
            reason_codes=(OwnerRepresentationReason.INTERNAL_AUTOMATION_PASSTHROUGH,),
            grant_hash=grant.grant_hash if grant is not None else None,
        )

    if grant is None:
        if proposal.derivation is PublicationDerivation.PUSH_DENIED:
            reasons = (OwnerRepresentationReason.PUSH_DENIED_IS_NOT_PUBLICATION_AUTHORITY,)
        elif proposal.derivation in {
            PublicationDerivation.PUSH_DENIED,
            PublicationDerivation.TASK_COMPLETION,
            PublicationDerivation.WORKER_OUTPUT,
            PublicationDerivation.UNTYPED,
        }:
            reasons = (OwnerRepresentationReason.PUBLICATION_AUTHORITY_NON_INFERABLE,)
        else:
            reasons = (OwnerRepresentationReason.OWNER_REPRESENTATION_REQUIRED,)
        return _decision_for(
            proposal,
            outcome=OwnerRepresentationOutcome.BLOCKED,
            reason_codes=reasons,
            grant_hash=None,
        )

    return evaluate_owner_representation(grant, proposal, now=now)


def _decision_for(
    proposal: ExternalPublicationProposal,
    *,
    outcome: OwnerRepresentationOutcome,
    reason_codes: tuple[OwnerRepresentationReason, ...],
    grant_hash: str | None,
) -> OwnerRepresentationDecision:
    payload = {
        "schema": "nexus.owner_representation_decision.v1",
        "outcome": outcome.value,
        "reason_codes": [code.value for code in reason_codes],
        "publication_authorized": outcome is OwnerRepresentationOutcome.GRANT_MATCH,
        "grant_hash": grant_hash,
        "proposal_hash": canonical_autonomy_hash(proposal.model_dump(mode="json")),
        "claim_ceiling": "OWNER_REPRESENTATION_EXACT_ONE_SHOT_ONLY",
    }
    return OwnerRepresentationDecision.model_validate({
        **payload,
        "decision_hash": canonical_autonomy_hash(payload),
    })


@dataclass(frozen=True)
class PreparedPublication:
    operation_id: str
    proposal: ExternalPublicationProposal
    grant: OwnerRepresentationGrant | None
    kind: ExternalDestinationKind
    state: str  # PREPARED | INTERNAL_PASSTHROUGH


class OwnerRepresentationPublisher:
    """Durable one-shot external-publication executor with readback reconcile.

    State transitions mirror the proven EIA publication pattern:

        PREPARED -> DISPATCHING -> COMPLETED
        PREPARED/dispatch-time unknown -> OUTCOME_UNKNOWN -> COMPLETED (via reconcile)

    ``DISPATCHING`` is persisted before any physical effect and cannot be
    blindly re-dispatched: an unacknowledged dispatch always routes to
    readback-only reconciliation.  A consumed one-shot grant is never reused.
    A published grant must be authoritative in the canonical grant store at
    send time; a grant object no store has ever issued is inert and fails
    closed with ``GRANT_NOT_ISSUED``.
    """

    def __init__(
        self,
        operation_root: Path,
        write_transport: Callable[[ExternalPublicationProposal], WriteOutcome],
        readback_transport: Callable[[ExternalPublicationProposal], str | None],
        grant_store: OwnerRepresentationGrantStore | None = None,
    ) -> None:
        self.operation_root = Path(operation_root)
        self.write_transport = write_transport
        self.readback_transport = readback_transport
        self.grant_store = grant_store or OwnerRepresentationGrantStore()

    # -- durable paths -------------------------------------------------------

    def _operation_path(self, operation_id: str) -> Path:
        return self.operation_root / "operations" / f"{operation_id}.json"

    def _ledger_path(self, grant_hash: str) -> Path:
        return self.operation_root / "consumed_grants" / f"{grant_hash}.json"

    # -- concurrency ---------------------------------------------------------

    @contextmanager
    def _dispatch_lock(self):
        """Serialize the send critical section for one operation root."""
        lock_path = self.operation_root / ".owner-representation-dispatch.lock"
        self.operation_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
        try:
            fd = os.open(str(lock_path), flags, 0o600)
        except OSError as exc:
            if exc.errno == errno.ELOOP:
                raise OwnerRepresentationBlocked("DISPATCH_LOCK_NOT_REGULAR_FILE") from exc
            if exc.errno == errno.ENOENT:
                raise OwnerRepresentationBlocked("DISPATCH_LOCK_OPEN_FAILED") from exc
            raise OwnerRepresentationBlocked("DISPATCH_LOCK_OPEN_FAILED") from exc
        try:
            st = os.fstat(fd)
            if not stat.S_ISREG(st.st_mode) or st.st_uid != os.geteuid():
                raise OwnerRepresentationBlocked("DISPATCH_LOCK_NOT_REGULAR_FILE")
            if stat.S_IMODE(st.st_mode) != 0o600:
                raise OwnerRepresentationBlocked("DISPATCH_LOCK_UNSAFE_PERMISSIONS")
            fcntl.flock(fd, fcntl.LOCK_EX)
            yield
        except OSError as exc:
            raise OwnerRepresentationBlocked("DISPATCH_LOCK_FAILED") from exc
        finally:
            os.close(fd)

    def _assert_repreparable(
        self,
        operation: Mapping[str, Any] | None,
        proposal: ExternalPublicationProposal,
        grant: OwnerRepresentationGrant | None,
    ) -> None:
        """Refuse to re-prepare a terminal or in-flight operation."""
        if operation is None:
            return
        state = operation.get("state")
        if state in {"COMPLETED", "DISPATCHING", "OUTCOME_UNKNOWN"}:
            raise OwnerRepresentationBlocked(
                f"{OwnerRepresentationReason.OPERATION_TERMINAL_OR_INFLIGHT.value}:{state}"
            )
        if state not in {"PREPARED", "INTERNAL_PASSTHROUGH"}:
            raise OwnerRepresentationBlocked("OPERATION_NOT_REPREPARABLE")
        expected_grant_hash = grant.grant_hash if grant is not None else None
        if (
            operation.get("proposal_hash")
            != canonical_autonomy_hash(proposal.model_dump(mode="json"))
            or operation.get("grant_hash") != expected_grant_hash
        ):
            raise OwnerRepresentationBlocked(OwnerRepresentationReason.OPERATION_CONFLICT.value)

    def _assert_prepared_binding(
        self,
        operation: Mapping[str, Any],
        prepared: PreparedPublication,
    ) -> None:
        """Ensure the prepared value still names the recorded operation."""
        expected_grant_hash = prepared.grant.grant_hash if prepared.grant is not None else None
        if (
            operation.get("operation_id") != prepared.operation_id
            or operation.get("proposal_hash")
            != canonical_autonomy_hash(prepared.proposal.model_dump(mode="json"))
            or operation.get("grant_hash") != expected_grant_hash
            or operation.get("grant_store_root") != str(self.grant_store.root.resolve())
        ):
            raise OwnerRepresentationBlocked(OwnerRepresentationReason.OPERATION_CONFLICT.value)

    def _authorize_grant(
        self,
        grant: OwnerRepresentationGrant,
        proposal: ExternalPublicationProposal,
        now: datetime | None,
    ) -> OwnerRepresentationDecision:
        """Fresh store-backed authorization immediately before any effect."""
        try:
            decision = self.grant_store.authorize(grant.grant_hash, proposal, now=now)
        except OwnerRepresentationGrantStoreError as exc:
            raise OwnerRepresentationBlocked(f"GRANT_STORE_FAIL_CLOSED:{exc}") from exc
        if decision.outcome is not OwnerRepresentationOutcome.GRANT_MATCH:
            raise OwnerRepresentationBlocked(":".join(code.value for code in decision.reason_codes))
        return decision

    # -- prepare -------------------------------------------------------------

    def prepare(
        self,
        proposal: ExternalPublicationProposal,
        grant: OwnerRepresentationGrant | None = None,
        boundary: tuple[InternalCollaborationBound, ...] = (),
        now: datetime | None = None,
    ) -> PreparedPublication:
        operation = _load_json(self._operation_path(proposal.operation_id))
        self._assert_repreparable(operation, proposal, grant)
        kind = classification(proposal.destination, proposal.effect, boundary)
        if kind is ExternalDestinationKind.UNKNOWN:
            raise OwnerRepresentationBlocked("DESTINATION_UNKNOWN")

        if kind is ExternalDestinationKind.OWNER_CONTROLLED_INTERNAL_COLLABORATION:
            decision = _decision_for(
                proposal,
                outcome=OwnerRepresentationOutcome.BLOCKED,
                reason_codes=(OwnerRepresentationReason.INTERNAL_AUTOMATION_PASSTHROUGH,),
                grant_hash=grant.grant_hash if grant is not None else None,
            )
            record = self._record_for(proposal, grant, kind, "INTERNAL_PASSTHROUGH", decision, now)
            _atomic_json(self._operation_path(proposal.operation_id), record)
            return PreparedPublication(
                operation_id=proposal.operation_id,
                proposal=proposal,
                grant=grant,
                kind=kind,
                state="INTERNAL_PASSTHROUGH",
            )

        decision = bind_external_publication(proposal, grant, boundary, now=now)
        if decision.outcome is not OwnerRepresentationOutcome.GRANT_MATCH:
            raise OwnerRepresentationBlocked(":".join(code.value for code in decision.reason_codes))
        record = self._record_for(proposal, grant, kind, "PREPARED", decision, now)
        _atomic_json(self._operation_path(proposal.operation_id), record)
        return PreparedPublication(
            operation_id=proposal.operation_id,
            proposal=proposal,
            grant=grant,
            kind=kind,
            state="PREPARED",
        )

    def _record_for(
        self,
        proposal: ExternalPublicationProposal,
        grant: OwnerRepresentationGrant | None,
        kind: ExternalDestinationKind,
        state: str,
        decision: OwnerRepresentationDecision,
        now: datetime | None,
    ) -> dict[str, Any]:
        return {
            "schema": "nexus.owner_representation_operation.v1",
            "operation_id": proposal.operation_id,
            "proposal_hash": canonical_autonomy_hash(proposal.model_dump(mode="json")),
            "grant_hash": grant.grant_hash if grant is not None else None,
            "grant_store_root": str(self.grant_store.root.resolve()),
            "kind": kind.value,
            "state": state,
            "decision_hash": decision.decision_hash,
            "created_at": (now or _now()).isoformat(),
        }

    # -- publish -------------------------------------------------------------

    def publish(
        self,
        prepared: PreparedPublication,
        now: datetime | None = None,
    ) -> Mapping[str, Any]:
        if prepared.state == "INTERNAL_PASSTHROUGH":
            return {
                "operation_id": prepared.operation_id,
                "classification": prepared.kind.value,
                "published": False,
                "reason": "INTERNAL_AUTOMATION_PASSTHROUGH",
                "remote_marker": None,
            }

        assert prepared.grant is not None, "third-party publish requires a grant"

        # Single-writer critical section: re-read the operation, verify it is
        # still sendable, consume the one-shot ledger, fresh-authorize against
        # the canonical store, and persist DISPATCHING atomically.
        with self._dispatch_lock():
            operation = _load_json(self._operation_path(prepared.operation_id))
            if operation is None:
                raise OwnerRepresentationBlocked(
                    OwnerRepresentationReason.DISPATCH_NOT_PREPARED.value
                )
            if operation["state"] == "COMPLETED":
                raise OwnerRepresentationBlocked(OwnerRepresentationReason.REPLAY_FORBIDDEN.value)
            if operation["state"] in {"DISPATCHING", "OUTCOME_UNKNOWN"}:
                raise OwnerRepresentationBlocked(
                    OwnerRepresentationReason.RECONCILIATION_REQUIRED.value
                )
            if operation["state"] != "PREPARED":
                raise OwnerRepresentationBlocked("DISPATCH_NOT_PREPARED")

            # One-shot ledger first: a consumed grant may never drive another
            # operation, regardless of how well it revalidates.  Existence is
            # sufficient: re-preparing the same operation with the same grant
            # must still fail after the grant was consumed exactly once.
            ledger = _load_json(self._ledger_path(prepared.grant.grant_hash))
            if ledger is not None:
                raise OwnerRepresentationBlocked(OwnerRepresentationReason.GRANT_REUSED.value)

            self._assert_prepared_binding(operation, prepared)

            # Fresh store-backed authorization immediately before any effect.
            self._authorize_grant(prepared.grant, prepared.proposal, now)

            _atomic_json(
                self._ledger_path(prepared.grant.grant_hash),
                {
                    "grant_hash": prepared.grant.grant_hash,
                    "operation_id": prepared.operation_id,
                    "consumed_at": (now or _now()).isoformat(),
                    "state": "CONSUMED",
                },
            )
            # Persist DISPATCHING before any effect; a crash after this point
            # must reconcile read-only rather than blindly re-dispatch.
            dispatch_record = dict(operation)
            dispatch_record["state"] = "DISPATCHING"
            dispatch_record["dispatched_at"] = (now or _now()).isoformat()
            _atomic_json(self._operation_path(prepared.operation_id), dispatch_record)

        outcome: WriteOutcome
        try:
            outcome = self.write_transport(prepared.proposal)
        except TransportDispatchedButUnacknowledged:
            self._mark_outcome_unknown(prepared.operation_id, now, "unacknowledged_dispatch")
            raise OwnerRepresentationBlocked(
                OwnerRepresentationReason.RECONCILIATION_REQUIRED.value
            ) from None
        except Exception as exc:
            # A transport exception after DISPATCHING may or may not have landed.
            self._mark_outcome_unknown(prepared.operation_id, now, "transport_exception")
            raise OwnerRepresentationBlocked(
                OwnerRepresentationReason.RECONCILIATION_REQUIRED.value
            ) from exc

        if outcome.status != "ACK":
            self._mark_outcome_unknown(
                prepared.operation_id,
                now,
                outcome.detail or outcome.status.lower(),
            )
            raise OwnerRepresentationBlocked(
                OwnerRepresentationReason.RECONCILIATION_REQUIRED.value
            )

        marker = outcome.remote_marker or self.readback_transport(prepared.proposal)
        if marker is None:
            self._mark_outcome_unknown(prepared.operation_id, now, "readback_marker_missing")
            raise OwnerRepresentationBlocked(
                OwnerRepresentationReason.RECONCILIATION_REQUIRED.value
            )

        return self._complete(prepared.operation_id, marker, now)

    # -- reconcile -----------------------------------------------------------

    def reconcile(
        self,
        prepared: PreparedPublication,
        now: datetime | None = None,
    ) -> Mapping[str, Any] | None:
        """Read-only reconciliation for OUTCOME_UNKNOWN / DISPATCHING ops."""
        operation = _load_json(self._operation_path(prepared.operation_id))
        if operation is None:
            return None
        self._assert_prepared_binding(operation, prepared)
        if operation["state"] == "COMPLETED":
            return operation
        if operation["state"] not in {"DISPATCHING", "OUTCOME_UNKNOWN"}:
            raise OwnerRepresentationBlocked(f"RECONCILE_INVALID_STATE:{operation['state']}")
        marker = self.readback_transport(prepared.proposal)
        if marker is None:
            return None
        return self._complete(prepared.operation_id, marker, now)

    # -- internals -----------------------------------------------------------

    def _mark_outcome_unknown(
        self,
        operation_id: str,
        now: datetime | None,
        detail: str,
    ) -> None:
        operation = _load_json(self._operation_path(operation_id))
        operation = dict(operation or {})
        operation["state"] = "OUTCOME_UNKNOWN"
        operation["outcome_reason"] = detail
        operation["updated_at"] = (now or _now()).isoformat()
        _atomic_json(self._operation_path(operation_id), operation)

    def _complete(
        self,
        operation_id: str,
        remote_marker: str,
        now: datetime | None,
    ) -> Mapping[str, Any]:
        operation = _load_json(self._operation_path(operation_id))
        operation = dict(operation or {})
        operation["state"] = "COMPLETED"
        operation["remote_marker"] = remote_marker
        operation["completed_at"] = (now or _now()).isoformat()
        _atomic_json(self._operation_path(operation_id), operation)
        return operation


__all__ = [
    "OwnerRepresentationBlocked",
    "OwnerRepresentationDecision",
    "OwnerRepresentationGrant",
    "OwnerRepresentationPublisher",
    "OwnerRepresentationReason",
    "PreparedPublication",
    "TransportDispatchedButUnacknowledged",
    "WriteOutcome",
    "bind_external_publication",
    "classify_external_destination",
]
