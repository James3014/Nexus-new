from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_FLEET_LANES = ("security_sentry", "logic_breaker", "ghost_regression")
SCHEMA_VERSION = "ultra-review.v1"
GHOST_REGRESSION_TIMEOUT_SEC = 30
LOGIC_BREAKER_TIMEOUT_SEC = 15
TEST_DIR_BY_SOURCE_DIR = {
    "app": "tests/app",
    "core": "tests/core",
    "delivery": "tests/delivery",
    "engine": "tests/engine",
    "health": "tests/health",
    "orchestrator": "tests/orchestrator",
    "research": "tests/research",
    "services": "tests/services",
}
SECURITY_PATTERNS = (
    ("secret_literal", re.compile(r"(?i)(api[_-]?key|secret|token|password)\s*=\s*['\"][^'\"]{8,}['\"]")),
    ("shell_true_subprocess", re.compile(r"subprocess\.(run|Popen|call|check_output)\([^#\n]*shell\s*=\s*True")),
    ("unsafe_delete", re.compile(r"shutil\.rmtree\([^#\n]*(ignore_errors\s*=\s*True|force|/tmp|\*)")),
)
SECURITY_REPRO_TIMEOUT_SEC = 10
RUNTIME_ARTIFACT_PREFIXES = (
    ".nexus/reports/",
    ".nexus-swarm-",
)
BENCHMARK_ONLY_ENV_VARS = (
    "NEXUS_LLM_CANDIDATE_CAP",
)
ULTRA_REUSE_WORKTREE_ENV = "NEXUS_ULTRA_REUSE_WORKTREE"
ULTRA_SKIP_GHOST_ENV = "NEXUS_ULTRA_SKIP_GHOST_REGRESSION"
TOOL_CHECK_TIMEOUT_SEC = 60
# Static-analysis rules that are noise for a diff review (asserts, subprocess import,
# argument-list subprocess calls, partial executable paths, non-crypto random).
BANDIT_IGNORED_TESTS = frozenset({"B101", "B311", "B404", "B603", "B607"})
RUFF_SECURITY_IGNORED_CODES = frozenset({"S101", "S311", "S404", "S603", "S607"})
# pyflakes/pycodestyle subset that means the changed code cannot run as written:
# syntax errors, invalid comparisons/statements, undefined names.
RUFF_LOGIC_SELECT = "E9,F63,F7,F82"
SECURITY_BLOCKING_SEVERITIES = frozenset({"medium", "high", "critical"})
REVIEW_MODE = "review"
# Set in the ghost-regression pytest environment: a review started from inside a review's
# test run (a test that reviews "."), would review the sandbox again; refuse instead.
ULTRA_REVIEW_NESTED_ENV = "NEXUS_ULTRA_REVIEW_IN_PROGRESS"
# Lane subprocesses (tools, repro scripts, the test re-run) see only these caller variables;
# everything else (tokens, credentials, provider keys) is dropped.
SANDBOX_ENV_ALLOWLIST = ("PATH", "LANG", "LC_ALL", "LC_CTYPE", "VIRTUAL_ENV", "SYSTEMROOT")
# Read-denied even inside the OS sandbox (credential stores under $HOME).
SANDBOX_DENIED_HOME_PATHS = (
    ".ssh",
    ".gnupg",
    ".aws",
    ".netrc",
    ".git-credentials",
    ".config/gh",
    ".config/gcloud",
    ".docker",
    ".kube",
    ".claude",
    ".codex",
    "Library/Keychains",
)
# Files whose change alters how the ghost-regression test run itself behaves.
TEST_HARNESS_FILES = ("conftest.py", "pytest.ini", "tox.ini", "setup.cfg", "pyproject.toml", "sitecustomize.py", "usercustomize.py")
_OS_SANDBOX_PROBE: dict[str, bool] = {}
# Every path interpolated into the sandbox-exec (SBPL) profile must match this: no quote,
# backslash, paren, whitespace or control character can reach an SBPL string literal, so
# no PR-, branch- or user-derived text can close a literal and rewrite the policy.
SBPL_SAFE_PATH = re.compile(r"^/[A-Za-z0-9._/@+-]*$")
# System locations the confined interpreter needs to start (dyld, frameworks, locale,
# timezone, devices). Nothing under a user's home directory.
SANDBOX_SYSTEM_READ_ROOTS = (
    "/usr/lib",
    "/usr/share",
    "/System/Library",
    "/System/Cryptexes",
    "/Library/Apple",
    "/private/var/db/dyld",
    "/private/var/db/timezone",
    "/private/etc/localtime",
    "/private/etc/ssl",
    "/dev",
)


def os_sandbox_available() -> bool:
    """True when an OS-level barrier (macOS sandbox-exec) can confine lane subprocesses.

    ``NEXUS_ULTRA_REVIEW_DISABLE_OS_SANDBOX=1`` only removes the barrier (fail closed), it
    can never grant one; it lets non-macOS behaviour be exercised anywhere.
    """
    if os.getenv("NEXUS_ULTRA_REVIEW_DISABLE_OS_SANDBOX", "").strip() == "1":
        return False
    if "sandbox-exec" not in _OS_SANDBOX_PROBE:
        ok = False
        if sys.platform == "darwin" and shutil.which("sandbox-exec"):
            try:
                ok = (
                    subprocess.run(  # noqa: S603 - fixed argv probe
                        ["sandbox-exec", "-p", "(version 1) (allow default)", "/usr/bin/true"],
                        capture_output=True,
                        timeout=5,
                        check=False,
                    ).returncode
                    == 0
                )
            except (OSError, subprocess.SubprocessError):
                ok = False
        _OS_SANDBOX_PROBE["sandbox-exec"] = ok
    return _OS_SANDBOX_PROBE["sandbox-exec"]
DRY_RUN_MODE = "dry-run"


class UltraReviewError(RuntimeError):
    """Raised when ultra-review cannot produce a trustworthy report."""


def sbpl_path(path: Path | str) -> str:
    """Return ``path`` resolved and absolute, safe to embed in an SBPL string literal.

    Raises UltraReviewError (fail closed) instead of escaping: a path that needs escaping is
    never placed in the sandbox policy.
    """

    text = str(path)
    if not text or not os.path.isabs(text):
        raise UltraReviewError("sandbox_path_not_absolute")
    resolved = str(Path(text).resolve())
    if not SBPL_SAFE_PATH.fullmatch(resolved) or "/../" in resolved + "/" or resolved.endswith("/.."):
        raise UltraReviewError("sandbox_path_unsafe_for_policy")
    return resolved


def _write_no_follow(target: Path, data: bytes) -> None:
    """Write ``data`` to ``target`` without following a symlink at (or replacing into) it."""

    if target.is_symlink() or target.exists():
        if target.is_dir() and not target.is_symlink():
            raise UltraReviewError(f"refusing_to_overwrite_directory:{target.name}")
        target.unlink()
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(target, flags, 0o600)
    with os.fdopen(fd, "wb") as handle:
        handle.write(data)


