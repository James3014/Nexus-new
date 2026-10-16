"""Codex run boundary: disposable HOME, env allowlist, target integrity (#2254).

The Agy launcher gives every run a disposable HOME that carries only the
copied auth file and an allowlisted environment (``agy_write_admission``).
Codex had neither: it inherited the host HOME (``~/.ssh``, ``~/.config/gh``,
``~/.gitconfig``, the whole ``~/.codex`` with history, sessions, memories,
MCP servers and hooks) and the ambient environment.  This module is the
Codex counterpart, shared by ``scripts/ops/start_codex_nexus_enforced.sh``
(through ``scripts/ops/codex_run_guard.py``) and ``CodexCliExecutor``.

Codex authenticates with ``$CODEX_HOME/auth.json`` alone (probed with codex
0.162.1: ``config.toml`` is not needed, and the real one carries MCP servers,
plugins and hooks, i.e. ambient authority, so it is deliberately not copied).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
import tempfile
from pathlib import Path
from typing import Mapping, Optional
from urllib.parse import urlsplit, urlunsplit

from nexus.executors.agy_write_admission import (
    escaping_symlinks,
    path_inside,
    target_git_entry_state,
)

CODEX_RUN_HOME_COPIED_FILES = (Path(".codex") / "auth.json",)
CODEX_ENV_ALLOWLIST = frozenset({"PATH", "LANG", "TERM", "USER", "LOGNAME", "SHELL"})
CODEX_ENV_PROXY_KEYS = frozenset({
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "NO_PROXY",
    "ALL_PROXY",
    "http_proxy",
    "https_proxy",
    "no_proxy",
    "all_proxy",
})
# Extra variable names the operator may pass through explicitly (comma
# separated).  Credential-shaped names are never passed, even when listed.
CODEX_ENV_PASSTHROUGH_VAR = "NEXUS_CODEX_ENV_PASSTHROUGH"
_CREDENTIAL_NAME_MARKERS = ("TOKEN", "KEY", "SECRET", "PASSWORD", "CREDENTIAL", "AUTH_SOCK")
_CREDENTIAL_NAME_PREFIXES = ("GH_", "GITHUB_", "SSH_")
# Loader / interpreter / git hooks that run code or fetch credentials.
_INJECTION_NAME_PREFIXES = ("GIT_", "LD_", "DYLD_", "PYTHON", "NODE_", "NPM_", "BASH_", "PERL")
_INJECTION_NAMES = frozenset({"ENV", "IFS", "SHELLOPTS", "PS4"})
AUTH_BASELINE_FILE = "auth-baseline.sha256"
CODEX_RUN_HOME_UNAVAILABLE = "codex_run_home_unavailable"
CODEX_TARGET_ESCAPE = "codex_target_symlink_or_git_escape"


def codex_source_home(source: Optional[Mapping[str, str]] = None) -> Path:
    """The Codex home the auth file is copied from (``CODEX_HOME`` or ``~/.codex``)."""
    base = os.environ if source is None else source
    configured = str(base.get("CODEX_HOME") or "").strip()
    if configured:
        return Path(configured)
    return Path(str(base.get("HOME") or Path.home())) / ".codex"


def _credential_shaped(name: str) -> bool:
    upper = name.upper()
    return (
        upper.startswith(_CREDENTIAL_NAME_PREFIXES)
        or upper.startswith(_INJECTION_NAME_PREFIXES)
        or upper in _INJECTION_NAMES
        or any(marker in upper for marker in _CREDENTIAL_NAME_MARKERS)
    )


_LOCALE_VALUE = re.compile(r"[A-Za-z0-9_.@-]{0,40}")


def _without_userinfo(value: str) -> str:
    """Drop ``user:pass@`` from proxy URLs (NO_PROXY style lists pass unchanged)."""
    if "@" not in value:
        return value
    if "://" not in value:
        return value.rpartition("@")[2]
    try:
        parts = urlsplit(value)
        if parts.username is None and parts.password is None:
            return value
        host = parts.netloc.rpartition("@")[2]
        return urlunsplit(parts._replace(netloc=host))
    except ValueError:
        return ""


def codex_child_env(
    source: Optional[Mapping[str, str]], *, home: Path, tmpdir: Path
) -> dict[str, str]:
    """Allowlisted environment for a codex child: no tokens, no agent sockets."""
    base = os.environ if source is None else source
    extra = {
        name.strip()
        for name in str(base.get(CODEX_ENV_PASSTHROUGH_VAR) or "").split(",")
        if name.strip() and not _credential_shaped(name.strip())
    }
    env = {}
    for key, value in base.items():
        name, text = str(key), str(value)
        if name in CODEX_ENV_PROXY_KEYS:
            env[name] = _without_userinfo(text)
        elif name in CODEX_ENV_ALLOWLIST or name in extra:
            env[name] = text
        elif (
            name.startswith("LC_")
            and not _credential_shaped(name)
            and _LOCALE_VALUE.fullmatch(text)
        ):
            env[name] = text
    env["HOME"] = str(home)
    env["CODEX_HOME"] = str(home / ".codex")
    env["TMPDIR"] = str(tmpdir)
    return env


def materialize_codex_home(
    run_home: Path, *, source: Optional[Mapping[str, str]] = None
) -> Optional[str]:
    """Create the disposable HOME holding only a 0600 copy of the auth file.

    Returns ``None`` on success or a typed refusal.  A missing auth file is
    not a refusal: codex then fails authentication itself, a normal typed
    non-delivery.  Files are copied, never symlinked.
    """
    source_codex = codex_source_home(source)
    try:
        run_home.mkdir(parents=True, exist_ok=True)
        os.chmod(run_home, 0o700)
        (run_home / ".codex").mkdir(mode=0o700, exist_ok=True)
        (run_home / "tmp").mkdir(mode=0o700, exist_ok=True)
    except OSError:
        return CODEX_RUN_HOME_UNAVAILABLE
    for relative in CODEX_RUN_HOME_COPIED_FILES:
        origin = source_codex / relative.name
        destination = run_home / relative
        try:
            shutil.copyfile(origin, destination)
            os.chmod(destination, 0o600)
            # Outside CODEX_HOME so the run never writes it; used by write-back.
            (run_home / AUTH_BASELINE_FILE).write_text(
                hashlib.sha256(destination.read_bytes()).hexdigest(), encoding="utf-8"
            )
        except FileNotFoundError:
            continue
        except OSError:
            return CODEX_RUN_HOME_UNAVAILABLE
    return None


def write_back_refreshed_auth(
    run_home: Path, *, source: Optional[Mapping[str, str]] = None
) -> bool:
    """Copy a token refreshed by codex in the run HOME back to the host, atomically.

    Only when the run copy changed, is a JSON object, and the host file still
    equals what was copied (another session did not refresh meanwhile).  Temp
    file in the host directory, 0600, then rename.  Never raises.
    """
    try:
        host = (codex_source_home(source) / "auth.json").resolve()
        baseline = (run_home / AUTH_BASELINE_FILE).read_text(encoding="utf-8").strip()
        refreshed = (run_home / ".codex" / "auth.json").read_bytes()
        if hashlib.sha256(refreshed).hexdigest() == baseline:
            return False
        new_body = json.loads(refreshed)
        host_bytes = host.read_bytes()
        if hashlib.sha256(host_bytes).hexdigest() != baseline:
            return False
        old_body = json.loads(host_bytes)
        # Same top-level shape as the real file and a non-empty credential.
        if not isinstance(new_body, dict) or set(new_body) != set(old_body):
            return False
        if not any(new_body.get(key) for key in ("tokens", "OPENAI_API_KEY")):
            return False
        descriptor, temporary = tempfile.mkstemp(prefix=".auth.json.", dir=str(host.parent))
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(refreshed)
            os.chmod(temporary, 0o600)
            os.replace(temporary, host)
        except OSError:
            if os.path.exists(temporary):
                os.unlink(temporary)
            return False
        return True
    except (OSError, ValueError):
        return False


def _hash_entry(digest: "hashlib._Hash", path: Path) -> None:
    """Type-tagged hash of one entry; never opens a FIFO/device (would block)."""
    try:
        mode = os.lstat(path).st_mode
        if stat.S_ISLNK(mode):
            digest.update(b"symlink" + os.readlink(path).encode("utf-8", "surrogateescape"))
        elif stat.S_ISREG(mode):
            digest.update(b"file" + path.read_bytes())
        elif stat.S_ISDIR(mode):
            digest.update(b"dir")
        else:
            digest.update(b"special")
    except OSError:
        digest.update(b"unreadable")


def _nested_git_entries(target: Path) -> dict[str, str]:
    """Every non-root ``.git`` entry (file, dir or symlink) with a content hash.

    A nested ``.git`` file (``gitdir: /outside``) or directory (``config`` with
    ``core.fsmonitor``, hooks) is a code-execution or redirect vector for the
    next git command run in the tree; only the baseline set may stay unchanged.
    """
    real_target = Path(os.path.realpath(target))
    found: dict[str, str] = {}
    for directory, dirnames, filenames in os.walk(real_target, onerror=lambda _error: None):
        here = Path(directory)
        if here == real_target and ".git" in dirnames:
            dirnames.remove(".git")
        for name in [*dirnames, *filenames]:
            if name != ".git" or here == real_target:
                continue
            path = here / name
            digest = hashlib.sha256()
            _hash_entry(digest, path)
            if path.is_dir() and not path.is_symlink():
                for sub, subdirs, subfiles in os.walk(path, onerror=lambda _e: None):
                    subdirs.sort()
                    for entry in sorted([*subdirs, *subfiles]):
                        full = Path(sub) / entry
                        digest.update(
                            str(full.relative_to(path)).encode("utf-8", "surrogateescape")
                        )
                        _hash_entry(digest, full)
            found[path.relative_to(real_target).as_posix()] = digest.hexdigest()
    return found


def _unreadable_directories(target: Path) -> list[str]:
    """Directories ``os.walk`` could not enter (``escaping_symlinks`` skips them
    silently, so a symlink hidden in a mode-0000 directory would go unseen)."""
    real_target = Path(os.path.realpath(target))
    found: list[str] = []

    def onerror(error: OSError) -> None:
        found.append(str(error.filename))

    for directory, dirnames, _filenames in os.walk(real_target, onerror=onerror):
        if Path(directory) == real_target and ".git" in dirnames:
            dirnames.remove(".git")
    return sorted(found)


def _nested_git_escapes(target: Path) -> dict[str, str]:
    """Escaping symlinks the shared walker prunes: it drops every directory named
    ``.git`` at any depth, so ``sub/.git -> /elsewhere`` or a ``sub/.git/`` tree
    holding escaping links would be invisible.  Only the root ``.git`` entry is
    exempt here (it is covered by ``target_git_entry_state``)."""
    real_target = Path(os.path.realpath(target))
    found: dict[str, str] = {}
    for directory, dirnames, filenames in os.walk(real_target, onerror=lambda _error: None):
        if Path(directory) == real_target and ".git" in dirnames:
            dirnames.remove(".git")
        for name in [*dirnames, *filenames]:
            path = Path(directory) / name
            if not path.is_symlink():
                continue
            if Path(directory) == real_target and name == ".git":
                continue
            if (
                Path(directory) != real_target
                and name != ".git"
                and ".git" not in path.relative_to(real_target).parts
            ):
                continue  # already reported by escaping_symlinks
            if not path_inside(Path(os.path.realpath(path)), real_target):
                found[path.relative_to(real_target).as_posix()] = os.readlink(path)
    return found


def target_integrity_snapshot(target: Path) -> dict[str, object]:
    """Escaping symlinks, unreadable directories and ``.git`` entry state of ``target``."""
    return {
        "escaping": escaping_symlinks(target),
        "nested_git": _nested_git_escapes(target),
        "nested_git_entries": _nested_git_entries(target),
        "unreadable": _unreadable_directories(target),
        "git": target_git_entry_state(target),
    }


def target_integrity_failure(
    before: Mapping[str, object], after: Mapping[str, object]
) -> Optional[str]:
    """``codex_target_symlink_or_git_escape`` when the run added or changed an
    escaping symlink or touched the ``.git`` pointer; else ``None``.

    Escaping symlinks already committed in the base tree (the Nexus tree has a
    few) are the baseline; only a difference is an escape.
    """
    if any(
        after.get(key) != before.get(key)
        for key in ("escaping", "nested_git", "nested_git_entries", "unreadable", "git")
    ):
        return CODEX_TARGET_ESCAPE
    return None
