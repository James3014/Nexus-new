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

import os
import shutil
from pathlib import Path
from typing import Mapping, Optional

from nexus.executors.agy_write_admission import escaping_symlinks, target_git_entry_state

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
    return upper.startswith(_CREDENTIAL_NAME_PREFIXES) or any(
        marker in upper for marker in _CREDENTIAL_NAME_MARKERS
    )


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
    env = {
        str(key): str(value)
        for key, value in base.items()
        if key in CODEX_ENV_ALLOWLIST
        or key in CODEX_ENV_PROXY_KEYS
        or key in extra
        or str(key).startswith("LC_")
    }
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
        except FileNotFoundError:
            continue
        except OSError:
            return CODEX_RUN_HOME_UNAVAILABLE
    return None


def target_integrity_snapshot(target: Path) -> dict[str, object]:
    """Escaping symlinks and ``.git`` entry state of ``target`` right now."""
    return {
        "escaping": escaping_symlinks(target),
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
    if after.get("escaping") != before.get("escaping") or after.get("git") != before.get("git"):
        return CODEX_TARGET_ESCAPE
    return None
