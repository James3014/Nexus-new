#!/usr/bin/env python3
"""Fail-closed durable LaunchAgent manager (prototype; never activates on import)."""
from __future__ import annotations
import argparse, hashlib, json, os, plistlib, subprocess, tempfile, re, shlex
from pathlib import Path
from typing import Callable

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
    head = verify_gateway(root, launch_floor_head); env_file = read_secret_env()
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
if __name__ == "__main__": raise SystemExit(main())
