import json
import os
import subprocess
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Callable, Dict, Optional

from nexus.orchestrator.task_contract import ApprovalStatus, SelfHostedTaskContract


NEXUS_SALVAGE_BOT_NAME = "Nexus Salvage Bot"
NEXUS_SALVAGE_BOT_EMAIL = "nexus-salvage-bot@nexus.local"


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


@dataclass(frozen=True)
class TargetCleanupReceipt:
    schema: str
    task_id: str
    target_worktree: str
    decision: str
    blocker: Optional[str]
    performed: bool
    eligible: bool


def get_canonical_git_hooks_dir(base_path: Optional[Path] = None) -> Path:
    override = os.getenv("NEXUS_CANONICAL_GIT_HOOKS_DIR", "").strip()
    if override:
        hooks_dir = Path(override).expanduser().resolve()
    else:
        root = (base_path.resolve() if base_path else Path.cwd().resolve())
        if "nexus-worktrees" in root.parts:
            idx = root.parts.index("nexus-worktrees")
            hooks_root = Path(*root.parts[:idx + 1]) / "runtime-targets"
        else:
            hooks_root = root / "nexus-worktrees" / "runtime-targets"
        hooks_dir = hooks_root / ".nexus_git_hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)
    try:
        hooks_dir.chmod(0o700)
    except Exception as exc:
        raise RuntimeError(f"failed to set permissions 0700 on canonical git hooks dir: {exc}") from exc

    if not hooks_dir.is_dir():
        raise RuntimeError(f"canonical git hooks path is not a directory: {hooks_dir}")

    st = hooks_dir.stat()
    current_uid = os.getuid()
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
    ):
        self.root_dir = Path(root_dir)
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
            hooks_dir = get_canonical_git_hooks_dir(Path(cwd) if cwd else self.root_dir)
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
            hooks_dir = get_canonical_git_hooks_dir(Path(cwd) if cwd else self.root_dir)
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

    def create_lease(
        self,
        contract: SelfHostedTaskContract,
    ) -> TargetWorktreeLease:
        controller_root, target_path, target_root = self._resolved_paths(contract)
        self._verify_target_boundary(controller_root, target_path, target_root)
        controller_status = self._verify_controller(contract)
        resolved_target_revision = self._run_git(
            ["rev-parse", f"{contract.target_base_revision}^{{commit}}"],
            cwd=controller_root,
        )
        if resolved_target_revision != contract.target_base_revision:
            raise RuntimeError("Target base revision did not resolve to the exact contract SHA")

        target_branch = f"nexus/task/{contract.task_id}"
        target_detached = False
        active_targets = [
            entry for entry in self._registered_worktrees(controller_root)
            if "worktree" in entry
            and Path(entry["worktree"]).resolve() != controller_root
            and self.root_dir.resolve() in Path(entry["worktree"]).resolve().parents
            and Path(entry["worktree"]).resolve() != target_path
        ]
        if active_targets:
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

        initial_head = self._run_git(["rev-parse", "HEAD"], cwd=target_path)
        actual_branch = self._run_git(["branch", "--show-current"], cwd=target_path)
        initial_status = self._status_bytes(target_path)
        if initial_head != contract.target_base_revision:
            raise RuntimeError("Target worktree was not created from the exact revision")
        if actual_branch != target_branch and not (target_detached and not actual_branch):
            raise RuntimeError("Target worktree branch does not match the lease identity")
        if initial_status:
            raise RuntimeError("Target worktree must be clean")

        return TargetWorktreeLease(
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
        )

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
            ["lsof", "+D", str(path)], capture_output=True, text=True
        )
        return result.returncode == 0 and bool(result.stdout.strip())

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
        if target_head != lease.initial_head:
            raise RuntimeError("Target HEAD drifted; working-tree-only mutation was required")
        target_status = self._status_bytes(target_path)
        changed_files, untracked_files, deleted_files = self._parse_status(target_status)
        tracked_diff = self._run_git_bytes(
            ["diff", "--binary", "--no-ext-diff", "HEAD", "--"],
            cwd=target_path,
        )
        tracked_diff_sha256 = sha256(tracked_diff).hexdigest()
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
        for component in components:
            digest.update(len(component).to_bytes(8, "big"))
            digest.update(component)
        return digest.hexdigest()


# integrity-seal: 1776512137
