"""Agy write-admission model for governed executors (Owner decision on #1912).

Layers, from preventive to detective:

1. Permission posture: no auto-approve flag ever reaches the argv.
   Implementation runs use ``--mode accept-edits`` (edits only; commands are
   auto-denied in headless print mode) and read-only roles ``--mode plan
   --sandbox``.  Each run gets a disposable HOME holding only the copied
   OAuth token and an explicit settings profile that denies ``command(*)``
   (and ``write_file(*)`` for read-only roles); the real HOME's settings,
   hooks, MCP config and memory are never loaded.
2. Seatbelt: every run is wrapped in a macOS ``sandbox-exec`` profile that
   denies file writes everywhere except the runtime-owned target worktree
   (implementation only, minus its ``.git`` entry) and the per-run root
   (disposable HOME + TMPDIR).  This stops absolute-path, symlink and
   Git-internal writes; it is mandatory and fails closed when
   ``sandbox-exec`` is unavailable.
3. Integrity fingerprint of every protected checkout (secondary check): the
   contract's controller checkout, the non-bare main worktree behind the
   target's Git common dir, and the loaded canonical source root; plus the
   target's ``.git`` entry.
4. Output classification: only a parseable JSON result with status SUCCESS,
   no denied actions and a non-empty response is delivery.
"""

from __future__ import annotations

import hashlib
import json
import os
import pwd
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional

AGY_PERMISSION_BYPASS_FLAGS: frozenset[str] = frozenset({
    "--dangerously-skip-permissions",
    "--yolo",
    "--auto-approve",
})
AGY_PERMISSION_MODE_ACCEPT_EDITS = "accept_edits_no_autoapprove"
AGY_PERMISSION_MODE_PLAN = "plan_no_autoapprove"
AGY_IMPLEMENTATION_ROLES: frozenset[str] = frozenset({
    "implementation",
    "implementer",
    "bounded_code_candidate",
})
AGY_READ_ONLY_ROLES: frozenset[str] = frozenset({
    "review",
    "reviewer",
    "plan",
    "planner",
    "planning",
    "read_only",
})
_AGY_ADMITTED_MODES = frozenset({"accept-edits", "plan"})
# Agy reports a headless auto-denial on stderr ("jetski: no output produced -
# a tool required the "command" permission that headless mode cannot prompt
# for, so it was auto-denied") and, with ``--output-format json``, as a
# non-empty ``denied_actions`` list while still exiting 0 / status SUCCESS.
_AGY_HEADLESS_PERMISSION_DENIAL_MARKERS = (
    "jetski: no output produced",
    "permission that headless mode cannot prompt",
    "headless mode cannot prompt for, so it was auto-denied",
)
SANDBOX_EXEC_PATH = "/usr/bin/sandbox-exec"


# ---------------------------------------------------------------------------
# argv posture
# ---------------------------------------------------------------------------


def agy_permission_bypass_flags(argv: tuple[str, ...] | list[str]) -> list[str]:
    """Deny-listed permission flags in ``argv``, ignoring the ``--print`` prompt value."""
    tokens = [str(token) for token in argv]
    if "--print" in tokens:
        index = tokens.index("--print")
        tokens = tokens[: index + 1] + tokens[index + 2 :]
    found: list[str] = []
    for index, token in enumerate(tokens):
        name, has_value, value = token.partition("=")
        if name in AGY_PERMISSION_BYPASS_FLAGS:
            found.append(token)
        elif name == "--mode":
            mode = value if has_value else (tokens[index + 1] if index + 1 < len(tokens) else "")
            if mode not in _AGY_ADMITTED_MODES:
                found.append(token if has_value else f"--mode {mode}".rstrip())
    return found


def agy_model_shape_ok(model: str) -> bool:
    return (
        bool(model)
        and not model.startswith("-")
        and not any(char.isspace() or char == "=" for char in model)
    )


# ---------------------------------------------------------------------------
# output classification
# ---------------------------------------------------------------------------


def last_json_object(text: str) -> Optional[dict[str, Any]]:
    """Return the last top-level JSON object in ``text`` (pretty or one-line)."""
    decoder = json.JSONDecoder()
    found: Optional[dict[str, Any]] = None
    index = text.find("{")
    while index != -1:
        try:
            value, end = decoder.raw_decode(text, index)
        except ValueError:
            index = text.find("{", index + 1)
            continue
        if isinstance(value, dict):
            found = value
        index = text.find("{", end)
    return found


_RESULT_ENVELOPE_KEYS = frozenset({"status", "response", "denied_actions", "conversation_id"})


def top_level_json_objects(text: str) -> list[dict[str, Any]]:
    """Every top-level JSON object in ``text``; non-JSON log lines are skipped."""
    decoder = json.JSONDecoder()
    found: list[dict[str, Any]] = []
    index = text.find("{")
    while index != -1:
        try:
            value, end = decoder.raw_decode(text, index)
        except ValueError:
            index = text.find("{", index + 1)
            continue
        if isinstance(value, dict):
            found.append(value)
        index = text.find("{", end)
    return found


