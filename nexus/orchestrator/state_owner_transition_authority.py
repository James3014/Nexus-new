"""Strict read-only verifier for externally published writer-transition authority."""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import stat
import subprocess
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping

from nexus.contracts.state_owner_transition import WriterTransitionRequest

TRACKED_RELATIVE = Path(
    "tasks/ASTRA-P5P6-LIVE-TRANSITION-20260908/01-writer-transition-authority.json"
)
DURABLE_PATH = Path(
    "/Users/jameschen/Library/Application Support/Nexus/writer-transition/authority.json"
)
MIRROR_ROOT = Path("/Users/jameschen/Workspace/Nexus-new-authority-main")
EXPECTED_REMOTE = "https://github.com/James3014/Nexus-new.git"
EXPECTED_REF = "refs/heads/main"
EXPECTED_OWNER = "James3014"
EXPECTED_COORDINATOR = "primary-codex-coordinator"


@dataclass(frozen=True, slots=True)
class AuthorityPublication:
    """One source-owned tracked/durable publication pair."""

    tracked_relative: Path
    durable_path: Path

    def __post_init__(self) -> None:
        tracked = Path(self.tracked_relative)
        durable = Path(self.durable_path)
        if tracked.is_absolute() or any(part in {"", ".", ".."} for part in tracked.parts):
            raise ValueError("AUTHORITY_PUBLICATION_TRACKED_PATH_INVALID")
        if not durable.is_absolute():
            raise ValueError("AUTHORITY_PUBLICATION_DURABLE_PATH_INVALID")
        object.__setattr__(self, "tracked_relative", tracked)
        object.__setattr__(self, "durable_path", durable)


# The default entry preserves the original single-root publication contract.
# Additional root entries are installed by the owner-controlled source package;
# callers may select only with the already-bound request.root_id.
PUBLICATION_INVENTORY: Mapping[str, AuthorityPublication] = MappingProxyType(
    {"root": AuthorityPublication(TRACKED_RELATIVE, DURABLE_PATH)}
)


class WriterAuthorityError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class LoadedSourceIdentity:
    repository: str
    source_head: str
    source_tree: str
    card_path: str
    card_sha256: str


@dataclass(frozen=True, slots=True)
class VerifiedWriterTransitionAuthority:
    receipt_id: str
    receipt_hash: str
    tracked_blob_hash: str
    issuer: str
    source_head: str
    card_sha256: str
    _private_token: object
    authorization_intent_digest: str = ""
    process_id: int = 0
    thread_ident: int = 0
    thread_id: str = ""
    full_request_digest: str = ""
    goal_id: str = ""
    grant_id: str = ""
    owner_id: str = ""
    coordinator_id: str = ""
    repository: str = ""
    expires_at: str = ""
    effect_hash: str = ""
    grant_receipt_hash: str = ""
    grant_context_hash: str = ""
    publication_root_id: str = ""


_REGISTERED: dict[int, VerifiedWriterTransitionAuthority] = {}


def is_authorized_for_request(value: Any, request: WriterTransitionRequest) -> bool:
    """Require the registered handle and exact request/intent binding."""
    if not is_registered_authority(value) or not isinstance(request, WriterTransitionRequest):
        return False
    if (
        value.full_request_digest != request.request_digest
        or value.authorization_intent_digest != _authorization_intent_digest(request)
        or value.effect_hash != _effect_hash(request)
    ):
        return False
    try:
        return datetime.fromisoformat(value.expires_at.replace("Z", "+00:00")) > datetime.now(
            timezone.utc
        )
    except (TypeError, ValueError):
        return False


def is_registered_authority(value: Any) -> bool:
    return (
        isinstance(value, VerifiedWriterTransitionAuthority)
        and _REGISTERED.get(id(value)) is value
        and isinstance(value._private_token, bytes)
        and value.process_id == os.getpid()
        and value.thread_ident == threading.get_ident()
    )


def _regular(path: Path) -> bytes:
    try:
        info = path.lstat()
    except OSError as exc:
        raise WriterAuthorityError("AUTHORITY_MISSING") from exc
    if (
        stat.S_ISLNK(info.st_mode)
        or not stat.S_ISREG(info.st_mode)
        or info.st_uid != os.getuid()
        or stat.S_IMODE(info.st_mode) & 0o022
    ):
        raise WriterAuthorityError("AUTHORITY_PATH_UNSAFE")
    parent = path.parent
    try:
        current = parent
        while True:
            pinfo = current.lstat()
            if (
                stat.S_ISLNK(pinfo.st_mode)
                or not stat.S_ISDIR(pinfo.st_mode)
                or pinfo.st_uid not in (os.getuid(), 0)
                or stat.S_IMODE(pinfo.st_mode) & 0o022
            ):
                raise WriterAuthorityError("AUTHORITY_PARENT_UNSAFE")
            if current.parent == current:
                break
            current = current.parent
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        opened = os.fstat(fd)
        if (opened.st_ino, opened.st_dev) != (info.st_ino, info.st_dev) or not stat.S_ISREG(
            opened.st_mode
        ):
            raise WriterAuthorityError("AUTHORITY_PATH_CHANGED")
        with os.fdopen(fd, "rb") as handle:
            return handle.read()
    except WriterAuthorityError:
        raise
    except OSError as exc:
        raise WriterAuthorityError("AUTHORITY_UNREADABLE") from exc


