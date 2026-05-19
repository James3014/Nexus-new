from __future__ import annotations

from collections.abc import Callable
from typing import Any


RUNTIME_CONTEXT_PAYLOAD_SCHEMA = "nexus.runtime_context_payload.v1"

CLAIM_BOUNDARY = [
    "Runtime context payloads may assemble context after adapter PASS only.",
    "They do not change route dispatch, runtime policy, or public benchmark readiness.",
]


def build_runtime_context_payload(
    *,
    task_id: str,
    layers: list[int],
    budget: int,
    adapter_receipt: dict[str, Any],
    assembler: Callable[..., str],
    bayesian_params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    blockers = list(adapter_receipt.get("blockers", []) or [])
    if adapter_receipt.get("status") != "PASS":
        return _payload(
            status="RETURN",
            task_id=task_id,
            context="",
            adapter_receipt=adapter_receipt,
            blockers=blockers or ["runtime_context_adapter_not_pass"],
        )

    context = assembler(
        task_id=task_id,
        layers=layers,
        budget=budget,
        bayesian_params=bayesian_params,
    )
    return _payload(
        status="PASS",
        task_id=task_id,
        context=context,
        adapter_receipt=adapter_receipt,
        blockers=[],
    )


def _payload(
    *,
    status: str,
    task_id: str,
    context: str,
    adapter_receipt: dict[str, Any],
    blockers: list[str],
) -> dict[str, Any]:
    return {
        "schema": RUNTIME_CONTEXT_PAYLOAD_SCHEMA,
        "status": status,
        "task_id": task_id,
        "context": context,
        "adapter_receipt": adapter_receipt,
        "runtime_dispatch_changed": False,
        "public_benchmark_allowed": False,
        "runtime_update_allowed": False,
        "blockers": blockers,
        "claim_boundary": CLAIM_BOUNDARY,
    }
