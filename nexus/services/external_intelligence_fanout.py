from __future__ import annotations

import contextlib
import fcntl
import hashlib
import json
import os
import re
import subprocess
import tempfile
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Iterator, Mapping, Sequence

from nexus.core.argv_command import ProcessGroupReapingUnavailable, run_reaping_process_group
from nexus.core.hardened_git import (
    linked_worktree_git_dir,
    repository_config_can_start_a_program,
    repository_git_dir,
    run_hardened_git,
)
from nexus.services.external_intelligence import (
    ENVELOPE_SCHEMA,
    OBSERVED_MODEL_ATTESTATION_MISMATCH,
    ExternalIntelligenceError,
    observed_model_violation,
    parse_external_execution_envelope,
    validate_selected_worker,
)
from nexus.services.external_intelligence_core_binding import (
    CAPABILITY_DISCOVERY_INDEX_PATH,
    MAX_REPAIRS_PER_UNIT_LIMIT,
    OPERATING_MODE_PATH,
    CoreAuthorityInputs,
    CoreBindingError,
    binding_validity_seconds,
    bound_operation_material,
    build_acceptance_contract,
    build_capability_discovery_receipt,
    build_integration_authority,
    build_repository_mutation_binding,
    canonical_origin_repository,
    core_hash,
    derive_bound_envelope,
    envelope_sha256,
    parse_bound_execution_envelope_v2,
    unit_closure_cycle_seconds,
    validate_repository_mutation_binding,
)

FANOUT_DECISION_SCHEMA = "external_intelligence_fanout_decision.v1"
DISPATCH_ATTEMPT_SCHEMA = "external_intelligence_dispatch_attempt.v1"
WORKER_RESULT_SCHEMA = "external_intelligence_worker_result.v1"
WORKER_RECEIPT_SCHEMA = "external_intelligence_worker_receipt.v1"
FANOUT_RUN_SCHEMA = "external_intelligence_fanout_run.v1"
PROVIDER = "opencode"
MODEL = "opencode-go/deepseek-v4-flash"
PROVIDER_ID = "opencode-go"
MODEL_ID = "deepseek-v4-flash"
CLAIM_CEILING = "CANDIDATE_READY_FOR_VERIFICATION"
_SESSION_RE = re.compile(r"^ses_[A-Za-z0-9_-]{8,}$")
_SHA1_RE = re.compile(r"^[0-9a-f]{40}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_PREFIXED_SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_SLUG_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,119}$")


class FanoutError(RuntimeError):
    pass


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha256(value: bytes | str) -> str:
    raw = value.encode("utf-8") if isinstance(value, str) else value
    return hashlib.sha256(raw).hexdigest()


def _worker_selection_sha256(
    selected_worker: Mapping[str, Any] | None, *, provider: str, model: str
) -> str:
    if selected_worker is None:
        material: Mapping[str, Any] = {
            "selected_worker": None,
            "provider": provider,
            "model": model,
        }
    else:
        try:
            worker = validate_selected_worker(selected_worker)
        except ExternalIntelligenceError as exc:
            raise FanoutError("INVALID_SELECTED_WORKER") from exc
        if worker["provider"] != provider or worker["model"] != model:
            raise FanoutError("SESSION_WORKER_PROVIDER_MODEL_CONFLICT")
        material = {"selected_worker": worker, "provider": provider, "model": model}
    return _sha256(_canonical_json(material))


