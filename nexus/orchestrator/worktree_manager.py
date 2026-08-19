import fcntl
import json
import os
import re
import subprocess
from contextlib import contextmanager
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any, Callable, Dict, Mapping, Optional, Sequence

from nexus.orchestrator.collaboration_realm import CollaborationRealmVerifier
from nexus.orchestrator.task_contract import ApprovalStatus, SelfHostedTaskContract

NEXUS_SALVAGE_BOT_NAME = "Nexus Salvage Bot"
NEXUS_SALVAGE_BOT_EMAIL = "nexus-salvage-bot@nexus.local"
_DIRECT_TERMINAL_STATUSES = frozenset({
    "FINAL_BLOCK", "RETAINED_FOR_REVIEW", "REJECTED", "SUPERSEDED",
    "INTEGRATED", "INTEGRATION_FAILED", "CANCELLED", "REHEARSAL_VERIFIED",
    "DIRECT_COMPLETED", "DIRECT_RECONCILE_REQUIRED", "INTEGRATED_AND_CLEANED",
})


def _record_value(record: Any, key: str, default: Any = None) -> Any:
    if isinstance(record, Mapping):
        return record.get(key, default)
    return getattr(record, key, default)


def _record_contract(record: Any) -> Any:
    contract = _record_value(record, "contract")
    return contract if contract is not None else record


def _normalized_mutation_paths(record: Any) -> tuple[str, ...]:
    contract = _record_contract(record)
    raw = _record_value(contract, "allowed_files")
    if raw is None:
        raw = _record_value(contract, "allowed_paths")
    if not isinstance(raw, (list, tuple)) or not raw:
        raise ValueError("MUTATION_DOMAIN_INVALID: allowed paths are required")
    normalized: list[str] = []
    for item in raw:
        if not isinstance(item, str) or not item.strip():
            raise ValueError("MUTATION_DOMAIN_INVALID: path is not a string")
        path = item.strip().rstrip("/")
        if not path:
            raise ValueError("MUTATION_DOMAIN_INVALID: path is ambiguous")
        if path.startswith("/") or "\\" in path or "//" in path:
            raise ValueError("MUTATION_DOMAIN_INVALID: path is not repository-relative")
        parts = path.split("/")
        if any(part in {"", ".", ".."} for part in parts):
            raise ValueError("MUTATION_DOMAIN_INVALID: path is ambiguous")
        if path in normalized or any(
            path == other or path.startswith(other + "/") or other.startswith(path + "/")
            for other in normalized
        ):
            raise ValueError("MUTATION_DOMAIN_INVALID: overlapping allowed paths")
        normalized.append(path)
    return tuple(sorted(normalized))


def _validate_mutation_identity(record: Any) -> None:
    task_id = str(_record_value(record, "task_id") or _record_value(_record_contract(record), "task_id") or "").strip()
    if not task_id:
        raise ValueError("MUTATION_IDENTITY_INVALID: task id is missing")
    contract = _record_contract(record)
    controller = str(
        _record_value(record, "controller_worktree")
        or _record_value(contract, "controller_repo_root")
        or ""
    ).strip()
    revision = str(
        _record_value(record, "controller_revision")
        or _record_value(contract, "controller_revision")
        or ""
    ).strip()
    if not controller or not controller.startswith("/") or len(revision) != 40:
        raise ValueError("MUTATION_IDENTITY_INVALID: controller binding is incomplete")
    status = str(_record_value(record, "status") or "").upper()
    lease = _record_value(record, "lease")
    for key in ("attempt_id", "lease_id"):
        value = _record_value(record, key)
        if value is None and key == "lease_id" and isinstance(lease, Mapping):
            value = lease.get(key)
        if value is None and status in {
            "TARGET_LEASED", "WORKER_RUNNING", "WORKER_COMPLETED", "CANDIDATE_CAPTURED", "VERIFIED",
        }:
            raise ValueError(f"MUTATION_IDENTITY_INVALID: {key} is missing")
        if value is not None and not str(value).strip():
            raise ValueError(f"MUTATION_IDENTITY_INVALID: {key} is empty")
        expected = _record_value(record, f"expected_{key}")
        if expected is not None and value != expected:
            raise ValueError(f"MUTATION_IDENTITY_INVALID: {key} is stale")
    for key, value in (
        ("controller_revision", revision),
        ("controller_worktree", controller),
    ):
        expected = _record_value(record, f"expected_{key}")
        if expected is not None and value != expected:
            raise ValueError(f"MUTATION_IDENTITY_INVALID: {key} is stale")
    if _record_value(record, "competition_id") is not None:
        raise ValueError("MUTATION_IDENTITY_INVALID: forged competition identity")


def mutation_domains_conflict(left: Any, right: Any) -> bool:
    """Fail-closed conflict predicate for two isolated mutation domains."""
    _validate_mutation_identity(left)
    _validate_mutation_identity(right)
    left_contract = _record_contract(left)
    right_contract = _record_contract(right)
    left_mode = str(_record_value(left_contract, "mutation_mode") or "ISOLATED_TARGET").upper()
    right_mode = str(_record_value(right_contract, "mutation_mode") or "ISOLATED_TARGET").upper()
    if left_mode == "DIRECT_CANONICAL" or right_mode == "DIRECT_CANONICAL":
        return True
    left_controller = str(_record_value(left, "controller_worktree") or _record_value(left_contract, "controller_repo_root") or "")
    right_controller = str(_record_value(right, "controller_worktree") or _record_value(right_contract, "controller_repo_root") or "")
    left_revision = str(_record_value(left, "controller_revision") or _record_value(left_contract, "controller_revision") or "")
    right_revision = str(_record_value(right, "controller_revision") or _record_value(right_contract, "controller_revision") or "")
    if left_controller != right_controller or left_revision != right_revision:
        return True
    left_paths = _normalized_mutation_paths(left)
    right_paths = _normalized_mutation_paths(right)
    return any(
        left_path == right_path
        or left_path.startswith(right_path + "/")
        or right_path.startswith(left_path + "/")
        for left_path in left_paths
        for right_path in right_paths
    )


@dataclass(frozen=True)
class TargetWorktreeLease:
    schema: str
    lease_id: str
    task_id: str
    controller_revision: str
    target_base_revision: str
    target_worktree: str
    target_branch: str
    initial_head: str
    initial_status_sha256: str
    controller_status_sha256: str
    created_from_exact_revision: bool
    commit_created: bool
    merge_performed: bool
    target_detached: bool = False
    collaboration_provenance: Optional[dict[str, object]] = None


@dataclass(frozen=True)
class CandidateDiffReceipt:
    schema: str
    task_id: str
    contract_hash: str
    lease_id: str
    controller_revision: str
    target_base_revision: str
    target_head: str
    changed_files: list[str]
    untracked_files: list[str]
    deleted_files: list[str]
    forbidden_path_violations: list[str]
    out_of_scope_paths: list[str]
    allowed_scope_passed: bool
    tracked_diff_sha256: str
    untracked_content_hashes: Dict[str, str]
    candidate_state_hash: str
    controller_status_before_sha256: str
    controller_status_after_sha256: str
    controller_unchanged: bool
    target_status_sha256: str
    approval_status: ApprovalStatus
    human_approval_required: bool
    commit_created: bool
    merge_performed: bool
    public_claim_allowed: bool
    production_ready: bool
    collaboration_provenance: Optional[dict[str, object]] = None


@dataclass(frozen=True)
class TargetCleanupReceipt:
    schema: str
    task_id: str
    target_worktree: str
    decision: str
    blocker: Optional[str]
    performed: bool
    eligible: bool


@dataclass(frozen=True)
class WorkspaceWorktreeEntry:
    path: str
    head: str
    branch: str
    classification: str
    is_dirty: bool
    reachable_from_controller: bool
    protected_by_ref: bool
    branch_protected: bool = False
    task_id: Optional[str] = None
    blocker_reason: Optional[str] = None
    # Evidence fields are intentionally primitive and deterministic so a
    # frozen inventory can be hashed and replayed without process metadata.
    unique_commits: tuple[str, ...] = ()
    lifecycle_owner: Optional[str] = None
    process_active: bool = False
    process_evidence_unavailable: bool = False
    lock_present: bool = False
    current_review: bool = False
    evidence_unavailable: bool = False
    disposition: str = "OWNER_DECISION_REQUIRED"


@dataclass(frozen=True)
class WorkspaceInventory:
    schema: str
    controller_root: str
    controller_branch: str
    controller_head: str
    controller_dirty: bool
    legacy_root_path: str
    legacy_root_exists: bool
    legacy_root_dirty: bool
    legacy_root_status_count: int
    worktrees: list[WorkspaceWorktreeEntry]
    inventory_hash: str


@dataclass(frozen=True)
class ConvergencePlan:
    schema: str
    controller_revision: str
    inventory_hash: str
    plan_hash: str
    groups: Dict[str, list[str]]
    releasable_paths: list[str]
    blocked_paths: list[str]
    blocker_codes: list[str]
    affected_paths: list[str]
    deletion_count: int
    next_allowed_gate: str


@dataclass(frozen=True)
class ConvergenceApplyReceipt:
    schema: str
    controller_revision: str
    plan_hash: str
    applied: bool
    released_paths: list[str]
    failed_paths: list[dict[str, str]]
    next_allowed_gate: str


@dataclass(frozen=True)
class ReusableSlotLease:
    schema: str
    slot_id: str
    campaign_id: str
    slot_path: str
    task_id: Optional[str]
    status: str
    controller_revision: str
    target_base_revision: Optional[str]
    blocker: Optional[str]


def get_canonical_git_hooks_dir(base_path: Optional[Path] = None) -> Path:
    override = os.getenv("NEXUS_CANONICAL_GIT_HOOKS_DIR", "").strip()
    if override:
        hooks_dir = Path(override).expanduser().resolve()
    else:
        root = (base_path.resolve() if base_path else Path.cwd().resolve())
        if "nexus-runtime-targets" in root.parts:
            idx = root.parts.index("nexus-runtime-targets")
            hooks_root = Path(*root.parts[:idx + 1])
        elif root == Path("/Users/jameschen/Workspace/nexus"):
            hooks_root = Path("/Users/jameschen/Workspace/nexus-runtime-targets")
        else:
            hooks_root = root.parent / "nexus-runtime-targets"
        hooks_dir = hooks_root / ".nexus_git_hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)
    if not hooks_dir.is_dir():
        raise RuntimeError(f"canonical git hooks path is not a directory: {hooks_dir}")

    st = hooks_dir.stat()
    current_uid = os.getuid()
    mode = st.st_mode & 0o777
    if mode != 0o700:
        try:
            hooks_dir.chmod(0o700)
        except Exception as exc:
            raise RuntimeError(f"failed to set permissions 0700 on canonical git hooks dir: {exc}") from exc
        st = hooks_dir.stat()
        mode = st.st_mode & 0o777
    if mode != 0o700:
        raise RuntimeError(f"canonical git hooks dir permissions must be 0700, got {oct(mode)}: {hooks_dir}")
    if st.st_uid != current_uid:
        raise RuntimeError(f"canonical git hooks dir owner {st.st_uid} does not match current process uid {current_uid}: {hooks_dir}")

    return hooks_dir


