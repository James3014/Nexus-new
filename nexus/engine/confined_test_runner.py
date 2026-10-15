"""Run one candidate test command inside ``sandboxed_lane.confinement`` (online A/B PR-2).

The post-candidate seam (``nexus.services.post_candidate_seam``) hands the ``sandbox``
capability a scratch copy of the workspace that holds the model candidate and the visible
test. This runner copies that tree into a fresh confined sandbox and runs the command there:

* writes and reads are confined to the sandbox (plus the trusted interpreter prefixes and the
  fixed system paths), ``$HOME`` and credential stores are read-denied, no network;
* every ``forbidden_paths`` entry (the hidden verifier test) is passed to
  ``checked_read_roots(..., extra_forbidden=...)``: a readable root that is, or contains, a
  forbidden path fails closed with ``sandbox_read_root_overbroad`` before anything runs;
* files named like a hidden verifier test are never copied, a copy that still holds one is
  forbidden too (same error), and an argv that names one is refused;
* without an OS barrier nothing runs (``no_os_barrier``).

The result never carries test output text beyond a short tail of the *visible* run.
"""

from __future__ import annotations

import hashlib
import shutil
import subprocess  # nosec B404 - argv lists only, never a shell
import sys
import tempfile
import time
import uuid
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

from nexus.engine.sandboxed_lane import SandboxError, confinement, copy_tree_no_symlinks, in_tree

# Hidden verifier tests that must never be copied, named in argv, or read by a candidate run.
HIDDEN_TEST_BASENAMES: tuple[str, ...] = ("test_hidden.py",)
# Never copied into the confined workspace (VCS metadata, caches, Nexus state).
CONFINED_COPY_IGNORE: tuple[str, ...] = (
    ".git",
    ".nexus",
    ".venv",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    ".mypy_cache",
)
_TAIL_CHARS = 1000
# Read-only system toolchain the bench fixtures need (some visible/hidden tests shell out to
# ``git``): system binaries and the macOS Command Line Tools. Nothing under $HOME, no workspace.
TOOLCHAIN_READ_ROOTS: tuple[str, ...] = (
    "/usr/bin",
    "/bin",
    "/usr/libexec",
    "/usr/share",
    "/private/etc",
    "/Library/Developer/CommandLineTools",
    "/Applications/Xcode.app/Contents/Developer",
    # Python's subprocess lists /dev/fd to close inherited descriptors; without it every spawn
    # falls back to closing all RLIMIT_NOFILE descriptors (~1 s per git call).
    "/dev/fd",
)


# Option tokens a confined command may carry (interpreter + pinned pytest flags); anything else
# starting with "-" is refused, so ``-o``/``-k``/``--override-ini``/``--pyargs`` and friends can
# never re-select or reconfigure tests. Options taking a value have their value pinned too.
ALLOWED_FLAG_OPTIONS: frozenset[str] = frozenset({"-I", "-m", "-q", "-x", "--maxfail=1"})
ALLOWED_VALUE_OPTIONS: dict[str, tuple[str, ...]] = {
    "--rootdir": (".",),
    "-c": (".nexus-scratch-pytest.ini", ".nexus-confined-pytest.ini"),
    "-p": ("no:cacheprovider",),
}
# ``python -m <module>``: only pytest may be run as a module.
ALLOWED_MODULES: frozenset[str] = frozenset({"pytest"})


def _refused_option_parts(argv: Sequence[str]) -> list[str]:
    """Option tokens outside the allowlist (before ``--``) and positional paths that start with
    ``-`` (after it). Tokens after ``--`` are never options."""

    refused: list[str] = []
    expect_value: tuple[str, ...] | None = None
    expect_module = False
    after_separator = False
    for part in argv[1:]:
        text = str(part)
        if expect_module:
            expect_module = False
            if text not in ALLOWED_MODULES:
                refused.append(text)
            continue
        if expect_value is not None:
            if text not in expect_value:
                refused.append(text)
            expect_value = None
            continue
        if after_separator:
            if Path(text).name.startswith("-") or text.startswith("-"):
                refused.append(text)
            continue
        if text == "--":
            after_separator = True
        elif text == "-m":
            expect_module = True
        elif text in ALLOWED_VALUE_OPTIONS:
            expect_value = ALLOWED_VALUE_OPTIONS[text]
        elif text.startswith("-") and text not in ALLOWED_FLAG_OPTIONS:
            refused.append(text)
    if expect_value is not None or expect_module:
        refused.append("<missing_option_value>")
    return refused


def _forbidden_argv_parts(
    argv: Sequence[str], *, cwd: Path, forbidden: Sequence[Path], forbidden_names: Iterable[str]
) -> list[str]:
    names = set(forbidden_names)
    hits: list[str] = []
    after_separator = False
    for part in argv[1:]:
        text = str(part)
        if text == "--" and not after_separator:
            after_separator = True
            continue
        if not text or (text.startswith("-") and not after_separator):
            continue  # option tokens are policed by _refused_option_parts
        candidate = Path(text)
        if candidate.name in names:
            hits.append(text)
            continue
        resolved = candidate if candidate.is_absolute() else cwd / candidate
        if forbidden and in_tree(resolved, forbidden):
            hits.append(text)
    return hits


def _trusted_argv(command: Sequence[str]) -> list[str]:
    argv = [str(part) for part in command if str(part).strip()]
    if argv and argv[0] in {"python", "python3", sys.executable}:
        argv[0] = sys.executable
        if argv[1:2] != ["-I"]:
            argv.insert(1, "-I")
    return argv


