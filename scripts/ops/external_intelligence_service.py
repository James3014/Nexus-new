from __future__ import annotations

import argparse
import html
import json
import os
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from nexus.services.external_intelligence import ExternalIntelligenceSidecar, ExternalIntelligenceStore, OpenCLIExternalIntelligenceTransport
from nexus.services.external_intelligence_automation import AutomationStateStore, ExternalIntelligenceAutomation
from nexus.services.external_intelligence_closure import ClosureStore, CompositionWorkspaceAllocator, ExternalIntelligenceClosureRuntime
from nexus.services.external_intelligence_fanout import AdaptiveDeepSeekFanoutRuntime, FanoutStore, GitWorktreeAllocator, OpenCodeDeepSeekTransport

SERVICE_LABEL = "com.nexus.external-intelligence"
DEFAULT_CONFIG = Path.home() / ".config" / "nexus-external-intelligence" / "config.json"


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


def load_config(path: str | os.PathLike[str]) -> ServiceConfig:
    raw = json.loads(Path(path).expanduser().read_text(encoding="utf-8"))
    allowed = {
        "repositories", "repository_roots", "state_root", "workspace_root", "label", "poll_interval_seconds",
        "opencli_executable", "opencli_profile", "opencode_executable", "publication_enabled", "requested_concurrency",
        "provider_available", "workspace_available", "controller_attention_limit", "max_repairs_per_unit",
    }
    if not isinstance(raw, dict) or set(raw) - allowed:
        raise ServiceError("CONFIG_KEYS_INVALID")
    repos = raw.get("repositories")
    roots = raw.get("repository_roots")
    if not isinstance(repos, list) or not repos or any(not isinstance(x, str) or not x for x in repos):
        raise ServiceError("CONFIG_REPOSITORIES_INVALID")
    if not isinstance(roots, dict) or set(roots) != set(repos) or any(not isinstance(v, str) or not v for v in roots.values()):
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
            "gh", "issue", "list", "--repo", repository, "--state", "open", "--label", label,
            "--limit", "100", "--json", "number,title,body,updatedAt",
        ])
        value = json.loads(out)
        if not isinstance(value, list):
            raise ServiceError("GH_ISSUE_LIST_INVALID")
        return [dict(row) for row in value if isinstance(row, Mapping)]

    def comment(self, repository: str, issue_number: int, body: str) -> None:
        self._run(["gh", "issue", "comment", str(issue_number), "--repo", repository, "--body", body])


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
        allocator=GitWorktreeAllocator(repo_root, config.workspace_root / "fanout" / _safe_repo(repository)),
        store=FanoutStore(repo_state / "fanout"),
        transport=OpenCodeDeepSeekTransport(executable=config.opencode_executable),
    )
    d_runtime = ExternalIntelligenceClosureRuntime(
        repository_root=repo_root,
        allocator=CompositionWorkspaceAllocator(repo_root, config.workspace_root / "closure" / _safe_repo(repository)),
        store=ClosureStore(repo_state / "closure"),
        c_runtime=c_runtime,
        max_repairs_per_unit=config.max_repairs_per_unit,
    )

    def capacity(contract):
        from nexus.services.external_intelligence_fanout import CapacityLease
        requested = min(int(contract.get("requested_concurrency") or config.requested_concurrency), config.requested_concurrency)
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


def run_once(config: ServiceConfig, gh: GhIssueTransport | Any | None = None, automation_factory=build_automation) -> dict[str, Any]:
    gh = gh or GhIssueTransport()
    last: dict[str, Any] | None = None
    for repository in config.repositories:
        issues = gh.list_open_labeled(repository, config.label)
        for issue in sorted(issues, key=lambda row: int(row.get("number") or 0)):
            automation = automation_factory(config, repository)
            result = automation.run_issue(repository, int(issue["number"]), str(issue.get("title") or ""), str(issue.get("body") or ""))
            if result.get("reuse") or (result.get("state") == "BLOCKED" and not result.get("semantic_dispatched")):
                last = {"status": result.get("state"), "repository": repository, "issue_number": int(issue["number"]), "result": result}
                continue
            if result.get("state") == "COMPLETE" and config.publication_enabled:
                gh.comment(repository, int(issue["number"]), render_comment(result))
            return {"status": result.get("state"), "repository": repository, "issue_number": int(issue["number"]), "result": result}
    if last is not None:
        return last
    return {"status": "IDLE"}


