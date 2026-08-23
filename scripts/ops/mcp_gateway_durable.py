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
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

from nexus.contracts.gateway_deployment import (
    CURRENT_PROFILE,
    CURRENT_WRAPPER_COMMAND,
    DESIRED_PROFILE,
    GATEWAY_ACTION,
    GATEWAY_TASK_ID,
    HOST_CARD_SHA256,
    SOURCE_BASE_MERGE,
    SOURCE_BASE_TREE,
    ContractError,
    DeploymentState,
    EffectClass,
    GatewayDeploymentRequest,
    HostEffectAuthorityBundle,
    HostEffectAuthorityReceipt,
    PostflightIdentity,
    _gateway_wrapper_command,
    canonical_hash,
    select_host_effect_authority_receipt,
    validate_authority_freshness,
    validate_host_effect_authority,
    validate_host_effect_authority_bundle,
    validate_postflight_identity,
    validate_profile,
    validate_receipt_freshness,
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
    p = argparse.ArgumentParser()
    p.add_argument("action", choices=("preflight", "render", "install", "status", "reload", "uninstall", "serve-gateway", "serve-devspace",
                                       "gateway-status", "gateway-preflight", "gateway-reload", "gateway-install-artifact", "gateway-rollback"))
    p.add_argument("--launch-floor-head", dest="launch_floor_head")
    p.add_argument("--expected-head", dest="launch_floor_head", help="backward-compat alias for --launch-floor-head")
    p.add_argument("--devspace-hash"); p.add_argument("--env-file")
    p.add_argument("--devspace-root", type=Path, default=DEVSPACE_ROOT); p.add_argument("--node-path", type=Path, default=NODE_PATH)
    p.add_argument("--gateway-request", type=Path)
    p.add_argument("--gateway-evidence", type=Path)
    a = p.parse_args()
    try:
        if a.action.startswith("gateway-") and (a.env_file or a.devspace_hash or a.launch_floor_head or a.devspace_root != DEVSPACE_ROOT or a.node_path != NODE_PATH):
            p.error("Gateway-only CLI accepts only fixed request/evidence stores")
        if a.env_file: globals()["ENV_PATH"] = Path(a.env_file)
        if a.action == "serve-gateway": serve("gateway", launch_floor_head=a.launch_floor_head)
        elif a.action == "serve-devspace": serve("devspace", launch_floor_head=a.launch_floor_head, devspace_hash=a.devspace_hash, devspace_root=a.devspace_root, node_path=a.node_path)
        elif a.action.startswith("gateway-"):
            if a.gateway_request is None:
                p.error("--gateway-request is required for Gateway-only operations")
            request_path = _fixed_cli_store_path(a.gateway_request, GATEWAY_REQUEST_STORE)
            try:
                payload = json.loads(request_path.read_text(), object_pairs_hook=_unique_pairs)
            except (OSError, ValueError) as exc:
                raise GateError("gateway request file malformed") from exc
            request = GatewayDeploymentRequest.model_validate(payload)
            operation = a.action.removeprefix("gateway-")
            if operation == "install-artifact": operation = "install-artifact"
            now = _current_observation_time()
            observed = {} if operation in {"status", "gateway-status"} else collect_gateway_observation(
                request, operation=operation, observation_time=now
            )
            if a.gateway_evidence is not None:
                _fixed_cli_store_path(a.gateway_evidence, GATEWAY_EVIDENCE_STORE)
            print(json.dumps(dispatch_gateway_cli(operation, request=request, observed=observed,
                                                  observation_time=now), sort_keys=True, default=str))
        else: print(json.dumps(manage(a.action, launch_floor_head=a.launch_floor_head, devspace_hash=a.devspace_hash, devspace_root=a.devspace_root, node_path=a.node_path), sort_keys=True))
    except (GateError, subprocess.CalledProcessError) as exc: p.error(str(exc))
    return 0
GATEWAY_LABEL = "com.nexus.mcp.gateway.direct"
GATEWAY_PLIST = Path("/Users/jameschen/Library/LaunchAgents/com.nexus.mcp.gateway.direct.plist")
GATEWAY_ENDPOINT = "http://127.0.0.1:8766"
GATEWAY_ENTRYPOINT = "scripts/ops/nexus_mcp_gateway_http.py"
GATEWAY_STATE_ROOT = Path("/Users/jameschen/Library/Application Support/Nexus/gateway-direct")
GATEWAY_LEDGER = GATEWAY_STATE_ROOT / "ledger.jsonl"
GATEWAY_LOCK = GATEWAY_STATE_ROOT / "ledger.lock"
GATEWAY_ARTIFACT = GATEWAY_STATE_ROOT / "manager.py"
GATEWAY_REQUEST_STORE = GATEWAY_STATE_ROOT / "request.json"
GATEWAY_EVIDENCE_STORE = GATEWAY_STATE_ROOT / "evidence.json"
GATEWAY_HOST_AUTHORITY_STORE = Path(
    "/Users/jameschen/Library/Application Support/Nexus/gateway-direct/host-authority.json"
)
# This is deliberately not caller-selectable.  The authority mirror is a
# detached, non-DevSpace Git worktree created only by the coordinator from
# verified remote ``main``.  The worker never creates or updates it; it only
# verifies exact path, safe non-symlink ancestry, expected UID/mode, fixed
# origin, clean status, local HEAD equal to remote main, and byte-identical
# bundle path before any host observation/effect.
HOST_AUTHORITY_SOURCE_ROOT = Path("/Users/jameschen/Workspace/Nexus-new-authority-main")
HOST_AUTHORITY_REMOTE = "https://github.com/James3014/Nexus-new.git"
HOST_AUTHORITY_REF = "refs/heads/main"
HOST_AUTHORITY_UID = 501
HOST_AUTHORITY_SOURCE_PATH = (
    "tasks/github-issue-526-host-authority-and-canary-20260823/02-host-effect-authority-receipt.json"
)
MAX_LEDGER_BYTES = 64 * 1024
MAX_LEDGER_RECORDS = 256
MAX_GATEWAY_STORE_BYTES = 64 * 1024
HOST_UID = 501


class GatewayContractError(GateError):
    """Gateway-only operation rejected before an effect or after uncertainty."""


class LedgerCorruption(GatewayContractError):
    pass


def _current_observation_time() -> str:
    """Manager-owned UTC clock; pure contract validation remains clock-free."""
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _freshness_time(value: str | None) -> str:
    return value if value is not None else _current_observation_time()


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


def _safe_store_path(
    path: Path, *, leaf_mode: int = 0o600, create: bool = False, require_owner: bool = True
) -> Path:
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
    if require_owner:
        try:
            parent_info = os.lstat(parent)
        except OSError as exc:
            raise _gateway_error("gateway store parent unreadable", exc) from exc
        if (
            not stat.S_ISDIR(parent_info.st_mode)
            or parent_info.st_uid != HOST_UID
            or stat.S_IMODE(parent_info.st_mode) != 0o700
        ):
            raise _gateway_error("gateway store parent ownership/mode invalid")
    if path.exists() or path.is_symlink():
        info = os.lstat(path)
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
            raise _gateway_error("gateway store is not a regular file")
        if stat.S_IMODE(info.st_mode) != leaf_mode:
            raise _gateway_error("gateway store mode mismatch")
        if require_owner and info.st_uid != HOST_UID:
            raise _gateway_error("gateway store owner mismatch")
        if info.st_size > MAX_GATEWAY_STORE_BYTES:
            raise _gateway_error("gateway store exceeds size bound")
    return path


def _read_host_authority_store() -> tuple[bytes, HostEffectAuthorityBundle]:
    """Read the fixed canonical bundle store and preserve its exact bytes."""
    path = _safe_store_path(GATEWAY_HOST_AUTHORITY_STORE)
    if path.is_symlink() or not path.is_file():
        raise _gateway_error("canonical host authority store missing")
    parent_info = os.stat(path.parent)
    if parent_info.st_uid != HOST_UID or stat.S_IMODE(parent_info.st_mode) != 0o700:
        raise _gateway_error("canonical host authority directory ownership/mode invalid")
    info = os.stat(path)
    if info.st_uid != HOST_UID or stat.S_IMODE(info.st_mode) != 0o600:
        raise _gateway_error("canonical host authority file ownership/mode invalid")
    try:
        raw = path.read_bytes()
        if not raw or len(raw) > MAX_GATEWAY_STORE_BYTES:
            raise _gateway_error("canonical host authority store size invalid")
        payload = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_pairs)
        bundle = HostEffectAuthorityBundle.model_validate(payload)
        validate_host_effect_authority_bundle(bundle, allow_revoked=True)
    except (OSError, UnicodeError, ValueError, ContractError) as exc:
        raise _gateway_error("canonical host authority bundle invalid", exc) from exc
    return raw, bundle


def _load_host_authority_store() -> HostEffectAuthorityBundle:
    """Load only the fixed canonical host bundle, with no caller path seam."""
    return _read_host_authority_store()[1]


