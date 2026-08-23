#!/usr/bin/env python3
# ruff: noqa: E701, E702, E731
"""Fail-closed durable LaunchAgent manager (prototype; never activates on import)."""
from __future__ import annotations

import argparse
import contextlib
import errno
import fcntl
import hashlib
import json
import os
import plistlib
import re
import shlex
import stat
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable, Mapping

from nexus.contracts.gateway_deployment import (
    ContractError,
    DeploymentState,
    GatewayDeploymentRequest,
    PostflightIdentity,
    canonical_hash,
    validate_profile,
    validate_request,
    validate_rollback_capture,
)

CANONICAL_ROOT = Path("/Users/jameschen/Workspace/nexus")
CANONICAL_BRANCH = "nexus/integration/main"
SCRIPT_PATH = CANONICAL_ROOT / "scripts/ops/mcp_gateway_durable.py"
STATE_DIR = Path.home() / "Library/Application Support/Nexus"
ENV_PATH = STATE_DIR / "mcp-gateway.env"
PLIST_DIR = Path.home() / "Library/LaunchAgents"
LOG_DIR = Path.home() / "Library/Logs/Nexus"
PLISTS = {"gateway": PLIST_DIR / "com.nexus.mcp.gateway.plist", "devspace": PLIST_DIR / "com.nexus.mcp.devspace.plist"}
LABELS = {"gateway": "com.nexus.mcp.gateway", "devspace": "com.nexus.mcp.devspace"}
IDENTITY_PATH = STATE_DIR / "devspace" / "build-identity.json"
DEVSPACE_ROOT = Path.home() / ".npm-global/lib/node_modules/@nexus-local/devspace"
NODE_PATH = Path("/opt/homebrew/bin/node")
UID_TARGET = f"gui/{os.getuid()}"

class GateError(RuntimeError): pass

def _git(root: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(root), *args], text=True).strip()

def _is_ancestor(root: Path, ancestor: str, descendant: str) -> bool:
    """True if `ancestor` is reachable from `descendant` (forward-only floor check)."""
    result = subprocess.run(
        ["git", "-C", str(root), "merge-base", "--is-ancestor", ancestor, descendant],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0

def verify_gateway(root: Path = CANONICAL_ROOT, launch_floor_head: str | None = None) -> str:
    root = root.resolve()
    if root != CANONICAL_ROOT: raise GateError("canonical root mismatch")
    if _git(root, "branch", "--show-current") != CANONICAL_BRANCH: raise GateError("canonical branch mismatch")
    if _git(root, "status", "--porcelain"): raise GateError("canonical root is dirty")
    head = _git(root, "rev-parse", "HEAD")
    if launch_floor_head and not _is_ancestor(root, launch_floor_head, head):
        raise GateError("canonical HEAD is not a descendant of the launch floor commit")
    return head

def read_secret_env(path: Path | None = None) -> dict[str, str]:
    path = Path(path or ENV_PATH)
    if not path.is_absolute() or ".git" in path.parts: raise GateError("invalid env path")
    try:
        resolved = path.resolve(strict=False)
        resolved.relative_to(CANONICAL_ROOT.resolve(strict=False))
    except ValueError:
        pass
    except (OSError, RuntimeError):
        raise GateError("invalid env path")
    else:
        raise GateError("secret env must be outside canonical root")
    try: mode = path.stat().st_mode & 0o777
    except FileNotFoundError: raise GateError("secret env missing")
    if mode != 0o600: raise GateError("secret env must be mode 0600")
    values = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"): continue
        if line.startswith("export "): line = line[7:].lstrip()
        if "=" not in line: raise GateError("invalid env line")
        key, value = line.split("=", 1); key = key.strip()
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key) or key in values: raise GateError("invalid env key")
        try:
            tokens = shlex.split(value, posix=True)
            if len(tokens) > 1: raise GateError("invalid env quoting")
            value = tokens[0] if tokens else ""
        except ValueError: raise GateError("invalid env quoting")
        values[key] = value
    if not values.get("NEXUS_MCP_GATEWAY_TOKEN"): raise GateError("gateway token missing")
    return values

def _plist(kind: str, head: str, devspace_hash: str | None, devspace_root: Path = DEVSPACE_ROOT, node_path: Path = NODE_PATH) -> dict:
    args = ["/usr/bin/python3", str(SCRIPT_PATH), f"serve-{kind}", "--env-file", str(ENV_PATH), "--launch-floor-head", head]
    if kind == "devspace": args += ["--devspace-hash", devspace_hash or "", "--devspace-root", str(devspace_root), "--node-path", str(node_path)]
    payload = {"Label": LABELS[kind], "ProgramArguments": args, "WorkingDirectory": str(CANONICAL_ROOT), "RunAtLoad": True, "KeepAlive": True,
               "StandardOutPath": str(LOG_DIR / f"{kind}.log"), "StandardErrorPath": str(LOG_DIR / f"{kind}.err.log"),
               "EnvironmentVariables": {"NEXUS_GATEWAY_HEAD": head}}
    if kind == "devspace": payload["EnvironmentVariables"]["NEXUS_DEVSPACE_ARTIFACT_SHA256"] = devspace_hash
    return payload