def agy_delivery_failure(stdout: bytes, stderr: bytes) -> Optional[str]:
    """Typed non-delivery reason for an Agy run that exited 0, else ``None``.

    Delivery requires exactly one result envelope (a JSON object carrying any
    of status/response/denied_actions/conversation_id; repeated identical
    copies are tolerated) with ``status == "SUCCESS"``, no ``denied_actions``
    and a non-empty ``response``.  Any envelope reporting a failure or a
    denial, or envelopes that disagree, make the run non-delivery.  The
    headless denial marker is only trusted on stderr, never in stdout.
    """
    err = stderr.decode("utf-8", errors="replace")
    if any(marker in err for marker in _AGY_HEADLESS_PERMISSION_DENIAL_MARKERS):
        return "agy_permission_denied"
    text = stdout.decode("utf-8", errors="replace")
    if not text.strip():
        return "agy_no_output"
    envelopes = [obj for obj in top_level_json_objects(text) if _RESULT_ENVELOPE_KEYS & set(obj)]
    if not envelopes:
        return "agy_output_unparseable"
    if any(envelope.get("denied_actions") for envelope in envelopes):
        return "agy_permission_denied"
    if any(envelope.get("status") != "SUCCESS" for envelope in envelopes):
        return "agy_status_not_success"
    if any(envelope != envelopes[0] for envelope in envelopes[1:]):
        return "agy_output_ambiguous"
    payload = envelopes[0]
    response = payload.get("response")
    if not isinstance(response, str) or not response.strip():
        return "agy_no_output"
    return None


# ---------------------------------------------------------------------------
# per-run Agy state home
# ---------------------------------------------------------------------------

# Files copied from the source HOME into the disposable per-run HOME.  Probed
# with agy (#1912): the OAuth token and installation id are all a headless
# print run needs; agy then writes its conversations, brain, implicit memory,
# project registry and logs into the disposable HOME, never into the real one.
AGY_RUN_HOME_COPIED_FILES = (
    Path(".gemini") / "antigravity-cli" / "antigravity-oauth-token",
    Path(".gemini") / "antigravity-cli" / "installation_id",
)
# Cline (#2254): ``~/.cline/data/settings/providers.json`` holds the OAuth
# tokens and provider/model selection; probed with cline 3.0.69: it is the
# only file a headless ``--json`` run needs to authenticate (no keychain, no
# db/, sessions/, cache/ or hooks).  Cline refreshes the access token into the
# disposable copy; the refresh token is not rotated, so the real file stays valid.
CLINE_RUN_HOME_COPIED_FILES = (Path(".cline") / "data" / "settings" / "providers.json",)
# Workspace entries cline loads on a later run in the target (hooks, rules,
# skills); the Seatbelt profile keeps them read-only for the worker.  Probed in
# the cline 3.0.69 bundle (#2332): ``.clinerules``, ``.cline`` and ``.agents``
# (hooks/skills/rules/workflows) plus ``AGENTS.md``.  ``.agents`` is also in
# ``TARGET_AGY_CUSTOMIZATION_PATHS``.  ``AGENTS.md`` stays writable on purpose:
# it is instruction text only (never executed), repositories edit it as normal
# work, and every change to it is part of the reviewed candidate diff.
CLINE_TARGET_CUSTOMIZATION_PATHS = (".cline", ".clinerules", ".agents")
# Cline tool admission (#2332, Owner ruling relayed for #2332: auto-approve
# file-editing tools only, because cline already runs inside the Seatbelt).
# Cline 3.0.69 has no per-tool approval on its CLI, and headless approval is
# refused for every tool, so the run uses cline's yolo mode (all *enabled* tools
# auto-approved; its tool set is read_files, editor, run_commands, skills and
# submit_and_exit, no sub-agents/teams) and a global-settings file that the
# worker cannot write disables every tool outside ``CLINE_ADMITTED_TOOLS``.
# The delivery check also refuses any run whose event stream shows another
# tool, so a settings file that failed to load (cline then falls back to its
# defaults) is never delivery.
CLINE_ADMITTED_TOOLS = frozenset({"read_files", "editor", "apply_patch", "submit_and_exit"})
CLINE_DISABLED_TOOLS = (
    "run_commands",
    "fetch_web_content",
    "skills",
    "ask_question",
    "search_codebase",
)
CLINE_SUPPORTED_VERSIONS = frozenset({"3.0.69"})
# Run-HOME paths cline loads as code or configuration (hooks, plugins,
# skills, rules, MCP servers).  The worker may not plant them mid-run: the
# whole ``~/.cline`` and ``~/Documents/Cline`` trees are write-denied except
# the data directory (sessions, db, logs, the refreshed providers.json).
CLINE_RUN_HOME_PROTECTED_PATHS = (Path(".cline"), Path("Documents"), Path(".agents"))
CLINE_RUN_HOME_WRITABLE_PATHS = (Path(".cline") / "data",)


def cline_run_settings() -> dict[str, Any]:
    """Cline global settings for one run: only the admitted tools stay enabled."""
    return {
        "disabledTools": list(CLINE_DISABLED_TOOLS),
        "tools": {"web_search": {"enabled": False}},
        "telemetryOptOut": True,
        "autoUpdateEnabled": False,
    }


def write_cline_run_config(config_dir: Path) -> dict[str, str]:
    """Write cline's per-run settings into ``config_dir``; the env pointing at them.

    ``config_dir`` must lie outside every Seatbelt-writable path, so the
    worker can neither re-enable a tool nor add an MCP server mid-run.
    """
    config_dir.mkdir(parents=True, exist_ok=True)
    settings = config_dir / "global-settings.json"
    mcp = config_dir / "cline_mcp_settings.json"
    settings.write_text(json.dumps(cline_run_settings(), sort_keys=True), encoding="utf-8")
    mcp.write_text(json.dumps({"mcpServers": {}}), encoding="utf-8")
    for path in (settings, mcp):
        os.chmod(path, 0o400)
    return {
        "CLINE_GLOBAL_SETTINGS_PATH": str(settings),
        "CLINE_MCP_SETTINGS_PATH": str(mcp),
    }