def _atomic_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = (json.dumps(dict(value), sort_keys=True, indent=2, ensure_ascii=False) + "\n").encode(
        "utf-8"
    )
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def _run_git(root: Path, *args: str, timeout: float = 30.0, git_dir: Path | None = None) -> str:
    """``git <args>`` in ``root``; with ``git_dir`` (from ``_worker_git_dir``) the call runs
    through the shared hardened runner, pinned to that git dir."""
    if git_dir is not None:
        result = run_hardened_git(root, *args, git_dir=git_dir, timeout=timeout)
    else:
        result = subprocess.run(
            ["git", *args],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()[:1000]
        raise FanoutError(f"GIT_COMMAND_FAILED:{args[0]}:{detail}")
    return result.stdout.strip()


def _worker_git_dir(root: Path, controller_root: str = "") -> Path:
    """The git dir to pin for git calls in a worker's worktree.

    The worker could rewrite the worktree's ``.git`` pointer or anything under it, so the
    worktree must be a linked worktree registered in the Controller's git dir
    (``controller_root``), and the repository config must name no program the command line
    cannot switch off.  Only a lease whose allocator names no Controller may instead be a
    repository whose ``.git`` directory sits in ``root``."""
    if controller_root:
        git_dir = linked_worktree_git_dir(root, Path(controller_root))
    else:
        git_dir = linked_worktree_git_dir(root) or _rooted_git_dir(root)
    if git_dir is None:
        raise FanoutError("WORKSPACE_GIT_DIR_UNTRUSTED")
    if repository_config_can_start_a_program(root, git_dir):
        raise FanoutError("WORKSPACE_GIT_CONFIG_NAMES_A_PROGRAM")
    return git_dir


def _rooted_git_dir(root: Path) -> Path | None:
    dotgit = root / ".git"
    if dotgit.is_symlink() or not dotgit.is_dir():
        return None  # a ``.git`` file the worker could have re-pointed
    return repository_git_dir(root)


EIA_COMMIT_EMAIL_DOMAIN = "nexus.invalid"
EIA_COMPOSER_NAME = "EIA closure composer"
EIA_COMPOSER_EMAIL = f"eia-closure@{EIA_COMMIT_EMAIL_DOMAIN}"
EIA_TRAILER_WORKER = "Nexus-EIA-Worker"
EIA_TRAILER_MODEL = "Nexus-EIA-Model"
EIA_TRAILER_BACKEND = "Nexus-EIA-Backend"
_IDENTITY_UNSAFE_RE = re.compile(r"[<>\x00-\x1f\x7f]+")
_EMAIL_TAG_UNSAFE_RE = re.compile(r"[^a-z0-9._-]+")


def _identity_text(value: Any, fallback: str) -> str:
    text = _IDENTITY_UNSAFE_RE.sub(" ", str(value or "")).strip()
    return " ".join(text.split())[:200] or fallback


def eia_worker_identity(
    *,
    provider: str,
    model: str,
    worker_id: str = "",
    worker_backend: str = "",
) -> dict[str, str]:
    """Deterministic git identity + provenance for an EIA-created candidate commit.

    Derived only from the bound worker, never from host git config, e.g.
    ``EIA open-swe worker (opencli_chatgpt/advanced)
    <eia-worker+opencli_chatgpt@nexus.invalid>``.
    """
    provider_text = _identity_text(provider, "unknown")
    model_text = _identity_text(model, "unknown")
    model_label = model_text if "/" in model_text else f"{provider_text}/{model_text}"
    backend = _identity_text(worker_backend, "worker")
    backend_label = backend.replace("_", "-")
    tag = _EMAIL_TAG_UNSAFE_RE.sub("-", provider_text.lower()).strip("-.")[:64] or "unknown"
    return {
        "name": f"EIA {backend_label} worker ({model_label})",
        "email": f"eia-worker+{tag}@{EIA_COMMIT_EMAIL_DOMAIN}",
        "worker_id": _identity_text(worker_id, "unbound"),
        "model": model_label,
        "backend": backend,
    }


def eia_git_commit(
    root: Path,
    *,
    subject: str,
    name: str,
    email: str,
    trailers: Sequence[tuple[str, str]],
    timeout: float = 60.0,
    git_dir: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    """``git commit`` with an explicit, command-scoped identity.

    Author and committer come from ``author.*``/``committer.*`` set on this command
    line (it outranks every config file, and the hardened runner reads no global or
    system config), so the host's ``user.*`` is never consulted and nothing is written
    to any git config.  Signing is disabled for the same reason: a host signing key
    would attest the wrong producer.  The commit runs through the shared hardened
    runner (no hooks, no signing program), pinned to ``git_dir`` (checked by
    ``_worker_git_dir`` when not given).
    """
    trailer_block = "\n".join(
        f"{key}: {_identity_text(value, 'unknown')}" for key, value in trailers
    )
    args = [
        *("-c", f"author.name={name}", "-c", f"author.email={email}"),
        *("-c", f"committer.name={name}", "-c", f"committer.email={email}"),
        *("commit", "--no-verify", "-m", subject),
    ]
    if trailer_block:
        args.extend(["-m", trailer_block])
    if git_dir is None:
        try:
            git_dir = _worker_git_dir(root)
        except FanoutError as exc:
            return subprocess.CompletedProcess(["git", *args], 128, "", f"{exc}\n")
    return run_hardened_git(root, *args, git_dir=git_dir, timeout=timeout)


def _safe_slug(value: Any, field: str) -> str:
    text = str(value or "").strip()
    if not _SLUG_RE.fullmatch(text):
        raise FanoutError(f"INVALID_{field.upper()}")
    return text


def _safe_relative_path(value: Any) -> str:
    raw = str(value or "")
    if any(not character.isprintable() for character in raw):
        raise FanoutError("INVALID_MUTATION_PATH")
    text = raw.strip()
    try:
        path = PurePosixPath(text)
    except (TypeError, ValueError) as exc:
        raise FanoutError("INVALID_MUTATION_PATH") from exc
    if not text or path.is_absolute() or ".." in path.parts or "\\" in text or "\x00" in text:
        raise FanoutError("INVALID_MUTATION_PATH")
    return path.as_posix()


def _path_matches(path: str, boundary: str) -> bool:
    p = path.rstrip("/")
    b = boundary.rstrip("/")
    return p == b or p.startswith(b + "/")


def _paths_overlap(left: str, right: str) -> bool:
    return _path_matches(left, right) or _path_matches(right, left)


def _sets_overlap(left: Sequence[str], right: Sequence[str]) -> bool:
    return any(_paths_overlap(a, b) for a in left for b in right)


def _parse_excerpt_base_hashes(value: Any, mutation_paths: Sequence[str]) -> dict[str, str] | None:
    if value is None:
        return None
    if not isinstance(value, Mapping) or not value:
        raise FanoutError("INVALID_EXCERPT_BASE_HASHES")
    result: dict[str, str] = {}
    for raw_path, raw_hash in value.items():
        path = _safe_relative_path(raw_path)
        digest = str(raw_hash or "").strip().lower()
        if path not in mutation_paths or not _SHA256_RE.fullmatch(digest) or path in result:
            raise FanoutError("INVALID_EXCERPT_BASE_HASHES")
        result[path] = digest
    return dict(sorted(result.items()))


def _verify_excerpt_base_hashes(root: Path, unit: "ExecutionUnit") -> None:
    """Refuse when a file the semantic stage saw only as an excerpt is not, at
    the unit's base revision, the exact whole file the excerpt's evidence ref
    was minted from (#2357)."""
    for path, expected in (unit.excerpt_base_hashes or {}).items():
        blob = _git_blob_bytes(root, unit.expected_base_sha, path)
        if blob is None or _sha256(blob) != expected:
            raise FanoutError("EXCERPT_BASE_FILE_HASH_MISMATCH")


@dataclass(frozen=True)
class ExecutionUnit:
    task_id: str
    unit_id: str
    envelope_ref: str
    envelope_sha256: str
    expected_base_sha: str
    mutation_paths: tuple[str, ...]
    dependencies_ready: bool = True
    priority: int = 0
    allow_deletions: bool = False
    selected_worker: Mapping[str, Any] | None = None
    provider: str = PROVIDER
    model: str = MODEL
    # Core binding authority inputs (Issue contract + Task Card + worker binding).
    # Deliberately excluded from identity(): unit identity, attempts and receipts of
    # unbound dispatch stay byte-identical; the minted binding pins this authority.
    core_authority: Mapping[str, Any] | None = field(default=None, compare=False, hash=False)
    # Whole-file sha256 at expected_base_sha of each mutation path the semantic
    # stage saw only as a symbol excerpt (#2357). Part of identity() only when set,
    # so units without excerpts keep their existing identity byte-for-byte.
    excerpt_base_hashes: Mapping[str, str] | None = None

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "ExecutionUnit":
        task_id = _safe_slug(value.get("task_id"), "task_id")
        unit_id = _safe_slug(value.get("unit_id"), "unit_id")
        envelope_ref = str(value.get("envelope_ref") or "").strip()
        envelope_sha256 = str(value.get("envelope_sha256") or "").strip().lower()
        expected_base_sha = str(value.get("expected_base_sha") or "").strip().lower()
        raw_paths = value.get("mutation_paths")
        if not isinstance(raw_paths, (list, tuple)) or not raw_paths:
            raise FanoutError("MUTATION_PATHS_REQUIRED")
        mutation_paths = tuple(dict.fromkeys(_safe_relative_path(path) for path in raw_paths))
        if not envelope_ref:
            raise FanoutError("ENVELOPE_REF_REQUIRED")
        if not _SHA256_RE.fullmatch(envelope_sha256):
            raise FanoutError("INVALID_ENVELOPE_SHA256")
        if not _SHA1_RE.fullmatch(expected_base_sha):
            raise FanoutError("INVALID_EXPECTED_BASE_SHA")
        priority = value.get("priority", 0)
        if not isinstance(priority, int):
            raise FanoutError("INVALID_PRIORITY")
        excerpt_base_hashes = _parse_excerpt_base_hashes(
            value.get("excerpt_base_hashes"), mutation_paths
        )
        selected_worker_raw = value.get("selected_worker")
        if selected_worker_raw is not None:
            try:
                selected_worker = validate_selected_worker(selected_worker_raw)
            except ExternalIntelligenceError as exc:
                raise FanoutError("INVALID_SELECTED_WORKER") from exc
        else:
            selected_worker = None
        provider = str(
            (selected_worker.get("provider") if selected_worker else None)
            or value.get("provider")
            or PROVIDER
        )
        model = str(
            (selected_worker.get("model") if selected_worker else None)
            or value.get("model")
            or MODEL
        )
        return cls(
            task_id=task_id,
            unit_id=unit_id,
            envelope_ref=envelope_ref,
            envelope_sha256=envelope_sha256,
            expected_base_sha=expected_base_sha,
            mutation_paths=mutation_paths,
            dependencies_ready=bool(value.get("dependencies_ready", True)),
            priority=priority,
            allow_deletions=bool(value.get("allow_deletions", False)),
            selected_worker=selected_worker,
            provider=provider,
            model=model,
            core_authority=dict(value["core_authority"])
            if isinstance(value.get("core_authority"), Mapping)
            else None,
            excerpt_base_hashes=excerpt_base_hashes,
        )

    def identity(self) -> dict[str, Any]:
        result = {
            "task_id": self.task_id,
            "unit_id": self.unit_id,
            "envelope_ref": self.envelope_ref,
            "envelope_sha256": self.envelope_sha256,
            "expected_base_sha": self.expected_base_sha,
            "mutation_paths": list(self.mutation_paths),
            "dependencies_ready": self.dependencies_ready,
            "priority": self.priority,
            "allow_deletions": self.allow_deletions,
            "provider": self.provider,
            "model": self.model,
        }
        if self.selected_worker is not None:
            result["selected_worker"] = dict(self.selected_worker)
        if self.excerpt_base_hashes:
            result["excerpt_base_hashes"] = dict(sorted(self.excerpt_base_hashes.items()))
        return result

    @property
    def identity_sha256(self) -> str:
        return _sha256(_canonical_json(self.identity()))


@dataclass(frozen=True)
class CapacityLease:
    requested_concurrency: int
    provider_available: int
    workspace_available: int
    controller_attention_limit: int
    active_workers: int = 0
    pending_verifications: int = 0
    pending_repairs: int = 0
    pending_candidates: int = 0

    def effective_capacity(self) -> tuple[int, dict[str, int]]:
        values = (
            self.requested_concurrency,
            self.provider_available,
            self.workspace_available,
            self.controller_attention_limit,
            self.active_workers,
            self.pending_verifications,
            self.pending_repairs,
            self.pending_candidates,
        )
        if any(not isinstance(value, int) or value < 0 for value in values):
            raise FanoutError("INVALID_CAPACITY_LEASE")
        pressure = (
            self.active_workers
            + self.pending_verifications
            + self.pending_repairs
            + self.pending_candidates
        )
        controller_available = max(0, self.controller_attention_limit - pressure)
        provider_free = max(0, self.provider_available - self.active_workers)
        capacity = min(
            self.requested_concurrency,
            provider_free,
            self.workspace_available,
            controller_available,
        )
        return capacity, {
            "control_pressure": pressure,
            "controller_available": controller_available,
            "provider_free": provider_free,
            "workspace_available": self.workspace_available,
        }


@dataclass(frozen=True)
class WorkspaceLease:
    workspace_id: str
    path: str
    expected_base_sha: str
    # The repository whose git dir registered this worktree ("" when unknown).
    controller_root: str = ""


@dataclass(frozen=True)
class OpenCodeRunResult:
    status: str
    worker_backend: str = "opencode"
    session_id: str = ""
    response_text: str = ""
    provider_id: str = ""
    model_id: str = ""
    directory: str = ""
    version: str = ""
    stdout_sha256: str = ""
    stderr_sha256: str = ""
    export_sha256: str = ""
    argv_sha256: str = ""
    process_started: bool = False
    outcome_unknown: bool = False
    retry_safe: bool = False
    error: str = ""
    diagnosis_status: str = ""
    diagnosis_sha256: str = ""
    diagnosis_evidence_paths: tuple[str, ...] = ()
    repair_admitted: bool = False
    repair_phase_count: int = 0
    worker_identity_sha256: str = ""
    operation_id: str = ""
    effect_authorization_hash: str = ""
    tool_projection_hash: str = ""
    execution_exposure_receipt: dict[str, Any] | None = None
    core_binding_status: str = ""
    core_binding_hash: str = ""
    acceptance_contract_hash: str = ""
    model_invocation_receipts: tuple[dict[str, Any], ...] = ()


def _observed_model_unproven(transport: Any, result: OpenCodeRunResult) -> bool:
    """Defense in depth: a COMPLETED result must prove the pinned observed model."""

    expected = getattr(transport, "expected_observed_model", "")
    if not isinstance(expected, str) or not expected:
        return False
    return observed_model_violation(
        result.model_invocation_receipts,
        expected=expected,
        provider_id=result.provider_id,
        model_id=result.model_id,
        operation_id=result.operation_id,
        strict=True,
    )


def plan_fanout(
    units: Iterable[Mapping[str, Any] | ExecutionUnit],
    lease: CapacityLease,
    *,
    completed_unit_ids: Iterable[str] = (),
) -> dict[str, Any]:
    parsed = [
        unit if isinstance(unit, ExecutionUnit) else ExecutionUnit.from_mapping(unit)
        for unit in units
    ]
    if not parsed:
        raise FanoutError("EXECUTION_UNITS_REQUIRED")
    task_ids = {unit.task_id for unit in parsed}
    if len(task_ids) != 1:
        raise FanoutError("MIXED_TASK_FANOUT_FORBIDDEN")
    unit_ids = [unit.unit_id for unit in parsed]
    if len(set(unit_ids)) != len(unit_ids):
        raise FanoutError("DUPLICATE_UNIT_ID")

    capacity, pressure = lease.effective_capacity()
    completed_ids = set(completed_unit_ids)
    if not completed_ids.issubset(unit_ids):
        raise FanoutError("COMPLETED_UNIT_UNKNOWN")
    ordered = sorted(parsed, key=lambda unit: (-unit.priority, unit.unit_id))
    admitted: list[ExecutionUnit] = []
    blocked_dependencies: list[str] = []
    deferred_overlap: list[str] = []
    deferred_capacity: list[str] = []

    completed_paths = [unit.mutation_paths for unit in ordered if unit.unit_id in completed_ids]
    for unit in ordered:
        if unit.unit_id in completed_ids:
            continue
        if not unit.dependencies_ready:
            blocked_dependencies.append(unit.unit_id)
            continue
        if any(_sets_overlap(unit.mutation_paths, paths) for paths in completed_paths):
            deferred_overlap.append(unit.unit_id)
            continue
        if any(
            _sets_overlap(unit.mutation_paths, selected.mutation_paths) for selected in admitted
        ):
            deferred_overlap.append(unit.unit_id)
            continue
        if len(admitted) >= capacity:
            deferred_capacity.append(unit.unit_id)
            continue
        admitted.append(unit)

    providers = {unit.provider for unit in parsed}
    models = {unit.model for unit in parsed}
    workers = {
        _canonical_json(unit.selected_worker) if unit.selected_worker else "" for unit in parsed
    }
    if len(providers) > 1 or len(models) > 1 or len(workers) > 1:
        raise FanoutError("MIXED_WORKER_FANOUT_FORBIDDEN")

    material = {
        "schema": FANOUT_DECISION_SCHEMA,
        "task_id": next(iter(task_ids)),
        "requested_concurrency": lease.requested_concurrency,
        "effective_capacity": capacity,
        "control_pressure": pressure,
        "admitted_units": [unit.unit_id for unit in admitted],
        "completed_units": sorted(completed_ids),
        "blocked_dependencies": blocked_dependencies,
        "deferred_mutation_overlap": deferred_overlap,
        "deferred_capacity": deferred_capacity,
        "fixed_worker_pool": False,
        "provider": parsed[0].provider,
        "model": parsed[0].model,
    }
    if parsed[0].selected_worker is not None:
        material["selected_worker"] = dict(parsed[0].selected_worker)
    material["decision_sha256"] = _sha256(_canonical_json(material))
    return material


class GitWorktreeAllocator:
    """Allocate fresh detached worktrees; lifecycle cleanup is intentionally out of scope."""

    def __init__(
        self, repository_root: str | os.PathLike[str], workspace_root: str | os.PathLike[str]
    ):
        self.repository_root = Path(repository_root).expanduser().resolve()
        self.workspace_root = Path(workspace_root).expanduser().resolve()

    def allocate(self, unit: ExecutionUnit) -> WorkspaceLease:
        live_base = _run_git(self.repository_root, "cat-file", "-t", unit.expected_base_sha)
        if live_base != "commit":
            raise FanoutError("EXPECTED_BASE_NOT_COMMIT")
        workspace_id = f"ei-{unit.task_id}-{unit.unit_id}-{uuid.uuid4().hex[:12]}"
        path = self.workspace_root / workspace_id
        if path.exists():
            raise FanoutError("WORKSPACE_COLLISION")
        self.workspace_root.mkdir(parents=True, exist_ok=True)
        result = subprocess.run(
            ["git", "worktree", "add", "--detach", str(path), unit.expected_base_sha],
            cwd=self.repository_root,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise FanoutError(
                f"WORKSPACE_ALLOCATION_FAILED:{(result.stderr or result.stdout).strip()[:1000]}"
            )
        observed = _run_git(path, "rev-parse", "HEAD")
        dirty = _run_git(path, "status", "--porcelain=v1")
        if observed != unit.expected_base_sha or dirty:
            raise FanoutError("WORKSPACE_FRESHNESS_FAILED")
        _verify_excerpt_base_hashes(path, unit)
        return WorkspaceLease(
            workspace_id=workspace_id,
            path=str(path),
            expected_base_sha=observed,
            controller_root=str(self.repository_root),
        )


_REPAIR_TERMINAL_STATES = frozenset({"COMPLETED", "TERMINAL_BLOCKED", "FAILED"})
_REPAIR_ATTEMPT_REQUIRED_FIELDS = (
    "schema",
    "task_id",
    "unit_id",
    "attempt_id",
    "mode",
    "repair_id",
    "state",
    "session_id",
    "workspace_id",
    "workspace_path",
    "expected_head",
    "repair_ref",
    "repair_sha256",
    "parent_receipt_id",
    "transport_status",
)


class FanoutStore:
    def __init__(self, root: str | os.PathLike[str]):
        self.root = Path(root).expanduser().resolve()
        self.attempts = self.root / "attempts"
        self.receipts = self.root / "receipts"
        self.sessions = self.root / "sessions"
        self.bound_envelopes = self.root / "bound-envelopes"
        self.capability_discovery = self.root / "capability-discovery"

    @staticmethod
    def _unit_key(task_id: str, unit_id: str) -> str:
        return f"{task_id}--{unit_id}"

    def _attempt_path(self, task_id: str, unit_id: str, suffix: str = "initial") -> Path:
        return self.attempts / f"{self._unit_key(task_id, unit_id)}--{suffix}.json"

    def _receipt_path(self, task_id: str, unit_id: str, suffix: str = "initial") -> Path:
        return self.receipts / f"{self._unit_key(task_id, unit_id)}--{suffix}.json"

    def _session_path(self, session_id: str) -> Path:
        return self.sessions / f"{_sha256(session_id)}.json"

    def existing_initial_attempt(self, unit: ExecutionUnit) -> dict[str, Any] | None:
        path = self._attempt_path(unit.task_id, unit.unit_id)
        if not path.exists():
            return None
        value = json.loads(path.read_text(encoding="utf-8"))
        if (
            value.get("schema") != DISPATCH_ATTEMPT_SCHEMA
            or value.get("unit_identity_sha256") != unit.identity_sha256
        ):
            raise FanoutError("FANOUT_ATTEMPT_IDENTITY_MISMATCH")
        return value

    def existing_initial_receipt(self, unit: ExecutionUnit) -> dict[str, Any] | None:
        path = self._receipt_path(unit.task_id, unit.unit_id)
        if not path.exists():
            return None
        value = json.loads(path.read_text(encoding="utf-8"))
        if (
            value.get("schema") != WORKER_RECEIPT_SCHEMA
            or value.get("task_id") != unit.task_id
            or value.get("unit_id") != unit.unit_id
            or value.get("envelope_sha256") != unit.envelope_sha256
            or value.get("base_sha") != unit.expected_base_sha
            or value.get("mutation_paths") != list(unit.mutation_paths)
        ):
            raise FanoutError("FANOUT_RECEIPT_IDENTITY_MISMATCH")
        return value

    def prepare_initial(self, unit: ExecutionUnit, workspace: WorkspaceLease) -> dict[str, Any]:
        path = self._attempt_path(unit.task_id, unit.unit_id)
        previous: dict[str, Any] | None = None
        if path.exists():
            value = json.loads(path.read_text(encoding="utf-8"))
            if value.get("state") == "RETRY_SAFE" and value.get("retry_safe") is True:
                if int(value.get("retry_count", 0)) >= 1:
                    raise FanoutError("FANOUT_REPLAY_FORBIDDEN")
                previous = value
            elif value.get("state") in {"PREPARED", "DISPATCHING", "OUTCOME_UNKNOWN"}:
                raise FanoutError("FANOUT_RECONCILIATION_REQUIRED")
            else:
                raise FanoutError("FANOUT_REPLAY_FORBIDDEN")
        attempt = {
            "schema": DISPATCH_ATTEMPT_SCHEMA,
            "task_id": unit.task_id,
            "unit_id": unit.unit_id,
            "unit_identity_sha256": unit.identity_sha256,
            "attempt_id": str(uuid.uuid4()),
            "mode": "INITIAL",
            "state": "PREPARED",
            "retry_safe": True,
            "workspace_id": workspace.workspace_id,
            "workspace_path": workspace.path,
            "expected_base_sha": workspace.expected_base_sha,
            "envelope_ref": unit.envelope_ref,
            "envelope_sha256": unit.envelope_sha256,
        }
        if previous is not None:
            attempt.update({
                "retry_of_attempt_id": previous.get("attempt_id"),
                "retry_count": int(previous.get("retry_count", 0)) + 1,
            })
        _atomic_json(path, attempt)
        return attempt

    def prepare_repair(
        self,
        previous_receipt: Mapping[str, Any],
        *,
        repair_id: str,
        repair_ref: str,
        repair_sha256: str,
        core_binding: Mapping[str, str] | None = None,
        operation_id: str | None = None,
    ) -> dict[str, Any]:
        task_id = _safe_slug(previous_receipt.get("task_id"), "task_id")
        unit_id = _safe_slug(previous_receipt.get("unit_id"), "unit_id")
        repair_id = _safe_slug(repair_id, "repair_id")
        if operation_id is not None and (
            not isinstance(operation_id, str) or _SHA256_RE.fullmatch(operation_id) is None
        ):
            raise FanoutError("OPERATION_ID_REQUIRED")
        with self._repair_lock(task_id, unit_id):
            return self._prepare_repair_locked(
                previous_receipt,
                task_id=task_id,
                unit_id=unit_id,
                repair_id=repair_id,
                repair_ref=repair_ref,
                repair_sha256=repair_sha256,
                core_binding=core_binding,
                operation_id=operation_id,
            )

    @contextlib.contextmanager
    def _repair_lock(self, task_id: str, unit_id: str) -> Iterator[None]:
        """Per-unit exclusive lock serializing repair attempt check-then-write."""
        lock_dir = self.root / "locks"
        lock_dir.mkdir(parents=True, exist_ok=True)
        lock_path = lock_dir / f"{self._unit_key(task_id, unit_id)}--repair.lock"
        fd = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            yield
        finally:
            os.close(fd)

    def _prepare_repair_locked(
        self,
        previous_receipt: Mapping[str, Any],
        *,
        task_id: str,
        unit_id: str,
        repair_id: str,
        repair_ref: str,
        repair_sha256: str,
        core_binding: Mapping[str, str] | None,
        operation_id: str | None,
    ) -> dict[str, Any]:
        suffix = f"repair-{repair_id}"
        path = self._attempt_path(task_id, unit_id, suffix)
        if path.exists():
            value = json.loads(path.read_text(encoding="utf-8"))
            if value.get("state") in {"PREPARED", "DISPATCHING", "OUTCOME_UNKNOWN"}:
                raise FanoutError("FANOUT_RECONCILIATION_REQUIRED")
            raise FanoutError("FANOUT_REPLAY_FORBIDDEN")
        unresolved = self._unresolved_repair_records(task_id, unit_id)
        if any(
            value is None
            or value.get("state") != "PREPARED"
            or self._repair_sent_marker(str(value.get("attempt_id") or "")).exists()
            for value in unresolved.values()
        ):
            # Another continuation of this unit's session has no known outcome: a new
            # one would race it on the same session/workspace.  Reconcile it first.
            raise FanoutError("FANOUT_RECONCILIATION_REQUIRED")
        session_id = str(previous_receipt.get("session_id") or "")
        self.assert_session_owner(
            session_id,
            task_id=task_id,
            unit_id=unit_id,
            workspace_id=str(previous_receipt.get("workspace_id") or ""),
            selected_worker=previous_receipt.get("selected_worker"),
            provider=str(previous_receipt.get("provider") or PROVIDER),
            model=str(previous_receipt.get("model") or MODEL),
        )
        attempt = {
            "schema": DISPATCH_ATTEMPT_SCHEMA,
            "task_id": task_id,
            "unit_id": unit_id,
            "attempt_id": str(uuid.uuid4()),
            "mode": "REPAIR_CONTINUE",
            "repair_id": repair_id,
            "state": "PREPARED",
            "retry_safe": True,
            "session_id": session_id,
            "workspace_id": previous_receipt.get("workspace_id"),
            "workspace_path": previous_receipt.get("workspace_path"),
            "expected_head": previous_receipt.get("candidate_commit"),
            "repair_ref": repair_ref,
            "repair_sha256": repair_sha256,
            "parent_receipt_id": previous_receipt.get("receipt_id"),
            "prepare_seq": self._next_repair_seq(task_id, unit_id),
        }
        if core_binding is not None:
            # A bound continuation reuses the parent's binding; the root bound
            # operation/attempt it was minted for are recorded alongside.
            attempt.update({key: str(core_binding[key]) for key in _CORE_CONTINUATION_FIELDS})
        if operation_id is not None:
            attempt["operation_id"] = operation_id
        # A well-formed PREPARED sibling was never sent: a repair only leaves PREPARED
        # through mark_repair_dispatching, under this same lock, before the transport
        # is called.  Abandon it so a crashed prepare cannot block the unit forever.
        # The new attempt is written first so every abandoned record points at an
        # attempt that exists (a crash in between leaves two PREPARED records, which
        # the next prepare abandons together).
        _atomic_json(path, attempt)
        for sibling_path, sibling in unresolved.items():
            assert sibling is not None
            abandoned = dict(sibling)
            abandoned.update({
                "state": "FAILED",
                "retry_safe": False,
                "transport_status": "ABANDONED_BEFORE_DISPATCH",
                "superseded_by_attempt_id": attempt["attempt_id"],
            })
            _atomic_json(sibling_path, abandoned)
        return attempt

    def mark_repair_dispatching(self, attempt: Mapping[str, Any]) -> dict[str, Any]:
        """PREPARED -> DISPATCHING for a repair, refusing an abandoned/changed record."""
        task_id = str(attempt["task_id"])
        unit_id = str(attempt["unit_id"])
        suffix = f"repair-{_safe_slug(attempt.get('repair_id'), 'repair_id')}"
        path = self._attempt_path(task_id, unit_id, suffix)
        with self._repair_lock(task_id, unit_id):
            try:
                on_disk = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError) as exc:
                raise FanoutError("FANOUT_REPAIR_ATTEMPT_SUPERSEDED") from exc
            if on_disk != dict(attempt) or on_disk.get("state") != "PREPARED":
                raise FanoutError("FANOUT_REPAIR_ATTEMPT_SUPERSEDED")
            # Durable sent-marker first: once it exists the attempt may have reached
            # the transport and can never be abandoned as "never sent".
            marker = self._repair_sent_marker(str(attempt["attempt_id"]))
            marker.parent.mkdir(parents=True, exist_ok=True)
            try:
                fd = os.open(marker, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            except FileExistsError as exc:
                raise FanoutError("FANOUT_REPAIR_ATTEMPT_SUPERSEDED") from exc
            os.close(fd)
            value = dict(attempt)
            value.update({"state": "DISPATCHING", "retry_safe": False})
            _atomic_json(path, value)
            return value

    def _repair_sent_marker(self, attempt_id: str) -> Path:
        return self.root / "repair-sent" / _safe_slug(attempt_id or "missing", "attempt_id")

    def _next_repair_seq(self, task_id: str, unit_id: str) -> int:
        """Monotonic per-unit prepare sequence (caller holds the per-unit lock)."""
        path = self.root / "locks" / f"{self._unit_key(task_id, unit_id)}--repair.seq"
        try:
            current = int(path.read_text(encoding="utf-8").strip() or "0")
        except FileNotFoundError:
            current = 0
        except (OSError, ValueError) as exc:
            raise FanoutError("FANOUT_REPAIR_SEQUENCE_INVALID") from exc
        nxt = current + 1
        tmp = path.with_suffix(".seq.tmp")
        tmp.write_text(str(nxt), encoding="utf-8")
        os.replace(tmp, path)
        return nxt

    def initial_attempt_is_bound(self, task_id: str, unit_id: str) -> bool:
        """Whether the unit's initial attempt was Core-bound; fails closed.

        Only an initial attempt record that exists, parses, carries this unit's
        identity and has none of the Core fields is positively unbound.  A missing,
        unreadable or malformed record, or a partial Core record, raises.
        """
        path = self._attempt_path(task_id, unit_id)
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise FanoutError("INITIAL_ATTEMPT_EVIDENCE_MISSING") from exc
        if (
            not isinstance(value, dict)
            or value.get("schema") != DISPATCH_ATTEMPT_SCHEMA
            or value.get("mode") != "INITIAL"
            or value.get("task_id") != task_id
            or value.get("unit_id") != unit_id
        ):
            raise FanoutError("INITIAL_ATTEMPT_EVIDENCE_MISSING")
        present = [key for key in _CORE_BOUND_ATTEMPT_FIELDS if key in value]
        if present and len(present) != len(_CORE_BOUND_ATTEMPT_FIELDS):
            raise FanoutError("CORE_BINDING_ATTEMPT_RECORD_INCOMPLETE")
        if present and not (
            isinstance(value.get("bound_envelope_ref"), str)
            and value["bound_envelope_ref"].strip()
            and isinstance(value.get("bound_envelope_sha256"), str)
            and _SHA256_RE.fullmatch(value["bound_envelope_sha256"]) is not None
            and all(
                isinstance(value.get(key), str)
                and _PREFIXED_SHA256_RE.fullmatch(value[key]) is not None
                for key in ("core_binding_hash", "acceptance_contract_hash")
            )
        ):
            raise FanoutError("INITIAL_ATTEMPT_EVIDENCE_MISSING")
        return bool(present)

    def existing_repair_attempt(
        self, task_id: str, unit_id: str, repair_id: str
    ) -> dict[str, Any] | None:
        suffix = f"repair-{_safe_slug(repair_id, 'repair_id')}"
        path = self._attempt_path(
            _safe_slug(task_id, "task_id"), _safe_slug(unit_id, "unit_id"), suffix
        )
        if not path.exists():
            return None
        value = json.loads(path.read_text(encoding="utf-8"))
        if (
            value.get("schema") != DISPATCH_ATTEMPT_SCHEMA
            or value.get("mode") != "REPAIR_CONTINUE"
            or value.get("task_id") != task_id
            or value.get("unit_id") != unit_id
            or value.get("repair_id") != repair_id
        ):
            raise FanoutError("FANOUT_ATTEMPT_IDENTITY_MISMATCH")
        return value

    def unresolved_repair_ids(self, task_id: str, unit_id: str) -> list[str]:
        """Repair ids of this unit whose continuation is not proven terminal."""
        prefix = f"{self._unit_key(task_id, unit_id)}--repair-"
        return [
            path.name[len(prefix) : -len(".json")]
            for path in self._unresolved_repair_records(task_id, unit_id)
        ]

    def _unresolved_repair_records(
        self, task_id: str, unit_id: str
    ) -> dict[Path, dict[str, Any] | None]:
        """Repair attempt records of this unit that are not proven terminal.

        Fails closed: an unreadable record, one with a wrong schema/identity or a
        missing/unknown state, or a terminal-looking record whose outcome is not
        proven (``_repair_terminal_proven``) is unresolved and mapped to None.  A
        well-formed non-terminal record is mapped to itself.
        """
        prefix = f"{self._unit_key(task_id, unit_id)}--repair-"
        if not self.attempts.is_dir():
            return {}
        unresolved: dict[Path, dict[str, Any] | None] = {}
        for path in sorted(self.attempts.glob(f"{prefix}*.json")):
            repair_id = path.name[len(prefix) : -len(".json")]
            try:
                value = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                unresolved[path] = None
                continue
            well_formed = (
                isinstance(value, dict)
                and value.get("schema") == DISPATCH_ATTEMPT_SCHEMA
                and value.get("mode") == "REPAIR_CONTINUE"
                and value.get("task_id") == task_id
                and value.get("unit_id") == unit_id
                and value.get("repair_id") == repair_id
            )
            if not well_formed:
                unresolved[path] = None
            elif value.get("state") in _REPAIR_TERMINAL_STATES:
                if not self._repair_terminal_proven(value, repair_id):
                    unresolved[path] = None
            else:
                unresolved[path] = value
        return unresolved

    def _repair_terminal_proven(self, attempt: Mapping[str, Any], repair_id: str) -> bool:
        """A terminal repair state counts only with the evidence that state leaves.

        - COMPLETED / TERMINAL_BLOCKED: the full attempt record plus the matching,
          self-consistent repair receipt (ids, session, parent, operation id).
        - FAILED: only an abandoned never-dispatched attempt, whose superseding
          attempt of the same unit exists.
        """
        if any(not attempt.get(key) for key in _REPAIR_ATTEMPT_REQUIRED_FIELDS):
            return False
        state = attempt.get("state")
        task_id = str(attempt["task_id"])
        unit_id = str(attempt["unit_id"])
        if state == "FAILED":
            superseded_by = attempt.get("superseded_by_attempt_id")
            own_seq = attempt.get("prepare_seq")
            if (
                attempt.get("transport_status") != "ABANDONED_BEFORE_DISPATCH"
                or attempt.get("retry_safe") is not False
                or not isinstance(superseded_by, str)
                or not superseded_by
                or superseded_by == attempt.get("attempt_id")
                or type(own_seq) is not int
                # Never sent: mark_repair_dispatching never created its marker.
                or self._repair_sent_marker(str(attempt["attempt_id"])).exists()
            ):
                return False
            prefix = f"{self._unit_key(task_id, unit_id)}--repair-"
            for path in self.attempts.glob(f"{prefix}*.json"):
                try:
                    other = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    continue
                if not isinstance(other, dict) or other.get("attempt_id") != superseded_by:
                    continue
                other_seq = other.get("prepare_seq")
                return (
                    other.get("schema") == DISPATCH_ATTEMPT_SCHEMA
                    and other.get("mode") == "REPAIR_CONTINUE"
                    and other.get("task_id") == task_id
                    and other.get("unit_id") == unit_id
                    and other.get("repair_id") == path.name[len(prefix) : -len(".json")]
                    and other.get("repair_id") != attempt.get("repair_id")
                    and other.get("session_id") == attempt.get("session_id")
                    and other.get("workspace_id") == attempt.get("workspace_id")
                    and type(other_seq) is int
                    and other_seq > own_seq
                )
            return False
        receipt_status = {
            "COMPLETED": "CANDIDATE_READY_FOR_VERIFICATION",
            "TERMINAL_BLOCKED": "WORKER_BLOCKED",
        }.get(str(state))
        if receipt_status is None:
            return False
        path = self._receipt_path(task_id, unit_id, f"repair-{repair_id}")
        try:
            receipt = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return False
        if not isinstance(receipt, dict):
            return False
        material = {key: value for key, value in receipt.items() if key != "receipt_id"}
        return (
            receipt.get("schema") == WORKER_RECEIPT_SCHEMA
            and receipt.get("receipt_id") == _sha256(_canonical_json(material))
            and receipt.get("status") == receipt_status
            and receipt.get("mode") == "REPAIR_CONTINUE"
            and receipt.get("task_id") == task_id
            and receipt.get("unit_id") == unit_id
            and receipt.get("repair_id") == repair_id
            and receipt.get("attempt_id") == attempt.get("attempt_id")
            and receipt.get("session_id") == attempt.get("session_id")
            and receipt.get("workspace_id") == attempt.get("workspace_id")
            and receipt.get("parent_receipt_id") == attempt.get("parent_receipt_id")
            and receipt.get("operation_id", "") == attempt.get("operation_id", "")
        )

    def bound_envelope_path(self, task_id: str, unit_id: str, attempt_id: str) -> Path:
        attempt_key = _safe_slug(attempt_id, "attempt_id")
        return self.bound_envelopes / f"{self._unit_key(task_id, unit_id)}--{attempt_key}.json"

    def write_bound_envelope(
        self, attempt: Mapping[str, Any], bound_envelope: Mapping[str, Any]
    ) -> Path:
        path = self.bound_envelope_path(
            str(attempt["task_id"]), str(attempt["unit_id"]), str(attempt["attempt_id"])
        )
        _atomic_json(path, bound_envelope)
        return path

    def write_capability_discovery_receipt(self, receipt: Mapping[str, Any]) -> Path:
        digest = core_hash(dict(receipt)).removeprefix("sha256:")
        path = self.capability_discovery / f"{digest}.json"
        if path.exists():
            existing = json.loads(path.read_text(encoding="utf-8"))
            if existing != dict(receipt):
                raise FanoutError("CAPABILITY_DISCOVERY_RECEIPT_COLLISION")
            return path
        _atomic_json(path, receipt)
        return path

    def record_core_binding(
        self,
        attempt: Mapping[str, Any],
        *,
        bound_envelope_ref: str,
        bound_envelope_sha256: str,
        core_binding_hash: str,
        acceptance_contract_hash: str,
        capability_discovery_receipt_ref: str,
        suffix: str = "initial",
    ) -> dict[str, Any]:
        value = dict(attempt)
        value.update({
            "bound_envelope_ref": bound_envelope_ref,
            "bound_envelope_sha256": bound_envelope_sha256,
            "core_binding_hash": core_binding_hash,
            "acceptance_contract_hash": acceptance_contract_hash,
            "capability_discovery_receipt_ref": capability_discovery_receipt_ref,
        })
        _atomic_json(self._attempt_path(value["task_id"], value["unit_id"], suffix), value)
        return value

    def mark_dispatching(
        self, attempt: Mapping[str, Any], *, suffix: str = "initial"
    ) -> dict[str, Any]:
        value = dict(attempt)
        value.update({"state": "DISPATCHING", "retry_safe": False})
        _atomic_json(self._attempt_path(value["task_id"], value["unit_id"], suffix), value)
        return value

    def bind_operation_id(
        self, attempt: Mapping[str, Any], operation_id: str, *, suffix: str = "initial"
    ) -> dict[str, Any]:
        if not isinstance(operation_id, str) or _SHA256_RE.fullmatch(operation_id) is None:
            raise FanoutError("OPERATION_ID_REQUIRED")
        value = dict(attempt)
        value["operation_id"] = operation_id
        _atomic_json(self._attempt_path(value["task_id"], value["unit_id"], suffix), value)
        return value

    def finish_attempt(
        self,
        attempt: Mapping[str, Any],
        *,
        state: str,
        transport_status: str,
        suffix: str = "initial",
    ) -> dict[str, Any]:
        if state not in {
            "COMPLETED",
            "TERMINAL_BLOCKED",
            "FAILED",
            "RETRY_SAFE",
            "OUTCOME_UNKNOWN",
        }:
            raise FanoutError("INVALID_ATTEMPT_STATE")
        value = dict(attempt)
        value.update({
            "state": state,
            "retry_safe": state == "RETRY_SAFE",
            "transport_status": transport_status,
        })
        _atomic_json(self._attempt_path(value["task_id"], value["unit_id"], suffix), value)
        return value

    def claim_session(
        self,
        session_id: str,
        *,
        task_id: str,
        unit_id: str,
        workspace_id: str,
        selected_worker: Mapping[str, Any] | None = None,
        provider: str = PROVIDER,
        model: str = MODEL,
    ) -> None:
        if not _SESSION_RE.fullmatch(session_id):
            raise FanoutError("INVALID_SESSION_ID")
        path = self._session_path(session_id)
        binding = {
            "session_id": session_id,
            "task_id": task_id,
            "unit_id": unit_id,
            "workspace_id": workspace_id,
            "provider": provider,
            "model": model,
            "worker_selection_sha256": _worker_selection_sha256(
                selected_worker, provider=provider, model=model
            ),
        }
        if path.exists():
            existing = json.loads(path.read_text(encoding="utf-8"))
            if existing != binding:
                raise FanoutError("SESSION_BINDING_CONFLICT")
            return
        _atomic_json(path, binding)

    def assert_session_owner(
        self,
        session_id: str,
        *,
        task_id: str,
        unit_id: str,
        workspace_id: str,
        selected_worker: Mapping[str, Any] | None = None,
        provider: str = PROVIDER,
        model: str = MODEL,
    ) -> None:
        path = self._session_path(session_id)
        if not path.exists():
            raise FanoutError("SESSION_BINDING_MISSING")
        binding = json.loads(path.read_text(encoding="utf-8"))
        expected = {
            "session_id": session_id,
            "task_id": task_id,
            "unit_id": unit_id,
            "workspace_id": workspace_id,
            "provider": provider,
            "model": model,
            "worker_selection_sha256": _worker_selection_sha256(
                selected_worker, provider=provider, model=model
            ),
        }
        if binding.get("worker_selection_sha256") != expected["worker_selection_sha256"]:
            raise FanoutError("SESSION_WORKER_SELECTION_CONFLICT")
        if binding != expected:
            raise FanoutError("SESSION_BINDING_CONFLICT")

    def write_receipt(self, receipt: Mapping[str, Any], *, suffix: str = "initial") -> Path:
        path = self._receipt_path(str(receipt["task_id"]), str(receipt["unit_id"]), suffix)
        _atomic_json(path, receipt)
        return path


class OpenCodeWorkerTransport:
    """Fresh OpenCode session per initial unit; exact-session continuation for repair only."""

    def __init__(
        self,
        executable: str = "opencode",
        *,
        model: str = MODEL,
        provider_id: str = "",
        model_id: str = "",
        timeout: float = 300.0,
    ):
        self.executable = executable
        self.model = model
        if provider_id and model_id:
            self.provider_id = provider_id
            self.model_id = model_id
        elif "/" in model:
            p_id, m_id = model.split("/", 1)
            self.provider_id = provider_id or p_id
            self.model_id = model_id or m_id
        else:
            self.provider_id = provider_id or PROVIDER_ID
            self.model_id = model_id or MODEL_ID
        self.timeout = float(timeout)

    def run_new(self, *, prompt: str, artifact_path: str, workspace_path: str) -> OpenCodeRunResult:
        return self._run(
            prompt=prompt,
            artifact_path=artifact_path,
            workspace_path=workspace_path,
            session_id="",
        )

    def continue_session(
        self,
        *,
        session_id: str,
        prompt: str,
        artifact_path: str,
        workspace_path: str,
    ) -> OpenCodeRunResult:
        if not _SESSION_RE.fullmatch(session_id):
            raise FanoutError("INVALID_SESSION_ID")
        return self._run(
            prompt=prompt,
            artifact_path=artifact_path,
            workspace_path=workspace_path,
            session_id=session_id,
        )

    def _run(
        self, *, prompt: str, artifact_path: str, workspace_path: str, session_id: str
    ) -> OpenCodeRunResult:
        argv = [
            self.executable,
            "run",
            prompt,
            "--model",
            self.model,
            "--format",
            "json",
            "--dir",
            workspace_path,
        ]
        if session_id:
            argv.extend(["--session", session_id])
        argv.extend(["-f", artifact_path])
        safe_argv = [self.executable, "run", "<compact-bootstrap>", *argv[3:]]
        argv_sha256 = _sha256(_canonical_json(safe_argv))
        try:
            # The worker leads its own process group, which is SIGKILLed on every exit, normal
            # or timeout, before it is reaped: nothing it started in that group outlives the
            # run, and a pipe held open past the timeout no longer blocks (#3052).
            process = run_reaping_process_group(
                argv, cwd=workspace_path, stdin=subprocess.DEVNULL, timeout=self.timeout
            )
        except FileNotFoundError as exc:
            return OpenCodeRunResult(
                status="OPENCODE_NOT_FOUND",
                argv_sha256=argv_sha256,
                process_started=False,
                retry_safe=True,
                error=str(exc),
            )
        except ProcessGroupReapingUnavailable as exc:
            # Refused before anything was spawned.
            return OpenCodeRunResult(
                status="OPENCODE_START_REFUSED",
                argv_sha256=argv_sha256,
                process_started=False,
                retry_safe=False,
                error=str(exc),
            )
        except subprocess.TimeoutExpired as exc:
            # No SIGTERM grace before the group SIGKILL (#3076): a timed-out run is
            # OUTCOME_UNKNOWN whatever OpenCode does on SIGTERM, ``-f`` names an input file it
            # does not write, and a reconcile accepts only a reply OpenCode already committed to
            # its SQLite store with finish "stop", which a SIGKILL cannot tear.
            return OpenCodeRunResult(
                status="OPENCODE_OUTCOME_UNKNOWN",
                stdout_sha256=_sha256(exc.output or ""),
                stderr_sha256=_sha256(exc.stderr or str(exc)),
                argv_sha256=argv_sha256,
                process_started=True,
                outcome_unknown=True,
                retry_safe=False,
                error="provider_timeout",
            )

        stdout = process.stdout or ""
        stderr = process.stderr or ""
        if process.returncode != 0:
            return OpenCodeRunResult(
                status="OPENCODE_OUTCOME_UNKNOWN",
                stdout_sha256=_sha256(stdout),
                stderr_sha256=_sha256(stderr),
                argv_sha256=argv_sha256,
                process_started=True,
                outcome_unknown=True,
                retry_safe=False,
                error=f"provider_nonzero:{process.returncode}",
            )
        try:
            parsed_session, response_text = self._parse_events(stdout)
            if session_id and parsed_session != session_id:
                raise FanoutError("SESSION_CONTINUATION_MISMATCH")
            attestation = self._export_attestation(parsed_session, workspace_path)
        except (FanoutError, ValueError, TypeError, json.JSONDecodeError) as exc:
            return OpenCodeRunResult(
                status="OPENCODE_ATTESTATION_UNKNOWN",
                stdout_sha256=_sha256(stdout),
                stderr_sha256=_sha256(stderr),
                argv_sha256=argv_sha256,
                process_started=True,
                outcome_unknown=True,
                retry_safe=False,
                error=str(exc),
            )
        return OpenCodeRunResult(
            status="COMPLETED",
            session_id=parsed_session,
            response_text=response_text,
            provider_id=attestation["provider_id"],
            model_id=attestation["model_id"],
            directory=attestation["directory"],
            version=attestation["version"],
            stdout_sha256=_sha256(stdout),
            stderr_sha256=_sha256(stderr),
            export_sha256=attestation["export_sha256"],
            argv_sha256=argv_sha256,
            process_started=True,
            outcome_unknown=False,
            retry_safe=False,
        )

    @staticmethod
    def _parse_events(stdout: str) -> tuple[str, str]:
        session_ids: set[str] = set()
        texts: list[str] = []
        finished = False
        for raw in stdout.splitlines():
            if not raw.strip():
                continue
            row = json.loads(raw)
            if not isinstance(row, dict):
                raise FanoutError("OPENCODE_EVENT_INVALID")
            data = row.get("data")
            if row.get("type") == "message.part.updated" and isinstance(data, Mapping):
                session = str(data.get("sessionID") or "")
                part = data.get("part")
                if session:
                    session_ids.add(session)
                if isinstance(part, Mapping):
                    part_type = part.get("type")
                    if part_type == "text" and isinstance(part.get("text"), str):
                        texts.append(part["text"])
                    if part_type in ("step-finish", "step_finish"):
                        finished = True
                continue
            session = str(row.get("sessionID") or "")
            if session:
                session_ids.add(session)
            if row.get("type") == "text":
                part = row.get("part")
                if isinstance(part, Mapping) and isinstance(part.get("text"), str):
                    texts.append(part["text"])
            if row.get("type") == "step_finish":
                finished = True
        if len(session_ids) != 1 or not finished or not texts:
            raise FanoutError("OPENCODE_EVENT_INCOMPLETE")
        session_id = next(iter(session_ids))
        if not _SESSION_RE.fullmatch(session_id):
            raise FanoutError("INVALID_SESSION_ID")
        return session_id, texts[-1]

    def _db_json(self, query: str, *, cwd: str) -> list[dict[str, Any]]:
        result = subprocess.run(
            [self.executable, "db", query, "--format", "json"],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=min(self.timeout, 60.0),
            check=False,
        )
        if result.returncode != 0:
            raise FanoutError("OPENCODE_DB_QUERY_FAILED")
        try:
            value = json.loads(result.stdout or "[]")
        except json.JSONDecodeError as exc:
            raise FanoutError("OPENCODE_DB_QUERY_INVALID") from exc
        if not isinstance(value, list) or any(not isinstance(row, dict) for row in value):
            raise FanoutError("OPENCODE_DB_QUERY_INVALID")
        return value

    @staticmethod
    def _sql_literal(value: str) -> str:
        return "'" + value.replace("'", "''") + "'"

    def reconcile_workspace(self, *, workspace_path: str) -> OpenCodeRunResult:
        expected_directory = str(Path(workspace_path).expanduser().resolve())
        directory_sql = self._sql_literal(expected_directory)
        sessions = self._db_json(
            "select id,directory,version,model,time_created,time_updated from session "
            f"where directory={directory_sql} order by time_created",
            cwd=workspace_path,
        )
        if len(sessions) != 1:
            raise FanoutError("OPENCODE_RECONCILE_SESSION_AMBIGUOUS")
        session = sessions[0]
        session_id = str(session.get("id") or "")
        if not _SESSION_RE.fullmatch(session_id):
            raise FanoutError("INVALID_SESSION_ID")
        try:
            model = json.loads(str(session.get("model") or "{}"))
        except json.JSONDecodeError as exc:
            raise FanoutError("OPENCODE_RECONCILE_MODEL_INVALID") from exc
        if not isinstance(model, Mapping):
            raise FanoutError("OPENCODE_RECONCILE_MODEL_INVALID")
        provider_id = str(model.get("providerID") or "")
        model_id = str(model.get("id") or "")
        if provider_id != self.provider_id or model_id != self.model_id:
            raise FanoutError("OPENCODE_MODEL_ATTESTATION_MISMATCH")
        if (
            str(Path(str(session.get("directory") or "")).expanduser().resolve())
            != expected_directory
        ):
            raise FanoutError("OPENCODE_DIRECTORY_ATTESTATION_MISMATCH")

        session_sql = self._sql_literal(session_id)
        rows = self._db_json(
            "select m.id,"
            "json_extract(m.data,'$.finish') as finish,"
            "json_extract(m.data,'$.providerID') as provider_id,"
            "json_extract(m.data,'$.modelID') as model_id,"
            "json_extract(p.data,'$.text') as text "
            "from message m join part p on p.message_id=m.id "
            f"where m.session_id={session_sql} "
            "and json_extract(m.data,'$.role')='assistant' "
            "and json_extract(p.data,'$.type')='text' "
            "order by m.time_created desc,p.time_created desc limit 1",
            cwd=workspace_path,
        )
        if len(rows) != 1:
            raise FanoutError("OPENCODE_RECONCILE_MESSAGE_AMBIGUOUS")
        latest = rows[0]
        latest_message_id = str(latest.get("id") or "")
        response_text = str(latest.get("text") or "")
        if latest.get("finish") != "stop" or not latest_message_id or not response_text:
            raise FanoutError("OPENCODE_RECONCILE_NOT_TERMINAL")
        if (
            str(latest.get("provider_id") or "") != self.provider_id
            or str(latest.get("model_id") or "") != self.model_id
        ):
            raise FanoutError("OPENCODE_MODEL_ATTESTATION_MISMATCH")
        evidence = {
            "session": session,
            "message_id": latest_message_id,
            "response_sha256": _sha256(response_text),
        }
        return OpenCodeRunResult(
            status="COMPLETED",
            session_id=session_id,
            response_text=response_text,
            provider_id=provider_id,
            model_id=model_id,
            directory=expected_directory,
            version=str(session.get("version") or ""),
            stdout_sha256=_sha256(response_text),
            stderr_sha256=_sha256(""),
            export_sha256=_sha256(_canonical_json(evidence)),
            argv_sha256=_sha256(_canonical_json([self.executable, "db", "<reconcile-workspace>"])),
            process_started=True,
            outcome_unknown=False,
            retry_safe=False,
        )

    def _export_attestation(self, session_id: str, workspace_path: str) -> dict[str, str]:
        result = subprocess.run(
            [self.executable, "export", session_id],
            cwd=workspace_path,
            capture_output=True,
            text=True,
            timeout=min(self.timeout, 60.0),
            check=False,
        )
        if result.returncode != 0:
            raise FanoutError("OPENCODE_EXPORT_FAILED")
        stdout = result.stdout or ""
        info_key = stdout.find('"info"')
        if info_key < 0:
            raise FanoutError("OPENCODE_EXPORT_INVALID")
        info_start = stdout.find("{", info_key)
        if info_start < 0:
            raise FanoutError("OPENCODE_EXPORT_INVALID")
        try:
            info, _ = json.JSONDecoder().raw_decode(stdout, info_start)
        except json.JSONDecodeError as exc:
            raise FanoutError("OPENCODE_EXPORT_INVALID") from exc
        if not isinstance(info, Mapping):
            raise FanoutError("OPENCODE_EXPORT_INVALID")
        model = info.get("model")
        if not isinstance(model, Mapping):
            raise FanoutError("OPENCODE_EXPORT_MODEL_MISSING")
        observed_session = str(info.get("id") or "")
        provider_id = str(model.get("providerID") or "")
        model_id = str(model.get("id") or "")
        directory = str(Path(str(info.get("directory") or "")).expanduser().resolve())
        expected_directory = str(Path(workspace_path).expanduser().resolve())
        if observed_session != session_id:
            raise FanoutError("OPENCODE_EXPORT_SESSION_MISMATCH")
        if provider_id != self.provider_id or model_id != self.model_id:
            raise FanoutError("OPENCODE_MODEL_ATTESTATION_MISMATCH")
        if directory != expected_directory:
            raise FanoutError("OPENCODE_DIRECTORY_ATTESTATION_MISMATCH")
        return {
            "provider_id": provider_id,
            "model_id": model_id,
            "directory": directory,
            "version": str(info.get("version") or ""),
            "export_sha256": _sha256(stdout),
        }


class OpenCodeDeepSeekTransport(OpenCodeWorkerTransport):
    def __init__(
        self,
        executable: str = "opencode",
        *,
        model: str = MODEL,
        provider_id: str = "",
        model_id: str = "",
        timeout: float = 300.0,
    ):
        if model != MODEL:
            raise FanoutError("MODEL_SUBSTITUTION_FORBIDDEN")
        super().__init__(
            executable=executable,
            model=model,
            provider_id=provider_id,
            model_id=model_id,
            timeout=timeout,
        )


def _load_and_verify_artifact(path_value: str, expected_sha256: str) -> tuple[Path, str]:
    path = Path(path_value).expanduser().resolve()
    if not path.is_file():
        raise FanoutError("ARTIFACT_NOT_FOUND")
    raw = path.read_bytes()
    observed = _sha256(raw)
    if observed != expected_sha256:
        raise FanoutError("ARTIFACT_SHA256_MISMATCH")
    try:
        return path, raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise FanoutError("ARTIFACT_UTF8_REQUIRED") from exc


def _verify_envelope_scope(unit: ExecutionUnit) -> Path:
    path = Path(unit.envelope_ref).expanduser().resolve()
    if not path.is_file():
        raise FanoutError("ARTIFACT_NOT_FOUND")
    try:
        text = path.read_text(encoding="utf-8")
        envelope = parse_external_execution_envelope(text)
    except UnicodeDecodeError as exc:
        raise FanoutError("ARTIFACT_UTF8_REQUIRED") from exc
    except ExternalIntelligenceError as exc:
        raise FanoutError("ENVELOPE_CONTRACT_INVALID") from exc
    if _sha256(_canonical_json(envelope)) != unit.envelope_sha256:
        raise FanoutError("ENVELOPE_SHA256_MISMATCH")
    if envelope.get("schema") not in (ENVELOPE_SCHEMA, "external_execution_envelope.v2"):
        raise FanoutError("ENVELOPE_CONTRACT_INVALID")
    binding = envelope.get("binding") or {}
    if binding.get("main_sha") != unit.expected_base_sha:
        raise FanoutError("ENVELOPE_BASE_MISMATCH")
    if envelope.get("schema") == "external_execution_envelope.v2":
        env_worker = envelope.get("selected_worker")
        if not unit.selected_worker or not env_worker:
            raise FanoutError("ENVELOPE_WORKER_BINDING_MISSING")
        if env_worker != dict(unit.selected_worker):
            raise FanoutError("ENVELOPE_WORKER_BINDING_MISMATCH")
    elif envelope.get("selected_worker") and unit.selected_worker:
        if envelope.get("selected_worker") != dict(unit.selected_worker):
            raise FanoutError("ENVELOPE_WORKER_BINDING_MISMATCH")
    scope = envelope.get("scope_signal") or {}
    allowed = [
        *scope.get("production_edit_paths", []),
        *scope.get("required_test_edit_paths", []),
        *scope.get("conditional_migration_paths", []),
    ]
    forbidden = list(scope.get("forbidden_paths", []))
    for mutation in unit.mutation_paths:
        if not any(_path_matches(mutation, boundary) for boundary in allowed):
            raise FanoutError("UNIT_SCOPE_WIDENING_FORBIDDEN")
        if any(_paths_overlap(mutation, boundary) for boundary in forbidden):
            raise FanoutError("UNIT_FORBIDDEN_PATH")
    max_files = scope.get("max_files")
    if isinstance(max_files, int) and len(unit.mutation_paths) > max_files:
        raise FanoutError("UNIT_SCOPE_FILE_LIMIT_EXCEEDED")
    return path


def _workspace_virtual_path(relative_ref: Any, *, required_prefix: str | None = None) -> str:
    """Map a validated repository-relative ref into the worker's virtual root."""
    safe = _safe_relative_path(relative_ref)
    if required_prefix and not safe.startswith(required_prefix.rstrip("/") + "/"):
        raise FanoutError("TASK_CARD_REF_REQUIRED")
    return "/" + safe


def _bootstrap_evidence_refs(unit: ExecutionUnit, envelope_text: str) -> tuple[str, list[str]]:
    try:
        envelope = parse_external_execution_envelope(envelope_text)
    except ExternalIntelligenceError as exc:
        raise FanoutError("ENVELOPE_CONTRACT_INVALID") from exc
    binding = envelope.get("binding")
    if not isinstance(binding, Mapping):
        raise FanoutError("ENVELOPE_CONTRACT_INVALID")
    task_card_ref = binding.get("task_card_ref")
    if not isinstance(task_card_ref, str) or not task_card_ref.strip():
        raise FanoutError("TASK_CARD_REF_REQUIRED")
    task_card_path = _workspace_virtual_path(task_card_ref, required_prefix="tasks")
    target_paths = [_workspace_virtual_path(mutation_path) for mutation_path in unit.mutation_paths]
    return task_card_path, target_paths


def build_worker_bootstrap(
    unit: ExecutionUnit,
    workspace: WorkspaceLease,
    *,
    bound_envelope_ref: str | None = None,
    bound_envelope_sha256: str | None = None,
) -> str:
    """Build a self-contained handoff with provenance-only artifact metadata.

    For a Core-bound dispatch ``envelope_sha256`` names the bound envelope (the
    artifact the runtime admits) and ``semantic_envelope_sha256`` keeps the immutable
    semantic envelope identity.
    """
    if (bound_envelope_ref is None) != (bound_envelope_sha256 is None):
        raise FanoutError("BOUND_ENVELOPE_IDENTITY_INCOMPLETE")
    artifact = _verify_envelope_scope(unit)
    envelope_text = artifact.read_text(encoding="utf-8")
    task_card_path, target_paths = _bootstrap_evidence_refs(unit, envelope_text)
    if unit.selected_worker:
        worker_name = (
            unit.selected_worker.get("worker_id")
            or unit.selected_worker.get("model")
            or "the bounded task engineer"
        )
        role = unit.selected_worker.get("role_ceiling") or "bounded task execution"
        header = f"You are {worker_name}, the {role} for exactly one Nexus execution unit."
        model_adapt_line = (
            "Read and follow the model_adaptation / task brief inside the embedded envelope above."
        )
        guard_line = "Apply only the task-relevant failure guards; encode one evidence-guided same-unit repair and no blind retry or auto-chain."
    elif unit.model != MODEL:
        header = (
            f"You are {unit.model}, the bounded task engineer for exactly one Nexus execution unit."
        )
        model_adapt_line = (
            "Read and follow the model_adaptation / task brief inside the embedded envelope above."
        )
        guard_line = "Apply only the task-relevant failure guards; encode one evidence-guided same-unit repair and no blind retry or auto-chain."
    else:
        header = "You are DeepSeek V4 Flash, the bounded L2 Task Engineer for exactly one Nexus execution unit."
        model_adapt_line = "Read and follow the model_adaptation brief inside the embedded envelope above: role_contract, task_local_invariants, known_failure_guards, execution_strategy, forbidden_inferences, repair_policy."
        guard_line = "Apply only the task-relevant known_failure_guards; encode one evidence-guided same-unit repair and no blind retry or auto-chain."

    if bound_envelope_sha256 is not None:
        envelope_lines = [
            f"envelope_artifact_ref={json.dumps(bound_envelope_ref, ensure_ascii=True)}",
            f"envelope_sha256={bound_envelope_sha256}",
            f"semantic_envelope_sha256={unit.envelope_sha256}",
        ]
    else:
        envelope_lines = [
            f"envelope_artifact_ref={json.dumps(unit.envelope_ref, ensure_ascii=True)}",
            f"envelope_sha256={unit.envelope_sha256}",
        ]
    return "\n".join([
        header,
        f"task_id={unit.task_id}",
        f"unit_id={unit.unit_id}",
        f"expected_base_sha={unit.expected_base_sha}",
        f"workspace_id={workspace.workspace_id}",
        *envelope_lines,
        "The full external_execution_envelope.v1 is embedded in Controller evidence above; use it as the authoritative task brief.",
        "envelope_artifact_ref is provenance/readback metadata only. Do not open envelope_artifact_ref through workspace tools.",
        f"task_card_workspace_path={task_card_path}",
        f"allowed_target_probe_paths={_canonical_json(target_paths)}",
        "Probe only the exact workspace-virtual Task Card and allowed target paths above. Do not use broad glob discovery.",
        model_adapt_line,
        f"authorized_mutation_paths={_canonical_json(list(unit.mutation_paths))}",
        "Do not modify any path outside authorized_mutation_paths. Do not commit, push, merge, approve, integrate, or spawn a replacement model.",
        "Use the embedded envelope as semantic guidance but never widen the Task Card authority.",
        guard_line,
        "When finished, return exactly one JSON object and no markdown/prose:",
        _canonical_json({
            "schema": WORKER_RESULT_SCHEMA,
            "task_id": unit.task_id,
            "unit_id": unit.unit_id,
            "status": "IMPLEMENTATION_COMPLETED|BLOCKED",
            "summary": "short factual summary",
        }),
    ])


def build_repair_bootstrap(
    previous_receipt: Mapping[str, Any],
    *,
    repair_id: str,
    repair_ref: str,
    repair_sha256: str,
) -> str:
    return "\n".join([
        "Continue the exact same execution unit session for a bounded repair.",
        f"task_id={previous_receipt.get('task_id')}",
        f"unit_id={previous_receipt.get('unit_id')}",
        f"repair_id={repair_id}",
        f"repair_artifact_ref={repair_ref}",
        f"repair_sha256={repair_sha256}",
        f"parent_candidate_commit={previous_receipt.get('candidate_commit')}",
        "The repair artifact is attached. Do not widen mutation scope, do not change model/session, and do not commit/push/approve/integrate.",
        "Return exactly one JSON object with schema external_intelligence_worker_result.v1 and status IMPLEMENTATION_COMPLETED or BLOCKED.",
    ])


def _extract_worker_result_object(text: str) -> dict[str, Any]:
    """Return the single JSON object in worker text, tolerating surrounding prose."""
    if not isinstance(text, str) or not text.strip():
        raise FanoutError("WORKER_RESULT_PARSE_FAILED")
    try:
        direct = json.loads(text)
        if isinstance(direct, dict):
            return direct
    except (TypeError, ValueError, json.JSONDecodeError):
        pass
    decoder = json.JSONDecoder()
    found: list[dict[str, Any]] = []
    index = 0
    while True:
        start = text.find("{", index)
        if start < 0:
            break
        try:
            value, end = decoder.raw_decode(text, start)
        except json.JSONDecodeError:
            index = start + 1
            continue
        if isinstance(value, dict):
            found.append(value)
        index = end
    if len(found) != 1:
        raise FanoutError("WORKER_RESULT_PARSE_FAILED")
    return found[0]


def parse_worker_result(text: str, *, task_id: str, unit_id: str) -> dict[str, str]:
    value = _extract_worker_result_object(text)
    required = {"schema", "task_id", "unit_id", "status", "summary"}
    if not isinstance(value, dict) or set(value) != required:
        raise FanoutError("WORKER_RESULT_PARSE_FAILED")
    if value.get("schema") != WORKER_RESULT_SCHEMA:
        raise FanoutError("WORKER_RESULT_PARSE_FAILED")
    if value.get("task_id") != task_id or value.get("unit_id") != unit_id:
        raise FanoutError("WORKER_RESULT_BINDING_MISMATCH")
    if value.get("status") not in {"IMPLEMENTATION_COMPLETED", "BLOCKED"}:
        raise FanoutError("WORKER_RESULT_STATUS_INVALID")
    if not isinstance(value.get("summary"), str) or len(value["summary"]) > 4000:
        raise FanoutError("WORKER_RESULT_PARSE_FAILED")
    return value


def _changed_paths(workspace: Path, base_sha: str, git_dir: Path) -> list[str]:
    tracked = _run_git(workspace, "diff", "--name-only", base_sha, "--", git_dir=git_dir)
    untracked = _run_git(workspace, "ls-files", "--others", "--exclude-standard", git_dir=git_dir)
    paths = [line.strip() for line in (tracked + "\n" + untracked).splitlines() if line.strip()]
    return sorted(dict.fromkeys(paths))


def _deleted_paths(workspace: Path, base_sha: str, git_dir: Path) -> list[str]:
    output = _run_git(workspace, "diff", "--name-status", base_sha, "--", git_dir=git_dir)
    deleted: list[str] = []
    for line in output.splitlines():
        parts = line.split("\t")
        if parts and parts[0].startswith("D") and len(parts) >= 2:
            deleted.append(parts[-1])
    return deleted


def _capture_candidate(
    unit: ExecutionUnit,
    workspace: WorkspaceLease,
    *,
    expected_head: str,
    worker_backend: str = "",
) -> dict[str, Any]:
    root = Path(workspace.path)
    git_dir = _worker_git_dir(root, workspace.controller_root)
    observed_head = _run_git(root, "rev-parse", "HEAD", git_dir=git_dir)
    if observed_head != expected_head:
        raise FanoutError("WORKER_COMMIT_FORBIDDEN")
    _verify_excerpt_base_hashes(root, unit)
    changed = _changed_paths(root, expected_head, git_dir)
    if not changed:
        raise FanoutError("EMPTY_IMPLEMENTATION_RESULT")
    for path in changed:
        if not any(_path_matches(path, boundary) for boundary in unit.mutation_paths):
            raise FanoutError(f"OUT_OF_SCOPE_MUTATION:{path}")
    deleted = _deleted_paths(root, expected_head, git_dir)
    if deleted and not unit.allow_deletions:
        raise FanoutError("DELETION_NOT_AUTHORIZED")

    run_hardened_git(root, "add", "--", *changed, git_dir=git_dir).check_returncode()
    check = run_hardened_git(root, "diff", "--cached", "--check", git_dir=git_dir)
    if check.returncode != 0:
        raise FanoutError(
            f"CANDIDATE_DIFF_CHECK_FAILED:{(check.stdout or check.stderr).strip()[:1000]}"
        )
    staged = [
        line
        for line in _run_git(root, "diff", "--cached", "--name-only", git_dir=git_dir).splitlines()
        if line
    ]
    if sorted(staged) != sorted(changed):
        raise FanoutError("CANDIDATE_STAGED_SCOPE_MISMATCH")
    identity = eia_worker_identity(
        provider=unit.provider,
        model=unit.model,
        worker_id=str((unit.selected_worker or {}).get("worker_id") or ""),
        worker_backend=worker_backend,
    )
    commit = eia_git_commit(
        root,
        subject=f"candidate: {unit.task_id}/{unit.unit_id}",
        name=identity["name"],
        email=identity["email"],
        trailers=(
            (EIA_TRAILER_WORKER, identity["worker_id"]),
            (EIA_TRAILER_MODEL, identity["model"]),
            (EIA_TRAILER_BACKEND, identity["backend"]),
        ),
        git_dir=git_dir,
    )
    if commit.returncode != 0:
        raise FanoutError(
            f"CANDIDATE_COMMIT_FAILED:{(commit.stderr or commit.stdout).strip()[:1000]}"
        )
    candidate_commit = _run_git(root, "rev-parse", "HEAD", git_dir=git_dir)
    candidate_tree = _run_git(root, "rev-parse", "HEAD^{tree}", git_dir=git_dir)
    diff = _run_git(root, "diff", "--binary", expected_head, candidate_commit, git_dir=git_dir)
    return {
        "candidate_commit": candidate_commit,
        "candidate_tree": candidate_tree,
        "candidate_diff_sha256": _sha256(diff),
        "changed_paths": changed,
        "deleted_paths": deleted,
        "parent_commit": expected_head,
    }


def _resolve_worker_transport_identity(
    worker: Mapping[str, Any] | None,
) -> tuple[str, str, str] | None:
    if not worker:
        return None
    model_val = str(worker.get("model") or "").strip()
    provider_val = str(worker.get("provider") or "").strip()
    if "/" in model_val:
        p_id, m_id = model_val.split("/", 1)
        provider_id = p_id.strip()
        model_id = m_id.strip()
        if provider_id != provider_val:
            raise FanoutError("INVALID_SELECTED_WORKER")
        exec_model = model_val
    elif provider_val in ("opencode", "opencode-go"):
        provider_id = "opencode-go"
        model_id = model_val
        exec_model = f"opencode-go/{model_id}" if model_id else ""
    elif provider_val == "deepseek":
        provider_id = "deepseek"
        model_id = model_val
        exec_model = f"deepseek/{model_id}" if model_id else ""
    else:
        raise FanoutError("UNSUPPORTED_WORKER_TRANSPORT")
    if not provider_id or not model_id or not exec_model:
        raise FanoutError("UNSUPPORTED_WORKER_TRANSPORT")
    return exec_model, provider_id, model_id


_CORE_BOUND_ATTEMPT_FIELDS = (
    "bound_envelope_ref",
    "bound_envelope_sha256",
    "core_binding_hash",
    "acceptance_contract_hash",
)


def _git_blob_bytes(root: Path, revision: str, rel_path: str) -> bytes | None:
    result = subprocess.run(
        ["git", "cat-file", "blob", f"{revision}:{rel_path}"],
        cwd=root,
        capture_output=True,
        timeout=30.0,
        check=False,
    )
    if result.returncode != 0:
        return None
    return result.stdout


_CORE_BOUND_RECEIPT_FIELDS = (
    "bound_envelope_ref",
    "bound_envelope_sha256",
    "core_binding_status",
    "core_binding_hash",
    "acceptance_contract_hash",
)
_CORE_CONTINUATION_FIELDS = (
    *_CORE_BOUND_ATTEMPT_FIELDS,
    "core_binding_operation_id",
    "core_binding_attempt_id",
)


def _receipt_core_binding(receipt: Mapping[str, Any]) -> dict[str, str] | None:
    """Return the Core identity a bound parent receipt pins, or None for unbound ones.

    The root operation/attempt are the ones the binding was minted for: the receipt's
    own ids for the initial dispatch, the recorded root ids for a bound continuation.
    """
    present = [key for key in _CORE_BOUND_RECEIPT_FIELDS if key in receipt]
    if not present:
        return None
    if (
        len(present) != len(_CORE_BOUND_RECEIPT_FIELDS)
        or receipt.get("core_binding_status") != "BOUND"
    ):
        raise FanoutError("CORE_BINDING_PARENT_RECEIPT_INVALID")
    if receipt.get("mode") == "REPAIR_CONTINUE":
        root_operation = receipt.get("core_binding_operation_id")
        root_attempt = receipt.get("core_binding_attempt_id")
    else:
        root_operation = receipt.get("operation_id")
        root_attempt = receipt.get("attempt_id")
    if (
        not isinstance(root_operation, str)
        or _SHA256_RE.fullmatch(root_operation) is None
        or not isinstance(root_attempt, str)
        or not root_attempt.strip()
    ):
        raise FanoutError("CORE_BINDING_PARENT_RECEIPT_INVALID")
    return {
        "bound_envelope_ref": str(receipt["bound_envelope_ref"]),
        "bound_envelope_sha256": str(receipt["bound_envelope_sha256"]),
        "core_binding_hash": str(receipt["core_binding_hash"]),
        "acceptance_contract_hash": str(receipt["acceptance_contract_hash"]),
        "core_binding_operation_id": root_operation,
        "core_binding_attempt_id": root_attempt,
    }


def _attempt_core_hashes(attempt: Mapping[str, Any]) -> tuple[str, str] | None:
    """Return the Core hashes recorded for a bound attempt, or None for unbound ones."""
    present = [key for key in _CORE_BOUND_ATTEMPT_FIELDS if key in attempt]
    if not present:
        return None
    if len(present) != len(_CORE_BOUND_ATTEMPT_FIELDS):
        raise FanoutError("CORE_BINDING_ATTEMPT_RECORD_INCOMPLETE")
    return str(attempt["core_binding_hash"]), str(attempt["acceptance_contract_hash"])


@dataclass(frozen=True)
class _CoreBindingPreflight:
    inputs: CoreAuthorityInputs
    semantic_envelope: Mapping[str, Any]
    worker_identity_sha256: str
    origin: str
    source_tree: str
    capability_receipt: Mapping[str, Any]
    integration_authority: Mapping[str, str]
    acceptance_contract: Mapping[str, Any]
    acceptance_contract_hash: str


class AdaptiveWorkerFanoutRuntime:
    def __init__(
        self,
        *,
        allocator: GitWorktreeAllocator,
        store: FanoutStore,
        transport: OpenCodeWorkerTransport | Any | None = None,
        max_repairs_per_unit: int = 1,
    ):
        if (
            isinstance(max_repairs_per_unit, bool)
            or not isinstance(max_repairs_per_unit, int)
            or not 0 <= max_repairs_per_unit <= MAX_REPAIRS_PER_UNIT_LIMIT
        ):
            raise FanoutError("INVALID_REPAIR_BUDGET")
        self.allocator = allocator
        self.store = store
        self.transport = transport or OpenCodeWorkerTransport()
        # The closure's per-unit repair budget; it sizes the Core binding's lifetime.
        self.max_repairs_per_unit = max_repairs_per_unit

    def _controller_root(self) -> str:
        """The repository the allocator registers worktrees in ("" for an allocator that
        names none)."""
        return str(getattr(self.allocator, "repository_root", "") or "")

    def _transport_for_unit(self, unit_or_receipt: ExecutionUnit | Mapping[str, Any]) -> Any:
        selected_worker = (
            unit_or_receipt.selected_worker
            if isinstance(unit_or_receipt, ExecutionUnit)
            else unit_or_receipt.get("selected_worker")
        )
        resolved = _resolve_worker_transport_identity(selected_worker)
        if resolved is not None:
            exec_model, provider_id, model_id = resolved
            if isinstance(self.transport, OpenCodeWorkerTransport):
                return OpenCodeWorkerTransport(
                    executable=self.transport.executable,
                    model=exec_model,
                    provider_id=provider_id,
                    model_id=model_id,
                    timeout=self.transport.timeout,
                )
            if hasattr(self.transport, "bind_worker"):
                return self.transport.bind_worker(selected_worker)
            return self.transport
        return self.transport

    def run(
        self,
        units: Iterable[Mapping[str, Any] | ExecutionUnit],
        lease: CapacityLease,
    ) -> dict[str, Any]:
        parsed = [
            unit if isinstance(unit, ExecutionUnit) else ExecutionUnit.from_mapping(unit)
            for unit in units
        ]
        completed_ids: set[str] = set()
        for unit in parsed:
            existing_receipt = self.store.existing_initial_receipt(unit)
            if existing_receipt is not None:
                completed_ids.add(unit.unit_id)
        decision = plan_fanout(parsed, lease, completed_unit_ids=completed_ids)
        selected_ids = set(decision["admitted_units"])
        selected = [unit for unit in parsed if unit.unit_id in selected_ids]
        leases: dict[str, WorkspaceLease] = {}
        actions: dict[str, str] = {}
        receipts: dict[str, Any] = {
            unit.unit_id: self.store.existing_initial_receipt(unit)
            for unit in parsed
            if unit.unit_id in completed_ids
        }
        errors: dict[str, str] = {}
        seen_paths: set[str] = set()
        for unit in selected:
            existing_receipt = self.store.existing_initial_receipt(unit)
            if existing_receipt is not None:
                receipts[unit.unit_id] = existing_receipt
                continue
            existing_attempt = self.store.existing_initial_attempt(unit)
            if existing_attempt is not None:
                state = str(existing_attempt.get("state") or "")
                if state not in {
                    "PREPARED",
                    "DISPATCHING",
                    "RETRY_SAFE",
                    "OUTCOME_UNKNOWN",
                }:
                    errors[unit.unit_id] = "FANOUT_REPLAY_FORBIDDEN"
                    continue
                if state == "RETRY_SAFE":
                    if int(existing_attempt.get("retry_count", 0)) >= 1:
                        errors[unit.unit_id] = "FANOUT_REPLAY_FORBIDDEN"
                        continue
                    workspace = self.allocator.allocate(unit)
                else:
                    workspace = WorkspaceLease(
                        workspace_id=str(existing_attempt.get("workspace_id") or ""),
                        path=str(existing_attempt.get("workspace_path") or ""),
                        expected_base_sha=str(existing_attempt.get("expected_base_sha") or ""),
                        controller_root=self._controller_root(),
                    )
                if (
                    not workspace.workspace_id
                    or not workspace.path
                    or workspace.expected_base_sha != unit.expected_base_sha
                ):
                    errors[unit.unit_id] = "FANOUT_ATTEMPT_WORKSPACE_INVALID"
                    continue
                actions[unit.unit_id] = (
                    "DISPATCH"
                    if state == "PREPARED"
                    else "RETRY"
                    if state == "RETRY_SAFE"
                    else "RECONCILE"
                )
            else:
                workspace = self.allocator.allocate(unit)
                actions[unit.unit_id] = "NEW"
            resolved = str(Path(workspace.path).resolve())
            if resolved in seen_paths:
                errors[unit.unit_id] = "WORKSPACE_REUSE_FORBIDDEN"
                continue
            seen_paths.add(resolved)
            leases[unit.unit_id] = workspace

        pending = [unit for unit in selected if unit.unit_id in leases]
        if pending:
            with ThreadPoolExecutor(
                max_workers=len(pending), thread_name_prefix="nexus-ei"
            ) as executor:
                futures = {
                    executor.submit(
                        self._reconcile_initial
                        if actions[unit.unit_id] == "RECONCILE"
                        else self._dispatch_initial,
                        unit,
                        leases[unit.unit_id],
                        actions[unit.unit_id] == "DISPATCH",
                    ): unit.unit_id
                    for unit in pending
                }
                for future in as_completed(futures):
                    unit_id = futures[future]
                    try:
                        receipts[unit_id] = future.result()
                    except Exception as exc:  # bounded per-unit failure; siblings are independent
                        errors[unit_id] = str(exc)
        result = {
            "schema": FANOUT_RUN_SCHEMA,
            "decision": decision,
            "receipts": receipts,
            "errors": errors,
            "claim_ceiling": CLAIM_CEILING,
        }
        result["run_sha256"] = _sha256(_canonical_json(result))
        return result

    @staticmethod
    def _requires_core_binding(artifact: Path, transport: Any) -> bool:
        """Open SWE admits a v2 envelope only with a Core repository_mutation_binding."""
        if not getattr(transport, "supports_core_mutation_binding", False):
            return False
        envelope = json.loads(artifact.read_text(encoding="utf-8"))
        return isinstance(envelope, Mapping) and (
            envelope.get("schema") == "external_execution_envelope.v2"
        )

    def _core_binding_preflight(
        self,
        unit: ExecutionUnit,
        workspace: WorkspaceLease,
        artifact: Path,
        transport: Any,
    ) -> _CoreBindingPreflight:
        """Everything a binding needs except the attempt identity; no attempt is written."""
        if unit.core_authority is None:
            raise FanoutError("CORE_BINDING_AUTHORITY_REQUIRED")
        try:
            inputs = CoreAuthorityInputs.from_mapping(unit.core_authority)
            semantic = json.loads(artifact.read_text(encoding="utf-8"))
            if not isinstance(semantic, Mapping) or envelope_sha256(semantic) != (
                unit.envelope_sha256
            ):
                raise FanoutError("ENVELOPE_SHA256_MISMATCH")
            envelope_binding = semantic.get("binding")
            if (
                not isinstance(envelope_binding, Mapping)
                or inputs.task_id != unit.task_id
                or inputs.main_sha != unit.expected_base_sha
                or envelope_binding.get("main_sha") != inputs.main_sha
                or str(envelope_binding.get("repository") or "").lower()
                != inputs.repository.lower()
                or envelope_binding.get("task_card_ref") != inputs.task_card_ref
                or str(envelope_binding.get("task_card_hash") or "").lower()
                != inputs.task_card_hash
            ):
                raise FanoutError("CORE_AUTHORITY_ENVELOPE_MISMATCH")
            if unit.selected_worker is None:
                raise FanoutError("CORE_BINDING_WORKER_REQUIRED")
            worker_sha = _sha256(_canonical_json(dict(unit.selected_worker)))
            if worker_sha != inputs.worker_binding_sha256 or worker_sha != getattr(
                transport, "worker_identity_sha256", worker_sha
            ):
                raise FanoutError("CORE_AUTHORITY_WORKER_MISMATCH")
            root = Path(workspace.path)
            base = unit.expected_base_sha
            try:
                origin = _run_git(root, "remote", "get-url", "origin")
                source_tree = _run_git(root, "rev-parse", "--verify", f"{base}^{{tree}}")
            except FanoutError as exc:
                raise FanoutError("CORE_BINDING_WORKSPACE_IDENTITY_UNAVAILABLE") from exc
            if (
                not canonical_origin_repository(origin)
                or canonical_origin_repository(origin) != inputs.repository.lower()
            ):
                raise FanoutError("CORE_BINDING_ORIGIN_MISMATCH")
            index_bytes = _git_blob_bytes(root, base, CAPABILITY_DISCOVERY_INDEX_PATH)
            operating_mode = _git_blob_bytes(root, base, OPERATING_MODE_PATH)
            if operating_mode is None:
                raise CoreBindingError("CORE_OPERATING_MODE_MISSING")
            worker = dict(unit.selected_worker)
            receipt = build_capability_discovery_receipt(
                repository=inputs.repository,
                main_sha=base,
                index_bytes=index_bytes,
                intent=inputs.intent,
                disposition=inputs.capability_disposition,
                matched_capability_ids=inputs.capability_ids,
                justification=inputs.capability_justification,
                evidence={
                    "architecture": [
                        f"git:{base}:{CAPABILITY_DISCOVERY_INDEX_PATH}",
                        f"git:{base}:{OPERATING_MODE_PATH}",
                    ],
                    "source": [f"git:{base}:{path}" for path in unit.mutation_paths],
                    "history": [
                        f"github://{inputs.repository}/issues/{inputs.issue_number}"
                        f"@{inputs.revision}",
                        f"task_card:{inputs.task_card_ref}@{inputs.task_card_hash}",
                    ],
                    "runtime": [
                        f"{worker['admission_evidence_ref']}@{worker['admission_evidence_hash']}",
                        f"{worker['selection_evidence_ref']}@{worker['selection_evidence_hash']}",
                    ],
                },
            )
            authority = build_integration_authority(
                inputs, operating_mode_sha256=hashlib.sha256(operating_mode).hexdigest()
            )
            contract, contract_hash = build_acceptance_contract(
                inputs,
                unit_id=unit.unit_id,
                mutation_paths=unit.mutation_paths,
                allow_deletions=unit.allow_deletions,
            )
        except CoreBindingError as exc:
            raise FanoutError(str(exc)) from exc
        return _CoreBindingPreflight(
            inputs=inputs,
            semantic_envelope=semantic,
            worker_identity_sha256=worker_sha,
            origin=origin,
            source_tree=source_tree,
            capability_receipt=receipt,
            integration_authority=authority,
            acceptance_contract=contract,
            acceptance_contract_hash=contract_hash,
        )

    def _mint_core_binding(
        self,
        unit: ExecutionUnit,
        workspace: WorkspaceLease,
        attempt: Mapping[str, Any],
        transport: Any,
        preflight: _CoreBindingPreflight,
    ) -> dict[str, Any]:
        """Mint the per-attempt binding and write the derived bound envelope."""
        attempt_id = str(attempt["attempt_id"])
        material = bound_operation_material(
            operation="worker_run",
            workspace_path=workspace.path,
            attempt_id=attempt_id,
            unit_identity_sha256=unit.identity_sha256,
            semantic_envelope_sha256=unit.envelope_sha256,
            worker_identity_sha256=preflight.worker_identity_sha256,
        )
        operation_id = transport.prepare_operation_id(
            "worker_run",
            prompt="",
            artifact_path="",
            workspace_path=workspace.path,
            session_id="",
            operation_material=material,
        )
        receipt_path = self.store.write_capability_discovery_receipt(preflight.capability_receipt)
        try:
            binding = build_repository_mutation_binding(
                operation_id=operation_id,
                attempt_id=attempt_id,
                repository=preflight.inputs.repository,
                origin=preflight.origin,
                source_revision=unit.expected_base_sha,
                source_tree=preflight.source_tree,
                workspace_path=workspace.path,
                integration_authority=preflight.integration_authority,
                capability_receipt_hash=core_hash(dict(preflight.capability_receipt)),
                index_revision=unit.expected_base_sha,
                acceptance_contract=preflight.acceptance_contract,
                contract_hash=preflight.acceptance_contract_hash,
                created_at=datetime.now(timezone.utc),
                valid_for_seconds=binding_validity_seconds(
                    float(getattr(transport, "timeout", 300.0)),
                    self.max_repairs_per_unit,
                    unit_closure_cycle_seconds(preflight.inputs, unit.unit_id),
                ),
            )
            bound = derive_bound_envelope(preflight.semantic_envelope, binding)
        except CoreBindingError as exc:
            raise FanoutError(str(exc)) from exc
        bound_path = self.store.write_bound_envelope(attempt, bound)
        return {
            "operation_id": operation_id,
            "operation_material": material,
            "bound_envelope_ref": str(bound_path),
            "bound_envelope_sha256": envelope_sha256(bound),
            "core_binding_hash": str(binding["binding_hash"]),
            "acceptance_contract_hash": preflight.acceptance_contract_hash,
            "capability_discovery_receipt_ref": str(receipt_path),
        }

    @staticmethod
    def _revalidate_core_binding(
        unit: ExecutionUnit, workspace: WorkspaceLease, attempt: Mapping[str, Any]
    ) -> None:
        """Re-observe the workspace and binding immediately before the first effect."""
        root = Path(workspace.path)
        base = unit.expected_base_sha
        try:
            git_dir = _worker_git_dir(root, workspace.controller_root)
            head = _run_git(root, "rev-parse", "HEAD", git_dir=git_dir)
            dirty = _run_git(root, "status", "--porcelain=v1", git_dir=git_dir)
            tree = _run_git(root, "rev-parse", "--verify", f"{base}^{{tree}}", git_dir=git_dir)
            origin = _run_git(root, "remote", "get-url", "origin", git_dir=git_dir)
        except FanoutError as exc:
            raise CoreBindingError("workspace_observation") from exc
        if head != base:
            raise CoreBindingError("workspace_head")
        if dirty:
            raise CoreBindingError("workspace_dirty")
        try:
            text = Path(str(attempt["bound_envelope_ref"])).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            raise CoreBindingError("bound_envelope_read") from exc
        semantic, binding, observed_sha = parse_bound_execution_envelope_v2(
            text, semantic_envelope_sha256=unit.envelope_sha256
        )
        if (
            observed_sha != attempt.get("bound_envelope_sha256")
            or binding.get("binding_hash") != attempt.get("core_binding_hash")
            or binding["core"].get("acceptance_contract_hash")
            != attempt.get("acceptance_contract_hash")
        ):
            raise CoreBindingError("core_binding_hash")
        validate_repository_mutation_binding(
            binding,
            operation_id=str(attempt.get("operation_id") or ""),
            attempt_id=str(attempt.get("attempt_id") or ""),
            repository=str(semantic["binding"].get("repository") or ""),
            expected_base=base,
            observed_origin=origin,
            observed_base_tree=tree,
            workspace_path=workspace.path,
            allowed_paths=unit.mutation_paths,
        )

    @staticmethod
    def _revalidate_core_binding_for_continuation(
        previous_receipt: Mapping[str, Any],
        core_binding: Mapping[str, str],
        workspace: WorkspaceLease,
    ) -> None:
        """Re-check the parent's binding before a bound repair continuation.

        The workspace now holds the parent candidate commit, so the binding is checked
        against the bound base's tree (not HEAD), and freshness in continuation mode.
        """
        root = Path(workspace.path)
        base = str(previous_receipt.get("base_sha") or "")
        try:
            git_dir = _worker_git_dir(root, workspace.controller_root)
            origin = _run_git(root, "remote", "get-url", "origin", git_dir=git_dir)
            tree = _run_git(root, "rev-parse", "--verify", f"{base}^{{tree}}", git_dir=git_dir)
        except FanoutError as exc:
            raise CoreBindingError("workspace_observation") from exc
        try:
            text = Path(core_binding["bound_envelope_ref"]).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            raise CoreBindingError("bound_envelope_read") from exc
        semantic, binding, observed_sha = parse_bound_execution_envelope_v2(
            text, semantic_envelope_sha256=str(previous_receipt.get("envelope_sha256") or "")
        )
        if (
            observed_sha != core_binding["bound_envelope_sha256"]
            or binding.get("binding_hash") != core_binding["core_binding_hash"]
            or binding["core"].get("acceptance_contract_hash")
            != core_binding["acceptance_contract_hash"]
        ):
            raise CoreBindingError("core_binding_hash")
        validate_repository_mutation_binding(
            binding,
            operation_id=core_binding["core_binding_operation_id"],
            attempt_id=core_binding["core_binding_attempt_id"],
            repository=str(semantic["binding"].get("repository") or ""),
            expected_base=base,
            observed_origin=origin,
            observed_base_tree=tree,
            workspace_path=workspace.path,
            allowed_paths=list(previous_receipt.get("mutation_paths") or []),
            continuation=True,
        )

    def _dispatch_initial(
        self,
        unit: ExecutionUnit,
        workspace: WorkspaceLease,
        resume_prepared: bool = False,
    ) -> dict[str, Any]:
        artifact = _verify_envelope_scope(unit)
        transport = self._transport_for_unit(unit)
        preflight = (
            self._core_binding_preflight(unit, workspace, artifact, transport)
            if self._requires_core_binding(artifact, transport)
            else None
        )
        if resume_prepared:
            attempt = self.store.existing_initial_attempt(unit)
            if attempt is None or attempt.get("state") != "PREPARED":
                raise FanoutError("FANOUT_PREPARED_ATTEMPT_REQUIRED")
        else:
            attempt = self.store.prepare_initial(unit, workspace)
        if preflight is not None:
            return self._dispatch_initial_bound(
                unit, workspace, attempt, artifact, transport, preflight
            )
        prompt = build_worker_bootstrap(unit, workspace)
        if artifact.read_text(encoding="utf-8") in prompt:
            raise FanoutError("FULL_ENVELOPE_IN_CONTROLLER_PROMPT")
        if hasattr(transport, "prepare_operation_id"):
            operation_id = transport.prepare_operation_id(
                "worker_run",
                prompt=prompt,
                artifact_path=str(artifact),
                workspace_path=workspace.path,
                session_id="",
            )
            attempt = self.store.bind_operation_id(attempt, operation_id)
        attempt = self.store.mark_dispatching(attempt)
        if hasattr(transport, "prepare_operation_id"):
            result: OpenCodeRunResult = transport.run_new(
                prompt=prompt,
                artifact_path=str(artifact),
                workspace_path=workspace.path,
                operation_id=operation_id,
            )
        else:
            result = transport.run_new(
                prompt=prompt,
                artifact_path=str(artifact),
                workspace_path=workspace.path,
            )
        return self._finalize_initial(unit, workspace, attempt, result, transport=transport)

    def _dispatch_initial_bound(
        self,
        unit: ExecutionUnit,
        workspace: WorkspaceLease,
        attempt: Mapping[str, Any],
        artifact: Path,
        transport: Any,
        preflight: _CoreBindingPreflight,
    ) -> dict[str, Any]:
        minted = self._mint_core_binding(unit, workspace, attempt, transport, preflight)
        attempt = self.store.record_core_binding(
            attempt,
            bound_envelope_ref=minted["bound_envelope_ref"],
            bound_envelope_sha256=minted["bound_envelope_sha256"],
            core_binding_hash=minted["core_binding_hash"],
            acceptance_contract_hash=minted["acceptance_contract_hash"],
            capability_discovery_receipt_ref=minted["capability_discovery_receipt_ref"],
        )
        prompt = build_worker_bootstrap(
            unit,
            workspace,
            bound_envelope_ref=minted["bound_envelope_ref"],
            bound_envelope_sha256=minted["bound_envelope_sha256"],
        )
        bound_artifact = Path(minted["bound_envelope_ref"])
        if (
            artifact.read_text(encoding="utf-8") in prompt
            or bound_artifact.read_text(encoding="utf-8") in prompt
        ):
            raise FanoutError("FULL_ENVELOPE_IN_CONTROLLER_PROMPT")
        operation_id = str(minted["operation_id"])
        attempt = self.store.bind_operation_id(attempt, operation_id)
        attempt = self.store.mark_dispatching(attempt)
        try:
            self._revalidate_core_binding(unit, workspace, attempt)
        except CoreBindingError as exc:
            reason = f"CORE_BINDING_REVALIDATION_FAILED:{exc}"
            # No effect has started: the worker was never invoked.
            self.store.finish_attempt(attempt, state="FAILED", transport_status=reason)
            raise FanoutError(reason) from exc
        result: OpenCodeRunResult = transport.run_new(
            prompt=prompt,
            artifact_path=str(bound_artifact),
            workspace_path=workspace.path,
            operation_id=operation_id,
            operation_material=minted["operation_material"],
            core_binding={
                "core_binding_hash": minted["core_binding_hash"],
                "acceptance_contract_hash": minted["acceptance_contract_hash"],
            },
        )
        return self._finalize_initial(unit, workspace, attempt, result, transport=transport)

    def _reconcile_initial(
        self,
        unit: ExecutionUnit,
        workspace: WorkspaceLease,
        resume_prepared: bool = False,
    ) -> dict[str, Any]:
        _verify_envelope_scope(unit)
        transport = self._transport_for_unit(unit)
        attempt = self.store.existing_initial_attempt(unit)
        if attempt is None or attempt.get("state") not in {"DISPATCHING", "OUTCOME_UNKNOWN"}:
            raise FanoutError("FANOUT_RECONCILIATION_REQUIRED")
        operation_id = attempt.get("operation_id")
        core_hashes = _attempt_core_hashes(attempt)
        if core_hashes is not None and not getattr(
            transport, "supports_core_mutation_binding", False
        ):
            raise FanoutError("CORE_BINDING_TRANSPORT_UNSUPPORTED")
        if hasattr(transport, "prepare_operation_id"):
            if not isinstance(operation_id, str) or _SHA256_RE.fullmatch(operation_id) is None:
                raise FanoutError("OPERATION_ID_REQUIRED")
            if core_hashes is not None:
                result: OpenCodeRunResult = transport.reconcile_workspace(
                    workspace_path=workspace.path,
                    operation_id=operation_id,
                    core_binding={
                        "core_binding_hash": core_hashes[0],
                        "acceptance_contract_hash": core_hashes[1],
                    },
                )
            else:
                result = transport.reconcile_workspace(
                    workspace_path=workspace.path, operation_id=operation_id
                )
        else:
            result = transport.reconcile_workspace(workspace_path=workspace.path)
        return self._finalize_initial(unit, workspace, attempt, result, transport=transport)

    def _finalize_initial(
        self,
        unit: ExecutionUnit,
        workspace: WorkspaceLease,
        attempt: Mapping[str, Any],
        result: OpenCodeRunResult,
        transport: Any = None,
    ) -> dict[str, Any]:
        active_transport = transport or self._transport_for_unit(unit)
        if result.status != "COMPLETED":
            if result.outcome_unknown or result.process_started:
                state = "OUTCOME_UNKNOWN"
            elif result.retry_safe:
                state = "RETRY_SAFE"
            else:
                state = "FAILED"
            self.store.finish_attempt(attempt, state=state, transport_status=result.status)
            if state == "OUTCOME_UNKNOWN":
                raise FanoutError("FANOUT_RECONCILIATION_REQUIRED")
            raise FanoutError(result.status)
        expected_operation_id = attempt.get("operation_id")
        if hasattr(active_transport, "prepare_operation_id"):
            if (
                not isinstance(expected_operation_id, str)
                or _SHA256_RE.fullmatch(expected_operation_id) is None
            ):
                self.store.finish_attempt(
                    attempt, state="OUTCOME_UNKNOWN", transport_status="OPERATION_ID_REQUIRED"
                )
                raise FanoutError("OPERATION_ID_REQUIRED")
            if result.operation_id != expected_operation_id:
                self.store.finish_attempt(
                    attempt, state="OUTCOME_UNKNOWN", transport_status="OPERATION_ID_MISMATCH"
                )
                raise FanoutError("OPERATION_ID_MISMATCH")
        expected_core = _attempt_core_hashes(attempt)
        if expected_core is not None and (
            result.core_binding_status != "BOUND"
            or (result.core_binding_hash, result.acceptance_contract_hash) != expected_core
        ):
            self.store.finish_attempt(
                attempt,
                state="OUTCOME_UNKNOWN",
                transport_status="CORE_BINDING_ATTESTATION_MISMATCH",
            )
            raise FanoutError("CORE_BINDING_ATTESTATION_MISMATCH")
        expected_provider_id = getattr(active_transport, "provider_id", PROVIDER_ID)
        expected_model_id = getattr(active_transport, "model_id", MODEL_ID)
        if result.provider_id != expected_provider_id or result.model_id != expected_model_id:
            self.store.finish_attempt(
                attempt,
                state="OUTCOME_UNKNOWN",
                transport_status="MODEL_ATTESTATION_MISMATCH",
            )
            raise FanoutError("MODEL_ATTESTATION_MISMATCH")
        if _observed_model_unproven(active_transport, result):
            self.store.finish_attempt(
                attempt,
                state="OUTCOME_UNKNOWN",
                transport_status=OBSERVED_MODEL_ATTESTATION_MISMATCH,
            )
            raise FanoutError(OBSERVED_MODEL_ATTESTATION_MISMATCH)
        if str(Path(result.directory).resolve()) != str(Path(workspace.path).resolve()):
            self.store.finish_attempt(
                attempt,
                state="OUTCOME_UNKNOWN",
                transport_status="WORKSPACE_ATTESTATION_MISMATCH",
            )
            raise FanoutError("WORKSPACE_ATTESTATION_MISMATCH")
        try:
            worker = parse_worker_result(
                result.response_text, task_id=unit.task_id, unit_id=unit.unit_id
            )
        except FanoutError:
            self.store.finish_attempt(
                attempt,
                state="OUTCOME_UNKNOWN",
                transport_status="WORKER_RESULT_INVALID",
            )
            raise FanoutError("FANOUT_RECONCILIATION_REQUIRED")
        self.store.claim_session(
            result.session_id,
            task_id=unit.task_id,
            unit_id=unit.unit_id,
            workspace_id=workspace.workspace_id,
            selected_worker=unit.selected_worker,
            provider=unit.provider,
            model=unit.model,
        )
        if worker["status"] == "BLOCKED":
            receipt = self._build_receipt(
                unit=unit,
                workspace=workspace,
                attempt=attempt,
                result=result,
                worker=worker,
                candidate=None,
                status="WORKER_BLOCKED",
            )
            self.store.write_receipt(receipt)
            self.store.finish_attempt(
                attempt, state="TERMINAL_BLOCKED", transport_status=result.status
            )
            return receipt
        try:
            candidate = _capture_candidate(
                unit,
                workspace,
                expected_head=unit.expected_base_sha,
                worker_backend=result.worker_backend,
            )
        except FanoutError as exc:
            hard_block = (
                str(exc) == "EMPTY_IMPLEMENTATION_RESULT"
                or str(exc) == "DELETION_NOT_AUTHORIZED"
                or str(exc).startswith("OUT_OF_SCOPE_MUTATION:")
            )
            if hard_block:
                blocked_worker = {
                    "status": "BLOCKED",
                    "summary": str(exc),
                }
                receipt = self._build_receipt(
                    unit=unit,
                    workspace=workspace,
                    attempt=attempt,
                    result=result,
                    worker=blocked_worker,
                    candidate=None,
                    status="WORKER_BLOCKED",
                )
                self.store.write_receipt(receipt)
                self.store.finish_attempt(
                    attempt, state="TERMINAL_BLOCKED", transport_status=str(exc)
                )
                return receipt
            self.store.finish_attempt(
                attempt, state="OUTCOME_UNKNOWN", transport_status="CANDIDATE_CAPTURE_FAILED"
            )
            raise
        receipt = self._build_receipt(
            unit=unit,
            workspace=workspace,
            attempt=attempt,
            result=result,
            worker=worker,
            candidate=candidate,
            status="CANDIDATE_READY_FOR_VERIFICATION",
        )
        self.store.write_receipt(receipt)
        self.store.finish_attempt(attempt, state="COMPLETED", transport_status=result.status)
        return receipt

    def continue_repair(
        self,
        previous_receipt: Mapping[str, Any],
        *,
        repair_id: str,
        repair_ref: str,
        repair_sha256: str,
    ) -> dict[str, Any]:
        if previous_receipt.get("schema") != WORKER_RECEIPT_SCHEMA:
            raise FanoutError("INVALID_PARENT_RECEIPT")
        if previous_receipt.get("status") != "CANDIDATE_READY_FOR_VERIFICATION":
            raise FanoutError("PARENT_CANDIDATE_REQUIRED")
        transport = self._transport_for_unit(previous_receipt)
        transport_model = getattr(transport, "model", MODEL)
        transport_provider_id = getattr(transport, "provider_id", PROVIDER_ID)
        transport_model_id = getattr(transport, "model_id", MODEL_ID)
        if (
            previous_receipt.get("model") != transport_model
            or previous_receipt.get("provider_id") != transport_provider_id
            or previous_receipt.get("model_id") != transport_model_id
        ):
            raise FanoutError("MODEL_SUBSTITUTION_FORBIDDEN")
        repair_path, _ = _load_and_verify_artifact(repair_ref, repair_sha256)
        task_id = _safe_slug(previous_receipt.get("task_id"), "task_id")
        unit_id = _safe_slug(previous_receipt.get("unit_id"), "unit_id")
        workspace = WorkspaceLease(
            workspace_id=str(previous_receipt.get("workspace_id") or ""),
            path=str(previous_receipt.get("workspace_path") or ""),
            expected_base_sha=str(previous_receipt.get("candidate_commit") or ""),
            controller_root=self._controller_root(),
        )
        repair_root = Path(workspace.path)
        repair_git_dir = _worker_git_dir(repair_root, workspace.controller_root)
        if (
            _run_git(repair_root, "rev-parse", "HEAD", git_dir=repair_git_dir)
            != workspace.expected_base_sha
        ):
            raise FanoutError("REPAIR_WORKSPACE_HEAD_MISMATCH")
        if _run_git(repair_root, "status", "--porcelain=v1", git_dir=repair_git_dir):
            raise FanoutError("REPAIR_WORKSPACE_DIRTY")
        self.store.assert_session_owner(
            str(previous_receipt.get("session_id") or ""),
            task_id=task_id,
            unit_id=unit_id,
            workspace_id=workspace.workspace_id,
            selected_worker=previous_receipt.get("selected_worker"),
            provider=str(previous_receipt.get("provider") or PROVIDER),
            model=str(previous_receipt.get("model") or MODEL),
        )
        core_binding = _receipt_core_binding(previous_receipt)
        if (core_binding is not None) != self.store.initial_attempt_is_bound(task_id, unit_id):
            # The parent receipt lost Core fields its unit's initial attempt recorded:
            # never continue a bound unit through the unbound path.
            raise FanoutError("CORE_BINDING_PARENT_RECEIPT_INVALID")
        if core_binding is not None:
            if not getattr(transport, "supports_core_mutation_binding", False) or not hasattr(
                transport, "prepare_operation_id"
            ):
                raise FanoutError("CORE_BINDING_TRANSPORT_UNSUPPORTED")
            try:
                self._revalidate_core_binding_for_continuation(
                    previous_receipt, core_binding, workspace
                )
            except CoreBindingError as exc:
                # No repair attempt exists yet and the worker was never invoked.
                raise FanoutError(f"CORE_BINDING_REVALIDATION_FAILED:{exc}") from exc
        prompt = build_repair_bootstrap(
            previous_receipt,
            repair_id=repair_id,
            repair_ref=str(repair_path),
            repair_sha256=repair_sha256,
        )
        operation_id: str | None = None
        if hasattr(transport, "prepare_operation_id"):
            # Pure derivation (no effect); recorded atomically with the attempt so the
            # attempt is never rewritten between PREPARED and DISPATCHING.
            operation_id = transport.prepare_operation_id(
                "worker_continue",
                prompt=prompt,
                artifact_path=str(repair_path),
                workspace_path=workspace.path,
                session_id=str(previous_receipt["session_id"]),
            )
        attempt = self.store.prepare_repair(
            previous_receipt,
            repair_id=repair_id,
            repair_ref=str(repair_path),
            repair_sha256=repair_sha256,
            core_binding=core_binding,
            operation_id=operation_id,
        )
        attempt = self.store.mark_repair_dispatching(attempt)
        expected_core = (
            (core_binding["core_binding_hash"], core_binding["acceptance_contract_hash"])
            if core_binding is not None
            else None
        )
        if expected_core is not None:
            result: OpenCodeRunResult = transport.continue_session(
                session_id=str(previous_receipt["session_id"]),
                prompt=prompt,
                artifact_path=str(repair_path),
                workspace_path=workspace.path,
                operation_id=str(attempt["operation_id"]),
                core_binding={
                    "core_binding_hash": expected_core[0],
                    "acceptance_contract_hash": expected_core[1],
                },
            )
        elif hasattr(transport, "prepare_operation_id"):
            result = transport.continue_session(
                session_id=str(previous_receipt["session_id"]),
                prompt=prompt,
                artifact_path=str(repair_path),
                workspace_path=workspace.path,
                operation_id=operation_id,
            )
        else:
            result = transport.continue_session(
                session_id=str(previous_receipt["session_id"]),
                prompt=prompt,
                artifact_path=str(repair_path),
                workspace_path=workspace.path,
            )
        return self._finalize_repair(
            previous_receipt,
            attempt,
            result,
            transport=transport,
            workspace=workspace,
            repair_id=repair_id,
            expected_core=expected_core,
        )

    def reconcile_repair(
        self, previous_receipt: Mapping[str, Any], *, repair_id: str
    ) -> dict[str, Any]:
        """Reconcile-only recovery of a repair continuation with no known outcome.

        Mirrors the initial-dispatch reconcile: it never starts a new continuation,
        asks the transport only about the attempt's recorded operation id, and leaves
        the attempt OUTCOME_UNKNOWN (raising) whenever the outcome cannot be proven.
        A transport without operation ids cannot tell the repair turn from the
        parent's turn in the same session, so it is refused.
        """
        if previous_receipt.get("schema") != WORKER_RECEIPT_SCHEMA:
            raise FanoutError("INVALID_PARENT_RECEIPT")
        task_id = _safe_slug(previous_receipt.get("task_id"), "task_id")
        unit_id = _safe_slug(previous_receipt.get("unit_id"), "unit_id")
        repair_id = _safe_slug(repair_id, "repair_id")
        attempt = self.store.existing_repair_attempt(task_id, unit_id, repair_id)
        if attempt is None or attempt.get("state") not in {"DISPATCHING", "OUTCOME_UNKNOWN"}:
            raise FanoutError("FANOUT_RECONCILIATION_REQUIRED")
        for attempt_field, receipt_field in (
            ("parent_receipt_id", "receipt_id"),
            ("session_id", "session_id"),
            ("workspace_id", "workspace_id"),
            ("workspace_path", "workspace_path"),
            ("expected_head", "candidate_commit"),
        ):
            if not attempt.get(attempt_field) or attempt.get(attempt_field) != previous_receipt.get(
                receipt_field
            ):
                raise FanoutError("REPAIR_RECONCILE_BINDING_MISMATCH")
        transport = self._transport_for_unit(previous_receipt)
        if (
            previous_receipt.get("model") != getattr(transport, "model", MODEL)
            or previous_receipt.get("provider_id") != getattr(transport, "provider_id", PROVIDER_ID)
            or previous_receipt.get("model_id") != getattr(transport, "model_id", MODEL_ID)
        ):
            raise FanoutError("MODEL_SUBSTITUTION_FORBIDDEN")
        if not hasattr(transport, "prepare_operation_id"):
            raise FanoutError("OPERATION_ID_REQUIRED")
        operation_id = attempt.get("operation_id")
        if not isinstance(operation_id, str) or _SHA256_RE.fullmatch(operation_id) is None:
            raise FanoutError("OPERATION_ID_REQUIRED")
        workspace = WorkspaceLease(
            workspace_id=str(attempt["workspace_id"]),
            path=str(attempt["workspace_path"]),
            expected_base_sha=str(attempt["expected_head"]),
            controller_root=self._controller_root(),
        )
        self.store.assert_session_owner(
            str(attempt["session_id"]),
            task_id=task_id,
            unit_id=unit_id,
            workspace_id=workspace.workspace_id,
            selected_worker=previous_receipt.get("selected_worker"),
            provider=str(previous_receipt.get("provider") or PROVIDER),
            model=str(previous_receipt.get("model") or MODEL),
        )
        # Bound-ness comes from the parent receipt (and the unit's initial attempt),
        # never from the repair attempt record alone: a record stripped of its Core
        # fields must not downgrade a bound continuation to an unbound reconcile.
        parent_core = _receipt_core_binding(previous_receipt)
        if (parent_core is not None) != self.store.initial_attempt_is_bound(task_id, unit_id):
            raise FanoutError("CORE_BINDING_PARENT_RECEIPT_INVALID")
        if parent_core is None:
            if any(key in attempt for key in _CORE_CONTINUATION_FIELDS):
                raise FanoutError("REPAIR_RECONCILE_CORE_BINDING_MISMATCH")
            core_hashes = None
        else:
            if any(attempt.get(key) != parent_core[key] for key in _CORE_CONTINUATION_FIELDS):
                raise FanoutError("REPAIR_RECONCILE_CORE_BINDING_MISMATCH")
            core_hashes = (
                parent_core["core_binding_hash"],
                parent_core["acceptance_contract_hash"],
            )
        if core_hashes is not None:
            if not getattr(transport, "supports_core_mutation_binding", False):
                raise FanoutError("CORE_BINDING_TRANSPORT_UNSUPPORTED")
            result: OpenCodeRunResult = transport.reconcile_workspace(
                workspace_path=workspace.path,
                operation_id=operation_id,
                core_binding={
                    "core_binding_hash": core_hashes[0],
                    "acceptance_contract_hash": core_hashes[1],
                },
            )
        else:
            result = transport.reconcile_workspace(
                workspace_path=workspace.path, operation_id=operation_id
            )
        return self._finalize_repair(
            previous_receipt,
            attempt,
            result,
            transport=transport,
            workspace=workspace,
            repair_id=repair_id,
            expected_core=core_hashes,
        )

    def _finalize_repair(
        self,
        previous_receipt: Mapping[str, Any],
        attempt: Mapping[str, Any],
        result: OpenCodeRunResult,
        *,
        transport: Any,
        workspace: WorkspaceLease,
        repair_id: str,
        expected_core: tuple[str, str] | None,
    ) -> dict[str, Any]:
        task_id = _safe_slug(previous_receipt.get("task_id"), "task_id")
        unit_id = _safe_slug(previous_receipt.get("unit_id"), "unit_id")
        suffix = f"repair-{_safe_slug(repair_id, 'repair_id')}"
        transport_provider_id = getattr(transport, "provider_id", PROVIDER_ID)
        transport_model_id = getattr(transport, "model_id", MODEL_ID)
        if result.status != "COMPLETED" or result.session_id != previous_receipt["session_id"]:
            self.store.finish_attempt(
                attempt,
                state="OUTCOME_UNKNOWN",
                transport_status=result.status,
                suffix=suffix,
            )
            raise FanoutError("FANOUT_RECONCILIATION_REQUIRED")
        expected_operation_id = attempt.get("operation_id")
        if hasattr(transport, "prepare_operation_id"):
            if (
                not isinstance(expected_operation_id, str)
                or _SHA256_RE.fullmatch(expected_operation_id) is None
            ):
                self.store.finish_attempt(
                    attempt,
                    state="OUTCOME_UNKNOWN",
                    transport_status="OPERATION_ID_REQUIRED",
                    suffix=suffix,
                )
                raise FanoutError("OPERATION_ID_REQUIRED")
            if result.operation_id != expected_operation_id:
                self.store.finish_attempt(
                    attempt,
                    state="OUTCOME_UNKNOWN",
                    transport_status="OPERATION_ID_MISMATCH",
                    suffix=suffix,
                )
                raise FanoutError("OPERATION_ID_MISMATCH")
        if expected_core is not None and (
            result.core_binding_status != "BOUND"
            or (result.core_binding_hash, result.acceptance_contract_hash) != expected_core
        ):
            self.store.finish_attempt(
                attempt,
                state="OUTCOME_UNKNOWN",
                transport_status="CORE_BINDING_ATTESTATION_MISMATCH",
                suffix=suffix,
            )
            raise FanoutError("CORE_BINDING_ATTESTATION_MISMATCH")
        if result.provider_id != transport_provider_id or result.model_id != transport_model_id:
            self.store.finish_attempt(
                attempt,
                state="OUTCOME_UNKNOWN",
                transport_status="MODEL_ATTESTATION_MISMATCH",
                suffix=suffix,
            )
            raise FanoutError("MODEL_ATTESTATION_MISMATCH")
        if _observed_model_unproven(transport, result):
            self.store.finish_attempt(
                attempt,
                state="OUTCOME_UNKNOWN",
                transport_status=OBSERVED_MODEL_ATTESTATION_MISMATCH,
                suffix=suffix,
            )
            raise FanoutError(OBSERVED_MODEL_ATTESTATION_MISMATCH)
        if str(Path(result.directory).resolve()) != str(Path(workspace.path).resolve()):
            self.store.finish_attempt(
                attempt,
                state="OUTCOME_UNKNOWN",
                transport_status="WORKSPACE_ATTESTATION_MISMATCH",
                suffix=suffix,
            )
            raise FanoutError("WORKSPACE_ATTESTATION_MISMATCH")
        try:
            worker = parse_worker_result(result.response_text, task_id=task_id, unit_id=unit_id)
        except FanoutError:
            self.store.finish_attempt(
                attempt,
                state="OUTCOME_UNKNOWN",
                transport_status="WORKER_RESULT_INVALID",
                suffix=suffix,
            )
            raise FanoutError("FANOUT_RECONCILIATION_REQUIRED")
        unit = ExecutionUnit.from_mapping({
            "task_id": task_id,
            "unit_id": unit_id,
            "envelope_ref": previous_receipt["envelope_ref"],
            "envelope_sha256": previous_receipt["envelope_sha256"],
            "expected_base_sha": previous_receipt["base_sha"],
            "mutation_paths": previous_receipt["mutation_paths"],
            "allow_deletions": previous_receipt.get("allow_deletions", False),
            "selected_worker": previous_receipt.get("selected_worker"),
            "provider": previous_receipt.get("provider", PROVIDER),
            "model": previous_receipt.get("model", MODEL),
            "excerpt_base_hashes": previous_receipt.get("excerpt_base_hashes"),
        })
        if worker["status"] == "BLOCKED":
            receipt = self._build_receipt(
                unit=unit,
                workspace=workspace,
                attempt=attempt,
                result=result,
                worker=worker,
                candidate=None,
                status="WORKER_BLOCKED",
                parent_receipt_id=str(previous_receipt.get("receipt_id") or ""),
                repair_id=repair_id,
            )
            self.store.write_receipt(receipt, suffix=suffix)
            self.store.finish_attempt(
                attempt,
                state="TERMINAL_BLOCKED",
                transport_status=result.status,
                suffix=suffix,
            )
            return receipt
        candidate = _capture_candidate(
            unit,
            workspace,
            expected_head=str(previous_receipt["candidate_commit"]),
            worker_backend=result.worker_backend,
        )
        receipt = self._build_receipt(
            unit=unit,
            workspace=workspace,
            attempt=attempt,
            result=result,
            worker=worker,
            candidate=candidate,
            status="CANDIDATE_READY_FOR_VERIFICATION",
            parent_receipt_id=str(previous_receipt.get("receipt_id") or ""),
            repair_id=repair_id,
        )
        self.store.write_receipt(receipt, suffix=suffix)
        self.store.finish_attempt(
            attempt, state="COMPLETED", transport_status=result.status, suffix=suffix
        )
        return receipt

    def _build_receipt(
        self,
        *,
        unit: ExecutionUnit,
        workspace: WorkspaceLease,
        attempt: Mapping[str, Any],
        result: OpenCodeRunResult,
        worker: Mapping[str, Any],
        candidate: Mapping[str, Any] | None,
        status: str,
        parent_receipt_id: str = "",
        repair_id: str = "",
    ) -> dict[str, Any]:
        receipt = {
            "schema": WORKER_RECEIPT_SCHEMA,
            "status": status,
            "task_id": unit.task_id,
            "unit_id": unit.unit_id,
            "attempt_id": attempt["attempt_id"],
            "mode": attempt["mode"],
            "provider": unit.provider,
            "model": unit.model,
            "provider_id": result.provider_id,
            "model_id": result.model_id,
            "session_id": result.session_id,
            "workspace_id": workspace.workspace_id,
            "workspace_path": workspace.path,
            "base_sha": unit.expected_base_sha,
            "envelope_ref": unit.envelope_ref,
            "envelope_sha256": unit.envelope_sha256,
            "mutation_paths": list(unit.mutation_paths),
            "allow_deletions": unit.allow_deletions,
            "worker_summary": worker["summary"],
            "argv_sha256": result.argv_sha256,
            "stdout_sha256": result.stdout_sha256,
            "export_sha256": result.export_sha256,
            "opencode_version": result.version,
            "worker_backend": result.worker_backend,
            "diagnosis_status": result.diagnosis_status,
            "diagnosis_sha256": result.diagnosis_sha256,
            "diagnosis_evidence_paths": list(result.diagnosis_evidence_paths),
            "repair_admitted": result.repair_admitted,
            "repair_phase_count": result.repair_phase_count,
            "worker_identity_sha256": result.worker_identity_sha256,
            "operation_id": result.operation_id,
            "parent_receipt_id": parent_receipt_id,
            "repair_id": repair_id,
            "claim_ceiling": CLAIM_CEILING,
            "candidate_commit": "",
            "candidate_tree": "",
            "candidate_diff_sha256": "",
            "changed_paths": [],
            "deleted_paths": [],
            "telemetry": {
                "worker_tokens": "NOT_OBSERVED",
                "provider": unit.provider,
                "model": unit.model,
            },
        }
        if unit.selected_worker is not None:
            receipt["selected_worker"] = dict(unit.selected_worker)
        if unit.excerpt_base_hashes:
            # Only when set, so receipts of units without excerpts stay byte-identical;
            # repair rebuilds the unit from this receipt and re-checks the base (#2357).
            receipt["excerpt_base_hashes"] = dict(sorted(unit.excerpt_base_hashes.items()))
        if _attempt_core_hashes(attempt) is not None:
            # The receipt's envelope_sha256 stays the semantic identity; the bound
            # envelope and the runtime-attested Core identity are added alongside.
            receipt.update({
                "bound_envelope_ref": str(attempt["bound_envelope_ref"]),
                "bound_envelope_sha256": str(attempt["bound_envelope_sha256"]),
                "core_binding_status": result.core_binding_status,
                "core_binding_hash": result.core_binding_hash,
                "acceptance_contract_hash": result.acceptance_contract_hash,
            })
            if "core_binding_operation_id" in attempt:
                receipt.update({
                    "core_binding_operation_id": str(attempt["core_binding_operation_id"]),
                    "core_binding_attempt_id": str(attempt["core_binding_attempt_id"]),
                })
        if candidate is not None:
            receipt.update(candidate)
        material = dict(receipt)
        receipt["receipt_id"] = _sha256(_canonical_json(material))
        return receipt


AdaptiveDeepSeekFanoutRuntime = AdaptiveWorkerFanoutRuntime


__all__ = [
    "CLAIM_CEILING",
    "DISPATCH_ATTEMPT_SCHEMA",
    "EIA_COMMIT_EMAIL_DOMAIN",
    "EIA_COMPOSER_EMAIL",
    "EIA_COMPOSER_NAME",
    "EIA_TRAILER_BACKEND",
    "EIA_TRAILER_MODEL",
    "EIA_TRAILER_WORKER",
    "FANOUT_DECISION_SCHEMA",
    "FANOUT_RUN_SCHEMA",
    "MODEL",
    "MODEL_ID",
    "PROVIDER",
    "PROVIDER_ID",
    "WORKER_RECEIPT_SCHEMA",
    "WORKER_RESULT_SCHEMA",
    "AdaptiveDeepSeekFanoutRuntime",
    "AdaptiveWorkerFanoutRuntime",
    "CapacityLease",
    "ExecutionUnit",
    "FanoutError",
    "FanoutStore",
    "GitWorktreeAllocator",
    "OpenCodeDeepSeekTransport",
    "OpenCodeRunResult",
    "OpenCodeWorkerTransport",
    "WorkspaceLease",
    "build_repair_bootstrap",
    "build_worker_bootstrap",
    "eia_git_commit",
    "eia_worker_identity",
    "parse_worker_result",
    "plan_fanout",
]
