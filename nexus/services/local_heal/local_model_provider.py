from __future__ import annotations

from dataclasses import dataclass
import json
import os
import socket
import time
from typing import Any, Callable
import urllib.request
import urllib.error


@dataclass(frozen=True)
class LocalModelProviderRequest:
    task_id: str
    prompt: str
    evidence_refs: tuple[str, ...]
    model_name: str = ""
    timeout_sec: float = 120.0
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
    # C6 timeout telemetry
    requested_timeout_sec: float = 0.0
    elapsed_sec: float = 0.0
    effective_timeout_sec: float = 0.0


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
            requested_timeout_sec=request.timeout_sec,
            effective_timeout_sec=request.timeout_sec,
        )


class InjectedLocalModelProvider(LocalModelProvider):
    def __init__(self, generate_fn: Callable[[LocalModelProviderRequest], str]) -> None:
        self._generate_fn = generate_fn

    def generate(self, request: LocalModelProviderRequest) -> LocalModelProviderResponse:
        t0 = time.monotonic()
        try:
            raw_text = self._generate_fn(request)
            elapsed = time.monotonic() - t0
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
                requested_timeout_sec=request.timeout_sec,
                elapsed_sec=round(elapsed, 3),
                effective_timeout_sec=request.timeout_sec,
            )
        except Exception as e:
            elapsed = time.monotonic() - t0
            return LocalModelProviderResponse(
                provider_invoked=True,
                model_called=False,
                model_name=request.model_name,
                output_text="",
                error=f"injected_provider_error: {str(e)}",
                requested_timeout_sec=request.timeout_sec,
                elapsed_sec=round(elapsed, 3),
                effective_timeout_sec=request.timeout_sec,
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
                requested_timeout_sec=request.timeout_sec,
                effective_timeout_sec=request.timeout_sec,
            )
            
        model_name = request.model_name or os.environ.get("NEXUS_LOCAL_MODEL_NAME", "").strip()
        if not model_name:
            return LocalModelProviderResponse(
                provider_invoked=True,
                model_called=False,
                model_name="",
                output_text="",
                error="model_name_missing",
                requested_timeout_sec=request.timeout_sec,
                effective_timeout_sec=request.timeout_sec,
            )
            
        url = os.environ.get("NEXUS_OLLAMA_URL", "http://127.0.0.1:11434/api/generate").strip()
        
        payload = {
            "model": model_name,
            "prompt": request.prompt,
            "stream": False
        }
        
        t0 = time.monotonic()
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
                elapsed = time.monotonic() - t0
                
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
                    requested_timeout_sec=request.timeout_sec,
                    elapsed_sec=round(elapsed, 3),
                    effective_timeout_sec=request.timeout_sec,
                )
        except (socket.timeout, TimeoutError) as e:
            elapsed = time.monotonic() - t0
            return LocalModelProviderResponse(
                provider_invoked=True,
                model_called=False,
                model_name=model_name,
                output_text="",
                error=f"ollama_timeout: timed out after {elapsed:.1f}s (limit={request.timeout_sec}s)",
                timed_out=True,
                requested_timeout_sec=request.timeout_sec,
                elapsed_sec=round(elapsed, 3),
                effective_timeout_sec=request.timeout_sec,
            )
        except urllib.error.HTTPError as e:
            elapsed = time.monotonic() - t0
            return LocalModelProviderResponse(
                provider_invoked=True,
                model_called=False,
                model_name=model_name,
                output_text="",
                error=f"ollama_http_error_{e.code}: {e.reason}",
                requested_timeout_sec=request.timeout_sec,
                elapsed_sec=round(elapsed, 3),
                effective_timeout_sec=request.timeout_sec,
            )
        except urllib.error.URLError as e:
            elapsed = time.monotonic() - t0
            # urllib wraps socket.timeout inside URLError.reason
            is_timeout = isinstance(e.reason, socket.timeout) or isinstance(e.reason, TimeoutError)
            if is_timeout:
                return LocalModelProviderResponse(
                    provider_invoked=True,
                    model_called=False,
                    model_name=model_name,
                    output_text="",
                    error=f"ollama_timeout: timed out after {elapsed:.1f}s (limit={request.timeout_sec}s)",
                    timed_out=True,
                    requested_timeout_sec=request.timeout_sec,
                    elapsed_sec=round(elapsed, 3),
                    effective_timeout_sec=request.timeout_sec,
                )
            return LocalModelProviderResponse(
                provider_invoked=True,
                model_called=False,
                model_name=model_name,
                output_text="",
                error=f"ollama_url_error: {str(e.reason)}",
                requested_timeout_sec=request.timeout_sec,
                elapsed_sec=round(elapsed, 3),
                effective_timeout_sec=request.timeout_sec,
            )
        except Exception as e:
            elapsed = time.monotonic() - t0
            # Final safety net: detect timeout buried in generic exception
            err_str = str(e).lower()
            is_timeout = "timed out" in err_str or "timeout" in err_str
            if is_timeout:
                return LocalModelProviderResponse(
                    provider_invoked=True,
                    model_called=False,
                    model_name=model_name,
                    output_text="",
                    error=f"ollama_timeout: {str(e)}",
                    timed_out=True,
                    requested_timeout_sec=request.timeout_sec,
                    elapsed_sec=round(elapsed, 3),
                    effective_timeout_sec=request.timeout_sec,
                )
            return LocalModelProviderResponse(
                provider_invoked=True,
                model_called=False,
                model_name=model_name,
                output_text="",
                error=f"ollama_internal_error: {str(e)}",
                requested_timeout_sec=request.timeout_sec,
                elapsed_sec=round(elapsed, 3),
                effective_timeout_sec=request.timeout_sec,
            )