def _git(*args: str) -> str:
    try:
        return subprocess.check_output(
            ["git", "-C", str(MIRROR_ROOT), *args], text=True, stderr=subprocess.DEVNULL
        ).strip()
    except (OSError, subprocess.CalledProcessError) as exc:
        raise WriterAuthorityError("AUTHORITY_MIRROR_UNAVAILABLE") from exc


def _remote_main_head() -> str:
    try:
        rows = subprocess.check_output(
            [
                "git",
                "-C",
                str(MIRROR_ROOT),
                "ls-remote",
                "--exit-code",
                "origin",
                "refs/heads/main",
            ],
            text=True,
            stderr=subprocess.DEVNULL,
        ).splitlines()
    except (OSError, subprocess.CalledProcessError) as exc:
        raise WriterAuthorityError("AUTHORITY_REMOTE_FRESHNESS_UNKNOWN") from exc
    shas = {row.split(maxsplit=1)[0] for row in rows if row.strip()}
    if len(shas) != 1:
        raise WriterAuthorityError("AUTHORITY_REMOTE_MAIN_UNKNOWN")
    return next(iter(shas))


def _mirror_identity(
    publication: AuthorityPublication | None = None,
) -> tuple[str, str, str]:
    """Read publication commit/blob provenance from the fixed clean mirror."""
    head = _git("rev-parse", "HEAD")
    origin = _git("rev-parse", "refs/remotes/origin/main")
    tree = _git("rev-parse", "HEAD^{tree}")
    branch = _git("branch", "--show-current")
    dirty = _git("status", "--porcelain", "--untracked-files=all")
    remote = _git("remote", "get-url", "origin")
    live_remote = _remote_main_head()
    if (
        branch != "main"
        or head != origin
        or head != live_remote
        or dirty
        or remote.rstrip("/") != EXPECTED_REMOTE.rstrip("/")
    ):
        raise WriterAuthorityError("AUTHORITY_MIRROR_NOT_FRESH_CLEAN_MAIN")
    publication = publication or AuthorityPublication(TRACKED_RELATIVE, DURABLE_PATH)
    tracked = str(publication.tracked_relative)
    try:
        _git("rev-parse", f"HEAD:{tracked}")
        tracked_bytes = subprocess.check_output(
            ["git", "-C", str(MIRROR_ROOT), "show", f"HEAD:{tracked}"], stderr=subprocess.DEVNULL
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise WriterAuthorityError("AUTHORITY_TRACKED_BLOB_MISSING") from exc
    # Blob identity is the git object hash; the durable file is compared byte-for-byte later.
    return head, tree, hashlib.sha256(tracked_bytes).hexdigest()


def _publication_for_request(request: WriterTransitionRequest) -> AuthorityPublication:
    """Resolve a fixed publication; never accept a caller-provided path."""
    if request.root_id == "root":
        # Keep legacy test/host overrides of the two original constants
        # observable without making either path request-selectable.
        return AuthorityPublication(TRACKED_RELATIVE, DURABLE_PATH)
    publication = PUBLICATION_INVENTORY.get(request.root_id)
    if publication is None:
        raise WriterAuthorityError("AUTHORITY_PUBLICATION_NOT_INDEXED")
    if not isinstance(publication, AuthorityPublication):
        raise WriterAuthorityError("AUTHORITY_PUBLICATION_INVENTORY_INVALID")
    return publication


def _authorization_intent_digest(request: WriterTransitionRequest) -> str:
    return request.authorization_intent_digest


def _effect_hash(request: WriterTransitionRequest) -> str:
    payload = {
        "operation_digest": _authorization_intent_digest(request),
        **{
            k: v
            for k, v in request.to_dict().items()
            if k not in {"authority_receipt_id", "authority_receipt_hash"}
        },
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()


def _parse_time(value: Any) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None or parsed <= datetime.now(timezone.utc):
            raise ValueError
        return parsed
    except (TypeError, ValueError) as exc:
        raise WriterAuthorityError("AUTHORITY_EXPIRY_INVALID") from exc


def load_verified_writer_transition_authority(
    *, request: WriterTransitionRequest, loaded_source_identity: LoadedSourceIdentity
) -> VerifiedWriterTransitionAuthority:
    if not isinstance(request, WriterTransitionRequest) or not isinstance(
        loaded_source_identity, LoadedSourceIdentity
    ):
        raise WriterAuthorityError("AUTHORITY_INPUT_INVALID")
    publication = _publication_for_request(request)
    default_publication = AuthorityPublication(TRACKED_RELATIVE, DURABLE_PATH)
    if publication == default_publication:
        mirror_head, mirror_tree, tracked_hash = _mirror_identity()
        tracked_path = MIRROR_ROOT / TRACKED_RELATIVE
    else:
        mirror_head, mirror_tree, tracked_hash = _mirror_identity(publication)
        tracked_path = MIRROR_ROOT / publication.tracked_relative
    try:
        source_tree = _git("rev-parse", f"{loaded_source_identity.source_head}^{{tree}}")
        subprocess.check_call(
            [
                "git",
                "-C",
                str(MIRROR_ROOT),
                "merge-base",
                "--is-ancestor",
                loaded_source_identity.source_head,
                mirror_head,
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise WriterAuthorityError("AUTHORITY_SOURCE_LINEAGE_MISMATCH") from exc
    if source_tree != loaded_source_identity.source_tree:
        raise WriterAuthorityError("AUTHORITY_SOURCE_TREE_MISMATCH")
    tracked_bytes = _regular(tracked_path)
    durable_bytes = _regular(publication.durable_path)
    if tracked_bytes != durable_bytes:
        raise WriterAuthorityError("AUTHORITY_PUBLICATION_BYTES_MISMATCH")
    if tracked_hash != request.authority_receipt_hash:
        raise WriterAuthorityError("AUTHORITY_BLOB_HASH_MISMATCH")
    try:
        data = json.loads(tracked_bytes)
    except (ValueError, json.JSONDecodeError) as exc:
        raise WriterAuthorityError("AUTHORITY_JSON_INVALID") from exc
    if not isinstance(data, Mapping):
        raise WriterAuthorityError("AUTHORITY_JSON_INVALID")
    required = {
        "schema",
        "receipt_id",
        "issuer",
        "coordinator_id",
        "owner_id",
        "repository",
        "goal_id",
        "thread_id",
        "grant_id",
        "grant_receipt_hash",
        "grant_context_hash",
        "action",
        "source_head",
        "source_tree",
        "card_path",
        "card_sha256",
        "authorization_intent_digest",
        "operation_digest",
        "root_id",
        "effect_hash",
        "revoked",
        "expires_at",
    }
    if set(data) != required or data.get("schema") != "nexus.writer_transition_authority.v1":
        raise WriterAuthorityError("AUTHORITY_SCHEMA_INVALID")
    if (
        data["issuer"] != EXPECTED_OWNER
        or data["owner_id"] != EXPECTED_OWNER
        or data["coordinator_id"] != EXPECTED_COORDINATOR
    ):
        raise WriterAuthorityError("AUTHORITY_ISSUER_INVALID")
    if (
        data["repository"] != loaded_source_identity.repository
        or data["source_head"] != loaded_source_identity.source_head
        or data["source_tree"] != loaded_source_identity.source_tree
        or data["card_path"] != loaded_source_identity.card_path
        or data["card_sha256"] != loaded_source_identity.card_sha256
    ):
        raise WriterAuthorityError("AUTHORITY_SOURCE_SCOPE_MISMATCH")
    if (
        data["receipt_id"] != request.authority_receipt_id
        or data["authorization_intent_digest"] != _authorization_intent_digest(request)
        or data["root_id"] != request.root_id
        or data["action"] != "WRITER_TRANSITION"
    ):
        raise WriterAuthorityError("AUTHORITY_REQUEST_MISMATCH")
    if data["revoked"] is not False:
        raise WriterAuthorityError("AUTHORITY_REVOKED")
    _parse_time(data["expires_at"])
    if data["operation_digest"] != _authorization_intent_digest(request) or data[
        "effect_hash"
    ] != _effect_hash(request):
        raise WriterAuthorityError("AUTHORITY_EFFECT_SCOPE_MISMATCH")
    value = VerifiedWriterTransitionAuthority(
        data["receipt_id"],
        tracked_hash,
        tracked_hash,
        data["issuer"],
        data["source_head"],
        data["card_sha256"],
        secrets.token_bytes(32),
        data["authorization_intent_digest"],
        os.getpid(),
        threading.get_ident(),
        data["thread_id"],
        request.request_digest,
        data["goal_id"],
        data["grant_id"],
        data["owner_id"],
        data["coordinator_id"],
        data["repository"],
        data["expires_at"],
        data["effect_hash"],
        data["grant_receipt_hash"],
        data["grant_context_hash"],
        request.root_id,
    )
    _REGISTERED[id(value)] = value
    return value


def _fixture_authority(
    *, request: WriterTransitionRequest, source: LoadedSourceIdentity
) -> VerifiedWriterTransitionAuthority:
    """Disabled in production; tests must monkeypatch the loader boundary."""
    raise WriterAuthorityError("FIXTURE_AUTHORITY_DISABLED")
    value = VerifiedWriterTransitionAuthority(
        request.authority_receipt_id,
        request.authority_receipt_hash,
        request.authority_receipt_hash,
        "fixture",
        source.source_head,
        source.card_sha256,
        secrets.token_bytes(32),
        _authorization_intent_digest(request),
        os.getpid(),
        threading.get_ident(),
        "",
        request.request_digest,
    )
    _REGISTERED[id(value)] = value
    return value
