"""Single GPT-visible MCP gateway for bounded Nexus workspace/lifecycle actions.

The gateway deliberately exposes a small public surface.  The existing
29-action self-hosted server remains an internal lifecycle provider; callers
must not need to know its Target paths or internal action names.
"""

from __future__ import annotations

import hashlib
import json
import fcntl
import difflib
import os
import re
import signal
import shlex
import shutil
import subprocess
import threading
import time
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping, Optional
from uuid import uuid4

from nexus.engine.capability_planner import CapabilityPlanner
from nexus.contracts.lifecycle_action import (
    ContractKind,
    LifecycleActionType,
    MutationDomain,
    PermissionProfile,
    build_owner_inline_contract,
    build_action_envelope,
)
from nexus.orchestrator.self_hosted_task_service import CANONICAL_SOURCE_ROOT, SelfHostedTaskService
from nexus.services.unified_runtime import ONLINE_CLI_SPEC_REGISTRY
from nexus.services.model_workforce_policy import NON_ADMISSIBLE_STATES, WorkforcePolicyLoader
from nexus.orchestrator.lifecycle_guards import (
    LifecycleGuardError,
    configure_runtime_manifest_hash,
    post_action_receipt_formatter,
    pre_action_guard,
    validate_approval_grant,
)

GATEWAY_NAME = "nexus-mcp-gateway"
GATEWAY_VERSION = "0.1.0"
PUBLIC_APP_NAME = "Nexus"
SERVER_INSTANCE_ID = uuid4().hex
SERVER_STARTED_AT = datetime.now(timezone.utc).isoformat()
LIFECYCLE_REVISION = "nexus.lifecycle.gateway.v2"
LIFECYCLE_STATE_SCHEMA_REVISION = "nexus.self_hosted_task_state.v1"
TASK_CONTRACT_REVISION = "nexus.task_contract.v1"
PERMISSION_POLICY_REVISION = "nexus.permission.policy.v1"
PERMISSION_POLICY = {
    "revision": PERMISSION_POLICY_REVISION,
    "profiles": ["DISCOVERY", "OBSERVE", "VERIFY", "MUTATE_BOUNDED", "CANDIDATE", "INTEGRATE"],
    "approval_scopes": ["ALLOW_ACTION_ONCE", "ALLOW_TASK_ATTEMPT", "REJECT"],
    "always_allow": False,
}
PERMISSION_POLICY_HASH = hashlib.sha256(
    json.dumps(PERMISSION_POLICY, sort_keys=True, separators=(",", ":")).encode("utf-8")
).hexdigest()
MAX_READ_BYTES = 1024 * 1024
MAX_RESULT_BYTES = 1024 * 1024
MAX_SEARCH_RESULTS = 200
_SHA_RE = re.compile(r"^[0-9a-f]{40}$")

# Populated from ``UnifiedMCPGateway.tool_specs()`` after the class definition.
# There must be one public manifest truth; status, health, recovery validation,
# and the MCP initialize revision all consume this derived tuple.
PUBLIC_TOOL_NAMES: tuple[str, ...]
TOOL_MANIFEST_REVISION: str
FULL_TOOL_SCHEMA_HASH: str
SERVER_REPO_HEAD_AT_START: str


class GatewayInputError(ValueError):
    """Raised when a public gateway request is outside its bounded contract."""


def _text(value: Any, field: str, *, max_length: int = 4096) -> str:
    result = str(value or "").strip()
    if not result:
        raise GatewayInputError(f"{field} is required")
    if len(result) > max_length:
        raise GatewayInputError(f"{field} exceeds {max_length} characters")
    return result


def _safe_relative_path(value: Any, field: str = "path") -> Path:
    raw = _text(value, field, max_length=1024)
    candidate = Path(raw)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise GatewayInputError(f"{field} must be a bounded relative path")
    if ".git" in candidate.parts:
        raise GatewayInputError(f"{field} cannot access .git")
    resolved = (CANONICAL_SOURCE_ROOT / candidate).resolve()
    try:
        resolved.relative_to(CANONICAL_SOURCE_ROOT)
    except ValueError as exc:
        raise GatewayInputError(f"{field} escapes canonical root") from exc
    return resolved


def _git(*args: str, timeout: float = 3.0) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=CANONICAL_SOURCE_ROOT,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"git command failed: {' '.join(args)}")
    return result.stdout


def _bounded_text(value: str, field: str) -> str:
    if len(value.encode("utf-8")) > MAX_RESULT_BYTES:
        raise RuntimeError(f"{field} exceeds {MAX_RESULT_BYTES} bytes")
    return value