def render(root: Path = CANONICAL_ROOT, launch_floor_head: str | None = None, devspace_hash: str | None = None, devspace_root: Path | None = None, node_path: Path | None = None) -> dict[str, bytes]:
    devspace_root = devspace_root or DEVSPACE_ROOT; node_path = node_path or NODE_PATH
    head = verify_gateway(root, launch_floor_head); read_secret_env()
    if not devspace_hash or len(devspace_hash) != 64 or any(c not in "0123456789abcdefABCDEF" for c in devspace_hash): raise GateError("explicit DevSpace artifact hash required")
    identity = devspace_root / "generated/build-identity.json"; cli = devspace_root / "dist/cli.js"
    if (not devspace_root.is_absolute() or not devspace_root.exists() or not node_path.is_absolute() or
        not node_path.is_file() or not os.access(node_path, os.X_OK) or not identity.is_file() or not cli.is_file() or
        hashlib.sha256(identity.read_bytes()).hexdigest() != devspace_hash): raise GateError("invalid DevSpace installation")
    return {k: plistlib.dumps(_plist(k, head, devspace_hash if k == "devspace" else None, devspace_root, node_path), fmt=plistlib.FMT_XML) for k in PLISTS}

def _atomic(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True); fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        with os.fdopen(fd, "wb") as handle:
            os.chmod(tmp, 0o600); handle.write(data); handle.flush(); os.fsync(handle.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp): os.unlink(tmp)

def manage(action: str, *, root: Path = CANONICAL_ROOT, launch_floor_head: str | None = None, devspace_hash: str | None = None, devspace_root: Path | None = None, node_path: Path | None = None,
           runner: Callable[..., str] | None = None) -> dict:
    devspace_root = devspace_root or DEVSPACE_ROOT; node_path = node_path or NODE_PATH
    run = runner or (lambda *args: subprocess.run(args, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE))
    def absent_service(result, args) -> bool:
        """Recognize only launchctl's documented missing per-user service forms."""
        code = getattr(result, "returncode", result[0] if isinstance(result, tuple) else 0)
        output = ((getattr(result, "stdout", "") or "") + (getattr(result, "stderr", "") or ""))
        output = str(output).strip()
        if len(args) < 3 or args[0] != "launchctl":
            return False
        target = str(args[-1])
        label = target.rsplit("/", 1)[-1]
        if args[1] == "print" and code == 113:
            expected = rf'Bad request\.\s*Could not find service "{re.escape(label)}" in domain for user gui:\s*{os.getuid()}\s*'
            return re.fullmatch(expected, output, flags=re.IGNORECASE | re.DOTALL) is not None
        if args[1] == "bootout" and code == 3:
            return re.fullmatch(r"Boot-out failed:\s*3:\s*No such process", output,
                                flags=re.IGNORECASE) is not None
        return False
    def invoke(*args):
        result = run(*args)
        code = getattr(result, "returncode", result[0] if isinstance(result, tuple) else 0)
        if code not in (0, None):
            if absent_service(result, args): return result
            raise GateError("launchctl command failed")
        return result
    if action in ("preflight", "render", "install"):
        blobs = render(root, launch_floor_head, devspace_hash, devspace_root, node_path)
        if action == "render": return {"gateway": blobs["gateway"].decode(), "devspace": blobs["devspace"].decode()}
        if action == "install":
            old = {k: PLISTS[k].read_bytes() if PLISTS[k].exists() else None for k in PLISTS}
            try:
                for k, data in blobs.items(): _atomic(PLISTS[k], data); invoke("launchctl", "bootout", f"{UID_TARGET}/{LABELS[k]}")
                for k in PLISTS: invoke("launchctl", "bootstrap", UID_TARGET, str(PLISTS[k]))
            except Exception:
                for k in PLISTS:
                    try: invoke("launchctl", "bootout", f"{UID_TARGET}/{LABELS[k]}")
                    except Exception: pass
                for k, data in old.items():
                    if data is None: PLISTS[k].unlink(missing_ok=True)
                    else: _atomic(PLISTS[k], data)
                for k, data in old.items():
                    if data is not None:
                        try: invoke("launchctl", "bootstrap", UID_TARGET, str(PLISTS[k]))
                        except Exception: pass
                raise
        return {"head": _git(root, "rev-parse", "HEAD"), "labels": list(LABELS.values())}
    if action == "status":
        out = {}
        for k, v in LABELS.items():
            r = invoke("launchctl", "print", f"{UID_TARGET}/{v}"); out[k] = {"label": v, "loaded": getattr(r, "returncode", 0) == 0, "returncode": getattr(r, "returncode", 0)}
        return out
    if action == "reload": return manage("install", root=root, launch_floor_head=launch_floor_head, devspace_hash=devspace_hash, devspace_root=devspace_root, node_path=node_path, runner=runner)
    if action == "uninstall":
        for k, label in LABELS.items(): invoke("launchctl", "bootout", f"{UID_TARGET}/{label}"); PLISTS[k].unlink(missing_ok=True)
        return {"removed": list(LABELS.values())}
    raise ValueError(action)