AGY_RUN_HOME_SETTINGS = Path(".gemini") / "antigravity-cli" / "settings.json"
AGY_RUN_HOME_PROJECTS = Path(".gemini") / "config" / "projects"

# Child environment allowlist (#1912).  Probed: agy authenticates and edits
# with only PATH, LANG, HOME, TMPDIR, USER, LOGNAME, SHELL and TERM.  Proxy
# variables pass through only when present.  Everything else (NEXUS_*,
# tokens, API keys, GH_*/GITHUB_*, OPENAI_*/ANTHROPIC_*, Google ADC, ...) is
# dropped.
AGY_ENV_ALLOWLIST = frozenset({"PATH", "LANG", "TERM", "USER", "LOGNAME", "SHELL"})
AGY_ENV_PROXY_KEYS = frozenset({
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "NO_PROXY",
    "ALL_PROXY",
    "http_proxy",
    "https_proxy",
    "no_proxy",
    "all_proxy",
})


def agy_child_env(
    source: Optional[Mapping[str, str]], *, home: Path, tmpdir: Path
) -> dict[str, str]:
    """Allowlisted environment for an agy child process."""
    base = os.environ if source is None else source
    env = {
        str(key): str(value)
        for key, value in base.items()
        if key in AGY_ENV_ALLOWLIST or key in AGY_ENV_PROXY_KEYS or str(key).startswith("LC_")
    }
    env["HOME"] = str(home)
    env["TMPDIR"] = str(tmpdir)
    return env


def agy_run_settings(*, read_only: bool) -> dict[str, Any]:
    """Explicit per-run permission profile: never commands; no writes for plan."""
    deny = ["command(*)", "write_file(*)"] if read_only else ["command(*)"]
    return {"permissions": {"allow": [], "deny": deny}}


# Absolute path: the run's PATH is untrusted input to the boundary.
SECURITY_TOOL_PATH = "/usr/bin/security"
KEYCHAIN_ISOLATED = "ISOLATED"
KEYCHAIN_NOT_APPLICABLE = "NOT_APPLICABLE"
AGY_RUN_HOME_KEYCHAIN_UNAVAILABLE = "agy_run_home_keychain_unavailable"


def run_home_keychain_state(run_home: Path) -> str:
    """``ISOLATED`` when the run HOME carries its own default keychain file."""
    from nexus.services.agy_account_pool import AGY_ISOLATED_KEYCHAIN

    return (
        KEYCHAIN_ISOLATED
        if (run_home / AGY_ISOLATED_KEYCHAIN).is_file()
        else KEYCHAIN_NOT_APPLICABLE
    )


def isolate_run_home_keychain(run_home: Path) -> Optional[str]:
    """Give the run HOME its own default keychain on macOS; a refusal reason on failure.

    Without one, agy's OAuth token store finds no default keychain and macOS
    raises a modal "no keychain to store" dialog on the Owner's screen that
    blocks until a human answers (#2256, #2260).  ``security`` runs here,
    unsandboxed and with ``HOME=<run_home>``, so the real login keychain and
    the user's keychain preferences are never touched; the sandboxed agy only
    reads and writes that keychain file, which lies inside the writable run
    root.  Not macOS: nothing to do.
    """
    from nexus.services.agy_account_pool import (
        AgyAccountPoolManagerError,
        ensure_macos_isolated_keychain,
    )

    try:
        ensure_macos_isolated_keychain(str(run_home), security=SECURITY_TOOL_PATH)
    except (AgyAccountPoolManagerError, OSError):
        # security(1) failures and filesystem errors (mkdir, chmod, a missing
        # tool) are the same typed refusal: no isolated keychain, no run.
        return AGY_RUN_HOME_KEYCHAIN_UNAVAILABLE
    return None


def materialize_run_home(
    source_home: Path, run_home: Path, *, read_only: bool, isolate_keychain: bool = True
) -> tuple[Optional[str], str]:
    """Create the disposable HOME; return ``(refusal_reason, profile_sha256)``.

    The worker never sees the source HOME's settings, hooks, MCP config,
    projects or memory: only the copied auth files and the explicit settings
    written here.  The profile hash binds those settings and the mode.  On
    macOS the HOME also gets its own default keychain (``isolate_keychain``;
    the dispatch boundary does this itself and passes ``False``).
    """
    for relative in AGY_RUN_HOME_COPIED_FILES:
        source = source_home / relative
        destination = run_home / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        try:
            shutil.copyfile(source, destination)
            os.chmod(destination, 0o600)
        except FileNotFoundError:
            # No token: agy itself fails authentication, which is a typed
            # non-delivery on the normal result path.
            continue
        except OSError:
            return "agy_run_home_unavailable", ""
    settings = json.dumps(agy_run_settings(read_only=read_only), sort_keys=True, indent=2) + "\n"
    settings_path = run_home / AGY_RUN_HOME_SETTINGS
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(settings, encoding="utf-8")
    # agy must create its project record; the rest of config/ stays locked.
    (run_home / AGY_RUN_HOME_PROJECTS).mkdir(parents=True, exist_ok=True)
    if isolate_keychain:
        keychain_refusal = isolate_run_home_keychain(run_home)
        if keychain_refusal is not None:
            return keychain_refusal, ""
    profile = json.dumps(
        {"mode": "plan" if read_only else "accept-edits", "settings": settings},
        sort_keys=True,
        separators=(",", ":"),
    )
    return None, hashlib.sha256(profile.encode("utf-8")).hexdigest()


