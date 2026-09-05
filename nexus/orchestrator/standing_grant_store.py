"""Canonical durable standing-grant receipt store and loader.

This module is a carrier only: it persists and validates one machine-local
Owner receipt and hands it to the existing pure semantic evaluator. It never
issues a live grant on its own, never mutates authorization state during
evaluation, and creates no second merge authority. Atomic durable write and
restrictive file modes guard the single canonical receipt path.

Production load/evaluate use the single canonical path only. Explicit temp
paths exist solely on private ``_*`` helpers for the security test matrix and
never select an alternative authority root.
"""

from __future__ import annotations

import errno
import fcntl
import json
import os
import pwd
import re
import stat
import tempfile
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal, Mapping
from uuid import uuid4

from pydantic import (
    BaseModel,
    ConfigDict,
    StrictStr,
    field_validator,
    model_validator,
)

from nexus.contracts.autonomy_goal import (
    AutonomyActionClass,
    RepositoryIdentity,
    StandingGrantContext,
    canonical_autonomy_hash,
)
from nexus.orchestrator.autonomy_policy import (
    StandingGrantDecision,
    StandingGrantRequest,
    evaluate_standing_grant_decision,
)

_HOME = pwd.getpwuid(os.getuid()).pw_dir
DEFAULT_RECEIPT_PATH = Path(_HOME) / ".local/state/nexus/authority/standing-grant.json"
DEFAULT_TRANSITIONS_DIR = DEFAULT_RECEIPT_PATH.parent / "transitions"
_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_SHA64_HEX = re.compile(r"^[0-9a-f]{64}$")
_MAX_RECEIPT_BYTES = 16 * 1024


class StandingGrantReceiptError(Exception):
    """Fail-closed error for a missing, malformed, tampered, or unsafe receipt."""


class _FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class StandingGrantReceipt(_FrozenModel):
    """Validated machine-local receipt binding one immutable granting context."""

    schema: Literal["nexus.standing_grant_receipt.v1"] = "nexus.standing_grant_receipt.v1"
    grant_id: StrictStr
    context: StandingGrantContext
    receipt_hash: StrictStr
    supersedes_grant_hash: StrictStr | None = None

    @field_validator("grant_id")
    @classmethod
    def validate_grant_id(cls, value: str) -> str:
        if not _SAFE_ID.fullmatch(value) or value != value.strip():
            raise ValueError("GRANT_ID_INVALID")
        return value

    @field_validator("supersedes_grant_hash")
    @classmethod
    def validate_supersedes(cls, value: str | None) -> str | None:
        if value is not None and not _SHA64_HEX.fullmatch(value):
            raise ValueError("SUPERSEDES_HASH_INVALID")
        return value

    @field_validator("receipt_hash")
    @classmethod
    def validate_receipt_hash(cls, value: str) -> str:
        if not _SHA64_HEX.fullmatch(value):
            raise ValueError("RECEIPT_HASH_INVALID")
        return value

    @model_validator(mode="after")
    def validate_receipt(self) -> "StandingGrantReceipt":
        # Self-reference detection by content is not possible without a competitor
        # store/state; the caller enforces predecessor hash binding at write CAS.
        payload = self.model_dump(mode="json", exclude={"receipt_hash"})
        if self.receipt_hash != canonical_autonomy_hash(payload):
            raise ValueError("RECEIPT_HASH_INVALID")
        return self

    @classmethod
    def issue(
        cls,
        *,
        grant_id: str,
        context: StandingGrantContext,
        supersedes_grant_hash: str | None = None,
    ) -> "StandingGrantReceipt":
        payload = {
            "schema": "nexus.standing_grant_receipt.v1",
            "grant_id": grant_id,
            "context": context.model_dump(mode="json"),
            "supersedes_grant_hash": supersedes_grant_hash,
        }
        return cls.model_validate({
            **payload,
            "receipt_hash": canonical_autonomy_hash(payload),
        })


def _canonical_json(payload: dict[str, Any]) -> str:
    return json.dumps(
        dict(payload),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
        allow_nan=False,
    )


def _assert_dir_chain_safe(directory: Path, *, create: bool) -> None:
    """Validate the directory chain from target parent to root.

    Every ancestor must be a real, non-symlink directory that is not group or
    world writable and is owned by the current uid or root. The authority leaf
    (the store's own directory) additionally requires exact mode 0700 and
    current-uid ownership.
    """
    missing: list[Path] = []
    current = directory
    while not current.exists():
        missing.append(current)
        parent = current.parent
        if parent == current:
            break
        current = parent
    # Validate the first existing ancestor itself, then every ancestor to root.
    node = current
    while True:
        _check_dir(node, strict_leaf=(node == directory))
        if node == node.parent:
            break
        if node.parent == node:
            break
        node = node.parent
    if create:
        for path in reversed(missing):
            try:
                path.mkdir(mode=0o700)
            except FileExistsError:
                pass
            _check_dir(path, strict_leaf=True)
        # The authority leaf is store-owned: enforce exact 0700 + uid.
        _check_dir(directory, strict_leaf=True)
    else:
        # Read path: the authority leaf must already exist and be exact 0700.
        _check_dir(directory, strict_leaf=True)


def _check_dir(directory: Path, *, strict_leaf: bool = False) -> None:
    try:
        st = directory.lstat()
    except OSError as exc:
        raise StandingGrantReceiptError("PARENT_DIRECTORY_UNSAFE") from exc
    if stat.S_ISLNK(st.st_mode) or not stat.S_ISDIR(st.st_mode):
        raise StandingGrantReceiptError("PARENT_SYMLINK_OR_NON_DIRECTORY")
    uid = os.geteuid()
    if strict_leaf:
        if st.st_uid != uid:
            raise StandingGrantReceiptError("PARENT_OWNER_MISMATCH")
        if stat.S_IMODE(st.st_mode) != 0o700:
            raise StandingGrantReceiptError("PARENT_MODE_NOT_0700")
        return
    # Generic ancestor: uid or root, never group/world writable.
    if st.st_uid not in (uid, 0):
        raise StandingGrantReceiptError("PARENT_OWNER_MISMATCH")
    if stat.S_IMODE(st.st_mode) & 0o022 and not (st.st_uid == 0 and st.st_mode & stat.S_ISVTX):
        raise StandingGrantReceiptError("PARENT_GROUP_OR_WORLD_WRITABLE")


def _open_receipt_fd(path: Path) -> int:
    """Open a regular file with O_NOFOLLOW, failing closed on symlink."""
    path = Path(path)
    path = path if path.is_absolute() else path.absolute()
    try:
        if path.is_symlink():
            raise StandingGrantReceiptError("NOT_REGULAR_FILE")
    except OSError as exc:
        raise StandingGrantReceiptError("RECEIPT_READ_FAILED") from exc
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        return os.open(str(path), flags)
    except OSError as exc:
        if exc.errno == errno.ELOOP:
            raise StandingGrantReceiptError("NOT_REGULAR_FILE") from exc
        if exc.errno == errno.ENOENT:
            raise StandingGrantReceiptError("RECEIPT_MISSING") from exc
        raise StandingGrantReceiptError("RECEIPT_OPEN_FAILED") from exc


