#!/usr/bin/env python3
"""Unattended, health-gated MCP Gateway deployer that tracks published main (#2153).

Owner decision (#2153, 2026-10-14): routine Gateway updates no longer go through
the #526 governed rebind.  One cycle (run every few minutes by the LaunchAgent
``com.nexus.gateway-auto-deploy``, see ``install_nexus_gateway_auto_deploy.sh``):

1. Trigger: fetch ``main`` into the existing Gateway bare repository
   (``gateway-direct/repository.git``, private ref ``refs/nexus-auto-deploy/main``).
   Deploy the tip only when the required checks (secret audit, Deletion guard,
   Exact-base impact gate) are green for it, either on the commit itself or on
   the head of the merged PR that produced it.  Anything else, including a
   GitHub error, means no deploy (fail closed).  Main movement that touches only
   docs/tasks/tests/workflow paths is skipped until the Gateway lags by
   ``--max-irrelevant-lag`` commits (#1445).  At most one attempt per
   ``--min-interval`` seconds; a candidate that was already rejected is not retried.
2. Build: ``deployments/a1-<sha>`` is a detached worktree of that bare repository
   (same layout as the #526 ``r1-<sha>`` deployments).  Each deployment gets its
   own venv ``venvs/a1-<sha>`` built by ``uv sync --frozen`` from the deployment's
   ``uv.lock``, so the shared clone's ``.venv`` is never used.  The venv lives
   outside the tree and the tree must still be clean after the build (#1939);
   durable state stays in ``~/.local/state`` (#1539).
3. Probe: start the candidate on a spare loopback port and require ``/health``
   for the exact commit, the candidate's own GB-077 live identity probe, MCP
   ``tools/list`` and ``nexus_gateway_status``.  On failure the live Gateway is
   left untouched.
4. Switch: rewrite the ``com.nexus.mcp.gateway.direct`` plist to the candidate,
   reload it, and probe the real port.  If that fails, restore the exact previous
   plist bytes and reload (automatic rollback).
5. Receipt: one JSON line per attempt in ``<state>/receipts.jsonl``; the last
   poll outcome is in ``<state>/status.json``.  ``check_gateway_source_drift.py``
   reports the last receipt.
6. Retention: keep the newest ``--keep`` ``a1-*`` deployments plus the live and
   previous one; ``r1-*`` deployments are never touched.
7. Kill switch: ``<state>/HOLD`` (``hold``/``release`` subcommands) or
   ``NEXUS_GATEWAY_AUTO_DEPLOY_HOLD=1`` pauses everything.  A failed rollback
   writes HOLD itself.

The LaunchAgent runs this file from ``gateway-direct/auto-deploy-current``, a
symlink the installer points at a bootstrap worktree of main and that every
successful deploy moves to the new deployment, so the deployer updates with the
Gateway.  It needs only the stdlib plus the tree's
``scripts/ops/mcp_gateway_durable.py``, which stays the single owner of the
Gateway launchd effect.  The #526 governed rebind stays available as a manual
fallback.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import plistlib
import re
import shlex
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, List, Optional

if __name__ == "__main__":
    # Run from a Nexus-new tree: the Gateway launchd effect lives in
    # scripts/ops/mcp_gateway_durable.py (single effect owner).
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

# Must equal nexus.contracts.gateway_deployment.LABEL / ENTRYPOINT / ENDPOINT
# (asserted by tests; not imported so this file stays standalone).
GATEWAY_LABEL = "com.nexus.mcp.gateway.direct"
ENTRYPOINT = "scripts/ops/nexus_mcp_gateway_http.py"
LIVE_PORT = 8766
REPOSITORY = "James3014/Nexus-new"
REQUIRED_CHECKS = (
    "Full published Git history secret audit",
    "Deletion guard",
    "Exact-base impact gate",
)
DEPLOYMENT_PREFIX = "a1-"
TRACK_REF = "refs/nexus-auto-deploy/main"
RECEIPT_SCHEMA = "nexus.gateway.auto_deploy_receipt.v1"
STATUS_SCHEMA = "nexus.gateway.auto_deploy_status.v1"
HOLD_ENV = "NEXUS_GATEWAY_AUTO_DEPLOY_HOLD"
TOKEN_ENV = "NEXUS_MCP_GATEWAY_TOKEN"
# Paths that cannot change Gateway behaviour; anything else counts as relevant.
IRRELEVANT_PREFIXES = ("tasks/", "docs/", "tests/", ".github/", "archives/", "artifacts/")
IRRELEVANT_SUFFIXES = (".md",)
REJECTED_OUTCOMES = ("REJECTED_PROBE", "REJECTED_BUILD", "ROLLED_BACK", "ROLLBACK_FAILED")
FAILED_OUTCOMES = REJECTED_OUTCOMES + ("BUILD_FAILED", "BLOCKED_NO_ROLLBACK")
# Open PRs that bump the runtime/dependency pin (or anchor such a bump).  While
# one is in flight no deploy starts, so deploys and pin bumps never interleave.
PIN_BUMP_PR = re.compile(
    r"pin nexus-runtime|pin-runtime|trusted-anchor|dependency.{0,20}transition|autoupdate",
    re.IGNORECASE,
)
_SHA = re.compile(r"^[0-9a-f]{40}$")
_DEPLOYMENT_NAME = re.compile(r"(?:^|/)[ar]1-([0-9a-f]{40})$")
_SHELL_UNSAFE = ('"', "$", "`", "\\", "\n", "\r", "\x00")

GB077_PROBE_CODE = """
import json, sys
root, url, commit = sys.argv[1:4]
sys.path.insert(0, root)
from scripts.ops.run_golden_behavior_eval import _fetch_gateway_health, probe_gb077_live_gateway_identity
ok, detail = probe_gb077_live_gateway_identity(
    fetch_health=lambda: _fetch_gateway_health(url),
    evaluated_identity=lambda: (commit, False),
)
print(detail)
sys.exit(0 if ok else 1)
"""


class DeployError(RuntimeError):
    pass


@dataclass(frozen=True)
class Config:
    gateway_root: Path
    state_dir: Path
    plist: Path
    env_file: Path
    canonical_state_dir: Path
    repository: str = REPOSITORY
    track_branch: str = "main"
    python_version: str = "3.12"
    keep: int = 3
    min_interval_seconds: int = 600
    max_irrelevant_lag: int = 25
    probe_timeout_seconds: float = 120.0

    @classmethod
    def default(cls, home: Optional[Path] = None, **overrides: Any) -> "Config":
        home = Path.home() if home is None else home
        support = home / "Library/Application Support/Nexus"
        values: Dict[str, Any] = {
            "gateway_root": support / "gateway-direct",
            "state_dir": home / ".local/state/nexus-gateway-auto-deploy",
            "plist": home / "Library/LaunchAgents" / f"{GATEWAY_LABEL}.plist",
            "env_file": support / "mcp-gateway.env",
            "canonical_state_dir": home / ".local/state/Nexus-new-self-hosted-state",
        }
        values.update({k: v for k, v in overrides.items() if v is not None})
        return cls(**values)

    @property
    def bare_repo(self) -> Path:
        return self.gateway_root / "repository.git"

    @property
    def deployments(self) -> Path:
        return self.gateway_root / "deployments"

    @property
    def venvs(self) -> Path:
        return self.gateway_root / "venvs"

    @property
    def tool_link(self) -> Path:
        """Tree the auto-deploy LaunchAgent runs this script from (moves to each new deployment)."""
        return self.gateway_root / "auto-deploy-current"

    @property
    def receipts(self) -> Path:
        return self.state_dir / "receipts.jsonl"

    @property
    def hold_file(self) -> Path:
        return self.state_dir / "HOLD"


# --------------------------------------------------------------------------- host


class Host:
    """Every process, launchd and clock effect.  Tests replace this class."""

    def run(
        self,
        argv: List[str],
        *,
        cwd: Optional[Path] = None,
        env: Optional[Dict[str, str]] = None,
        timeout: float = 1800,
    ) -> subprocess.CompletedProcess:
        full_env = dict(os.environ, **(env or {}))
        return subprocess.run(
            argv,
            cwd=str(cwd) if cwd else None,
            env=full_env,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )

    def start(self, command: str, log_path: Path) -> Callable[[], None]:
        """Start a candidate Gateway; return a function that stops it."""
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log = open(log_path, "ab")  # noqa: SIM115 - closed by the returned stop()
        proc = subprocess.Popen(  # noqa: S603 - fixed /bin/zsh wrapper, quoted paths
            ["/bin/zsh", "-c", command],
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=log,
            start_new_session=True,
        )

        def stop() -> None:
            with contextlib.suppress(ProcessLookupError):
                os.killpg(proc.pid, signal.SIGTERM)
            try:
                proc.wait(timeout=15)
            except subprocess.TimeoutExpired:
                with contextlib.suppress(ProcessLookupError):
                    os.killpg(proc.pid, signal.SIGKILL)
                proc.wait(timeout=15)
            log.close()

        return stop

    def reload_service(self, plist: Path, label: str) -> None:
        # The durable manager stays the single Gateway launchd effect owner.
        from scripts.ops.mcp_gateway_durable import reload_gateway_launch_agent

        if label != GATEWAY_LABEL:
            raise DeployError("GATEWAY_LABEL_MISMATCH")
        try:
            reload_gateway_launch_agent(plist)
        except Exception as exc:  # noqa: BLE001
            raise DeployError(f"GATEWAY_RELOAD_FAILED:{exc}") from exc

    def free_port(self) -> int:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("127.0.0.1", 0))
            return int(sock.getsockname()[1])

    def now(self) -> float:
        return time.time()

    def sleep(self, seconds: float) -> None:
        time.sleep(seconds)


def _must(host: Host, argv: List[str], code: str, **kwargs: Any) -> str:
    result = host.run(argv, **kwargs)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()[:300]
        raise DeployError(f"{code}:{detail}")
    return result.stdout


def _git(cfg: Config, *args: str) -> List[str]:
    return ["git", "--git-dir", str(cfg.bare_repo), *args]


# ------------------------------------------------------------------ required checks


def gh_api_getter(host: Host, gh: str = "gh") -> Callable[[str], Any]:
    def get(path: str) -> Any:
        return json.loads(_must(host, [gh, "api", path], "GH_API_FAILED", timeout=60))

    return get


def _latest_run(api_get: Callable[[str], Any], repo: str, sha: str, name: str) -> Optional[dict]:
    query = urllib.parse.urlencode({"check_name": name, "per_page": 100})
    runs = api_get(f"repos/{repo}/commits/{sha}/check-runs?{query}").get("check_runs") or []
    runs = [r for r in runs if r.get("name") == name]
    if not runs:
        return None
    return max(runs, key=lambda r: (r.get("started_at") or "", r.get("id") or 0))


def required_checks(
    api_get: Callable[[str], Any], sha: str, *, repo: str = REPOSITORY, branch: str = "main"
) -> Dict[str, Any]:
    """GREEN only when every required check is success; PENDING, RED or UNKNOWN otherwise."""
    detail: Dict[str, Any] = {}
    try:
        pr_heads: Optional[List[str]] = None
        for name in REQUIRED_CHECKS:
            run = _latest_run(api_get, repo, sha, name)
            source = sha
            if run is None:
                if pr_heads is None:
                    pulls = api_get(f"repos/{repo}/commits/{sha}/pulls") or []
                    pr_heads = [
                        p["head"]["sha"]
                        for p in pulls
                        if p.get("merged_at")
                        and p.get("merge_commit_sha") == sha
                        and (p.get("base") or {}).get("ref") == branch
                    ]
                for head in pr_heads:
                    run = _latest_run(api_get, repo, head, name)
                    if run is not None:
                        source = head
                        break
            if run is None:
                detail[name] = {"state": "MISSING"}
            elif run.get("status") != "completed":
                detail[name] = {"state": "PENDING", "sha": source}
            else:
                state = "SUCCESS" if run.get("conclusion") == "success" else "FAILURE"
                detail[name] = {"state": state, "conclusion": run.get("conclusion"), "sha": source}
    except Exception as exc:  # noqa: BLE001 - any transport/shape error fails closed
        return {
            "verdict": "UNKNOWN",
            "error": f"{type(exc).__name__}:{exc}"[:300],
            "checks": detail,
        }
    states = {d["state"] for d in detail.values()}
    if states == {"SUCCESS"}:
        verdict = "GREEN"
    elif "FAILURE" in states:
        verdict = "RED"
    elif "MISSING" in states:
        verdict = "UNKNOWN"
    else:
        verdict = "PENDING"
    return {"verdict": verdict, "checks": detail}


def pin_bumps_in_flight(api_get: Callable[[str], Any], *, repo: str = REPOSITORY) -> Dict[str, Any]:
    """Open pin-bump PRs; ``verdict`` is CLEAR, IN_FLIGHT or UNKNOWN (fail closed)."""
    try:
        pulls = api_get(f"repos/{repo}/pulls?state=open&per_page=100") or []
        hits = [
            p["number"]
            for p in pulls
            if PIN_BUMP_PR.search(
                f"{p.get('title') or ''} {(p.get('head') or {}).get('ref') or ''}"
            )
        ]
    except Exception as exc:  # noqa: BLE001
        return {"verdict": "UNKNOWN", "error": f"{type(exc).__name__}:{exc}"[:300]}
    return {"verdict": "IN_FLIGHT" if hits else "CLEAR", "pull_requests": sorted(hits)}


# ------------------------------------------------------------------------- probes


def read_env_token(env_file: Path) -> str:
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        key, sep, value = line.partition("=")
        if sep and key.strip() == TOKEN_ENV:
            parts = shlex.split(value)
            if parts and parts[0]:
                return parts[0]
    raise DeployError("GATEWAY_TOKEN_UNAVAILABLE")


class Prober:
    """Smoke probe of one Gateway instance.  Tests replace this class."""

    def __init__(self, host: Host) -> None:
        self.host = host

    def _http(self, url: str, *, body: Optional[dict] = None, token: str = "") -> Any:
        data = None if body is None else json.dumps(body).encode("utf-8")
        request = urllib.request.Request(url, data=data, method="GET" if body is None else "POST")
        if body is not None:
            request.add_header("Content-Type", "application/json")
            request.add_header("Authorization", f"Bearer {token}")
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(request, timeout=30) as response:
            return json.loads(response.read(8 * 1024 * 1024).decode("utf-8"))

    def probe(
        self, *, port: int, token: str, commit: str, root: Path, python: Path, timeout: float
    ) -> Dict[str, Any]:
        base = f"http://127.0.0.1:{port}"
        checks: Dict[str, Any] = {}
        deadline = self.host.now() + timeout
        observed: Any = None
        while True:
            try:
                observed = self._http(f"{base}/health")
                if isinstance(observed, dict) and observed.get("git_head") == commit:
                    break
            except Exception as exc:  # noqa: BLE001 - not up yet
                observed = f"{type(exc).__name__}"
            if self.host.now() >= deadline:
                checks["health"] = {"ok": False, "observed": observed}
                return {"ok": False, "checks": checks}
            self.host.sleep(2)
        checks["health"] = {"ok": observed.get("status") == "ok", "status": observed.get("status")}
        gb077 = self.host.run(
            [str(python), "-c", GB077_PROBE_CODE, str(root), f"{base}/health", commit],
            env={"PYTHONDONTWRITEBYTECODE": "1"},
            timeout=60,
        )
        checks["gb077"] = {"ok": gb077.returncode == 0, "detail": gb077.stdout.strip()[-2000:]}
        try:
            tools = self._http(
                f"{base}/mcp", body={"jsonrpc": "2.0", "id": 1, "method": "tools/list"}, token=token
            )
            count = len(tools["result"]["tools"])
            checks["tools_list"] = {"ok": count > 0, "tool_count": count}
        except Exception as exc:  # noqa: BLE001
            checks["tools_list"] = {"ok": False, "error": f"{type(exc).__name__}:{exc}"[:300]}
        try:
            call = {"name": "nexus_gateway_status", "arguments": {}}
            status = self._http(
                f"{base}/mcp",
                body={"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": call},
                token=token,
            )
            checks["gateway_status"] = {"ok": status.get("result", {}).get("isError") is False}
        except Exception as exc:  # noqa: BLE001
            checks["gateway_status"] = {"ok": False, "error": f"{type(exc).__name__}:{exc}"[:300]}
        return {"ok": all(c["ok"] for c in checks.values()), "checks": checks}


# --------------------------------------------------------------------- deployment


def wrapper_command(cfg: Config, root: Path, python: Path, port: Optional[int] = None) -> str:
    """The same fixed zsh wrapper as the #526 deployments, with a per-deployment venv."""
    for value in (str(root), str(python), str(cfg.env_file), str(cfg.canonical_state_dir)):
        if any(token in value for token in _SHELL_UNSAFE):
            raise DeployError("WRAPPER_PATH_UNSAFE")
    port_export = "" if port is None else f"export NEXUS_MCP_GATEWAY_PORT={int(port)} ; "
    return (
        f'cd "{root}" ; source "{cfg.env_file}" ; export PYTHONDONTWRITEBYTECODE=1 ; '
        f'export NEXUS_CANONICAL_SOURCE_ROOT="{root}" ; '
        f'export NEXUS_SELF_HOSTED_CANONICAL_STATE_DIR="{cfg.canonical_state_dir}" ; '
        f'{port_export}exec "{python}" "{root / ENTRYPOINT}"'
    )


