"""Committee verifier that judges each candidate patch by executing it, inside a sandbox.

Candidate patches are untrusted (model output) and so are the request's verify commands. Each
candidate gets its own sandbox ``<workspace>/.nexus/committee/<task>/candidate-<n>/`` with a
symlink-free copy of the workspace (``worktree/``) and a private ``home/`` and ``tmp/``. The
patch is refused before ``git apply`` when it creates/edits a symlink or gitlink, renames or
copies a path, touches a ``.git`` path or is unparseable, and the applied tree is lstat-walked
afterwards (any symlink or special file is refused). ``git`` runs with no system/global config,
hooks, filters or enclosing repository.

Verify commands are argv only, from an allowlist (``python -I -m pytest ...``, ``ruff
check|format ...``, ``python -I <script inside the sandbox>``); anything else is
``COMMAND_NOT_ALLOWED``. They run with the trusted interpreter under the shared sandbox
(``nexus.engine.sandboxed_lane``): scrubbed env, ``cwd`` in the copy, macOS ``sandbox-exec``
with default-deny reads, no network and writes only inside the candidate sandbox. Without an OS
barrier nothing is executed: the candidate is ``not_executed:no_os_barrier`` (unverified), so it
cannot win. The workspace itself is never modified.
"""

from __future__ import annotations

import hashlib
import os
import re
import shlex
import shutil
import stat
import subprocess  # nosec B404 - argv lists only, never a shell
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from nexus.engine import sandboxed_lane as lane
from nexus.verifiers.contracts import EvidenceRef, FailureTag, VerifierVerdict

VERIFIER_NAME = "patch_execution"
# The only pytest config a verify run reads: written by the verifier next to (not inside) the
# candidate copy, so no candidate pytest.ini/pyproject.toml/setup.cfg/tox.ini is consulted.
VERIFIER_INI = "verifier-pytest.ini"
NOT_EXECUTED_NO_BARRIER = "not_executed:no_os_barrier"
_COPY_IGNORE = (".git", ".nexus", ".armor", "__pycache__", ".venv", "node_modules")
# Shell syntax in a command string means the caller expected a shell; there is none.
_SHELL_SYNTAX = re.compile(r"[;&|`$<>\n\r]")
_PYTHON_NAMES = frozenset({"python", "python3"})
_PYTEST_FLAGS = frozenset({
    "-q",
    "-qq",
    "-v",
    "-vv",
    "-x",
    "-s",
    "-ra",
    "-rA",
    "--no-header",
    "--strict-markers",
    "--tb=short",
    "--tb=line",
    "--tb=no",
    "--tb=long",
})
# Flags whose value is an expression, not a path.
_PYTEST_VALUE_FLAGS = frozenset({"-k", "-m"})
_RUFF_SUBCOMMANDS = frozenset({"check", "format"})
_RUFF_FLAGS = frozenset({"--no-fix", "--diff", "--check", "--quiet", "-q", "--preview"})
_RUFF_FLAG_PREFIXES = ("--select=", "--ignore=", "--output-format=", "--line-length=")
# Files that change how a verify command or its interpreter runs (pytest/ruff config, conftest
# plugins, start-up hooks, environment files). Decided on the APPLIED copy, not the patch text:
# a candidate that adds, modifies or deletes one (any directory, any letter case) is refused.
# pytest additionally runs with --noconftest -c /dev/null -o addopts= and ruff with --isolated,
# so such files would not be loaded even if present.
_HARNESS_NAMES = frozenset({
    "conftest.py",
    "pytest.ini",
    "tox.ini",
    "setup.cfg",
    "pyproject.toml",
    "ruff.toml",
    ".ruff.toml",
    "sitecustomize.py",
    "usercustomize.py",
    "pyvenv.cfg",
    ".env",
})


def _is_harness(rel: str) -> bool:
    name = Path(rel).name.lower()
    return (
        name in _HARNESS_NAMES
        or name.endswith(".pth")
        or name.startswith(".env.")
        or (name.startswith("requirements") and name.endswith(".txt"))
    )


def _harness_snapshot(root: Path) -> dict[str, str]:
    """``{relative path: sha256}`` of every harness/environment file under ``root``, found by
    an lstat walk that never follows links (a non-regular entry is recorded as such)."""

    snapshot: dict[str, str] = {}
    for current, _dirs, files in os.walk(root, followlinks=False):
        for name in files:
            path = Path(current) / name
            rel = path.relative_to(root).as_posix()
            if not _is_harness(rel):
                continue
            info = os.lstat(path)
            if not stat.S_ISREG(info.st_mode):
                snapshot[rel] = f"non_regular:{stat.S_IFMT(info.st_mode)}"
                continue
            snapshot[rel] = hashlib.sha256(path.read_bytes()).hexdigest()
    return snapshot


