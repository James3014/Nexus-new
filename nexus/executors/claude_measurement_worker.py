"""Measurement-only Claude worker for the #2721 bare-vs-Nexus study.

#2721 (prereg v0.4 §9) runs one model, ``claude-haiku-5-5``, in both arms.
The NEXUS arm reaches it through P1 (``nexus_worker_candidate``); the BARE arm
calls ``ClaudeMeasurementWorkerAdapter.invoke`` directly.  This module is the
single definition of the run, so both arms get the same argv, environment,
sandbox, network policy and time cap; they differ only in the prompt text
Nexus appends and in the work directory path.

The worker is inert unless ``NEXUS_MEASUREMENT_CLAUDE_WORKER=1`` is set in the
process environment (only the measurement Gateway sets it).  With the switch
off, the worker registry, provider allowlist and workforce policy are exactly
what they were before this module existed.

One run:

* executable: ``NEXUS_MEASUREMENT_CLAUDE_BIN``, an absolute path that is not a
  symlink (a pinned ``versions/<x.y.z>`` binary, so auto-update cannot move
  it); ``NEXUS_MEASUREMENT_CLAUDE_VERSION`` optionally pins the version string;
* auth: a dedicated, spend-capped API key, read only by this module from the
  0600 ``KEY=value`` file named by ``NEXUS_MEASUREMENT_ANTHROPIC_ENV_FILE`` and
  passed to the CLI as ``ANTHROPIC_API_KEY``; it is redacted from everything
  kept (trace, sidecar, receipt tails);
* isolation: ``--bare`` (no CLAUDE.md, memory, hooks, plugins, keychain or
  OAuth), ``--setting-sources "" --strict-mcp-config`` with an empty MCP
  config, no web tools, subagents or workflows (``--disallowedTools``), a
  fresh empty HOME / ``CLAUDE_CONFIG_DIR`` / TMPDIR per run, auto-update,
  telemetry and non-essential traffic off;
* sandbox: a Seatbelt profile that allows writes only to the target (its
  ``.git`` stays read-only) and the run root; allows reads of user data only
  in the target, the run root, the task venv, the CLI install and the
  operator's ``NEXUS_MEASUREMENT_READ_ROOTS``; starts no program from the
  writable roots; and allows outbound network only to a local proxy that
  tunnels ``api.anthropic.com:443`` when the TLS SNI matches;
* task environment: when ``<controller_repo_root>/../venv`` exists it is put
  first on PATH (read-only) with ``VIRTUAL_ENV``; the target's ``src``
  directory (or the target itself) is on ``PYTHONPATH``;
* trace: ``--output-format stream-json --verbose``; with
  ``NEXUS_MEASUREMENT_TRACE_DIR`` the raw stream and a sidecar (init event,
  proxy log, sandbox hash) are kept per task, keyed by the receipt's
  ``stdout_sha256``.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import select
import shutil
import socket
import tempfile
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Optional

MEASUREMENT_CLAUDE_ENV = "NEXUS_MEASUREMENT_CLAUDE_WORKER"
MEASUREMENT_CLAUDE_BIN_ENV = "NEXUS_MEASUREMENT_CLAUDE_BIN"
MEASUREMENT_CLAUDE_VERSION_ENV = "NEXUS_MEASUREMENT_CLAUDE_VERSION"
MEASUREMENT_ANTHROPIC_ENV_FILE_ENV = "NEXUS_MEASUREMENT_ANTHROPIC_ENV_FILE"
MEASUREMENT_READ_ROOTS_ENV = "NEXUS_MEASUREMENT_READ_ROOTS"
MEASUREMENT_TRACE_DIR_ENV = "NEXUS_MEASUREMENT_TRACE_DIR"
ANTHROPIC_API_KEY_ENV = "ANTHROPIC_API_KEY"

CLAUDE_MEASUREMENT_PROVIDER = "claude"
CLAUDE_MEASUREMENT_MODEL = "claude-haiku-5-5"
CLAUDE_MEASUREMENT_WORKER_ID = "claude_haiku_measure"
CLAUDE_DISALLOWED_TOOLS = "WebSearch,WebFetch,Task,Agent,Workflow"
# Explicit and identical in both arms: without it ``-p`` auto-denies every Bash
# call (no prompt), so the agent could not run tests.  Bash runs inside the
# Seatbelt sandbox below.
CLAUDE_ALLOWED_TOOLS = "Bash,Edit,Read"
EMPTY_MCP_CONFIG = '{"mcpServers":{}}'
CLAUDE_MEASUREMENT_FLAGS: tuple[str, ...] = (
    "-p",
    "--bare",
    "--setting-sources",
    "",
    "--strict-mcp-config",
    "--mcp-config",
    EMPTY_MCP_CONFIG,
    "--model",
    CLAUDE_MEASUREMENT_MODEL,
    "--permission-mode",
    "acceptEdits",
    "--allowedTools",
    CLAUDE_ALLOWED_TOOLS,
    "--disallowedTools",
    CLAUDE_DISALLOWED_TOOLS,
    "--output-format",
    "stream-json",
    "--verbose",
    "--no-session-persistence",
)
CLAUDE_MEASUREMENT_ENV: Mapping[str, str] = {
    "CLAUDE_CODE_DISABLE_AUTO_MEMORY": "1",
    "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
    "DISABLE_AUTOUPDATER": "1",
    "DISABLE_TELEMETRY": "1",
    "DISABLE_ERROR_REPORTING": "1",
}
# System directories only: no Homebrew, no ~/.local/bin (so no gh, agy, uv).
CLAUDE_MEASUREMENT_SYSTEM_PATH = "/usr/bin:/bin:/usr/sbin:/sbin"
ALLOWED_API_HOSTS: tuple[str, ...] = ("api.anthropic.com",)
# User-data roots whose contents a run may not read unless re-allowed.
_READ_DENIED_ROOTS: tuple[str, ...] = (
    "/Users",
    "/private/tmp",
    "/private/var/folders",
    "/Volumes",
    "/opt",
)
MEASUREMENT_CLAUDE_TIMEOUT_ENV = "NEXUS_MEASUREMENT_CLAUDE_TIMEOUT_SECONDS"
MEASUREMENT_KEY_LABEL_ENV = "NEXUS_MEASUREMENT_KEY_LABEL"
DEFAULT_MEASUREMENT_TIMEOUT_SECONDS = 900.0
# Both arms stop the CLI this many seconds before the cap so the diff snapshot fits.
SNAPSHOT_RESERVE_SECONDS = 30.0


def measurement_cli_timeout(
    requested: Optional[float], environ: Optional[Mapping[str, str]] = None
) -> float:
    """The CLI time limit, identical in both arms (review M2): the configured cap
    (``NEXUS_MEASUREMENT_CLAUDE_TIMEOUT_SECONDS``, default 900), never more than
    the caller's limit, minus the snapshot reserve."""
    env = os.environ if environ is None else environ
    try:
        cap = float(
            env.get(MEASUREMENT_CLAUDE_TIMEOUT_ENV, "") or DEFAULT_MEASUREMENT_TIMEOUT_SECONDS
        )
    except ValueError:
        cap = DEFAULT_MEASUREMENT_TIMEOUT_SECONDS
    if requested:
        cap = min(cap, float(requested))
    return max(1.0, cap - SNAPSHOT_RESERVE_SECONDS)