def _fixed_authority_command_runner(*args: Any) -> Any:
    """Execute only manager-constructed Git authority commands."""
    command = tuple(args) if args and isinstance(args[0], str) else tuple(args[0])
    root = str(HOST_AUTHORITY_SOURCE_ROOT)
    allowed = {
        ("git", "-C", root, "rev-parse", "--show-toplevel"),
        ("git", "-C", root, "remote", "get-url", "origin"),
        ("git", "-C", root, "status", "--porcelain"),
        ("git", "-C", root, "rev-parse", "HEAD"),
        ("git", "-C", root, "ls-remote", HOST_AUTHORITY_REMOTE, HOST_AUTHORITY_REF),
    }
    # The ancestry check is manager-owned and the SHA arguments come only from
    # the validated bundle and fixed remote-main observation.
    if len(command) == 7 and command[:5] == ("git", "-C", root, "merge-base", "--is-ancestor"):
        if not all(isinstance(value, str) and re.fullmatch(r"[0-9a-f]{40}", value) for value in command[5:]):
            raise _gateway_error("caller-selected authority ancestry rejected")
        return subprocess.run(command, text=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if command not in allowed and not (
        len(command) == 5
        and command[:4] == ("git", "-C", root, "show")
        and re.fullmatch(r"[0-9a-f]{40}:" + re.escape(HOST_AUTHORITY_SOURCE_PATH), command[4])
    ):
        raise _gateway_error("caller-selected authority command rejected")
    return subprocess.run(command, text=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)


def _authority_command_output(
    runner: Callable[..., Any], command: tuple[str, ...], *, preserve_bytes: bool = False
) -> bytes | str:
    """Read one output from a fixed command; the caller never supplies command data."""
    try:
        result = runner(*command)
    except TypeError:
        try:
            result = runner(command)
        except OSError as exc:
            raise _gateway_error("fixed authority command unavailable", exc) from exc
    except OSError as exc:
        raise _gateway_error("fixed authority command unavailable", exc) from exc
    if isinstance(result, tuple):
        code = result[0] if result else 0
        output = result[1] if len(result) > 1 else b""
    else:
        code = getattr(result, "returncode", 0)
        output = result if isinstance(result, (str, bytes)) else getattr(result, "stdout", b"")
    if code not in (0, None):
        raise _gateway_error(f"fixed authority command failed: {command[0]}")
    if output is None:
        output = b""
    if isinstance(output, str):
        output = output.encode("utf-8")
    if not isinstance(output, bytes):
        raise _gateway_error("fixed authority command output malformed")
    if preserve_bytes:
        return output
    try:
        return output.decode("utf-8").strip()
    except UnicodeDecodeError as exc:
        raise _gateway_error("fixed authority command output is not UTF-8", exc) from exc


def _verify_git_main_host_authority(
    local_bytes: bytes,
    local_bundle: HostEffectAuthorityBundle,
    *,
    command_runner: Callable[..., Any] | None = None,
) -> HostEffectAuthorityBundle:
    """Bind the local store to the exact bundle blob on clean remote ``main``."""
    root = HOST_AUTHORITY_SOURCE_ROOT
    if root.is_symlink() or not root.is_dir():
        raise _gateway_error("trusted authority source root invalid")
    # The mirror is a coordinator-created cache, never an implicit authority
    # path.  Reject symlinked/loosely-owned ancestry before any Git read.
    cursor = root
    while True:
        try:
            info = os.lstat(cursor)
        except OSError as exc:
            raise _gateway_error("trusted authority source ancestry unavailable", exc) from exc
        if stat.S_ISLNK(info.st_mode) or stat.S_IMODE(info.st_mode) not in {0o700, 0o755}:
            raise _gateway_error("trusted authority source ancestry unsafe")
        if cursor == root and info.st_uid != HOST_AUTHORITY_UID:
            raise _gateway_error("trusted authority source owner mismatch")
        if cursor.parent == cursor:
            break
        if cursor == Path("/"):
            break
        cursor = cursor.parent
    run = command_runner or _fixed_authority_command_runner
    root_text = str(root)
    top = _authority_command_output(run, ("git", "-C", root_text, "rev-parse", "--show-toplevel"))
    remote = _authority_command_output(run, ("git", "-C", root_text, "remote", "get-url", "origin"))
    dirty = _authority_command_output(run, ("git", "-C", root_text, "status", "--porcelain"))
    head = _authority_command_output(run, ("git", "-C", root_text, "rev-parse", "HEAD"))
    remote_line = _authority_command_output(
        run, ("git", "-C", root_text, "ls-remote", HOST_AUTHORITY_REMOTE, HOST_AUTHORITY_REF)
    )
    if top != str(root.resolve()) or remote != HOST_AUTHORITY_REMOTE or dirty != "":
        raise _gateway_error("trusted authority source is not clean/fixed")
    parts = str(remote_line).split()
    if len(parts) != 2 or parts[1] != HOST_AUTHORITY_REF or not re.fullmatch(r"[0-9a-f]{40}", parts[0]):
        raise _gateway_error("remote main SHA malformed")
    remote_sha = parts[0]
    if head != remote_sha:
        raise _gateway_error("trusted authority source HEAD differs from remote main")
    ancestor = local_bundle.current_main_sha
    if not re.fullmatch(r"[0-9a-f]{40}", ancestor):
        raise _gateway_error("bundle current main SHA malformed")
    _authority_command_output(
        run,
        ("git", "-C", root_text, "merge-base", "--is-ancestor", ancestor, remote_sha),
    )
    blob = _authority_command_output(
        run,
        ("git", "-C", root_text, "show", f"{remote_sha}:{HOST_AUTHORITY_SOURCE_PATH}"),
        preserve_bytes=True,
    )
    if not isinstance(blob, bytes) or blob != local_bytes:
        raise _gateway_error("local host authority is not byte-identical to remote main blob")
    try:
        payload = json.loads(blob.decode("utf-8"), object_pairs_hook=_unique_pairs)
        remote_bundle = HostEffectAuthorityBundle.model_validate(payload)
        validate_host_effect_authority_bundle(remote_bundle, allow_revoked=True)
    except (UnicodeError, ValueError, ContractError) as exc:
        raise _gateway_error("remote host authority bundle invalid", exc) from exc
    if remote_bundle != local_bundle:
        raise _gateway_error("remote host authority differs from local bundle")
    return remote_bundle


def _require_host_authority(
    request: GatewayDeploymentRequest, *, observation_time: str | None = None,
    authority_command_runner: Callable[..., Any] | None = None,
) -> GatewayDeploymentRequest:
    """Revalidate pure bindings and exact equality with the canonical store."""
    try:
        typed = validate_request(request)
    except ContractError as exc:
        raise _gateway_error("host authority rejected", exc) from exc
    receipt = typed.host_authority
    if receipt is None:  # defensive: validate_request already rejects this
        raise _gateway_error("host-effect authority receipt required")
    try:
        validate_receipt_freshness(receipt, now=_freshness_time(observation_time))
        local_bytes, bundle = _read_host_authority_store()
        # Select locally before touching the remote authority seam.  A
        # consistently revoked bundle/child is evidence-only and must stop
        # every operation without a Git authority read or host observation.
        select_host_effect_authority_receipt(
            bundle,
            typed,
            now=_freshness_time(observation_time),
        )
        remote_bundle = _verify_git_main_host_authority(
            local_bytes, bundle, command_runner=authority_command_runner
        )
        select_host_effect_authority_receipt(
            remote_bundle,
            typed,
            now=_freshness_time(observation_time),
        )
    except (ContractError, GatewayContractError) as exc:
        raise _gateway_error("host authority rejected", exc) from exc
    return typed


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
            if not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o600 or info.st_uid != HOST_UID:
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
        info = os.stat(self.path)
        if info.st_uid != HOST_UID or stat.S_IMODE(info.st_mode) != 0o600:
            raise LedgerCorruption("ledger ownership/mode invalid")
        raw = self.path.read_bytes()
        if not raw or len(raw) > MAX_LEDGER_BYTES:
            raise LedgerCorruption("ledger missing or exceeds size bound")
        rows: list[dict[str, Any]] = []
        last_state: dict[str, str] = {}
        fences: dict[str, str] = {}
        for line in raw.splitlines(keepends=True):
            if not line.endswith(b"\n"):
                raise LedgerCorruption("ledger is not newline terminated")
            try:
                row = json.loads(line.decode("utf-8"), object_pairs_hook=_unique_pairs)
            except (ValueError, UnicodeError) as exc:
                raise LedgerCorruption("ledger JSON malformed") from exc
            expected_keys = {
                "schema", "request_id", "request_hash", "state", "sequence", "parent_hash",
                "record_hash", "pre_effect_identity", "observed_identity", "host_receipt_hash",
                "source_base_merge", "source_base_tree", "host_card_sha256", "effect_class",
                "operation", "idempotency_fence",
            }
            if not isinstance(row, dict) or set(row) != expected_keys:
                raise LedgerCorruption("ledger schema mismatch")
            if row["schema"] != "nexus.gateway.ledger.v1" or not isinstance(row["request_id"], str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}", row["request_id"]):
                raise LedgerCorruption("ledger request identity malformed")
            if not isinstance(row["request_hash"], str) or not re.fullmatch(r"[0-9a-f]{64}", row["request_hash"]):
                raise LedgerCorruption("ledger request hash malformed")
            if any(not isinstance(row[key], str) or not row[key] for key in (
                "host_receipt_hash", "source_base_merge", "source_base_tree", "host_card_sha256",
                "effect_class", "operation", "idempotency_fence"
            )):
                raise LedgerCorruption("ledger host authority binding missing")
            for key in ("host_receipt_hash", "host_card_sha256"):
                if not re.fullmatch(r"[0-9a-f]{64}", row[key]):
                    raise LedgerCorruption("ledger host authority hash malformed")
            for key in ("source_base_merge", "source_base_tree"):
                if not re.fullmatch(r"[0-9a-f]{40}", row[key]):
                    raise LedgerCorruption("ledger source binding malformed")
            if row["source_base_merge"] != SOURCE_BASE_MERGE or row["source_base_tree"] != SOURCE_BASE_TREE:
                raise LedgerCorruption("ledger source binding drift")
            if row["host_card_sha256"] != HOST_CARD_SHA256:
                raise LedgerCorruption("ledger host Card binding drift")
            if row["effect_class"] not in {effect.value for effect in EffectClass}:
                raise LedgerCorruption("ledger effect class unknown")
            operation_effects = {
                "status": EffectClass.STATUS.value, "gateway-status": EffectClass.STATUS.value,
                "preflight": EffectClass.PREFLIGHT.value, "gateway-preflight": EffectClass.PREFLIGHT.value,
                "install": EffectClass.INSTALL_ARTIFACT.value, "install-artifact": EffectClass.INSTALL_ARTIFACT.value,
                "install_artifact": EffectClass.INSTALL_ARTIFACT.value,
                "reload": EffectClass.GATEWAY_RELOAD.value, "gateway-reload": EffectClass.GATEWAY_RELOAD.value,
                "rollback": EffectClass.GATEWAY_ROLLBACK.value, "gateway-rollback": EffectClass.GATEWAY_ROLLBACK.value,
            }
            if row["operation"] not in operation_effects:
                raise LedgerCorruption("ledger operation unknown")
            if row["effect_class"] != operation_effects[row["operation"]]:
                raise LedgerCorruption("ledger operation/effect mismatch")
            prior_fence = fences.get(row["idempotency_fence"])
            if prior_fence is not None and prior_fence != row["request_id"]:
                raise LedgerCorruption("ledger idempotency fence reused")
            fences[row["idempotency_fence"]] = row["request_id"]
            if not isinstance(row["sequence"], int) or row["sequence"] != len(rows) + 1:
                raise LedgerCorruption("ledger sequence gap")
            if row["state"] not in {state.value for state in DeploymentState}:
                raise LedgerCorruption("ledger state unknown")
            previous_state = last_state.get(row["request_id"])
            try:
                if previous_state is None:
                    if row["state"] != DeploymentState.REQUESTED.value:
                        raise LedgerCorruption("ledger request does not begin in REQUESTED")
                else:
                    from nexus.contracts.gateway_deployment import transition
                    transition(previous_state, row["state"])
            except LedgerCorruption:
                raise
            except Exception as exc:
                raise LedgerCorruption("ledger state transition invalid") from exc
            if row["parent_hash"] != (rows[-1]["record_hash"] if rows else ""):
                raise LedgerCorruption("ledger parent mismatch")
            if row["record_hash"] != _record_hash(row):
                raise LedgerCorruption("ledger record hash mismatch")
            rows.append(row)
            last_state[row["request_id"]] = row["state"]
            if len(rows) > MAX_LEDGER_RECORDS:
                raise LedgerCorruption("ledger record limit exceeded")
        return rows

    def read(self) -> list[dict[str, Any]]:
        with InterProcessLock(self.lock_path):
            return self._scan_unlocked()

    def append(self, *, request_id: str, request_hash: str, state: DeploymentState | str,
               pre_effect_identity: Mapping[str, Any] | None = None,
               observed_identity: Mapping[str, Any] | None = None,
               expected_tail: str | None = None,
               host_authority: HostEffectAuthorityReceipt | None = None,
               operation: str | None = None,
               effect_class: str | None = None,
               idempotency_fence: str | None = None) -> dict[str, Any]:
        state = DeploymentState(state)
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}", request_id) or not re.fullmatch(r"[0-9a-f]{64}", request_hash):
            raise GatewayContractError("ledger request identity malformed")
        if host_authority is None or not isinstance(host_authority, HostEffectAuthorityReceipt):
            raise GatewayContractError("ledger host authority binding required")
        validate_host_effect_authority(host_authority)
        if host_authority.request_id != request_id or operation != host_authority.operation or effect_class != host_authority.effect_class.value or idempotency_fence != host_authority.idempotency_fence:
            raise GatewayContractError("ledger host authority binding mismatch")
        with InterProcessLock(self.lock_path):
            rows = self._scan_unlocked()
            for prior in rows:
                if prior["idempotency_fence"] == idempotency_fence and prior["request_id"] != request_id:
                    raise GatewayContractError("idempotency fence conflict")
            prior_for_request = next((row for row in reversed(rows) if row["request_id"] == request_id), None)
            for prior in rows:
                if prior["request_id"] == request_id:
                    if prior["request_hash"] != request_hash:
                        raise GatewayContractError("duplicate request fence conflict")
                    if prior["state"] == state.value:
                        return prior
            if prior_for_request is None:
                if state is not DeploymentState.REQUESTED:
                    raise GatewayContractError("request must begin in REQUESTED")
            else:
                try:
                    transition = __import__("nexus.contracts.gateway_deployment", fromlist=["transition"]).transition
                    transition(prior_for_request["state"], state)
                except Exception as exc:
                    raise GatewayContractError("invalid ledger state transition") from exc
            tail = rows[-1]["record_hash"] if rows else ""
            if expected_tail is not None and expected_tail != tail:
                raise GatewayContractError("ledger compare-and-swap conflict")
            return self._append_unlocked(rows, request_id=request_id, request_hash=request_hash,
                                         state=state, pre_effect_identity=pre_effect_identity,
                                         observed_identity=observed_identity,
                                         host_authority=host_authority, operation=operation,
                                         effect_class=effect_class, idempotency_fence=idempotency_fence)

    def _append_unlocked(self, rows: list[dict[str, Any]], *, request_id: str,
                         request_hash: str, state: DeploymentState | str,
                         pre_effect_identity: Mapping[str, Any] | None = None,
                         observed_identity: Mapping[str, Any] | None = None,
                         host_authority: HostEffectAuthorityReceipt | None = None,
                         operation: str | None = None, effect_class: str | None = None,
                         idempotency_fence: str | None = None) -> dict[str, Any]:
            if host_authority is None or operation is None or effect_class is None or idempotency_fence is None:
                raise GatewayContractError("ledger host authority binding required")
            state = DeploymentState(state)
            tail = rows[-1]["record_hash"] if rows else ""
            row: dict[str, Any] = {
                "schema": "nexus.gateway.ledger.v1", "request_id": request_id,
                "request_hash": request_hash, "state": state.value,
                "sequence": len(rows) + 1, "parent_hash": tail,
                "record_hash": "", "pre_effect_identity": dict(pre_effect_identity or {}),
                "observed_identity": dict(observed_identity or {}),
                "host_receipt_hash": host_authority.receipt_hash,
                "source_base_merge": host_authority.source_base_merge,
                "source_base_tree": host_authority.source_base_tree,
                "host_card_sha256": host_authority.host_card_sha256,
                "effect_class": effect_class,
                "operation": operation,
                "idempotency_fence": idempotency_fence,
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
    required = {
        "root": profile.git.root, "toplevel": profile.git.toplevel,
        "remote": profile.git.remote, "head": profile.git.head, "tree": profile.git.tree,
        "clean": profile.git.clean, "entrypoint": profile.entrypoint,
        "entrypoint_sha256": profile.entrypoint_sha256,
        "interpreter_path": profile.interpreter.path,
        "interpreter_resolved_path": profile.interpreter.resolved_path,
        "interpreter_sha256": profile.interpreter.sha256,
        "interpreter_uid": profile.interpreter.uid, "interpreter_gid": profile.interpreter.gid,
        "interpreter_mode": profile.interpreter.mode, "trust_class": profile.trust_class,
        "repository": profile.repository.repository, "plist": profile.repository.plist,
        "stdout": profile.repository.stdout, "stderr": profile.repository.stderr,
        "endpoint": profile.repository.endpoint, "label": profile.repository.label,
    }
    # Physical adapters may expose nested interpreter/repository objects; flatten only
    # those typed fields and reject any omitted safety-critical identity.
    flat = dict(observed)
    for prefix in ("interpreter", "repository", "git"):
        nested = observed.get(prefix)
        if isinstance(nested, Mapping):
            flat.update({f"{prefix}_{key}": value for key, value in nested.items()})
    if "interpreter_path" not in flat and isinstance(observed.get("interpreter"), Mapping):
        flat["interpreter_path"] = observed["interpreter"].get("path")
    if flat.get("entrypoint") == str(Path(profile.git.root) / GATEWAY_ENTRYPOINT):
        flat["entrypoint"] = profile.entrypoint
    return all(flat.get(key) == value for key, value in required.items())


def preflight_gateway(request: GatewayDeploymentRequest, *, observed: Mapping[str, Any],
                      quiescence: Mapping[str, Any] | None = None,
                      observation_time: str | None = None,
                      authority_command_runner: Callable[..., Any] | None = None) -> dict[str, Any]:
    """Validate fresh physical evidence without performing a process effect."""
    try:
        request = _require_host_authority(
            request, observation_time=observation_time,
            authority_command_runner=authority_command_runner,
        )
        validate_authority_freshness(request.authority, now=_freshness_time(observation_time))
    except (ContractError, ValueError) as exc:
        raise _gateway_error("gateway request rejected", exc) from exc
    required_physical = {
        "plist_sha256", "plist_bytes_sha256", "plist_bytes_hex", "loaded", "pid", "server_instance",
        "source_sha256", "tool_manifest_sha256", "schema_sha256", "permission_sha256",
        "action", "task_id", "lifecycle", "stable_artifact", "rollback_predecessor", "listener", "services",
    }
    if not required_physical.issubset(observed):
        raise _gateway_error("complete fresh physical Gateway evidence required")
    if not isinstance(observed.get("loaded"), bool) or not isinstance(observed.get("pid"), int) or observed["pid"] <= 0:
        raise _gateway_error("Gateway loaded/PID identity invalid")
    for key in ("plist_sha256", "plist_bytes_sha256", "source_sha256", "tool_manifest_sha256", "schema_sha256", "permission_sha256"):
        if not isinstance(observed.get(key), str) or not re.fullmatch(r"[0-9a-f]{64}", observed[key]):
            raise _gateway_error(f"Gateway physical hash missing: {key}")
    try:
        plist_bytes = bytes.fromhex(str(observed["plist_bytes_hex"]))
    except (TypeError, ValueError) as exc:
        raise _gateway_error("Gateway plist bytes malformed", exc) from exc
    plist_digest = hashlib.sha256(plist_bytes).hexdigest()
    if plist_digest != observed["plist_sha256"] or plist_digest != observed["plist_bytes_sha256"]:
        raise _gateway_error("Gateway plist bytes hash mismatch")
    if not isinstance(observed.get("stable_artifact"), Mapping) or not isinstance(observed.get("rollback_predecessor"), Mapping):
        raise _gateway_error("stable artifact/rollback predecessor evidence missing")
    if not gateway_profile_matches(observed, request.current):
        raise _gateway_error("current Gateway identity does not match request")
    identity_bindings = {
        "plist_sha256": request.current_identity.plist_sha256,
        "plist_bytes_sha256": request.current_identity.plist_bytes_sha256,
        "pid": request.current_identity.pid,
        "server_instance": request.current_identity.server_instance,
        "root": request.current_identity.root, "head": request.current_identity.head, "tree": request.current_identity.tree,
        "source_sha256": request.current_identity.source_sha256,
        "tool_manifest_sha256": request.current_identity.tool_manifest_sha256,
        "schema_sha256": request.current_identity.schema_sha256,
        "permission_sha256": request.current_identity.permission_sha256,
        "action": request.current_identity.action, "task_id": request.current_identity.task_id,
        "lifecycle": request.current_identity.lifecycle, "loaded": request.current_identity.loaded,
    }
    if any(observed.get(key) != value for key, value in identity_bindings.items()):
        raise _gateway_error("current Gateway identity evidence substituted")
    predecessor = observed["rollback_predecessor"]
    for key in ("plist_sha256", "artifact_sha256", "source_sha256"):
        expected_value = getattr(request.rollback, key, None)
        if expected_value and predecessor.get(key) != expected_value:
            raise _gateway_error("rollback predecessor identity mismatch")
    fixed = {"label": GATEWAY_LABEL, "endpoint": GATEWAY_ENDPOINT}
    if any(observed.get(key) != value for key, value in fixed.items()) or observed.get("plist") not in {str(GATEWAY_PLIST), request.current.repository.plist}:
        raise _gateway_error("fixed Gateway service identity mismatch")
    if observed["listener"] not in {GATEWAY_ENDPOINT, "127.0.0.1:8766"}:
        raise _gateway_error("Gateway listener mismatch")
    if observed["services"] != [GATEWAY_LABEL]:
        raise _gateway_error("ambiguous Gateway service ownership")
    q = quiescence or observed.get("quiescence", {})
    if q.get("disposition") not in {"drained", "held", "reconciled"} or not q.get("lifecycle_state") or not q.get("assist_state") or not q.get("evidence_sha256") or not q.get("reacquisition_receipt"):
        raise _gateway_error("lifecycle/assist quiescence missing")
    if q.get("pending_actions") and q.get("disposition") != "reconciled":
        raise _gateway_error("pending actions require durable reconciliation")
    return {"state": DeploymentState.PREFLIGHTED.value, "request_hash": request.request_hash,
            "observed": dict(observed), "quiescence": dict(q), "effects": []}


def gateway_preflight(*args: Any, **kwargs: Any) -> dict[str, Any]:
    return preflight_gateway(*args, **kwargs)


def _gateway_plist(profile: Any) -> bytes:
    validate_profile(profile)
    root = profile.git.root
    entrypoint = profile.entrypoint if profile.entrypoint.startswith("/") else str(Path(root) / profile.entrypoint)
    payload = {
        "Label": GATEWAY_LABEL,
        "ProgramArguments": ["/bin/zsh", "-c", _gateway_wrapper_command(root, entrypoint)],
        "WorkingDirectory": root,
        "RunAtLoad": True,
        "KeepAlive": True,
        "StandardOutPath": "/Users/jameschen/Library/Logs/Nexus/gateway.log",
        "StandardErrorPath": "/Users/jameschen/Library/Logs/Nexus/gateway.err.log",
    }
    return plistlib.dumps(payload, fmt=plistlib.FMT_XML)


def build_artifact_observation_commands(source_root: Path, source_path: Path) -> tuple[tuple[str, ...], ...]:
    """Return the fixed, manager-owned Git/file observation command set."""
    root = str(source_root)
    relative = os.path.relpath(source_path, source_root)
    if relative.startswith("../") or relative == ".." or os.path.isabs(relative):
        raise _gateway_error("artifact source outside clean root")
    return (
        ("git", "-C", root, "rev-parse", "--show-toplevel"),
        ("git", "-C", root, "remote", "get-url", "origin"),
        ("git", "-C", root, "rev-parse", "HEAD"),
        ("git", "-C", root, "rev-parse", "HEAD^{tree}"),
        ("git", "-C", root, "status", "--porcelain"),
        ("git", "-C", root, "ls-files", "--full-name", "--error-unmatch", "--", relative),
        ("git", "-C", root, "hash-object", "--", relative),
        ("shasum", "-a", "256", str(source_path)),
    )


def _command_output(runner: Callable[..., Any], command: tuple[str, ...]) -> str:
    """Run one fixed observation command and return stdout only."""
    try:
        result = runner(*command)
    except TypeError:
        result = runner(command)
    if isinstance(result, str):
        return result.strip()
    code = getattr(result, "returncode", 0)
    if code not in (0, None):
        raise _gateway_error(f"fixed observation command failed: {command[0]}")
    return str(getattr(result, "stdout", "") or "").strip()


def observe_artifact_source(source_root: Path, source_path: Path,
                            *, command_runner: Callable[..., Any] | None = None) -> dict[str, Any]:
    """Collect Git/file truth; callers can inject only command results."""
    raw_root, raw_path = Path(source_root), Path(source_path)
    if raw_root.is_symlink() or raw_path.is_symlink():
        raise _gateway_error("artifact source/root symlink rejected")
    source_root = raw_root.resolve(strict=False)
    source_path = raw_path.resolve(strict=False)
    try:
        relative = source_path.relative_to(source_root)
    except ValueError as exc:
        raise _gateway_error("artifact source outside clean root", exc) from exc
    if not source_path.is_file() or source_path.is_symlink():
        raise _gateway_error("artifact source is not a regular file")
    run = command_runner or (lambda *args: subprocess.run(args, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE))
    commands = build_artifact_observation_commands(source_root, source_path)
    values = [_command_output(run, command) for command in commands]
    top, remote, head, tree, status, tracked, git_blob, sha_line = values
    try:
        digest = sha_line.split()[0]
        info = source_path.stat()
    except (IndexError, OSError) as exc:
        raise _gateway_error("fixed file observation failed", exc) from exc
    if not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise _gateway_error("fixed bytes hash observation malformed")
    if not re.fullmatch(r"[0-9a-f]{40}", git_blob):
        raise _gateway_error("fixed Git blob observation malformed")
    if tracked != str(relative) or not top or not remote or not head or not tree:
        raise _gateway_error("fixed Git source identity observation incomplete")
    if hashlib.sha256(source_path.read_bytes()).hexdigest() != digest:
        raise _gateway_error("fixed bytes hash observation disagrees")
    return {
        "root": str(source_root), "toplevel": top, "remote": remote,
        "head": head, "tree": tree, "clean": status == "", "path": str(source_path),
        "relative_path": str(relative), "tracked_path": tracked,
        "git_blob_sha1": git_blob, "blob_sha256": digest, "bytes_sha256": digest,
        "uid": info.st_uid, "mode": stat.S_IMODE(info.st_mode),
    }


def _fixed_git_command_runner(*args: Any) -> Any:
    """Run only the command tuples constructed by the manager's fixed observer."""
    command = tuple(args) if args and isinstance(args[0], str) else tuple(args[0])
    return subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)


