"""Local-only integration of one verified candidate into a non-protected branch."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
import stat
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from nexus.contracts.lifecycle_action import ContractKind, LifecycleActionType
from nexus.contracts.target_integration_lifecycle import (
    ExternalAcceptanceReceipt,
    IntegrationAuthorizationEnvelope,
)
from nexus.executors.cli_worker import (
    CliWorkerRequest,
    CliWorkerStatus,
    bounded_environment_receipt,
    run_cli_worker,
)
from nexus.orchestrator.canonical_source_root import (
    _GIT_META_NAMES,
    CONTROLLER_BIND_PREFIX,
    _bind_path_problem,
)
from nexus.orchestrator.lifecycle_guards import LifecycleGuardError, require_bound_approval_grant
from nexus.orchestrator.worktree_manager import get_canonical_git_hooks_dir

_SHA = re.compile(r"^[0-9a-f]{40}$")
_PROTECTED_BRANCHES = frozenset({"main", "master", "develop", "production"})


@dataclass(frozen=True)
class IntegrationReceipt:
    schema: str
    task_id: str
    integration_branch: str
    source_branch: str
    candidate_commit_sha: str
    integration_base_sha: str
    integration_commit_sha: str
    verifier_passed: bool
    merge_performed: bool
    push_performed: bool
    worktree_removed: bool
    failure_reason: str | None = None
    staging_commit_sha: str | None = None
    post_apply_verified: bool = False
    post_apply_error: str | None = None
    acceptance_receipt_hash: str | None = None
    authorization_hash: str | None = None
    task_card_hash: str | None = None
    candidate_tree_sha: str | None = None
    candidate_state_hash: str | None = None
    verified_receipt_hash: str | None = None
    branch_head_before: str | None = None
    branch_head_after: str | None = None
    candidate_is_ancestor: bool = False
    staging_verified: bool = False


class IntegrationExecutionError(RuntimeError):
    """Carry physical Git truth across a failed integration execution."""

    def __init__(
        self,
        *,
        stage: str,
        branch_head_before: str,
        branch_head_after: str,
        staging_commit_sha: str | None,
        candidate_commit_sha: str,
        merge_performed: bool,
        post_apply_verified: bool,
        failure_reason: str,
        cleanup_failure: str | None = None,
    ) -> None:
        self.stage = stage
        self.branch_head_before = branch_head_before
        self.branch_head_after = branch_head_after
        self.staging_commit_sha = staging_commit_sha
        self.candidate_commit_sha = candidate_commit_sha
        self.merge_performed = merge_performed
        self.post_apply_verified = post_apply_verified
        self.failure_reason = failure_reason
        self.cleanup_failure = cleanup_failure
        self.integration_result_sha = branch_head_after if merge_performed else None
        super().__init__(failure_reason)


class ControlledIntegrationManager:
    def __init__(self, *, integration_root: str | Path):
        self.integration_root = Path(integration_root).expanduser().resolve()

    @staticmethod
    def _run_sanitised_git(
        args: Sequence[str], cwd: str | Path
    ) -> subprocess.CompletedProcess[str]:
        git_env = os.environ.copy()
        git_env["GIT_CONFIG_NOSYSTEM"] = "1"
        git_env["GIT_CONFIG_GLOBAL"] = "/dev/null"
        hooks_dir = get_canonical_git_hooks_dir(Path(cwd))
        git_cmd = ["git", "-c", f"core.hooksPath={hooks_dir}", *args]
        return subprocess.run(
            git_cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            env=git_env,
        )

    @classmethod
    def _git_status(cls, args: Sequence[str], cwd: str | Path) -> int:
        """Exit code of ``git <args>`` under the same sanitised config as ``_git``."""
        return cls._run_sanitised_git(args, cwd).returncode

    @classmethod
    def _git(cls, args: Sequence[str], cwd: str | Path) -> str:
        result = cls._run_sanitised_git(args, cwd)
        if result.returncode != 0:
            raise RuntimeError(
                f"git {' '.join(args)} failed: {result.stderr.strip()}"
            )
        return result.stdout.strip()

    @classmethod
    def _is_detached_linked_worktree(cls, root: Path) -> bool:
        """True only for a separate Controller shape: a linked worktree on a detached HEAD.

        A primary checkout, or any worktree with a branch checked out, keeps
        the fully strict cleanliness rule (#2230 F3).  Probes run under the
        same sanitised git environment as every other Controller git call;
        any failure (not a repository, hooks dir unusable) is "not separate".
        """

        def probe(*args: str) -> subprocess.CompletedProcess[str] | None:
            try:
                return cls._run_sanitised_git(args, root)
            except (OSError, RuntimeError):
                return None

        git_dir = probe("rev-parse", "--absolute-git-dir")
        common_dir = probe("rev-parse", "--path-format=absolute", "--git-common-dir")
        if (
            git_dir is None
            or common_dir is None
            or git_dir.returncode != 0
            or common_dir.returncode != 0
        ):
            return False
        try:
            linked = not os.path.samefile(git_dir.stdout.strip(), common_dir.stdout.strip())
        except OSError:
            return False
        # ``symbolic-ref -q HEAD`` exits 1 exactly when HEAD is detached.
        if not linked:
            return False
        head = probe("symbolic-ref", "-q", "HEAD")
        return head is not None and head.returncode == 1

    @classmethod
    def separate_controller_integration_head(
        cls, controller_root: Path, integration_branch: str
    ) -> str | None:
        """Integration-branch head a separate detached Controller binds to, else None.

        None for every shape except a linked worktree on a detached HEAD: those
        callers keep binding ``HEAD`` with the branch checked out (#2230).
        For the separate shape apply is ``update-ref refs/heads/<branch>`` with
        a compare-and-swap on this exact head, while the Controller HEAD moves
        with tasks/-only Task Card bind commits, so the closure binds the ref.
        Raises when the branch is invalid, a symbolic ref (update-ref would
        move its target), missing, or checked out in any worktree, including
        one mid-rebase or mid-bisect on it (update-ref would move it under
        that checkout).
        """
        if not cls._is_detached_linked_worktree(controller_root):
            return None
        try:
            cls._validate_branch(integration_branch)
        except ValueError as exc:
            raise RuntimeError("CLOSURE_INTEGRATION_BRANCH_INVALID") from exc
        ref = f"refs/heads/{integration_branch}"
        # A revision expression (``~1``, ``^``, ``@{...}``) would resolve to a
        # commit other than the ref the apply moves.
        if cls._git_status(["check-ref-format", ref], controller_root) != 0:
            raise RuntimeError("CLOSURE_INTEGRATION_BRANCH_INVALID")
        cls._require_integration_branch_not_in_use(controller_root, integration_branch)
        try:
            head = cls._git(["show-ref", "--verify", "--hash", ref], controller_root)
        except RuntimeError as exc:
            raise RuntimeError("CLOSURE_INTEGRATION_BRANCH_MISSING") from exc
        if not _SHA.fullmatch(head):
            raise RuntimeError("CLOSURE_INTEGRATION_BRANCH_MISSING")
        # The ref exists; it must name a commit itself (not a tag, tree or blob).
        try:
            peeled = cls._git(["rev-parse", "--verify", f"{head}^{{commit}}"], controller_root)
        except RuntimeError as exc:
            raise RuntimeError("CLOSURE_INTEGRATION_BRANCH_INVALID") from exc
        if peeled != head:
            raise RuntimeError("CLOSURE_INTEGRATION_BRANCH_INVALID")
        return head

    @classmethod
    def _require_integration_branch_not_in_use(cls, root: Path, branch: str) -> None:
        """Raise unless ``update-ref refs/heads/<branch>`` moves only that ref, under no checkout.

        Refuses a symbolic ref (the update would move its target), and a
        branch checked out, rebasing or bisecting in any worktree.  Used at
        bind and again right before every update-ref apply (#2230).
        """
        ref = f"refs/heads/{branch}"
        if cls._git_status(["symbolic-ref", "-q", ref], root) == 0:
            raise RuntimeError("CLOSURE_INTEGRATION_BRANCH_SYMBOLIC")
        listing = cls._git(["worktree", "list", "--porcelain"], root)
        if f"branch {ref}" in listing.splitlines() or cls._branch_in_progress_in_any_worktree(
            root, branch
        ):
            raise RuntimeError("CLOSURE_INTEGRATION_BRANCH_CHECKED_OUT")

    @classmethod
    def _require_sole_controller_checkout(cls, controller_root: Path, branch: str) -> None:
        """Raise unless the Controller root is the only worktree on ``branch``.

        ``git merge --ff-only`` in the Controller moves the branch under any
        other worktree forced onto it (``worktree add -f``), leaving that
        checkout with a staged reverse diff.  Re-proved right before the
        fast-forward (#2230).
        """
        ref = f"refs/heads/{branch}"
        raw = cls._git(["worktree", "list", "--porcelain", "-z"], controller_root)
        paths: list[str] = []
        current: str | None = None
        for field in raw.split("\0"):
            if field.startswith("worktree "):
                current = field[len("worktree ") :]
            elif field == f"branch {ref}" and current is not None:
                paths.append(current)
        if len(paths) != 1:
            raise RuntimeError(f"integration branch is checked out in {len(paths)} worktrees")
        try:
            same = os.path.samefile(paths[0], controller_root)
        except OSError:
            same = False
        if not same:
            raise RuntimeError("integration branch is checked out outside the Controller")
        if cls._branch_in_progress_in_any_worktree(controller_root, branch):
            raise RuntimeError("integration branch is rebasing or bisecting in a worktree")

    @classmethod
    def _branch_in_progress_in_any_worktree(cls, controller_root: Path, branch: str) -> bool:
        """True when any worktree is rebasing (incl. ``--update-refs``) or bisecting ``branch``.

        ``worktree list`` reports such a worktree as detached, but Git still
        treats the branch as in use there.  Every worktree's admin dir is read
        from the common dir (main plus ``worktrees/*``), as Git itself does.
        """
        ref = f"refs/heads/{branch}"
        common = Path(
            cls._git(["rev-parse", "--path-format=absolute", "--git-common-dir"], controller_root)
        )
        linked = common / "worktrees"
        admin_dirs = [common, *(sorted(linked.iterdir()) if linked.is_dir() else ())]

        def read(path: Path) -> str | None:
            # Only an absent marker means "not in progress"; a marker that
            # exists but cannot be read fails closed (#2230).
            try:
                return path.read_text(encoding="utf-8").strip()
            except (FileNotFoundError, NotADirectoryError):
                return None
            except (OSError, UnicodeDecodeError) as exc:
                raise RuntimeError(
                    f"integration branch state unreadable: {path.name}: {type(exc).__name__}"
                ) from exc

        for admin in admin_dirs:
            for state in ("rebase-merge", "rebase-apply"):
                if read(admin / state / "head-name") == ref:
                    return True
            # ``rebase --update-refs`` lists each ref it will move (refname,
            # old oid, new oid per entry).
            update_refs = read(admin / "rebase-merge" / "update-refs")
            if update_refs is not None and ref in update_refs.splitlines():
                return True
            if read(admin / "BISECT_START") in {branch, ref}:
                return True
        return False

    @staticmethod
    def _pending_task_card_problem(root: Path, relative: str) -> str | None:
        """Why an untracked ``tasks/`` entry is not a plain pending Task Card, else None.

        Every component from ``tasks`` down to the leaf is lstat'ed: none may
        be a symlink or named ``.git``; the leaf must be a regular file with
        a single link.
        """
        problem = _bind_path_problem(relative)
        if problem is not None:
            return problem
        parts = relative.split("/")
        if any(part.casefold() == ".git" for part in parts):
            return "CONTROLLER_BIND_GIT_METADATA"
        current = root
        for index, part in enumerate(parts):
            current = current / part
            try:
                info = os.lstat(current)
            except OSError:
                return "CONTROLLER_BIND_UNREADABLE"
            if stat.S_ISLNK(info.st_mode):
                return "CONTROLLER_BIND_NOT_REGULAR_FILE"
            if index == len(parts) - 1:
                if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                    return "CONTROLLER_BIND_NOT_REGULAR_FILE"
            elif not stat.S_ISDIR(info.st_mode):
                return "CONTROLLER_BIND_NOT_REGULAR_FILE"
        return None

    @staticmethod
    def _tasks_tree_problem(root: Path) -> str | None:
        """Reject symlinks, multi-link files and Git metadata names under ``tasks/``.

        ``git status`` never lists paths inside a nested ``.git`` directory
        nor ignored paths (a ``tasks/.gitignore`` or any exclude rule can hide
        them), so the on-disk tree is checked directly (without following
        links).
        """
        tasks_root = root / CONTROLLER_BIND_PREFIX.rstrip("/")
        if os.path.islink(tasks_root):
            return "CONTROLLER_BIND_NOT_REGULAR_FILE"
        if not os.path.isdir(tasks_root):
            return None
        unreadable: list[OSError] = []
        for current, dirs, files in os.walk(
            tasks_root, followlinks=False, onerror=unreadable.append
        ):
            for name in (*dirs, *files):
                if name.casefold() == ".git" or name.casefold() in _GIT_META_NAMES:
                    return "CONTROLLER_BIND_GIT_METADATA"
                path = os.path.join(current, name)
                if os.path.islink(path):
                    return "CONTROLLER_BIND_NOT_REGULAR_FILE"
            for name in files:
                try:
                    info = os.lstat(os.path.join(current, name))
                except OSError:
                    return "CONTROLLER_BIND_UNREADABLE"
                if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                    return "CONTROLLER_BIND_NOT_REGULAR_FILE"
        if unreadable:
            return "CONTROLLER_BIND_UNREADABLE"
        return None

    @classmethod
    def _require_clean_controller(
        cls, controller_root: Path, *, allow_pending_task_cards: bool, message: str
    ) -> None:
        """Fail unless the Controller worktree is clean.

        ``allow_pending_task_cards`` admits only untracked plain files under
        ``tasks/`` (pending Task Cards, #2230 F3).  Callers pass it only for a
        separate detached Controller, where apply is a pure ref update, so
        integration never reads or writes that worktree and a pending card
        cannot reach the integrated commit.  Any other entry, including a
        tracked edit under ``tasks/`` or an ignored entry there, still blocks.
        Every tracked entry must be a plain ``H`` in ``ls-files -v``: the
        assume-unchanged and skip-worktree flags hide edits from status.
        """
        if allow_pending_task_cards:
            if cls._tasks_tree_problem(controller_root) is not None:
                raise RuntimeError(message)
            ignored = cls._git(
                [
                    "status",
                    "--porcelain=v1",
                    "-z",
                    "--untracked-files=all",
                    "--ignored=matching",
                    "--",
                    CONTROLLER_BIND_PREFIX,
                ],
                controller_root,
            )
            if any(entry.startswith("!! ") for entry in ignored.split("\0")):
                raise RuntimeError(message)
        flagged = cls._git(["ls-files", "-v", "-z"], controller_root)
        if any(entry and not entry.startswith("H ") for entry in flagged.split("\0")):
            raise RuntimeError(message)
        status = cls._git(
            ["status", "--porcelain=v1", "-z", "--untracked-files=all"], controller_root
        )
        for entry in status.split("\0"):
            if not entry:
                continue
            if (
                allow_pending_task_cards
                and entry.startswith("?? " + CONTROLLER_BIND_PREFIX)
                and cls._pending_task_card_problem(controller_root, entry[3:]) is None
            ):
                continue
            raise RuntimeError(message)

    @classmethod
    def _remove_owned_worktrees(cls, paths: Sequence[Path], controller_root: Path) -> list[str]:
        """Remove worktrees this run created; each in its own try, never raising."""
        failures: list[str] = []
        for path in paths:
            if not os.path.lexists(path):
                continue
            try:
                cls._git(["worktree", "remove", "--force", str(path)], controller_root)
            except RuntimeError as exc:
                failures.append(f"{path.name}: {exc}")
        try:
            cls._git(["worktree", "prune"], controller_root)
        except RuntimeError as exc:
            failures.append(f"prune: {exc}")
        return failures

    @staticmethod
    def _validate_branch(branch: str) -> None:
        if branch in _PROTECTED_BRANCHES or branch.startswith("refs/"):
            raise ValueError(f"protected integration branch: {branch}")
        if branch != "nexus/integration" and not branch.startswith("nexus/integration/"):
            raise ValueError("integration branch must be nexus/integration or nexus/integration/*")

    @staticmethod
    def _command_intent(
        command: str,
    ) -> tuple[str, tuple[str, ...], dict[str, str]]:
        try:
            lexer = shlex.shlex(command, posix=True, punctuation_chars=";&|<>")
            lexer.whitespace_split = True
            tokens = tuple(lexer)
        except ValueError as exc:
            raise RuntimeError("staging verifier command is malformed") from exc
        if not tokens:
            raise RuntimeError("staging verifier command is malformed")

        assignments: dict[str, str] = {}
        assignment_pattern = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)=(.*)$")
        index = 0
        while index < len(tokens):
            match = assignment_pattern.fullmatch(tokens[index])
            if match is None:
                if "=" in tokens[index] and index == 0:
                    raise RuntimeError("staging verifier environment is malformed")
                break
            name, value = match.groups()
            if name != "PYTHONDONTWRITEBYTECODE" or value != "1":
                raise RuntimeError("staging verifier environment is not admitted")
            if name in assignments and assignments[name] != value:
                raise RuntimeError("staging verifier environment is conflicting")
            assignments[name] = value
            index += 1
        if index >= len(tokens):
            raise RuntimeError("staging verifier command is malformed")

        executable = tokens[index]
        argv = tokens[index + 1 :]
        if (
            executable in {";", "&&", "||", "|", "<", ">"}
            or not executable.strip()
            or executable.startswith("-")
            or ".." in Path(executable).parts
            or any(token in {";", "&&", "||", "|", "<", ">"} for token in argv)
        ):
            raise RuntimeError("staging verifier command is not admitted")
        for arg_index, token in enumerate(argv):
            if re.search(r"[\x00\r\n]", token):
                raise RuntimeError("staging verifier argv is malformed")
            if any(char in token for char in ";&|<>()$`") and not (
                arg_index > 0 and argv[arg_index - 1] == "-c"
            ):
                raise RuntimeError("staging verifier argv is not admitted")
            if assignment_pattern.fullmatch(token):
                raise RuntimeError("staging verifier environment position is invalid")
        assignments.setdefault("PYTHONDONTWRITEBYTECODE", "1")
        return executable, argv, assignments

    @staticmethod
    def _admitted_manifest(
        state: Mapping[str, Any],
        contract: Mapping[str, Any],
    ) -> tuple[dict[str, Any], ...]:
        """Bind staging verifiers to the successful Candidate evidence.

        Contract commands are human-readable intent.  They are never resolved
        again through the integration process' ambient ``PATH``.  The only
        executable authority is the ordered, successful verifier evidence
        already sealed into the verified Candidate receipt.
        """
        commands = tuple(str(item) for item in contract.get("verifier_commands") or ())
        if not commands:
            return ()
        receipt = state.get("verified_receipt")
        if not isinstance(receipt, Mapping):
            raise RuntimeError("staging verifier evidence is missing")
        evidence = receipt.get("verifier_evidence")
        if not isinstance(evidence, (list, tuple)) or len(evidence) != len(commands):
            raise RuntimeError("staging verifier evidence order mismatch")

        admitted: list[dict[str, Any]] = []
        for index, (command, item) in enumerate(zip(commands, evidence, strict=True)):
            if not isinstance(item, Mapping):
                raise RuntimeError("staging verifier evidence is malformed")
            executable_intent, argv_intent, bounded_env = (
                ControlledIntegrationManager._command_intent(command)
            )
            if str(item.get("command") or "") != command:
                raise RuntimeError("staging verifier command mismatch")
            argv = item.get("argv")
            if (
                not isinstance(argv, (list, tuple))
                or not all(isinstance(value, str) for value in argv)
                or tuple(argv) != argv_intent
            ):
                raise RuntimeError("staging verifier argv mismatch")
            executable = Path(str(item.get("executable_identity") or "")).expanduser()
            if (
                not executable.is_absolute()
                or not executable.is_file()
                or not os.access(executable, os.X_OK)
                or executable.name != Path(executable_intent).name
                or (
                    Path(executable_intent).is_absolute()
                    and str(executable) != str(Path(executable_intent).expanduser())
                )
            ):
                raise RuntimeError("staging verifier executable identity is invalid")
            expected_sha = str(item.get("executable_sha256") or "")
            if not re.fullmatch(r"[0-9a-f]{64}", expected_sha):
                raise RuntimeError("staging verifier executable SHA is missing")
            try:
                actual_sha = hashlib.sha256(executable.read_bytes()).hexdigest()
            except OSError as exc:
                raise RuntimeError("staging verifier executable is unreadable") from exc
            if actual_sha != expected_sha:
                raise RuntimeError("staging verifier executable SHA drift")
            if (
                str(item.get("status") or "") != CliWorkerStatus.COMPLETED.value
                or item.get("exit_code") != 0
                or bool(item.get("timed_out"))
                or bool(item.get("process_group_killed"))
            ):
                raise RuntimeError("staging verifier evidence is not successful")
            evidence_env = item.get("env")
            expected_env = bounded_environment_receipt(bounded_env)
            if (
                not isinstance(evidence_env, (list, tuple))
                or not all(
                    isinstance(pair, (list, tuple))
                    and len(pair) == 2
                    and all(isinstance(value, str) for value in pair)
                    for pair in evidence_env
                )
                or tuple(tuple(pair) for pair in evidence_env) != expected_env
            ):
                raise RuntimeError("staging verifier environment receipt mismatch")
            admitted.append({
                "schema": "nexus.integration_verifier_identity.v1",
                "index": index,
                "command": command,
                "executable_identity": str(executable),
                "executable_sha256": expected_sha,
                "argv": list(argv),
                "env": dict(bounded_env),
            })
        return tuple(admitted)

    @staticmethod
    def _admitted_commands(
        state: Mapping[str, Any],
        contract: Mapping[str, Any],
    ) -> tuple[tuple[str, tuple[str, ...]], ...]:
        return tuple(
            (
                str(item["executable_identity"]),
                tuple(str(value) for value in item["argv"]),
            )
            for item in ControlledIntegrationManager._admitted_manifest(state, contract)
        )

    @staticmethod
    def _bound_manifest(
        state: Mapping[str, Any],
        contract: Mapping[str, Any],
    ) -> tuple[dict[str, Any], ...]:
        manifest = ControlledIntegrationManager._admitted_manifest(state, contract)
        persisted = state.get("integration_verifier_manifest")
        if manifest and (
            not isinstance(persisted, (list, tuple))
            or list(manifest) != list(persisted)
        ):
            raise RuntimeError("staging verifier manifest binding mismatch")
        if not manifest and persisted not in (None, [], ()):
            raise RuntimeError("staging verifier manifest binding mismatch")
        return manifest

    @staticmethod
    def _execute_manifest(
        manifest: Sequence[Mapping[str, Any]],
        cwd: Path,
    ) -> None:
        for verifier in manifest:
            executable = str(verifier["executable_identity"])
            expected_sha = str(verifier["executable_sha256"])
            try:
                current_sha = hashlib.sha256(Path(executable).read_bytes()).hexdigest()
            except OSError as exc:
                raise RuntimeError("staging verifier executable is unreadable") from exc
            if current_sha != expected_sha:
                raise RuntimeError("staging verifier executable SHA drift")
            result = run_cli_worker(
                CliWorkerRequest(
                    executable=executable,
                    argv=tuple(str(value) for value in verifier["argv"]),
                    cwd=str(cwd),
                    timeout_seconds=300.0,
                    env=dict(verifier["env"]),
                )
            )
            if (
                result.executable_identity != executable
                or result.executable_sha256 != expected_sha
                or result.status is not CliWorkerStatus.COMPLETED
                or result.exit_code != 0
            ):
                raise RuntimeError(
                    "staging verifier failed: "
                    f"{verifier['command']} status={result.status.value} "
                    f"exit_code={result.exit_code} "
                    f"stdout_sha256={result.stdout_sha256} "
                    f"stderr_sha256={result.stderr_sha256}"
                )

    @staticmethod
    def _require_bound_acceptance(
        acceptance: Any, *, state: Mapping[str, Any], task_id: str, candidate_sha: str
    ) -> None:
        """Acceptance must pass and name this task, attempt and candidate commit."""
        if not isinstance(acceptance, Mapping) or not acceptance.get("passed"):
            raise RuntimeError("external acceptance is required before integration")
        fields: dict[str, Any] = {
            key: acceptance.get(key)
            for key in (
                "schema", "task_id", "attempt_id", "candidate_commit",
                "receipt_hash", "reviewer_id", "passed", "verifier_artifact",
            )
        }
        try:
            ExternalAcceptanceReceipt(**fields)
        except (TypeError, ValueError) as exc:
            raise RuntimeError("external acceptance is not bound to this task and candidate") from exc
        attempt_id = str(state.get("attempt_id") or "")
        if (
            not task_id
            or not candidate_sha
            or str(acceptance.get("task_id") or "") != task_id
            or str(acceptance.get("candidate_commit") or "") != candidate_sha
            or not str(acceptance.get("receipt_hash") or "").strip()
            or (attempt_id and str(acceptance.get("attempt_id") or "") != attempt_id)
        ):
            raise RuntimeError("external acceptance is not bound to this task and candidate")

    @staticmethod
    def _require_integration_authority(
        state: Mapping[str, Any], approved: Mapping[str, Any], packet: Mapping[str, Any]
    ) -> None:
        """Re-establish acceptance, consumed grant and verified receipt at the sink."""
        task_id = str(state.get("task_id") or (state.get("contract") or {}).get("task_id") or "")
        candidate_sha = str(packet.get("candidate_commit_sha") or packet.get("candidate_commit") or "")
        ControlledIntegrationManager._require_bound_acceptance(
            state.get("external_acceptance"), state=state, task_id=task_id, candidate_sha=candidate_sha
        )
        integration_grant = state.get("integration_approval_grant")
        grant = integration_grant or approved.get("approval_grant")
        if not isinstance(grant, Mapping) or not grant.get("consumed_at"):
            raise RuntimeError("consumed approval grant is required before integration")
        contract_kind = str(state.get("contract_kind") or ContractKind.TRACKED_TASK_CARD.value)
        task_card_hash = str(state.get("task_card_hash") or "").strip() or None
        contract_hash = str(state.get("contract_hash") or "").strip() or task_card_hash
        if contract_kind == ContractKind.OWNER_INLINE.value:
            contract_hash = str((state.get("owner_inline_contract") or {}).get("contract_hash") or contract_hash or "")
            task_card_hash = None
        action_type = (
            LifecycleActionType.CANDIDATE_INTEGRATE
            if isinstance(integration_grant, Mapping) and integration_grant
            else LifecycleActionType.CANDIDATE_APPROVE
        ).value
        try:
            require_bound_approval_grant(
                grant,
                task_id=task_id,
                attempt_id=str(state.get("attempt_id") or ""),
                action_type=action_type,
                task_card_hash=task_card_hash,
                contract_kind=contract_kind,
                contract_hash=contract_hash,
                owner_inline_contract=state.get("owner_inline_contract"),
                allow_consumed=True,
            )
        except LifecycleGuardError as exc:
            raise RuntimeError(
                f"approval grant is not bound to this task and action: {exc}"
            ) from exc
        receipt = state.get("verified_receipt")
        if not isinstance(receipt, Mapping) or receipt.get("verified") is not True:
            raise RuntimeError("verified candidate receipt is required before integration")
        canonical = json.dumps(
            receipt, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")
        if hashlib.sha256(canonical).hexdigest() != str(packet.get("verified_receipt_hash") or ""):
            raise RuntimeError("verified receipt hash does not bind to promotion packet")

    def integrate_task_state(
        self,
        state: Mapping[str, Any],
        *,
        integration_branch: str = "nexus/integration",
    ) -> IntegrationReceipt:
        self._validate_branch(integration_branch)
        contract = state.get("contract") or {}
        packet = state.get("promotion_packet") or {}
        lease = state.get("lease") or {}
        task_id = str(state.get("task_id") or contract.get("task_id") or "")
        controller_root = Path(str(contract.get("controller_repo_root", ""))).expanduser().resolve()
        target_base_revision = str(contract.get("target_base_revision", ""))
        candidate_sha = str(packet.get("candidate_commit_sha", ""))
        source_branch = str(
            state.get("candidate_ref")
            if lease.get("target_detached")
            else lease.get("target_branch", "")
        )
        if state.get("status") not in {"CANDIDATE_COMMITTED", "APPROVED", "INTEGRATING", "INTEGRATION_FAILED"}:
            raise RuntimeError("only a terminal candidate task can be integrated")
        approved = state.get("approved_binding") or {}
        binding_fields = (
            "candidate_commit_sha", "candidate_tree_sha",
            "candidate_state_hash", "verified_receipt_hash",
        )
        if not approved or not packet or state.get("promotion_status") not in {"APPROVED", "INTEGRATION_FAILED"} or any(
            approved.get(field) != packet.get(field) for field in binding_fields
        ):
            raise RuntimeError("exact approved binding is required")
        self._require_integration_authority(state, approved, packet)
        if not _SHA.fullmatch(candidate_sha) or not _SHA.fullmatch(target_base_revision):
            raise RuntimeError("candidate and target base revisions must be exact Git SHAs")
        if not source_branch:
            raise RuntimeError("candidate source branch is missing")
        if not controller_root.is_dir():
            raise RuntimeError("controller repository root is missing")
        if self._git(["rev-parse", "--verify", f"{candidate_sha}^{{commit}}"], controller_root) != candidate_sha:
            raise RuntimeError("candidate commit is not present in controller repository")
        if self._git(["rev-parse", source_branch], controller_root) != candidate_sha:
            raise RuntimeError("candidate source branch does not bind to promotion commit")
        actual_tree = self._git(["rev-parse", f"{candidate_sha}^{{tree}}"], controller_root)
        if actual_tree != str(packet.get("candidate_tree_sha", "")):
            raise RuntimeError("candidate tree does not bind to promotion packet")
        if self._git(["rev-parse", f"{target_base_revision}^{{commit}}"], controller_root) != target_base_revision:
            raise RuntimeError("target base revision is not present")
        admitted_verifiers = self._bound_manifest(state, contract)
        if not admitted_verifiers:
            raise RuntimeError("integration requires at least one admitted verifier")

        self.integration_root.mkdir(parents=True, exist_ok=True)
        integration_path = self.integration_root / task_id
        controller_branch = self._git(["branch", "--show-current"], controller_root)
        reuse_controller_worktree = controller_branch == integration_branch
        if integration_path.exists():
            raise RuntimeError("integration worktree path already exists")
        branch_exists = subprocess.run(
            ["git", "rev-parse", "--verify", integration_branch],
            cwd=controller_root,
            capture_output=True,
            text=True,
        ).returncode == 0
        if not branch_exists:
            raise RuntimeError("governed integration branch must already exist")
        if reuse_controller_worktree:
            integration_path = controller_root
        else:
            add_args = ["worktree", "add", str(integration_path), integration_branch]
            self._git(add_args, controller_root)
        removed = False
        integration_base_sha = self._git(["rev-parse", "HEAD"], integration_path)
        try:
            self._git(["merge", "--no-ff", "--no-edit", candidate_sha], integration_path)
            self._execute_manifest(admitted_verifiers, integration_path)
            integration_sha = self._git(["rev-parse", "HEAD"], integration_path)
        except Exception:
            subprocess.run(["git", "merge", "--abort"], cwd=integration_path, capture_output=True, text=True)
            subprocess.run(["git", "reset", "--merge", integration_base_sha], cwd=integration_path, capture_output=True, text=True)
            if not reuse_controller_worktree:
                self._git(["worktree", "remove", str(integration_path)], controller_root)
            raise
        if not reuse_controller_worktree:
            self._git(["worktree", "remove", str(integration_path)], controller_root)
        removed = True
        return IntegrationReceipt(
            schema="nexus.integration_receipt.v1",
            task_id=task_id,
            integration_branch=integration_branch,
            source_branch=source_branch,
            candidate_commit_sha=candidate_sha,
            integration_base_sha=integration_base_sha,
            integration_commit_sha=integration_sha,
            verifier_passed=True,
            merge_performed=True,
            push_performed=False,
            worktree_removed=removed,
        )

    def integrate_authorized_task_state(
        self,
        state: Mapping[str, Any],
        *,
        integration_branch: str,
        staging_root: str | Path,
        apply: bool = True,
        post_apply_commands: Sequence[Sequence[str]] = (),
    ) -> IntegrationReceipt:
        """Stage and apply one already authorized Candidate through this authority.

        This is intentionally the only new Git execution seam.  Callers provide
        persisted lifecycle state; the manager rechecks exact identity, clean
        worktree state, branch head, staging ancestry, and post-apply state.
        """
        self._validate_branch(integration_branch)
        contract = state.get("contract") or {}
        packet = state.get("promotion_packet") or {}
        authorization = state.get("integration_authorization") or {}
        acceptance = state.get("external_acceptance") or {}
        candidate_sha = str(packet.get("candidate_commit_sha") or packet.get("candidate_commit") or "")
        task_id = str(state.get("task_id") or contract.get("task_id") or "")
        controller_root = Path(str(contract.get("controller_repo_root", ""))).expanduser().resolve()
        expected_head = str(authorization.get("expected_canonical_head") or "")
        if not task_id or not candidate_sha or not expected_head:
            raise RuntimeError("authorized integration identity is incomplete")
        self._require_bound_acceptance(
            state.get("external_acceptance"), state=state, task_id=task_id, candidate_sha=candidate_sha
        )
        if not authorization.get("cleanup_requested") and "CLEANUP_OWNED_TARGET" in (authorization.get("action_set") or []):
            raise RuntimeError("authorization cleanup binding is inconsistent")
        if "INTEGRATION_STAGING" not in (authorization.get("action_set") or []) or "APPLY_VERIFIED_INTEGRATION" not in (authorization.get("action_set") or []):
            raise RuntimeError("Owner authorization does not include integration actions")
        if str(authorization.get("canonical_branch") or "") != integration_branch:
            raise RuntimeError("authorization integration branch drift")
        if str(authorization.get("canonical_root") or "") != str(controller_root):
            raise RuntimeError("authorization integration root drift")
        if self._git(["rev-parse", f"{candidate_sha}^{{commit}}"], controller_root) != candidate_sha:
            raise RuntimeError("candidate commit is not present in controller repository")
        # Fully qualified everywhere: a same-named tag must never win (#2230).
        branch_ref = f"refs/heads/{integration_branch}"
        branch_head = self._git(["rev-parse", f"{branch_ref}^{{commit}}"], controller_root)
        if branch_head != expected_head:
            raise RuntimeError("integration branch HEAD drift")
        # Only a separate detached Controller (#1939) may hold pending Task
        # Cards: apply there is a pure ref update.  A primary checkout or any
        # checkout on a branch stays fully strict.
        self._require_clean_controller(
            controller_root,
            allow_pending_task_cards=self._is_detached_linked_worktree(controller_root),
            message="canonical/integration worktree must be clean before apply",
        )

        auth_obj = (
            authorization
            if isinstance(authorization, IntegrationAuthorizationEnvelope)
            else IntegrationAuthorizationEnvelope(
                **{
                    "schema": "nexus.integration_authorization.v1",
                    "task_id": task_id,
                    "campaign_id": "campaign-default",
                    "task_card_hash": "0" * 64,
                    "candidate_commit": candidate_sha,
                    "candidate_receipt_hash": "0" * 64,
                    "acceptance_receipt_hash": "0" * 64,
                    "canonical_root": str(controller_root),
                    "canonical_branch": integration_branch,
                    "expected_canonical_head": expected_head,
                    "canonical_dirty_baseline": "clean",
                    "integration_plan_hash": "0" * 64,
                    "action_set": tuple(authorization.get("action_set") or ()),
                    "cleanup_target_id": "target-default",
                    "cleanup_target_path": str(controller_root),
                    "durable_ref": f"refs/heads/nexus/task/{task_id}",
                    "rollback": "none",
                    "issued_at": "2026-08-01T00:00:00+00:00",
                    **{k: v for k, v in dict(authorization).items() if k != "authorization_hash"},
                }
            )
        )
        current_universe = {
            "task_id": task_id,
            "campaign_id": str(state.get("campaign_id") or contract.get("campaign_id") or auth_obj.campaign_id),
            "task_card_hash": str(state.get("task_card_hash") or contract.get("task_card_hash") or auth_obj.task_card_hash),
            "candidate_commit": candidate_sha,
            "candidate_receipt_hash": str(packet.get("candidate_receipt_hash") or auth_obj.candidate_receipt_hash),
            "acceptance_receipt_hash": str(acceptance.get("receipt_hash") or auth_obj.acceptance_receipt_hash),
            "canonical_root": str(controller_root),
            "canonical_branch": integration_branch,
            "expected_canonical_head": expected_head,
            "canonical_dirty_baseline": str(state.get("canonical_dirty_baseline") or auth_obj.canonical_dirty_baseline),
            "integration_plan_hash": str(state.get("integration_plan_hash") or auth_obj.integration_plan_hash),
            "cleanup_target_id": str((state.get("lease") or {}).get("target_id") or auth_obj.cleanup_target_id),
            "cleanup_target_path": str((state.get("lease") or {}).get("target_path") or auth_obj.cleanup_target_path),
            "durable_ref": str(state.get("candidate_ref") or auth_obj.durable_ref),
            "attempt_id": str(state.get("attempt_id") or auth_obj.attempt_id),
            "candidate_tree_sha": str(packet.get("candidate_tree_sha") or auth_obj.candidate_tree_sha),
            "candidate_state_hash": str(packet.get("candidate_state_hash") or auth_obj.candidate_state_hash),
            "reviewer_id": str(acceptance.get("reviewer_id") or auth_obj.reviewer_id),
            "verifier_artifact_hash": str(auth_obj.verifier_artifact_hash),
            "require_clean": auth_obj.require_clean,
            "strategy": auth_obj.strategy,
            "verification_commands_hash": auth_obj.verification_commands_hash,
            "post_apply_commands_hash": auth_obj.post_apply_commands_hash,
            "cleanup_requested": auth_obj.cleanup_requested,
            "approval_scope": auth_obj.approval_scope,
        }
        try:
            auth_obj.validate_current(current_universe)
        except ValueError as exc:
            raise RuntimeError(f"authorization validation failed: {exc}") from exc

        admitted_verifiers = self._bound_manifest(state, contract)

        staging_base = Path(staging_root).expanduser().resolve()
        staging_path = staging_base / task_id
        if os.path.lexists(staging_path):
            raise RuntimeError("integration staging Target already exists")
        # Post-apply verification runs in its own throwaway worktree at the
        # integrated commit, never in the Controller (#2230 F3).
        post_apply_parent = staging_base / ".post-apply"
        post_apply_path = post_apply_parent / task_id
        if post_apply_commands and (
            os.path.islink(post_apply_parent) or os.path.lexists(post_apply_path)
        ):
            raise RuntimeError("post-apply verification Target already exists")
        staging_path.parent.mkdir(parents=True, exist_ok=True)
        self._git(["worktree", "add", "--detach", str(staging_path), expected_head], controller_root)
        owned_worktrees: list[Path] = [staging_path]
        staging_sha = ""
        applied = False
        post_apply_verified = False
        branch_head_after = expected_head
        failure: Exception | None = None
        try:
            self._git(["merge", "--no-ff", "--no-edit", candidate_sha], staging_path)
            self._execute_manifest(admitted_verifiers, staging_path)
            staging_sha = self._git(["rev-parse", "HEAD"], staging_path)
            if apply:
                if self._git(["rev-parse", f"{branch_ref}^{{commit}}"], controller_root) != expected_head:
                    raise RuntimeError("integration branch HEAD drift before apply")
                current_branch = self._git(["branch", "--show-current"], controller_root)
                separate_controller = self._is_detached_linked_worktree(controller_root)
                self._require_clean_controller(
                    controller_root,
                    allow_pending_task_cards=separate_controller,
                    message="canonical/integration worktree must be clean before apply",
                )
                if current_branch == integration_branch:
                    try:
                        self._require_sole_controller_checkout(
                            controller_root, integration_branch
                        )
                    except RuntimeError as exc:
                        raise RuntimeError(
                            f"INTEGRATION_BRANCH_REFUSED_AT_APPLY: {exc}"
                        ) from exc
                    self._git(["merge", "--ff-only", staging_sha], controller_root)
                else:
                    # Whatever the shape, the branch rules are re-proved right
                    # before the ref moves: a worktree may have checked out
                    # (or started rebasing) the branch, or turned it into a
                    # symref, since the closure was bound (#2230).
                    refused = "INTEGRATION_BRANCH_REFUSED_AT_APPLY"
                    try:
                        self._require_integration_branch_not_in_use(
                            controller_root, integration_branch
                        )
                        live_head = (
                            self.separate_controller_integration_head(
                                controller_root, integration_branch
                            )
                            if separate_controller
                            else expected_head
                        )
                    except RuntimeError as exc:
                        raise RuntimeError(f"{refused}: {exc}") from exc
                    if live_head != expected_head:
                        raise RuntimeError(f"{refused}: shape or head drift")
                    self._git(
                        ["update-ref", "--no-deref", branch_ref, staging_sha, expected_head],
                        controller_root,
                    )
                applied = True
                exact_head = self._git(["rev-parse", f"{branch_ref}^{{commit}}"], controller_root)
                branch_head_after = exact_head
                if exact_head != staging_sha:
                    raise RuntimeError("applied HEAD is not the verified staging commit")
                self._git(["merge-base", "--is-ancestor", candidate_sha, exact_head], controller_root)
                self._require_clean_controller(
                    controller_root,
                    allow_pending_task_cards=separate_controller,
                    message="canonical/integration worktree is dirty after apply",
                )
                if post_apply_commands:
                    post_apply_parent.mkdir(exist_ok=True)
                    if os.path.islink(post_apply_parent) or os.path.lexists(post_apply_path):
                        raise RuntimeError("post-apply verification Target already exists")
                    owned_worktrees.append(post_apply_path)
                    self._git(
                        ["worktree", "add", "--detach", str(post_apply_path), exact_head],
                        controller_root,
                    )
                    if self._git(["rev-parse", "HEAD"], post_apply_path) != exact_head:
                        raise RuntimeError("post-apply worktree is not the integrated commit")
                    for command in post_apply_commands:
                        result = subprocess.run(
                            tuple(command), cwd=post_apply_path, capture_output=True, text=True
                        )
                        if result.returncode != 0:
                            raise RuntimeError(
                                f"post-apply verification failed: {' '.join(command)}"
                            )
                post_apply_verified = True
        except Exception as exc:
            failure = exc
        except BaseException:
            self._remove_owned_worktrees(owned_worktrees, controller_root)
            raise
        # Cleanup never masks the classified outcome: every owned worktree is
        # removed in its own try and a failure is attached as detail.
        cleanup_failures = self._remove_owned_worktrees(owned_worktrees, controller_root)
        cleanup_failure = "; ".join(cleanup_failures) or None
        if failure is not None or cleanup_failure is not None:
            if isinstance(failure, IntegrationExecutionError):
                if cleanup_failure is not None:
                    failure.cleanup_failure = cleanup_failure
                raise failure
            try:
                branch_head_after = self._git(["rev-parse", f"{branch_ref}^{{commit}}"], controller_root)
            except RuntimeError:
                branch_head_after = expected_head
            if failure is not None:
                stage = "POST_APPLY_VERIFICATION" if applied else "PRE_APPLY"
                reason = str(failure)
            else:
                stage = "POST_APPLY_CLEANUP" if applied else "PRE_APPLY"
                reason = f"integration worktree cleanup failed: {cleanup_failure}"
            raise IntegrationExecutionError(
                stage=stage,
                branch_head_before=expected_head,
                branch_head_after=branch_head_after,
                staging_commit_sha=staging_sha or None,
                candidate_commit_sha=candidate_sha,
                merge_performed=applied,
                post_apply_verified=post_apply_verified,
                failure_reason=reason,
                cleanup_failure=cleanup_failure,
            ) from failure
        final_head = self._git(["rev-parse", f"{branch_ref}^{{commit}}"], controller_root)
        return IntegrationReceipt(
            schema="nexus.integration_receipt.v1", task_id=task_id,
            integration_branch=integration_branch,
            source_branch=str((state.get("lease") or {}).get("target_branch") or ""),
            candidate_commit_sha=candidate_sha,
            integration_base_sha=expected_head,
            integration_commit_sha=final_head,
            verifier_passed=True,
            merge_performed=applied,
            push_performed=False,
            worktree_removed=True,
            staging_commit_sha=staging_sha,
            post_apply_verified=bool(applied),
            acceptance_receipt_hash=str(authorization.get("acceptance_receipt_hash") or acceptance.get("receipt_hash") or "") or None,
            authorization_hash=str(authorization.get("authorization_hash") or "") or None,
            task_card_hash=str(authorization.get("task_card_hash") or "") or None,
            candidate_tree_sha=str(authorization.get("candidate_tree_sha") or "") or None,
            candidate_state_hash=str(authorization.get("candidate_state_hash") or "") or None,
            verified_receipt_hash=str(packet.get("verified_receipt_hash") or "") or None,
            branch_head_before=expected_head,
            branch_head_after=final_head,
            candidate_is_ancestor=True,
            staging_verified=True,
        )
