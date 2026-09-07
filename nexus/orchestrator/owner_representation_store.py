"""Canonical durable one-shot Owner-representation grant store.

This module is the single physical provenance for an exact one-shot
``OwnerRepresentationGrant``.  It persists ``grant_hash``-addressed receipts
under an authority root and revalidates them at publication time via the pure
semantic evaluator.  Design boundaries:

* **No minting.**  ``issue`` only persists a fully-built,
  already-hash-bound :class:`OwnerRepresentationGrant` object supplied by the
  Owner-facing issuer.  Issuance requires the exact canonical
  ``nexus.standing_grant_effect_authorization.v1`` authorization for the
  ``OWNER_REPRESENTATION_GRANT_ISSUE`` effect bound to the durable Owner
  standing grant; ``issue`` independently re-derives that authorization and
  requires exact equality, so a worker/agent can never cause an authority-backed
  receipt to appear for a grant it constructed itself.
* **Live issuance authority.**  The persisted ``issuance_authorization`` is
  re-validated fresh against the single canonical Owner standing-grant receipt
  at publication time.  A superseded, revoked, expired, or missing standing
  grant (``ISSUANCE_AUTHORITY_CHANGED`` / ``ISSUANCE_AUTHORITY_NOT_LIVE``) or a
  stripped/forged authorization (``ISSUANCE_AUTHORIZATION_REQUIRED`` /
  ``ISSUANCE_AUTHORIZATION_REJECTED``) fails the publication closed even if the
  one-shot grant itself still exists.
* **Fail closed.**  A missing, malformed, tampered, unsafe-permissioned, or
  unexpected sibling record is a hard ``OwnerRepresentationGrantStoreError``
  (never a silent GRANT_MATCH).
* **Live revocation/supersession.**  A ``revocations/`` record or a sibling
  receipt that names ``supersedes_grant_hash == grant_hash`` blocks
  authorization regardless of the grant's own serialized policy fields.
* **Carrier only.**  This module never writes to a real external destination;
  it only answers "is this exact grant still authoritative for this exact
  proposal right now".

Production load/evaluate use the single canonical authority root only.
Explicit temp roots exist solely on the ``*_at`` helpers and the
:class:`OwnerRepresentationGrantStore` ``root`` parameter for the security
test matrix and never select an alternative authority root by themselves.
"""

from __future__ import annotations

import json
import os
import pwd
import re
import stat
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, Mapping

from pydantic import ConfigDict

from nexus.contracts.autonomy_goal import (
    AutonomyActionClass,
    RepositoryIdentity,
    canonical_autonomy_hash,
)
from nexus.contracts.owner_representation import (
    ExternalDestination,
    ExternalPublicationProposal,
    OwnerRepresentationDecision,
    OwnerRepresentationGrant,
    OwnerRepresentationOutcome,
    OwnerRepresentationReason,
    evaluate_owner_representation,
)
from nexus.orchestrator.standing_grant_store import (
    StandingGrantReceiptError,
    _authorize_durable_standing_grant_effect_at,
    _canonical_json,
    _open_receipt_fd,
    _read_all_fd,
    _reject_duplicates,
    _write_bytes,
    authorize_durable_standing_grant_effect,
)

_HOME = pwd.getpwuid(os.getuid()).pw_dir
DEFAULT_OWNER_REPRESENTATION_AUTHORITY_ROOT = (
    Path(_HOME) / ".local/state/nexus/authority/owner-representation"
)
_GRANTS_DIR = "grants"
_REVOCATIONS_DIR = "revocations"
_SHA64_HEX = re.compile(r"^[0-9a-f]{64}$")
_MAX_RECORD_BYTES = 32 * 1024
_RECEIPT_SCHEMA = "nexus.owner_representation_grant_receipt.v1"
_REVOCATION_SCHEMA = "nexus.owner_representation_grant_revocation.v1"
_ISSUANCE_AUTHORIZATION_SCHEMA = "nexus.standing_grant_effect_authorization.v1"
_ISSUANCE_AUTHORIZATION_FIELDS = (
    "schema",
    "grant_id",
    "grant_receipt_hash",
    "context_hash",
    "owner_id",
    "coordinator_id",
    "repository",
    "goal_id",
    "action",
    "requested_at",
    "effect",
    "effect_hash",
    "decision_hash",
    "mutation_authorized",
    "claim_ceiling",
    "authorization_hash",
)

