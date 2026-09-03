from __future__ import annotations

import argparse
import hashlib
import html
import json
import math
import os
import re
import shlex
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

from nexus.core.exit_codes import NexusExitCode
from nexus.services.external_intelligence import (
    ExternalIntelligenceSidecar,
    ExternalIntelligenceStore,
    OpenCLIExternalIntelligenceTransport,
)
from nexus.services.external_intelligence_automation import (
    TERMINAL_DISPOSITIONS,
    AutomationStateStore,
    ExternalIntelligenceAutomation,
    _normalize_github_repo,
    compute_publication_id,
)
from nexus.services.external_intelligence_closure import (
    ClosureStore,
    CompositionWorkspaceAllocator,
    ExternalIntelligenceClosureRuntime,
)
from nexus.services.external_intelligence_fanout import (
    AdaptiveWorkerFanoutRuntime,
    FanoutStore,
    GitWorktreeAllocator,
    OpenCodeWorkerTransport,
)
from nexus.services.open_swe_external_intelligence import (
    OpenSWEExternalIntelligenceError,
    OpenSWEExternalIntelligenceTransport,
    OpenSWEWorkerTransport,
)

SERVICE_LABEL = "com.nexus.external-intelligence"
DEFAULT_CONFIG = Path.home() / ".config" / "nexus-external-intelligence" / "config.json"
READINESS_SUCCESS_THRESHOLD = 2
SERVICE_HEARTBEAT_STALE_SECONDS = 180.0
SERVICE_RECEIPT_SCHEMA = "nexus.external_intelligence_daemon_receipt.v1"
_RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


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
    semantic_backend: str = "opencli"
    open_swe_model_provider: str = ""
    open_swe_model: str = ""
    open_swe_executable: str = "nexus-open-swe-runtime"
    open_swe_opencli_executable: str = "opencli"
    open_swe_opencli_profile: str = ""
    open_swe_opencli_site_session: str = "ephemeral"
    open_swe_opencli_timeout_seconds: int = 120
    worker_backend: str = "opencode"
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

    _validate_service_receipt(payload)
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


