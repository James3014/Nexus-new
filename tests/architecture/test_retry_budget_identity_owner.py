"""Phase 5b-2: nexus-runtime owns the retry attempt budget and retry identity minting."""

from __future__ import annotations

import inspect
from pathlib import Path

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


SERVICE_PARTS_DIR = (
    Path(__file__).resolve().parents[2]
    / "nexus"
    / "orchestrator"
    / "self_hosted_task_service_parts"
)


def test_service_parts_do_not_redefine_budget_or_mint_retry_identity() -> None:
    # Issue #2434: ``inspect.getsource(service)`` only covers the facade file, so
    # code split into the *_parts package is scanned too (vacuous until parts exist).
    if not SERVICE_PARTS_DIR.is_dir():
        return
    for path in sorted(SERVICE_PARTS_DIR.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        source = path.read_text(encoding="utf-8")
        assert "DEFAULT_MAXIMUM_ATTEMPTS_PER_TASK = " not in source, path
        assert ":retry-" not in source, path