class WorktreeManager:
    def __init__(
        self,
        root_dir: str = ".nexus/worktrees",
        *,
        process_checker: Optional[Callable[[Path], bool]] = None,
        create_root: bool = True,
    ):
        self.root_dir = Path(root_dir)
        if "nexus-worktrees" in self.root_dir.resolve().parts:
            raise ValueError("DISABLED_TARGET_ROOT: nexus-worktrees is retired")
        self._ensure_hooks = create_root
        if create_root:
            self.root_dir.mkdir(parents=True, exist_ok=True)
        self.process_checker = process_checker or self._path_has_process

    def _run_git(
        self,
        args: list[str],
        cwd: Optional[str | Path] = None,
        env: Optional[dict[str, str]] = None,
    ) -> str:
        git_env = os.environ.copy() if env is None else env.copy()
        git_env["GIT_CONFIG_NOSYSTEM"] = "1"
        git_env["GIT_CONFIG_GLOBAL"] = "/dev/null"
        git_args = list(args)
        if not any("core.hooksPath" in a for a in args):
            hooks_dir = get_canonical_git_hooks_dir(Path(cwd) if cwd else self.root_dir) if self._ensure_hooks else Path("/dev/null")
            git_args = ["-c", f"core.hooksPath={hooks_dir}", *args]
        result = subprocess.run(
            ["git", *git_args],
            capture_output=True,
            text=True,
            cwd=cwd,
            env=git_env,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"Git command failed: git {' '.join(args)}\n"
                f"Error: {result.stderr.strip()}"
            )
        return result.stdout.strip()

    def _run_git_bytes(
        self,
        args: list[str],
        cwd: Optional[str | Path] = None,
    ) -> bytes:
        git_env = os.environ.copy()
        git_env["GIT_CONFIG_NOSYSTEM"] = "1"
        git_env["GIT_CONFIG_GLOBAL"] = "/dev/null"
        git_args = list(args)
        if not any("core.hooksPath" in a for a in args):
            hooks_dir = get_canonical_git_hooks_dir(Path(cwd) if cwd else self.root_dir) if self._ensure_hooks else Path("/dev/null")
            git_args = ["-c", f"core.hooksPath={hooks_dir}", *args]
        result = subprocess.run(
            ["git", *git_args],
            capture_output=True,
            cwd=cwd,
            env=git_env,
        )
        if result.returncode != 0:
            stderr = result.stderr.decode("utf-8", errors="replace").strip()
            raise RuntimeError(
                f"Git command failed: git {' '.join(args)}\nError: {stderr}"
            )
        return result.stdout

    def get_worktree_path(self, task_id: str) -> Path:
        return self.root_dir / task_id

    def get_branch_name(self, task_id: str) -> str:
        return f"codex/task/{task_id}"

    def create(self, task_id: str, base_branch: str = "main") -> str:
        worktree_path = self.get_worktree_path(task_id)
        branch_name = self.get_branch_name(task_id)

        if worktree_path.exists():
            registered_paths = {
                entry["worktree"]
                for entry in self._registered_worktrees(Path.cwd())
                if "worktree" in entry
            }
            if str(worktree_path.resolve()) in registered_paths:
                return str(worktree_path.resolve())
            raise RuntimeError(
                f"existing path is not a registered worktree: {worktree_path}"
            )

        try:
            self._run_git(["rev-parse", "--verify", branch_name])
        except RuntimeError:
            self._run_git(["branch", branch_name, base_branch])

        self._run_git(["worktree", "add", str(worktree_path), branch_name])
        return str(worktree_path.resolve())

    def cleanup(self, task_id: str, force: bool = False):
        worktree_path = self.get_worktree_path(task_id)
        if not worktree_path.exists():
            return

        args = ["worktree", "remove", str(worktree_path)]
        if force:
            args.append("--force")
        self._run_git(args)

    def prune(self):
        self._run_git(["worktree", "prune"])

    @contextmanager
    def _reservation_lock(self, controller_root: Path):
        try:
            resolved_root = Path(
                self._run_git(["rev-parse", "--show-toplevel"], cwd=controller_root)
            ).resolve()
            if resolved_root != controller_root.resolve():
                raise RuntimeError("controller identity does not match Git toplevel")
            raw_common = self._run_git(["rev-parse", "--git-common-dir"], cwd=controller_root)
            common_dir = Path(raw_common)
            if not common_dir.is_absolute():
                common_dir = (controller_root / common_dir).resolve()
            else:
                common_dir = common_dir.resolve()
            if not common_dir.is_dir() or common_dir.name != ".git":
                raise RuntimeError("Git common directory is not a valid .git directory")
        except Exception as exc:
            raise RuntimeError("TARGET_ADMISSION_LOCK_UNRESOLVED") from exc
        lock_path = common_dir / "nexus-target-admission.lock"
        with lock_path.open("a+", encoding="utf-8") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    def create_lease(
        self,
        contract: SelfHostedTaskContract,
        *,
        task_states: Optional[Mapping[str, dict]] = None,
    ) -> TargetWorktreeLease:
        controller_root = Path(contract.controller_repo_root).resolve()
        with self._reservation_lock(controller_root):
            return self._create_lease_locked(contract, task_states=task_states)

    @staticmethod
    def _ownership_record_path(controller_root: Path, task_id: str) -> Path:
        raw_common = Path(
            subprocess.run(
                ["git", "-c", "core.hooksPath=/dev/null", "rev-parse", "--git-common-dir"],
                cwd=controller_root,
                check=True,
                capture_output=True,
                text=True,
                env={**os.environ, "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null"},
            ).stdout.strip()
        )
        common_dir = (controller_root / raw_common).resolve() if not raw_common.is_absolute() else raw_common.resolve()
        return common_dir / "nexus-target-ownership" / f"{sha256(task_id.encode()).hexdigest()}.json"

    def _write_target_ownership(
        self,
        contract: SelfHostedTaskContract,
        lease: TargetWorktreeLease,
    ) -> None:
        path = self._ownership_record_path(Path(contract.controller_repo_root).resolve(), contract.task_id)
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        record = {
            "schema": "nexus.target_ownership.v1",
            "task_id": contract.task_id,
            "attempt_id": lease.lease_id,
            "lease_id": lease.lease_id,
            "controller_revision": contract.controller_revision,
            "controller_worktree": str(Path(contract.controller_repo_root).resolve()),
            "expected_attempt_id": lease.lease_id,
            "expected_lease_id": lease.lease_id,
            "expected_controller_revision": contract.controller_revision,
            "expected_controller_worktree": str(Path(contract.controller_repo_root).resolve()),
            "status": "TARGET_LEASED",
            "contract": {
                "task_id": contract.task_id,
                "controller_repo_root": str(Path(contract.controller_repo_root).resolve()),
                "controller_revision": contract.controller_revision,
                "target_repo_root": lease.target_worktree,
                "target_base_revision": contract.target_base_revision,
                "allowed_files": list(contract.allowed_files),
                "mutation_mode": str(contract.mutation_mode),
            },
            "lease": lease.__dict__,
        }
        temp = path.with_suffix(f".{os.getpid()}.tmp")
        temp.write_text(json.dumps(record, sort_keys=True, separators=(",", ":")), encoding="utf-8")
        temp.chmod(0o600)
        os.replace(temp, path)

    def _read_target_ownership(
        self,
        controller_root: Path,
        entry: Mapping[str, str],
        task_id: str,
    ) -> dict[str, Any] | None:
        path = self._ownership_record_path(controller_root, task_id)
        if not path.is_file():
            return None
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise ValueError("MUTATION_IDENTITY_INVALID: ownership record is unreadable") from exc
        if not isinstance(record, dict) or record.get("schema") != "nexus.target_ownership.v1":
            raise ValueError("MUTATION_IDENTITY_INVALID: ownership record schema is invalid")
        branch = entry.get("branch", "")
        expected_branch = f"refs/heads/nexus/task/{task_id}"
        lease = record.get("lease")
        if (
            record.get("task_id") != task_id
            or record.get("controller_worktree") != str(controller_root)
            or record.get("expected_controller_worktree") != str(controller_root)
            or branch != expected_branch
            or not isinstance(lease, Mapping)
            or Path(str(lease.get("target_worktree", ""))).resolve() != Path(str(entry.get("worktree", ""))).resolve()
        ):
            raise ValueError("MUTATION_IDENTITY_INVALID: ownership record is stale")
        _validate_mutation_identity(record)
        return record

    def _create_lease_locked(
        self,
        contract: SelfHostedTaskContract,
        *,
        task_states: Optional[Mapping[str, dict]] = None,
    ) -> TargetWorktreeLease:
        controller_root, target_path, target_root = self._resolved_paths(contract)
        self._verify_target_boundary(controller_root, target_path, target_root)
        _normalized_mutation_paths(contract)
        CollaborationRealmVerifier.verify_submission(contract)
        controller_status = self._verify_controller(contract)
        resolved_target_revision = self._run_git(
            ["rev-parse", f"{contract.target_base_revision}^{{commit}}"],
            cwd=controller_root,
        )
        if resolved_target_revision != contract.target_base_revision:
            raise RuntimeError("Target base revision did not resolve to the exact contract SHA")

        target_branch = f"nexus/task/{contract.task_id}"
        target_detached = False
        target_created_this_call = False
        branch_created_this_call = False
        if self.target_conflict(contract, task_states=task_states):
            raise RuntimeError("serial Target budget exceeded: active Target limit is 1")
        if target_path.exists():
            entry = self._worktree_entry(controller_root, target_path)
            if entry is None:
                raise RuntimeError(
                    f"existing path is not a registered worktree: {target_path}"
                )
            expected_branch = f"refs/heads/{target_branch}"
            if (
                entry.get("HEAD") != contract.target_base_revision
                or entry.get("branch") != expected_branch
            ):
                raise RuntimeError("existing worktree has a different lease identity")
        else:
            if self._worktree_entry(controller_root, target_path) is not None:
                raise RuntimeError("registered worktree metadata has a different identity")
            target_root.mkdir(parents=True, exist_ok=True)
            branch_ref = f"refs/heads/{target_branch}"
            try:
                branch_head = self._run_git(["rev-parse", f"{branch_ref}^{{commit}}"], cwd=controller_root)
            except RuntimeError:
                branch_head = None
            if branch_head is None:
                add_args = ["worktree", "add", "-b", target_branch, str(target_path), contract.target_base_revision]
                branch_created_this_call = True
            else:
                if branch_head != contract.target_base_revision:
                    protected = self._run_git(
                        ["for-each-ref", "--format=%(objectname)", f"refs/nexus-candidates/{contract.task_id}/"],
                        cwd=controller_root,
                    ).splitlines()
                    protected.extend(
                        self._run_git(
                            ["for-each-ref", "--format=%(objectname)", f"refs/nexus-candidate-commits/{contract.task_id}/"],
                            cwd=controller_root,
                        ).splitlines()
                    )
                    try:
                        legacy_candidate = self._run_git(
                            ["rev-parse", f"refs/nexus-candidates/{contract.task_id}^{{commit}}"],
                            cwd=controller_root,
                        )
                    except RuntimeError:
                        legacy_candidate = None
                    if legacy_candidate:
                        protected.append(legacy_candidate)
                    salvage_refs = self._run_git(
                        [
                            "for-each-ref",
                            "--format=%(refname)",
                            f"refs/nexus-salvage/worktree/{contract.task_id}-*",
                        ],
                        cwd=controller_root,
                    ).splitlines()
                    for salvage_ref in salvage_refs:
                        try:
                            salvage_parents = self._run_git(
                                ["rev-list", "--parents", "-n", "1", salvage_ref],
                                cwd=controller_root,
                            ).split()
                        except RuntimeError:
                            continue
                        if len(salvage_parents) == 2:
                            protected.append(salvage_parents[1])
                    if branch_head not in protected:
                        raise RuntimeError("existing task branch candidate lacks durable protection")
                    target_detached = True
                    add_args = ["worktree", "add", "--detach", str(target_path), contract.target_base_revision]
                else:
                    add_args = ["worktree", "add", str(target_path), target_branch]
            self._run_git(add_args, cwd=controller_root)
            target_created_this_call = True

        initial_head = self._run_git(["rev-parse", "HEAD"], cwd=target_path)
        actual_branch = self._run_git(["branch", "--show-current"], cwd=target_path)
        initial_status = self._status_bytes(target_path)
        if initial_head != contract.target_base_revision:
            raise RuntimeError("Target worktree was not created from the exact revision")
        if actual_branch != target_branch and not (target_detached and not actual_branch):
            raise RuntimeError("Target worktree branch does not match the lease identity")
        if initial_status:
            raise RuntimeError("Target worktree must be clean")
        try:
            collaboration_provenance = CollaborationRealmVerifier.verify_target(
                contract, target_path, initial_head,
            )
        except Exception as verification_error:
            if target_created_this_call:
                rollback_failures: list[str] = []
                try:
                    self._run_git(
                        ["worktree", "remove", "--force", str(target_path)],
                        cwd=controller_root,
                    )
                except RuntimeError as exc:
                    rollback_failures.append(f"worktree:{exc}")
                if branch_created_this_call:
                    try:
                        self._run_git(
                            ["branch", "-D", target_branch],
                            cwd=controller_root,
                        )
                    except RuntimeError as exc:
                        rollback_failures.append(f"branch:{exc}")
                if rollback_failures:
                    detail = ";".join(rollback_failures)
                    raise RuntimeError(
                        f"COLLABORATION_REALM_TARGET_ROLLBACK_FAILED:{detail}"
                    ) from verification_error
            raise

        lease = TargetWorktreeLease(
            schema="nexus.target_worktree_lease.v1",
            lease_id=self._lease_id(contract, target_path, target_branch),
            task_id=contract.task_id,
            controller_revision=contract.controller_revision,
            target_base_revision=contract.target_base_revision,
            target_worktree=str(target_path),
            target_branch=target_branch,
            initial_head=initial_head,
            initial_status_sha256=sha256(initial_status).hexdigest(),
            controller_status_sha256=sha256(controller_status).hexdigest(),
            created_from_exact_revision=True,
            commit_created=False,
            merge_performed=False,
            target_detached=target_detached,
            collaboration_provenance=collaboration_provenance or None,
        )
        self._write_target_ownership(contract, lease)
        return lease

    def target_conflict(
        self,
        contract: SelfHostedTaskContract,
        *,
        task_states: Optional[Mapping[str, dict]] = None,
    ) -> bool:
        """Return whether an existing active Target overlaps this contract."""
        controller_root, target_path, _ = self._resolved_paths(contract)
        active = self._active_target_worktrees(
            controller_root, target_path, task_states=task_states,
        )
        if not active:
            return False
        states = task_states or {}
        for entry in active:
            branch = entry.get("branch", "")
            task_id = ""
            if branch.startswith("refs/heads/nexus/task/"):
                task_id = branch.removeprefix("refs/heads/nexus/task/")
            elif branch.startswith("nexus/task/"):
                task_id = branch.removeprefix("nexus/task/")
            existing = states.get(task_id)
            if not isinstance(existing, Mapping):
                existing = self._read_target_ownership(controller_root, entry, task_id)
            if not isinstance(existing, Mapping):
                return True
            if mutation_domains_conflict(existing, contract):
                return True
        return False

    def protect_candidate(
        self,
        contract: SelfHostedTaskContract,
        lease: TargetWorktreeLease,
        candidate_commit: str,
    ) -> str:
        self.validate_lease_identity(contract, lease)
        target = Path(lease.target_worktree).resolve()
        actual = self._run_git(["rev-parse", "HEAD"], cwd=target)
        if actual != candidate_commit:
            raise RuntimeError("candidate commit does not match Target HEAD")
        legacy_ref = f"refs/nexus-candidates/{contract.task_id}"
        try:
            self._run_git(["rev-parse", f"{legacy_ref}^{{commit}}"], cwd=contract.controller_repo_root)
            candidate_ref = f"refs/nexus-candidate-commits/{contract.task_id}/{candidate_commit}"
        except RuntimeError:
            candidate_ref = f"refs/nexus-candidates/{contract.task_id}/{candidate_commit}"
        self._run_git(["update-ref", candidate_ref, candidate_commit], cwd=contract.controller_repo_root)
        if self._run_git(["rev-parse", candidate_ref], cwd=contract.controller_repo_root) != candidate_commit:
            raise RuntimeError("candidate durable ref verification failed")
        expected_tree = self._run_git(["rev-parse", f"{candidate_commit}^{{tree}}"], cwd=contract.controller_repo_root)
        ref_tree = self._run_git(["rev-parse", f"{candidate_ref}^{{tree}}"], cwd=contract.controller_repo_root)
        if ref_tree != expected_tree:
            raise RuntimeError("candidate ref tree verification failed")
        return candidate_ref

    @staticmethod
    def salvage_ref_for(task_id: str, attempt_id: str) -> str:
        return f"refs/nexus-salvage/worktree/{task_id}-{attempt_id}"

    def protect_salvage_head(
        self,
        contract: SelfHostedTaskContract,
        lease: TargetWorktreeLease,
        attempt_id: str,
    ) -> dict[str, str | bool]:
        """Protect an already-committed non-candidate Target HEAD for cleanup."""
        self.validate_lease_identity(contract, lease)
        target = Path(lease.target_worktree).resolve()
        controller = Path(contract.controller_repo_root).resolve()
        if target == controller:
            raise RuntimeError("Target is controller")
        if self._worktree_entry(controller, target) is None:
            raise RuntimeError("salvage requires a registered Target worktree")
        if self.process_checker(target):
            raise RuntimeError("active process uses Target")
        if self._status_bytes(target):
            raise RuntimeError("dirty Target requires a salvage snapshot commit")
        salvage_commit = self._run_git(["rev-parse", "HEAD"], cwd=target)
        salvage_ref = self.salvage_ref_for(contract.task_id, attempt_id)
        try:
            existing = self._run_git(["rev-parse", f"{salvage_ref}^{{commit}}"], cwd=controller)
        except RuntimeError:
            existing = None
        if existing is not None and existing != salvage_commit:
            raise RuntimeError(f"salvage ref already exists with different commit: {salvage_ref}")
        if existing is None:
            self._run_git(["update-ref", salvage_ref, salvage_commit, ""], cwd=controller)
        if self._run_git(["rev-parse", salvage_ref], cwd=controller) != salvage_commit:
            raise RuntimeError("salvage durable ref verification failed")
        return {
            "salvage_commit_sha": salvage_commit,
            "salvage_ref": salvage_ref,
            "salvage_only": True,
            "promotion_eligible": False,
        }

    def create_salvage_snapshot(
        self,
        contract: SelfHostedTaskContract,
        lease: TargetWorktreeLease,
        attempt_id: str,
    ) -> dict[str, str | bool]:
        """Commit and protect dirty Target state without entering candidate flow."""
        self.validate_lease_identity(contract, lease)
        target = Path(lease.target_worktree).resolve()
        controller = Path(contract.controller_repo_root).resolve()
        if target == controller:
            raise RuntimeError("Target is controller")
        if self._worktree_entry(controller, target) is None:
            raise RuntimeError("salvage requires a registered Target worktree")
        if self.process_checker(target):
            raise RuntimeError("active process uses Target")
        if not self._status_bytes(target):
            raise RuntimeError("Target has no dirty state to salvage")

        salvage_ref = self.salvage_ref_for(contract.task_id, attempt_id)
        try:
            existing = self._run_git(
                ["rev-parse", f"{salvage_ref}^{{commit}}"], cwd=controller
            )
        except RuntimeError:
            existing = None
        if existing is not None:
            raise RuntimeError(f"salvage ref already exists: {salvage_ref}")

        self._run_git(["add", "--all"], cwd=target)
        message = f"Nexus Salvage Bot: salvage-only snapshot {contract.task_id}/{attempt_id}"
        self._run_git(
            [
                "-c", f"user.name={NEXUS_SALVAGE_BOT_NAME}",
                "-c", f"user.email={NEXUS_SALVAGE_BOT_EMAIL}",
                "commit", "-m", message,
            ],
            cwd=target,
        )
        salvage_commit = self._run_git(["rev-parse", "HEAD"], cwd=target)
        if self._status_bytes(target):
            raise RuntimeError("salvage commit did not capture the complete Target state")
        self._run_git(
            ["update-ref", salvage_ref, salvage_commit, ""],
            cwd=controller,
        )
        if self._run_git(["rev-parse", salvage_ref], cwd=controller) != salvage_commit:
            raise RuntimeError("salvage durable ref verification failed")
        return {
            "salvage_commit_sha": salvage_commit,
            "salvage_ref": salvage_ref,
            "salvage_only": True,
            "promotion_eligible": False,
        }

    def cleanup_terminal_target(
        self,
        contract: SelfHostedTaskContract,
        lease: TargetWorktreeLease,
        *,
        candidate_commit: Optional[str] = None,
        candidate_ref: Optional[str] = None,
        salvage_commit: Optional[str] = None,
        salvage_ref: Optional[str] = None,
        dry_run: bool = False,
    ) -> TargetCleanupReceipt:
        self.validate_lease_identity(contract, lease)
        target = Path(lease.target_worktree).resolve()
        controller = Path(contract.controller_repo_root).resolve()
        if target == controller:
            return self._cleanup_receipt(contract, lease, "BLOCKED_BY_UNSAVED_CHANGES", "Target is controller", False, False)
        if (candidate_commit is not None or candidate_ref is not None) and (
            salvage_commit is not None or salvage_ref is not None
        ):
            return self._cleanup_receipt(
                contract, lease, "BLOCKED_BY_MISSING_REF",
                "candidate and salvage durable bindings cannot be combined", False, False,
            )
        durable_commit = candidate_commit or salvage_commit
        durable_ref = candidate_ref or salvage_ref
        missing_ref_blocker = (
            "candidate ref is missing or mismatched"
            if candidate_commit is not None or candidate_ref is not None
            else "salvage ref is missing or mismatched"
        )
        entry = self._worktree_entry(controller, target)
        if not target.exists() and entry is None:
            return self._cleanup_receipt(contract, lease, "ALREADY_REMOVED", None, False, True)
        if entry is None:
            if self.process_checker(target):
                return self._cleanup_receipt(contract, lease, "BLOCKED_BY_PROCESS", "active process uses Target", False, False)
            if not target.is_dir() or target.is_symlink():
                return self._cleanup_receipt(contract, lease, "BLOCKED_BY_UNSAVED_CHANGES", "unregistered Target is not an empty directory", False, False)
            try:
                is_empty = not any(target.iterdir())
            except OSError as exc:
                return self._cleanup_receipt(contract, lease, "BLOCKED_BY_UNSAVED_CHANGES", str(exc), False, False)
            if not is_empty:
                return self._cleanup_receipt(contract, lease, "BLOCKED_BY_UNSAVED_CHANGES", "unregistered Target is not an empty directory", False, False)
            if durable_commit:
                if not durable_ref:
                    return self._cleanup_receipt(contract, lease, "BLOCKED_BY_MISSING_REF", missing_ref_blocker, False, False)
                try:
                    protected = self._run_git(["rev-parse", f"{durable_ref}^{{commit}}"], cwd=controller)
                except RuntimeError:
                    protected = ""
                if protected != durable_commit:
                    return self._cleanup_receipt(contract, lease, "BLOCKED_BY_MISSING_REF", missing_ref_blocker, False, False)
            if not dry_run:
                target.rmdir()
            return self._cleanup_receipt(contract, lease, "REMOVED", None, not dry_run, True)
        if self.process_checker(target):
            return self._cleanup_receipt(contract, lease, "BLOCKED_BY_PROCESS", "active process uses Target", False, False)
        status = self._status_bytes(target)
        if status:
            return self._cleanup_receipt(contract, lease, "BLOCKED_BY_UNSAVED_CHANGES", "dirty target has no durable snapshot", False, False)
        head = self._run_git(["rev-parse", "HEAD"], cwd=target)
        if durable_commit:
            if head != durable_commit or not durable_ref:
                return self._cleanup_receipt(contract, lease, "BLOCKED_BY_MISSING_REF", missing_ref_blocker, False, False)
            try:
                protected = self._run_git(["rev-parse", f"{durable_ref}^{{commit}}"], cwd=controller)
            except RuntimeError:
                protected = ""
            if protected != durable_commit:
                return self._cleanup_receipt(contract, lease, "BLOCKED_BY_MISSING_REF", missing_ref_blocker, False, False)
        elif head != lease.initial_head:
            return self._cleanup_receipt(contract, lease, "BLOCKED_BY_UNSAVED_CHANGES", "Target HEAD changed without durable snapshot", False, False)
        if not dry_run:
            self._run_git(["worktree", "remove", "--", str(target)], cwd=controller)
            self._run_git(["worktree", "prune"], cwd=controller)
        return self._cleanup_receipt(contract, lease, "REMOVED", None, not dry_run, True)

    def restore_task_branch_for_retry(
        self,
        contract: SelfHostedTaskContract,
        lease: TargetWorktreeLease,
        salvage_commit: str,
        salvage_ref: str,
    ) -> dict[str, str | bool]:
        """
        Restore the task branch to lease.initial_head after durable salvage.

        Idempotent: returns ALREADY_RESTORED when branch is already at
        lease.initial_head with valid salvage evidence.

        Safety check fail-closed conditions (ALL must hold):
          1. Branch follows the nexus/task/<task_id> naming convention.
          2. Branch currently points to salvage_commit OR lease.initial_head.
          3. salvage_ref resolves to salvage_commit.
          4. salvage_commit has exactly 1 parent.
          5. The single parent equals lease.initial_head.
          6. Target is no longer a registered worktree.
          7. No active candidate/promotion binding exists.
          8. Branch update uses compare-and-swap (git update-ref with old-value).

        Returns:
            {
                "decision": "RESTORED" | "ALREADY_RESTORED",
                "branch_ref": ...,
                "restored_to": lease.initial_head,
                "salvage_commit": ...,
                "salvage_ref": ...,
            }
        Raises RuntimeError with diagnostics on any violation (fail-closed).
        """
        self.validate_lease_identity(contract, lease)
        controller = Path(contract.controller_repo_root).resolve()
        task_id = contract.task_id
        target_branch = f"nexus/task/{task_id}"
        branch_ref = f"refs/heads/{target_branch}"
        initial_head = lease.initial_head

        result_base: dict[str, str | bool] = {
            "branch_ref": branch_ref,
            "restored_to": initial_head,
            "salvage_commit": salvage_commit,
            "salvage_ref": salvage_ref,
        }

        # Check 1: Branch is a known task branch
        if not target_branch.startswith("nexus/task/"):
            raise RuntimeError(
                f"Safety check 1 failed: branch '{target_branch}' "
                f"does not follow nexus/task/<task_id> convention"
            )

        # Check 2: Branch currently points to salvage_commit or initial_head
        try:
            current_branch_sha = self._run_git(
                ["rev-parse", f"{branch_ref}^{{commit}}"], cwd=controller
            )
        except RuntimeError as e:
            raise RuntimeError(
                f"Safety check 2 failed: cannot resolve task branch "
                f"'{branch_ref}': {e}"
            )

        already_restored = current_branch_sha == initial_head

        if not already_restored and current_branch_sha != salvage_commit:
            raise RuntimeError(
                f"Safety check 2 failed: task branch '{branch_ref}' points to "
                f"{current_branch_sha}, expected salvage commit {salvage_commit} "
                f"or initial_head {initial_head}"
            )

        # Check 3: Salvage ref resolves to salvage_commit
        try:
            current_salvage_sha = self._run_git(
                ["rev-parse", f"{salvage_ref}^{{commit}}"], cwd=controller
            )
        except RuntimeError as e:
            raise RuntimeError(
                f"Safety check 3 failed: salvage ref '{salvage_ref}' not found: {e}"
            )
        if current_salvage_sha != salvage_commit:
            raise RuntimeError(
                f"Safety check 3 failed: salvage ref '{salvage_ref}' points to "
                f"{current_salvage_sha}, expected {salvage_commit}"
            )

        # Check 4: Salvage commit has exactly 1 parent
        try:
            parent_info = self._run_git(
                ["rev-list", "--parents", "-n", "1", salvage_commit], cwd=controller
            )
        except RuntimeError as e:
            raise RuntimeError(
                f"Safety check 4 failed: cannot inspect parents of "
                f"{salvage_commit}: {e}"
            )
        parts = parent_info.split()
        if len(parts) == 1:
            raise RuntimeError(
                f"Safety check 4 failed: salvage commit {salvage_commit} "
                f"is a root commit (0 parents), expected exactly 1"
            )
        if len(parts) != 2:
            raise RuntimeError(
                f"Safety check 4 failed: salvage commit {salvage_commit} "
                f"has {len(parts) - 1} parent(s), expected exactly 1"
            )

        # Check 5: Parent equals initial_head
        actual_parent = parts[1]
        if actual_parent != initial_head:
            raise RuntimeError(
                f"Safety check 5 failed: salvage commit parent {actual_parent} "
                f"does not match lease.initial_head {initial_head}"
            )

        # Check 6: Target is no longer a registered worktree
        target_path = Path(contract.target_repo_root).resolve()
        entry = self._worktree_entry(controller, target_path)
        if entry is not None:
            raise RuntimeError(
                f"Safety check 6 failed: Target '{target_path}' is still "
                f"a registered worktree; must be cleaned up first"
            )

        # Check 7: No active candidate/promotion binding
        candidate_refs = self._run_git(
            ["for-each-ref", "--format=%(refname)",
             f"refs/nexus-candidates/{task_id}/"],
            cwd=controller,
        ).splitlines()
        candidate_commit_refs = self._run_git(
            ["for-each-ref", "--format=%(refname)",
             f"refs/nexus-candidate-commits/{task_id}/"],
            cwd=controller,
        ).splitlines()
        try:
            self._run_git(
                ["rev-parse", f"refs/nexus-candidates/{task_id}^{{commit}}"],
                cwd=controller,
            )
            has_legacy = True
        except RuntimeError:
            has_legacy = False
        if candidate_refs or candidate_commit_refs or has_legacy:
            violations = []
            if candidate_refs:
                violations.append(f"nexus-candidates/{task_id}/ ({len(candidate_refs)} ref(s))")
            if candidate_commit_refs:
                violations.append(f"nexus-candidate-commits/{task_id}/ ({len(candidate_commit_refs)} ref(s))")
            if has_legacy:
                violations.append(f"nexus-candidates/{task_id} (legacy)")
            raise RuntimeError(
                f"Safety check 7 failed: active candidate binding(s) exist "
                f"for task {task_id}: {'; '.join(violations)}"
            )

        # Idempotent: if branch is already at initial_head, return ALREADY_RESTORED
        if already_restored:
            verified = self._run_git(
                ["rev-parse", f"{branch_ref}^{{commit}}"], cwd=controller
            )
            if verified != initial_head:
                raise RuntimeError(
                    f"Post-ALREADY_RESTORED verification failed: branch "
                    f"'{branch_ref}' resolved to {verified}, expected {initial_head}"
                )
            return {**result_base, "decision": "ALREADY_RESTORED"}

        # Check 8: Atomic compare-and-swap branch update
        try:
            self._run_git(
                ["update-ref", branch_ref, initial_head, salvage_commit],
                cwd=controller,
            )
        except RuntimeError as e:
            raise RuntimeError(
                f"Safety check 8 failed (CAS): branch '{branch_ref}' was "
                f"concurrently modified away from {salvage_commit}: {e}"
            )

        # Post-restoration verification
        verified = self._run_git(
            ["rev-parse", f"{branch_ref}^{{commit}}"], cwd=controller
        )
        if verified != initial_head:
            raise RuntimeError(
                f"Post-restoration verification failed: branch '{branch_ref}' "
                f"resolved to {verified}, expected {initial_head}"
            )

        return {**result_base, "decision": "RESTORED"}

    @staticmethod
    def _cleanup_receipt(contract, lease, decision, blocker, performed, eligible):
        return TargetCleanupReceipt(
            schema="nexus.target_cleanup_receipt.v1",
            task_id=contract.task_id,
            target_worktree=lease.target_worktree,
            decision=decision,
            blocker=blocker,
            performed=performed,
            eligible=eligible,
        )

    @staticmethod
    def _path_has_process(path: Path) -> bool:
        result = subprocess.run(
            ["lsof", "+D", str(path)], capture_output=True, text=True, check=False
        )
        if result.returncode == 0:
            return bool(result.stdout.strip())
        if result.returncode == 1 and not result.stderr.strip():
            return False
        raise RuntimeError(f"process probe unavailable for {path}: {result.stderr.strip() or result.returncode}")

    def capture_candidate(
        self,
        contract: SelfHostedTaskContract,
        lease: TargetWorktreeLease,
    ) -> CandidateDiffReceipt:
        self.validate_lease_identity(contract, lease)
        controller_root = Path(contract.controller_repo_root).resolve()
        target_path = Path(lease.target_worktree).resolve()
        controller_status = self._status_bytes(controller_root)
        controller_head = self._run_git(["rev-parse", "HEAD"], cwd=controller_root)
        controller_status_after = sha256(controller_status).hexdigest()
        controller_unchanged = (
            controller_head == contract.controller_revision
            and controller_status_after == lease.controller_status_sha256
        )
        if not controller_unchanged:
            raise RuntimeError("Controller changed after the target lease was created")

        target_head = self._run_git(["rev-parse", "HEAD"], cwd=target_path)
        collaboration_provenance = CollaborationRealmVerifier.verify_target(
            contract, target_path, target_head,
        )
        committed_changed: list[str] = []
        committed_deleted: list[str] = []
        if target_head != lease.initial_head:
            try:
                self._run_git(
                    ["merge-base", "--is-ancestor", lease.initial_head, target_head],
                    cwd=target_path,
                )
            except RuntimeError as exc:
                raise RuntimeError(
                    "Target HEAD must descend from the leased initial_head"
                ) from exc
            committed_changed, committed_deleted = self._parse_commit_diff(
                self._run_git(
                    ["diff", "--name-status", lease.initial_head, target_head],
                    cwd=target_path,
                )
            )
        target_status = self._status_bytes(target_path)
        working_changed, untracked_files, working_deleted = self._parse_status(target_status)
        changed_files = sorted(set(committed_changed) | set(working_changed))
        deleted_files = sorted(set(committed_deleted) | set(working_deleted))
        committed_diff = self._run_git_bytes(
            ["diff", "--binary", "--no-ext-diff", f"{lease.initial_head}..{target_head}", "--"],
            cwd=target_path,
        ) if target_head != lease.initial_head else b""
        working_diff = self._run_git_bytes(
            ["diff", "--binary", "--no-ext-diff", "HEAD", "--"],
            cwd=target_path,
        )
        tracked_diff_sha256 = sha256(committed_diff + b"\0" + working_diff).hexdigest()
        untracked_content_hashes = {
            path: self._hash_untracked_path(target_path / path)
            for path in untracked_files
        }
        candidate_paths = sorted(
            set(changed_files) | set(untracked_files) | set(deleted_files)
        )
        forbidden_path_violations = sorted(
            path
            for path in candidate_paths
            if self._matches_any(path, contract.forbidden_files)
        )
        out_of_scope_paths = sorted(
            path
            for path in candidate_paths
            if path in forbidden_path_violations
            or not self._matches_any(path, contract.allowed_files)
        )
        candidate_state_hash = self._candidate_state_hash(
            target_base_revision=contract.target_base_revision,
            target_head=target_head,
            status_bytes=target_status,
            tracked_diff_sha256=tracked_diff_sha256,
            untracked_content_hashes=untracked_content_hashes,
            collaboration_binding_hash=(
                contract.collaboration_realm.binding_hash
                if getattr(contract, "collaboration_realm", None) is not None
                else ""
            ),
        )

        return CandidateDiffReceipt(
            schema="nexus.candidate_diff_receipt.v1",
            task_id=contract.task_id,
            contract_hash=contract.contract_hash,
            lease_id=lease.lease_id,
            controller_revision=contract.controller_revision,
            target_base_revision=contract.target_base_revision,
            target_head=target_head,
            changed_files=changed_files,
            untracked_files=untracked_files,
            deleted_files=deleted_files,
            forbidden_path_violations=forbidden_path_violations,
            out_of_scope_paths=out_of_scope_paths,
            allowed_scope_passed=not out_of_scope_paths,
            tracked_diff_sha256=tracked_diff_sha256,
            untracked_content_hashes=untracked_content_hashes,
            candidate_state_hash=candidate_state_hash,
            controller_status_before_sha256=lease.controller_status_sha256,
            controller_status_after_sha256=controller_status_after,
            controller_unchanged=controller_unchanged,
            target_status_sha256=sha256(target_status).hexdigest(),
            approval_status=ApprovalStatus.PENDING,
            human_approval_required=contract.human_approval_required,
            commit_created=False,
            merge_performed=False,
            public_claim_allowed=False,
            production_ready=False,
            collaboration_provenance=collaboration_provenance or None,
        )

    def validate_lease_identity(
        self,
        contract: SelfHostedTaskContract,
        lease: TargetWorktreeLease,
    ) -> None:
        target_path = Path(contract.target_repo_root).resolve()
        target_branch = f"nexus/task/{contract.task_id}"
        expected_lease_id = self._lease_id(contract, target_path, target_branch)
        if (
            lease.task_id != contract.task_id
            or lease.controller_revision != contract.controller_revision
            or lease.target_base_revision != contract.target_base_revision
            or Path(lease.target_worktree).resolve() != target_path
            or lease.target_branch != target_branch
            or lease.lease_id != expected_lease_id
        ):
            raise RuntimeError("contract and lease identity mismatch")
        expected_collaboration = CollaborationRealmVerifier.verify_submission(contract)
        if expected_collaboration:
            actual = lease.collaboration_provenance or {}
            immutable_fields = (
                "binding_hash", "repository_id", "canonical_remote", "base_branch",
                "base_sha", "collaboration_root", "execution_root",
            )
            if any(actual.get(field) != expected_collaboration.get(field) for field in immutable_fields):
                raise RuntimeError("contract and collaboration lease identity mismatch")
            if actual.get("sanitized_ancestry_verified") is not True:
                raise RuntimeError("collaboration lease lacks sanitized ancestry proof")
        elif lease.collaboration_provenance is not None:
            raise RuntimeError("local lease unexpectedly contains collaboration provenance")

    def verify_controller_unchanged(
        self,
        contract: SelfHostedTaskContract,
        expected_status_sha256: Optional[str] = None,
    ) -> str:
        controller_root = Path(contract.controller_repo_root).resolve()
        head = self._run_git(["rev-parse", "HEAD"], cwd=controller_root)
        if head != contract.controller_revision:
            raise RuntimeError("Controller revision drift")
        status = self._status_bytes(controller_root)
        if status:
            raise RuntimeError("Controller must remain clean")
        status_sha256 = sha256(status).hexdigest()
        if (
            expected_status_sha256 is not None
            and status_sha256 != expected_status_sha256
        ):
            raise RuntimeError("Controller status drift")
        return status_sha256

    def _verify_controller(self, contract: SelfHostedTaskContract) -> bytes:
        controller_root = Path(contract.controller_repo_root).resolve()
        if not re.fullmatch(r"[0-9a-f]{40}", contract.controller_revision):
            raise RuntimeError("Controller revision must be a lowercase 40-hex SHA")
        head = self._run_git(["rev-parse", "HEAD"], cwd=controller_root)
        if head != contract.controller_revision:
            raise RuntimeError("Controller revision does not match the contract")
        status = self._status_bytes(controller_root)
        if status:
            raise RuntimeError("Controller must be clean")
        return status

    @staticmethod
    def _resolved_paths(
        contract: SelfHostedTaskContract,
    ) -> tuple[Path, Path, Path]:
        return (
            Path(contract.controller_repo_root).resolve(),
            Path(contract.target_repo_root).resolve(),
            Path(contract.target_worktree_root).resolve(),
        )

    @staticmethod
    def _verify_target_boundary(
        controller_root: Path,
        target_path: Path,
        target_root: Path,
    ) -> None:
        if target_path == target_root or target_root not in target_path.parents:
            raise RuntimeError("Target worktree must be under target_worktree_root")
        if target_path == controller_root or controller_root in target_path.parents:
            raise RuntimeError("Controller and Target must be physically separate")

    def _status_bytes(self, repo_root: Path) -> bytes:
        return self._run_git_bytes(
            ["status", "--porcelain=v1", "-z", "--untracked-files=all"],
            cwd=repo_root,
        )

    def _registered_worktrees(self, controller_root: Path) -> list[dict[str, str]]:
        output = self._run_git(
            ["worktree", "list", "--porcelain"],
            cwd=controller_root,
        )
        entries: list[dict[str, str]] = []
        current: dict[str, str] = {}
        for line in output.splitlines():
            if not line:
                if current:
                    entries.append(current)
                    current = {}
                continue
            key, _, value = line.partition(" ")
            current[key] = value
        if current:
            entries.append(current)
        for entry in entries:
            if "worktree" in entry:
                entry["worktree"] = str(Path(entry["worktree"]).resolve())
        return entries

    def _active_target_worktrees(
        self,
        controller_root: Path,
        target_path: Path,
        *,
        task_states: Optional[Mapping[str, dict]] = None,
    ) -> list[dict[str, str]]:
        """Return only Targets that consume the serial execution budget.

        Retained/terminal worktrees are evidence and remain untouched.  A
        durable task owner (``nexus/task/<id>``) is active unless its supplied
        lifecycle state is terminal or explicitly retained for review.  Live
        process/lock evidence always wins; unavailable process evidence fails
        closed rather than allowing a concurrent lease.
        """
        terminal = _DIRECT_TERMINAL_STATUSES
        review = {"RETAINED_FOR_REVIEW", "FINAL_BLOCK"}
        states = task_states or {}
        active: list[dict[str, str]] = []
        root = self.root_dir.resolve()
        controller = controller_root.resolve()
        requested = target_path.resolve()
        for entry in self._registered_worktrees(controller):
            raw_path = entry.get("worktree")
            if not raw_path:
                continue
            path = Path(raw_path).resolve()
            if path == controller or path == requested or root not in path.parents:
                continue

            # Git's ``locked`` marker is an explicit owner protection.
            if "locked" in entry:
                active.append(entry)
                continue
            try:
                process_state = self.process_checker(path)
            except Exception:
                process_state = None
            if process_state is None or bool(process_state):
                active.append(entry)
                continue

            branch = entry.get("branch", "")
            task_id: Optional[str] = None
            if branch.startswith("refs/heads/nexus/task/"):
                task_id = branch.removeprefix("refs/heads/nexus/task/")
            elif branch.startswith("nexus/task/"):
                task_id = branch.removeprefix("nexus/task/")
            state = states.get(task_id) if task_id else None
            status = str(state.get("status")) if state else None
            if task_id and (status not in terminal and status not in review):
                # A managed nexus/task branch without durable lifecycle
                # ownership is intentionally active; its disposition cannot
                # be proven passive.
                active.append(entry)
        return active

    def _worktree_entry(
        self,
        controller_root: Path,
        target_path: Path,
    ) -> Optional[dict[str, str]]:
        resolved_target = str(target_path.resolve())
        for entry in self._registered_worktrees(controller_root):
            if entry.get("worktree") == resolved_target:
                return entry
        return None

    @staticmethod
    def _lease_id(
        contract: SelfHostedTaskContract,
        target_path: Path,
        target_branch: str,
    ) -> str:
        payload = {
            "task_id": contract.task_id,
            "controller_revision": contract.controller_revision,
            "target_base_revision": contract.target_base_revision,
            "target_path": target_path.as_posix(),
            "target_branch": target_branch,
        }
        collaboration_realm = getattr(contract, "collaboration_realm", None)
        if collaboration_realm is not None:
            payload["collaboration_binding_hash"] = collaboration_realm.binding_hash
        canonical = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return sha256(canonical).hexdigest()

    @staticmethod
    def _parse_status(status_bytes: bytes) -> tuple[list[str], list[str], list[str]]:
        changed_files: set[str] = set()
        untracked_files: set[str] = set()
        deleted_files: set[str] = set()
        records = status_bytes.split(b"\0")
        index = 0
        while index < len(records):
            record = records[index]
            index += 1
            if not record:
                continue
            text = record.decode("utf-8", errors="surrogateescape")
            status_code = text[:2]
            path = text[3:]
            if status_code == "??":
                untracked_files.add(path)
                continue
            if "R" in status_code or "C" in status_code:
                index += 1
            if "D" in status_code:
                deleted_files.add(path)
            else:
                changed_files.add(path)
        return (
            sorted(changed_files),
            sorted(untracked_files),
            sorted(deleted_files),
        )

    @staticmethod
    def _parse_commit_diff(diff_text: str) -> tuple[list[str], list[str]]:
        """Return changed and deleted paths introduced by committed Target work."""
        changed_files: set[str] = set()
        deleted_files: set[str] = set()
        for line in diff_text.splitlines():
            if not line.strip():
                continue
            fields = line.split("\t")
            status = fields[0]
            path = fields[-1]
            if status.startswith("D"):
                deleted_files.add(path)
            elif status.startswith(("R", "C")) and len(fields) > 2:
                changed_files.add(fields[-1])
                changed_files.add(fields[-2])
            else:
                changed_files.add(path)
        return sorted(changed_files), sorted(deleted_files)

    @staticmethod
    def _hash_untracked_path(path: Path) -> str:
        if path.is_symlink():
            content = os.readlink(path).encode("utf-8", errors="surrogateescape")
        else:
            content = path.read_bytes()
        return sha256(content).hexdigest()

    @staticmethod
    def _matches_any(path: str, patterns: list[str]) -> bool:
        for pattern in patterns:
            if pattern.endswith("/"):
                if path.startswith(pattern):
                    return True
            elif path == pattern:
                return True
        return False

    @staticmethod
    def _candidate_state_hash(
        *,
        target_base_revision: str,
        target_head: str,
        status_bytes: bytes,
        tracked_diff_sha256: str,
        untracked_content_hashes: Dict[str, str],
        collaboration_binding_hash: str = "",
    ) -> str:
        digest = sha256()
        components = [
            target_base_revision.encode("ascii"),
            target_head.encode("ascii"),
            status_bytes,
            tracked_diff_sha256.encode("ascii"),
            json.dumps(
                sorted(untracked_content_hashes.items()),
                separators=(",", ":"),
            ).encode("utf-8"),
        ]
        if collaboration_binding_hash:
            components.append(collaboration_binding_hash.encode("ascii"))
        for component in components:
            digest.update(len(component).to_bytes(8, "big"))
            digest.update(component)
        return digest.hexdigest()

    def get_workspace_inventory(
        self,
        controller_root: Optional[str | Path] = None,
        task_states: Optional[Dict[str, dict]] = None,
    ) -> WorkspaceInventory:
        c_root = Path(controller_root or Path.cwd()).resolve()
        c_head = self._run_git(["rev-parse", "HEAD"], cwd=c_root)
        try:
            c_branch = self._run_git(["branch", "--show-current"], cwd=c_root)
            if not c_branch:
                c_branch = self._run_git(["rev-parse", "--abbrev-ref", "HEAD"], cwd=c_root)
        except Exception:
            c_branch = "HEAD"
        c_dirty_bytes = self._status_bytes(c_root)
        c_dirty = bool(c_dirty_bytes)

        legacy_path = Path("/Users/jameschen/Workspace/nexus")
        legacy_exists = legacy_path.exists()
        legacy_dirty = False
        legacy_status_count = 0
        if legacy_exists and legacy_path.is_dir():
            try:
                l_bytes = self._status_bytes(legacy_path)
                legacy_dirty = bool(l_bytes)
                if l_bytes:
                    records = [r for r in l_bytes.split(b"\0") if r]
                    legacy_status_count = len(records)
            except Exception:
                legacy_dirty = True
                legacy_status_count = 1

        registered = self._registered_worktrees(c_root)
        worktree_entries: list[WorkspaceWorktreeEntry] = []

        protected_refs: set[str] = set()
        try:
            raw_refs = self._run_git(
                [
                    "for-each-ref",
                    "--format=%(objectname)",
                    "refs/nexus-candidates/",
                    "refs/nexus-candidate-commits/",
                    "refs/nexus-salvage/",
                ],
                cwd=c_root,
            ).splitlines()
            protected_refs.update(r.strip() for r in raw_refs if r.strip())
        except Exception:
            pass

        states = task_states or {}
        path_to_task: dict[str, tuple[str, dict]] = {}
        for tid, st in states.items():
            lease_dict = st.get("lease") or {}
            target_wt = lease_dict.get("target_worktree") or (st.get("contract") or {}).get("target_repo_root")
            if target_wt:
                path_to_task[str(Path(target_wt).resolve())] = (tid, st)

        for reg in registered:
            wt_path_str = reg.get("worktree")
            if not wt_path_str:
                continue
            wt_path = Path(wt_path_str).resolve()
            wt_str = str(wt_path)

            if not wt_path.exists():
                worktree_entries.append(
                    WorkspaceWorktreeEntry(
                        path=wt_str,
                        head=reg.get("HEAD", ""),
                        branch=reg.get("branch", ""),
                        classification="KEEP_DIRTY_OR_UNKNOWN",
                        is_dirty=False,
                        reachable_from_controller=False,
                        protected_by_ref=False,
                        blocker_reason="missing_worktree_directory",
                    )
                )
                continue

            try:
                head = self._run_git(["rev-parse", "HEAD"], cwd=wt_path)
            except Exception:
                head = reg.get("HEAD", "")
            try:
                branch = self._run_git(["branch", "--show-current"], cwd=wt_path)
                if not branch:
                    branch = reg.get("branch", "detached")
            except Exception:
                branch = reg.get("branch", "detached")

            is_dirty = bool(self._status_bytes(wt_path))

            # Git's porcelain worktree output emits ``locked`` when an
            # operator explicitly protects a worktree.  Keep this signal
            # separate from lifecycle ownership; either one is fail-closed.
            lock_present = "locked" in reg
            process_evidence_unavailable = False
            if wt_path == c_root:
                process_active = False
            else:
                try:
                    process_state = self.process_checker(wt_path)
                    process_evidence_unavailable = process_state is None
                    process_active = bool(process_state) if process_state is not None else False
                except Exception:
                    process_active = False
                    process_evidence_unavailable = True

            reachable = False
            if head == c_head:
                reachable = True
            else:
                try:
                    self._run_git(["merge-base", "--is-ancestor", head, c_head], cwd=c_root)
                    reachable = True
                except Exception:
                    reachable = False

            unique_commits_unavailable = False
            try:
                unique_commits = tuple(sorted(set(self._run_git(
                    ["rev-list", f"{c_head}..{head}"], cwd=c_root
                ).splitlines())))
            except Exception:
                unique_commits = ()
                unique_commits_unavailable = True

            protected = head in protected_refs
            registered_branch_ref = reg.get("branch", "")
            branch_ref_unavailable = False
            branch_ref_valid = False
            if registered_branch_ref:
                try:
                    branch_ref_valid = self._run_git(
                        ["rev-parse", f"{registered_branch_ref}^{{commit}}"], cwd=c_root
                    ) == head
                except Exception:
                    branch_ref_unavailable = True
            branch_protected = branch_ref_valid or protected or branch.startswith(
                (
                    "refs/nexus-candidates/", "refs/nexus-candidate-commits/", "refs/nexus-salvage/",
                    "nexus-candidates/", "nexus-candidate-commits/", "nexus-salvage/",
                )
            )

            task_info = path_to_task.get(wt_str)
            mapped_task_id = task_info[0] if task_info else None
            task_st = task_info[1] if task_info else None
            task_status = task_st.get("status") if task_st else None
            lifecycle_owner = mapped_task_id
            current_review = task_status in {"RETAINED_FOR_REVIEW", "FINAL_BLOCK"}

            classification = "KEEP_DIRTY_OR_UNKNOWN"
            blocker_reason = None

            if wt_path == c_root:
                classification = "KEEP_CONTROLLER"
            elif wt_path == legacy_path.resolve() or wt_str == "/Users/jameschen/Workspace/nexus":
                classification = "KEEP_DIRTY_OR_UNKNOWN"
                blocker_reason = "legacy_root_protected"
            elif task_status is not None and task_status not in {"INTEGRATED", "SUPERSEDED", "CANCELLED", "REJECTED", "RETAINED_FOR_REVIEW", "FINAL_BLOCK"}:
                classification = "KEEP_ACTIVE_OR_RETAINED"
                blocker_reason = "active_task_ownership"
            elif task_status in {"RETAINED_FOR_REVIEW", "FINAL_BLOCK"}:
                classification = "KEEP_ACTIVE_OR_RETAINED"
                blocker_reason = "retained_for_review_evidence"
            elif task_status in {"INTEGRATED", "SUPERSEDED", "CANCELLED", "REJECTED"}:
                if is_dirty:
                    classification = "KEEP_DIRTY_OR_UNKNOWN"
                    blocker_reason = "dirty_terminal_target"
                elif reachable or protected or head == (task_st.get("lease") or {}).get("initial_head"):
                    classification = "RELEASABLE_TERMINAL_TARGET"
                else:
                    classification = "BLOCKED_UNPROTECTED_UNIQUE_COMMIT"
                    blocker_reason = "unprotected_unique_commit"
            else:
                if is_dirty:
                    classification = "KEEP_DIRTY_OR_UNKNOWN"
                    blocker_reason = "unmapped_dirty_worktree"
                elif reachable or protected:
                    classification = "RELEASABLE_REDUNDANT_CLEAN"
                else:
                    classification = "BLOCKED_UNPROTECTED_UNIQUE_COMMIT"
                    blocker_reason = "unmapped_unique_commit"

            if wt_path != c_root and (process_active or lock_present):
                # Preserve the legacy classification names for compatibility,
                # while making the disposition gate conservative.
                blocker_reason = "active_process_or_lock"
            if wt_path != c_root and (process_active or lock_present or process_evidence_unavailable or branch_ref_unavailable or unique_commits_unavailable):
                classification = "KEEP_ACTIVE_OR_RETAINED" if (process_active or lock_present) else "KEEP_DIRTY_OR_UNKNOWN"
            if wt_path == c_root:
                disposition = "ACTIVE_RETAIN"
            elif current_review or task_status in {"RETAINED_FOR_REVIEW", "FINAL_BLOCK"}:
                disposition = "FORENSIC_RETAIN"
            elif process_evidence_unavailable:
                disposition = "OWNER_DECISION_REQUIRED"
            elif process_active or lock_present or is_dirty:
                disposition = "ACTIVE_RETAIN" if process_active or lock_present else "OWNER_DECISION_REQUIRED"
            elif unique_commits_unavailable:
                disposition = "OWNER_DECISION_REQUIRED"
            elif branch_ref_unavailable:
                disposition = "OWNER_DECISION_REQUIRED"
            elif unique_commits and (protected or branch_protected):
                disposition = "FORENSIC_RETAIN"
            elif unique_commits and not protected:
                disposition = "BLOCKED_UNPROTECTED_UNIQUE_COMMIT"
            elif task_status is not None and task_status not in {"INTEGRATED", "SUPERSEDED", "CANCELLED", "REJECTED"}:
                disposition = "ACTIVE_RETAIN"
            else:
                disposition = "RELEASABLE_REDUNDANT_CLEAN"

            if unique_commits and (protected or branch_protected):
                classification = "KEEP_ACTIVE_OR_RETAINED"
                blocker_reason = "protected_unique_commit"
            elif branch_ref_unavailable or unique_commits_unavailable:
                blocker_reason = "worktree_evidence_unavailable"
            if process_evidence_unavailable:
                blocker_reason = "process_evidence_unavailable"
            elif branch_ref_unavailable:
                blocker_reason = "branch_ref_evidence_unavailable"
            elif unique_commits_unavailable:
                blocker_reason = "unique_commit_evidence_unavailable"

            worktree_entries.append(
                WorkspaceWorktreeEntry(
                    path=wt_str,
                    head=head,
                    branch=branch,
                    classification=classification,
                    is_dirty=is_dirty,
                    reachable_from_controller=reachable,
                    protected_by_ref=protected,
                    branch_protected=branch_protected,
                    task_id=mapped_task_id,
                    blocker_reason=blocker_reason,
                    unique_commits=unique_commits,
                    lifecycle_owner=lifecycle_owner,
                    process_active=process_active,
                    process_evidence_unavailable=process_evidence_unavailable,
                    evidence_unavailable=(
                        process_evidence_unavailable or branch_ref_unavailable or unique_commits_unavailable
                    ),
                    lock_present=lock_present,
                    current_review=current_review,
                    disposition=disposition,
                )
            )

        if legacy_exists and not any(w.path == str(legacy_path.resolve()) or w.path == "/Users/jameschen/Workspace/nexus" for w in worktree_entries):
            worktree_entries.append(
                WorkspaceWorktreeEntry(
                    path=str(legacy_path.resolve()),
                    head="",
                    branch="",
                    classification="KEEP_DIRTY_OR_UNKNOWN",
                    is_dirty=legacy_dirty,
                    reachable_from_controller=False,
                    protected_by_ref=False,
                    blocker_reason="legacy_root_protected",
                    lifecycle_owner=None,
                    disposition="OWNER_DECISION_REQUIRED",
                )
            )

        inv_payload = {
            "controller_root": str(c_root),
            "controller_head": c_head,
            "controller_dirty": c_dirty,
            "legacy_root_path": str(legacy_path),
            "legacy_root_dirty": legacy_dirty,
            "worktrees": [
                {
                    "path": w.path,
                    "head": w.head,
                    "branch": w.branch,
                    "classification": w.classification,
                    "is_dirty": w.is_dirty,
                    "reachable_from_controller": w.reachable_from_controller,
                    "protected_by_ref": w.protected_by_ref,
                    "branch_protected": w.branch_protected,
                    "task_id": w.task_id,
                    "unique_commits": list(w.unique_commits),
                    "lifecycle_owner": w.lifecycle_owner,
                    "process_active": w.process_active,
                    "process_evidence_unavailable": w.process_evidence_unavailable,
                    "lock_present": w.lock_present,
                    "current_review": w.current_review,
                    "evidence_unavailable": w.evidence_unavailable,
                    "disposition": w.disposition,
                    "blocker_reason": w.blocker_reason,
                }
                for w in sorted(worktree_entries, key=lambda x: x.path)
            ],
        }
        inv_hash = sha256(json.dumps(inv_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()

        return WorkspaceInventory(
            schema="nexus.workspace_inventory.v1",
            controller_root=str(c_root),
            controller_branch=c_branch,
            controller_head=c_head,
            controller_dirty=c_dirty,
            legacy_root_path=str(legacy_path),
            legacy_root_exists=legacy_exists,
            legacy_root_dirty=legacy_dirty,
            legacy_root_status_count=legacy_status_count,
            worktrees=worktree_entries,
            inventory_hash=inv_hash,
        )

    def audit_direct_completion(
        self,
        *,
        controller_root: str | Path,
        expected_head: str,
        expected_branch: str,
        allowed_files: Sequence[str] = (),
        task_states: Optional[Dict[str, dict]] = None,
    ) -> dict:
        """Return a deterministic, read-only gate for direct completion.

        Registered clean worktrees are informational. Only canonical drift,
        active Target ownership, or dirty managed worktrees overlapping the
        direct task's allowed scope block completion.
        """
        inventory = self.get_workspace_inventory(
            controller_root=controller_root,
            task_states=task_states,
        )
        registered_paths = {
            str(Path(entry["worktree"]).resolve())
            for entry in self._registered_worktrees(Path(controller_root).resolve())
            if entry.get("worktree")
        }
        allowed = [str(path) for path in allowed_files if str(path).strip()]
        states = task_states or {}
        blockers: list[str] = []
        if inventory.controller_head != expected_head:
            blockers.append("canonical_head_mismatch")
        if inventory.controller_branch != expected_branch:
            blockers.append("canonical_branch_mismatch")
        if inventory.controller_dirty:
            blockers.append("canonical_dirty")

        aux_records: list[dict[str, object]] = []
        terminal = _DIRECT_TERMINAL_STATUSES
        exempt = {"PENDING_HUMAN_APPROVAL", "APPROVED"}
        for entry in inventory.worktrees:
            if (
                entry.path not in registered_paths
                or entry.path == inventory.controller_root
                or entry.path == inventory.legacy_root_path
            ):
                continue
            path = Path(entry.path)
            changed: list[str] = []
            status_read_error = False
            if path.exists():
                try:
                    changed, untracked, deleted = self._parse_status(
                        self._status_bytes(path)
                    )
                    changed = sorted(set(changed) | set(untracked) | set(deleted))
                except Exception:
                    status_read_error = True
            task_id = entry.task_id
            state = states.get(task_id or "") if task_id else None
            status = state.get("status") if state else None
            active_target = bool(
                task_id
                and status not in terminal
                and status not in exempt
            )
            overlap = [
                path_name for path_name in changed
                if any(
                    path_name == boundary
                    or boundary.endswith("/") and path_name.startswith(boundary)
                    for boundary in allowed
                )
            ]
            record_blockers: list[str] = []
            if entry.process_evidence_unavailable:
                record_blockers.append("process_evidence_unavailable")
                blockers.append(f"process_evidence_unavailable:{entry.path}")
            if entry.disposition in {
                "ACTIVE_RETAIN", "FORENSIC_RETAIN", "OWNER_DECISION_REQUIRED",
                "BLOCKED_UNPROTECTED_UNIQUE_COMMIT",
            }:
                # The controller is intentionally omitted above; every
                # non-canonical disposition is a typed, fail-closed signal.
                if entry.disposition == "ACTIVE_RETAIN":
                    record_blockers.append("active_or_locked_worktree")
                    blockers.append(f"active_or_locked_worktree:{entry.path}")
                elif entry.disposition == "FORENSIC_RETAIN":
                    record_blockers.append("current_review_retention")
                    blockers.append(f"current_review_retention:{entry.path}")
                elif entry.disposition == "OWNER_DECISION_REQUIRED":
                    record_blockers.append("owner_decision_required")
                    blockers.append(f"owner_decision_required:{entry.path}")
                else:
                    record_blockers.append("unprotected_unique_commit")
                    blockers.append(f"unprotected_unique_commit:{entry.path}")
            if active_target:
                record_blockers.append("active_target")
                blockers.append(f"active_target:{entry.path}")
            if entry.is_dirty and task_id and overlap:
                record_blockers.append("dirty_allowed_overlap")
                blockers.append(f"dirty_allowed_overlap:{entry.path}")
            if entry.is_dirty and task_id and status_read_error:
                record_blockers.append("worktree_status_unreadable")
                blockers.append(f"worktree_status_unreadable:{entry.path}")
            aux_records.append({
                "path": entry.path,
                "head": entry.head,
                "branch": entry.branch,
                "classification": entry.classification,
                "disposition": entry.disposition,
                "is_dirty": entry.is_dirty,
                "process_active": entry.process_active,
                "process_evidence_unavailable": entry.process_evidence_unavailable,
                "lock_present": entry.lock_present,
                "reachable_from_controller": entry.reachable_from_controller,
                "unique_commits": list(entry.unique_commits),
                "protected_by_ref": entry.protected_by_ref,
                "branch_protected": entry.branch_protected,
                "lifecycle_owner": entry.lifecycle_owner,
                "current_review": entry.current_review,
                "evidence_unavailable": entry.evidence_unavailable,
                "task_id": task_id,
                "task_status": status,
                "changed_files": changed,
                "allowed_overlap": overlap,
                "status_read_error": status_read_error,
                "blockers": record_blockers,
            })

        return {
            "schema": "nexus.direct_worktree_audit.v1",
            "controller_root": inventory.controller_root,
            "revision": inventory.controller_head,
            "expected_revision": expected_head,
            "branch": inventory.controller_branch,
            "expected_branch": expected_branch,
            "registered_count": len(registered_paths),
            "aux_records": aux_records,
            "blockers": sorted(set(blockers)),
            "inventory_hash": inventory.inventory_hash,
        }

    def plan_convergence(
        self,
        inventory: WorkspaceInventory,
        expected_controller_revision: Optional[str] = None,
    ) -> ConvergencePlan:
        c_rev = inventory.controller_head
        groups: Dict[str, list[str]] = {
            "KEEP_CONTROLLER": [],
            "KEEP_DIRTY_OR_UNKNOWN": [],
            "KEEP_ACTIVE_OR_RETAINED": [],
            "RELEASABLE_TERMINAL_TARGET": [],
            "RELEASABLE_REDUNDANT_CLEAN": [],
            "BLOCKED_UNPROTECTED_UNIQUE_COMMIT": [],
            "ACTIVE_RETAIN": [],
            "FORENSIC_RETAIN": [],
            "OWNER_DECISION_REQUIRED": [],
        }
        blocker_codes_set: set[str] = set()

        if expected_controller_revision and c_rev != expected_controller_revision:
            blocker_codes_set.add("CONTROLLER_REVISION_DRIFT")

        for w in inventory.worktrees:
            cls = w.classification
            if cls not in groups:
                groups[cls] = []
            groups[cls].append(w.path)
            if w.disposition in groups and w.path not in groups[w.disposition]:
                groups[w.disposition].append(w.path)
            if w.blocker_reason:
                blocker_codes_set.add(w.blocker_reason)

        releasable_paths = sorted(
            w.path for w in inventory.worktrees
            if w.disposition == "RELEASABLE_REDUNDANT_CLEAN"
        )
        blocked_paths = sorted(
            groups["KEEP_DIRTY_OR_UNKNOWN"]
            + groups["KEEP_ACTIVE_OR_RETAINED"]
            + groups["BLOCKED_UNPROTECTED_UNIQUE_COMMIT"]
            + [
                w.path for w in inventory.worktrees
                if w.disposition in {
                    "ACTIVE_RETAIN", "FORENSIC_RETAIN", "OWNER_DECISION_REQUIRED",
                    "BLOCKED_UNPROTECTED_UNIQUE_COMMIT",
                }
            ]
        )
        blocked_paths = sorted(set(p for p in blocked_paths if p != inventory.controller_root))
        blocker_codes = sorted(blocker_codes_set)
        affected_paths = sorted(set(releasable_paths) | set(blocked_paths))

        plan_payload = {
            "controller_revision": c_rev,
            "inventory_hash": inventory.inventory_hash,
            "groups": {k: sorted(v) for k, v in sorted(groups.items())},
            "releasable_paths": releasable_paths,
            "blocked_paths": blocked_paths,
            "blocker_codes": blocker_codes,
        }
        plan_hash = sha256(json.dumps(plan_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()

        return ConvergencePlan(
            schema="nexus.workspace_convergence_plan.v1",
            controller_revision=c_rev,
            inventory_hash=inventory.inventory_hash,
            plan_hash=plan_hash,
            groups=groups,
            releasable_paths=releasable_paths,
            blocked_paths=blocked_paths,
            blocker_codes=blocker_codes,
            affected_paths=affected_paths,
            deletion_count=len(releasable_paths),
            next_allowed_gate="INDEPENDENT_CANDIDATE_REVIEW",
        )

    def apply_convergence_plan(
        self,
        plan: ConvergencePlan,
        expected_controller_revision: str,
        expected_plan_hash: str,
    ) -> ConvergenceApplyReceipt:
        if plan.controller_revision != expected_controller_revision:
            raise RuntimeError(
                f"CONTROLLER_REVISION_DRIFT: plan controller revision {plan.controller_revision} "
                f"does not match expected {expected_controller_revision}"
            )
        if plan.plan_hash != expected_plan_hash:
            raise RuntimeError(
                f"PLAN_HASH_MISMATCH: plan hash {plan.plan_hash} "
                f"does not match expected {expected_plan_hash}"
            )

        controller_root = Path(
            plan.groups.get("KEEP_CONTROLLER", ["."])[0]
            if plan.groups.get("KEEP_CONTROLLER")
            else "."
        ).resolve()

        released_paths: list[str] = []
        failed_paths: list[dict[str, str]] = []

        for p_str in plan.releasable_paths:
            p = Path(p_str).resolve()
            if str(p) == str(Path("/Users/jameschen/Workspace/nexus").resolve()):
                raise RuntimeError("LEGACY_ROOT_APPLY_FORBIDDEN: legacy root cannot be released")
            if not p.exists():
                released_paths.append(p_str)
                continue
            try:
                entry = self._worktree_entry(controller_root, p)
                if entry is not None:
                    self._run_git(["worktree", "remove", "--", str(p)], cwd=controller_root)
                    self._run_git(["worktree", "prune"], cwd=controller_root)
                elif p.is_dir() and not any(p.iterdir()):
                    p.rmdir()
                released_paths.append(p_str)
            except Exception as exc:
                failed_paths.append({"path": p_str, "error": str(exc)})

        return ConvergenceApplyReceipt(
            schema="nexus.workspace_convergence_apply_receipt.v1",
            controller_revision=expected_controller_revision,
            plan_hash=expected_plan_hash,
            applied=True,
            released_paths=released_paths,
            failed_paths=failed_paths,
            next_allowed_gate="INDEPENDENT_CANDIDATE_REVIEW",
        )

    def get_reusable_slot_path(self, campaign_id: str = "default", slot_index: int = 0) -> Path:
        # One serial slot is shared across campaigns; campaign_id remains
        # receipt metadata, never a second physical Target namespace.
        return self.root_dir / "serial-slot" / f"slot-{slot_index}"

    def get_reusable_slot_status(
        self,
        campaign_id: str = "default",
        slot_index: int = 0,
        controller_root: Optional[Path] = None,
        task_states: Optional[Dict[str, dict]] = None,
    ) -> ReusableSlotLease:
        c_root = (controller_root or Path.cwd()).resolve()
        c_head = self._run_git(["rev-parse", "HEAD"], cwd=c_root)
        slot_path = self.get_reusable_slot_path(campaign_id, slot_index).resolve()
        slot_id = f"{campaign_id}/slot-{slot_index}"

        states = task_states or {}
        active_task_id = None
        for tid, st in states.items():
            lease_dict = st.get("lease") or {}
            target_wt = lease_dict.get("target_worktree") or (st.get("contract") or {}).get("target_repo_root")
            if target_wt and Path(target_wt).resolve() == slot_path:
                if st.get("status") not in {"INTEGRATED", "SUPERSEDED", "CANCELLED", "REJECTED"}:
                    active_task_id = tid
                    break

        if active_task_id:
            return ReusableSlotLease(
                schema="nexus.reusable_slot_lease.v1",
                slot_id=slot_id,
                campaign_id=campaign_id,
                slot_path=str(slot_path),
                task_id=active_task_id,
                status="BLOCKED",
                controller_revision=c_head,
                target_base_revision=None,
                blocker=f"BLOCKED_SLOT_IN_USE: active task {active_task_id} owns slot",
            )

        if not slot_path.exists():
            return ReusableSlotLease(
                schema="nexus.reusable_slot_lease.v1",
                slot_id=slot_id,
                campaign_id=campaign_id,
                slot_path=str(slot_path),
                task_id=None,
                status="READY",
                controller_revision=c_head,
                target_base_revision=c_head,
                blocker=None,
            )

        if self._status_bytes(slot_path):
            return ReusableSlotLease(
                schema="nexus.reusable_slot_lease.v1",
                slot_id=slot_id,
                campaign_id=campaign_id,
                slot_path=str(slot_path),
                task_id=None,
                status="BLOCKED",
                controller_revision=c_head,
                target_base_revision=None,
                blocker="BLOCKED_DIRTY_SLOT: dirty reusable slot fails closed and remains untouched",
            )

        return ReusableSlotLease(
            schema="nexus.reusable_slot_lease.v1",
            slot_id=slot_id,
            campaign_id=campaign_id,
            slot_path=str(slot_path),
            task_id=None,
            status="READY",
            controller_revision=c_head,
            target_base_revision=c_head,
            blocker=None,
        )

    def prepare_reusable_slot(
        self,
        contract: SelfHostedTaskContract,
        campaign_id: str = "default",
        slot_index: int = 0,
        task_states: Optional[Dict[str, dict]] = None,
    ) -> ReusableSlotLease:
        status_lease = self.get_reusable_slot_status(
            campaign_id,
            slot_index,
            controller_root=Path(contract.controller_repo_root),
            task_states=task_states,
        )
        if status_lease.status == "BLOCKED":
            return status_lease

        slot_path = Path(status_lease.slot_path)
        c_root = Path(contract.controller_repo_root).resolve()

        if slot_path.exists():
            entry = self._worktree_entry(c_root, slot_path)
            if entry is not None:
                current_head = self._run_git(["rev-parse", "HEAD"], cwd=slot_path)
                if current_head == contract.target_base_revision:
                    return ReusableSlotLease(
                        schema="nexus.reusable_slot_lease.v1",
                        slot_id=status_lease.slot_id,
                        campaign_id=campaign_id,
                        slot_path=str(slot_path),
                        task_id=contract.task_id,
                        status="READY",
                        controller_revision=contract.controller_revision,
                        target_base_revision=contract.target_base_revision,
                        blocker=None,
                    )

                # Different-base reuse check: fail closed unless prior slot is proven clean/releasable
                protected_refs: set[str] = set()
                try:
                    raw_refs = self._run_git(
                        [
                            "for-each-ref",
                            "--format=%(objectname)",
                            "refs/nexus-candidates/",
                            "refs/nexus-candidate-commits/",
                            "refs/nexus-salvage/",
                        ],
                        cwd=c_root,
                    ).splitlines()
                    protected_refs.update(r.strip() for r in raw_refs if r.strip())
                except Exception:
                    pass

                reachable = False
                try:
                    self._run_git(["merge-base", "--is-ancestor", current_head, contract.controller_revision], cwd=c_root)
                    reachable = True
                except Exception:
                    reachable = False

                if not reachable and current_head not in protected_refs:
                    return ReusableSlotLease(
                        schema="nexus.reusable_slot_lease.v1",
                        slot_id=status_lease.slot_id,
                        campaign_id=campaign_id,
                        slot_path=str(slot_path),
                        task_id=contract.task_id,
                        status="BLOCKED",
                        controller_revision=contract.controller_revision,
                        target_base_revision=contract.target_base_revision,
                        blocker="BLOCKED_UNPROTECTED_UNIQUE_COMMIT: slot contains unprotected unique commit",
                    )

                self._run_git(["worktree", "remove", "--", str(slot_path)], cwd=c_root)
                self._run_git(["worktree", "prune"], cwd=c_root)
            elif not any(slot_path.iterdir()):
                slot_path.rmdir()
            else:
                return ReusableSlotLease(
                    schema="nexus.reusable_slot_lease.v1",
                    slot_id=status_lease.slot_id,
                    campaign_id=campaign_id,
                    slot_path=str(slot_path),
                    task_id=contract.task_id,
                    status="BLOCKED",
                    controller_revision=contract.controller_revision,
                    target_base_revision=contract.target_base_revision,
                    blocker="BLOCKED_DIRTY_SLOT: unregistered directory in slot",
                )

        slot_contract = SelfHostedTaskContract(
            task_id=contract.task_id,
            objective=contract.objective,
            controller_revision=contract.controller_revision,
            target_base_revision=contract.target_base_revision,
            controller_repo_root=contract.controller_repo_root,
            target_repo_root=str(slot_path),
            target_worktree_root=str(slot_path.parent),
            allowed_files=contract.allowed_files,
            forbidden_files=contract.forbidden_files,
            authorized_deletions=contract.authorized_deletions,
            verifier_commands=contract.verifier_commands,
            protected_contracts=contract.protected_contracts,
            preferred_provider=contract.preferred_provider,
            fallback_provider=contract.fallback_provider,
            maximum_provider_calls=contract.maximum_provider_calls,
            maximum_replans=contract.maximum_replans,
            mutation_mode=contract.mutation_mode,
            human_approval_required=contract.human_approval_required,
        )
        self.create_lease(slot_contract)

        return ReusableSlotLease(
            schema="nexus.reusable_slot_lease.v1",
            slot_id=status_lease.slot_id,
            campaign_id=campaign_id,
            slot_path=str(slot_path),
            task_id=contract.task_id,
            status="READY",
            controller_revision=contract.controller_revision,
            target_base_revision=contract.target_base_revision,
            blocker=None,
        )


# integrity-seal: 1776512137