def live_root(plist_bytes: bytes) -> Optional[Path]:
    data = plistlib.loads(plist_bytes)
    if data.get("Label") != GATEWAY_LABEL:
        raise DeployError("GATEWAY_PLIST_LABEL_MISMATCH")
    root = data.get("WorkingDirectory")
    if isinstance(root, str) and root:
        return Path(root)
    match = re.search(r'NEXUS_CANONICAL_SOURCE_ROOT="([^"]+)"', " ".join(data["ProgramArguments"]))
    return Path(match.group(1)) if match else None


def live_python(plist_bytes: bytes) -> Optional[Path]:
    command = " ".join(plistlib.loads(plist_bytes).get("ProgramArguments") or [])
    match = re.search(r'exec "?([^" ]+)"? ', command)
    return Path(match.group(1)) if match else None


def commit_of(root: Optional[Path]) -> Optional[str]:
    match = _DEPLOYMENT_NAME.search(str(root)) if root else None
    return match.group(1) if match else None


def render_plist(previous: bytes, command: str, root: Path) -> bytes:
    data = plistlib.loads(previous)
    if data.get("Label") != GATEWAY_LABEL:
        raise DeployError("GATEWAY_PLIST_LABEL_MISMATCH")
    data["ProgramArguments"] = ["/bin/zsh", "-c", command]
    data["WorkingDirectory"] = str(root)
    return plistlib.dumps(data, sort_keys=True)