# The wall-clock timestamp (and its derived hash) legitimately advances between
# the issuance instant and a later publication instant.  Full exact equality is
# still required at issuance time (both sides share the same requested_at);
# publication-time revalidation compares every other binding field invariantly
# and relies on the fresh live re-derivation to catch revocation/replacement.
_ISSUANCE_AUTHORIZATION_TIME_VARYING_FIELDS = frozenset({"requested_at", "authorization_hash"})


class OwnerRepresentationGrantStoreError(Exception):
    """Fail-closed error for the one-shot Owner-representation grant store."""


class OwnerRepresentationGrantBlocked(OwnerRepresentationGrantStoreError):
    """Semantic grant-state rejection (not issued / revoked / already issued)."""


class _FrozenModel:
    model_config = ConfigDict(extra="forbid", frozen=True)


class OwnerRepresentationGrantReceipt(_FrozenModel):
    """Durable receipt binding one exact one-shot grant to the authority root."""

    schema: Literal["nexus.owner_representation_grant_receipt.v1"] = _RECEIPT_SCHEMA
    grant: OwnerRepresentationGrant
    supersedes_grant_hash: str | None = None
    receipt_hash: str


class OwnerRepresentationGrantRevocation(_FrozenModel):
    """Immutable revocation record for one previously issued grant hash."""

    schema: Literal["nexus.owner_representation_grant_revocation.v1"] = _REVOCATION_SCHEMA
    grant_hash: str
    revoked_by: str
    reason: str
    revoked_at: str
    record_hash: str


def _grants_dir(root: Path) -> Path:
    return Path(root) / _GRANTS_DIR


def _revocations_dir(root: Path) -> Path:
    return Path(root) / _REVOCATIONS_DIR


def _read_sealed_record(path: Path, schema: str, hash_field: str) -> dict[str, Any]:
    """Read and integrity-validate one sealed record via a no-follow fd."""
    fd = _open_receipt_fd(path)
    try:
        fst = os.fstat(fd)
    except OSError as exc:
        if fd >= 0:
            os.close(fd)
        raise OwnerRepresentationGrantStoreError("RECORD_READ_FAILED") from exc
    if stat.S_ISLNK(fst.st_mode) or not stat.S_ISREG(fst.st_mode):
        os.close(fd)
        raise OwnerRepresentationGrantStoreError("NOT_REGULAR_FILE")
    if fst.st_uid != os.geteuid():
        os.close(fd)
        raise OwnerRepresentationGrantStoreError("RECORD_OWNER_MISMATCH")
    if stat.S_IMODE(fst.st_mode) != 0o600:
        os.close(fd)
        raise OwnerRepresentationGrantStoreError("UNSAFE_PERMISSIONS")
    if fst.st_size > _MAX_RECORD_BYTES:
        os.close(fd)
        raise OwnerRepresentationGrantStoreError("RECORD_TOO_LARGE")
    raw = _read_all_fd(fd, fst.st_size)
    os.close(fd)
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise OwnerRepresentationGrantStoreError("MALFORMED") from exc
    if text.endswith("\n"):
        text = text[:-1]
    if "\x00" in text or "\n" in text:
        raise OwnerRepresentationGrantStoreError("NONCANONICAL_SERIALIZATION")
    try:
        parsed = json.loads(text, object_pairs_hook=_reject_duplicates)
    except (json.JSONDecodeError, ValueError) as exc:
        raise OwnerRepresentationGrantStoreError("MALFORMED") from exc
    if not isinstance(parsed, dict):
        raise OwnerRepresentationGrantStoreError("MALFORMED")
    if parsed.get("schema") != schema:
        raise OwnerRepresentationGrantStoreError("MALFORMED")
    if _canonical_json(parsed) != text:
        raise OwnerRepresentationGrantStoreError("NONCANONICAL_SERIALIZATION")
    stored_hash = parsed.get(hash_field)
    if not isinstance(stored_hash, str) or not _SHA64_HEX.fullmatch(stored_hash):
        raise OwnerRepresentationGrantStoreError("TAMPERED")
    body = {k: v for k, v in parsed.items() if k != hash_field}
    if canonical_autonomy_hash(body) != stored_hash:
        raise OwnerRepresentationGrantStoreError("TAMPERED")
    return parsed