class UltraReviewService:
    def __init__(self, project_root: Path | str):
        self.project_root = Path(project_root).resolve()

    def run(
        self,
        *,
        dry_run: bool = True,
        task: str = "",
        base_ref: str = "HEAD",
        report_path: Path | str = ".nexus/reports/ultra_review_report.json",
        sandbox_root: Path | str = ".nexus/reports/ultra_review/sandboxes",
    ) -> dict[str, Any]:
        mode = DRY_RUN_MODE if dry_run else REVIEW_MODE
        try:
            if os.getenv(ULTRA_REVIEW_NESTED_ENV, "").strip():
                raise UltraReviewError("nested_ultra_review_refused")
            return self._run(
                dry_run=dry_run,
                task=task,
                base_ref=base_ref,
                report_path=report_path,
                sandbox_root=sandbox_root,
            )
        except (UltraReviewError, OSError, subprocess.SubprocessError) as exc:
            # Fail closed with a reason instead of an unhandled traceback.
            out_path = self._resolve(report_path)
            payload = {
                "schema_version": SCHEMA_VERSION,
                "run_id": "",
                "status": "BLOCKED",
                "blocked_reason": f"{type(exc).__name__}: {exc}"[:500],
                "gate_passed": False,
                "mode": mode,
                "task": task,
                "base_ref": base_ref,
                "project_root": str(self.project_root),
                "fleet": [],
                "findings": [],
                "created_at": datetime.now(timezone.utc).isoformat(),
                "report_path": str(out_path),
            }
            try:
                out_path.parent.mkdir(parents=True, exist_ok=True)
                out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
            except OSError:
                payload["report_path"] = ""
            return payload

    def _run(
        self,
        *,
        dry_run: bool,
        task: str,
        base_ref: str,
        report_path: Path | str,
        sandbox_root: Path | str,
    ) -> dict[str, Any]:
        mode = DRY_RUN_MODE if dry_run else REVIEW_MODE
        run_id = self._run_id()
        sandbox_path = self._prepare_sandbox(Path(sandbox_root), run_id)
        progress_path = sandbox_path / "progress.jsonl"
        progress: list[dict[str, Any]] = []
        self._record_progress(progress, progress_path, "sandbox_prepared", sandbox_path=str(sandbox_path))
        diff_text = self._capture_diff(base_ref)
        status_text = self._capture_status()

        diff_path = sandbox_path / "changes.diff"
        diff_path.write_text(diff_text, encoding="utf-8")
        (sandbox_path / "git_status.txt").write_text(status_text, encoding="utf-8")
        changed_files = self._changed_files(diff_text)
        self._record_progress(
            progress,
            progress_path,
            "diff_captured",
            changed_files=len(changed_files),
            bytes=len(diff_text.encode("utf-8")),
        )

        regression_map = self._derive_regression_candidate_map(diff_text)
        test_candidates = self._existing_regression_candidates(regression_map)
        execution_root, mirror_metadata = self._prepare_execution_workspace(sandbox_path, diff_path=diff_path)
        self._bind_sandbox(sandbox_path=sandbox_path, execution_root=execution_root)
        security_sentry = self._run_security_sentry(
            diff_text=diff_text,
            execution_root=execution_root,
            sandbox_path=sandbox_path,
        )
        self._record_progress(
            progress,
            progress_path,
            "security_sentry_complete",
            passed=security_sentry["passed"],
            verified_findings=security_sentry["verified_findings"],
            unverified_observations=security_sentry["unverified_observations"],
        )
        logic_breaker = self._run_logic_breaker(
            diff_path=diff_path,
            execution_root=execution_root,
            sandbox_path=sandbox_path,
        )
        self._record_progress(progress, progress_path, "logic_breaker_complete", passed=logic_breaker["passed"])
        ghost_regression = self._run_ghost_regression(test_candidates, execution_root=execution_root)
        self._record_progress(progress, progress_path, "ghost_regression_complete", passed=ghost_regression["passed"])
        findings = [*security_sentry["findings"], *logic_breaker["findings"], *ghost_regression["findings"]]
        sub_checks_passed = bool(security_sentry["passed"] and logic_breaker["passed"] and ghost_regression["passed"])
        fleet = self._build_dry_run_fleet(test_candidates, security_sentry, logic_breaker, ghost_regression)
        out_path = self._resolve(report_path)
        self._record_progress(progress, progress_path, "report_written", report_path=str(out_path))
        lanes_blocked = [
            lane_name
            for lane_name, lane in (
                ("security_sentry", security_sentry),
                ("logic_breaker", logic_breaker),
            )
            if lane.get("unavailable_checks")
        ]
        mirror_ok = bool(mirror_metadata.get("diff_applied", False))
        blocked_reason = ""
        if not changed_files:
            blocked_reason = "no_diff_to_review"
        elif not mirror_ok:
            blocked_reason = "sandbox_mirror_diff_not_applied"
        elif lanes_blocked:
            blocked_reason = "check_tool_unavailable:" + ",".join(lanes_blocked)
        elif ghost_regression.get("blocked"):
            blocked_reason = f"ghost_regression_not_executed:{ghost_regression.get('blocked_reason')}"
        elif ghost_regression.get("execution_mode") == "skipped_by_env":
            blocked_reason = "ghost_regression_not_executed:skipped_by_env"
        elif not ghost_regression.get("executed_tests"):
            blocked_reason = "ghost_regression_not_executed:no_mapped_tests"
        elif not security_sentry.get("executed_checks") or not logic_breaker.get("executed_checks"):
            blocked_reason = "lane_not_executed"
        if dry_run:
            # Dry-run is advisory: checks execute but a clean dry-run is NOT_VERIFIED, never a pass.
            gate_passed = False
            status = "DRY_RUN_NOT_VERIFIED" if sub_checks_passed else "DRY_RUN_FAIL"
        else:
            # Review mode: the gate is the conjunction of executed lane results; fail closed when
            # there is nothing to review or a required check could not run.
            if blocked_reason:
                gate_passed = False
                status = "BLOCKED"
            else:
                gate_passed = sub_checks_passed
                status = "PASS" if sub_checks_passed else "FAIL"
        worktree_cleanup = self._cleanup_execution_worktree(execution_root, mirror_metadata) if not dry_run else {}
        payload = {
            "schema_version": SCHEMA_VERSION,
            "run_id": run_id,
            "status": status,
            "blocked_reason": blocked_reason if not dry_run else "",
            "gate_passed": gate_passed,
            "mode": mode,
            "worktree_cleanup": worktree_cleanup,
            "isolation": self.sandbox_isolation(),
            "task": task,
            "base_ref": base_ref,
            "project_root": str(self.project_root),
            "sandbox_path": str(sandbox_path),
            "sandbox_mirror": mirror_metadata,
            "artifacts": {
                "diff": str(diff_path),
                "git_status": str(sandbox_path / "git_status.txt"),
                "progress_log": str(progress_path),
            },
            "diff": {
                "bytes": len(diff_text.encode("utf-8")),
                "changed_files": changed_files,
                "has_worktree_delta": bool(diff_text.strip() or status_text.strip()),
            },
            "fleet": fleet,
            "findings": findings,
            "security_sentry": {k: v for k, v in security_sentry.items() if k != "findings"},
            "logic_breaker": {k: v for k, v in logic_breaker.items() if k != "findings"},
            "ghost_regression": {k: v for k, v in ghost_regression.items() if k != "findings"},
            "summary": {
                "security_verified_findings": security_sentry["verified_findings"],
                "security_unverified_observations": security_sentry["unverified_observations"],
                "logic_breaker_passed": logic_breaker["passed"],
                "ghost_regression_passed": ghost_regression["passed"],
                "executed_regression_tests": len(ghost_regression["executed_tests"]),
                "verified_findings": sum(1 for finding in findings if finding.get("state") == "VERIFIED_FINDING"),
            },
            "progress": progress,
            "regression_candidate_map": regression_map,
            "verification": {
                "verified_findings": sum(1 for finding in findings if finding.get("state") == "VERIFIED_FINDING"),
                "unverified_observations": sum(1 for finding in findings if finding.get("state") != "VERIFIED_FINDING"),
                "reproduction_required": True,
                "negative_test_execution": "executed" if test_candidates else "not_applicable_no_candidates",
            },
            "created_at": datetime.now(timezone.utc).isoformat(),
            "report_path": str(out_path),
        }

        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        return payload

    def _record_progress(self, progress: list[dict[str, Any]], progress_path: Path, stage: str, **fields: Any) -> None:
        event = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "stage": stage,
            **fields,
        }
        progress.append(event)
        progress_path.parent.mkdir(parents=True, exist_ok=True)
        with progress_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=False, default=str) + "\n")

    def _prepare_sandbox(self, sandbox_root: Path, run_id: str) -> Path:
        root = self._resolve(sandbox_root)
        root.mkdir(parents=True, exist_ok=True)
        sandbox_path = root / run_id
        sandbox_path.mkdir(parents=False, exist_ok=False)
        (sandbox_path / "README.txt").write_text(
            "Nexus ultra-review dry-run sandbox. Contains captured diff artifacts only.\n",
            encoding="utf-8",
        )
        return sandbox_path

    def _benchmark_env_keys_removed(self) -> list[str]:
        removed: list[str] = []
        for key in BENCHMARK_ONLY_ENV_VARS:
            if key in os.environ:
                removed.append(key)
        return removed

    def _prepare_execution_workspace(self, sandbox_path: Path, *, diff_path: Path) -> tuple[Path, dict[str, Any]]:
        if os.getenv(ULTRA_REUSE_WORKTREE_ENV, "").strip().lower() in {"1", "true", "yes", "on"}:
            reusable_root = self._resolve(".nexus/reports/ultra_review/reusable_worktree")
            reusable_root.mkdir(parents=True, exist_ok=True)
            execution_root = reusable_root / "worktree"
            metadata = self._prepare_reusable_git_worktree(execution_root, diff_path=diff_path, sandbox_path=sandbox_path)
            if metadata.get("strategy") == "git_worktree_reuse":
                return execution_root, metadata
        execution_root = sandbox_path / "worktree"
        metadata = self._prepare_git_worktree_mirror(execution_root, diff_path=diff_path, sandbox_path=sandbox_path)
        if metadata.get("strategy") == "git_worktree":
            return execution_root, metadata

        fallback_metadata = self._copy_execution_workspace(execution_root, sandbox_path)
        fallback_metadata["fallback_reason"] = metadata.get("fallback_reason", "")
        return execution_root, fallback_metadata

    def _prepare_reusable_git_worktree(self, execution_root: Path, *, diff_path: Path, sandbox_path: Path) -> dict[str, Any]:
        if not (execution_root / ".git").exists():
            add_cmd = ["git", "worktree", "add", "--detach", str(execution_root), "HEAD"]
            add = subprocess.run(add_cmd, cwd=self.project_root, capture_output=True, text=True, check=False)
            if add.returncode != 0:
                return {
                    "strategy": "copytree",
                    "fallback_reason": (add.stderr or add.stdout or "reusable git worktree add failed")[-1000:],
                }
            created = True
        else:
            created = False

        reset_cmd = ["git", "reset", "--hard", "HEAD"]
        clean_cmd = ["git", "clean", "-fd"]
        reset = subprocess.run(reset_cmd, cwd=execution_root, capture_output=True, text=True, check=False)
        clean = subprocess.run(clean_cmd, cwd=execution_root, capture_output=True, text=True, check=False)
        if reset.returncode != 0 or clean.returncode != 0:
            return {
                "strategy": "copytree",
                "fallback_reason": (
                    reset.stderr
                    or clean.stderr
                    or reset.stdout
                    or clean.stdout
                    or "reusable git worktree reset/clean failed"
                )[-1000:],
            }

        diff_has_content = bool(diff_path.read_text(encoding="utf-8").strip()) if diff_path.exists() else False
        if diff_has_content:
            apply_cmd = ["git", "apply", "--binary", str(diff_path)]
            apply = subprocess.run(apply_cmd, cwd=execution_root, capture_output=True, text=True, check=False)
            if apply.returncode != 0:
                return {
                    "strategy": "copytree",
                    "fallback_reason": (apply.stderr or apply.stdout or "reusable git apply failed")[-1000:],
                }

        untracked_overlay_count = self._overlay_untracked_files(execution_root, sandbox_path=sandbox_path)
        return {
            "strategy": "git_worktree_reuse",
            "diff_applied": True,
            "empty_diff": not diff_has_content,
            "reused": not created,
            "untracked_overlay_count": untracked_overlay_count,
        }

    def _prepare_git_worktree_mirror(self, execution_root: Path, *, diff_path: Path, sandbox_path: Path) -> dict[str, Any]:
        add_cmd = ["git", "worktree", "add", "--detach", str(execution_root), "HEAD"]
        add = subprocess.run(add_cmd, cwd=self.project_root, capture_output=True, text=True, check=False)
        if add.returncode != 0:
            return {
                "strategy": "copytree",
                "fallback_reason": (add.stderr or add.stdout or "git worktree add failed")[-1000:],
            }

        diff_has_content = bool(diff_path.read_text(encoding="utf-8").strip()) if diff_path.exists() else False
        if not diff_has_content:
            untracked_overlay_count = self._overlay_untracked_files(execution_root, sandbox_path=sandbox_path)
            return {
                "strategy": "git_worktree",
                "diff_applied": True,
                "command": " ".join(add_cmd),
                "untracked_overlay_count": untracked_overlay_count,
                "empty_diff": True,
            }

        apply_cmd = ["git", "apply", "--index", "--binary", str(diff_path)]
        apply = subprocess.run(apply_cmd, cwd=execution_root, capture_output=True, text=True, check=False)
        if apply.returncode != 0:
            apply_cmd = ["git", "apply", "--binary", str(diff_path)]
            apply = subprocess.run(apply_cmd, cwd=execution_root, capture_output=True, text=True, check=False)
        if apply.returncode != 0:
            subprocess.run(
                ["git", "worktree", "remove", "--force", str(execution_root)],
                cwd=self.project_root,
                capture_output=True,
                text=True,
                check=False,
            )
            return {
                "strategy": "copytree",
                "diff_applied": False,
                "fallback_reason": (apply.stderr or apply.stdout or "git apply failed")[-1000:],
                "command": " ".join(add_cmd),
            }

        untracked_overlay_count = self._overlay_untracked_files(execution_root, sandbox_path=sandbox_path)
        return {
            "strategy": "git_worktree",
            "diff_applied": True,
            "command": " ".join(add_cmd),
            "untracked_overlay_count": untracked_overlay_count,
        }

    def _overlay_untracked_files(self, execution_root: Path, *, sandbox_path: Path) -> int:
        ls = subprocess.run(
            ["git", "ls-files", "--others", "--exclude-standard", "-z"],
            cwd=self.project_root,
            capture_output=True,
            text=False,
            check=False,
        )
        if ls.returncode != 0:
            return 0
        count = 0
        for raw in ls.stdout.split(b"\0"):
            if not raw:
                continue
            rel = raw.decode("utf-8", errors="ignore")
            if self._is_runtime_artifact_path(rel):
                continue
            source = self.project_root / rel
            target = execution_root / rel
            try:
                if source.resolve().is_relative_to(sandbox_path.resolve()):
                    continue
            except OSError:
                continue
            if source.is_symlink() or not source.is_file():
                # Never follow an untracked symlink into the sandbox (it could point at a
                # credential file outside the checkout).
                continue
            try:
                if not source.resolve().is_relative_to(self.project_root):
                    continue
            except OSError:
                continue
            if not self._target_inside(target, execution_root):
                # A PR-tracked symlinked directory (or file) at the target must not redirect
                # the overlay write outside the mirror.
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            if not self._target_inside(target, execution_root):
                continue
            _write_no_follow(target, source.read_bytes())
            count += 1
        return count

    @staticmethod
    def _target_inside(target: Path, execution_root: Path) -> bool:
        """True when no existing component of ``target`` below ``execution_root`` is a symlink."""

        root = execution_root.resolve()
        try:
            rel_parts = target.relative_to(execution_root).parts
        except ValueError:
            return False
        if ".." in rel_parts:
            return False
        current = execution_root
        for part in rel_parts:
            current = current / part
            if current.is_symlink():
                return False
        parent = target.parent.resolve() if target.parent.exists() else None
        return parent is None or parent == root or root in parent.parents

    def _copy_execution_workspace(self, execution_root: Path, sandbox_path: Path) -> dict[str, Any]:
        ignored_patterns = shutil.ignore_patterns(
            ".git",
            ".venv",
            ".nexus",
            ".pytest_cache",
            "__pycache__",
            "MagicMock",
            "compliance/audit",
        )

        def ignore(path: str, names: list[str]) -> set[str]:
            ignored = set(ignored_patterns(path, names))
            # Never copy a symlink (dangling or not): following it could pull a file from
            # outside the checkout (for example a credential) into the mirror.
            ignored.update(name for name in names if os.path.islink(os.path.join(path, name)))
            current = Path(path).resolve()
            if current == self.project_root:
                try:
                    sandbox_anchor = sandbox_path.relative_to(self.project_root).parts[0]
                except ValueError:
                    sandbox_anchor = ""
                if sandbox_anchor in names:
                    ignored.add(sandbox_anchor)
            return ignored

        # Runtime-local links (for example user-specific Gemini state or an
        # unbuilt native extension) may be dangling in the source checkout.
        # They are not review inputs and must not make the fallback mirror
        # fail before the actual diff is evaluated.
        shutil.copytree(
            self.project_root,
            execution_root,
            ignore=ignore,
            # Defence in depth: symlinks are already ignored above; never dereference one.
            symlinks=True,
            ignore_dangling_symlinks=True,
        )
        return {"strategy": "copytree", "diff_applied": True}

    def _bind_sandbox(self, *, sandbox_path: Path, execution_root: Path) -> None:
        home = sandbox_path / "home"
        tmp = sandbox_path / "tmp"
        home.mkdir(parents=True, exist_ok=True)
        tmp.mkdir(parents=True, exist_ok=True)
        self._sandbox_ctx = {
            "sandbox_path": Path(sbpl_path(sandbox_path.resolve())),
            "execution_root": Path(sbpl_path(execution_root.resolve())),
            "home": Path(sbpl_path(home.resolve())),
            "tmp": Path(sbpl_path(tmp.resolve())),
        }

    def _sandbox_env(self) -> dict[str, str]:
        ctx = getattr(self, "_sandbox_ctx", None) or {}
        env = {key: os.environ[key] for key in SANDBOX_ENV_ALLOWLIST if key in os.environ}
        # PATH never resolves into the reviewed checkout, the mirror or the sandbox, so a
        # PR-supplied executable cannot shadow a tool. Every Python lane runs with -I, so
        # PYTHONPATH is not set at all (the ghost re-run gets the mirror via pytest's
        # ``pythonpath`` ini override after interpreter start-up).
        if "PATH" in env:
            env["PATH"] = os.pathsep.join(
                part for part in env["PATH"].split(os.pathsep) if part and os.path.isabs(part) and not self._in_untrusted_tree(part)
            )
        if "VIRTUAL_ENV" in env and self._in_untrusted_tree(env["VIRTUAL_ENV"]):
            env.pop("VIRTUAL_ENV")
        env["HOME"] = str(ctx.get("home") or "")
        env["TMPDIR"] = str(ctx.get("tmp") or "")
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        env["PYTHONNOUSERSITE"] = "1"
        env["NEXUS_SANDBOX_NO_NETWORK"] = "1"
        env[ULTRA_REVIEW_NESTED_ENV] = "1"
        return env

    def _sandbox_profile(self) -> str:
        """SBPL policy for one lane command (last matching rule wins).

        Reads: default-deny; only the sandbox/mirror, the trusted interpreter prefixes and
        import roots, and fixed system locations are readable. ``$HOME`` is denied before
        those allows, and credential stores are denied again last, so they stay unreadable
        even if an allowed root contains them. Every interpolated path goes through
        ``sbpl_path`` (absolute, resolved, ``SBPL_SAFE_PATH``) or the profile is refused.
        """

        ctx = getattr(self, "_sandbox_ctx", None) or {}
        if not ctx.get("execution_root") or not ctx.get("sandbox_path"):
            raise UltraReviewError("sandbox_not_bound")
        writable = [sbpl_path(ctx["execution_root"]), sbpl_path(ctx["sandbox_path"])]
        real_home = sbpl_path(Path(os.path.expanduser("~")).resolve())
        denied = " ".join(f'(subpath "{sbpl_path(Path(real_home) / rel)}")' for rel in SANDBOX_DENIED_HOME_PATHS)
        writes = " ".join(f'(subpath "{path}")' for path in writable)
        readable = " ".join(f'(subpath "{path}")' for path in self._sandbox_read_roots())
        return "\n".join(
            [
                "(version 1)",
                "(deny default)",
                "(allow process-fork)",
                "(allow process-exec*)",
                f'(deny file-read* (subpath "{real_home}"))',
                "(allow file-read-metadata)",
                # The root directory entry itself (dyld/realpath walk), not its subtree.
                f'(allow file-read* (literal "/") {readable})',
                "(allow sysctl-read)",
                "(allow mach-lookup)",
                "(allow ipc-posix-shm)",
                "(allow signal (target self))",
                "(deny network*)",
                f'(allow file-write* {writes} (literal "/dev/null") (literal "/dev/tty") (literal "/dev/dtracehelper"))',
                f"(deny file-read* {denied})",
            ]
        )

    def _sandbox_read_roots(self) -> list[str]:
        ctx = getattr(self, "_sandbox_ctx", None) or {}
        # Required roots fail closed when unsafe for the policy.
        roots = {sbpl_path(ctx["execution_root"]), sbpl_path(ctx["sandbox_path"])}
        roots.update({sbpl_path(Path(sys.prefix).resolve()), sbpl_path(Path(sys.base_prefix).resolve())})
        roots.update(path for path in SANDBOX_SYSTEM_READ_ROOTS if os.path.exists(path))
        for entry in sys.path:
            if not entry or not os.path.isabs(entry):
                continue
            candidate = Path(entry).resolve()
            # The reviewed checkout itself is never an extra readable import root.
            if self._in_untrusted_tree(candidate) or not candidate.is_dir():
                continue
            try:
                roots.add(sbpl_path(candidate))
            except UltraReviewError:
                # Optional root: leaving it unreadable is the safe direction.
                continue
        return sorted(roots)

    def _in_untrusted_tree(self, path: Path | str) -> bool:
        """True when ``path`` resolves into the reviewed checkout, the mirror or the sandbox."""

        ctx = getattr(self, "_sandbox_ctx", None) or {}
        candidate = Path(path).resolve()
        for root in (self.project_root, ctx.get("execution_root"), ctx.get("sandbox_path")):
            if not root:
                continue
            root_path = Path(root).resolve()
            if candidate == root_path or root_path in candidate.parents:
                return True
        return False

    def _trusted_interpreter(self) -> str:
        """The reviewer's own interpreter; refused if it lives in the mirror or the sandbox."""

        ctx = getattr(self, "_sandbox_ctx", None) or {}
        interpreter = Path(sys.executable).resolve()
        for root in (ctx.get("execution_root"), ctx.get("sandbox_path")):
            if root and (interpreter == Path(root) or Path(root) in interpreter.parents):
                raise UltraReviewError("interpreter_inside_reviewed_tree")
        return sys.executable

    def sandbox_isolation(self) -> dict[str, Any]:
        contained = os_sandbox_available()
        return {
            "barrier": "macos_sandbox_exec" if contained else "none",
            "network": "denied" if contained else "not_enforced",
            "writes_confined_to": [
                str((getattr(self, "_sandbox_ctx", None) or {}).get(key) or "")
                for key in ("execution_root", "sandbox_path")
            ]
            if contained
            else [],
            "env": "allowlist:" + ",".join(SANDBOX_ENV_ALLOWLIST) + "+HOME/TMPDIR in sandbox",
            "credential_paths_read_denied": list(SANDBOX_DENIED_HOME_PATHS) if contained else [],
        }

    def _sandboxed_run(self, cmd: list[str], *, cwd: Path, timeout: float) -> subprocess.CompletedProcess:
        """Run a lane command on PR-controlled content: scrubbed env, sandbox cwd, timeout,
        and (when available) an OS barrier denying network, credential reads and writes
        outside the sandbox. Never a shell; raises subprocess.TimeoutExpired on timeout."""
        argv = list(cmd)
        if not argv:
            raise UltraReviewError("empty_lane_command")
        if argv[0] == sys.executable:
            argv[0] = self._trusted_interpreter()
            if "-I" not in argv[1:2]:
                raise UltraReviewError("python_lane_not_isolated")
        ctx = getattr(self, "_sandbox_ctx", None) or {}
        resolved_cwd = Path(cwd).resolve()
        if not any(
            root and (resolved_cwd == Path(root) or Path(root) in resolved_cwd.parents)
            for root in (ctx.get("execution_root"), ctx.get("sandbox_path"))
        ):
            raise UltraReviewError("lane_cwd_outside_sandbox")
        cwd = resolved_cwd
        if os_sandbox_available():
            argv = ["sandbox-exec", "-p", self._sandbox_profile(), *argv]
        return subprocess.run(  # noqa: S603 - argv list, no shell
            argv,
            cwd=cwd,
            env=self._sandbox_env(),
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
        )

    def _cleanup_execution_worktree(self, execution_root: Path, mirror_metadata: dict[str, Any]) -> dict[str, Any]:
        """Remove the per-run git worktree registration (review artifacts stay in the sandbox)."""
        strategy = str(mirror_metadata.get("strategy") or "")
        if strategy == "git_worktree":
            removed = subprocess.run(
                ["git", "worktree", "remove", "--force", str(execution_root)],
                cwd=self.project_root,
                capture_output=True,
                text=True,
                check=False,
            )
            return {
                "strategy": strategy,
                "removed": removed.returncode == 0,
                "detail": (removed.stderr or removed.stdout or "")[-300:],
            }
        if strategy == "copytree" and execution_root.exists():
            shutil.rmtree(execution_root, ignore_errors=False)
            return {"strategy": strategy, "removed": True, "detail": ""}
        return {"strategy": strategy, "removed": False, "detail": "kept_for_reuse_or_missing"}

    def _added_lines(self, diff_text: str) -> dict[str, set[int]]:
        """New-side line numbers added by the diff, per changed file."""
        added: dict[str, set[int]] = {}
        current_file = ""
        new_line = 0
        for raw_line in diff_text.splitlines():
            if raw_line.startswith("diff --git "):
                current_file = self._path_from_diff_header(raw_line)
                new_line = 0
                continue
            if raw_line.startswith("@@"):
                parsed = re.search(r"\+(\d+)", raw_line)
                new_line = int(parsed.group(1)) - 1 if parsed else 0
                continue
            if raw_line.startswith("+++") or raw_line.startswith("---"):
                continue
            if raw_line.startswith("+"):
                new_line += 1
                if current_file:
                    added.setdefault(current_file, set()).add(new_line)
                continue
            if raw_line.startswith("-") or raw_line.startswith("\\"):
                continue
            if current_file:
                new_line += 1
        return added

    def _contained_path(self, rel: str, execution_root: Path) -> Path | None:
        """``execution_root/rel`` when it stays inside the worktree and is not a symlink."""
        root = execution_root.resolve()
        candidate = execution_root / rel
        if candidate.is_symlink():
            return None
        resolved = candidate.resolve()
        if resolved != root and root not in resolved.parents:
            return None
        return resolved

    def _uncontained_changed_files(self, diff_text: str, execution_root: Path) -> list[str]:
        return [
            rel
            for rel in self._changed_files(diff_text)
            if (execution_root / rel).exists() or (execution_root / rel).is_symlink() or ".." in Path(rel).parts
            if self._contained_path(rel, execution_root) is None
        ]

    def _changed_python_files(self, diff_text: str, execution_root: Path) -> list[str]:
        out: list[str] = []
        for rel in self._changed_files(diff_text):
            if not rel.endswith(".py"):
                continue
            contained = self._contained_path(rel, execution_root)
            if contained is not None and contained.is_file():
                out.append(rel)
        return out

    def _run_tool(self, cmd: list[str], *, cwd: Path) -> dict[str, Any]:
        try:
            result = self._sandboxed_run(cmd, cwd=cwd, timeout=TOOL_CHECK_TIMEOUT_SEC)
        except FileNotFoundError as exc:
            return {"available": False, "error": str(exc)[:300], "command": " ".join(cmd)}
        except subprocess.TimeoutExpired:
            return {"available": True, "timeout": True, "returncode": None, "stdout": "", "stderr": "", "command": " ".join(cmd)}
        stderr = result.stderr or ""
        if result.returncode != 0 and "No module named" in stderr:
            return {"available": False, "error": stderr.strip()[-300:], "command": " ".join(cmd)}
        return {
            "available": True,
            "timeout": False,
            "returncode": result.returncode,
            "stdout": result.stdout or "",
            "stderr": stderr,
            "command": " ".join(cmd),
        }

    def _relative_to_root(self, filename: str, execution_root: Path) -> str:
        path = Path(filename)
        if path.is_absolute():
            try:
                return path.resolve().relative_to(execution_root.resolve()).as_posix()
            except ValueError:
                return path.as_posix()
        text = path.as_posix()
        while text.startswith("./"):
            text = text[2:]
        return text

    def _bandit_findings(
        self, py_files: list[str], *, execution_root: Path, added: dict[str, set[int]]
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        # Absolute paths from the sandbox dir: a PR-supplied .bandit config is not read, and
        # --ignore-nosec stops the diff from silencing its own findings.
        targets = [str((execution_root / rel).resolve()) for rel in py_files]
        cmd = [sys.executable, "-I", "-m", "bandit", "-f", "json", "-q", "--ignore-nosec", *targets]
        ctx = getattr(self, "_sandbox_ctx", None) or {}
        run = self._run_tool(cmd, cwd=Path(ctx.get("sandbox_path") or execution_root))
        if not run.get("available") or run.get("timeout"):
            return run, []
        try:
            data = json.loads(run.get("stdout") or "{}")
        except json.JSONDecodeError:
            run["available"] = False
            run["error"] = "bandit_output_not_json"
            return run, []
        findings: list[dict[str, Any]] = []
        for item in data.get("results") or []:
            test_id = str(item.get("test_id") or "")
            if test_id in BANDIT_IGNORED_TESTS:
                continue
            rel = self._relative_to_root(str(item.get("filename") or ""), execution_root)
            line = int(item.get("line_number") or 0)
            if line not in added.get(rel, set()):
                continue
            findings.append(
                {
                    "lane": "security_sentry",
                    "rule_id": f"bandit:{test_id}",
                    "tool": "bandit",
                    "state": "VERIFIED_FINDING",
                    "severity": str(item.get("issue_severity") or "").lower() or "low",
                    "confidence": str(item.get("issue_confidence") or "").lower(),
                    "file": rel,
                    "line": line,
                    "repro_command": run["command"],
                    "execution_cwd": str(execution_root),
                    "summary": str(item.get("issue_text") or "")[:300],
                }
            )
        run["errors"] = list(data.get("errors") or [])[:5]
        return run, findings

    def _ruff_findings(
        self,
        py_files: list[str],
        *,
        execution_root: Path,
        added: dict[str, set[int]],
        select: str,
        lane: str,
        ignored: frozenset[str] = frozenset(),
        added_only: bool = True,
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        cmd = [
            sys.executable,
            "-I",
            "-m",
            "ruff",
            "check",
            "--no-cache",
            "--isolated",
            "--ignore-noqa",
            "--select",
            select,
            "--output-format",
            "json",
            *py_files,
        ]
        run = self._run_tool(cmd, cwd=execution_root)
        if not run.get("available") or run.get("timeout"):
            return run, []
        try:
            data = json.loads(run.get("stdout") or "[]")
        except json.JSONDecodeError:
            run["available"] = False
            run["error"] = "ruff_output_not_json"
            return run, []
        findings: list[dict[str, Any]] = []
        for item in data if isinstance(data, list) else []:
            code = str(item.get("code") or "")
            if not code or code in ignored:
                continue
            rel = self._relative_to_root(str(item.get("filename") or ""), execution_root)
            line = int(((item.get("location") or {}).get("row")) or 0)
            if added_only and line not in added.get(rel, set()):
                continue
            findings.append(
                {
                    "lane": lane,
                    "rule_id": f"ruff:{code}",
                    "tool": "ruff",
                    "state": "VERIFIED_FINDING",
                    "severity": "medium" if lane == "security_sentry" else "high",
                    "file": rel,
                    "line": line,
                    "repro_command": run["command"],
                    "execution_cwd": str(execution_root),
                    "summary": str(item.get("message") or "")[:300],
                }
            )
        return run, findings

    def _capture_diff(self, base_ref: str) -> str:
        return self._filter_diff(self._git(["diff", "--binary", base_ref]))

    def _capture_status(self) -> str:
        lines: list[str] = []
        for line in self._git(["status", "--short"]).splitlines():
            path = line[3:] if len(line) > 3 else ""
            if path.startswith('"') and " -> " not in path:
                path = path.strip('"')
            if " -> " in path:
                path = path.rsplit(" -> ", 1)[-1].strip('"')
            if path and self._is_runtime_artifact_path(path):
                continue
            lines.append(line)
        return "\n".join(lines) + ("\n" if lines else "")

    def _filter_diff(self, diff_text: str) -> str:
        chunks: list[list[str]] = []
        current: list[str] = []
        for line in diff_text.splitlines(keepends=True):
            if line.startswith("diff --git "):
                if current:
                    chunks.append(current)
                current = [line]
                continue
            if current:
                current.append(line)
            else:
                chunks.append([line])
        if current:
            chunks.append(current)

        kept: list[str] = []
        for chunk in chunks:
            header = chunk[0] if chunk else ""
            if header.startswith("diff --git "):
                path = self._path_from_diff_header(header.rstrip("\n"))
                if path and self._is_runtime_artifact_path(path):
                    continue
            kept.extend(chunk)
        return "".join(kept)

    def _derive_regression_candidate_map(self, diff_text: str) -> list[dict[str, Any]]:
        candidate_map: list[dict[str, Any]] = []
        for changed in self._changed_files(diff_text):
            path = Path(changed)
            if not path.parts:
                continue
            candidates = self._candidate_tests_for_changed_file(path)
            existing = [candidate for candidate in candidates if (self.project_root / candidate).exists()]
            candidate_map.append(
                {
                    "changed_file": changed,
                    "candidates": candidates,
                    "existing": existing,
                    "skipped": [candidate for candidate in candidates if candidate not in existing],
                    "status": "READY" if existing else "SKIPPED",
                    "skip_reason": "" if existing else "no_existing_regression_candidates",
                }
            )
        return candidate_map

    def _candidate_tests_for_changed_file(self, path: Path) -> list[str]:
        candidates: list[str] = []
        top = path.parts[0] if path.parts else ""
        if top == "nexus" and path.suffix == ".py":
            stem = path.stem
            module_dir = path.parts[1] if len(path.parts) > 1 else ""
            test_dir = TEST_DIR_BY_SOURCE_DIR.get(module_dir, f"tests/{module_dir}" if module_dir else "tests")
            candidates.extend(
                [
                    f"{test_dir}/test_{stem}.py",
                    f"tests/test_{stem}.py",
                ]
            )
        if top == "scripts" and path.suffix == ".py":
            script_area = path.parts[1] if len(path.parts) > 1 else ""
            test_dir = "tests/ops" if script_area == "ops" else "tests/engine"
            candidates.append(f"{test_dir}/test_{path.stem}.py")
        if top not in {"nexus", "scripts"} and path.suffix == ".py":
            if path.name.startswith("test_"):
                # A changed test file is its own regression candidate.
                candidates.append(path.as_posix())
            else:
                parent = path.parent.as_posix()
                candidates.extend(
                    [
                        f"tests/test_{path.stem}.py",
                        f"{parent}/test_{path.stem}.py" if parent not in ("", ".") else f"test_{path.stem}.py",
                    ]
                )

        seen: set[str] = set()
        deduped: list[str] = []
        for candidate in candidates:
            if candidate not in seen:
                seen.add(candidate)
                deduped.append(candidate)
        return deduped

    def _existing_regression_candidates(self, regression_map: list[dict[str, Any]]) -> list[str]:
        seen: set[str] = set()
        existing: list[str] = []
        for item in regression_map:
            for candidate in item.get("existing", []):
                if candidate in seen:
                    continue
                seen.add(candidate)
                existing.append(candidate)
        return existing

    def _scan_security_observations(self, diff_text: str) -> list[dict[str, Any]]:
        findings: list[dict[str, Any]] = []
        current_file = ""
        new_line = 0
        for raw_line in diff_text.splitlines():
            if raw_line.startswith("diff --git "):
                current_file = self._path_from_diff_header(raw_line)
                new_line = 0
                continue
            if raw_line.startswith("@@"):
                parsed = re.search(r"\+(\d+)", raw_line)
                new_line = int(parsed.group(1)) - 1 if parsed else 0
                continue
            if raw_line.startswith("+") and not raw_line.startswith("+++"):
                new_line += 1
                content = raw_line[1:]
                for rule_id, pattern in SECURITY_PATTERNS:
                    if pattern.search(content):
                        findings.append(
                            {
                                "id": f"security-{len(findings) + 1}",
                                "lane": "security_sentry",
                                "rule_id": rule_id,
                                "state": "UNVERIFIED_OBSERVATION",
                                "severity": "high" if rule_id == "secret_literal" else "medium",
                                "file": current_file,
                                "line": new_line,
                                "repro_command": "",
                                "matched_text": content,
                                "summary": f"Dry-run security observation matched {rule_id}.",
                            }
                        )
                continue
            if raw_line.startswith("-") and not raw_line.startswith("---"):
                continue
            if current_file:
                new_line += 1
        return findings

    def _path_from_diff_header(self, line: str) -> str:
        parsed = re.match(r"^diff --git a/(.*) b/(.*)$", line)
        if parsed:
            return parsed.group(2)
        parts = line.split()
        if len(parts) < 4:
            return ""
        path = parts[3]
        return path[2:] if path.startswith("b/") else path

    def _derive_regression_candidates(self, diff_text: str) -> list[str]:
        return self._existing_regression_candidates(self._derive_regression_candidate_map(diff_text))

    def _build_dry_run_fleet(
        self,
        test_candidates: list[str],
        security_sentry: dict[str, Any] | None = None,
        logic_breaker: dict[str, Any] | None = None,
        ghost_regression: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        security_sentry = security_sentry or {
            "passed": True,
            "findings": [],
            "verified_findings": 0,
            "unverified_observations": 0,
        }
        logic_breaker = logic_breaker or {
            "passed": True,
            "repro_script": "",
            "repro_command": "",
        }
        ghost_regression = ghost_regression or {
            "passed": True,
            "executed_tests": [],
            "failed_tests": [],
            "skipped_tests": [],
        }
        ghost_status = "SKIPPED"
        if test_candidates:
            ghost_status = "PASS" if bool(ghost_regression.get("passed", False)) else "FAIL"
        logic_status = "PASS" if bool(logic_breaker.get("passed", False)) else "FAIL"
        return [
            {
                "lane": "security_sentry",
                "status": "PASS" if security_sentry.get("passed", True) else "FAIL",
                "planned_checks": ["diff-pattern-scan", "bandit", "ruff-security"],
                "executed_checks": security_sentry.get("executed_checks", []),
                "unavailable_checks": security_sentry.get("unavailable_checks", []),
                "unverified_observations": security_sentry.get("unverified_observations", 0),
                "verified_findings": security_sentry.get("verified_findings", 0),
            },
            {
                "lane": "logic_breaker",
                "status": logic_status,
                "planned_checks": ["ultra_logic_repro.py", "py_compile", "ruff-correctness"],
                "executed_checks": logic_breaker.get("executed_checks", ["ultra_logic_repro.py"]),
                "unavailable_checks": logic_breaker.get("unavailable_checks", []),
                "repro_script": logic_breaker.get("repro_script", ""),
                "verified_findings": len(logic_breaker.get("findings", []) or [])
                if logic_breaker.get("findings") is not None
                else (0 if logic_breaker.get("passed", True) else 1),
            },
            {
                "lane": "ghost_regression",
                "status": ghost_status,
                "planned_checks": test_candidates,
                "executed_checks": ghost_regression.get("executed_tests", []),
                "failed_checks": ghost_regression.get("failed_tests", []),
                "skipped_checks": ghost_regression.get("skipped_tests", []),
                "skip_reason": "" if test_candidates else "no_existing_regression_candidates",
                "verified_findings": len(ghost_regression.get("failed_tests", [])),
            },
        ]

    def _run_security_sentry(self, *, diff_text: str, execution_root: Path, sandbox_path: Path) -> dict[str, Any]:
        observations = self._scan_security_observations(diff_text)
        findings: list[dict[str, Any]] = []
        executed_checks: list[str] = ["diff-pattern-scan"]
        unavailable_checks: list[dict[str, Any]] = []
        tool_runs: dict[str, Any] = {}
        verified_count = 0
        unverified_count = 0

        for index, observation in enumerate(observations, start=1):
            script_name = f"ultra_security_repro_{index}.py"
            script_path = sandbox_path / script_name
            expected = str(observation.get("matched_text", ""))
            script_path.write_text(
                "\n".join(
                    [
                        "from pathlib import Path",
                        "",
                        f"expected = {expected!r}",
                        f"target = Path({str(observation.get('file', ''))!r})",
                        "# The smell must be present in the sandbox tree the diff was applied to,",
                        "# not merely in the diff text.",
                        "if not target.is_file():",
                        "    raise SystemExit('changed file missing from sandbox mirror')",
                        "if expected not in target.read_text(encoding='utf-8', errors='replace'):",
                        "    raise SystemExit('security observation not reproduced')",
                        "print('security_repro_ok')",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            _write_no_follow(execution_root / "changes.diff", self._resolve(sandbox_path / "changes.diff").read_bytes())
            cmd = [sys.executable, "-I", str(script_path)]
            executed_checks.append(script_name)
            timeout = False
            try:
                result = self._sandboxed_run(cmd, cwd=execution_root, timeout=SECURITY_REPRO_TIMEOUT_SEC)
                reproduced = result.returncode == 0
                stdout_tail = (result.stdout or "")[-2000:]
                stderr_tail = (result.stderr or "")[-2000:]
            except subprocess.TimeoutExpired as exc:
                reproduced = False
                timeout = True
                stdout_tail = str(exc.output or "")[-2000:]
                stderr_tail = str(exc.stderr or "")[-2000:]
            finding = dict(observation)
            finding.update(
                {
                    "repro_command": " ".join(cmd),
                    "execution_cwd": str(execution_root),
                    "stdout_tail": stdout_tail,
                    "stderr_tail": stderr_tail,
                    "timeout_sec": SECURITY_REPRO_TIMEOUT_SEC,
                    "timeout": timeout,
                }
            )
            if reproduced:
                finding["state"] = "VERIFIED_FINDING"
                finding["summary"] = f"Security Sentry reproduced {finding['rule_id']} from diff evidence."
                verified_count += 1
            else:
                finding["state"] = "UNVERIFIED_OBSERVATION"
                finding["summary"] = f"Security Sentry observed {finding['rule_id']} but repro did not confirm it."
                unverified_count += 1
            findings.append(finding)

        py_files = self._changed_python_files(diff_text, execution_root)
        added = self._added_lines(diff_text)
        tool_findings: list[dict[str, Any]] = []
        if py_files:
            for check_name, runner in (
                ("bandit", lambda: self._bandit_findings(py_files, execution_root=execution_root, added=added)),
                (
                    "ruff-security",
                    lambda: self._ruff_findings(
                        py_files,
                        execution_root=execution_root,
                        added=added,
                        select="S",
                        lane="security_sentry",
                        ignored=RUFF_SECURITY_IGNORED_CODES,
                    ),
                ),
            ):
                run, found = runner()
                tool_runs[check_name] = {
                    key: run.get(key)
                    for key in ("available", "timeout", "returncode", "command", "error", "errors")
                    if key in run
                }
                if not run.get("available") or run.get("timeout"):
                    unavailable_checks.append({"check": check_name, **tool_runs[check_name]})
                    continue
                executed_checks.append(check_name)
                tool_findings.extend(found)
        # ruff's S-rules mirror bandit's B-rules: keep one finding per file/line/rule number.
        seen_keys: dict[tuple[str, int, str], dict[str, Any]] = {}
        for finding in tool_findings:
            number = re.sub(r"\D", "", str(finding["rule_id"]).split(":", 1)[-1])
            key = (str(finding["file"]), int(finding["line"]), number)
            if key in seen_keys:
                seen_keys[key].setdefault("corroborated_by", []).append(finding["rule_id"])
                continue
            seen_keys[key] = finding
            finding["id"] = f"security-{len(findings) + 1}"
            findings.append(finding)
        blocking = [
            finding
            for finding in findings
            if finding.get("state") == "VERIFIED_FINDING"
            and str(finding.get("severity") or "").lower() in SECURITY_BLOCKING_SEVERITIES
        ]
        verified_count = sum(1 for finding in findings if finding.get("state") == "VERIFIED_FINDING")
        return {
            "passed": not blocking and not unavailable_checks,
            "executed_checks": executed_checks,
            "unavailable_checks": unavailable_checks,
            "tool_runs": tool_runs,
            "scanned_python_files": py_files,
            "blocking_findings": len(blocking),
            "verified_findings": verified_count,
            "unverified_observations": unverified_count,
            "timeout_sec": SECURITY_REPRO_TIMEOUT_SEC,
            "execution_mode": "sandbox_mirror",
            "execution_cwd": str(execution_root),
            "dependency_mode": "active_venv",
            "findings": findings,
        }

    def _run_logic_breaker(self, *, diff_path: Path, execution_root: Path, sandbox_path: Path) -> dict[str, Any]:
        repro_script = sandbox_path / "ultra_logic_repro.py"
        mirror_diff_path = execution_root / ".nexus_ultra_changes.diff"
        _write_no_follow(mirror_diff_path, Path(diff_path).read_bytes())
        repro_script.write_text(
            "\n".join(
                [
                    "import re",
                    "from pathlib import Path",
                    "",
                    "diff_path = Path('.nexus_ultra_changes.diff')",
                    "if not diff_path.exists():",
                    "    raise SystemExit('missing diff artifact')",
                    "diff_text = diff_path.read_text(encoding='utf-8')",
                    "deleted_files = set()",
                    "current_changed = None",
                    "for line in diff_text.splitlines():",
                    "    if line.startswith('diff --git '):",
                    "        parsed = re.match(r'^diff --git a/(.*) b/(.*)$', line)",
                    "        if not parsed:",
                    "            raise SystemExit(f'malformed diff header: {line}')",
                    "        current_changed = parsed.group(2)",
                    "        continue",
                    "    if current_changed and line.startswith('deleted file mode '):",
                    "        deleted_files.add(current_changed)",
                    "for line in diff_text.splitlines():",
                    "    if not line.startswith('diff --git '):",
                    "        continue",
                    "    parsed = re.match(r'^diff --git a/(.*) b/(.*)$', line)",
                    "    changed = parsed.group(2)",
                    "    if changed and changed not in deleted_files and not Path(changed).exists():",
                    "        raise SystemExit(f'changed file missing from sandbox mirror: {changed}')",
                    "print('logic_repro_ok')",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        cmd = [sys.executable, "-I", str(repro_script)]
        timeout = False
        try:
            result = self._sandboxed_run(cmd, cwd=execution_root, timeout=LOGIC_BREAKER_TIMEOUT_SEC)
            passed = result.returncode == 0
            stdout_tail = (result.stdout or "")[-2000:]
            stderr_tail = (result.stderr or "")[-2000:]
            rule_id = "logic_repro_failed"
            summary = "Logic Breaker deterministic repro failed in ultra-review dry-run."
        except subprocess.TimeoutExpired as exc:
            passed = False
            timeout = True
            stdout_tail = str(exc.output or "")[-2000:]
            stderr_tail = str(exc.stderr or "")[-2000:]
            rule_id = "logic_repro_timeout"
            summary = "Logic Breaker deterministic repro timed out in ultra-review dry-run."

        findings = []
        executed_checks = ["ultra_logic_repro.py"]
        unavailable_checks: list[dict[str, Any]] = []
        if not passed:
            findings.append(
                {
                    "id": "logic-breaker-1",
                    "lane": "logic_breaker",
                    "rule_id": rule_id,
                    "state": "VERIFIED_FINDING",
                    "severity": "high",
                    "file": "",
                    "line": 0,
                    "repro_command": " ".join(cmd),
                    "summary": summary,
                    "execution_cwd": str(execution_root),
                    "stdout_tail": stdout_tail,
                    "stderr_tail": stderr_tail,
                }
            )

        diff_text = diff_path.read_text(encoding="utf-8") if diff_path.exists() else ""
        uncontained = self._uncontained_changed_files(diff_text, execution_root)
        executed_checks.append("path-containment")
        if uncontained:
            findings.append(
                {
                    "id": f"logic-breaker-{len(findings) + 1}",
                    "lane": "logic_breaker",
                    "rule_id": "path_outside_worktree",
                    "tool": "path-containment",
                    "state": "VERIFIED_FINDING",
                    "severity": "high",
                    "file": uncontained[0],
                    "line": 0,
                    "repro_command": "",
                    "summary": "Changed path is a symlink or resolves outside the sandbox worktree: "
                    + ", ".join(uncontained[:5]),
                    "execution_cwd": str(execution_root),
                }
            )
        harness = [rel for rel in self._changed_files(diff_text) if Path(rel).name in TEST_HARNESS_FILES]
        executed_checks.append("test-harness-guard")
        if harness:
            # A diff that edits the test harness can make the ghost re-run report green
            # without running the tests honestly; a human must review it.
            findings.append(
                {
                    "id": f"logic-breaker-{len(findings) + 1}",
                    "lane": "logic_breaker",
                    "rule_id": "test_harness_modified",
                    "tool": "test-harness-guard",
                    "state": "VERIFIED_FINDING",
                    "severity": "high",
                    "file": harness[0],
                    "line": 0,
                    "repro_command": "",
                    "summary": "Diff changes test-harness configuration: " + ", ".join(harness[:5]),
                    "execution_cwd": str(execution_root),
                }
            )
        py_files = self._changed_python_files(diff_text, execution_root)
        if py_files:
            compile_cmd = [sys.executable, "-I", "-m", "py_compile", *py_files]
            compiled = self._run_tool(compile_cmd, cwd=execution_root)
            executed_checks.append("py_compile")
            if compiled.get("timeout") or compiled.get("returncode") not in (0, None):
                findings.append(
                    {
                        "id": f"logic-breaker-{len(findings) + 1}",
                        "lane": "logic_breaker",
                        "rule_id": "py_compile_failed",
                        "tool": "py_compile",
                        "state": "VERIFIED_FINDING",
                        "severity": "high",
                        "file": "",
                        "line": 0,
                        "repro_command": compiled.get("command", ""),
                        "summary": "Changed Python file does not compile.",
                        "execution_cwd": str(execution_root),
                        "stderr_tail": str(compiled.get("stderr") or "")[-2000:],
                    }
                )
            run, found = self._ruff_findings(
                py_files,
                execution_root=execution_root,
                added=self._added_lines(diff_text),
                select=RUFF_LOGIC_SELECT,
                lane="logic_breaker",
            )
            if not run.get("available") or run.get("timeout"):
                unavailable_checks.append(
                    {"check": "ruff-correctness", "command": run.get("command"), "error": run.get("error", "timeout")}
                )
            else:
                executed_checks.append("ruff-correctness")
                for finding in found:
                    finding["id"] = f"logic-breaker-{len(findings) + 1}"
                    findings.append(finding)
        passed = bool(passed and not findings and not unavailable_checks)

        return {
            "passed": passed,
            "executed_checks": executed_checks,
            "unavailable_checks": unavailable_checks,
            "scanned_python_files": py_files,
            "repro_script": str(repro_script),
            "repro_command": " ".join(cmd),
            "execution_mode": "sandbox_mirror",
            "execution_cwd": str(execution_root),
            "timeout": timeout,
            "timeout_sec": LOGIC_BREAKER_TIMEOUT_SEC,
            "dependency_mode": "active_venv",
            "stdout_tail": stdout_tail,
            "stderr_tail": stderr_tail,
            "findings": findings,
        }

    def _run_ghost_regression(self, test_candidates: list[str], *, execution_root: Path) -> dict[str, Any]:
        if os.getenv(ULTRA_SKIP_GHOST_ENV, "").strip().lower() in {"1", "true", "yes", "on"}:
            return {
                "passed": True,
                "executed_tests": [],
                "failed_tests": [],
                "skipped_tests": list(test_candidates),
                "findings": [],
                "execution_mode": "skipped_by_env",
                "timeout_sec": GHOST_REGRESSION_TIMEOUT_SEC,
                "dependency_mode": "active_venv",
                "sanitized_env": self._benchmark_env_keys_removed(),
                "execution_cwd": str(execution_root),
                "timeout": False,
            }
        if not test_candidates:
            return {
                "passed": True,
                "executed_tests": [],
                "failed_tests": [],
                "skipped_tests": [],
                "findings": [],
                "execution_mode": "sandbox_mirror",
                "execution_cwd": str(execution_root),
                "timeout": False,
                "timeout_sec": GHOST_REGRESSION_TIMEOUT_SEC,
                "dependency_mode": "active_venv",
                "pytest_stdout_tail": "",
                "pytest_stderr_tail": "",
            }

        # rootdir pins conftest discovery to the sandbox mirror (the sandbox may sit inside the
        # reviewed repo); no cache dir is written into the mirror.
        # -I: no PYTHONPATH, user site or cwd at start-up, so a PR sitecustomize/.pth never
        # loads; the mirror is put on sys.path by pytest's ``pythonpath`` ini override.
        cmd = [
            sys.executable,
            "-I",
            "-m",
            "pytest",
            "-q",
            "-p",
            "no:cacheprovider",
            "--rootdir",
            str(execution_root),
            "-o",
            f"pythonpath={sbpl_path(execution_root)}",
            *test_candidates,
        ]
        sanitized_env = [key for key in BENCHMARK_ONLY_ENV_VARS if key in os.environ]
        test_candidates = [
            rel for rel in test_candidates if self._contained_path(rel, execution_root) is not None
        ]
        if not os_sandbox_available():
            # The re-run imports and executes PR-controlled code: without an OS barrier it
            # does not run at all, and the lane fails closed.
            return {
                "passed": False,
                "blocked": True,
                "blocked_reason": "no_os_barrier",
                "executed_tests": [],
                "failed_tests": [],
                "skipped_tests": list(test_candidates),
                "findings": [],
                "execution_mode": "refused_uncontained",
                "execution_cwd": str(execution_root),
                "timeout": False,
                "timeout_sec": GHOST_REGRESSION_TIMEOUT_SEC,
                "dependency_mode": "active_venv",
                "sanitized_env": sanitized_env,
                "isolation": self.sandbox_isolation(),
                "pytest_stdout_tail": "",
                "pytest_stderr_tail": "",
            }
        timeout = False
        try:
            result = self._sandboxed_run(cmd, cwd=execution_root, timeout=GHOST_REGRESSION_TIMEOUT_SEC)
            passed = result.returncode == 0
            stdout_tail = (result.stdout or "")[-2000:]
            stderr_tail = (result.stderr or "")[-2000:]
            rule_id = "regression_test_failed"
            summary = "Ghost regression candidate failed in ultra-review dry-run."
        except subprocess.TimeoutExpired as exc:
            passed = False
            timeout = True
            stdout_tail = str(exc.output or "")[-2000:]
            stderr_tail = str(exc.stderr or "")[-2000:]
            rule_id = "regression_test_timeout"
            summary = "Ghost regression candidate timed out in ultra-review dry-run."
        failed_tests = [] if passed else list(test_candidates)
        findings = []
        if not passed:
            findings.append(
                {
                    "id": "ghost-regression-1",
                    "lane": "ghost_regression",
                    "rule_id": rule_id,
                    "state": "VERIFIED_FINDING",
                    "severity": "high",
                    "file": "",
                    "line": 0,
                    "repro_command": " ".join(cmd),
                    "summary": summary,
                    "execution_cwd": str(execution_root),
                    "stdout_tail": stdout_tail,
                    "stderr_tail": stderr_tail,
                }
            )
        return {
            "passed": passed,
            "executed_tests": list(test_candidates),
            "failed_tests": failed_tests,
            "skipped_tests": [],
            "findings": findings,
            "execution_mode": "sandbox_mirror",
            "execution_cwd": str(execution_root),
            "timeout": timeout,
            "timeout_sec": GHOST_REGRESSION_TIMEOUT_SEC,
            "dependency_mode": "active_venv",
            "sanitized_env": sanitized_env,
            "isolation": self.sandbox_isolation(),
            "pytest_stdout_tail": stdout_tail,
            "pytest_stderr_tail": stderr_tail,
        }

    def _changed_files(self, diff_text: str) -> list[str]:
        files: list[str] = []
        for line in diff_text.splitlines():
            if not line.startswith("diff --git "):
                continue
            path = self._path_from_diff_header(line)
            if path and not self._is_runtime_artifact_path(path):
                files.append(path)
        return files

    def _is_runtime_artifact_path(self, path: str) -> bool:
        normalized = path.replace("\\", "/")
        while normalized.startswith("./"):
            normalized = normalized[2:]
        return any(normalized.startswith(prefix) for prefix in RUNTIME_ARTIFACT_PREFIXES)

    def _resolve(self, path: Path | str) -> Path:
        path_obj = Path(path)
        if path_obj.is_absolute():
            return path_obj
        return (self.project_root / path_obj).resolve()

    def _git(self, args: list[str]) -> str:
        result = subprocess.run(
            ["git", *args],
            cwd=self.project_root,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise UltraReviewError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
        return result.stdout

    def _run_id(self) -> str:
        return "ultra-review-" + datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