_DENIED_HELPER_EXECUTABLES: tuple[str, ...] = (
    "/usr/bin/open",
    "/usr/bin/osascript",
    "/usr/bin/security",
    "/usr/bin/pbcopy",
    "/usr/bin/pbpaste",
)
# Test-only switch for hosts without macOS Seatbelt (Linux CI); never set in production.
_USE_SEATBELT = True
_SAFE_TASK_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_INFRA_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("rate_limited", re.compile(r"\b429\b|rate[ _-]?limit|usage limit|quota", re.I)),
    ("overloaded", re.compile(r"\b529\b|overloaded", re.I)),
    (
        "auth",
        re.compile(r"\b401\b|\b403\b|authenticat|invalid api key|oauth|not logged in|login", re.I),
    ),
    (
        "api_error",
        re.compile(r"\b5\d\d\b|api[_ ]error|connection (?:error|refused|reset)|timed? ?out", re.I),
    ),
)


def measurement_claude_enabled(environ: Optional[Mapping[str, str]] = None) -> bool:
    """True only for the exact value ``"1"``; anything else keeps the worker off."""
    env = os.environ if environ is None else environ
    return str(env.get(MEASUREMENT_CLAUDE_ENV, "")) == "1"


def measurement_claude_executable(environ: Optional[Mapping[str, str]] = None) -> Optional[str]:
    """The configured CLI: absolute, executable and not a symlink; else None."""
    env = os.environ if environ is None else environ
    raw = str(env.get(MEASUREMENT_CLAUDE_BIN_ENV, "") or "").strip()
    if not raw or not os.path.isabs(raw):
        return None
    path = Path(raw)
    if path.is_symlink() or os.path.realpath(raw) != os.path.normpath(raw):
        return None
    if not path.is_file() or not os.access(path, os.X_OK):
        return None
    return str(path)


def measurement_claude_api_key(environ: Optional[Mapping[str, str]] = None) -> Optional[str]:
    """The measurement API key, read only from the 0600 ``KEY=value`` file named by
    ``NEXUS_MEASUREMENT_ANTHROPIC_ENV_FILE`` (``ANTHROPIC_API_KEY=...``); never
    from the process environment, never logged."""
    env = os.environ if environ is None else environ
    raw = str(env.get(MEASUREMENT_ANTHROPIC_ENV_FILE_ENV, "") or "").strip()
    if not raw:
        return None
    path = Path(raw)
    try:
        if not path.is_absolute() or path.is_symlink() or path.stat().st_mode & 0o077:
            return None
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    for line in lines:
        key, sep, value = line.strip().removeprefix("export ").partition("=")
        if sep and key.strip() == ANTHROPIC_API_KEY_ENV:
            value = value.strip().strip("'\"")
            return value or None
    return None


def claude_measurement_argv(prompt: str) -> tuple[str, ...]:
    """Arguments after the executable; the prompt is the final positional."""
    text = str(prompt)
    if not text.strip():
        raise ValueError("claude measurement prompt is empty")
    if text.startswith("-"):
        raise ValueError("claude measurement prompt must not start with '-'")
    return (*CLAUDE_MEASUREMENT_FLAGS, text)


def task_venv_for(contract: Any) -> Optional[Path]:
    """The task venv: ``<controller_repo_root>/../venv`` when it is a real venv
    whose resolved location is a safe read root."""
    root = str(getattr(contract, "controller_repo_root", "") or "").strip()
    if not root:
        return None
    venv = Path(os.path.realpath(Path(root).parent / "venv"))
    if not (venv / "bin" / "python").exists() or not (venv / "pyvenv.cfg").is_file():
        return None
    return venv if is_safe_read_root(venv, configured_read_roots()) else None


def _venv_interpreter_home(venv: Path) -> Optional[Path]:
    """The install prefix of the interpreter the venv's python resolves to.

    Taken from the resolved ``bin/python`` symlink (never from ``pyvenv.cfg``),
    and only when it is a safe read root (gap review / Codex r1 #4).
    """
    python = Path(os.path.realpath(venv / "bin" / "python"))
    if not python.is_file() or python.parent.name != "bin":
        return None
    prefix = python.parent.parent
    return prefix if is_safe_read_root(prefix, configured_read_roots()) else None


def configured_read_roots(environ: Optional[Mapping[str, str]] = None) -> tuple[Path, ...]:
    """Operator-listed extra read roots (``NEXUS_MEASUREMENT_READ_ROOTS``, ``:``-separated,
    absolute), e.g. the task-venv directory and the uv interpreter store.  Each one
    must itself be narrow: never ``/``, a denied root, HOME, or an ancestor of HOME."""
    env = os.environ if environ is None else environ
    roots = []
    for raw in str(env.get(MEASUREMENT_READ_ROOTS_ENV, "") or "").split(":"):
        raw = raw.strip()
        if raw and os.path.isabs(raw) and _is_narrow(Path(raw)):
            roots.append(Path(os.path.realpath(raw)))
    return tuple(roots)


def _is_narrow(path: Path) -> bool:
    resolved = Path(os.path.realpath(path))
    home = Path(os.path.realpath(os.path.expanduser("~")))
    denied = {Path(os.path.realpath(root)) for root in _READ_DENIED_ROOTS}
    covers_denied = any(resolved in root.parents for root in denied)  # e.g. /private/var
    return (
        len(resolved.parts) >= 3
        and resolved not in denied
        and not covers_denied
        and resolved != home
        and resolved not in home.parents
    )


def _under_denied_root(path: Path) -> bool:
    for root in _READ_DENIED_ROOTS:
        real_root = Path(os.path.realpath(root))
        if path == real_root or real_root in path.parents:
            return True
    return False


def is_safe_read_root(path: Path, extra_roots: tuple[Path, ...] = ()) -> bool:
    """Whether ``path`` may be re-allowed for reading (Codex r1 #4, r2 #3).

    Allowed: a narrow path outside every denied user-data root (``/usr/...``),
    or a path inside one of the operator-listed ``extra_roots``.  Anything else
    under ``/Users``, ``/private/var``, ``/private/tmp`` ... is refused, so a
    symlinked venv cannot open a whole directory of user data.
    """
    resolved = Path(os.path.realpath(path))
    if not _is_narrow(resolved):
        return False
    if any(resolved == root or root in resolved.parents for root in extra_roots):
        return True
    return not _under_denied_root(resolved)