def _atomic_write(path: Path, data: bytes, mode: int = 0o644) -> None:
    tmp = path.with_name(f".{path.name}.tmp.{os.getpid()}")
    tmp.write_bytes(data)
    os.chmod(tmp, mode)
    os.replace(tmp, path)


def _atomic_symlink(target: Path, link: Path) -> None:
    tmp = link.with_name(f".{link.name}.tmp.{os.getpid()}")
    with contextlib.suppress(FileNotFoundError):
        tmp.unlink()
    os.symlink(str(target), str(tmp))
    os.replace(tmp, link)


def is_irrelevant(path: str) -> bool:
    return path.startswith(IRRELEVANT_PREFIXES) or (
        "/" not in path and path.endswith(IRRELEVANT_SUFFIXES)
    )


def build(cfg: Config, host: Host, commit: str) -> Dict[str, Any]:
    """Materialize the immutable deployment and its dedicated venv."""
    root = cfg.deployments / f"{DEPLOYMENT_PREFIX}{commit}"
    venv = cfg.venvs / f"{DEPLOYMENT_PREFIX}{commit}"
    if not root.exists():
        _must(
            host, _git(cfg, "worktree", "add", "--detach", str(root), commit), "WORKTREE_ADD_FAILED"
        )
    head = _must(
        host, ["git", "-C", str(root), "rev-parse", "HEAD"], "WORKTREE_HEAD_FAILED"
    ).strip()
    if head != commit:
        raise DeployError(f"WORKTREE_HEAD_MISMATCH:{head}")
    cfg.venvs.mkdir(parents=True, exist_ok=True)
    _must(
        host,
        [
            "uv",
            "sync",
            "--frozen",
            "--all-extras",
            "--no-install-project",
            "--python",
            cfg.python_version,
            "--project",
            str(root),
        ],
        "VENV_SYNC_FAILED",
        cwd=root,
        env={"UV_PROJECT_ENVIRONMENT": str(venv)},
    )
    python = venv / "bin" / "python"
    if not python.exists():
        raise DeployError("VENV_PYTHON_MISSING")
    dirty = _must(host, ["git", "-C", str(root), "status", "--porcelain"], "WORKTREE_STATUS_FAILED")
    if dirty.strip():
        raise DeployError("SOURCE_TREE_WRITTEN_BY_BUILD")
    lock = root / "uv.lock"
    return {
        "deployment_root": str(root),
        "venv": str(venv),
        "venv_python": str(python),
        "uv_lock_sha256": hashlib.sha256(lock.read_bytes()).hexdigest() if lock.exists() else None,
    }


