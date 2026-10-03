"""Mode B — Local Worker Adapter (Execution Substrate).

Builds the execution substrate for local workers over RDC.

Hard Invariants:
- Mutation is DISABLED BY DEFAULT: `LOCAL_WRITE = DENY_UNQUALIFIED`.
- Writing requires:
  1. Exact qualified role/model/runtime for `bounded_code_patch`.
  2. Task/work authority.
  3. #129 claim receipt reference.
  4. #98 physical conflict admission token.
  5. Isolated bounded workspace.
- The Local adapter does NOT self-mint, widen, or approve these authorities.
- Malformed/missing authority = REJECTED_DENIED / fail closed.
"""

from __future__ import annotations

from typing import Optional

from .contracts import (
    LOCAL_MODEL_IDENTITY_MISMATCH,
    LOCAL_ROLE_NOT_QUALIFIED,
    LOCAL_RUNTIME_UNAVAILABLE,
    LOCAL_TIMEOUT,
    LOCAL_WRITE_DEFAULT,
    LocalWorkerRequest,
    LocalWorkerResponse,
)
from .host_inventory import ModelInventoryItem, verify_model_identity
from .runtimes import LlamaCppRuntime, LocalInferenceRuntime, MlxRuntime


class LocalWorkerService:
    """Execution substrate for Mode B — Local Worker."""

    def __init__(
        self,
        runtime: Optional[LocalInferenceRuntime] = None,
        models: Optional[dict[str, ModelInventoryItem]] = None,
    ):
        self._custom_runtime = runtime
        self._custom_models = models

    def _resolve_runtime(self, runtime_id: str) -> Optional[LocalInferenceRuntime]:
        if self._custom_runtime is not None:
            return self._custom_runtime
        if runtime_id == "llama.cpp":
            return LlamaCppRuntime()
        if runtime_id == "mlx":
            return MlxRuntime()
        return None

    def execute(self, request: LocalWorkerRequest) -> LocalWorkerResponse:
        """Execute a bounded local worker operation."""
        # Check mutation gating: Local coding mutation is disabled by default.
        # This bridge is a read-only inference substrate; #129 claim evidence and #98 admission
        # are external prerequisites that this bridge does not validate or mint.
        if request.write_permitted:
            return LocalWorkerResponse(
                task_id=request.task_id,
                attempt_id=request.attempt_id,
                operation_id=request.operation_id,
                status="REJECTED_DENIED",
                escalation_reason=LOCAL_ROLE_NOT_QUALIFIED,
                write_performed=False,
                stderr=(
                    f"[LOCAL_WRITE = {LOCAL_WRITE_DEFAULT}] Local coding mutation is disabled. "
                    f"Model {request.requested_model} is not qualified for bounded_code_patch on M5. "
                    "#129 claim evidence and #98 admission are external prerequisites; "
                    "this bridge does not validate or mint them."
                ),
            )

        # Resolve runtime
        runtime_adapter = self._resolve_runtime(request.requested_runtime)
        if runtime_adapter is None:
            return LocalWorkerResponse(
                task_id=request.task_id,
                attempt_id=request.attempt_id,
                operation_id=request.operation_id,
                status="FAILED",
                escalation_reason=LOCAL_RUNTIME_UNAVAILABLE,
                stderr=f"Runtime {request.requested_runtime} is unavailable on host.",
            )

        # Build prompt and execute
        prompt = (
            f"Task: {request.task_instruction}\n"
            f"Scope: {', '.join(request.allowed_scope)}\n"
            "Provide bounded execution output."
        )

        res = runtime_adapter.run_inference(
            model_id=request.requested_model,
            prompt=prompt,
            timeout_seconds=request.timeout_seconds,
        )

        if res.timed_out:
            return LocalWorkerResponse(
                task_id=request.task_id,
                attempt_id=request.attempt_id,
                operation_id=request.operation_id,
                status="TIMEOUT",
                escalation_reason=LOCAL_TIMEOUT,
                requested_runtime=request.requested_runtime,
                observed_runtime=res.observed_runtime,
                requested_model=request.requested_model,
                observed_model=res.observed_model,
                stderr=f"Operation timed out after {request.timeout_seconds}s",
            )

        if res.cancelled:
            return LocalWorkerResponse(
                task_id=request.task_id,
                attempt_id=request.attempt_id,
                operation_id=request.operation_id,
                status="CANCELLED",
                requested_runtime=request.requested_runtime,
                observed_runtime=res.observed_runtime,
                requested_model=request.requested_model,
                observed_model=res.observed_model,
                stderr="Operation cancelled by coordinator",
            )

        # Invariant: Physical model identity attestation check per Section 4 & 5
        identity_check = verify_model_identity(
            requested_model=request.requested_model,
            result=res,
            models=self._custom_models,
        )
        if not identity_check.is_valid and not res.error:
            return LocalWorkerResponse(
                task_id=request.task_id,
                attempt_id=request.attempt_id,
                operation_id=request.operation_id,
                status="FAILED",
                escalation_reason=LOCAL_MODEL_IDENTITY_MISMATCH,
                requested_runtime=request.requested_runtime,
                observed_runtime=res.observed_runtime,
                requested_model=request.requested_model,
                observed_model=res.observed_model,
                stderr=identity_check.reason
                or f"Model identity mismatch: requested {request.requested_model}, observed {res.observed_model}",
            )

        if res.error:
            return LocalWorkerResponse(
                task_id=request.task_id,
                attempt_id=request.attempt_id,
                operation_id=request.operation_id,
                status="FAILED",
                escalation_reason=res.escalation_reason,
                requested_runtime=request.requested_runtime,
                observed_runtime=res.observed_runtime,
                requested_model=request.requested_model,
                observed_model=res.observed_model,
                stdout=res.stdout,
                stderr=res.stderr or res.error,
                exit_code=res.exit_code,
            )

        # Successful bounded run
        return LocalWorkerResponse(
            task_id=request.task_id,
            attempt_id=request.attempt_id,
            operation_id=request.operation_id,
            status="COMPLETED",
            stdout=res.output_text,
            stderr="",
            exit_code=0,
            write_performed=False,
            requested_runtime=request.requested_runtime,
            observed_runtime=res.observed_runtime,
            requested_model=request.requested_model,
            observed_model=res.observed_model,
            telemetry={
                "elapsed_ms": res.elapsed_ms,
                "rss_bytes": res.rss_bytes,
                "input_tokens": res.input_tokens,
                "output_tokens": res.output_tokens,
            },
        )