def measurement_child_env(
    *,
    run_root: Path,
    target: Path,
    proxy_url: str,
    token: Optional[str],
    venv: Optional[Path] = None,
    environ: Optional[Mapping[str, str]] = None,
) -> dict[str, str]:
    """The exact child environment of one measurement run (both arms)."""
    env = os.environ if environ is None else environ
    home = run_root / "home"
    child = {key: str(env[key]) for key in ("USER", "LOGNAME", "LANG") if env.get(key)}
    child.update(
        HOME=str(home),
        CLAUDE_CONFIG_DIR=str(home / ".claude"),
        TMPDIR=str(run_root / "tmp"),
        CLAUDE_CODE_TMPDIR=str(run_root / "tmp"),
        PATH=(f"{venv}/bin:" if venv else "") + CLAUDE_MEASUREMENT_SYSTEM_PATH,
        HTTPS_PROXY=proxy_url,
        HTTP_PROXY=proxy_url,
        ALL_PROXY=proxy_url,
        https_proxy=proxy_url,
        http_proxy=proxy_url,
        NO_PROXY="",
    )
    if venv is not None:
        src = target / "src"
        child["VIRTUAL_ENV"] = str(venv)
        child["PYTHONPATH"] = str(src if src.is_dir() else target)
    child.update(CLAUDE_MEASUREMENT_ENV)
    if token:
        child[ANTHROPIC_API_KEY_ENV] = token
    return child


def api_key_id(key: Optional[str]) -> Optional[str]:
    """A non-reversible label for the key a run used (first 12 hex of its sha256)."""
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:12] if key else None


def cli_install_dir_ok(cli_dir: Path) -> bool:
    """The CLI's directory may be re-allowed for reading when it is narrow and
    holds only executable regular files (CLI builds), never configs or secrets."""
    if not _is_narrow(cli_dir):
        return False
    try:
        entries = list(cli_dir.iterdir())
    except OSError:
        return False
    return all(
        entry.is_file()
        and not entry.is_symlink()
        and os.access(entry, os.X_OK)
        and not entry.name.startswith(".")
        for entry in entries
    )


MEASURE_EXTERNAL_TARGET_ROOT_ENV = "NEXUS_MEASURE_EXTERNAL_TARGET_ROOT"


class WorktreeGitdirOutsideMeasurementRoot(ValueError):
    """A linked worktree whose common gitdir is not a fresh per-task Controller
    under the measurement root (review H2'): its refs could hold the answer."""


def require_gitdir_in_measurement_root(
    target: Path, environ: Optional[Mapping[str, str]] = None
) -> None:
    """For a linked worktree, the common gitdir must resolve under
    ``NEXUS_MEASURE_EXTERNAL_TARGET_ROOT`` (where #2742 keeps one fresh Controller
    per task/repeat); otherwise the run fails.  A shared Controller (e.g. the
    Gateway's own Nexus-new checkout) could expose a later fix or earlier
    repeats' candidates through ``git log --all``."""
    dot_git = Path(target) / ".git"
    if not dot_git.is_file():
        return  # a standalone repository: its gitdir is inside the target
    env = os.environ if environ is None else environ
    raw_root = str(env.get(MEASURE_EXTERNAL_TARGET_ROOT_ENV, "") or "").strip()
    common = _linked_common_gitdir(Path(target))
    if not raw_root or not os.path.isabs(raw_root) or common is None:
        raise WorktreeGitdirOutsideMeasurementRoot("worktree_gitdir_outside_measurement_root")
    root = Path(os.path.realpath(raw_root))
    if root not in common.parents:
        raise WorktreeGitdirOutsideMeasurementRoot("worktree_gitdir_outside_measurement_root")


def _linked_common_gitdir(target: Path) -> Optional[Path]:
    dot_git = target / ".git"
    try:
        line = dot_git.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    if not line.startswith("gitdir:"):
        return None
    gitdir = Path(line.split(":", 1)[1].strip())
    gitdir = Path(os.path.realpath(gitdir if gitdir.is_absolute() else target / gitdir))
    try:
        common = (gitdir / "commondir").read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return Path(os.path.realpath(Path(common) if os.path.isabs(common) else gitdir / common))


def worktree_git_dirs(target: Path, controller_root: Optional[Path | str] = None) -> list[Path]:
    """For a linked worktree (``.git`` is a ``gitdir:`` file), its gitdir and the
    common gitdir; ``[]`` for a standalone repository.  Read from the files,
    never by running git on the worktree.

    Both must resolve inside ``<controller_root>/.git`` (the contract's
    Controller); anything else, e.g. a ``.git`` file repointed at ``~/.ssh``,
    is never admitted as a read root (Codex r3).
    """
    if controller_root is None:
        return []
    controller_git = Path(os.path.realpath(Path(controller_root) / ".git"))
    dot_git = Path(target) / ".git"
    if not dot_git.is_file() or dot_git.is_symlink():
        return []
    try:
        line = dot_git.read_text(encoding="utf-8").strip()
    except OSError:
        return []
    if not line.startswith("gitdir:"):
        return []
    gitdir = Path(line.split(":", 1)[1].strip())
    if not gitdir.is_absolute():
        gitdir = Path(target) / gitdir
    gitdir = Path(os.path.realpath(gitdir))
    roots = [gitdir]
    try:
        common = (gitdir / "commondir").read_text(encoding="utf-8").strip()
        common_dir = Path(common) if os.path.isabs(common) else gitdir / common
        roots.append(Path(os.path.realpath(common_dir)))
    except OSError:
        pass
    return [
        root
        for root in roots
        if root.is_dir()
        and _is_narrow(root)
        and (root == controller_git or controller_git in root.parents)
    ]


def _sbpl(path: Path | str) -> str:
    text = str(path)
    if '"' in text or "\\" in text or "\n" in text:
        raise ValueError("path not representable in a Seatbelt profile")
    return text


