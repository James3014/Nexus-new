from __future__ import annotations

from dataclasses import dataclass
import json
import os
from typing import Any, Callable
import urllib.request
import urllib.error


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


class OllamaLocalModelProvider(LocalModelProvider):
    def generate(self, request: LocalModelProviderRequest) -> LocalModelProviderResponse:
        call_allowed = os.environ.get("NEXUS_LOCAL_MODEL_CALL_ALLOWED") == "1"
        provider_name = os.environ.get("NEXUS_LOCAL_MODEL_PROVIDER", "").lower()
        
        if not call_allowed or provider_name != "ollama":
            return LocalModelProviderResponse(
                provider_invoked=True,
                model_called=False,
                model_name="",
                output_text="",
                error="provider_not_configured",
            )
            
        model_name = request.model_name or os.environ.get("NEXUS_LOCAL_MODEL_NAME", "").strip()
        if not model_name:
            return LocalModelProviderResponse(
                provider_invoked=True,
                model_called=False,
                model_name="",
                output_text="",
                error="model_name_missing",
            )
            
        url = os.environ.get("NEXUS_OLLAMA_URL", "http://127.0.0.1:11434/api/generate").strip()
        
        payload = {
            "model": model_name,
            "prompt": request.prompt,
            "stream": False
        }
        
        try:
            req_data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                url,
                data=req_data,
                headers={"Content-Type": "application/json"},
            )
            
            with urllib.request.urlopen(req, timeout=request.timeout_sec) as resp:
                resp_data = resp.read().decode("utf-8")
                resp_json = json.loads(resp_data)
                raw_text = resp_json.get("response", "")
                
                truncated = False
                if len(raw_text) > request.max_output_chars:
                    raw_text = raw_text[:request.max_output_chars]
                    truncated = True
                    
                return LocalModelProviderResponse(
                    provider_invoked=True,
                    model_called=True,
                    model_name=model_name,
                    output_text=raw_text,
                    output_truncated=truncated,
                )
        except urllib.error.HTTPError as e:
            return LocalModelProviderResponse(
                provider_invoked=True,
                model_called=False,
                model_name=model_name,
                output_text="",
                error=f"ollama_http_error_{e.code}: {e.reason}",
            )
        except urllib.error.URLError as e:
            return LocalModelProviderResponse(
                provider_invoked=True,
                model_called=False,
                model_name=model_name,
                output_text="",
                error=f"ollama_url_error: {str(e.reason)}",
            )
        except Exception as e:
            return LocalModelProviderResponse(
                provider_invoked=True,
                model_called=False,
                model_name=model_name,
                output_text="",
                error=f"ollama_internal_error: {str(e)}",
            )