def install_stable_artifact(request: GatewayDeploymentRequest, *, source_root: Path,
                            source_path: Path, artifact_path: Path | None = None,
                            command_runner: Callable[..., Any] | None = None,
                            observation_time: str | None = None,
                            authority_command_runner: Callable[..., Any] | None = None) -> dict[str, Any]:
    """Publish one exact manager artifact; this is never part of reload."""
    request = _require_host_authority(
        request, observation_time=observation_time,
        authority_command_runner=authority_command_runner,
    )
    try:
        validate_authority_freshness(request.authority, now=_freshness_time(observation_time))
    except ContractError as exc:
        raise _gateway_error("artifact source authority freshness rejected", exc) from exc
    if request.operation not in {"install", "install-artifact", "install_artifact"} or request.stable_artifact is None:
        raise _gateway_error("artifact installation requires explicit install-artifact request")
    artifact_path = Path(artifact_path or GATEWAY_ARTIFACT)
    if artifact_path != Path(GATEWAY_ARTIFACT):
        raise _gateway_error("stable artifact destination substitution")
    artifact = request.stable_artifact
    raw_root, raw_path = Path(source_root), Path(source_path)
    if raw_root.is_symlink() or raw_path.is_symlink():
        raise _gateway_error("artifact source/root symlink rejected")
    source_root = raw_root.resolve(strict=False)
    source_path = raw_path.resolve(strict=False)
    if source_root != Path(artifact.source_root) or source_path != Path(artifact.source_path):
        raise _gateway_error("artifact source substitution")
    try:
        source_path.relative_to(source_root)
    except ValueError as exc:
        raise _gateway_error("artifact source outside clean root", exc) from exc
    if not source_path.is_file() or source_path.is_symlink():
        raise _gateway_error("artifact source is not a regular file")
    data = source_path.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    if digest != artifact.source_blob_sha256 or digest != artifact.artifact_sha256:
        raise _gateway_error("artifact bytes hash mismatch")
    physical = observe_artifact_source(source_root, source_path, command_runner=command_runner)
    expected_physical = {
        "root": str(source_root), "toplevel": str(source_root), "remote": "https://github.com/James3014/Nexus-new.git",
        "head": artifact.source_head, "tree": artifact.source_tree, "clean": True,
        "path": str(source_path), "blob_sha256": artifact.source_blob_sha256,
    }
    if any(physical.get(key) != value for key, value in expected_physical.items()):
        raise _gateway_error("stable artifact source identity mismatch")
    info = source_path.stat()
    if info.st_uid != artifact.uid or stat.S_IMODE(info.st_mode) != artifact.mode:
        raise _gateway_error("stable artifact source ownership/mode mismatch")
    if artifact.predecessor_sha256 and Path(artifact_path or GATEWAY_ARTIFACT).exists():
        predecessor = hashlib.sha256(Path(artifact_path or GATEWAY_ARTIFACT).read_bytes()).hexdigest()
        if predecessor != artifact.predecessor_sha256:
            raise _gateway_error("stable artifact predecessor mismatch")
    destination = _safe_store_path(Path(artifact_path), leaf_mode=artifact.mode, create=True)
    if destination.exists():
        if hashlib.sha256(destination.read_bytes()).hexdigest() != artifact.predecessor_sha256:
            raise _gateway_error("stable artifact predecessor conflict")
        _atomic_gateway_write(destination, data, mode=artifact.mode)
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


