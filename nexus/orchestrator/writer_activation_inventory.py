"""Fail-closed loader for the owner-installed pre-hold inventory."""

from __future__ import annotations

import hashlib
import json
import os
import stat
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from nexus.events.state_owner_manifest import StateOwnerSelection
from nexus.orchestrator.state_owner_transition_authority import (
    AuthorityPublication,
    LoadedSourceIdentity,
)

DEFAULT_INVENTORY_PATH = Path(
    "/Users/jameschen/Library/Application Support/Nexus/writer-transition/bootstrap-inventory.json"
)
_ROLES = {"task_state", "event_log", "runtime_receipt", "effect_journal"}


class PreholdInventoryError(RuntimeError):
    pass


def _regular_bytes(path: Path, *, owner_only: bool = False) -> bytes:
    path = Path(path)
    try:
        info = path.lstat()
    except OSError as exc:
        raise PreholdInventoryError("INVENTORY_READ_FAILED") from exc
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        raise PreholdInventoryError("INVENTORY_FILE_UNSAFE")
    if owner_only and (info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) & 0o077):
        raise PreholdInventoryError("INVENTORY_FILE_NOT_OWNER_ONLY")
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        try:
            before = os.fstat(fd)
            data = os.read(fd, before.st_size + 1)
            after = os.fstat(fd)
        finally:
            os.close(fd)
        current = path.lstat()
    except OSError as exc:
        raise PreholdInventoryError("INVENTORY_READ_FAILED") from exc
    if (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
    ) != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns) or (
        current.st_dev,
        current.st_ino,
    ) != (after.st_dev, after.st_ino):
        raise PreholdInventoryError("INVENTORY_FILE_CHANGED")
    return data


def _object(data: bytes) -> dict[str, Any]:
    def pairs(items):
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                raise PreholdInventoryError("INVENTORY_DUPLICATE_FIELD")
            result[key] = value
        return result

    try:
        value = json.loads(data, object_pairs_hook=pairs)
    except (TypeError, ValueError) as exc:
        raise PreholdInventoryError("INVENTORY_JSON_INVALID") from exc
    if not isinstance(value, dict):
        raise PreholdInventoryError("INVENTORY_OBJECT_REQUIRED")
    return value


def _text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PreholdInventoryError(f"INVENTORY_{name.upper()}_INVALID")
    return value


def _root(value: Any, name: str) -> Path:
    if isinstance(value, Path):
        path = value.expanduser()
    else:
        path = Path(_text(value, name)).expanduser()
    if not path.is_absolute() or ".." in path.parts:
        raise PreholdInventoryError(f"INVENTORY_{name.upper()}_INVALID")
    resolved = path.resolve()
    if resolved != path:
        raise PreholdInventoryError(f"INVENTORY_{name.upper()}_NOT_CANONICAL")
    try:
        info = resolved.lstat()
    except OSError as exc:
        raise PreholdInventoryError(f"INVENTORY_{name.upper()}_MISSING") from exc
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
        raise PreholdInventoryError(f"INVENTORY_{name.upper()}_UNSAFE")
    return resolved


@dataclass(frozen=True, slots=True)
class LoadedRootIntent:
    root_id: str
    root: Path
    owner_id: str
    selections: tuple[StateOwnerSelection, ...]
    next_writer_id: str
    authority_publication: AuthorityPublication | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "root", _root(self.root, "root"))
        if not isinstance(self.selections, tuple):
            object.__setattr__(self, "selections", tuple(self.selections))
        if not self.selections:
            raise PreholdInventoryError("INVENTORY_SELECTIONS_REQUIRED")
        if not _text(self.root_id, "root_id") or not _text(self.owner_id, "owner_id"):
            raise PreholdInventoryError("INVENTORY_ROOT_IDENTITY_INVALID")
        _text(self.next_writer_id, "next_writer_id")
        if not isinstance(self.authority_publication, AuthorityPublication):
            raise PreholdInventoryError("INVENTORY_AUTHORITY_PUBLICATION_INVALID")
        seen: set[str] = set()
        for selection in self.selections:
            if not isinstance(selection, StateOwnerSelection):
                raise PreholdInventoryError("INVENTORY_SELECTION_TYPE_INVALID")
            if selection.role not in _ROLES or selection.entry_id in seen:
                raise PreholdInventoryError("INVENTORY_SELECTION_ROLE_INVALID")
            seen.add(selection.entry_id)
            relative = Path(selection.relative_path)
            if relative.is_absolute() or ".." in relative.parts or not selection.relative_path:
                raise PreholdInventoryError("INVENTORY_SELECTION_PATH_INVALID")