def _read_current_hash_nofollow(path: Path) -> str:
    """Read and fully validate the existing receipt, returning its real hash.

    Uses a no-follow fd (never Path.read_text) and re-validates canonical JSON,
    the body receipt hash, and the stored 64-char hash before returning it.
    """
    fd = _open_receipt_fd(path)
    try:
        fst = os.fstat(fd)
    except OSError as exc:
        os.close(fd)
        raise StandingGrantReceiptError("RECEIPT_READ_FAILED") from exc
    if not stat.S_ISREG(fst.st_mode) or fst.st_uid != os.geteuid():
        os.close(fd)
        raise StandingGrantReceiptError("NOT_REGULAR_FILE")
    if stat.S_IMODE(fst.st_mode) != 0o600:
        os.close(fd)
        raise StandingGrantReceiptError("UNSAFE_PERMISSIONS")
    if fst.st_size > _MAX_RECEIPT_BYTES:
        os.close(fd)
        raise StandingGrantReceiptError("RECEIPT_TOO_LARGE")
    raw = _read_all_fd(fd, _MAX_RECEIPT_BYTES + 1)
    os.close(fd)
    try:
        text = raw.decode("utf-8")
        parsed = json.loads(text, object_pairs_hook=_reject_duplicates)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise StandingGrantReceiptError("MALFORMED") from exc
    if not isinstance(parsed, dict):
        raise StandingGrantReceiptError("MALFORMED")
    if parsed.get("schema") != "nexus.standing_grant_receipt.v1":
        raise StandingGrantReceiptError("MALFORMED")
    if text.endswith("\n"):
        text = text[:-1]
    if "\x00" in text or "\n" in text:
        raise StandingGrantReceiptError("NONCANONICAL_SERIALIZATION")
    if _canonical_json(parsed) != text:
        raise StandingGrantReceiptError("NONCANONICAL_SERIALIZATION")
    stored_hash = parsed.get("receipt_hash")
    if not isinstance(stored_hash, str) or len(stored_hash) != 64:
        raise StandingGrantReceiptError("TAMPERED")
    body = {k: v for k, v in parsed.items() if k != "receipt_hash"}
    if canonical_autonomy_hash(body) != stored_hash:
        raise StandingGrantReceiptError("TAMPERED")
    return stored_hash


@contextmanager
def _coordination_lock(directory: Path):
    """Hold the authority-directory lock across the complete receipt CAS."""
    lock_path = directory / ".standing-grant.lock"
    flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(str(lock_path), flags, 0o600)
    except OSError as exc:
        if exc.errno == errno.ELOOP:
            raise StandingGrantReceiptError("LOCK_NOT_REGULAR_FILE") from exc
        raise StandingGrantReceiptError("LOCK_OPEN_FAILED") from exc
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode) or st.st_uid != os.geteuid():
            raise StandingGrantReceiptError("LOCK_NOT_REGULAR_FILE")
        if stat.S_IMODE(st.st_mode) != 0o600:
            raise StandingGrantReceiptError("LOCK_UNSAFE_PERMISSIONS")
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    except OSError as exc:
        raise StandingGrantReceiptError("LOCK_FAILED") from exc
    finally:
        os.close(fd)