def materialize_cline_run_home(source_home: Path, run_home: Path) -> Optional[str]:
    """Create cline's disposable HOME; a refusal reason, else ``None`` (#2254).

    Only ``CLINE_RUN_HOME_COPIED_FILES`` cross over (mode 0600); the source
    HOME's other credentials (``~/.ssh``, ``~/.config/gh``, ``~/.gitconfig``,
    keychains) and cline's history/db/hooks never do.  A missing auth file is
    not a refusal: cline then fails authentication itself, a typed non-delivery.
    """
    run_home.mkdir(parents=True, exist_ok=True)
    for relative in CLINE_RUN_HOME_COPIED_FILES:
        destination = run_home / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        try:
            shutil.copyfile(source_home / relative, destination)
            os.chmod(destination, 0o600)
        except FileNotFoundError:
            continue
        except OSError:
            return "cline_run_home_unavailable"
    return None


# ---------------------------------------------------------------------------
# Seatbelt
# ---------------------------------------------------------------------------


def _sbpl_path(path: Path) -> str:
    text = str(path)
    if '"' in text or "\\" in text or "\n" in text:
        raise ValueError("path not representable in a Seatbelt profile")
    return text


# Workspace customizations agy may load on a later run in the target (hooks,
# plugins, MCP servers, skills, rules): the whole ``.agents`` subtree.
TARGET_AGY_CUSTOMIZATION_PATHS = (
    ".agents",
    ".antigravitycli",
)


def run_home_settings_sha256(run_home: Path) -> str:
    try:
        return hashlib.sha256((run_home / AGY_RUN_HOME_SETTINGS).read_bytes()).hexdigest()
    except OSError:
        return "unreadable"


# Credential material under the REAL (source) home that a confined worker must
# not read by absolute path (#1752/#1841).  The disposable run HOME holds the
# copies the worker needs; nothing here is required by agy or cline.  A
# ``literal`` plus ``subpath`` pair covers both files and directories.
SOURCE_HOME_CREDENTIAL_PATHS = (
    ".ssh",
    ".config/gh",
    ".git-credentials",
    ".netrc",
    ".gitconfig",
    ".config/git/config",
    ".config/git/credentials",
    ".config/nexus-agent-bot",
    ".config/nexus-jev",
    ".codex",
    ".cline",
    ".gemini",
    ".grok",
    ".aws",
    ".docker/config.json",
    ".npmrc",
    ".pypirc",
    "Library/Keychains",
)


class CredentialPathOverlapError(ValueError):
    """The writable target or run root sits inside a denied credential path."""


def _is_within(path: Path, parent: Path) -> bool:
    if sys.platform == "darwin":  # case-insensitive filesystems
        path, parent = Path(str(path).casefold()), Path(str(parent).casefold())
    return path == parent or parent in path.parents


def _credential_candidates(unresolved: Path) -> list[Path]:
    """The credential path, where it resolves to, and where symlinks inside it lead.

    Seatbelt matches resolved vnodes: ``~/.gitconfig -> ~/dotfiles/gitconfig`` or
    ``~/.ssh/id_rsa -> ~/dotfiles/ssh/id_rsa`` would otherwise stay readable.
    Only the first level inside a credential directory is scanned.
    """
    found = [unresolved, Path(os.path.realpath(unresolved))]
    if found[1].is_dir():
        try:
            with os.scandir(found[1]) as entries:
                for entry in entries:
                    if entry.is_symlink():
                        found.append(Path(os.path.realpath(entry.path)))
        except OSError:
            pass
    return list(dict.fromkeys(found))


def _credential_homes(source_home: Optional[Path]) -> list[Path]:
    """The source HOME plus the account's real home (pool HOMEs differ from it)."""
    homes = [Path(os.path.realpath(source_home if source_home is not None else worker_home(None)))]
    try:
        account_home = Path(os.path.realpath(pwd.getpwuid(os.getuid()).pw_dir))
    except (KeyError, OSError):
        return homes
    if account_home not in homes:
        homes.append(account_home)
    return homes


