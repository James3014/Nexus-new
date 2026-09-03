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
import shutil
import stat
import subprocess
import tempfile
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
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
    INTERPRETER,
    RECOVERY_RECEIPT_PATH,
    REPOSITORY,
    SOURCE_BASE_MERGE,
    SOURCE_BASE_TREE,
    BareStoreEvidence,
    BundleRoleHead,
    ContractError,
    DeploymentManifest,
    DeploymentState,
    EffectClass,
    GatewayDeploymentRequest,
    GatewayReconcileOutcome,
    GatewayRecoveryRequest,
    HostEffectAuthorityBundle,
    HostEffectAuthorityReceipt,
    PostflightIdentity,
    RecoveryAuthorityReceipt,
    RecoveryEffectAck,
    RecoveryEffectPlan,
    RecoveryEntrypointIdentity,
    RecoveryLedgerRecord,
    RecoveryPhysicalIdentity,
    RecoverySourceSet,
    ResultClass,
    SourceBundleEvidence,
    _gateway_wrapper_command,
    canonical_hash,
    derive_deployment_manifest,
    select_host_effect_authority_receipt,
    validate_authority_freshness,
    validate_deployment_manifest,
    validate_host_effect_authority,
    validate_host_effect_authority_bundle,
    validate_postflight_identity,
    validate_profile,
    validate_receipt_freshness,
    validate_reconcile_outcome,
    validate_recovery_authority,
    validate_recovery_effect_ack,
    validate_recovery_effect_plan,
    validate_recovery_ledger_record,
    validate_recovery_physical_identity,
    validate_recovery_request,
    validate_recovery_source_set,
    validate_request,
    validate_rollback_capture,
    validate_source_bundle_evidence,
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
                                       "gateway-status", "gateway-preflight", "gateway-reload", "gateway-install-artifact", "gateway-rollback", "gateway-recover"))
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
            operation = "gateway-recover" if a.action == "gateway-recover" else a.action.removeprefix("gateway-")
            if operation == "install-artifact": operation = "install-artifact"
            request = (
                GatewayRecoveryRequest.model_validate(payload)
                if operation == "gateway-recover"
                else GatewayDeploymentRequest.model_validate(payload)
            )
            now = _current_observation_time()
            observed = {} if operation in {"status", "gateway-status", "install-artifact", "gateway-recover"} else collect_gateway_observation(
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
GATEWAY_DEPLOYMENTS_ROOT = GATEWAY_STATE_ROOT / "deployments"
GATEWAY_SOURCE_BUNDLES_ROOT = GATEWAY_STATE_ROOT / "source-bundles"
GATEWAY_PREDECESSOR_ARTIFACT_ROOT = GATEWAY_STATE_ROOT / "predecessor-artifacts"
GATEWAY_REPOSITORY = GATEWAY_STATE_ROOT / "repository.git"
GATEWAY_RECOVERY_AUTHORITY_STORE = GATEWAY_STATE_ROOT / "recovery-authority.json"
RECOVERY_AUTHORITY_SOURCE_PATH = RECOVERY_RECEIPT_PATH
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
HOST_GID = 20


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


def _validate_authority_source_directory(info: Any, *, leaf: bool) -> None:
    """Validate the mirror leaf or one generic ancestor without weakening it."""
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
        raise _gateway_error("trusted authority source ancestry unsafe")
    mode = stat.S_IMODE(info.st_mode)
    if leaf:
        if info.st_uid != HOST_AUTHORITY_UID:
            raise _gateway_error("trusted authority source owner mismatch")
        if mode not in {0o700, 0o755}:
            raise _gateway_error("trusted authority source ancestry unsafe")
        return
    if info.st_uid not in {HOST_AUTHORITY_UID, 0}:
        raise _gateway_error("trusted authority source ancestry unsafe")
    if mode & 0o022 and not (info.st_uid == 0 and info.st_mode & stat.S_ISVTX):
        raise _gateway_error("trusted authority source ancestry unsafe")


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
        _validate_authority_source_directory(info, leaf=cursor == root)
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


@dataclass(frozen=True)
class _R1StageResult:
    desired_path: Path
    predecessor_path: Path
    desired_manifest: DeploymentManifest
    predecessor_manifest: DeploymentManifest
    bundle_evidence: SourceBundleEvidence


@dataclass(frozen=True)
class _R1PreparedSource:
    desired_manifest: DeploymentManifest
    predecessor_manifest: DeploymentManifest
    bundle_evidence: SourceBundleEvidence


@dataclass(frozen=True)
class _RecoveryAdapters:
    observe: Callable[[RecoveryEffectPlan], RecoveryPhysicalIdentity]
    effect: Callable[[RecoveryEffectPlan], RecoveryEffectAck]
    postflight: Callable[
        [RecoveryEffectPlan, RecoveryPhysicalIdentity], Mapping[str, Any]
    ]
    clock: Callable[[], str]
    crash_hook: Callable[[str], None]


def _r1_run(*command: str, bytes_output: bool = False) -> str | bytes:
    try:
        result = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=not bytes_output,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise _gateway_error("R1 fixed subprocess failed", exc) from exc
    if result.returncode != 0:
        raise _gateway_error("R1 fixed subprocess rejected")
    return result.stdout if bytes_output else str(result.stdout).strip()


def _r1_safe_directory(path: Path) -> Path:
    """Create/validate only manager-owned 0700 directories below the fixed root."""
    path = Path(path)
    root = Path(GATEWAY_STATE_ROOT)
    if not path.is_absolute() or not root.is_absolute():
        raise _gateway_error("R1 manager directory must be absolute")
    try:
        relative = path.relative_to(root)
    except ValueError as exc:
        raise _gateway_error("R1 manager directory escaped fixed root", exc) from exc
    current = root
    components = (root, *(root / Path(*relative.parts[:index]) for index in range(1, len(relative.parts) + 1)))
    for current in components:
        if current.exists() or current.is_symlink():
            info = os.lstat(current)
            if (
                stat.S_ISLNK(info.st_mode)
                or not stat.S_ISDIR(info.st_mode)
                or info.st_uid != HOST_UID
                or info.st_gid != HOST_GID
                or stat.S_IMODE(info.st_mode) != 0o700
            ):
                raise _gateway_error("R1 manager directory ownership/mode invalid")
            continue
        current.mkdir(mode=0o700, parents=current == root)
        os.chmod(current, 0o700)
        info = os.lstat(current)
        if (info.st_uid, info.st_gid, stat.S_IMODE(info.st_mode)) != (HOST_UID, HOST_GID, 0o700):
            raise _gateway_error("R1 manager directory creation identity mismatch")
    return path


def _r1_mirror_fresh_main() -> tuple[str, str]:
    root = Path(HOST_AUTHORITY_SOURCE_ROOT)
    if root.is_symlink() or not root.is_dir() or (root / ".git").is_symlink():
        raise _gateway_error("R1 authority mirror unavailable")
    info = os.lstat(root)
    if info.st_uid != HOST_AUTHORITY_UID or stat.S_IMODE(info.st_mode) not in {0o700, 0o755}:
        raise _gateway_error("R1 authority mirror ownership/mode invalid")
    root_text = str(root)
    if _r1_run("git", "-C", root_text, "rev-parse", "--show-toplevel") != str(root.resolve()):
        raise _gateway_error("R1 authority mirror root mismatch")
    if _r1_run("git", "-C", root_text, "remote", "get-url", "origin") != HOST_AUTHORITY_REMOTE:
        raise _gateway_error("R1 authority mirror origin mismatch")
    if _r1_run("git", "-C", root_text, "status", "--porcelain"):
        raise _gateway_error("R1 authority mirror dirty")
    observed = str(
        _r1_run("git", "-C", root_text, "ls-remote", HOST_AUTHORITY_REMOTE, HOST_AUTHORITY_REF)
    ).split()
    if len(observed) != 2 or observed[1] != HOST_AUTHORITY_REF or not re.fullmatch(r"[0-9a-f]{40}", observed[0]):
        raise _gateway_error("R1 fresh-main observation malformed")
    fresh_main = observed[0]
    if _r1_run("git", "-C", root_text, "rev-parse", "HEAD") != fresh_main:
        raise _gateway_error("R1 authority mirror stale")
    fresh_tree = str(_r1_run("git", "-C", root_text, "rev-parse", f"{fresh_main}^{{tree}}"))
    return fresh_main, fresh_tree


def _r1_source_command(source: Path, *, bare: bool) -> tuple[str, ...]:
    return (
        ("git", "--git-dir", str(source))
        if bare
        else ("git", "-C", str(source))
    )


def _r1_entrypoint_identity(
    commit: str,
    *,
    source: Path | None = None,
    bare: bool = False,
) -> RecoveryEntrypointIdentity:
    source = Path(HOST_AUTHORITY_SOURCE_ROOT) if source is None else Path(source)
    command = _r1_source_command(source, bare=bare)
    entry = str(_r1_run(*command, "ls-tree", commit, "--", GATEWAY_ENTRYPOINT))
    metadata, separator, tracked = entry.partition("\t")
    fields = metadata.split()
    if (
        not separator
        or len(fields) != 3
        or fields[0] != "100644"
        or fields[1] != "blob"
        or not re.fullmatch(r"[0-9a-f]{40}", fields[2])
        or tracked != GATEWAY_ENTRYPOINT
    ):
        raise _gateway_error("R1 tracked entrypoint identity invalid")
    payload = _r1_run(
        *command, "cat-file", "blob", fields[2], bytes_output=True
    )
    return RecoveryEntrypointIdentity(
        path=GATEWAY_ENTRYPOINT,
        blob_oid=fields[2],
        sha256=hashlib.sha256(bytes(payload)).hexdigest(),
        tracked_mode=fields[0],
    )


def _r1_gitlink_paths(commit: str) -> tuple[Path, ...]:
    raw = bytes(_r1_run(
        "git", "--git-dir", str(GATEWAY_REPOSITORY),
        "ls-tree", "-rz", commit,
        bytes_output=True,
    ))
    paths: list[Path] = []
    for row in raw.split(b"\0"):
        if not row:
            continue
        try:
            metadata, encoded_path = row.split(b"\t", 1)
            mode, kind, oid = metadata.decode("ascii").split()
            path = Path(encoded_path.decode("utf-8", errors="strict"))
        except (UnicodeError, ValueError) as exc:
            raise _gateway_error("R1 Gitlink tree entry malformed", exc) from exc
        if mode != "160000":
            continue
        if kind != "commit" or not re.fullmatch(r"[0-9a-f]{40}", oid):
            raise _gateway_error("R1 Gitlink tree identity invalid")
        if path.is_absolute() or not path.parts or any(part in {"", ".", ".."} for part in path.parts):
            raise _gateway_error("R1 Gitlink path invalid")
        paths.append(path)
    return tuple(paths)


def _r1_verify_inert_gitlinks(worktree: Path, commit: str) -> None:
    for relative in _r1_gitlink_paths(commit):
        current = worktree
        for part in relative.parts:
            current = current / part
            try:
                info = os.lstat(current)
            except FileNotFoundError:
                break
            except OSError as exc:
                raise _gateway_error("R1 Gitlink path unreadable", exc) from exc
            if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
                raise _gateway_error("R1 Gitlink path substituted")
        else:
            try:
                if any(current.iterdir()):
                    raise _gateway_error("R1 Gitlink path populated")
            except OSError as exc:
                raise _gateway_error("R1 Gitlink path unreadable", exc) from exc


def _r1_interpreter_identity() -> Any:
    path = Path(INTERPRETER)
    try:
        info = os.lstat(path)
        resolved = path.resolve(strict=True)
        payload = resolved.read_bytes()
    except OSError as exc:
        raise _gateway_error("R1 fixed interpreter unavailable", exc) from exc
    from nexus.contracts.gateway_deployment import InterpreterIdentity
    return InterpreterIdentity(
        path=str(path),
        resolved_path=str(resolved),
        sha256=hashlib.sha256(payload).hexdigest(),
        uid=info.st_uid,
        gid=info.st_gid,
        mode=stat.filemode(info.st_mode),
    )


def _r1_derive_source_set(
    receipt: RecoveryAuthorityReceipt,
    predecessor_store: Path,
) -> RecoverySourceSet:
    mirror = Path(HOST_AUTHORITY_SOURCE_ROOT)
    commits = (receipt.accepted_source_merge, receipt.desired_commit, receipt.predecessor_commit)
    sources = ((mirror, False), (mirror, False), (predecessor_store, True))
    for commit, (source, bare) in zip(commits, sources, strict=True):
        if not re.fullmatch(r"[0-9a-f]{40}", commit):
            raise _gateway_error("R1 semantic commit malformed")
        _r1_run(*_r1_source_command(source, bare=bare), "cat-file", "-e", f"{commit}^{{commit}}")
    trees = tuple(
        str(_r1_run(*_r1_source_command(source, bare=bare), "rev-parse", f"{commit}^{{tree}}"))
        for commit, (source, bare) in zip(commits, sources, strict=True)
    )
    if trees != (
        receipt.accepted_source_tree,
        receipt.desired_tree,
        receipt.predecessor_tree,
    ):
        raise _gateway_error("R1 semantic commit/tree mismatch")
    values = {
        "repository": REPOSITORY,
        "accepted_commit": commits[0],
        "accepted_tree": trees[0],
        "accepted_entrypoint": _r1_entrypoint_identity(commits[0], source=mirror),
        "desired_commit": commits[1],
        "desired_tree": trees[1],
        "desired_entrypoint": _r1_entrypoint_identity(commits[1], source=mirror),
        "predecessor_commit": commits[2],
        "predecessor_tree": trees[2],
        "predecessor_entrypoint": _r1_entrypoint_identity(
            commits[2], source=predecessor_store, bare=True
        ),
        "interpreter": _r1_interpreter_identity(),
    }
    source_set = RecoverySourceSet(
        **values,
        source_set_sha256=canonical_hash(values),
    )
    return validate_recovery_source_set(source_set)


def _r1_local_receipt(receipt: RecoveryAuthorityReceipt) -> tuple[bytes, str, str]:
    path = _safe_store_path(GATEWAY_RECOVERY_AUTHORITY_STORE)
    if not path.exists() or path.stat().st_uid != HOST_UID or path.stat().st_gid != HOST_GID:
        raise _gateway_error("R1 recovery authority store invalid")
    raw = path.read_bytes()
    try:
        payload = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_pairs)
        local_receipt = RecoveryAuthorityReceipt.model_validate(payload)
        validate_recovery_authority(local_receipt)
    except (UnicodeError, ValueError, ContractError) as exc:
        raise _gateway_error("R1 local recovery receipt malformed", exc) from exc
    if local_receipt != receipt or receipt.receipt_hash != canonical_hash({
        key: value for key, value in receipt.model_dump().items() if key != "receipt_hash"
    }):
        raise _gateway_error("R1 supplied receipt differs from fixed local receipt")
    fresh_main, fresh_tree = _r1_mirror_fresh_main()
    root = str(HOST_AUTHORITY_SOURCE_ROOT)
    if _r1_run(
        "git", "-C", root, "merge-base", "--is-ancestor",
        receipt.authority_floor_commit, fresh_main,
    ) != "":
        raise _gateway_error("R1 authority floor is outside fresh main")
    if _r1_run(
        "git", "-C", root, "rev-parse", f"{receipt.authority_floor_commit}^{{tree}}"
    ) != receipt.authority_floor_tree:
        raise _gateway_error("R1 authority floor tree mismatch")
    tracked = _r1_run(
        "git", "-C", root, "show",
        f"{fresh_main}:{RECOVERY_AUTHORITY_SOURCE_PATH}",
        bytes_output=True,
    )
    if bytes(tracked) != raw:
        raise _gateway_error("R1 recovery receipt remote/local byte mismatch")
    return raw, fresh_main, fresh_tree


