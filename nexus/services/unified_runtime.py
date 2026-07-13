"""Canonical task-scoped runtime seam for Online and Local execution.

The seam is deliberately provider-neutral.  Adapters supply callables for
Online execution, verification, and learning; the runtime owns task identity,
one planner invocation, stage ordering, and one fail-closed receipt.
"""

from __future__ import annotations

import hashlib
import json
import os
import shlex
import shutil
import subprocess
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Callable, Mapping

from nexus.engine.capability_planner import CapabilityPlanner

REQUEST_SCHEMA = "nexus.unified_runtime.request.v1"
RECEIPT_SCHEMA = "nexus.unified_runtime.receipt.v1"

# Provider-neutral registration metadata.  Commands stay configurable at the
# edge; this registry records the supported adapter contract without claiming
# that a provider binary was invoked.
ONLINE_CLI_SPEC_REGISTRY: dict[str, dict[str, str]] = {
    "gemini": {
        "transport": "subprocess",
        "binary_env": "NEXUS_GEMINI_BIN",
        "command_env": "NEXUS_GEMINI_COMMAND",
        "binary_name": "gemini",
    },
    "grok": {
        "transport": "subprocess",
        "binary_env": "NEXUS_GROK_BIN",
        "command_env": "NEXUS_GROK_COMMAND",
        "binary_name": "grok",
    },
    "codex": {
        "transport": "subprocess",
        "binary_env": "NEXUS_CODEX_BIN",
        "command_env": "NEXUS_CODEX_COMMAND",
        "binary_name": "codex",
    },
    "openai": {
        "transport": "subprocess",
        "binary_env": "NEXUS_OPENAI_BIN",
        "command_env": "NEXUS_OPENAI_COMMAND",
        "binary_name": "openai",
    },
}

# Local-only providers may appear on Gateway defaults (auto-detect) but are not
# Online CLI registry members. They must not be promoted into Online route.provider
# merely because they are locally available.
LOCAL_ONLY_PROVIDERS: frozenset[str] = frozenset({"ollama"})

TRANSPORT_STRUCTURED_CALLABLE = "structured_callable"
TRANSPORT_REGISTERED_CLI = "registered_cli"
TRANSPORT_GATEWAY_COMPATIBILITY = "gateway_compatibility"
TRANSPORT_UNRESOLVED = "unresolved"

SELECTION_EXPLICIT_REQUEST = "explicit_request"
SELECTION_INJECTED_TRANSPORT = "injected_transport"
SELECTION_ENVIRONMENT_DEFAULT = "environment_default"
SELECTION_COMPATIBILITY_DEFAULT = "compatibility_default"
SELECTION_PLANNER = "planner"


def _safe_task_id(value: str) -> str:
    raw = str(value or "").strip()
    if not raw or any(char in raw for char in "/\\\x00"):
        raise ValueError("task_id_invalid")
    return raw


def _hash_json(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        converted = to_dict()
        if isinstance(converted, Mapping):
            return dict(converted)
    return {"status": "FAILED", "error": "stage_result_not_mapping"}


def _capability_evidence_summary(results: Mapping[str, Any]) -> dict[str, Any]:
    """Keep Online receipt awareness after Local context compression."""
    summary: dict[str, Any] = {}
    for name, value in results.items():
        data = value if isinstance(value, Mapping) else {}
        summary[str(name)] = {
            "status": str(data.get("status", "")),
            "task_id": str(data.get("task_id", "")),
            "evidence_refs": [str(ref) for ref in data.get("evidence_refs", []) or []][:6],
        }
    return summary


def _stage(
    name: str,
    *,
    status: str,
    invoked: bool = False,
    evidence_present: bool = False,
    gate_passed: bool = False,
    outcome_contributed: bool = False,
    evidence_refs: list[str] | None = None,
    reason: str = "",
    **fields: Any,
) -> dict[str, Any]:
    return {
        "name": name,
        "status": status,
        "invoked": invoked,
        "evidence_present": evidence_present,
        "gate_passed": gate_passed,
        "outcome_contributed": outcome_contributed,
        "evidence_refs": list(evidence_refs or []),
        "reason": reason,
        **fields,
    }


def _capability_stage(
    name: str,
    task_id: str,
    result: Any,
    *,
    delegated_to: str = "Local",
) -> dict[str, Any]:
    """Normalize an explicit capability executor result fail-closed."""
    data = _mapping(result)
    response_task_id = str(data.get("task_id", "") or "")
    task_identity_shared = not response_task_id or response_task_id == task_id
    invoked = bool(data.get("invoked", False))
    gate_passed = bool(
        data.get(
            "gate_passed",
            str(data.get("status", "")).lower() in {"ok", "pass", "passed", "succeeded", "success"},
        )
    )
    evidence_refs = [str(ref) for ref in data.get("evidence_refs", []) or []]
    evidence_present = bool(evidence_refs or data.get("evidence"))
    return _stage(
        f"capability:{name}",
        status="SUCCEEDED" if task_identity_shared and invoked and evidence_present and gate_passed else "FAILED",
        invoked=invoked,
        evidence_present=evidence_present,
        gate_passed=task_identity_shared and gate_passed,
        outcome_contributed=bool(data.get("outcome_contributed", False)),
        evidence_refs=evidence_refs,
        reason="capability_task_id_mismatch" if not task_identity_shared else "",
        task_id=task_id,
        response_task_id=response_task_id,
        task_identity_shared=task_identity_shared,
        delegated_to=str(data.get("delegated_to", delegated_to) or delegated_to),
        response=data,
    )


@dataclass(frozen=True)
class UnifiedRuntimeRequest:
    """Inputs shared by every provider route for one task."""

    task_id: str
    workspace_revision: str
    task_statement: str
    task_type: str
    route: Mapping[str, Any]
    online_enabled: bool = True
    local_enabled: bool = False
    online_prompt: str = ""
    online_payload: str = ""
    online_phase: str = "R"
    online_model_name: str | None = None
    online_output_schema: Mapping[str, Any] | None = None
    pillars: Mapping[str, Any] = field(default_factory=dict)
    codeintel: Mapping[str, Any] = field(default_factory=dict)
    phase_trace: Mapping[str, Any] = field(default_factory=dict)
    budget: Mapping[str, Any] = field(default_factory=dict)
    skills: tuple[Mapping[str, Any], ...] = ()
    local_request: Any = None
    evidence_refs: tuple[str, ...] = ()
    schema: str = REQUEST_SCHEMA

    def validate(self) -> None:
        if self.schema != REQUEST_SCHEMA:
            raise ValueError("unsupported_request_schema")
        _safe_task_id(self.task_id)
        if not str(self.workspace_revision).strip():
            raise ValueError("missing_workspace_revision")
        if not str(self.task_statement).strip():
            raise ValueError("missing_task_statement")
        if not str(self.task_type).strip():
            raise ValueError("missing_task_type")
        if not isinstance(self.route, Mapping):
            raise ValueError("route_must_be_object")
        if not self.online_enabled and not self.local_enabled:
            raise ValueError("at_least_one_runtime_route_required")
        if self.local_enabled and self.local_request is None:
            raise ValueError("local_request_required")


@dataclass(frozen=True)
class OnlineCliSpec:
    """Provider-neutral subprocess contract for Online CLI adapters."""

    provider: str
    command: tuple[str, ...]
    timeout_sec: float = 120.0

    def validate(self) -> None:
        if not str(self.provider or "").strip():
            raise ValueError("provider_required")
        if not self.command or any(not str(part).strip() for part in self.command):
            raise ValueError("command_required")
        if self.timeout_sec <= 0:
            raise ValueError("timeout_must_be_positive")


@dataclass(frozen=True)
class OnlineTransportBinding:
    """Resolved Online execution binding (identity ≠ transport).

    Fields:
      execution_role: always ``online`` for this binder
      provider: selected provider identity (may be empty, injected, or registry key)
      transport: how the Online call is physically made
      selection_source: why this binding was chosen
      resolution_error: non-empty when transport cannot be resolved
      use_gateway_structured: prefer Gateway ``ask_structured`` compatibility path
      use_registered_cli: prefer registered Online CLI invoker
    """

    execution_role: str
    provider: str
    transport: str
    selection_source: str
    resolution_error: str = ""
    use_gateway_structured: bool = False
    use_registered_cli: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "execution_role": self.execution_role,
            "provider": self.provider,
            "transport": self.transport,
            "selection_source": self.selection_source,
            "resolution_error": self.resolution_error,
            "use_gateway_structured": self.use_gateway_structured,
            "use_registered_cli": self.use_registered_cli,
        }


