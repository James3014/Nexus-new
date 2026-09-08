"""Canonical durable one-shot Owner-representation grant store.

This module is the single physical provenance for an exact one-shot
``OwnerRepresentationGrant``.  It persists ``grant_hash``-addressed receipts
under an authority root and revalidates them at publication time via the pure
semantic evaluator.  Design boundaries:

* **No minting.**  ``issue`` only persists a fully-built,
  already-hash-bound :class:`OwnerRepresentationGrant` object supplied by the
  Owner-facing issuer.  Issuance requires a sealed non-reusable issuance permit
  (``nexus.owner_representation_publication_issuance_permit.v1``) that is exact,
  effect-bound, and consumed once.  Each owned one-shot grant must first be
  minted into ``permits/<standing_grant_receipt_hash>.json``; ``issue`` accepts
  only the one permit whose ``grant_hash`` matches the grant, re-reads it sealed
  from disk, and refuses everything else
  (``ISSUANCE_AUTHORIZATION_REQUIRED`` / ``ISSUANCE_AUTHORIZATION_REJECTED``),
  so a worker/agent can never cause an authority-backed receipt to appear for a
  grant it constructed itself.
* **One Owner standing-grant receipt mints at most one permit.**  The permit
  slot is addressed by the standing-grant receipt hash; a second mint on the
  same slot fails ``ISSUANCE_PERMIT_SLOT_CONSUMED`` (``PERMIT_ALREADY_MINTED``
  for a repeat mint of the identical grant).  The permit is therefore a strict
  superset of the standing grant's "one issuance decision" scope and cannot be
  replayed to drive a different grant or a second issuance.
* **Consumption fence.**  The authority store creates the sealed issuance
  permit during ``authorize_owner_representation_grant_issuance`` and, on the
  first accepted ``issue``, writes a ``permits/consumed/<grant_hash>.json``
  marker before the grant receipt.  Any subsequent issue attempt fails closed
  (``GRANT_ALREADY_ISSUED`` if the receipt still exists, ``GRANT_REUSED`` if
  the grant receipt was destroyed but the consumed marker remains).
* **Live issuance authority.**  The persisted permit is re-validated fresh
  against the single canonical Owner standing-grant receipt at issue and at
  publication time.  A superseded, revoked, expired, or missing standing grant
  (``ISSUANCE_AUTHORITY_CHANGED`` / ``ISSUANCE_AUTHORITY_NOT_LIVE``) or a
  stripped/forged permit (``ISSUANCE_AUTHORIZATION_REQUIRED`` /
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
Explicit temp roots exist solely on the ``*_at`` helpers, the
:class:`OwnerRepresentationGrantStore` ``root`` parameter, and the permit
``authority_root`` parameter for the security test matrix and never select an
alternative authority root by themselves.
"""

from __future__ import annotations

import base64
import json
import os
import pwd
import re
import stat
import subprocess
import sys
import tempfile
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
    OwnerExactPublicationAuthorization,
    OwnerExactPublicationAuthorizationSpec,
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
_PERMITS_DIR = "permits"
_PERMITS_CONSUMED_DIR = "consumed"
_AUTHORIZATIONS_DIR = "authorizations"
_AUTHORIZATIONS_CONSUMED_DIR = "consumed"
_SHA64_HEX = re.compile(r"^[0-9a-f]{64}$")
_MAX_RECORD_BYTES = 32 * 1024
_RECEIPT_SCHEMA = "nexus.owner_representation_grant_receipt.v1"
_REVOCATION_SCHEMA = "nexus.owner_representation_grant_revocation.v1"
_PERMIT_SCHEMA = "nexus.owner_representation_publication_issuance_permit.v1"
_PERMIT_CONSUMED_SCHEMA = "nexus.owner_representation_issuance_permit_consumed.v1"
_AUTHORIZATION_SCHEMA = "nexus.owner_exact_publication_authorization.v1"
_AUTHORIZATION_CONSUMED_SCHEMA = "nexus.owner_exact_publication_authorization_consumed.v1"
# Deployment-owned trust root.  This is deliberately not derived from the
# caller's authority_root or from fields in an authorization record.
# ``/etc`` is a symlink to ``/private/etc`` on macOS.  Pin the canonical
# platform path so the lstat boundary can reject symlinks without making the
# real deployment path unusable.  This is fixed process configuration: callers
# and authorization records cannot select a trust root.
_TRUST_ETC_ROOT = Path("/private/etc") if sys.platform == "darwin" else Path("/etc")
OWNER_AUTHORIZATION_TRUST_ROOT = _TRUST_ETC_ROOT / "nexus/owner-representation/trusted-keys"
OPENSSL_BINARY = "/usr/bin/openssl"


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
    permit_id: str | None = None
    authorization_id: str | None = None
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


def _parse_iso(value: Any) -> datetime:
    """Parse one permit timestamp strictly; a malformed value fails closed."""
    if not isinstance(value, str):
        raise OwnerRepresentationGrantStoreError("MALFORMED")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise OwnerRepresentationGrantStoreError("MALFORMED") from exc
    if parsed.tzinfo is None:
        raise OwnerRepresentationGrantStoreError("MALFORMED")
    return parsed


def _permits_dir(root: Path) -> Path:
    return Path(root) / _PERMITS_DIR


def _permits_consumed_dir(root: Path) -> Path:
    return _permits_dir(root) / _PERMITS_CONSUMED_DIR