def _profile_for_expected(expected: Mapping[str, Any]) -> Any:
    """Resolve only one of the two frozen profiles; callers cannot choose another."""
    for profile in (DESIRED_PROFILE, CURRENT_PROFILE):
        if (expected.get("root") in (None, "", profile.git.root)
                and expected.get("head") in (None, "", profile.git.head)
                and expected.get("tree") in (None, "", profile.git.tree)):
            return profile
    raise _gateway_error("postflight expected profile substitution")


def _canonical_alias(mapping: Mapping[str, Any], canonical: str, aliases: tuple[str, ...]) -> Any:
    """Resolve camel/snake aliases, rejecting conflicting physical values."""
    values = [mapping[key] for key in (canonical, *aliases) if key in mapping]
    if not values or any(not isinstance(value, str) or not value for value in values) or any(value != values[0] for value in values[1:]):
        raise _gateway_error(f"postflight alias conflict: {canonical}")
    return values[0]


def _postflight_root_is_safe(root: Path) -> bool:
    """Require the fixed profile root to be a real, owner-controlled directory."""
    try:
        if not root.is_absolute() or root.is_symlink() or not root.is_dir():
            return False
        if root.resolve(strict=True) != root:
            return False
        info = os.lstat(root)
    except OSError:
        return False
    return (
        stat.S_ISDIR(info.st_mode)
        and info.st_uid == HOST_UID
        and stat.S_IMODE(info.st_mode) & 0o022 == 0
    )