@dataclass(frozen=True, slots=True)
class LoadedPreholdInventory:
    source_root: Path
    source: LoadedSourceIdentity
    cohort_id: str
    task_id: str
    roots: tuple[LoadedRootIntent, ...]
    installed_receipt_sha256: str
    accepted_source_receipt: Path
    accepted_source_receipt_sha256: str
    raw_bytes: bytes = b""
    source_root_identity: tuple[int, int] = (0, 0)
    host_manifest_sha256: str = ""

    def __post_init__(self) -> None:
        source_root = _root(self.source_root, "source_root")
        object.__setattr__(self, "source_root", source_root)
        if not isinstance(self.source, LoadedSourceIdentity):
            raise PreholdInventoryError("INVENTORY_SOURCE_TYPE_INVALID")
        roots = tuple(self.roots)
        object.__setattr__(self, "roots", roots)
        if len(roots) != 3 or any(not isinstance(item, LoadedRootIntent) for item in roots):
            raise PreholdInventoryError("INVENTORY_THREE_ROOTS_REQUIRED")
        paths = [item.root for item in roots]
        if len(set(paths)) != 3 or any(
            a in b.parents or b in a.parents for i, a in enumerate(paths) for b in paths[i + 1 :]
        ):
            raise PreholdInventoryError("INVENTORY_ROOTS_OVERLAP")
        roles = {item.root_id: {selection.role for selection in item.selections} for item in roots}
        if {frozenset(value) for value in roles.values()} != {
            frozenset({"task_state"}),
            frozenset({"event_log"}),
            frozenset({"runtime_receipt", "effect_journal"}),
        }:
            raise PreholdInventoryError("INVENTORY_ROLE_VECTOR_INVALID")
        if len({item.root_id for item in roots}) != 3 or not _text(self.cohort_id, "cohort_id"):
            raise PreholdInventoryError("INVENTORY_ROOT_VECTOR_INVALID")
        if len(self.installed_receipt_sha256) != 64 or any(
            c not in "0123456789abcdef" for c in self.installed_receipt_sha256
        ):
            raise PreholdInventoryError("INVENTORY_RECEIPT_HASH_INVALID")
        if not isinstance(self.raw_bytes, bytes) or not self.raw_bytes:
            raise PreholdInventoryError("INVENTORY_RAW_BYTES_REQUIRED")
        info = source_root.lstat()
        if self.source_root_identity != (info.st_dev, info.st_ino):
            raise PreholdInventoryError("INVENTORY_SOURCE_ROOT_IDENTITY_CHANGED")
        _text(self.task_id, "task_id")
        receipt = Path(self.accepted_source_receipt)
        if not receipt.is_absolute() or receipt.is_symlink():
            raise PreholdInventoryError("INVENTORY_SOURCE_RECEIPT_PATH_INVALID")
        if len(self.accepted_source_receipt_sha256) != 64:
            raise PreholdInventoryError("INVENTORY_SOURCE_RECEIPT_HASH_INVALID")
        if self.host_manifest_sha256 and len(self.host_manifest_sha256) != 64:
            raise PreholdInventoryError("INVENTORY_HOST_MANIFEST_HASH_INVALID")


def _git_identity(root: Path) -> tuple[str, str]:
    try:
        head = subprocess.check_output(
            ["git", "-C", str(root), "rev-parse", "HEAD"], text=True
        ).strip()
        tree = subprocess.check_output(
            ["git", "-C", str(root), "rev-parse", "HEAD^{tree}"], text=True
        ).strip()
    except (OSError, subprocess.CalledProcessError) as exc:
        raise PreholdInventoryError("INVENTORY_SOURCE_GIT_UNAVAILABLE") from exc
    return head, tree