def build_claude_seatbelt_profile(
    *,
    target: Path,
    run_root: Path,
    readable: tuple[Path, ...],
    proxy_port: int,
) -> str:
    """Writes: target (not .git) and run root.  Reads: user data only in
    target, run root and ``readable``.  Network: the local proxy only."""
    target = Path(os.path.realpath(target))
    run_root = Path(os.path.realpath(run_root))
    reads = [target, run_root, *(Path(os.path.realpath(p)) for p in readable)]
    git_entry = _sbpl(target / ".git")
    lines = [
        "(version 1)",
        "(allow default)",
        "(deny file-write*)",
        "(allow file-write*",
        f'  (subpath "{_sbpl(target)}")',
        f'  (subpath "{_sbpl(run_root)}")',
        '  (literal "/dev/null")',
        '  (literal "/dev/tty")',
        '  (regex #"^/dev/fd/")',
        '  (regex #"^/dev/ttys"))',
        f'(deny file-write* (literal "{git_entry}") (subpath "{git_entry}"))',
        "(deny file-read-data",
        *[f'  (subpath "{root}")' for root in _READ_DENIED_ROOTS],
        ")",
        "(allow file-read-data",
        *[f'  (subpath "{_sbpl(path)}")' for path in reads],
        ")",
        # No program may be started from the writable roots (a copied helper
        # binary), nor these helpers that act through unsandboxed services
        # (LaunchServices, AppleScript, the keychain, the pasteboard).
        "(deny process-exec",
        f'  (subpath "{_sbpl(target)}")',
        f'  (subpath "{_sbpl(run_root)}")',
        *[f'  (literal "{tool}")' for tool in _DENIED_HELPER_EXECUTABLES],
        ")",
        # Signals only within this sandbox (the CLI and its own children): the
        # agent cannot kill other processes of the same user, such as a live
        # Gateway (review H1).
        "(deny signal)",
        "(allow signal (target same-sandbox))",
        "(deny network-outbound)",
        f'(allow network-outbound (remote ip "localhost:{int(proxy_port)}"))',
        '(allow network-outbound (literal "/private/var/run/syslog"))',
    ]
    return "\n".join(lines) + "\n"


def normalize_seatbelt_profile(
    profile: str, *, target: str, run_root: str, venv: Optional[str], git_dirs: tuple[str, ...] = ()
) -> str:
    """The profile with the per-run paths and proxy port replaced by placeholders."""
    text = profile
    for index, path in enumerate(sorted(git_dirs, key=len, reverse=True)):
        text = text.replace(path, f"<GITDIR{index}>")
    text = text.replace(run_root, "<RUN_ROOT>").replace(target, "<TARGET>")
    if venv:
        text = text.replace(venv, "<VENV>")
    return re.sub(r'remote ip "localhost:\d+"', 'remote ip "localhost:<PORT>"', text)


def tls_handshake_bytes(data: bytes) -> Optional[bytes]:
    """The first handshake message reassembled from consecutive TLS records,
    or None until it is complete (or when the bytes are not TLS handshake records)."""
    payload = b""
    pos = 0
    while pos + 5 <= len(data):
        if data[pos] != 0x16:
            return None
        length = int.from_bytes(data[pos + 3 : pos + 5], "big")
        if pos + 5 + length > len(data):
            return None
        payload += data[pos + 5 : pos + 5 + length]
        pos += 5 + length
        if len(payload) >= 4 and len(payload) >= 4 + int.from_bytes(payload[1:4], "big"):
            return payload[: 4 + int.from_bytes(payload[1:4], "big")]
    return None


def tls_client_hello_sni(data: bytes) -> Optional[str]:
    """The SNI host name of a TLS ClientHello (possibly split over several
    records), or None when absent, incomplete or malformed."""
    hello = tls_handshake_bytes(data)
    if hello is None or hello[0] != 0x01:
        return None
    try:
        end = len(hello)
        pos = 4 + 2 + 32  # handshake header, client version, random
        pos += 1 + hello[pos]  # session id
        pos += 2 + int.from_bytes(hello[pos : pos + 2], "big")  # cipher suites
        pos += 1 + hello[pos]  # compression methods
        ext_end = pos + 2 + int.from_bytes(hello[pos : pos + 2], "big")
        if ext_end > end:
            return None
        pos += 2
        while pos + 4 <= ext_end:
            ext_type = int.from_bytes(hello[pos : pos + 2], "big")
            ext_len = int.from_bytes(hello[pos + 2 : pos + 4], "big")
            pos += 4
            if pos + ext_len > ext_end:
                return None
            if ext_type == 0:
                body = hello[pos : pos + ext_len]
                list_len = int.from_bytes(body[0:2], "big")
                if list_len + 2 != len(body) or body[2] != 0:
                    return None
                name_len = int.from_bytes(body[3:5], "big")
                if 5 + name_len != len(body):
                    return None
                return body[5 : 5 + name_len].decode("ascii").lower()
            pos += ext_len
    except (IndexError, UnicodeDecodeError):
        return None
    return None


class HostAllowlistProxy:
    """A local HTTP CONNECT proxy that tunnels only ``ALLOWED_API_HOSTS:443``.

    Every attempt is logged (host, port, allowed), so a run that tried to
    reach anything else (a package index, GitHub) is visible in the trace.
    The tunnel opens only when the client's TLS ClientHello names the same
    host (SNI), so the CONNECT authority cannot front for another site.  At
    most ``max_connections`` connections are served at once; a client gets
    10 s to send its CONNECT header and its ClientHello.
    """

    def __init__(
        self, allowed_hosts: tuple[str, ...] = ALLOWED_API_HOSTS, max_connections: int = 32
    ):
        self.allowed_hosts = tuple(host.lower() for host in allowed_hosts)
        self.attempts: list[dict[str, Any]] = []
        self._server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._server.bind(("127.0.0.1", 0))
        self._server.listen(16)
        self.port = int(self._server.getsockname()[1])
        self._closed = threading.Event()
        self._lock = threading.Lock()
        self._slots = threading.BoundedSemaphore(max_connections)
        self._thread = threading.Thread(target=self._serve, daemon=True)

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def __enter__(self) -> "HostAllowlistProxy":
        self._thread.start()
        return self

    def __exit__(self, *_exc: Any) -> None:
        self.close()

    def close(self) -> None:
        self._closed.set()
        try:
            self._server.close()
        except OSError:
            pass

    def _serve(self) -> None:
        while not self._closed.is_set():
            try:
                client, _ = self._server.accept()
            except OSError:
                return
            if not self._slots.acquire(blocking=False):
                self._record("<over-connection-limit>", 0, False)
                try:
                    client.close()
                except OSError:
                    pass
                continue
            threading.Thread(target=self._handle_slot, args=(client,), daemon=True).start()

    def _handle_slot(self, client: socket.socket) -> None:
        try:
            self._handle(client)
        finally:
            self._slots.release()

    def _record(self, host: str, port: int, allowed: bool, **extra: Any) -> None:
        with self._lock:
            if len(self.attempts) < 1000:
                self.attempts.append({"host": host, "port": port, "allowed": allowed, **extra})

    def _handle(self, client: socket.socket) -> None:
        upstream: Optional[socket.socket] = None
        try:
            client.settimeout(10)
            head = b""
            while b"\r\n\r\n" not in head and len(head) < 16384:
                chunk = client.recv(4096)
                if not chunk:
                    return
                head += chunk
            request_line = head.split(b"\r\n", 1)[0].decode("latin-1")
            parts = request_line.split()
            if len(parts) < 2 or parts[0].upper() != "CONNECT":
                host = parts[1] if len(parts) > 1 else ""
                self._record(host[:200], 0, False)
                client.sendall(b"HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\n\r\n")
                return
            host, _, port_text = parts[1].rpartition(":")
            port = int(port_text) if port_text.isdigit() else 0
            allowed = host.lower() in self.allowed_hosts and port == 443
            if not allowed:
                self._record(host[:200], port, False)
                client.sendall(b"HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\n\r\n")
                return
            client.sendall(b"HTTP/1.1 200 Connection Established\r\n\r\n")
            hello = head.split(b"\r\n\r\n", 1)[1]
            while tls_handshake_bytes(hello) is None:
                if len(hello) >= 65536:
                    break
                chunk = client.recv(4096)
                if not chunk:
                    return
                hello += chunk
            sni = tls_client_hello_sni(hello)
            self._record(host[:200], port, sni == host.lower(), sni=sni)
            if sni != host.lower():
                return
            upstream = socket.create_connection((host, port), timeout=30)
            upstream.sendall(hello)
            client.settimeout(None)
            upstream.settimeout(None)
            sockets = [client, upstream]
            while not self._closed.is_set():
                ready, _, errored = select.select(sockets, [], sockets, 1.0)
                if errored:
                    return
                for source in ready:
                    data = source.recv(65536)
                    if not data:
                        return
                    (upstream if source is client else client).sendall(data)
        except (OSError, ValueError):
            return
        finally:
            for sock in (client, upstream):
                if sock is not None:
                    try:
                        sock.close()
                    except OSError:
                        pass