class CommandNotAllowed(ValueError):
    """A verify command outside the allowlist (the candidate stays unverified)."""


def _safe_segment(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value or ""))[:80] or "task"


def parse_command(command: Any) -> list[str]:
    """argv for one verify command: a list of strings, or a string split without a shell
    (shell operators refused). Raises CommandNotAllowed."""

    if isinstance(command, (list, tuple)):
        argv = [str(part) for part in command]
    elif isinstance(command, str):
        if _SHELL_SYNTAX.search(command):
            raise CommandNotAllowed("shell_syntax")
        try:
            argv = shlex.split(command)
        except ValueError as exc:
            raise CommandNotAllowed("unparseable") from exc
    else:
        raise CommandNotAllowed("not_argv")
    if not argv or any(not part or "\x00" in part for part in argv):
        raise CommandNotAllowed("empty_argument")
    if any(".." in part for part in argv):
        raise CommandNotAllowed("dotdot_argument")
    kind, args = _classify(argv)
    _checked_args(kind, args, None)
    return argv


def _classify(argv: list[str]) -> tuple[str, list[str]]:
    """(kind, tool arguments) for an allowlisted argv; raises CommandNotAllowed."""

    head, rest = argv[0], argv[1:]
    if head in _PYTHON_NAMES:
        if rest[:1] == ["-I"]:
            rest = rest[1:]
        if rest[:2] == ["-m", "pytest"]:
            return "pytest", rest[2:]
        if rest and rest[0].endswith(".py") and not rest[0].startswith("-"):
            return "script", rest
        raise CommandNotAllowed(f"python_form_not_allowed:{' '.join(argv)[:80]}")
    if head == "ruff":
        if not rest or rest[0] not in _RUFF_SUBCOMMANDS:
            raise CommandNotAllowed("ruff_subcommand_not_allowed")
        return "ruff", rest
    raise CommandNotAllowed(f"program_not_allowed:{head[:40]}")


def _scoped_arg(mirror: Path | None, value: str) -> str:
    """``value`` when it names a path inside ``mirror`` (without a mirror yet: relative and
    without ``..``). Raises CommandNotAllowed."""

    path_part = value.split("::", 1)[0]
    if mirror is None:
        candidate = Path(path_part)
        contained = not candidate.is_absolute() and ".." not in candidate.parts
    else:
        contained = lane.scoped_path(mirror, path_part) is not None
    if not path_part or not contained:
        raise CommandNotAllowed(f"path_outside_sandbox:{value[:80]}")
    return value


def _checked_args(kind: str, args: list[str], mirror: Path | None) -> list[str]:
    """Tool arguments with every flag allowlisted and every path argument scoped."""

    checked: list[str] = []
    if kind == "pytest":
        expect_value = False
        for arg in args:
            if expect_value:
                if arg.startswith("-"):
                    raise CommandNotAllowed(f"pytest_flag_value_is_a_flag:{arg[:40]}")
                checked.append(arg)
                expect_value = False
            elif arg in _PYTEST_VALUE_FLAGS:
                checked.append(arg)
                expect_value = True
            elif arg.startswith("-"):
                if arg not in _PYTEST_FLAGS:
                    raise CommandNotAllowed(f"pytest_flag_not_allowed:{arg[:40]}")
                checked.append(arg)
            else:
                checked.append(_scoped_arg(mirror, arg))
        if expect_value:
            raise CommandNotAllowed("pytest_flag_missing_value")
        return checked
    if kind == "script":
        script = _scoped_arg(mirror, args[0])
        if mirror is not None:
            resolved = lane.scoped_path(mirror, script)
            if resolved is None or not resolved.is_file():
                raise CommandNotAllowed(f"script_outside_sandbox:{script[:80]}")
            script = str(resolved)
        if any(arg.startswith("-") for arg in args[1:]):
            raise CommandNotAllowed("script_flag_not_allowed")
        return [script, *(_scoped_arg(mirror, arg) for arg in args[1:])]
    checked.append(args[0])
    for arg in args[1:]:
        if arg.startswith("-"):
            if arg not in _RUFF_FLAGS and not arg.startswith(_RUFF_FLAG_PREFIXES):
                raise CommandNotAllowed(f"ruff_flag_not_allowed:{arg[:40]}")
            checked.append(arg)
        else:
            checked.append(_scoped_arg(mirror, arg))
    return checked