def _write_bytes_locked(
    canonical: str,
    supersedes_grant_hash: str | None,
    destination: Path,
    expected: str | None,
) -> None:
    present = os.path.lexists(destination)
    if present:
        # Replacing an existing receipt requires exact predecessor binding.
        if supersedes_grant_hash is None:
            raise StandingGrantReceiptError("SUPERSEDES_HASH_REQUIRED_FOR_REPLACE")
        if expected is None:
            raise StandingGrantReceiptError("EXISTS_NO_CAS")
        if supersedes_grant_hash != expected:
            raise StandingGrantReceiptError("SUPERSEDES_CAS_MISMATCH")
        current = _read_current_hash_nofollow(destination)
        if current != expected:
            raise StandingGrantReceiptError("STALE_WRITER_CAS_MISMATCH")
    else:
        # Initial write: neither a predecessor hash nor a CAS may be supplied.
        if supersedes_grant_hash is not None or expected is not None:
            raise StandingGrantReceiptError("INITIAL_WRITE_NO_SUPERSEDES")
    fd, tmp_name = tempfile.mkstemp(prefix=".standing-grant-", dir=str(destination.parent))
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb") as handle:
            handle.write(canonical.encode("utf-8") + b"\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, destination)
        os.chmod(destination, 0o600)
        # fsync the parent directory so the rename survives a crash.
        parent_fd = os.open(str(destination.parent), os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(parent_fd)
        finally:
            os.close(parent_fd)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:
            pass
        raise


def _write_bytes(
    canonical: str,
    supersedes_grant_hash: str | None,
    destination: Path,
    expected: str | None,
) -> None:
    _assert_dir_chain_safe(destination.parent, create=True)
    with _coordination_lock(destination.parent):
        _write_bytes_locked(canonical, supersedes_grant_hash, destination, expected)


def write_standing_grant_receipt(
    receipt: StandingGrantReceipt,
    *,
    expected_receipt_hash: str | None = None,
) -> Path:
    """Atomically persist one validated standing-grant receipt to the canonical path.

    This is an explicit bootstrap/operator write action. It accepts only a
    validated :class:`StandingGrantReceipt` (never a raw mapping) and never
    evaluates or authorizes any request. ``expected_receipt_hash`` is the CAS
    guard: overwriting an existing receipt requires the caller to name the
    current hash (the predecessor receipt hash bound by ``supersedes_grant_hash``).
    """
    if not isinstance(receipt, StandingGrantReceipt):
        raise TypeError("receipt must be a validated StandingGrantReceipt")
    payload = receipt.model_dump(mode="json")
    canonical = _canonical_json(payload)
    _write_bytes(
        canonical, receipt.supersedes_grant_hash, DEFAULT_RECEIPT_PATH, expected_receipt_hash
    )
    return DEFAULT_RECEIPT_PATH


def _write_standing_grant_receipt_at(
    receipt: StandingGrantReceipt,
    path: Path,
    *,
    expected_receipt_hash: str | None = None,
) -> Path:
    """Test/internal-only writer bound to an explicit path (never production)."""
    payload = receipt.model_dump(mode="json")
    canonical = _canonical_json(payload)
    _write_bytes(canonical, receipt.supersedes_grant_hash, path, expected_receipt_hash)
    return path


def _read_all_fd(fd: int, size: int) -> bytes:
    chunks: list[bytes] = []
    while len(b"".join(chunks)) < size:
        chunk = os.read(fd, size)
        if not chunk:
            break
        chunks.append(chunk)
    return b"".join(chunks)


def _load_receipt_structural_at(path: Path) -> StandingGrantReceipt:
    """Validate receipt structure/integrity without granting current authority.

    This helper intentionally does not evaluate issuance, expiry, or revocation.
    It exists so read-only operator inspection can distinguish a structurally
    valid but inactive receipt from malformed/tampered state without creating a
    second authorization evaluator.
    """
    fd = _open_receipt_fd(path)
    try:
        fst = os.fstat(fd)
    except OSError as exc:
        if fd >= 0:
            os.close(fd)
        raise StandingGrantReceiptError("RECEIPT_READ_FAILED") from exc
    if stat.S_ISLNK(fst.st_mode) or not stat.S_ISREG(fst.st_mode):
        os.close(fd)
        raise StandingGrantReceiptError("NOT_REGULAR_FILE")
    if fst.st_uid != os.geteuid():
        os.close(fd)
        raise StandingGrantReceiptError("RECEIPT_OWNER_MISMATCH")
    if stat.S_IMODE(fst.st_mode) != 0o600:
        os.close(fd)
        raise StandingGrantReceiptError("UNSAFE_PERMISSIONS")
    if fst.st_size > _MAX_RECEIPT_BYTES:
        os.close(fd)
        raise StandingGrantReceiptError("RECEIPT_TOO_LARGE")
    raw = _read_all_fd(fd, fst.st_size)
    os.close(fd)
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise StandingGrantReceiptError("MALFORMED") from exc
    if text.endswith("\n"):
        text = text[:-1]
    if "\x00" in text:
        raise StandingGrantReceiptError("NONCANONICAL_SERIALIZATION")
    if "\n" in text:
        raise StandingGrantReceiptError("NONCANONICAL_SERIALIZATION")
    try:
        parsed = json.loads(text, object_pairs_hook=_reject_duplicates)
    except (json.JSONDecodeError, ValueError) as exc:
        raise StandingGrantReceiptError("MALFORMED") from exc
    if not isinstance(parsed, dict):
        raise StandingGrantReceiptError("MALFORMED")
    if parsed.get("schema") != "nexus.standing_grant_receipt.v1":
        raise StandingGrantReceiptError("MALFORMED")
    if _canonical_json(parsed) != text:
        raise StandingGrantReceiptError("NONCANONICAL_SERIALIZATION")
    stored_hash = parsed.get("receipt_hash")
    if not isinstance(stored_hash, str) or len(stored_hash) != 64:
        raise StandingGrantReceiptError("TAMPERED")
    body = {k: v for k, v in parsed.items() if k != "receipt_hash"}
    if canonical_autonomy_hash(body) != stored_hash:
        raise StandingGrantReceiptError("TAMPERED")
    try:
        return StandingGrantReceipt.model_validate(parsed)
    except Exception as exc:
        raise StandingGrantReceiptError("MALFORMED") from exc


def _load_receipt_at(path: Path, *, now: datetime | None = None) -> StandingGrantReceipt:
    """Validate one receipt from an explicit path using fd-based O_NOFOLLOW reads.

    This is a test/internal helper; production callers must use
    :func:`load_standing_grant_receipt` against the canonical path only.
    """
    receipt = _load_receipt_structural_at(path)
    try:
        now = now if now is not None else datetime.now(timezone.utc)
        if not isinstance(now, datetime) or now.tzinfo is None:
            raise StandingGrantReceiptError("EXACT_TIMEZONE_REQUIRED")
    except StandingGrantReceiptError:
        raise
    if now < receipt.context.issued_at:
        raise StandingGrantReceiptError("NOT_YET_VALID")
    if now >= receipt.context.expires_at:
        raise StandingGrantReceiptError("EXPIRED")
    if receipt.context.revoked_at is not None and receipt.context.revocation_reason is None:
        raise StandingGrantReceiptError("REVOCATION_BINDING_INVALID")
    if receipt.context.revoked_at is not None:
        raise StandingGrantReceiptError("REVOKED")
    return receipt


def _reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("DUPLICATE_KEY")
        result[key] = value
    return result


def inspect_standing_grant_receipt(*, now: datetime | None = None) -> dict[str, Any]:
    """Return a non-authorizing status projection for the canonical receipt.

    The projection never substitutes for :func:`load_standing_grant_receipt` or
    the semantic evaluator.  It exposes only bounded grant metadata needed by a
    fresh coordinator/operator to understand whether durable authority can be
    rehydrated.
    """
    effective_now = now if now is not None else datetime.now(timezone.utc)
    if not isinstance(effective_now, datetime) or effective_now.tzinfo is None:
        raise StandingGrantReceiptError("EXACT_TIMEZONE_REQUIRED")
    try:
        st = DEFAULT_RECEIPT_PATH.lstat()
    except FileNotFoundError:
        return {"schema": "nexus.standing_grant_inspection.v1", "status": "MISSING"}
    except OSError:
        return {
            "schema": "nexus.standing_grant_inspection.v1",
            "status": "INVALID",
            "reason": "RECEIPT_READ_FAILED",
        }
    try:
        if stat.S_ISLNK(st.st_mode):
            raise StandingGrantReceiptError("NOT_REGULAR_FILE")
        _assert_dir_chain_safe(DEFAULT_RECEIPT_PATH.parent, create=False)
        receipt = _load_receipt_structural_at(DEFAULT_RECEIPT_PATH)
    except StandingGrantReceiptError as exc:
        return {
            "schema": "nexus.standing_grant_inspection.v1",
            "status": "INVALID",
            "reason": str(exc),
        }

    context = receipt.context
    if context.revoked_at is not None:
        status = "REVOKED"
    elif effective_now < context.issued_at:
        status = "NOT_YET_VALID"
    elif effective_now >= context.expires_at:
        status = "EXPIRED"
    else:
        status = "VALID"
    return {
        "schema": "nexus.standing_grant_inspection.v1",
        "status": status,
        "grant_id": receipt.grant_id,
        "receipt_hash": receipt.receipt_hash,
        "owner_id": context.owner_id,
        "coordinator_id": context.coordinator_id,
        "repository_id": context.repository.repository_id,
        "canonical_remote": context.repository.canonical_remote,
        "coordination_scope_id": context.thread_id,
        "goal_id": context.goal_id,
        "allowed_actions": [action.value for action in context.allowed_actions],
        "issued_at": context.issued_at.isoformat(),
        "expires_at": context.expires_at.isoformat(),
        "revoked_at": context.revoked_at.isoformat() if context.revoked_at else None,
        "revocation_reason": context.revocation_reason,
    }


def load_standing_grant_receipt(*, now: datetime | None = None) -> StandingGrantReceipt | None:
    """Load and validate the single canonical receipt, or fail closed.

    Returns ``None`` when no receipt exists at the canonical path. Any
    malformed, tampered, unsafe, expired, or revoked receipt raises
    :class:`StandingGrantReceiptError` rather than returning partial evidence.
    """
    try:
        # Use a no-follow lstat so a dangling symlink is a typed unsafe error,
        # never silently treated as "no receipt".
        st = DEFAULT_RECEIPT_PATH.lstat()
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise StandingGrantReceiptError("RECEIPT_READ_FAILED") from exc
    if stat.S_ISLNK(st.st_mode):
        raise StandingGrantReceiptError("NOT_REGULAR_FILE")
    _assert_dir_chain_safe(DEFAULT_RECEIPT_PATH.parent, create=False)
    return _load_receipt_at(DEFAULT_RECEIPT_PATH, now=now)


def rehydrate_durable_standing_grant_request(
    *,
    requested_owner_id: str,
    requested_coordinator_id: str,
    repository: RepositoryIdentity,
    goal_id: str,
    action: AutonomyActionClass,
    requested_at: datetime,
) -> tuple[StandingGrantReceipt, StandingGrantRequest]:
    """Bind a fresh coordinator session to the receipt's durable scope.

    ``StandingGrantContext.thread_id`` is treated here as the durable
    coordination-scope identifier issued by the Owner.  Replaceable chat,
    provider, or agent session identifiers are transport provenance and must not
    be substituted for that authority identifier.  All other identity, action,
    validity, and hash checks remain enforced by the canonical loader/evaluator.
    """
    receipt = load_standing_grant_receipt(now=requested_at)
    if receipt is None:
        raise StandingGrantReceiptError("RECEIPT_MISSING")
    context = receipt.context
    try:
        request = StandingGrantRequest(
            owner_id=requested_owner_id,
            coordinator_id=requested_coordinator_id,
            repository=repository,
            thread_id=context.thread_id,
            goal_id=goal_id,
            action=action,
            requested_at=requested_at,
            context_hash=context.context_hash,
        )
    except Exception as exc:
        raise StandingGrantReceiptError("REQUEST_INVALID") from exc
    return receipt, request


def evaluate_rehydrated_durable_standing_grant(
    *,
    requested_owner_id: str,
    requested_coordinator_id: str,
    repository: RepositoryIdentity,
    goal_id: str,
    action: AutonomyActionClass,
    requested_at: datetime,
    platform_approval_required: bool = False,
) -> StandingGrantDecision:
    """Evaluate a durable grant after rehydrating its coordination scope."""
    try:
        receipt, request = rehydrate_durable_standing_grant_request(
            requested_owner_id=requested_owner_id,
            requested_coordinator_id=requested_coordinator_id,
            repository=repository,
            goal_id=goal_id,
            action=action,
            requested_at=requested_at,
        )
    except StandingGrantReceiptError:
        return evaluate_standing_grant_decision({}, {})
    return evaluate_standing_grant_decision(
        receipt.context,
        request,
        platform_approval_required=platform_approval_required,
    )


def evaluate_durable_standing_grant(
    *,
    requested_owner_id: str,
    requested_coordinator_id: str,
    repository: RepositoryIdentity,
    thread_id: str,
    goal_id: str,
    action: AutonomyActionClass,
    requested_at: datetime,
    platform_approval_required: bool = False,
) -> StandingGrantDecision:
    """Load the canonical durable receipt and run the existing semantic evaluator.

    Missing or invalid receipts fail closed to ``GRANT_INVALID``. A valid
    receipt lacking the requested action (e.g. ``GITHUB_MERGE`` absent)
    reports ``GRANT_OUT_OF_SCOPE``. Real platform approval reports
    ``PLATFORM_APPROVAL_REQUIRED``; it is never conflated with a grant
    mismatch. Evaluation never writes or mutates the receipt/authorization
    state. Uses the canonical path only.
    """
    try:
        receipt = load_standing_grant_receipt(now=requested_at)
    except StandingGrantReceiptError:
        return evaluate_standing_grant_decision({}, {})
    if receipt is None:
        return evaluate_standing_grant_decision({}, {})
    context = receipt.context
    try:
        request = StandingGrantRequest(
            owner_id=requested_owner_id,
            coordinator_id=requested_coordinator_id,
            repository=repository,
            thread_id=thread_id,
            goal_id=goal_id,
            action=action,
            requested_at=requested_at,
            context_hash=context.context_hash,
        )
        return evaluate_standing_grant_decision(
            context,
            request,
            platform_approval_required=platform_approval_required,
        )
    except Exception:
        return evaluate_standing_grant_decision({}, {})


def _authorize_effect_from_receipt(
    receipt: StandingGrantReceipt,
    *,
    repository: RepositoryIdentity,
    action: AutonomyActionClass,
    effect: Mapping[str, Any],
    requested_at: datetime,
) -> dict[str, Any]:
    """Bind one exact effect to the canonical durable Owner standing grant.

    This is an authorization projection only: it never writes or consumes the
    standing grant.  The caller supplies the requested effect, while Owner,
    coordinator, durable coordination scope, Goal, and allowed action class are
    taken only from the validated machine-local receipt.
    """
    context = receipt.context
    if context.repository != repository:
        raise StandingGrantReceiptError("AUTHORIZATION_REPOSITORY_MISMATCH")
    try:
        effect_payload = dict(effect)
        effect_hash = canonical_autonomy_hash(effect_payload)
        request = StandingGrantRequest(
            owner_id=context.owner_id,
            coordinator_id=context.coordinator_id,
            repository=repository,
            thread_id=context.thread_id,
            goal_id=context.goal_id,
            action=action,
            requested_at=requested_at,
            context_hash=context.context_hash,
        )
    except Exception as exc:
        raise StandingGrantReceiptError("AUTHORIZATION_REQUEST_INVALID") from exc
    decision = evaluate_standing_grant_decision(context, request)
    if decision.mutation_authorized is not True:
        raise StandingGrantReceiptError(f"AUTHORIZATION_{decision.outcome.value}")
    payload: dict[str, Any] = {
        "schema": "nexus.standing_grant_effect_authorization.v1",
        "grant_id": receipt.grant_id,
        "grant_receipt_hash": receipt.receipt_hash,
        "context_hash": context.context_hash,
        "owner_id": context.owner_id,
        "coordinator_id": context.coordinator_id,
        "repository": repository.model_dump(mode="json"),
        "goal_id": context.goal_id,
        "action": action.value,
        "requested_at": requested_at.isoformat(),
        "effect": effect_payload,
        "effect_hash": effect_hash,
        "decision_hash": decision.decision_hash,
        "mutation_authorized": True,
        "claim_ceiling": decision.claim_ceiling,
    }
    payload["authorization_hash"] = canonical_autonomy_hash(payload)
    return payload


def authorize_durable_standing_grant_effect(
    *,
    repository: RepositoryIdentity,
    action: AutonomyActionClass,
    effect: Mapping[str, Any],
    requested_at: datetime | None = None,
) -> dict[str, Any]:
    """Authorize one request-bound effect from the single canonical receipt."""
    effective_now = requested_at or datetime.now(timezone.utc)
    receipt = load_standing_grant_receipt(now=effective_now)
    if receipt is None:
        raise StandingGrantReceiptError("RECEIPT_MISSING")
    return _authorize_effect_from_receipt(
        receipt,
        repository=repository,
        action=action,
        effect=effect,
        requested_at=effective_now,
    )


def _authorize_durable_standing_grant_effect_at(
    path: Path,
    *,
    repository: RepositoryIdentity,
    action: AutonomyActionClass,
    effect: Mapping[str, Any],
    requested_at: datetime,
) -> dict[str, Any]:
    """Test/internal-only effect authorization bound to an explicit receipt path."""
    receipt = _load_receipt_at(path, now=requested_at)
    return _authorize_effect_from_receipt(
        receipt,
        repository=repository,
        action=action,
        effect=effect,
        requested_at=requested_at,
    )


def _evaluate_durable_standing_grant_at(
    path: Path,
    *,
    requested_owner_id: str,
    requested_coordinator_id: str,
    repository: RepositoryIdentity,
    thread_id: str,
    goal_id: str,
    action: AutonomyActionClass,
    requested_at: datetime,
    platform_approval_required: bool = False,
) -> StandingGrantDecision:
    """Test/internal-only evaluator bound to an explicit path (never production)."""
    try:
        receipt = _load_receipt_at(path, now=requested_at)
    except StandingGrantReceiptError:
        return evaluate_standing_grant_decision({}, {})
    context = receipt.context
    try:
        request = StandingGrantRequest(
            owner_id=requested_owner_id,
            coordinator_id=requested_coordinator_id,
            repository=repository,
            thread_id=thread_id,
            goal_id=goal_id,
            action=action,
            requested_at=requested_at,
            context_hash=context.context_hash,
        )
        return evaluate_standing_grant_decision(
            context,
            request,
            platform_approval_required=platform_approval_required,
        )
    except Exception:
        return evaluate_standing_grant_decision({}, {})


def _write_transition_file(path: Path, payload: dict[str, Any]) -> None:
    _assert_dir_chain_safe(path.parent, create=True)
    body = {k: v for k, v in payload.items() if k != "record_hash"}
    record_hash = canonical_autonomy_hash(body)
    full_payload = {**body, "record_hash": record_hash}
    canonical = _canonical_json(full_payload)
    fd, tmp_name = tempfile.mkstemp(prefix=".trans-", dir=str(path.parent))
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb") as handle:
            handle.write(canonical.encode("utf-8") + b"\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
        os.chmod(path, 0o600)
        parent_fd = os.open(str(path.parent), os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(parent_fd)
        finally:
            os.close(parent_fd)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:
            pass
        raise


def _read_transition_file(path: Path) -> dict[str, Any]:
    fd = _open_receipt_fd(path)
    try:
        fst = os.fstat(fd)
    except OSError as exc:
        if fd >= 0:
            os.close(fd)
        raise StandingGrantReceiptError("TRANSITION_READ_FAILED") from exc
    if not stat.S_ISREG(fst.st_mode) or fst.st_uid != os.geteuid():
        os.close(fd)
        raise StandingGrantReceiptError("NOT_REGULAR_FILE")
    if stat.S_IMODE(fst.st_mode) != 0o600:
        os.close(fd)
        raise StandingGrantReceiptError("UNSAFE_PERMISSIONS")
    if fst.st_size > _MAX_RECEIPT_BYTES:
        os.close(fd)
        raise StandingGrantReceiptError("RECEIPT_TOO_LARGE")
    raw = _read_all_fd(fd, fst.st_size)
    os.close(fd)
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise StandingGrantReceiptError("MALFORMED") from exc
    if text.endswith("\n"):
        text = text[:-1]
    if "\x00" in text or "\n" in text:
        raise StandingGrantReceiptError("NONCANONICAL_SERIALIZATION")
    try:
        parsed = json.loads(text, object_pairs_hook=_reject_duplicates)
    except (json.JSONDecodeError, ValueError) as exc:
        raise StandingGrantReceiptError("MALFORMED") from exc
    if not isinstance(parsed, dict):
        raise StandingGrantReceiptError("MALFORMED")
    if _canonical_json(parsed) != text:
        raise StandingGrantReceiptError("NONCANONICAL_SERIALIZATION")
    stored_hash = parsed.get("record_hash")
    if not isinstance(stored_hash, str) or not _SHA64_HEX.fullmatch(stored_hash):
        raise StandingGrantReceiptError("TRANSITION_TAMPERED")
    body = {k: v for k, v in parsed.items() if k != "record_hash"}
    if canonical_autonomy_hash(body) != stored_hash:
        raise StandingGrantReceiptError("TRANSITION_TAMPERED")
    return parsed


def _switch_task_card_authority_at(
    target_path: Path,
    *,
    attempt_key: str,
    expected_current_receipt_hash: str,
    expected_current_goal_id: str,
    successor_goal_id: str,
    successor_thread_id: str,
    ttl_minutes: int,
    owner_confirmation: bool,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Switch standing grant to a bounded temporary task-card authority scope at an explicit path."""
    if owner_confirmation is not True:
        raise StandingGrantReceiptError("OWNER_CONFIRMATION_REQUIRED")
    if not isinstance(ttl_minutes, int) or ttl_minutes < 1 or ttl_minutes > 30:
        raise StandingGrantReceiptError("TTL_MINUTES_INVALID")
    if not _SAFE_ID.fullmatch(attempt_key):
        raise StandingGrantReceiptError("ATTEMPT_KEY_INVALID")
    if not _SHA64_HEX.fullmatch(expected_current_receipt_hash):
        raise StandingGrantReceiptError("RECEIPT_HASH_INVALID")
    if not _SAFE_ID.fullmatch(expected_current_goal_id):
        raise StandingGrantReceiptError("EXPECTED_GOAL_INVALID")
    if not _SAFE_ID.fullmatch(successor_goal_id):
        raise StandingGrantReceiptError("SUCCESSOR_GOAL_INVALID")
    if not _SAFE_ID.fullmatch(successor_thread_id):
        raise StandingGrantReceiptError("SUCCESSOR_THREAD_INVALID")

    effective_now = now if now is not None else datetime.now(timezone.utc)
    if not isinstance(effective_now, datetime) or effective_now.tzinfo is None:
        raise StandingGrantReceiptError("EXACT_TIMEZONE_REQUIRED")

    request_payload = {
        "operation": "SWITCH",
        "attempt_key": attempt_key,
        "expected_current_receipt_hash": expected_current_receipt_hash,
        "expected_current_goal_id": expected_current_goal_id,
        "successor_goal_id": successor_goal_id,
        "successor_thread_id": successor_thread_id,
        "ttl_minutes": ttl_minutes,
    }
    request_hash = canonical_autonomy_hash(request_payload)

    authority_dir = target_path.parent
    transitions_dir = authority_dir / "transitions"
    attempt_path = transitions_dir / f"attempt_{attempt_key}.json"

    _assert_dir_chain_safe(authority_dir, create=True)
    with _coordination_lock(authority_dir):
        if attempt_path.exists():
            attempt_record = _read_transition_file(attempt_path)
            if (
                attempt_record.get("schema") != "nexus.task_card_authority_transition_attempt.v1"
                or attempt_record.get("operation_type") != "SWITCH"
                or attempt_record.get("attempt_key") != attempt_key
                or attempt_record.get("request_hash") != request_hash
            ):
                raise StandingGrantReceiptError("ATTEMPT_KEY_CONFLICT")

            attempt_status = attempt_record.get("status")
            if attempt_status == "COMMITTED" or attempt_status is None:
                return dict(attempt_record["result"])

            if attempt_status == "PREPARED":
                predecessor_hash = attempt_record.get("predecessor_receipt_hash")
                intended_successor_hash = attempt_record.get("intended_successor_receipt_hash")
                switch_operation_id = attempt_record.get("switch_operation_id")
                if not switch_operation_id or not _SAFE_ID.fullmatch(str(switch_operation_id)):
                    raise StandingGrantReceiptError("SWITCH_OPERATION_NOT_FOUND")
                op_path = transitions_dir / f"op_{switch_operation_id}.json"
                if not op_path.exists():
                    raise StandingGrantReceiptError("SWITCH_OPERATION_NOT_FOUND")
                op_record = _read_transition_file(op_path)

                if (
                    op_record.get("schema") != "nexus.task_card_authority_switch_record.v1"
                    or op_record.get("switch_operation_id") != switch_operation_id
                    or op_record.get("attempt_key") != attempt_key
                    or op_record.get("predecessor_receipt_hash") != predecessor_hash
                    or op_record.get("predecessor_receipt_hash") != expected_current_receipt_hash
                    or op_record.get("temporary_receipt_hash") != intended_successor_hash
                    or op_record.get("temporary_goal_id") != successor_goal_id
                    or op_record.get("temporary_thread_id") != successor_thread_id
                ):
                    raise StandingGrantReceiptError("TRANSITION_RECORD_INCONSISTENT")

                temporary_dict = op_record.get("temporary_receipt")
                if not isinstance(temporary_dict, dict):
                    raise StandingGrantReceiptError("TRANSITION_RECORD_INCONSISTENT")
                try:
                    temporary_receipt = StandingGrantReceipt.model_validate(temporary_dict)
                except Exception as exc:
                    raise StandingGrantReceiptError("TRANSITION_RECORD_INCONSISTENT") from exc
                if (
                    temporary_receipt.receipt_hash != intended_successor_hash
                    or temporary_receipt.supersedes_grant_hash != predecessor_hash
                ):
                    raise StandingGrantReceiptError("TRANSITION_RECORD_INCONSISTENT")

                try:
                    current_hash = _read_current_hash_nofollow(target_path)
                except StandingGrantReceiptError:
                    current_hash = None

                if current_hash == predecessor_hash:
                    _write_bytes_locked(
                        _canonical_json(temporary_receipt.model_dump(mode="json")),
                        temporary_receipt.supersedes_grant_hash,
                        target_path,
                        predecessor_hash,
                    )
                    op_record["status"] = "ACTIVE"
                    _write_transition_file(op_path, op_record)
                    attempt_record["status"] = "COMMITTED"
                    _write_transition_file(attempt_path, attempt_record)
                    return dict(attempt_record["result"])
                elif current_hash == intended_successor_hash:
                    op_record["status"] = "ACTIVE"
                    _write_transition_file(op_path, op_record)
                    attempt_record["status"] = "COMMITTED"
                    _write_transition_file(attempt_path, attempt_record)
                    return dict(attempt_record["result"])
                else:
                    raise StandingGrantReceiptError("CURRENT_RECEIPT_HASH_MISMATCH")

            raise StandingGrantReceiptError("ATTEMPT_STATE_INVALID")

        current_receipt = _load_receipt_at(target_path, now=effective_now)
        if current_receipt is None:
            raise StandingGrantReceiptError("RECEIPT_MISSING")
        if current_receipt.receipt_hash != expected_current_receipt_hash:
            raise StandingGrantReceiptError("CURRENT_RECEIPT_HASH_MISMATCH")
        if current_receipt.context.goal_id != expected_current_goal_id:
            raise StandingGrantReceiptError("CURRENT_GOAL_MISMATCH")

        switch_operation_id = f"switch_{uuid4().hex}"
        temporary_actions = (
            AutonomyActionClass.TASK_CARD_COMMIT,
            AutonomyActionClass.TASK_CARD_CREATE,
        )
        temporary_context = StandingGrantContext.issue(
            owner_id=current_receipt.context.owner_id,
            coordinator_id=current_receipt.context.coordinator_id,
            repository=current_receipt.context.repository,
            thread_id=successor_thread_id,
            goal_id=successor_goal_id,
            allowed_actions=temporary_actions,
            issued_at=effective_now,
            expires_at=min(
                effective_now + timedelta(minutes=ttl_minutes),
                current_receipt.context.expires_at,
            ),
        )
        temporary_grant_id = f"{current_receipt.grant_id}-switch-{uuid4().hex[:8]}"
        temporary_receipt = StandingGrantReceipt.issue(
            grant_id=temporary_grant_id,
            context=temporary_context,
            supersedes_grant_hash=current_receipt.receipt_hash,
        )

        result: dict[str, Any] = {
            "schema": "nexus.task_card_authority_switch.v1",
            "status": "SWITCHED",
            "switch_operation_id": switch_operation_id,
            "attempt_key": attempt_key,
            "predecessor_receipt_hash": current_receipt.receipt_hash,
            "predecessor_goal_id": current_receipt.context.goal_id,
            "temporary_grant_id": temporary_receipt.grant_id,
            "temporary_receipt_hash": temporary_receipt.receipt_hash,
            "temporary_goal_id": successor_goal_id,
            "temporary_thread_id": successor_thread_id,
            "allowed_actions": [a.value for a in temporary_actions],
            "expires_at": temporary_context.expires_at.isoformat(),
            "owner_confirmation": True,
        }

        op_record: dict[str, Any] = {
            "schema": "nexus.task_card_authority_switch_record.v1",
            "switch_operation_id": switch_operation_id,
            "attempt_key": attempt_key,
            "status": "PREPARED",
            "predecessor_receipt": current_receipt.model_dump(mode="json"),
            "predecessor_receipt_hash": current_receipt.receipt_hash,
            "predecessor_goal_id": current_receipt.context.goal_id,
            "temporary_receipt": temporary_receipt.model_dump(mode="json"),
            "temporary_receipt_hash": temporary_receipt.receipt_hash,
            "temporary_goal_id": successor_goal_id,
            "temporary_thread_id": successor_thread_id,
            "allowed_actions": [a.value for a in temporary_actions],
            "created_at": effective_now.isoformat(),
            "expires_at": temporary_context.expires_at.isoformat(),
            "restored_at": None,
            "restored_receipt_hash": None,
        }
        op_path = transitions_dir / f"op_{switch_operation_id}.json"
        _write_transition_file(op_path, op_record)

        attempt_record = {
            "schema": "nexus.task_card_authority_transition_attempt.v1",
            "attempt_key": attempt_key,
            "operation_type": "SWITCH",
            "status": "PREPARED",
            "switch_operation_id": switch_operation_id,
            "request": request_payload,
            "request_hash": request_hash,
            "predecessor_receipt_hash": current_receipt.receipt_hash,
            "intended_successor_receipt_hash": temporary_receipt.receipt_hash,
            "result": result,
            "created_at": effective_now.isoformat(),
        }
        _write_transition_file(attempt_path, attempt_record)

        _write_bytes_locked(
            _canonical_json(temporary_receipt.model_dump(mode="json")),
            temporary_receipt.supersedes_grant_hash,
            target_path,
            current_receipt.receipt_hash,
        )

        op_record["status"] = "ACTIVE"
        _write_transition_file(op_path, op_record)

        attempt_record["status"] = "COMMITTED"
        _write_transition_file(attempt_path, attempt_record)

        return result


def switch_task_card_authority(
    *,
    attempt_key: str,
    expected_current_receipt_hash: str,
    expected_current_goal_id: str,
    successor_goal_id: str,
    successor_thread_id: str,
    ttl_minutes: int,
    owner_confirmation: bool,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Switch canonical standing grant to a bounded temporary task-card authority scope."""
    return _switch_task_card_authority_at(
        DEFAULT_RECEIPT_PATH,
        attempt_key=attempt_key,
        expected_current_receipt_hash=expected_current_receipt_hash,
        expected_current_goal_id=expected_current_goal_id,
        successor_goal_id=successor_goal_id,
        successor_thread_id=successor_thread_id,
        ttl_minutes=ttl_minutes,
        owner_confirmation=owner_confirmation,
        now=now,
    )


def _restore_task_card_authority_at(
    target_path: Path,
    *,
    attempt_key: str,
    switch_operation_id: str,
    expected_temporary_receipt_hash: str,
    owner_confirmation: bool,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Restore standing grant from temporary task-card scope to exact predecessor at an explicit path."""
    if owner_confirmation is not True:
        raise StandingGrantReceiptError("OWNER_CONFIRMATION_REQUIRED")
    if not _SAFE_ID.fullmatch(attempt_key):
        raise StandingGrantReceiptError("ATTEMPT_KEY_INVALID")
    if not _SAFE_ID.fullmatch(switch_operation_id):
        raise StandingGrantReceiptError("SWITCH_OPERATION_ID_INVALID")
    if not _SHA64_HEX.fullmatch(expected_temporary_receipt_hash):
        raise StandingGrantReceiptError("RECEIPT_HASH_INVALID")

    effective_now = now if now is not None else datetime.now(timezone.utc)
    if not isinstance(effective_now, datetime) or effective_now.tzinfo is None:
        raise StandingGrantReceiptError("EXACT_TIMEZONE_REQUIRED")

    request_payload = {
        "operation": "RESTORE",
        "attempt_key": attempt_key,
        "switch_operation_id": switch_operation_id,
        "expected_temporary_receipt_hash": expected_temporary_receipt_hash,
    }
    request_hash = canonical_autonomy_hash(request_payload)

    authority_dir = target_path.parent
    transitions_dir = authority_dir / "transitions"
    attempt_path = transitions_dir / f"attempt_{attempt_key}.json"
    op_path = transitions_dir / f"op_{switch_operation_id}.json"

    _assert_dir_chain_safe(authority_dir, create=True)
    with _coordination_lock(authority_dir):
        if attempt_path.exists():
            attempt_record = _read_transition_file(attempt_path)
            if (
                attempt_record.get("schema") != "nexus.task_card_authority_transition_attempt.v1"
                or attempt_record.get("operation_type") != "RESTORE"
                or attempt_record.get("attempt_key") != attempt_key
                or attempt_record.get("request_hash") != request_hash
            ):
                raise StandingGrantReceiptError("ATTEMPT_KEY_CONFLICT")

            attempt_status = attempt_record.get("status")
            if attempt_status == "COMMITTED" or attempt_status is None:
                return dict(attempt_record["result"])

            if attempt_status == "PREPARED":
                switch_op_id = attempt_record.get("switch_operation_id")
                if switch_op_id != switch_operation_id or not op_path.exists():
                    raise StandingGrantReceiptError("SWITCH_OPERATION_NOT_FOUND")
                op_record = _read_transition_file(op_path)
                expected_temp_hash = attempt_record.get("expected_temporary_receipt_hash")
                intended_restored_hash = attempt_record.get("intended_restored_receipt_hash")

                if (
                    op_record.get("schema") != "nexus.task_card_authority_switch_record.v1"
                    or op_record.get("switch_operation_id") != switch_operation_id
                    or op_record.get("temporary_receipt_hash") != expected_temp_hash
                    or op_record.get("temporary_receipt_hash") != expected_temporary_receipt_hash
                ):
                    raise StandingGrantReceiptError("TRANSITION_RECORD_INCONSISTENT")

                intended_restored_dict = attempt_record.get("intended_restored_receipt")
                if not isinstance(intended_restored_dict, dict):
                    raise StandingGrantReceiptError("TRANSITION_RECORD_INCONSISTENT")
                try:
                    intended_restored_receipt = StandingGrantReceipt.model_validate(
                        intended_restored_dict
                    )
                except Exception as exc:
                    raise StandingGrantReceiptError("TRANSITION_RECORD_INCONSISTENT") from exc

                if (
                    intended_restored_receipt.receipt_hash != intended_restored_hash
                    or intended_restored_receipt.supersedes_grant_hash != expected_temp_hash
                ):
                    raise StandingGrantReceiptError("TRANSITION_RECORD_INCONSISTENT")

                predecessor_dict = op_record.get("predecessor_receipt")
                if not isinstance(predecessor_dict, dict):
                    raise StandingGrantReceiptError("PREDECESSOR_RECORD_MALFORMED")
                try:
                    predecessor_receipt = StandingGrantReceipt.model_validate(predecessor_dict)
                except Exception as exc:
                    raise StandingGrantReceiptError("PREDECESSOR_RECORD_MALFORMED") from exc
                if predecessor_receipt.receipt_hash != op_record.get("predecessor_receipt_hash"):
                    raise StandingGrantReceiptError("TRANSITION_RECORD_INCONSISTENT")
                if intended_restored_receipt.context != predecessor_receipt.context:
                    raise StandingGrantReceiptError("TRANSITION_RECORD_INCONSISTENT")

                try:
                    current_hash = _read_current_hash_nofollow(target_path)
                except StandingGrantReceiptError:
                    current_hash = None

                if current_hash == expected_temp_hash:
                    _write_bytes_locked(
                        _canonical_json(intended_restored_receipt.model_dump(mode="json")),
                        intended_restored_receipt.supersedes_grant_hash,
                        target_path,
                        expected_temp_hash,
                    )
                    op_record["status"] = "RESTORED"
                    op_record["restored_at"] = effective_now.isoformat()
                    op_record["restored_receipt_hash"] = intended_restored_receipt.receipt_hash
                    _write_transition_file(op_path, op_record)

                    attempt_record["status"] = "COMMITTED"
                    _write_transition_file(attempt_path, attempt_record)
                    return dict(attempt_record["result"])
                elif current_hash == intended_restored_hash:
                    op_record["status"] = "RESTORED"
                    op_record["restored_at"] = effective_now.isoformat()
                    op_record["restored_receipt_hash"] = intended_restored_receipt.receipt_hash
                    _write_transition_file(op_path, op_record)

                    attempt_record["status"] = "COMMITTED"
                    _write_transition_file(attempt_path, attempt_record)
                    return dict(attempt_record["result"])
                else:
                    raise StandingGrantReceiptError("CURRENT_RECEIPT_HASH_MISMATCH")

            raise StandingGrantReceiptError("ATTEMPT_STATE_INVALID")

        if not op_path.exists():
            raise StandingGrantReceiptError("SWITCH_OPERATION_NOT_FOUND")

        op_record = _read_transition_file(op_path)
        if (
            op_record.get("schema") != "nexus.task_card_authority_switch_record.v1"
            or op_record.get("switch_operation_id") != switch_operation_id
        ):
            raise StandingGrantReceiptError("TRANSITION_RECORD_INCONSISTENT")
        if op_record.get("temporary_receipt_hash") != expected_temporary_receipt_hash:
            raise StandingGrantReceiptError("TEMPORARY_RECEIPT_HASH_MISMATCH")
        if op_record.get("status") == "RESTORED":
            raise StandingGrantReceiptError("SWITCH_OPERATION_ALREADY_RESTORED")
        if op_record.get("status") not in ("ACTIVE", "PREPARED"):
            raise StandingGrantReceiptError("SWITCH_OPERATION_NOT_ACTIVE")

        current_receipt = _load_receipt_structural_at(target_path)
        if current_receipt.receipt_hash != expected_temporary_receipt_hash:
            raise StandingGrantReceiptError("CURRENT_RECEIPT_HASH_MISMATCH")

        predecessor_dict = op_record.get("predecessor_receipt")
        if not isinstance(predecessor_dict, dict):
            raise StandingGrantReceiptError("PREDECESSOR_RECORD_MALFORMED")
        try:
            predecessor_receipt = StandingGrantReceipt.model_validate(predecessor_dict)
        except Exception as exc:
            raise StandingGrantReceiptError("PREDECESSOR_RECORD_MALFORMED") from exc
        if predecessor_receipt.receipt_hash != op_record.get("predecessor_receipt_hash"):
            raise StandingGrantReceiptError("TRANSITION_RECORD_INCONSISTENT")

        restored_grant_id = f"{predecessor_receipt.grant_id}-restored-{uuid4().hex[:8]}"
        restored_receipt = StandingGrantReceipt.issue(
            grant_id=restored_grant_id,
            context=predecessor_receipt.context,
            supersedes_grant_hash=expected_temporary_receipt_hash,
        )

        result: dict[str, Any] = {
            "schema": "nexus.task_card_authority_restore.v1",
            "status": "RESTORED",
            "switch_operation_id": switch_operation_id,
            "attempt_key": attempt_key,
            "restored_grant_id": restored_receipt.grant_id,
            "restored_receipt_hash": restored_receipt.receipt_hash,
            "restored_goal_id": restored_receipt.context.goal_id,
            "restored_thread_id": restored_receipt.context.thread_id,
            "restored_allowed_actions": [a.value for a in restored_receipt.context.allowed_actions],
            "temporary_receipt_hash": expected_temporary_receipt_hash,
            "owner_confirmation": True,
        }

        attempt_record = {
            "schema": "nexus.task_card_authority_transition_attempt.v1",
            "attempt_key": attempt_key,
            "operation_type": "RESTORE",
            "status": "PREPARED",
            "switch_operation_id": switch_operation_id,
            "request": request_payload,
            "request_hash": request_hash,
            "expected_temporary_receipt_hash": expected_temporary_receipt_hash,
            "intended_restored_receipt": restored_receipt.model_dump(mode="json"),
            "intended_restored_receipt_hash": restored_receipt.receipt_hash,
            "result": result,
            "created_at": effective_now.isoformat(),
        }
        _write_transition_file(attempt_path, attempt_record)

        _write_bytes_locked(
            _canonical_json(restored_receipt.model_dump(mode="json")),
            restored_receipt.supersedes_grant_hash,
            target_path,
            expected_temporary_receipt_hash,
        )

        op_record["status"] = "RESTORED"
        op_record["restored_at"] = effective_now.isoformat()
        op_record["restored_receipt_hash"] = restored_receipt.receipt_hash
        _write_transition_file(op_path, op_record)

        attempt_record["status"] = "COMMITTED"
        _write_transition_file(attempt_path, attempt_record)

        return result


def restore_task_card_authority(
    *,
    attempt_key: str,
    switch_operation_id: str,
    expected_temporary_receipt_hash: str,
    owner_confirmation: bool,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Restore canonical standing grant from a temporary task-card authority scope to exact predecessor."""
    return _restore_task_card_authority_at(
        DEFAULT_RECEIPT_PATH,
        attempt_key=attempt_key,
        switch_operation_id=switch_operation_id,
        expected_temporary_receipt_hash=expected_temporary_receipt_hash,
        owner_confirmation=owner_confirmation,
        now=now,
    )