@dataclass(frozen=True)
class ClaudeStreamSummary:
    """What a stream-json run reports about itself."""

    result_seen: bool
    is_error: Optional[bool]
    subtype: str
    num_turns: Optional[int]
    total_cost_usd: Optional[float]
    usage: dict[str, Any]
    model_usage: dict[str, Any]
    models_seen: tuple[str, ...]
    tool_calls: tuple[dict[str, Any], ...]
    permission_denials: tuple[Any, ...]
    session_id: str
    result_text: str = ""
    api_error_status: Any = None
    terminal_reason: str = ""
    init: dict[str, Any] = field(default_factory=dict)
    # Models that actually produced output (assistant messages, modelUsage);
    # the init event's configured model is not evidence of service.
    served_models: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "result_seen": self.result_seen,
            "is_error": self.is_error,
            "subtype": self.subtype,
            "num_turns": self.num_turns,
            "total_cost_usd": self.total_cost_usd,
            "usage": self.usage,
            "model_usage": self.model_usage,
            "models_seen": list(self.models_seen),
            "served_models": list(self.served_models),
            "tool_calls": [dict(call) for call in self.tool_calls],
            "permission_denials": list(self.permission_denials),
            "session_id": self.session_id,
            "api_error_status": self.api_error_status,
            "terminal_reason": self.terminal_reason,
            "init": self.init,
        }


# Init-event fields that describe the agent's shell (compared across arms).
INIT_SHELL_FIELDS = (
    "tools",
    "mcp_servers",
    "model",
    "permissionMode",
    "slash_commands",
    "skills",
    "plugins",
    "agents",
    "claude_code_version",
    "output_style",
    "apiKeySource",
)


def summarize_stream_json(stdout: str | bytes) -> ClaudeStreamSummary:
    """Parse ``--output-format stream-json`` output; unknown lines are skipped."""
    text = stdout.decode("utf-8", errors="replace") if isinstance(stdout, bytes) else str(stdout)
    tool_calls: list[dict[str, Any]] = []
    models: list[str] = []
    served: list[str] = []
    result: dict[str, Any] = {}
    init: dict[str, Any] = {}
    session_id = ""
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict):
            continue
        kind = event.get("type")
        if kind == "system" and event.get("subtype") == "init" and not init:
            init = {key: event.get(key) for key in INIT_SHELL_FIELDS if key in event}
            session_id = str(event.get("session_id") or session_id)
            model = event.get("model")
            if isinstance(model, str) and model not in models:
                models.append(model)
        elif kind == "assistant":
            raw_message = event.get("message")
            message: dict[str, Any] = raw_message if isinstance(raw_message, dict) else {}
            model = message.get("model")
            if isinstance(model, str) and model not in models:
                models.append(model)
            if isinstance(model, str) and model not in served:
                served.append(model)
            for block in message.get("content") or []:
                if isinstance(block, dict) and block.get("type") == "tool_use":
                    tool_calls.append({
                        "id": str(block.get("id") or ""),
                        "name": str(block.get("name") or ""),
                        "input": block.get("input"),
                        "parent_tool_use_id": event.get("parent_tool_use_id"),
                    })
        elif kind == "result":
            result = event
    raw_usage = result.get("usage")
    usage: dict[str, Any] = raw_usage if isinstance(raw_usage, dict) else {}
    raw_model_usage = result.get("modelUsage")
    model_usage: dict[str, Any] = raw_model_usage if isinstance(raw_model_usage, dict) else {}
    for name in model_usage:
        if name not in models:
            models.append(str(name))
        if name not in served:
            served.append(str(name))
    num_turns = result.get("num_turns")
    cost = result.get("total_cost_usd")
    denials = result.get("permission_denials")
    return ClaudeStreamSummary(
        result_seen=bool(result),
        is_error=result.get("is_error") if isinstance(result.get("is_error"), bool) else None,
        subtype=str(result.get("subtype") or ""),
        num_turns=num_turns
        if isinstance(num_turns, int) and not isinstance(num_turns, bool)
        else None,
        total_cost_usd=float(cost)
        if isinstance(cost, (int, float)) and not isinstance(cost, bool)
        else None,
        usage=dict(usage),
        model_usage=dict(model_usage),
        models_seen=tuple(models),
        served_models=tuple(served),
        tool_calls=tuple(tool_calls),
        permission_denials=tuple(denials) if isinstance(denials, list) else (),
        session_id=str(result.get("session_id") or session_id),
        result_text=str(result.get("result") or "")[-4000:],
        api_error_status=result.get("api_error_status"),
        terminal_reason=str(result.get("terminal_reason") or ""),
        init=init,
    )


def classify_claude_infra(summary: ClaudeStreamSummary, stderr: str | bytes) -> Optional[str]:
    """``rate_limited`` / ``overloaded`` / ``auth`` / ``api_error`` when the run
    failed for a provider reason (both arms re-run it), else None.

    The run's own reply text is consulted only when the CLI itself reports an
    API error, so a task that merely talks about logins or quotas is never
    re-labelled infra; without that signal only stderr is read.
    """
    err = stderr.decode("utf-8", errors="replace") if isinstance(stderr, bytes) else str(stderr)
    api_error = summary.terminal_reason == "api_error" or summary.api_error_status not in (None, "")
    if summary.result_seen and summary.is_error is False and not api_error:
        return None
    if api_error:
        evidence = " ".join(
            str(part)
            for part in (
                summary.api_error_status,
                summary.subtype,
                summary.result_text,
                err[-4000:],
            )
            if part
        )
        for kind, pattern in _INFRA_PATTERNS:
            if pattern.search(evidence):
                return kind
        return "api_error"
    for kind, pattern in _INFRA_PATTERNS[:3]:
        if pattern.search(err[-4000:]):
            return kind
    return None


