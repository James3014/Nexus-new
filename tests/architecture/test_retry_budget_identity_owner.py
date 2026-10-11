"""Phase 5b-2: nexus-runtime owns the retry attempt budget and retry identity minting."""

from __future__ import annotations

import inspect

import nexus_runtime.task_retry as runtime_retry

import nexus.orchestrator.runtime_retry_bridge as bridge
import nexus.orchestrator.self_hosted_task_service as service


def test_default_attempt_budget_is_the_runtime_constant() -> None:
    assert (
        service.DEFAULT_MAXIMUM_ATTEMPTS_PER_TASK == runtime_retry.DEFAULT_MAXIMUM_ATTEMPTS_PER_TASK
    )
    assert "DEFAULT_MAXIMUM_ATTEMPTS_PER_TASK = " not in inspect.getsource(service)


def test_bridge_budget_delegates_to_runtime() -> None:
    source = inspect.getsource(bridge._Contract.maximum_attempts)
    assert "resolve_maximum_attempts(" in source
    assert "ATTEMPT_BUDGET_INVALID" not in source


def test_retry_request_mints_identity_through_runtime() -> None:
    source = inspect.getsource(service._retry_request)
    assert "mint_retry_identity(" in source
    assert ":retry-" not in source