def _verify_host_manifest(
    path: Path, source: LoadedSourceIdentity, module_root: Path, expected_sha256: str
) -> None:
    """Verify the installed host payload before accepting its source identity."""
    # Installed package manifests are wheel payloads (normally 0644); their
    # integrity comes from the inventory pin and stable physical hashing.
    manifest = _regular_bytes(path)
    if hashlib.sha256(manifest).hexdigest() != expected_sha256:
        raise PreholdInventoryError("INVENTORY_HOST_MANIFEST_HASH_MISMATCH")
    data = _object(manifest)
    if data.get("schema") != "astra.installed_host.provenance.v1" or data.get("version") != 1:
        raise PreholdInventoryError("INVENTORY_HOST_PROVENANCE_SCHEMA_INVALID")
    if (
        data.get("source_repository") != source.repository
        or data.get("source_head") != source.source_head
        or data.get("source_tree") != source.source_tree
    ):
        raise PreholdInventoryError("INVENTORY_HOST_PROVENANCE_MISMATCH")
    payloads = data.get("payload_python_sha256")
    runtime = data.get("runtime")
    if not isinstance(runtime, Mapping):
        runtime = data
    runtime_payloads = runtime.get("payload_sha256")
    required = ("distribution_name", "version", "wheel_sha256", "manifest_sha256")
    if (
        not isinstance(payloads, Mapping)
        or not payloads
        or not all(
            isinstance(key, str) and isinstance(value, str) for key, value in payloads.items()
        )
        or not isinstance(runtime_payloads, Mapping)
        or not runtime_payloads
        or not all(
            isinstance(key, str) and isinstance(value, str)
            for key, value in runtime_payloads.items()
        )
        or any(
            not isinstance(runtime.get(key), str) or not runtime[key].strip() for key in required
        )
    ):
        raise PreholdInventoryError("INVENTORY_HOST_PROVENANCE_INCOMPLETE")
    for key in ("wheel_sha256", "manifest_sha256"):
        if len(runtime[key]) != 64 or any(char not in "0123456789abcdef" for char in runtime[key]):
            raise PreholdInventoryError("INVENTORY_HOST_PROVENANCE_HASH_INVALID")
    for relative, expected in tuple(payloads.items()) + tuple(runtime_payloads.items()):
        candidate = Path(relative)
        if (
            candidate.is_absolute()
            or ".." in candidate.parts
            or not expected
            or len(expected) != 64
            or any(char not in "0123456789abcdef" for char in expected)
        ):
            raise PreholdInventoryError("INVENTORY_HOST_PAYLOAD_PATH_INVALID")
        physical = module_root / candidate
        if hashlib.sha256(_regular_bytes(physical)).hexdigest() != expected:
            raise PreholdInventoryError("INVENTORY_HOST_PAYLOAD_MISMATCH")