def _grant_receipt_path(root: Path, grant_hash: str) -> Path:
    return _grants_dir(root) / f"{grant_hash}.json"


def _revocation_path(root: Path, grant_hash: str) -> Path:
    return _revocations_dir(root) / f"{grant_hash}.json"


def _require_issued(root: Path, grant_hash: str) -> dict[str, Any]:
    """Return the sealed issued grant record, blocking closed on any else."""
    if not _SHA64_HEX.fullmatch(grant_hash):
        raise OwnerRepresentationGrantBlocked(OwnerRepresentationReason.GRANT_NOT_ISSUED.value)
    try:
        return _read_sealed_record(
            _grant_receipt_path(root, grant_hash),
            _RECEIPT_SCHEMA,
            "receipt_hash",
        )
    except StandingGrantReceiptError as exc:
        if str(exc) == "RECEIPT_MISSING":
            raise OwnerRepresentationGrantBlocked(
                OwnerRepresentationReason.GRANT_NOT_ISSUED.value
            ) from exc
        raise OwnerRepresentationGrantStoreError(str(exc)) from exc


def _has_revocation(root: Path, grant_hash: str) -> bool:
    """Return True when a sealed revocation record exists for the grant hash."""
    path = _revocation_path(root, grant_hash)
    if not path.exists():
        return False
    _read_sealed_record(path, _REVOCATION_SCHEMA, "record_hash")
    return True


def _superseding_grant_hash(root: Path, grant_hash: str) -> str | None:
    """Return the first sibling receipt that supersedes this grant hash.

    A malformed or unexpected sibling inside the authority ``grants/``
    directory fails closed: authorization never proceeds while the authority
    surface is ambiguous.
    """
    grants_dir = _grants_dir(root)
    if not grants_dir.exists():
        return None
    for entry in sorted(grants_dir.iterdir()):
        name = entry.name
        if name.startswith("."):
            # Coordination artifacts (e.g. the flock file) are not records.
            continue
        if not entry.is_file():
            raise OwnerRepresentationGrantStoreError("GRANTS_DIR_UNEXPECTED_ENTRY")
        if not name.endswith(".json"):
            raise OwnerRepresentationGrantStoreError("GRANTS_DIR_UNEXPECTED_ENTRY")
        record = _read_sealed_record(entry, _RECEIPT_SCHEMA, "receipt_hash")
        if record.get("supersedes_grant_hash") == grant_hash:
            return name[: -len(".json")]
    return None


def _blocked_decision(
    proposal: ExternalPublicationProposal,
    reason_code: OwnerRepresentationReason,
    grant_hash: str | None = None,
) -> OwnerRepresentationDecision:
    """Build one BLOCKED owner-representation decision without a second evaluator."""
    payload = {
        "schema": "nexus.owner_representation_decision.v1",
        "outcome": OwnerRepresentationOutcome.BLOCKED.value,
        "reason_codes": [reason_code.value],
        "publication_authorized": False,
        "grant_hash": grant_hash,
        "proposal_hash": canonical_autonomy_hash(proposal.model_dump(mode="json")),
        "claim_ceiling": "OWNER_REPRESENTATION_EXACT_ONE_SHOT_ONLY",
    }
    return OwnerRepresentationDecision.model_validate({
        **payload,
        "decision_hash": canonical_autonomy_hash(payload),
    })


def owner_representation_issuance_effect(grant: OwnerRepresentationGrant) -> dict[str, Any]:
    """Return the exact Owner-representation grant issuance effect.

    The effect payload binds the complete ``grant`` so the issuance
    authorization can only ever cover exactly this grant object.
    """
    return {
        "operation": AutonomyActionClass.OWNER_REPRESENTATION_GRANT_ISSUE.value,
        "grant": grant.model_dump(mode="json"),
    }


def _repository_identity_for_destination(destination: ExternalDestination) -> RepositoryIdentity:
    """Map one external destination to the standing-grant repository identity."""
    return RepositoryIdentity(
        repository_id=destination.repository_id,
        canonical_remote=destination.canonical_remote,
    )


