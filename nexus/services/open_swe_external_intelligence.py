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
EXPOSURE_RECEIPT_SCHEMA = "nexus.open_swe_runtime.execution_exposure_receipt.v1"
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


def _default_runtime_state_root() -> Path:
    return Path.home() / ".local" / "state" / "nexus" / "open_swe_runtime"


def _runtime_env(provider_id: str) -> dict[str, str]:
    """Pass only process/runtime essentials plus the selected provider credential.

    GitHub/GH credentials and arbitrary controller environment are deliberately
    absent.  The runtime graph has no environment-reading tool surface.
    """

    allowed = [*_SYSTEM_ENV_ALLOWLIST, *_PROVIDER_ENV_ALLOWLIST.get(provider_id, ())]
    return {name: os.environ[name] for name in allowed if name in os.environ}


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
    effect_authorization = payload.get("effect_authorization")
    tool_projection = payload.get("tool_projection_manifest")
    safe = {
        "schema": payload.get("schema"),
        "operation": payload.get("operation"),
        "operation_id": payload.get("operation_id"),
        "attempt_id": payload.get("attempt_id"),
        "provider_id": payload.get("provider_id"),
        "model_id": payload.get("model_id"),
        "workspace_path": payload.get("workspace_path"),
        "repository_root": payload.get("repository_root"),
        "session_id": payload.get("session_id"),
        "worker_identity_sha256": payload.get("worker_identity_sha256"),
        "effect_authorization_hash": (
            effect_authorization.get("authorization_hash")
            if isinstance(effect_authorization, Mapping)
            else None
        ),
        "tool_projection_hash": (
            tool_projection.get("projection_hash") if isinstance(tool_projection, Mapping) else None
        ),
    }
    return _sha256(_canonical_json(safe))


