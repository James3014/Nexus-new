from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
import time
import uuid
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Mapping, Sequence

from nexus.services.external_intelligence_fanout import (
    MODEL,
    PROVIDER,
    WORKER_RECEIPT_SCHEMA,
)


UNIT_VERIFICATION_SCHEMA = "external_intelligence_unit_verification.v1"
WHOLE_VERIFICATION_SCHEMA = "external_intelligence_whole_task_verification.v1"
UNIT_REPAIR_DELTA_SCHEMA = "unit_repair_delta.v2"
COMPOSITION_REPAIR_DELTA_SCHEMA = "composition_repair_delta.v1"
TASK_CANDIDATE_SCHEMA = "external_intelligence_task_candidate.v1"
ACCEPTANCE_PACKET_SCHEMA = "external_intelligence_acceptance_packet.v1"
CLOSURE_CAPSULE_SCHEMA = "external_intelligence_closure_capsule.v1"
CLOSURE_RUN_SCHEMA = "external_intelligence_closure_run.v1"
CLAIM_CEILING = "TASK_CANDIDATE_VERIFIED_PENDING_INDEPENDENT_ACCEPTANCE"
_SESSION_PREFIX = "ses_"
_HEX40 = frozenset("0123456789abcdef")
_HEX64 = _HEX40


class ClosureError(RuntimeError):
    pass


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256(value: bytes | str) -> str:
    raw = value.encode("utf-8") if isinstance(value, str) else value
    return hashlib.sha256(raw).hexdigest()


def _is_hex(value: Any, size: int) -> bool:
    text = str(value or "").lower()
    return len(text) == size and all(char in _HEX40 for char in text)