def authorize_owner_representation_grant_issuance(
    grant: OwnerRepresentationGrant,
    *,
    standing_grant_path: Path | None = None,
    requested_at: datetime | None = None,
) -> dict[str, Any]:
    """Bind one exact Owner-representation grant issuance to the canonical
    durable Owner standing grant (``OWNER_REPRESENTATION_GRANT_ISSUE``).

    ``standing_grant_path`` is a test/operator-only surface; production uses
    the single canonical standing-grant receipt path.
    """
    if not isinstance(grant, OwnerRepresentationGrant):
        raise TypeError("grant must be a validated OwnerRepresentationGrant")
    if grant.revoked_at is not None:
        raise OwnerRepresentationGrantBlocked(OwnerRepresentationReason.GRANT_REVOKED.value)
    if grant.superseded_by is not None:
        raise OwnerRepresentationGrantBlocked(OwnerRepresentationReason.GRANT_SUPERSEDED.value)
    effective_now = requested_at if requested_at is not None else datetime.now(timezone.utc)
    if not isinstance(effective_now, datetime) or effective_now.tzinfo is None:
        raise OwnerRepresentationGrantBlocked("EXACT_TIMEZONE_REQUIRED")
    repository = _repository_identity_for_destination(grant.destination)
    effect = owner_representation_issuance_effect(grant)
    if standing_grant_path is None:
        return authorize_durable_standing_grant_effect(
            repository=repository,
            action=AutonomyActionClass.OWNER_REPRESENTATION_GRANT_ISSUE,
            effect=effect,
            requested_at=effective_now,
        )
    return _authorize_durable_standing_grant_effect_at(
        Path(standing_grant_path),
        repository=repository,
        action=AutonomyActionClass.OWNER_REPRESENTATION_GRANT_ISSUE,
        effect=effect,
        requested_at=effective_now,
    )


def _revalidate_issuance_authorization(
    grant: OwnerRepresentationGrant,
    issuance_authorization: Mapping[str, Any],
    *,
    standing_grant_path: Path | None,
    requested_at: datetime,
) -> dict[str, Any]:
    """Independently re-derive the exact issuance authorization for one grant.

    Requires full field equality (including ``authorization_hash``) between the
    caller-supplied authorization and a fresh authorization re-derived from the
    canonical durable Owner standing grant at the same ``requested_at``.  The
    grant identity bindings (``owner_id``, ``coordinator_id``, ``issued_by``)
    are additionally enforced so a forged ``issued_by``/``owner_id`` can never
    masquerade as Owner issuance.
    """
    if not isinstance(issuance_authorization, Mapping):
        raise OwnerRepresentationGrantBlocked(
            OwnerRepresentationReason.ISSUANCE_AUTHORIZATION_REQUIRED.value
        )
    if issuance_authorization.get("schema") != _ISSUANCE_AUTHORIZATION_SCHEMA:
        raise OwnerRepresentationGrantBlocked(
            OwnerRepresentationReason.ISSUANCE_AUTHORIZATION_REJECTED.value
        )
    try:
        allowed = authorize_owner_representation_grant_issuance(
            grant,
            standing_grant_path=standing_grant_path,
            requested_at=requested_at,
        )
    except OwnerRepresentationGrantBlocked:
        raise
    except StandingGrantReceiptError as exc:
        raise OwnerRepresentationGrantBlocked(
            OwnerRepresentationReason.ISSUANCE_AUTHORIZATION_REJECTED.value
        ) from exc
    supplied = {key: issuance_authorization.get(key) for key in _ISSUANCE_AUTHORIZATION_FIELDS}
    derived = {key: allowed.get(key) for key in _ISSUANCE_AUTHORIZATION_FIELDS}
    if supplied != derived:
        raise OwnerRepresentationGrantBlocked(
            OwnerRepresentationReason.ISSUANCE_AUTHORIZATION_REJECTED.value
        )
    if grant.owner_id != str(allowed.get("owner_id")):
        raise OwnerRepresentationGrantBlocked(
            OwnerRepresentationReason.ISSUANCE_AUTHORIZATION_REJECTED.value
        )
    if grant.coordinator_id != str(allowed.get("coordinator_id")):
        raise OwnerRepresentationGrantBlocked(
            OwnerRepresentationReason.ISSUANCE_AUTHORIZATION_REJECTED.value
        )
    if grant.issued_by != str(allowed.get("owner_id")):
        raise OwnerRepresentationGrantBlocked(
            OwnerRepresentationReason.ISSUANCE_AUTHORIZATION_REJECTED.value
        )
    return allowed