def serve(kind: str, *, root: Path = CANONICAL_ROOT, launch_floor_head: str | None = None,
          devspace_hash: str | None = None, devspace_root: Path = DEVSPACE_ROOT,
          node_path: Path = NODE_PATH, execve=os.execve) -> None:
    verify_gateway(root, launch_floor_head); env_file = read_secret_env()
    env = os.environ.copy(); env.update(env_file); env["NEXUS_CANONICAL_SOURCE_ROOT"] = str(CANONICAL_ROOT)
    if kind == "gateway":
        argv = [str(CANONICAL_ROOT / ".venv/bin/python"), str(CANONICAL_ROOT / "scripts/ops/nexus_mcp_gateway_http.py")]
    else:
        if not devspace_hash: raise GateError("explicit DevSpace artifact hash required")
        identity_path = devspace_root / "generated/build-identity.json"
        try: actual = hashlib.sha256(identity_path.read_bytes()).hexdigest()
        except OSError: raise GateError("DevSpace build identity missing")
        if actual != devspace_hash: raise GateError("DevSpace artifact hash mismatch")
        if not node_path.is_absolute() or not node_path.is_file() or not os.access(node_path, os.X_OK): raise GateError("invalid node executable")
        cli = devspace_root / "dist/cli.js"
        if not cli.is_file(): raise GateError("DevSpace CLI missing")
        argv = [str(node_path), str(cli), "serve"]
        env["NEXUS_MCP_SURFACE_PROFILE"] = "canonical_gateway_proxy"; env["MCP_PROTOCOL_MODE"] = "dual"; env["NEXUS_GATEWAY_PROXY_URL"] = "http://127.0.0.1:8766"; env["NEXUS_GATEWAY_PROXY_TOKEN"] = env_file["NEXUS_MCP_GATEWAY_TOKEN"]
        env["NEXUS_DEVSPACE_ARTIFACT_SHA256"] = devspace_hash
    execve(argv[0], argv, env)

def main() -> int:
    p = argparse.ArgumentParser(); p.add_argument("action", choices=("preflight","render","install","status","reload","uninstall","serve-gateway","serve-devspace")); p.add_argument("--launch-floor-head", dest="launch_floor_head"); p.add_argument("--expected-head", dest="launch_floor_head", help="backward-compat alias for --launch-floor-head"); p.add_argument("--devspace-hash"); p.add_argument("--env-file"); p.add_argument("--devspace-root", type=Path, default=DEVSPACE_ROOT); p.add_argument("--node-path", type=Path, default=NODE_PATH)
    a = p.parse_args()
    try:
        if a.env_file: globals()["ENV_PATH"] = Path(a.env_file)
        if a.action == "serve-gateway": serve("gateway", launch_floor_head=a.launch_floor_head)
        elif a.action == "serve-devspace": serve("devspace", launch_floor_head=a.launch_floor_head, devspace_hash=a.devspace_hash, devspace_root=a.devspace_root, node_path=a.node_path)
        else: print(json.dumps(manage(a.action, launch_floor_head=a.launch_floor_head, devspace_hash=a.devspace_hash, devspace_root=a.devspace_root, node_path=a.node_path), sort_keys=True))
    except (GateError, subprocess.CalledProcessError) as exc: p.error(str(exc))
    return 0
GATEWAY_LABEL = "com.nexus.mcp.gateway.direct"
GATEWAY_PLIST = Path("/Users/jameschen/Library/LaunchAgents/com.nexus.mcp.gateway.direct.plist")
GATEWAY_ENDPOINT = "http://127.0.0.1:8766"
GATEWAY_ENTRYPOINT = "scripts/ops/nexus_mcp_gateway_http.py"
GATEWAY_LEDGER = Path.home() / "Library/Application Support/Nexus/gateway-direct/ledger.jsonl"
GATEWAY_LOCK = Path.home() / "Library/Application Support/Nexus/gateway-direct/ledger.lock"
GATEWAY_ARTIFACT = Path.home() / "Library/Application Support/Nexus/gateway-direct/manager.py"
MAX_LEDGER_BYTES = 4 * 1024 * 1024
MAX_LEDGER_RECORDS = 256


class GatewayContractError(GateError):
    """Gateway-only operation rejected before an effect or after uncertainty."""


class LedgerCorruption(GatewayContractError):
    pass


def _legacy_absent_service(result: Any, args: tuple[Any, ...] | list[Any]) -> bool:
    """Recognize only the documented missing fixed Gateway service forms."""
    code = getattr(result, "returncode", result[0] if isinstance(result, tuple) else 0)
    output = str((getattr(result, "stdout", "") or "") + (getattr(result, "stderr", "") or "")).strip()
    if len(args) < 3 or args[0] != "launchctl":
        return False
    label = str(args[-1]).rsplit("/", 1)[-1]
    if args[1] == "bootout" and code == 3:
        return bool(re.fullmatch(r"Boot-out failed:\s*3:\s*No such process", output, flags=re.IGNORECASE))
    if args[1] == "print" and code == 113:
        expected = rf'Bad request\.\s*Could not find service "{re.escape(label)}" in domain for user gui:\s*{os.getuid()}\s*'
        return bool(re.fullmatch(expected, output, flags=re.IGNORECASE | re.DOTALL))
    return False


def _gateway_error(message: str, exc: BaseException | None = None) -> GatewayContractError:
    error = GatewayContractError(message)
    if exc is not None:
        error.__cause__ = exc
    return error