def build_online_route(
    *,
    recommended_flow: str = "direct",
    gateway_provider: str = "",
    explicit_provider: str = "",
    local_enabled: bool = False,
    selection_source: str = "",
) -> dict[str, Any]:
    """Build an Online route object without conflating local discovery.

    Gateway default / auto-detected local providers (for example Ollama) are
    recorded as environment context but are **not** copied into
    ``route["provider"]`` unless they are registered Online CLI providers or
    the caller supplies an explicit Online provider.
    """
    explicit = str(explicit_provider or "").strip().lower()
    gateway = str(gateway_provider or "").strip().lower()
    source = str(selection_source or "").strip().lower()

    provider = ""
    if explicit:
        provider = explicit
        source = source or SELECTION_EXPLICIT_REQUEST
    elif gateway in ONLINE_CLI_SPEC_REGISTRY:
        provider = gateway
        source = source or SELECTION_ENVIRONMENT_DEFAULT
    else:
        # Local-only or empty gateway default: leave Online provider unset so
        # transport resolution can prefer injected/bound structured transport
        # or gateway compatibility without inventing a false Online identity.
        provider = ""
        source = source or SELECTION_COMPATIBILITY_DEFAULT

    route: dict[str, Any] = {
        "recommended_flow": recommended_flow,
        "execution_role": "online",
        "selection_source": source,
        "local_enabled": bool(local_enabled),
        "gateway_default_provider": gateway,
    }
    if provider:
        route["provider"] = provider
    if gateway and gateway in LOCAL_ONLY_PROVIDERS:
        route["local_provider_detected"] = gateway
    return route


def resolve_online_transport_binding(
    *,
    has_explicit_invoker: bool = False,
    structured_transport_injected: bool = False,
    route_provider: str = "",
    gateway_provider: str = "",
) -> OnlineTransportBinding:
    """Deterministic Online transport resolution.

    Precedence:
      1. explicit online_invoker
      2. injected / bound structured transport
      3. explicit route provider (registered CLI, with gemini gateway special-case)
      4. registered CLI when route provider is registered
      5. gateway compatibility fallback for empty or local-only providers
      6. fail-closed for unknown Online providers
    """
    requested = str(route_provider or "").strip().lower()
    gateway = str(gateway_provider or "").strip().lower()

    if has_explicit_invoker:
        return OnlineTransportBinding(
            execution_role="online",
            provider=requested or "explicit_invoker",
            transport=TRANSPORT_STRUCTURED_CALLABLE,
            selection_source=SELECTION_EXPLICIT_REQUEST,
            use_gateway_structured=False,
            use_registered_cli=False,
        )

    if structured_transport_injected:
        return OnlineTransportBinding(
            execution_role="online",
            # Injected transport identity is not the local auto-detect default.
            provider="injected",
            transport=TRANSPORT_STRUCTURED_CALLABLE,
            selection_source=SELECTION_INJECTED_TRANSPORT,
            use_gateway_structured=True,
            use_registered_cli=False,
        )

    if requested and requested in ONLINE_CLI_SPEC_REGISTRY:
        # Gemini retains specialized Gateway CLI transport when the Gateway
        # itself is also configured for Gemini; other registered providers use
        # the provider-neutral registered CLI edge.
        if requested == "gemini" and gateway == "gemini":
            return OnlineTransportBinding(
                execution_role="online",
                provider="gemini",
                transport=TRANSPORT_GATEWAY_COMPATIBILITY,
                selection_source=SELECTION_ENVIRONMENT_DEFAULT if not requested else SELECTION_EXPLICIT_REQUEST,
                use_gateway_structured=True,
                use_registered_cli=False,
            )
        return OnlineTransportBinding(
            execution_role="online",
            provider=requested,
            transport=TRANSPORT_REGISTERED_CLI,
            selection_source=SELECTION_EXPLICIT_REQUEST,
            use_gateway_structured=False,
            use_registered_cli=True,
        )

    if not requested or requested in LOCAL_ONLY_PROVIDERS:
        return OnlineTransportBinding(
            execution_role="online",
            provider=gateway or requested or "gateway",
            transport=TRANSPORT_GATEWAY_COMPATIBILITY,
            selection_source=SELECTION_COMPATIBILITY_DEFAULT,
            use_gateway_structured=True,
            use_registered_cli=False,
        )

    # Unknown Online provider with no injected transport: fail closed.
    return OnlineTransportBinding(
        execution_role="online",
        provider=requested,
        transport=TRANSPORT_UNRESOLVED,
        selection_source=SELECTION_EXPLICIT_REQUEST,
        resolution_error="provider_not_registered",
        use_gateway_structured=False,
        use_registered_cli=False,
    )


def extract_online_stage_payload(
    online_stage: Mapping[str, Any] | None,
) -> tuple[Any, str, dict[str, Any]]:
    """Canonical Online stage unwrapping for callers.

    UnifiedRuntime stores the invoker result at ``receipt["online"]["response"]``.
    That invoker result itself carries domain output under ``response`` and the
    physical transport text under ``raw_response``.

    Returns:
      (domain_response, raw_response, invoker_payload)
    """
    if not isinstance(online_stage, Mapping):
        return "", "", {}
    invoker_payload = online_stage.get("response", {})
    if not isinstance(invoker_payload, Mapping):
        # Stage response was a bare scalar; treat as domain body.
        return invoker_payload, str(invoker_payload or ""), {}
    domain = invoker_payload.get("response", "")
    raw = str(invoker_payload.get("raw_response", "") or "")
    return domain, raw, dict(invoker_payload)


