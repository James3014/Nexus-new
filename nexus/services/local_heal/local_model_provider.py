from __future__ import annotations

from dataclasses import dataclass, field, replace
import hashlib
import json
import os
import socket
import time
import uuid
from typing import Any, Callable
import urllib.request
import urllib.error

from nexus.services.local_heal.local_model_name_resolver import resolve_local_model_name


@dataclass(frozen=True)
class LocalModelProviderRequest:
    task_id: str
    prompt: str
    evidence_refs: tuple[str, ...]
    model_name: str = ""
    timeout_sec: float = 120.0
    max_output_chars: int = 4000
    options: dict[str, Any] | None = None
    think: bool | None = None
    api_type: str = "generate"
    # N30R-V3 Phase 2: caller-supplied phase for authoritative ledger records.
    # One of: "planning", "spec_gen", "patch", "retry", "judge", "proposer", ""
    phase: str = ""
    # N30R-V3.1: Linkage metrics
    attempt_id: str = ""
    execution_profile: str = ""


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
    # Ollama native metrics
    ollama_total_duration: int = 0
    ollama_load_duration: int = 0
    ollama_prompt_eval_count: int = 0
    ollama_prompt_eval_duration: int = 0
    ollama_eval_count: int = 0
    ollama_eval_duration: int = 0
    ollama_done_reason: str = ""
    ollama_metrics_available: bool = False



class LocalModelProvider:
    """Physical local provider boundary and explicit identity contract."""

    @property
    def provider_identity(self) -> str:
        return ""

    @property
    def model_identity(self) -> str:
        return ""

    @property
    def model_binding_mode(self) -> str:
        return "untagged"

    def generate(self, request: LocalModelProviderRequest) -> LocalModelProviderResponse:
        raise NotImplementedError


class InertLocalModelProvider(LocalModelProvider):
    @property
    def provider_identity(self) -> str:
        return "inert"

    @property
    def model_binding_mode(self) -> str:
        return "none"

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
    def __init__(
        self,
        generate_fn: Callable[[LocalModelProviderRequest], str],
        *,
        provider_identity: str = "",
        model_identity: str = "",
    ) -> None:
        self._generate_fn = generate_fn
        self._provider_identity = provider_identity
        self._model_identity = model_identity

    @property
    def provider_identity(self) -> str:
        return self._provider_identity

    @property
    def model_identity(self) -> str:
        return self._model_identity

    @property
    def model_binding_mode(self) -> str:
        return "fixed" if self._model_identity else "untagged"

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


@dataclass
class LedgerRecord:
    """N30R-V3 Phase 2: Per-invocation provider call record."""
    call_id:       str   # uuid4
    task_id:       str
    phase:         str   # planning / spec_gen / patch / retry / judge / proposer / unknown
    model:         str   # actual model sent to provider (resolved)
    prompt_hash:   str   # sha256[:16]
    response_hash: str   # sha256[:16]
    duration_sec:  float
    status:        str   # ok / error / timeout
    error:         str   # empty if ok
    attempt_id:    str = ""
    execution_profile: str = ""
    requested_model: str = ""
    resolved_model: str = ""
    model_resolution_source: str = ""
    model_alias_applied: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "call_id":       self.call_id,
            "task_id":       self.task_id,
            "phase":         self.phase,
            "model":         self.model,
            "prompt_hash":   self.prompt_hash,
            "response_hash": self.response_hash,
            "duration_sec":  self.duration_sec,
            "status":        self.status,
            "error":         self.error,
            "attempt_id":    self.attempt_id,
            "execution_profile": self.execution_profile,
            "requested_model": self.requested_model,
            "resolved_model": self.resolved_model,
            "model_resolution_source": self.model_resolution_source,
            "model_alias_applied": self.model_alias_applied,
        }