_API_KEY_SHAPE = re.compile(rb"sk" + rb"-ant-[A-Za-z0-9_\-]{8,}")  # split: no key-shaped literal
_SECRET_FRAGMENT = 16


def redact_secrets(data: bytes, secrets: tuple[str, ...]) -> bytes:
    """``data`` without the secrets: every key-shaped string, every exact secret
    and every ``_SECRET_FRAGMENT``-character piece of one (a secret printed in
    pieces) becomes ``<REDACTED>``."""
    data = _API_KEY_SHAPE.sub(b"<REDACTED>", bytes(data))
    for secret in secrets:
        raw = secret.encode("utf-8") if secret else b""
        if len(raw) < 8:
            continue
        data = data.replace(raw, b"<REDACTED>")
        for start in range(0, max(1, len(raw) - _SECRET_FRAGMENT + 1)):
            piece = raw[start : start + _SECRET_FRAGMENT]
            if len(piece) == _SECRET_FRAGMENT and piece in data:
                data = data.replace(piece, b"<REDACTED>")
    return data


def _write_private(path: Path, data: bytes) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as handle:
        handle.write(data)
    os.chmod(path, 0o600)


def write_measurement_trace(
    task_id: str,
    stdout: bytes,
    stdout_sha256: str,
    sidecar: Mapping[str, Any],
    environ: Optional[Mapping[str, str]] = None,
    secrets: tuple[str, ...] = (),
    target: Optional[Path] = None,
) -> Optional[str]:
    """Keep the stream-json trace (and its sidecar) on a measurement host.

    Only ``NEXUS_MEASUREMENT_TRACE_DIR`` (absolute) enables this.  Files are
    named by the receipt's ``stdout_sha256`` (the hash of the raw stream) and
    created 0600; every ``secrets`` value (the API key) is redacted from
    the stored stream and sidecar, since a tool call may print the environment.
    """
    env = os.environ if environ is None else environ
    root = str(env.get(MEASUREMENT_TRACE_DIR_ENV, "") or "").strip()
    if not root or not os.path.isabs(root) or not _SAFE_TASK_ID.fullmatch(str(task_id)):
        return None
    directory = Path(root) / str(task_id)
    if target is not None:
        real_dir, real_target = Path(os.path.realpath(directory)), Path(os.path.realpath(target))
        if (
            real_dir == real_target
            or real_target in real_dir.parents
            or real_dir in real_target.parents
        ):
            return None  # never write the trace into (or around) the worktree (review L2, Codex r3)
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / f"{stdout_sha256}.stream.jsonl"
    _write_private(target, redact_secrets(bytes(stdout), secrets))
    side_text = json.dumps(
        {**dict(sidecar), "secrets_redacted": bool(secrets)}, sort_keys=True, indent=2, default=str
    )
    _write_private(
        directory / f"{stdout_sha256}.run.json", redact_secrets(side_text.encode("utf-8"), secrets)
    )
    return str(target)


@dataclass
class ClaudeRun:
    """One sandboxed CLI run: its raw result plus what the shell looked like."""

    result: Any
    summary: ClaudeStreamSummary
    infra: Optional[str]
    seatbelt_sha256: str
    seatbelt_profile: str
    target: str
    run_root: str
    proxy_attempts: list[dict[str, Any]]
    venv: Optional[str]
    env_keys: tuple[str, ...]
    git_dirs: tuple[str, ...] = ()


def run_claude_once(
    executable: str,
    *,
    target: Path,
    prompt: str,
    timeout_seconds: float,
    venv: Optional[Path],
    environ: Optional[Mapping[str, str]] = None,
    on_process_group: Any = None,
    argv: Optional[tuple[str, ...]] = None,
    controller_root: Optional[Path | str] = None,
) -> ClaudeRun:
    """Run the CLI once in ``target`` under the measurement sandbox.

    ``argv`` replaces the measurement flags + prompt (used only for
    ``--version``, which then also runs inside the sandbox).
    """
    from nexus.executors.cli_worker import CliWorkerRequest, run_cli_worker

    target = Path(os.path.realpath(target))
    run_root = Path(os.path.realpath(tempfile.mkdtemp(prefix="nexus-claude-run-")))
    try:
        (run_root / "home" / ".claude").mkdir(parents=True)
        (run_root / "tmp").mkdir()
        cli_dir = Path(os.path.realpath(executable)).parent
        if not cli_install_dir_ok(cli_dir):
            raise ValueError("claude executable directory is not a safe read root")
        readable: list[Path] = [cli_dir]
        # A P1 lease is a ``git worktree``: its ``.git`` file points into the
        # Controller's gitdir, which must be readable (never writable) so git
        # works in the NEXUS arm as it does in BARE (review H2).
        git_dirs = worktree_git_dirs(target, controller_root)
        readable.extend(git_dirs)
        if venv is not None:
            readable.append(venv)
            interpreter_home = _venv_interpreter_home(venv)
            if interpreter_home is not None:
                readable.append(interpreter_home)
        with HostAllowlistProxy() as proxy:
            env = measurement_child_env(
                run_root=run_root,
                target=target,
                proxy_url=proxy.url,
                token=measurement_claude_api_key(environ),
                venv=venv,
                environ=environ,
            )
            profile = build_claude_seatbelt_profile(
                target=target,
                run_root=run_root,
                readable=tuple(readable),
                proxy_port=proxy.port,
            )
            request = CliWorkerRequest(
                executable=executable,
                argv=argv if argv is not None else claude_measurement_argv(prompt),
                cwd=str(target),
                timeout_seconds=float(timeout_seconds),
                env=env,
                exact_env=True,
                # The sandbox is mandatory: without sandbox-exec, run_cli_worker
                # refuses to start.  Only tests on hosts without Seatbelt turn
                # ``_USE_SEATBELT`` off (the profile is still built and hashed).
                seatbelt_profile=profile if _USE_SEATBELT else None,
                sweep_descendants_on_exit=True,
                sweep_roots=(str(target), str(run_root)),
            )
            result = run_cli_worker(request, on_process_group=on_process_group)
            attempts = list(proxy.attempts)
        summary = summarize_stream_json(result.stdout)
        return ClaudeRun(
            result=result,
            summary=summary,
            infra=classify_claude_infra(summary, result.stderr),
            seatbelt_sha256=hashlib.sha256(profile.encode("utf-8")).hexdigest(),
            seatbelt_profile=profile,
            target=str(target),
            run_root=str(run_root),
            proxy_attempts=attempts,
            venv=str(venv) if venv is not None else None,
            env_keys=tuple(sorted(env)),
            git_dirs=tuple(str(path) for path in git_dirs),
        )
    finally:
        shutil.rmtree(run_root, ignore_errors=True)