def _permit_path(root: Path, standing_grant_receipt_hash: str) -> Path:
    if not _SHA64_HEX.fullmatch(standing_grant_receipt_hash):
        raise OwnerRepresentationGrantStoreError("RECEIPT_HASH_INVALID")
    return _permits_dir(root) / f"{standing_grant_receipt_hash}.json"


def _consumed_marker_path(root: Path, grant_hash: str) -> Path:
    if not _SHA64_HEX.fullmatch(grant_hash):
        raise OwnerRepresentationGrantStoreError("RECEIPT_HASH_INVALID")
    return _permits_consumed_dir(root) / f"{grant_hash}.json"


def _permit_records(root: Path) -> list[dict[str, Any]]:
    """Return every sealed issuance permit under the authority root.

    A malformed or unexpected sibling inside ``permits/`` fails closed: the
    authority surface is ambiguous and must never be evaluated optimistically.
    """
    permits_dir = _permits_dir(root)
    if not permits_dir.exists():
        return []
    records = []
    for entry in sorted(permits_dir.iterdir()):
        name = entry.name
        if name.startswith("."):
            # Coordination artifacts (e.g. the flock file) are not records.
            continue
        if entry.is_dir():
            if name == _PERMITS_CONSUMED_DIR:
                continue
            raise OwnerRepresentationGrantStoreError("PERMITS_DIR_UNEXPECTED_ENTRY")
        if not name.endswith(".json"):
            raise OwnerRepresentationGrantStoreError("PERMITS_DIR_UNEXPECTED_ENTRY")
        records.append(_read_sealed_record(entry, _PERMIT_SCHEMA, "permit_hash"))
    return records


def _load_permit_for_grant(root: Path, grant_hash: str) -> dict[str, Any] | None:
    """Return the sealed issuance permit for one grant hash, if minted."""
    for record in _permit_records(root):
        if record.get("grant_hash") == grant_hash:
            return record
    return None


def _permit_consumed(root: Path, grant_hash: str) -> bool:
    """Return True when a sealed consumption marker exists for the grant hash."""
    path = _consumed_marker_path(root, grant_hash)
    if not path.exists():
        return False
    _read_sealed_record(path, _PERMIT_CONSUMED_SCHEMA, "record_hash")
    return True


def _authorizations_dir(root: Path) -> Path:
    return Path(root) / _AUTHORIZATIONS_DIR


def _authorizations_consumed_dir(root: Path) -> Path:
    return _authorizations_dir(root) / _AUTHORIZATIONS_CONSUMED_DIR


def _authorization_path(root: Path, grant_hash: str) -> Path:
    return _authorizations_dir(root) / f"{grant_hash}.json"


def _authorization_consumed_marker_path(root: Path, grant_hash: str) -> Path:
    return _authorizations_consumed_dir(root) / f"{grant_hash}.json"


def _authorization_consumed(root: Path, grant_hash: str) -> bool:
    if not _SHA64_HEX.fullmatch(grant_hash):
        return False
    path = _authorization_consumed_marker_path(root, grant_hash)
    if not path.exists():
        return False
    _read_sealed_record(path, _AUTHORIZATION_CONSUMED_SCHEMA, "record_hash")
    return True


def _load_authorization_for_grant(root: Path, grant_hash: str) -> dict[str, Any] | None:
    if not _SHA64_HEX.fullmatch(grant_hash):
        return None
    path = _authorization_path(root, grant_hash)
    if not path.exists():
        return None
    return _read_sealed_record(path, _AUTHORIZATION_SCHEMA, "authorization_hash")


def _authorization_records(root: Path) -> list[dict[str, Any]]:
    auth_dir = _authorizations_dir(root)
    if not auth_dir.exists():
        return []
    records = []
    for entry in sorted(auth_dir.iterdir()):
        name = entry.name
        if name.startswith("."):
            continue
        if entry.is_dir():
            if name == _AUTHORIZATIONS_CONSUMED_DIR:
                continue
            raise OwnerRepresentationGrantStoreError("AUTHORIZATIONS_DIR_UNEXPECTED_ENTRY")
        if not name.endswith(".json"):
            raise OwnerRepresentationGrantStoreError("AUTHORIZATIONS_DIR_UNEXPECTED_ENTRY")
        records.append(_read_sealed_record(entry, _AUTHORIZATION_SCHEMA, "authorization_hash"))
    return records