def _validate_service_receipt(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("RECEIPT_MAPPING_INVALID")
    required = {
        "schema",
        "status",
        "run_id",
        "pid",
        "source_path",
        "source_sha256",
        "config_path",
        "config_sha256",
        "started_at",
        "heartbeat_at",
        "successful_polls",
        "last_error",
    }
    if set(value) != required:
        raise ValueError("RECEIPT_SCHEMA_INVALID")
    if value["schema"] != SERVICE_RECEIPT_SCHEMA:
        raise ValueError("RECEIPT_SCHEMA_INVALID")
    if not isinstance(value["status"], str) or value["status"] not in {
        state.value for state in ServiceReadiness
    }:
        raise ValueError("RECEIPT_STATUS_INVALID")
    if not isinstance(value["run_id"], str) or _RUN_ID_RE.fullmatch(value["run_id"]) is None:
        raise ValueError("RECEIPT_RUN_ID_INVALID")
    if not isinstance(value["pid"], int) or isinstance(value["pid"], bool) or value["pid"] <= 0:
        raise ValueError("RECEIPT_PID_INVALID")
    for key in ("source_path", "config_path"):
        if not isinstance(value[key], str) or not value[key] or "\x00" in value[key]:
            raise ValueError("RECEIPT_IDENTITY_PATH_INVALID")
    for key in ("source_sha256", "config_sha256"):
        if not isinstance(value[key], str) or _SHA256_RE.fullmatch(value[key]) is None:
            raise ValueError("RECEIPT_IDENTITY_HASH_INVALID")
    for key in ("started_at", "heartbeat_at"):
        if (
            not isinstance(value[key], (int, float))
            or isinstance(value[key], bool)
            or not math.isfinite(value[key])
            or value[key] < 0
        ):
            raise ValueError("RECEIPT_TIMESTAMP_INVALID")
    if (
        not isinstance(value["successful_polls"], int)
        or isinstance(value["successful_polls"], bool)
        or value["successful_polls"] < 0
    ):
        raise ValueError("RECEIPT_POLL_COUNT_INVALID")
    error = value["last_error"]
    if error is not None and (
        not isinstance(error, Mapping)
        or set(error) != {"type", "code"}
        or not all(isinstance(error[key], str) and error[key] for key in ("type", "code"))
    ):
        raise ValueError("RECEIPT_ERROR_INVALID")
    return dict(value)


def _read_service_receipt(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return None
    try:
        return _validate_service_receipt(value)
    except ValueError:
        return None


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


def _expected_process_argv(config_path: Path) -> list[str]:
    return [
        str(Path(sys.executable).resolve()),
        "-m",
        "scripts.ops.external_intelligence_service",
        "daemon",
        "--config",
        str(config_path.resolve()),
    ]


def _accepted_python_executables() -> set[str]:
    current_exe = Path(sys.executable).resolve()
    accepted = {str(current_exe)}

    # Framework layout: <framework_root>/bin/python* -> <framework_root>/Resources/Python.app/Contents/MacOS/Python
    framework_root = current_exe.parent.parent
    app_exe = framework_root / "Resources" / "Python.app" / "Contents" / "MacOS" / "Python"
    if app_exe.is_file():
        accepted.add(str(app_exe.resolve()))
    elif "Python.framework" in current_exe.parts:
        accepted.add(str(app_exe))

    # App layout: <framework_root>/Resources/Python.app/Contents/MacOS/Python -> <framework_root>/bin/python*
    if len(current_exe.parts) >= 5 and current_exe.parts[-5:] == (
        "Resources",
        "Python.app",
        "Contents",
        "MacOS",
        "Python",
    ):
        app_framework_root = current_exe.parents[4]
        bin_dir = app_framework_root / "bin"
        candidates = [
            bin_dir / f"python{sys.version_info.major}.{sys.version_info.minor}",
            bin_dir / f"python{sys.version_info.major}",
            bin_dir / "python",
        ]
        for cand in candidates:
            if cand.is_file():
                accepted.add(str(cand.resolve()))
            elif "Python.framework" in current_exe.parts:
                accepted.add(str(cand))

    return accepted


def _is_matching_python_executable(candidate: str) -> bool:
    try:
        resolved_candidate = str(Path(candidate).resolve())
    except Exception:
        resolved_candidate = candidate
    accepted = _accepted_python_executables()
    return candidate in accepted or resolved_candidate in accepted


def _process_matches(command: str, config_path: Path) -> bool:
    try:
        argv = shlex.split(command)
    except ValueError:
        return False
    expected_tail = [
        "-m",
        "scripts.ops.external_intelligence_service",
        "daemon",
        "--config",
        str(config_path.resolve()),
    ]
    if len(argv) != len(expected_tail) + 1 or argv[1:] != expected_tail:
        return False
    return _is_matching_python_executable(argv[0])


def _parse_launchctl(result: Any) -> dict[str, Any]:
    text = str(getattr(result, "stdout", "") or "")
    state = re.search(r"^\s*state\s*=\s*(\S+)", text, re.MULTILINE)
    pid = re.search(r"^\s*pid\s*=\s*(\d+)", text, re.MULTILINE)
    exit_match = re.search(r"^\s*last exit code\s*=\s*(.+)$", text, re.MULTILINE)
    last_exit_code: int | None = None
    last_exit_state = "UNKNOWN_OR_MISSING"
    if exit_match:
        raw_exit = exit_match.group(1).strip()
        if raw_exit == "(never exited)":
            last_exit_state = "NEVER_EXITED"
        elif re.fullmatch(r"-?\d+", raw_exit):
            last_exit_state = "EXITED_WITH_CODE"
            last_exit_code = int(raw_exit)
    return {
        "registered": getattr(result, "returncode", 1) == 0,
        "state": state.group(1) if state else None,
        "pid": int(pid.group(1)) if pid else None,
        "last_exit_code": last_exit_code,
        "last_exit_state": last_exit_state,
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
        result["status"] = (
            ServiceReadiness.DEGRADED.value
            if receipt_file.exists()
            else ServiceReadiness.STARTING.value
        )
        return result
    result.update({
        key: receipt.get(key)
        for key in (
            "run_id",
            "pid",
            "heartbeat_at",
            "last_error",
            "started_at",
            "successful_polls",
        )
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
    last_exit_state = launch.get("last_exit_state")
    if last_exit_state == "EXITED_WITH_CODE":
        if launch.get("last_exit_code") != 0:
            result["status"] = ServiceReadiness.DEGRADED.value
            return result
    elif last_exit_state == "NEVER_EXITED":
        pass
    else:
        result["status"] = ServiceReadiness.DEGRADED.value
        return result
    if launch.get("pid") != receipt.get("pid"):
        result["status"] = ServiceReadiness.IDENTITY_MISMATCH.value
        return result
    processes = process_snapshot() if callable(process_snapshot) else process_snapshot
    matching = [
        pid
        for pid, command in processes
        if _process_matches(command, config_file) and pid == receipt.get("pid")
    ]
    if (
        len(matching) != 1
        or sum(1 for _pid, command in processes if _process_matches(command, config_file)) != 1
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
        "semantic_backend",
        "open_swe_model_provider",
        "open_swe_model",
        "open_swe_executable",
        "open_swe_opencli_executable",
        "open_swe_opencli_profile",
        "open_swe_opencli_site_session",
        "open_swe_opencli_timeout_seconds",
        "worker_backend",
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
    semantic_backend = raw.get("semantic_backend", "opencli")
    if semantic_backend not in {"opencli", "open_swe"}:
        raise ServiceError("CONFIG_SEMANTIC_BACKEND_INVALID")
    worker_backend = raw.get("worker_backend", "opencode")
    if worker_backend not in {"opencode", "open_swe"}:
        raise ServiceError("CONFIG_WORKER_BACKEND_INVALID")
    open_swe_provider = raw.get("open_swe_model_provider", "")
    open_swe_model = raw.get("open_swe_model", "")
    open_swe_executable = raw.get("open_swe_executable", "nexus-open-swe-runtime")
    if (
        not isinstance(open_swe_provider, str)
        or not isinstance(open_swe_model, str)
        or (
            (semantic_backend == "open_swe" or worker_backend == "open_swe")
            and (not open_swe_provider.strip() or not open_swe_model.strip())
        )
    ):
        raise ServiceError("CONFIG_OPEN_SWE_MODEL_BINDING_REQUIRED")
    if not isinstance(open_swe_executable, str) or not open_swe_executable.strip():
        raise ServiceError("CONFIG_OPEN_SWE_EXECUTABLE_REQUIRED")
    opencli_transport_keys = {
        "open_swe_opencli_executable",
        "open_swe_opencli_profile",
        "open_swe_opencli_site_session",
        "open_swe_opencli_timeout_seconds",
    }
    if open_swe_provider != "opencli_chatgpt" and set(raw).intersection(opencli_transport_keys):
        raise ServiceError("CONFIG_OPEN_SWE_TRANSPORT_PROVIDER_MISMATCH")
    if open_swe_provider == "opencli_chatgpt":
        opencli_executable = raw.get("open_swe_opencli_executable", "opencli")
        opencli_profile = raw.get("open_swe_opencli_profile", "")
        opencli_site_session = raw.get("open_swe_opencli_site_session", "ephemeral")
        opencli_timeout_seconds = raw.get("open_swe_opencli_timeout_seconds", 120)
        if (
            not isinstance(opencli_executable, str)
            or not opencli_executable.strip()
            or "\x00" in opencli_executable
            or not isinstance(opencli_profile, str)
            or "\x00" in opencli_profile
            or not isinstance(opencli_site_session, str)
            or not opencli_site_session.strip()
            or "\x00" in opencli_site_session
            or not isinstance(opencli_timeout_seconds, int)
            or isinstance(opencli_timeout_seconds, bool)
            or not 30 <= opencli_timeout_seconds <= 900
        ):
            raise ServiceError("CONFIG_OPEN_SWE_TRANSPORT_INVALID")
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

    def list_comments(self, repository: str, issue_number: int) -> list[dict[str, Any]]:
        clean_repo = repository.strip().strip("/")
        out = self._run([
            "gh",
            "api",
            f"repos/{clean_repo}/issues/{issue_number}/comments",
            "--paginate",
            "--slurp",
        ])
        try:
            value = json.loads(out)
        except Exception as exc:
            raise ServiceError("GH_COMMENTS_LIST_INVALID") from exc
        comments: list[dict[str, Any]] = []
        if isinstance(value, list):
            for item in value:
                if isinstance(item, list):
                    for elem in item:
                        if isinstance(elem, Mapping):
                            comments.append(dict(elem))
                elif isinstance(item, Mapping):
                    comments.append(dict(item))
            return comments
        elif (
            isinstance(value, Mapping)
            and "comments" in value
            and isinstance(value["comments"], list)
        ):
            return [dict(row) for row in value["comments"] if isinstance(row, Mapping)]
        raise ServiceError("GH_COMMENTS_LIST_INVALID")

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


def _open_swe_transport_config(config: ServiceConfig) -> dict[str, Any]:
    if config.open_swe_model_provider != "opencli_chatgpt":
        return {}
    return {
        "executable": config.open_swe_opencli_executable,
        "profile": config.open_swe_opencli_profile,
        "site_session": config.open_swe_opencli_site_session,
        "timeout_seconds": config.open_swe_opencli_timeout_seconds,
    }


def build_automation(config: ServiceConfig, repository: str) -> ExternalIntelligenceAutomation:
    if config.semantic_backend not in {"opencli", "open_swe"}:
        raise ServiceError("CONFIG_SEMANTIC_BACKEND_INVALID")
    repo_root = Path(config.repository_roots[repository]).expanduser().resolve()
    repo_state = config.state_root / _safe_repo(repository)
    intel_store = ExternalIntelligenceStore(repo_state / "intelligence")
    if config.semantic_backend == "open_swe" and (
        not config.open_swe_model_provider.strip() or not config.open_swe_model.strip()
    ):
        raise ServiceError("CONFIG_OPEN_SWE_MODEL_BINDING_REQUIRED")
    if config.semantic_backend == "opencli":
        semantic_transport: Any = OpenCLIExternalIntelligenceTransport(
            executable=config.opencli_executable,
            profile=config.opencli_profile,
        )
    else:
        try:
            semantic_transport = OpenSWEExternalIntelligenceTransport(
                repository_root=repo_root,
                model_provider=config.open_swe_model_provider,
                model_id=config.open_swe_model,
                executable=config.open_swe_executable,
                runtime_state_root=config.state_root / "open_swe_runtime",
                transport_config=_open_swe_transport_config(config),
            )
        except OpenSWEExternalIntelligenceError as exc:
            raise ServiceError(str(exc)) from exc
    sidecar = ExternalIntelligenceSidecar(
        transport=semantic_transport,
        store=intel_store,
    )
    if config.worker_backend == "opencode":
        worker_transport: Any = OpenCodeWorkerTransport(executable=config.opencode_executable)
    elif config.worker_backend == "open_swe":
        try:
            worker_transport = OpenSWEWorkerTransport(
                model_provider=config.open_swe_model_provider,
                model_id=config.open_swe_model,
                executable=config.open_swe_executable,
                runtime_state_root=config.state_root / "open_swe_runtime",
                require_worker_binding=True,
                transport_config=_open_swe_transport_config(config),
            )
        except OpenSWEExternalIntelligenceError as exc:
            raise ServiceError(str(exc)) from exc
    else:
        raise ServiceError("CONFIG_WORKER_BACKEND_INVALID")
    c_runtime = AdaptiveWorkerFanoutRuntime(
        allocator=GitWorktreeAllocator(
            repo_root, config.workspace_root / "fanout" / _safe_repo(repository)
        ),
        store=FanoutStore(repo_state / "fanout"),
        transport=worker_transport,
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


def render_comment(result: Mapping[str, Any], publication_id: str | None = None) -> str:
    publication = result.get("publication") or {}
    pub_id = publication_id or publication.get("publication_id") or ""
    if not pub_id and isinstance(result.get("publication_record"), Mapping):
        pub_id = result["publication_record"].get("publication_id") or ""
    header = (
        f"<!-- nexus-external-intelligence:{pub_id} -->\n"
        if pub_id
        else "<!-- nexus-external-intelligence -->\n"
    )
    return (
        header + "External Intelligence automation completed.\n\n"
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


def reconcile_publication(
    *,
    repository: str,
    issue_number: int,
    result: dict[str, Any],
    gh: Any,
    config: ServiceConfig,
    state_store: AutomationStateStore | None = None,
    identity_hash: str | None = None,
) -> dict[str, Any]:
    if not config.publication_enabled:
        return result

    publication = result.get("publication")
    if not isinstance(publication, Mapping) or not publication:
        return result

    id_hash = identity_hash or str(result.get("identity_hash") or "")

    pub_record = result.get("publication_record")
    if not isinstance(pub_record, Mapping) or "state" not in pub_record:
        return {
            **result,
            "state": "RECONCILIATION_REQUIRED",
            "error": "PUBLICATION_RECORD_MISSING",
            "reconcile_only": True,
        }

    current_pub_state = str(pub_record.get("state") or "")
    if current_pub_state not in {"PREPARED", "DISPATCHING", "OUTCOME_UNKNOWN", "COMPLETED"}:
        return {
            **result,
            "state": "RECONCILIATION_REQUIRED",
            "prior_state": current_pub_state,
            "error": "PUBLICATION_STATE_INVALID",
            "reconcile_only": True,
        }

    pub_id = (
        pub_record.get("publication_id")
        or result.get("publication_id")
        or compute_publication_id(repository, issue_number, id_hash, publication)
    )
    marker = f"<!-- nexus-external-intelligence:{pub_id} -->"

    def _persist(new_state: str, **extra: Any) -> bool:
        rec = {
            "publication_id": pub_id,
            "state": new_state,
            "marker": marker,
            "payload": dict(publication),
            **extra,
        }
        result["publication_record"] = rec
        if state_store is not None:
            if not id_hash:
                return False
            try:
                updated = state_store.update_publication_record(
                    repository, issue_number, id_hash, rec
                )
                if updated is None:
                    return False
            except Exception:
                return False
        return True

    def _find_markers(comments: list[dict[str, Any]]) -> tuple[int, list[dict[str, Any]]]:
        matching = []
        pattern = re.compile(rf"<!--\s*nexus-external-intelligence:{re.escape(pub_id)}\s*-->")
        for c in comments:
            b = str(c.get("body") or "")
            if marker in b or pattern.search(b):
                matching.append(c)
        return len(matching), matching

    def _list_comments() -> list[dict[str, Any]] | None:
        if not hasattr(gh, "list_comments"):
            return None
        try:
            return gh.list_comments(repository, issue_number)
        except Exception:
            return None

    if current_pub_state == "COMPLETED":
        return result

    if current_pub_state in {"DISPATCHING", "OUTCOME_UNKNOWN"}:
        comments = _list_comments()
        if comments is None:
            _persist("OUTCOME_UNKNOWN", error="GH_COMMENTS_LIST_FAILED")
            return {
                **result,
                "state": "RECONCILIATION_REQUIRED",
                "prior_state": current_pub_state,
                "error": "GH_COMMENTS_LIST_FAILED",
                "reconcile_only": True,
            }
        count, matching = _find_markers(comments)
        if count == 1:
            _persist("COMPLETED", comment_id=matching[0].get("id"))
            return {**result, "state": "COMPLETE"}
        elif count > 1:
            _persist("OUTCOME_UNKNOWN", error="DUPLICATE_PUBLICATION_MARKER")
            return {
                **result,
                "state": "RECONCILIATION_REQUIRED",
                "prior_state": current_pub_state,
                "error": "DUPLICATE_PUBLICATION_MARKER",
                "reconcile_only": True,
            }
        else:
            _persist("OUTCOME_UNKNOWN", error="PUBLICATION_UNCONFIRMED_ZERO_MARKER")
            return {
                **result,
                "state": "RECONCILIATION_REQUIRED",
                "prior_state": current_pub_state,
                "error": "PUBLICATION_UNCONFIRMED_ZERO_MARKER",
                "reconcile_only": True,
            }

    comments = _list_comments()
    if comments is None:
        _persist("OUTCOME_UNKNOWN", error="GH_COMMENTS_LIST_FAILED")
        return {
            **result,
            "state": "RECONCILIATION_REQUIRED",
            "prior_state": "PREPARED",
            "error": "GH_COMMENTS_LIST_FAILED",
            "reconcile_only": True,
        }

    count, matching = _find_markers(comments)
    if count == 1:
        _persist("COMPLETED", comment_id=matching[0].get("id"))
        return {**result, "state": "COMPLETE"}
    elif count > 1:
        _persist("OUTCOME_UNKNOWN", error="DUPLICATE_PUBLICATION_MARKER")
        return {
            **result,
            "state": "RECONCILIATION_REQUIRED",
            "prior_state": "PREPARED",
            "error": "DUPLICATE_PUBLICATION_MARKER",
            "reconcile_only": True,
        }

    ok = _persist("DISPATCHING")
    if not ok:
        return {
            **result,
            "state": "RECONCILIATION_REQUIRED",
            "prior_state": "PREPARED",
            "error": "PUBLICATION_PERSISTENCE_FAILED",
            "reconcile_only": True,
        }

    body = render_comment(result, publication_id=pub_id)
    try:
        gh.comment(repository, issue_number, body)
    except Exception as exc:
        _persist("OUTCOME_UNKNOWN", error=type(exc).__name__)
        return {
            **result,
            "state": "RECONCILIATION_REQUIRED",
            "prior_state": "DISPATCHING",
            "error": type(exc).__name__,
            "reconcile_only": True,
        }

    comments_after = _list_comments()
    if comments_after is None:
        _persist("OUTCOME_UNKNOWN", error="GH_COMMENTS_READBACK_FAILED")
        return {
            **result,
            "state": "RECONCILIATION_REQUIRED",
            "prior_state": "DISPATCHING",
            "error": "GH_COMMENTS_READBACK_FAILED",
            "reconcile_only": True,
        }

    count_after, matching_after = _find_markers(comments_after)
    if count_after == 1:
        _persist("COMPLETED", comment_id=matching_after[0].get("id"))
        return {**result, "state": "COMPLETE"}
    elif count_after > 1:
        _persist("OUTCOME_UNKNOWN", error="DUPLICATE_PUBLICATION_MARKER")
        return {
            **result,
            "state": "RECONCILIATION_REQUIRED",
            "prior_state": "DISPATCHING",
            "error": "DUPLICATE_PUBLICATION_MARKER",
            "reconcile_only": True,
        }
    else:
        _persist("OUTCOME_UNKNOWN", error="PUBLICATION_OUTCOME_UNKNOWN")
        return {
            **result,
            "state": "RECONCILIATION_REQUIRED",
            "prior_state": "DISPATCHING",
            "error": "PUBLICATION_OUTCOME_UNKNOWN",
            "reconcile_only": True,
        }


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
            if (
                result.get("state") in TERMINAL_DISPOSITIONS
                or result.get("state") == "RECONCILIATION_REQUIRED"
                or result.get("state") == "BLOCKED"
            ):
                last = {
                    "status": result.get("state"),
                    "repository": repository,
                    "issue_number": int(issue["number"]),
                    "result": result,
                }
                continue
            if result.get("state") == "COMPLETE":
                state_store = getattr(automation, "state_store", None)
                pub_result = reconcile_publication(
                    repository=repository,
                    issue_number=int(issue["number"]),
                    result=result,
                    gh=gh,
                    config=config,
                    state_store=state_store,
                    identity_hash=result.get("identity_hash"),
                )
                if pub_result.get("state") in {"RECONCILIATION_REQUIRED", "BLOCKED"}:
                    last = {
                        "status": pub_result.get("state"),
                        "repository": repository,
                        "issue_number": int(issue["number"]),
                        "result": pub_result,
                    }
                    continue
                if result.get("reuse") and (
                    not config.publication_enabled
                    or (pub_result.get("publication_record") or {}).get("state") == "COMPLETED"
                ):
                    last = {
                        "status": "COMPLETE",
                        "repository": repository,
                        "issue_number": int(issue["number"]),
                        "result": pub_result,
                    }
                    continue
                return {
                    "status": pub_result.get("state"),
                    "repository": repository,
                    "issue_number": int(issue["number"]),
                    "result": pub_result,
                }
            if result.get("reuse"):
                last = {
                    "status": result.get("state"),
                    "repository": repository,
                    "issue_number": int(issue["number"]),
                    "result": result,
                }
                continue
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


_BOOTOUT_UNLOAD_TIMEOUT = "BOOTOUT_UNLOAD_TIMEOUT"
_TERMINAL_BOOTOUT_FAILURE = "TERMINAL_BOOTOUT_FAILURE"
_TERMINAL_BOOTSTRAP_FAILURE = "TERMINAL_BOOTSTRAP_FAILURE"
_TERMINAL_PRINT_FAILURE = "TERMINAL_PRINT_FAILURE"
_DEFAULT_UNLOAD_DEADLINE = 30.0
_DEFAULT_UNLOAD_POLL_INTERVAL = 0.5
_LAUNCHCTL_NOT_FOUND = "Could not find service"


def _is_label_loaded(
    label: str,
    *,
    launchctl_runner: Callable[..., Any] | None = None,
    uid: int | None = None,
) -> bool:
    """Return True if launchctl still reports the given label registered.

    Only the exact known not-found/unregistered output means unloaded (False).
    Permission, I/O, or other unexpected errors fail closed by raising
    ServiceError(_TERMINAL_PRINT_FAILURE) — the caller must never bootstrap
    when we cannot confirm label state.
    """
    runner = launchctl_runner or _launchctl
    domain_uid = uid if uid is not None else os.getuid()
    result = runner("print", f"gui/{domain_uid}/{label}")
    stdout = str(getattr(result, "stdout", "") or "")
    stderr = str(getattr(result, "stderr", "") or "")
    combined = stdout + stderr
    if _LAUNCHCTL_NOT_FOUND in combined:
        return False
    if getattr(result, "returncode", 1) != 0:
        raise ServiceError(_TERMINAL_PRINT_FAILURE)
    state_match = re.search(r"^\s*state\s*=\s*(\S+)", stdout, re.MULTILINE)
    if state_match:
        return True
    # A successful command without the documented state shape is not proof
    # that the service is unloaded.  Fail closed rather than bootstrapping
    # over an unknown launchd response.
    raise ServiceError(_TERMINAL_PRINT_FAILURE)


def _wait_until_unloaded(
    label: str,
    *,
    launchctl_runner: Callable[..., Any] | None = None,
    deadline: float = _DEFAULT_UNLOAD_DEADLINE,
    poll_interval: float = _DEFAULT_UNLOAD_POLL_INTERVAL,
) -> None:
    """Poll until exact label is confirmed unloaded or deadline expires.

    Raises ServiceError on timeout or unexpected launchctl error.
    """
    start_time = time.monotonic()
    while True:
        if not _is_label_loaded(label, launchctl_runner=launchctl_runner):
            return
        elapsed = time.monotonic() - start_time
        if elapsed >= deadline:
            raise ServiceError(_BOOTOUT_UNLOAD_TIMEOUT)
        time.sleep(min(poll_interval, deadline - elapsed))


def _bootstrap(
    domain: str, plist_path: str, *, runner: Callable[..., Any] | None = None
) -> subprocess.CompletedProcess[str]:
    """Bootstrap the plist and return a result with distinct error codes."""
    bootstrap = (runner or _launchctl)("bootstrap", domain, plist_path)
    if bootstrap.returncode != 0:
        msg = str(getattr(bootstrap, "stderr", "") or "").strip()
        return subprocess.CompletedProcess(
            ["launchctl", "bootstrap", domain, plist_path],
            returncode=1,
            stdout=_TERMINAL_BOOTSTRAP_FAILURE,
            stderr=f"{_TERMINAL_BOOTSTRAP_FAILURE}: {msg}" if msg else _TERMINAL_BOOTSTRAP_FAILURE,
        )
    return bootstrap


def start(config_path: str | os.PathLike[str]):
    """Install the plist and bootstrap.  Best-effort bootout of any prior
    instance; the caller is not required to wait for unload.  For the
    durability-aware stop-wait-bootstrap sequence, use ``restart()``."""
    plist = install(config_path)
    domain = f"gui/{os.getuid()}"
    _launchctl("bootout", f"{domain}/{SERVICE_LABEL}")
    return _launchctl("bootstrap", domain, str(plist))


def restart(
    config_path: str | os.PathLike[str],
    *,
    launchctl_runner: Callable[..., Any] | None = None,
    deadline: float = _DEFAULT_UNLOAD_DEADLINE,
    poll_interval: float = _DEFAULT_UNLOAD_POLL_INTERVAL,
) -> subprocess.CompletedProcess[str]:
    """Durability-aware restart: stop once, wait for exact label unload, then
    bootstrap once.  This is the single coordination point for restart;
    no duplicate bootout race, no blind loop, no root escalation."""
    runner = launchctl_runner or _launchctl
    domain = f"gui/{os.getuid()}"
    try:
        bootout = stop(launchctl_runner=runner)
    except (OSError, subprocess.SubprocessError) as exc:
        msg = f"{_TERMINAL_BOOTOUT_FAILURE}: {exc}"
        return subprocess.CompletedProcess(
            ["launchctl", "bootout", f"{domain}/{SERVICE_LABEL}"],
            returncode=1,
            stdout=_TERMINAL_BOOTOUT_FAILURE,
            stderr=msg,
        )
    if bootout.returncode != 0:
        bootout_output = "".join(
            str(getattr(bootout, field, "") or "") for field in ("stdout", "stderr")
        )
        if _LAUNCHCTL_NOT_FOUND not in bootout_output:
            msg = f"{_TERMINAL_BOOTOUT_FAILURE}: {bootout_output.strip()}".rstrip()
            return subprocess.CompletedProcess(
                ["launchctl", "bootout", f"{domain}/{SERVICE_LABEL}"],
                returncode=1,
                stdout=_TERMINAL_BOOTOUT_FAILURE,
                stderr=msg,
            )
    try:
        _wait_until_unloaded(
            SERVICE_LABEL,
            launchctl_runner=runner,
            deadline=deadline,
            poll_interval=poll_interval,
        )
    except ServiceError as exc:
        msg = str(exc)
        return subprocess.CompletedProcess(
            ["launchctl", "bootstrap", domain, str(config_path)],
            returncode=1,
            stdout=msg,
            stderr=msg,
        )
    # Do not write/overwrite the installed plist until bootout has succeeded
    # (or the exact already-unloaded response was observed) and launchd has
    # confirmed the label is gone.
    plist = install(config_path)
    return _bootstrap(domain, str(plist), runner=runner)


def stop(launchctl_runner: Callable[..., Any] | None = None):
    return (launchctl_runner or _launchctl)("bootout", f"gui/{os.getuid()}/{SERVICE_LABEL}")


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
        r = restart(args.config)
        value = {
            "status": "RESTARTED" if r.returncode == 0 else "RESTART_FAILED",
            "detail": r.stderr.strip(),
        }
    else:
        value = service_status(args.config)
    print(json.dumps(value, sort_keys=True))
    status = str(value.get("status") or "")
    if args.command == "run-once":
        if status in {"IDLE", "COMPLETE"}:
            return NexusExitCode.SUCCESS
        if status in TERMINAL_DISPOSITIONS | {"ESCALATED", "RECONCILIATION_REQUIRED"}:
            return NexusExitCode.ESCALATED
        if status in {"BLOCKED", "HUMAN_REVIEW"}:
            return NexusExitCode.HUMAN_REVIEW
        return NexusExitCode.FAILED
    if status in {"START_FAILED", "STOP_FAILED", "RESTART_FAILED"}:
        return NexusExitCode.FAILED
    return NexusExitCode.SUCCESS


if __name__ == "__main__":
    raise SystemExit(main())