_R1_ROLE_REFS = (
    ("fresh-main", "refs/nexus-r1/fresh-main"),
    ("desired", "refs/nexus-r1/desired"),
    ("predecessor", "refs/nexus-r1/predecessor"),
)
_R1_PREDECESSOR_ARTIFACT_REF = "refs/nexus-r1/predecessor-artifact"


def _r1_predecessor_artifact_path(receipt: RecoveryAuthorityReceipt) -> Path:
    return Path(GATEWAY_PREDECESSOR_ARTIFACT_ROOT) / (
        f"{receipt.predecessor_artifact_sha256}.bundle"
    )


def _r1_verify_predecessor_artifact(
    receipt: RecoveryAuthorityReceipt,
) -> tuple[Path, Path]:
    root = _r1_safe_directory(GATEWAY_PREDECESSOR_ARTIFACT_ROOT)
    artifact = _r1_predecessor_artifact_path(receipt)
    try:
        info = os.lstat(artifact)
    except OSError as exc:
        raise _gateway_error("R1 predecessor artifact unavailable", exc) from exc
    if (
        stat.S_ISLNK(info.st_mode)
        or not stat.S_ISREG(info.st_mode)
        or info.st_uid != HOST_UID
        or info.st_gid != HOST_GID
        or stat.S_IMODE(info.st_mode) != 0o600
        or info.st_size != receipt.predecessor_artifact_size
    ):
        raise _gateway_error("R1 predecessor artifact identity invalid")
    try:
        payload = artifact.read_bytes()
    except OSError as exc:
        raise _gateway_error("R1 predecessor artifact unreadable", exc) from exc
    if hashlib.sha256(payload).hexdigest() != receipt.predecessor_artifact_sha256:
        raise _gateway_error("R1 predecessor artifact hash mismatch")

    scratch = Path(tempfile.mkdtemp(prefix=".predecessor-artifact.", dir=root))
    try:
        os.chmod(scratch, 0o700)
        source = scratch / "source.git"
        _r1_run("git", "init", "--bare", str(source))
        # Verification against an empty object database proves the bundle has
        # no prerequisite dependency on a caller checkout or authority mirror.
        _r1_run("git", "--git-dir", str(source), "bundle", "verify", str(artifact))
        lines = str(_r1_run("git", "bundle", "list-heads", str(artifact))).splitlines()
        if len(lines) != 1:
            raise _gateway_error("R1 predecessor artifact role count mismatch")
        commit, ref = lines[0].split(maxsplit=1)
        if ref != _R1_PREDECESSOR_ARTIFACT_REF or commit != receipt.predecessor_commit:
            raise _gateway_error("R1 predecessor artifact role/head mismatch")
        _r1_run(
            "git", "--git-dir", str(source), "fetch", "--no-tags", str(artifact),
            f"+{ref}:{ref}",
        )
        _r1_run("git", "--git-dir", str(source), "fsck", "--full", "--strict")
        if _r1_run("git", "--git-dir", str(source), "rev-parse", f"{commit}^{{tree}}") != receipt.predecessor_tree:
            raise _gateway_error("R1 predecessor artifact tree mismatch")
        entrypoint = _r1_entrypoint_identity(commit, source=source, bare=True)
        if entrypoint != receipt.source_set.predecessor_entrypoint:
            raise _gateway_error("R1 predecessor artifact entrypoint mismatch")
        return scratch, source
    except Exception:
        shutil.rmtree(scratch, ignore_errors=True)
        raise


def _r1_bundle_heads(bundle: Path) -> tuple[BundleRoleHead, ...]:
    observed: dict[str, str] = {}
    for line in str(_r1_run("git", "bundle", "list-heads", str(bundle))).splitlines():
        commit, ref = line.split(maxsplit=1)
        if ref in observed:
            raise _gateway_error("R1 duplicate bundle head")
        observed[ref] = commit
    expected_refs = tuple(ref for _, ref in _R1_ROLE_REFS)
    if set(observed) != set(expected_refs):
        raise _gateway_error("R1 named bundle refs mismatch")
    return tuple(
        BundleRoleHead(role=role, ref=ref, commit=observed[ref])
        for role, ref in _R1_ROLE_REFS
    )


def _r1_create_or_verify_bundle(
    receipt: RecoveryAuthorityReceipt,
    fresh_main: str,
    predecessor_store: Path,
) -> tuple[Path, tuple[BundleRoleHead, ...]]:
    bundles = _r1_safe_directory(GATEWAY_SOURCE_BUNDLES_ROOT)
    bundle = bundles / f"{receipt.receipt_hash}.bundle"
    expected = (fresh_main, receipt.desired_commit, receipt.predecessor_commit)
    try:
        existing_info = os.lstat(bundle)
    except FileNotFoundError:
        bundle_exists = False
    except OSError as exc:
        raise _gateway_error("R1 persisted bundle identity unreadable", exc) from exc
    else:
        bundle_exists = True
        if (
            stat.S_ISLNK(existing_info.st_mode)
            or not stat.S_ISREG(existing_info.st_mode)
            or existing_info.st_uid != HOST_UID
            or existing_info.st_gid != HOST_GID
            or stat.S_IMODE(existing_info.st_mode) != 0o600
        ):
            raise _gateway_error("R1 persisted bundle identity invalid")
    scratch = Path(tempfile.mkdtemp(prefix=".bundle-source.", dir=bundles))
    try:
        os.chmod(scratch, 0o700)
        source = scratch / "source.git"
        candidate = scratch / "candidate.bundle"
        _r1_run("git", "init", "--bare", str(source))
        for (role, ref), commit in zip(_R1_ROLE_REFS, expected, strict=True):
            source_root = (
                predecessor_store
                if role == "predecessor"
                else Path(HOST_AUTHORITY_SOURCE_ROOT)
            )
            _r1_run(
                "git", "--git-dir", str(source), "fetch", "--no-tags",
                str(source_root), f"+{commit}:{ref}",
            )
        _r1_run(
            "git", "--git-dir", str(source), "bundle", "create",
            str(candidate), *(ref for _, ref in _R1_ROLE_REFS),
        )
        os.chmod(candidate, 0o600)
        candidate_bytes = candidate.read_bytes()
        if not bundle_exists:
            os.replace(candidate, bundle)
        elif bundle.read_bytes() != candidate_bytes:
            raise _gateway_error("R1 persisted bundle bytes changed")
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
    if bundle.exists() or bundle.is_symlink():
        info = os.lstat(bundle)
        if (
            stat.S_ISLNK(info.st_mode)
            or not stat.S_ISREG(info.st_mode)
            or info.st_uid != HOST_UID
            or info.st_gid != HOST_GID
            or stat.S_IMODE(info.st_mode) != 0o600
        ):
            raise _gateway_error("R1 persisted bundle identity invalid")
    verify_scratch = Path(tempfile.mkdtemp(prefix=".bundle-verify.", dir=bundles))
    try:
        verify_store = verify_scratch / "verify.git"
        _r1_run("git", "init", "--bare", str(verify_store))
        _r1_run("git", "--git-dir", str(verify_store), "bundle", "verify", str(bundle))
    finally:
        shutil.rmtree(verify_scratch, ignore_errors=True)
    heads = _r1_bundle_heads(bundle)
    if tuple(head.commit for head in heads) != expected:
        raise _gateway_error("R1 named bundle role/commit mismatch")
    return bundle, heads


def _r1_verify_bare_repository() -> None:
    repository = Path(GATEWAY_REPOSITORY)
    if repository.is_symlink() or not repository.is_dir():
        raise _gateway_error("R1 bare repository unavailable")
    info = os.lstat(repository)
    if (
        info.st_uid != HOST_UID
        or info.st_gid != HOST_GID
        or stat.S_IMODE(info.st_mode) != 0o700
    ):
        raise _gateway_error("R1 bare repository ownership/mode invalid")
    try:
        is_bare = _r1_run(
            "git", "--git-dir", str(repository), "rev-parse", "--is-bare-repository"
        )
    except GatewayContractError as exc:
        raise _gateway_error("R1 repository is not bare", exc) from exc
    if is_bare != "true":
        raise _gateway_error("R1 repository is not bare")
    try:
        origin = _r1_run(
            "git", "--git-dir", str(repository), "remote", "get-url", "origin"
        )
    except GatewayContractError as exc:
        raise _gateway_error("R1 bare repository origin mismatch", exc) from exc
    if origin != HOST_AUTHORITY_REMOTE:
        raise _gateway_error("R1 bare repository origin mismatch")
    if (repository / "objects/info/alternates").exists():
        raise _gateway_error("R1 repository alternates forbidden")


def _r1_import_bundle(
    bundle: Path,
    heads: tuple[BundleRoleHead, ...],
) -> BareStoreEvidence:
    _r1_safe_directory(GATEWAY_STATE_ROOT)
    repository = Path(GATEWAY_REPOSITORY)
    if not repository.exists():
        _r1_run("git", "init", "--bare", str(repository))
        os.chmod(repository, 0o700)
        _r1_run(
            "git", "--git-dir", str(repository), "remote", "add",
            "origin", HOST_AUTHORITY_REMOTE,
        )
    _r1_verify_bare_repository()
    for head in heads:
        _r1_run(
            "git", "--git-dir", str(repository), "fetch", "--no-tags",
            str(bundle), f"+{head.ref}:{head.ref}",
        )
    _r1_run("git", "--git-dir", str(repository), "fsck", "--full", "--strict")
    for head in heads:
        if _r1_run("git", "--git-dir", str(repository), "rev-parse", head.ref) != head.commit:
            raise _gateway_error("R1 bare repository role head mismatch")
        _r1_run("git", "--git-dir", str(repository), "cat-file", "-e", f"{head.commit}^{{commit}}")
    object_rows = str(
        _r1_run(
            "git", "--git-dir", str(repository), "rev-list", "--objects",
            *(head.ref for head in heads),
        )
    ).splitlines()
    return BareStoreEvidence(
        path=str(Path(GATEWAY_REPOSITORY)),
        repository=REPOSITORY,
        origin=HOST_AUTHORITY_REMOTE,
        is_bare=True,
        alternates_absent=True,
        owner_uid=HOST_UID,
        owner_gid=HOST_GID,
        mode=0o700,
        object_set_sha256=canonical_hash(sorted(object_rows)),
    )