class RecordingLocalModelProvider(LocalModelProvider):
    """N30R-V3 Phase 2: Transparent wrapper that appends a LedgerRecord to
    ``self.ledger`` for every generate() call.
    """

    def __init__(self, inner: LocalModelProvider) -> None:
        self._inner = inner
        self.ledger: list[LedgerRecord] = []

    @property
    def provider_identity(self) -> str:
        return str(getattr(self._inner, "provider_identity", "") or "")

    @property
    def model_identity(self) -> str:
        return str(getattr(self._inner, "model_identity", "") or "")

    @property
    def model_binding_mode(self) -> str:
        return str(getattr(self._inner, "model_binding_mode", "untagged") or "untagged")

    @property
    def ledger_count(self) -> int:
        return len(self.ledger)

    def generate(self, request: LocalModelProviderRequest) -> LocalModelProviderResponse:
        t0 = time.monotonic()
        resp = None
        exc = None
        try:
            resp = self._inner.generate(request)
            return resp
        except Exception as e:
            exc = e
            raise
        finally:
            elapsed = round(time.monotonic() - t0, 4)
            ph = request.phase or "unknown"
            resolution = resolve_local_model_name(request.model_name)

            if exc is not None or resp is None:
                status_str = "error"
                error_str = f"exception: {str(exc)}" if exc is not None else "response_is_none"
                model_str = resolution.resolved_name or request.model_name
                resp_hash = hashlib.sha256(b"").hexdigest()[:16]
            else:
                status_str = "ok" if resp.model_called and not resp.error else (
                    "timeout" if resp.timed_out else "error"
                )
                error_str = resp.error or ""
                # model field = actual provider tag (resolved), not the alias
                model_str = resp.model_name or resolution.resolved_name or request.model_name
                resp_hash = hashlib.sha256((resp.output_text or "").encode("utf-8")).hexdigest()[:16]

            record = LedgerRecord(
                call_id=str(uuid.uuid4()),
                task_id=request.task_id,
                phase=ph,
                model=model_str,
                prompt_hash=hashlib.sha256(request.prompt.encode("utf-8")).hexdigest()[:16],
                response_hash=resp_hash,
                duration_sec=elapsed,
                status=status_str,
                error=error_str,
                attempt_id=request.attempt_id,
                execution_profile=request.execution_profile,
                requested_model=resolution.requested_name,
                resolved_model=resolution.resolved_name or model_str,
                model_resolution_source=resolution.resolution_source,
                model_alias_applied=resolution.alias_applied,
            )
            self.ledger.append(record)

    @property
    def ledger_summary(self) -> dict[str, Any]:
        """Aggregated per-phase call counts and total invocations."""
        by_phase: dict[str, int] = {}
        unknown_count = 0
        missing_attempt_id_count = 0
        missing_execution_profile_count = 0
        for r in self.ledger:
            by_phase[r.phase] = by_phase.get(r.phase, 0) + 1
            if r.phase == "unknown" or not r.phase:
                unknown_count += 1
            if not r.attempt_id:
                missing_attempt_id_count += 1
            if not r.execution_profile:
                missing_execution_profile_count += 1
        return {
            "total_calls": len(self.ledger),
            "by_phase": by_phase,
            "authoritative": True,
            "source": "recording_provider",
            "phase_complete": unknown_count == 0,
            "unknown_call_count": unknown_count,
            "missing_attempt_id_count": missing_attempt_id_count,
            "attempt_context_complete": missing_attempt_id_count == 0,
            "missing_execution_profile_count": missing_execution_profile_count,
            "profile_context_complete": missing_execution_profile_count == 0,
        }


class AuthorityBoundLocalModelProvider(LocalModelProvider):
    """Fail-closed model binding guard around the recording physical provider."""

    def __init__(self, inner: LocalModelProvider, *, resolved_model: str) -> None:
        self._inner = inner
        self._resolved_model = resolved_model
        self._sticky_failure_reason = ""
        self._last_actual_model = ""

    @property
    def provider_identity(self) -> str:
        return str(getattr(self._inner, "provider_identity", "") or "")

    @property
    def model_identity(self) -> str:
        return str(getattr(self._inner, "model_identity", "") or "")

    @property
    def model_binding_mode(self) -> str:
        return str(getattr(self._inner, "model_binding_mode", "untagged") or "untagged")

    @property
    def ledger(self) -> Any:
        return getattr(self._inner, "ledger", [])

    @property
    def ledger_summary(self) -> dict[str, Any]:
        summary = getattr(self._inner, "ledger_summary", {})
        return dict(summary) if isinstance(summary, dict) else {}

    @property
    def ledger_count(self) -> int:
        summary = self.ledger_summary
        if isinstance(summary.get("total_calls"), int):
            return int(summary["total_calls"])
        ledger = self.ledger
        return len(ledger) if hasattr(ledger, "__len__") else 0

    @property
    def sticky_failure_reason(self) -> str:
        return self._sticky_failure_reason

    @property
    def actual_model(self) -> str:
        return self._last_actual_model

    def _blocked_response(self, *, reported_model: str = "") -> LocalModelProviderResponse:
        reason = self._sticky_failure_reason or "local_model_provider_model_mismatch"
        self._last_actual_model = reported_model
        return LocalModelProviderResponse(
            provider_invoked=False,
            model_called=False,
            model_name=self._resolved_model,
            output_text="",
            error=reason,
        )

    def generate(self, request: LocalModelProviderRequest) -> LocalModelProviderResponse:
        if self._sticky_failure_reason:
            return self._blocked_response(reported_model=request.model_name)

        if request.model_name != self._resolved_model:
            self._sticky_failure_reason = "local_model_provider_request_model_mismatch"
            return self._blocked_response(reported_model=request.model_name)

        response = self._inner.generate(request)
        reported_model = str(getattr(response, "model_name", "") or "")
        self._last_actual_model = reported_model
        if reported_model != self._resolved_model:
            self._sticky_failure_reason = "local_model_provider_reported_model_mismatch"
            return replace(
                response,
                provider_invoked=bool(response.provider_invoked),
                model_called=False,
                model_name=self._resolved_model,
                output_text="",
                error=self._sticky_failure_reason,
            )
        return response