def _safe_store_path(path: Path, *, leaf_mode: int = 0o600, create: bool = False) -> Path:
    """Reject symlink/non-directory ancestry and unsafe writable parents."""
    path = Path(path)
    if not path.is_absolute() or ".git" in path.parts or path == Path("/"):
        raise _gateway_error("unsafe gateway store path")
    parent = path.parent
    if create:
        missing: list[Path] = []
        cursor = parent
        while not cursor.exists():
            missing.append(cursor)
            cursor = cursor.parent
        for directory in reversed(missing):
            directory.mkdir(mode=0o700)
            os.chmod(directory, 0o700)
    cursor = parent
    while True:
        try:
            info = os.lstat(cursor)
        except OSError as exc:
            raise _gateway_error("gateway store ancestry unreadable", exc) from exc
        # macOS exposes /var (and, on some hosts, /tmp) as a fixed system
        # alias.  It is not caller-controlled state; reject every other
        # symlink in the ancestry.
        system_alias = cursor in {Path("/var"), Path("/tmp")}
        if (stat.S_ISLNK(info.st_mode) and not system_alias) or (not stat.S_ISDIR(info.st_mode) and not system_alias):
            raise _gateway_error("gateway store ancestry is not a directory")
        if info.st_mode & 0o022 and not (info.st_mode & stat.S_ISVTX):
            raise _gateway_error("gateway store ancestry writable by group/other")
        if cursor.parent == cursor:
            break
        cursor = cursor.parent
    if path.exists() or path.is_symlink():
        info = os.lstat(path)
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
            raise _gateway_error("gateway store is not a regular file")
        if info.st_mode & 0o077:
            raise _gateway_error("gateway store permissions are too broad")
    return path


def _fsync_dir(path: Path) -> None:
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    except OSError as exc:
        raise _gateway_error("gateway directory durability uncertain", exc) from exc