def _r1_import_witness(path: Path) -> None:
    code = (
        "import importlib.util,pathlib,sys; "
        "sys.path.insert(0, sys.argv[1]); "
        "p=pathlib.Path(sys.argv[1])/'scripts/ops/nexus_mcp_gateway_http.py'; "
        "s=importlib.util.spec_from_file_location('nexus_r1_gateway_entrypoint', p); "
        "m=importlib.util.module_from_spec(s); "
        "s.loader.exec_module(m)"
    )
    result = subprocess.run(
        (INTERPRETER, "-I", "-B", "-c", code, str(path)),
        cwd=path,
        env={"PATH": os.defpath, "PYTHONNOUSERSITE": "1", "PYTHONDONTWRITEBYTECODE": "1"},
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=10,
        check=False,
    )
    if result.returncode != 0:
        raise _gateway_error("R1 bounded repository import failed")


def _r1_verify_worktree(path: Path, manifest: DeploymentManifest) -> Path:
    validate_deployment_manifest(manifest)
    if path.is_symlink() or not path.is_dir() or (path / ".git").is_symlink():
        raise _gateway_error("R1 worktree identity invalid")
    root_info = os.lstat(path)
    if (
        root_info.st_uid != HOST_UID
        or root_info.st_gid != HOST_GID
        or stat.S_IMODE(root_info.st_mode) != 0o700
    ):
        raise _gateway_error("R1 worktree ownership/mode invalid")
    top = _r1_run("git", "-C", str(path), "rev-parse", "--show-toplevel")
    common = Path(str(_r1_run("git", "-C", str(path), "rev-parse", "--git-common-dir")))
    if not common.is_absolute():
        common = (path / common).resolve()
    if top != str(path.resolve()) or common.resolve() != Path(GATEWAY_REPOSITORY).resolve():
        raise _gateway_error("R1 worktree common-dir escaped")
    if _r1_run("git", "-C", str(path), "remote", "get-url", "origin") != HOST_AUTHORITY_REMOTE:
        raise _gateway_error("R1 worktree origin mismatch")
    _r1_verify_inert_gitlinks(path, manifest.commit)
    if (
        _r1_run("git", "-C", str(path), "status", "--porcelain")
        or _r1_run("git", "-C", str(path), "rev-parse", "HEAD") != manifest.commit
        or _r1_run("git", "-C", str(path), "rev-parse", "HEAD^{tree}") != manifest.tree
    ):
        raise _gateway_error("R1 worktree commit/tree/clean mismatch")
    entry = _r1_entrypoint_from_store(manifest.commit)
    if entry != (
        manifest.entrypoint_blob_oid,
        manifest.entrypoint_sha256,
        manifest.tracked_mode,
    ):
        raise _gateway_error("R1 worktree tracked entrypoint mismatch")
    source = path / manifest.entrypoint
    if source.is_symlink() or not source.is_file():
        raise _gateway_error("R1 worktree entrypoint unavailable")
    info = os.lstat(source)
    payload = source.read_bytes()
    if (
        info.st_uid != manifest.owner_uid
        or info.st_gid != manifest.owner_gid
        or stat.S_IMODE(info.st_mode) != manifest.mode
        or hashlib.sha256(payload).hexdigest() != manifest.entrypoint_sha256
    ):
        raise _gateway_error("R1 worktree entrypoint physical identity mismatch")
    _r1_import_witness(path)
    return path


def _r1_entrypoint_from_store(commit: str) -> tuple[str, str, str]:
    repository = str(GATEWAY_REPOSITORY)
    entry = str(_r1_run(
        "git", "--git-dir", repository, "ls-tree", commit, "--", GATEWAY_ENTRYPOINT
    ))
    metadata, separator, tracked = entry.partition("\t")
    fields = metadata.split()
    if (
        not separator or len(fields) != 3 or fields[0] != "100644"
        or fields[1] != "blob" or tracked != GATEWAY_ENTRYPOINT
    ):
        raise _gateway_error("R1 bare entrypoint identity invalid")
    payload = _r1_run(
        "git", "--git-dir", repository, "cat-file", "blob", fields[2],
        bytes_output=True,
    )
    return fields[2], hashlib.sha256(bytes(payload)).hexdigest(), fields[0]


def _r1_materialize_worktree(manifest: DeploymentManifest) -> Path:
    deployments = _r1_safe_directory(GATEWAY_DEPLOYMENTS_ROOT)
    target = deployments / manifest.deployment_id
    if target.exists() or target.is_symlink():
        return _r1_verify_worktree(target, manifest)
    temporary = Path(tempfile.mkdtemp(prefix=f".{manifest.deployment_id}.", dir=deployments))
    os.rmdir(temporary)
    try:
        _r1_run(
            "git", "--git-dir", str(GATEWAY_REPOSITORY), "worktree", "add",
            "--detach", str(temporary), manifest.commit,
        )
        os.chmod(temporary, 0o700)
        _r1_run(
            "git", "--git-dir", str(GATEWAY_REPOSITORY), "worktree", "move",
            str(temporary), str(target),
        )
        os.chmod(target, 0o700)
    except Exception:
        with contextlib.suppress(Exception):
            _r1_run(
                "git", "--git-dir", str(GATEWAY_REPOSITORY), "worktree",
                "remove", "--force", str(temporary),
            )
        raise
    return _r1_verify_worktree(target, manifest)


def _r1_bundle_evidence(
    request: GatewayRecoveryRequest,
    receipt: RecoveryAuthorityReceipt,
    fresh_main: str,
    fresh_tree: str,
    bundle: Path,
    heads: tuple[BundleRoleHead, ...],
    bare_store: BareStoreEvidence,
) -> SourceBundleEvidence:
    values = {
        "request_id": request.request_id,
        "request_hash": request.request_hash,
        "idempotency_fence": request.idempotency_fence,
        "receipt_id": receipt.receipt_id,
        "receipt_hash": receipt.receipt_hash,
        "source_set_sha256": receipt.source_set.source_set_sha256,
        "observed_fresh_main_commit": fresh_main,
        "observed_fresh_main_tree": fresh_tree,
        "role_heads": heads,
        "bundle_sha256": hashlib.sha256(bundle.read_bytes()).hexdigest(),
        "bundle_size": bundle.stat().st_size,
        "bundle_verified": True,
        "bare_store": bare_store,
        "observed_at": _current_observation_time(),
    }
    evidence = SourceBundleEvidence(**values, evidence_hash=canonical_hash(values))
    return validate_source_bundle_evidence(
        evidence,
        request=request,
        receipt=receipt,
        source_set=receipt.source_set,
        expected_fresh_main_commit=fresh_main,
        expected_fresh_main_tree=fresh_tree,
        expected_bare_store=bare_store,
    )


def _recovery_evidence_path(request: GatewayRecoveryRequest) -> Path:
    return Path(GATEWAY_STATE_ROOT) / f"source-bundle-evidence-{request.request_id}.json"


def _persist_or_load_recovery_evidence(
    request: GatewayRecoveryRequest,
    receipt: RecoveryAuthorityReceipt,
    current: SourceBundleEvidence,
) -> SourceBundleEvidence:
    path = _recovery_evidence_path(request)
    if path.exists() or path.is_symlink():
        path = _safe_store_path(path)
        try:
            persisted = SourceBundleEvidence.model_validate(
                json.loads(path.read_text(), object_pairs_hook=_unique_pairs)
            )
            validate_source_bundle_evidence(
                persisted,
                request=request,
                receipt=receipt,
                source_set=receipt.source_set,
                expected_fresh_main_commit=current.observed_fresh_main_commit,
                expected_fresh_main_tree=current.observed_fresh_main_tree,
                expected_bare_store=current.bare_store,
            )
        except (OSError, ValueError, ContractError) as exc:
            raise _gateway_error("persisted recovery bundle evidence invalid", exc) from exc
        physical_fields = {
            "role_heads", "bundle_sha256", "bundle_size", "bundle_verified",
            "bare_store", "source_set_sha256", "receipt_hash", "request_hash",
        }
        if any(
            getattr(persisted, field) != getattr(current, field)
            for field in physical_fields
        ):
            raise _gateway_error("persisted recovery bundle evidence changed")
        return persisted
    encoded = json.dumps(
        current.model_dump(), sort_keys=True, separators=(",", ":")
    ).encode()
    _atomic_gateway_write(path, encoded)
    return current


def _prepare_recovery_source(
    request: GatewayRecoveryRequest,
    receipt: RecoveryAuthorityReceipt,
) -> _R1PreparedSource:
    try:
        validate_recovery_request(request)
        validate_recovery_authority(receipt, request=request)
    except ContractError as exc:
        raise _gateway_error("R1 source authority rejected", exc) from exc
    _, fresh_main, fresh_tree = _r1_local_receipt(receipt)
    root = str(HOST_AUTHORITY_SOURCE_ROOT)
    for commit in (
        receipt.accepted_source_merge,
        receipt.desired_commit,
    ):
        if _r1_run(
            "git", "-C", root, "merge-base", "--is-ancestor", commit, fresh_main
        ) != "":
            raise _gateway_error("R1 semantic commit outside fresh main")
    artifact_scratch, predecessor_store = _r1_verify_predecessor_artifact(receipt)
    try:
        source_set = _r1_derive_source_set(receipt, predecessor_store)
        desired_manifest = derive_deployment_manifest(source_set, role="desired")
        predecessor_manifest = derive_deployment_manifest(source_set, role="predecessor")
        if (
            source_set != receipt.source_set
            or desired_manifest != receipt.desired_manifest
            or predecessor_manifest != receipt.predecessor_manifest
            or request.desired_manifest_id != desired_manifest.deployment_id
            or request.desired_manifest_hash != desired_manifest.manifest_sha256
            or request.predecessor_manifest_id != predecessor_manifest.deployment_id
            or request.predecessor_manifest_hash != predecessor_manifest.manifest_sha256
        ):
            raise _gateway_error("R1 manager-derived identity mismatch")
        bundle, heads = _r1_create_or_verify_bundle(
            receipt, fresh_main, predecessor_store
        )
        bare_store = _r1_import_bundle(bundle, heads)
        evidence = _r1_bundle_evidence(
            request, receipt, fresh_main, fresh_tree, bundle, heads, bare_store
        )
        evidence = _persist_or_load_recovery_evidence(request, receipt, evidence)
        return _R1PreparedSource(
            desired_manifest=desired_manifest,
            predecessor_manifest=predecessor_manifest,
            bundle_evidence=evidence,
        )
    finally:
        shutil.rmtree(artifact_scratch, ignore_errors=True)


def _promote_recovery_source(prepared: _R1PreparedSource) -> _R1StageResult:
    desired_manifest = prepared.desired_manifest
    predecessor_manifest = prepared.predecessor_manifest
    desired_path = _r1_materialize_worktree(desired_manifest)
    predecessor_path = _r1_materialize_worktree(predecessor_manifest)
    return _R1StageResult(
        desired_path=desired_path,
        predecessor_path=predecessor_path,
        desired_manifest=desired_manifest,
        predecessor_manifest=predecessor_manifest,
        bundle_evidence=prepared.bundle_evidence,
    )


def stage_verified_git_store(
    request: GatewayRecoveryRequest,
    receipt: RecoveryAuthorityReceipt,
) -> _R1StageResult:
    """Build the receipt-bound B1 store and two complete detached worktrees."""
    return _promote_recovery_source(_prepare_recovery_source(request, receipt))


def _resolve_manifest_source(manifest: DeploymentManifest) -> Path:
    """Resolve only a manager-derived ID below the fixed deployments root."""
    try:
        validate_deployment_manifest(manifest)
    except ContractError as exc:
        raise _gateway_error("manager manifest rejected", exc) from exc
    target = Path(GATEWAY_DEPLOYMENTS_ROOT) / manifest.deployment_id
    _r1_verify_worktree(target, manifest)
    return target / manifest.entrypoint


def _require_recovery_authority(request: GatewayRecoveryRequest) -> RecoveryAuthorityReceipt:
    path = _safe_store_path(GATEWAY_RECOVERY_AUTHORITY_STORE)
    if not path.exists() or path.stat().st_uid != HOST_UID or path.stat().st_gid != HOST_GID:
        raise _gateway_error("R1 recovery authority store invalid")
    try:
        raw = path.read_bytes()
        payload = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_pairs)
        receipt = RecoveryAuthorityReceipt.model_validate(payload)
        validate_recovery_authority(
            receipt, request=request, now=_current_observation_time()
        )
    except (OSError, UnicodeError, ValueError, ContractError) as exc:
        raise _gateway_error("R1 recovery authority rejected", exc) from exc
    if hashlib.sha256(Path(__file__).read_bytes()).hexdigest() != receipt.final_manager_sha256:
        raise _gateway_error("R1 recovery manager hash mismatch")
    _r1_local_receipt(receipt)
    return receipt


