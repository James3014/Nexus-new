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


def agy_delivery_failure(stdout: bytes, stderr: bytes) -> Optional[str]:
    """Typed non-delivery reason for an Agy run that exited 0, else ``None``.

    Delivery requires a parseable JSON object with ``status == "SUCCESS"``,
    no ``denied_actions`` and a non-empty ``response``.  The headless denial
    marker is only trusted on stderr, never in the model-controlled stdout.
    """
    err = stderr.decode("utf-8", errors="replace")
    if any(marker in err for marker in _AGY_HEADLESS_PERMISSION_DENIAL_MARKERS):
        return "agy_permission_denied"
    text = stdout.decode("utf-8", errors="replace")
    if not text.strip():
        return "agy_no_output"
    payload = last_json_object(text)
    if payload is None:
        return "agy_output_unparseable"
    if payload.get("denied_actions"):
        return "agy_permission_denied"
    if payload.get("status") != "SUCCESS":
        return "agy_status_not_success"
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
AGY_RUN_HOME_SETTINGS = Path(".gemini") / "antigravity-cli" / "settings.json"


def agy_run_settings(*, read_only: bool) -> dict[str, Any]:
    """Explicit per-run permission profile: never commands; no writes for plan."""
    deny = ["command(*)", "write_file(*)"] if read_only else ["command(*)"]
    return {"permissions": {"allow": [], "deny": deny}}


def materialize_run_home(
    source_home: Path, run_home: Path, *, read_only: bool
) -> tuple[Optional[str], str]:
    """Create the disposable HOME; return ``(refusal_reason, profile_sha256)``.

    The worker never sees the source HOME's settings, hooks, MCP config,
    projects or memory: only the copied auth files and the explicit settings
    written here.  The profile hash binds those settings and the mode.
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
    profile = json.dumps(
        {"mode": "plan" if read_only else "accept-edits", "settings": settings},
        sort_keys=True,
        separators=(",", ":"),
    )
    return None, hashlib.sha256(profile.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Seatbelt
# ---------------------------------------------------------------------------


def _sbpl_path(path: Path) -> str:
    text = str(path)
    if '"' in text or "\\" in text or "\n" in text:
        raise ValueError("path not representable in a Seatbelt profile")
    return text


TARGET_AGY_CUSTOMIZATION_PATHS = (
    ".agents/hooks.json",
    ".agents/plugins",
    ".agents/mcp_config.json",
    ".antigravitycli",
)


def build_seatbelt_profile(*, run_root: Path, writable_target: Optional[Path]) -> str:
    """Deny every file write except the target and the per-run root.

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


def checkout_fingerprint(root: Path | str, *, include_ignored: bool = True) -> Optional[str]:
    """Fingerprint one protected checkout; ``None`` when it cannot be read.

    Covers HEAD, porcelain status, the tracked diff, untracked file bytes, a
    stat of every ignored path (``--directory`` collapsed, so ``.venv/`` is
    one entry: deep writes inside ignored directories are left to Seatbelt),
    and the Git common dir's code-bearing metadata: ``config``, ``hooks/``
    and ``info/``.  Refs and ``packed-refs`` are deliberately excluded: the
    common dir is shared with concurrent sessions that fetch and branch, and
    Seatbelt already denies the worker any write there.
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
    if None in (head, status, diff, ignored, common):
        return None
    assert head is not None and status is not None and diff is not None
    assert ignored is not None and common is not None
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
    try:
        config = (common_dir / "config").read_bytes()
    except OSError:
        config = b"missing"
    _update(digest, b"common:config", config)
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


def worker_home(env: Optional[Mapping[str, str]]) -> Path:
    home = (env or {}).get("HOME") or os.environ.get("HOME") or str(Path.home())
    return Path(os.path.realpath(Path(home).expanduser()))
