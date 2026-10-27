"""Shared sandbox primitives for running untrusted (PR- or candidate-controlled) code.

Used by the ultra-review lanes (``nexus.engine.ultra_review_service``) and the committee patch
execution verifier (``nexus.committee.execution_verifier``). Everything here fails closed:

* ``os_sandbox_available`` reports whether an OS barrier (macOS ``sandbox-exec``) exists; callers
  must not execute untrusted code when it does not.
* ``build_sandbox_profile`` emits a default-deny SBPL policy (``$HOME`` read-denied first, then
  only the sandbox, the trusted interpreter prefixes and fixed system locations readable,
  credential stores denied again last, no network, writes only inside the sandbox). Every
  interpolated path goes through ``sbpl_path``.
* ``scrubbed_env`` / ``git_safe_env`` drop every caller variable outside a small allowlist.
* ``diff_policy_violations`` / ``unsafe_summary_lines`` / ``lstat_walk_violations`` refuse
  symlink, gitlink, rename/copy and ``.git`` patches before and after ``git apply``.
"""

from __future__ import annotations

import os
import re
import shutil
import signal
import stat
import subprocess  # nosec B404 - argv lists only, never a shell
import sys
import tempfile
from collections.abc import Callable, Iterable
from pathlib import Path

# Only removes the barrier (fail closed), never grants one; lets the non-macOS contract be
# exercised anywhere.
DISABLE_OS_SANDBOX_ENVS = ("NEXUS_ULTRA_REVIEW_DISABLE_OS_SANDBOX", "NEXUS_DISABLE_OS_SANDBOX")
# Lane subprocesses see only these caller variables; everything else (tokens, credentials,
# provider keys) is dropped.
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
    # The bench's hidden-test staging parent: denied by the LAST profile rule for every
    # confined lane (seam, ultra_review, committee, swarm), whatever its read roots are.
    ".cache/nexus-bench-hidden",
)
_OS_SANDBOX_PROBE: dict[str, bool] = {}
# The barrier binary is never looked up on the inherited PATH (a planted ``sandbox-exec``
# earlier on PATH could "confine" nothing).
SANDBOX_EXEC = "/usr/bin/sandbox-exec"
# Runs a script with its own directory on sys.path, as ``python script.py`` would (``-I``
# alone drops it). Fixed code: the script path arrives as argv, never interpolated.
SCRIPT_BOOTSTRAP = (
    "import os, runpy, sys; s = sys.argv[1]; sys.argv = sys.argv[1:]; "
    "sys.path.insert(0, os.path.dirname(s)); runpy.run_path(s, run_name='__main__')"
)
# Every path interpolated into the sandbox-exec (SBPL) profile must match this: no quote,
# backslash, paren, tab, newline, other control or non-ASCII character can reach an SBPL
# string literal, so no PR-, branch- or user-derived text can close a literal and rewrite the
# policy. The plain ASCII space is allowed: inside a double-quoted literal it is inert, and
# macOS keeps per-user data under ``~/Library/Application Support`` (the Gateway deployment
# root lives there; rejecting it blocked every live ultra_review run, #2665).
SBPL_SAFE_PATH = re.compile(r"^/[A-Za-z0-9._/@+ -]*$")
# System locations the confined interpreter needs to start: subtrees, then single files.
# Nothing under a user's home directory, no temp tree, no repository root.
# ``/usr/share/i18n`` holds only the system charset tables (``csmapper``/``esdb``) that libiconv
# loads: without it ``git status`` fails with ``iconv_open(UTF-8,UTF-8-MAC)`` (#2665, P6).
SANDBOX_SYSTEM_READ_SUBPATHS = (
    "/usr/lib",
    "/usr/share/zoneinfo",
    "/usr/share/i18n",
    "/System/Library",
)
SANDBOX_SYSTEM_READ_LITERALS = (
    "/",
    "/private/etc/passwd",
    "/private/etc/localtime",
    "/dev/null",
    "/dev/urandom",
)
# Single system tool files some lanes' test runs need: ``/usr/bin/shasum`` is a Perl script,
# so Perl must read it (an executable binary needs no read grant to be exec'd) (#2650).
SANDBOX_TOOL_READ_FILES = ("/usr/bin/shasum",)
# The active developer dir (``xcode-select -p``) is read-allowed for confined git: ``/usr/bin/git``
# is an xcrun shim that loads ``libxcrun`` and the real git from it (#2650). Only a system
# toolchain location is accepted, never a path under a user's home or a temp tree.
DEVELOPER_DIR_ALLOWED_PREFIXES = ("/Library/Developer/", "/Applications/")
XCODE_SELECT = "/usr/bin/xcode-select"
_DEVELOPER_DIR_PROBE: dict[str, list[str]] = {}
# A readable subtree may never be (or contain) one of these.
# (The bare temp roots are joined, not literal: this is a deny list, not a temp-file use.)
SANDBOX_FORBIDDEN_READ_ROOTS = (
    "/",
    "/Users",
    "/home",
    "/private",
    "/private/tmp",
    os.path.join(os.sep, "tmp"),
    "/private/var",
    "/var",
)
# Git never runs hooks, fsmonitor, LFS/other filter processes or external diff/textconv, and
# never reads system/global config. Passed as GIT_CONFIG_COUNT/KEY/VALUE (equivalent to
# ``git -c``, highest precedence) by git_safe_env.
GIT_SAFE_CONFIG = (
    ("core.hooksPath", "/dev/null"),
    ("core.fsmonitor", "false"),
    ("filter.lfs.required", "false"),
    ("filter.lfs.process", ""),
    ("filter.lfs.smudge", ""),
    ("filter.lfs.clean", ""),
    ("diff.external", ""),
    ("core.pager", "cat"),
    ("protocol.allow", "never"),
)
# Caller variables a git call keeps (no tokens, credentials or GIT_* overrides).
GIT_ENV_ALLOWLIST = ("PATH", "LANG", "LC_ALL", "LC_CTYPE", "SYSTEMROOT", "TMPDIR")
SYMLINK_MODE = "120000"
# ``git apply --summary`` lines that make a patch unreviewable: link/gitlink creation,
# deletion or mode change, and rename/copy.
UNSAFE_PATCH_SUMMARY = re.compile(
    r"^\s*(?:(?:create|delete) mode (?:120000|160000)\b|mode change .*\b(?:120000|160000)\b|rename |copy )",
    re.MULTILINE,
)


