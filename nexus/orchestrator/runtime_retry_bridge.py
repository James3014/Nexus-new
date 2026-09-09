"""Adapters from the legacy task service to the installed retry runtime."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from nexus_runtime.task_retry import RetryService

from .self_hosted_task_service import (
    _recover_pre_provider_cli_envelope_drift,
    _workforce_dispatch_inputs,
    build_canonical_dispatch_envelope,
    validate_workforce_dispatch_binding,
)


class _State:
    def __init__(self, owner): self.owner = owner
    def read_snapshot(self, task_id): return self.owner._read_state_snapshot(task_id)
    def persist(self, task_id, state): self.owner._mutate_state(task_id, dict(state))


class _Contract:
    def __init__(self, owner): self.owner = owner
    def maximum_attempts(self, request):
        return int(getattr(self.owner.build_contract(request), "maximum_attempts_per_task", 1) or 1)
    def build_retry_request(self, state):
        return self.owner._retry_request(state)


class _Dispatch:
    def __init__(self, owner): self.owner = owner
    def workforce_inputs(self, request): return _workforce_dispatch_inputs(request)
    def recover_predecessor(self, state, request, failure):
        return _recover_pre_provider_cli_envelope_drift(state, request, failure)
    def validate_predecessor(self, request, state):
        return validate_workforce_dispatch_binding(request, require_binding=True)
    def rebind_fresh_attempt(self, request, dispatch):
        envelope = build_canonical_dispatch_envelope(
            request.get("planner_output"), dispatch,
            task_id=str(request.get("task_id") or ""),
            attempt_id=str(request.get("attempt_id") or ""),
            task_card_path=str(request.get("task_card_path") or ""),
            task_card_hash=str(request.get("task_card_hash") or ""),
        ).to_dict()
        result = dict(request)
        result.update({"canonical_dispatch_envelope": envelope})
        return result
    def validate_fresh(self, request, state):
        return validate_workforce_dispatch_binding(request, require_binding=True)


class _Submission:
    def __init__(self, owner): self.owner = owner
    def submit(self, request): return self.owner.submit_task(dict(request))


def retry_task_via_runtime(owner, task_id: str) -> dict[str, Any]:
    return RetryService(_State(owner), _Contract(owner), _Dispatch(owner), _Submission(owner)).retry_task(task_id)