def build_seatbelt_profile(
    *,
    run_root: Path,
    writable_target: Optional[Path],
    run_home: Optional[Path] = None,
    extra_protected_target_names: tuple[str, ...] = (),
    source_home: Optional[Path] = None,
    target_root: Optional[Path] = None,
    extra_protected_paths: tuple[Path, ...] = (),
    extra_reallowed_paths: tuple[Path, ...] = (),
    deny_process_fork: bool = False,
) -> str:
    """Deny every file write except the target and the per-run root.

    It also denies READS of the credential paths in
    ``SOURCE_HOME_CREDENTIAL_PATHS`` under ``source_home`` (the real home the
    run HOME was materialized from; default ``worker_home(None)``).  Only those
    subpaths are denied: the target and run root stay readable wherever they
    live.  ``target_root`` is the (possibly read-only) target, checked for overlap.
    The macOS keychain daemon is not covered (see #1841).

    ``run_root`` holds the disposable HOME and TMPDIR, so the real HOME
    (``~/.gemini`` config, projects, OAuth token, memory) and
    ``~/Library/Keychains`` stay read-only; probes showed agy needs neither.
    The target's ``.git`` entry stays read-only too, so a worker cannot
    repoint the worktree at an attacker-controlled gitdir.  Paths must be
    real paths (Seatbelt matches resolved vnodes).
    """
    allow = [run_root]
    deny: list[str] = []
    if writable_target is not None:
        allow.insert(0, writable_target)
        git_entry = _sbpl_path(writable_target / ".git")
        deny = [f'  (literal "{git_entry}")', f'  (subpath "{git_entry}")']
        # Workspace customizations agy loads on a later run in this target
        # (hooks, plugins, MCP servers) must not be plantable by a worker.
        for name in TARGET_AGY_CUSTOMIZATION_PATHS:
            entry = _sbpl_path(writable_target / name)
            deny += [f'  (literal "{entry}")', f'  (subpath "{entry}")']
        # Worker-specific workspace customizations (e.g. cline's .cline).
        for name in extra_protected_target_names:
            entry = _sbpl_path(writable_target / name)
            deny += [f'  (literal "{entry}")', f'  (subpath "{entry}")']
    # Absolute paths inside a writable root that stay read-only (e.g. cline's
    # run-HOME hooks/plugins, #2332); ``extra_reallowed_paths`` re-opens a
    # subtree of them (cline's data directory).
    for path in extra_protected_paths:
        entry = _sbpl_path(path)
        deny += [f'  (literal "{entry}")', f'  (subpath "{entry}")']
    reallow: list[str] = [f'  (subpath "{_sbpl_path(path)}")' for path in extra_reallowed_paths]
    if run_home is not None:
        # The worker may not rewrite its own permission profile or the agy
        # config (hooks, MCP, plugins); only the project registry stays
        # writable because agy creates its project record there.
        settings = _sbpl_path(run_home / AGY_RUN_HOME_SETTINGS)
        config = _sbpl_path(run_home / ".gemini" / "config")
        deny += [f'  (literal "{settings}")', f'  (literal "{config}")', f'  (subpath "{config}")']
        reallow.append(f'  (subpath "{_sbpl_path(run_home / AGY_RUN_HOME_PROJECTS)}")')
    credential_denies: list[str] = []
    for home in _credential_homes(source_home):
        for relative in SOURCE_HOME_CREDENTIAL_PATHS:
            unresolved = home / relative
            for candidate in _credential_candidates(unresolved):
                entry = _sbpl_path(candidate)
                for owned in (run_root, writable_target, run_home, target_root):
                    if owned is None:
                        continue
                    resolved = Path(os.path.realpath(owned))
                    # A target inside a denied path cannot be read.  A symlink
                    # destination inside a writable target (a dotfiles repo)
                    # would also be writable, so that direction is refused too.
                    if _is_within(resolved, candidate) or (
                        candidate != unresolved and _is_within(candidate, resolved)
                    ):
                        raise CredentialPathOverlapError(
                            "target or run root overlaps a denied credential path"
                        )
                credential_denies += [f'  (literal "{entry}")', f'  (subpath "{entry}")']
    lines = [
        "(version 1)",
        "(allow default)",
        "(deny file-write*)",
        "(allow file-write*",
        *[f'  (subpath "{_sbpl_path(path)}")' for path in allow],
        '  (literal "/dev/null")',
        '  (literal "/dev/tty")',
        '  (regex #"^/dev/fd/")',
        '  (regex #"^/dev/ttys"))',
    ]
    if deny:
        lines += ["(deny file-write*", *deny, ")"]
    if reallow:
        lines += ["(allow file-write*", *reallow, ")"]
    # Reads of the real home's credential files (#1752); appended last so the
    # leading profile lines stay stable.
    lines += ["(deny file-read*", *credential_denies, ")"]
    # A worker whose tools all run in-process (cline, #2332) may not start
    # any process: a shell tool fails with EPERM whatever cline's settings say.
    if deny_process_fork:
        lines.append("(deny process-fork)")
    return "\n".join(lines) + "\n"


def seatbelt_available() -> bool:
    return (
        sys.platform == "darwin"
        and os.path.isfile(SANDBOX_EXEC_PATH)
        and os.access(SANDBOX_EXEC_PATH, os.X_OK)
    )


# ---------------------------------------------------------------------------
# protected checkouts and integrity fingerprint
# ---------------------------------------------------------------------------