def run_confined_test(
    workspace_root: Path | str,
    *,
    command: Sequence[str],
    forbidden_paths: Iterable[Path | str] = (),
    forbidden_names: Iterable[str] = HIDDEN_TEST_BASENAMES,
    timeout_sec: float = 60,
    toolchain: bool = True,
) -> dict[str, Any]:
    """Copy ``workspace_root`` into a confined sandbox and run ``command`` there (cwd = copy).

    Returns a bounded result mapping; ``executed`` is False whenever the confinement refused
    to run (``error`` names the SandboxError).
    """

    start = time.monotonic()
    run_id = f"confined_{uuid.uuid4().hex[:12]}"
    names = tuple(forbidden_names)
    forbidden = [Path(path).resolve() for path in forbidden_paths if str(path).strip()]
    argv = _trusted_argv(command)
    result: dict[str, Any] = {
        "schema": "nexus.confined_test_run.v1",
        "run_id": run_id,
        "executed": False,
        "success": False,
        "exit_code": None,
        "timed_out": False,
        "stdout_sha256": "",
        "stdout_tail": "",
        "stderr_tail": "",
        "command": list(argv),
        "workspace_source": "local_project_copy",
        "network_allowed": False,
        "forbidden_paths_count": len(forbidden),
        "forbidden_names": list(names),
        "error": "",
    }
    root = Path(workspace_root).resolve()
    sandbox_dir = Path(tempfile.mkdtemp(prefix="nexus-confined-test-")).resolve()
    try:
        if not argv:
            raise SandboxError("empty_lane_command")
        if not root.is_dir():
            raise SandboxError("workspace_root_missing")
        if forbidden and in_tree(root, forbidden):
            raise SandboxError("workspace_root_is_forbidden")
        workspace = sandbox_dir / "ws"
        copy_tree_no_symlinks(root, workspace, ignore_names=(*CONFINED_COPY_IGNORE, *names))
        # Fail closed on anything hidden-test-like that survived the copy: as a forbidden root
        # it makes checked_read_roots refuse the sandbox itself.
        leaked = [path for path in workspace.rglob("*") if path.name in names]
        refused = _forbidden_argv_parts(
            argv, cwd=workspace, forbidden=[*forbidden, *leaked], forbidden_names=names
        )
        if refused:
            raise SandboxError(
                "sandbox_argv_names_forbidden_path:" + ",".join(sorted(refused))[:200]
            )
        bad_options = _refused_option_parts(argv)
        if bad_options:
            raise SandboxError("sandbox_argv_option_refused:" + ",".join(bad_options)[:200])
        bound = confinement(
            sandbox=sandbox_dir,
            extra_forbidden=[*forbidden, *leaked],
            extra_readable=TOOLCHAIN_READ_ROOTS if toolchain else (),
        )
        result["confinement"] = bound.describe()
        try:
            proc = bound.run(argv, cwd=workspace, timeout=max(1.0, float(timeout_sec)))
        except subprocess.TimeoutExpired as exc:
            out = (
                exc.stdout
                if isinstance(exc.stdout, str)
                else (exc.stdout or b"").decode("utf-8", "replace")
            )
            result.update(
                executed=True,
                timed_out=True,
                exit_code=124,
                stdout_sha256=hashlib.sha256(out.encode("utf-8")).hexdigest(),
                stdout_tail=out[-_TAIL_CHARS:],
                error="timeout",
            )
            return result
        stdout = proc.stdout or ""
        result.update(
            executed=True,
            success=proc.returncode == 0,
            exit_code=int(proc.returncode),
            stdout_sha256=hashlib.sha256(stdout.encode("utf-8")).hexdigest(),
            stdout_tail=stdout[-_TAIL_CHARS:],
            stderr_tail=(proc.stderr or "")[-_TAIL_CHARS:],
        )
        return result
    except SandboxError as exc:
        result["error"] = f"SandboxError: {exc}"[:300]
        return result
    finally:
        result["duration_sec"] = round(time.monotonic() - start, 4)
        shutil.rmtree(sandbox_dir, ignore_errors=True)


DIR_COPY_PYTEST_CONFIG = ".nexus-confined-pytest.ini"


def run_pytest_dir_copy(
    source_dir: Path | str,
    test_name: str,
    *,
    forbidden_paths: Iterable[Path | str] = (),
    timeout_sec: float = 300,
) -> dict[str, Any]:
    """Copy the regular files of ``source_dir`` (non-recursive, no symlinks, no dotfiles) into a
    fresh directory and run ``pytest <test_name>`` there inside the confinement.

    Used for the bench's hidden verifier: the test (hidden included) and the delivered target
    are read from the copy only; the workspace is never readable by the run. Pytest config
    discovery is pinned to the copy."""

    source = Path(source_dir).resolve()
    staging = Path(tempfile.mkdtemp(prefix="nexus-confined-dir-")).resolve()
    try:
        for entry in sorted(source.iterdir()):
            if entry.name.startswith(".") or entry.is_symlink() or not entry.is_file():
                continue
            shutil.copyfile(entry, staging / entry.name, follow_symlinks=False)
        (staging / DIR_COPY_PYTEST_CONFIG).write_text("[pytest]\n", encoding="utf-8")
        command = [
            sys.executable,
            "-I",
            "-m",
            "pytest",
            "-q",
            "--maxfail=1",
            "--rootdir",
            ".",
            "-c",
            DIR_COPY_PYTEST_CONFIG,
            "-p",
            "no:cacheprovider",
            "--",
            Path(test_name).name,
        ]
        return run_confined_test(
            staging,
            command=command,
            forbidden_paths=forbidden_paths,
            forbidden_names=(),
            timeout_sec=timeout_sec,
        )
    finally:
        shutil.rmtree(staging, ignore_errors=True)