def _resolve_manifest_reference(
    request: GatewayRecoveryRequest,
    receipt: RecoveryAuthorityReceipt,
    *,
    desired: bool,
) -> DeploymentManifest:
    manifest = derive_deployment_manifest(
        receipt.source_set,
        role="desired" if desired else "predecessor",
    )
    expected = (
        (request.desired_manifest_id, request.desired_manifest_hash)
        if desired
        else (request.predecessor_manifest_id, request.predecessor_manifest_hash)
    )
    if (manifest.deployment_id, manifest.manifest_sha256) != expected:
        raise _gateway_error("R1 request manifest reference mismatch")
    _resolve_manifest_source(manifest)
    return manifest


def gateway_recover(
    request: GatewayRecoveryRequest | Mapping[str, Any],
) -> GatewayReconcileOutcome:
    """Reach the positive, effect-free B1 source checkpoint."""
    try:
        typed = GatewayRecoveryRequest.model_validate(request)
        validate_recovery_request(typed)
    except ContractError as exc:
        raise _gateway_error("R1 recovery request rejected", exc) from exc
    receipt = _require_recovery_authority(typed)
    with InterProcessLock(GATEWAY_LOCK):
        staged = stage_verified_git_store(typed, receipt)
        desired_manifest = _resolve_manifest_reference(typed, receipt, desired=True)
        predecessor_manifest = _resolve_manifest_reference(typed, receipt, desired=False)
    observation = {
        "desired_path": str(staged.desired_path),
        "predecessor_path": str(staged.predecessor_path),
        "source_set_sha256": receipt.source_set.source_set_sha256,
        "bundle_evidence_hash": staged.bundle_evidence.evidence_hash,
        "readiness": ["TARGET_READY", "ROLLBACK_READY"],
    }
    outcome_values = {
        "request_id": typed.request_id,
        "request_hash": typed.request_hash,
        "idempotency_fence": typed.idempotency_fence,
        "desired_manifest_id": desired_manifest.deployment_id,
        "predecessor_manifest_id": predecessor_manifest.deployment_id,
        "physical_observation": observation,
        "effect_started": False,
        "result": ResultClass.BLOCKED,
    }
    return validate_reconcile_outcome(
        GatewayReconcileOutcome(
            **outcome_values,
            evidence_hash=canonical_hash(outcome_values),
        )
    )


class InterProcessLock:
    """Timed, no-follow advisory lock used for every mutable gateway store."""

    _process_holds: dict[tuple[int, int, str], tuple[int, int]] = {}

    def __init__(self, path: Path, *, timeout: float = 2.0):
        self.path = _safe_store_path(path, create=True)
        self.timeout = timeout
        self._fd: int | None = None
        self._key = (os.getpid(), threading.get_ident(), str(self.path.resolve()))
        self._reentrant = False

    def __enter__(self) -> "InterProcessLock":
        self._key = (os.getpid(), threading.get_ident(), str(self.path.resolve()))
        held = self._process_holds.get(self._key)
        if held is not None:
            self._process_holds[self._key] = (held[0], held[1] + 1)
            self._reentrant = True
            return self
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
            self._process_holds[self._key] = (self._fd, 1)
            return self
        except Exception:
            self._close()
            raise

    def _close(self) -> None:
        held = self._process_holds.get(self._key)
        if self._reentrant:
            if held is not None:
                self._process_holds[self._key] = (held[0], held[1] - 1)
            self._reentrant = False
            return
        if self._fd is not None:
            self._process_holds.pop(self._key, None)
            with contextlib.suppress(OSError):
                fcntl.flock(self._fd, fcntl.LOCK_UN)
            with contextlib.suppress(OSError):
                os.close(self._fd)
            self._fd = None

    def __exit__(self, *_: object) -> None:
        self._close()

    @classmethod
    def _reset_after_fork(cls) -> None:
        for fd, _depth in set(cls._process_holds.values()):
            with contextlib.suppress(OSError):
                os.close(fd)
        cls._process_holds.clear()


if hasattr(os, "register_at_fork"):
    os.register_at_fork(after_in_child=InterProcessLock._reset_after_fork)


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
        last_schema: dict[str, str] = {}
        fences: dict[str, str] = {}
        requests: dict[str, tuple[str, str]] = {}
        for line in raw.splitlines(keepends=True):
            if not line.endswith(b"\n"):
                raise LedgerCorruption("ledger is not newline terminated")
            try:
                row = json.loads(line.decode("utf-8"), object_pairs_hook=_unique_pairs)
            except (ValueError, UnicodeError) as exc:
                raise LedgerCorruption("ledger JSON malformed") from exc
            v1_keys = {
                "schema", "request_id", "request_hash", "state", "sequence", "parent_hash",
                "record_hash", "pre_effect_identity", "observed_identity", "host_receipt_hash",
                "source_base_merge", "source_base_tree", "host_card_sha256", "effect_class",
                "operation", "idempotency_fence",
            }
            v2_keys = {
                "schema", "request_id", "request_hash", "state", "sequence",
                "parent_hash", "record_hash", "authority_schema", "receipt_id",
                "receipt_hash", "card_sha256", "accepted_source_merge",
                "accepted_source_tree", "final_manager_sha256",
                "independent_acceptance_receipt_hash", "source_set_sha256",
                "desired_manifest_id", "desired_manifest_hash",
                "predecessor_manifest_id", "predecessor_manifest_hash",
                "source_bundle_evidence_hash", "operation", "effect_class",
                "idempotency_fence", "pre_effect_identity", "observed_identity",
            }
            if not isinstance(row, dict) or (
                row.get("schema") == "nexus.gateway.ledger.v1"
                and set(row) != v1_keys
            ) or (
                row.get("schema") == "nexus.gateway.ledger.v2"
                and set(row) != v2_keys
            ) or row.get("schema") not in {
                "nexus.gateway.ledger.v1", "nexus.gateway.ledger.v2"
            }:
                raise LedgerCorruption("ledger schema mismatch")
            canonical_line = (
                json.dumps(row, sort_keys=True, separators=(",", ":")).encode() + b"\n"
            )
            if line != canonical_line:
                raise LedgerCorruption("ledger JSON is not canonical")
            if not isinstance(row["request_id"], str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}", row["request_id"]):
                raise LedgerCorruption("ledger request identity malformed")
            if not isinstance(row["request_hash"], str) or not re.fullmatch(r"[0-9a-f]{64}", row["request_hash"]):
                raise LedgerCorruption("ledger request hash malformed")
            if row["schema"] == "nexus.gateway.ledger.v1":
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
            else:
                for key in (
                    "receipt_hash", "card_sha256", "final_manager_sha256",
                    "independent_acceptance_receipt_hash", "source_set_sha256",
                    "desired_manifest_hash", "predecessor_manifest_hash",
                ):
                    if not isinstance(row[key], str) or not re.fullmatch(
                        r"[0-9a-f]{64}", row[key]
                    ):
                        raise LedgerCorruption("recovery ledger hash malformed")
                for key in ("accepted_source_merge", "accepted_source_tree"):
                    if not isinstance(row[key], str) or not re.fullmatch(
                        r"[0-9a-f]{40}", row[key]
                    ):
                        raise LedgerCorruption("recovery ledger source malformed")
                if row["state"] == DeploymentState.REQUESTED.value:
                    if row["source_bundle_evidence_hash"] is not None:
                        raise LedgerCorruption("REQUESTED evidence must be null")
                elif not isinstance(row["source_bundle_evidence_hash"], str) or not re.fullmatch(
                    r"[0-9a-f]{64}", row["source_bundle_evidence_hash"]
                ):
                    raise LedgerCorruption("recovery ledger evidence missing")
            if row["effect_class"] not in {effect.value for effect in EffectClass}:
                raise LedgerCorruption("ledger effect class unknown")
            operation_effects = {
                "status": EffectClass.STATUS.value, "gateway-status": EffectClass.STATUS.value,
                "preflight": EffectClass.PREFLIGHT.value, "gateway-preflight": EffectClass.PREFLIGHT.value,
                "install": EffectClass.INSTALL_ARTIFACT.value, "install-artifact": EffectClass.INSTALL_ARTIFACT.value,
                "install_artifact": EffectClass.INSTALL_ARTIFACT.value,
                "reload": EffectClass.GATEWAY_RELOAD.value, "gateway-reload": EffectClass.GATEWAY_RELOAD.value,
                "rollback": EffectClass.GATEWAY_ROLLBACK.value, "gateway-rollback": EffectClass.GATEWAY_ROLLBACK.value,
                "gateway-recover": EffectClass.GATEWAY_DURABLE_RECOVERY.value,
            }
            if row["operation"] not in operation_effects:
                raise LedgerCorruption("ledger operation unknown")
            if row["effect_class"] != operation_effects[row["operation"]]:
                raise LedgerCorruption("ledger operation/effect mismatch")
            prior_fence = fences.get(row["idempotency_fence"])
            if prior_fence is not None and prior_fence != row["request_id"]:
                raise LedgerCorruption("ledger idempotency fence reused")
            fences[row["idempotency_fence"]] = row["request_id"]
            prior_request = requests.get(row["request_id"])
            request_binding = (row["request_hash"], row["idempotency_fence"])
            if prior_request is not None and prior_request != request_binding:
                raise LedgerCorruption("ledger request binding changed")
            requests[row["request_id"]] = request_binding
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
                    legacy_uncertain = (
                        last_schema.get(row["request_id"]) == "nexus.gateway.ledger.v1"
                        and row["schema"] == "nexus.gateway.ledger.v1"
                        and previous_state == DeploymentState.UNCERTAIN_EFFECT.value
                        and row["state"] in {
                            DeploymentState.PREFLIGHTED.value,
                            DeploymentState.ROLLBACK_STARTED.value,
                        }
                    )
                    if not legacy_uncertain:
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
            last_schema[row["request_id"]] = row["schema"]
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

    def append_recovery(
        self,
        record: RecoveryLedgerRecord,
        *,
        expected_tail: str,
        request: GatewayRecoveryRequest,
        receipt: RecoveryAuthorityReceipt,
        source_bundle_evidence: SourceBundleEvidence | None,
    ) -> RecoveryLedgerRecord:
        with InterProcessLock(self.lock_path):
            rows = self._scan_unlocked()
            tail = rows[-1]["record_hash"] if rows else ""
            if expected_tail != tail:
                raise GatewayContractError("recovery ledger compare-and-swap conflict")
            for prior in rows:
                if (
                    prior["idempotency_fence"] == record.idempotency_fence
                    and prior["request_id"] != record.request_id
                ):
                    raise GatewayContractError("recovery idempotency fence conflict")
                if prior["request_id"] == record.request_id and (
                    prior["request_hash"] != record.request_hash
                    or prior["idempotency_fence"] != record.idempotency_fence
                ):
                    raise GatewayContractError("recovery request binding conflict")
                if (
                    prior["schema"] == "nexus.gateway.ledger.v2"
                    and prior["request_id"] == record.request_id
                    and prior["state"] == record.state.value
                ):
                    return RecoveryLedgerRecord.model_validate(prior)
            try:
                validate_recovery_ledger_record(
                    record,
                    request=request,
                    receipt=receipt,
                    source_bundle_evidence=source_bundle_evidence,
                    expected_sequence=len(rows) + 1,
                    expected_parent_hash=tail,
                )
            except ContractError as exc:
                raise GatewayContractError("recovery ledger record rejected") from exc
            return self._append_recovery_unlocked(rows, record)

    def _append_recovery_unlocked(
        self,
        rows: list[dict[str, Any]],
        record: RecoveryLedgerRecord,
    ) -> RecoveryLedgerRecord:
        encoded = (
            json.dumps(
                record.model_dump(),
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=True,
            ).encode()
            + b"\n"
        )
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        if self.path.exists():
            with self.path.open("ab") as handle:
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())
            _fsync_dir(self.path.parent)
        else:
            _atomic_gateway_write(self.path, encoded)
        return record

    @staticmethod
    def _validate_recovery_context_without_evidence(
        record: RecoveryLedgerRecord,
        request: GatewayRecoveryRequest,
        receipt: RecoveryAuthorityReceipt,
    ) -> None:
        exact = {
            "request_id": request.request_id,
            "request_hash": request.request_hash,
            "authority_schema": receipt.schema,
            "receipt_id": receipt.receipt_id,
            "receipt_hash": receipt.receipt_hash,
            "card_sha256": receipt.card_sha256,
            "accepted_source_merge": receipt.accepted_source_merge,
            "accepted_source_tree": receipt.accepted_source_tree,
            "final_manager_sha256": receipt.final_manager_sha256,
            "independent_acceptance_receipt_hash": (
                receipt.independent_acceptance_receipt_hash
            ),
            "source_set_sha256": receipt.source_set.source_set_sha256,
            "desired_manifest_id": receipt.desired_manifest_id,
            "desired_manifest_hash": receipt.desired_manifest_sha256,
            "predecessor_manifest_id": receipt.predecessor_manifest_id,
            "predecessor_manifest_hash": receipt.predecessor_manifest_sha256,
            "operation": request.operation,
            "effect_class": request.effect_class,
            "idempotency_fence": request.idempotency_fence,
        }
        if any(getattr(record, key) != value for key, value in exact.items()):
            raise GatewayContractError("recovery ledger trusted context mismatch")

    def recovery_rows(
        self,
        request_id: str,
        *,
        request: GatewayRecoveryRequest,
        receipt: RecoveryAuthorityReceipt,
        source_bundle_evidence: SourceBundleEvidence | None,
    ) -> list[RecoveryLedgerRecord]:
        with InterProcessLock(self.lock_path):
            rows = self._scan_unlocked()
        selected = [
            RecoveryLedgerRecord.model_validate(row)
            for row in rows
            if row["schema"] == "nexus.gateway.ledger.v2"
            and row["request_id"] == request_id
        ]
        for record in selected:
            if record.state is DeploymentState.REQUESTED:
                evidence = None
            else:
                evidence = source_bundle_evidence
            if evidence is None and record.state is not DeploymentState.REQUESTED:
                self._validate_recovery_context_without_evidence(record, request, receipt)
            else:
                try:
                    validate_recovery_ledger_record(
                        record,
                        request=request,
                        receipt=receipt,
                        source_bundle_evidence=evidence,
                        expected_sequence=record.sequence,
                        expected_parent_hash=record.parent_hash,
                    )
                except ContractError as exc:
                    raise GatewayContractError(
                        "recovery ledger trusted context mismatch"
                    ) from exc
        return selected

    def current_recovery_state(
        self,
        request_id: str,
        *,
        request: GatewayRecoveryRequest,
        receipt: RecoveryAuthorityReceipt,
        source_bundle_evidence: SourceBundleEvidence | None,
    ) -> str | None:
        rows = self.recovery_rows(
            request_id,
            request=request,
            receipt=receipt,
            source_bundle_evidence=source_bundle_evidence,
        )
        return rows[-1].state.value if rows else None

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


