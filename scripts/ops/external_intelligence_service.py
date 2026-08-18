from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
import signal
import subprocess
import sys
import tempfile
import time
import uuid
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Mapping

from nexus.services.external_intelligence import (
    ExternalIntelligenceSidecar,
    ExternalIntelligenceStore,
    OpenCLIExternalIntelligenceTransport,
)
from nexus.services.external_intelligence_automation import (
    AutomationStateStore,
    ExternalIntelligenceAutomation,
    _normalize_github_repo,
)
from nexus.services.external_intelligence_closure import (
    ClosureStore,
    CompositionWorkspaceAllocator,
    ExternalIntelligenceClosureRuntime,
)
from nexus.services.external_intelligence_fanout import (
    AdaptiveDeepSeekFanoutRuntime,
    FanoutStore,
    GitWorktreeAllocator,
    OpenCodeDeepSeekTransport,
)

SERVICE_LABEL = "com.nexus.external-intelligence"
DEFAULT_CONFIG = Path.home() / ".config" / "nexus-external-intelligence" / "config.json"
READINESS_SUCCESS_THRESHOLD = 2
SERVICE_HEARTBEAT_STALE_SECONDS = 180.0


class ServiceReadiness(str, Enum):
    READY = "READY"
    STARTING = "STARTING"
    DEGRADED = "DEGRADED"
    STALE = "STALE"
    IDENTITY_MISMATCH = "IDENTITY_MISMATCH"
    DUPLICATE_PROCESS = "DUPLICATE_PROCESS"
    STOPPED = "STOPPED"


class ServiceError(RuntimeError):
    pass


@dataclass(frozen=True)
class ServiceConfig:
    repositories: tuple[str, ...]
    repository_roots: Mapping[str, str]
    state_root: Path
    workspace_root: Path
    label: str = "nexus:external-intelligence"
    poll_interval_seconds: int = 60
    opencli_executable: str = "opencli"
    opencli_profile: str = ""
    opencode_executable: str = "opencode"
    publication_enabled: bool = True
    requested_concurrency: int = 2
    provider_available: int = 2
    workspace_available: int = 2
    controller_attention_limit: int = 2
    max_repairs_per_unit: int = 1


def _service_receipt_path(config: ServiceConfig) -> Path:
    return config.state_root / "service" / "daemon.json"


def _sha256_path(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _source_identity() -> tuple[str, str]:
    source = Path(__file__).resolve()
    return str(source), _sha256_path(source)


def _config_identity(config_path: Path) -> tuple[str, str]:
    path = config_path.expanduser().resolve()
    return str(path), _sha256_path(path)


def write_service_receipt(path: Path, payload: Mapping[str, Any]) -> None:
    """Atomically write a restrictive daemon observability receipt."""

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, prefix=".daemon-", suffix=".tmp", delete=False
    ) as handle:
        temporary = Path(handle.name)
        json.dump(dict(payload), handle, sort_keys=True, separators=(",", ":"))
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    temporary.chmod(0o600)
    os.replace(temporary, path)
    path.chmod(0o600)