def _safe_slug(value: Any, field: str) -> str:
    text = str(value or "").strip()
    if not text or len(text) > 160 or any(char not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_.-" for char in text):
        raise ClosureError(f"INVALID_{field.upper()}")
    return text


def _safe_relative_path(value: Any) -> str:
    text = str(value or "").strip()
    path = PurePosixPath(text)
    if not text or path.is_absolute() or ".." in path.parts or "\\" in text or "\x00" in text:
        raise ClosureError("INVALID_MUTATION_PATH")
    return path.as_posix()


def _path_matches(path: str, boundary: str) -> bool:
    p = path.rstrip("/")
    b = boundary.rstrip("/")
    return p == b or p.startswith(b + "/")


def _run_git(root: Path, *args: str, timeout: float = 30.0) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()[:1200]
        raise ClosureError(f"GIT_COMMAND_FAILED:{args[0]}:{detail}")
    return result.stdout.strip()


def _atomic_json(path: Path, value: Mapping[str, Any]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = (json.dumps(dict(value), ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")
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
    return _sha256(payload)


def _changed_paths(root: Path, base: str, head: str) -> list[str]:
    output = _run_git(root, "diff", "--name-only", base, head, "--")
    return sorted(line.strip() for line in output.splitlines() if line.strip())


def _deleted_paths(root: Path, base: str, head: str) -> list[str]:
    output = _run_git(root, "diff", "--name-status", base, head, "--")
    deleted: list[str] = []
    for line in output.splitlines():
        parts = line.split("\t")
        if parts and parts[0].startswith("D") and len(parts) >= 2:
            deleted.append(parts[-1])
    return sorted(deleted)


def _diff_sha(root: Path, base: str, head: str) -> str:
    # C worker receipts hash the normalized/stripped git-diff text. Preserve
    # that identity contract for receipt verification.
    return _sha256(_run_git(root, "diff", "--binary", base, head))


def _raw_diff_patch(root: Path, base: str, head: str) -> str:
    result = subprocess.run(
        ["git", "diff", "--binary", base, head],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise ClosureError(f"GIT_DIFF_FAILED:{(result.stderr or result.stdout).strip()[:1200]}")
    return result.stdout


def _receipt_identity(receipt: Mapping[str, Any]) -> str:
    material = dict(receipt)
    material.pop("receipt_id", None)
    return _sha256(_canonical_json(material))


def _verify_task_card_binding(repository_root: Path, task_card_ref: str, task_card_hash: str) -> None:
    relative = _safe_relative_path(task_card_ref)
    if not _is_hex(task_card_hash, 64):
        raise ClosureError("TASK_CARD_HASH_INVALID")
    path = (repository_root / relative).resolve()
    try:
        path.relative_to(repository_root)
    except ValueError as exc:
        raise ClosureError("TASK_CARD_OUTSIDE_REPOSITORY") from exc
    if not path.is_file():
        raise ClosureError("TASK_CARD_MISSING")
    tracked = subprocess.run(
        ["git", "ls-files", "--error-unmatch", "--", relative],
        cwd=repository_root,
        capture_output=True,
        text=True,
        check=False,
    )
    if tracked.returncode != 0:
        raise ClosureError("TASK_CARD_NOT_TRACKED")
    if _sha256(path.read_bytes()) != str(task_card_hash).lower():
        raise ClosureError("TASK_CARD_HASH_MISMATCH")


@dataclass(frozen=True)
class VerifierSpec:
    verifier_id: str
    argv: tuple[str, ...]
    owner_unit: str = ""
    timeout: float = 120.0

    @classmethod
    def from_value(cls, value: Mapping[str, Any] | "VerifierSpec") -> "VerifierSpec":
        if isinstance(value, cls):
            return value
        if not isinstance(value, Mapping):
            raise ClosureError("INVALID_VERIFIER_SPEC")
        verifier_id = _safe_slug(value.get("id"), "verifier_id")
        raw_argv = value.get("argv")
        if not isinstance(raw_argv, (list, tuple)) or not raw_argv or len(raw_argv) > 64:
            raise ClosureError("INVALID_VERIFIER_ARGV")
        argv: list[str] = []
        for part in raw_argv:
            text = str(part)
            if not text or len(text) > 4096 or "\x00" in text:
                raise ClosureError("INVALID_VERIFIER_ARGV")
            argv.append(text)
        owner_unit = str(value.get("owner_unit") or "").strip()
        if owner_unit:
            owner_unit = _safe_slug(owner_unit, "owner_unit")
        timeout = float(value.get("timeout", 120.0))
        if timeout <= 0 or timeout > 1800:
            raise ClosureError("INVALID_VERIFIER_TIMEOUT")
        return cls(verifier_id=verifier_id, argv=tuple(argv), owner_unit=owner_unit, timeout=timeout)


@dataclass(frozen=True)
class AssemblyLease:
    workspace_id: str
    path: str
    base_sha: str


class ClosureStore:
    def __init__(self, root: str | os.PathLike[str]):
        self.root = Path(root).expanduser().resolve()
        self.verifications = self.root / "verifications"
        self.repair_deltas = self.root / "repair-deltas"
        self.task_candidates = self.root / "task-candidates"
        self.acceptance_packets = self.root / "acceptance-packets"
        self.capsules = self.root / "capsules"

    def write_verification(self, value: Mapping[str, Any]) -> tuple[str, str]:
        scope = str(value.get("scope") or "")
        task = _safe_slug(value.get("task_id"), "task_id")
        unit = str(value.get("unit_id") or "task")
        name = f"{task}--{unit}--{scope.lower()}--{value.get('verification_id')}.json"
        path = self.verifications / name
        return str(path), _atomic_json(path, value)

    def repair_count(self, task_id: str, unit_id: str) -> int:
        prefix = f"{_safe_slug(task_id, 'task_id')}--{_safe_slug(unit_id, 'unit_id')}--"
        if not self.repair_deltas.exists():
            return 0
        return sum(1 for path in self.repair_deltas.iterdir() if path.is_file() and path.name.startswith(prefix))

    def next_repair_index(self, task_id: str, unit_id: str) -> int:
        return self.repair_count(task_id, unit_id) + 1

    def write_repair_delta(self, value: Mapping[str, Any], *, repair_index: int) -> tuple[str, str]:
        task = _safe_slug(value.get("task_id"), "task_id")
        unit = _safe_slug(value.get("unit_id"), "unit_id")
        path = self.repair_deltas / f"{task}--{unit}--{repair_index:03d}.json"
        if path.exists():
            raise ClosureError("REPAIR_DELTA_REPLAY_FORBIDDEN")
        return str(path), _atomic_json(path, value)

    def write_task_candidate(self, value: Mapping[str, Any]) -> tuple[str, str]:
        task = _safe_slug(value.get("task_id"), "task_id")
        path = self.task_candidates / f"{task}--{value.get('task_candidate_id')}.json"
        return str(path), _atomic_json(path, value)

    def write_acceptance_packet(self, value: Mapping[str, Any]) -> tuple[str, str]:
        task = _safe_slug(value.get("task_id"), "task_id")
        path = self.acceptance_packets / f"{task}--{value.get('packet_id')}.json"
        return str(path), _atomic_json(path, value)

    def write_capsule(self, value: Mapping[str, Any]) -> tuple[str, str]:
        task = _safe_slug(value.get("task_id"), "task_id")
        path = self.capsules / f"{task}--{value.get('capsule_id')}.json"
        return str(path), _atomic_json(path, value)


class CompositionWorkspaceAllocator:
    def __init__(self, repository_root: str | os.PathLike[str], workspace_root: str | os.PathLike[str]):
        self.repository_root = Path(repository_root).expanduser().resolve()
        self.workspace_root = Path(workspace_root).expanduser().resolve()

    def allocate(self, task_id: str, base_sha: str) -> AssemblyLease:
        if not _is_hex(base_sha, 40):
            raise ClosureError("INVALID_BASE_SHA")
        if _run_git(self.repository_root, "cat-file", "-t", base_sha) != "commit":
            raise ClosureError("BASE_NOT_COMMIT")
        workspace_id = f"ei-close-{_safe_slug(task_id, 'task_id')}-{uuid.uuid4().hex[:12]}"
        path = self.workspace_root / workspace_id
        if path.exists():
            raise ClosureError("ASSEMBLY_WORKSPACE_COLLISION")
        self.workspace_root.mkdir(parents=True, exist_ok=True)
        result = subprocess.run(
            ["git", "worktree", "add", "--detach", str(path), base_sha],
            cwd=self.repository_root,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise ClosureError(f"ASSEMBLY_WORKSPACE_FAILED:{(result.stderr or result.stdout).strip()[:1200]}")
        if _run_git(path, "rev-parse", "HEAD") != base_sha or _run_git(path, "status", "--porcelain=v1"):
            raise ClosureError("ASSEMBLY_WORKSPACE_NOT_FRESH")
        return AssemblyLease(workspace_id=workspace_id, path=str(path), base_sha=base_sha)


def validate_worker_receipt(receipt: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(receipt, Mapping) or receipt.get("schema") != WORKER_RECEIPT_SCHEMA:
        raise ClosureError("INVALID_WORKER_RECEIPT")
    if receipt.get("status") != "CANDIDATE_READY_FOR_VERIFICATION":
        raise ClosureError("UNIT_CANDIDATE_REQUIRED")
    task_id = _safe_slug(receipt.get("task_id"), "task_id")
    unit_id = _safe_slug(receipt.get("unit_id"), "unit_id")
    if receipt.get("provider") != PROVIDER or receipt.get("model") != MODEL:
        raise ClosureError("WORKER_MODEL_BINDING_MISMATCH")
    session_id = str(receipt.get("session_id") or "")
    if not session_id.startswith(_SESSION_PREFIX) or len(session_id) < 12:
        raise ClosureError("INVALID_SESSION_ID")
    workspace_id = _safe_slug(receipt.get("workspace_id"), "workspace_id")
    workspace_path = Path(str(receipt.get("workspace_path") or "")).expanduser().resolve()
    if not workspace_path.is_dir():
        raise ClosureError("UNIT_WORKSPACE_MISSING")
    base_sha = str(receipt.get("base_sha") or "").lower()
    candidate_commit = str(receipt.get("candidate_commit") or "").lower()
    candidate_tree = str(receipt.get("candidate_tree") or "").lower()
    candidate_diff_sha256 = str(receipt.get("candidate_diff_sha256") or "").lower()
    receipt_id = str(receipt.get("receipt_id") or "").lower()
    if not _is_hex(base_sha, 40) or not _is_hex(candidate_commit, 40) or not _is_hex(candidate_tree, 40):
        raise ClosureError("INVALID_CANDIDATE_GIT_IDENTITY")
    if not _is_hex(candidate_diff_sha256, 64) or not _is_hex(receipt_id, 64):
        raise ClosureError("INVALID_CANDIDATE_HASH_IDENTITY")
    if _receipt_identity(receipt) != receipt_id:
        raise ClosureError("WORKER_RECEIPT_IDENTITY_MISMATCH")
    if _run_git(workspace_path, "rev-parse", "HEAD") != candidate_commit:
        raise ClosureError("UNIT_WORKSPACE_HEAD_MISMATCH")
    if _run_git(workspace_path, "status", "--porcelain=v1"):
        raise ClosureError("UNIT_WORKSPACE_DIRTY")
    if _run_git(workspace_path, "rev-parse", "HEAD^{tree}") != candidate_tree:
        raise ClosureError("UNIT_CANDIDATE_TREE_MISMATCH")
    parent_commit = str(receipt.get("parent_commit") or base_sha).lower()
    if not _is_hex(parent_commit, 40):
        raise ClosureError("INVALID_PARENT_COMMIT")
    if _diff_sha(workspace_path, parent_commit, candidate_commit) != candidate_diff_sha256:
        raise ClosureError("UNIT_CANDIDATE_DIFF_HASH_MISMATCH")
    mutation_paths_raw = receipt.get("mutation_paths")
    if not isinstance(mutation_paths_raw, list) or not mutation_paths_raw:
        raise ClosureError("UNIT_MUTATION_SCOPE_MISSING")
    mutation_paths = [_safe_relative_path(path) for path in mutation_paths_raw]
    cumulative_changed = _changed_paths(workspace_path, base_sha, candidate_commit)
    if not cumulative_changed:
        raise ClosureError("EMPTY_UNIT_CANDIDATE")
    for path in cumulative_changed:
        if not any(_path_matches(path, boundary) for boundary in mutation_paths):
            raise ClosureError(f"UNIT_SCOPE_WIDENING:{path}")
    cumulative_deleted = _deleted_paths(workspace_path, base_sha, candidate_commit)
    if cumulative_deleted and not bool(receipt.get("allow_deletions", False)):
        raise ClosureError("UNIT_DELETION_NOT_AUTHORIZED")
    return {
        "task_id": task_id,
        "unit_id": unit_id,
        "receipt_id": receipt_id,
        "session_id": session_id,
        "workspace_id": workspace_id,
        "workspace_path": str(workspace_path),
        "base_sha": base_sha,
        "candidate_commit": candidate_commit,
        "candidate_tree": candidate_tree,
        "candidate_diff_sha256": candidate_diff_sha256,
        "parent_commit": parent_commit,
        "mutation_paths": mutation_paths,
        "allow_deletions": bool(receipt.get("allow_deletions", False)),
        "cumulative_changed_paths": cumulative_changed,
        "cumulative_deleted_paths": cumulative_deleted,
    }


def _run_verifier_specs(
    *,
    task_id: str,
    unit_id: str,
    workspace_path: str,
    candidate_commit: str,
    specs: Sequence[Mapping[str, Any] | VerifierSpec],
    schema: str,
    scope: str,
) -> dict[str, Any]:
    root = Path(workspace_path).expanduser().resolve()
    if _run_git(root, "rev-parse", "HEAD") != candidate_commit:
        raise ClosureError("VERIFIER_HEAD_MISMATCH")
    if _run_git(root, "status", "--porcelain=v1"):
        raise ClosureError("VERIFIER_WORKSPACE_DIRTY")
    parsed = [VerifierSpec.from_value(spec) for spec in specs]
    if not parsed:
        raise ClosureError("VERIFIER_SPECS_REQUIRED")
    results: list[dict[str, Any]] = []
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    for spec in parsed:
        started = time.monotonic()
        try:
            proc = subprocess.run(
                list(spec.argv),
                cwd=root,
                capture_output=True,
                text=True,
                timeout=spec.timeout,
                check=False,
                env=env,
                shell=False,
            )
            returncode: int | None = int(proc.returncode)
            stdout = proc.stdout or ""
            stderr = proc.stderr or ""
            error = ""
        except subprocess.TimeoutExpired as exc:
            returncode = None
            stdout = str(exc.stdout or "")
            stderr = str(exc.stderr or "")
            error = "VERIFIER_TIMEOUT"
        wall_ms = max(0, int((time.monotonic() - started) * 1000))
        row = {
            "verifier_id": spec.verifier_id,
            "argv": list(spec.argv),
            "argv_sha256": _sha256(_canonical_json(list(spec.argv))),
            "cwd_sha256": _sha256(str(root)),
            "owner_unit": spec.owner_unit,
            "returncode": returncode,
            "stdout_sha256": _sha256(stdout),
            "stderr_sha256": _sha256(stderr),
            "wall_time_ms": wall_ms,
            "error": error,
            "passed": returncode == 0 and not error,
        }
        results.append(row)
        if _run_git(root, "rev-parse", "HEAD") != candidate_commit or _run_git(root, "status", "--porcelain=v1"):
            raise ClosureError("VERIFIER_MUTATED_WORKSPACE")
    status = "PASS" if all(row["passed"] for row in results) else "FAIL"
    verification = {
        "schema": schema,
        "scope": scope,
        "task_id": task_id,
        "unit_id": unit_id,
        "workspace_path": str(root),
        "candidate_commit": candidate_commit,
        "status": status,
        "failed_verifier_ids": [row["verifier_id"] for row in results if not row["passed"]],
        "results": results,
    }
    verification["verification_id"] = _sha256(_canonical_json(verification))
    return verification


def verify_unit_candidate(
    receipt: Mapping[str, Any],
    verifier_specs: Sequence[Mapping[str, Any] | VerifierSpec],
) -> dict[str, Any]:
    bound = validate_worker_receipt(receipt)
    result = _run_verifier_specs(
        task_id=bound["task_id"],
        unit_id=bound["unit_id"],
        workspace_path=bound["workspace_path"],
        candidate_commit=bound["candidate_commit"],
        specs=verifier_specs,
        schema=UNIT_VERIFICATION_SCHEMA,
        scope="UNIT",
    )
    result.update({
        "worker_receipt_id": bound["receipt_id"],
        "session_id": bound["session_id"],
        "workspace_id": bound["workspace_id"],
        "candidate_tree": bound["candidate_tree"],
        "candidate_diff_sha256": bound["candidate_diff_sha256"],
        "base_sha": bound["base_sha"],
    })
    material = dict(result)
    material.pop("verification_id", None)
    result["verification_id"] = _sha256(_canonical_json(material))
    return result


def build_unit_repair_delta(
    receipt: Mapping[str, Any],
    verification: Mapping[str, Any],
    *,
    repair_index: int,
) -> dict[str, Any]:
    bound = validate_worker_receipt(receipt)
    if verification.get("schema") != UNIT_VERIFICATION_SCHEMA or verification.get("status") != "FAIL":
        raise ClosureError("FAILED_UNIT_VERIFICATION_REQUIRED")
    if verification.get("worker_receipt_id") != bound["receipt_id"] or verification.get("task_id") != bound["task_id"] or verification.get("unit_id") != bound["unit_id"]:
        raise ClosureError("UNIT_VERIFICATION_BINDING_MISMATCH")
    if repair_index <= 0:
        raise ClosureError("INVALID_REPAIR_INDEX")
    findings = [
        {
            "verifier_id": row["verifier_id"],
            "returncode": row["returncode"],
            "stdout_sha256": row["stdout_sha256"],
            "stderr_sha256": row["stderr_sha256"],
            "error": row["error"],
        }
        for row in verification.get("results", [])
        if not row.get("passed")
    ]
    delta = {
        "schema": UNIT_REPAIR_DELTA_SCHEMA,
        "task_id": bound["task_id"],
        "unit_id": bound["unit_id"],
        "repair_index": repair_index,
        "parent_receipt_id": bound["receipt_id"],
        "parent_candidate_commit": bound["candidate_commit"],
        "verification_id": verification["verification_id"],
        "session_id": bound["session_id"],
        "workspace_id": bound["workspace_id"],
        "workspace_path": bound["workspace_path"],
        "provider": PROVIDER,
        "model": MODEL,
        "allowed_mutation_paths": list(bound["mutation_paths"]),
        "findings": findings,
        "stop_conditions": [
            "scope_expands",
            "session_changes",
            "workspace_changes",
            "model_changes",
            "provider_outcome_becomes_ambiguous",
        ],
        "claim_ceiling": "BOUNDED_REPAIR_ONLY",
    }
    delta["delta_id"] = _sha256(_canonical_json(delta))
    return delta


def build_composition_repair_delta(
    receipt: Mapping[str, Any],
    whole_verification: Mapping[str, Any],
    *,
    repair_index: int,
) -> dict[str, Any]:
    bound = validate_worker_receipt(receipt)
    if whole_verification.get("schema") != WHOLE_VERIFICATION_SCHEMA or whole_verification.get("status") != "FAIL":
        raise ClosureError("FAILED_WHOLE_VERIFICATION_REQUIRED")
    failed = [row for row in whole_verification.get("results", []) if not row.get("passed")]
    owners = {str(row.get("owner_unit") or "") for row in failed}
    if not failed or owners != {bound["unit_id"]}:
        raise ClosureError("WHOLE_FAILURE_NOT_UNIQUELY_OWNED")
    findings = [
        {
            "verifier_id": row["verifier_id"],
            "returncode": row["returncode"],
            "stdout_sha256": row["stdout_sha256"],
            "stderr_sha256": row["stderr_sha256"],
            "error": row["error"],
        }
        for row in failed
    ]
    delta = {
        "schema": COMPOSITION_REPAIR_DELTA_SCHEMA,
        "task_id": bound["task_id"],
        "unit_id": bound["unit_id"],
        "repair_index": repair_index,
        "parent_receipt_id": bound["receipt_id"],
        "parent_candidate_commit": bound["candidate_commit"],
        "whole_verification_id": whole_verification["verification_id"],
        "session_id": bound["session_id"],
        "workspace_id": bound["workspace_id"],
        "workspace_path": bound["workspace_path"],
        "provider": PROVIDER,
        "model": MODEL,
        "allowed_mutation_paths": list(bound["mutation_paths"]),
        "findings": findings,
        "stop_conditions": [
            "scope_expands",
            "failure_requires_more_than_this_unit",
            "session_changes",
            "workspace_changes",
            "model_changes",
        ],
        "claim_ceiling": "BOUNDED_COMPOSITION_REPAIR_ONLY",
    }
    delta["delta_id"] = _sha256(_canonical_json(delta))
    return delta


def _validate_repair_result(parent_bound: Mapping[str, Any], repaired: Mapping[str, Any]) -> None:
    repaired_bound = validate_worker_receipt(repaired)
    for field in ("task_id", "unit_id", "session_id", "workspace_id", "workspace_path", "base_sha"):
        if repaired_bound[field] != parent_bound[field]:
            raise ClosureError(f"REPAIR_{field.upper()}_MISMATCH")
    if repaired.get("provider") != PROVIDER or repaired.get("model") != MODEL:
        raise ClosureError("REPAIR_MODEL_BINDING_MISMATCH")
    if repaired.get("parent_receipt_id") != parent_bound["receipt_id"]:
        raise ClosureError("REPAIR_PARENT_RECEIPT_MISMATCH")


def compose_task_candidate(
    *,
    repository_root: str | os.PathLike[str],
    allocator: CompositionWorkspaceAllocator,
    receipts: Sequence[Mapping[str, Any]],
    verifications: Sequence[Mapping[str, Any]],
) -> tuple[dict[str, Any], AssemblyLease]:
    if not receipts:
        raise ClosureError("UNIT_RECEIPTS_REQUIRED")
    receipt_by_unit: dict[str, tuple[Mapping[str, Any], dict[str, Any]]] = {}
    for receipt in receipts:
        bound = validate_worker_receipt(receipt)
        if bound["unit_id"] in receipt_by_unit:
            raise ClosureError("DUPLICATE_UNIT_RECEIPT")
        receipt_by_unit[bound["unit_id"]] = (receipt, bound)
    verification_by_unit: dict[str, Mapping[str, Any]] = {}
    for verification in verifications:
        unit_id = _safe_slug(verification.get("unit_id"), "unit_id")
        if verification.get("schema") != UNIT_VERIFICATION_SCHEMA or verification.get("status") != "PASS":
            raise ClosureError("ALL_UNIT_VERIFICATIONS_MUST_PASS")
        if unit_id in verification_by_unit:
            raise ClosureError("DUPLICATE_UNIT_VERIFICATION")
        verification_by_unit[unit_id] = verification
    if set(verification_by_unit) != set(receipt_by_unit):
        raise ClosureError("UNIT_VERIFICATION_SET_MISMATCH")
    task_ids = {bound["task_id"] for _, bound in receipt_by_unit.values()}
    bases = {bound["base_sha"] for _, bound in receipt_by_unit.values()}
    if len(task_ids) != 1:
        raise ClosureError("MIXED_TASK_COMPOSITION_FORBIDDEN")
    if len(bases) != 1:
        raise ClosureError("COMMON_BASE_REQUIRED")
    task_id = next(iter(task_ids))
    base_sha = next(iter(bases))
    for unit_id, (receipt, bound) in receipt_by_unit.items():
        verification = verification_by_unit[unit_id]
        if verification.get("worker_receipt_id") != bound["receipt_id"] or verification.get("candidate_commit") != bound["candidate_commit"]:
            raise ClosureError("UNIT_VERIFICATION_RECEIPT_DRIFT")
    lease = allocator.allocate(task_id, base_sha)
    assembly = Path(lease.path)
    repo = Path(repository_root).expanduser().resolve()
    order = sorted(receipt_by_unit)
    cumulative_paths_by_unit: dict[str, list[str]] = {}
    seen_changed: set[str] = set()
    for unit_id in order:
        _, bound = receipt_by_unit[unit_id]
        cumulative = _changed_paths(repo, base_sha, bound["candidate_commit"])
        if not cumulative:
            raise ClosureError("EMPTY_UNIT_CANDIDATE")
        overlap = seen_changed.intersection(cumulative)
        if overlap:
            raise ClosureError(f"COMPOSITION_PATH_OVERLAP:{','.join(sorted(overlap))}")
        seen_changed.update(cumulative)
        cumulative_paths_by_unit[unit_id] = cumulative
        patch = _raw_diff_patch(repo, base_sha, bound["candidate_commit"])
        check = subprocess.run(
            ["git", "apply", "--index", "--check"],
            cwd=assembly,
            input=patch,
            capture_output=True,
            text=True,
            check=False,
        )
        if check.returncode != 0:
            raise ClosureError(f"COMPOSITION_CONFLICT:{unit_id}:{(check.stderr or check.stdout).strip()[:800]}")
        apply = subprocess.run(
            ["git", "apply", "--index"],
            cwd=assembly,
            input=patch,
            capture_output=True,
            text=True,
            check=False,
        )
        if apply.returncode != 0:
            raise ClosureError(f"COMPOSITION_APPLY_FAILED:{unit_id}:{(apply.stderr or apply.stdout).strip()[:800]}")
    staged = sorted(line for line in _run_git(assembly, "diff", "--cached", "--name-only").splitlines() if line)
    if staged != sorted(seen_changed):
        raise ClosureError("COMPOSED_STAGED_PATH_SET_MISMATCH")
    for unit_id, (_, bound) in receipt_by_unit.items():
        for path in cumulative_paths_by_unit[unit_id]:
            if not any(_path_matches(path, boundary) for boundary in bound["mutation_paths"]):
                raise ClosureError(f"COMPOSED_SCOPE_WIDENING:{unit_id}:{path}")
    check = subprocess.run(["git", "diff", "--cached", "--check"], cwd=assembly, capture_output=True, text=True, check=False)
    if check.returncode != 0:
        raise ClosureError(f"COMPOSED_DIFF_CHECK_FAILED:{(check.stdout or check.stderr).strip()[:800]}")
    commit = subprocess.run(
        ["git", "commit", "-m", f"candidate: {task_id}/composed"],
        cwd=assembly,
        capture_output=True,
        text=True,
        check=False,
    )
    if commit.returncode != 0:
        raise ClosureError(f"COMPOSED_COMMIT_FAILED:{(commit.stderr or commit.stdout).strip()[:1000]}")
    candidate_commit = _run_git(assembly, "rev-parse", "HEAD")
    candidate_tree = _run_git(assembly, "rev-parse", "HEAD^{tree}")
    changed_paths = _changed_paths(assembly, base_sha, candidate_commit)
    deleted_paths = _deleted_paths(assembly, base_sha, candidate_commit)
    for path in deleted_paths:
        owners = [bound for _, bound in receipt_by_unit.values() if any(_path_matches(path, boundary) for boundary in bound["mutation_paths"])]
        if not owners or not all(owner["allow_deletions"] for owner in owners):
            raise ClosureError(f"COMPOSED_DELETION_NOT_AUTHORIZED:{path}")
    task_candidate = {
        "schema": TASK_CANDIDATE_SCHEMA,
        "task_id": task_id,
        "base_sha": base_sha,
        "workspace_id": lease.workspace_id,
        "workspace_path": lease.path,
        "candidate_commit": candidate_commit,
        "candidate_tree": candidate_tree,
        "candidate_diff_sha256": _diff_sha(assembly, base_sha, candidate_commit),
        "changed_paths": changed_paths,
        "deleted_paths": deleted_paths,
        "composition_order": order,
        "unit_lineage": [
            {
                "unit_id": unit_id,
                "receipt_id": receipt_by_unit[unit_id][1]["receipt_id"],
                "verification_id": verification_by_unit[unit_id]["verification_id"],
                "unit_candidate_commit": receipt_by_unit[unit_id][1]["candidate_commit"],
                "unit_candidate_tree": receipt_by_unit[unit_id][1]["candidate_tree"],
            }
            for unit_id in order
        ],
        "claim_ceiling": "TASK_CANDIDATE_REQUIRES_WHOLE_TASK_VERIFICATION",
    }
    task_candidate["task_candidate_id"] = _sha256(_canonical_json(task_candidate))
    return task_candidate, lease


def verify_whole_task_candidate(
    task_candidate: Mapping[str, Any],
    verifier_specs: Sequence[Mapping[str, Any] | VerifierSpec],
) -> dict[str, Any]:
    if task_candidate.get("schema") != TASK_CANDIDATE_SCHEMA:
        raise ClosureError("INVALID_TASK_CANDIDATE")
    result = _run_verifier_specs(
        task_id=_safe_slug(task_candidate.get("task_id"), "task_id"),
        unit_id="",
        workspace_path=str(task_candidate.get("workspace_path") or ""),
        candidate_commit=str(task_candidate.get("candidate_commit") or ""),
        specs=verifier_specs,
        schema=WHOLE_VERIFICATION_SCHEMA,
        scope="WHOLE_TASK",
    )
    result.update({
        "task_candidate_id": task_candidate.get("task_candidate_id"),
        "candidate_tree": task_candidate.get("candidate_tree"),
        "candidate_diff_sha256": task_candidate.get("candidate_diff_sha256"),
    })
    material = dict(result)
    material.pop("verification_id", None)
    result["verification_id"] = _sha256(_canonical_json(material))
    return result


def _unique_failed_owner(whole_verification: Mapping[str, Any], valid_units: set[str]) -> str:
    failed = [row for row in whole_verification.get("results", []) if not row.get("passed")]
    if not failed:
        return ""
    owners = [str(row.get("owner_unit") or "") for row in failed]
    if any(not owner for owner in owners):
        return ""
    unique = set(owners)
    if len(unique) != 1:
        return ""
    owner = next(iter(unique))
    return owner if owner in valid_units else ""


def build_acceptance_packet(
    *,
    task_candidate: Mapping[str, Any],
    whole_verification: Mapping[str, Any],
    unit_receipts: Sequence[Mapping[str, Any]],
    unit_verifications: Sequence[Mapping[str, Any]],
    task_card_ref: str,
    task_card_hash: str,
    external_intelligence_refs: Sequence[str] = (),
) -> dict[str, Any]:
    if task_candidate.get("schema") != TASK_CANDIDATE_SCHEMA:
        raise ClosureError("INVALID_TASK_CANDIDATE")
    if whole_verification.get("schema") != WHOLE_VERIFICATION_SCHEMA or whole_verification.get("status") != "PASS":
        raise ClosureError("WHOLE_TASK_PASS_REQUIRED")
    if whole_verification.get("task_candidate_id") != task_candidate.get("task_candidate_id"):
        raise ClosureError("WHOLE_VERIFICATION_CANDIDATE_MISMATCH")
    if not task_card_ref or not _is_hex(task_card_hash, 64):
        raise ClosureError("TASK_CARD_BINDING_REQUIRED")
    receipt_by_unit = {str(receipt.get("unit_id")): validate_worker_receipt(receipt) for receipt in unit_receipts}
    verification_by_unit = {str(value.get("unit_id")): value for value in unit_verifications}
    if set(receipt_by_unit) != set(verification_by_unit):
        raise ClosureError("ACCEPTANCE_UNIT_SET_MISMATCH")
    for unit_id, verification in verification_by_unit.items():
        if verification.get("schema") != UNIT_VERIFICATION_SCHEMA or verification.get("status") != "PASS":
            raise ClosureError("ACCEPTANCE_REQUIRES_UNIT_PASS")
        if verification.get("worker_receipt_id") != receipt_by_unit[unit_id]["receipt_id"]:
            raise ClosureError("ACCEPTANCE_UNIT_BINDING_MISMATCH")
    packet = {
        "schema": ACCEPTANCE_PACKET_SCHEMA,
        "task_id": task_candidate["task_id"],
        "task_card_ref": str(task_card_ref),
        "task_card_hash": str(task_card_hash).lower(),
        "external_intelligence_refs": [str(ref) for ref in external_intelligence_refs],
        "task_candidate": {
            "task_candidate_id": task_candidate["task_candidate_id"],
            "base_sha": task_candidate["base_sha"],
            "candidate_commit": task_candidate["candidate_commit"],
            "candidate_tree": task_candidate["candidate_tree"],
            "candidate_diff_sha256": task_candidate["candidate_diff_sha256"],
            "changed_paths": list(task_candidate["changed_paths"]),
            "deleted_paths": list(task_candidate["deleted_paths"]),
            "composition_order": list(task_candidate["composition_order"]),
        },
        "unit_lineage": [
            {
                "unit_id": unit_id,
                "worker_receipt_id": receipt_by_unit[unit_id]["receipt_id"],
                "unit_verification_id": verification_by_unit[unit_id]["verification_id"],
                "session_id": receipt_by_unit[unit_id]["session_id"],
                "workspace_id": receipt_by_unit[unit_id]["workspace_id"],
                "candidate_commit": receipt_by_unit[unit_id]["candidate_commit"],
                "candidate_tree": receipt_by_unit[unit_id]["candidate_tree"],
            }
            for unit_id in sorted(receipt_by_unit)
        ],
        "whole_task_verification_id": whole_verification["verification_id"],
        "whole_task_status": "PASS",
        "current_gate": "PENDING_INDEPENDENT_ACCEPTANCE",
        "claim_ceiling": CLAIM_CEILING,
    }
    packet["packet_id"] = _sha256(_canonical_json(packet))
    return packet


def build_closure_capsule(
    *,
    task_candidate: Mapping[str, Any],
    acceptance_packet_ref: str,
    acceptance_packet_sha256: str,
) -> dict[str, Any]:
    if task_candidate.get("schema") != TASK_CANDIDATE_SCHEMA or not acceptance_packet_ref or not _is_hex(acceptance_packet_sha256, 64):
        raise ClosureError("INVALID_CAPSULE_INPUT")
    capsule = {
        "schema": CLOSURE_CAPSULE_SCHEMA,
        "task_id": task_candidate["task_id"],
        "candidate_commit": task_candidate["candidate_commit"],
        "candidate_tree": task_candidate["candidate_tree"],
        "candidate_diff_sha256": task_candidate["candidate_diff_sha256"],
        "verification_state": "WHOLE_TASK_PASS",
        "acceptance_packet_ref": acceptance_packet_ref,
        "acceptance_packet_sha256": acceptance_packet_sha256,
        "current_gate": "PENDING_INDEPENDENT_ACCEPTANCE",
        "next_action": "run_independent_candidate_acceptance_audit",
        "stop_if": "independent_acceptance_not_explicitly_granted",
        "claim_ceiling": CLAIM_CEILING,
    }
    capsule["capsule_id"] = _sha256(_canonical_json(capsule))
    return capsule


class ExternalIntelligenceClosureRuntime:
    def __init__(
        self,
        *,
        repository_root: str | os.PathLike[str],
        allocator: CompositionWorkspaceAllocator,
        store: ClosureStore,
        c_runtime: Any | None = None,
        max_repairs_per_unit: int = 1,
    ):
        if max_repairs_per_unit < 0 or max_repairs_per_unit > 20:
            raise ClosureError("INVALID_REPAIR_BUDGET")
        self.repository_root = Path(repository_root).expanduser().resolve()
        self.allocator = allocator
        self.store = store
        self.c_runtime = c_runtime
        self.max_repairs_per_unit = max_repairs_per_unit

    def _persist_verification(self, verification: Mapping[str, Any]) -> dict[str, Any]:
        ref, sha = self.store.write_verification(verification)
        value = dict(verification)
        value["artifact_ref"] = ref
        value["artifact_sha256"] = sha
        return value

    def _repair(
        self,
        *,
        receipt: Mapping[str, Any],
        delta: Mapping[str, Any],
        repair_index: int,
    ) -> tuple[Mapping[str, Any] | None, dict[str, Any]]:
        ref, sha = self.store.write_repair_delta(delta, repair_index=repair_index)
        persisted = dict(delta)
        persisted["artifact_ref"] = ref
        persisted["artifact_sha256"] = sha
        if self.c_runtime is None:
            return None, persisted
        parent_bound = validate_worker_receipt(receipt)
        repaired = self.c_runtime.continue_repair(
            receipt,
            repair_id=f"d{repair_index:03d}",
            repair_ref=ref,
            repair_sha256=sha,
        )
        _validate_repair_result(parent_bound, repaired)
        return repaired, persisted

    def close_task(
        self,
        *,
        unit_receipts: Sequence[Mapping[str, Any]],
        unit_verifiers: Mapping[str, Sequence[Mapping[str, Any] | VerifierSpec]],
        whole_verifiers: Sequence[Mapping[str, Any] | VerifierSpec],
        task_card_ref: str,
        task_card_hash: str,
        external_intelligence_refs: Sequence[str] = (),
    ) -> dict[str, Any]:
        started = time.monotonic()
        _verify_task_card_binding(self.repository_root, task_card_ref, task_card_hash)
        if not unit_receipts:
            raise ClosureError("UNIT_RECEIPTS_REQUIRED")
        current: dict[str, Mapping[str, Any]] = {}
        for receipt in unit_receipts:
            bound = validate_worker_receipt(receipt)
            if bound["unit_id"] in current:
                raise ClosureError("DUPLICATE_UNIT_RECEIPT")
            current[bound["unit_id"]] = receipt
        if set(unit_verifiers) != set(current):
            raise ClosureError("UNIT_VERIFIER_SET_MISMATCH")
        task_ids = {validate_worker_receipt(receipt)["task_id"] for receipt in current.values()}
        if len(task_ids) != 1:
            raise ClosureError("MIXED_TASK_CLOSURE_FORBIDDEN")
        task_id = next(iter(task_ids))
        repair_counts = {unit_id: self.store.repair_count(task_id, unit_id) for unit_id in current}
        repair_deltas: list[dict[str, Any]] = []
        verification_history: list[dict[str, Any]] = []
        composition_conflicts = 0
        max_cycles = max(2, 2 + self.max_repairs_per_unit * max(1, len(current)))

        for _cycle in range(max_cycles):
            latest_verifications: dict[str, dict[str, Any]] = {}
            failing_units: list[str] = []
            for unit_id in sorted(current):
                verification = self._persist_verification(verify_unit_candidate(current[unit_id], unit_verifiers[unit_id]))
                latest_verifications[unit_id] = verification
                verification_history.append(verification)
                if verification["status"] != "PASS":
                    failing_units.append(unit_id)
            if failing_units:
                for unit_id in failing_units:
                    if repair_counts[unit_id] >= self.max_repairs_per_unit:
                        return self._terminal(
                            status="REPAIR_BUDGET_EXHAUSTED",
                            current=current,
                            verifications=latest_verifications,
                            repair_deltas=repair_deltas,
                            composition_conflicts=composition_conflicts,
                            started=started,
                            reason=unit_id,
                        )
                    repair_index = self.store.next_repair_index(task_id, unit_id)
                    delta = build_unit_repair_delta(current[unit_id], latest_verifications[unit_id], repair_index=repair_index)
                    repaired, persisted = self._repair(receipt=current[unit_id], delta=delta, repair_index=repair_index)
                    repair_deltas.append(persisted)
                    repair_counts[unit_id] += 1
                    if repaired is None:
                        return self._terminal(
                            status="UNIT_REPAIR_REQUIRED",
                            current=current,
                            verifications=latest_verifications,
                            repair_deltas=repair_deltas,
                            composition_conflicts=composition_conflicts,
                            started=started,
                            reason=unit_id,
                        )
                    current[unit_id] = repaired
                continue

            try:
                task_candidate, _lease = compose_task_candidate(
                    repository_root=self.repository_root,
                    allocator=self.allocator,
                    receipts=[current[unit_id] for unit_id in sorted(current)],
                    verifications=[latest_verifications[unit_id] for unit_id in sorted(current)],
                )
            except ClosureError as exc:
                composition_conflicts += 1
                return self._terminal(
                    status="SCOPE_DELTA_REQUIRED",
                    current=current,
                    verifications=latest_verifications,
                    repair_deltas=repair_deltas,
                    composition_conflicts=composition_conflicts,
                    started=started,
                    reason=str(exc),
                )
            task_candidate_ref, task_candidate_sha = self.store.write_task_candidate(task_candidate)
            task_candidate = dict(task_candidate)
            task_candidate["artifact_ref"] = task_candidate_ref
            task_candidate["artifact_sha256"] = task_candidate_sha
            whole = self._persist_verification(verify_whole_task_candidate(task_candidate, whole_verifiers))
            if whole["status"] == "FAIL":
                owner = _unique_failed_owner(whole, set(current))
                if not owner:
                    return self._terminal(
                        status="SCOPE_DELTA_REQUIRED",
                        current=current,
                        verifications=latest_verifications,
                        repair_deltas=repair_deltas,
                        composition_conflicts=composition_conflicts,
                        started=started,
                        reason="WHOLE_FAILURE_OWNER_AMBIGUOUS",
                        task_candidate=task_candidate,
                        whole_verification=whole,
                    )
                if repair_counts[owner] >= self.max_repairs_per_unit:
                    return self._terminal(
                        status="REPAIR_BUDGET_EXHAUSTED",
                        current=current,
                        verifications=latest_verifications,
                        repair_deltas=repair_deltas,
                        composition_conflicts=composition_conflicts,
                        started=started,
                        reason=owner,
                        task_candidate=task_candidate,
                        whole_verification=whole,
                    )
                repair_index = self.store.next_repair_index(task_candidate["task_id"], owner)
                delta = build_composition_repair_delta(current[owner], whole, repair_index=repair_index)
                repaired, persisted = self._repair(receipt=current[owner], delta=delta, repair_index=repair_index)
                repair_deltas.append(persisted)
                repair_counts[owner] += 1
                if repaired is None:
                    return self._terminal(
                        status="COMPOSITION_REPAIR_REQUIRED",
                        current=current,
                        verifications=latest_verifications,
                        repair_deltas=repair_deltas,
                        composition_conflicts=composition_conflicts,
                        started=started,
                        reason=owner,
                        task_candidate=task_candidate,
                        whole_verification=whole,
                    )
                current[owner] = repaired
                continue

            packet = build_acceptance_packet(
                task_candidate=task_candidate,
                whole_verification=whole,
                unit_receipts=[current[unit_id] for unit_id in sorted(current)],
                unit_verifications=[latest_verifications[unit_id] for unit_id in sorted(current)],
                task_card_ref=task_card_ref,
                task_card_hash=task_card_hash,
                external_intelligence_refs=external_intelligence_refs,
            )
            packet_ref, packet_sha = self.store.write_acceptance_packet(packet)
            packet = dict(packet)
            packet["artifact_ref"] = packet_ref
            packet["artifact_sha256"] = packet_sha
            capsule = build_closure_capsule(
                task_candidate=task_candidate,
                acceptance_packet_ref=packet_ref,
                acceptance_packet_sha256=packet_sha,
            )
            capsule_ref, capsule_sha = self.store.write_capsule(capsule)
            capsule = dict(capsule)
            capsule["artifact_ref"] = capsule_ref
            capsule["artifact_sha256"] = capsule_sha
            telemetry = {
                "unit_count": len(current),
                "verified_unit_count": len(latest_verifications),
                "repair_count": sum(repair_counts.values()),
                "composition_conflict_count": composition_conflicts,
                "whole_task_verifier_count": len(whole.get("results", [])),
                "whole_task_outcome": whole["status"],
                "wall_time_ms": max(0, int((time.monotonic() - started) * 1000)),
                "policy_tuned": False,
            }
            result = {
                "schema": CLOSURE_RUN_SCHEMA,
                "status": CLAIM_CEILING,
                "task_id": task_candidate["task_id"],
                "task_candidate": task_candidate,
                "whole_verification": whole,
                "unit_verifications": [latest_verifications[unit_id] for unit_id in sorted(latest_verifications)],
                "repair_deltas": repair_deltas,
                "acceptance_packet": packet,
                "control_capsule": capsule,
                "telemetry": telemetry,
                "claim_ceiling": CLAIM_CEILING,
            }
            result["run_id"] = _sha256(_canonical_json(result))
            return result

        return self._terminal(
            status="REPAIR_BUDGET_EXHAUSTED",
            current=current,
            verifications={},
            repair_deltas=repair_deltas,
            composition_conflicts=composition_conflicts,
            started=started,
            reason="CLOSURE_CYCLE_LIMIT",
        )

    def _terminal(
        self,
        *,
        status: str,
        current: Mapping[str, Mapping[str, Any]],
        verifications: Mapping[str, Mapping[str, Any]],
        repair_deltas: Sequence[Mapping[str, Any]],
        composition_conflicts: int,
        started: float,
        reason: str,
        task_candidate: Mapping[str, Any] | None = None,
        whole_verification: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        task_ids = {validate_worker_receipt(receipt)["task_id"] for receipt in current.values()}
        result = {
            "schema": CLOSURE_RUN_SCHEMA,
            "status": status,
            "task_id": next(iter(task_ids)) if len(task_ids) == 1 else "",
            "reason": reason,
            "unit_verifications": [dict(verifications[key]) for key in sorted(verifications)],
            "repair_deltas": [dict(value) for value in repair_deltas],
            "task_candidate": dict(task_candidate or {}),
            "whole_verification": dict(whole_verification or {}),
            "acceptance_packet": {},
            "control_capsule": {},
            "telemetry": {
                "unit_count": len(current),
                "verified_unit_count": sum(1 for value in verifications.values() if value.get("status") == "PASS"),
                "repair_count": len(repair_deltas),
                "composition_conflict_count": composition_conflicts,
                "whole_task_verifier_count": len((whole_verification or {}).get("results", [])),
                "whole_task_outcome": str((whole_verification or {}).get("status") or "NOT_RUN"),
                "wall_time_ms": max(0, int((time.monotonic() - started) * 1000)),
                "policy_tuned": False,
            },
            "claim_ceiling": "NO_ACCEPTANCE_CLAIM",
        }
        result["run_id"] = _sha256(_canonical_json(result))
        return result


__all__ = [
    "ACCEPTANCE_PACKET_SCHEMA",
    "CLAIM_CEILING",
    "CLOSURE_CAPSULE_SCHEMA",
    "CLOSURE_RUN_SCHEMA",
    "COMPOSITION_REPAIR_DELTA_SCHEMA",
    "TASK_CANDIDATE_SCHEMA",
    "UNIT_REPAIR_DELTA_SCHEMA",
    "UNIT_VERIFICATION_SCHEMA",
    "WHOLE_VERIFICATION_SCHEMA",
    "AssemblyLease",
    "ClosureError",
    "ClosureStore",
    "CompositionWorkspaceAllocator",
    "ExternalIntelligenceClosureRuntime",
    "VerifierSpec",
    "build_acceptance_packet",
    "build_closure_capsule",
    "build_composition_repair_delta",
    "build_unit_repair_delta",
    "compose_task_candidate",
    "validate_worker_receipt",
    "verify_unit_candidate",
    "verify_whole_task_candidate",
]