def launch_agent_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{SERVICE_LABEL}.plist"


def plist_xml(config_path: Path) -> str:
    args = [sys.executable, "-m", "scripts.ops.external_intelligence_service", "daemon", "--config", str(config_path)]
    arg_xml = "".join(f"<string>{html.escape(value)}</string>" for value in args)
    root = Path(__file__).resolve().parents[2]
    return f'''<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n<plist version="1.0"><dict>\n<key>Label</key><string>{SERVICE_LABEL}</string>\n<key>ProgramArguments</key><array>{arg_xml}</array>\n<key>WorkingDirectory</key><string>{html.escape(str(root))}</string>\n<key>RunAtLoad</key><true/><key>KeepAlive</key><true/>\n<key>ProcessType</key><string>Background</string><key>ThrottleInterval</key><integer>30</integer>\n<key>StandardOutPath</key><string>/dev/null</string><key>StandardErrorPath</key><string>/dev/null</string>\n<key>EnvironmentVariables</key><dict><key>PYTHONDONTWRITEBYTECODE</key><string>1</string><key>PYTHONPATH</key><string>{html.escape(str(root))}</string><key>PATH</key><string>/Users/jameschen/.opencode/bin:/Users/jameschen/.npm-global/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string></dict>\n</dict></plist>\n'''


def install(config_path: str | os.PathLike[str]) -> Path:
    path = Path(config_path).expanduser().resolve()
    load_config(path)
    target = launch_agent_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(plist_xml(path), encoding="utf-8")
    target.chmod(0o600)
    return target


def _launchctl(*args: str):
    return subprocess.run(["launchctl", *args,], check=False, capture_output=True, text=True, timeout=20)


def start(config_path: str | os.PathLike[str]):
    plist = install(config_path)
    domain = f"gui/{os.getuid()}"
    _launchctl("bootout", f"{domain}/{SERVICE_LABEL}")
    return _launchctl("bootstrap", domain, str(plist))


def stop():
    return _launchctl("bootout", f"gui/{os.getuid()}/{SERVICE_LABEL}")


def daemon(config: ServiceConfig) -> None:
    stopping = False
    def halt(_sig, _frame):
        nonlocal stopping
        stopping = True
    signal.signal(signal.SIGTERM, halt)
    signal.signal(signal.SIGINT, halt)
    while not stopping:
        run_once(config)
        deadline = time.monotonic() + config.poll_interval_seconds
        while not stopping and time.monotonic() < deadline:
            time.sleep(min(1.0, deadline - time.monotonic()))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="nexus-external-intelligence-service")
    parser.add_argument("command", choices=("run-once", "daemon", "install", "start", "stop", "restart", "status"))
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    args = parser.parse_args(argv)
    config = load_config(args.config)
    if args.command == "run-once": value = run_once(config)
    elif args.command == "daemon": daemon(config); return 0
    elif args.command == "install": value = {"status": "INSTALLED", "path": str(install(args.config))}
    elif args.command == "start":
        r = start(args.config); value = {"status": "STARTED" if r.returncode == 0 else "START_FAILED", "detail": r.stderr.strip()}
    elif args.command == "stop":
        r = stop(); value = {"status": "STOPPED" if r.returncode == 0 else "STOP_FAILED", "detail": r.stderr.strip()}
    elif args.command == "restart":
        stop(); r = start(args.config); value = {"status": "RESTARTED" if r.returncode == 0 else "RESTART_FAILED", "detail": r.stderr.strip()}
    else:
        r = _launchctl("print", f"gui/{os.getuid()}/{SERVICE_LABEL}")
        value = {"status": "RUNNING" if r.returncode == 0 else "STOPPED", "service": SERVICE_LABEL}
    print(json.dumps(value, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
