"""Provider-neutral subprocess adapter plus an opt-in Gemini CLI adapter."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
from typing import Any, Callable, Mapping, Sequence

from nexus.services.cloud_agent_contract import CloudAgentAdapter, CloudAgentRequest, CloudAgentResponse


CommandBuilder = Callable[[CloudAgentRequest], tuple[Sequence[str], str | None]]


class SubprocessCloudAgentAdapter(CloudAgentAdapter):
    def __init__(
        self,
        *,
        command_builder: CommandBuilder,
        provider: str,
        model: str,
        cwd: str | Path | None = None,
        env: Mapping[str, str] | None = None,
        timeout_sec: float = 120.0,
        is_real_provider: bool = False,
    ) -> None:
        self._command_builder = command_builder
        self.provider = provider
        self.model = model
        self.cwd = str(cwd) if cwd is not None else None
        self.env = dict(env) if env is not None else None
        self.timeout_sec = timeout_sec
        self.is_real_provider = is_real_provider

    @staticmethod
    def _parse_output(stdout: str) -> tuple[dict[str, Any], str]:
        try:
            payload = json.loads(stdout)
        except (TypeError, ValueError, json.JSONDecodeError):
            return {}, "cloud_response_invalid_json"
        if isinstance(payload, dict) and isinstance(payload.get("response"), str):
            try:
                nested = json.loads(payload["response"])
            except (TypeError, ValueError, json.JSONDecodeError):
                nested = {}
            if isinstance(nested, dict):
                payload = {**payload, **nested}
        if not isinstance(payload, dict):
            return {}, "cloud_response_must_be_object"
        return payload, ""

    def generate(self, request: CloudAgentRequest) -> CloudAgentResponse:
        try:
            command, stdin_payload = self._command_builder(request)
            completed = subprocess.run(
                [str(item) for item in command],
                input=stdin_payload,
                capture_output=True,
                text=True,
                cwd=self.cwd,
                env=self.env,
                timeout=self.timeout_sec,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return CloudAgentResponse(
                task_id=request.task_id,
                workspace_revision=request.workspace_revision,
                provider=self.provider,
                model=self.model,
                response_identity="",
                error="provider_timeout",
                provider_call_confirmed=False,
            )
        except (OSError, ValueError) as exc:
            return CloudAgentResponse(
                task_id=request.task_id,
                workspace_revision=request.workspace_revision,
                provider=self.provider,
                model=self.model,
                response_identity="",
                error=f"provider_process_error:{exc}",
                provider_call_confirmed=False,
            )
        if completed.returncode != 0:
            return CloudAgentResponse(
                task_id=request.task_id,
                workspace_revision=request.workspace_revision,
                provider=self.provider,
                model=self.model,
                response_identity="",
                error="provider_process_failed",
                provider_call_confirmed=True,
            )
        payload, parse_error = self._parse_output(completed.stdout)
        if parse_error:
            return CloudAgentResponse(
                task_id=request.task_id,
                workspace_revision=request.workspace_revision,
                provider=self.provider,
                model=self.model,
                response_identity="",
                error=parse_error,
                provider_call_confirmed=True,
            )
        response_identity = str(payload.get("response_identity") or payload.get("response_id") or payload.get("id") or "")
        candidate_payload = str(payload.get("candidate_payload") or "")
        error = str(payload.get("error") or "")
        if candidate_payload and not response_identity:
            error = "response_identity_missing"
            candidate_payload = ""
        usage = payload.get("usage") if isinstance(payload.get("usage"), dict) else {}
        latency = float(payload.get("latency_sec", 0.0) or 0.0)
        return CloudAgentResponse(
            task_id=str(payload.get("task_id", request.task_id)),
            workspace_revision=str(payload.get("workspace_revision", request.workspace_revision)),
            provider=str(payload.get("provider", self.provider)),
            model=str(payload.get("model", self.model)),
            response_identity=response_identity,
            candidate_payload=candidate_payload,
            usage=dict(usage),
            latency_sec=latency,
            error=error,
            provider_call_confirmed=True,
        )


class GeminiCliCloudAgentAdapter(SubprocessCloudAgentAdapter):
    """Opt-in real-provider adapter; output is accepted only as strict JSON."""

    def __init__(
        self,
        *,
        model: str | None = None,
        cwd: str | Path,
        gemini_entry: str | None = None,
        env: Mapping[str, str] | None = None,
        timeout_sec: float = 120.0,
    ) -> None:
        self.model = model or os.environ.get("NEXUS_GEMINI_MODEL_NAME", "gemini-2.5-flash")
        self.gemini_entry = gemini_entry
        super().__init__(
            command_builder=self._build_command,
            provider="gemini",
            model=self.model,
            cwd=cwd,
            env=env,
            timeout_sec=timeout_sec,
            is_real_provider=True,
        )

    def _build_command(self, request: CloudAgentRequest) -> tuple[Sequence[str], str | None]:
        from nexus.services.gemini_cli import build_gemini_cli_invocation

        prompt = (
            "Return one JSON object only. Do not call tools or modify files. "
            "Fields: response_identity, candidate_payload, usage, latency_sec, error.\n"
            f"task_id={request.task_id}\n"
            f"workspace_revision={request.workspace_revision}\n"
            f"bounded_context={request.bounded_context}\n"
            f"local_diagnosis={request.local_diagnosis}\n"
            f"semantic_assertions={json.dumps(request.semantic_assertions)}\n"
            f"target_files={json.dumps(request.target_files)}\n"
            f"allowed_mutation_scope={json.dumps(request.allowed_mutation_scope)}"
        )
        invocation = build_gemini_cli_invocation(
            prompt=prompt,
            model_name=self.model,
            gemini_entry=self.gemini_entry,
            env=dict(self.env or os.environ),
            cwd=self.cwd or "/tmp",
            approval_mode="plan",
            transport="inline",
        )
        return invocation.command, invocation.prompt_stdin