class ClaudeMeasurementWorkerAdapter:
    """``WorkerRegistry`` adapter for provider ``claude`` (measurement only).

    Refuses unless the switch is on and the pinned executable is configured,
    refuses any model other than ``claude-haiku-5-5`` (no silent substitution),
    and runs only in the contract's leased target worktree.  The BARE arm calls
    ``invoke`` directly with a contract/lease of the same shape.
    """

    provider = CLAUDE_MEASUREMENT_PROVIDER
    requires_leased_target = True

    def __init__(self, environ: Optional[Mapping[str, str]] = None):
        self._environ = environ

    def _env(self) -> Mapping[str, str]:
        return os.environ if self._environ is None else self._environ

    def _secrets(self) -> tuple[str, ...]:
        token = measurement_claude_api_key(self._env())
        return (token,) if token else ()

    def preflight(self) -> Any:
        from nexus.executors.worker_contract import WorkerPreflight

        enabled = measurement_claude_enabled(self._env())
        executable = measurement_claude_executable(self._env())
        if not enabled:
            reason = f"{MEASUREMENT_CLAUDE_ENV}=1 is required (measurement Gateway only)"
        elif executable is None:
            reason = f"{MEASUREMENT_CLAUDE_BIN_ENV} must name an absolute, non-symlink claude CLI"
        else:
            reason = "ready"
        return WorkerPreflight(
            provider=self.provider,
            executable=executable,
            executable_available=executable is not None,
            authorized=enabled,
            implementation_status="IMPLEMENTED",
            ready=enabled and executable is not None,
            reason=reason,
        )

    def invoke(
        self,
        contract: Any,
        lease: Any,
        *,
        prompt: str,
        timeout_seconds: Optional[float] = None,
        on_process_group: Any = None,
        model: Optional[str] = None,
        require_leased_target: bool = False,
        **_ignored: Any,
    ) -> Any:
        from nexus.executors.agy_write_admission import leased_target_failure
        from nexus.executors.cli_worker import CliWorkerStatus
        from nexus.executors.worker_contract import (
            WorkerExecutionReceipt,
            WorkerOutcome,
            WorkerProviderUnavailable,
            redacted_output_tail,
        )

        preflight = self.preflight()
        if not preflight.ready:
            raise WorkerProviderUnavailable(f"{self.provider}: {preflight.reason}")
        if model is not None and str(model) != CLAUDE_MEASUREMENT_MODEL:
            raise WorkerProviderUnavailable(
                f"{self.provider}: model {model!r} is not the measurement model {CLAUDE_MEASUREMENT_MODEL}"
            )
        # Always: the BARE arm calls invoke directly, so the lease check may not
        # depend on the registry's require_leased_target flag (Codex r1 #5).
        lease_failure = leased_target_failure(contract, lease)
        if lease_failure is not None:
            raise WorkerProviderUnavailable(f"{self.provider}: {lease_failure}")
        del require_leased_target
        target = Path(os.path.realpath(lease.target_worktree))
        try:
            require_gitdir_in_measurement_root(target, self._env())
        except WorktreeGitdirOutsideMeasurementRoot as exc:
            raise WorkerProviderUnavailable(f"{self.provider}: {exc}") from exc
        run = run_claude_once(
            str(preflight.executable),
            target=target,
            prompt=prompt,
            timeout_seconds=measurement_cli_timeout(timeout_seconds, self._env()),
            venv=task_venv_for(contract),
            environ=self._env(),
            on_process_group=on_process_group,
            controller_root=getattr(contract, "controller_repo_root", None),
        )
        result, summary = run.result, run.summary
        if result.status is CliWorkerStatus.TIMED_OUT:
            outcome = WorkerOutcome.INCOMPLETE
        elif (
            result.status is not CliWorkerStatus.COMPLETED
            or result.exit_code != 0
            or not summary.result_seen
            or summary.is_error is not False
        ):
            outcome = WorkerOutcome.FAILED
        else:
            outcome = WorkerOutcome.EXECUTION_COMPLETED
        foreign = [name for name in summary.models_seen if name != CLAUDE_MEASUREMENT_MODEL]
        failure = None
        if foreign:
            outcome = WorkerOutcome.FAILED
            failure = f"{self.provider}: model substitution observed: {sorted(foreign)}"
        elif outcome is WorkerOutcome.EXECUTION_COMPLETED and set(summary.served_models) != {
            CLAUDE_MEASUREMENT_MODEL
        }:
            # A success must positively show the measurement model served it.
            outcome = WorkerOutcome.FAILED
            failure = f"{self.provider}: no evidence that {CLAUDE_MEASUREMENT_MODEL} served the run"
        elif run.infra is not None and outcome is not WorkerOutcome.EXECUTION_COMPLETED:
            failure = f"claude_infra:{run.infra}"
        elif outcome is not WorkerOutcome.EXECUTION_COMPLETED:
            failure = f"{self.provider} execution did not complete successfully ({summary.subtype or result.status.value})"
        write_measurement_trace(
            str(getattr(contract, "task_id", "")),
            result.stdout,
            result.stdout_sha256,
            {
                "schema": "nexus.measurement_claude_run.v1",
                "argv_sha256": hashlib.sha256(
                    json.dumps(list(result.argv)).encode("utf-8")
                ).hexdigest(),
                "flags": list(CLAUDE_MEASUREMENT_FLAGS),
                "env_keys": list(run.env_keys),
                "seatbelt_sha256": run.seatbelt_sha256,
                # Normalized (paths/port replaced) so both arms' profiles compare byte for byte.
                "seatbelt_profile_normalized": normalize_seatbelt_profile(
                    run.seatbelt_profile,
                    target=run.target,
                    run_root=run.run_root,
                    venv=run.venv,
                    git_dirs=run.git_dirs,
                ),
                "proxy_attempts": run.proxy_attempts,
                "venv": run.venv,
                "init": summary.init,
                "infra": run.infra,
                "wall_time_ms": result.wall_time_ms,
                "timed_out": result.timed_out,
                "cli_timeout_seconds": measurement_cli_timeout(timeout_seconds, self._env()),
                "key_label": str(self._env().get(MEASUREMENT_KEY_LABEL_ENV, "") or "") or None,
                "api_key_sha256_12": api_key_id(measurement_claude_api_key(self._env())),
                "worktree_git_dirs": list(run.git_dirs),
            },
            self._env(),
            secrets=self._secrets(),
            target=target,
        )
        return WorkerExecutionReceipt(
            provider=self.provider,
            task_id=contract.task_id,
            target_worktree=str(target),
            worker_status=result.status.value,
            outcome=outcome.value,
            exit_code=result.exit_code,
            executable_identity=result.executable_identity,
            argv=result.argv,
            stdout_sha256=result.stdout_sha256,
            stderr_sha256=result.stderr_sha256,
            wall_time_ms=result.wall_time_ms,
            process_group_id=result.process_group_id,
            process_group_killed=result.process_group_killed,
            timed_out=result.timed_out,
            provider_calls=1,
            evidence_complete=outcome is WorkerOutcome.EXECUTION_COMPLETED,
            commit_created=False,
            merge_performed=False,
            push_performed=False,
            failure_reason=failure,
            provider_attempt_count=1,
            provider_permission_mode="acceptEdits_no_web_no_subagents",
            provider_permission_profile_sha256=run.seatbelt_sha256,
            provider_write_sandbox=f"seatbelt:{run.seatbelt_sha256}",
            provider_env_keys_sha256=result.env_keys_sha256 or None,
            stdout_tail=redacted_output_tail(redact_secrets(result.stdout, self._secrets())),
            stderr_tail=redacted_output_tail(redact_secrets(result.stderr, self._secrets())),
        )


