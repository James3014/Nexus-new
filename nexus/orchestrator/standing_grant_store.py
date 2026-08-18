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
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

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
        return cls.model_validate(
            {
                **payload,
                "receipt_hash": canonical_autonomy_hash(payload),
            }
        )


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
    if stat.S_IMODE(st.st_mode) & 0o022:
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


def _write_bytes(
    canonical: str,
    supersedes_grant_hash: str | None,
    destination: Path,
    expected: str | None,
) -> None:
    _assert_dir_chain_safe(destination.parent, create=True)
    with _coordination_lock(destination.parent):
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
            parent_fd = os.open(
                str(destination.parent), os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
            )
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


def _load_receipt_at(path: Path, *, now: datetime | None = None) -> StandingGrantReceipt:
    """Validate one receipt from an explicit path using fd-based O_NOFOLLOW reads.

    This is a test/internal helper; production callers must use
    :func:`load_standing_grant_receipt` against the canonical path only.
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
        receipt = StandingGrantReceipt.model_validate(parsed)
    except Exception as exc:
        raise StandingGrantReceiptError("MALFORMED") from exc
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