class SandboxError(RuntimeError):
    """Raised when a sandboxed run cannot be set up safely (always fail closed)."""


def os_sandbox_available() -> bool:
    """True when an OS-level barrier (macOS sandbox-exec) can confine lane subprocesses."""

    if any(os.getenv(name, "").strip() == "1" for name in DISABLE_OS_SANDBOX_ENVS):
        return False
    if "sandbox-exec" not in _OS_SANDBOX_PROBE:
        ok = False
        if sys.platform == "darwin" and os.path.isfile(SANDBOX_EXEC):
            try:
                ok = (
                    subprocess.run(  # noqa: S603 - fixed argv probe
                        [SANDBOX_EXEC, "-p", "(version 1) (allow default)", "/usr/bin/true"],
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


def sbpl_path(path: Path | str) -> str:
    """Return ``path`` resolved and absolute, safe to embed in an SBPL string literal.

    Raises SandboxError (fail closed) instead of escaping: a path that needs escaping is never
    placed in the sandbox policy.
    """

    text = str(path)
    if not text or not os.path.isabs(text):
        raise SandboxError("sandbox_path_not_absolute")
    resolved = str(Path(text).resolve())
    if (
        not SBPL_SAFE_PATH.fullmatch(resolved)
        or "/../" in resolved + "/"
        or resolved.endswith("/..")
    ):
        raise SandboxError("sandbox_path_unsafe_for_policy")
    return resolved


def write_no_follow(target: Path, data: bytes) -> None:
    """Write ``data`` to ``target`` without following a symlink at (or replacing into) it."""

    if target.is_symlink() or target.exists():
        if target.is_dir() and not target.is_symlink():
            raise SandboxError(f"refusing_to_overwrite_directory:{target.name}")
        target.unlink()
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(target, flags, 0o600)
    with os.fdopen(fd, "wb") as handle:
        handle.write(data)


def in_tree(path: Path | str, roots: Iterable[Path | str | None]) -> bool:
    """True when ``path`` resolves to, or below, one of ``roots``."""

    candidate = Path(path).resolve()
    for root in roots:
        if not root:
            continue
        root_path = Path(root).resolve()
        if candidate == root_path or root_path in candidate.parents:
            return True
    return False


def scoped_path(root: Path, rel: str) -> Path | None:
    """``root/rel`` resolved, or None when it escapes ``root`` or crosses a symlink."""

    if not rel or "\x00" in rel:
        return None
    base = Path(root).resolve()
    candidate = Path(rel)
    if not candidate.is_absolute():
        candidate = base / candidate
    current = base
    try:
        rel_parts = candidate.relative_to(base).parts
    except ValueError:
        rel_parts = ()
    for part in rel_parts:
        current = current / part
        if current.is_symlink():
            return None
    resolved = candidate.resolve()
    if resolved != base and base not in resolved.parents:
        return None
    return resolved


def checked_read_roots(
    roots: Iterable[str],
    *,
    extra_forbidden: Iterable[Path] = (),
    forbidden_subtrees: Iterable[Path | str] = (),
) -> list[str]:
    """Validate readable subtrees (none may be, or contain, ``$HOME``/``/Users``/a temp root/
    a repository root) and append the fixed system subpaths. Fails closed."""

    validated = {sbpl_path(root) for root in roots}
    forbidden = {Path(path) for path in SANDBOX_FORBIDDEN_READ_ROOTS}
    forbidden.add(Path(os.path.expanduser("~")).resolve())
    forbidden.add(Path(tempfile.gettempdir()).resolve())
    forbidden.update(Path(path).resolve() for path in extra_forbidden)
    # ``forbidden_subtrees`` (hidden tests, the bench staging parent, fixture trees) deny their
    # WHOLE subtree: a read root inside one would re-open it, because the profile's later
    # ``allow file-read*`` rule overrides the earlier ``$HOME`` deny. ``extra_forbidden`` (e.g.
    # a repository root whose venv or worktree legitimately lives below it) and the broad
    # defaults only forbid being or containing them.
    subtrees = {Path(path).resolve() for path in forbidden_subtrees}
    forbidden.update(subtrees)
    for root in validated:
        root_path = Path(root)
        if any(root_path == bad or root_path in bad.parents for bad in forbidden):
            raise SandboxError(f"sandbox_read_root_overbroad:{root}")
        if any(bad in root_path.parents for bad in subtrees):
            raise SandboxError(f"sandbox_read_root_inside_forbidden:{root}")
    validated.update(path for path in SANDBOX_SYSTEM_READ_SUBPATHS if os.path.exists(path))
    return sorted(validated)


def interpreter_read_roots() -> list[str]:
    """The trusted interpreter prefixes (venv and base installation)."""

    return [
        sbpl_path(Path(sys.prefix).resolve()),
        sbpl_path(Path(sys.base_prefix).resolve()),
    ]


def developer_toolchain_read_roots() -> list[str]:
    """The macOS active developer dir (``xcode-select -p``) as a read root, or ``[]``.

    Resolved once with a fixed binary path and an empty environment (no ``DEVELOPER_DIR``
    override), and accepted only when it resolves to an existing directory under
    ``DEVELOPER_DIR_ALLOWED_PREFIXES`` that is also safe for an SBPL literal. Anything else
    (non-macOS, no Command Line Tools, an unusual location) yields ``[]``: git then stays
    unavailable inside the sandbox, which is the pre-#2650 behaviour (fail closed)."""

    if "developer_dir" not in _DEVELOPER_DIR_PROBE:
        roots: list[str] = []
        if sys.platform == "darwin" and os.path.isfile(XCODE_SELECT):
            try:
                found = subprocess.run(  # noqa: S603 - fixed argv, empty env
                    [XCODE_SELECT, "-p"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                    check=False,
                    env={},
                )
                text = (found.stdout or "").strip() if found.returncode == 0 else ""
                if text and os.path.isabs(text):
                    resolved = sbpl_path(text)
                    if os.path.isdir(resolved) and any(
                        resolved.startswith(prefix) for prefix in DEVELOPER_DIR_ALLOWED_PREFIXES
                    ):
                        roots = [resolved]
            except (OSError, subprocess.SubprocessError, SandboxError):
                roots = []
        _DEVELOPER_DIR_PROBE["developer_dir"] = roots
    return list(_DEVELOPER_DIR_PROBE["developer_dir"])


def tool_read_roots() -> list[str]:
    """Existing ``SANDBOX_TOOL_READ_FILES`` plus the developer toolchain dir (#2650)."""

    return [
        *(path for path in SANDBOX_TOOL_READ_FILES if os.path.isfile(path)),
        *developer_toolchain_read_roots(),
    ]


def build_sandbox_profile(
    *,
    writable: Iterable[str],
    read_roots: Iterable[str],
    deny_subtrees: Iterable[Path | str] = (),
    allow_signal_same_sandbox: bool = False,
    read_only_paths: Iterable[str] = (),
) -> str:
    """SBPL policy for one confined command (last matching rule wins).

    Reads: default-deny; ``$HOME`` is denied before the ``read_roots`` allows, and credential
    stores are denied again last, so they stay unreadable even if an allowed root contains
    them. No network. Writes only inside ``writable``.

    Signals: only to the process itself by default. ``allow_signal_same_sandbox`` also lets
    it signal processes inside the same sandbox (its own children and process group), never
    a process outside it; test suites that kill their own subprocesses need it.

    ``read_only_paths`` (absolute, already SBPL-safe, not resolved: a symlink there must not be
    replaceable either) stay unwritable even inside ``writable``.
    """

    writes = " ".join(f'(subpath "{sbpl_path(path)}")' for path in writable)
    if not writes:
        raise SandboxError("sandbox_not_bound")
    readable = " ".join(f'(subpath "{sbpl_path(path)}")' for path in read_roots)
    real_home = sbpl_path(Path(os.path.expanduser("~")).resolve())
    denied = " ".join(
        f'(subpath "{sbpl_path(Path(real_home) / rel)}")' for rel in SANDBOX_DENIED_HOME_PATHS
    )
    literals = " ".join(f'(literal "{path}")' for path in SANDBOX_SYSTEM_READ_LITERALS)
    return "\n".join([
        "(version 1)",
        "(deny default)",
        "(allow process-fork)",
        "(allow process-exec*)",
        f'(deny file-read* (subpath "{real_home}"))',
        "(allow file-read-metadata)",
        # Single system files (and the "/" entry itself, not its subtree).
        f"(allow file-read* {literals})",
        f"(allow file-read* {readable})",
        "(allow sysctl-read)",
        "(allow mach-lookup)",
        "(allow ipc-posix-shm)",
        "(allow signal (target self))",
        *(["(allow signal (target same-sandbox))"] if allow_signal_same_sandbox else []),
        "(deny network*)",
        f'(allow file-write* {writes} (literal "/dev/null") (literal "/dev/tty") (literal "/dev/dtracehelper"))',
        *(f'(deny file-write* (subpath "{path}"))' for path in read_only_paths),
        f"(deny file-read* {denied})",
        # Last rule wins: forbidden subtrees stay unreadable even under an allowed root.
        *(
            f'(deny file-read* (subpath "{sbpl_path(Path(path).resolve())}"))'
            for path in deny_subtrees
        ),
    ])


def scrubbed_env(
    *, home: Path | str, tmp: Path | str, untrusted_roots: Iterable[Path | str | None]
) -> dict[str, str]:
    """Allowlisted caller env; PATH/VIRTUAL_ENV never resolve into an untrusted tree; HOME and
    TMPDIR point inside the sandbox; no PYTHONPATH (every Python lane runs with ``-I``)."""

    roots = list(untrusted_roots)
    env = {key: os.environ[key] for key in SANDBOX_ENV_ALLOWLIST if key in os.environ}
    if "PATH" in env:
        env["PATH"] = os.pathsep.join(
            part
            for part in env["PATH"].split(os.pathsep)
            if part and os.path.isabs(part) and not in_tree(part, roots)
        )
    if "VIRTUAL_ENV" in env and in_tree(env["VIRTUAL_ENV"], roots):
        env.pop("VIRTUAL_ENV")
    env["HOME"] = str(home or "")
    env["TMPDIR"] = str(tmp or "")
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONNOUSERSITE"] = "1"
    env["NEXUS_SANDBOX_NO_NETWORK"] = "1"
    return env


def git_safe_env(
    *,
    home: Path | str,
    filter_drivers: Iterable[str] = (),
    git_dir: Path | None = None,
    work_tree: Path | None = None,
    ceiling: Path | None = None,
) -> dict[str, str]:
    """Environment for a git call on untrusted content: no system/global config, no inherited
    ``GIT_*``, hooks/fsmonitor/filters/external diff off. ``ceiling`` stops repository
    discovery above a directory (so ``git apply`` there never binds to an enclosing repo)."""

    env = {key: os.environ[key] for key in GIT_ENV_ALLOWLIST if key in os.environ}
    env.update({
        "HOME": str(home),
        "XDG_CONFIG_HOME": str(home),
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_ATTR_NOSYSTEM": "1",
        "GIT_LFS_SKIP_SMUDGE": "1",
    })
    overrides = [*GIT_SAFE_CONFIG]
    for name in filter_drivers:
        overrides.extend([
            (f"filter.{name}.smudge", ""),
            (f"filter.{name}.clean", ""),
            (f"filter.{name}.process", ""),
            (f"filter.{name}.required", "false"),
        ])
    env["GIT_CONFIG_COUNT"] = str(len(overrides))
    for index, (key, value) in enumerate(overrides):
        env[f"GIT_CONFIG_KEY_{index}"] = key
        env[f"GIT_CONFIG_VALUE_{index}"] = value
    if git_dir is not None:
        env["GIT_DIR"] = str(git_dir)
        env["GIT_WORK_TREE"] = str(work_tree or "")
    if ceiling is not None:
        env["GIT_CEILING_DIRECTORIES"] = str(ceiling)
    return env


def diff_policy_violations(diff_text: str) -> dict[str, list[str]]:
    """Paths the diff makes (or keeps) symlinks, and paths with a ``.git`` component."""

    symlinks: list[str] = []
    nested_git: list[str] = []
    current = ""
    for line in diff_text.splitlines():
        if line.startswith("diff --git "):
            match = re.match(r"^diff --git a/(.*) b/(.*)$", line)
            current = match.group(2) if match else ""
            if (
                match
                and current not in nested_git
                and any(
                    part.lower() == ".git"
                    for side in (match.group(1), match.group(2))
                    for part in Path(side).parts
                )
            ):
                nested_git.append(current)
            continue
        if line.startswith(("--- ", "+++ ")):
            target = line[4:].strip()
            if target.startswith(("a/", "b/")):
                target = target[2:]
            if (
                target != "/dev/null"
                and target not in nested_git
                and any(part.lower() == ".git" for part in Path(target).parts)
            ):
                nested_git.append(target)
            continue
        if not current:
            continue
        mode_line = line.startswith((
            "new file mode ",
            "new mode ",
            "old mode ",
            "deleted file mode ",
        ))
        index_line = line.startswith("index ") and line.rstrip().endswith(" " + SYMLINK_MODE)
        if (mode_line and line.rstrip().endswith(SYMLINK_MODE)) or index_line:
            if current not in symlinks:
                symlinks.append(current)
    return {"symlinks": symlinks, "nested_git": nested_git}


def unsafe_summary_lines(summary_stdout: str) -> list[str]:
    """Lines of ``git apply --summary`` output that create/delete/re-mode a symlink or gitlink,
    or rename/copy a path."""

    return [
        match.group(0)
        for match in re.finditer(r"^.*$", summary_stdout or "", re.MULTILINE)
        if UNSAFE_PATCH_SUMMARY.search(match.group(0))
    ]


def lstat_walk_violations(
    root: Path, *, on_symlink: Callable[[Path, str], bool] | None = None
) -> list[str]:
    """lstat-walk ``root`` (never following links). Any entry that is not a regular file or
    directory is offending unless ``on_symlink(path, rel)`` accepts a symlink. Returns the
    offending relative paths."""

    offending: list[str] = []
    for current, dirs, files in os.walk(root, followlinks=False):
        for name in [*dirs, *files]:
            path = Path(current) / name
            rel = path.relative_to(root).as_posix()
            info = os.lstat(path)
            if stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode):
                continue
            if stat.S_ISLNK(info.st_mode) and on_symlink is not None and on_symlink(path, rel):
                continue
            offending.append(rel)
    return offending


def copy_tree_no_symlinks(source: Path, dest: Path, *, ignore_names: Iterable[str] = ()) -> None:
    """Copy ``source`` to ``dest`` skipping every symlink (dangling or not) and ``ignore_names``."""

    patterns = shutil.ignore_patterns(*ignore_names)

    def ignore(path: str, names: list[str]) -> set[str]:
        ignored = set(patterns(path, names))
        ignored.update(name for name in names if os.path.islink(os.path.join(path, name)))
        return ignored

    shutil.copytree(source, dest, ignore=ignore, symlinks=True, ignore_dangling_symlinks=True)


def run_confined(
    argv: list[str],
    *,
    cwd: Path,
    confine_roots: Iterable[Path | str | None],
    profile: Callable[[], str],
    env: dict[str, str],
    timeout: float,
    require_barrier: bool = False,
    stdin_text: str | None = None,
    kill_process_group: bool = False,
) -> subprocess.CompletedProcess:
    """Run ``argv`` (never a shell) with ``env`` in a ``cwd`` inside ``confine_roots``, wrapped
    in ``sandbox-exec`` when available. ``require_barrier`` refuses to run without one.
    ``stdin_text``, when given, is the child's whole stdin (a pipe, never the caller's).
    ``kill_process_group`` starts the child in its own session and, on timeout, SIGKILLs that
    whole process group by the child's PID, so grandchildren do not outlive the run (#2650).
    Raises subprocess.TimeoutExpired on timeout."""

    if not argv:
        raise SandboxError("empty_lane_command")
    resolved_cwd = Path(cwd).resolve()
    if not in_tree(resolved_cwd, confine_roots):
        raise SandboxError("lane_cwd_outside_sandbox")
    command = list(argv)
    if command[0] == sys.executable and command[1:2] != ["-I"]:
        raise SandboxError("python_lane_not_isolated")
    if os_sandbox_available():
        command = [SANDBOX_EXEC, "-p", profile(), *command]
    elif require_barrier:
        raise SandboxError("no_os_barrier")
    if kill_process_group:
        return _run_in_own_process_group(
            command, cwd=resolved_cwd, env=env, timeout=timeout, stdin_text=stdin_text
        )
    return subprocess.run(  # noqa: S603 - argv list, no shell
        command,
        cwd=resolved_cwd,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout,
        input=stdin_text,
    )


def _run_in_own_process_group(
    command: list[str], *, cwd: Path, env: dict[str, str], timeout: float, stdin_text: str | None
) -> subprocess.CompletedProcess:
    """``subprocess.run`` equivalent whose timeout kills the child's whole process group.

    The child starts a new session, so its PID is its process group id. On timeout the group
    is SIGKILLed by that PID before the child is reaped (so the id cannot have been reused),
    and every descendant still in the group dies with it (#2650: orphaned ``stall``
    grandchildren of a timed-out ghost run kept running for hours)."""

    proc = subprocess.Popen(  # noqa: S603 - argv list, no shell
        command,
        cwd=cwd,
        env=env,
        stdin=subprocess.PIPE if stdin_text is not None else subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    try:
        stdout, stderr = proc.communicate(input=stdin_text, timeout=timeout)
    except subprocess.TimeoutExpired:
        _kill_group(proc.pid)
        try:
            stdout, stderr = proc.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            # A descendant that left the group still holds the pipes: stop reading.
            for stream in (proc.stdout, proc.stderr):
                if stream is not None:
                    stream.close()
            proc.wait()
            stdout, stderr = "", ""
        raise subprocess.TimeoutExpired(command, timeout, output=stdout, stderr=stderr) from None
    except BaseException:
        _kill_group(proc.pid)
        proc.wait()
        raise
    return subprocess.CompletedProcess(command, proc.returncode, stdout, stderr)


def _kill_group(pid: int) -> None:
    """SIGKILL the process group led by ``pid`` (a child started with a new session)."""

    try:
        os.killpg(pid, signal.SIGKILL)
    except OSError:
        pass


def trusted_executable(name: str, *, untrusted_roots: Iterable[Path | str | None]) -> str:
    """Absolute path of ``name`` from the caller's PATH, skipping relative entries and every
    entry inside an untrusted tree. Raises SandboxError when none is found."""

    roots = list(untrusted_roots)
    for entry in os.environ.get("PATH", "").split(os.pathsep):
        if not entry or not os.path.isabs(entry) or in_tree(entry, roots):
            continue
        candidate = Path(entry) / name
        if candidate.is_file() and os.access(candidate, os.X_OK) and not in_tree(candidate, roots):
            return str(candidate)
    raise SandboxError(f"tool_unavailable:{name}")


def python_script_argv(script: Path, args: Iterable[str] = ()) -> list[str]:
    """Trusted interpreter, ``-I``, fixed bootstrap, then the (already scoped) script."""

    return [sys.executable, "-I", "-c", SCRIPT_BOOTSTRAP, str(script), *args]


class Confinement:
    """A bound sandbox: one profile and one env for every command run in it. Only exists when
    an OS barrier exists; every run requires it."""

    def __init__(self, *, profile: str, env: dict[str, str], roots: tuple[Path, ...]) -> None:
        self.profile = profile
        self.env = env
        self.roots = roots

    def describe(self) -> dict[str, object]:
        return {
            "barrier": "macos_sandbox_exec",
            "network": "denied",
            "writes_confined_to": [str(root) for root in self.roots],
            "env": "allowlist:" + ",".join(SANDBOX_ENV_ALLOWLIST) + "+HOME/TMPDIR in sandbox",
            "credential_paths_read_denied": list(SANDBOX_DENIED_HOME_PATHS),
        }

    def run(self, argv: list[str], *, cwd: Path, timeout: float) -> subprocess.CompletedProcess:
        return run_confined(
            argv,
            cwd=cwd,
            confine_roots=self.roots,
            profile=lambda: self.profile,
            env=self.env,
            timeout=timeout,
            require_barrier=True,
        )


def confinement(
    *,
    sandbox: Path,
    extra_writable: Iterable[Path] = (),
    untrusted_roots: Iterable[Path] = (),
    extra_forbidden: Iterable[Path] = (),
    extra_readable: Iterable[Path | str] = (),
    forbidden_subtrees: Iterable[Path | str] = (),
    read_only_paths: Iterable[str] = (),
) -> Confinement:
    """Bind a sandbox (``home/`` and ``tmp/`` created inside ``sandbox``): writes and reads only
    in ``sandbox`` + ``extra_writable`` (+ interpreter prefixes and system paths for reads).
    Raises SandboxError("no_os_barrier") when there is no OS barrier: nothing may run."""

    if not os_sandbox_available():
        raise SandboxError("no_os_barrier")
    subtrees = tuple(forbidden_subtrees)
    home, tmp = sandbox / "home", sandbox / "tmp"
    home.mkdir(parents=True, exist_ok=True)
    tmp.mkdir(parents=True, exist_ok=True)
    writable = tuple(Path(sbpl_path(path)) for path in (sandbox, *extra_writable))
    if in_tree(sys.executable, writable):
        raise SandboxError("interpreter_inside_sandbox")
    read_roots = checked_read_roots(
        [
            *(str(path) for path in writable),
            *interpreter_read_roots(),
            # Optional read-only system toolchain roots (e.g. /usr/bin for git); validated by
            # checked_read_roots like every other root, never $HOME or a repository.
            *(str(path) for path in extra_readable if os.path.exists(path)),
        ],
        extra_forbidden=extra_forbidden,
        forbidden_subtrees=subtrees,
    )
    profile = build_sandbox_profile(
        writable=[str(p) for p in writable],
        read_roots=read_roots,
        deny_subtrees=subtrees,
        read_only_paths=read_only_paths,
    )
    env = scrubbed_env(
        home=sbpl_path(home), tmp=sbpl_path(tmp), untrusted_roots=(*untrusted_roots, *writable)
    )
    return Confinement(profile=profile, env=env, roots=writable)