# -- Gateway readiness (nexus_worker_candidate preflight) ---------------------

PROBE_PROMPT = "Reply with exactly the word ok and nothing else."
PROBE_TTL_SECONDS = 3600
_PROBE_CACHE: dict[tuple[str, str, str], dict[str, Any]] = {}  # (binary sha, version, token sha)


def _blocked(provider_result: dict[str, Any], blocker: str, **extra: Any) -> dict[str, Any]:
    provider_result.update(status="BLOCKED", blocker=blocker, execution_ready=False, **extra)
    return provider_result


def measurement_claude_preflight(
    requested_model: str,
    *,
    environ: Optional[Mapping[str, str]] = None,
    now: Any = None,
) -> dict[str, Any]:
    """``nexus.provider_preflight.v1`` for provider ``claude`` on a measurement Gateway.

    Readiness is proven by one real run of the exact measurement invocation
    (sandbox included) in an empty directory; its stream-json result must be a
    success served only by ``claude-haiku-5-5``.  The proof is cached per
    (binary sha256, CLI version, model) for one hour.
    """
    import datetime

    env = os.environ if environ is None else environ
    clock = now or (lambda: datetime.datetime.now(datetime.timezone.utc))
    result: dict[str, Any] = {
        "schema": "nexus.provider_preflight.v1",
        "provider": CLAUDE_MEASUREMENT_PROVIDER,
        "requested_model": str(requested_model or ""),
        "resolved_model": str(requested_model or ""),
        "requested_model_verified": False,
        "binary_found": False,
        "binary_path": None,
        "binary_sha256": None,
        "cli_version": None,
        "authenticated": False,
        "authentication_required": False,
        "model_reachable": False,
        "status": "BLOCKED",
        "blocker": None,
        "next_action": None,
        "readiness_status": "BLOCKED",
        "execution_ready": False,
        "measurement_only": True,
    }
    if not measurement_claude_enabled(env):
        return _blocked(result, "MEASUREMENT_CLAUDE_WORKER_DISABLED")
    if str(requested_model or "") != CLAUDE_MEASUREMENT_MODEL:
        return _blocked(result, "MEASUREMENT_CLAUDE_MODEL_MISMATCH")
    executable = measurement_claude_executable(env)
    if executable is None:
        return _blocked(result, "MEASUREMENT_CLAUDE_BINARY_UNAVAILABLE")
    binary_sha256 = hashlib.sha256(Path(executable).read_bytes()).hexdigest()
    result.update(binary_found=True, binary_path=executable, binary_sha256=binary_sha256)
    with tempfile.TemporaryDirectory(prefix="nexus-claude-preflight-") as scratch:
        # ``--version`` runs inside the same sandbox as every other call (Codex r1 #2).
        version_target = Path(scratch) / "version"
        version_target.mkdir()
        version_run = run_claude_once(
            executable,
            target=version_target,
            prompt="",
            timeout_seconds=30.0,
            venv=None,
            environ=env,
            argv=("--version",),
        )
        version = version_run.result
        cli_version = (
            (version.stdout or version.stderr or b"")
            .decode("utf-8", errors="replace")
            .strip()[:512]
        )
        result.update(
            cli_version=cli_version,
            cli_version_sha256=hashlib.sha256(cli_version.encode("utf-8")).hexdigest(),
        )
        if version.exit_code != 0 or not cli_version:
            return _blocked(result, "MEASUREMENT_CLAUDE_VERSION_FAILED")
        pinned = str(env.get(MEASUREMENT_CLAUDE_VERSION_ENV, "") or "").strip()
        if pinned and not cli_version.startswith(pinned):
            return _blocked(result, "MEASUREMENT_CLAUDE_VERSION_MISMATCH")
        token = measurement_claude_api_key(env) or ""
        # A different account (token) needs its own proof (review finding #5).
        key = (binary_sha256, cli_version, hashlib.sha256(token.encode("utf-8")).hexdigest())
        cached = _PROBE_CACHE.get(key)
        current = clock()
        if cached is None or datetime.datetime.fromisoformat(cached["probe_expires_at"]) <= current:
            probe_target = Path(scratch) / "probe"
            probe_target.mkdir()
            run = run_claude_once(
                executable,
                target=probe_target,
                prompt=PROBE_PROMPT,
                timeout_seconds=120.0,
                venv=None,
                environ=env,
            )
            summary = run.summary
            served = set(summary.served_models)
            if (
                run.result.exit_code != 0
                or summary.is_error is not False
                or served != {CLAUDE_MEASUREMENT_MODEL}
            ):
                return _blocked(
                    result,
                    "MEASUREMENT_CLAUDE_PROBE_FAILED",
                    probe_subtype=summary.subtype,
                    probe_models=sorted(served),
                    probe_infra=run.infra,
                )
            evidence = {
                "binary_sha256": binary_sha256,
                "cli_version": cli_version,
                "model": CLAUDE_MEASUREMENT_MODEL,
                "session_id": summary.session_id,
                "seatbelt_sha256": run.seatbelt_sha256,
                "probed_at": current.isoformat(),
            }
            cached = {
                "probe_evidence_hash": hashlib.sha256(
                    json.dumps(evidence, sort_keys=True).encode("utf-8")
                ).hexdigest(),
                "probe_expires_at": (
                    current + datetime.timedelta(seconds=PROBE_TTL_SECONDS)
                ).isoformat(),
                "probed_at": evidence["probed_at"],
                "probe_usage": summary.usage,
            }
            _PROBE_CACHE[key] = cached
    result.update(
        status="VERSION_VERIFIED",
        readiness_status="MODEL_VERIFIED",
        execution_ready=True,
        model_reachable=True,
        requested_model_verified=True,
        authenticated=True,
        authentication_evidence="successful_exact_model_probe",
        probe_evidence_hash=cached["probe_evidence_hash"],
        probe_expires_at=cached["probe_expires_at"],
        probed_at=cached["probed_at"],
        probe_usage=cached.get("probe_usage"),
    )
    return result