def _recovery_record(
    rows: list[dict[str, Any]],
    request: GatewayRecoveryRequest,
    receipt: RecoveryAuthorityReceipt,
    evidence: SourceBundleEvidence | None,
    state: DeploymentState,
    *,
    pre_effect_identity: Mapping[str, Any] | None = None,
    observed_identity: Mapping[str, Any] | None = None,
) -> RecoveryLedgerRecord:
    values = {
        "schema": "nexus.gateway.ledger.v2",
        "request_id": request.request_id,
        "request_hash": request.request_hash,
        "state": state,
        "sequence": len(rows) + 1,
        "parent_hash": rows[-1]["record_hash"] if rows else "",
        "authority_schema": receipt.schema,
        "receipt_id": receipt.receipt_id,
        "receipt_hash": receipt.receipt_hash,
        "card_sha256": receipt.card_sha256,
        "accepted_source_merge": receipt.accepted_source_merge,
        "accepted_source_tree": receipt.accepted_source_tree,
        "final_manager_sha256": receipt.final_manager_sha256,
        "independent_acceptance_receipt_hash": (
            receipt.independent_acceptance_receipt_hash
        ),
        "source_set_sha256": receipt.source_set.source_set_sha256,
        "desired_manifest_id": receipt.desired_manifest_id,
        "desired_manifest_hash": receipt.desired_manifest_sha256,
        "predecessor_manifest_id": receipt.predecessor_manifest_id,
        "predecessor_manifest_hash": receipt.predecessor_manifest_sha256,
        "source_bundle_evidence_hash": (
            None if state is DeploymentState.REQUESTED else evidence.evidence_hash
        ),
        "operation": request.operation,
        "effect_class": request.effect_class,
        "idempotency_fence": request.idempotency_fence,
        "pre_effect_identity": dict(pre_effect_identity or {}),
        "observed_identity": dict(observed_identity or {}),
    }
    return RecoveryLedgerRecord(
        **values,
        record_hash=canonical_hash(values),
    )


RECOVERY_OWNER_COMPLETION_SECONDS = 6.0
RECOVERY_OWNER_POLL_SECONDS = 0.02
RECOVERY_LEDGER_LOCK_TIMEOUT_SECONDS = 15.0
_RECOVERY_PROCESS_PID = os.getpid()
_RECOVERY_PROCESS_START = canonical_hash({
    "pid": _RECOVERY_PROCESS_PID,
    "started_ns": time.time_ns(),
})


def _current_recovery_process_start() -> str:
    global _RECOVERY_PROCESS_PID, _RECOVERY_PROCESS_START
    pid = os.getpid()
    if pid != _RECOVERY_PROCESS_PID:
        _RECOVERY_PROCESS_PID = pid
        _RECOVERY_PROCESS_START = canonical_hash({
            "pid": pid,
            "started_ns": time.time_ns(),
        })
    return _RECOVERY_PROCESS_START


def _recovery_owner_marker(pid: int) -> Path:
    return Path(GATEWAY_STATE_ROOT) / f"effect-owner-{pid}.json"


