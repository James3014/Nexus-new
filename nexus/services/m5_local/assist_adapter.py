"""Mode A — Local Assist Service.

Provides read-only repository intelligence and assistance on M5.
Has NO repository mutation authority.

Guarantees:
- Produces evidence-backed candidate files, test suggestions, and findings.
- Fully functional even when local LLM is absent or unqualified (deterministic path).
- Strictly rejects any repository write attempt.
- Explicitly links findings back to supplied evidence.
- Emits typed escalation reasons when local inference cannot fully satisfy the task.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from .contracts import (
    LOCAL_MODEL_IDENTITY_MISMATCH,
    LOCAL_RESULT_INSUFFICIENT,
    LOCAL_ROLE_NOT_QUALIFIED,
    LOCAL_RUNTIME_UNAVAILABLE,
    LOCAL_TIMEOUT,
    QUALIFICATION_QUALIFIED,
    ROLE_READ_ONLY_ASSIST,
    LocalAssistMutationAttemptedError,
    LocalAssistRequest,
    LocalAssistResponse,
)
from .deterministic_fallback import build_deterministic_fallback_packet
from .host_inventory import ModelInventoryItem, inspect_models, verify_model_identity
from .runtimes import LlamaCppRuntime, LocalInferenceRuntime, MlxRuntime, MockLocalRuntime


class LocalAssistService:
    """Service executing Mode A — Local Assist."""

    def __init__(
        self,
        runtime: Optional[LocalInferenceRuntime] = None,
        models: Optional[dict[str, ModelInventoryItem]] = None,
    ):
        self._custom_runtime = runtime
        self._custom_models = models

    def _resolve_runtime(self, runtime_id: Optional[str]) -> Optional[LocalInferenceRuntime]:
        if self._custom_runtime is not None:
            return self._custom_runtime
        if runtime_id == "llama.cpp":
            return LlamaCppRuntime()
        if runtime_id == "mlx":
            return MlxRuntime()
        return None

    def execute(self, request: LocalAssistRequest) -> LocalAssistResponse:
        """Execute a bounded, read-only Local Assist query."""
        # Invariant 1: Local Assist has NO repository mutation authority.
        # Check that caller didn't supply mutation parameters or attempt write.
        if getattr(request, "write_permitted", False):
            raise LocalAssistMutationAttemptedError(
                "Local Assist strictly forbids repository mutation authority."
            )

        repo_path = Path(request.repo_path).expanduser().resolve()
        if not repo_path.is_dir():
            return LocalAssistResponse(
                task_id=request.task_id,
                status="FAILED",
                findings="Target repository path does not exist.",
                escalation_reason=LOCAL_RESULT_INSUFFICIENT,
            )

        # Build bounded evidence packet via deterministic local fallback
        packet = build_deterministic_fallback_packet(
            task_id=request.task_id,
            query=request.query,
            repo_path=repo_path,
            base_sha=request.base_sha,
            candidate_hints=request.candidate_hints,
        )

        candidate_files = [p.path for p in packet.candidate_paths]
        suggested_tests = list(packet.test_candidates)
        evidence_refs = [f"path:{p.path}#reason={p.reason}" for p in packet.candidate_paths]

        # Case 1: Deterministic Assist only (no local LLM requested or allowed)
        if (
            not request.allow_inference
            or not request.requested_model
            or not request.requested_runtime
        ):
            findings = (
                f"Deterministic Local Assist found {len(candidate_files)} candidate paths "
                f"and {len(suggested_tests)} test candidates for query: {request.query!r}. "
                f"Top candidates: {', '.join(candidate_files[:3]) or 'none'}."
            )
            return LocalAssistResponse(
                task_id=request.task_id,
                status="SUCCESS",
                findings=findings,
                candidate_files=candidate_files,
                suggested_tests=suggested_tests,
                evidence_refs=evidence_refs,
                claims_linked_to_evidence=True,
                evidence_packet_hash=packet.packet_hash(),
                telemetry={"mode": "deterministic_only"},
            )

        # Case 2: Local inference requested
        runtime_adapter = self._resolve_runtime(request.requested_runtime)
        if runtime_adapter is None:
            # Clean fallback to deterministic assistance with typed escalation
            findings = (
                f"Deterministic fallback: local runtime {request.requested_runtime!r} is unavailable. "
                f"Found {len(candidate_files)} candidates: {', '.join(candidate_files[:3])}."
            )
            return LocalAssistResponse(
                task_id=request.task_id,
                status="ESCALATED",
                findings=findings,
                candidate_files=candidate_files,
                suggested_tests=suggested_tests,
                evidence_refs=evidence_refs,
                escalation_reason=LOCAL_RUNTIME_UNAVAILABLE,
                requested_runtime=request.requested_runtime,
                observed_runtime="UNAVAILABLE",
                requested_model=request.requested_model,
                observed_model="UNAVAILABLE",
                evidence_packet_hash=packet.packet_hash(),
                telemetry={"mode": "fallback_deterministic"},
            )

        # Check qualification if running against real inventory
        if not isinstance(runtime_adapter, MockLocalRuntime):
            models = self._custom_models if self._custom_models is not None else inspect_models()
            model_item = models.get(request.requested_model)
            if (
                model_item is None
                or model_item.role_qualifications.get(ROLE_READ_ONLY_ASSIST)
                != QUALIFICATION_QUALIFIED
            ):
                findings = (
                    f"Deterministic fallback: model {request.requested_model!r} is not qualified for read_only_assist on M5. "
                    f"Retrieved {len(candidate_files)} candidates."
                )
                return LocalAssistResponse(
                    task_id=request.task_id,
                    status="ESCALATED",
                    findings=findings,
                    candidate_files=candidate_files,
                    suggested_tests=suggested_tests,
                    evidence_refs=evidence_refs,
                    escalation_reason=LOCAL_ROLE_NOT_QUALIFIED,
                    requested_runtime=request.requested_runtime,
                    observed_runtime=request.requested_runtime,
                    requested_model=request.requested_model,
                    observed_model=model_item.model_id if model_item else "UNKNOWN",
                    evidence_packet_hash=packet.packet_hash(),
                )

            if not model_item.runtime_runnable:
                findings = (
                    f"Deterministic fallback: requested model {request.requested_model!r} is not runnable on M5. "
                    f"Retrieved {len(candidate_files)} candidates."
                )
                return LocalAssistResponse(
                    task_id=request.task_id,
                    status="ESCALATED",
                    findings=findings,
                    candidate_files=candidate_files,
                    suggested_tests=suggested_tests,
                    evidence_refs=evidence_refs,
                    escalation_reason=LOCAL_RUNTIME_UNAVAILABLE,
                    requested_runtime=request.requested_runtime,
                    observed_runtime=request.requested_runtime,
                    requested_model=request.requested_model,
                    observed_model="NOT_INSTALLED",
                    evidence_packet_hash=packet.packet_hash(),
                )

        # Format bounded prompt
        prompt = (
            f"You are M5 Local Assist. Analyze the task based strictly on the provided evidence:\n"
            f"Task: {request.query}\n"
            f"Candidate Files: {', '.join(candidate_files)}\n"
            f"Suggested Tests: {', '.join(suggested_tests)}\n"
            f"Briefly summarize relevant files and tests."
        )

        res = runtime_adapter.run_inference(
            model_id=request.requested_model,
            prompt=prompt,
            max_tokens=request.max_tokens,
            timeout_seconds=request.timeout_seconds,
        )

        # Invariant: Physical model identity attestation check per Section 4 & 5
        identity_check = verify_model_identity(
            requested_model=request.requested_model,
            result=res,
            models=self._custom_models,
        )
        if not identity_check.is_valid and not res.timed_out and not res.error:
            # Model identity mismatch fails closed
            return LocalAssistResponse(
                task_id=request.task_id,
                status="ESCALATED",
                findings=identity_check.reason
                or f"Model identity mismatch: requested {request.requested_model}, observed {res.observed_model}",
                candidate_files=candidate_files,
                suggested_tests=suggested_tests,
                evidence_refs=evidence_refs,
                escalation_reason=LOCAL_MODEL_IDENTITY_MISMATCH,
                requested_runtime=request.requested_runtime,
                observed_runtime=res.observed_runtime,
                requested_model=request.requested_model,
                observed_model=res.observed_model,
                evidence_packet_hash=packet.packet_hash(),
            )

        if res.timed_out:
            return LocalAssistResponse(
                task_id=request.task_id,
                status="ESCALATED",
                findings=f"Inference timed out after {request.timeout_seconds}s. Falling back to deterministic evidence.",
                candidate_files=candidate_files,
                suggested_tests=suggested_tests,
                evidence_refs=evidence_refs,
                escalation_reason=LOCAL_TIMEOUT,
                requested_runtime=request.requested_runtime,
                observed_runtime=res.observed_runtime,
                requested_model=request.requested_model,
                observed_model=res.observed_model,
                evidence_packet_hash=packet.packet_hash(),
            )

        if res.error:
            return LocalAssistResponse(
                task_id=request.task_id,
                status="ESCALATED",
                findings=f"Inference error: {res.error}. Falling back to deterministic evidence.",
                candidate_files=candidate_files,
                suggested_tests=suggested_tests,
                evidence_refs=evidence_refs,
                escalation_reason=res.escalation_reason or LOCAL_RESULT_INSUFFICIENT,
                requested_runtime=request.requested_runtime,
                observed_runtime=res.observed_runtime,
                requested_model=request.requested_model,
                observed_model=res.observed_model,
                evidence_packet_hash=packet.packet_hash(),
            )

        # Successful local inference assistance
        return LocalAssistResponse(
            task_id=request.task_id,
            status="SUCCESS",
            findings=res.output_text,
            candidate_files=candidate_files,
            suggested_tests=suggested_tests,
            evidence_refs=evidence_refs,
            claims_linked_to_evidence=True,
            requested_runtime=request.requested_runtime,
            observed_runtime=res.observed_runtime,
            requested_model=request.requested_model,
            observed_model=res.observed_model,
            evidence_packet_hash=packet.packet_hash(),
            telemetry={
                "elapsed_ms": res.elapsed_ms,
                "rss_bytes": res.rss_bytes,
                "input_tokens": res.input_tokens,
                "output_tokens": res.output_tokens,
            },
        )
