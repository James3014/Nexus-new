from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class LocalModelProviderRequest:
    task_id: str
    prompt: str
    evidence_refs: tuple[str, ...]
    model_name: str = ""
    timeout_sec: float = 30.0
    max_output_chars: int = 4000


@dataclass(frozen=True)
class LocalModelProviderResponse:
    provider_invoked: bool
    model_called: bool
    model_name: str
    output_text: str
    error: str = ""
    timed_out: bool = False
    output_truncated: bool = False
    public_claim_allowed: bool = False
    production_ready: bool = False
    adapter_output_is_route_truth: bool = False
    behavior_changed: bool = False


class LocalModelProvider:
    def generate(self, request: LocalModelProviderRequest) -> LocalModelProviderResponse:
        raise NotImplementedError


class InertLocalModelProvider(LocalModelProvider):
    def generate(self, request: LocalModelProviderRequest) -> LocalModelProviderResponse:
        return LocalModelProviderResponse(
            provider_invoked=True,
            model_called=False,
            model_name="",
            output_text="",
            error="provider_not_configured",
        )


class InjectedLocalModelProvider(LocalModelProvider):
    def __init__(self, generate_fn: Callable[[LocalModelProviderRequest], str]) -> None:
        self._generate_fn = generate_fn

    def generate(self, request: LocalModelProviderRequest) -> LocalModelProviderResponse:
        try:
            raw_text = self._generate_fn(request)
            truncated = False
            if len(raw_text) > request.max_output_chars:
                raw_text = raw_text[:request.max_output_chars]
                truncated = True
                
            return LocalModelProviderResponse(
                provider_invoked=True,
                model_called=True,
                model_name=request.model_name,
                output_text=raw_text,
                output_truncated=truncated,
            )
        except Exception as e:
            return LocalModelProviderResponse(
                provider_invoked=True,
                model_called=False,
                model_name=request.model_name,
                output_text="",
                error=f"injected_provider_error: {str(e)}",
            )