def _git_output(root: Path, *args: str) -> Optional[bytes]:
    try:
        completed = subprocess.run(
            [
                "git",
                "--no-optional-locks",
                "-c",
                "core.fsmonitor=false",
                "-c",
                "core.hooksPath=/dev/null",
                *args,
            ],
            cwd=root,
            capture_output=True,
            timeout=120,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return completed.stdout if completed.returncode == 0 else None


def _path_key(path: Path) -> str:
    text = os.path.realpath(path)
    return text.casefold() if sys.platform == "darwin" else text


def paths_overlap(left: Path, right: Path) -> bool:
    return path_inside(left, right) or path_inside(right, left)


def path_inside(path: Path, root: Path) -> bool:
    a, b = _path_key(path), _path_key(root)
    return a == b or a.startswith(b.rstrip(os.sep) + os.sep)


def main_worktree_of(target: Path) -> Optional[Path]:
    """Non-bare main worktree behind ``target``'s Git common dir, if any.

    A bare repository (the gateway deployment layout) has no checkout to
    protect; its first ``worktree list`` entry is marked ``bare`` and skipped.
    """
    if _git_output(target, "rev-parse", "--git-common-dir") is None:
        return None
    listing = _git_output(target, "worktree", "list", "--porcelain")
    if not listing:
        return None
    first_block = listing.decode("utf-8", errors="surrogateescape").split("\n\n")[0]
    lines = first_block.splitlines()
    if not lines or not lines[0].startswith("worktree ") or "bare" in lines[1:]:
        return None
    return Path(lines[0][len("worktree ") :])


def protected_checkout_plan(
    *,
    target: Path,
    controller_repo_root: Optional[str],
    canonical_source_root: Path,
) -> list[tuple[Path, bool]]:
    """``(root, include_ignored)`` for each deduplicated protected checkout.

    Union of the contract's controller checkout, the non-bare main worktree
    of the target's Git common dir (unless that is the target itself) and the
    loaded canonical source root; realpath, case-insensitive on darwin.

    Ignored-file stats are fingerprinted only for the controller and
    canonical source roots.  The target's main worktree is often the Owner's
    working checkout where concurrent sessions touch logs and caches; there
    Seatbelt already denies every worker write, so only the overlap refusal
    and the tracked/untracked fingerprint are kept to avoid false failures.
    That claim holds for every caller of this plan: the Agy and Cline adapters
    both launch the worker under ``build_seatbelt_profile`` (#2254) and fail
    closed when Seatbelt is unavailable.  A worker that runs without Seatbelt
    must fingerprint ignored files too (``include_ignored=True``).
    """
    candidates: list[tuple[Path, bool]] = []
    if controller_repo_root and str(controller_repo_root).strip():
        candidates.append((Path(str(controller_repo_root)).expanduser(), True))
    main = main_worktree_of(target)
    if main is not None and _path_key(main) != _path_key(target):
        candidates.append((main, False))
    candidates.append((canonical_source_root, True))
    plan: dict[str, tuple[Path, bool]] = {}
    for candidate, include_ignored in candidates:
        key = _path_key(candidate)
        if key in plan:
            plan[key] = (plan[key][0], plan[key][1] or include_ignored)
        else:
            plan[key] = (Path(os.path.realpath(candidate)), include_ignored)
    return list(plan.values())


def protected_checkout_roots(
    *,
    target: Path,
    controller_repo_root: Optional[str],
    canonical_source_root: Path,
) -> list[Path]:
    return [
        root
        for root, _ in protected_checkout_plan(
            target=target,
            controller_repo_root=controller_repo_root,
            canonical_source_root=canonical_source_root,
        )
    ]


def _update(digest: Any, label: bytes, part: bytes) -> None:
    digest.update(label)
    digest.update(len(part).to_bytes(8, "big"))
    digest.update(part)


def _tree_files(root: Path) -> Iterable[tuple[str, bytes]]:
    if not root.is_dir():
        return
    for directory, dirnames, filenames in os.walk(root):
        dirnames.sort()
        for name in sorted(filenames):
            path = Path(directory) / name
            relative = path.relative_to(root).as_posix()
            try:
                if path.is_symlink():
                    yield relative, b"link:" + os.readlink(path).encode("utf-8", "surrogateescape")
                else:
                    yield relative, hashlib.sha256(path.read_bytes()).digest()
            except OSError:
                yield relative, b"unreadable"


# #2541: the common dir's ``config`` is shared by every worktree and is
# rewritten whenever another session creates a branch or worktree.  Only the
# keys named here are excluded from the fingerprint, and only while their
# value has the shape Git's own bookkeeping writes; every other key, known or
# unknown, stays covered (``core.hooksPath``, ``include*``, ``filter.*``,
# ``alias.*``, ``remote.*.url`` ...).  Keys are matched exactly on the
# lower-cased section and variable name that ``git config --list`` prints.
_CONFIG_BOOKKEEPING_BRANCH_VARS: frozenset[str] = frozenset({
    "remote",
    "pushremote",
    "merge",
    "rebase",
    "description",
    "vscode-merge-base",
    "gh-merge-base",
})
_CONFIG_BOOKKEEPING_REMOTE_VARS: frozenset[str] = frozenset({"fetch"})
_CONFIG_REBASE_VALUES: frozenset[str] = frozenset({
    "true",
    "false",
    "merges",
    "interactive",
    "i",
    "m",
})
_REF_NAME_RE = re.compile(r"refs/[A-Za-z0-9._/+@-]+")
_FETCH_REFSPEC_RE = re.compile(r"\+?refs/heads/([A-Za-z0-9._/*+@-]+):refs/remotes/(.+)")


def _split_config_key(key: str) -> Optional[tuple[str, str, str]]:
    """``(section, subsection, variable)`` of a three-level key, else ``None``."""
    section, dot, rest = key.partition(".")
    subsection, dot2, variable = rest.rpartition(".")
    if not dot or not dot2 or not subsection:
        return None
    return section, subsection, variable


def _config_key_is_bookkeeping(key: str) -> bool:
    """True only for the named ``branch.<name>.<var>`` / ``remote.<name>.fetch`` keys."""
    parts = _split_config_key(key)
    if parts is None:
        return False  # two-level keys (``branch.autosetupmerge``) stay covered
    section, _, variable = parts
    if section == "branch":
        return variable in _CONFIG_BOOKKEEPING_BRANCH_VARS
    if section == "remote":
        return variable in _CONFIG_BOOKKEEPING_REMOTE_VARS
    return False


def _config_entry_is_bookkeeping(key: str, value: Optional[str], remotes: frozenset[str]) -> bool:
    """A named bookkeeping key whose value cannot redirect Git elsewhere.

    ``branch.*.remote`` / ``pushremote`` must name a remote whose URL is in
    the same file (or ``.``, the local repository): a URL or path value
    stays covered.  ``merge`` and the merge-base keys must be ref names,
    ``rebase`` one of Git's values, and ``remote.<name>.fetch`` the standard
    ``refs/heads/X:refs/remotes/<name>/X`` mapping.
    """
    if value is None or not _config_key_is_bookkeeping(key):
        return False
    parts = _split_config_key(key)
    assert parts is not None
    section, subsection, variable = parts
    if section == "remote":
        match = _FETCH_REFSPEC_RE.fullmatch(value)
        return bool(match) and match.group(2) == f"{subsection}/{match.group(1)}"
    if variable in {"remote", "pushremote"}:
        return value == "." or value in remotes
    if variable in {"merge", "vscode-merge-base", "gh-merge-base"}:
        return bool(_REF_NAME_RE.fullmatch(value)) and ".." not in value
    if variable == "rebase":
        return value.lower() in _CONFIG_REBASE_VALUES
    return variable == "description"


def code_bearing_git_config(
    config_path: Path, *, exclude_bookkeeping: bool = True
) -> Optional[bytes]:
    """Code-bearing entries of one Git config file; ``None`` if unparseable.

    Parsed by Git itself (``git config --file <path> --no-includes --list
    -z``) so the fingerprint sees exactly the keys Git will act on, in file
    order.  ``include.path`` / ``includeIf.*.path`` keys are covered as
    values.  A missing file reads as ``b"missing"``; a file Git refuses to
    parse fails closed.  ``exclude_bookkeeping=False`` keeps every entry
    (used for the per-worktree ``config.worktree``, which nobody else writes).
    """
    if not os.path.lexists(config_path):
        return b"missing"
    listing = _git_output(
        config_path.parent,
        "config",
        "--file",
        str(config_path),
        "--no-includes",
        "--list",
        "-z",
    )
    if listing is None:
        return None
    entries: list[tuple[str, Optional[str], bytes]] = []
    for entry in listing.split(b"\0"):
        if not entry:
            continue
        raw_key, newline, raw_value = entry.partition(b"\n")
        key = raw_key.decode("utf-8", errors="surrogateescape")
        value = raw_value.decode("utf-8", errors="surrogateescape") if newline else None
        entries.append((key, value, entry))
    remotes = frozenset(
        parts[1]
        for key, value, _ in entries
        if value
        and (parts := _split_config_key(key))
        and parts[0] == "remote"
        and parts[2] == "url"
    )
    kept: list[bytes] = []
    for key, value, entry in entries:
        if exclude_bookkeeping and _config_entry_is_bookkeeping(key, value, remotes):
            continue
        kept.append(len(entry).to_bytes(8, "big") + entry)
    return b"".join(kept)


def _code_bearing_config_parts(
    common_dir: Path, git_dir: Path
) -> Optional[list[tuple[bytes, bytes]]]:
    """Labelled config material shared by both fingerprints; ``None`` if unparseable.

    The common dir's ``config`` minus bookkeeping and the per-worktree
    ``config.worktree`` unfiltered (see ``code_bearing_git_config``).
    """
    config = code_bearing_git_config(common_dir / "config")
    worktree_config = code_bearing_git_config(
        git_dir / "config.worktree", exclude_bookkeeping=False
    )
    if config is None or worktree_config is None:
        return None
    return [(b"common:config", config), (b"gitdir:config.worktree", worktree_config)]


def git_config_fingerprint(root: Path | str) -> Optional[str]:
    """sha256 hex of the code-bearing Git config behind ``root``; ``None`` on failure.

    Exactly the config material ``checkout_fingerprint`` covers, for callers
    that fingerprint the rest of a checkout themselves, so the bookkeeping
    exclusions have one definition (#2547).  Its only caller, the Codex
    launcher and ``codex_run_guard.py``, was retired on 2026-10-21 (#2584
    Phase-2 batch B).  A root Git cannot resolve, or a config Git refuses to
    parse, fails closed.
    """
    path = Path(os.path.realpath(root))
    common = _git_output(path, "rev-parse", "--path-format=absolute", "--git-common-dir")
    git_dir = _git_output(path, "rev-parse", "--absolute-git-dir")
    if common is None or git_dir is None:
        return None
    config_parts = _code_bearing_config_parts(
        Path(common.decode("utf-8", errors="surrogateescape").strip()),
        Path(git_dir.decode("utf-8", errors="surrogateescape").strip()),
    )
    if config_parts is None:
        return None
    digest = hashlib.sha256()
    for label, part in config_parts:
        _update(digest, label, part)
    return digest.hexdigest()


def checkout_fingerprint(root: Path | str, *, include_ignored: bool = True) -> Optional[str]:
    """Fingerprint one protected checkout; ``None`` when it cannot be read.

    Covers HEAD, porcelain status, the tracked diff, untracked file bytes, a
    stat of every ignored path (``--directory`` collapsed, so ``.venv/`` is
    one entry: deep writes inside ignored directories are left to Seatbelt),
    and the Git common dir's code-bearing metadata: ``config`` (minus the
    bookkeeping keys named in ``_CONFIG_BOOKKEEPING_*`` with bookkeeping-shaped
    values), the per-worktree ``config.worktree`` (unfiltered), ``hooks/`` and ``info/``.  Refs and ``packed-refs``
    are deliberately excluded: the common dir is shared with concurrent
    sessions that fetch and branch, and Seatbelt already denies the worker
    any write there.  Unparseable config fails closed (``None``).
    """
    path = Path(os.path.realpath(root))
    toplevel = _git_output(path, "rev-parse", "--show-toplevel")
    if toplevel is None or _path_key(
        Path(toplevel.decode("utf-8", "surrogateescape").strip())
    ) != _path_key(path):
        return None
    head = _git_output(path, "rev-parse", "--verify", "HEAD")
    status = _git_output(path, "status", "--porcelain=v1", "-uall", "-z")
    diff = _git_output(path, "diff", "--binary", "HEAD")
    ignored = (
        _git_output(
            path, "ls-files", "-z", "--others", "--ignored", "--exclude-standard", "--directory"
        )
        if include_ignored
        else b""
    )
    common = _git_output(path, "rev-parse", "--path-format=absolute", "--git-common-dir")
    git_dir = _git_output(path, "rev-parse", "--absolute-git-dir")
    if None in (head, status, diff, ignored, common, git_dir):
        return None
    assert head is not None and status is not None and diff is not None
    assert ignored is not None and common is not None and git_dir is not None
    digest = hashlib.sha256()
    _update(digest, b"head", head)
    _update(digest, b"status", status)
    _update(digest, b"diff", hashlib.sha256(diff).digest())
    for entry in status.split(b"\0"):
        if entry.startswith(b"?? "):
            relative = entry[3:].decode("utf-8", errors="surrogateescape")
            try:
                content = hashlib.sha256((path / relative).read_bytes()).digest()
            except OSError:
                content = b"unreadable"
            _update(digest, b"untracked:" + entry, content)
    for entry in ignored.split(b"\0"):
        if not entry:
            continue
        relative = entry.decode("utf-8", errors="surrogateescape").rstrip("/")
        try:
            stat = os.lstat(path / relative)
            stamp = f"{stat.st_mode}:{stat.st_size}:{stat.st_mtime_ns}".encode()
        except OSError:
            stamp = b"missing"
        _update(digest, b"ignored:" + entry, stamp)
    common_dir = Path(common.decode("utf-8", errors="surrogateescape").strip())
    git_dir_path = Path(git_dir.decode("utf-8", errors="surrogateescape").strip())
    config_parts = _code_bearing_config_parts(common_dir, git_dir_path)
    if config_parts is None:
        return None
    for label, part in config_parts:
        _update(digest, label, part)
    for name in ("hooks", "info"):
        for relative, content in _tree_files(common_dir / name):
            _update(digest, f"common:{name}/{relative}".encode("utf-8", "surrogateescape"), content)
    return digest.hexdigest()


def fingerprint_roots(plan: Iterable[tuple[Path, bool]]) -> Optional[dict[str, str]]:
    result: dict[str, str] = {}
    for root, include_ignored in plan:
        value = checkout_fingerprint(root, include_ignored=include_ignored)
        if value is None:
            return None
        result[str(root)] = value
    return result


def escaping_symlinks(target: Path) -> dict[str, str]:
    """Symlinks under ``target`` (excluding ``.git``) that resolve outside it."""
    found: dict[str, str] = {}
    real_target = Path(os.path.realpath(target))
    for directory, dirnames, filenames in os.walk(real_target):
        if ".git" in dirnames:
            dirnames.remove(".git")
        for name in [*dirnames, *filenames]:
            path = Path(directory) / name
            if not path.is_symlink():
                continue
            if not path_inside(Path(os.path.realpath(path)), real_target):
                try:
                    found[path.relative_to(real_target).as_posix()] = os.readlink(path)
                except OSError:
                    found[path.relative_to(real_target).as_posix()] = "unreadable"
    return found


def target_git_entry_state(target: Path) -> str:
    """Hash of the target's ``.git`` entry: the gitdir pointer file, or the
    code-bearing parts (config, hooks, info) of an embedded ``.git`` dir."""
    entry = Path(os.path.realpath(target)) / ".git"
    digest = hashlib.sha256()
    try:
        if entry.is_symlink():
            _update(digest, b"symlink", os.readlink(entry).encode("utf-8", "surrogateescape"))
        elif entry.is_file():
            _update(digest, b"file", entry.read_bytes())
        elif entry.is_dir():
            try:
                _update(digest, b"config", (entry / "config").read_bytes())
            except OSError:
                _update(digest, b"config", b"missing")
            for name in ("hooks", "info"):
                for relative, content in _tree_files(entry / name):
                    _update(
                        digest, f"{name}/{relative}".encode("utf-8", "surrogateescape"), content
                    )
        else:
            _update(digest, b"absent", b"")
    except OSError:
        _update(digest, b"unreadable", b"")
    return digest.hexdigest()


def leased_target_failure(contract: Any, lease: Any) -> Optional[str]:
    """``agy_target_not_leased_worktree`` unless the target is the contract's leased worktree.

    The target must equal the contract's ``target_repo_root``, sit strictly
    inside its ``target_worktree_root``, and the lease must carry the
    contract's task id.
    """
    reason = "agy_target_not_leased_worktree"
    task_id = str(getattr(contract, "task_id", "") or "")
    root = str(getattr(contract, "target_worktree_root", "") or "").strip()
    repo_root = str(getattr(contract, "target_repo_root", "") or "").strip()
    target = str(getattr(lease, "target_worktree", "") or "").strip()
    if not (task_id and root and repo_root and target):
        return reason
    if str(getattr(lease, "task_id", "") or "") != task_id:
        return reason
    target_path = Path(os.path.realpath(Path(target).expanduser()))
    root_path = Path(os.path.realpath(Path(root).expanduser()))
    if _path_key(target_path) != _path_key(Path(repo_root).expanduser()):
        return reason
    if _path_key(target_path) == _path_key(root_path) or not path_inside(target_path, root_path):
        return reason
    return None


def worker_home(env: Optional[Mapping[str, str]]) -> Path:
    home = (env or {}).get("HOME") or os.environ.get("HOME") or str(Path.home())
    return Path(os.path.realpath(Path(home).expanduser()))
