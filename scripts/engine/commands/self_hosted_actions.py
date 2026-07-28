from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Callable, Optional

from nexus.orchestrator.self_hosted_task_service import SelfHostedTaskService
from scripts.engine.commands.exception_translation import NexusCliActionError


_TEST_RUNNER: Optional[Callable[..., Any]] = None


def set_test_runner(runner: Optional[Callable[..., Any]]) -> None:
    global _TEST_RUNNER
    _TEST_RUNNER = runner


def get_self_hosted_service(
    state_dir: str | Path | None = None,
    service: SelfHostedTaskService | None = None,
) -> SelfHostedTaskService:
    if service is not None:
        return service
    return SelfHostedTaskService(
        state_dir=state_dir or os.getenv("NEXUS_SELF_HOSTED_STATE_DIR") or None,
        runner=_TEST_RUNNER,
        auto_reconcile=False,
    )


def run_self_hosted_submit(
    request: dict[str, Any],
    state_dir: str | Path | None = None,
    service: SelfHostedTaskService | None = None,
) -> dict[str, Any]:
    svc = get_self_hosted_service(state_dir=state_dir, service=service)
    try:
        return svc.submit_task(request)
    except (ValueError, KeyError, RuntimeError, TypeError) as exc:
        raise NexusCliActionError(str(exc), exit_code=1) from exc


def run_self_hosted_status(
    task_id: str,
    state_dir: str | Path | None = None,
    service: SelfHostedTaskService | None = None,
) -> dict[str, Any]:
    if not task_id or not str(task_id).strip():
        raise NexusCliActionError("task_id is required", exit_code=1)
    svc = get_self_hosted_service(state_dir=state_dir, service=service)
    try:
        task_state = svc.get_task(task_id)
        if task_state is None:
            raise NexusCliActionError(f"task {task_id} not found", exit_code=1)
        return task_state
    except (ValueError, KeyError, RuntimeError, TypeError) as exc:
        if isinstance(exc, NexusCliActionError):
            raise
        raise NexusCliActionError(str(exc), exit_code=1) from exc