def _load(path: Path, *, loaded_module_root: Path | None = None) -> LoadedPreholdInventory:
    raw = _regular_bytes(path, owner_only=True)
    data = _object(raw)
    if data.get("schema") != "nexus.writer_activation_prehold_inventory.v1":
        raise PreholdInventoryError("INVENTORY_SCHEMA_INVALID")
    expected_hash = data.get("installed_receipt_sha256")
    unsigned = dict(data)
    unsigned.pop("installed_receipt_sha256", None)
    canonical_unsigned = json.dumps(
        unsigned, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode()
    if (
        not isinstance(expected_hash, str)
        or hashlib.sha256(canonical_unsigned).hexdigest() != expected_hash
    ):
        raise PreholdInventoryError("INVENTORY_RECEIPT_HASH_MISMATCH")
    source_data = data.get("source")
    if not isinstance(source_data, Mapping):
        raise PreholdInventoryError("INVENTORY_SOURCE_MISSING")
    source_root = _root(data.get("backing_source_root"), "source_root")
    source = LoadedSourceIdentity(
        repository=_text(source_data.get("repository"), "repository"),
        source_head=_text(source_data.get("source_head"), "source_head"),
        source_tree=_text(source_data.get("source_tree"), "source_tree"),
        card_path=_text(source_data.get("card_path"), "card_path"),
        card_sha256=_text(source_data.get("card_sha256"), "card_sha256"),
    )
    head, tree = _git_identity(source_root)
    if (head, tree) != (source.source_head, source.source_tree):
        raise PreholdInventoryError("INVENTORY_SOURCE_GIT_MISMATCH")
    card_path = Path(source.card_path)
    if card_path.is_absolute() or ".." in card_path.parts:
        raise PreholdInventoryError("INVENTORY_CARD_PATH_INVALID")
    card = source_root / card_path
    if not card.is_file() or hashlib.sha256(_regular_bytes(card)).hexdigest() != source.card_sha256:
        raise PreholdInventoryError("INVENTORY_CARD_MISMATCH")
    module_root = (loaded_module_root or Path(__file__).resolve().parents[2]).resolve()
    if module_root != source_root:
        manifest = module_root / "nexus" / "_host_artifact_manifest.json"
        if not manifest.is_file():
            raise PreholdInventoryError("INVENTORY_HOST_PROVENANCE_MISSING")
        host_manifest_sha = _text(data.get("host_manifest_sha256"), "host_manifest_sha256")
        _verify_host_manifest(manifest, source, module_root, host_manifest_sha)
    else:
        host_manifest_sha = ""
    roots_data = data.get("roots")
    if not isinstance(roots_data, list):
        raise PreholdInventoryError("INVENTORY_ROOTS_MISSING")
    roots = []
    for item in roots_data:
        if not isinstance(item, Mapping):
            raise PreholdInventoryError("INVENTORY_ROOT_INVALID")
        try:
            selections = tuple(
                StateOwnerSelection(
                    str(s.get("entry_id")), str(s.get("role")), str(s.get("relative_path"))
                )
                for s in item.get("selections", ())
                if isinstance(s, Mapping)
            )
        except Exception as exc:
            raise PreholdInventoryError("INVENTORY_SELECTION_INVALID") from exc
        publication = item.get("authority_publication")
        if not isinstance(publication, Mapping):
            raise PreholdInventoryError("INVENTORY_AUTHORITY_PUBLICATION_MISSING")
        tracked = Path(_text(publication.get("tracked_relative"), "tracked_relative"))
        durable = Path(_text(publication.get("durable_path"), "durable_path"))
        durable_resolved = durable.resolve()
        if (
            tracked.is_absolute()
            or ".." in tracked.parts
            or not tracked.parts
            or tracked.parts[0] != "tasks"
            or not durable.is_absolute()
            or path.parent.resolve() not in durable_resolved.parents
            or any(part.is_symlink() for part in durable_resolved.parents if part.exists())
        ):
            raise PreholdInventoryError("INVENTORY_AUTHORITY_PUBLICATION_PATH_INVALID")
        roots.append(
            LoadedRootIntent(
                item.get("root_id"),
                item.get("root"),
                item.get("owner_id"),
                selections,
                item.get("next_writer_id"),
                AuthorityPublication(tracked, durable),
            )
        )
    info = source_root.lstat()
    source_receipt = Path(_text(data.get("accepted_source_receipt"), "accepted_source_receipt"))
    source_receipt_sha = _text(
        data.get("accepted_source_receipt_sha256"), "accepted_source_receipt_sha256"
    )
    if not source_receipt.is_absolute() or source_receipt.parent.resolve() != path.parent.resolve():
        raise PreholdInventoryError("INVENTORY_SOURCE_RECEIPT_PATH_INVALID")
    if (
        hashlib.sha256(_regular_bytes(source_receipt, owner_only=True)).hexdigest()
        != source_receipt_sha
    ):
        raise PreholdInventoryError("INVENTORY_SOURCE_RECEIPT_HASH_MISMATCH")
    return LoadedPreholdInventory(
        source_root,
        source,
        _text(data.get("cohort_id"), "cohort_id"),
        _text(data.get("task_id"), "task_id"),
        tuple(roots),
        expected_hash,
        source_receipt,
        source_receipt_sha,
        raw,
        (info.st_dev, info.st_ino),
        host_manifest_sha,
    )


def load_installed_prehold_inventory() -> LoadedPreholdInventory:
    return _load(DEFAULT_INVENTORY_PATH)


def _load_installed_prehold_inventory(
    path: Path, *, loaded_module_root: Path | None = None
) -> LoadedPreholdInventory:
    """Internal deterministic seam for tests; public loading has no path selector."""
    return _load(Path(path), loaded_module_root=loaded_module_root)
