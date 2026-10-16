"""Probe-evidence, job-storage and decode helpers of ``UnifiedMCPGateway``.

Big-file split G4 (Issue #2445). The 19 methods of ``_AssistProbeMixin`` were moved out
of ``nexus/orchestrator/unified_mcp_gateway.py``; their source lines are verbatim, except
that the gateway-defined names ``GatewayInputError``, ``_text`` and ``UnifiedMCPGateway``
are resolved at call time through ``_gateway()``. ``UnifiedMCPGateway`` inherits the
mixin, so every method keeps its name, descriptor kind and signature on the gateway class.
"""

from __future__ import annotations

import hashlib
import importlib
import json
import os
import re
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Mapping, Optional

from nexus.services.unified_runtime import LOCAL_ONLY_PROVIDERS, ONLINE_CLI_SPEC_REGISTRY

if TYPE_CHECKING:
    from nexus.orchestrator.self_hosted_task_service import SelfHostedTaskService


def _gateway():
    # Late binding: the gateway imports this module at its top level, so its own
    # names are only resolved once a method runs.
    return importlib.import_module("nexus.orchestrator.unified_mcp_gateway")


class _AssistProbeMixin:
    """Mixin base of ``UnifiedMCPGateway``; never instantiated on its own."""

    if TYPE_CHECKING:  # provided by UnifiedMCPGateway
        service: SelfHostedTaskService

        @staticmethod
        def _hash_file(path: Path) -> str: ...

    # fmt: off
    def _assist_root(self) -> Path:
        configured = getattr(self.service, "state_dir", None)
        root = Path(configured).expanduser().resolve() if configured else Path("/tmp/nexus-mcp-gateway-assist-jobs")
        root = root / "assisted_provider_jobs"
        root.mkdir(parents=True, exist_ok=True)
        return root

    def _assist_path(self, task_id: str) -> Path:
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}", str(task_id)):
            raise _gateway().GatewayInputError("task_id must be a stable bounded slug")
        return self._assist_root() / f"{task_id}.json"

    def _probe_evidence_root(self) -> Path:
        root = self._assist_root() / "probe_evidence"
        root.mkdir(parents=True, exist_ok=True)
        return root

    def _probe_evidence_read_root(self) -> Path:
        configured = getattr(self.service, "state_dir", None)
        base = Path(configured).expanduser().resolve() if configured else Path("/tmp/nexus-mcp-gateway-assist-jobs")
        return base / "assisted_provider_jobs" / "probe_evidence"

    def _assist_read_root(self) -> Path:
        """Return the evidence root without creating any filesystem state."""
        configured = getattr(self.service, "state_dir", None)
        base = Path(configured).expanduser().resolve() if configured else Path("/tmp/nexus-mcp-gateway-assist-jobs")
        return base / "assisted_provider_jobs"

    @staticmethod
    def _canonical_hash(value: Any) -> str:
        return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()

    @staticmethod
    def _provider_requires_authentication(provider: str) -> bool:
        key = str(provider or "").strip().lower()
        return key in ONLINE_CLI_SPEC_REGISTRY and key not in LOCAL_ONLY_PROVIDERS

    def _provider_execution_ready(
        self,
        preflight: Mapping[str, Any],
        *,
        provider: str,
        model: Optional[str] = None,
    ) -> tuple[bool, Optional[str]]:
        if preflight.get("provider") != provider:
            return False, "WORKER_PREFLIGHT_PROVIDER_MISMATCH"
        if model is not None and preflight.get("requested_model") != model:
            return False, "WORKER_PREFLIGHT_REQUESTED_MODEL_MISMATCH"
        if model is not None and preflight.get("resolved_model") != model:
            return False, "WORKER_PREFLIGHT_RESOLVED_MODEL_MISMATCH"
        if str(preflight.get("status") or "") != "VERSION_VERIFIED":
            return False, str(preflight.get("blocker") or "WORKER_PREFLIGHT_FAILED")
        blocker = str(preflight.get("blocker") or "")
        if blocker in {"MODEL_PROBE_REQUIRED", "MODEL_PROBE_ASYNC_REQUIRED"}:
            return False, blocker
        if preflight.get("readiness_status") != "MODEL_VERIFIED" or preflight.get("execution_ready") is not True:
            return False, "MODEL_PROBE_REQUIRED"
        if preflight.get("model_reachable") is not True or preflight.get("requested_model_verified") is not True:
            return False, "MODEL_PROBE_REQUIRED"
        required_identity = (
            "probe_evidence_hash",
            "binary_path",
            "binary_sha256",
            "cli_version_sha256",
            "probe_expires_at",
        )
        if any(not preflight.get(field) for field in required_identity):
            return False, "MODEL_PROBE_REQUIRED"
        if self._provider_requires_authentication(provider):
            if (
                preflight.get("authenticated") is not True
                or preflight.get("authentication_evidence") != "successful_exact_model_probe"
            ):
                return False, "PROVIDER_AUTHENTICATION_REQUIRED"
        return True, None

    def _assist_read(self, task_id: str) -> Optional[dict[str, Any]]:
        path = self._assist_path(task_id)
        if not path.exists():
            return None
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        return value if isinstance(value, dict) else None

    def _assist_read_snapshot(self, task_id: str) -> Optional[dict[str, Any]]:
        """Read a persisted job without creating the state root."""
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}", str(task_id)):
            return None
        path = self._assist_read_root() / f"{task_id}.json"
        if not path.exists():
            return None
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        return value if isinstance(value, dict) else None

    def _assist_write(self, value: Mapping[str, Any]) -> dict[str, Any]:
        task_id = _gateway()._text(value.get("task_id"), "task_id")
        path = self._assist_path(task_id)
        serialized = json.dumps(dict(value), sort_keys=True, ensure_ascii=False, indent=2) + "\n"
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            handle.write(serialized)
            temporary = Path(handle.name)
        os.replace(temporary, path)
        return dict(value)

    @classmethod
    def _probe_evidence_identity(cls, values: Mapping[str, Any]) -> str:
        identity = {
            key: values.get(key)
            for key in (
                "provider",
                "requested_model",
                "resolved_model",
                "binary_path",
                "binary_sha256",
                "cli_version",
            )
        }
        return cls._canonical_hash(identity)

    def _write_probe_evidence(self, job: Mapping[str, Any]) -> Optional[dict[str, Any]]:
        if job.get("job_kind") != "model_probe" or job.get("status") != "COMPLETED":
            return None
        required = (
            "task_id",
            "job_id",
            "provider",
            "requested_model",
            "resolved_model",
            "binary_path",
            "binary_sha256",
            "cli_version",
            "cli_version_sha256",
            "command_hash",
            "probe_prompt_hash",
            "probe_semantics_hash",
            "action_request_hash",
            "action_id",
            "attempt_id",
            "result",
            "output_schema",
            "finished_at",
            "stdout_sha256",
            "stderr_sha256",
            "stdout_bytes",
            "stderr_bytes",
            "filesystem_delta",
            "process_cleanup",
            "durable_exit_marker",
            "stream_flush_status",
            "workspace_mode",
            "model_response_provenance",
            "submitted_at",
            "started_at",
        )
        if any(job.get(key) in (None, "") for key in required) or job.get("exit_code") != 0:
            return None
        if (
            job.get("model_response_verified") is not True
            or job.get("durable_exit_marker") is not True
            or job.get("process_cleanup") is not True
            or job.get("filesystem_delta") != {"created": [], "removed": [], "changed": []}
            or job.get("schema_error") not in (None, "")
            or job.get("stream_flush_status") != "FLUSHED"
            or job.get("workspace_mode") != "isolated"
            or not self._probe_command_identity_valid(job)
        ):
            return None
        remote_authentication = self._provider_requires_authentication(str(job.get("provider") or ""))
        payload = {
            key: job.get(key)
            for key in required
            if key not in {"result", "output_schema"}
        }
        payload.update({
            "schema": "nexus.model_probe_evidence.v1",
            "status": "SUCCESS",
            "model_response_verified": True,
            # Authentication is inferred only from a successful exact remote
            # model response, never from provider metadata or --version.
            "authenticated": remote_authentication,
            "authentication_evidence": (
                "successful_exact_model_probe"
                if remote_authentication
                else "local_provider_no_auth_required"
            ),
            "exit_code": 0,
            "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
        })
        payload["output_schema_hash"] = self._canonical_hash(job.get("output_schema"))
        payload["result_hash"] = self._canonical_hash(job.get("result"))
        trust = {key: value for key, value in payload.items() if key != "evidence_hash"}
        payload["evidence_hash"] = self._canonical_hash(trust)
        identity = self._probe_evidence_identity(payload)
        path = self._probe_evidence_root() / f"{identity}.json"
        serialized = json.dumps(payload, sort_keys=True, ensure_ascii=False, indent=2) + "\n"
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            handle.write(serialized)
            temporary = Path(handle.name)
        os.replace(temporary, path)
        return payload

    def _read_probe_evidence(self, *, provider: str, requested_model: str, resolved_model: str, executable: str, binary_sha256: str, cli_version: str) -> Optional[dict[str, Any]]:
        root = self._probe_evidence_read_root()
        if not root.exists():
            return None
        identity_values = {
            "provider": provider,
            "requested_model": requested_model,
            "resolved_model": resolved_model,
            "binary_path": executable,
            "binary_sha256": binary_sha256,
            "cli_version": cli_version,
        }
        path = root / f"{self._probe_evidence_identity(identity_values)}.json"
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            expires_at = datetime.fromisoformat(str(value.get("expires_at")))
            finished_at = datetime.fromisoformat(str(value.get("finished_at")))
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            return None
        now = datetime.now(timezone.utc)
        if expires_at.tzinfo is None or finished_at.tzinfo is None:
            return None
        if (
            finished_at > now + timedelta(minutes=1)
            or expires_at <= now
            or expires_at <= finished_at
            or expires_at - finished_at > timedelta(hours=1, minutes=1)
        ):
            return None
        if value.get("status") != "SUCCESS" or value.get("model_response_verified") is not True:
            return None
        if any(value.get(key) != expected for key, expected in identity_values.items()):
            return None
        if value.get("cli_version_sha256") != hashlib.sha256(cli_version.encode("utf-8")).hexdigest():
            return None
        digest = value.get("evidence_hash")
        trust = {key: item for key, item in value.items() if key != "evidence_hash"}
        if not digest or self._canonical_hash(trust) != digest:
            return None
        job = self._assist_read_snapshot(str(value.get("task_id")))
        matched_fields = (
            "job_id",
            "action_id",
            "attempt_id",
            "command_hash",
            "probe_prompt_hash",
            "probe_semantics_hash",
            "action_request_hash",
            "submitted_at",
            "started_at",
            "provider",
            "requested_model",
            "resolved_model",
            "binary_path",
            "binary_sha256",
            "cli_version",
            "cli_version_sha256",
            "finished_at",
            "stdout_sha256",
            "stderr_sha256",
            "stdout_bytes",
            "stderr_bytes",
            "filesystem_delta",
            "process_cleanup",
            "durable_exit_marker",
            "model_response_verified",
            "model_response_provenance",
            "stream_flush_status",
            "workspace_mode",
        )
        if job is None or any(job.get(key) != value.get(key) for key in matched_fields):
            return None
        if (
            job.get("status") != "COMPLETED"
            or job.get("exit_code") != 0
            or job.get("durable_exit_marker") is not True
            or job.get("process_cleanup") is not True
            or job.get("model_response_verified") is not True
            or not job.get("model_response_provenance")
            or job.get("filesystem_delta") != {"created": [], "removed": [], "changed": []}
            or value.get("exit_code") != 0
            or not self._probe_command_identity_valid(job)
            or value.get("output_schema_hash") != self._canonical_hash(job.get("output_schema"))
            or value.get("result_hash") != self._canonical_hash(job.get("result"))
        ):
            return None
        for name in ("stdout", "stderr"):
            artifact = Path(str(job.get(f"{name}_artifact") or ""))
            try:
                if (
                    not artifact.is_file()
                    or artifact.resolve().parent != self._assist_read_root().resolve()
                    or self._hash_file(artifact) != job.get(f"{name}_sha256")
                    or artifact.stat().st_size != job.get(f"{name}_bytes")
                ):
                    return None
            except OSError:
                return None
        if job.get("schema_error") not in (None, "") or job.get("stream_flush_status") != "FLUSHED":
            return None
        if self._provider_requires_authentication(provider):
            if value.get("authenticated") is not True or value.get("authentication_evidence") != "successful_exact_model_probe":
                return None
        return value

    @classmethod
    def _probe_command_identity_valid(cls, job: Mapping[str, Any]) -> bool:
        command = job.get("command")
        if not isinstance(command, list) or not command or not all(isinstance(item, str) and item for item in command):
            return False
        if command[0] != job.get("binary_path"):
            return False
        command_hash = hashlib.sha256(
            json.dumps(command, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        if command_hash != job.get("command_hash"):
            return False
        provider = str(job.get("provider") or "")
        expected_model = str(job.get("resolved_model") or "")
        try:
            if provider in {"cline", "agy", "opencode", "mimo", "grok"}:
                model_value = command[command.index("--model") + 1]
            elif provider in {"codex", "gemini"}:
                model_value = command[command.index("-m") + 1]
            elif provider == "ollama":
                model_value = command[2]
            else:
                return False
            if model_value != expected_model:
                return False
            if provider == "agy":
                prompt = command[command.index("--prompt") + 1]
            elif provider == "gemini":
                prompt = command[command.index("-p") + 1]
            else:
                prompt = command[-1]
        except (ValueError, IndexError):
            return False
        return cls._canonical_hash(prompt) == job.get("probe_prompt_hash")

    @staticmethod
    def _decode_model_probe_payload(text: str, provider: str, resolved_model: str) -> tuple[Optional[dict[str, Any]], Optional[str]]:
        """Return only a model-originated JSON payload, never transport metadata."""

        def decode_document(
            raw: str, *, allow_single_json_fence: bool = False
        ) -> Optional[dict[str, Any]]:
            if not isinstance(raw, str):
                return None
            candidate = raw.strip()
            if allow_single_json_fence:
                if candidate.startswith("```json\n") and candidate.endswith("\n```"):
                    candidate = candidate[len("```json\n") : -len("\n```")].strip()
                elif candidate.startswith("```") or candidate.endswith("```"):
                    return None
            try:
                value = json.loads(candidate)
            except (json.JSONDecodeError, TypeError):
                return None
            return value if isinstance(value, dict) else None

        stripped = text.strip()
        direct = decode_document(stripped)
        transport_types = {
            "run_start",
            "run_result",
            "item.started",
            "item.completed",
            "agent_message",
            "thread.started",
            "turn.started",
            "turn.completed",
        }
        if provider == "agy" and direct is not None:
            if str(direct.get("status") or "").upper() != "SUCCESS":
                return None, None
            response = direct.get("response")
            if isinstance(response, Mapping):
                return dict(response), "agy_json_envelope"
            if isinstance(response, str):
                payload = decode_document(response, allow_single_json_fence=True)
                if payload is not None:
                    return payload, "agy_json_envelope"
            return None, None
        if provider not in {"cline", "codex", "agy"} and direct is not None and direct.get("type") not in transport_types:
            return direct, "direct_json_document"

        events: list[dict[str, Any]] = []
        for line in text.splitlines():
            value = decode_document(line)
            if value is not None:
                events.append(value)
        if provider == "codex":
            event_types = [str(event.get("type") or "") for event in events]
            try:
                thread_index = event_types.index("thread.started")
                turn_index = event_types.index("turn.started", thread_index + 1)
                completed_index = event_types.index("turn.completed", turn_index + 1)
            except ValueError:
                return None, None
            for event in reversed(events[turn_index + 1 : completed_index]):
                if event.get("type") != "item.completed":
                    continue
                item = event.get("item") if isinstance(event.get("item"), Mapping) else event
                if item.get("type") != "agent_message" or not isinstance(item.get("text"), str):  # pyright: ignore[reportOptionalMemberAccess]
                    continue
                payload = decode_document(item["text"])  # pyright: ignore[reportOptionalSubscript]
                if payload is not None:
                    return payload, "codex_jsonl_sequence"
            return None, None
        if provider == "cline":
            start_indices = [
                index
                for index, event in enumerate(events)
                if (
                event.get("type") == "run_start"
                and event.get("providerId") == "cline"
                and event.get("modelId") == resolved_model
                )
            ]
            if not start_indices:
                return None, None
            for event in reversed(events[start_indices[-1] + 1 :]):
                if event.get("type") != "run_result" or str(event.get("finishReason") or "").lower() == "error":
                    continue
                model = event.get("model") if isinstance(event.get("model"), Mapping) else {}
                if (
                    str(model.get("provider") or "") != "cline"  # pyright: ignore[reportOptionalMemberAccess]
                    or str(model.get("id") or "") != resolved_model  # pyright: ignore[reportOptionalMemberAccess]
                    or not isinstance(event.get("text"), str)
                ):
                    continue
                payload = decode_document(event["text"])
                if payload is not None:
                    return payload, "cline_run_result"
            return None, None
        return None, None

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
                # Codex JSONL wraps the model payload in an agent_message
                # event whose text field is itself JSON.  Decode that inner
                # value instead of treating the transport envelope as the
                # probe result.
                if provider == "codex" and value.get("type") == "agent_message" and isinstance(value.get("text"), str):
                    nested = _gateway().UnifiedMCPGateway._decode_assist_payload(value["text"], provider, require_patch=require_patch)
                    if nested is not None:
                        return nested
                if provider == "codex" and isinstance(value.get("item"), Mapping):
                    nested = visit(value["item"])
                    if nested is not None:
                        return nested
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
                        found = _gateway().UnifiedMCPGateway._decode_assist_payload(nested, provider, require_patch=require_patch)
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
                snapshot[str(path.relative_to(root))] = _gateway().UnifiedMCPGateway._hash_file(path)
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
            min_length = shape.get("minLength")
            if (
                isinstance(current, str)
                and isinstance(min_length, int)
                and not isinstance(min_length, bool)
                and len(current.strip()) < min_length
            ):
                return f"output_schema_min_length:{path}:{min_length}"
            if isinstance(current, Mapping):
                missing = [str(field) for field in shape.get("required", []) or [] if str(field) not in current]
                if missing:
                    return "output_schema_missing:" + ",".join(f"{path}.{field}" for field in missing)
                properties = shape.get("properties") if isinstance(shape.get("properties"), Mapping) else {}
                for key, child in properties.items():  # pyright: ignore[reportOptionalMemberAccess]
                    if key in current and isinstance(child, Mapping):
                        error = validate(current[key], child, f"{path}.{key}")
                        if error:
                            return error
                if shape.get("additionalProperties") is False:
                    extras = sorted(set(current) - set(properties))  # pyright: ignore[reportArgumentType]
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
    # fmt: on