def _record_recovery_owner(pid: int, start_identity: str) -> None:
    encoded = json.dumps(
        {"pid": pid, "start_identity": start_identity},
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    _atomic_gateway_write(_recovery_owner_marker(pid), encoded)


def _recovery_owner_is_live(pid: int, start_identity: str) -> bool:
    try:
        payload = json.loads(
            _safe_store_path(_recovery_owner_marker(pid)).read_text(),
            object_pairs_hook=_unique_pairs,
        )
        os.kill(pid, 0)
    except (OSError, ValueError, GatewayContractError):
        return False
    return payload == {"pid": pid, "start_identity": start_identity}


def _append_recovery_state_unlocked(
    ledger: GatewayLedger,
    rows: list[dict[str, Any]],
    request: GatewayRecoveryRequest,
    receipt: RecoveryAuthorityReceipt,
    evidence: SourceBundleEvidence | None,
    state: DeploymentState,
    *,
    pre_effect_identity: Mapping[str, Any] | None = None,
    observed_identity: Mapping[str, Any] | None = None,
) -> RecoveryLedgerRecord:
    record = _recovery_record(
        rows,
        request,
        receipt,
        evidence,
        state,
        pre_effect_identity=pre_effect_identity,
        observed_identity=observed_identity,
    )
    validate_recovery_ledger_record(
        record,
        request=request,
        receipt=receipt,
        source_bundle_evidence=evidence,
        expected_sequence=len(rows) + 1,
        expected_parent_hash=rows[-1]["record_hash"] if rows else "",
    )
    ledger._append_recovery_unlocked(rows, record)
    rows.append(record.model_dump())
    return record


def _recovery_typed_rows(
    rows: list[dict[str, Any]], request_id: str
) -> list[RecoveryLedgerRecord]:
    return [
        RecoveryLedgerRecord.model_validate(row)
        for row in rows
        if row["schema"] == "nexus.gateway.ledger.v2"
        and row["request_id"] == request_id
    ]


def _recovery_plan(
    request: GatewayRecoveryRequest,
    receipt: RecoveryAuthorityReceipt,
) -> RecoveryEffectPlan:
    values = {
        "request_id": request.request_id,
        "request_hash": request.request_hash,
        "idempotency_fence": request.idempotency_fence,
        "receipt_id": receipt.receipt_id,
        "receipt_hash": receipt.receipt_hash,
        "source_set_sha256": receipt.source_set.source_set_sha256,
        "desired_manifest_id": receipt.desired_manifest_id,
        "desired_manifest_hash": receipt.desired_manifest_sha256,
        "predecessor_manifest_id": receipt.predecessor_manifest_id,
        "predecessor_manifest_hash": receipt.predecessor_manifest_sha256,
        "desired_root": str(
            Path(GATEWAY_DEPLOYMENTS_ROOT) / receipt.desired_manifest_id
        ),
        "predecessor_root": str(
            Path(GATEWAY_DEPLOYMENTS_ROOT) / receipt.predecessor_manifest_id
        ),
        "service_label": GATEWAY_LABEL,
        "plist_path": str(GATEWAY_PLIST),
        "endpoint": GATEWAY_ENDPOINT,
        "pre_effect_identity_hash": canonical_hash({}),
    }
    plan = RecoveryEffectPlan(**values, plan_hash=canonical_hash(values))
    return validate_recovery_effect_plan(
        plan,
        request=request,
        receipt=receipt,
        deployment_root=str(GATEWAY_DEPLOYMENTS_ROOT),
    )


def _recovery_wrapper_command(root: str) -> str:
    """R1 form of the accepted fixed wrapper, restricted to derived deployment roots."""
    root_path = Path(root)
    deployments = Path(GATEWAY_DEPLOYMENTS_ROOT)
    if (
        not root_path.is_absolute()
        or root_path.parent != deployments
        or not re.fullmatch(r"r1-[0-9a-f]{40}", root_path.name)
    ):
        raise _gateway_error("R1 recovery wrapper root substitution")
    entrypoint = str(root_path / GATEWAY_ENTRYPOINT)
    if any(
        token in str(root_path) or token in entrypoint
        for token in (";", "&&", "|", "$", "`", "\n", "\r", "\x00")
    ):
        raise _gateway_error("R1 recovery wrapper path contains shell metacharacter")
    return (
        f'cd {root_path} ; source "{ENV_PATH}" ; export PYTHONDONTWRITEBYTECODE=1 ; '
        f"export NEXUS_CANONICAL_SOURCE_ROOT={root_path} ; "
        "export NEXUS_SELF_HOSTED_CANONICAL_STATE_DIR="
        "/Users/jameschen/Workspace/Nexus-new-self-hosted-state ; "
        f"exec {INTERPRETER} {entrypoint}"
    )


def _recovery_expected_plist_bytes(root: str) -> bytes:
    """Render the one fixed direct-Gateway wrapper for an R1 deployment root."""
    root_path = Path(root)
    wrapper = _recovery_wrapper_command(str(root_path))
    payload = {
        "Label": GATEWAY_LABEL,
        "ProgramArguments": [
            "/bin/zsh",
            "-c",
            wrapper,
        ],
        "WorkingDirectory": str(root_path),
        "RunAtLoad": True,
        "KeepAlive": True,
        "StandardOutPath": "/Users/jameschen/Library/Logs/Nexus/gateway.log",
        "StandardErrorPath": "/Users/jameschen/Library/Logs/Nexus/gateway.err.log",
    }
    return plistlib.dumps(payload, fmt=plistlib.FMT_XML)


def _recovery_expected_plist_sha256(root: str) -> str:
    return hashlib.sha256(_recovery_expected_plist_bytes(root)).hexdigest()


_RECOVERY_RUNTIME_IDENTITY_CODE = """
import json
import sys
sys.path.insert(0, sys.argv[1])
from nexus.orchestrator.unified_mcp_gateway import (
    FULL_TOOL_SCHEMA_HASH,
    LIFECYCLE_REVISION,
    PERMISSION_POLICY_HASH,
    PUBLIC_TOOL_NAMES,
    TOOL_MANIFEST_REVISION,
)
print(json.dumps({
    "tool_manifest_sha256": TOOL_MANIFEST_REVISION,
    "schema_sha256": FULL_TOOL_SCHEMA_HASH,
    "permission_sha256": PERMISSION_POLICY_HASH,
    "lifecycle": LIFECYCLE_REVISION,
    "tool_count": len(PUBLIC_TOOL_NAMES),
}, sort_keys=True, separators=(",", ":")))
""".strip()


def _recovery_expected_postflight(
    receipt: RecoveryAuthorityReceipt,
    *,
    command_runner: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    """Derive runtime identity from the exact staged desired source, never live predecessor state."""
    root = Path(GATEWAY_DEPLOYMENTS_ROOT) / receipt.desired_manifest_id
    _r1_verify_worktree(root, receipt.desired_manifest)
    command = (INTERPRETER, "-c", _RECOVERY_RUNTIME_IDENTITY_CODE, str(root))
    run = command_runner or (
        lambda *args: subprocess.run(
            args,
            cwd=root,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=10,
            check=False,
        )
    )
    try:
        result = run(*command)
    except TypeError:
        result = run(command)
    if isinstance(result, str):
        output = result.strip()
    else:
        if getattr(result, "returncode", 0) not in (0, None):
            raise _gateway_error("R1 desired runtime identity derivation failed")
        output = str(getattr(result, "stdout", "") or "").strip()
    try:
        value = json.loads(output, object_pairs_hook=_unique_pairs)
    except (TypeError, ValueError) as exc:
        raise _gateway_error("R1 desired runtime identity malformed", exc) from exc
    required = {
        "tool_manifest_sha256",
        "schema_sha256",
        "permission_sha256",
        "lifecycle",
        "tool_count",
    }
    if not isinstance(value, Mapping) or set(value) != required:
        raise _gateway_error("R1 desired runtime identity incomplete")
    for key in ("tool_manifest_sha256", "schema_sha256", "permission_sha256"):
        if not isinstance(value[key], str) or not re.fullmatch(r"[0-9a-f]{64}", value[key]):
            raise _gateway_error(f"R1 desired runtime identity hash malformed: {key}")
    if not isinstance(value["lifecycle"], str) or not value["lifecycle"]:
        raise _gateway_error("R1 desired runtime lifecycle missing")
    if type(value["tool_count"]) is not int or value["tool_count"] <= 0:
        raise _gateway_error("R1 desired runtime tool count invalid")
    return dict(value)


def _recovery_outcome(
    request: GatewayRecoveryRequest,
    receipt: RecoveryAuthorityReceipt,
    *,
    result: ResultClass,
    effect_started: bool,
    observation: Mapping[str, Any],
) -> GatewayReconcileOutcome:
    values = {
        "request_id": request.request_id,
        "request_hash": request.request_hash,
        "idempotency_fence": request.idempotency_fence,
        "desired_manifest_id": receipt.desired_manifest_id,
        "predecessor_manifest_id": receipt.predecessor_manifest_id,
        "physical_observation": dict(observation),
        "effect_started": effect_started,
        "result": result,
    }
    return validate_reconcile_outcome(
        GatewayReconcileOutcome(
            **values,
            evidence_hash=canonical_hash(values),
        )
    )


def _terminal_recovery_outcome(
    records: list[RecoveryLedgerRecord],
) -> GatewayReconcileOutcome | None:
    if not records:
        return None
    terminal = records[-1]
    payload = terminal.observed_identity.get("outcome")
    if terminal.state in {
        DeploymentState.VERIFIED,
        DeploymentState.ROLLED_BACK,
        DeploymentState.BLOCKED,
    } and isinstance(payload, Mapping):
        return GatewayReconcileOutcome.model_validate(payload)
    return None


def _validate_recovery_postflight(
    postflight: Mapping[str, Any],
    identity: RecoveryPhysicalIdentity,
    receipt: RecoveryAuthorityReceipt,
) -> None:
    if not isinstance(postflight, Mapping) or postflight.get("authenticated") is not True:
        raise GatewayContractError("recovery postflight is not authenticated")
    health = postflight.get("health")
    initialize = postflight.get("initialize")
    tools = postflight.get("tools_list")
    if not all(isinstance(item, Mapping) for item in (health, initialize, tools)):
        raise GatewayContractError("recovery postflight response missing")
    expected = _recovery_expected_postflight(receipt)
    desired_root = str(Path(GATEWAY_DEPLOYMENTS_ROOT) / receipt.desired_manifest_id)
    if (
        identity.deployment_id != receipt.desired_manifest_id
        or identity.root != desired_root
        or identity.head != receipt.desired_manifest.commit
        or identity.tree != receipt.desired_manifest.tree
    ):
        raise GatewayContractError("recovery physical identity is not desired source")
    canonical_identity = {
        "root": identity.root,
        "head": identity.head,
        "tree": identity.tree,
        "server_instance": identity.server_instance,
        "permission_sha256": expected["permission_sha256"],
        "lifecycle": expected["lifecycle"],
    }
    for surface, label in ((health, "health"), (initialize, "initialize")):
        if any(surface.get(key) != value for key, value in canonical_identity.items()):
            raise GatewayContractError(f"recovery {label} identity mismatch")
        if (
            surface.get("tool_manifest_sha256") != expected["tool_manifest_sha256"]
            or surface.get("schema_sha256") != expected["schema_sha256"]
        ):
            raise GatewayContractError(f"recovery {label} runtime identity mismatch")
    if (
        tools.get("tool_manifest_sha256") != expected["tool_manifest_sha256"]
        or tools.get("schema_sha256") != expected["schema_sha256"]
        or tools.get("tool_count") != expected["tool_count"]
    ):
        raise GatewayContractError("recovery tools identity mismatch")
    previous = postflight.get("previous_server_instance")
    if postflight.get("applied") is True and (
        not isinstance(previous, str)
        or not previous
        or previous == identity.server_instance
    ):
        raise GatewayContractError("recovery server instance did not change")


def _classify_recovery_physical(
    identity: RecoveryPhysicalIdentity,
    receipt: RecoveryAuthorityReceipt,
) -> str:
    desired_root = str(
        Path(GATEWAY_DEPLOYMENTS_ROOT) / receipt.desired_manifest_id
    )
    predecessor_root = str(
        Path(GATEWAY_DEPLOYMENTS_ROOT) / receipt.predecessor_manifest_id
    )
    try:
        validate_recovery_physical_identity(
            identity,
            expected_manifest=receipt.desired_manifest,
            expected_root=desired_root,
            expected_plist_sha256=_recovery_expected_plist_sha256(desired_root),
        )
        return "desired"
    except ContractError:
        pass
    try:
        validate_recovery_physical_identity(
            identity,
            expected_manifest=receipt.predecessor_manifest,
            expected_root=predecessor_root,
            expected_plist_sha256=_recovery_expected_plist_sha256(predecessor_root),
        )
        return "predecessor"
    except ContractError:
        return "unknown"


def _gateway_reconcile_physical(
    request: GatewayRecoveryRequest,
    receipt: RecoveryAuthorityReceipt,
    identities: RecoveryPhysicalIdentity | tuple[RecoveryPhysicalIdentity, ...],
) -> str:
    candidates = identities if isinstance(identities, tuple) else (identities,)
    classifications = {
        _classify_recovery_physical(identity, receipt) for identity in candidates
    }
    classifications.discard("unknown")
    if len(classifications) > 1 or len(candidates) > 1 and classifications:
        raise GatewayContractError("recovery physical identity ambiguous")
    return next(iter(classifications), "unknown")


def _recovery_token(token_loader: Callable[[], str] | None = None) -> str:
    loader = token_loader or (
        lambda: read_secret_env().get("NEXUS_MCP_GATEWAY_TOKEN", "")
    )
    try:
        token = loader()
    except Exception as exc:
        raise _gateway_error("R1 Gateway token unavailable", exc) from exc
    if not isinstance(token, str) or not token:
        raise _gateway_error("R1 Gateway token missing")
    return token


def _recovery_process_start_identity(
    pid: int, *, runner: Callable[..., Any] | None = None
) -> str:
    if type(pid) is not int or pid <= 0:
        raise _gateway_error("R1 Gateway PID missing")
    run = runner or (
        lambda *args: subprocess.run(
            args,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
    )
    result = run("ps", "-p", str(pid), "-o", "lstart=")
    if getattr(result, "returncode", 0) not in (0, None):
        raise _gateway_error("R1 Gateway process start observation failed")
    value = str(getattr(result, "stdout", "") or "").strip()
    if not value:
        raise _gateway_error("R1 Gateway process start identity missing")
    return f"pid-{pid}:{value}"


def _recovery_git_identity(root: Path, manifest: DeploymentManifest) -> dict[str, Any]:
    expected = Path(GATEWAY_DEPLOYMENTS_ROOT) / manifest.deployment_id
    if root != expected:
        raise _gateway_error("R1 recovery root substitution")
    _r1_verify_worktree(root, manifest)
    head = str(_r1_run("git", "-C", str(root), "rev-parse", "HEAD"))
    tree = str(_r1_run("git", "-C", str(root), "rev-parse", "HEAD^{tree}"))
    status = str(_r1_run("git", "-C", str(root), "status", "--porcelain"))
    if head != manifest.commit or tree != manifest.tree or status:
        raise _gateway_error("R1 recovery staged Git identity mismatch")
    return {"root": str(root), "head": head, "tree": tree, "clean": True}


def _recovery_health(
    *, token: str, opener: Any = urllib.request.urlopen
) -> Mapping[str, Any]:
    value = _http_json(
        GATEWAY_ENDPOINT + "/health", token=token, opener=opener
    )
    value = value.get("result", value)
    if not isinstance(value, Mapping):
        raise _gateway_error("R1 Gateway health malformed")
    return value


def _recovery_observe_physical(
    plan: RecoveryEffectPlan,
    receipt: RecoveryAuthorityReceipt,
    *,
    runner: Callable[..., Any] | None = None,
    opener: Any = urllib.request.urlopen,
    token_loader: Callable[[], str] | None = None,
    sleeper: Callable[[float], None] = time.sleep,
    retries: int = 5,
) -> RecoveryPhysicalIdentity:
    if retries < 1 or retries > 5:
        raise _gateway_error("R1 recovery observation retry bound invalid")
    token = _recovery_token(token_loader)
    desired_root = Path(plan.desired_root)
    predecessor_root = Path(plan.predecessor_root)
    roots = {
        _recovery_expected_plist_sha256(str(desired_root)): (
            desired_root,
            receipt.desired_manifest,
        ),
        _recovery_expected_plist_sha256(str(predecessor_root)): (
            predecessor_root,
            receipt.predecessor_manifest,
        ),
    }
    last: BaseException | None = None
    for attempt in range(retries):
        try:
            service = _launchctl_observation(runner=runner)
            pid = service.get("pid")
            if service.get("loaded") is not True or type(pid) is not int or pid <= 0:
                raise _gateway_error("R1 Gateway service/PID missing")
            plist_bytes = Path(GATEWAY_PLIST).read_bytes()
            plist_sha = hashlib.sha256(plist_bytes).hexdigest()
            selected = roots.get(plist_sha)
            if selected is None:
                raise _gateway_error("R1 Gateway plist does not match staged deployment")
            root, manifest = selected
            if plist_bytes != _recovery_expected_plist_bytes(str(root)):
                raise _gateway_error("R1 Gateway plist bytes drift")
            git = _recovery_git_identity(root, manifest)
            health = _recovery_health(token=token, opener=opener)
            server_instance = _canonical_alias(
                health,
                "server_instance",
                _GATEWAY_PROTOCOL_ALIASES["server_instance"],
            )
            health_root = _canonical_alias(health, "root", ("repo_root",))
            health_head = _canonical_alias(health, "head", ("git_head",))
            if health_root != git["root"] or health_head != git["head"]:
                raise _gateway_error("R1 Gateway health/source disagreement")
            if "tree" in health or "git_tree" in health:
                if _canonical_alias(health, "tree", ("git_tree",)) != git["tree"]:
                    raise _gateway_error("R1 Gateway health/tree disagreement")
            values = {
                "loaded": True,
                "service_label": GATEWAY_LABEL,
                "pid": pid,
                "start_identity": _recovery_process_start_identity(pid, runner=runner),
                "listener": GATEWAY_ENDPOINT,
                "plist_sha256": plist_sha,
                "deployment_id": manifest.deployment_id,
                "root": git["root"],
                "head": git["head"],
                "tree": git["tree"],
                "server_instance": server_instance,
                "observed_at": datetime.now(timezone.utc).isoformat(),
            }
            identity = RecoveryPhysicalIdentity(
                **values, evidence_hash=canonical_hash(values)
            )
            return validate_recovery_physical_identity(
                identity,
                expected_manifest=manifest,
                expected_root=str(root),
                expected_plist_sha256=plist_sha,
            )
        except (GatewayContractError, ContractError, OSError) as exc:
            last = exc
            if attempt + 1 < retries:
                sleeper(min(0.25, 0.05 * (2**attempt)))
    raise _gateway_error("R1 Gateway physical observation remained uncertain", last)


def _recovery_live_postflight(
    plan: RecoveryEffectPlan,
    identity: RecoveryPhysicalIdentity,
    receipt: RecoveryAuthorityReceipt,
    *,
    previous_server_instance: str | None,
    applied: bool,
    opener: Any = urllib.request.urlopen,
    token_loader: Callable[[], str] | None = None,
) -> Mapping[str, Any]:
    token = _recovery_token(token_loader)
    health = _recovery_health(token=token, opener=opener)
    initialize_raw = _http_json(
        GATEWAY_ENDPOINT + "/mcp",
        token=token,
        opener=opener,
        payload={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
    )
    tools_raw = _http_json(
        GATEWAY_ENDPOINT + "/mcp",
        token=token,
        opener=opener,
        payload={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
    )
    initialize_result = initialize_raw.get("result", initialize_raw)
    tools_result = tools_raw.get("result", tools_raw)
    if not isinstance(initialize_result, Mapping) or not isinstance(tools_result, Mapping):
        raise _gateway_error("R1 Gateway MCP postflight malformed")
    server_info = initialize_result.get("serverInfo")
    tools = tools_result.get("tools")
    if not isinstance(server_info, Mapping):
        raise _gateway_error("R1 Gateway initialize identity missing")
    if (
        not isinstance(tools, list)
        or not tools
        or any(
            not isinstance(item, Mapping)
            or not isinstance(item.get("name"), str)
            or not item.get("name")
            for item in tools
        )
    ):
        raise _gateway_error("R1 Gateway tools/list malformed")
    names = tuple(sorted(str(item["name"]) for item in tools))
    manifest_hash = hashlib.sha256(
        json.dumps(names, separators=(",", ":"), ensure_ascii=True).encode()
    ).hexdigest()
    schema_hash = hashlib.sha256(
        json.dumps(
            tools,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode()
    ).hexdigest()
    expected = _recovery_expected_postflight(receipt)
    health_identity = {
        key: _canonical_alias(health, key, aliases)
        for key, aliases in _GATEWAY_PROTOCOL_ALIASES.items()
    }
    initialize_identity = {
        key: _canonical_alias(server_info, key, aliases)
        for key, aliases in _GATEWAY_PROTOCOL_ALIASES.items()
    }
    if health_identity != initialize_identity:
        raise _gateway_error("R1 health/initialize identity disagreement")
    root = _canonical_alias(health, "root", ("repo_root",))
    head = _canonical_alias(health, "head", ("git_head",))
    if (
        root != identity.root
        or head != identity.head
        or health_identity["server_instance"] != identity.server_instance
    ):
        raise _gateway_error("R1 postflight physical identity disagreement")
    if "tree" in health or "git_tree" in health:
        if _canonical_alias(health, "tree", ("git_tree",)) != identity.tree:
            raise _gateway_error("R1 postflight tree disagreement")
    if (
        manifest_hash != expected["tool_manifest_sha256"]
        or schema_hash != expected["schema_sha256"]
        or health_identity["tool_manifest_sha256"] != manifest_hash
        or health_identity["schema_sha256"] != schema_hash
        or health_identity["permission_sha256"] != expected["permission_sha256"]
        or health_identity["lifecycle"] != expected["lifecycle"]
        or len(tools) != expected["tool_count"]
    ):
        raise _gateway_error("R1 postflight desired-source runtime identity mismatch")
    canonical_surface = {
        "root": identity.root,
        "head": identity.head,
        "tree": identity.tree,
        "server_instance": identity.server_instance,
        "tool_manifest_sha256": manifest_hash,
        "schema_sha256": schema_hash,
        "permission_sha256": health_identity["permission_sha256"],
        "lifecycle": health_identity["lifecycle"],
    }
    return {
        "authenticated": True,
        "health": dict(canonical_surface),
        "initialize": dict(canonical_surface),
        "tools_list": {
            "tool_manifest_sha256": manifest_hash,
            "schema_sha256": schema_hash,
            "tool_count": len(tools),
            "actions": names,
        },
        "previous_server_instance": previous_server_instance,
        "applied": applied,
    }


def _production_recovery_adapters(
    receipt: RecoveryAuthorityReceipt,
    *,
    runner: Callable[..., Any] | None = None,
    opener: Any = urllib.request.urlopen,
    token_loader: Callable[[], str] | None = None,
    sleeper: Callable[[float], None] = time.sleep,
) -> _RecoveryAdapters:
    """Bind R1 to the one fixed direct-Gateway host; optional seams are test-only."""
    state: dict[str, Any] = {
        "previous_server_instance": None,
        "applied": False,
    }
    run = runner or (
        lambda *args: subprocess.run(
            args,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
    )

    def observe(plan: RecoveryEffectPlan) -> RecoveryPhysicalIdentity:
        return _recovery_observe_physical(
            plan,
            receipt,
            runner=run,
            opener=opener,
            token_loader=token_loader,
            sleeper=sleeper,
        )

    def effect(plan: RecoveryEffectPlan) -> RecoveryEffectAck:
        desired_bytes = _recovery_expected_plist_bytes(plan.desired_root)
        predecessor_bytes = _recovery_expected_plist_bytes(plan.predecessor_root)
        try:
            current_bytes = Path(GATEWAY_PLIST).read_bytes()
        except OSError:
            current_bytes = b""
        if current_bytes == desired_bytes:
            try:
                current = observe(plan)
            except Exception:
                current = None
            if current is not None and _classify_recovery_physical(current, receipt) == "desired":
                values = {
                    "plan_hash": plan.plan_hash,
                    "acknowledged": True,
                    "applied": False,
                    "already_desired": True,
                    "effect_kind": "GATEWAY_DURABLE_RECOVERY",
                }
                return RecoveryEffectAck(
                    **values, evidence_hash=canonical_hash(values)
                )
        token = _recovery_token(token_loader)
        current_health = _recovery_health(token=token, opener=opener)
        state["previous_server_instance"] = _canonical_alias(
            current_health,
            "server_instance",
            _GATEWAY_PROTOCOL_ALIASES["server_instance"],
        )
        command = ("launchctl", "bootout", f"{UID_TARGET}/{GATEWAY_LABEL}")
        result = run(*command)
        if (
            getattr(result, "returncode", 0) not in (0, None)
            and not _legacy_absent_service(result, command)
        ):
            raise _gateway_error("R1 Gateway bootout failed")
        _atomic_gateway_write(Path(GATEWAY_PLIST), desired_bytes)
        result = run("launchctl", "bootstrap", UID_TARGET, str(GATEWAY_PLIST))
        if getattr(result, "returncode", 0) not in (0, None):
            _atomic_gateway_write(Path(GATEWAY_PLIST), predecessor_bytes)
            rollback = run(
                "launchctl", "bootstrap", UID_TARGET, str(GATEWAY_PLIST)
            )
            if getattr(rollback, "returncode", 0) not in (0, None):
                raise _gateway_error(
                    "R1 desired bootstrap failed and predecessor restoration failed"
                )
            raise _gateway_error(
                "R1 desired bootstrap failed; exact predecessor restoration attempted"
            )
        state["applied"] = True
        values = {
            "plan_hash": plan.plan_hash,
            "acknowledged": True,
            "applied": True,
            "already_desired": False,
            "effect_kind": "GATEWAY_DURABLE_RECOVERY",
        }
        return RecoveryEffectAck(**values, evidence_hash=canonical_hash(values))

    def postflight(
        plan: RecoveryEffectPlan, identity: RecoveryPhysicalIdentity
    ) -> Mapping[str, Any]:
        return _recovery_live_postflight(
            plan,
            identity,
            receipt,
            previous_server_instance=state["previous_server_instance"],
            applied=bool(state["applied"]),
            opener=opener,
            token_loader=token_loader,
        )

    return _RecoveryAdapters(
        observe=observe,
        effect=effect,
        postflight=postflight,
        clock=lambda: datetime.now(timezone.utc).isoformat(),
        crash_hook=lambda _point: None,
    )


def _gateway_recover_live(
    request: GatewayRecoveryRequest | Mapping[str, Any],
) -> GatewayReconcileOutcome:
    """Manager-local R1 host seam; deliberately absent from public CLI/MCP dispatch."""
    try:
        typed = GatewayRecoveryRequest.model_validate(request)
        validate_recovery_request(typed)
    except ContractError as exc:
        raise _gateway_error("R1 live recovery request rejected", exc) from exc
    receipt = _require_recovery_authority(typed)
    return _gateway_recover_with_adapters(
        typed,
        adapters=_production_recovery_adapters(receipt),
        ledger=GatewayLedger(),
    )


def _revalidate_recovery_artifacts(
    request: GatewayRecoveryRequest,
    receipt: RecoveryAuthorityReceipt,
    *,
    expected_bundle_evidence_hash: str,
) -> _R1StageResult:
    prepared = _prepare_recovery_source(request, receipt)
    if prepared.bundle_evidence.evidence_hash != expected_bundle_evidence_hash:
        raise GatewayContractError("recovery bundle evidence replay mismatch")
    desired = Path(GATEWAY_DEPLOYMENTS_ROOT) / receipt.desired_manifest_id
    predecessor = Path(GATEWAY_DEPLOYMENTS_ROOT) / receipt.predecessor_manifest_id
    _r1_verify_worktree(desired, receipt.desired_manifest)
    _r1_verify_worktree(predecessor, receipt.predecessor_manifest)
    return _R1StageResult(
        desired_path=desired,
        predecessor_path=predecessor,
        desired_manifest=receipt.desired_manifest,
        predecessor_manifest=receipt.predecessor_manifest,
        bundle_evidence=prepared.bundle_evidence,
    )


def _validate_terminal_recovery_replay(
    terminal: GatewayReconcileOutcome,
    records: list[RecoveryLedgerRecord],
    request: GatewayRecoveryRequest,
    receipt: RecoveryAuthorityReceipt,
    adapters: _RecoveryAdapters,
) -> GatewayReconcileOutcome:
    if terminal.result is ResultClass.BLOCKED:
        return terminal
    evidence_hashes = {
        record.source_bundle_evidence_hash
        for record in records
        if record.source_bundle_evidence_hash is not None
    }
    if len(evidence_hashes) != 1:
        raise GatewayContractError("terminal recovery evidence binding invalid")
    _revalidate_recovery_artifacts(
        request,
        receipt,
        expected_bundle_evidence_hash=next(iter(evidence_hashes)),
    )
    plan = _recovery_plan(request, receipt)
    identity = adapters.observe(plan)
    classification = _gateway_reconcile_physical(request, receipt, identity)
    if terminal.result is ResultClass.VERIFIED:
        if classification != "desired":
            raise GatewayContractError("VERIFIED recovery physical identity drift")
        postflight = adapters.postflight(plan, identity)
        _validate_recovery_postflight(postflight, identity, receipt)
    elif terminal.result is ResultClass.ROLLED_BACK:
        if classification != "predecessor":
            raise GatewayContractError("ROLLED_BACK recovery physical identity drift")
    else:
        raise GatewayContractError("unsupported terminal recovery replay")
    return terminal


def _gateway_recover_with_adapters(
    request: GatewayRecoveryRequest | Mapping[str, Any],
    *,
    adapters: _RecoveryAdapters,
    ledger: GatewayLedger,
) -> GatewayReconcileOutcome:
    try:
        typed = GatewayRecoveryRequest.model_validate(request)
        validate_recovery_request(typed)
    except ContractError as exc:
        raise _gateway_error("R1 B2 recovery request rejected", exc) from exc
    receipt = _require_recovery_authority(typed)
    prepared: _R1PreparedSource | None = None
    evidence: SourceBundleEvidence | None = None
    plan = _recovery_plan(typed, receipt)
    invoke_effect = False
    wait_for_owner: tuple[int, str] | None = None
    with InterProcessLock(
        ledger.lock_path, timeout=RECOVERY_LEDGER_LOCK_TIMEOUT_SECONDS
    ):
        rows = ledger._scan_unlocked()
        for prior in rows:
            if (
                prior["idempotency_fence"] == typed.idempotency_fence
                and prior["request_id"] != typed.request_id
            ):
                raise GatewayContractError("recovery idempotency fence conflict")
        records = _recovery_typed_rows(rows, typed.request_id)
        terminal = _terminal_recovery_outcome(records)
        if terminal is not None:
            return _validate_terminal_recovery_replay(
                terminal, records, typed, receipt, adapters
            )
        if not records:
            _append_recovery_state_unlocked(
                ledger, rows, typed, receipt, None, DeploymentState.REQUESTED
            )
            records = _recovery_typed_rows(rows, typed.request_id)
        state = records[-1].state
        if state in {
            DeploymentState.REQUESTED,
            DeploymentState.PREFLIGHTED,
            DeploymentState.TARGET_READY,
            DeploymentState.ROLLBACK_READY,
        }:
            prepared = _prepare_recovery_source(typed, receipt)
            evidence = prepared.bundle_evidence
        else:
            evidence_hashes = {
                record.source_bundle_evidence_hash
                for record in records
                if record.source_bundle_evidence_hash is not None
            }
            if len(evidence_hashes) != 1:
                raise GatewayContractError("recovery evidence binding missing")
            evidence_hash = next(iter(evidence_hashes))
            prepared = _prepare_recovery_source(typed, receipt)
            evidence = prepared.bundle_evidence
            if evidence.evidence_hash != evidence_hash:
                raise GatewayContractError("recovery evidence changed")
            _r1_verify_worktree(
                Path(GATEWAY_DEPLOYMENTS_ROOT) / receipt.desired_manifest_id,
                receipt.desired_manifest,
            )
            _r1_verify_worktree(
                Path(GATEWAY_DEPLOYMENTS_ROOT) / receipt.predecessor_manifest_id,
                receipt.predecessor_manifest,
            )
            owner_pid = records[-1].pre_effect_identity.get("effect_owner_pid")
            owner_start = records[-1].pre_effect_identity.get("effect_owner_start")
            if (
                records[-1].state is DeploymentState.EFFECT_STARTED
                and type(owner_pid) is int
                and isinstance(owner_start, str)
                and owner_pid != os.getpid()
            ):
                wait_for_owner = (owner_pid, owner_start)
        if state is DeploymentState.REQUESTED:
            _append_recovery_state_unlocked(
                ledger,
                rows,
                typed,
                receipt,
                evidence,
                DeploymentState.PREFLIGHTED,
            )
            state = DeploymentState.PREFLIGHTED
            adapters.crash_hook("after_bundle_evidence")
        if state is DeploymentState.PREFLIGHTED:
            _r1_materialize_worktree(prepared.desired_manifest)
            _append_recovery_state_unlocked(
                ledger, rows, typed, receipt, evidence, DeploymentState.TARGET_READY
            )
            state = DeploymentState.TARGET_READY
            adapters.crash_hook("after_target_ready")
        if state is DeploymentState.TARGET_READY:
            try:
                _r1_materialize_worktree(prepared.predecessor_manifest)
            except Exception as exc:
                _append_recovery_state_unlocked(
                    ledger,
                    rows,
                    typed,
                    receipt,
                    evidence,
                    DeploymentState.ROLLBACK_UNAVAILABLE,
                    observed_identity={"error": type(exc).__name__},
                )
                outcome = _recovery_outcome(
                    typed,
                    receipt,
                    result=ResultClass.BLOCKED,
                    effect_started=False,
                    observation={"state": "ROLLBACK_UNAVAILABLE"},
                )
                _append_recovery_state_unlocked(
                    ledger,
                    rows,
                    typed,
                    receipt,
                    evidence,
                    DeploymentState.BLOCKED,
                    observed_identity={"outcome": outcome.model_dump()},
                )
                return outcome
            _append_recovery_state_unlocked(
                ledger,
                rows,
                typed,
                receipt,
                evidence,
                DeploymentState.ROLLBACK_READY,
            )
            state = DeploymentState.ROLLBACK_READY
            adapters.crash_hook("after_rollback_ready")
        if state is DeploymentState.ROLLBACK_READY:
            owner_start = _current_recovery_process_start()
            _record_recovery_owner(os.getpid(), owner_start)
            _append_recovery_state_unlocked(
                ledger,
                rows,
                typed,
                receipt,
                evidence,
                DeploymentState.EFFECT_STARTED,
                pre_effect_identity={
                    "plan_hash": plan.plan_hash,
                    "effect_owner_pid": os.getpid(),
                    "effect_owner_start": owner_start,
                },
            )
            state = DeploymentState.EFFECT_STARTED
            invoke_effect = True
            adapters.crash_hook("after_effect_started_before_call")
    if wait_for_owner is not None:
        owner_pid, owner_start = wait_for_owner
        deadline = time.monotonic() + RECOVERY_OWNER_COMPLETION_SECONDS
        owner_live = True
        while True:
            with InterProcessLock(
                ledger.lock_path, timeout=RECOVERY_LEDGER_LOCK_TIMEOUT_SECONDS
            ):
                current_rows = ledger._scan_unlocked()
                current_records = _recovery_typed_rows(
                    current_rows, typed.request_id
                )
                terminal = _terminal_recovery_outcome(current_records)
                if terminal is not None:
                    return _validate_terminal_recovery_replay(
                        terminal, current_records, typed, receipt, adapters
                    )
            owner_live = _recovery_owner_is_live(owner_pid, owner_start)
            now = time.monotonic()
            if not owner_live or now >= deadline:
                break
            time.sleep(min(RECOVERY_OWNER_POLL_SECONDS, deadline - now))
        # Close the owner-exit/terminal-write race with one final durable read.
        with InterProcessLock(
            ledger.lock_path, timeout=RECOVERY_LEDGER_LOCK_TIMEOUT_SECONDS
        ):
            current_rows = ledger._scan_unlocked()
            current_records = _recovery_typed_rows(current_rows, typed.request_id)
            terminal = _terminal_recovery_outcome(current_records)
            if terminal is not None:
                return _validate_terminal_recovery_replay(
                    terminal, current_records, typed, receipt, adapters
                )
        if owner_live and _recovery_owner_is_live(owner_pid, owner_start):
            return _recovery_outcome(
                typed,
                receipt,
                result=ResultClass.UNCERTAIN_EFFECT,
                effect_started=True,
                observation={"state": "EFFECT_STARTED", "owner_live": True},
            )
    ack: RecoveryEffectAck | None = None
    if invoke_effect:
        try:
            ack = adapters.effect(plan)
            adapters.crash_hook("after_effect_call_before_ack")
            validate_recovery_effect_ack(ack, plan=plan)
            adapters.crash_hook("after_effect_success_before_observation")
        except Exception as exc:
            with InterProcessLock(
                ledger.lock_path, timeout=RECOVERY_LEDGER_LOCK_TIMEOUT_SECONDS
            ):
                rows = ledger._scan_unlocked()
                records = _recovery_typed_rows(rows, typed.request_id)
                if records[-1].state is DeploymentState.EFFECT_STARTED:
                    _append_recovery_state_unlocked(
                        ledger,
                        rows,
                        typed,
                        receipt,
                        evidence,
                        DeploymentState.UNCERTAIN_EFFECT,
                        observed_identity={"error": type(exc).__name__},
                    )
            return _recovery_outcome(
                typed,
                receipt,
                result=ResultClass.UNCERTAIN_EFFECT,
                effect_started=True,
                observation={"state": "UNCERTAIN_EFFECT"},
            )
    identity = adapters.observe(plan)
    classification = _gateway_reconcile_physical(typed, receipt, identity)
    with InterProcessLock(
        ledger.lock_path, timeout=RECOVERY_LEDGER_LOCK_TIMEOUT_SECONDS
    ):
        rows = ledger._scan_unlocked()
        records = _recovery_typed_rows(rows, typed.request_id)
        terminal = _terminal_recovery_outcome(records)
        if terminal is not None:
            return _validate_terminal_recovery_replay(
                terminal, records, typed, receipt, adapters
            )
        state = records[-1].state
        if classification == "predecessor":
            if state is DeploymentState.EFFECT_STARTED:
                _append_recovery_state_unlocked(
                    ledger, rows, typed, receipt, evidence,
                    DeploymentState.UNCERTAIN_EFFECT,
                )
            outcome = _recovery_outcome(
                typed,
                receipt,
                result=ResultClass.ROLLED_BACK,
                effect_started=True,
                observation={"state": "ROLLED_BACK"},
            )
            _append_recovery_state_unlocked(
                ledger,
                rows,
                typed,
                receipt,
                evidence,
                DeploymentState.ROLLED_BACK,
                observed_identity={"outcome": outcome.model_dump()},
            )
            return outcome
        if classification != "desired":
            if state is not DeploymentState.UNCERTAIN_EFFECT:
                _append_recovery_state_unlocked(
                    ledger, rows, typed, receipt, evidence,
                    DeploymentState.UNCERTAIN_EFFECT,
                )
            outcome = _recovery_outcome(
                typed,
                receipt,
                result=ResultClass.BLOCKED,
                effect_started=True,
                observation={"state": "BLOCKED"},
            )
            _append_recovery_state_unlocked(
                ledger,
                rows,
                typed,
                receipt,
                evidence,
                DeploymentState.BLOCKED,
                observed_identity={"outcome": outcome.model_dump()},
            )
            return outcome
        ack_view = (
            {
                "acknowledged": ack.acknowledged,
                "applied": ack.applied,
                "already_desired": ack.already_desired,
            }
            if ack is not None
            else {}
        )
        if state in {
            DeploymentState.EFFECT_STARTED,
            DeploymentState.UNCERTAIN_EFFECT,
        }:
            _append_recovery_state_unlocked(
                ledger,
                rows,
                typed,
                receipt,
                evidence,
                DeploymentState.SERVICE_OBSERVED,
                observed_identity={"physical": identity.model_dump(), "ack": ack_view},
            )
            state = DeploymentState.SERVICE_OBSERVED
            adapters.crash_hook("after_service_observed")
        if state is DeploymentState.SERVICE_OBSERVED:
            _append_recovery_state_unlocked(
                ledger,
                rows,
                typed,
                receipt,
                evidence,
                DeploymentState.IDENTITY_VERIFIED,
                observed_identity={"physical": identity.model_dump(), "ack": ack_view},
            )
            state = DeploymentState.IDENTITY_VERIFIED
            adapters.crash_hook("after_identity_verified")
    try:
        postflight = adapters.postflight(plan, identity)
        _validate_recovery_postflight(postflight, identity, receipt)
    except Exception as exc:
        with InterProcessLock(
            ledger.lock_path, timeout=RECOVERY_LEDGER_LOCK_TIMEOUT_SECONDS
        ):
            rows = ledger._scan_unlocked()
            records = _recovery_typed_rows(rows, typed.request_id)
            lost_ack_reconcile = (
                not invoke_effect
                and any(
                    record.state is DeploymentState.UNCERTAIN_EFFECT
                    and record.observed_identity.get("error") == "TimeoutError"
                    for record in records
                )
            )
            if lost_ack_reconcile:
                if records[-1].state is not DeploymentState.UNCERTAIN_EFFECT:
                    _append_recovery_state_unlocked(
                        ledger,
                        rows,
                        typed,
                        receipt,
                        evidence,
                        DeploymentState.UNCERTAIN_EFFECT,
                        observed_identity={"error": type(exc).__name__},
                    )
                outcome = _recovery_outcome(
                    typed,
                    receipt,
                    result=ResultClass.BLOCKED,
                    effect_started=True,
                    observation={"state": "BLOCKED"},
                )
                _append_recovery_state_unlocked(
                    ledger,
                    rows,
                    typed,
                    receipt,
                    evidence,
                    DeploymentState.BLOCKED,
                    observed_identity={
                        "error": type(exc).__name__,
                        "outcome": outcome.model_dump(),
                    },
                )
                return outcome
            if records[-1].state is not DeploymentState.UNCERTAIN_EFFECT:
                _append_recovery_state_unlocked(
                    ledger,
                    rows,
                    typed,
                    receipt,
                    evidence,
                    DeploymentState.UNCERTAIN_EFFECT,
                    observed_identity={"error": type(exc).__name__},
                )
        return _recovery_outcome(
            typed,
            receipt,
            result=ResultClass.UNCERTAIN_EFFECT,
            effect_started=True,
            observation={"state": "UNCERTAIN_EFFECT"},
        )
    with InterProcessLock(
        ledger.lock_path, timeout=RECOVERY_LEDGER_LOCK_TIMEOUT_SECONDS
    ):
        rows = ledger._scan_unlocked()
        records = _recovery_typed_rows(rows, typed.request_id)
        terminal = _terminal_recovery_outcome(records)
        if terminal is not None:
            return _validate_terminal_recovery_replay(
                terminal, records, typed, receipt, adapters
            )
        state = records[-1].state
        if state is DeploymentState.IDENTITY_VERIFIED:
            _append_recovery_state_unlocked(
                ledger,
                rows,
                typed,
                receipt,
                evidence,
                DeploymentState.CLIENT_BOUND,
                observed_identity={"postflight": dict(postflight), "ack": ack_view},
            )
            adapters.crash_hook("after_client_bound")
        outcome = _recovery_outcome(
            typed,
            receipt,
            result=ResultClass.VERIFIED,
            effect_started=True,
            observation={"state": "VERIFIED", "deployment_id": identity.deployment_id},
        )
        _append_recovery_state_unlocked(
            ledger,
            rows,
            typed,
            receipt,
            evidence,
            DeploymentState.VERIFIED,
            observed_identity={"ack": ack_view, "outcome": outcome.model_dump()},
        )
        return outcome


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
    action: str, request: GatewayDeploymentRequest | GatewayRecoveryRequest | Mapping[str, Any]
) -> GatewayDeploymentRequest | GatewayRecoveryRequest:
    """Parse and validate the typed request before any physical authority read."""
    try:
        if action == "gateway-recover":
            typed = GatewayRecoveryRequest.model_validate(request)
            validate_recovery_request(typed)
        else:
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
        "gateway-recover": {"gateway-recover"},
    }
    if action not in expected_operation:
        raise _gateway_error("unsupported Gateway-only action")
    if typed.operation not in expected_operation[action]:
        raise _gateway_error("operation substitution rejected")
    return typed


def manage_gateway(action: str, *, request: GatewayDeploymentRequest | GatewayRecoveryRequest | Mapping[str, Any],
                   observed: Mapping[str, Any] | None = None, **kwargs: Any) -> dict[str, Any]:
    """Explicit Gateway-only dispatch; legacy ``manage`` cannot reach this path."""
    # Pairing is deliberately checked while the request is still pure.  A
    # cross-operation request must not cause a canonical store, remote-main,
    # source, or local-Git read merely to discover the mismatch.
    parsed = _validate_gateway_action_pair(action, request)
    if action == "gateway-recover":
        return gateway_recover(parsed)
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