def _authorize_at(
    root: Path,
    grant_hash: str,
    proposal: ExternalPublicationProposal,
    now: datetime | None,
    standing_grant_path: Path | None = None,
) -> OwnerRepresentationDecision:
    """Revalidate one issued grant against one exact proposal right now.

    Order of checks is deliberately fail-closed: issuance first (the grant
    must exist in canonical form), then live revocation, then live
    supersession, then live issuance-authority revalidation against the
    canonical durable Owner standing grant, and only then the pure field-for-field
    semantic evaluation.

    Issuance-authority revalidation re-derives the authorization fresh at the
    current instant, which fails closed on a revoked/unreadable standing grant
    (``ISSUANCE_AUTHORITY_NOT_LIVE``) and on a replaced standing grant whose
    context/receipt/binding fields changed (``ISSUANCE_AUTHORITY_CHANGED``).
    The time-varying ``requested_at``/``authorization_hash`` pair is excluded
    from the comparison because the clock legitimately advances between
    issuance and publication; every other issuance binding is compared exactly.
    """
    record = _require_issued(root, grant_hash)
    if _has_revocation(root, grant_hash):
        return _blocked_decision(
            proposal, OwnerRepresentationReason.GRANT_REVOKED, grant_hash=grant_hash
        )
    superseding = _superseding_grant_hash(root, grant_hash)
    if superseding is not None:
        return _blocked_decision(
            proposal, OwnerRepresentationReason.GRANT_SUPERSEDED, grant_hash=grant_hash
        )
    try:
        grant = OwnerRepresentationGrant.model_validate(record["grant"])
    except Exception as exc:
        raise OwnerRepresentationGrantStoreError("TAMPERED") from exc
    stored_auth = record.get("issuance_authorization")
    if not isinstance(stored_auth, Mapping):
        return _blocked_decision(
            proposal,
            OwnerRepresentationReason.ISSUANCE_AUTHORIZATION_REQUIRED,
            grant_hash=grant_hash,
        )
    effective_now = now if now is not None else datetime.now(timezone.utc)
    try:
        fresh = authorize_owner_representation_grant_issuance(
            grant,
            standing_grant_path=standing_grant_path,
            requested_at=effective_now,
        )
    except OwnerRepresentationGrantStoreError:
        raise
    except StandingGrantReceiptError as exc:
        raise OwnerRepresentationGrantStoreError(f"ISSUANCE_AUTHORITY_NOT_LIVE:{exc}") from exc
    invariant_fields = [
        key
        for key in _ISSUANCE_AUTHORIZATION_FIELDS
        if key not in _ISSUANCE_AUTHORIZATION_TIME_VARYING_FIELDS
    ]
    for key in invariant_fields:
        if fresh.get(key) != stored_auth.get(key):
            return _blocked_decision(
                proposal,
                OwnerRepresentationReason.ISSUANCE_AUTHORITY_CHANGED,
                grant_hash=grant_hash,
            )
    return evaluate_owner_representation(grant, proposal, now=now)