def _atomic_gateway_write(path: Path, data: bytes, *, mode: int = 0o600) -> None:
    path = _safe_store_path(path, leaf_mode=mode, create=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    tmp = Path(tmp_name)
    try:
        os.fchmod(fd, mode)
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
        os.chmod(path, mode)
        _fsync_dir(path.parent)
    except Exception:
        with contextlib.suppress(OSError):
            tmp.unlink()
        raise


class InterProcessLock:
    """Timed, no-follow advisory lock used for every mutable gateway store."""

    def __init__(self, path: Path, *, timeout: float = 2.0):
        self.path = _safe_store_path(path, create=True)
        self.timeout = timeout
        self._fd: int | None = None

    def __enter__(self) -> "InterProcessLock":
        try:
            flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
            self._fd = os.open(self.path, flags, 0o600)
            info = os.fstat(self._fd)
            if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077:
                raise _gateway_error("gateway lock permissions invalid")
            deadline = time.monotonic() + self.timeout
            while True:
                try:
                    fcntl.flock(self._fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except (BlockingIOError, OSError) as exc:
                    if isinstance(exc, OSError) and exc.errno not in (errno.EACCES, errno.EAGAIN):
                        raise
                    if time.monotonic() >= deadline:
                        raise _gateway_error("gateway lock contention") from exc
                    time.sleep(0.01)
            return self
        except Exception:
            self._close()
            raise

    def _close(self) -> None:
        if self._fd is not None:
            with contextlib.suppress(OSError):
                fcntl.flock(self._fd, fcntl.LOCK_UN)
            with contextlib.suppress(OSError):
                os.close(self._fd)
            self._fd = None

    def __exit__(self, *_: object) -> None:
        self._close()


def _record_hash(record: Mapping[str, Any]) -> str:
    return canonical_hash({key: value for key, value in record.items() if key != "record_hash"})


class GatewayLedger:
    """Bounded JSONL state ledger with sequence, parent, self-hash, and CAS."""

    def __init__(self, path: Path | None = None, *, lock_path: Path | None = None):
        self.path = Path(path or GATEWAY_LEDGER)
        self.lock_path = Path(lock_path) if lock_path is not None else self.path.with_name(self.path.name + ".lock")

    def _scan_unlocked(self) -> list[dict[str, Any]]:
        if self.path.is_symlink():
            raise LedgerCorruption("ledger symlink rejected")
        if not self.path.exists():
            return []
        self.path = _safe_store_path(self.path)
        raw = self.path.read_bytes()
        if not raw or len(raw) > MAX_LEDGER_BYTES:
            raise LedgerCorruption("ledger missing or exceeds size bound")
        rows: list[dict[str, Any]] = []
        for line in raw.splitlines(keepends=True):
            if not line.endswith(b"\n"):
                raise LedgerCorruption("ledger is not newline terminated")
            try:
                row = json.loads(line.decode("utf-8"), object_pairs_hook=_unique_pairs)
            except (ValueError, UnicodeError) as exc:
                raise LedgerCorruption("ledger JSON malformed") from exc
            if not isinstance(row, dict) or set(row) != {"schema", "request_id", "request_hash", "state", "sequence", "parent_hash", "record_hash", "pre_effect_identity", "observed_identity"}:
                raise LedgerCorruption("ledger schema mismatch")
            if row["schema"] != "nexus.gateway.ledger.v1" or not isinstance(row["request_id"], str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}", row["request_id"]):
                raise LedgerCorruption("ledger request identity malformed")
            if not isinstance(row["request_hash"], str) or not re.fullmatch(r"[0-9a-f]{64}", row["request_hash"]):
                raise LedgerCorruption("ledger request hash malformed")
            if not isinstance(row["sequence"], int) or row["sequence"] != len(rows) + 1:
                raise LedgerCorruption("ledger sequence gap")
            if row["state"] not in {state.value for state in DeploymentState}:
                raise LedgerCorruption("ledger state unknown")
            if row["parent_hash"] != (rows[-1]["record_hash"] if rows else ""):
                raise LedgerCorruption("ledger parent mismatch")
            if row["record_hash"] != _record_hash(row):
                raise LedgerCorruption("ledger record hash mismatch")
            rows.append(row)
            if len(rows) > MAX_LEDGER_RECORDS:
                raise LedgerCorruption("ledger record limit exceeded")
        return rows

    def read(self) -> list[dict[str, Any]]:
        with InterProcessLock(self.lock_path):
            return self._scan_unlocked()

    def append(self, *, request_id: str, request_hash: str, state: DeploymentState | str,
               pre_effect_identity: Mapping[str, Any] | None = None,
               observed_identity: Mapping[str, Any] | None = None,
               expected_tail: str | None = None) -> dict[str, Any]:
        state = DeploymentState(state)
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}", request_id) or not re.fullmatch(r"[0-9a-f]{64}", request_hash):
            raise GatewayContractError("ledger request identity malformed")
        with InterProcessLock(self.lock_path):
            rows = self._scan_unlocked()
            for prior in rows:
                if prior["request_id"] == request_id:
                    if prior["request_hash"] != request_hash:
                        raise GatewayContractError("duplicate request fence conflict")
                    if prior["state"] == state.value:
                        return prior
            tail = rows[-1]["record_hash"] if rows else ""
            if expected_tail is not None and expected_tail != tail:
                raise GatewayContractError("ledger compare-and-swap conflict")
            return self._append_unlocked(rows, request_id=request_id, request_hash=request_hash,
                                         state=state, pre_effect_identity=pre_effect_identity,
                                         observed_identity=observed_identity)

    def _append_unlocked(self, rows: list[dict[str, Any]], *, request_id: str,
                         request_hash: str, state: DeploymentState | str,
                         pre_effect_identity: Mapping[str, Any] | None = None,
                         observed_identity: Mapping[str, Any] | None = None) -> dict[str, Any]:
            state = DeploymentState(state)
            tail = rows[-1]["record_hash"] if rows else ""
            row: dict[str, Any] = {
                "schema": "nexus.gateway.ledger.v1", "request_id": request_id,
                "request_hash": request_hash, "state": state.value,
                "sequence": len(rows) + 1, "parent_hash": tail,
                "record_hash": "", "pre_effect_identity": dict(pre_effect_identity or {}),
                "observed_identity": dict(observed_identity or {}),
            }
            row["record_hash"] = _record_hash(row)
            encoded = (json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n").encode()
            previous = self.path.read_bytes() if self.path.exists() else b""
            self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            if previous:
                with self.path.open("ab") as handle:
                    handle.write(encoded); handle.flush(); os.fsync(handle.fileno())
            else:
                _atomic_gateway_write(self.path, encoded)
            return row


def _unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def load_gateway_ledger(path: Path | None = None) -> list[dict[str, Any]]:
    return GatewayLedger(path).read()


def gateway_profile_matches(observed: Mapping[str, Any], expected: Any) -> bool:
    """Compare physical identity fields; absent or substituted fields fail."""
    try:
        profile = validate_profile(expected)
    except ContractError:
        return False
    required = {"root": profile.git.root, "toplevel": profile.git.toplevel,
                "remote": profile.git.remote, "head": profile.git.head,
                "tree": profile.git.tree, "entrypoint": profile.entrypoint,
                "entrypoint_sha256": profile.entrypoint_sha256}
    return all(observed.get(key) == value or (key == "entrypoint" and observed.get(key) == str(Path(profile.git.root) / GATEWAY_ENTRYPOINT)) for key, value in required.items())


def preflight_gateway(request: GatewayDeploymentRequest, *, observed: Mapping[str, Any],
                      quiescence: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Validate fresh physical evidence without performing a process effect."""
    try:
        validate_request(request)
    except (ContractError, ValueError) as exc:
        raise _gateway_error("gateway request rejected", exc) from exc
    if not gateway_profile_matches(observed, request.current):
        raise _gateway_error("current Gateway identity does not match request")
    fixed = {"label": GATEWAY_LABEL, "plist": str(GATEWAY_PLIST), "endpoint": GATEWAY_ENDPOINT}
    if any(observed.get(key) != value for key, value in fixed.items()):
        raise _gateway_error("fixed Gateway service identity mismatch")
    if "listener" in observed and observed["listener"] not in {GATEWAY_ENDPOINT, "127.0.0.1:8766"}:
        raise _gateway_error("Gateway listener mismatch")
    if "pid" in observed and (not isinstance(observed["pid"], int) or observed["pid"] <= 0):
        raise _gateway_error("Gateway PID identity invalid")
    if "services" in observed and observed["services"] != [GATEWAY_LABEL]:
        raise _gateway_error("ambiguous Gateway service ownership")
    q = quiescence or observed.get("quiescence", {})
    if q.get("disposition") not in {"drained", "held", "reconciled"}:
        raise _gateway_error("lifecycle/assist quiescence missing")
    if q.get("pending_actions") and q.get("disposition") != "reconciled":
        raise _gateway_error("pending actions require durable reconciliation")
    return {"state": DeploymentState.PREFLIGHTED.value, "request_hash": request.request_hash,
            "observed": dict(observed), "quiescence": dict(q), "effects": []}


def gateway_preflight(*args: Any, **kwargs: Any) -> dict[str, Any]:
    return preflight_gateway(*args, **kwargs)


def _gateway_plist(profile: Any, *, token_env: str = "NEXUS_MCP_GATEWAY_TOKEN") -> bytes:
    validate_profile(profile)
    root = profile.git.root
    entrypoint = profile.entrypoint if profile.entrypoint.startswith("/") else str(Path(root) / profile.entrypoint)
    payload = {
        "Label": GATEWAY_LABEL,
        "ProgramArguments": [profile.interpreter.path, entrypoint],
        "WorkingDirectory": root,
        "RunAtLoad": True,
        "KeepAlive": True,
        "StandardOutPath": "/Users/jameschen/Library/Logs/Nexus/gateway.log",
        "StandardErrorPath": "/Users/jameschen/Library/Logs/Nexus/gateway.err.log",
        "EnvironmentVariables": {"NEXUS_MCP_GATEWAY_TOKEN": f"${{{token_env}}}"},
    }
    return plistlib.dumps(payload, fmt=plistlib.FMT_XML)


def install_stable_artifact(request: GatewayDeploymentRequest, *, source_root: Path,
                            source_path: Path, artifact_path: Path | None = None) -> dict[str, Any]:
    """Publish one exact manager artifact; this is never part of reload."""
    validate_request(request)
    if request.operation not in {"install-artifact", "install_artifact"} or request.stable_artifact is None:
        raise _gateway_error("artifact installation requires explicit install-artifact request")
    artifact_path = Path(artifact_path or GATEWAY_ARTIFACT)
    if artifact_path != Path(GATEWAY_ARTIFACT):
        raise _gateway_error("stable artifact destination substitution")
    artifact = request.stable_artifact
    source_root = Path(source_root).resolve(strict=False)
    source_path = Path(source_path).resolve(strict=False)
    if source_root != Path(artifact.source_root) or source_path != Path(artifact.source_path):
        raise _gateway_error("artifact source substitution")
    if not source_path.is_file() or source_path.is_symlink():
        raise _gateway_error("artifact source is not a regular file")
    data = source_path.read_bytes()
    if hashlib.sha256(data).hexdigest() != artifact.source_blob_sha256 or hashlib.sha256(data).hexdigest() != artifact.artifact_sha256:
        raise _gateway_error("artifact bytes hash mismatch")
    destination = _safe_store_path(Path(artifact_path), create=True)
    if destination.exists():
        if destination.read_bytes() != data:
            raise _gateway_error("stable artifact predecessor conflict")
    else:
        fd, tmp_name = tempfile.mkstemp(dir=destination.parent, prefix=f".{destination.name}.")
        try:
            os.fchmod(fd, artifact.mode)
            with os.fdopen(fd, "wb") as handle:
                handle.write(data); handle.flush(); os.fsync(handle.fileno())
            os.link(tmp_name, destination)
            _fsync_dir(destination.parent)
        finally:
            with contextlib.suppress(OSError): os.unlink(tmp_name)
    return {"state": DeploymentState.VERIFIED.value, "artifact_sha256": artifact.artifact_sha256,
            "source_root": str(source_root), "request_id": request.request_id}


def _http_json(url: str, *, token: str, payload: Mapping[str, Any] | None = None, timeout: float = 2.0,
               opener: Any = urllib.request.urlopen) -> Mapping[str, Any]:
    if not url.startswith("http://127.0.0.1:") and not url.startswith("http://localhost:"):
        raise _gateway_error("Gateway postflight endpoint must be loopback")
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    request = urllib.request.Request(url, headers=headers, method="POST" if payload is not None else "GET")
    if payload is not None:
        request.data = json.dumps(payload, separators=(",", ":")).encode()
    try:
        with opener(request, timeout=timeout) as response:
            value = json.loads(response.read().decode("utf-8"))
    except (OSError, urllib.error.URLError, TimeoutError, ValueError) as exc:
        raise _gateway_error("Gateway postflight response unavailable", exc) from exc
    if not isinstance(value, Mapping):
        raise _gateway_error("Gateway postflight response malformed")
    return value


def postflight_gateway(expected: Mapping[str, Any], *, token: str, endpoint: str = GATEWAY_ENDPOINT,
                       opener: Any = urllib.request.urlopen, retries: int = 3,
                       timeout: float = 2.0, sleeper: Callable[[float], None] = time.sleep) -> PostflightIdentity:
    """Bounded authenticated health/initialize/tools-list identity proof."""
    if not token or retries < 1 or retries > 5:
        raise _gateway_error("postflight retry/token contract invalid")
    last: BaseException | None = None
    for attempt in range(retries):
        try:
            health = _http_json(endpoint + "/health", token=token, timeout=timeout, opener=opener)
            init = _http_json(endpoint + "/mcp", token=token, timeout=timeout, opener=opener,
                              payload={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
            listing = _http_json(endpoint + "/mcp", token=token, timeout=timeout, opener=opener,
                                 payload={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
            result = init.get("result", init); health_result = health.get("result", health)
            tools_result = listing.get("result", listing)
            tools = tools_result.get("tools", []) if isinstance(tools_result, Mapping) else []
            names = tuple(sorted(str(item.get("name")) for item in tools if isinstance(item, Mapping) and item.get("name")))
            manifest = hashlib.sha256(json.dumps(names, separators=(",", ":"), ensure_ascii=True).encode()).hexdigest()
            schema = hashlib.sha256(json.dumps(tools, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()
            merged = dict(health_result) if isinstance(health_result, Mapping) else {}
            if isinstance(result, Mapping):
                merged.update(result.get("serverInfo", result))
            identity = PostflightIdentity(
                server_instance=str(merged.get("server_instance") or merged.get("instance_id") or ""),
                root=str(merged.get("repo_root") or merged.get("root") or ""),
                head=str(merged.get("git_head") or merged.get("head") or ""),
                tree=str(merged.get("git_tree") or merged.get("tree") or ""),
                tool_manifest_sha256=str(merged.get("tool_manifest_revision") or manifest),
                schema_sha256=str(merged.get("full_tool_schema_hash") or schema),
                permission_sha256=str(merged.get("permission_policy_hash") or expected.get("permission_sha256", "")),
                action=str(merged.get("action") or expected.get("action", "")),
                task_id=str(merged.get("task_id") or expected.get("task_id", "")),
                lifecycle=str(merged.get("lifecycle") or merged.get("lifecycle_identity") or expected.get("lifecycle", "")),
                client_bound=True,
                required_actions=tuple(expected.get("required_actions", names)), observed_actions=names,
                token_bound=True,
            )
            for key, expected_value in expected.items():
                actual = getattr(identity, key, merged.get(key))
                if expected_value not in (None, "") and actual != expected_value:
                    raise _gateway_error(f"postflight identity mismatch: {key}")
            if identity.required_actions and not set(identity.required_actions).issubset(set(identity.observed_actions)):
                raise _gateway_error("postflight required action missing")
            return identity
        except GatewayContractError as exc:
            last = exc
            if attempt + 1 < retries:
                sleeper(min(0.25, 0.05 * (2 ** attempt)))
            continue
    raise _gateway_error("postflight remained uncertain", last)


def rollback_gateway(capture: Any, *, plist_path: Path | None = None,
                     runner: Callable[..., Any] | None = None, postflight: Callable[[], Any] | None = None) -> dict[str, Any]:
    """Restore only the captured fixed predecessor; never select a new target."""
    plist_path = Path(plist_path or GATEWAY_PLIST)
    if plist_path != Path(GATEWAY_PLIST):
        raise _gateway_error("rollback plist destination substitution")
    try:
        validate_rollback_capture(capture)
        if capture.label != GATEWAY_LABEL:
            raise _gateway_error("rollback fixed identity mismatch")
        payload = bytes.fromhex(capture.plist_bytes_hex)
        payload_hash = hashlib.sha256(payload).hexdigest()
        if payload_hash != capture.plist_bytes_sha256 or (capture.plist_sha256 and capture.plist_sha256 != payload_hash):
            raise _gateway_error("rollback plist bytes tampered")
        parsed = plistlib.loads(payload)
        if parsed.get("Label") != GATEWAY_LABEL:
            raise _gateway_error("rollback plist label drift")
        args = parsed.get("ProgramArguments")
        if not isinstance(args, list) or len(args) != 2 or not str(args[0]).endswith("/python") or not str(args[1]).endswith(GATEWAY_ENTRYPOINT):
            raise _gateway_error("rollback program arguments drift")
    except (ValueError, KeyError, TypeError, ContractError) as exc:
        raise _gateway_error("rollback predecessor malformed", exc) from exc
    run = runner or (lambda *args: subprocess.run(args, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE))
    with InterProcessLock(GATEWAY_LOCK):
        if capture.loaded:
            result = run("launchctl", "bootout", f"{UID_TARGET}/{GATEWAY_LABEL}")
            if getattr(result, "returncode", 0) not in (0, None) and not _legacy_absent_service(result, ("launchctl", "bootout", f"{UID_TARGET}/{GATEWAY_LABEL}")):
                raise _gateway_error("rollback bootout failed")
        _atomic_gateway_write(Path(plist_path), payload)
        if capture.loaded:
            result = run("launchctl", "bootstrap", UID_TARGET, str(plist_path))
            if getattr(result, "returncode", 0) not in (0, None):
                raise _gateway_error("rollback bootstrap failed")
        if postflight is not None:
            postflight()
    return {"state": DeploymentState.ROLLED_BACK.value, "loaded": bool(capture.loaded), "plist_sha256": hashlib.sha256(payload).hexdigest()}


def gateway_reload(request: GatewayDeploymentRequest, *, observed: Mapping[str, Any],
                   runner: Callable[..., Any] | None = None, plist_path: Path | None = None,
                   ledger: GatewayLedger | None = None, postflight: Callable[[], Any] | None = None) -> dict[str, Any]:
    """Gateway-only reload/adopt operation.  It cannot install a stable artifact."""
    validate_request(request)
    if request.operation not in {"reload", "gateway-reload"}:
        raise _gateway_error("gateway_reload requires reload operation")
    plist_path = Path(plist_path or GATEWAY_PLIST)
    if plist_path != Path(GATEWAY_PLIST):
        raise _gateway_error("Gateway plist destination substitution")
    preflight = preflight_gateway(request, observed=observed)
    store = ledger or GatewayLedger()
    run = runner or (lambda *args: subprocess.run(args, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE))
    with InterProcessLock(store.lock_path):
        rows = store._scan_unlocked()
        existing = next((row for row in reversed(rows) if row["request_id"] == request.request_id), None)
        if existing is not None:
            if existing["request_hash"] != request.request_hash:
                raise _gateway_error("duplicate request id with conflicting fence")
            if existing["state"] in {DeploymentState.STARTED.value, DeploymentState.UNCERTAIN_EFFECT.value}:
                raise _gateway_error("duplicate or uncertain request requires physical reconciliation")
            if existing["state"] == DeploymentState.VERIFIED.value:
                return {"state": existing["state"], "replayed": True, "request_id": request.request_id}
        # The lock is held across the STARTED record and first effect.  The
        # ledger method takes the same lock, so append directly while held.
        row = {"schema": "nexus.gateway.ledger.v1", "request_id": request.request_id, "request_hash": request.request_hash,
               "state": DeploymentState.STARTED.value, "sequence": len(rows) + 1,
               "parent_hash": rows[-1]["record_hash"] if rows else "", "record_hash": "",
               "pre_effect_identity": preflight["observed"], "observed_identity": {}}
        row["record_hash"] = _record_hash(row)
        encoded = (json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n").encode()
        if store.path.exists():
            with store.path.open("ab") as handle:
                handle.write(encoded); handle.flush(); os.fsync(handle.fileno())
        else:
            _atomic_gateway_write(store.path, encoded)
        try:
            plist_data = _gateway_plist(request.desired)
            _atomic_gateway_write(Path(plist_path), plist_data)
            result = run("launchctl", "bootout", f"{UID_TARGET}/{GATEWAY_LABEL}")
            if getattr(result, "returncode", 0) not in (0, None) and not _legacy_absent_service(result, ("launchctl", "bootout", f"{UID_TARGET}/{GATEWAY_LABEL}")):
                raise _gateway_error("Gateway bootout failed")
            result = run("launchctl", "bootstrap", UID_TARGET, str(plist_path))
            if getattr(result, "returncode", 0) not in (0, None):
                raise _gateway_error("Gateway bootstrap failed")
            if postflight is None:
                raise _gateway_error("postflight callback required before VERIFIED")
            postflight_result = postflight()
            store._append_unlocked(store._scan_unlocked(), request_id=request.request_id, request_hash=request.request_hash, state=DeploymentState.VERIFIED,
                                   pre_effect_identity=preflight["observed"], observed_identity=dict(postflight_result) if isinstance(postflight_result, Mapping) else {})
            return {"state": DeploymentState.VERIFIED.value, "request_id": request.request_id, "postflight": postflight_result}
        except Exception as exc:
            with contextlib.suppress(Exception):
                store._append_unlocked(store._scan_unlocked(), request_id=request.request_id, request_hash=request.request_hash, state=DeploymentState.UNCERTAIN_EFFECT,
                                       pre_effect_identity=preflight["observed"], observed_identity={"error": type(exc).__name__})
            raise _gateway_error("Gateway effect uncertain", exc) from exc


def manage_gateway(action: str, *, request: GatewayDeploymentRequest | Mapping[str, Any],
                   observed: Mapping[str, Any] | None = None, **kwargs: Any) -> dict[str, Any]:
    """Explicit Gateway-only dispatch; legacy ``manage`` cannot reach this path."""
    typed = validate_request(request)
    expected_operation = {
        "preflight": {"preflight", "gateway-preflight"},
        "reload": {"reload", "gateway-reload"},
        "install-artifact": {"install-artifact", "install_artifact"},
        "rollback": {"rollback", "gateway-rollback"},
    }
    if action not in expected_operation or typed.operation not in expected_operation[action]:
        raise _gateway_error("operation substitution rejected")
    if action == "preflight":
        if observed is None:
            raise _gateway_error("fresh physical Gateway evidence required")
        return preflight_gateway(typed, observed=observed)
    if action == "reload":
        if observed is None:
            raise _gateway_error("fresh physical Gateway evidence required")
        return gateway_reload(typed, observed=observed, **kwargs)
    if action == "install-artifact":
        return install_stable_artifact(typed, **kwargs)
    if action == "rollback":
        return rollback_gateway(**kwargs)
    raise _gateway_error("unsupported Gateway-only action")


if __name__ == "__main__": raise SystemExit(main())