class OllamaLocalModelProvider(LocalModelProvider):
    @property
    def provider_identity(self) -> str:
        return "ollama"

    @property
    def model_binding_mode(self) -> str:
        return "request_bound"

    def generate(self, request: LocalModelProviderRequest) -> LocalModelProviderResponse:
        call_allowed = os.environ.get("NEXUS_LOCAL_MODEL_CALL_ALLOWED") == "1"
        provider_name = (os.environ.get("NEXUS_LOCAL_MODEL_PROVIDER") or os.environ.get("NEXUS_LOCAL_MODEL_EXECUTOR_PROVIDER") or "").lower()

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

        requested_model = request.model_name or os.environ.get("NEXUS_LOCAL_MODEL_NAME", "").strip()
        if not requested_model:
            return LocalModelProviderResponse(
                provider_invoked=True,
                model_called=False,
                model_name="",
                output_text="",
                error="model_name_missing",
                requested_timeout_sec=request.timeout_sec,
                effective_timeout_sec=request.timeout_sec,
            )

        # Single resolution boundary: every Ollama HTTP call uses the canonical tag.
        resolution = resolve_local_model_name(requested_model)
        model_name = resolution.resolved_name

        if request.api_type == "chat":
            raw_prompt = request.prompt
            system_content = ""
            user_content = raw_prompt
            sys_marker = "[SYSTEM]\n"
            user_marker = "\n\n[USER]\n"
            if sys_marker in raw_prompt and user_marker in raw_prompt:
                parts = raw_prompt.split(sys_marker, 1)
                after_sys = parts[1]
                sys_end = after_sys.find(user_marker)
                if sys_end != -1:
                    system_content = after_sys[:sys_end]
                    user_content = after_sys[sys_end + len(user_marker):]
            messages = []
            if system_content:
                messages.append({"role": "system", "content": system_content})
            messages.append({"role": "user", "content": user_content})
            url = os.environ.get("NEXUS_OLLAMA_URL", "http://127.0.0.1:11434/api/chat").strip()
            payload = {
                "model": model_name,
                "messages": messages,
                "stream": False
            }
        else:
            url = os.environ.get("NEXUS_OLLAMA_URL", "http://127.0.0.1:11434/api/generate").strip()
            payload = {
                "model": model_name,
                "prompt": request.prompt,
                "stream": False
            }
        if request.options:
            payload["options"] = request.options
        if request.think is not None:
            payload["think"] = request.think

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
                if request.api_type == "chat":
                    raw_text = resp_json.get("message", {}).get("content", "")
                else:
                    raw_text = resp_json.get("response", "")
                elapsed = time.monotonic() - t0

                truncated = False
                if len(raw_text) > request.max_output_chars:
                    raw_text = raw_text[:request.max_output_chars]
                    truncated = True

                # Extract Ollama native metrics (nanosecond fields)
                metrics_available = any(
                    k in resp_json for k in (
                        "total_duration", "load_duration",
                        "prompt_eval_count", "prompt_eval_duration",
                        "eval_count", "eval_duration",
                    )
                )

                return LocalModelProviderResponse(
                    provider_invoked=True,
                    model_called=True,
                    model_name=model_name,
                    output_text=raw_text,
                    output_truncated=truncated,
                    requested_timeout_sec=request.timeout_sec,
                    elapsed_sec=round(elapsed, 3),
                    effective_timeout_sec=request.timeout_sec,
                    ollama_total_duration=resp_json.get("total_duration", 0),
                    ollama_load_duration=resp_json.get("load_duration", 0),
                    ollama_prompt_eval_count=resp_json.get("prompt_eval_count", 0),
                    ollama_prompt_eval_duration=resp_json.get("prompt_eval_duration", 0),
                    ollama_eval_count=resp_json.get("eval_count", 0),
                    ollama_eval_duration=resp_json.get("eval_duration", 0),
                    ollama_done_reason=resp_json.get("done_reason", ""),
                    ollama_metrics_available=metrics_available,
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
