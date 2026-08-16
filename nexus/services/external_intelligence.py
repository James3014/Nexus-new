from __future__ import annotations

import hashlib
import json
import os
import signal
import subprocess
import tempfile
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


REQUEST_SCHEMA = "external_intelligence_request.v1"
ATTEMPT_SCHEMA = "external_intelligence_attempt.v1"
ENVELOPE_SCHEMA = "external_execution_envelope.v1"
RECEIPT_SCHEMA = "external_intelligence_receipt.v1"
CONTEXT_SCHEMA = "external_intelligence_context_pack.v1"
CONTROL_CAPSULE_SCHEMA = "control_capsule.v1"
INTAKE_SCHEMA = "external_intelligence_intake.v1"
CLAIM_CEILING = "PRE_IMPLEMENTATION_INTELLIGENCE_ONLY"
DEFAULT_CONTEXT_BUDGET = 200_000
DEFAULT_SOURCE_BUDGET = 64_000
MAX_TEXT = 20_000
MAX_LIST = 64
MODEL_ADAPTATION_KEYS = (
    "role_contract",
    "task_local_invariants",
    "known_failure_guards",
    "execution_strategy",
    "forbidden_inferences",
    "repair_policy",
)


class ExternalIntelligenceError(RuntimeError):
    pass


class IntakeDisposition(str, Enum):
    EXECUTABLE = "EXECUTABLE"
    ACTIVE_ELSEWHERE = "ACTIVE_ELSEWHERE"
    BLOCKED = "BLOCKED"
    NEEDS_RECONCILIATION = "NEEDS_RECONCILIATION"
    NEEDS_CONTRACT_SLICE = "NEEDS_CONTRACT_SLICE"


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha256(value: bytes | str) -> str:
    raw = value.encode("utf-8") if isinstance(value, str) else value
    return hashlib.sha256(raw).hexdigest()


def _bounded_text(value: Any, field: str, *, allow_empty: bool = False) -> str:
    text = str(value or "").strip()
    if (not text and not allow_empty) or len(text) > MAX_TEXT:
        raise ExternalIntelligenceError(f"INVALID_{field.upper()}")
    return text


def _bounded_list(value: Any, field: str, *, max_items: int = MAX_LIST) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, (list, tuple)) or len(value) > max_items:
        raise ExternalIntelligenceError(f"INVALID_{field.upper()}")
    result: list[str] = []
    for item in value:
        text = _bounded_text(item, field)
        result.append(text)
    return result