class OwnerRepresentationGrantStore:
    """Machine-local one-shot Owner-representation grant store.

    ``root`` selects the authority root; production defaults to the single
    canonical path.  ``standing_grant_path`` selects the durable Owner
    standing-grant receipt used to re-derive issuance authorization; production
    defaults to the single canonical standing-grant path.  Explicit roots/paths
    are for tests/operator tooling only.
    """

    def __init__(
        self,
        root: Path | None = None,
        *,
        standing_grant_path: Path | None = None,
    ) -> None:
        self.root = Path(root) if root is not None else DEFAULT_OWNER_REPRESENTATION_AUTHORITY_ROOT
        self.standing_grant_path = (
            Path(standing_grant_path) if standing_grant_path is not None else None
        )

    def issue(
        self,
        grant: OwnerRepresentationGrant,
        *,
        issuance_authorization: Mapping[str, Any],
        supersedes_grant_hash: str | None = None,
        requested_at: datetime | None = None,
    ) -> Path:
        """Persist one validated Owner-supplied grant as a durable receipt.

        ``issuance_authorization`` is the exact
        ``nexus.standing_grant_effect_authorization.v1`` authorization produced
        by :func:`authorize_owner_representation_grant_issuance`.  The store
        independently re-derives that authorization from the canonical durable
        Owner standing grant and requires exact equality, so a worker/agent can
        never mint an authority-backed receipt for a grant it constructed
        itself.

        ``supersedes_grant_hash`` must name an already-issued sibling, which
        makes this grant a live supersession of that earlier one-shot grant.
        """
        if not isinstance(grant, OwnerRepresentationGrant):
            raise TypeError("grant must be a validated OwnerRepresentationGrant")
        if grant.revoked_at is not None:
            raise OwnerRepresentationGrantBlocked(OwnerRepresentationReason.GRANT_REVOKED.value)
        if grant.superseded_by is not None:
            raise OwnerRepresentationGrantBlocked(OwnerRepresentationReason.GRANT_SUPERSEDED.value)
        now = requested_at if requested_at is not None else datetime.now(timezone.utc)
        if not isinstance(now, datetime) or now.tzinfo is None:
            raise OwnerRepresentationGrantBlocked("EXACT_TIMEZONE_REQUIRED")
        if supersedes_grant_hash is not None:
            if not _SHA64_HEX.fullmatch(supersedes_grant_hash):
                raise OwnerRepresentationGrantBlocked(
                    OwnerRepresentationReason.GRANT_SUPERSEDED.value
                )
            if supersedes_grant_hash == grant.grant_hash:
                raise OwnerRepresentationGrantBlocked(
                    OwnerRepresentationReason.GRANT_SUPERSEDED.value
                )
            _require_issued(self.root, supersedes_grant_hash)

        destination = _grant_receipt_path(self.root, grant.grant_hash)
        if destination.exists():
            raise OwnerRepresentationGrantBlocked(
                OwnerRepresentationReason.GRANT_ALREADY_ISSUED.value
            )
        if _has_revocation(self.root, grant.grant_hash):
            raise OwnerRepresentationGrantBlocked(OwnerRepresentationReason.GRANT_REVOKED.value)

        allowed = _revalidate_issuance_authorization(
            grant,
            issuance_authorization,
            standing_grant_path=self.standing_grant_path,
            requested_at=now,
        )
        payload = {
            "schema": _RECEIPT_SCHEMA,
            "grant": grant.model_dump(mode="json"),
            "supersedes_grant_hash": supersedes_grant_hash,
            "issuance_authorization": allowed,
        }
        record = {
            **payload,
            "receipt_hash": canonical_autonomy_hash(payload),
        }
        canonical = _canonical_json(record)
        try:
            _write_bytes(canonical, None, destination, None)
        except StandingGrantReceiptError as exc:
            raise OwnerRepresentationGrantStoreError(str(exc)) from exc
        return destination

    def revoke(
        self,
        grant_hash: str,
        *,
        revoked_by: str,
        reason: str,
        revoked_at: datetime | None = None,
    ) -> Path:
        """Persist an immutable revocation for one issued grant hash."""
        record = _require_issued(self.root, grant_hash)
        _ = record
        if _has_revocation(self.root, grant_hash):
            raise OwnerRepresentationGrantBlocked(OwnerRepresentationReason.GRANT_REVOKED.value)
        when = revoked_at if revoked_at is not None else datetime.now(timezone.utc)
        payload = {
            "schema": _REVOCATION_SCHEMA,
            "grant_hash": grant_hash,
            "revoked_by": str(revoked_by),
            "reason": str(reason),
            "revoked_at": when.isoformat(),
        }
        record = {
            **payload,
            "record_hash": canonical_autonomy_hash(payload),
        }
        canonical = _canonical_json(record)
        destination = _revocation_path(self.root, grant_hash)
        try:
            _write_bytes(canonical, None, destination, None)
        except StandingGrantReceiptError as exc:
            if str(exc) in {"SUPERSEDES_HASH_REQUIRED_FOR_REPLACE", "EXISTS_NO_CAS"}:
                raise OwnerRepresentationGrantBlocked(
                    OwnerRepresentationReason.GRANT_REVOKED.value
                ) from exc
            raise OwnerRepresentationGrantStoreError(str(exc)) from exc
        return destination

    def load(self, grant_hash: str) -> OwnerRepresentationGrant:
        """Load one issued grant, failing closed when it is not issued."""
        record = _require_issued(self.root, grant_hash)
        try:
            return OwnerRepresentationGrant.model_validate(record["grant"])
        except Exception as exc:
            raise OwnerRepresentationGrantStoreError("MALFORMED") from exc

    def authorize(
        self,
        grant_hash: str,
        proposal: ExternalPublicationProposal,
        now: datetime | None = None,
    ) -> OwnerRepresentationDecision:
        """Fresh pre-effect revalidation against the canonical store."""
        return _authorize_at(
            self.root,
            grant_hash,
            proposal,
            now,
            standing_grant_path=self.standing_grant_path,
        )

    def inspect_grant(self, grant_hash: str) -> Mapping[str, Any]:
        """Read-only status projection; never raises for a non-issued hash."""
        try:
            record = _require_issued(self.root, grant_hash)
        except OwnerRepresentationGrantBlocked:
            return {"grant_hash": grant_hash, "status": "GRANT_NOT_ISSUED"}
        status = "ISSUED"
        try:
            if _has_revocation(self.root, grant_hash):
                status = "REVOKED"
            elif _superseding_grant_hash(self.root, grant_hash) is not None:
                status = "SUPERSEDED"
        except OwnerRepresentationGrantStoreError:
            status = "INTEGRITY_ERROR"
        return {
            "grant_hash": grant_hash,
            "status": status,
            "grant": record["grant"],
            "supersedes_grant_hash": record.get("supersedes_grant_hash"),
            "issued_with_authority": isinstance(record.get("issuance_authorization"), Mapping),
        }