def prune(cfg: Config, host: Host, protected: List[Optional[Path]]) -> List[str]:
    """Keep the newest ``cfg.keep`` a1-* deployments plus every protected one."""
    if not cfg.deployments.is_dir():
        return []
    keep_names = {p.name for p in protected if p is not None}
    candidates = sorted(
        (
            p
            for p in cfg.deployments.iterdir()
            if p.name.startswith(DEPLOYMENT_PREFIX) and p.is_dir()
        ),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    removed: List[str] = []
    for index, path in enumerate(candidates):
        if index < cfg.keep or path.name in keep_names:
            continue
        host.run(_git(cfg, "worktree", "remove", "--force", str(path)), timeout=300)
        shutil.rmtree(path, ignore_errors=True)
        shutil.rmtree(cfg.venvs / path.name, ignore_errors=True)
        removed.append(path.name)
    if cfg.venvs.is_dir():
        live = {p.name for p in cfg.deployments.iterdir()}
        for venv in cfg.venvs.iterdir():
            if venv.name.startswith(DEPLOYMENT_PREFIX) and venv.name not in live:
                shutil.rmtree(venv, ignore_errors=True)
    return removed


# ----------------------------------------------------------------- receipts/state


def _iso(epoch: float) -> str:
    return datetime.fromtimestamp(epoch, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def read_receipts(state_dir: Path) -> List[Dict[str, Any]]:
    path = state_dir / "receipts.jsonl"
    if not path.is_file():
        return []
    receipts = []
    for line in path.read_text(encoding="utf-8").splitlines():
        with contextlib.suppress(ValueError):
            item = json.loads(line)
            if isinstance(item, dict) and item.get("schema") == RECEIPT_SCHEMA:
                receipts.append(item)
    return receipts


def last_receipt(state_dir: Path) -> Optional[Dict[str, Any]]:
    receipts = read_receipts(state_dir)
    return receipts[-1] if receipts else None


def _append_receipt(cfg: Config, receipt: Dict[str, Any]) -> None:
    cfg.state_dir.mkdir(parents=True, exist_ok=True)
    line = json.dumps(receipt, sort_keys=True, separators=(",", ":")) + "\n"
    with open(cfg.receipts, "a", encoding="utf-8") as handle:
        handle.write(line)
        handle.flush()
        os.fsync(handle.fileno())


def hold_reason(cfg: Config, environ: Optional[Dict[str, str]] = None) -> Optional[str]:
    env = os.environ if environ is None else environ
    if env.get(HOLD_ENV, "") not in ("", "0"):
        return f"env:{HOLD_ENV}"
    if cfg.hold_file.exists():
        return f"file:{cfg.hold_file}"
    return None


@contextlib.contextmanager
def _cycle_lock(cfg: Config) -> Iterator[bool]:
    import fcntl

    cfg.state_dir.mkdir(parents=True, exist_ok=True)
    with open(cfg.state_dir / ".lock", "w", encoding="utf-8") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            yield False
            return
        yield True


# -------------------------------------------------------------------------- cycle


def run_cycle(
    cfg: Config,
    host: Host,
    prober: Prober,
    api_get: Callable[[str], Any],
    *,
    dry_run: bool = False,
    force: bool = False,
    environ: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    started = host.now()
    status: Dict[str, Any] = {
        "schema": STATUS_SCHEMA,
        "polled_at": _iso(started),
        "dry_run": dry_run,
    }
    held = hold_reason(cfg, environ)
    if held:
        return {**status, "status": "HELD", "hold": held}
    with _cycle_lock(cfg) as acquired:
        if not acquired:
            return {**status, "status": "BUSY"}
        result = _cycle(cfg, host, prober, api_get, status, dry_run=dry_run, force=force)
    if not dry_run:
        _atomic_write(
            cfg.state_dir / "status.json", json.dumps(result, sort_keys=True).encode(), 0o600
        )
    return result


def _cycle(
    cfg: Config,
    host: Host,
    prober: Prober,
    api_get: Callable[[str], Any],
    status: Dict[str, Any],
    *,
    dry_run: bool,
    force: bool,
) -> Dict[str, Any]:
    _must(
        host,
        _git(
            cfg,
            "fetch",
            "--quiet",
            "--no-tags",
            "origin",
            f"+refs/heads/{cfg.track_branch}:{TRACK_REF}",
        ),
        "FETCH_FAILED",
        timeout=300,
    )
    candidate = _must(
        host, _git(cfg, "rev-parse", f"{TRACK_REF}^{{commit}}"), "TRACK_REF_FAILED"
    ).strip()
    if not _SHA.match(candidate):
        raise DeployError("TRACK_REF_NOT_A_COMMIT")
    previous_plist = cfg.plist.read_bytes()
    previous_root = live_root(previous_plist)
    previous_commit = commit_of(previous_root)
    status.update(
        candidate_commit=candidate, live_commit=previous_commit, live_root=str(previous_root)
    )

    def finish(state: str, **extra: Any) -> Dict[str, Any]:
        if not dry_run and state not in ("PLAN",):
            tool = Path(os.path.realpath(cfg.tool_link)) if cfg.tool_link.is_symlink() else None
            removed = prune(cfg, host, [previous_root, _current_root(cfg), tool])
            if removed:
                extra["pruned"] = removed
        return {**status, "status": state, **extra}

    if candidate == previous_commit:
        return finish("IN_SYNC")
    receipts = read_receipts(cfg.state_dir)
    if not force and any(
        r.get("candidate_commit") == candidate and r.get("outcome") in REJECTED_OUTCOMES
        for r in receipts
    ):
        return finish("CANDIDATE_REJECTED_BEFORE")
    checks = required_checks(api_get, candidate, repo=cfg.repository, branch=cfg.track_branch)
    status["required_checks"] = checks
    if checks["verdict"] != "GREEN":
        return finish(f"CHECKS_{checks['verdict']}")
    pins = pin_bumps_in_flight(api_get, repo=cfg.repository)
    status["pin_bumps"] = pins
    if pins["verdict"] != "CLEAR":
        return finish(f"PIN_BUMP_{pins['verdict']}")
    if previous_commit and not force:
        diff = host.run(_git(cfg, "diff", "--name-only", previous_commit, candidate))
        count = host.run(_git(cfg, "rev-list", "--count", f"{previous_commit}..{candidate}"))
        if diff.returncode == 0 and count.returncode == 0:
            changed = [p for p in diff.stdout.splitlines() if p]
            behind = int(count.stdout.strip() or 0)
            status.update(changed_path_count=len(changed), behind=behind)
            if all(is_irrelevant(p) for p in changed) and behind < cfg.max_irrelevant_lag:
                return finish("SKIPPED_IRRELEVANT")
    if receipts and not force:
        last_started = receipts[-1].get("started_epoch", 0)
        if host.now() - float(last_started) < cfg.min_interval_seconds:
            return finish("DEBOUNCED")
    root = cfg.deployments / f"{DEPLOYMENT_PREFIX}{candidate}"
    venv_python = cfg.venvs / f"{DEPLOYMENT_PREFIX}{candidate}" / "bin" / "python"
    if dry_run:
        return finish(
            "PLAN",
            plan={
                "deployment_root": str(root),
                "venv_python": str(venv_python),
                "steps": [
                    "build worktree + venv (uv sync --frozen)",
                    "probe on spare port",
                    f"rewrite {cfg.plist}",
                    f"reload {GATEWAY_LABEL}",
                    f"probe port {LIVE_PORT}",
                    "rollback to previous plist on failure",
                ],
                "live_command": wrapper_command(cfg, root, venv_python),
            },
        )
    receipt = _attempt(cfg, host, prober, candidate, previous_plist, previous_root, checks)
    status["receipt"] = receipt
    return finish(receipt["outcome"])


def _current_root(cfg: Config) -> Optional[Path]:
    with contextlib.suppress(Exception):
        return live_root(cfg.plist.read_bytes())
    return None


def _attempt(
    cfg: Config,
    host: Host,
    prober: Prober,
    candidate: str,
    previous_plist: bytes,
    previous_root: Optional[Path],
    checks: Dict[str, Any],
) -> Dict[str, Any]:
    started = host.now()
    receipt: Dict[str, Any] = {
        "schema": RECEIPT_SCHEMA,
        "attempt_id": f"{candidate[:12]}-{int(started)}",
        "candidate_commit": candidate,
        "previous_commit": commit_of(previous_root),
        "previous_root": str(previous_root),
        "required_checks": checks,
        "started_at": _iso(started),
        "started_epoch": started,
        "switched": False,
        "rolled_back": False,
        "probes": {},
    }
    try:
        receipt.update(
            _attempt_effects(cfg, host, prober, candidate, previous_plist, previous_root, receipt)
        )
    except Exception as exc:  # noqa: BLE001 - every failure must still leave a receipt
        receipt["reason"] = f"{type(exc).__name__}:{exc}"[:500]
        if receipt["switched"] and not receipt["rolled_back"]:
            receipt.update(_rollback(cfg, host, prober, previous_plist, receipt))
        elif str(exc).startswith("SOURCE_TREE_WRITTEN"):
            receipt["outcome"] = "REJECTED_BUILD"
        else:
            receipt["outcome"] = "BUILD_FAILED"
    finished = host.now()
    receipt.update(finished_at=_iso(finished), duration_seconds=round(finished - started, 3))
    _append_receipt(cfg, receipt)
    if receipt["outcome"] == "ROLLBACK_FAILED":
        cfg.hold_file.write_text(
            f"auto-hold after ROLLBACK_FAILED {receipt['attempt_id']}\n", encoding="utf-8"
        )
    return receipt


def _attempt_effects(
    cfg: Config,
    host: Host,
    prober: Prober,
    candidate: str,
    previous_plist: bytes,
    previous_root: Optional[Path],
    receipt: Dict[str, Any],
) -> Dict[str, Any]:
    built = build(cfg, host, candidate)
    receipt.update(built)
    root, python = Path(built["deployment_root"]), Path(built["venv_python"])
    token = read_env_token(cfg.env_file)
    logs = cfg.state_dir / "logs"

    port = host.free_port()
    stop = host.start(
        wrapper_command(cfg, root, python, port), logs / f"{receipt['attempt_id']}.probe.log"
    )
    try:
        spare = prober.probe(
            port=port,
            token=token,
            commit=candidate,
            root=root,
            python=python,
            timeout=cfg.probe_timeout_seconds,
        )
    finally:
        stop()
    receipt["probes"]["spare"] = {"port": port, **spare}
    if not spare["ok"]:
        return {"outcome": "REJECTED_PROBE", "reason": "candidate failed the spare-port probe"}

    readiness = rollback_readiness(host, previous_plist)
    receipt["rollback_readiness"] = readiness
    if not readiness["ok"]:
        return {"outcome": "BLOCKED_NO_ROLLBACK", "reason": readiness["reason"]}

    _atomic_write(cfg.plist, render_plist(previous_plist, wrapper_command(cfg, root, python), root))
    receipt["switched"] = True
    try:
        host.reload_service(cfg.plist, GATEWAY_LABEL)
        live = prober.probe(
            port=LIVE_PORT,
            token=token,
            commit=candidate,
            root=root,
            python=python,
            timeout=cfg.probe_timeout_seconds,
        )
    except DeployError as exc:
        live = {"ok": False, "error": str(exc)[:300]}
    receipt["probes"]["live"] = live
    if live["ok"]:
        _atomic_symlink(root, cfg.tool_link)
        return {"outcome": "DEPLOYED"}

    receipt["reason"] = "candidate failed the live probe"
    return _rollback(cfg, host, prober, previous_plist, receipt)


def rollback_readiness(host: Host, previous_plist: bytes) -> Dict[str, Any]:
    """Refuse to switch unless the predecessor deployment could be restarted and re-probed."""
    root = live_root(previous_plist)
    python = live_python(previous_plist)
    if not commit_of(root):
        return {"ok": False, "reason": "PREDECESSOR_COMMIT_UNKNOWN"}
    if root is None or not (root / ENTRYPOINT).is_file():
        return {"ok": False, "reason": "PREDECESSOR_DEPLOYMENT_MISSING"}
    if python is None or not python.exists():
        return {"ok": False, "reason": "PREDECESSOR_PYTHON_MISSING"}
    result = host.run([str(python), "-c", "import sys"], timeout=60)
    if result.returncode != 0:
        return {"ok": False, "reason": "PREDECESSOR_PYTHON_NOT_RUNNABLE"}
    return {"ok": True, "root": str(root), "python": str(python)}


def _rollback(
    cfg: Config, host: Host, prober: Prober, previous_plist: bytes, receipt: Dict[str, Any]
) -> Dict[str, Any]:
    """Restore the exact previous plist bytes, reload, and re-probe the previous deployment."""
    receipt["rolled_back"] = True
    previous_root = live_root(previous_plist)
    previous_commit = commit_of(previous_root)
    previous_python = live_python(previous_plist)
    try:
        _atomic_write(cfg.plist, previous_plist)
        host.reload_service(cfg.plist, GATEWAY_LABEL)
        if previous_commit and previous_root and previous_python:
            restored = prober.probe(
                port=LIVE_PORT,
                token=read_env_token(cfg.env_file),
                commit=previous_commit,
                root=previous_root,
                python=previous_python,
                timeout=cfg.probe_timeout_seconds,
            )
        else:
            restored = {
                "ok": False,
                "error": "previous identity unknown; restored plist bytes only",
            }
    except Exception as exc:  # noqa: BLE001
        restored = {"ok": False, "error": f"{type(exc).__name__}:{exc}"[:300]}
    receipt["probes"]["rollback"] = restored
    return {"outcome": "ROLLED_BACK" if restored["ok"] else "ROLLBACK_FAILED"}


# ---------------------------------------------------------------------------- cli


def main(
    argv: Optional[List[str]] = None,
    *,
    host: Optional[Host] = None,
    prober: Optional[Prober] = None,
    api_get: Optional[Callable[[str], Any]] = None,
) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("command", choices=("run", "status", "hold", "release"))
    parser.add_argument(
        "--dry-run", action="store_true", help="print the plan; no build, launchd or prune"
    )
    parser.add_argument(
        "--force", action="store_true", help="ignore debounce, relevance and earlier rejection"
    )
    parser.add_argument(
        "--reason", default="manual hold", help="hold: reason written to the HOLD file"
    )
    parser.add_argument("--home", type=Path, default=None)
    parser.add_argument("--state-dir", type=Path, default=None)
    parser.add_argument("--gateway-root", type=Path, default=None)
    parser.add_argument("--plist", type=Path, default=None)
    parser.add_argument("--gh", default="gh", help="gh executable used for the check-runs API")
    parser.add_argument("--keep", type=int, default=None)
    parser.add_argument("--min-interval", type=int, default=None, dest="min_interval_seconds")
    parser.add_argument("--max-irrelevant-lag", type=int, default=None)
    parser.add_argument("--python-version", default=None)
    args = parser.parse_args(argv)
    cfg = Config.default(
        args.home,
        state_dir=args.state_dir,
        gateway_root=args.gateway_root,
        plist=args.plist,
        keep=args.keep,
        min_interval_seconds=args.min_interval_seconds,
        max_irrelevant_lag=args.max_irrelevant_lag,
        python_version=args.python_version,
    )
    if args.command == "hold":
        cfg.state_dir.mkdir(parents=True, exist_ok=True)
        cfg.hold_file.write_text(args.reason + "\n", encoding="utf-8")
        print(json.dumps({"status": "HELD", "hold": str(cfg.hold_file)}))
        return 0
    if args.command == "release":
        with contextlib.suppress(FileNotFoundError):
            cfg.hold_file.unlink()
        print(json.dumps({"status": "RELEASED"}))
        return 0
    if args.command == "status":
        state = cfg.state_dir / "status.json"
        print(
            json.dumps(
                {
                    "hold": hold_reason(cfg),
                    "status": json.loads(state.read_text(encoding="utf-8"))
                    if state.is_file()
                    else None,
                    "last_receipt": last_receipt(cfg.state_dir),
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    if not args.dry_run and os.environ.get(TOKEN_ENV):
        # The Gateway wrapper sources the token; a deploy started from inside the
        # Gateway would kill itself mid-switch.  Run it out of process only.
        print(
            json.dumps({"schema": STATUS_SCHEMA, "status": "ERROR", "error": "IN_GATEWAY_PROCESS"})
        )
        return 2
    host = host or Host()
    try:
        result = run_cycle(
            cfg,
            host,
            prober or Prober(host),
            api_get or gh_api_getter(host, args.gh),
            dry_run=args.dry_run,
            force=args.force,
        )
    except (DeployError, OSError, ValueError) as exc:
        print(json.dumps({"schema": STATUS_SCHEMA, "status": "ERROR", "error": str(exc)[:500]}))
        return 2
    print(json.dumps(result, indent=2 if args.dry_run else None, sort_keys=True))
    return 1 if result["status"] in FAILED_OUTCOMES else 0


if __name__ == "__main__":
    raise SystemExit(main())