def _validate_execution_exposure_receipt(
    receipt: Any,
    *,
    operation_id: str,
    provider_id: str,
    effect_authorization: Mapping[str, Any],
    tool_projection_manifest: Mapping[str, Any],
) -> dict[str, Any]:
    if not isinstance(receipt, Mapping):
        raise OpenSWEExternalIntelligenceError("OPEN_SWE_EXPOSURE_RECEIPT_REQUIRED")
    expected_fields = {
        "schema",
        "operation_id",
        "attempt_id",
        "provider",
        "backend_id",
        "authorization_hash",
        "projection_hash",
        "actual_exposed_tools",
        "phase_tool_surfaces",
        "authority_kind",
        "exposure_hash",
    }
    if set(receipt) != expected_fields:
        raise OpenSWEExternalIntelligenceError("OPEN_SWE_EXPOSURE_RECEIPT_FIELDS_INVALID")
    if (
        receipt.get("schema") != EXPOSURE_RECEIPT_SCHEMA
        or receipt.get("authority_kind") != "DERIVED_EXPOSURE_EVIDENCE_ONLY"
        or receipt.get("operation_id") != operation_id
        or receipt.get("attempt_id") != effect_authorization.get("attempt_id")
        or receipt.get("provider") != provider_id
        or receipt.get("backend_id") != tool_projection_manifest.get("backend_id")
        or receipt.get("authorization_hash") != effect_authorization.get("authorization_hash")
        or receipt.get("projection_hash") != tool_projection_manifest.get("projection_hash")
    ):
        raise OpenSWEExternalIntelligenceError("OPEN_SWE_EXPOSURE_RECEIPT_IDENTITY_INVALID")

    selected_tools_raw = tool_projection_manifest.get("selected_tools")
    actual_tools_raw = receipt.get("actual_exposed_tools")
    phase_surfaces_raw = receipt.get("phase_tool_surfaces")
    if (
        not isinstance(selected_tools_raw, list)
        or not isinstance(actual_tools_raw, list)
        or not isinstance(phase_surfaces_raw, Mapping)
        or any(not isinstance(item, str) or not item for item in selected_tools_raw)
        or any(not isinstance(item, str) or not item for item in actual_tools_raw)
    ):
        raise OpenSWEExternalIntelligenceError("OPEN_SWE_EXPOSURE_RECEIPT_TOOLS_INVALID")
    selected_tools = set(selected_tools_raw)
    actual_tools = tuple(sorted(set(actual_tools_raw)))
    if list(actual_tools) != actual_tools_raw or not set(actual_tools).issubset(selected_tools):
        raise OpenSWEExternalIntelligenceError("OPEN_SWE_EXPOSURE_RECEIPT_TOOLS_INVALID")

    observed_union: set[str] = set()
    normalized_phases: dict[str, list[str]] = {}
    for raw_phase, raw_tools in sorted(phase_surfaces_raw.items()):
        if (
            not isinstance(raw_phase, str)
            or not raw_phase
            or not isinstance(raw_tools, list)
            or any(not isinstance(item, str) or not item for item in raw_tools)
        ):
            raise OpenSWEExternalIntelligenceError("OPEN_SWE_EXPOSURE_RECEIPT_TOOLS_INVALID")
        normalized = sorted(set(raw_tools))
        if normalized != raw_tools or not set(normalized).issubset(selected_tools):
            raise OpenSWEExternalIntelligenceError("OPEN_SWE_EXPOSURE_RECEIPT_TOOLS_INVALID")
        normalized_phases[raw_phase] = normalized
        observed_union.update(normalized)
    if sorted(observed_union) != list(actual_tools):
        raise OpenSWEExternalIntelligenceError("OPEN_SWE_EXPOSURE_RECEIPT_TOOLS_INVALID")

    material = dict(receipt)
    observed_hash = material.pop("exposure_hash")
    if (
        not isinstance(observed_hash, str)
        or _SHA256_RE.fullmatch(observed_hash) is None
        or _sha256(_canonical_json(material)) != observed_hash
    ):
        raise OpenSWEExternalIntelligenceError("OPEN_SWE_EXPOSURE_RECEIPT_HASH_INVALID")
    return dict(receipt)


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
        effect_authorization_hash: str = "",
        tool_projection_hash: str = "",
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
            effect_authorization_hash=effect_authorization_hash,
            tool_projection_hash=tool_projection_hash,
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
        effect_authorization: Mapping[str, Any] | None = None,
        tool_projection_manifest: Mapping[str, Any] | None = None,
    ) -> OpenCodeRunResult:
        if session_id and _SESSION_RE.fullmatch(session_id) is None:
            raise FanoutError("INVALID_SESSION_ID")
        effect_requested = effect_authorization is not None or tool_projection_manifest is not None
        if effect_requested and (
            not isinstance(effect_authorization, Mapping)
            or not isinstance(tool_projection_manifest, Mapping)
        ):
            raise FanoutError("EFFECT_AUTHORIZATION_PROJECTION_PAIR_REQUIRED")
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
        if effect_requested and not operation_id:
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

        effect_authorization_hash = ""
        tool_projection_hash = ""
        attempt_id = ""
        if effect_requested:
            assert isinstance(effect_authorization, Mapping)
            assert isinstance(tool_projection_manifest, Mapping)
            if effect_authorization.get("operation_id") != operation_id:
                raise FanoutError("EFFECT_AUTHORIZATION_OPERATION_MISMATCH")
            attempt_id = str(effect_authorization.get("attempt_id") or "").strip()
            if not attempt_id:
                raise FanoutError("EFFECT_AUTHORIZATION_ATTEMPT_ID_REQUIRED")
            if tool_projection_manifest.get("operation_id") != operation_id:
                raise FanoutError("TOOL_PROJECTION_OPERATION_MISMATCH")
            if tool_projection_manifest.get("attempt_id") != attempt_id:
                raise FanoutError("TOOL_PROJECTION_ATTEMPT_MISMATCH")
            if tool_projection_manifest.get("provider") != self.provider_id:
                raise FanoutError("TOOL_PROJECTION_PROVIDER_MISMATCH")
            effect_authorization_hash = str(effect_authorization.get("authorization_hash") or "")
            tool_projection_hash = str(tool_projection_manifest.get("projection_hash") or "")

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
        if effect_requested:
            payload.update({
                "attempt_id": attempt_id,
                "effect_authorization": dict(effect_authorization),
                "tool_projection_manifest": dict(tool_projection_manifest),
            })
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
        exposure_receipt: dict[str, Any] | None = None
        if effect_requested:
            returned_authorization_hash = str(value.get("effect_authorization_hash") or "")
            returned_projection_hash = str(value.get("tool_projection_hash") or "")
            completed = str(value.get("status") or "") == "COMPLETED"
            if (
                (
                    returned_authorization_hash
                    and returned_authorization_hash != effect_authorization_hash
                )
                or (returned_projection_hash and returned_projection_hash != tool_projection_hash)
                or (
                    completed
                    and (
                        returned_authorization_hash != effect_authorization_hash
                        or returned_projection_hash != tool_projection_hash
                    )
                )
            ):
                return self._local_failure(
                    "OPEN_SWE_OUTCOME_UNKNOWN",
                    workspace_path=str(workspace),
                    process_started=bool(value.get("process_started", process_started)),
                    outcome_unknown=True,
                    error="EFFECT_PROJECTION_ATTESTATION_MISMATCH",
                    argv_sha256=argv_sha256,
                    effect_authorization_hash=effect_authorization_hash,
                    tool_projection_hash=tool_projection_hash,
                )
            raw_exposure_receipt = value.get("execution_exposure_receipt")
            if completed or raw_exposure_receipt is not None:
                try:
                    exposure_receipt = _validate_execution_exposure_receipt(
                        raw_exposure_receipt,
                        operation_id=operation_id,
                        provider_id=self.provider_id,
                        effect_authorization=effect_authorization,
                        tool_projection_manifest=tool_projection_manifest,
                    )
                except OpenSWEExternalIntelligenceError as exc:
                    return self._local_failure(
                        "OPEN_SWE_OUTCOME_UNKNOWN",
                        workspace_path=str(workspace),
                        process_started=bool(value.get("process_started", process_started)),
                        outcome_unknown=True,
                        error=str(exc),
                        argv_sha256=argv_sha256,
                        effect_authorization_hash=effect_authorization_hash,
                        tool_projection_hash=tool_projection_hash,
                    )

        evidence_paths_raw = value.get("diagnosis_evidence_paths") or []
        evidence_paths = (
            tuple(str(path) for path in evidence_paths_raw)
            if isinstance(evidence_paths_raw, list)
            else ()
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
            effect_authorization_hash=effect_authorization_hash,
            tool_projection_hash=tool_projection_hash,
            execution_exposure_receipt=exposure_receipt,
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
        self,
        *,
        prompt: str,
        artifact_path: str,
        workspace_path: str,
        operation_id: str = "",
        effect_authorization: Mapping[str, Any] | None = None,
        tool_projection_manifest: Mapping[str, Any] | None = None,
    ) -> OpenCodeRunResult:
        return self._request(
            "worker_run",
            prompt=prompt,
            artifact_path=artifact_path,
            workspace_path=workspace_path,
            operation_id=operation_id,
            effect_authorization=effect_authorization,
            tool_projection_manifest=tool_projection_manifest,
        )

    def continue_session(
        self,
        *,
        session_id: str,
        prompt: str,
        artifact_path: str,
        workspace_path: str,
        operation_id: str = "",
        effect_authorization: Mapping[str, Any] | None = None,
        tool_projection_manifest: Mapping[str, Any] | None = None,
    ) -> OpenCodeRunResult:
        return self._request(
            "worker_continue",
            session_id=session_id,
            prompt=prompt,
            artifact_path=artifact_path,
            workspace_path=workspace_path,
            operation_id=operation_id,
            effect_authorization=effect_authorization,
            tool_projection_manifest=tool_projection_manifest,
        )

    def reconcile_workspace(
        self,
        *,
        workspace_path: str,
        operation_id: str = "",
        effect_authorization: Mapping[str, Any] | None = None,
        tool_projection_manifest: Mapping[str, Any] | None = None,
    ) -> OpenCodeRunResult:
        return self._request(
            "worker_reconcile",
            workspace_path=workspace_path,
            operation_id=operation_id,
            effect_authorization=effect_authorization,
            tool_projection_manifest=tool_projection_manifest,
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