def _read_service_receipt(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return None
    return dict(value) if isinstance(value, Mapping) else None


def _safe_error(exc: Exception) -> dict[str, str]:
    code = str(exc) if isinstance(exc, ServiceError) else type(exc).__name__
    if not re.fullmatch(r"[A-Z0-9_:-]{1,120}", code):
        code = type(exc).__name__
    return {"type": type(exc).__name__, "code": code}


def _process_snapshot() -> list[tuple[int, str]]:
    result = subprocess.run(
        ["ps", "-axo", "pid=,command="], capture_output=True, text=True, check=False, timeout=5
    )
    if result.returncode != 0:
        return []
    rows: list[tuple[int, str]] = []
    for line in result.stdout.splitlines():
        match = re.match(r"\s*(\d+)\s+(.*)", line)
        if match:
            rows.append((int(match.group(1)), match.group(2).strip()))
    return rows


def _parse_launchctl(result: Any) -> dict[str, Any]:
    text = str(getattr(result, "stdout", "") or "")
    state = re.search(r"^\s*state\s*=\s*(\S+)", text, re.MULTILINE)
    pid = re.search(r"^\s*pid\s*=\s*(\d+)", text, re.MULTILINE)
    exit_code = re.search(r"^\s*last exit code\s*=\s*(-?\d+)", text, re.MULTILINE)
    return {
        "registered": getattr(result, "returncode", 1) == 0,
        "state": state.group(1) if state else None,
        "pid": int(pid.group(1)) if pid else None,
        "last_exit_code": int(exit_code.group(1)) if exit_code else None,
    }


def service_status(
    config_path: str | os.PathLike[str],
    *,
    launchctl_runner: Callable[..., Any] | None = None,
    process_snapshot: Callable[[], list[tuple[int, str]]]
    | list[tuple[int, str]] = _process_snapshot,
    now: float | None = None,
    receipt_path: Path | None = None,
) -> dict[str, Any]:
    """Reconcile LaunchAgent registration with the daemon's durable identity."""

    config_file = Path(config_path).expanduser().resolve()
    config = load_config(config_file)
    receipt_file = receipt_path or _service_receipt_path(config)
    receipt = _read_service_receipt(receipt_file)
    launchctl = launchctl_runner or _launchctl
    launch = _parse_launchctl(launchctl("print", f"gui/{os.getuid()}/{SERVICE_LABEL}"))
    source_path, source_sha = _source_identity()
    bound_config_path, config_sha = _config_identity(config_file)
    result: dict[str, Any] = {
        "service": SERVICE_LABEL,
        "status": ServiceReadiness.STOPPED.value,
        "ready": False,
        "source_path": source_path,
        "source_sha256": source_sha,
        "config_path": bound_config_path,
        "config_sha256": config_sha,
        "launchctl": launch,
    }
    if not launch["registered"]:
        return result
    if receipt is None:
        result["status"] = ServiceReadiness.STARTING.value
        return result
    result.update({
        key: receipt.get(key)
        for key in ("run_id", "pid", "heartbeat_at", "last_error", "started_at", "successful_polls")
    })
    if (
        receipt.get("source_path") not in (None, source_path)
        or receipt.get("source_sha256") != source_sha
        or receipt.get("config_path") not in (None, bound_config_path)
        or receipt.get("config_sha256") != config_sha
    ):
        result["status"] = ServiceReadiness.IDENTITY_MISMATCH.value
        return result
    if launch.get("state") != "running":
        result["status"] = ServiceReadiness.STOPPED.value
        return result
    if receipt.get("status") == ServiceReadiness.STOPPED.value:
        result["status"] = ServiceReadiness.STOPPED.value
        return result
    if receipt.get("status") == ServiceReadiness.DEGRADED.value:
        result["status"] = ServiceReadiness.DEGRADED.value
        return result
    if launch.get("last_exit_code") != 0:
        result["status"] = ServiceReadiness.DEGRADED.value
        return result
    if launch.get("pid") != receipt.get("pid"):
        result["status"] = ServiceReadiness.IDENTITY_MISMATCH.value
        return result
    processes = process_snapshot() if callable(process_snapshot) else process_snapshot
    matching = [
        pid
        for pid, command in processes
        if "scripts.ops.external_intelligence_service" in command
        and " daemon" in command
        and pid == receipt.get("pid")
    ]
    if (
        len(matching) != 1
        or sum(
            1
            for _pid, command in processes
            if "scripts.ops.external_intelligence_service" in command and " daemon" in command
        )
        != 1
    ):
        result["status"] = ServiceReadiness.DUPLICATE_PROCESS.value
        return result
    heartbeat = receipt.get("heartbeat_at")
    if (
        not isinstance(heartbeat, (int, float))
        or (now if now is not None else time.time()) - heartbeat > SERVICE_HEARTBEAT_STALE_SECONDS
    ):
        result["status"] = ServiceReadiness.STALE.value
        return result
    if receipt.get("successful_polls", 0) < READINESS_SUCCESS_THRESHOLD:
        result["status"] = ServiceReadiness.STARTING.value
        return result
    result["status"] = ServiceReadiness.READY.value
    result["ready"] = True
    return result


def load_config(path: str | os.PathLike[str]) -> ServiceConfig:
    raw = json.loads(Path(path).expanduser().read_text(encoding="utf-8"))
    allowed = {
        "repositories",
        "repository_roots",
        "state_root",
        "workspace_root",
        "label",
        "poll_interval_seconds",
        "opencli_executable",
        "opencli_profile",
        "opencode_executable",
        "publication_enabled",
        "requested_concurrency",
        "provider_available",
        "workspace_available",
        "controller_attention_limit",
        "max_repairs_per_unit",
    }
    if not isinstance(raw, dict) or set(raw) - allowed:
        raise ServiceError("CONFIG_KEYS_INVALID")
    repos = raw.get("repositories")
    roots = raw.get("repository_roots")
    if (
        not isinstance(repos, list)
        or not repos
        or any(not isinstance(x, str) or not x for x in repos)
    ):
        raise ServiceError("CONFIG_REPOSITORIES_INVALID")
    if (
        not isinstance(roots, dict)
        or set(roots) != set(repos)
        or any(not isinstance(v, str) or not v for v in roots.values())
    ):
        raise ServiceError("CONFIG_REPOSITORY_ROOTS_INVALID")
    state_root = raw.get("state_root")
    workspace_root = raw.get("workspace_root")
    if not isinstance(state_root, str) or not isinstance(workspace_root, str):
        raise ServiceError("CONFIG_PATHS_INVALID")
    kwargs = dict(raw)
    kwargs["repositories"] = tuple(repos)
    kwargs["repository_roots"] = roots
    kwargs["state_root"] = Path(state_root).expanduser().resolve()
    kwargs["workspace_root"] = Path(workspace_root).expanduser().resolve()
    return ServiceConfig(**kwargs)


class GhIssueTransport:
    def _run(self, argv: list[str]) -> str:
        result = subprocess.run(argv, check=False, capture_output=True, text=True, timeout=45)
        if result.returncode:
            raise ServiceError("GH_COMMAND_FAILED")
        return result.stdout or ""

    def list_open_labeled(self, repository: str, label: str) -> list[dict[str, Any]]:
        out = self._run([
            "gh",
            "issue",
            "list",
            "--repo",
            repository,
            "--state",
            "open",
            "--label",
            label,
            "--limit",
            "100",
            "--json",
            "number,title,body,updatedAt",
        ])
        value = json.loads(out)
        if not isinstance(value, list):
            raise ServiceError("GH_ISSUE_LIST_INVALID")
        return [dict(row) for row in value if isinstance(row, Mapping)]

    def comment(self, repository: str, issue_number: int, body: str) -> None:
        self._run([
            "gh",
            "issue",
            "comment",
            str(issue_number),
            "--repo",
            repository,
            "--body",
            body,
        ])


def _safe_repo(repo: str) -> str:
    return repo.replace("/", "_")


def build_automation(config: ServiceConfig, repository: str) -> ExternalIntelligenceAutomation:
    repo_root = Path(config.repository_roots[repository]).expanduser().resolve()
    repo_state = config.state_root / _safe_repo(repository)
    intel_store = ExternalIntelligenceStore(repo_state / "intelligence")
    sidecar = ExternalIntelligenceSidecar(
        transport=OpenCLIExternalIntelligenceTransport(
            executable=config.opencli_executable,
            profile=config.opencli_profile,
        ),
        store=intel_store,
    )
    c_runtime = AdaptiveDeepSeekFanoutRuntime(
        allocator=GitWorktreeAllocator(
            repo_root, config.workspace_root / "fanout" / _safe_repo(repository)
        ),
        store=FanoutStore(repo_state / "fanout"),
        transport=OpenCodeDeepSeekTransport(executable=config.opencode_executable),
    )
    d_runtime = ExternalIntelligenceClosureRuntime(
        repository_root=repo_root,
        allocator=CompositionWorkspaceAllocator(
            repo_root, config.workspace_root / "closure" / _safe_repo(repository)
        ),
        store=ClosureStore(repo_state / "closure"),
        c_runtime=c_runtime,
        max_repairs_per_unit=config.max_repairs_per_unit,
    )

    def capacity(contract):
        from nexus.services.external_intelligence_fanout import CapacityLease

        requested = min(
            int(contract.get("requested_concurrency") or config.requested_concurrency),
            config.requested_concurrency,
        )
        return CapacityLease(
            requested_concurrency=requested,
            provider_available=config.provider_available,
            workspace_available=config.workspace_available,
            controller_attention_limit=config.controller_attention_limit,
        )

    return ExternalIntelligenceAutomation(
        repository_root=repo_root,
        state_store=AutomationStateStore(config.state_root / "automation"),
        intelligence_store=intel_store,
        sidecar=sidecar,
        c_runtime=c_runtime,
        d_runtime=d_runtime,
        capacity_factory=capacity,
    )


def render_comment(result: Mapping[str, Any]) -> str:
    publication = result.get("publication") or {}
    return (
        "<!-- nexus-external-intelligence -->\n"
        "External Intelligence automation completed.\n\n"
        f"- Task: `{publication.get('task_id')}`\n"
        f"- Candidate: `{publication.get('candidate_commit')}`\n"
        f"- Tree: `{publication.get('candidate_tree')}`\n"
        f"- Verification: `{publication.get('verification_state')}`\n"
        f"- Gate: `{publication.get('current_gate')}`\n"
        f"- Acceptance packet: `{publication.get('acceptance_packet_sha256')}` ({publication.get('acceptance_packet_ref')})\n"
        f"- Next action: `{publication.get('next_action')}`\n"
        f"- Stop condition: `{publication.get('stop_condition')}`\n"
        f"- Claim ceiling: `{publication.get('claim_ceiling')}`\n"
    )


def refresh_remote_main(repo_root: Path, repository: str, timeout: float = 30.0) -> None:
    remotes_res = subprocess.run(
        ["git", "remote", "-v"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout,
    )
    if remotes_res.returncode != 0:
        raise ServiceError("REMOTE_MAIN_REFRESH_FAILED")
    remote_map: dict[str, str] = {}
    for line in remotes_res.stdout.splitlines():
        parts = line.strip().split()
        if len(parts) >= 2:
            remote_map[parts[0]] = parts[1]

    target_repo = _normalize_github_repo(repository)
    matching_remote: str | None = None
    for r_name, r_url in remote_map.items():
        if _normalize_github_repo(r_url) == target_repo:
            matching_remote = r_name
            break
    if not matching_remote:
        raise ServiceError("REPOSITORY_IDENTITY_MISMATCH")

    refspec = f"refs/heads/main:refs/remotes/{matching_remote}/main"
    fetch_res = subprocess.run(
        ["git", "fetch", "--no-tags", matching_remote, refspec],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout,
    )
    if fetch_res.returncode != 0:
        raise ServiceError("REMOTE_MAIN_REFRESH_FAILED")


def run_once(
    config: ServiceConfig,
    gh: GhIssueTransport | Any | None = None,
    automation_factory=build_automation,
    refresh_fn=refresh_remote_main,
) -> dict[str, Any]:
    if gh is None:
        gh = GhIssueTransport()
    last: dict[str, Any] | None = None
    for repository in config.repositories:
        issues = gh.list_open_labeled(repository, config.label)
        if not issues:
            continue
        repo_root = Path(config.repository_roots[repository]).expanduser().resolve()
        try:
            refresh_fn(repo_root, repository)
        except Exception as exc:
            err = (
                str(exc)
                if str(exc) in {"REPOSITORY_IDENTITY_MISMATCH", "REMOTE_MAIN_REFRESH_FAILED"}
                else "REMOTE_MAIN_REFRESH_FAILED"
            )
            first_issue_num = int(issues[0].get("number") or 0) if issues else 0
            last = {
                "status": "BLOCKED",
                "repository": repository,
                "issue_number": first_issue_num,
                "result": {
                    "state": "BLOCKED",
                    "error": err,
                    "semantic_dispatched": False,
                },
            }
            continue
        for issue in sorted(issues, key=lambda row: int(row.get("number") or 0)):
            automation = automation_factory(config, repository)
            result = automation.run_issue(
                repository,
                int(issue["number"]),
                str(issue.get("title") or ""),
                str(issue.get("body") or ""),
            )
            if result.get("reuse") or (
                result.get("state") == "BLOCKED" and not result.get("semantic_dispatched")
            ):
                last = {
                    "status": result.get("state"),
                    "repository": repository,
                    "issue_number": int(issue["number"]),
                    "result": result,
                }
                continue
            if result.get("state") == "COMPLETE" and config.publication_enabled:
                gh.comment(repository, int(issue["number"]), render_comment(result))
            return {
                "status": result.get("state"),
                "repository": repository,
                "issue_number": int(issue["number"]),
                "result": result,
            }
    if last is not None:
        return last
    return {"status": "IDLE"}


def launch_agent_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{SERVICE_LABEL}.plist"


def plist_xml(config_path: Path, state_root: Path | None = None) -> str:
    args = [
        sys.executable,
        "-m",
        "scripts.ops.external_intelligence_service",
        "daemon",
        "--config",
        str(config_path),
    ]
    arg_xml = "".join(f"<string>{html.escape(value)}</string>" for value in args)
    root = Path(__file__).resolve().parents[2]
    logs = (state_root or config_path.parent / "state") / "service"
    return f"""<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n<plist version="1.0"><dict>\n<key>Label</key><string>{SERVICE_LABEL}</string>\n<key>ProgramArguments</key><array>{arg_xml}</array>\n<key>WorkingDirectory</key><string>{html.escape(str(root))}</string>\n<key>RunAtLoad</key><true/><key>KeepAlive</key><true/>\n<key>ProcessType</key><string>Background</string><key>ThrottleInterval</key><integer>30</integer>\n<key>StandardOutPath</key><string>{html.escape(str(logs / "daemon.stdout.log"))}</string><key>StandardErrorPath</key><string>{html.escape(str(logs / "daemon.stderr.log"))}</string>\n<key>EnvironmentVariables</key><dict><key>PYTHONDONTWRITEBYTECODE</key><string>1</string><key>PYTHONPATH</key><string>{html.escape(str(root))}</string><key>PATH</key><string>/Users/jameschen/.opencode/bin:/Users/jameschen/.npm-global/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/usr/sbin:/sbin</string></dict>\n</dict></plist>\n"""


def install(config_path: str | os.PathLike[str]) -> Path:
    path = Path(config_path).expanduser().resolve()
    config = load_config(path)
    (config.state_root / "service").mkdir(parents=True, exist_ok=True, mode=0o700)
    target = launch_agent_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(plist_xml(path, state_root=config.state_root), encoding="utf-8")
    target.chmod(0o600)
    return target


def _launchctl(*args: str):
    return subprocess.run(
        [
            "launchctl",
            *args,
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=20,
    )


def start(config_path: str | os.PathLike[str]):
    plist = install(config_path)
    domain = f"gui/{os.getuid()}"
    _launchctl("bootout", f"{domain}/{SERVICE_LABEL}")
    return _launchctl("bootstrap", domain, str(plist))


def stop():
    return _launchctl("bootout", f"gui/{os.getuid()}/{SERVICE_LABEL}")


def daemon(config: ServiceConfig, config_path: Path | None = None) -> None:
    stopping = False
    started = time.time()
    run_id = uuid.uuid4().hex
    source_path, source_sha = _source_identity()
    bound_config_path = str(config_path.resolve()) if config_path is not None else ""
    config_sha = _sha256_path(config_path) if config_path is not None else ""
    receipt = _service_receipt_path(config)
    successful_polls = 0

    def write_status(status: ServiceReadiness, *, error: dict[str, str] | None = None) -> None:
        write_service_receipt(
            receipt,
            {
                "schema": "nexus.external_intelligence_daemon_receipt.v1",
                "status": status.value,
                "run_id": run_id,
                "pid": os.getpid(),
                "source_path": source_path,
                "source_sha256": source_sha,
                "config_path": bound_config_path,
                "config_sha256": config_sha,
                "started_at": started,
                "heartbeat_at": time.time(),
                "successful_polls": successful_polls,
                "last_error": error,
            },
        )

    def halt(_sig, _frame):
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGTERM, halt)
    signal.signal(signal.SIGINT, halt)
    write_status(ServiceReadiness.STARTING)
    while not stopping:
        try:
            run_once(config)
            successful_polls += 1
            write_status(
                ServiceReadiness.READY
                if successful_polls >= READINESS_SUCCESS_THRESHOLD
                else ServiceReadiness.STARTING
            )
        except Exception as exc:
            successful_polls = 0
            write_status(ServiceReadiness.DEGRADED, error=_safe_error(exc))
        deadline = time.monotonic() + config.poll_interval_seconds
        while not stopping and time.monotonic() < deadline:
            time.sleep(min(1.0, deadline - time.monotonic()))
    write_status(ServiceReadiness.STOPPED)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="nexus-external-intelligence-service")
    parser.add_argument(
        "command", choices=("run-once", "daemon", "install", "start", "stop", "restart", "status")
    )
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    args = parser.parse_args(argv)
    config = load_config(args.config)
    if args.command == "run-once":
        value = run_once(config)
    elif args.command == "daemon":
        daemon(config, Path(args.config).expanduser().resolve())
        return 0
    elif args.command == "install":
        value = {"status": "INSTALLED", "path": str(install(args.config))}
    elif args.command == "start":
        r = start(args.config)
        value = {
            "status": "STARTED" if r.returncode == 0 else "START_FAILED",
            "detail": r.stderr.strip(),
        }
    elif args.command == "stop":
        r = stop()
        value = {
            "status": "STOPPED" if r.returncode == 0 else "STOP_FAILED",
            "detail": r.stderr.strip(),
        }
    elif args.command == "restart":
        stop()
        r = start(args.config)
        value = {
            "status": "RESTARTED" if r.returncode == 0 else "RESTART_FAILED",
            "detail": r.stderr.strip(),
        }
    else:
        value = service_status(args.config)
    print(json.dumps(value, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
