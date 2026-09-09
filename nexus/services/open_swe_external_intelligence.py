"""Thin external-process adapters for the Open SWE execution runtime.

Nexus owns request identity, durable orchestration, replay/reconciliation authority,
worker admission, Candidate capture, acceptance, and GitHub/merge authority.  The
Deep Agents/provider runtime lives in a separate executable and dependency domain.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import signal
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from nexus.services.external_intelligence import TransportResult
from nexus.services.external_intelligence_fanout import FanoutError, OpenCodeRunResult

PROTOCOL_REQUEST_SCHEMA = "nexus.open_swe_runtime.request.v1"
PROTOCOL_RESULT_SCHEMA = "nexus.open_swe_runtime.result.v1"
READ_ONLY_SEMANTIC_TOOLS = frozenset({"glob", "grep", "ls", "read_file", "record_finding"})
FORBIDDEN_SEMANTIC_TOOLS = frozenset({
    "delete",
    "delete_file",
    "deploy",
    "edit_file",
    "execute",
    "fetch_url",
    "git_commit",
    "git_push",
    "http_request",
    "merge",
    "release",
    "shell",
    "task",
    "web_search",
    "write_file",
})
DIAGNOSIS_TOOL_SURFACE = frozenset({"glob", "grep", "ls", "read_file", "record_diagnosis"})
REPAIR_TOOL_SURFACE = frozenset({
    "edit_file",
    "glob",
    "grep",
    "ls",
    "read_file",
    "record_worker_result",
    "write_file",
})
_SESSION_RE = re.compile(r"^ses_open_swe_[0-9a-f]{20}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
OPEN_SWE_DISTRIBUTION = "nexus-open-swe-runtime"
_SYSTEM_ENV_ALLOWLIST = (
    "HOME",
    "LANG",
    "LC_ALL",
    "PATH",
    "SSL_CERT_DIR",
    "SSL_CERT_FILE",
    "TMPDIR",
)
_PROVIDER_ENV_ALLOWLIST = {
    "google_genai": ("GEMINI_API_KEY", "GOOGLE_API_KEY"),
    "openai": ("OPENAI_API_KEY",),
    "anthropic": ("ANTHROPIC_API_KEY",),
}

EFFECT_RECOVERY_STATUS = "EFFECT_RECOVERED_PENDING_VERIFICATION"


class OpenSWEExternalIntelligenceError(RuntimeError):
    """Fail-closed external Open SWE transport error."""


def _validate_runtime_binding(executable: str, expected_artifact_sha256: str) -> tuple[str, str]:
    selected = str(executable or "").strip()
    expected = str(expected_artifact_sha256 or "").strip().lower()
    if not selected:
        raise OpenSWEExternalIntelligenceError("OPEN_SWE_EXECUTABLE_REQUIRED")
    if "\x00" in selected or not Path(selected).is_absolute():
        raise OpenSWEExternalIntelligenceError("OPEN_SWE_EXECUTABLE_ABSOLUTE_REQUIRED")
    if _SHA256_RE.fullmatch(expected) is None:
        raise OpenSWEExternalIntelligenceError("OPEN_SWE_EXPECTED_ARTIFACT_HASH_REQUIRED")
    return selected, expected


def _validate_runtime_identity(value: Mapping[str, Any], expected_hash: str) -> None:
    if (
        value.get("schema") != PROTOCOL_RESULT_SCHEMA
        or value.get("kind") != "identity"
        or value.get("status") != "IDENTIFIED"
        or value.get("distribution_name") != OPEN_SWE_DISTRIBUTION
        or not isinstance(value.get("distribution_version"), str)
        or value.get("runtime_protocol_version") != PROTOCOL_REQUEST_SCHEMA
        or value.get("authority_boundary") != "execution_runtime_only"
        or value.get("process_started") is not False
        or value.get("outcome_unknown") is not False
        or value.get("retry_safe") is not True
    ):
        raise OpenSWEExternalIntelligenceError("OPEN_SWE_RUNTIME_IDENTITY_INVALID")
    artifact = value.get("artifact_identity")
    if not isinstance(artifact, Mapping):
        raise OpenSWEExternalIntelligenceError("OPEN_SWE_RUNTIME_IDENTITY_INVALID")
    module_file = artifact.get("module_file")
    module_hash = artifact.get("module_sha256")
    if (
        not isinstance(module_file, str)
        or not module_file
        or not Path(module_file).is_absolute()
        or not isinstance(module_hash, str)
        or _SHA256_RE.fullmatch(module_hash.lower()) is None
        or module_hash.lower() != expected_hash
        or not isinstance(artifact.get("deepagents_version"), str)
    ):
        raise OpenSWEExternalIntelligenceError("OPEN_SWE_RUNTIME_ARTIFACT_MISMATCH")


def _semantic_attestation(value: Mapping[str, Any], field: str) -> str | None:
    """Return an explicitly observed identity, never a configured default."""

    observed = value.get(field)
    if (
        not isinstance(observed, str)
        or not observed
        or observed != observed.strip()
        or "\x00" in observed
    ):
        return None
    return observed


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha256(value: bytes | str) -> str:
    raw = value.encode("utf-8") if isinstance(value, str) else value
    return hashlib.sha256(raw).hexdigest()


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate JSON key")
        value[key] = item
    return value


def _default_runtime_state_root() -> Path:
    return Path.home() / ".local" / "state" / "nexus" / "open_swe_runtime"


def _runtime_env(provider_id: str) -> dict[str, str]:
    """Pass only process/runtime essentials plus the selected provider credential.

    GitHub/GH credentials and arbitrary controller environment are deliberately
    absent.  The runtime graph has no environment-reading tool surface.
    """

    allowed = [*_SYSTEM_ENV_ALLOWLIST, *_PROVIDER_ENV_ALLOWLIST.get(provider_id, ())]
    return {name: os.environ[name] for name in allowed if name in os.environ}


def _safe_state_file(path: Path) -> dict[str, Any] | None:
    """Read one owner-only runtime record without following symlinks."""
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        try:
            stat = os.fstat(fd)
            if not stat or stat.st_uid != os.getuid() or stat.st_mode & 0o022:
                return None
            if stat.st_size > 1_048_576:
                return None
            value = json.loads(os.read(fd, stat.st_size).decode("utf-8"))
        finally:
            os.close(fd)
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return None
    return dict(value) if isinstance(value, Mapping) else None


def _safe_journal_file(root: Path, relative: str) -> dict[str, Any] | None:
    path = root / relative
    try:
        ancestors = []
        current = path.parent
        while True:
            ancestors.append(current)
            if current == root:
                break
            if root not in current.parents:
                return None
            current = current.parent
        for parent in (root, *ancestors):
            if parent.is_symlink() or not parent.is_dir():
                return None
            stat = parent.stat()
            if stat.st_uid != os.getuid() or stat.st_mode & 0o022:
                return None
        if path.is_symlink():
            return None
        return _safe_state_file(path)
    except (OSError, ValueError):
        return None


def _inspect_effect_recovery(
    *,
    runtime_state_root: Path,
    operation_id: str,
    workspace_path: Path,
    provider_id: str,
    model_id: str,
    worker_identity_sha256: str,
) -> dict[str, Any] | None:
    """Return host-derived evidence for one already-applied Open SWE effect."""
    root = runtime_state_root.expanduser()
    workspace = workspace_path.expanduser()
    if not root.is_absolute():
        root = Path(os.path.abspath(root))
    if not workspace.is_absolute():
        workspace = Path(os.path.abspath(workspace))
    try:
        for directory in (
            root,
            root / "operations",
            root / "recovery",
            root / "recovery" / "operations",
            root / "recovery" / "effects",
            workspace,
        ):
            if directory.is_symlink() or not directory.is_dir():
                return None
            stat = directory.stat()
            if stat.st_uid != os.getuid() or stat.st_mode & 0o022:
                return None
    except OSError:
        return None
    operation = _safe_journal_file(root, f"operations/{operation_id}.json")
    if operation is None or operation.get("operation_id") != operation_id:
        return None
    if (
        operation.get("status") != "OPEN_SWE_OUTCOME_UNKNOWN"
        or operation.get("outcome_unknown") is not True
    ):
        return None
    if str(Path(str(operation.get("directory") or "")).expanduser()) != str(workspace):
        return None
    if operation.get("provider_id") != provider_id or operation.get("model_id") != model_id:
        return None
    if worker_identity_sha256 and operation.get("worker_identity_sha256") != worker_identity_sha256:
        return None
    journal = _safe_journal_file(root, f"recovery/operations/{operation_id}.json")
    if journal is None:
        return None
    journal_identity = journal.get("identity")
    if not isinstance(journal_identity, Mapping):
        return None
    if (
        journal.get("status") != "ASK_DISPATCHING"
        or not journal.get("turn_id")
        or journal.get("turn_id") == journal.get("protocol_repair_turn_id")
        or journal_identity.get("operation_id") != operation_id
        or str(Path(str(journal_identity.get("workspace") or "")).expanduser()) != str(workspace)
        or journal_identity.get("provider_id") != provider_id
        or journal_identity.get("model_id") != model_id
        or (
            worker_identity_sha256
            and journal_identity.get("worker_identity_sha256") != worker_identity_sha256
        )
        or journal.get("protocol_repair_status") != "RECOVERED"
    ):
        return None
    allowed_paths = journal_identity.get("allowed_paths")
    if (
        not isinstance(allowed_paths, list)
        or not allowed_paths
        or any(
            not isinstance(value, str) or not value or Path(value).is_absolute()
            for value in allowed_paths
        )
    ):
        return None
    recovered_raw = journal.get("recovered_response")
    if not isinstance(recovered_raw, str):
        return None
    try:
        recovered = json.loads(recovered_raw, object_pairs_hook=_strict_object)
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
    if not isinstance(recovered, Mapping):
        return None
    name = recovered.get("name")
    arguments = recovered.get("arguments")
    if set(recovered) != {"type", "name", "arguments"} or recovered.get("type") != "tool_call":
        return None
    raw = recovered_raw
    if not isinstance(name, str) or not isinstance(arguments, Mapping):
        return None
    original_arguments = dict(arguments)
    normalized_arguments = dict(arguments)
    if isinstance(normalized_arguments.get("file_path"), str):
        candidate_path = Path(normalized_arguments["file_path"]).expanduser()
        if candidate_path.is_absolute():
            try:
                normalized_arguments["file_path"] = candidate_path.relative_to(workspace).as_posix()
            except ValueError:
                normalized_arguments["file_path"] = candidate_path.as_posix().lstrip("/")
    tool_call_canonical = _canonical_json({
        "name": name,
        "arguments": original_arguments,
        "raw": raw,
    })
    tool_call_id = "opencli_" + _sha256(tool_call_canonical)[:24]
    effect_canonical = _canonical_json({
        "operation_id": operation_id,
        "turn_id": journal.get("protocol_repair_turn_id"),
        "tool_call_id": tool_call_id,
        "tool_name": name,
        "arguments": normalized_arguments,
    })
    effect_id = "effect_" + _sha256(effect_canonical)
    effect = _safe_journal_file(root, f"recovery/effects/{effect_id}.json")
    if effect is None:
        return None
    if (
        effect.get("status") != "RESULT"
        or effect.get("tool_name") not in {"write_file", "edit_file"}
        or effect.get("effect_id") != effect_id
        or effect.get("tool_call_id") != tool_call_id
        or effect.get("turn_id") != journal.get("protocol_repair_turn_id")
        or not effect.get("tool_call_id")
    ):
        return None
    raw_path = effect.get("path")
    effect_arguments = effect.get("arguments")
    postimage = effect.get("postimage")
    if (
        not isinstance(raw_path, str)
        or not isinstance(effect_arguments, Mapping)
        or not isinstance(postimage, str)
    ):
        return None
    path = Path(raw_path).expanduser()
    if path.is_symlink() or not path.is_file():
        return None
    try:
        current = path.parent
        while current != workspace:
            if current.is_symlink() or workspace not in current.parents:
                return None
            current = current.parent
        relative = path.relative_to(workspace).as_posix()
        actual = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError, ValueError):
        return None
    if (
        effect_arguments.get("file_path") != relative
        or effect_arguments.get("content") != postimage
    ):
        return None
    if relative not in allowed_paths:
        return None
    if _sha256(actual) != str(effect.get("postimage_sha256") or ""):
        return None
    if _sha256(postimage) != str(effect.get("postimage_sha256") or ""):
        return None
    return {
        "status": EFFECT_RECOVERY_STATUS,
        "effect_id": str(effect.get("effect_id") or ""),
        "operation_id": operation_id,
        "turn_id": str(effect.get("turn_id") or ""),
        "tool_call_id": str(effect.get("tool_call_id") or ""),
        "tool_name": str(effect.get("tool_name") or ""),
        "path": relative,
        "postimage_sha256": str(effect.get("postimage_sha256") or ""),
    }


def _normalize_transport_config(
    provider_id: str, transport_config: Mapping[str, Any] | None
) -> dict[str, Any]:
    if provider_id != "opencli_chatgpt":
        if transport_config:
            raise OpenSWEExternalIntelligenceError("OPEN_SWE_TRANSPORT_CONFIG_PROVIDER_MISMATCH")
        return {}
    if not isinstance(transport_config, Mapping):
        raise OpenSWEExternalIntelligenceError("OPEN_SWE_TRANSPORT_CONFIG_REQUIRED")
    expected = {"executable", "profile", "site_session", "timeout_seconds"}
    if set(transport_config) != expected:
        raise OpenSWEExternalIntelligenceError("OPEN_SWE_TRANSPORT_CONFIG_INVALID")
    executable = transport_config.get("executable")
    profile = transport_config.get("profile")
    site_session = transport_config.get("site_session")
    timeout_seconds = transport_config.get("timeout_seconds")
    if (
        not isinstance(executable, str)
        or not executable.strip()
        or "\x00" in executable
        or not Path(executable.strip()).is_absolute()
    ):
        raise OpenSWEExternalIntelligenceError("OPEN_SWE_TRANSPORT_CONFIG_INVALID")
    if not isinstance(profile, str) or not profile.strip() or "\x00" in profile:
        raise OpenSWEExternalIntelligenceError("OPEN_SWE_TRANSPORT_CONFIG_INVALID")
    if not isinstance(site_session, str) or site_session.strip() not in {"ephemeral", "persistent"}:
        raise OpenSWEExternalIntelligenceError("OPEN_SWE_TRANSPORT_CONFIG_INVALID")
    if (
        not isinstance(timeout_seconds, int)
        or isinstance(timeout_seconds, bool)
        or not 30 <= timeout_seconds <= 900
    ):
        raise OpenSWEExternalIntelligenceError("OPEN_SWE_TRANSPORT_CONFIG_INVALID")
    return {
        "executable": executable.strip(),
        "profile": profile.strip(),
        "site_session": site_session.strip(),
        "timeout_seconds": timeout_seconds,
    }


def _safe_request_hash(payload: Mapping[str, Any]) -> str:
    safe = {
        "schema": payload.get("schema"),
        "operation": payload.get("operation"),
        "operation_id": payload.get("operation_id"),
        "provider_id": payload.get("provider_id"),
        "model_id": payload.get("model_id"),
        "workspace_path": payload.get("workspace_path"),
        "repository_root": payload.get("repository_root"),
        "session_id": payload.get("session_id"),
        "worker_identity_sha256": payload.get("worker_identity_sha256"),
    }
    return _sha256(_canonical_json(safe))


def _runtime_call(
    executable: str,
    payload: Mapping[str, Any],
    *,
    provider_id: str,
    timeout: float,
) -> tuple[dict[str, Any] | None, str, bool, str]:
    """Run one external runtime operation.

    Returns ``(result, stderr, process_started, failure_kind)``.  Any timeout,
    non-zero exit, or invalid stdout after process start is conservatively
    ambiguous because the external runtime may already have invoked a model or
    mutated its bounded workspace.  Reconciliation is a separate read-only call.
    """

    try:
        process = subprocess.Popen(
            [executable],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=True,
            shell=False,
            env=_runtime_env(provider_id),
        )
    except FileNotFoundError:
        return None, "", False, "runtime_not_found"
    try:
        try:
            stdout, stderr = process.communicate(
                _canonical_json(dict(payload)) + "\n", timeout=timeout
            )
        except subprocess.TimeoutExpired:
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except (OSError, ProcessLookupError):
                pass
            try:
                stdout, stderr = process.communicate(timeout=2)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except (OSError, ProcessLookupError):
                    pass
                stdout, stderr = process.communicate()
            return None, stderr or "", True, "runtime_timeout"
    finally:
        for stream in (process.stdin, process.stdout, process.stderr):
            if stream is not None:
                stream.close()
    if process.returncode != 0:
        return None, stderr or "", True, f"runtime_nonzero:{process.returncode}"
    try:
        value = json.loads(stdout or "")
    except json.JSONDecodeError:
        return None, stderr or "", True, "runtime_result_invalid"
    if not isinstance(value, dict) or value.get("schema") != PROTOCOL_RESULT_SCHEMA:
        return None, stderr or "", True, "runtime_result_invalid"
    return dict(value), stderr or "", True, ""


def _semantic_failure(
    status: str,
    *,
    outcome_unknown: bool,
    retry_safe: bool,
    started: str,
    safe_argv: tuple[str, ...],
) -> TransportResult:
    return TransportResult(
        status,
        outcome_unknown=outcome_unknown,
        retry_safe=retry_safe,
        started_at=started,
        finished_at=_now(),
        safe_argv=safe_argv,
    )


class OpenSWEExternalIntelligenceTransport:
    """Nexus-side client for one external Open SWE semantic runtime."""

    def __init__(
        self,
        *,
        repository_root: str | Path,
        model_provider: str,
        model_id: str,
        executable: str = "",
        expected_artifact_sha256: str = "",
        runtime_state_root: str | Path | None = None,
        timeout: float = 180.0,
        transport_config: Mapping[str, Any] | None = None,
    ) -> None:
        root = Path(repository_root).expanduser().resolve()
        if not root.is_dir():
            raise OpenSWEExternalIntelligenceError("OPEN_SWE_REPOSITORY_ROOT_INVALID")
        provider = str(model_provider or "").strip()
        selected_model = str(model_id or "").strip()
        selected_executable, expected_hash = _validate_runtime_binding(
            executable, expected_artifact_sha256
        )
        if not provider or not selected_model:
            raise OpenSWEExternalIntelligenceError("OPEN_SWE_MODEL_BINDING_REQUIRED")
        self.repository_root = root
        self.model_provider = provider
        self.model_id = selected_model
        self.executable = selected_executable
        self.expected_artifact_sha256 = expected_hash
        self.runtime_state_root = (
            Path(
                runtime_state_root
                if runtime_state_root is not None
                else _default_runtime_state_root()
            )
            .expanduser()
            .resolve()
        )
        self.timeout = float(timeout)
        self.transport_config = _normalize_transport_config(provider, transport_config)

    def safe_argv(self) -> tuple[str, ...]:
        return (self.executable, "<json-stdin>")

    @staticmethod
    def _operation_id(prompt: str) -> str:
        return _sha256(prompt)

    def _request(self, operation: str, prompt: str) -> TransportResult:
        if not self._ensure_runtime_identity():
            return _semantic_failure(
                "OPEN_SWE_RUNTIME_IDENTITY_FAILED",
                outcome_unknown=operation == "semantic_reconcile",
                retry_safe=False,
                started=_now(),
                safe_argv=self.safe_argv(),
            )
        started = _now()
        payload = {
            "schema": PROTOCOL_REQUEST_SCHEMA,
            "operation": operation,
            "operation_id": self._operation_id(prompt),
            "provider_id": self.model_provider,
            "model_id": self.model_id,
            "repository_root": str(self.repository_root),
            "runtime_state_root": str(self.runtime_state_root),
            "transport_config": dict(self.transport_config),
            "prompt": prompt if operation == "semantic_run" else "",
        }
        value, _stderr, process_started, failure = _runtime_call(
            self.executable,
            payload,
            provider_id=self.model_provider,
            timeout=self.timeout,
        )
        safe = self.safe_argv()
        if value is None:
            if failure == "runtime_not_found" and operation == "semantic_run":
                return _semantic_failure(
                    "OPEN_SWE_RUNTIME_NOT_FOUND",
                    outcome_unknown=False,
                    retry_safe=True,
                    started=started,
                    safe_argv=safe,
                )
            return _semantic_failure(
                "OPEN_SWE_OUTCOME_UNKNOWN",
                outcome_unknown=True,
                retry_safe=False,
                started=started,
                safe_argv=safe,
            )
        if value.get("kind") != "semantic":
            return _semantic_failure(
                "OPEN_SWE_RESULT_INVALID",
                outcome_unknown=process_started,
                retry_safe=False,
                started=started,
                safe_argv=safe,
            )
        provider = _semantic_attestation(value, "provider_id")
        model = _semantic_attestation(value, "model_id")
        if provider is None or model is None:
            return _semantic_failure(
                "OPEN_SWE_MODEL_ATTESTATION_MISMATCH",
                outcome_unknown=True,
                retry_safe=False,
                started=started,
                safe_argv=safe,
            )
        if provider != self.model_provider or model != self.model_id:
            return _semantic_failure(
                "OPEN_SWE_MODEL_ATTESTATION_MISMATCH",
                outcome_unknown=True,
                retry_safe=False,
                started=started,
                safe_argv=safe,
            )
        status = str(value.get("status") or "OPEN_SWE_RESULT_INVALID")
        return TransportResult(
            status,
            raw=str(value.get("raw") or ""),
            conversation_id=str(value.get("session_id") or ""),
            outcome_unknown=bool(value.get("outcome_unknown")),
            retry_safe=bool(value.get("retry_safe")),
            started_at=str(value.get("started_at") or started),
            finished_at=str(value.get("finished_at") or _now()),
            safe_argv=safe,
        )

    def _ensure_runtime_identity(self) -> bool:
        payload = {
            "schema": PROTOCOL_REQUEST_SCHEMA,
            "operation": "identity",
            "provider_id": self.model_provider,
            "model_id": self.model_id,
            "runtime_state_root": str(self.runtime_state_root),
            "transport_config": dict(self.transport_config),
        }
        value, _stderr, _started, failure = _runtime_call(
            self.executable, payload, provider_id=self.model_provider, timeout=self.timeout
        )
        if value is None:
            return False
        try:
            _validate_runtime_identity(value, self.expected_artifact_sha256)
        except OpenSWEExternalIntelligenceError:
            return False
        return True

    def invoke(self, prompt: str) -> TransportResult:
        return self._request("semantic_run", prompt)

    def reconcile(self, prompt: str) -> TransportResult:
        return self._request("semantic_reconcile", prompt)


class OpenSWEWorkerTransport:
    """Nexus-side client for external Open SWE diagnosis/repair execution."""

    def __init__(
        self,
        *,
        model_provider: str,
        model_id: str,
        executable: str = "",
        expected_artifact_sha256: str = "",
        runtime_state_root: str | Path | None = None,
        timeout: float = 300.0,
        require_worker_binding: bool = False,
        transport_config: Mapping[str, Any] | None = None,
    ) -> None:
        provider = str(model_provider or "").strip()
        selected_model = str(model_id or "").strip()
        selected_executable, expected_hash = _validate_runtime_binding(
            executable, expected_artifact_sha256
        )
        if not provider or not selected_model:
            raise OpenSWEExternalIntelligenceError("OPEN_SWE_MODEL_BINDING_REQUIRED")
        self.provider_id = provider
        self.model_id = selected_model
        self.model = f"{provider}/{selected_model}"
        self.executable = selected_executable
        self.expected_artifact_sha256 = expected_hash
        self.runtime_state_root = (
            Path(
                runtime_state_root
                if runtime_state_root is not None
                else _default_runtime_state_root()
            )
            .expanduser()
            .resolve()
        )
        self.timeout = float(timeout)
        self.transport_config = _normalize_transport_config(provider, transport_config)
        self._require_worker_binding = bool(require_worker_binding)
        self._bound_worker: dict[str, Any] | None = None
        self._bound_worker_sha256 = ""

    def bind_worker(self, selected_worker: Mapping[str, Any]) -> "OpenSWEWorkerTransport":
        provider = str(selected_worker.get("provider") or "").strip()
        model = str(selected_worker.get("model") or "").strip()
        selected_model = model.split("/", 1)[1] if "/" in model else model
        selected_provider = model.split("/", 1)[0] if "/" in model else provider
        if selected_provider != self.provider_id or selected_model != self.model_id:
            raise FanoutError("MODEL_SUBSTITUTION_FORBIDDEN")
        worker = dict(selected_worker)
        if self._bound_worker is not None and worker != self._bound_worker:
            raise FanoutError("WORKER_IDENTITY_SUBSTITUTION_FORBIDDEN")
        self._bound_worker = worker
        self._bound_worker_sha256 = _sha256(_canonical_json(worker))
        return self

    def _operation_id(
        self,
        operation: str,
        *,
        prompt: str,
        artifact_path: str,
        workspace_path: str,
        session_id: str,
    ) -> str:
        artifact = Path(artifact_path).expanduser().resolve() if artifact_path else None
        artifact_sha = (
            _sha256(artifact.read_bytes()) if artifact is not None and artifact.is_file() else ""
        )
        return _sha256(
            _canonical_json({
                "operation": operation,
                "workspace": str(Path(workspace_path).expanduser().resolve()),
                "prompt_sha256": _sha256(prompt),
                "artifact_sha256": artifact_sha,
                "session_id": session_id,
                "worker_identity_sha256": self._bound_worker_sha256,
            })
        )

    def prepare_operation_id(
        self,
        operation: str,
        *,
        prompt: str,
        artifact_path: str,
        workspace_path: str,
        session_id: str,
    ) -> str:
        operation_id = self._operation_id(
            operation,
            prompt=prompt,
            artifact_path=artifact_path,
            workspace_path=workspace_path,
            session_id=session_id,
        )
        return operation_id

    def _local_failure(
        self,
        status: str,
        *,
        workspace_path: str,
        process_started: bool = False,
        outcome_unknown: bool = False,
        retry_safe: bool = False,
        error: str = "",
        argv_sha256: str = "",
    ) -> OpenCodeRunResult:
        return OpenCodeRunResult(
            status=status,
            worker_backend="open_swe",
            provider_id=self.provider_id,
            model_id=self.model_id,
            directory=str(Path(workspace_path).expanduser().resolve()),
            argv_sha256=argv_sha256,
            process_started=process_started,
            outcome_unknown=outcome_unknown,
            retry_safe=retry_safe,
            error=error,
            worker_identity_sha256=self._bound_worker_sha256,
        )

    def _request(
        self,
        operation: str,
        *,
        prompt: str = "",
        artifact_path: str = "",
        workspace_path: str,
        session_id: str = "",
        operation_id: str = "",
    ) -> OpenCodeRunResult:
        if session_id and _SESSION_RE.fullmatch(session_id) is None:
            raise FanoutError("INVALID_SESSION_ID")
        if operation == "worker_reconcile" and (
            not isinstance(operation_id, str) or _SHA256_RE.fullmatch(operation_id) is None
        ):
            raise FanoutError("OPERATION_ID_REQUIRED")
        if (
            operation != "worker_reconcile"
            and operation_id != ""
            and (not isinstance(operation_id, str) or _SHA256_RE.fullmatch(operation_id) is None)
        ):
            raise FanoutError("OPERATION_ID_REQUIRED")
        workspace = Path(workspace_path).expanduser().resolve()
        if operation != "worker_reconcile":
            artifact = Path(artifact_path).expanduser().resolve()
            if not workspace.is_dir() or not artifact.is_file():
                return self._local_failure(
                    "OPEN_SWE_EXECUTION_INPUT_INVALID", workspace_path=str(workspace)
                )
            if self._require_worker_binding and self._bound_worker is None:
                return self._local_failure(
                    "OPEN_SWE_WORKER_BINDING_REQUIRED", workspace_path=str(workspace)
                )
        if not self._ensure_runtime_identity():
            return self._local_failure(
                "OPEN_SWE_RUNTIME_IDENTITY_FAILED",
                workspace_path=str(workspace),
                outcome_unknown=operation == "worker_reconcile",
                retry_safe=False,
            )
        if operation == "worker_reconcile":
            pass
        else:
            computed_operation_id = self.prepare_operation_id(
                operation,
                prompt=prompt,
                artifact_path=artifact_path,
                workspace_path=str(workspace),
                session_id=session_id,
            )
            if operation_id and operation_id != computed_operation_id:
                return self._local_failure(
                    "OPEN_SWE_OUTCOME_UNKNOWN",
                    workspace_path=str(workspace),
                    outcome_unknown=True,
                    error="OPERATION_ID_MISMATCH",
                )
            operation_id = computed_operation_id
        payload = {
            "schema": PROTOCOL_REQUEST_SCHEMA,
            "operation": operation,
            "operation_id": operation_id,
            "provider_id": self.provider_id,
            "model_id": self.model_id,
            "runtime_state_root": str(self.runtime_state_root),
            "transport_config": dict(self.transport_config),
            "workspace_path": str(workspace),
            "artifact_path": str(Path(artifact_path).expanduser().resolve())
            if artifact_path
            else "",
            "prompt": prompt,
            "session_id": session_id,
            "worker_identity": self._bound_worker or {},
            "worker_identity_sha256": self._bound_worker_sha256,
        }
        argv_sha256 = _safe_request_hash(payload)
        value, _stderr, process_started, failure = _runtime_call(
            self.executable,
            payload,
            provider_id=self.provider_id,
            timeout=self.timeout,
        )
        if value is None:
            if failure == "runtime_not_found" and operation != "worker_reconcile":
                return self._local_failure(
                    "OPEN_SWE_RUNTIME_NOT_FOUND",
                    workspace_path=str(workspace),
                    retry_safe=True,
                    error=failure,
                    argv_sha256=argv_sha256,
                )
            return self._local_failure(
                "OPEN_SWE_OUTCOME_UNKNOWN",
                workspace_path=str(workspace),
                process_started=process_started,
                outcome_unknown=True,
                retry_safe=False,
                error=failure,
                argv_sha256=argv_sha256,
            )
        if value.get("kind") != "worker":
            return self._local_failure(
                "OPEN_SWE_OUTCOME_UNKNOWN",
                workspace_path=str(workspace),
                process_started=process_started,
                outcome_unknown=True,
                error="runtime_result_kind_mismatch",
                argv_sha256=argv_sha256,
            )
        returned_operation_id = value.get("operation_id")
        if not isinstance(returned_operation_id, str) or returned_operation_id != operation_id:
            return self._local_failure(
                "OPEN_SWE_OUTCOME_UNKNOWN",
                workspace_path=str(workspace),
                process_started=process_started,
                outcome_unknown=True,
                error="OPERATION_ID_MISMATCH",
                argv_sha256=argv_sha256,
            )
        provider = str(value.get("provider_id") or "")
        model = str(value.get("model_id") or "")
        if provider != self.provider_id or model != self.model_id:
            return self._local_failure(
                "OPEN_SWE_OUTCOME_UNKNOWN",
                workspace_path=str(workspace),
                process_started=process_started,
                outcome_unknown=True,
                error="MODEL_ATTESTATION_MISMATCH",
                argv_sha256=argv_sha256,
            )
        worker_hash = str(value.get("worker_identity_sha256") or "")
        if self._bound_worker_sha256 and worker_hash != self._bound_worker_sha256:
            return self._local_failure(
                "OPEN_SWE_OUTCOME_UNKNOWN",
                workspace_path=str(workspace),
                process_started=process_started,
                outcome_unknown=True,
                error="WORKER_IDENTITY_ATTESTATION_MISMATCH",
                argv_sha256=argv_sha256,
            )
        evidence_paths_raw = value.get("diagnosis_evidence_paths") or []
        evidence_paths = (
            tuple(str(path) for path in evidence_paths_raw)
            if isinstance(evidence_paths_raw, list)
            else ()
        )
        effect_recovery = None
        if (
            operation == "worker_reconcile"
            and str(value.get("status") or "") == "OPEN_SWE_OUTCOME_UNKNOWN"
        ):
            effect_recovery = _inspect_effect_recovery(
                runtime_state_root=self.runtime_state_root,
                operation_id=operation_id,
                workspace_path=workspace,
                provider_id=provider,
                model_id=model,
                worker_identity_sha256=worker_hash,
            )
        return OpenCodeRunResult(
            status=str(value.get("status") or "OPEN_SWE_OUTCOME_UNKNOWN"),
            worker_backend="open_swe",
            session_id=str(value.get("session_id") or ""),
            response_text=str(value.get("response_text") or ""),
            provider_id=provider,
            model_id=model,
            directory=str(value.get("directory") or workspace),
            version=str(value.get("version") or ""),
            stdout_sha256=str(value.get("stdout_sha256") or ""),
            stderr_sha256=str(value.get("stderr_sha256") or ""),
            export_sha256=str(value.get("export_sha256") or ""),
            argv_sha256=argv_sha256,
            process_started=bool(value.get("process_started", process_started)),
            outcome_unknown=bool(value.get("outcome_unknown")),
            retry_safe=bool(value.get("retry_safe")),
            error=str(value.get("error") or ""),
            diagnosis_status=str(value.get("diagnosis_status") or ""),
            diagnosis_sha256=str(value.get("diagnosis_sha256") or ""),
            diagnosis_evidence_paths=evidence_paths,
            repair_admitted=bool(value.get("repair_admitted")),
            repair_phase_count=int(value.get("repair_phase_count") or 0),
            worker_identity_sha256=worker_hash,
            operation_id=operation_id,
            effect_recovery=effect_recovery,
        )

    def _ensure_runtime_identity(self) -> bool:
        payload = {
            "schema": PROTOCOL_REQUEST_SCHEMA,
            "operation": "identity",
            "provider_id": self.provider_id,
            "model_id": self.model_id,
            "runtime_state_root": str(self.runtime_state_root),
            "transport_config": dict(self.transport_config),
        }
        value, _stderr, _started, _failure = _runtime_call(
            self.executable, payload, provider_id=self.provider_id, timeout=self.timeout
        )
        if value is None:
            return False
        try:
            _validate_runtime_identity(value, self.expected_artifact_sha256)
        except OpenSWEExternalIntelligenceError:
            return False
        return True

    def run_new(
        self, *, prompt: str, artifact_path: str, workspace_path: str, operation_id: str = ""
    ) -> OpenCodeRunResult:
        return self._request(
            "worker_run",
            prompt=prompt,
            artifact_path=artifact_path,
            workspace_path=workspace_path,
            operation_id=operation_id,
        )

    def continue_session(
        self,
        *,
        session_id: str,
        prompt: str,
        artifact_path: str,
        workspace_path: str,
        operation_id: str = "",
    ) -> OpenCodeRunResult:
        return self._request(
            "worker_continue",
            session_id=session_id,
            prompt=prompt,
            artifact_path=artifact_path,
            workspace_path=workspace_path,
            operation_id=operation_id,
        )

    def reconcile_workspace(
        self, *, workspace_path: str, operation_id: str = ""
    ) -> OpenCodeRunResult:
        return self._request(
            "worker_reconcile", workspace_path=workspace_path, operation_id=operation_id
        )


__all__ = [
    "DIAGNOSIS_TOOL_SURFACE",
    "FORBIDDEN_SEMANTIC_TOOLS",
    "OpenSWEExternalIntelligenceError",
    "OpenSWEExternalIntelligenceTransport",
    "OpenSWEWorkerTransport",
    "PROTOCOL_REQUEST_SCHEMA",
    "PROTOCOL_RESULT_SCHEMA",
    "READ_ONLY_SEMANTIC_TOOLS",
    "REPAIR_TOOL_SURFACE",
]