def _verify_owner_signature(auth: OwnerExactPublicationAuthorization) -> None:
    """Verify an Owner signature against the deployment trust root.

    The trust root is process/deployment configuration, never caller data.
    Missing keys, malformed signatures, unavailable OpenSSL, and verification
    failures all fail closed.
    """
    key_path = OWNER_AUTHORIZATION_TRUST_ROOT / f"{auth.owner_id}--{auth.owner_key_id}.pem"
    try:
        root_stat = OWNER_AUTHORIZATION_TRUST_ROOT.lstat()
        key_stat = key_path.lstat()
        ancestor_stats = [parent.lstat() for parent in OWNER_AUTHORIZATION_TRUST_ROOT.parents]
    except OSError:
        raise OwnerRepresentationGrantBlocked(
            OwnerRepresentationReason.EXACT_OWNER_AUTHORIZATION_REJECTED.value
        )
    if (
        auth.owner_signature_algorithm != "RSA-SHA256"
        or not stat.S_ISDIR(root_stat.st_mode)
        or stat.S_ISLNK(root_stat.st_mode)
        or root_stat.st_uid != 0
        or stat.S_IMODE(root_stat.st_mode) & 0o022
        or not stat.S_ISREG(key_stat.st_mode)
        or stat.S_ISLNK(key_stat.st_mode)
        or key_stat.st_uid != 0
        or stat.S_IMODE(key_stat.st_mode) & 0o077
        or not Path(OPENSSL_BINARY).is_file()
        or any(
            stat.S_ISLNK(item.st_mode)
            or not stat.S_ISDIR(item.st_mode)
            or item.st_uid != 0
            or stat.S_IMODE(item.st_mode) & 0o022
            for item in ancestor_stats
        )
    ):
        raise OwnerRepresentationGrantBlocked(
            OwnerRepresentationReason.EXACT_OWNER_AUTHORIZATION_REJECTED.value
        )
    try:
        signature = base64.b64decode(auth.owner_signature, validate=True)
        payload = auth.model_dump(mode="json", exclude={"owner_signature", "authorization_hash"})
        encoded = _canonical_json(payload).encode("utf-8")
        with tempfile.TemporaryDirectory(prefix="nexus-owner-auth-") as directory:
            payload_path = Path(directory) / "payload"
            signature_path = Path(directory) / "signature"
            payload_path.write_bytes(encoded)
            signature_path.write_bytes(signature)
            result = subprocess.run(
                [OPENSSL_BINARY, "rsa", "-pubin", "-in", str(key_path), "-text", "-noout"],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                timeout=2,
                check=False,
            )
            bits = re.search(rb"(\d+) bit", result.stdout or b"")
            if result.returncode != 0 or bits is None or int(bits.group(1)) < 3072:
                raise OwnerRepresentationGrantBlocked(
                    OwnerRepresentationReason.EXACT_OWNER_AUTHORIZATION_REJECTED.value
                )
            result = subprocess.run(
                [
                    OPENSSL_BINARY,
                    "dgst",
                    "-sha256",
                    "-verify",
                    str(key_path),
                    "-signature",
                    str(signature_path),
                    str(payload_path),
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=2,
                check=False,
            )
    except (OSError, ValueError, subprocess.SubprocessError):
        raise OwnerRepresentationGrantBlocked(
            OwnerRepresentationReason.EXACT_OWNER_AUTHORIZATION_REJECTED.value
        )
    if result.returncode != 0:
        raise OwnerRepresentationGrantBlocked(
            OwnerRepresentationReason.EXACT_OWNER_AUTHORIZATION_REJECTED.value
        )


def _write_authorization_consumed_marker(
    root: Path,
    *,
    grant_hash: str,
    authorization_id: str,
    consumed_at: datetime,
) -> None:
    payload = {
        "schema": _AUTHORIZATION_CONSUMED_SCHEMA,
        "grant_hash": grant_hash,
        "authorization_id": authorization_id,
        "consumed_at": consumed_at.isoformat(),
    }
    record = {
        **payload,
        "record_hash": canonical_autonomy_hash(payload),
    }
    canonical = _canonical_json(record)
    destination = _authorization_consumed_marker_path(root, grant_hash)
    _write_bytes(canonical, None, destination, None)


def owner_issues_exact_publication_authorization(
    grant: OwnerRepresentationGrant,
    *,
    authorization_id: str | None = None,
    issued_at: datetime | None = None,
    expires_at: datetime | None = None,
    authority_root: Path | None = None,
    owner_key_id: str | None = None,
    owner_signature: str | None = None,
) -> OwnerExactPublicationAuthorization:
    """Issue one immutable exact Owner authorization for one exact grant."""
    if not isinstance(grant, OwnerRepresentationGrant):
        raise TypeError("grant must be a validated OwnerRepresentationGrant")
    if grant.revoked_at is not None:
        raise OwnerRepresentationGrantBlocked(OwnerRepresentationReason.GRANT_REVOKED.value)
    if grant.superseded_by is not None:
        raise OwnerRepresentationGrantBlocked(OwnerRepresentationReason.GRANT_SUPERSEDED.value)
    effective_now = issued_at if issued_at is not None else datetime.now(timezone.utc)
    if not isinstance(effective_now, datetime) or effective_now.tzinfo is None:
        raise OwnerRepresentationGrantBlocked("EXACT_TIMEZONE_REQUIRED")
    auth_expires = expires_at if expires_at is not None else grant.expires_at
    if not isinstance(auth_expires, datetime) or auth_expires.tzinfo is None:
        raise OwnerRepresentationGrantBlocked("EXACT_TIMEZONE_REQUIRED")
    if auth_expires <= effective_now:
        raise OwnerRepresentationGrantBlocked(
            OwnerRepresentationReason.EXACT_OWNER_AUTHORIZATION_EXPIRED.value
        )
    auth_id = authorization_id or f"auth-{grant.grant_hash}"
    if not owner_key_id or not owner_signature:
        raise OwnerRepresentationGrantBlocked(
            OwnerRepresentationReason.EXACT_OWNER_AUTHORIZATION_REQUIRED.value
        )
    spec = OwnerExactPublicationAuthorizationSpec.model_validate({
        "schema": _AUTHORIZATION_SCHEMA,
        "authorization_id": auth_id,
        "owner_id": grant.owner_id,
        "coordinator_id": grant.coordinator_id,
        "destination": grant.destination,
        "effect": grant.effect,
        "target": grant.target,
        "content_hash": grant.content_hash,
        "purpose": grant.purpose,
        "actor": grant.actor,
        "transport": grant.transport,
        "operation_id": grant.operation_id,
        "grant_hash": grant.grant_hash,
        "owner_key_id": owner_key_id,
        "owner_signature": owner_signature,
        "owner_signature_algorithm": "RSA-SHA256",
        "replay_mode": "ONE_SHOT",
        "issued_at": effective_now,
        "expires_at": auth_expires,
        "revoked_at": grant.revoked_at,
        "revocation_reason": grant.revocation_reason,
        "superseded_by": grant.superseded_by,
    })
    payload = spec.model_dump(mode="json")
    record = {
        **payload,
        "authorization_hash": canonical_autonomy_hash(payload),
    }
    auth = OwnerExactPublicationAuthorization.model_validate(record)
    _verify_owner_signature(auth)
    if authority_root is not None:
        root = Path(authority_root)
        destination = _authorization_path(root, grant.grant_hash)
        canonical = _canonical_json(record)
        _write_bytes(canonical, None, destination, None)
    return auth


def exact_owner_publication_authorization_exists(
    grant_hash: str | None = None,
    *,
    authority_root: Path | None = None,
) -> bool:
    """Return True if an exact unconsumed Owner publication authorization exists."""
    root = (
        Path(authority_root)
        if authority_root is not None
        else DEFAULT_OWNER_REPRESENTATION_AUTHORITY_ROOT
    )
    if grant_hash is not None:
        if not _SHA64_HEX.fullmatch(grant_hash):
            return False
        rec = _load_authorization_for_grant(root, grant_hash)
        if rec is None:
            return False
        if _authorization_consumed(root, grant_hash):
            return False
        return True
    records = _authorization_records(root)
    for rec in records:
        gh = rec.get("grant_hash")
        if gh and isinstance(gh, str) and not _authorization_consumed(root, gh):
            return True
    return False


def validate_exact_owner_authorization(
    grant: OwnerRepresentationGrant,
    owner_authorization: OwnerExactPublicationAuthorization | Mapping[str, Any],
    *,
    authority_root: Path | None = None,
    now: datetime | None = None,
) -> OwnerExactPublicationAuthorization:
    """Validate one exact Owner authorization against one proposed grant."""
    if not isinstance(grant, OwnerRepresentationGrant):
        raise TypeError("grant must be a validated OwnerRepresentationGrant")
    try:
        auth = (
            owner_authorization
            if isinstance(owner_authorization, OwnerExactPublicationAuthorization)
            else OwnerExactPublicationAuthorization.model_validate(owner_authorization)
        )
    except Exception as exc:
        raise OwnerRepresentationGrantBlocked(
            OwnerRepresentationReason.EXACT_OWNER_AUTHORIZATION_REJECTED.value
        ) from exc

    effective_now = now if now is not None else datetime.now(timezone.utc)
    if not isinstance(effective_now, datetime) or effective_now.tzinfo is None:
        raise OwnerRepresentationGrantBlocked("EXACT_TIMEZONE_REQUIRED")
    if effective_now < auth.issued_at:
        raise OwnerRepresentationGrantBlocked(
            OwnerRepresentationReason.EXACT_OWNER_AUTHORIZATION_REJECTED.value
        )
    if effective_now >= auth.expires_at:
        raise OwnerRepresentationGrantBlocked(
            OwnerRepresentationReason.EXACT_OWNER_AUTHORIZATION_EXPIRED.value
        )
    if auth.revoked_at is not None:
        raise OwnerRepresentationGrantBlocked(
            OwnerRepresentationReason.EXACT_OWNER_AUTHORIZATION_REVOKED.value
        )
    if auth.grant_hash != grant.grant_hash:
        raise OwnerRepresentationGrantBlocked(
            OwnerRepresentationReason.EXACT_OWNER_AUTHORIZATION_MISMATCH.value
        )
    if auth.owner_id != grant.owner_id:
        raise OwnerRepresentationGrantBlocked(
            OwnerRepresentationReason.EXACT_OWNER_AUTHORIZATION_MISMATCH.value
        )
    if auth.coordinator_id != grant.coordinator_id:
        raise OwnerRepresentationGrantBlocked(
            OwnerRepresentationReason.EXACT_OWNER_AUTHORIZATION_MISMATCH.value
        )
    if auth.destination != grant.destination:
        raise OwnerRepresentationGrantBlocked(
            OwnerRepresentationReason.EXACT_OWNER_AUTHORIZATION_MISMATCH.value
        )
    if auth.effect != grant.effect:
        raise OwnerRepresentationGrantBlocked(
            OwnerRepresentationReason.EXACT_OWNER_AUTHORIZATION_MISMATCH.value
        )
    if auth.target != grant.target:
        raise OwnerRepresentationGrantBlocked(
            OwnerRepresentationReason.EXACT_OWNER_AUTHORIZATION_MISMATCH.value
        )
    if auth.content_hash != grant.content_hash:
        raise OwnerRepresentationGrantBlocked(
            OwnerRepresentationReason.EXACT_OWNER_AUTHORIZATION_MISMATCH.value
        )
    if auth.purpose != grant.purpose:
        raise OwnerRepresentationGrantBlocked(
            OwnerRepresentationReason.EXACT_OWNER_AUTHORIZATION_MISMATCH.value
        )
    if auth.actor != grant.actor:
        raise OwnerRepresentationGrantBlocked(
            OwnerRepresentationReason.EXACT_OWNER_AUTHORIZATION_MISMATCH.value
        )
    if auth.transport != grant.transport:
        raise OwnerRepresentationGrantBlocked(
            OwnerRepresentationReason.EXACT_OWNER_AUTHORIZATION_MISMATCH.value
        )
    if auth.operation_id != grant.operation_id:
        raise OwnerRepresentationGrantBlocked(
            OwnerRepresentationReason.EXACT_OWNER_AUTHORIZATION_MISMATCH.value
        )
    if auth.replay_mode != "ONE_SHOT":
        raise OwnerRepresentationGrantBlocked(
            OwnerRepresentationReason.STANDING_EXTERNAL_GRANT_NOT_SUPPORTED.value
        )

    if authority_root is not None:
        root = Path(authority_root)
        if _authorization_consumed(root, grant.grant_hash):
            raise OwnerRepresentationGrantBlocked(
                OwnerRepresentationReason.EXACT_OWNER_AUTHORIZATION_CONSUMED.value
            )
        disk_rec = _load_authorization_for_grant(root, grant.grant_hash)
        if disk_rec is None:
            raise OwnerRepresentationGrantBlocked(
                OwnerRepresentationReason.EXACT_OWNER_AUTHORIZATION_REQUIRED.value
            )
        if disk_rec.get("authorization_hash") != auth.authorization_hash:
            raise OwnerRepresentationGrantBlocked(
                OwnerRepresentationReason.EXACT_OWNER_AUTHORIZATION_MISMATCH.value
            )
    _verify_owner_signature(auth)
    return auth


def consume_exact_owner_authorization(
    grant: OwnerRepresentationGrant,
    owner_authorization: OwnerExactPublicationAuthorization | Mapping[str, Any] | None = None,
    *,
    authority_root: Path | None = None,
    standing_grant_path: Path | None = None,
    requested_at: datetime | None = None,
    expires_at: datetime | None = None,
) -> dict[str, Any]:
    """Consume one exact Owner authorization to mint a sealed issuance permit."""
    root = (
        Path(authority_root)
        if authority_root is not None
        else DEFAULT_OWNER_REPRESENTATION_AUTHORITY_ROOT
    )
    return mint_owner_representation_publication_issuance_permit(
        grant,
        authority_root=root,
        standing_grant_path=standing_grant_path,
        requested_at=requested_at,
        expires_at=expires_at,
        owner_authorization=owner_authorization,
    )


def mint_owner_representation_publication_issuance_permit(
    grant: OwnerRepresentationGrant,
    *,
    authority_root: Path,
    standing_grant_path: Path | None = None,
    requested_at: datetime | None = None,
    expires_at: datetime | None = None,
    owner_authorization: OwnerExactPublicationAuthorization | Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Mint the exact sealed one-shot issuance permit for one owned grant."""
    if not isinstance(grant, OwnerRepresentationGrant):
        raise TypeError("grant must be a validated OwnerRepresentationGrant")
    if grant.revoked_at is not None:
        raise OwnerRepresentationGrantBlocked(OwnerRepresentationReason.GRANT_REVOKED.value)
    if grant.superseded_by is not None:
        raise OwnerRepresentationGrantBlocked(OwnerRepresentationReason.GRANT_SUPERSEDED.value)
    effective_now = requested_at if requested_at is not None else datetime.now(timezone.utc)
    if not isinstance(effective_now, datetime) or effective_now.tzinfo is None:
        raise OwnerRepresentationGrantBlocked("EXACT_TIMEZONE_REQUIRED")
    permits_root = Path(authority_root)
    if _load_permit_for_grant(permits_root, grant.grant_hash) is not None:
        raise OwnerRepresentationGrantBlocked(OwnerRepresentationReason.PERMIT_ALREADY_MINTED.value)

    if owner_authorization is None:
        disk_rec = _load_authorization_for_grant(permits_root, grant.grant_hash)
        if disk_rec is None:
            raise OwnerRepresentationGrantBlocked(
                OwnerRepresentationReason.EXACT_OWNER_AUTHORIZATION_REQUIRED.value
            )
        owner_authorization = OwnerExactPublicationAuthorization.model_validate(disk_rec)

    auth = validate_exact_owner_authorization(
        grant,
        owner_authorization,
        authority_root=permits_root,
        now=effective_now,
    )

    try:
        allowed = authorize_owner_representation_grant_issuance(
            grant,
            standing_grant_path=standing_grant_path,
            requested_at=effective_now,
        )
    except OwnerRepresentationGrantStoreError:
        raise
    except StandingGrantReceiptError as exc:
        raise OwnerRepresentationGrantStoreError(f"ISSUANCE_AUTHORITY_NOT_LIVE:{exc}") from exc
    standing_receipt_hash = str(allowed.get("grant_receipt_hash"))
    permit_expires = expires_at if expires_at is not None else grant.expires_at
    if not isinstance(permit_expires, datetime) or permit_expires.tzinfo is None:
        raise OwnerRepresentationGrantBlocked("EXACT_TIMEZONE_REQUIRED")
    destination = _permit_path(permits_root, standing_receipt_hash)
    payload = {
        "schema": _PERMIT_SCHEMA,
        "permit_id": f"permit-{grant.grant_hash}",
        "grant_hash": grant.grant_hash,
        "authorization_id": auth.authorization_id,
        "authorization_hash": auth.authorization_hash,
        "action": str(allowed.get("action")),
        "effect": allowed.get("effect"),
        "effect_hash": str(allowed.get("effect_hash")),
        "grant_receipt_hash": standing_receipt_hash,
        "owner_id": str(allowed.get("owner_id")),
        "coordinator_id": str(allowed.get("coordinator_id")),
        "repository": allowed.get("repository"),
        "requested_at": effective_now.isoformat(),
        "expires_at": permit_expires.isoformat(),
    }
    record = {
        **payload,
        "permit_hash": canonical_autonomy_hash(payload),
    }
    canonical = _canonical_json(record)
    try:
        _write_bytes(canonical, None, destination, None)
    except StandingGrantReceiptError as exc:
        if str(exc) in {"SUPERSEDES_HASH_REQUIRED_FOR_REPLACE", "EXISTS_NO_CAS"}:
            raise OwnerRepresentationGrantBlocked(
                f"{OwnerRepresentationReason.ISSUANCE_PERMIT_SLOT_CONSUMED.value}:"
                "grant_b_receipt_does_not_exist"
            ) from exc
        raise OwnerRepresentationGrantStoreError(str(exc)) from exc

    try:
        _write_authorization_consumed_marker(
            permits_root,
            grant_hash=grant.grant_hash,
            authorization_id=auth.authorization_id,
            consumed_at=effective_now,
        )
    except StandingGrantReceiptError as exc:
        if str(exc) in {"SUPERSEDES_HASH_REQUIRED_FOR_REPLACE", "EXISTS_NO_CAS"}:
            raise OwnerRepresentationGrantBlocked(
                OwnerRepresentationReason.EXACT_OWNER_AUTHORIZATION_CONSUMED.value
            ) from exc
        raise OwnerRepresentationGrantStoreError(str(exc)) from exc
    return record


def _write_consumed_marker(
    root: Path,
    *,
    grant_hash: str,
    permit_id: str,
    consumed_at: datetime,
    destination: Path | None = None,
) -> None:
    """Persist the fail-closed consumption marker for one issued grant.

    The marker is sealed the same way as every other authority record and must
    be written before the grant receipt.
    """
    payload = {
        "schema": _PERMIT_CONSUMED_SCHEMA,
        "grant_hash": grant_hash,
        "permit_id": permit_id,
        "consumed_at": consumed_at.isoformat(),
    }
    record = {
        **payload,
        "record_hash": canonical_autonomy_hash(payload),
    }
    canonical = _canonical_json(record)
    _write_bytes(canonical, None, destination, None)


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
    supersession, then the stored one-shot issuance permit, then live
    standing-grant revalidation, and only then the pure field-for-field
    semantic evaluation.

    Issuance-authority revalidation requires the stored sealed one-shot
    issuance permit (``ISSUANCE_AUTHORIZATION_REQUIRED`` if none was minted and
    ``TAMPERED`` if the receipt's ``permit_id`` does not match the permit it
    names), then re-derives the standing-grant authority fresh at the current
    instant.  A revoked/unreadable standing grant fails
    ``ISSUANCE_AUTHORITY_NOT_LIVE``, and a replaced standing grant whose
    binding fields changed fails ``ISSUANCE_AUTHORITY_CHANGED``.  The permit's
    time-varying ``requested_at`` is excluded from the invariant comparison
    because the clock legitimately advances between issuance and publication;
    the consumption fence lives in the store's ``permits/consumed/`` markers,
    so a replayed receipt is caught by the publisher before it reaches this
    evaluator.
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
    permit = _load_permit_for_grant(root, grant_hash)
    if permit is None:
        return _blocked_decision(
            proposal,
            OwnerRepresentationReason.ISSUANCE_AUTHORIZATION_REQUIRED,
            grant_hash=grant_hash,
        )
    if record.get("permit_id") != permit.get("permit_id"):
        raise OwnerRepresentationGrantStoreError("TAMPERED")
    if record.get("authorization_id") != permit.get("authorization_id"):
        raise OwnerRepresentationGrantStoreError("TAMPERED")

    auth_rec = _load_authorization_for_grant(root, grant_hash)
    if auth_rec is None:
        return _blocked_decision(
            proposal,
            OwnerRepresentationReason.EXACT_OWNER_AUTHORIZATION_REQUIRED,
            grant_hash=grant_hash,
        )
    if auth_rec.get("authorization_hash") != permit.get("authorization_hash"):
        return _blocked_decision(
            proposal,
            OwnerRepresentationReason.EXACT_OWNER_AUTHORIZATION_MISMATCH,
            grant_hash=grant_hash,
        )
    try:
        auth = OwnerExactPublicationAuthorization.model_validate(auth_rec)
    except Exception as exc:
        raise OwnerRepresentationGrantStoreError("TAMPERED") from exc
    try:
        _verify_owner_signature(auth)
    except OwnerRepresentationGrantBlocked:
        return _blocked_decision(
            proposal,
            OwnerRepresentationReason.EXACT_OWNER_AUTHORIZATION_REJECTED,
            grant_hash=grant_hash,
        )
    if auth.revoked_at is not None:
        return _blocked_decision(
            proposal,
            OwnerRepresentationReason.EXACT_OWNER_AUTHORIZATION_REVOKED,
            grant_hash=grant_hash,
        )
    effective_now = now if now is not None else datetime.now(timezone.utc)
    if effective_now >= auth.expires_at:
        return _blocked_decision(
            proposal,
            OwnerRepresentationReason.EXACT_OWNER_AUTHORIZATION_EXPIRED,
            grant_hash=grant_hash,
        )
    try:
        permit_valid = _parse_iso(permit["requested_at"])
        permit_expires = _parse_iso(permit["expires_at"])
    except KeyError as exc:
        raise OwnerRepresentationGrantStoreError("MALFORMED") from exc
    if effective_now < permit_valid:
        raise OwnerRepresentationGrantStoreError("ISSUANCE_AUTHORITY_NOT_LIVE:PERMIT_NOT_YET_VALID")
    if effective_now >= permit_expires:
        raise OwnerRepresentationGrantStoreError("ISSUANCE_AUTHORITY_NOT_LIVE:PERMIT_EXPIRED")
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
    invariant_fields = (
        "grant_receipt_hash",
        "owner_id",
        "coordinator_id",
        "repository",
        "effect_hash",
        "action",
    )
    for key in invariant_fields:
        if fresh.get(key) != permit.get(key):
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
    standing-grant receipt used to mint/re-derive the one-shot issuance
    permit; production defaults to the single canonical standing-grant path.
    Explicit roots/paths are for tests/operator tooling only.
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
        issuance_permit: Mapping[str, Any],
        supersedes_grant_hash: str | None = None,
        requested_at: datetime | None = None,
    ) -> Path:
        """Persist one validated Owner-supplied grant as a durable receipt.

        ``issuance_permit`` is the sealed
        ``nexus.owner_representation_publication_issuance_permit.v1`` permit
        produced by :func:`mint_owner_representation_publication_issuance_permit`
        for exactly this grant.  The store ignores every caller-supplied field
        except the grant-hash mapping, re-reads the permit sealed from disk
        (``permits/<standing_grant_receipt_hash>.json``), re-derives the
        standing-grant authority from the canonical durable Owner standing
        grant, and binds the grant identity and effect exactly, so a
        worker/agent can never mint an authority-backed receipt for a grant it
        constructed itself.

        The first accepted issuance writes a
        ``permits/consumed/<grant_hash>.json`` consumption marker before the
        grant receipt (fail-closed: a failed receipt write never consumes the
        permit).  Any later issuance attempt is refused
        (``GRANT_ALREADY_ISSUED`` when the receipt still exists, ``GRANT_REUSED``
        when the receipt was deleted but the marker remains).

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
        if issuance_permit is None:
            raise OwnerRepresentationGrantBlocked(
                OwnerRepresentationReason.ISSUANCE_AUTHORIZATION_REQUIRED.value
            )
        if not isinstance(issuance_permit, Mapping) or (
            issuance_permit.get("grant_hash") != grant.grant_hash
        ):
            raise OwnerRepresentationGrantBlocked(
                OwnerRepresentationReason.ISSUANCE_AUTHORIZATION_REJECTED.value
            )
        permit = _load_permit_for_grant(self.root, grant.grant_hash)
        if permit is None:
            raise OwnerRepresentationGrantBlocked(
                OwnerRepresentationReason.ISSUANCE_AUTHORIZATION_REJECTED.value
            )
        # Exact identity and effect bindings against the sealed disk permit.
        if grant.owner_id != str(permit.get("owner_id")):
            raise OwnerRepresentationGrantBlocked(
                OwnerRepresentationReason.ISSUANCE_AUTHORIZATION_REJECTED.value
            )
        if grant.coordinator_id != str(permit.get("coordinator_id")):
            raise OwnerRepresentationGrantBlocked(
                OwnerRepresentationReason.ISSUANCE_AUTHORIZATION_REJECTED.value
            )
        if grant.issued_by != str(permit.get("owner_id")):
            raise OwnerRepresentationGrantBlocked(
                OwnerRepresentationReason.ISSUANCE_AUTHORIZATION_REJECTED.value
            )
        if canonical_autonomy_hash(owner_representation_issuance_effect(grant)) != permit.get(
            "effect_hash"
        ):
            raise OwnerRepresentationGrantBlocked(
                OwnerRepresentationReason.ISSUANCE_AUTHORIZATION_REJECTED.value
            )
        try:
            allowed = authorize_owner_representation_grant_issuance(
                grant,
                standing_grant_path=self.standing_grant_path,
                requested_at=now,
            )
        except OwnerRepresentationGrantBlocked:
            raise
        except StandingGrantReceiptError as exc:
            raise OwnerRepresentationGrantBlocked(
                OwnerRepresentationReason.ISSUANCE_AUTHORITY_NOT_LIVE.value
            ) from exc
        invariant_fields = (
            "grant_receipt_hash",
            "owner_id",
            "coordinator_id",
            "repository",
            "effect_hash",
            "action",
        )
        for key in invariant_fields:
            if allowed.get(key) != permit.get(key):
                raise OwnerRepresentationGrantBlocked(
                    OwnerRepresentationReason.ISSUANCE_AUTHORITY_CHANGED.value
                )
        auth_id = permit.get("authorization_id")
        auth_hash = permit.get("authorization_hash")
        if not auth_id or not auth_hash:
            raise OwnerRepresentationGrantBlocked(
                OwnerRepresentationReason.EXACT_OWNER_AUTHORIZATION_REQUIRED.value
            )
        auth_rec = _load_authorization_for_grant(self.root, grant.grant_hash)
        if auth_rec is None:
            raise OwnerRepresentationGrantBlocked(
                OwnerRepresentationReason.EXACT_OWNER_AUTHORIZATION_REQUIRED.value
            )
        if (
            auth_rec.get("authorization_hash") != auth_hash
            or auth_rec.get("authorization_id") != auth_id
        ):
            raise OwnerRepresentationGrantBlocked(
                OwnerRepresentationReason.EXACT_OWNER_AUTHORIZATION_MISMATCH.value
            )
        auth = OwnerExactPublicationAuthorization.model_validate(auth_rec)
        if auth.revoked_at is not None:
            raise OwnerRepresentationGrantBlocked(
                OwnerRepresentationReason.EXACT_OWNER_AUTHORIZATION_REVOKED.value
            )
        if now >= auth.expires_at:
            raise OwnerRepresentationGrantBlocked(
                OwnerRepresentationReason.EXACT_OWNER_AUTHORIZATION_EXPIRED.value
            )
        if _permit_consumed(self.root, grant.grant_hash):
            raise OwnerRepresentationGrantBlocked(OwnerRepresentationReason.GRANT_REUSED.value)
        if _has_revocation(self.root, grant.grant_hash):
            raise OwnerRepresentationGrantBlocked(OwnerRepresentationReason.GRANT_REVOKED.value)

        try:
            _write_consumed_marker(
                self.root,
                grant_hash=grant.grant_hash,
                permit_id=str(permit.get("permit_id")),
                consumed_at=now,
                destination=_consumed_marker_path(self.root, grant.grant_hash),
            )
        except StandingGrantReceiptError as exc:
            if str(exc) in {"SUPERSEDES_HASH_REQUIRED_FOR_REPLACE", "EXISTS_NO_CAS"}:
                raise OwnerRepresentationGrantBlocked(
                    OwnerRepresentationReason.GRANT_REUSED.value
                ) from exc
            raise OwnerRepresentationGrantStoreError(str(exc)) from exc
        payload = {
            "schema": _RECEIPT_SCHEMA,
            "grant": grant.model_dump(mode="json"),
            "supersedes_grant_hash": supersedes_grant_hash,
            "permit_id": str(permit.get("permit_id")),
            "authorization_id": str(auth_id),
        }
        record = {
            **payload,
            "receipt_hash": canonical_autonomy_hash(payload),
        }
        canonical = _canonical_json(record)
        try:
            _write_bytes(canonical, None, destination, None)
        except StandingGrantReceiptError as exc:
            if str(exc) in {"SUPERSEDES_HASH_REQUIRED_FOR_REPLACE", "EXISTS_NO_CAS"}:
                raise OwnerRepresentationGrantBlocked(
                    OwnerRepresentationReason.GRANT_ALREADY_ISSUED.value
                ) from exc
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
        permit = None
        consumed = False
        auth_rec = None
        auth_consumed = False
        try:
            if _has_revocation(self.root, grant_hash):
                status = "REVOKED"
            elif _superseding_grant_hash(self.root, grant_hash) is not None:
                status = "SUPERSEDED"
            permit = _load_permit_for_grant(self.root, grant_hash)
            consumed = _permit_consumed(self.root, grant_hash)
            auth_rec = _load_authorization_for_grant(self.root, grant_hash)
            auth_consumed = _authorization_consumed(self.root, grant_hash)
        except OwnerRepresentationGrantStoreError:
            status = "INTEGRITY_ERROR"
            permit = None
            consumed = False
            auth_rec = None
            auth_consumed = False
        return {
            "grant_hash": grant_hash,
            "status": status,
            "grant": record["grant"],
            "supersedes_grant_hash": record.get("supersedes_grant_hash"),
            "issued_with_authority": permit is not None,
            "permit_minted": permit is not None,
            "permit_consumed": consumed,
            "owner_authorization_present": auth_rec is not None,
            "owner_authorization_consumed": auth_consumed,
        }


def issue_owner_representation_grant(
    grant: OwnerRepresentationGrant,
    *,
    requested_at: datetime | None = None,
    supersedes_grant_hash: str | None = None,
    owner_authorization: OwnerExactPublicationAuthorization | Mapping[str, Any] | None = None,
) -> Path:
    """Persist one one-shot Owner-representation grant to the canonical root.

    Mints the exact sealed issuance permit bound to the durable Owner standing
    grant and the exact Owner publication authorization at one fixed
    ``requested_at`` and passes it to ``issue``, which re-reads the permit sealed
    from disk and re-derives the same standing-grant authority.  A self-authorized
    worker can never mint an authority-backed receipt for a grant it constructed
    itself.
    """
    now = requested_at if requested_at is not None else datetime.now(timezone.utc)
    permit = consume_exact_owner_authorization(
        grant,
        owner_authorization=owner_authorization,
        authority_root=DEFAULT_OWNER_REPRESENTATION_AUTHORITY_ROOT,
        requested_at=now,
    )
    return OwnerRepresentationGrantStore().issue(
        grant,
        issuance_permit=permit,
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
    "OwnerExactPublicationAuthorization",
    "OwnerRepresentationGrantBlocked",
    "OwnerRepresentationGrantReceipt",
    "OwnerRepresentationGrantRevocation",
    "OwnerRepresentationGrantStore",
    "OwnerRepresentationGrantStoreError",
    "authorize_owner_representation_grant_issuance",
    "authorize_owner_representation_publication",
    "consume_exact_owner_authorization",
    "exact_owner_publication_authorization_exists",
    "inspect_owner_representation_grant",
    "issue_owner_representation_grant",
    "load_owner_representation_grant",
    "mint_owner_representation_publication_issuance_permit",
    "owner_issues_exact_publication_authorization",
    "owner_representation_issuance_effect",
    "revoke_owner_representation_grant",
    "validate_exact_owner_authorization",
]