def issue_owner_representation_grant(
    grant: OwnerRepresentationGrant,
    *,
    requested_at: datetime | None = None,
    supersedes_grant_hash: str | None = None,
) -> Path:
    """Persist one one-shot Owner-representation grant to the canonical root.

    Computes the exact canonical issuance authorization bound to the durable
    Owner standing grant at one fixed ``requested_at`` and passes it to
    ``issue``, which re-derives the same authorization from the canonical
    standing-grant receipt.  A self-authorized worker can never mint an
    authority-backed receipt for a grant it constructed itself.
    """
    now = requested_at if requested_at is not None else datetime.now(timezone.utc)
    authorization = authorize_owner_representation_grant_issuance(grant, requested_at=now)
    return OwnerRepresentationGrantStore().issue(
        grant,
        issuance_authorization=authorization,
        requested_at=now,
        supersedes_grant_hash=supersedes_grant_hash,
    )


def revoke_owner_representation_grant(
    grant_hash: str,
    *,
    revoked_by: str,
    reason: str,
    revoked_at: datetime | None = None,
) -> Path:
    """Revoke one one-shot Owner-representation grant at the canonical root."""
    return OwnerRepresentationGrantStore().revoke(
        grant_hash,
        revoked_by=revoked_by,
        reason=reason,
        revoked_at=revoked_at,
    )


def load_owner_representation_grant(grant_hash: str) -> OwnerRepresentationGrant:
    """Load a canonical one-shot Owner-representation grant, failing closed."""
    return OwnerRepresentationGrantStore().load(grant_hash)


def authorize_owner_representation_publication(
    grant_hash: str,
    proposal: ExternalPublicationProposal,
    now: datetime | None = None,
) -> OwnerRepresentationDecision:
    """Fresh canonical revalidation for one exact publication proposal."""
    return OwnerRepresentationGrantStore().authorize(grant_hash, proposal, now)


def inspect_owner_representation_grant(grant_hash: str) -> Mapping[str, Any]:
    """Return a read-only status projection for one grant hash."""
    return OwnerRepresentationGrantStore().inspect_grant(grant_hash)


__all__ = [
    "DEFAULT_OWNER_REPRESENTATION_AUTHORITY_ROOT",
    "OwnerRepresentationGrantBlocked",
    "OwnerRepresentationGrantReceipt",
    "OwnerRepresentationGrantRevocation",
    "OwnerRepresentationGrantStore",
    "OwnerRepresentationGrantStoreError",
    "authorize_owner_representation_grant_issuance",
    "authorize_owner_representation_publication",
    "inspect_owner_representation_grant",
    "issue_owner_representation_grant",
    "load_owner_representation_grant",
    "owner_representation_issuance_effect",
    "revoke_owner_representation_grant",
]