class UnifiedMCPGateway:
    """JSON-RPC MCP server with one public identity and bounded tools."""

    def __init__(self, service: Optional[SelfHostedTaskService] = None, *, model_runner: Any = None, apply_runner: Any = None):
        self.service = service or SelfHostedTaskService()
        self._model_runner = model_runner or self._run_agy_plan
        self._apply_runner = apply_runner or self._apply_assisted_patch
        self._workforce_loader = WorkforcePolicyLoader()
        self._assist_processes: dict[str, subprocess.Popen[str]] = {}
        self._assist_lock = threading.RLock()

    @staticmethod
    def _utc_now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def _assist_root(self) -> Path:
        configured = getattr(self.service, "state_dir", None)
        root = Path(configured).expanduser().resolve() if configured else Path("/tmp/nexus-mcp-gateway-assist-jobs")
        root = root / "assisted_provider_jobs"
        root.mkdir(parents=True, exist_ok=True)
        return root

    def _assist_path(self, task_id: str) -> Path:
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}", str(task_id)):
            raise GatewayInputError("task_id must be a stable bounded slug")
        return self._assist_root() / f"{task_id}.json"

    def _assist_read(self, task_id: str) -> Optional[dict[str, Any]]:
        path = self._assist_path(task_id)
        if not path.exists():
            return None
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        return value if isinstance(value, dict) else None

    def _assist_write(self, value: Mapping[str, Any]) -> dict[str, Any]:
        task_id = _text(value.get("task_id"), "task_id")
        path = self._assist_path(task_id)
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(dict(value), sort_keys=True, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(temporary, path)
        return dict(value)

    @staticmethod
    def _assist_command(*, executable: str, provider: str, model: str, prompt: str) -> list[str]:
        if provider == "cline":
            selected = model or "glm-5.2"
            if "/" not in selected:
                selected = f"cline-pass/{selected}"
            return [executable, "--json", "--plan", "--auto-approve", "false", "--thinking", "none", "--model", selected, prompt]
        if provider == "agy":
            return [executable, "--mode", "plan", "--sandbox", "--output-format", "json", "--effort", "low", "--print-timeout", "25s", "--prompt", prompt]
        if provider == "gemini":
            return [executable, "--skip-trust", "--approval-mode", "auto_edit", "-m", model, "-p", prompt, "--output-format", "json"]
        if provider == "opencode":
            return [executable, "run", "--model", model, prompt]
        if provider == "mimo":
            return [executable, "run", "--never-ask-questions", "--model", model, prompt]
        if provider == "ollama":
            return [executable, "run", model, prompt]
        if provider == "grok":
            return [executable, "--model", model, "--single", prompt, "--output-format", "json", "--no-alt-screen"]
        if provider == "codex":
            return [executable, "exec", "--json", "--full-auto", "-m", model, prompt]
        raise GatewayInputError("ASSIST_ASYNC_PROVIDER_UNSUPPORTED")

    @staticmethod
    def _decode_assist_payload(text: str, provider: str, *, require_patch: bool = False) -> Optional[dict[str, Any]]:
        decoder = json.JSONDecoder()
        candidates: list[Any] = []
        stripped = text.strip()
        if stripped:
            try:
                candidates.append(json.loads(stripped))
            except json.JSONDecodeError:
                pass
        for line in reversed(text.splitlines()):
            try:
                candidates.append(json.loads(line))
            except json.JSONDecodeError:
                pass

        # Cline emits JSON events, and some versions wrap the event stream in
        # an array.  Extract complete JSON values instead of using a greedy
        # object regex, which can join unrelated log objects together.
        if provider == "cline":
            for index, char in enumerate(text):
                if char not in "[{":
                    continue
                try:
                    value, _ = decoder.raw_decode(text[index:])
                except json.JSONDecodeError:
                    continue
                candidates.append(value)

        def visit(value: Any) -> Optional[dict[str, Any]]:
            if isinstance(value, dict):
                if "patch" in value:
                    return value
                if not require_patch:
                    return value
                # These are the documented/observed Cline envelope fields.
                # Preserve event order and inspect the final content first.
                nested_values: list[Any] = []
                for key in ("text", "content", "message", "result", "output", "data", "event", "payload"):
                    if key in value:
                        nested_values.append(value[key])
                for nested in reversed(nested_values):
                    if isinstance(nested, str) and nested.strip():
                        found = UnifiedMCPGateway._decode_assist_payload(nested, provider, require_patch=require_patch)
                    else:
                        found = visit(nested)
                    if found is not None:
                        return found
                return None if require_patch or provider == "cline" else value
            if isinstance(value, list):
                for item in reversed(value):
                    found = visit(item)
                    if found is not None:
                        return found
            return None

        for candidate in candidates:
            found = visit(candidate)
            if found is not None:
                return found
        return None

    @staticmethod
    def _snapshot_workspace(root: Path) -> dict[str, str]:
        snapshot: dict[str, str] = {}
        if not root.exists():
            return snapshot
        for path in sorted(item for item in root.rglob("*") if item.is_file()):
            try:
                snapshot[str(path.relative_to(root))] = UnifiedMCPGateway._hash_file(path)
            except OSError:
                snapshot[str(path.relative_to(root))] = "unreadable"
        return snapshot

    @staticmethod
    def _validate_output_schema(value: Any, schema: Any) -> tuple[bool, str]:
        if not isinstance(schema, Mapping):
            return True, ""
        def validate(current: Any, shape: Mapping[str, Any], path: str = "$") -> str:
            expected = shape.get("type")
            type_ok = {
                "object": lambda x: isinstance(x, Mapping),
                "array": lambda x: isinstance(x, list),
                "string": lambda x: isinstance(x, str),
                "number": lambda x: isinstance(x, (int, float)) and not isinstance(x, bool),
                "integer": lambda x: isinstance(x, int) and not isinstance(x, bool),
                "boolean": lambda x: isinstance(x, bool),
                "null": lambda x: x is None,
            }
            if expected in type_ok and not type_ok[expected](current):
                return f"output_schema_type:{path}:{expected}"
            if "enum" in shape and current not in shape.get("enum", []):
                return f"output_schema_enum:{path}"
            if isinstance(current, Mapping):
                missing = [str(field) for field in shape.get("required", []) or [] if str(field) not in current]
                if missing:
                    return "output_schema_missing:" + ",".join(f"{path}.{field}" for field in missing)
                properties = shape.get("properties") if isinstance(shape.get("properties"), Mapping) else {}
                for key, child in properties.items():
                    if key in current and isinstance(child, Mapping):
                        error = validate(current[key], child, f"{path}.{key}")
                        if error:
                            return error
                if shape.get("additionalProperties") is False:
                    extras = sorted(set(current) - set(properties))
                    if extras:
                        return f"output_schema_additional:{path}:{','.join(map(str, extras))}"
            if isinstance(current, list) and isinstance(shape.get("items"), Mapping):
                for index, item in enumerate(current):
                    error = validate(item, shape["items"], f"{path}[{index}]")
                    if error:
                        return error
            return ""

        error = validate(value, schema)
        return (not bool(error), error)

    def _assist_refresh(self, task_id: str) -> Optional[dict[str, Any]]:
        job = self._assist_read(task_id)
        if job is None:
            return None
        if job.get("status") in {"COMPLETED", "FAILED", "CANCELLED"}:
            return job
        with self._assist_lock:
            process = self._assist_processes.get(task_id)
        returncode = process.poll() if process is not None else None
        if process is not None and returncode is not None:
            job["durable_exit_marker"] = True
            job["durable_exit_code"] = returncode
        if process is None and job.get("pid"):
            try:
                os.kill(int(job["pid"]), 0)
                return job
            except (OSError, ValueError):
                # A restarted Gateway may retain artifacts but no durable exit
                # marker.  Output alone is not completion evidence: fail closed
                # and require an explicit reconciliation decision.
                if not job.get("durable_exit_marker"):
                    job.update({
                        "status": "UNKNOWN_REQUIRES_RECONCILE",
                        "blocker": "ASSIST_PROVIDER_PROCESS_LOST",
                        "reconciliation_required": True,
                        "last_polled_at": self._utc_now(),
                    })
                    return self._assist_write(job)
                returncode = job.get("exit_code")
        if returncode is None:
            job["status"] = "RUNNING"
            job["last_polled_at"] = self._utc_now()
            return self._assist_write(job)
        stdout_path = Path(str(job.get("stdout_artifact") or ""))
        stderr_path = Path(str(job.get("stderr_artifact") or ""))
        stdout = stdout_path.read_text(encoding="utf-8", errors="replace") if stdout_path.exists() else ""
        stderr = stderr_path.read_text(encoding="utf-8", errors="replace") if stderr_path.exists() else ""
        require_patch = str(job.get("job_kind") or "assist") != "model_probe"
        parsed = self._decode_assist_payload(stdout, str(job.get("provider") or ""), require_patch=require_patch)
        schema_valid, schema_error = self._validate_output_schema(parsed, job.get("output_schema"))
        started_at = job.get("started_at")
        provider_time_ms = 0
        if started_at:
            try:
                provider_time_ms = max(0, int((time.time() - datetime.fromisoformat(str(started_at)).timestamp()) * 1000))
            except (TypeError, ValueError):
                provider_time_ms = 0
        job.update({
            "status": "COMPLETED" if returncode == 0 and parsed is not None and schema_valid else "FAILED",
            "finished_at": self._utc_now(),
            "exit_code": returncode,
            "result": parsed,
            "blocker": ("ASSIST_PROVIDER_MALFORMED_OUTPUT" if returncode == 0 and (parsed is None or not schema_valid) else ("ASSIST_PROVIDER_FAILED" if returncode != 0 else None)),
            "schema_error": schema_error,
            "schema_validation_level": "bounded_subset",
            "provider_error": stderr[-1000:] if returncode != 0 else "",
            "provider_time_ms": provider_time_ms,
        })
        self._assist_record_stream_artifacts(job)
        workspace_root = Path(str(job.get("workspace_root") or ""))
        if workspace_root.exists() and workspace_root != CANONICAL_SOURCE_ROOT:
            after = self._snapshot_workspace(workspace_root)
            before = job.get("filesystem_before") if isinstance(job.get("filesystem_before"), Mapping) else {}
            job["filesystem_after"] = after
            job["filesystem_delta"] = {
                "created": sorted(set(after) - set(before)),
                "removed": sorted(set(before) - set(after)),
                "changed": sorted(path for path in set(before) & set(after) if before[path] != after[path]),
            }
            try:
                shutil.rmtree(workspace_root)
                job["process_cleanup"] = True
            except OSError as exc:
                job["process_cleanup"] = False
                job["cleanup_error"] = str(exc)
        with self._assist_lock:
            self._assist_processes.pop(task_id, None)
        return self._assist_write(job)

    def _assist_response(self, job: Mapping[str, Any], *, operation: str = "status") -> dict[str, Any]:
        status = str(job.get("status") or "UNKNOWN")
        terminal = status in {"COMPLETED", "FAILED", "CANCELLED"}
        result_tool = "nexus_model_probe_result" if str(job.get("job_kind") or "assist") == "model_probe" else "nexus_assist_result"
        if status == "UNKNOWN_REQUIRES_RECONCILE":
            next_action = "nexus_task_reconcile"
        else:
            next_action = result_tool if not terminal else ("none" if status == "COMPLETED" else "nexus_task_retry")
        return {
            "schema": "nexus.assisted_provider_job.v1",
            "operation": operation,
            "task_id": job.get("task_id"),
            "job_id": job.get("job_id"),
            "action_id": job.get("action_id"),
            "attempt_id": job.get("attempt_id"),
            "attempt_history": job.get("attempt_history", []),
            "status": status,
            "execution_lane": "ASSISTED_CANONICAL",
            "candidate_only": True,
            "apply_requested": bool(job.get("apply_requested")),
            "provider": job.get("provider"),
            "model": job.get("model"),
            "command_hash": job.get("command_hash"),
            "job_kind": job.get("job_kind", "assist"),
            "workspace_mode": job.get("workspace_mode", "isolated"),
            "workspace_root": job.get("workspace_root"),
            "pid": job.get("pid"),
            "pgid": job.get("pgid"),
            "started_at": job.get("started_at"),
            "finished_at": job.get("finished_at"),
            "exit_code": job.get("exit_code"),
            "provider_time_ms": job.get("provider_time_ms", 0),
            "provider_started": bool(job.get("started_at")),
            "binary_exec_started": job.get("started_at"),
            "last_stdout_at": job.get("last_stdout_at"),
            "last_stderr_at": job.get("last_stderr_at"),
            "stdout_sha256": job.get("stdout_sha256"),
            "stderr_sha256": job.get("stderr_sha256"),
            "stdout_bytes": job.get("stdout_bytes"),
            "stderr_bytes": job.get("stderr_bytes"),
            "durable_exit_marker": bool(job.get("durable_exit_marker", False)),
            "reconciliation_required": bool(job.get("reconciliation_required", False)),
            "context_arm": job.get("context_arm"),
            "context_arm_applied": bool(job.get("context_arm_applied", False)),
            "context_arm_semantics": job.get("context_arm_semantics", "record_only_not_applied"),
            "result": job.get("result") if status == "COMPLETED" else None,
            "blocker": job.get("blocker"),
            "provider_error": job.get("provider_error", ""),
            "schema_error": job.get("schema_error", ""),
            "schema_validation_level": job.get("schema_validation_level", "bounded_subset"),
            "requested_tools_policy": job.get("requested_tools_policy", []),
            "tool_policy_enforcement": job.get("tool_policy_enforcement", "not_enforced"),
            "filesystem_delta": job.get("filesystem_delta", {"created": [], "removed": [], "changed": []}),
            "process_cleanup": job.get("process_cleanup", False),
            "process_killed": bool(job.get("process_killed", False)),
            "stream_flush_status": job.get("stream_flush_status", "not_observed"),
            "connector_disconnected_at": job.get("connector_disconnected_at"),
            "reconnected_at": job.get("reconnected_at"),
            "artifacts": {"stdout": job.get("stdout_artifact"), "stderr": job.get("stderr_artifact")},
            "attention_required": status in {"FAILED", "CANCELLED", "UNKNOWN_REQUIRES_RECONCILE"},
            "next_action": next_action,
            "recommended_tool": next_action,
        }

    def _assist_submit(self, arguments: Mapping[str, Any], *, action: Optional[Mapping[str, Any]] = None) -> dict[str, Any]:
        task_id = self._task_id(arguments, str(arguments.get("what") or "assist"), str(arguments.get("why") or "assist"), [str(path) for path in arguments.get("allowed_files") or []])
        existing = self._assist_read(task_id)
        if existing is not None:
            return self._assist_response(self._assist_refresh(task_id) or existing, operation="submit")
        provider = str(arguments.get("provider") or arguments.get("preferred_worker") or "cline").strip().lower()
        model = str(arguments.get("model") or arguments.get("preferred_model") or "glm-5.2").strip()
        if provider != "cline":
            raise GatewayInputError("ASSIST_ASYNC_PROVIDER_UNSUPPORTED")
        metadata = ONLINE_CLI_SPEC_REGISTRY.get(provider)
        if metadata is None:
            raise GatewayInputError("ASSIST_PROVIDER_NOT_REGISTERED")
        binary_env = metadata.get("binary_env", "")
        configured = os.environ.get(binary_env, "").strip() if binary_env else ""
        executable = configured or shutil.which(metadata.get("binary_name", provider))
        if not executable or not Path(executable).is_file():
            raise GatewayInputError("ASSIST_PROVIDER_UNAVAILABLE")
        allowed = [str(path).strip() for path in arguments.get("allowed_files") or [] if str(path).strip()]
        if not allowed or len(allowed) > 4:
            raise GatewayInputError("allowed_files must contain 1-4 bounded paths")
        for path in allowed:
            _safe_relative_path(path, "allowed_files")
        prompt = self._assist_prompt(str(arguments.get("what") or "assist"), str(arguments.get("why") or "assist"), allowed, list(arguments.get("verifier_commands") or ["git diff --check"]))
        command = self._assist_command(executable=executable, provider=provider, model=model, prompt=prompt)
        job_id = f"assist-{uuid4().hex}"
        root = self._assist_root()
        stdout_path = root / f"{job_id}.stdout"
        stderr_path = root / f"{job_id}.stderr"
        workspace_root = Path(tempfile.mkdtemp(prefix=f"nexus-assist-{task_id}-", dir="/tmp"))
        action_value = dict(action or {})
        if not action_value:
            base = _git("rev-parse", "HEAD").strip()
            action_value = build_action_envelope(
                task_id=task_id,
                action_type=LifecycleActionType.TASK_RUN,
                request={
                    "task_id": task_id,
                    "what": str(arguments.get("what") or "assist"),
                    "why": str(arguments.get("why") or "assist"),
                    "allowed_files": allowed,
                    "apply": False,
                },
                tool_manifest_hash=TOOL_MANIFEST_REVISION,
                expected_head=base,
                allowed_paths=allowed,
                mutation=False,
                permission_profile=PermissionProfile.VERIFY,
            ).model_dump(mode="json")
        now = self._utc_now()
        job: dict[str, Any] = {
            "schema": "nexus.assisted_provider_job.v1",
            "job_kind": "assist",
            "task_id": task_id,
            "job_id": job_id,
            "attempt_history": [],
            "action_id": action_value.get("action_id") or f"action-{uuid4().hex}",
            "attempt_id": action_value.get("attempt_id") or f"attempt-{uuid4().hex}",
            "status": "SUBMITTED",
            "execution_lane": "ASSISTED_CANONICAL",
            "candidate_only": True,
            "apply_requested": bool(arguments.get("apply", False)),
            "workspace_mode": "isolated",
            "workspace_root": str(workspace_root),
            "filesystem_before": self._snapshot_workspace(workspace_root),
            "filesystem_after": None,
            "filesystem_delta": {"created": [], "removed": [], "changed": []},
            "process_cleanup": False,
            "output_schema": {"type": "object", "required": ["patch"]},
            "result_artifact": str(self._assist_path(task_id)),
            "provider": provider,
            "model": model if "/" in model else f"cline-pass/{model}",
            "command_hash": hashlib.sha256(json.dumps(command, separators=(",", ":")).encode("utf-8")).hexdigest(),
            "command": command,
            "submitted_at": now,
            "started_at": None,
            "finished_at": None,
            "provider_time_ms": 0,
            "stdout_artifact": str(stdout_path),
            "stderr_artifact": str(stderr_path),
            "action": action_value,
            "connector_disconnected_at": None,
            "reconnected_at": None,
        }
        self._assist_write(job)
        started = time.perf_counter()
        stdout_handle = stdout_path.open("w", encoding="utf-8")
        stderr_handle = stderr_path.open("w", encoding="utf-8")
        try:
            process = subprocess.Popen(command, cwd=workspace_root, stdout=stdout_handle, stderr=stderr_handle, text=True, start_new_session=True)
        except Exception:
            stdout_handle.close()
            stderr_handle.close()
            shutil.rmtree(workspace_root, ignore_errors=True)
            job.update({"status": "FAILED", "finished_at": self._utc_now(), "blocker": "ASSIST_PROVIDER_FAILED", "provider_error": "provider process could not start"})
            return self._assist_response(self._assist_write(job), operation="submit")
        stdout_handle.close()
        stderr_handle.close()
        job.update({"status": "RUNNING", "pid": process.pid, "pgid": process.pid, "started_at": self._utc_now(), "provider_start_ms": max(0, int((time.perf_counter() - started) * 1000))})
        with self._assist_lock:
            self._assist_processes[task_id] = process
        return self._assist_response(self._assist_write(job), operation="submit")

    def _assist_wait(self, task_id: str, *, timeout_seconds: float = 10.0, poll_interval_seconds: float = 0.25) -> dict[str, Any]:
        deadline = time.monotonic() + max(0.0, min(60.0, timeout_seconds))
        while True:
            job = self._assist_refresh(task_id)
            if job is None:
                raise KeyError(f"unknown task_id: {task_id}")
            response = self._assist_response(job, operation="wait")
            if response["status"] in {"COMPLETED", "FAILED", "CANCELLED", "UNKNOWN_REQUIRES_RECONCILE"} or time.monotonic() >= deadline:
                return response
            time.sleep(max(0.01, min(5.0, poll_interval_seconds)))

    def _cleanup_assist_workspace(self, job: dict[str, Any]) -> None:
        workspace_root = Path(str(job.get("workspace_root") or ""))
        if not workspace_root.exists() or workspace_root == CANONICAL_SOURCE_ROOT:
            job["process_cleanup"] = workspace_root == CANONICAL_SOURCE_ROOT or not workspace_root.exists()
            return
        after = self._snapshot_workspace(workspace_root)
        before = job.get("filesystem_before") if isinstance(job.get("filesystem_before"), Mapping) else {}
        job["filesystem_after"] = after
        job["filesystem_delta"] = {
            "created": sorted(set(after) - set(before)),
            "removed": sorted(set(before) - set(after)),
            "changed": sorted(path for path in set(before) & set(after) if before[path] != after[path]),
        }
        try:
            shutil.rmtree(workspace_root)
            job["process_cleanup"] = True
        except OSError as exc:
            job["process_cleanup"] = False
            job["cleanup_error"] = str(exc)

    @staticmethod
    def _assist_record_stream_artifacts(job: dict[str, Any]) -> None:
        """Record flushed stdout/stderr evidence after the child has exited.

        Cancellation must not report cleanup closure while leaving the durable
        receipt without the bytes that were already emitted.  Reading after a
        bounded wait/reap makes the hashes an observation of the final files,
        not a promise that the provider completed successfully.
        """
        streams = {
            "stdout": Path(str(job.get("stdout_artifact") or "")),
            "stderr": Path(str(job.get("stderr_artifact") or "")),
        }
        complete = True
        for name, path in streams.items():
            if not path.exists():
                complete = False
                job[f"{name}_sha256"] = None
                job[f"{name}_bytes"] = 0
                job[f"last_{name}_at"] = None
                continue
            try:
                data = path.read_bytes()
                stat = path.stat()
            except OSError:
                complete = False
                job[f"{name}_sha256"] = None
                job[f"{name}_bytes"] = 0
                job[f"last_{name}_at"] = None
                continue
            job[f"{name}_sha256"] = hashlib.sha256(data).hexdigest()
            job[f"{name}_bytes"] = len(data)
            job[f"last_{name}_at"] = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat()
        job["stream_flush_status"] = "FLUSHED" if complete else "PARTIAL_OR_MISSING"

    def _assist_cancel(self, task_id: str) -> dict[str, Any]:
        job = self._assist_refresh(task_id)
        if job is None:
            raise KeyError(f"unknown task_id: {task_id}")
        if job.get("status") == "UNKNOWN_REQUIRES_RECONCILE":
            job.update({
                "status": "CANCELLED",
                "finished_at": self._utc_now(),
                "blocker": "ASSIST_PROVIDER_PROCESS_LOST",
                "process_killed": False,
            })
            self._assist_record_stream_artifacts(job)
            self._cleanup_assist_workspace(job)
            self._assist_write(job)
        elif job.get("status") not in {"COMPLETED", "FAILED", "CANCELLED"}:
            pid = int(job.get("pid") or 0)
            process = None
            with self._assist_lock:
                process = self._assist_processes.get(task_id)
            terminated = False
            if pid:
                try:
                    os.killpg(int(job.get("pgid") or pid), signal.SIGTERM)
                except OSError:
                    pass
                deadline = time.monotonic() + 2.0
                while time.monotonic() < deadline:
                    if process is not None and process.poll() is not None:
                        terminated = True
                        break
                    try:
                        os.kill(pid, 0)
                    except OSError:
                        terminated = True
                        break
                    time.sleep(0.05)
                if not terminated:
                    try:
                        os.killpg(int(job.get("pgid") or pid), signal.SIGKILL)
                    except OSError:
                        pass
                    if process is not None:
                        try:
                            process.wait(timeout=2)
                        except subprocess.TimeoutExpired:
                            pass
                    try:
                        os.kill(pid, 0)
                    except OSError:
                        terminated = True
            job.update({
                "status": "CANCELLED",
                "finished_at": self._utc_now(),
                "blocker": "ASSIST_CANCELLED" if terminated else "ASSIST_CANCEL_CLEANUP_INCOMPLETE",
                "process_killed": terminated,
                "exit_code": process.returncode if process is not None else None,
            })
            self._assist_record_stream_artifacts(job)
            self._cleanup_assist_workspace(job)
            with self._assist_lock:
                self._assist_processes.pop(task_id, None)
            self._assist_write(job)
        return self._assist_response(job, operation="cancel")

    def _assist_retry(self, task_id: str) -> dict[str, Any]:
        job = self._assist_refresh(task_id)
        if job is None:
            raise KeyError(f"unknown task_id: {task_id}")
        if job.get("status") not in {"FAILED", "CANCELLED"}:
            raise GatewayInputError("ASSIST_RETRY_REQUIRES_TERMINAL_FAILURE")
        command = job.get("command")
        if not isinstance(command, list) or not command:
            raise GatewayInputError("ASSIST_RETRY_COMMAND_NOT_RETAINED")
        history = list(job.get("attempt_history") or [])
        history.append({
            "job_id": job.get("job_id"),
            "attempt_id": job.get("attempt_id"),
            "status": job.get("status"),
            "exit_code": job.get("exit_code"),
            "result_artifact": job.get("result_artifact"),
        })
        new_job_id = f"{str(job.get('job_kind') or 'assist')}-{uuid4().hex}"
        root = self._assist_root()
        stdout_path = root / f"{new_job_id}.stdout"
        stderr_path = root / f"{new_job_id}.stderr"
        workspace_root = Path(tempfile.mkdtemp(prefix=f"nexus-retry-{task_id}-", dir="/tmp"))
        new_job = dict(job)
        new_job.update({
            "job_id": new_job_id,
            "attempt_id": f"attempt-{uuid4().hex}",
            "attempt_history": history,
            "status": "SUBMITTED",
            "submitted_at": self._utc_now(),
            "started_at": None,
            "finished_at": None,
            "pid": None,
            "pgid": None,
            "exit_code": None,
            "blocker": None,
            "provider_error": "",
            "result": None,
            "stdout_artifact": str(stdout_path),
            "stderr_artifact": str(stderr_path),
            "result_artifact": str(self._assist_path(task_id)),
            "workspace_root": str(workspace_root),
            "filesystem_before": self._snapshot_workspace(workspace_root),
            "filesystem_after": None,
            "filesystem_delta": {"created": [], "removed": [], "changed": []},
            "process_cleanup": False,
            "process_killed": False,
            "connector_disconnected_at": None,
            "reconnected_at": self._utc_now(),
        })
        self._assist_write(new_job)
        stdout_handle = stdout_path.open("w", encoding="utf-8")
        stderr_handle = stderr_path.open("w", encoding="utf-8")
        try:
            process = subprocess.Popen(command, cwd=workspace_root, stdout=stdout_handle, stderr=stderr_handle, text=True, start_new_session=True)
        except Exception:
            stdout_handle.close()
            stderr_handle.close()
            shutil.rmtree(workspace_root, ignore_errors=True)
            new_job.update({"status": "FAILED", "finished_at": self._utc_now(), "blocker": "ASSIST_PROVIDER_FAILED", "provider_error": "provider process could not start"})
            return self._assist_response(self._assist_write(new_job), operation="retry")
        stdout_handle.close()
        stderr_handle.close()
        new_job.update({"status": "RUNNING", "pid": process.pid, "pgid": process.pid, "started_at": self._utc_now()})
        with self._assist_lock:
            self._assist_processes[task_id] = process
        return self._assist_response(self._assist_write(new_job), operation="retry")

    @staticmethod
    def _safe_slug(value: Any, field: str, *, max_length: int = 80) -> str:
        result = _text(value, field, max_length=max_length)
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0," + str(max_length - 1) + r"}", result):
            raise GatewayInputError(f"{field} must be a stable bounded slug")
        return result

    @staticmethod
    def _hash_file(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            while True:
                chunk = handle.read(1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
        return digest.hexdigest()

    def _provider_executable(self, provider: str) -> tuple[dict[str, str], Optional[str]]:
        metadata = ONLINE_CLI_SPEC_REGISTRY.get(provider)
        if metadata is None:
            return {}, None
        binary_env = metadata.get("binary_env", "")
        configured = os.environ.get(binary_env, "").strip() if binary_env else ""
        executable = configured or shutil.which(metadata.get("binary_name", provider))
        if not executable or not Path(executable).is_file() or not os.access(executable, os.X_OK):
            return metadata, None
        return metadata, executable

    def _provider_preflight(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        provider = str(arguments.get("provider") or "cline").strip().lower()
        requested_model = str(arguments.get("model") or arguments.get("preferred_model") or "").strip()
        if provider == "cline" and not requested_model:
            requested_model = "glm-5.2"
        metadata, executable = self._provider_executable(provider)
        resolved_model = requested_model
        if provider == "cline" and resolved_model and "/" not in resolved_model:
            resolved_model = f"cline-pass/{resolved_model}"
        result: dict[str, Any] = {
            "schema": "nexus.provider_preflight.v1",
            "provider": provider,
            "requested_model": requested_model,
            "resolved_model": resolved_model,
            "requested_model_verified": False,
            "resolved_model_evidence": None,
            "binary_found": bool(executable),
            "binary_path": executable,
            "binary_sha256": None,
            "cli_version": None,
            "authenticated": False,
            "model_reachable": False,
            "probe_requested": bool(arguments.get("probe", False)),
            "probe_latency_ms": 0,
            "exit_code": None,
            "stdout_sha256": None,
            "stderr_sha256": None,
            "status": "BLOCKED",
            "blocker": None,
            "next_action": None,
        }
        if not metadata:
            result["blocker"] = "ASSIST_PROVIDER_NOT_REGISTERED"
            return result
        if not executable:
            result["blocker"] = "ASSIST_PROVIDER_UNAVAILABLE"
            return result
        try:
            result["binary_sha256"] = self._hash_file(Path(executable))
        except OSError:
            result["blocker"] = "ASSIST_PROVIDER_BINARY_UNREADABLE"
            return result
        version_started = time.perf_counter()
        version_root = Path(tempfile.mkdtemp(prefix=f"nexus-preflight-{provider}-", dir="/tmp"))
        try:
            version = subprocess.run([executable, "--version"], cwd=version_root, capture_output=True, text=True, timeout=5, check=False)
        except (OSError, subprocess.TimeoutExpired) as exc:
            result["blocker"] = "ASSIST_PROVIDER_VERSION_FAILED"
            result["provider_error"] = str(exc)
            shutil.rmtree(version_root, ignore_errors=True)
            return result
        shutil.rmtree(version_root, ignore_errors=True)
        result["cli_version"] = (version.stdout or version.stderr).strip()[:512]
        result["version_latency_ms"] = max(0, int((time.perf_counter() - version_started) * 1000))
        if version.returncode != 0:
            result["exit_code"] = version.returncode
            result["blocker"] = "ASSIST_PROVIDER_VERSION_FAILED"
            return result
        # Model/auth execution is intentionally never synchronous here.  A
        # caller asking for probe=true receives a bounded handoff to the
        # isolated async model-probe surface, so ChatGPT request lifetimes and
        # the canonical checkout are not part of provider probing.
        if bool(arguments.get("probe", False)):
            result.update({
                "status": "VERSION_VERIFIED",
                "blocker": "MODEL_PROBE_ASYNC_REQUIRED",
                "next_action": "nexus_model_probe",
                "probe_mode": "deferred_async_isolated",
            })
        else:
            result.update({"status": "VERSION_VERIFIED", "blocker": "MODEL_PROBE_REQUIRED", "next_action": "nexus_model_probe"})
        return result

    def _task_card_create(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        if arguments.get("owner_confirmation") is not True:
            raise GatewayInputError("OWNER_CONFIRMATION_REQUIRED")
        campaign = self._safe_slug(arguments.get("campaign_id"), "campaign_id")
        task_id = self._safe_slug(arguments.get("task_id"), "task_id")
        objective = _text(arguments.get("objective"), "objective", max_length=4000)
        allowed = [str(path).strip() for path in arguments.get("allowed_files") or [] if str(path).strip()]
        if not allowed or len(allowed) > 10:
            raise GatewayInputError("allowed_files must contain 1-10 bounded paths")
        for path in allowed:
            _safe_relative_path(path, "allowed_files")
        verifiers = [str(command).strip() for command in arguments.get("verifier_commands") or [] if str(command).strip()]
        if not verifiers:
            raise GatewayInputError("verifier_commands is required")
        campaign_root = CANONICAL_SOURCE_ROOT / "tasks" / campaign
        index_path = campaign_root / "INDEX.md"
        card_path = campaign_root / f"00-{task_id}.md"
        if campaign_root.exists() or index_path.exists() or card_path.exists():
            raise GatewayInputError("TASK_CARD_CREATE_WOULD_OVERWRITE")
        card = "\n".join([
            f"# Task Card: {task_id}", "", "artifact_authority: current", f"task_id: `{task_id}`",
            "owner: James Chen", "status: ACTIVE", "commit_required: true", "candidate_required: true",
            "worker_may_commit: true", "worker_may_approve: false", "worker_may_integrate: false",
            "worker_may_push: false", "AUTO_CHAIN: false", "", "## Objective", "", objective, "",
            "## Allowed files", "", *[f"- `{path}`" for path in allowed], "", "## Verification commands", "",
            "```bash", *verifiers, "```", "", "## Exit criteria", "", "Owner review of the exact scoped commit.",
            "", "## Block classification", "", "Unverifiable or out-of-scope mutation is a HARD_BLOCK.", "",
        ])
        index = "\n".join([
            f"# Campaign Index: {campaign}", "", "artifact_authority: current", "owner: James Chen",
            "status: active, governed and sequential", "AUTO_CHAIN: false", "", "## Objective", "", objective,
            "", "## Ordered cards", "", "| Order | Task ID | Card | Status | Dependency |", "|---:|---|---|---|---|",
            f"| 0 | `{task_id}` | `00-{task_id}.md` | ACTIVE | Owner confirmation |", "",
        ])
        tasks_root = CANONICAL_SOURCE_ROOT / "tasks"
        tasks_root.mkdir(parents=True, exist_ok=True)
        temporary_root = tasks_root / f".{campaign}.create-{uuid4().hex}"
        try:
            temporary_root.mkdir(parents=False, exist_ok=False)
            temporary_index = temporary_root / "INDEX.md"
            temporary_card = temporary_root / f"00-{task_id}.md"
            temporary_index.write_text(index, encoding="utf-8")
            temporary_card.write_text(card, encoding="utf-8")
            if not temporary_index.is_file() or not temporary_card.is_file():
                raise RuntimeError("TASK_CARD_CREATE_ATOMIC_WRITE_FAILED")
            hashed = subprocess.run(["git", "hash-object", str(temporary_card)], cwd=CANONICAL_SOURCE_ROOT, capture_output=True, text=True, check=False)
            card_hash = hashed.stdout.strip()
            if hashed.returncode != 0 or not _SHA_RE.fullmatch(card_hash):
                raise RuntimeError("TASK_CARD_CREATE_HASH_FAILED")
            card_sha256 = hashlib.sha256(card.encode("utf-8")).hexdigest()
            if campaign_root.exists():
                raise GatewayInputError("TASK_CARD_CREATE_WOULD_OVERWRITE")
            os.replace(temporary_root, campaign_root)
        except Exception:
            shutil.rmtree(temporary_root, ignore_errors=True)
            raise
        diff_lines = list(difflib.unified_diff([], card.splitlines(True), fromfile="/dev/null", tofile=str(card_path.relative_to(CANONICAL_SOURCE_ROOT))))
        index_diff_lines = list(difflib.unified_diff([], index.splitlines(True), fromfile="/dev/null", tofile=str(index_path.relative_to(CANONICAL_SOURCE_ROOT))))
        return {
            "schema": "nexus.task_card_create.v1",
            "status": "CREATED_PENDING_COMMIT",
            "campaign_id": campaign,
            "task_id": task_id,
            "index_path": str(index_path.relative_to(CANONICAL_SOURCE_ROOT)),
            "card_path": str(card_path.relative_to(CANONICAL_SOURCE_ROOT)),
            "card_hash": card_sha256,
            "git_blob_sha": card_hash,
            "exact_card_diff": "".join(diff_lines),
            "exact_index_diff": "".join(index_diff_lines),
            "successor_execution": "NOT_STARTED",
            "owner_confirmation": True,
        }

    def _model_probe_submit(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        provider = str(arguments.get("provider") or "cline").strip().lower()
        metadata, executable = self._provider_executable(provider)
        if not metadata:
            raise GatewayInputError("ASSIST_PROVIDER_NOT_REGISTERED")
        if not executable:
            raise GatewayInputError("ASSIST_PROVIDER_UNAVAILABLE")
        model = str(arguments.get("model") or metadata.get("default_model") or "").strip()
        prompt = _text(arguments.get("prompt"), "prompt", max_length=16000)
        schema = arguments.get("output_schema") or {"type": "object"}
        if not isinstance(schema, Mapping) or len(json.dumps(schema, ensure_ascii=False)) > 16000:
            raise GatewayInputError("output_schema must be a bounded object")
        workspace_mode = str(arguments.get("workspace_mode") or "isolated").strip().lower()
        if workspace_mode != "isolated":
            raise GatewayInputError("MODEL_PROBE_REQUIRES_ISOLATED_WORKSPACE")
        task_id = self._task_id(arguments, prompt, provider, ["model_probe"])
        existing = self._assist_read(task_id)
        if existing is not None:
            return self._assist_response(self._assist_refresh(task_id) or existing, operation="submit")
        action = build_action_envelope(
            task_id=task_id,
            action_type=LifecycleActionType.TASK_RUN,
            request={"task_id": task_id, "provider": provider, "model": model, "prompt": prompt, "output_schema": schema, "context_arm": arguments.get("context_arm")},
            tool_manifest_hash=TOOL_MANIFEST_REVISION,
            expected_head=_git("rev-parse", "HEAD").strip(),
            allowed_paths=[],
            mutation=False,
            permission_profile=PermissionProfile.VERIFY,
        ).model_dump(mode="json")
        job_id = f"probe-{uuid4().hex}"
        root = self._assist_root()
        stdout_path = root / f"{job_id}.stdout"
        stderr_path = root / f"{job_id}.stderr"
        workspace_root = Path(tempfile.mkdtemp(prefix=f"nexus-probe-{task_id}-", dir="/tmp"))
        probe_prompt = f"{prompt}\nReturn JSON matching this schema exactly: {json.dumps(schema, ensure_ascii=False)}"
        command = self._assist_command(executable=executable, provider=provider, model=model, prompt=probe_prompt)
        job: dict[str, Any] = {
            "schema": "nexus.assisted_provider_job.v1",
            "job_kind": "model_probe",
            "task_id": task_id,
            "job_id": job_id,
            "attempt_history": [],
            "action_id": action["action_id"],
            "attempt_id": action["attempt_id"],
            "status": "SUBMITTED",
            "execution_lane": "ASSISTED_CANONICAL",
            "candidate_only": True,
            "apply_requested": False,
            "provider": provider,
            "model": model,
            "context_arm": arguments.get("context_arm"),
            "context_arm_applied": False,
            "context_arm_semantics": "record_only_not_applied",
            "requested_tools_policy": list(arguments.get("tools_allowed") or []),
            "tool_policy_enforcement": "cline_plan_auto_approve_false_allowlist_not_enforced",
            "workspace_mode": workspace_mode,
            "workspace_root": str(workspace_root),
            "filesystem_before": self._snapshot_workspace(workspace_root),
            "output_schema": dict(schema),
            "command_hash": hashlib.sha256(json.dumps(command, separators=(",", ":")).encode("utf-8")).hexdigest(),
            "command": command,
            "submitted_at": self._utc_now(),
            "started_at": None,
            "finished_at": None,
            "provider_time_ms": 0,
            "stdout_artifact": str(stdout_path),
            "stderr_artifact": str(stderr_path),
            "result_artifact": str(self._assist_path(task_id)),
            "action": action,
            "connector_disconnected_at": None,
            "reconnected_at": None,
        }
        self._assist_write(job)
        stdout_handle = stdout_path.open("w", encoding="utf-8")
        stderr_handle = stderr_path.open("w", encoding="utf-8")
        try:
            process = subprocess.Popen(command, cwd=workspace_root, stdout=stdout_handle, stderr=stderr_handle, text=True, start_new_session=True)
        except Exception:
            stdout_handle.close()
            stderr_handle.close()
            shutil.rmtree(workspace_root, ignore_errors=True)
            job.update({"status": "FAILED", "finished_at": self._utc_now(), "blocker": "ASSIST_PROVIDER_FAILED", "provider_error": "provider process could not start"})
            return self._assist_response(self._assist_write(job), operation="submit")
        stdout_handle.close()
        stderr_handle.close()
        job.update({"status": "RUNNING", "pid": process.pid, "pgid": process.pid, "started_at": self._utc_now()})
        with self._assist_lock:
            self._assist_processes[task_id] = process
        return self._assist_response(self._assist_write(job), operation="submit")

    def _resolve_assisted_worker(self, requested: str, requested_model: str) -> tuple[str, str, str | None]:
        """Resolve provider, exact model, and policy worker ID from one request."""
        key = str(requested or "auto").strip().lower() or "auto"
        model = str(requested_model or "").strip()
        if key == "auto":
            provider = os.environ.get("NEXUS_ASSIST_PROVIDER", "agy").strip().lower() or "agy"
            return provider, model, None
        snapshot = self._workforce_loader.load()
        worker = snapshot.workers.get(key)
        if worker is None:
            matches = [item for item in snapshot.workers.values() if item.model == key]
            if len(matches) == 1:
                worker = matches[0]
            elif key not in ONLINE_CLI_SPEC_REGISTRY and key not in {"mimo", "ollama"}:
                raise GatewayInputError("ASSIST_PROVIDER_NOT_REGISTERED")
        if worker is not None:
            if worker.state in NON_ADMISSIBLE_STATES:
                raise GatewayInputError(f"ASSIST_MODEL_NOT_ADMISSIBLE:{worker.worker_id}")
            if model and model != worker.model:
                raise GatewayInputError("ASSIST_MODEL_IDENTITY_MISMATCH")
            return worker.provider, worker.model, worker.worker_id
        return key, model, None

    @staticmethod
    def tool_specs() -> list[dict[str, Any]]:
        return [
            {
                "name": "nexus_gateway_status",
                "description": "Read the single gateway identity, manifest, route stages, and lifecycle counts.",
                "inputSchema": {"type": "object", "properties": {}},
            },
            {
                "name": "nexus_workspace_snapshot",
                "description": "Read the canonical checkout snapshot without creating state or a Target.",
                "inputSchema": {"type": "object", "properties": {}},
            },
            {
                "name": "nexus_read",
                "description": "Read a bounded UTF-8 file inside the canonical checkout.",
                "inputSchema": {
                    "type": "object",
                    "required": ["path"],
                    "properties": {
                        "path": {"type": "string"},
                        "start_line": {"type": "integer", "minimum": 1, "default": 1},
                        "max_lines": {"type": "integer", "minimum": 1, "maximum": 1000, "default": 200},
                    },
                },
            },
            {
                "name": "nexus_search",
                "description": "Search bounded literal text inside one canonical relative path.",
                "inputSchema": {
                    "type": "object",
                    "required": ["pattern"],
                    "properties": {
                        "pattern": {"type": "string", "maxLength": 200},
                        "path": {"type": "string", "default": "."},
                    },
                },
            },
            {
                "name": "nexus_git_diff",
                "description": "Read a bounded canonical diff; no arbitrary Git flags are accepted.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "base_revision": {"type": "string", "pattern": "^[0-9a-f]{40}$"},
                        "staged": {"type": "boolean", "default": False},
                    },
                },
            },
            {
                "name": "nexus_task_run",
                "description": "Route one bounded task through CapabilityPlanner and the governed lifecycle.",
                "inputSchema": {
                    "type": "object",
                    "required": ["what", "why", "allowed_files"],
                    "properties": {
                        "task_id": {"type": "string"},
                        "what": {"type": "string"},
                        "why": {"type": "string"},
                        "allowed_files": {"type": "array", "items": {"type": "string"}, "maxItems": 4},
                        "verifier_commands": {"type": "array", "items": {"type": "string"}},
                        "execution_preference": {"type": "string", "enum": ["auto", "DIRECT_CANONICAL", "ASSISTED_CANONICAL", "ISOLATED_TARGET"], "default": "auto"},
                        "preferred_worker": {"type": "string", "default": "auto"},
                        "preferred_model": {"type": "string", "default": ""},
                        "task_card_path": {"type": "string"},
                        "task_card_hash": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                        "owner_confirmation": {"type": "boolean", "description": "Explicit Owner authorization for a bounded inline contract."},
                        "owner_inline_expires_at": {"type": "string", "format": "date-time"},
                        "worker_may_commit": {"type": "boolean", "default": False},
                        "idempotency_key": {"type": "string", "maxLength": 256},
                        "apply": {"type": "boolean", "default": False},
                    },
                },
            },
            {
                "name": "nexus_task_status",
                "description": "Read one durable task's status and next action.",
                "inputSchema": {"type": "object", "required": ["task_id"], "properties": {"task_id": {"type": "string"}}},
            },
            {
                "name": "nexus_task_wait",
                "description": "Poll one bounded lifecycle task until attention, terminal, or timeout.",
                "inputSchema": {
                    "type": "object",
                    "required": ["task_id"],
                    "properties": {
                        "task_id": {"type": "string"},
                        "timeout_seconds": {"type": "number", "minimum": 0, "maximum": 60, "default": 10},
                        "poll_interval_seconds": {"type": "number", "exclusiveMinimum": 0, "maximum": 5, "default": 0.25},
                    },
                },
            },
            {
                "name": "nexus_task_finish",
                "description": "Finish a Direct receipt or owner-finish an exact isolated Candidate binding.",
                "inputSchema": {
                    "type": "object",
                    "required": ["execution_lane"],
                    "properties": {
                        "execution_lane": {"type": "string", "enum": ["DIRECT_CANONICAL", "ISOLATED_TARGET"]},
                        "request": {"type": "object"},
                        "base_sha": {"type": "string", "pattern": "^[0-9a-f]{40}$"},
                        "controller_revision": {"type": "string", "pattern": "^[0-9a-f]{40}$"},
                        "allowed_files": {"type": "array", "items": {"type": "string"}, "maxItems": 4},
                        "verifier_commands": {"type": "array", "items": {"type": "string"}},
                        "expected_commit_sha": {"type": "string", "pattern": "^[0-9a-f]{40}$"},
                        "task_id": {"type": "string"},
                        "candidate_commit_sha": {"type": "string", "pattern": "^[0-9a-f]{40}$"},
                        "candidate_tree_sha": {"type": "string", "pattern": "^[0-9a-f]{40}$"},
                        "candidate_state_hash": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                        "verified_receipt_hash": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                    },
                },
            },
            {
                "name": "nexus_task_cancel",
                "description": "Cancel one non-running lifecycle task through formal cleanup authority.",
                "inputSchema": {"type": "object", "required": ["task_id"], "properties": {"task_id": {"type": "string"}}},
            },
            {
                "name": "nexus_task_list_actionable",
                "description": "List durable tasks that require exactly one recovery or owner action.",
                "inputSchema": {"type": "object", "properties": {"include_details": {"type": "boolean", "default": False}}},
            },
            {
                "name": "nexus_task_reconcile",
                "description": "Reconcile one uncertain task from durable evidence without replaying a mutation.",
                "inputSchema": {"type": "object", "required": ["task_id"], "properties": {"task_id": {"type": "string"}}},
            },
            {
                "name": "nexus_task_retry",
                "description": "Retry one terminal task with the same task_id and a new attempt_id after cleanup.",
                "inputSchema": {"type": "object", "required": ["task_id"], "properties": {"task_id": {"type": "string"}}},
            },
            {
                "name": "nexus_task_resume",
                "description": "Resume one durable task only from its recorded execution evidence.",
                "inputSchema": {"type": "object", "required": ["task_id"], "properties": {"task_id": {"type": "string"}}},
            },
            {
                "name": "nexus_assist_submit",
                "description": "Submit a durable Assisted Cline provider job and return immediately.",
                "inputSchema": {
                    "type": "object",
                    "required": ["what", "why", "allowed_files"],
                    "properties": {
                        "task_id": {"type": "string"},
                        "what": {"type": "string"},
                        "why": {"type": "string"},
                        "allowed_files": {"type": "array", "items": {"type": "string"}, "maxItems": 4},
                        "verifier_commands": {"type": "array", "items": {"type": "string"}},
                        "provider": {"type": "string", "enum": ["cline"], "default": "cline"},
                        "model": {"type": "string", "default": "glm-5.2"},
                        "apply": {"type": "boolean", "default": False},
                    },
                },
            },
            {
                "name": "nexus_assist_result",
                "description": "Read the durable Assisted provider result for one task after disconnect or timeout.",
                "inputSchema": {"type": "object", "required": ["task_id"], "properties": {"task_id": {"type": "string"}}},
            },
            {
                "name": "nexus_assist_cancel",
                "description": "Cancel one running Assisted provider job without applying a candidate.",
                "inputSchema": {"type": "object", "required": ["task_id"], "properties": {"task_id": {"type": "string"}}},
            },
            {
                "name": "nexus_provider_preflight",
                "description": "Verify a registered provider binary, version, identity, and optional exact-model probe.",
                "inputSchema": {
                    "type": "object",
                    "required": ["provider"],
                    "properties": {
                        "provider": {"type": "string"},
                        "model": {"type": "string"},
                        "probe": {"type": "boolean", "default": False},
                        "timeout_seconds": {"type": "number", "minimum": 1, "maximum": 60, "default": 30},
                    },
                },
            },
            {
                "name": "nexus_task_card_create",
                "description": "Create exactly one new governed campaign INDEX and Task Card after explicit owner confirmation.",
                "inputSchema": {
                    "type": "object",
                    "required": ["owner_confirmation", "campaign_id", "task_id", "objective", "allowed_files", "verifier_commands"],
                    "properties": {
                        "owner_confirmation": {"type": "boolean"},
                        "campaign_id": {"type": "string"},
                        "task_id": {"type": "string"},
                        "objective": {"type": "string"},
                        "allowed_files": {"type": "array", "items": {"type": "string"}, "maxItems": 10},
                        "verifier_commands": {"type": "array", "items": {"type": "string"}, "minItems": 1},
                    },
                },
            },
            {
                "name": "nexus_model_probe",
                "description": "Run one schema-bound model probe in an isolated workspace and return a durable job.",
                "inputSchema": {
                    "type": "object",
                    "required": ["provider", "model", "prompt", "output_schema"],
                    "properties": {
                        "task_id": {"type": "string"},
                        "provider": {"type": "string"},
                        "model": {"type": "string"},
                        "prompt": {"type": "string", "maxLength": 16000},
                        "output_schema": {"type": "object"},
                        "tools_allowed": {"type": "array", "items": {"type": "string"}, "maxItems": 16, "description": "Requested policy only; provider-specific enforcement is not claimed."},
                        "workspace_mode": {"type": "string", "enum": ["isolated"], "default": "isolated"},
                        "context_arm": {"type": "string", "enum": ["bare", "nexus_bounded", "nexus_full"], "description": "Recorded for future calibration only; not applied to the probe prompt in this version."},
                    },
                },
            },
            {
                "name": "nexus_model_probe_result",
                "description": "Retrieve one durable schema-bound model probe result and filesystem/process receipt.",
                "inputSchema": {"type": "object", "required": ["task_id"], "properties": {"task_id": {"type": "string"}}},
            },
            {
                "name": "nexus_candidate_approve",
                "description": "Approve an exact Candidate binding; approval does not integrate or push.",
                "inputSchema": {
                    "type": "object",
                    "required": ["task_id", "candidate_commit_sha", "candidate_tree_sha", "candidate_state_hash", "verified_receipt_hash", "approval"],
                    "properties": {
                        "task_id": {"type": "string"},
                        "candidate_commit_sha": {"type": "string", "pattern": "^[0-9a-f]{40}$"},
                        "candidate_tree_sha": {"type": "string", "pattern": "^[0-9a-f]{40}$"},
                        "candidate_state_hash": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                        "verified_receipt_hash": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                        "approval": {
                            "type": "object",
                            "description": "Versioned, expiring approval bound to the persisted task attempt and runtime identity.",
                            "required": [
                                "schema", "approval_id", "approved_by", "issued_at", "expires_at",
                                "bound_task_id", "bound_attempt_id", "bound_action_type", "contract_kind", "contract_hash", "task_card_hash",
                                "tool_manifest_hash", "full_tool_schema_hash", "permission_policy_hash",
                                "lifecycle_revision", "server_instance_id",
                            ],
                            "properties": {
                                "schema": {"type": "string", "const": "nexus.approval.v2"},
                                "approval_id": {"type": "string"},
                                "approved_by": {"type": "string"},
                                "issued_at": {"type": "string", "format": "date-time"},
                                "expires_at": {"type": "string", "format": "date-time"},
                                "bound_task_id": {"type": "string"},
                                "bound_attempt_id": {"type": "string"},
                                "bound_action_type": {"type": "string", "const": "CANDIDATE_APPROVE"},
                                "approval_scope": {"type": "string", "const": "ALLOW_ACTION_ONCE", "default": "ALLOW_ACTION_ONCE"},
                                "contract_kind": {"type": "string", "enum": ["TRACKED_TASK_CARD", "OWNER_INLINE"]},
                                "contract_hash": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                                "task_card_hash": {"type": ["string", "null"], "pattern": "^[0-9a-f]{64}$"},
                                "tool_manifest_hash": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                                "full_tool_schema_hash": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                                "permission_policy_hash": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                                "lifecycle_revision": {"type": "string"},
                                "server_instance_id": {"type": "string"},
                                "consumed_at": {"type": ["string", "null"], "format": "date-time"},
                            },
                            "additionalProperties": False,
                        },
                    },
                },
            },
            {
                "name": "nexus_candidate_integrate",
                "description": "Integrate an already approved exact Candidate binding without pushing.",
                "inputSchema": {"type": "object", "required": ["task_id"], "properties": {"task_id": {"type": "string"}, "integration_branch": {"type": "string", "default": "nexus/integration/main"}}},
            },
            {
                "name": "nexus_candidate_dispose",
                "description": "Dispose a pending Candidate as REJECTED or SUPERSEDED through cleanup authority.",
                "inputSchema": {"type": "object", "required": ["task_id", "disposition"], "properties": {"task_id": {"type": "string"}, "disposition": {"type": "string", "enum": ["REJECTED", "SUPERSEDED"]}, "superseded_by": {"type": "string"}}},
            },
        ]

    @staticmethod
    def _success(request_id: Any, payload: Mapping[str, Any]) -> dict[str, Any]:
        text = json.dumps(payload, sort_keys=True, ensure_ascii=False)
        return {"jsonrpc": "2.0", "id": request_id, "result": {"content": [{"type": "text", "text": text}], "structuredContent": dict(payload), "isError": False}}

    @staticmethod
    def _error(request_id: Any, error: Exception | str) -> dict[str, Any]:
        payload = error.as_dict() if isinstance(error, LifecycleGuardError) else {"schema": "nexus.mcp_gateway_error.v1", "error": str(error)}
        return {"jsonrpc": "2.0", "id": request_id, "result": {"content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False)}], "structuredContent": payload, "isError": True}}

    def _gateway_status(self) -> dict[str, Any]:
        lifecycle = self.service.lifecycle_status()
        current_head = _git("rev-parse", "HEAD").strip()
        formal_actionable = self.service.list_actionable_tasks()
        pending_actions = int(formal_actionable.get("actionable_count", 0) or 0)
        for job_path in self._assist_root().glob("*.json"):
            try:
                job = json.loads(job_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if isinstance(job, Mapping) and job.get("status") not in {"COMPLETED", "FAILED", "CANCELLED"}:
                pending_actions += 1
        return {
            "schema": "nexus.mcp_gateway_status.v1",
            "public_app_name": PUBLIC_APP_NAME,
            "namespace_policy": "stable_public_name_with_manifest_revision",
            "server": GATEWAY_NAME,
            "version": GATEWAY_VERSION,
            "tool_manifest_revision": TOOL_MANIFEST_REVISION,
            "full_tool_schema_hash": FULL_TOOL_SCHEMA_HASH,
            "permission_policy_hash": PERMISSION_POLICY_HASH,
            "permission_policy_revision": PERMISSION_POLICY_REVISION,
            "task_contract_revision": TASK_CONTRACT_REVISION,
            "lifecycle_revision": LIFECYCLE_REVISION,
            "lifecycle_state_schema_revision": LIFECYCLE_STATE_SCHEMA_REVISION,
            "server_instance_id": SERVER_INSTANCE_ID,
            "server_started_at": SERVER_STARTED_AT,
            "repo_head_at_start": SERVER_REPO_HEAD_AT_START,
            "repo_head_current": current_head,
            "reload_required": bool(SERVER_REPO_HEAD_AT_START not in {"", "unknown"} and current_head != SERVER_REPO_HEAD_AT_START),
            "session_tracking": "unsupported",
            "active_sessions": None,
            "pending_actions": pending_actions,
            "tool_count": len(PUBLIC_TOOL_NAMES),
            "route_authority": "CapabilityPlanner",
            "execution_lanes": ["DIRECT_CANONICAL", "ASSISTED_CANONICAL", "ISOLATED_TARGET"],
            "canonical_repo_root": str(CANONICAL_SOURCE_ROOT),
            "lifecycle": lifecycle,
        }

    @staticmethod
    def _recovery_payload(state: Mapping[str, Any], *, operation: str = "status", include_state: bool = False) -> dict[str, Any]:
        """Normalize every recovery response to one actionable contract."""
        action = state.get("task_action") if isinstance(state.get("task_action"), Mapping) else {}
        action = dict(action)
        task_id = str(state.get("task_id") or action.get("task_id") or "")
        status = str(state.get("status") or action.get("task_status") or "UNKNOWN")
        terminal = status in {"CANCELLED", "INTEGRATED", "REJECTED", "SUPERSEDED", "FINAL_BLOCK"} and not bool(state.get("reconciliation_required"))
        next_action = str(action.get("next_action") or ("none" if terminal else "nexus_task_reconcile"))
        candidate = state.get("promotion_packet") if isinstance(state.get("promotion_packet"), Mapping) else {}
        if not candidate and isinstance(action.get("candidate"), Mapping):
            candidate = action.get("candidate") or {}
        cleanup = state.get("cleanup_status") if isinstance(state.get("cleanup_status"), Mapping) else {}
        cleanup = dict(cleanup)
        if not cleanup:
            cleanup = {
                "state_retention_status": state.get("state_retention_status"),
                "cleanup_eligible": state.get("cleanup_eligible"),
                "cleanup_performed": state.get("cleanup_performed"),
                "cleanup_decision": state.get("cleanup_decision"),
                "cleanup_blocker": state.get("cleanup_blocker"),
            }
        action_id = state.get("action_id")
        if not action_id and isinstance(state.get("action"), Mapping):
            action_id = state["action"].get("action_id")
        if not action_id and isinstance(state.get("request"), Mapping) and isinstance(state["request"].get("action"), Mapping):
            action_id = state["request"]["action"].get("action_id")
        recommended = action.get("recommended_tool") or next_action
        if recommended not in PUBLIC_TOOL_NAMES:
            if status in {"DIRECT_RECONCILE_REQUIRED", "UNKNOWN_REQUIRES_RECONCILE"} or state.get("reconciliation_required"):
                recommended = "nexus_task_reconcile"
            elif status in {"FINAL_BLOCK", "RETAINED_FOR_REVIEW", "INTEGRATION_FAILED"}:
                recommended = "nexus_task_status"
            else:
                recommended = "nexus_task_wait"
        result: dict[str, Any] = {
            "schema": "nexus.lifecycle_recovery.v1",
            "operation": operation,
            "task_id": task_id,
            "attempt_id": state.get("attempt_id") or action.get("attempt_id"),
            "last_action_id": action_id,
            "status": status,
            "attention_required": bool(action.get("attention_required", not terminal)),
            "next_action": next_action,
            "recommended_tool": recommended,
            "candidate_binding": {
                "candidate_commit_sha": state.get("candidate_commit_sha") or candidate.get("candidate_commit_sha"),
                "candidate_tree_sha": state.get("candidate_tree_sha") or candidate.get("candidate_tree_sha"),
                "candidate_state_hash": state.get("candidate_state_hash") or candidate.get("candidate_state_hash"),
                "verified_receipt_hash": state.get("verified_receipt_hash") or candidate.get("verified_receipt_hash"),
                "candidate_ref": state.get("candidate_ref"),
            },
            "cleanup_status": cleanup,
            "uncertain_mutation": status in {"DIRECT_RECONCILE_REQUIRED", "UNKNOWN_REQUIRES_RECONCILE"} or bool(state.get("reconciliation_required")),
        }
        if include_state:
            result["state"] = dict(state)
        return result

    def _task_list_actionable(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        include_details = bool(arguments.get("include_details", False))
        raw = self.service.list_actionable_tasks(include_details=include_details)
        tasks = [self._recovery_payload(item, operation="list", include_state=include_details) for item in raw.get("tasks", []) if isinstance(item, Mapping)]
        for path in sorted(self._assist_root().glob("*.json")):
            try:
                job = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(job, Mapping) or job.get("status") not in {"FAILED", "CANCELLED", "UNKNOWN_REQUIRES_RECONCILE"}:
                continue
            tasks.append(self._assist_response(self._assist_refresh(str(job.get("task_id"))) or job, operation="list"))
        return {
            "schema": "nexus.task_actionable_list.v1",
            "actionable_count": len(tasks),
            "details_included": include_details,
            "tasks": tasks,
        }

    def _task_reconcile(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        task_id = _text(arguments.get("task_id"), "task_id")
        assisted = self._assist_read(task_id)
        if assisted is not None:
            current = self._assist_refresh(task_id) or assisted
            if current.get("status") == "UNKNOWN_REQUIRES_RECONCILE":
                # No durable exit marker means the provider outcome is not
                # recoverable from output alone.  Reconciliation deliberately
                # converges to a retryable process-loss failure and performs
                # isolated-workspace cleanup; it never upgrades to success.
                current.update({
                    "status": "FAILED",
                    "blocker": "ASSIST_PROVIDER_PROCESS_LOST",
                    "reconciliation_required": False,
                    "reconciled_from": "UNKNOWN_REQUIRES_RECONCILE",
                    "reconciled_at": self._utc_now(),
                    "finished_at": current.get("finished_at") or self._utc_now(),
                })
                self._cleanup_assist_workspace(current)
                current = self._assist_write(current)
            return self._assist_response(current, operation="reconcile")
        result = self.service.reconcile_task(task_id)
        if result is None:
            raise KeyError(f"unknown task_id: {task_id}")
        return self._recovery_payload(result, operation="reconcile", include_state=True)

    def _task_retry(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        task_id = _text(arguments.get("task_id"), "task_id")
        assisted = self._assist_read(task_id)
        if assisted is not None:
            return self._assist_retry(task_id)
        return self._recovery_payload(self.service.retry_task(task_id), operation="retry", include_state=True)

    def _task_resume(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        task_id = _text(arguments.get("task_id"), "task_id")
        assisted = self._assist_read(task_id)
        if assisted is not None:
            return self._assist_wait(task_id, timeout_seconds=0.0)
        result = self.service.resume_task(task_id)
        if result is None:
            raise KeyError(f"unknown task_id: {task_id}")
        return self._recovery_payload(result, operation="resume", include_state=True)

    @staticmethod
    def _exact_hash(value: Any, field: str, length: int) -> str:
        text = _text(value, field)
        pattern = rf"^[0-9a-f]{{{length}}}$"
        if not re.fullmatch(pattern, text):
            raise GatewayInputError(f"{field} must be an exact lowercase Git hash")
        return text

    def _candidate_approve(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        task_id = _text(arguments.get("task_id"), "task_id")
        candidate_commit_sha = self._exact_hash(arguments.get("candidate_commit_sha"), "candidate_commit_sha", 40)
        candidate_tree_sha = self._exact_hash(arguments.get("candidate_tree_sha"), "candidate_tree_sha", 40)
        candidate_state_hash = self._exact_hash(arguments.get("candidate_state_hash"), "candidate_state_hash", 64)
        verified_receipt_hash = self._exact_hash(arguments.get("verified_receipt_hash"), "verified_receipt_hash", 64)
        state = self.service.get_task_snapshot(task_id, include_details=True)
        if not isinstance(state, Mapping):
            raise GatewayInputError("CANDIDATE_TASK_STATE_REQUIRED")
        base = str(state.get("controller_revision") or "").strip()
        if not re.fullmatch(r"[0-9a-f]{40}", base):
            raise GatewayInputError("CANDIDATE_CONTROLLER_REVISION_REQUIRED")
        packet = state.get("promotion_packet") if isinstance(state.get("promotion_packet"), Mapping) else {}
        task_card_hash = str(state.get("task_card_hash")).strip() if state.get("task_card_hash") else None
        contract_kind = str(state.get("contract_kind") or ContractKind.TRACKED_TASK_CARD.value)
        contract_hash = str(state.get("contract_hash") or "").strip() or (task_card_hash or None)
        owner_inline_contract = state.get("owner_inline_contract") if isinstance(state.get("owner_inline_contract"), Mapping) else None
        if contract_kind == ContractKind.TRACKED_TASK_CARD.value and not re.fullmatch(r"[0-9a-f]{64}", task_card_hash):
            raise GatewayInputError("CANDIDATE_TASK_CARD_HASH_REQUIRED")
        if contract_kind == ContractKind.OWNER_INLINE.value and not contract_hash:
            raise GatewayInputError("CANDIDATE_OWNER_INLINE_CONTRACT_REQUIRED")
        approval_receipt = validate_approval_grant(
            arguments.get("approval"),
            task_id=task_id,
            attempt_id=str(state.get("attempt_id") or ""),
            action_type=LifecycleActionType.CANDIDATE_APPROVE.value,
            task_card_hash=task_card_hash,
            contract_kind=contract_kind,
            contract_hash=contract_hash,
            owner_inline_contract=owner_inline_contract,
            tool_manifest_hash=TOOL_MANIFEST_REVISION,
            full_tool_schema_hash=FULL_TOOL_SCHEMA_HASH,
            permission_policy_hash=PERMISSION_POLICY_HASH,
            lifecycle_revision=LIFECYCLE_REVISION,
            server_instance_id=SERVER_INSTANCE_ID,
        )
        action_request = {**dict(arguments), "source_attempt_id": state.get("attempt_id"), "candidate_binding": {
            "candidate_commit_sha": packet.get("candidate_commit_sha") or state.get("candidate_commit_sha"),
            "candidate_tree_sha": packet.get("candidate_tree_sha") or state.get("candidate_tree_sha"),
            "candidate_state_hash": packet.get("candidate_state_hash") or state.get("candidate_state_hash"),
            "verified_receipt_hash": packet.get("verified_receipt_hash") or state.get("verified_receipt_hash"),
        }}
        action = build_action_envelope(
            task_id=task_id,
            action_type=LifecycleActionType.CANDIDATE_APPROVE,
            request=action_request,
            tool_manifest_hash=TOOL_MANIFEST_REVISION,
            expected_head=base,
            allowed_paths=[],
            mutation=True,
            permission_profile=PermissionProfile.CANDIDATE,
            mutation_domain=MutationDomain.LIFECYCLE_STATE,
        )
        guard_receipt = pre_action_guard(action, request={}, current_head=base, tool_manifest_hash=TOOL_MANIFEST_REVISION)
        result = self.service.approve_promotion(
            task_id,
            candidate_commit_sha=candidate_commit_sha,
            candidate_tree_sha=candidate_tree_sha,
            candidate_state_hash=candidate_state_hash,
            verified_receipt_hash=verified_receipt_hash,
            approval_context={**dict(arguments.get("approval") or {}), "validation_receipt": approval_receipt},
        )
        payload = self._recovery_payload(result, operation="candidate_approve", include_state=True)
        payload["guard_receipt"] = guard_receipt
        payload["approval_receipt"] = approval_receipt
        return payload

    def _candidate_integrate(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        task_id = _text(arguments.get("task_id"), "task_id")
        branch = str(arguments.get("integration_branch") or "nexus/integration/main").strip()
        if not branch or branch.startswith("-") or any(char in branch for char in "\n\r"):
            raise GatewayInputError("integration_branch is invalid")
        state = self.service.get_task_snapshot(task_id, include_details=True)
        if not isinstance(state, Mapping):
            raise GatewayInputError("CANDIDATE_TASK_STATE_REQUIRED")
        base = str(state.get("controller_revision") or "").strip()
        if not re.fullmatch(r"[0-9a-f]{40}", base):
            raise GatewayInputError("CANDIDATE_CONTROLLER_REVISION_REQUIRED")
        contract = state.get("contract") if isinstance(state.get("contract"), Mapping) else {}
        allowed_files = [str(path) for path in contract.get("allowed_files") or [] if str(path).strip()]
        if not allowed_files:
            raise GatewayInputError("CANDIDATE_ALLOWED_PATHS_REQUIRED")
        packet = state.get("promotion_packet") if isinstance(state.get("promotion_packet"), Mapping) else {}
        task_card_hash = str(state.get("task_card_hash")).strip() if state.get("task_card_hash") else None
        contract_kind = str(state.get("contract_kind") or ContractKind.TRACKED_TASK_CARD.value)
        contract_hash = str(state.get("contract_hash") or "").strip() or (task_card_hash or None)
        owner_inline_contract = state.get("owner_inline_contract") if isinstance(state.get("owner_inline_contract"), Mapping) else None
        binding = state.get("approved_binding") if isinstance(state.get("approved_binding"), Mapping) else {}
        approval_grant = binding.get("approval_grant") if isinstance(binding.get("approval_grant"), Mapping) else None
        if contract_kind == ContractKind.TRACKED_TASK_CARD.value and not re.fullmatch(r"[0-9a-f]{64}", task_card_hash):
            raise LifecycleGuardError("CANDIDATE_TASK_CARD_HASH_REQUIRED", "tracked candidate integration requires a task card hash")
        if contract_kind == ContractKind.OWNER_INLINE.value and not contract_hash:
            raise LifecycleGuardError("CANDIDATE_OWNER_INLINE_CONTRACT_REQUIRED", "Owner Inline integration requires a contract hash")
        if not approval_grant:
            raise LifecycleGuardError("APPROVAL_REVALIDATION_REQUIRED", "integration requires a persisted versioned approval binding")
        approval_receipt = validate_approval_grant(
            approval_grant,
            task_id=task_id,
            attempt_id=str(state.get("attempt_id") or ""),
            action_type=LifecycleActionType.CANDIDATE_APPROVE.value,
            task_card_hash=task_card_hash,
            contract_kind=contract_kind,
            contract_hash=contract_hash,
            owner_inline_contract=owner_inline_contract,
            tool_manifest_hash=TOOL_MANIFEST_REVISION,
            full_tool_schema_hash=FULL_TOOL_SCHEMA_HASH,
            permission_policy_hash=PERMISSION_POLICY_HASH,
            lifecycle_revision=LIFECYCLE_REVISION,
            server_instance_id=SERVER_INSTANCE_ID,
            allow_consumed=True,
        )
        action_request = {**dict(arguments), "allowed_files": allowed_files, "source_attempt_id": state.get("attempt_id"), "candidate_binding": {
            "candidate_commit_sha": packet.get("candidate_commit_sha") or state.get("candidate_commit_sha"),
            "candidate_tree_sha": packet.get("candidate_tree_sha") or state.get("candidate_tree_sha"),
            "candidate_state_hash": packet.get("candidate_state_hash") or state.get("candidate_state_hash"),
            "verified_receipt_hash": packet.get("verified_receipt_hash") or state.get("verified_receipt_hash"),
        }}
        action = build_action_envelope(
            task_id=task_id,
            action_type=LifecycleActionType.CANDIDATE_INTEGRATE,
            request=action_request,
            tool_manifest_hash=TOOL_MANIFEST_REVISION,
            expected_head=base,
            allowed_paths=allowed_files,
            mutation=True,
            permission_profile=PermissionProfile.INTEGRATE,
            mutation_domain=MutationDomain.INTEGRATION,
        )
        guard_receipt = pre_action_guard(action, request={"allowed_files": allowed_files}, current_head=base, tool_manifest_hash=TOOL_MANIFEST_REVISION)
        result = self.service.integrate_approved(
            task_id,
            integration_branch=branch,
            runtime_identity={
                "task_card_hash": task_card_hash,
                "contract_kind": contract_kind,
                "contract_hash": contract_hash,
                "tool_manifest_hash": TOOL_MANIFEST_REVISION,
                "full_tool_schema_hash": FULL_TOOL_SCHEMA_HASH,
                "permission_policy_hash": PERMISSION_POLICY_HASH,
                "lifecycle_revision": LIFECYCLE_REVISION,
                "server_instance_id": SERVER_INSTANCE_ID,
            },
        )
        payload = self._recovery_payload(result, operation="candidate_integrate", include_state=True)
        payload["guard_receipt"] = guard_receipt
        payload["approval_revalidation"] = approval_receipt
        return payload

    def _candidate_dispose(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        task_id = _text(arguments.get("task_id"), "task_id")
        disposition = str(arguments.get("disposition") or "").strip().upper()
        if disposition not in {"REJECTED", "SUPERSEDED"}:
            raise GatewayInputError("disposition must be REJECTED or SUPERSEDED")
        superseded_by = str(arguments.get("superseded_by") or "").strip() or None
        if disposition == "SUPERSEDED" and not superseded_by:
            raise GatewayInputError("superseded_by is required for SUPERSEDED")
        state = self.service.get_task_snapshot(task_id, include_details=True)
        if not isinstance(state, Mapping):
            raise GatewayInputError("CANDIDATE_TASK_STATE_REQUIRED")
        base = str(state.get("controller_revision") or "").strip()
        if not re.fullmatch(r"[0-9a-f]{40}", base):
            raise GatewayInputError("CANDIDATE_CONTROLLER_REVISION_REQUIRED")
        packet = state.get("promotion_packet") if isinstance(state.get("promotion_packet"), Mapping) else {}
        action_request = {**dict(arguments), "source_attempt_id": state.get("attempt_id"), "candidate_binding": {
            "candidate_commit_sha": packet.get("candidate_commit_sha") or state.get("candidate_commit_sha"),
            "candidate_tree_sha": packet.get("candidate_tree_sha") or state.get("candidate_tree_sha"),
            "candidate_state_hash": packet.get("candidate_state_hash") or state.get("candidate_state_hash"),
            "verified_receipt_hash": packet.get("verified_receipt_hash") or state.get("verified_receipt_hash"),
        }}
        action = build_action_envelope(
            task_id=task_id,
            action_type=LifecycleActionType.CANDIDATE_DISPOSE,
            request=action_request,
            tool_manifest_hash=TOOL_MANIFEST_REVISION,
            expected_head=base,
            allowed_paths=[],
            mutation=True,
            permission_profile=PermissionProfile.CANDIDATE,
            mutation_domain=MutationDomain.CANDIDATE_REF,
        )
        guard_receipt = pre_action_guard(action, request={}, current_head=base, tool_manifest_hash=TOOL_MANIFEST_REVISION)
        result = self.service.dispose_candidate(task_id, disposition=disposition, superseded_by=superseded_by)
        payload = self._recovery_payload(result, operation="candidate_dispose", include_state=True)
        payload["guard_receipt"] = guard_receipt
        return payload

    def _workspace_snapshot(self) -> dict[str, Any]:
        status = _git("status", "--porcelain=v1")
        branch = _git("branch", "--show-current").strip()
        head = _git("rev-parse", "HEAD").strip()
        worktree_lines = _git("worktree", "list", "--porcelain").splitlines()
        worktrees = [line.removeprefix("worktree ") for line in worktree_lines if line.startswith("worktree ")]
        actionable = self.service.list_actionable_tasks()
        return {
            "schema": "nexus.workspace_snapshot.v1",
            "root": str(CANONICAL_SOURCE_ROOT),
            "branch": branch,
            "head": head,
            "clean": not bool(status.strip()),
            "registered_worktrees": worktrees,
            "registered_worktree_count": len(worktrees),
            "actionable_count": int(actionable.get("actionable_count", 0)),
            "target_root": "/Users/jameschen/Workspace/nexus-runtime-targets",
        }

    def _read(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        path = _safe_relative_path(arguments.get("path"))
        if not path.is_file():
            raise GatewayInputError("path is not a regular file")
        if path.stat().st_size > MAX_READ_BYTES:
            raise GatewayInputError(f"path exceeds {MAX_READ_BYTES} bytes")
        start = max(1, int(arguments.get("start_line", 1)))
        limit = min(1000, max(1, int(arguments.get("max_lines", 200))))
        lines = path.read_text(encoding="utf-8").splitlines()
        selected = lines[start - 1 : start - 1 + limit]
        return {"schema": "nexus.workspace_read.v1", "path": str(path.relative_to(CANONICAL_SOURCE_ROOT)), "start_line": start, "lines": selected, "truncated": start - 1 + limit < len(lines)}

    def _search(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        pattern = _text(arguments.get("pattern"), "pattern", max_length=200)
        path = _safe_relative_path(arguments.get("path", "."), "path")
        relative = str(path.relative_to(CANONICAL_SOURCE_ROOT)) or "."
        result = subprocess.run(
            ["rg", "-n", "--fixed-strings", "--no-heading", "--color", "never", "--max-count", "200", pattern, relative],
            cwd=CANONICAL_SOURCE_ROOT, capture_output=True, text=True, timeout=3, check=False,
        )
        if result.returncode not in (0, 1):
            raise RuntimeError(result.stderr.strip() or "search failed")
        output = result.stdout.splitlines()[:MAX_SEARCH_RESULTS]
        return {"schema": "nexus.workspace_search.v1", "pattern": pattern, "path": relative, "matches": output, "truncated": len(result.stdout.splitlines()) > MAX_SEARCH_RESULTS}

    def _diff(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        base = arguments.get("base_revision")
        if base is not None and not _SHA_RE.fullmatch(str(base)):
            raise GatewayInputError("base_revision must be an exact lowercase Git SHA")
        args = ["diff", "--no-ext-diff", "--unified=3"]
        if bool(arguments.get("staged", False)):
            args.append("--cached")
        if base:
            args.append(str(base))
        output = _bounded_text(_git(*args), "git diff")
        return {"schema": "nexus.workspace_diff.v1", "base_revision": base, "staged": bool(arguments.get("staged", False)), "diff": output}

    @staticmethod
    def _task_id(arguments: Mapping[str, Any], what: str, why: str, allowed: list[str]) -> str:
        explicit = str(arguments.get("task_id") or "").strip()
        if explicit:
            if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}", explicit):
                raise GatewayInputError("task_id must be a stable bounded slug")
            return explicit
        seed = json.dumps([what, why, sorted(allowed)], ensure_ascii=False, separators=(",", ":"))
        return "dispatch-" + hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]

    def _plan_route(self, *, what: str, allowed: list[str], preference: str, worker: str) -> dict[str, Any]:
        top_level_paths = {path.split("/", 1)[0] for path in allowed}
        cross_module = len(allowed) > 1 and (
            len(top_level_paths) > 1 or any(path.startswith("nexus/") for path in allowed)
        )
        plan = CapabilityPlanner().plan(
            task_desc=what,
            task_type="code",
            route={
                "recommended_flow": "execute",
                "mutation_requested": True,
                "route_features": {"impact_complexity": 0.8 if cross_module else 0.1, "is_cross_module_task": cross_module},
            },
        )
        planner_snapshot = plan.signal_snapshot
        if preference != "auto":
            lane = preference
            reason = "caller_explicit_preference"
        elif worker not in {"", "auto", "primary", "codex"}:
            lane = "ISOLATED_TARGET"
            reason = "delegated_worker_requires_target"
        elif plan.execution_depth == "LIGHT":
            lane = "DIRECT_CANONICAL"
            reason = "CapabilityPlanner_light_execution_depth"
        else:
            lane = "ISOLATED_TARGET"
            reason = "CapabilityPlanner_non_light_execution_depth"
        return {
            "execution_lane": lane,
            "route_reason": reason,
            "route_authority": "CapabilityPlanner",
            "planner_execution_depth": plan.execution_depth,
            "planner_routing_tier": planner_snapshot.get("routing_tier"),
            "planner_decision_id": hashlib.sha256(json.dumps(planner_snapshot, sort_keys=True, default=str).encode("utf-8")).hexdigest()[:16],
        }

    @staticmethod
    def _dirty_paths() -> list[str]:
        """Return normalized paths from the canonical porcelain snapshot."""
        paths: list[str] = []
        for line in _git("status", "--porcelain=v1").splitlines():
            if len(line) < 4:
                continue
            raw = line[3:].strip()
            if " -> " in raw:
                raw = raw.rsplit(" -> ", 1)[-1]
            if raw.startswith('"') and raw.endswith('"'):
                raw = raw[1:-1]
            if raw:
                paths.append(raw)
        return sorted(set(paths))

    @staticmethod
    def _dirty_overlap(dirty_paths: list[str], requested_paths: list[str]) -> list[str]:
        overlap: list[str] = []
        for dirty in dirty_paths:
            for requested in requested_paths:
                if dirty == requested or dirty.startswith(requested.rstrip("/") + "/") or requested.startswith(dirty.rstrip("/") + "/"):
                    overlap.append(dirty)
                    break
        return sorted(set(overlap))

    @staticmethod
    def _owner_inline_contract(
        *, task_id: str, what: str, allowed: list[str], verifiers: list[str], expected_head: str, arguments: Mapping[str, Any]
    ) -> dict[str, Any]:
        issued_at = datetime.now(timezone.utc)
        expires_raw = str(arguments.get("owner_inline_expires_at") or "").strip()
        expires_at = expires_raw or (issued_at + timedelta(minutes=10)).isoformat()
        return build_owner_inline_contract(
            task_id=task_id,
            objective=what,
            allowed_files=allowed,
            verifier_commands=verifiers,
            expected_head=expected_head,
            issued_at=issued_at.isoformat(),
            expires_at=expires_at,
            permission_profile=PermissionProfile.MUTATE_BOUNDED,
            worker_may_commit=bool(arguments.get("worker_may_commit", False)),
        )

    def _resolve_contract_binding(
        self, *, task_id: str, what: str, allowed: list[str], verifiers: list[str], base: str, arguments: Mapping[str, Any], worker: str,
        defer_required_error: bool = False,
    ) -> dict[str, Any]:
        card_path = str(arguments.get("task_card_path") or "").strip() or None
        card_hash = str(arguments.get("task_card_hash") or "").strip() or None
        owner_confirmation = arguments.get("owner_confirmation") is True
        delegated = worker not in {"", "auto", "primary", "codex"}
        high_risk = any(bool(arguments.get(flag)) for flag in (
            "migration_authority", "schema_authority", "route_authority_mutation",
            "security_policy_weakening", "public_claim_allowed", "production_ready",
        ))
        top_level = {path.split("/", 1)[0] for path in allowed}
        cross_module = len(allowed) > 1 and (len(top_level) > 1 or any(path.startswith("nexus/") for path in allowed))
        if card_path or card_hash:
            if not card_path or not card_hash:
                raise GatewayInputError("TASK_CARD_BINDING_REQUIRED")
            kind = ContractKind.TRACKED_TASK_CARD
            if owner_confirmation:
                raise GatewayInputError("CONTRACT_BINDING_AMBIGUOUS")
        elif owner_confirmation:
            if delegated or high_risk or cross_module:
                raise GatewayInputError("TRACKED_TASK_CARD_REQUIRED")
            try:
                inline = self._owner_inline_contract(
                    task_id=task_id, what=what, allowed=allowed, verifiers=verifiers, expected_head=base, arguments=arguments,
                )
            except ValueError as exc:
                raise GatewayInputError(str(exc)) from exc
            return {
                "contract_kind": ContractKind.OWNER_INLINE.value,
                "contract_hash": inline["contract_hash"],
                "owner_inline_contract": inline,
                "task_card_path": None,
                "task_card_hash": None,
                "task_card_required": False,
            }
        else:
            kind = ContractKind.NONE
        if (delegated or high_risk or cross_module) and kind != ContractKind.TRACKED_TASK_CARD and not defer_required_error:
            raise GatewayInputError("TASK_CARD_BINDING_REQUIRED")
        return {
            "contract_kind": kind.value,
            "contract_hash": None,
            "owner_inline_contract": None,
            "task_card_path": card_path,
            "task_card_hash": card_hash,
            "task_card_required": kind == ContractKind.TRACKED_TASK_CARD,
        }

    def _task_run(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        dispatch_started = time.perf_counter()
        what = _text(arguments.get("what"), "what")
        why = _text(arguments.get("why"), "why")
        allowed = [str(path).strip() for path in (arguments.get("allowed_files") or []) if str(path).strip()]
        if not allowed or len(allowed) > 4:
            raise GatewayInputError("allowed_files must contain 1-4 bounded paths")
        for path in allowed:
            _safe_relative_path(path, "allowed_files")
        preference = str(arguments.get("execution_preference", "auto")).strip().upper()
        if preference == "AUTO":
            preference = "auto"
        if preference not in {"auto", "DIRECT_CANONICAL", "ASSISTED_CANONICAL", "ISOLATED_TARGET"}:
            raise GatewayInputError("execution_preference is unsupported")
        worker = str(arguments.get("preferred_worker", "auto")).strip().lower() or "auto"
        requested_model = str(arguments.get("preferred_model") or "").strip()
        resolved_provider, resolved_model, resolved_worker_id = self._resolve_assisted_worker(worker, requested_model)
        task_id = self._task_id(arguments, what, why, allowed)
        route_started = time.perf_counter()
        route_worker = worker if worker == "auto" else resolved_provider
        route = self._plan_route(what=what, allowed=allowed, preference=preference, worker=route_worker)
        route["requested_worker"] = worker
        route["resolved_provider"] = resolved_provider
        if resolved_model:
            route["resolved_model"] = resolved_model
        if resolved_worker_id:
            route["resolved_worker_id"] = resolved_worker_id
        route_decision_ms = max(0, int((time.perf_counter() - route_started) * 1000))
        base = _git("rev-parse", "HEAD").strip()
        apply_requested = bool(arguments.get("apply", False))
        verifiers = list(arguments.get("verifier_commands") or ["git diff --check"])
        binding = self._resolve_contract_binding(
            task_id=task_id, what=what, allowed=allowed, verifiers=verifiers, base=base, arguments=arguments, worker=worker,
            defer_required_error=preference in {"ASSISTED_CANONICAL", "ISOLATED_TARGET"},
        )
        dirty_paths = self._dirty_paths()
        overlapping_paths = self._dirty_overlap(dirty_paths, allowed)
        route["dirty_paths"] = dirty_paths
        route["requested_allowed_files"] = allowed
        route["dirty_overlap"] = bool(overlapping_paths)
        route["overlapping_paths"] = overlapping_paths
        if dirty_paths and not overlapping_paths and route["execution_lane"] == "DIRECT_CANONICAL" and binding["contract_kind"] == ContractKind.OWNER_INLINE.value:
            route["execution_lane"] = "ISOLATED_TARGET"
            route["route_reason"] = "dirty_non_overlapping_owner_inline"
        if dirty_paths and not overlapping_paths and route["execution_lane"] == "DIRECT_CANONICAL" and binding["contract_kind"] == ContractKind.NONE.value:
            return {
                "schema": "nexus.task_dispatch.v1",
                "task_id": task_id,
                "controller_revision": base,
                "execution_lane": "DIRECT_CANONICAL",
                "contract_kind": ContractKind.NONE.value,
                "contract_hash": None,
                "task_card_required": True,
                "dirty_paths": dirty_paths,
                "requested_allowed_files": allowed,
                "dirty_overlap": False,
                "overlapping_paths": [],
                "target_created": False,
                "status": "FINAL_BLOCK",
                "blocker": "CONTRACT_BINDING_REQUIRED",
                "next_action": "provide_owner_inline_contract_or_task_card",
                "route": route,
            }
        if overlapping_paths and route["execution_lane"] != "ASSISTED_CANONICAL":
            return {
                "schema": "nexus.task_dispatch.v1",
                "task_id": task_id,
                "what": what,
                "why": why,
                "controller_revision": base,
                "execution_lane": route["execution_lane"],
                "route_authority": "CapabilityPlanner",
                "contract_kind": binding["contract_kind"],
                "contract_hash": binding["contract_hash"],
                "task_card_required": binding["task_card_required"],
                "dirty_paths": dirty_paths,
                "requested_allowed_files": allowed,
                "dirty_overlap": True,
                "overlapping_paths": overlapping_paths,
                "target_created": False,
                "status": "FINAL_BLOCK",
                "blocker": "DIRTY_PATH_OVERLAP_REQUIRES_RECONCILIATION",
                "next_action": "reconcile_overlapping_work",
                "recommended_tool": "nexus_workspace_snapshot",
                "route": route,
            }
        assisted_candidate_only = route["execution_lane"] == "ASSISTED_CANONICAL" and not apply_requested
        action_request = {
            "task_id": task_id,
            "what": what,
            "why": why,
            "allowed_files": allowed,
            "verifier_commands": verifiers,
            "execution_preference": preference,
            "preferred_worker": worker,
            "preferred_model": requested_model,
            "task_card_path": binding["task_card_path"],
            "task_card_hash": binding["task_card_hash"],
            "contract_kind": binding["contract_kind"],
            "contract_hash": binding["contract_hash"],
            "owner_inline_contract": binding["owner_inline_contract"],
            "apply": apply_requested,
        }
        action = build_action_envelope(
            task_id=task_id,
            action_type=LifecycleActionType.TASK_RUN,
            request=action_request,
            tool_manifest_hash=TOOL_MANIFEST_REVISION,
            expected_head=base,
            allowed_paths=allowed,
            mutation=not assisted_candidate_only,
            task_card_path=binding["task_card_path"],
            task_card_hash=binding["task_card_hash"],
            contract_kind=ContractKind(binding["contract_kind"]),
            contract_hash=binding["contract_hash"],
            idempotency_key=arguments.get("idempotency_key"),
            permission_profile=PermissionProfile.VERIFY if assisted_candidate_only else PermissionProfile.MUTATE_BOUNDED,
            mutation_domain=MutationDomain.NONE if assisted_candidate_only else MutationDomain.REPOSITORY,
        )
        guard_receipt = pre_action_guard(
            action,
            request=action_request,
            canonical_root=CANONICAL_SOURCE_ROOT,
            current_head=base,
            tool_manifest_hash=TOOL_MANIFEST_REVISION,
        )
        envelope = {
            "schema": "nexus.task_dispatch.v1",
            "task_id": task_id,
            "what": what,
            "why": why,
            "controller_revision": base,
            "allowed_files": allowed,
            "contract_kind": binding["contract_kind"],
            "contract_hash": binding["contract_hash"],
            "task_card_required": binding["task_card_required"],
            "dirty_paths": dirty_paths,
            "dirty_overlap": bool(overlapping_paths),
            "overlapping_paths": overlapping_paths,
            "action": action.model_dump(mode="json"),
            "guard_receipt": guard_receipt,
            **route,
        }
        def telemetry(**values: int) -> dict[str, int]:
            defaults = {
                "control_plane_ms": 0,
                "route_decision_ms": route_decision_ms,
                "context_build_ms": 0,
                "provider_start_ms": 0,
                "provider_time_ms": 0,
                "patch_validation_ms": 0,
                "verifier_time_ms": 0,
                "commit_time_ms": 0,
                "worktree_time_ms": 0,
                "cleanup_time_ms": 0,
                "total_wall_time_ms": max(0, int((time.perf_counter() - dispatch_started) * 1000)),
            }
            defaults.update(values)
            defaults["total_wall_time_ms"] = max(0, int((time.perf_counter() - dispatch_started) * 1000))
            defaults["control_plane_ms"] = max(0, defaults["total_wall_time_ms"] - defaults["provider_time_ms"])
            return defaults
        if route["execution_lane"] == "ASSISTED_CANONICAL":
            if resolved_provider == "cline":
                if apply_requested:
                    return {**envelope, "status": "FINAL_BLOCK", "blocker": "ASSIST_APPLY_REQUIRES_EXPLICIT_FINISH", "provider": resolved_provider, "next_action": "nexus_assist_result", "telemetry": telemetry()}
                async_arguments = dict(arguments)
                async_arguments.update({
                    "task_id": task_id,
                    "provider": resolved_provider,
                    "model": resolved_model or "glm-5.2",
                    "what": what,
                    "why": why,
                    "allowed_files": allowed,
                    "verifier_commands": list(arguments.get("verifier_commands") or ["git diff --check"]),
                    "apply": False,
                })
                submitted = self._assist_submit(async_arguments, action=action.model_dump(mode="json"))
                return {**envelope, **submitted, "status": "ASSISTED_PROVIDER_SUBMITTED", "execution_lane": "ASSISTED_CANONICAL", "provider": resolved_provider, "model": resolved_model or "glm-5.2", "next_action": "nexus_assist_result", "recommended_tool": "nexus_assist_result", "telemetry": telemetry(provider_start_ms=0)}
            request = self._canonical_request(
                task_id,
                what,
                why,
                allowed,
                verifiers,
                base,
                action=action.model_dump(mode="json"),
                contract_binding=binding,
            )
            # Legacy synchronous non-Cline adapters still use the existing
            # service handoff; the Cline path above is the durable Assisted
            # provider surface and retains its lane identity.
            request.update({"execution_lane": "DIRECT_CANONICAL", "primary_agent": True, "worker": "primary", "provider": resolved_provider, "model": resolved_model, "candidate_only": not apply_requested, "apply_requested": apply_requested})
            try:
                handoff = self.service.submit_task(request)
            except Exception as exc:
                return {**envelope, "status": "FINAL_BLOCK", "blocker": "ASSIST_ACTION_STATE_FAILED", "error": str(exc), "telemetry": telemetry(), "next_action": "inspect_action_state"}
            handoff_action = handoff.get("task_action") if isinstance(handoff, Mapping) else None
            if isinstance(handoff_action, Mapping) and handoff_action.get("action_state") == "FINAL_BLOCK":
                return {**envelope, "status": "FINAL_BLOCK", "blocker": "DIRECT_RECONCILE_REQUIRED", "handoff": handoff, "telemetry": telemetry(), "next_action": "nexus_task_reconcile"}
            context_started = time.perf_counter()
            prompt = self._assist_prompt(what, why, allowed, list(arguments.get("verifier_commands") or ["git diff --check"]))
            context_build_ms = max(0, int((time.perf_counter() - context_started) * 1000))
            provider_start_ms = max(0, int((time.perf_counter() - dispatch_started) * 1000))
            started = time.perf_counter()
            try:
                proposal = self._model_runner(
                    prompt=prompt,
                    allowed_files=allowed,
                    provider=resolved_provider,
                    model=resolved_model,
                )
            except Exception as exc:
                recorder = getattr(self.service, "record_canonical_action_failure", None)
                if recorder:
                    recorder(task_id, "ASSIST_PROVIDER_FAILED", str(exc))
                return {**envelope, "status": "FINAL_BLOCK", "blocker": "ASSIST_PROVIDER_FAILED", "provider_error": str(exc), "handoff": self.service.get_task(task_id) if hasattr(self.service, "get_task") else handoff, "telemetry": telemetry(context_build_ms=context_build_ms, provider_start_ms=provider_start_ms), "next_action": "inspect_provider_or_retry_same_task"}
            provider_time_ms = max(0, int((time.perf_counter() - started) * 1000))
            if not proposal.get("patch"):
                recorder = getattr(self.service, "record_canonical_action_failure", None)
                if recorder:
                    recorder(task_id, str(proposal.get("blocker") or "EMPTY_ASSIST_PATCH"), str(proposal.get("error") or ""))
                return {**envelope, "status": "FINAL_BLOCK", "blocker": str(proposal.get("blocker") or "EMPTY_ASSIST_PATCH"), "provider": proposal.get("provider", "unknown"), "provider_error": str(proposal.get("error") or ""), "handoff": self.service.get_task(task_id) if hasattr(self.service, "get_task") else handoff, "telemetry": telemetry(context_build_ms=context_build_ms, provider_start_ms=provider_start_ms, provider_time_ms=provider_time_ms), "next_action": "inspect_provider_or_retry_same_task"}
            patch_validation_started = time.perf_counter()
            try:
                changed = self._validate_assisted_patch(str(proposal["patch"]), allowed)
            except Exception as exc:
                patch_validation_ms = max(0, int((time.perf_counter() - patch_validation_started) * 1000))
                recorder = getattr(self.service, "record_canonical_action_failure", None)
                if recorder:
                    recorder(task_id, "ASSIST_PATCH_REJECTED", str(exc))
                return {**envelope, "status": "FINAL_BLOCK", "blocker": "ASSIST_PATCH_REJECTED", "error": str(exc), "provider": proposal.get("provider", "unknown"), "handoff": self.service.get_task(task_id) if hasattr(self.service, "get_task") else handoff, "telemetry": telemetry(context_build_ms=context_build_ms, provider_start_ms=provider_start_ms, provider_time_ms=provider_time_ms, patch_validation_ms=patch_validation_ms), "next_action": "inspect_provider_or_retry_same_task"}
            patch_validation_ms = max(0, int((time.perf_counter() - patch_validation_started) * 1000))
            if not bool(arguments.get("apply", False)):
                return {**envelope, "status": "ASSISTED_CANONICAL_PROPOSAL_READY", "provider": proposal.get("provider", "unknown"), "telemetry": telemetry(context_build_ms=context_build_ms, provider_start_ms=provider_start_ms, provider_time_ms=provider_time_ms, patch_validation_ms=patch_validation_ms), "patch": str(proposal["patch"]), "changed_files": changed, "handoff": handoff, "next_action": "apply_assisted_candidate"}
            try:
                applied = self._apply_runner(patch=str(proposal["patch"]), request=request, provider=str(proposal.get("provider") or "agy"), provider_time_ms=provider_time_ms)
            except Exception as exc:
                recorder = getattr(self.service, "record_canonical_action_failure", None)
                if recorder:
                    recorder(task_id, "ASSIST_APPLY_FAILED", str(exc))
                return {**envelope, "status": "FINAL_BLOCK", "blocker": "ASSIST_APPLY_FAILED", "error": str(exc), "provider": proposal.get("provider", "unknown"), "handoff": self.service.get_task(task_id) if hasattr(self.service, "get_task") else handoff, "telemetry": telemetry(context_build_ms=context_build_ms, provider_start_ms=provider_start_ms, provider_time_ms=provider_time_ms, patch_validation_ms=patch_validation_ms), "next_action": "inspect_provider_or_retry_same_task"}
            applied_telemetry = dict(applied.get("telemetry") or {}) if isinstance(applied, Mapping) else {}
            applied_telemetry.update(telemetry(context_build_ms=context_build_ms, provider_start_ms=provider_start_ms, provider_time_ms=provider_time_ms, patch_validation_ms=patch_validation_ms, verifier_time_ms=int(applied_telemetry.get("verifier_time_ms", 0) or 0), commit_time_ms=int(applied_telemetry.get("commit_time_ms", 0) or 0), worktree_time_ms=int(applied_telemetry.get("worktree_time_ms", 0) or 0), cleanup_time_ms=int(applied_telemetry.get("cleanup_time_ms", 0) or 0)))
            return {**envelope, "status": "ASSISTED_CANONICAL_COMPLETED", "provider": proposal.get("provider", "unknown"), "telemetry": applied_telemetry, "changed_files": changed, "receipt": applied, "handoff": handoff, "next_action": "none"}
        request = self._canonical_request(task_id, what, why, allowed, verifiers, base, action=action.model_dump(mode="json"), contract_binding=binding)
        request.update({"execution_lane": route["execution_lane"]})
        if route["execution_lane"] == "DIRECT_CANONICAL":
            request.update({"primary_agent": True, "worker": "primary"})
            return {**envelope, "status": "DIRECT_CANONICAL_READY", "telemetry": telemetry(), "next_action": "edit_canonical_checkout", "completion_surface": "nexus_task_finish", "base_sha": base, "mutation_lease": {"type": "canonical_mutation_lock", "path": "/tmp/nexus-mcp-gateway-canonical.lock", "required_for_apply": True}, "handoff": self.service.submit_task(request)}
        if binding["contract_kind"] == ContractKind.NONE.value:
            return {**envelope, "status": "FINAL_BLOCK", "blocker": "TASK_CARD_BINDING_REQUIRED", "telemetry": telemetry(), "next_action": "provide_task_card_path_and_hash"}
        request.update({
            "worker": worker if worker != "auto" else "codex",
            "contract_kind": binding["contract_kind"],
            "contract_hash": binding["contract_hash"],
            "owner_inline_contract": binding["owner_inline_contract"],
            "task_card_path": binding["task_card_path"],
            "task_card_hash": binding["task_card_hash"],
        })
        handoff = self.service.submit_task(request)
        return {**envelope, "status": "ISOLATED_TARGET_SUBMITTED", "telemetry": telemetry(), "next_action": "wait_for_task", "target_created": bool(handoff.get("target_created", False)) if isinstance(handoff, Mapping) else None, "handoff": handoff}

    @staticmethod
    def _canonical_request(task_id: str, what: str, why: str, allowed: list[str], verifiers: list[str], base: str, *, action: Optional[Mapping[str, Any]] = None, contract_binding: Optional[Mapping[str, Any]] = None) -> dict[str, Any]:
        request = {
            "task_id": task_id, "what": what, "why": why,
            "controller_revision": base, "target_base_revision": base,
            "controller_repo_root": str(CANONICAL_SOURCE_ROOT),
            "target_repo_root": f"/Users/jameschen/Workspace/nexus-runtime-targets/{task_id}",
            "target_worktree_root": "/Users/jameschen/Workspace/nexus-runtime-targets",
            "allowed_files": allowed, "verifier_commands": verifiers,
        }
        if contract_binding:
            request.update({
                "contract_kind": contract_binding.get("contract_kind"),
                "contract_hash": contract_binding.get("contract_hash"),
                "owner_inline_contract": contract_binding.get("owner_inline_contract"),
                "task_card_path": contract_binding.get("task_card_path"),
                "task_card_hash": contract_binding.get("task_card_hash"),
            })
        if action:
            request["action"] = dict(action)
            request["action_id"] = action.get("action_id")
            request["attempt_id"] = action.get("attempt_id")
            request["idempotency_key"] = action.get("idempotency_key")
            request["action_request_hash"] = action.get("request_hash")
        return request

    @staticmethod
    def _assist_prompt(what: str, why: str, allowed: list[str], verifiers: list[str]) -> str:
        context: list[str] = []
        for raw in allowed:
            path = _safe_relative_path(raw, "allowed_files")
            if path.is_file() and path.stat().st_size <= 128 * 1024:
                context.append(f"FILE {raw}\n{path.read_text(encoding='utf-8')}\nEND FILE")
        return (
            "You are a bounded patch proposer. Use plan/read-only mode. Do not edit files, run tools, or commit. "
            "Return only JSON matching the requested schema, with a unified diff in patch. "
            "The patch string must begin exactly with diff --git and must not use markdown fences. "
            f"WHAT: {what}\nWHY: {why}\nALLOWED FILES: {', '.join(allowed)}\nVERIFIERS: {verifiers}\n" + "\n".join(context)
        )

    @staticmethod
    def _run_agy_plan(*, prompt: str, allowed_files: list[str], provider: str, model: str = "") -> dict[str, Any]:
        """Run any registered assisted provider with one bounded JSON contract.

        The historical name is retained for compatibility, but the provider
        edge is no longer hard-coded to Agy. Unknown providers fail closed;
        registered providers still require an installed executable and return
        parser/transport failures as non-success receipts.
        """
        requested = str(provider or "auto").strip().lower() or "auto"
        if requested == "auto":
            requested = os.environ.get("NEXUS_ASSIST_PROVIDER", "agy").strip().lower() or "agy"
        metadata = ONLINE_CLI_SPEC_REGISTRY.get(requested)
        if metadata is None:
            return {"provider": requested, "blocker": "ASSIST_PROVIDER_NOT_REGISTERED"}
        binary_env = metadata.get("binary_env", "")
        configured = os.environ.get(binary_env, "").strip() if binary_env else ""
        executable = configured or shutil.which(metadata.get("binary_name", requested))
        if not executable or not Path(executable).is_file():
            return {"provider": requested, "blocker": "ASSIST_PROVIDER_UNAVAILABLE"}
        schema = json.dumps({"type": "object", "required": ["patch"], "properties": {"patch": {"type": "string"}, "summary": {"type": "string"}, "tests": {"type": "array", "items": {"type": "string"}}}}, separators=(",", ":"))
        selected_model = str(model or os.environ.get("NEXUS_ASSIST_MODEL", "") or metadata.get("default_model", "")).strip()
        if requested == "agy":
            command = [executable, "--mode", "plan", "--sandbox", "--output-format", "json", "--json-schema", schema, "--effort", "low"]
            if selected_model:
                command.extend(["--model", selected_model])
            command.extend(["--print-timeout", "25s", "--prompt", prompt])
        elif requested == "cline":
            # Cline's JSON mode is non-interactive; yolo is restricted to the
            # bounded canonical apply path or an isolated Target by the caller.
            cline_model = selected_model or "glm-5.2"
            if "/" not in cline_model:
                cline_model = f"cline-pass/{cline_model}"
            command = [executable, "--json", "--plan", "--auto-approve", "false", "--thinking", "none", "--model", cline_model, prompt]
        elif requested == "gemini":
            command = [executable, "--skip-trust", "--approval-mode", "auto_edit", "-m", selected_model, "-p", prompt, "--output-format", "json"]
        elif requested == "opencode":
            command = [executable, "run", "--model", selected_model, prompt]
        elif requested == "codex":
            command = [executable, "exec", "--json", "--full-auto", "-m", selected_model, prompt]
        elif requested == "mimo":
            command = [executable, "run", "--model", selected_model, prompt]
        elif requested == "ollama":
            command = [executable, "run", selected_model, prompt]
        elif requested == "grok":
            command = [executable, "--model", selected_model, "--single", prompt, "--output-format", "json", "--no-alt-screen"]
        else:
            command = [executable, "--model", selected_model, "--prompt", prompt]
        provider_timeout = 90 if requested == "cline" else 30
        try:
            result = subprocess.run(command, cwd=CANONICAL_SOURCE_ROOT, capture_output=True, text=True, timeout=provider_timeout, check=False)
        except subprocess.TimeoutExpired as exc:
            return {
                "provider": requested,
                "model": selected_model,
                "blocker": "ASSIST_PROVIDER_TIMEOUT",
                "timeout_seconds": provider_timeout,
                "error": str(exc),
                "tool_policy_enforcement": "cline_plan_auto_approve_false_allowlist_not_enforced" if requested == "cline" else "provider_specific",
            }
        if result.returncode != 0:
            return {"provider": requested, "model": selected_model, "blocker": "ASSIST_PROVIDER_FAILED", "error": result.stderr.strip()[-1000:]}
        def decode_object(text: str) -> dict[str, Any] | None:
            candidates = [text.strip()]
            match = re.search(r"\{.*\}", text, re.DOTALL)
            if match and match.group(0) not in candidates:
                candidates.append(match.group(0))
            for candidate_text in candidates:
                try:
                    candidate = json.loads(candidate_text)
                except json.JSONDecodeError:
                    continue
                if isinstance(candidate, dict):
                    return candidate
            return None

        payload = decode_object(result.stdout)
        if requested == "cline" and isinstance(payload, dict) and "patch" not in payload:
            payload = None
        if payload is None:
            for line in reversed(result.stdout.splitlines()):
                try:
                    candidate = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(candidate, dict):
                    continue
                nested_texts = [str(candidate.get("text") or "")]
                event = candidate.get("event")
                if isinstance(event, dict):
                    nested_texts.append(str(event.get("text") or ""))
                for nested_text in nested_texts:
                    if nested_text:
                        payload = decode_object(nested_text)
                        if payload is not None:
                            break
                if payload is not None:
                    break
                if requested != "cline":
                    payload = candidate
                    break
            if payload is None:
                return {"provider": requested, "model": selected_model, "blocker": "ASSIST_PROVIDER_MALFORMED_OUTPUT"}
        if isinstance(payload, dict) and isinstance(payload.get("result"), dict):
            payload = payload["result"]
        if not isinstance(payload, dict):
            return {"provider": requested, "model": selected_model, "blocker": "ASSIST_PROVIDER_MALFORMED_OUTPUT"}
        payload["provider"] = requested
        payload["model"] = selected_model
        if requested == "cline":
            payload["tool_policy_enforcement"] = "cline_plan_auto_approve_false_allowlist_not_enforced"
        return payload

    @staticmethod
    def _validate_assisted_patch(patch: str, allowed: list[str]) -> list[str]:
        if not patch.startswith("diff --git "):
            raise GatewayInputError("assist output must begin with diff --git")
        changed: list[str] = []
        for line in patch.splitlines():
            if line.startswith("+++ b/"):
                path = line[6:]
                _safe_relative_path(path, "assist patch")
                changed.append(path)
            if line.startswith("+++ /dev/null"):
                raise GatewayInputError("assist deletions are forbidden")
        changed = sorted(set(changed))
        if not changed:
            raise GatewayInputError("assist patch has no changed files")
        for path in changed:
            if not any(path == boundary or boundary.endswith("/") and path.startswith(boundary) for boundary in allowed):
                raise GatewayInputError(f"assist patch changed file outside allowed_files: {path}")
        check = subprocess.run(["git", "apply", "--check", "--binary", "--whitespace=nowarn", "-"], cwd=CANONICAL_SOURCE_ROOT, input=patch, capture_output=True, text=True, timeout=5, check=False)
        if check.returncode != 0:
            raise GatewayInputError(check.stderr.strip() or "assist patch does not apply cleanly")
        return changed

    def _apply_assisted_patch(self, *, patch: str, request: Mapping[str, Any], provider: str, provider_time_ms: int) -> dict[str, Any]:
        apply_started = time.perf_counter()
        lock_path = Path("/tmp/nexus-mcp-gateway-canonical.lock")
        with lock_path.open("w", encoding="utf-8") as lock_handle:
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX)
            if _git("status", "--porcelain=v1").strip():
                raise RuntimeError("canonical checkout must be clean")
            base = _git("rev-parse", "HEAD").strip()
            if base != request["controller_revision"]:
                raise RuntimeError("canonical revision drift")
            changed = self._validate_assisted_patch(patch, list(request["allowed_files"]))
            applied = False
            try:
                apply_result = subprocess.run(["git", "apply", "--binary", "--whitespace=nowarn", "-"], cwd=CANONICAL_SOURCE_ROOT, input=patch, capture_output=True, text=True, timeout=10, check=False)
                if apply_result.returncode != 0:
                    raise RuntimeError(apply_result.stderr.strip() or "assist patch apply failed")
                applied = True
                changed_after = _git("diff", "--name-only").splitlines()
                if sorted(changed_after) != changed or _git("diff", "--diff-filter=D", "--name-only").strip():
                    raise RuntimeError("assist patch scope or deletion gate failed")
                for command in request.get("verifier_commands") or ["git diff --check"]:
                    tokens = shlex.split(str(command))
                    if not tokens or any(token in {";", "&&", "||", "|", ">", "`"} for token in tokens):
                        raise RuntimeError("verifier command is not bounded")
                    if tokens[:2] in (["git", "commit"], ["git", "push"], ["git", "merge"], ["git", "reset"], ["git", "clean"]):
                        raise RuntimeError("verifier command may not mutate lifecycle state")
                    result = subprocess.run(tokens, cwd=CANONICAL_SOURCE_ROOT, capture_output=True, text=True, timeout=30, check=False)
                    if result.returncode != 0:
                        raise RuntimeError(f"verifier failed: {command}: {result.stderr.strip()}")
                commit_started = time.perf_counter()
                subprocess.run(["git", "add", "--", *changed], cwd=CANONICAL_SOURCE_ROOT, check=True, capture_output=True, text=True)
                commit = subprocess.run(["git", "commit", "-m", f"feat(assist): apply bounded model patch {request['task_id']}"], cwd=CANONICAL_SOURCE_ROOT, capture_output=True, text=True, check=False)
                if commit.returncode != 0:
                    raise RuntimeError(commit.stderr.strip() or "assist commit failed")
                receipt = self.service.complete_direct_canonical({**dict(request), "execution_lane": "DIRECT_CANONICAL", "primary_agent": True, "worker": "primary"}, expected_commit_sha=_git("rev-parse", "HEAD").strip())
                receipt.setdefault("telemetry", {}).update({"provider_time_ms": provider_time_ms, "worktree_time_ms": 0, "commit_time_ms": max(0, int((time.perf_counter() - commit_started) * 1000)), "cleanup_time_ms": 0, "total_wall_time_ms": max(0, int((time.perf_counter() - apply_started) * 1000))})
                return receipt
            except Exception:
                if applied:
                    subprocess.run(["git", "reset", "--", *changed], cwd=CANONICAL_SOURCE_ROOT, capture_output=True, text=True, check=False)
                    subprocess.run(["git", "apply", "-R", "--binary", "--whitespace=nowarn", "-"], cwd=CANONICAL_SOURCE_ROOT, input=patch, capture_output=True, text=True, check=False)
                raise

    def _finish(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        lane = _text(arguments.get("execution_lane"), "execution_lane").upper()
        if lane == "DIRECT_CANONICAL":
            request = dict(arguments.get("request") or {})
            if not request:
                task_id = _text(arguments.get("task_id"), "task_id")
                base = arguments.get("base_sha") or arguments.get("controller_revision")
                if not isinstance(base, str) or not _SHA_RE.fullmatch(base):
                    raise GatewayInputError("base_sha is required for minimal Direct finish")
                allowed = [str(path).strip() for path in (arguments.get("allowed_files") or []) if str(path).strip()]
                if not allowed or len(allowed) > 4:
                    raise GatewayInputError("allowed_files is required for minimal Direct finish")
                for path in allowed:
                    _safe_relative_path(path, "allowed_files")
                request = self._canonical_request(
                    task_id,
                    "Complete bounded canonical task",
                    "Finish the prior gateway Direct handoff",
                    allowed,
                    list(arguments.get("verifier_commands") or ["git diff --check"]),
                    base,
                )
            request.setdefault("execution_lane", "DIRECT_CANONICAL")
            request.setdefault("primary_agent", True)
            request.setdefault("worker", "primary")
            result = self.service.complete_direct_canonical(request, expected_commit_sha=arguments.get("expected_commit_sha"))
            action_payload = request.get("action") if isinstance(request.get("action"), Mapping) else None
            if action_payload is not None:
                result["guard_receipt"] = post_action_receipt_formatter(
                    action=action_payload,
                    status="COMPLETED",
                    commit_sha=result.get("commit_sha"),
                    receipt=result,
                )
            return result
        if lane == "ISOLATED_TARGET":
            task_id = _text(arguments.get("task_id"), "task_id")
            fields = ("candidate_commit_sha", "candidate_tree_sha", "candidate_state_hash", "verified_receipt_hash")
            values = {field: _text(arguments.get(field), field) for field in fields}
            return self.service.owner_finish(task_id, **values)
        raise GatewayInputError("execution_lane is unsupported")

    def _call_tool(self, name: str, arguments: Mapping[str, Any]) -> dict[str, Any]:
        if name == "nexus_gateway_status":
            return self._gateway_status()
        if name == "nexus_workspace_snapshot":
            return self._workspace_snapshot()
        if name == "nexus_read":
            return self._read(arguments)
        if name == "nexus_search":
            return self._search(arguments)
        if name == "nexus_git_diff":
            return self._diff(arguments)
        if name == "nexus_task_run":
            return self._task_run(arguments)
        if name == "nexus_task_status":
            task_id = _text(arguments.get("task_id"), "task_id")
            assisted = self._assist_read(task_id)
            if assisted is not None:
                return self._assist_response(self._assist_refresh(task_id) or assisted, operation="status")
            return self.service.get_task(task_id)
        if name == "nexus_task_wait":
            task_id = _text(arguments.get("task_id"), "task_id")
            timeout = min(60.0, max(0.0, float(arguments.get("timeout_seconds", 10.0))))
            poll = min(5.0, max(0.01, float(arguments.get("poll_interval_seconds", 0.25))))
            if self._assist_read(task_id) is not None:
                return self._assist_wait(task_id, timeout_seconds=timeout, poll_interval_seconds=poll)
            return self.service.wait_task(task_id, timeout_seconds=timeout, poll_interval_seconds=poll)
        if name == "nexus_task_finish":
            return self._finish(arguments)
        if name == "nexus_task_cancel":
            task_id = _text(arguments.get("task_id"), "task_id")
            if self._assist_read(task_id) is not None:
                return self._assist_cancel(task_id)
            return self.service.cancel_task(task_id)
        if name == "nexus_task_list_actionable":
            return self._task_list_actionable(arguments)
        if name == "nexus_task_reconcile":
            return self._task_reconcile(arguments)
        if name == "nexus_task_retry":
            return self._task_retry(arguments)
        if name == "nexus_task_resume":
            return self._task_resume(arguments)
        if name == "nexus_assist_submit":
            return self._assist_submit(arguments)
        if name == "nexus_assist_result":
            task_id = _text(arguments.get("task_id"), "task_id")
            job = self._assist_read(task_id)
            if job is None:
                raise KeyError(f"unknown task_id: {task_id}")
            return self._assist_response(self._assist_refresh(task_id) or job, operation="result")
        if name == "nexus_assist_cancel":
            return self._assist_cancel(_text(arguments.get("task_id"), "task_id"))
        if name == "nexus_provider_preflight":
            return self._provider_preflight(arguments)
        if name == "nexus_task_card_create":
            return self._task_card_create(arguments)
        if name == "nexus_model_probe":
            return self._model_probe_submit(arguments)
        if name == "nexus_model_probe_result":
            task_id = _text(arguments.get("task_id"), "task_id")
            job = self._assist_read(task_id)
            if job is None or job.get("job_kind") != "model_probe":
                raise KeyError(f"unknown model_probe task_id: {task_id}")
            return self._assist_response(self._assist_refresh(task_id) or job, operation="result")
        if name == "nexus_candidate_approve":
            return self._candidate_approve(arguments)
        if name == "nexus_candidate_integrate":
            return self._candidate_integrate(arguments)
        if name == "nexus_candidate_dispose":
            return self._candidate_dispose(arguments)
        raise GatewayInputError(f"unknown public tool: {name}")

    def handle(self, request: Mapping[str, Any]) -> Optional[dict[str, Any]]:
        method = request.get("method")
        request_id = request.get("id")
        if method == "notifications/initialized" or request_id is None:
            return None
        if method == "initialize":
            return {
                "jsonrpc": "2.0", "id": request_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {"listChanged": False}},
                    "serverInfo": {
                        "name": GATEWAY_NAME,
                        "title": PUBLIC_APP_NAME,
                        "version": GATEWAY_VERSION,
                        "toolManifestRevision": TOOL_MANIFEST_REVISION,
                        "fullToolSchemaHash": FULL_TOOL_SCHEMA_HASH,
                        "permissionPolicyHash": PERMISSION_POLICY_HASH,
                        "taskContractRevision": TASK_CONTRACT_REVISION,
                        "lifecycleRevision": LIFECYCLE_REVISION,
                        "serverInstanceId": SERVER_INSTANCE_ID,
                        "serverStartedAt": SERVER_STARTED_AT,
                    },
                },
            }
        if method == "tools/list":
            return {"jsonrpc": "2.0", "id": request_id, "result": {"tools": self.tool_specs()}}
        if method == "tools/call":
            params = request.get("params") or {}
            try:
                return self._success(request_id, self._call_tool(str(params.get("name", "")), params.get("arguments") or {}))
            except Exception as exc:
                return self._error(request_id, exc)
        return {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32601, "message": f"method not found: {method}"}}

    def serve(self, input_stream, output_stream) -> None:
        for line in input_stream:
            if not line.strip():
                continue
            response = self.handle(json.loads(line))
            if response is not None:
                output_stream.write(json.dumps(response, sort_keys=True, ensure_ascii=False) + "\n")
                output_stream.flush()


# Single manifest truth: every public name is derived from the actual MCP
# schema returned by tools/list.  No second hand-maintained inventory can drift
# from connector discovery, status, health, or recommended-tool validation.
PUBLIC_TOOL_NAMES = tuple(spec["name"] for spec in UnifiedMCPGateway.tool_specs())
TOOL_MANIFEST_REVISION = hashlib.sha256(
    json.dumps(PUBLIC_TOOL_NAMES, separators=(",", ":")).encode("utf-8")
).hexdigest()
FULL_TOOL_SCHEMA_HASH = hashlib.sha256(
    json.dumps(UnifiedMCPGateway.tool_specs(), sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
).hexdigest()
try:
    SERVER_REPO_HEAD_AT_START = _git("rev-parse", "HEAD").strip() or "unknown"
except Exception:
    SERVER_REPO_HEAD_AT_START = "unknown"
configure_runtime_manifest_hash(TOOL_MANIFEST_REVISION)