def _fixed_postflight_git_command_runner(*args: Any) -> Any:
    """Execute only the manager-owned postflight Git identity commands."""
    command = tuple(args) if args and isinstance(args[0], str) else tuple(args[0])
    roots = {CURRENT_PROFILE.git.root, DESIRED_PROFILE.git.root}
    suffixes = {
        ("rev-parse", "--show-toplevel"),
        ("remote", "get-url", "origin"),
        ("status", "--porcelain"),
        ("rev-parse", "HEAD"),
        ("rev-parse", "HEAD^{tree}"),
    }
    if (
        len(command) < 5
        or command[:2] != ("git", "-C")
        or command[2] not in roots
        or command[3:] not in suffixes
    ):
        raise _gateway_error("caller-selected postflight Git command rejected")
    return subprocess.run(
        command,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def _observe_postflight_git(
    profile: Any,
    *,
    command_runner: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    """Reread exact local Git truth for one already-resolved frozen profile."""
    validate_profile(profile)
    root = Path(profile.git.root)
    if not _postflight_root_is_safe(root):
        raise _gateway_error("postflight Git root unsafe or unavailable")
    commands = (
        ("git", "-C", str(root), "rev-parse", "--show-toplevel"),
        ("git", "-C", str(root), "remote", "get-url", "origin"),
        ("git", "-C", str(root), "status", "--porcelain"),
        ("git", "-C", str(root), "rev-parse", "HEAD"),
        ("git", "-C", str(root), "rev-parse", "HEAD^{tree}"),
    )
    run = command_runner or _fixed_postflight_git_command_runner
    top, remote, status_output, head, tree = (
        _command_output(run, command) for command in commands
    )
    observed = {
        "root": str(root),
        "toplevel": top,
        "remote": remote,
        "clean": status_output == "",
        "head": head,
        "tree": tree,
    }
    expected = {
        "root": profile.git.root,
        "toplevel": profile.git.toplevel,
        "remote": profile.git.remote,
        "clean": profile.git.clean,
        "head": profile.git.head,
        "tree": profile.git.tree,
    }
    if observed != expected:
        raise _gateway_error("postflight local Git identity mismatch")
    return observed


_GATEWAY_PROTOCOL_ALIASES = {
    "server_instance": ("serverInstanceId", "server_instance_id", "instance_id"),
    "tool_manifest_sha256": ("toolManifestRevision", "tool_manifest_revision"),
    "schema_sha256": ("fullToolSchemaHash", "full_tool_schema_hash"),
    "permission_sha256": ("permissionPolicyHash", "permission_policy_hash"),
    "lifecycle": ("lifecycleRevision", "lifecycle_revision"),
}


def _normalize_gateway_identity_surfaces(
    health: Mapping[str, Any],
    *,
    profile: Any,
    git: Mapping[str, Any],
    server_info: Mapping[str, Any] | None = None,
) -> dict[str, str]:
    """Normalize physical health/initialize fields against fixed local Git."""
    normalized: dict[str, str] = {}
    for key, aliases in _GATEWAY_PROTOCOL_ALIASES.items():
        health_value = _canonical_alias(health, key, aliases)
        if server_info is not None:
            initialize_value = _canonical_alias(server_info, key, aliases)
            if health_value != initialize_value:
                raise _gateway_error(f"health/initialize identity disagreement: {key}")
        normalized[key] = health_value

    root = _canonical_alias(health, "root", ("repo_root",))
    head = _canonical_alias(health, "head", ("git_head",))
    local_root = git.get("root")
    local_head = git.get("head")
    local_tree = git.get("tree")
    if (
        root != profile.git.root
        or head != profile.git.head
        or local_root != profile.git.root
        or local_head != profile.git.head
        or local_tree != profile.git.tree
    ):
        raise _gateway_error("health/local Git identity disagreement")
    if "tree" in health or "git_tree" in health:
        if _canonical_alias(health, "tree", ("git_tree",)) != local_tree:
            raise _gateway_error("health/local Git tree disagreement")
    normalized.update(root=root, head=head, tree=str(local_tree))
    return normalized


def postflight_gateway(expected: Mapping[str, Any], *, token: str, endpoint: str = GATEWAY_ENDPOINT,
                       opener: Any = urllib.request.urlopen, retries: int = 3,
                       timeout: float = 2.0, sleeper: Callable[[float], None] = time.sleep,
                       git_command_runner: Callable[..., Any] | None = None) -> PostflightIdentity:
    """Bounded authenticated health/initialize/tools-list identity proof."""
    if not token or retries < 1 or retries > 5:
        raise _gateway_error("postflight retry/token contract invalid")
    last: BaseException | None = None
    for attempt in range(retries):
        try:
            authenticated_methods: set[str] = set()
            health = _http_json(endpoint + "/health", token=token, timeout=timeout, opener=opener)
            init = _http_json(endpoint + "/mcp", token=token, timeout=timeout, opener=opener,
                              payload={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
            authenticated_methods.add("initialize")
            listing = _http_json(endpoint + "/mcp", token=token, timeout=timeout, opener=opener,
                                 payload={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
            authenticated_methods.add("tools/list")
            result = init.get("result", init); health_result = health.get("result", health)
            tools_result = listing.get("result", listing)
            if not isinstance(health_result, Mapping) or not isinstance(result, Mapping) or not isinstance(tools_result, Mapping):
                raise _gateway_error("postflight response missing typed result")
            tools = tools_result.get("tools")
            if not isinstance(tools, list) or not tools or any(not isinstance(item, Mapping) or not isinstance(item.get("name"), str) or not item.get("name") for item in tools):
                raise _gateway_error("postflight tool manifest missing")
            names = tuple(sorted(item["name"] for item in tools))
            manifest = hashlib.sha256(json.dumps(names, separators=(",", ":"), ensure_ascii=True).encode()).hexdigest()
            schema = hashlib.sha256(json.dumps(tools, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()
            server_info = result.get("serverInfo")
            if not isinstance(server_info, Mapping):
                raise _gateway_error("initialize identity missing")
            profile = _profile_for_expected(expected)
            git_identity = _observe_postflight_git(
                profile,
                command_runner=git_command_runner,
            )
            merged = _normalize_gateway_identity_surfaces(
                health_result,
                profile=profile,
                git=git_identity,
                server_info=server_info,
            )
            declared_manifest = merged["tool_manifest_sha256"]
            declared_schema = merged["schema_sha256"]
            if declared_manifest != manifest or declared_schema != schema:
                raise _gateway_error("postflight manifest/schema recomputation mismatch")
            required = tuple(expected.get("required_actions", ()))
            previous = expected.get("previous_server_instance")
            if previous and merged.get("server_instance") == previous:
                raise _gateway_error("postflight server instance did not change")
            identity = PostflightIdentity(
                server_instance=str(merged["server_instance"]),
                root=str(merged["root"]),
                head=str(merged["head"]),
                tree=str(merged["tree"]),
                tool_manifest_sha256=str(declared_manifest or ""),
                schema_sha256=str(declared_schema or ""),
                permission_sha256=str(merged["permission_sha256"]),
                action=GATEWAY_ACTION,
                task_id=GATEWAY_TASK_ID,
                lifecycle=str(merged["lifecycle"]),
                client_bound="initialize" in authenticated_methods,
                required_actions=required,
                observed_actions=names,
                token_bound=bool(token) and authenticated_methods == {"initialize", "tools/list"},
            )
            validate_postflight_identity(identity, profile)
            for key, expected_value in expected.items():
                if key == "previous_server_instance":
                    continue
                if key in {"required_actions", "observed_actions"}:
                    expected_value = tuple(expected_value)
                actual = getattr(identity, key, merged.get(key))
                if expected_value not in (None, "") and actual != expected_value:
                    raise _gateway_error(f"postflight identity mismatch: {key}")
            return identity
        except (GatewayContractError, ContractError) as exc:
            last = exc
            if attempt + 1 < retries:
                sleeper(min(0.25, 0.05 * (2 ** attempt)))
            continue
    raise _gateway_error("postflight remained uncertain", last)


def rollback_gateway(request: GatewayDeploymentRequest, *, plist_path: Path | None = None,
                     runner: Callable[..., Any] | None = None,
                     predecessor_observer: Mapping[str, Any] | None = None,
                     opener: Any = urllib.request.urlopen,
                     token_loader: Callable[[], str] | None = None,
                     sleeper: Callable[[float], None] = time.sleep,
                     observation_time: str | None = None,
                     authority_command_runner: Callable[..., Any] | None = None) -> dict[str, Any]:
    """Restore one request-bound predecessor after mandatory physical proof."""
    plist_path = Path(plist_path or GATEWAY_PLIST)
    if plist_path != Path(GATEWAY_PLIST):
        raise _gateway_error("rollback plist destination substitution")
    try:
        request = _require_host_authority(
            request, observation_time=observation_time,
            authority_command_runner=authority_command_runner,
        )
        validate_authority_freshness(request.authority, now=_freshness_time(observation_time))
    except ContractError as exc:
        raise _gateway_error("rollback authority freshness rejected", exc) from exc
    try:
        if request.operation not in {"rollback", "gateway-rollback"}:
            raise _gateway_error("rollback requires rollback operation")
        capture = request.rollback
        if predecessor_observer is None:
            raise _gateway_error("fresh rollback predecessor observer required")
        validate_rollback_capture(capture)
        if capture.label != GATEWAY_LABEL:
            raise _gateway_error("rollback fixed identity mismatch")
        if capture.loaded and not capture.server_instance:
            raise _gateway_error("loaded rollback predecessor server identity missing")
        payload = bytes.fromhex(capture.plist_bytes_hex)
        payload_hash = hashlib.sha256(payload).hexdigest()
        if payload_hash != capture.plist_bytes_sha256 or (capture.plist_sha256 and capture.plist_sha256 != payload_hash):
            raise _gateway_error("rollback plist bytes tampered")
        parsed = plistlib.loads(payload)
        if parsed.get("Label") != GATEWAY_LABEL:
            raise _gateway_error("rollback plist label drift")
        args = parsed.get("ProgramArguments")
        if not isinstance(args, list):
            raise _gateway_error("rollback program arguments drift")
        wrapper = len(args) == 3 and args[:2] == ["/bin/zsh", "-c"]
        if wrapper:
            if args[2] != CURRENT_WRAPPER_COMMAND or payload_hash != "082c7786f9b7254949a6fdb38d905414a78c1b1979aabf7f434dd7019c09e100":
                raise _gateway_error("rollback wrapper command drift")
        elif args != ["/Users/jameschen/Workspace/Nexus-new/.venv/bin/python", "/Users/jameschen/Workspace/.devspace-chatgpt/worktrees/Nexus-new-482a79fe/scripts/ops/nexus_mcp_gateway_http.py"]:
            raise _gateway_error("rollback program arguments drift")
        if parsed.get("WorkingDirectory") != capture.root or parsed.get("StandardOutPath") != "/Users/jameschen/Library/Logs/Nexus/gateway.log" or parsed.get("StandardErrorPath") != "/Users/jameschen/Library/Logs/Nexus/gateway.err.log":
            raise _gateway_error("rollback root/log identity drift")
        env = parsed.get("EnvironmentVariables")
        if wrapper and env not in (None, {}):
            raise _gateway_error("rollback wrapper environment drift")
        if not wrapper and env != {"NEXUS_MCP_GATEWAY_TOKEN": "${NEXUS_MCP_GATEWAY_TOKEN}"}:
            raise _gateway_error("rollback environment drift")
        if capture.root != "/Users/jameschen/Workspace/.devspace-chatgpt/worktrees/Nexus-new-482a79fe":
            raise _gateway_error("rollback source root drift")
        required_observer = ("plist_sha256", "plist_bytes_sha256", "artifact_sha256", "source_sha256",
                             "source_root", "source_head", "source_tree", "loaded")
        if any(key not in predecessor_observer for key in required_observer):
            raise _gateway_error("rollback predecessor observer incomplete")
        for key in required_observer:
            expected = getattr(capture, key, None)
            if predecessor_observer.get(key) != expected:
                raise _gateway_error("rollback predecessor physical identity mismatch")
        if capture.loaded:
            if predecessor_observer.get("server_instance") != capture.server_instance or not isinstance(predecessor_observer.get("pid"), int) or predecessor_observer["pid"] <= 0:
                raise _gateway_error("loaded rollback predecessor service identity mismatch")
        if not capture.loaded:
            if predecessor_observer.get("pid") not in (None, 0) or predecessor_observer.get("server_instance") not in (None, ""):
                raise _gateway_error("unloaded rollback predecessor is not absent")
            if predecessor_observer.get("listener") not in (None, "") or predecessor_observer.get("service_loaded") not in (None, False):
                raise _gateway_error("unloaded rollback predecessor has physical service")
    except (ValueError, KeyError, TypeError, ContractError) as exc:
        raise _gateway_error("rollback predecessor malformed", exc) from exc
    run = runner or (lambda *args: subprocess.run(args, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE))
    rollback_token: str | None = None
    if capture.loaded:
        loader = token_loader or (lambda: read_secret_env().get("NEXUS_MCP_GATEWAY_TOKEN", ""))
        try:
            rollback_token = loader()
        except Exception as exc:
            raise _gateway_error("rollback authenticated postflight unavailable", exc) from exc
        if not rollback_token:
            raise _gateway_error("rollback authenticated postflight token missing")
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
        if capture.loaded:
            expected = {
                "root": capture.root, "head": capture.source_head, "tree": capture.source_tree,
                "server_instance": capture.server_instance,
                "required_actions": tuple(request.postflight.required_actions),
            }
            observed = postflight_gateway(expected, token=rollback_token or "", endpoint=GATEWAY_ENDPOINT,
                                          opener=opener, sleeper=sleeper)
            if capture.server_instance and observed.server_instance != capture.server_instance:
                raise _gateway_error("rollback server identity mismatch")
    return {"state": DeploymentState.ROLLED_BACK.value, "loaded": bool(capture.loaded), "plist_sha256": hashlib.sha256(payload).hexdigest()}


def gateway_reload(request: GatewayDeploymentRequest, *, observed: Mapping[str, Any],
                   runner: Callable[..., Any] | None = None, plist_path: Path | None = None,
                   ledger: GatewayLedger | None = None,
                   opener: Any = urllib.request.urlopen,
                   token_loader: Callable[[], str] | None = None,
                   sleeper: Callable[[float], None] = time.sleep,
                   observation_time: str | None = None,
                   authority_command_runner: Callable[..., Any] | None = None) -> dict[str, Any]:
    """Gateway-only reload/adopt operation.  It cannot install a stable artifact."""
    request = _require_host_authority(
        request, observation_time=observation_time,
        authority_command_runner=authority_command_runner,
    )
    try:
        validate_authority_freshness(request.authority, now=_freshness_time(observation_time))
    except ContractError as exc:
        raise _gateway_error("Gateway source authority freshness rejected", exc) from exc
    if request.operation not in {"reload", "gateway-reload"}:
        raise _gateway_error("gateway_reload requires reload operation")
    plist_path = Path(plist_path or GATEWAY_PLIST)
    if plist_path != Path(GATEWAY_PLIST):
        raise _gateway_error("Gateway plist destination substitution")
    preflight = preflight_gateway(
        request, observed=observed, observation_time=observation_time,
        authority_command_runner=authority_command_runner,
    )
    store = ledger or GatewayLedger()
    run = runner or (lambda *args: subprocess.run(args, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE))
    loader = token_loader or (lambda: read_secret_env().get("NEXUS_MCP_GATEWAY_TOKEN", ""))
    try:
        token = loader()
    except Exception as exc:
        raise _gateway_error("Gateway postflight token unavailable", exc) from exc
    if not token:
        raise _gateway_error("Gateway postflight token missing")
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
        # Persist the legal lifecycle chain while this same lock remains held.
        def append_state(state: DeploymentState, observed_identity: Mapping[str, Any] | None = None) -> dict[str, Any]:
            current_rows = store._scan_unlocked()
            prior = next((item for item in reversed(current_rows) if item["request_id"] == request.request_id), None)
            if prior is not None:
                from nexus.contracts.gateway_deployment import transition
                transition(prior["state"], state)
            row = store._append_unlocked(current_rows, request_id=request.request_id, request_hash=request.request_hash,
                                          state=state, pre_effect_identity=preflight["observed"],
                                          observed_identity=observed_identity or {},
                                          host_authority=request.host_authority,
                                          operation=request.operation,
                                          effect_class=request.effect_class.value,
                                          idempotency_fence=request.idempotency_fence)
            return row
        append_state(DeploymentState.REQUESTED)
        append_state(DeploymentState.PREFLIGHTED)
        append_state(DeploymentState.STARTED)
        try:
            plist_data = _gateway_plist(request.desired)
            _atomic_gateway_write(Path(plist_path), plist_data)
            result = run("launchctl", "bootout", f"{UID_TARGET}/{GATEWAY_LABEL}")
            if getattr(result, "returncode", 0) not in (0, None) and not _legacy_absent_service(result, ("launchctl", "bootout", f"{UID_TARGET}/{GATEWAY_LABEL}")):
                raise _gateway_error("Gateway bootout failed")
            result = run("launchctl", "bootstrap", UID_TARGET, str(plist_path))
            if getattr(result, "returncode", 0) not in (0, None):
                raise _gateway_error("Gateway bootstrap failed")
            expected = request.postflight.model_dump()
            expected["previous_server_instance"] = request.current_identity.server_instance
            postflight_result = postflight_gateway(expected, token=token, endpoint=GATEWAY_ENDPOINT,
                                                   opener=opener, sleeper=sleeper)
            validate_postflight_identity(postflight_result, request.desired)
            previous = request.current_identity.server_instance
            if previous and postflight_result.server_instance == previous:
                raise _gateway_error("postflight server instance was not replaced")
            append_state(DeploymentState.SERVICE_OBSERVED, postflight_result.model_dump())
            append_state(DeploymentState.IDENTITY_VERIFIED, postflight_result.model_dump())
            append_state(DeploymentState.CLIENT_BOUND, postflight_result.model_dump())
            append_state(DeploymentState.VERIFIED, postflight_result.model_dump())
            return {"state": DeploymentState.VERIFIED.value, "request_id": request.request_id, "postflight": postflight_result}
        except Exception as exc:
            with contextlib.suppress(Exception):
                current_rows = store._scan_unlocked()
                prior = next((item for item in reversed(current_rows) if item["request_id"] == request.request_id), None)
                if prior is not None and prior["state"] not in {DeploymentState.UNCERTAIN_EFFECT.value, DeploymentState.VERIFIED.value}:
                    store._append_unlocked(current_rows, request_id=request.request_id, request_hash=request.request_hash, state=DeploymentState.UNCERTAIN_EFFECT,
                                           pre_effect_identity=preflight["observed"], observed_identity={"error": type(exc).__name__},
                                           host_authority=request.host_authority,
                                           operation=request.operation,
                                           effect_class=request.effect_class.value,
                                           idempotency_fence=request.idempotency_fence)
            raise _gateway_error("Gateway effect uncertain", exc) from exc


def gateway_status(
    request: GatewayDeploymentRequest,
    *,
    runner: Callable[..., Any] | None = None,
    observation_time: str | None = None,
    authority_command_runner: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    """Read status for the fixed Gateway service under a STATUS receipt only."""
    request = _require_host_authority(
        request, observation_time=observation_time,
        authority_command_runner=authority_command_runner,
    )
    if request.operation not in {"status", "gateway-status"} or request.effect_class is not EffectClass.STATUS:
        raise _gateway_error("Gateway status requires STATUS operation")
    observed = _launchctl_observation(runner=runner)
    return {"state": "SERVICE_OBSERVED", "operation": "status", "service": GATEWAY_LABEL, **observed}


def _validate_gateway_action_pair(
    action: str, request: GatewayDeploymentRequest | Mapping[str, Any]
) -> GatewayDeploymentRequest:
    """Parse and validate the typed request before any physical authority read."""
    try:
        typed = validate_request(request)
    except ContractError as exc:
        raise _gateway_error("Gateway request rejected", exc) from exc
    expected_operation = {
        "status": {"status", "gateway-status"},
        "preflight": {"preflight", "gateway-preflight"},
        "reload": {"reload", "gateway-reload"},
        "install": {"install", "install-artifact", "install_artifact"},
        "install-artifact": {"install", "install-artifact", "install_artifact"},
        "rollback": {"rollback", "gateway-rollback"},
    }
    if action not in expected_operation:
        raise _gateway_error("unsupported Gateway-only action")
    if typed.operation not in expected_operation[action]:
        raise _gateway_error("operation substitution rejected")
    return typed


def manage_gateway(action: str, *, request: GatewayDeploymentRequest | Mapping[str, Any],
                   observed: Mapping[str, Any] | None = None, **kwargs: Any) -> dict[str, Any]:
    """Explicit Gateway-only dispatch; legacy ``manage`` cannot reach this path."""
    # Pairing is deliberately checked while the request is still pure.  A
    # cross-operation request must not cause a canonical store, remote-main,
    # source, or local-Git read merely to discover the mismatch.
    parsed = _validate_gateway_action_pair(action, request)
    typed = _require_host_authority(
        parsed,
        observation_time=kwargs.get("observation_time"),
        authority_command_runner=kwargs.get("authority_command_runner"),
    )
    observation_time = kwargs.get("observation_time")
    try:
        validate_authority_freshness(typed.authority, now=_freshness_time(observation_time))
    except ContractError as exc:
        raise _gateway_error("Gateway authority freshness rejected", exc) from exc
    if action == "status":
        return gateway_status(
            typed, runner=kwargs.get("runner"), observation_time=observation_time,
            authority_command_runner=kwargs.get("authority_command_runner"),
        )
    if action == "preflight":
        if observed is None:
            raise _gateway_error("fresh physical Gateway evidence required")
        return preflight_gateway(
            typed, observed=observed, observation_time=observation_time,
            authority_command_runner=kwargs.get("authority_command_runner"),
        )
    if action == "reload":
        if observed is None:
            raise _gateway_error("fresh physical Gateway evidence required")
        return gateway_reload(typed, observed=observed, **kwargs)
    if action in {"install", "install-artifact"}:
        return install_stable_artifact(typed, **kwargs)
    if action == "rollback":
        return rollback_gateway(typed, **kwargs)
    raise _gateway_error("unsupported Gateway-only action")


def _fixed_cli_store_path(value: Path, expected: Path) -> Path:
    path = Path(value)
    if path != Path(expected):
        raise _gateway_error("caller-selected Gateway store path rejected")
    path = _safe_store_path(path)
    if path.exists():
        info = os.stat(path)
        if info.st_uid != HOST_UID or stat.S_IMODE(info.st_mode) != 0o600:
            raise _gateway_error("Gateway store ownership/mode invalid")
    return path


def _launchctl_observation(*, runner: Callable[..., Any] | None = None) -> dict[str, Any]:
    run = runner or (lambda *args: subprocess.run(args, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE))
    command = ("launchctl", "print", f"{UID_TARGET}/{GATEWAY_LABEL}")
    result = run(*command)
    code = getattr(result, "returncode", 0)
    output = str(getattr(result, "stdout", "") or "")
    if code not in (0, None):
        if _legacy_absent_service(result, command):
            return {"loaded": False, "pid": None, "service_loaded": False}
        raise _gateway_error("Gateway service observation failed")
    match = re.search(r"\bpid\s*=\s*(\d+)", output)
    return {"loaded": True, "service_loaded": True, "pid": int(match.group(1)) if match else None}


def observe_gateway_quiescence() -> dict[str, Any]:
    """Read the manager-owned durable quiescence receipt; never trust request input."""
    path = _safe_store_path(GATEWAY_EVIDENCE_STORE)
    try:
        value = json.loads(path.read_text(), object_pairs_hook=_unique_pairs)
    except (OSError, ValueError) as exc:
        raise _gateway_error("Gateway quiescence evidence unavailable", exc) from exc
    if not isinstance(value, Mapping) or value.get("disposition") not in {"drained", "held", "reconciled"}:
        raise _gateway_error("Gateway quiescence evidence malformed")
    required = ("lifecycle_state", "assist_state", "evidence_sha256", "reacquisition_receipt")
    if any(not value.get(key) for key in required):
        raise _gateway_error("Gateway quiescence evidence incomplete")
    return dict(value)


def collect_gateway_observation(request: GatewayDeploymentRequest, *, observation_time: str | None = None,
                                operation: str | None = None,
                                runner: Callable[..., Any] | None = None,
                                token_loader: Callable[[], str] | None = None,
                                plist_observer: Callable[[Path], tuple[bytes, Mapping[str, Any]]] | None = None,
                                git_observer: Callable[[Path], Mapping[str, Any]] | None = None,
                                source_observer: Callable[[Path], str] | None = None,
                                interpreter_observer: Callable[[Path], tuple[Path, str, int, int, str]] | None = None,
                                artifact_observer: Callable[[Path], str] | None = None,
                                health_observer: Callable[[str], Mapping[str, Any]] | None = None,
                                quiescence_observer: Callable[[], Mapping[str, Any]] | None = None,
                                authority_command_runner: Callable[..., Any] | None = None) -> dict[str, Any]:
    """Collect all preflight evidence from fixed manager-owned observations."""
    request = _require_host_authority(
        request, observation_time=observation_time,
        authority_command_runner=authority_command_runner,
    )
    profile = request.current
    plist_path = Path(profile.repository.plist)
    def read_plist(path: Path) -> tuple[bytes, Mapping[str, Any]]:
        data = path.read_bytes()
        value = plistlib.loads(data)
        if not isinstance(value, Mapping):
            raise _gateway_error("Gateway plist observation malformed")
        return data, value

    try:
        plist_bytes, parsed = (plist_observer or read_plist)(plist_path)
    except (OSError, ValueError, plistlib.InvalidFileException) as exc:
        raise _gateway_error("Gateway plist observation failed", exc) from exc
    if not isinstance(parsed, Mapping):
        raise _gateway_error("Gateway plist observation malformed")
    args = parsed.get("ProgramArguments")
    wrapper_ok = isinstance(args, list) and len(args) == 3 and args[:2] == ["/bin/zsh", "-c"] and args[2] == _gateway_wrapper_command(profile.git.root, str(Path(profile.git.root) / GATEWAY_ENTRYPOINT))
    direct_ok = isinstance(args, list) and len(args) == 2 and args[0] == profile.interpreter.path and str(args[1]) in {GATEWAY_ENTRYPOINT, str(Path(profile.git.root) / GATEWAY_ENTRYPOINT)} and parsed.get("EnvironmentVariables") == {"NEXUS_MCP_GATEWAY_TOKEN": "${NEXUS_MCP_GATEWAY_TOKEN}"}
    if (parsed.get("Label") != GATEWAY_LABEL or parsed.get("WorkingDirectory") != profile.git.root
            or parsed.get("StandardOutPath") != profile.repository.stdout
            or parsed.get("StandardErrorPath") != profile.repository.stderr
            or not (wrapper_ok or direct_ok)
            or parsed.get("RunAtLoad") is not True or parsed.get("KeepAlive") is not True):
        raise _gateway_error("Gateway plist physical identity mismatch")
    plist_digest = hashlib.sha256(plist_bytes).hexdigest()
    if git_observer is None:
        git = {
            "root": profile.git.root, "toplevel": _git(Path(profile.git.root), "rev-parse", "--show-toplevel"),
            "remote": _git(Path(profile.git.root), "remote", "get-url", "origin"),
            "head": _git(Path(profile.git.root), "rev-parse", "HEAD"),
            "tree": _git(Path(profile.git.root), "rev-parse", "HEAD^{tree}"),
            "clean": not bool(_git(Path(profile.git.root), "status", "--porcelain")),
        }
    else:
        git = dict(git_observer(Path(profile.git.root)))
        git.setdefault("root", profile.git.root)
    source_path = Path(profile.git.root) / GATEWAY_ENTRYPOINT
    source_hash = (source_observer or (lambda path: hashlib.sha256(path.read_bytes()).hexdigest()))(source_path)
    if interpreter_observer is None:
        interpreter = Path(profile.interpreter.path)
        target = interpreter.resolve(strict=True)
        interpreter_values = (target, hashlib.sha256(target.read_bytes()).hexdigest(), target.stat().st_uid,
                              target.stat().st_gid, stat.filemode(target.stat().st_mode))
    else:
        interpreter_values = interpreter_observer(Path(profile.interpreter.path))
    target, interpreter_hash, interpreter_uid, interpreter_gid, interpreter_mode = interpreter_values
    service = _launchctl_observation(runner=runner)
    requested_operation = operation or request.operation
    rollback_unloaded = requested_operation in {"rollback", "gateway-rollback"} and not service.get("loaded", False)
    health: Mapping[str, Any] = {}
    if not rollback_unloaded:
        loader = token_loader or (lambda: read_secret_env().get("NEXUS_MCP_GATEWAY_TOKEN", ""))
        token = loader()
        if not token:
            raise _gateway_error("Gateway observation token missing")
        health = (health_observer or (lambda value: _http_json(GATEWAY_ENDPOINT + "/health", token=value)))(token)
        health = health.get("result", health)
        if not isinstance(health, Mapping):
            raise _gateway_error("Gateway health observation malformed")
    if artifact_observer is None:
        try:
            artifact_digest = hashlib.sha256(Path(GATEWAY_ARTIFACT).read_bytes()).hexdigest()
        except OSError:
            artifact_digest = ""
    else:
        artifact_digest = artifact_observer(Path(GATEWAY_ARTIFACT))
    quiescence = (quiescence_observer or observe_gateway_quiescence)()
    normalized_health = (
        {}
        if rollback_unloaded
        else _normalize_gateway_identity_surfaces(
            health,
            profile=profile,
            git=git,
        )
    )
    source_root = str(normalized_health.get("root") or git.get("root") or "")
    source_head = str(normalized_health.get("head") or git.get("head") or "")
    source_tree = str(normalized_health.get("tree") or git.get("tree") or "")
    physical_source_hash = str(health.get("source_sha256") or source_hash)
    server_instance = str(normalized_health.get("server_instance") or "")
    predecessor = {
        "plist_sha256": plist_digest, "plist_bytes_sha256": plist_digest,
        "artifact_sha256": artifact_digest, "source_sha256": physical_source_hash,
        "source_root": source_root, "source_head": source_head, "source_tree": source_tree,
        "loaded": service.get("loaded", False), "pid": service.get("pid"),
        "server_instance": server_instance if not rollback_unloaded else "",
        "listener": GATEWAY_ENDPOINT if not rollback_unloaded else "",
        "service_loaded": service.get("service_loaded", False),
    }
    observed = {
        **git, "entrypoint": GATEWAY_ENTRYPOINT, "entrypoint_sha256": source_hash,
        "interpreter_path": profile.interpreter.path, "interpreter_resolved_path": str(target),
        "interpreter_sha256": interpreter_hash, "interpreter_uid": interpreter_uid,
        "interpreter_gid": interpreter_gid, "interpreter_mode": interpreter_mode,
        "trust_class": profile.trust_class, "repository": profile.repository.repository,
        "stdout": profile.repository.stdout, "stderr": profile.repository.stderr,
        "label": GATEWAY_LABEL, "plist": str(plist_path), "endpoint": GATEWAY_ENDPOINT,
        "plist_sha256": plist_digest, "plist_bytes_sha256": plist_digest,
        "plist_bytes_hex": plist_bytes.hex(), **service,
        "server_instance": server_instance,
        "source_sha256": physical_source_hash,
        "tool_manifest_sha256": str(normalized_health.get("tool_manifest_sha256") or ""),
        "schema_sha256": str(normalized_health.get("schema_sha256") or ""),
        "permission_sha256": str(normalized_health.get("permission_sha256") or ""),
        "action": GATEWAY_ACTION,
        "task_id": GATEWAY_TASK_ID,
        "lifecycle": str(normalized_health.get("lifecycle") or ""),
        "stable_artifact": {"artifact_sha256": artifact_digest},
        "rollback_predecessor": predecessor, "listener": GATEWAY_ENDPOINT if not rollback_unloaded else "",
        "services": [GATEWAY_LABEL], "quiescence": quiescence,
    }
    return observed


def observe_gateway_physical(request: GatewayDeploymentRequest, **kwargs: Any) -> dict[str, Any]:
    """Named physical-observation seam used by the fixed CLI adapter."""
    return collect_gateway_observation(request, **kwargs)


def dispatch_gateway_cli(action: str, *, request: GatewayDeploymentRequest,
                         observed: Mapping[str, Any], observation_time: str,
                         command_runner: Callable[..., Any] | None = None,
                         authority_command_runner: Callable[..., Any] | None = None,
                         runner: Callable[..., Any] | None = None,
                         opener: Any | None = None,
                         token_loader: Callable[[], str] | None = None) -> dict[str, Any]:
    """Route only the fixed Gateway operations with manager-owned arguments."""
    parsed = _validate_gateway_action_pair(action, request)
    kwargs: dict[str, Any] = {
        "observation_time": observation_time,
        "authority_command_runner": authority_command_runner or _fixed_authority_command_runner,
    }
    if action == "status":
        if runner is not None:
            kwargs["runner"] = runner
    elif action == "reload":
        if runner is not None:
            kwargs["runner"] = runner
        kwargs.update(opener=opener or urllib.request.urlopen,
                      token_loader=token_loader or (lambda: read_secret_env()["NEXUS_MCP_GATEWAY_TOKEN"]))
    elif action == "install-artifact":
        artifact = parsed.stable_artifact
        if artifact is None:
            raise _gateway_error("artifact installation requires explicit stable artifact identity")
        kwargs.update(source_root=Path(artifact.source_root), source_path=Path(artifact.source_path),
                      artifact_path=Path(GATEWAY_ARTIFACT),
                      command_runner=command_runner or _fixed_git_command_runner)
    elif action == "rollback":
        if runner is not None:
            kwargs["runner"] = runner
        kwargs.update(predecessor_observer=observed.get("rollback_predecessor"),
                      opener=opener or urllib.request.urlopen,
                      token_loader=token_loader or (lambda: read_secret_env()["NEXUS_MCP_GATEWAY_TOKEN"]))
    return manage_gateway(action, request=parsed, observed=observed, **kwargs)


if __name__ == "__main__": raise SystemExit(main())