def _atomic_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = (json.dumps(dict(value), sort_keys=True, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def _utf8_prefix(text: str, budget: int) -> str:
    if budget <= 0:
        return ""
    encoded = text.encode("utf-8")
    if len(encoded) <= budget:
        return text
    clipped = encoded[:budget]
    while clipped:
        try:
            return clipped.decode("utf-8")
        except UnicodeDecodeError as exc:
            clipped = clipped[: exc.start]
    return ""


def _material_identity(record: Mapping[str, Any]) -> dict[str, Any]:
    repository = _bounded_text(record.get("repository"), "repository")
    item_type = _bounded_text(record.get("item_type") or "task", "item_type").lower()
    if item_type not in {"issue", "task"}:
        raise ExternalIntelligenceError("INVALID_ITEM_TYPE")
    item_id = _bounded_text(record.get("item_id"), "item_id")
    revision = _bounded_text(record.get("revision"), "revision")
    main_sha = _bounded_text(record.get("main_sha"), "main_sha")
    task_card_ref = _bounded_text(record.get("task_card_ref"), "task_card_ref", allow_empty=True)
    task_card_hash = _bounded_text(record.get("task_card_hash"), "task_card_hash", allow_empty=True)
    dependency_state = record.get("dependency_state") or {}
    overlap_state = record.get("overlap_state") or {}
    if not isinstance(dependency_state, Mapping) or not isinstance(overlap_state, Mapping):
        raise ExternalIntelligenceError("INVALID_STATE_PROJECTION")
    return {
        "repository": repository,
        "item_type": item_type,
        "item_id": item_id,
        "revision": revision,
        "main_sha": main_sha,
        "task_card_ref": task_card_ref,
        "task_card_hash": task_card_hash,
        "dependency_state": dict(dependency_state),
        "overlap_state": dict(overlap_state),
    }


def normalize_intake(record: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize one Nexus/GitHub work item without granting execution authority."""
    identity = _material_identity(record)
    active_elsewhere = bool(record.get("active_elsewhere"))
    needs_reconciliation = bool(record.get("needs_reconciliation"))
    contract_ready = bool(record.get("contract_ready"))
    ready = bool(record.get("ready"))
    blockers = _bounded_list(record.get("blocked_reasons") or [], "blocked_reasons")

    if active_elsewhere:
        disposition = IntakeDisposition.ACTIVE_ELSEWHERE
        reasons = ["active_elsewhere"]
    elif needs_reconciliation:
        disposition = IntakeDisposition.NEEDS_RECONCILIATION
        reasons = ["needs_reconciliation"]
    elif blockers or not ready:
        disposition = IntakeDisposition.BLOCKED
        reasons = blockers or ["not_ready"]
    elif not contract_ready or not identity["task_card_ref"] or not identity["task_card_hash"]:
        disposition = IntakeDisposition.NEEDS_CONTRACT_SLICE
        reasons = ["contract_slice_required"]
    else:
        disposition = IntakeDisposition.EXECUTABLE
        reasons = []

    identity_hash = _sha256(_canonical_json(identity))
    return {
        "schema": INTAKE_SCHEMA,
        "disposition": disposition.value,
        "reasons": reasons,
        "identity": identity,
        "identity_sha256": identity_hash,
        "claim_ceiling": CLAIM_CEILING,
    }


def build_context_pack(
    sources: Iterable[Mapping[str, Any]],
    *,
    max_bytes: int = DEFAULT_CONTEXT_BUDGET,
    per_source_bytes: int = DEFAULT_SOURCE_BUDGET,
) -> dict[str, Any]:
    """Create a deterministic, provenance-preserving bounded context pack."""
    if max_bytes <= 0 or per_source_bytes <= 0 or per_source_bytes > max_bytes:
        raise ExternalIntelligenceError("INVALID_CONTEXT_BUDGET")
    normalized: list[dict[str, Any]] = []
    for source in sources:
        if not isinstance(source, Mapping):
            raise ExternalIntelligenceError("INVALID_CONTEXT_SOURCE")
        kind = _bounded_text(source.get("kind") or "source", "source_kind")
        ref = _bounded_text(source.get("ref"), "source_ref")
        revision = _bounded_text(source.get("revision"), "source_revision", allow_empty=True)
        provenance = _bounded_text(source.get("provenance") or "unknown", "source_provenance")
        content = str(source.get("content") or "")
        normalized.append({
            "kind": kind,
            "ref": ref,
            "revision": revision,
            "provenance": provenance,
            "content": content,
        })
    normalized.sort(key=lambda item: (item["kind"], item["ref"], item["revision"]))

    remaining = max_bytes
    entries: list[dict[str, Any]] = []
    for source in normalized:
        raw = source["content"].encode("utf-8")
        source_limit = min(per_source_bytes, remaining)
        clipped = _utf8_prefix(source["content"], source_limit)
        clipped_bytes = clipped.encode("utf-8")
        entry = {
            "kind": source["kind"],
            "ref": source["ref"],
            "revision": source["revision"],
            "provenance": source["provenance"],
            "content": clipped,
            "source_sha256": _sha256(raw),
            "included_sha256": _sha256(clipped_bytes),
            "source_bytes": len(raw),
            "included_bytes": len(clipped_bytes),
            "truncated": len(clipped_bytes) < len(raw),
        }
        entries.append(entry)
        remaining -= len(clipped_bytes)
        if remaining <= 0:
            break

    material = {
        "schema": CONTEXT_SCHEMA,
        "max_bytes": max_bytes,
        "per_source_bytes": per_source_bytes,
        "entries": entries,
    }
    material["context_pack_sha256"] = _sha256(_canonical_json(material))
    return material


def external_execution_envelope_contract() -> dict[str, Any]:
    string_array = {"type": "array", "maxItems": MAX_LIST, "items": {"type": "string", "maxLength": MAX_TEXT}}
    return {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "schema", "binding", "goal", "root_cause", "scope_signal",
            "implementation_signal", "verification_signal", "worker_binding", "stop_conditions",
            "model_adaptation",
        ],
        "properties": {
            "schema": {"const": ENVELOPE_SCHEMA},
            "binding": {
                "type": "object", "additionalProperties": False,
                "required": ["repository", "item_type", "item_id", "revision", "main_sha", "task_card_ref", "task_card_hash", "context_pack_sha256"],
                "properties": {key: {"type": "string", "maxLength": MAX_TEXT} for key in (
                    "repository", "item_type", "item_id", "revision", "main_sha", "task_card_ref", "task_card_hash", "context_pack_sha256"
                )},
            },
            "goal": {"type": "string", "maxLength": MAX_TEXT},
            "root_cause": {"type": "string", "maxLength": MAX_TEXT},
            "scope_signal": {
                "type": "object", "additionalProperties": False,
                "required": ["production_edit_paths", "required_test_edit_paths", "conditional_migration_paths", "read_only_authorities", "verification_only_paths", "forbidden_paths", "max_files", "scope_confidence", "scope_block_conditions"],
                "properties": {
                    "production_edit_paths": string_array,
                    "required_test_edit_paths": string_array,
                    "conditional_migration_paths": string_array,
                    "read_only_authorities": string_array,
                    "verification_only_paths": string_array,
                    "forbidden_paths": string_array,
                    "max_files": {"type": "integer", "minimum": 0, "maximum": 256},
                    "scope_confidence": {"enum": ["LOW", "MEDIUM", "HIGH"]},
                    "scope_block_conditions": string_array,
                },
            },
            "implementation_signal": {
                "type": "object", "additionalProperties": False,
                "required": ["inspect_first", "proven_facts", "required_semantics", "suggested_direction", "forbidden_behavior"],
                "properties": {
                    "inspect_first": string_array,
                    "proven_facts": string_array,
                    "required_semantics": string_array,
                    "suggested_direction": string_array,
                    "forbidden_behavior": string_array,
                },
            },
            "verification_signal": {
                "type": "object", "additionalProperties": False,
                "required": ["red_probe", "positive_probes", "hostile_negative_probes", "impact_suites", "static_checks", "false_green_conditions"],
                "properties": {
                    "red_probe": {"type": "string", "maxLength": MAX_TEXT},
                    "positive_probes": string_array,
                    "hostile_negative_probes": string_array,
                    "impact_suites": string_array,
                    "static_checks": string_array,
                    "false_green_conditions": string_array,
                },
            },
            "worker_binding": {
                "type": "object", "additionalProperties": False,
                "required": ["assigned_thread", "persistent_thread", "create_subagent", "fallback_allowed"],
                "properties": {
                    "assigned_thread": {"enum": ["UNASSIGNED", "d1", "d2", "d3", "d4"]},
                    "persistent_thread": {"type": "boolean"},
                    "create_subagent": {"type": "boolean"},
                    "fallback_allowed": {"type": "boolean"},
                },
            },
            "stop_conditions": string_array,
            "model_adaptation": {
                "type": "object", "additionalProperties": False,
                "required": list(MODEL_ADAPTATION_KEYS),
                "properties": {key: string_array for key in MODEL_ADAPTATION_KEYS},
            },
        },
    }


def _validate_string_list(value: Any, field: str) -> None:
    if not isinstance(value, list) or len(value) > MAX_LIST:
        raise ExternalIntelligenceError("INTELLIGENCE_PARSE_FAILED")
    if any(not isinstance(item, str) or len(item) > MAX_TEXT for item in value):
        raise ExternalIntelligenceError("INTELLIGENCE_PARSE_FAILED")


def parse_external_execution_envelope(text: str) -> dict[str, Any]:
    """Fail-closed parser for ChatGPT-produced external intelligence."""
    try:
        value = json.loads(text)
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ExternalIntelligenceError("INTELLIGENCE_PARSE_FAILED") from exc
    top = {
        "schema", "binding", "goal", "root_cause", "scope_signal",
        "implementation_signal", "verification_signal", "worker_binding", "stop_conditions",
        "model_adaptation",
    }
    if not isinstance(value, dict) or set(value) != top or value.get("schema") != ENVELOPE_SCHEMA:
        raise ExternalIntelligenceError("INTELLIGENCE_PARSE_FAILED")
    if not isinstance(value.get("goal"), str) or not isinstance(value.get("root_cause"), str):
        raise ExternalIntelligenceError("INTELLIGENCE_PARSE_FAILED")
    if len(value["goal"]) > MAX_TEXT or len(value["root_cause"]) > MAX_TEXT:
        raise ExternalIntelligenceError("INTELLIGENCE_PARSE_FAILED")

    binding = value.get("binding")
    binding_keys = {"repository", "item_type", "item_id", "revision", "main_sha", "task_card_ref", "task_card_hash", "context_pack_sha256"}
    if not isinstance(binding, dict) or set(binding) != binding_keys:
        raise ExternalIntelligenceError("INTELLIGENCE_PARSE_FAILED")
    if any(not isinstance(binding[key], str) or len(binding[key]) > MAX_TEXT for key in binding_keys):
        raise ExternalIntelligenceError("INTELLIGENCE_PARSE_FAILED")

    scope = value.get("scope_signal")
    scope_keys = {"production_edit_paths", "required_test_edit_paths", "conditional_migration_paths", "read_only_authorities", "verification_only_paths", "forbidden_paths", "max_files", "scope_confidence", "scope_block_conditions"}
    if not isinstance(scope, dict) or set(scope) != scope_keys:
        raise ExternalIntelligenceError("INTELLIGENCE_PARSE_FAILED")
    for field in scope_keys - {"max_files", "scope_confidence"}:
        _validate_string_list(scope[field], field)
    if not isinstance(scope["max_files"], int) or not 0 <= scope["max_files"] <= 256:
        raise ExternalIntelligenceError("INTELLIGENCE_PARSE_FAILED")
    if scope["scope_confidence"] not in {"LOW", "MEDIUM", "HIGH"}:
        raise ExternalIntelligenceError("INTELLIGENCE_PARSE_FAILED")

    implementation = value.get("implementation_signal")
    implementation_keys = {"inspect_first", "proven_facts", "required_semantics", "suggested_direction", "forbidden_behavior"}
    if not isinstance(implementation, dict) or set(implementation) != implementation_keys:
        raise ExternalIntelligenceError("INTELLIGENCE_PARSE_FAILED")
    for field in implementation_keys:
        _validate_string_list(implementation[field], field)

    verification = value.get("verification_signal")
    verification_keys = {"red_probe", "positive_probes", "hostile_negative_probes", "impact_suites", "static_checks", "false_green_conditions"}
    if not isinstance(verification, dict) or set(verification) != verification_keys:
        raise ExternalIntelligenceError("INTELLIGENCE_PARSE_FAILED")
    if not isinstance(verification["red_probe"], str) or len(verification["red_probe"]) > MAX_TEXT:
        raise ExternalIntelligenceError("INTELLIGENCE_PARSE_FAILED")
    for field in verification_keys - {"red_probe"}:
        _validate_string_list(verification[field], field)

    adaptation = value.get("model_adaptation")
    if not isinstance(adaptation, dict) or set(adaptation) != set(MODEL_ADAPTATION_KEYS):
        raise ExternalIntelligenceError("INTELLIGENCE_PARSE_FAILED")
    for field in MODEL_ADAPTATION_KEYS:
        _validate_string_list(adaptation[field], field)

    worker = value.get("worker_binding")
    if not isinstance(worker, dict) or set(worker) != {"assigned_thread", "persistent_thread", "create_subagent", "fallback_allowed"}:
        raise ExternalIntelligenceError("INTELLIGENCE_PARSE_FAILED")
    if worker["assigned_thread"] not in {"UNASSIGNED", "d1", "d2", "d3", "d4"}:
        raise ExternalIntelligenceError("INTELLIGENCE_PARSE_FAILED")
    if any(not isinstance(worker[field], bool) for field in ("persistent_thread", "create_subagent", "fallback_allowed")):
        raise ExternalIntelligenceError("INTELLIGENCE_PARSE_FAILED")
    _validate_string_list(value["stop_conditions"], "stop_conditions")
    return value


def build_request(intake: Mapping[str, Any], context_pack: Mapping[str, Any], *, semantic_contract_sha256: str | None = None) -> dict[str, Any]:
    if intake.get("schema") != INTAKE_SCHEMA or intake.get("disposition") != IntakeDisposition.EXECUTABLE.value:
        raise ExternalIntelligenceError("INTAKE_NOT_EXECUTABLE")
    if context_pack.get("schema") != CONTEXT_SCHEMA:
        raise ExternalIntelligenceError("INVALID_CONTEXT_PACK")
    identity = dict(intake["identity"])
    contract_hash = semantic_contract_sha256 or _sha256(_canonical_json(external_execution_envelope_contract()))
    request = {
        "schema": REQUEST_SCHEMA,
        "identity": identity,
        "identity_sha256": intake["identity_sha256"],
        "context_pack_sha256": context_pack["context_pack_sha256"],
        "semantic_contract_sha256": contract_hash,
        "claim_ceiling": CLAIM_CEILING,
    }
    request["request_sha256"] = _sha256(_canonical_json(request))
    return request


def project_refresh(previous: Mapping[str, Any], current_request: Mapping[str, Any]) -> dict[str, Any]:
    """Decide reuse vs stale without silently refreshing material identity."""
    if previous.get("schema") != RECEIPT_SCHEMA or current_request.get("schema") != REQUEST_SCHEMA:
        raise ExternalIntelligenceError("INVALID_REFRESH_INPUT")
    previous_request = previous.get("request")
    if not isinstance(previous_request, Mapping):
        raise ExternalIntelligenceError("INVALID_REFRESH_INPUT")
    fields = ["identity_sha256", "context_pack_sha256", "semantic_contract_sha256", "request_sha256"]
    changed = [field for field in fields if previous_request.get(field) != current_request.get(field)]
    return {
        "status": "REUSE" if not changed else "STALE",
        "changed_fields": changed,
        "previous_request_sha256": previous_request.get("request_sha256"),
        "current_request_sha256": current_request.get("request_sha256"),
    }


def build_control_capsule(receipt: Mapping[str, Any]) -> dict[str, Any]:
    if receipt.get("schema") != RECEIPT_SCHEMA:
        raise ExternalIntelligenceError("INVALID_RECEIPT")
    request = receipt.get("request") or {}
    envelope = receipt.get("envelope") or {}
    identity = request.get("identity") or {}
    if not isinstance(identity, Mapping) or not isinstance(envelope, Mapping):
        raise ExternalIntelligenceError("INVALID_RECEIPT")
    stop_conditions = envelope.get("stop_conditions") or []
    if not isinstance(stop_conditions, list):
        raise ExternalIntelligenceError("INVALID_RECEIPT")
    return {
        "schema": CONTROL_CAPSULE_SCHEMA,
        "repository": identity.get("repository"),
        "item_type": identity.get("item_type"),
        "item_id": identity.get("item_id"),
        "main_sha": identity.get("main_sha"),
        "task_card_ref": identity.get("task_card_ref"),
        "task_card_hash": identity.get("task_card_hash"),
        "intelligence_receipt_id": receipt.get("receipt_id"),
        "intelligence_request_sha256": request.get("request_sha256"),
        "intelligence_envelope_sha256": receipt.get("envelope_sha256"),
        "refresh_status": (receipt.get("refresh_projection") or {}).get("status", "NEW"),
        "current_gate": "PRE_IMPLEMENTATION_INTELLIGENCE_READY",
        "last_proven": "external_execution_envelope_validated",
        "next_action": "dispatch_to_bound_worker_after_separate_worker_transport_gate",
        "stop_if": list(stop_conditions),
        "claim_ceiling": CLAIM_CEILING,
    }


_REQUEST_MARKER_PREFIX = "NEXUS_REQUEST_SHA256="
_HEX64 = frozenset("0123456789abcdef")


def _request_marker(request_sha256: Any) -> str:
    if not isinstance(request_sha256, str) or len(request_sha256) != 64 or any(c not in _HEX64 for c in request_sha256):
        raise ExternalIntelligenceError("INVALID_REQUEST_IDENTITY")
    return f"{_REQUEST_MARKER_PREFIX}{request_sha256}"


def _extract_request_marker(prompt: Any) -> str | None:
    if not isinstance(prompt, str):
        return None
    start = prompt.find(_REQUEST_MARKER_PREFIX)
    if start < 0:
        return None
    end = prompt.find("\n", start)
    if end < 0:
        end = len(prompt)
    candidate = prompt[start:end]
    value = candidate[len(_REQUEST_MARKER_PREFIX):]
    if len(value) == 64 and all(c in _HEX64 for c in value):
        return candidate
    return None


def build_prompt(request: Mapping[str, Any], context_pack: Mapping[str, Any]) -> str:
    schema = external_execution_envelope_contract()
    identity = request.get("identity") or {}
    binding = {
        "repository": identity.get("repository", ""),
        "item_type": identity.get("item_type", ""),
        "item_id": identity.get("item_id", ""),
        "revision": identity.get("revision", ""),
        "main_sha": identity.get("main_sha", ""),
        "task_card_ref": identity.get("task_card_ref", ""),
        "task_card_hash": identity.get("task_card_hash", ""),
        "context_pack_sha256": request.get("context_pack_sha256", ""),
    }
    marker = _request_marker(request.get("request_sha256"))
    return (
        "You are the Nexus External Intelligence Sidecar. Produce pre-implementation intelligence only; do not claim execution, Candidate, approval, integration, or production authority. "
        f"{marker}\n"
        "Return exactly one JSON object and no markdown fences or prose. The response must be directly parseable by standard json.loads. "
        "Every JSON string must be serialized without literal U+0000-U+001F control characters; encode newlines/tabs with JSON escapes. "
        "Inside free-text string values, do not include unescaped double-quote characters; prefer single quotes, backticks, or paraphrase identifiers instead. "
        "Before responding, mentally validate that the entire response is accepted by standard json.loads without repair. "
        "Do not use JSON5, comments, trailing commas, or extra keys. The binding object MUST exactly equal the supplied binding. "
        "Worker binding is advisory only in Phase A+B: assigned_thread must be UNASSIGNED; persistent_thread=true; create_subagent=false; fallback_allowed=false. "
        "OUTPUT_COMPLETENESS: The response MUST contain every property declared in every `required` array of the SCHEMA; no required property may be omitted. "
        "For a required array field with no substantive content, emit [] rather than omitting the key. "
        "implementation_signal MUST include all five keys: inspect_first, proven_facts, required_semantics, suggested_direction, forbidden_behavior. "
        "MODEL_ADAPTATION: Compile a DeepSeek-adaptive L2 task brief into the required model_adaptation object; do not paste broad governance text. "
        "model_adaptation must include all six keys: role_contract, task_local_invariants, known_failure_guards, execution_strategy, forbidden_inferences, repair_policy. "
        "role_contract must keep role/authority bounded to DeepSeek V4 Flash L2 Task Engineer. "
        "task_local_invariants must be derived from current task-local evidence only. "
        "known_failure_guards must select only task-relevant failure families, never mechanically include every historical failure family. "
        "execution_strategy must be actionable yet leave bounded task-local engineering judgment to DeepSeek. "
        "forbidden_inferences must list implementation-as-policy and authority overreach when applicable. "
        "repair_policy must encode one evidence-guided same-unit repair and no blind retry or auto-chain. "
        "Keep model_adaptation as minimal-but-complete task-local truth, not a full policy or governance dump. "
        "The response must contain exactly the allowed keys and no extras, and must not add prose or markdown fences. "
        f"BINDING={_canonical_json(binding)}\n"
        f"INTAKE_PROJECTION={_canonical_json(identity)}\n"
        f"SCHEMA={_canonical_json(schema)}\n"
        "BEGIN_UNTRUSTED_CONTEXT\n"
        f"{_canonical_json(context_pack)}\n"
        "END_UNTRUSTED_CONTEXT"
    )


@dataclass(frozen=True)
class TransportResult:
    status: str
    raw: str = ""
    conversation_id: str = ""
    outcome_unknown: bool = False
    retry_safe: bool = False
    started_at: str = ""
    finished_at: str = ""
    safe_argv: tuple[str, ...] = ()


class OpenCLIExternalIntelligenceTransport:
    """One-write OpenCLI transport followed by stable read-back of the same conversation.

    A failed/timed-out ``ask`` is reconciled READ-ONLY against existing
    ChatGPT history: the transport locates the exact conversation whose user
    prompt matches this invocation and stable-reads its assistant response.
    A timeout never triggers a second ``ask``.
    """

    def __init__(self, executable: str = "opencli", *, profile: str = "", timeout: int = 120, stable_seconds: int = 6, history_limit: int = 5):
        self.executable = executable
        self.profile = profile
        self.timeout = int(timeout)
        self.stable_seconds = int(stable_seconds)
        self.history_limit = int(history_limit)

    def safe_argv(self) -> tuple[str, ...]:
        return (
            self.executable, "chatgpt", "ask", "<prompt>", "--new", "--timeout", str(self.timeout),
            "--site-session", "ephemeral", "-f", "json",
        )

    @staticmethod
    def _prompt_matches(user_prompt: str, expected_prompt: str) -> bool:
        """Exact-request-marker match.

        The expected prompt is produced by build_prompt and always carries a
        NEXUS_REQUEST_SHA256=<64hex> line. The user message rendered by
        ChatGPT/OpenCLI may reflow markdown/whitespace, so the match is keyed
        on the exact cryptographic marker, never on fuzzy whole-prompt text.
        """
        if not isinstance(user_prompt, str) or not isinstance(expected_prompt, str):
            return False
        marker = _extract_request_marker(expected_prompt)
        if marker is None:
            return False
        return marker in user_prompt

    def _history_argv(self) -> list[str]:
        return [
            self.executable, "chatgpt", "history",
            "--limit", str(self.history_limit),
            "--site-session", "ephemeral", "-f", "json",
        ]

    def _run(self, argv: Sequence[str], env: Mapping[str, str]) -> tuple[int | None, str, str, bool]:
        try:
            process = subprocess.Popen(
                list(argv), stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, start_new_session=True, shell=False, env=dict(env),
            )
        except FileNotFoundError:
            return None, "", "", False
        try:
            try:
                stdout, stderr = process.communicate(timeout=self.timeout + 5)
                return process.returncode, stdout or "", stderr or "", False
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                except (OSError, ProcessLookupError):
                    pass
                try:
                    stdout, stderr = process.communicate(timeout=1)
                except subprocess.TimeoutExpired:
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except (OSError, ProcessLookupError):
                        pass
                    stdout, stderr = process.communicate()
                return process.returncode, stdout or "", stderr or "", True
        finally:
            for stream in (process.stdout, process.stderr):
                if stream is not None:
                    stream.close()

    def invoke(self, prompt: str) -> TransportResult:
        started = _now()
        safe = self.safe_argv()
        env = os.environ.copy()
        if self.profile:
            env["OPENCLI_PROFILE"] = self.profile
        ask = [
            self.executable, "chatgpt", "ask", prompt, "--new", "--timeout", str(self.timeout),
            "--site-session", "ephemeral", "-f", "json",
        ]
        code, stdout, stderr, timed_out = self._run(ask, env)
        if code is None:
            return TransportResult("OPENCLI_NOT_FOUND", started_at=started, finished_at=_now(), safe_argv=safe)
        if timed_out or code:
            # Once the ask process starts, timeout or nonzero exit is outcome-ambiguous:
            # ChatGPT may already have accepted the prompt even if OpenCLI lost the
            # response/bridge state. Reconcile read-only by exact request marker;
            # never blind-resend the semantic ask.
            return self._reconcile_timeout(prompt, env, started, safe)
        try:
            rows = json.loads(stdout)
            if not isinstance(rows, list) or len(rows) != 1 or not isinstance(rows[0], dict):
                raise ValueError
            conversation_id = rows[0].get("conversationId")
            if not isinstance(conversation_id, str) or not conversation_id:
                raise ValueError
        except (TypeError, ValueError, json.JSONDecodeError):
            return TransportResult("OPENCLI_PROCESS_FAILURE", stdout, retry_safe=False, started_at=started, finished_at=_now(), safe_argv=safe)

        detail = [
            self.executable, "chatgpt", "detail", conversation_id,
            "--wait", "--stable", str(self.stable_seconds), "--timeout", str(self.timeout),
            "--site-session", "ephemeral", "-f", "json",
        ]
        detail_code, detail_stdout, detail_stderr, detail_timeout = self._run(detail, env)
        if detail_code is None or detail_timeout or detail_code:
            return TransportResult(
                "OPENCLI_STABLE_READ_FAILURE", detail_stdout or detail_stderr, conversation_id=conversation_id,
                retry_safe=False, started_at=started, finished_at=_now(), safe_argv=safe,
            )
        raw, matched_id = self._extract_stable(detail_stdout, conversation_id)
        if raw is None:
            return TransportResult(
                "OPENCLI_STABLE_READ_FAILURE", detail_stdout, conversation_id=conversation_id,
                retry_safe=False, started_at=started, finished_at=_now(), safe_argv=safe,
            )
        return TransportResult(
            "INTELLIGENCE_COMPLETED", raw, conversation_id=matched_id,
            retry_safe=False, started_at=started, finished_at=_now(), safe_argv=safe,
        )

    def _extract_stable(self, detail_stdout: str, conversation_id: str) -> tuple[str | None, str]:
        try:
            detail_rows = json.loads(detail_stdout)
            stable = [
                row for row in detail_rows
                if isinstance(row, dict)
                and row.get("Role") == "Assistant"
                and isinstance(row.get("Text"), str)
                and row.get("Generating") is False
                and isinstance(row.get("StableSeconds"), (int, float))
                and row.get("StableSeconds") >= self.stable_seconds
            ]
            if not stable:
                raise ValueError
            return stable[-1]["Text"], conversation_id
        except (TypeError, ValueError, json.JSONDecodeError):
            return None, conversation_id

    def reconcile(self, prompt: str) -> TransportResult:
        """READ-ONLY recovery for a previously started ambiguous ask.

        This method never issues a semantic ask. It searches recent ChatGPT
        history for exactly one conversation containing the request marker and
        stable-reads that conversation.
        """
        started = _now()
        env = os.environ.copy()
        if self.profile:
            env["OPENCLI_PROFILE"] = self.profile
        return self._reconcile_timeout(prompt, env, started, self.safe_argv())

    def _reconcile_timeout(self, prompt: str, env: Mapping[str, str], started: str, safe: tuple[str, ...]) -> TransportResult:
        """READ-ONLY recovery after an ambiguous ask outcome. Never issues a second ask."""
        code, stdout, stderr, timed_out = self._run(self._history_argv(), env)
        if code is None or timed_out or code:
            return TransportResult(
                "OPENCLI_OUTCOME_UNKNOWN", stdout or stderr, outcome_unknown=True, retry_safe=False,
                started_at=started, finished_at=_now(), safe_argv=safe,
            )
        try:
            rows = json.loads(stdout)
            if not isinstance(rows, list):
                raise ValueError
        except (TypeError, ValueError, json.JSONDecodeError):
            return TransportResult(
                "OPENCLI_OUTCOME_UNKNOWN", stdout, outcome_unknown=True, retry_safe=False,
                started_at=started, finished_at=_now(), safe_argv=safe,
            )
        matching: list[str] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            conversation_id = row.get("Id")
            if not isinstance(conversation_id, str) or not conversation_id:
                continue
            detail_read = [
                self.executable, "chatgpt", "detail", conversation_id,
                "--site-session", "ephemeral", "-f", "json",
            ]
            read_code, read_stdout, read_stderr, read_timeout = self._run(detail_read, env)
            if read_code is None or read_timeout or read_code:
                continue
            try:
                detail_rows = json.loads(read_stdout)
                if not isinstance(detail_rows, list):
                    raise ValueError
            except (TypeError, ValueError, json.JSONDecodeError):
                continue
            user_prompts = [
                row.get("Text") for row in detail_rows
                if isinstance(row, dict) and row.get("Role") == "User" and isinstance(row.get("Text"), str)
            ]
            if any(self._prompt_matches(text, prompt) for text in user_prompts):
                matching.append(conversation_id)
        if len(matching) != 1:
            return TransportResult(
                "OPENCLI_OUTCOME_UNKNOWN", "", outcome_unknown=True, retry_safe=False,
                started_at=started, finished_at=_now(), safe_argv=safe,
            )
        conversation_id = matching[0]
        detail = [
            self.executable, "chatgpt", "detail", conversation_id,
            "--wait", "--stable", str(self.stable_seconds), "--timeout", str(self.timeout),
            "--site-session", "ephemeral", "-f", "json",
        ]
        detail_code, detail_stdout, detail_stderr, detail_timeout = self._run(detail, env)
        if detail_code is None or detail_timeout or detail_code:
            return TransportResult(
                "OPENCLI_STABLE_READ_FAILURE", detail_stdout or detail_stderr, conversation_id=conversation_id,
                retry_safe=False, started_at=started, finished_at=_now(), safe_argv=safe,
            )
        raw, matched_id = self._extract_stable(detail_stdout, conversation_id)
        if raw is None:
            return TransportResult(
                "OPENCLI_STABLE_READ_FAILURE", detail_stdout, conversation_id=conversation_id,
                retry_safe=False, started_at=started, finished_at=_now(), safe_argv=safe,
            )
        return TransportResult(
            "INTELLIGENCE_COMPLETED", raw, conversation_id=matched_id,
            retry_safe=False, started_at=started, finished_at=_now(), safe_argv=safe,
        )


class ExternalIntelligenceStore:
    def __init__(self, root: str | os.PathLike[str]):
        self.root = Path(root)
        self.requests = self.root / "requests"
        self.attempts = self.root / "attempts"
        self.envelopes = self.root / "envelopes"
        self.receipts = self.root / "receipts"

    def _request_path(self, request_sha256: str) -> Path:
        return self.requests / f"{request_sha256}.json"

    def _attempt_path(self, request_sha256: str) -> Path:
        return self.attempts / f"{request_sha256}.json"

    def _envelope_path(self, request_sha256: str) -> Path:
        return self.envelopes / f"{request_sha256}.json"

    def _receipt_path(self, request_sha256: str) -> Path:
        return self.receipts / f"{request_sha256}.json"

    def persist_request(self, request: Mapping[str, Any]) -> Path:
        request_sha = str(request.get("request_sha256") or "")
        if request.get("schema") != REQUEST_SCHEMA or len(request_sha) != 64:
            raise ExternalIntelligenceError("INVALID_REQUEST_IDENTITY")
        path = self._request_path(request_sha)
        if path.exists():
            try:
                existing = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError, UnicodeError) as exc:
                raise ExternalIntelligenceError("INTELLIGENCE_REQUEST_CORRUPT") from exc
            if existing != dict(request):
                raise ExternalIntelligenceError("INTELLIGENCE_REQUEST_IDENTITY_MISMATCH")
            return path
        _atomic_json(path, request)
        return path

    def write_envelope(self, request: Mapping[str, Any], envelope: Mapping[str, Any]) -> Path:
        request_sha = str(request.get("request_sha256") or "")
        if request.get("schema") != REQUEST_SCHEMA or envelope.get("schema") != ENVELOPE_SCHEMA or len(request_sha) != 64:
            raise ExternalIntelligenceError("INVALID_ENVELOPE_ARTIFACT")
        path = self._envelope_path(request_sha)
        if path.exists():
            try:
                existing = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError, UnicodeError) as exc:
                raise ExternalIntelligenceError("INTELLIGENCE_ENVELOPE_CORRUPT") from exc
            if existing != dict(envelope):
                raise ExternalIntelligenceError("INTELLIGENCE_ENVELOPE_IDENTITY_MISMATCH")
            return path
        _atomic_json(path, envelope)
        return path

    def latest_receipt_for_item(self, request: Mapping[str, Any]) -> dict[str, Any] | None:
        identity = request.get("identity") or {}
        key = (identity.get("repository"), identity.get("item_type"), identity.get("item_id"))
        matches: list[dict[str, Any]] = []
        if not self.receipts.exists():
            return None
        for path in sorted(self.receipts.glob("*.json")):
            try:
                value = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError, UnicodeError) as exc:
                raise ExternalIntelligenceError("INTELLIGENCE_RECEIPT_CORRUPT") from exc
            if value.get("schema") != RECEIPT_SCHEMA:
                raise ExternalIntelligenceError("INTELLIGENCE_RECEIPT_CORRUPT")
            previous_identity = value.get("request", {}).get("identity", {})
            previous_key = (
                previous_identity.get("repository"),
                previous_identity.get("item_type"),
                previous_identity.get("item_id"),
            )
            if previous_key == key:
                matches.append(value)
        if not matches:
            return None
        return max(matches, key=lambda value: (str(value.get("created_at") or ""), str(value.get("receipt_id") or "")))

    def existing_receipt(self, request: Mapping[str, Any]) -> dict[str, Any] | None:
        path = self._receipt_path(str(request.get("request_sha256") or ""))
        if not path.exists():
            return None
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, UnicodeError) as exc:
            raise ExternalIntelligenceError("INTELLIGENCE_RECEIPT_CORRUPT") from exc
        if value.get("schema") != RECEIPT_SCHEMA or value.get("request", {}).get("request_sha256") != request.get("request_sha256"):
            raise ExternalIntelligenceError("INTELLIGENCE_RECEIPT_IDENTITY_MISMATCH")
        return value

    def load_attempt(self, request: Mapping[str, Any]) -> dict[str, Any] | None:
        request_sha = str(request.get("request_sha256") or "")
        if len(request_sha) != 64:
            raise ExternalIntelligenceError("INVALID_REQUEST_IDENTITY")
        path = self._attempt_path(request_sha)
        if not path.exists():
            return None
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, UnicodeError) as exc:
            raise ExternalIntelligenceError("INTELLIGENCE_ATTEMPT_CORRUPT") from exc
        if value.get("schema") != ATTEMPT_SCHEMA or value.get("request_sha256") != request_sha:
            raise ExternalIntelligenceError("INTELLIGENCE_ATTEMPT_IDENTITY_MISMATCH")
        return value

    def prepare(self, request: Mapping[str, Any]) -> dict[str, Any]:
        request_sha = str(request.get("request_sha256") or "")
        if len(request_sha) != 64:
            raise ExternalIntelligenceError("INVALID_REQUEST_IDENTITY")
        self.persist_request(request)
        path = self._attempt_path(request_sha)
        if path.exists():
            try:
                existing = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError, UnicodeError) as exc:
                raise ExternalIntelligenceError("INTELLIGENCE_ATTEMPT_CORRUPT") from exc
            state = existing.get("state")
            if state in {"PREPARED", "DISPATCHING", "OUTCOME_UNKNOWN"}:
                raise ExternalIntelligenceError("INTELLIGENCE_RECONCILIATION_REQUIRED")
            if state in {"COMPLETED", "FAILED"}:
                raise ExternalIntelligenceError("INTELLIGENCE_REPLAY_FORBIDDEN")
            raise ExternalIntelligenceError("INTELLIGENCE_ATTEMPT_STATE_INVALID")
        value = {
            "schema": ATTEMPT_SCHEMA,
            "attempt_id": str(uuid.uuid4()),
            "request_sha256": request_sha,
            "state": "PREPARED",
            "retry_safe": True,
            "prepared_at": _now(),
        }
        _atomic_json(path, value)
        return value

    def mark_dispatching(self, attempt: Mapping[str, Any]) -> dict[str, Any]:
        value = dict(attempt)
        value.update({"state": "DISPATCHING", "retry_safe": False, "dispatching_at": _now()})
        _atomic_json(self._attempt_path(value["request_sha256"]), value)
        return value

    def finish_attempt(self, attempt: Mapping[str, Any], *, state: str, transport_status: str) -> dict[str, Any]:
        if state not in {"COMPLETED", "FAILED", "OUTCOME_UNKNOWN"}:
            raise ExternalIntelligenceError("INVALID_ATTEMPT_TERMINAL_STATE")
        value = dict(attempt)
        value.update({
            "state": state,
            "retry_safe": False,
            "transport_status": transport_status,
            "finished_at": _now(),
        })
        _atomic_json(self._attempt_path(value["request_sha256"]), value)
        return value

    def write_receipt(self, receipt: Mapping[str, Any]) -> Path:
        request_sha = str(receipt.get("request", {}).get("request_sha256") or "")
        path = self._receipt_path(request_sha)
        _atomic_json(path, receipt)
        return path


class ExternalIntelligenceSidecar:
    def __init__(self, *, transport: Any, store: ExternalIntelligenceStore):
        self.transport = transport
        self.store = store

    def analyze(self, record: Mapping[str, Any], sources: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
        intake = normalize_intake(record)
        if intake["disposition"] != IntakeDisposition.EXECUTABLE.value:
            return {
                "schema": RECEIPT_SCHEMA,
                "status": "NOT_DISPATCHED",
                "intake": intake,
                "claim_ceiling": CLAIM_CEILING,
            }
        context_pack = build_context_pack(sources)
        request = build_request(intake, context_pack)
        existing = self.store.existing_receipt(request)
        if existing is not None:
            return {**existing, "reuse": True}
        previous = self.store.latest_receipt_for_item(request)
        if previous is None:
            refresh_projection = {
                "status": "NEW",
                "changed_fields": [],
                "previous_request_sha256": None,
                "current_request_sha256": request["request_sha256"],
                "previous_receipt_id": None,
            }
        else:
            refresh_projection = {
                **project_refresh(previous, request),
                "previous_receipt_id": previous.get("receipt_id"),
            }
        prompt = build_prompt(request, context_pack)
        attempt = self.store.load_attempt(request)
        if attempt is None:
            attempt = self.store.prepare(request)
            attempt = self.store.mark_dispatching(attempt)
            result: TransportResult = self.transport.invoke(prompt)
        elif attempt.get("state") == "PREPARED":
            # The prior controller stopped before dispatch was journaled. No
            # semantic ask can have started, so resume the original attempt.
            attempt = self.store.mark_dispatching(attempt)
            result = self.transport.invoke(prompt)
        elif attempt.get("state") in {"DISPATCHING", "OUTCOME_UNKNOWN"}:
            # A prior ask may have reached ChatGPT. Reconcile read-only using
            # the exact request marker; never resend the semantic request.
            reconcile = getattr(self.transport, "reconcile", None)
            if not callable(reconcile):
                raise ExternalIntelligenceError("INTELLIGENCE_RECONCILIATION_REQUIRED")
            result = reconcile(prompt)
        elif attempt.get("state") == "COMPLETED":
            raise ExternalIntelligenceError("INTELLIGENCE_RECEIPT_MISSING")
        else:
            raise ExternalIntelligenceError("INTELLIGENCE_REPLAY_FORBIDDEN")
        if result.status != "INTELLIGENCE_COMPLETED":
            terminal = "OUTCOME_UNKNOWN" if result.outcome_unknown else "FAILED"
            self.store.finish_attempt(attempt, state=terminal, transport_status=result.status)
            if result.outcome_unknown or not result.retry_safe:
                raise ExternalIntelligenceError("INTELLIGENCE_RECONCILIATION_REQUIRED")
            raise ExternalIntelligenceError(result.status)
        try:
            envelope = parse_external_execution_envelope(result.raw)
        except ExternalIntelligenceError:
            self.store.finish_attempt(attempt, state="FAILED", transport_status="INTELLIGENCE_PARSE_FAILED")
            raise
        identity = request["identity"]
        expected_binding = {
            "repository": identity["repository"],
            "item_type": identity["item_type"],
            "item_id": identity["item_id"],
            "revision": identity["revision"],
            "main_sha": identity["main_sha"],
            "task_card_ref": identity["task_card_ref"],
            "task_card_hash": identity["task_card_hash"],
            "context_pack_sha256": request["context_pack_sha256"],
        }
        if envelope["binding"] != expected_binding:
            self.store.finish_attempt(attempt, state="FAILED", transport_status="INTELLIGENCE_BINDING_MISMATCH")
            raise ExternalIntelligenceError("INTELLIGENCE_BINDING_MISMATCH")
        if envelope["worker_binding"] != {
            "assigned_thread": "UNASSIGNED",
            "persistent_thread": True,
            "create_subagent": False,
            "fallback_allowed": False,
        }:
            self.store.finish_attempt(attempt, state="FAILED", transport_status="INTELLIGENCE_WORKER_BOUNDARY_VIOLATION")
            raise ExternalIntelligenceError("INTELLIGENCE_WORKER_BOUNDARY_VIOLATION")
        envelope_sha256 = _sha256(_canonical_json(envelope))
        self.store.write_envelope(request, envelope)
        receipt_material = {
            "request_sha256": request["request_sha256"],
            "attempt_id": attempt["attempt_id"],
            "raw_sha256": _sha256(result.raw),
            "envelope_sha256": envelope_sha256,
            "envelope": envelope,
        }
        receipt = {
            "schema": RECEIPT_SCHEMA,
            "receipt_id": _sha256(_canonical_json(receipt_material)),
            "status": "COMPLETED",
            "request": request,
            "attempt_id": attempt["attempt_id"],
            "context_pack_sha256": request["context_pack_sha256"],
            "semantic_contract_sha256": request["semantic_contract_sha256"],
            "transport_status": result.status,
            "conversation_id": result.conversation_id,
            "safe_argv": list(result.safe_argv),
            "raw_response_sha256": _sha256(result.raw),
            "envelope_sha256": envelope_sha256,
            "envelope": envelope,
            "refresh_projection": refresh_projection,
            "claim_ceiling": CLAIM_CEILING,
            "created_at": _now(),
            "reuse": False,
        }
        receipt["control_capsule"] = build_control_capsule(receipt)
        self.store.write_receipt(receipt)
        self.store.finish_attempt(attempt, state="COMPLETED", transport_status=result.status)
        return receipt


__all__ = [
    "ATTEMPT_SCHEMA",
    "CLAIM_CEILING",
    "CONTEXT_SCHEMA",
    "CONTROL_CAPSULE_SCHEMA",
    "ENVELOPE_SCHEMA",
    "INTAKE_SCHEMA",
    "RECEIPT_SCHEMA",
    "REQUEST_SCHEMA",
    "ExternalIntelligenceError",
    "ExternalIntelligenceSidecar",
    "ExternalIntelligenceStore",
    "IntakeDisposition",
    "MODEL_ADAPTATION_KEYS",
    "OpenCLIExternalIntelligenceTransport",
    "TransportResult",
    "build_context_pack",
    "build_control_capsule",
    "build_prompt",
    "build_request",
    "external_execution_envelope_contract",
    "normalize_intake",
    "parse_external_execution_envelope",
    "project_refresh",
]
