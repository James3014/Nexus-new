"""Provider-neutral Cloud Agent request/response boundary."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Mapping


CLOUD_AGENT_REQUEST_SCHEMA = "nexus.cloud_agent.request.v1"
CLOUD_AGENT_RESPONSE_SCHEMA = "nexus.cloud_agent.response.v1"


@dataclass(frozen=True)
class CloudAgentRequest:
    task_id: str
    workspace_revision: str
    bounded_context: str
    local_diagnosis: str
    semantic_assertions: tuple[str, ...]
    target_files: tuple[str, ...]
    allowed_mutation_scope: tuple[str, ...]
    provider: str
    model: str
    schema: str = CLOUD_AGENT_REQUEST_SCHEMA

    def __post_init__(self) -> None:
        self.validate()

    def validate(self) -> None:
        if self.schema != CLOUD_AGENT_REQUEST_SCHEMA:
            raise ValueError("unsupported_cloud_agent_request_schema")
        if not self.task_id.strip():
            raise ValueError("task_id_missing")
        if not self.workspace_revision.strip():
            raise ValueError("workspace_revision_missing")
        if not self.bounded_context.strip():
            raise ValueError("bounded_context_missing")
        if not self.provider.strip() or not self.model.strip():
            raise ValueError("provider_model_missing")
        if not self.target_files:
            raise ValueError("target_files_missing")
        if not self.allowed_mutation_scope:
            raise ValueError("allowed_mutation_scope_missing")
        if not set(self.target_files).issubset(set(self.allowed_mutation_scope)):
            raise ValueError("target_outside_allowed_scope")


@dataclass(frozen=True)
class CloudAgentResponse:
    task_id: str
    workspace_revision: str
    provider: str
    model: str
    response_identity: str
    candidate_payload: str = ""
    usage: dict[str, Any] = field(default_factory=dict)
    latency_sec: float = 0.0
    error: str = ""
    provider_call_confirmed: bool = False
    real_cloud_call: bool = False
    formal_workspace_mutated: bool = False
    route_truth_source: str = "CapabilityPlanner"
    candidate_isolation_required: bool = True
    schema: str = CLOUD_AGENT_RESPONSE_SCHEMA

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["claim_boundary"] = {
            "real_cloud_call": self.real_cloud_call,
            "candidate_isolation_required": self.candidate_isolation_required,
            "formal_workspace_mutated": self.formal_workspace_mutated,
            "outcome_contributed": False,
            "value_measured": False,
            "production_ready": False,
            "public_claim_allowed": False,
        }
        return payload


class CloudAgentAdapter:
    provider = "provider-neutral"
    model = ""
    is_real_provider = False

    def generate(self, request: CloudAgentRequest) -> CloudAgentResponse:
        raise NotImplementedError


class InjectedCloudAgentAdapter(CloudAgentAdapter):
    """Deterministic test adapter; never qualifies as a real cloud call."""

    provider = "injected"
    is_real_provider = False

    def __init__(self, generate_fn: Callable[[CloudAgentRequest], Mapping[str, Any]]) -> None:
        self._generate_fn = generate_fn

    def generate(self, request: CloudAgentRequest) -> CloudAgentResponse:
        try:
            raw = dict(self._generate_fn(request) or {})
        except Exception as exc:
            raw = {"error": f"adapter_error:{exc}"}
        return CloudAgentResponse(
            task_id=str(raw.get("task_id", request.task_id)),
            workspace_revision=str(raw.get("workspace_revision", request.workspace_revision)),
            provider=str(raw.get("provider", self.provider)),
            model=str(raw.get("model", request.model)),
            response_identity=str(raw.get("response_identity", "")),
            candidate_payload=str(raw.get("candidate_payload", "")),
            usage=dict(raw.get("usage", {}) or {}),
            latency_sec=float(raw.get("latency_sec", 0.0) or 0.0),
            error=str(raw.get("error", "")),
            provider_call_confirmed=True,
            real_cloud_call=False,
        )


def invoke_cloud_agent(adapter: CloudAgentAdapter, request: CloudAgentRequest) -> dict[str, Any]:
    request.validate()
    response = adapter.generate(request)
    if response.task_id != request.task_id or response.workspace_revision != request.workspace_revision:
        response = CloudAgentResponse(
            task_id=request.task_id,
            workspace_revision=request.workspace_revision,
            provider=response.provider,
            model=response.model,
            response_identity=response.response_identity,
            error="cloud_response_lineage_mismatch",
            provider_call_confirmed=response.provider_call_confirmed,
            real_cloud_call=False,
        )
    elif response.candidate_payload and not response.response_identity:
        response = CloudAgentResponse(
            task_id=response.task_id,
            workspace_revision=response.workspace_revision,
            provider=response.provider,
            model=response.model,
            response_identity=response.response_identity,
            usage=response.usage,
            latency_sec=response.latency_sec,
            error="response_identity_missing",
            provider_call_confirmed=response.provider_call_confirmed,
            real_cloud_call=False,
        )
    else:
        response = CloudAgentResponse(
            **{
                **asdict(response),
                "real_cloud_call": bool(adapter.is_real_provider and response.provider_call_confirmed and not response.error),
            }
        )
    return response.to_dict()