def normalize_online_invoker_payload(
    *,
    provider: str,
    task_id: str,
    invoked: bool,
    output_delivered: bool,
    gate_passed: bool,
    provider_call_count: int,
    response: Any = "",
    raw_response: str = "",
    usage: Mapping[str, Any] | None = None,
    error: str = "",
    evidence_refs: list[str] | None = None,
    transport: str = "",
    selection_source: str = "",
    execution_role: str = "online",
    extra: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Stable Online invoker payload contract for all transports.

    Required fields:
      provider, task_id, invoked, output_delivered, gate_passed,
      provider_call_count, response, raw_response, usage, error, evidence_refs

    Optional binding metadata:
      execution_role, transport, selection_source
    """
    payload: dict[str, Any] = {
        "provider": str(provider or ""),
        "task_id": str(task_id or ""),
        "invoked": bool(invoked),
        "output_delivered": bool(output_delivered),
        "gate_passed": bool(gate_passed),
        "provider_call_count": int(provider_call_count or 0),
        "response": response,
        "raw_response": str(raw_response or ""),
        "usage": dict(usage) if isinstance(usage, Mapping) else {},
        "error": str(error or ""),
        "evidence_refs": [str(ref) for ref in (evidence_refs or [])],
        "execution_role": str(execution_role or "online"),
        "transport": str(transport or ""),
        "selection_source": str(selection_source or ""),
    }
    if isinstance(extra, Mapping):
        for key, value in extra.items():
            if key not in payload:
                payload[str(key)] = value
    return payload


def resolve_registered_online_cli_spec(
    provider: str,
    *,
    command: tuple[str, ...] | list[str] | str | None = None,
    timeout_sec: float = 120.0,
    environ: Mapping[str, str] | None = None,
) -> OnlineCliSpec:
    """Resolve a registered provider command without invoking it.

    Provider-specific flags remain an edge concern.  The resolver accepts an
    explicit argv, then a provider-specific ``*_COMMAND`` environment value,
    and finally a configured/discovered binary. It never shells out or treats
    presence as a live-consumption claim.
    """
    key = str(provider or "").strip().lower()
    metadata = ONLINE_CLI_SPEC_REGISTRY.get(key)
    if metadata is None:
        raise ValueError("provider_not_registered")
    env = dict(environ or os.environ)
    resolved_command: tuple[str, ...]
    if isinstance(command, str):
        resolved_command = tuple(shlex.split(command))
    elif command is not None:
        resolved_command = tuple(str(part) for part in command)
    else:
        configured_command = str(env.get(metadata["command_env"], "") or "").strip()
        configured_binary = str(env.get(metadata["binary_env"], "") or "").strip()
        if configured_command:
            resolved_command = tuple(shlex.split(configured_command))
        elif configured_binary:
            resolved_command = tuple(shlex.split(configured_binary))
        else:
            binary = shutil.which(metadata["binary_name"])
            if not binary:
                raise ValueError("provider_binary_not_found")
            resolved_command = (binary,)
    spec = OnlineCliSpec(provider=key, command=resolved_command, timeout_sec=timeout_sec)
    spec.validate()
    return spec


def build_subprocess_online_invoker(
    spec: OnlineCliSpec,
    *,
    runner: Callable[..., Any] = subprocess.run,
    include_local_context: bool = True,
) -> Callable[[Mapping[str, Any]], dict[str, Any]]:
    """Build a no-shell Online CLI invoker with explicit receipt fields."""

    spec.validate()

    def invoke(context: Mapping[str, Any]) -> dict[str, Any]:
        task_id = str(context.get("task_id", ""))
        prompt = str(context.get("online_prompt") or context.get("task_statement") or "")
        payload = str(context.get("online_payload") or "")
        local_context_forwarded = False
        capability_context_forwarded = False
        if include_local_context:
            local_stage = context.get("local", {})
            local_response = local_stage.get("response", {}) if isinstance(local_stage, Mapping) else {}
            local_outputs = local_response.get("local_outputs", {}) if isinstance(local_response, Mapping) else {}
            if local_outputs:
                prompt += "\n\n[LOCAL_ASSIST_CONTEXT]\n" + json.dumps(
                    local_outputs,
                    ensure_ascii=False,
                    sort_keys=True,
                    default=str,
                )
                local_context_forwarded = True
            capability_results = context.get("capability_results", {})
            if capability_results:
                compressed = bool(context.get("capability_context_compressed"))
                prompt += (
                    "\n\n[CAPABILITY_EVIDENCE_SUMMARY]\n"
                    if compressed
                    else "\n\n[CAPABILITY_CONTEXT]\n"
                ) + json.dumps(
                    _capability_evidence_summary(capability_results)
                    if compressed
                    else capability_results,
                    ensure_ascii=False,
                    sort_keys=True,
                    default=str,
                )
                capability_context_forwarded = True
        stdin = f"{prompt}\n\n[PAYLOAD]\n{payload}" if payload else prompt
        try:
            result = runner(
                list(spec.command),
                input=stdin,
                capture_output=True,
                text=True,
                timeout=spec.timeout_sec,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            return normalize_online_invoker_payload(
                provider=spec.provider,
                task_id=task_id,
                invoked=True,
                output_delivered=False,
                gate_passed=False,
                provider_call_count=1,
                response="",
                raw_response="",
                usage={},
                error="provider_timeout",
                evidence_refs=[f"online:{spec.provider}:{task_id}:timeout"],
                transport=TRANSPORT_REGISTERED_CLI,
                selection_source=SELECTION_EXPLICIT_REQUEST,
                extra={"returncode": None, "stderr": str(exc)},
            )
        except OSError as exc:
            return normalize_online_invoker_payload(
                provider=spec.provider,
                task_id=task_id,
                invoked=False,
                output_delivered=False,
                gate_passed=False,
                provider_call_count=0,
                response="",
                raw_response="",
                usage={},
                error="provider_not_invoked",
                evidence_refs=[f"online:{spec.provider}:{task_id}:not_invoked"],
                transport=TRANSPORT_REGISTERED_CLI,
                selection_source=SELECTION_EXPLICIT_REQUEST,
                extra={"returncode": None, "stderr": str(exc)},
            )
        stdout = str(getattr(result, "stdout", "") or "")
        stderr = str(getattr(result, "stderr", "") or "")
        returncode = int(getattr(result, "returncode", 1))
        delivered = bool(stdout.strip())
        return normalize_online_invoker_payload(
            provider=spec.provider,
            task_id=task_id,
            invoked=True,
            output_delivered=delivered,
            gate_passed=returncode == 0 and delivered,
            provider_call_count=1,
            response=stdout,
            raw_response=stdout,
            usage={},
            error="" if returncode == 0 and delivered else "provider_subprocess_failed",
            evidence_refs=(
                [f"online:{spec.provider}:{task_id}:subprocess"]
                + ([f"online:{spec.provider}:{task_id}:local_context_forwarded"] if local_context_forwarded else [])
                + ([f"online:{spec.provider}:{task_id}:capability_context_forwarded"] if capability_context_forwarded else [])
                + ([f"online:{spec.provider}:{task_id}:compressed_context_applied"] if context.get("capability_context_compressed") else [])
            ),
            transport=TRANSPORT_REGISTERED_CLI,
            selection_source=SELECTION_EXPLICIT_REQUEST,
            extra={"returncode": returncode, "stderr": stderr},
        )

    return invoke


def build_registered_online_invoker(
    provider: str,
    *,
    command: tuple[str, ...] | list[str] | str | None = None,
    timeout_sec: float = 120.0,
    environ: Mapping[str, str] | None = None,
    runner: Callable[..., Any] = subprocess.run,
    include_local_context: bool = True,
) -> Callable[[Mapping[str, Any]], dict[str, Any]]:
    """Build the single provider-neutral Online edge adapter.

    Provider-specific command discovery is intentionally kept at this edge.
    The returned callable has the same contract for Gemini, Grok, Codex, and
    OpenAI and is consumed by :class:`UnifiedRuntime`; it does not create a
    second planner, receipt, verifier, or learning path.
    """
    spec = resolve_registered_online_cli_spec(
        provider,
        command=command,
        timeout_sec=timeout_sec,
        environ=environ,
    )
    invoker = build_subprocess_online_invoker(
        spec,
        runner=runner,
        include_local_context=include_local_context,
    )

    # Real provider subprocesses require a canonical OnlineExecutionDecision.
    # Custom runners remain available for deterministic/injected tests.
    if runner is subprocess.run:
        def guarded_invoke(context: Mapping[str, Any]) -> dict[str, Any]:
            from nexus.services.online_execution_policy import physical_online_authorized

            task_id = str(context.get("task_id", ""))
            if not physical_online_authorized(context, injected_transport=False):
                return normalize_online_invoker_payload(
                    provider=spec.provider,
                    task_id=task_id,
                    invoked=False,
                    output_delivered=False,
                    gate_passed=False,
                    provider_call_count=0,
                    response="",
                    raw_response="",
                    usage={},
                    error="online_execution_not_authorized",
                    evidence_refs=[f"online:{spec.provider}:{task_id}:authorization_required"],
                    transport=TRANSPORT_REGISTERED_CLI,
                    selection_source=SELECTION_EXPLICIT_REQUEST,
                )
            return invoker(context)

        return guarded_invoke
    return invoker


def _build_default_memory_retrieval_adapter(project_root: str | Path) -> Any:
    from nexus.services.local_heal.memory_retrieval_adapter import (
        FindingsMemoryLessonStore,
        LocalJsonlLessonStore,
        MemoryRepositoryLessonStore,
        MemoryRetrievalAdapter,
        NexusCompositeLessonStore,
    )

    root = Path(project_root).expanduser().resolve()
    return MemoryRetrievalAdapter(
        store=NexusCompositeLessonStore(
            [
                LocalJsonlLessonStore(
                    path=root / ".nexus" / "reports" / "learn" / "learning_closure.jsonl"
                ),
                FindingsMemoryLessonStore(project_root=root),
                MemoryRepositoryLessonStore(project_root=root),
            ]
        )
    )


def build_local_memory_capability_invoker(
    project_root: str | Path,
    *,
    adapter: Any = None,
    limit: int = 5,
) -> Callable[[Mapping[str, Any]], dict[str, Any]]:
    """Build the bounded, read-only Local memory edge for the shared runtime.

    The adapter owns backend selection and provenance filtering; this edge
    only binds the task identity, query, and a capability receipt.  A miss is
    a valid read result, while a retrieval failure remains gate-failed.
    """
    if adapter is None:
        adapter = _build_default_memory_retrieval_adapter(project_root)

    bounded_limit = max(1, min(int(limit), 20))

    def invoke(context: Mapping[str, Any]) -> dict[str, Any]:
        task_id = str(context.get("task_id", ""))
        query = str(
            context.get("task_statement")
            or context.get("online_prompt")
            or ""
        ).strip()
        try:
            lessons = list(adapter.retrieve(query_text=query, limit=bounded_limit))
            metadata = dict(getattr(adapter, "last_metadata", {}) or {})
            status = str(metadata.get("status", "ok") or "ok")
            gate_passed = status == "ok"
            evidence_refs = [f"memory:{task_id}:retrieval_attempted"]
            evidence_refs.append(
                f"memory:{task_id}:{'hit' if lessons else 'no_match'}"
            )
            return {
                "task_id": task_id,
                "invoked": True,
                "gate_passed": gate_passed,
                "outcome_contributed": bool(lessons),
                "evidence": "MemoryRetrievalAdapter.retrieve",
                "evidence_refs": evidence_refs,
                "response": {
                    "query": query,
                    "lessons": [
                        {
                            "finding_id": lesson.finding_id,
                            "summary": lesson.summary,
                            "relevance_score": lesson.relevance_score,
                            "provenance": lesson.provenance,
                            "source": lesson.source,
                            "pattern_type": lesson.pattern_type,
                            "task_id": lesson.task_id,
                        }
                        for lesson in lessons
                    ],
                    "metadata": metadata,
                },
            }
        except Exception as exc:  # fail closed in the shared receipt
            return {
                "task_id": task_id,
                "invoked": True,
                "gate_passed": False,
                "evidence": "MemoryRetrievalAdapter.retrieve",
                "evidence_refs": [f"memory:{task_id}:retrieval_exception"],
                "error": f"{exc.__class__.__name__}:{exc}",
            }

    return invoke


def build_local_search_ranking_capability_invoker(
    project_root: str | Path,
    *,
    adapter: Any = None,
    limit: int = 5,
) -> Callable[[Mapping[str, Any]], dict[str, Any]]:
    """Build a bounded Local semantic retrieval/ranking capability edge."""
    if adapter is None:
        adapter = _build_default_memory_retrieval_adapter(project_root)
    bounded_limit = max(1, min(int(limit), 20))

    def invoke(context: Mapping[str, Any]) -> dict[str, Any]:
        task_id = str(context.get("task_id", ""))
        query = str(
            context.get("task_statement")
            or context.get("online_prompt")
            or ""
        ).strip()
        route = context.get("route", {})
        route = route if isinstance(route, Mapping) else {}
        anchor_symbol = str(route.get("anchor_symbol", "") or "")
        anchor_file = str(route.get("anchor_file", "") or "")
        try:
            lessons = list(
                adapter.retrieve_reranked(
                    query_text=query,
                    anchor_symbol=anchor_symbol,
                    anchor_file=anchor_file,
                    limit=bounded_limit,
                    task_id=task_id,
                )
            )
            metadata = dict(getattr(adapter, "last_metadata", {}) or {})
            status = str(metadata.get("status", "ok") or "ok")
            gate_passed = status == "ok"
            evidence_refs = [f"search:{task_id}:retrieval_attempted"]
            evidence_refs.append(f"search:{task_id}:{'ranked' if lessons else 'no_match'}")
            return {
                "task_id": task_id,
                "invoked": True,
                "gate_passed": gate_passed,
                "outcome_contributed": bool(lessons),
                "evidence": "MemoryRetrievalAdapter.retrieve_reranked",
                "evidence_refs": evidence_refs,
                "response": {
                    "query": query,
                    "anchor_symbol": anchor_symbol,
                    "anchor_file": anchor_file,
                    "selected_ids": [lesson.finding_id for lesson in lessons],
                    "results": [
                        {
                            "finding_id": lesson.finding_id,
                            "summary": lesson.summary,
                            "relevance_score": lesson.relevance_score,
                            "provenance": lesson.provenance,
                            "source": lesson.source,
                            "pattern_type": lesson.pattern_type,
                            "task_id": lesson.task_id,
                        }
                        for lesson in lessons
                    ],
                    "metadata": metadata,
                },
            }
        except Exception as exc:  # fail closed in the shared receipt
            return {
                "task_id": task_id,
                "invoked": True,
                "gate_passed": False,
                "evidence": "MemoryRetrievalAdapter.retrieve_reranked",
                "evidence_refs": [f"search:{task_id}:retrieval_exception"],
                "error": f"{exc.__class__.__name__}:{exc}",
            }

    return invoke


def build_local_ast_capability_invoker(
    project_root: str | Path,
    *,
    max_files: int = 5,
) -> Callable[[Mapping[str, Any]], dict[str, Any]]:
    """Build a bounded, read-only AST/code-intel capability edge."""
    root = Path(project_root).expanduser().resolve()
    bounded_files = max(1, min(int(max_files), 5))

    def invoke(context: Mapping[str, Any]) -> dict[str, Any]:
        task_id = str(context.get("task_id", ""))
        route = context.get("route", {})
        route = route if isinstance(route, Mapping) else {}
        raw_files = route.get("target_files") or route.get("target_file") or ()
        if isinstance(raw_files, (str, Path)):
            raw_files = (raw_files,)
        files: list[Path] = []
        rejected: list[str] = []
        for raw in list(raw_files or ())[:bounded_files]:
            candidate = (root / str(raw)).resolve() if not Path(str(raw)).is_absolute() else Path(str(raw)).resolve()
            try:
                candidate.relative_to(root)
            except ValueError:
                rejected.append(f"outside_project_root:{candidate}")
                continue
            files.append(candidate)
        if not files:
            return {
                "task_id": task_id,
                "invoked": True,
                "gate_passed": False,
                "evidence": "RuntimeASTExtractor.extract_from_file",
                "evidence_refs": [f"ast:{task_id}:no_safe_target"],
                "error": "ast_target_required",
                "response": {"files": [], "rejected": rejected},
            }

        try:
            from nexus.services.local_heal.evidence_graph import RuntimeASTExtractor

            nodes: list[dict[str, Any]] = []
            edges: list[dict[str, Any]] = []
            risks: list[str] = list(rejected)
            for file_path in files:
                file_nodes, file_edges, file_risks = RuntimeASTExtractor.extract_from_file(str(file_path))
                nodes.extend(file_nodes)
                edges.extend(file_edges)
                risks.extend(file_risks)
            fatal_risks = tuple(
                risk for risk in risks
                if str(risk).startswith(("file_not_found:", "ast_parse_error:"))
            )
            gate_passed = bool(nodes) and not fatal_risks
            return {
                "task_id": task_id,
                "invoked": True,
                "gate_passed": gate_passed,
                "outcome_contributed": bool(nodes),
                "evidence": "RuntimeASTExtractor.extract_from_file",
                "evidence_refs": [
                    f"ast:{task_id}:extracted",
                    *[f"ast:{task_id}:file:{path.name}" for path in files],
                ],
                "response": {
                    "files": [str(path) for path in files],
                    "node_count": len(nodes),
                    "edge_count": len(edges),
                    "nodes": nodes[:50],
                    "edges": edges[:100],
                    "risks": risks,
                },
            }
        except Exception as exc:  # fail closed in the shared receipt
            return {
                "task_id": task_id,
                "invoked": True,
                "gate_passed": False,
                "evidence": "RuntimeASTExtractor.extract_from_file",
                "evidence_refs": [f"ast:{task_id}:exception"],
                "error": f"{exc.__class__.__name__}:{exc}",
            }

    return invoke


def build_prompt_compression_capability_invoker(
    *,
    max_chars: int = 4096,
) -> Callable[[Mapping[str, Any]], dict[str, Any]]:
    """Build a deterministic, receipt-backed context compression edge."""
    bounded_max_chars = max(256, min(int(max_chars), 32_000))

    def _text(value: Any) -> str:
        return str(value or "")

    def _compact(value: Any) -> str:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)

    def invoke(context: Mapping[str, Any]) -> dict[str, Any]:
        task_id = str(context.get("task_id", ""))
        prompt = _text(context.get("online_prompt") or context.get("task_statement"))
        payload = _text(context.get("online_payload"))
        capability_results = context.get("capability_results", {})
        capability_results = capability_results if isinstance(capability_results, Mapping) else {}
        raw_context = _compact(
            {
                "prompt": prompt,
                "payload": payload,
                "capability_results": capability_results,
            }
        )
        original_chars = len(raw_context)
        compacted = raw_context
        truncated = False
        if original_chars > bounded_max_chars:
            cap_summary = {
                str(name): {
                    "status": str(value.get("status", "")) if isinstance(value, Mapping) else "",
                    "evidence_refs": list(value.get("evidence_refs", []) or [])[:4]
                    if isinstance(value, Mapping)
                    else [],
                }
                for name, value in capability_results.items()
            }
            # Reduce prompt/payload together until the serialized context fits
            # while preserving a valid JSON object and capability evidence keys.
            for field_budget in range(bounded_max_chars, 0, -64):
                prompt_budget = max(32, field_budget // 2)
                payload_budget = max(32, field_budget - prompt_budget)
                candidate = {
                    "prompt": prompt[:prompt_budget],
                    "payload": payload[:payload_budget],
                    "capability_results": cap_summary,
                    "truncated": True,
                }
                candidate_text = _compact(candidate)
                if len(candidate_text) <= bounded_max_chars:
                    compacted = candidate_text
                    truncated = True
                    break
            else:
                compacted = _compact(
                    {
                        "prompt": "",
                        "payload": "",
                        "capability_results": {},
                        "capability_keys": list(cap_summary)[:8],
                        "truncated": True,
                    }
                )
                truncated = True
        compressed_chars = len(compacted)
        gate_passed = bool(original_chars and compacted and compressed_chars <= original_chars)
        evidence_refs = [f"compression:{task_id}:measured"]
        if truncated:
            evidence_refs.append(f"compression:{task_id}:truncated")
        return {
            "task_id": task_id,
            "invoked": True,
            "gate_passed": gate_passed,
            "outcome_contributed": gate_passed,
            "evidence": "bounded_json_context_compression",
            "evidence_refs": evidence_refs,
            "response": {
                "original_context_chars": original_chars,
                "compressed_context_chars": compressed_chars,
                "compression_ratio": round(1.0 - (compressed_chars / original_chars), 4)
                if original_chars
                else 0.0,
                "truncated": truncated,
                "compressed_context": compacted,
            },
        }

    return invoke


def build_structured_online_invoker(
    ask_structured: Callable[..., Any],
    *,
    phase: str = "R",
    model_name: str | None = None,
    output_schema: Mapping[str, Any] | None = None,
    provider: str = "gateway",
    transport: str = TRANSPORT_STRUCTURED_CALLABLE,
    selection_source: str = SELECTION_EXPLICIT_REQUEST,
) -> Callable[[Mapping[str, Any]], dict[str, Any]]:
    """Adapt a compatibility structured transport into the canonical seam.

    This is an edge adapter for old fixtures or transports only.  Planner,
    receipt, verifier, and learning ownership stays in ``UnifiedRuntime``.
    """

    def invoke(context: Mapping[str, Any]) -> dict[str, Any]:
        result = ask_structured(
            prompt=str(context.get("online_prompt") or context.get("task_statement") or ""),
            payload=str(context.get("online_payload") or ""),
            phase=str(context.get("online_phase") or phase),
            output_schema=dict(context.get("online_output_schema") or output_schema or {}),
            model_name=context.get("online_model_name") or model_name,
        )
        if isinstance(result, tuple) and len(result) >= 2:
            structured, raw = result[0], result[1]
        else:
            structured, raw = result, ""
        response = structured if isinstance(structured, Mapping) else str(raw or structured or "")
        delivered = bool(response)
        task_id = str(context.get("task_id", ""))
        usage: dict[str, Any] = {}
        if isinstance(structured, Mapping):
            maybe_usage = structured.get("usage")
            if isinstance(maybe_usage, Mapping):
                usage = dict(maybe_usage)
            for key in ("tokens_used", "token_capture_status", "gateway_token_source"):
                if key in structured and key not in usage:
                    usage[key] = structured.get(key)
        return normalize_online_invoker_payload(
            provider=provider,
            task_id=task_id,
            invoked=True,
            output_delivered=delivered,
            gate_passed=delivered,
            provider_call_count=1 if delivered else 0,
            response=response,
            raw_response=str(raw or ""),
            usage=usage,
            error="" if delivered else "structured_transport_empty_response",
            evidence_refs=[f"online:{provider}:{task_id}:structured_transport"],
            transport=transport,
            selection_source=selection_source,
        )

    return invoke


class UnifiedRuntime:
    """Execute one task through a shared planner and emit one receipt.

    This class does not fabricate provider success.  A missing callable,
    provider exception, missing invocation flag, or missing verifier/learning
    result remains visible in the receipt and prevents completion.
    """

    def __init__(self, *, planner: CapabilityPlanner | None = None, local_service: Any = None) -> None:
        self._planner = planner or CapabilityPlanner()
        self._local_service = local_service

    def run(
        self,
        request: UnifiedRuntimeRequest,
        *,
        online_invoker: Callable[[Mapping[str, Any]], Mapping[str, Any]] | None = None,
        capability_invokers: Mapping[str, Callable[[Mapping[str, Any]], Mapping[str, Any]]] | None = None,
        verifier: Callable[[Mapping[str, Any]], Mapping[str, Any]] | None = None,
        learning: Callable[[Mapping[str, Any]], Mapping[str, Any]] | None = None,
        receipt_path: str | Path | None = None,
    ) -> dict[str, Any]:
        request.validate()
        planner_route = dict(request.route)
        planner_route.setdefault("local_enabled", request.local_enabled)
        plan = self._planner.plan(
            task_desc=request.task_statement,
            task_type=request.task_type,
            route=planner_route,
            pillars=dict(request.pillars),
            codeintel=dict(request.codeintel),
            phase_trace=dict(request.phase_trace),
            budget=dict(request.budget),
            skills=[dict(item) for item in request.skills],
        )
        plan_payload = plan.to_dict()
        planner_stage = _stage(
            "planner",
            status="SUCCEEDED",
            invoked=True,
            evidence_present=True,
            gate_passed=True,
            evidence_refs=["runtime:planner_invoked"],
            selected_capabilities=list(plan.selected_capabilities),
            plan_schema=plan.schema_version,
            plan_hash=_hash_json(plan_payload),
        )

        stages: dict[str, dict[str, Any]] = {"planner": planner_stage}
        local_stage = self._run_local(request, plan_payload)
        if request.local_enabled:
            stages["local"] = local_stage
        else:
            stages["local"] = _stage("local", status="NOT_REQUESTED", reason="local_route_disabled")

        capability_results: dict[str, dict[str, Any]] = {}
        capability_context = {
            "schema": REQUEST_SCHEMA,
            "task_id": request.task_id,
            "workspace_revision": request.workspace_revision,
            "task_statement": request.task_statement,
            "task_type": request.task_type,
            "route": dict(request.route),
            "planner": plan_payload,
            "local": local_stage,
            "online_prompt": request.online_prompt,
            "online_payload": request.online_payload,
            "capability_results": capability_results,
        }
        for capability_name, invoker in dict(capability_invokers or {}).items():
            if capability_name not in plan.selected_capabilities:
                continue
            if not callable(invoker):
                result: Any = {
                    "task_id": request.task_id,
                    "invoked": False,
                    "gate_passed": False,
                    "evidence_refs": [f"capability:{capability_name}:{request.task_id}:not_callable"],
                }
            else:
                try:
                    result = invoker(capability_context)
                except Exception as exc:  # fail closed in the shared receipt
                    result = {
                        "task_id": request.task_id,
                        "invoked": True,
                        "gate_passed": False,
                        "evidence_refs": [f"capability:{capability_name}:{request.task_id}:exception"],
                        "error": f"{exc.__class__.__name__}:{exc}",
                    }
            capability_results[capability_name] = _capability_stage(
                capability_name,
                request.task_id,
                result,
            )

        effective_online_prompt = request.online_prompt
        capability_context_compressed = False
        compression_stage = capability_results.get("prompt_compression", {})
        compression_data = compression_stage.get("response", {}) if isinstance(compression_stage, Mapping) else {}
        compression_response = compression_data.get("response", {}) if isinstance(compression_data, Mapping) else {}
        compressed_context = compression_response.get("compressed_context") if isinstance(compression_response, Mapping) else None
        if (
            compression_stage.get("status") == "SUCCEEDED"
            and isinstance(compressed_context, str)
            and compressed_context
        ):
            effective_online_prompt = compressed_context
            capability_context_compressed = True

        from nexus.services.online_execution_policy import (
            decision_from_context,
            resolve_online_execution_decision,
        )

        route_map = dict(request.route) if isinstance(request.route, Mapping) else {}
        prior = decision_from_context(route_map)
        if prior is None:
            task_policy = str(route_map.get("online_policy") or "").strip().lower()
            injected_flag = bool(route_map.get("injected_transport", False))
            # Fixture default: online_invoker without product policy → injected transport.
            # Product auto/require must NOT force inject (physical path needs real auth).
            if online_invoker is not None and not task_policy and not injected_flag:
                task_policy = "auto"
                injected_flag = True
            online_decision = resolve_online_execution_decision(
                task_online_policy=task_policy,
                project_root=str(route_map.get("workspace_root") or "."),
                planner_online_needed=bool(request.online_enabled),
                injected_transport=injected_flag,
                requested_provider=str(route_map.get("provider") or ""),
            )
        else:
            online_decision = prior

        context: dict[str, Any] = {
            "schema": REQUEST_SCHEMA,
            "task_id": request.task_id,
            "workspace_revision": request.workspace_revision,
            "task_statement": request.task_statement,
            "task_type": request.task_type,
            "online_prompt": effective_online_prompt,
            "online_payload": request.online_payload,
            "online_phase": request.online_phase,
            "online_model_name": request.online_model_name,
            "online_output_schema": dict(request.online_output_schema or {}),
            "planner": plan_payload,
            "local": local_stage,
            "capability_results": capability_results,
            "capability_context_compressed": capability_context_compressed,
            "online_execution_decision": online_decision.to_dict(),
            "online_policy": online_decision.online_policy,
            "online_execution_requested": online_decision.online_execution_requested,
            "online_execution_authorized": online_decision.online_execution_authorized,
            "online_authorization_source": online_decision.online_authorization_source,
            "online_preflight_status": online_decision.preflight_status,
            "approved_online_providers": list(online_decision.approved_online_providers),
        }
        online_stage = self._run_online(request, online_invoker, context)
        if request.online_enabled:
            stages["online"] = online_stage
        else:
            stages["online"] = _stage("online", status="NOT_REQUESTED", reason="online_route_disabled")
        context["online"] = online_stage

        verifier_stage = self._run_callback("verifier", verifier, context, required=True)
        stages["verifier"] = verifier_stage
        context["verifier"] = verifier_stage
        learning_stage = self._run_callback("learning", learning, context, required=True)
        stages["learning"] = learning_stage
        context["learning"] = learning_stage

        required_stage_names = ["planner"]
        if request.local_enabled:
            required_stage_names.append("local")
        if request.online_enabled:
            required_stage_names.append("online")
        required_stage_names.extend(("verifier", "learning"))
        required_stages = [stages[name] for name in required_stage_names]
        required_stages.extend(capability_results.values())
        receipt_complete = all(
            bool(stage["invoked"] and stage["evidence_present"] and stage["gate_passed"])
            for stage in required_stages
        )
        outcome_contributed = any(bool(stage.get("outcome_contributed")) for stage in required_stages)
        evidence_refs = list(request.evidence_refs)
        for stage in stages.values():
            evidence_refs.extend(stage.get("evidence_refs", []))
        for capability_stage in capability_results.values():
            evidence_refs.extend(capability_stage.get("evidence_refs", []))
        claim_boundary = {
            "task_identity_shared": True,
            "planner_shared": planner_stage["invoked"],
            "local_online_continuation": bool(request.local_enabled and request.online_enabled and local_stage["invoked"] and online_stage["invoked"]),
            "receipt_complete": receipt_complete,
            "outcome_contributed": outcome_contributed,
            "value_measured": False,
            "public_claim_allowed": False,
        }
        capability_receipts: list[dict[str, Any]] = []
        online_capabilities = set()
        if isinstance(request.route, Mapping):
            online_capabilities = {
                str(name)
                for name in request.route.get("online_capabilities", ()) or ()
            }
        for name in plan.selected_capabilities:
            if name == "local_model_executor":
                delegated_to = "Local"
                stage = local_stage
                stage_name = "local"
            elif name in capability_results:
                delegated_to = str(capability_results[name].get("delegated_to", "Local"))
                stage = capability_results[name]
                stage_name = f"capability:{name}"
            elif name in online_capabilities:
                delegated_to = "Online"
                stage = online_stage
                stage_name = "online"
            else:
                delegated_to = "PlannerOnly"
                stage = {}
                stage_name = ""
            invoked = bool(stage.get("invoked", False))
            capability_receipts.append(
                {
                    "name": name,
                    "selected": True,
                    "selection_source": "CapabilityPlanner",
                    "delegated_to": delegated_to,
                    "stage": stage_name,
                    "invoked": invoked,
                    "evidence_present": bool(stage.get("evidence_present", False)),
                    "gate_passed": bool(stage.get("gate_passed", False)),
                    "outcome_contributed": bool(stage.get("outcome_contributed", False)),
                    "evidence_refs": list(stage.get("evidence_refs", []) or []),
                    "task_id": request.task_id,
                    "status": "INVOKED" if invoked else "SELECTED_NOT_EXECUTED",
                    "reason": "" if invoked else "planner_selected_no_runtime_executor",
                }
            )
        online_evidence_refs = [str(ref) for ref in online_stage.get("evidence_refs", []) or []]
        context_trace = {
            "task_id": request.task_id,
            "workspace_revision": request.workspace_revision,
            "task_statement_hash": hashlib.sha256(request.task_statement.encode("utf-8")).hexdigest(),
            "online_prompt_hash": _hash_json(effective_online_prompt),
            "online_payload_hash": _hash_json(request.online_payload),
            "capability_results_hash": _hash_json(capability_results),
            "selected_capabilities": list(plan.selected_capabilities),
            "capability_context_compressed": capability_context_compressed,
            "online_received_context": {
                "local_context_forwarded": any("local_context_forwarded" in ref for ref in online_evidence_refs),
                "capability_context_forwarded": any("capability_context_forwarded" in ref for ref in online_evidence_refs),
                "compressed_context_applied": any("compressed_context_applied" in ref for ref in online_evidence_refs),
            },
        }
        receipt = {
            "schema": RECEIPT_SCHEMA,
            "task_id": request.task_id,
            "workspace_revision": request.workspace_revision,
            "task_statement_hash": hashlib.sha256(request.task_statement.encode("utf-8")).hexdigest(),
            "context_trace": context_trace,
            "planner": planner_stage,
            "capabilities": capability_receipts,
            "delegation": {
                "planner": "Nexus",
                "local_assist": "Local" if request.local_enabled else "NOT_REQUESTED",
                "online_provider": "Online" if request.online_enabled else "NOT_REQUESTED",
                "verifier": "Hybrid",
                "learning": "Hybrid",
            },
            "local": local_stage,
            "capability_results": capability_results,
            "online": online_stage,
            "online_preflight": {
                "status": online_decision.preflight_status,
                "online_policy": online_decision.online_policy,
                "online_execution_requested": online_decision.online_execution_requested,
                "online_execution_authorized": online_decision.online_execution_authorized,
                "online_authorization_source": online_decision.online_authorization_source,
                "approved_online_providers": list(online_decision.approved_online_providers),
                "reason": online_decision.reason,
                "physical_invocation_allowed": online_decision.physical_invocation_allowed,
            },
            "verifier": verifier_stage,
            "learning": learning_stage,
            "stages": list(stages.values()),
            "evidence_refs": sorted(set(evidence_refs)),
            "receipt_complete": receipt_complete,
            "terminal_status": "SUCCEEDED" if receipt_complete else "INCOMPLETE",
            "claim_boundary": claim_boundary,
        }
        if receipt_path is not None:
            path = Path(receipt_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            receipt["receipt_path"] = str(path)
            path.write_text(json.dumps(receipt, indent=2, ensure_ascii=False), encoding="utf-8")
        return receipt

    def finalize_receipt(
        self,
        receipt: Mapping[str, Any],
        *,
        verifier: Mapping[str, Any],
        learning: Mapping[str, Any],
        outcome: Mapping[str, Any] | None = None,
        receipt_path: str | Path | None = None,
    ) -> dict[str, Any]:
        """Attach final verifier/learning evidence to an existing task receipt.

        Candidate-generation receipts intentionally stop before semantic
        completion.  This method closes that same receipt only when callers
        provide observed final-stage payloads; it never invokes a provider or
        infers success from a missing stage.
        """
        if not isinstance(receipt, Mapping) or receipt.get("schema") != RECEIPT_SCHEMA:
            raise ValueError("unsupported_receipt_schema")

        finalized = dict(receipt)

        def final_stage(name: str, payload: Mapping[str, Any]) -> dict[str, Any]:
            data = _mapping(payload)
            response_task_id = str(data.get("task_id", "") or "")
            task_identity_valid = not response_task_id or response_task_id == str(finalized.get("task_id", ""))
            invoked = bool(data.get("invoked", True))
            passed = bool(
                data.get(
                    "gate_passed",
                    str(data.get("status", "")).lower() in {"ok", "pass", "passed", "succeeded", "success"},
                )
            )
            refs = [str(ref) for ref in data.get("evidence_refs", []) or []]
            return _stage(
                name,
                status="SUCCEEDED" if task_identity_valid and invoked and passed else "FAILED",
                invoked=invoked,
                evidence_present=bool(refs or data.get("evidence")),
                gate_passed=task_identity_valid and passed,
                outcome_contributed=bool(data.get("outcome_contributed", False)),
                evidence_refs=refs,
                task_id=str(finalized.get("task_id", "")),
                response_task_id=response_task_id,
                task_identity_shared=task_identity_valid,
                reason=f"{name}_task_id_mismatch" if not task_identity_valid else "",
                response=data,
            )

        verifier_stage = final_stage("verifier", verifier)
        learning_stage = final_stage("learning", learning)
        finalized["verifier"] = verifier_stage
        finalized["learning"] = learning_stage
        stages = [dict(stage) for stage in finalized.get("stages", []) if isinstance(stage, Mapping)]
        replaced: set[str] = set()
        for index, stage in enumerate(stages):
            name = str(stage.get("name", ""))
            if name == "verifier":
                stages[index] = verifier_stage
                replaced.add(name)
            elif name == "learning":
                stages[index] = learning_stage
                replaced.add(name)
        if "verifier" not in replaced:
            stages.append(verifier_stage)
        if "learning" not in replaced:
            stages.append(learning_stage)
        finalized["stages"] = stages

        required_names = ["planner"]
        for name in ("local", "online"):
            stage = finalized.get(name, {})
            if isinstance(stage, Mapping) and stage.get("status") != "NOT_REQUESTED":
                required_names.append(name)
        required_names.extend(("verifier", "learning"))
        required_stages = [finalized.get(name, {}) for name in required_names]
        capability_results = finalized.get("capability_results", {})
        if isinstance(capability_results, Mapping):
            required_stages.extend(
                stage for stage in capability_results.values() if isinstance(stage, Mapping)
            )
        receipt_complete = all(
            isinstance(stage, Mapping)
            and bool(stage.get("invoked"))
            and bool(stage.get("evidence_present"))
            and bool(stage.get("gate_passed"))
            for stage in required_stages
        )
        outcome_contributed = any(bool(stage.get("outcome_contributed")) for stage in required_stages if isinstance(stage, Mapping))
        evidence_refs: set[str] = set(str(ref) for ref in finalized.get("evidence_refs", []) or [])
        for stage in stages:
            evidence_refs.update(str(ref) for ref in stage.get("evidence_refs", []) or [])
        if isinstance(capability_results, Mapping):
            for stage in capability_results.values():
                if isinstance(stage, Mapping):
                    evidence_refs.update(str(ref) for ref in stage.get("evidence_refs", []) or [])
        finalized["evidence_refs"] = sorted(evidence_refs)
        finalized["receipt_complete"] = receipt_complete
        finalized["terminal_status"] = "SUCCEEDED" if receipt_complete else "INCOMPLETE"
        claim_boundary = dict(finalized.get("claim_boundary", {}) or {})
        claim_boundary.update(
            {
                "receipt_complete": receipt_complete,
                "outcome_contributed": outcome_contributed,
                "value_measured": bool(outcome and outcome.get("value_measured", outcome.get("score") is not None)),
                "public_claim_allowed": False,
                "finalized": True,
            }
        )
        finalized["claim_boundary"] = claim_boundary
        finalized["finalization"] = {"verifier": "observed_payload", "learning": "observed_payload"}

        target = receipt_path or finalized.get("receipt_path")
        if target is not None:
            path = Path(target)
            path.parent.mkdir(parents=True, exist_ok=True)
            finalized["receipt_path"] = str(path)
            path.write_text(json.dumps(finalized, indent=2, ensure_ascii=False), encoding="utf-8")
        return finalized

    def _run_local(self, request: UnifiedRuntimeRequest, plan: Mapping[str, Any]) -> dict[str, Any]:
        if not request.local_enabled:
            return _stage("local", status="NOT_REQUESTED", reason="local_route_disabled")
        selected = set(plan.get("selected_capabilities", []) or [])
        if "local_model_executor" not in selected:
            return _stage("local", status="BLOCKED", reason="local_capability_not_selected")
        local_request = request.local_request
        shared_snapshot = dict(plan.get("signal_snapshot", {}) or {})
        if isinstance(local_request, Mapping):
            local_request = dict(local_request)
            local_request["planner_snapshot"] = shared_snapshot
        elif hasattr(local_request, "planner_snapshot"):
            try:
                local_request = replace(local_request, planner_snapshot=shared_snapshot)
            except TypeError:
                return _stage("local", status="BLOCKED", reason="local_request_not_replaceable")
        local_payload = _mapping(local_request)
        local_task_id = str(local_payload.get("task_id") or getattr(local_request, "task_id", ""))
        if local_task_id != request.task_id:
            return _stage("local", status="BLOCKED", reason="local_task_id_mismatch")
        if self._local_service is None:
            return _stage("local", status="NOT_RUN", reason="local_service_not_supplied")
        try:
            response = self._local_service.handle(local_request)
        except Exception as exc:
            return _stage("local", status="FAILED", reason=f"local_exception:{exc}")
        payload = _mapping(response)
        response_task_id = str(payload.get("task_id", "") or "")
        task_identity_valid = not response_task_id or response_task_id == request.task_id
        invoked = bool(payload.get("local_model_invoked", payload.get("invoked", False)))
        delivered = bool(payload.get("output_delivered", False))
        refs = [str(ref) for ref in payload.get("evidence_refs", []) or []]
        verifier_payload = payload.get("verifier_summary")
        local_verifier_status = ""
        if isinstance(verifier_payload, Mapping):
            local_verifier_status = str(verifier_payload.get("verifier_status", "") or "").lower()
        local_boundary_passed = task_identity_valid and invoked and delivered and (
            local_verifier_status in {"", "not_run", "pass", "passed"}
        )
        return _stage(
            "local",
            status="SUCCEEDED" if task_identity_valid and invoked and delivered else "FAILED",
            invoked=invoked,
            evidence_present=bool(payload.get("receipt_path") or refs),
            gate_passed=local_boundary_passed,
            outcome_contributed=bool(payload.get("outcome_contributed", False)),
            evidence_refs=refs,
            planner_snapshot_hash=_hash_json(shared_snapshot),
            task_id=request.task_id,
            response_task_id=response_task_id,
            task_identity_shared=task_identity_valid,
            reason="local_task_id_mismatch" if not task_identity_valid else "",
            response=payload,
        )

    @staticmethod
    def _run_online(
        request: UnifiedRuntimeRequest,
        invoker: Callable[[Mapping[str, Any]], Mapping[str, Any]] | None,
        context: Mapping[str, Any],
    ) -> dict[str, Any]:
        if not request.online_enabled:
            return _stage("online", status="NOT_REQUESTED", reason="online_route_disabled")
        if invoker is None:
            return _stage("online", status="NOT_RUN", reason="online_invoker_not_supplied")

        # Product deny / unauthorized decisions must never invoke Online transport
        # (including custom repair-style callables). Injected fixtures authorize
        # via online_execution_authorized=true with injected_test_transport source.
        from nexus.services.online_execution_policy import decision_from_context

        decision = decision_from_context(context)
        if decision is not None and not decision.online_execution_authorized:
            return _stage(
                "online",
                status="FAILED",
                invoked=False,
                evidence_present=True,
                gate_passed=False,
                reason=str(decision.reason or decision.preflight_status or "online_execution_not_authorized"),
                response={
                    "provider": str(decision.requested_provider or ""),
                    "task_id": str(context.get("task_id", "")),
                    "invoked": False,
                    "output_delivered": False,
                    "gate_passed": False,
                    "provider_call_count": 0,
                    "response": "",
                    "raw_response": "",
                    "usage": {},
                    "error": "online_execution_not_authorized",
                    "online_preflight_status": decision.preflight_status,
                    "online_authorization_source": decision.online_authorization_source,
                    "evidence_refs": [
                        f"online:{context.get('task_id')}:authorization_denied"
                    ],
                },
                evidence_refs=[f"online:{context.get('task_id')}:authorization_denied"],
                task_id=str(context.get("task_id", "")),
            )

        try:
            payload = _mapping(invoker(context))
        except Exception as exc:
            return _stage("online", status="FAILED", reason=f"online_exception:{exc}")
        response_task_id = str(payload.get("task_id", "") or "")
        task_identity_valid = not response_task_id or response_task_id == str(context.get("task_id", ""))
        invoked = bool(payload.get("invoked", False))
        delivered = bool(payload.get("output_delivered", payload.get("response")))
        refs = [str(ref) for ref in payload.get("evidence_refs", []) or []]
        return _stage(
            "online",
            status="SUCCEEDED" if task_identity_valid and invoked and delivered else "FAILED",
            invoked=invoked,
            evidence_present=bool(refs or payload.get("provider_call_count", 0)),
            gate_passed=task_identity_valid and bool(payload.get("gate_passed", False)),
            outcome_contributed=bool(payload.get("outcome_contributed", False)),
            evidence_refs=refs,
            task_id=str(context.get("task_id", "")),
            response_task_id=response_task_id,
            task_identity_shared=task_identity_valid,
            reason="online_task_id_mismatch" if not task_identity_valid else "",
            response=payload,
        )

    @staticmethod
    def _run_callback(
        name: str,
        callback: Callable[[Mapping[str, Any]], Mapping[str, Any]] | None,
        context: Mapping[str, Any],
        *,
        required: bool,
    ) -> dict[str, Any]:
        if callback is None:
            return _stage(name, status="NOT_RUN" if required else "NOT_REQUESTED", reason=f"{name}_callback_not_supplied")
        try:
            payload = _mapping(callback(context))
        except Exception as exc:
            return _stage(name, status="FAILED", reason=f"{name}_exception:{exc}")
        response_task_id = str(payload.get("task_id", "") or "")
        task_identity_valid = not response_task_id or response_task_id == str(context.get("task_id", ""))
        invoked = bool(payload.get("invoked", True))
        passed = bool(payload.get("gate_passed", payload.get("status", "").lower() in {"ok", "pass", "passed", "succeeded"}))
        refs = [str(ref) for ref in payload.get("evidence_refs", []) or []]
        return _stage(
            name,
            status="SUCCEEDED" if task_identity_valid and invoked and passed else "FAILED",
            invoked=invoked,
            evidence_present=bool(refs or payload.get("evidence")),
            gate_passed=task_identity_valid and passed,
            outcome_contributed=bool(payload.get("outcome_contributed", False)),
            evidence_refs=refs,
            task_id=str(context.get("task_id", "")),
            response_task_id=response_task_id,
            task_identity_shared=task_identity_valid,
            reason=f"{name}_task_id_mismatch" if not task_identity_valid else "",
            response=payload,
        )