def build_argv(command: list[str], *, mirror: Path, interpreter: str) -> list[str]:
    """The confined argv for an allowlisted command (trusted interpreter, ``-I``, every path
    argument inside ``mirror``). Raises CommandNotAllowed."""

    kind, args = _classify(command)
    checked = _checked_args(kind, args, mirror)
    if kind == "pytest":
        root = lane.sbpl_path(mirror)
        return [
            interpreter,
            "-I",
            "-m",
            "pytest",
            "-p",
            "no:cacheprovider",
            "--noconftest",
            "-c",
            lane.sbpl_path(mirror.parent / VERIFIER_INI),
            "--rootdir",
            root,
            "-o",
            # pytest shlex-splits a ``paths`` ini value; quoted, a root with a space stays whole.
            f"pythonpath={shlex.quote(str(root))}",
            "-o",
            "addopts=",
            *checked,
        ]
    if kind == "script":
        return [interpreter, "-I", "-c", lane.SCRIPT_BOOTSTRAP, *checked]
    ruff = Path(sys.prefix) / "bin" / "ruff"
    if not ruff.is_file():
        raise CommandNotAllowed("ruff_unavailable")
    return [str(ruff), checked[0], "--no-cache", "--isolated", *checked[1:]]


@dataclass
class PatchExecutionVerifier:
    workspace_root: Path
    commands: list[Any]
    task_id: str
    timeout_sec: int = 30
    results: list[dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.workspace_root = Path(self.workspace_root).resolve()
        self.run_root = self.workspace_root / ".nexus" / "committee" / _safe_segment(self.task_id)

    def evaluate(self, candidate_id: str, patch: str) -> VerifierVerdict:
        index = len(self.results)
        sandbox = self.run_root / f"candidate-{index}"
        mirror = sandbox / "worktree"
        patch_text = str(patch or "")
        record: dict[str, Any] = {
            "candidate_id": candidate_id,
            "workspace": str(mirror),
            "patch_sha256": hashlib.sha256(patch_text.encode("utf-8")).hexdigest(),
            "apply_status": "",
            "commands": [
                list(c) if isinstance(c, (list, tuple)) else str(c) for c in self.commands
            ],
            "exit_codes": [],
            # "pass" / "fail" / "not_executed:*": a per-candidate result, deliberately not a
            # ``passed`` flag, so one rejected candidate does not read as a failed committee run.
            "verify_result": "not_run",
            "isolation": {"barrier": "none"},
        }
        self.results.append(record)
        try:
            return self._evaluate(candidate_id, patch_text, sandbox, mirror, record)
        except lane.SandboxError as exc:
            record["verify_result"] = "not_executed:sandbox_error"
            return self._verdict(candidate_id, mirror, False, "SANDBOX_SETUP_FAILED", str(exc))

    def _evaluate(
        self, candidate_id: str, patch_text: str, sandbox: Path, mirror: Path, record: dict
    ) -> VerifierVerdict:
        if not patch_text.strip():
            record["apply_status"] = "empty_patch"
            return self._verdict(
                candidate_id, mirror, False, "EMPTY_PATCH", "candidate carries no patch"
            )
        try:
            commands = [parse_command(command) for command in self.commands]
        except CommandNotAllowed as exc:
            record["verify_result"] = "not_executed:command_not_allowed"
            return self._verdict(candidate_id, mirror, False, "COMMAND_NOT_ALLOWED", str(exc))
        if not commands:
            record["verify_result"] = "not_executed:no_commands"
            return self._verdict(
                candidate_id, mirror, False, "NO_VERIFY_COMMANDS", "no verify commands"
            )
        policy = lane.diff_policy_violations(patch_text)
        if policy["symlinks"] or policy["nested_git"]:
            return self._reject(
                candidate_id, mirror, record, [*policy["symlinks"], *policy["nested_git"]]
            )
        self._prepare_sandbox(sandbox, mirror)
        home = sandbox / "home"
        patch_file = sandbox / "candidate.diff"
        lane.write_no_follow(
            patch_file,
            (patch_text if patch_text.endswith("\n") else patch_text + "\n").encode("utf-8"),
        )
        git_env = lane.git_safe_env(home=home, ceiling=sandbox.resolve())
        git = lane.trusted_executable("git", untrusted_roots=(self.workspace_root,))
        summary = self._git(
            git, ["apply", "--summary", "--numstat", str(patch_file)], mirror, git_env
        )
        if summary.returncode != 0:
            return self._reject(candidate_id, mirror, record, ["patch_unparseable"])
        unsafe = lane.unsafe_summary_lines(summary.stdout or "")
        if unsafe:
            return self._reject(candidate_id, mirror, record, [line.strip() for line in unsafe])
        harness_before = _harness_snapshot(mirror)
        applied = self._git(git, ["apply", "--whitespace=nowarn", str(patch_file)], mirror, git_env)
        if applied.returncode != 0:
            record["apply_status"] = "apply_failed"
            record["apply_stderr"] = (applied.stderr or "")[-300:]
            return self._verdict(
                candidate_id, mirror, False, "PATCH_APPLY_FAILED", (applied.stderr or "")[-200:]
            )
        offending = lane.lstat_walk_violations(mirror)
        if offending:
            return self._reject(candidate_id, mirror, record, offending)
        harness_after = _harness_snapshot(mirror)
        harness = sorted(
            f"test_harness:{rel}"
            for rel in set(harness_before) | set(harness_after)
            if harness_before.get(rel) != harness_after.get(rel)
        )
        if harness:
            return self._reject(candidate_id, mirror, record, harness)
        record["apply_status"] = "applied"

        if not lane.os_sandbox_available():
            # The verify commands import and run candidate code: without an OS barrier they do
            # not run at all, and the candidate stays unverified (it cannot win).
            record["verify_result"] = NOT_EXECUTED_NO_BARRIER
            return self._verdict(
                candidate_id,
                mirror,
                False,
                "NO_OS_BARRIER",
                "no OS sandbox barrier on this host; candidate code was not executed",
            )
        interpreter = self._trusted_interpreter(sandbox)  # the pinned one, never PATH
        try:
            argvs = [build_argv(c, mirror=mirror, interpreter=interpreter) for c in commands]
            lane.write_no_follow(sandbox / VERIFIER_INI, b"[pytest]\n")
        except CommandNotAllowed as exc:
            record["verify_result"] = "not_executed:command_not_allowed"
            return self._verdict(candidate_id, mirror, False, "COMMAND_NOT_ALLOWED", str(exc))
        return self._run(candidate_id, sandbox, mirror, argvs, record)

    def _run(
        self, candidate_id: str, sandbox: Path, mirror: Path, argvs: list[list[str]], record: dict
    ) -> VerifierVerdict:
        confined = lane.confinement(
            sandbox=sandbox,
            untrusted_roots=(self.workspace_root,),
            extra_forbidden=(self.workspace_root,),
        )
        record["isolation"] = confined.describe()
        failure_tail = ""
        for argv in argvs:
            try:
                run = confined.run(argv, cwd=mirror, timeout=self.timeout_sec)
                record["exit_codes"].append(run.returncode)
                if run.returncode != 0 and not failure_tail:
                    failure_tail = (run.stderr or run.stdout or "")[-200:]
            except subprocess.TimeoutExpired:
                record["exit_codes"].append(None)
                failure_tail = failure_tail or f"timeout after {self.timeout_sec}s"
        passed = all(code == 0 for code in record["exit_codes"])
        record["verify_result"] = "pass" if passed else "fail"
        if not passed:
            return self._verdict(candidate_id, mirror, False, "VERIFY_COMMAND_FAILED", failure_tail)
        return self._verdict(candidate_id, mirror, True, "", "")

    def _prepare_sandbox(self, sandbox: Path, mirror: Path) -> None:
        # The run root must stay inside the workspace (no planted .nexus symlink redirecting
        # the rmtree/copy below).
        if (
            lane.scoped_path(self.workspace_root, str(sandbox.relative_to(self.workspace_root)))
            is None
        ):
            raise lane.SandboxError("sandbox_outside_workspace")
        if sandbox.exists():
            shutil.rmtree(sandbox)
        sandbox.mkdir(parents=True)
        (sandbox / "home").mkdir()
        (sandbox / "tmp").mkdir()
        lane.copy_tree_no_symlinks(self.workspace_root, mirror, ignore_names=_COPY_IGNORE)

    @staticmethod
    def _git(
        git: str, args: list[str], cwd: Path, env: dict[str, str]
    ) -> subprocess.CompletedProcess:
        # Trusted git binary (resolved outside the workspace), safe env, patch file we wrote;
        # git only reads the patch and writes the copy, it never runs candidate code.
        return subprocess.run(  # nosec B603 - absolute trusted git, fixed argv
            [git, *args],
            cwd=cwd,
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )

    @staticmethod
    def _trusted_interpreter(sandbox: Path) -> str:
        if lane.in_tree(sys.executable, (sandbox,)):
            raise lane.SandboxError("interpreter_inside_sandbox")
        return sys.executable

    def _reject(
        self, candidate_id: str, mirror: Path, record: dict, reasons: list[str]
    ) -> VerifierVerdict:
        record["apply_status"] = "rejected"
        record["reject_reasons"] = reasons[:20]
        record["verify_result"] = "not_executed:patch_rejected"
        return self._verdict(
            candidate_id, mirror, False, "PATCH_REJECTED", "; ".join(reasons[:5])[:200]
        )

    def _verdict(
        self, candidate_id: str, dest: Path, passed: bool, code: str, detail: str
    ) -> VerifierVerdict:
        return VerifierVerdict(
            verifier_name=VERIFIER_NAME,
            candidate_id=candidate_id,
            passed=passed,
            score=1.0 if passed else 0.0,
            evidence_refs=[EvidenceRef(source_file=str(dest), snippet=detail or None)],
            failure_tags=[FailureTag(code=code, description=detail)] if code else [],
        )
