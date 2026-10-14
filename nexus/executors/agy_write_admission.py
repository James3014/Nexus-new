"""Agy write-admission model for governed executors (Owner decision on #1912).

Layers, from preventive to detective:

1. Permission posture: no auto-approve flag ever reaches the argv.
   Implementation runs use ``--mode accept-edits`` (edits only; commands are
   auto-denied in headless print mode) and read-only roles ``--mode plan
   --sandbox``.  The effective Agy settings profile is read before each run
   and refused when it grants commands (or edits, for read-only roles).
2. Seatbelt: every run is wrapped in a macOS ``sandbox-exec`` profile that
   denies file writes everywhere except the runtime-owned target worktree
   (implementation only), Agy's own state directory and a per-run temp dir.
   This is what stops absolute-path, symlink and Git-internal writes; it is
   mandatory and fails closed when ``sandbox-exec`` is unavailable.
3. Integrity fingerprint of every protected checkout (secondary check): the
   contract's controller checkout, the main worktree behind the target's Git
   common dir, and the loaded canonical source root.
4. Output classification: only a parseable JSON result with status SUCCESS,
   no denied actions and a non-empty response is delivery.
"""

from __future__ import annotations

import hashlib
import json
import os
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
# effective Agy settings profile
# ---------------------------------------------------------------------------


def agy_settings_paths(home: Path) -> dict[str, Path]:
    gemini = home / ".gemini"
    return {
        "settings": gemini / "antigravity-cli" / "settings.json",
        "hooks": gemini / "config" / "hooks.json",
        "mcp": gemini / "config" / "mcp_config.json",
    }


def agy_permission_profile(home: Path, *, read_only: bool) -> tuple[Optional[str], str]:
    """Return ``(refusal_reason, profile_sha256)`` for the worker HOME.

    The profile hash binds the effective allow/deny lists, the mode, and the
    bytes of the hooks and MCP config files that Agy loads from that HOME.
    """
    paths = agy_settings_paths(home)
    allow: list[str] = []
    deny: list[str] = []
    reason: Optional[str] = None
    try:
        raw = paths["settings"].read_bytes() if paths["settings"].exists() else b""
        data = json.loads(raw.decode("utf-8")) if raw.strip() else {}
        perms = data.get("permissions") if isinstance(data, dict) else None
        if perms is not None and not isinstance(perms, dict):
            raise ValueError("permissions must be an object")
        perms = perms or {}
        allow = [str(rule) for rule in (perms.get("allow") or [])]
        deny = [str(rule) for rule in (perms.get("deny") or [])]
    except (OSError, ValueError) as exc:
        reason = f"agy_permission_profile_unreadable:{type(exc).__name__}"
    if reason is None and any(rule.strip().startswith("command") for rule in allow):
        reason = "agy_permission_profile_grants_commands"
    if (
        reason is None
        and read_only
        and any(rule.strip().startswith("write_file") for rule in allow)
    ):
        reason = "agy_permission_profile_grants_writes_for_read_only_role"
    extra: dict[str, str] = {}
    for name in ("hooks", "mcp"):
        try:
            extra[name] = hashlib.sha256(paths[name].read_bytes()).hexdigest()
        except FileNotFoundError:
            extra[name] = ""
        except OSError:
            extra[name] = "unreadable"
    canonical = json.dumps(
        {
            "allow": sorted(set(allow)),
            "deny": sorted(set(deny)),
            "mode": "plan" if read_only else "accept-edits",
            **extra,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return reason, hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Seatbelt
# ---------------------------------------------------------------------------


def _sbpl_path(path: Path) -> str:
    text = str(path)
    if '"' in text or "\\" in text or "\n" in text:
        raise ValueError("path not representable in a Seatbelt profile")
    return text


def build_seatbelt_profile(
    *,
    home: Path,
    run_tmp: Path,
    writable_target: Optional[Path],
) -> str:
    """Deny file writes except to the target, Agy state under HOME and run tmp.

    Paths must already be real paths (Seatbelt matches resolved vnodes).  Agy
    configuration that changes what runs (settings, hooks, MCP config, its own
    binaries) stays read-only even inside the state directory.
    """
    gemini = home / ".gemini"
    allow = [gemini, home / "Library" / "Keychains", run_tmp]
    if writable_target is not None:
        allow.insert(0, writable_target)
    deny_subpaths = [
        gemini / "antigravity-cli" / "bin",
        gemini / "antigravity-cli" / "builtin",
        gemini / "antigravity-cli" / "updater",
    ]
    deny_literals = list(agy_settings_paths(home).values())
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
        "(deny file-write*",
        *[f'  (subpath "{_sbpl_path(path)}")' for path in deny_subpaths],
        *[f'  (literal "{_sbpl_path(path)}")' for path in deny_literals],
        ")",
    ]
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
            ["git", "--no-optional-locks", *args],
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
    """Main worktree behind ``target``'s Git common dir, if ``target`` is in Git."""
    if _git_output(target, "rev-parse", "--git-common-dir") is None:
        return None
    listing = _git_output(target, "worktree", "list", "--porcelain")
    if not listing:
        return None
    first = listing.decode("utf-8", errors="surrogateescape").splitlines()[0]
    if not first.startswith("worktree "):
        return None
    return Path(first[len("worktree ") :])


def protected_checkout_roots(
    *,
    target: Path,
    controller_repo_root: Optional[str],
    canonical_source_root: Path,
) -> list[Path]:
    """Deduplicated (realpath, case-insensitive on darwin) protected checkouts.

    Union of the contract's controller checkout, the main worktree of the
    target's Git common dir (unless that is the target itself) and the
    loaded canonical source root.
    """
    candidates: list[Path] = []
    if controller_repo_root and str(controller_repo_root).strip():
        candidates.append(Path(str(controller_repo_root)).expanduser())
    main = main_worktree_of(target)
    if main is not None and _path_key(main) != _path_key(target):
        candidates.append(main)
    candidates.append(canonical_source_root)
    roots: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = _path_key(candidate)
        if key not in seen:
            seen.add(key)
            roots.append(Path(os.path.realpath(candidate)))
    return roots


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


def checkout_fingerprint(root: Path | str) -> Optional[str]:
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
    ignored = _git_output(
        path, "ls-files", "-z", "--others", "--ignored", "--exclude-standard", "--directory"
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


def fingerprint_roots(roots: Iterable[Path]) -> Optional[dict[str, str]]:
    result: dict[str, str] = {}
    for root in roots:
        value = checkout_fingerprint(root)
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


def worker_home(env: Optional[Mapping[str, str]]) -> Path:
    home = (env or {}).get("HOME") or os.environ.get("HOME") or str(Path.home())
    return Path(os.path.realpath(Path(home).expanduser()))
