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


def run_self_hosted_retry(
    task_id: str,
    state_dir: str | Path | None = None,
    service: SelfHostedTaskService | None = None,
) -> dict[str, Any]:
    if not task_id or not str(task_id).strip():
        raise NexusCliActionError("task_id is required", exit_code=1)
    svc = get_self_hosted_service(state_dir=state_dir, service=service)
    try:
        return svc.retry_task(task_id)
    except (OSError, ValueError, KeyError, RuntimeError, TypeError) as exc:
        if isinstance(exc, NexusCliActionError):
            raise
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


def run_self_hosted_wait(
    task_id: str,
    timeout_seconds: float = 10.0,
    poll_interval_seconds: float = 0.25,
    state_dir: str | Path | None = None,
    service: SelfHostedTaskService | None = None,
) -> dict[str, Any]:
    if not task_id or not str(task_id).strip():
        raise NexusCliActionError("task_id is required", exit_code=1)
    svc = get_self_hosted_service(state_dir=state_dir, service=service)
    try:
        res = svc.wait_task(
            task_id,
            timeout_seconds=timeout_seconds,
            poll_interval_seconds=poll_interval_seconds,
        )
        if res is None:
            raise NexusCliActionError(f"task {task_id} not found", exit_code=1)
        return res
    except (ValueError, KeyError, RuntimeError, TypeError) as exc:
        if isinstance(exc, NexusCliActionError):
            raise
        raise NexusCliActionError(str(exc), exit_code=1) from exc


def run_self_hosted_list_actionable(
    state_dir: str | Path | None = None,
    service: SelfHostedTaskService | None = None,
) -> dict[str, Any]:
    svc = get_self_hosted_service(state_dir=state_dir, service=service)
    try:
        return svc.list_actionable_tasks()
    except (ValueError, KeyError, RuntimeError, TypeError) as exc:
        if isinstance(exc, NexusCliActionError):
            raise
        raise NexusCliActionError(str(exc), exit_code=1) from exc


def run_self_hosted_workspace_inventory(
    controller_root: str | Path | None = None,
    state_dir: str | Path | None = None,
    service: SelfHostedTaskService | None = None,
) -> dict[str, Any]:
    svc = get_self_hosted_service(state_dir=state_dir, service=service)
    try:
        return svc.workspace_inventory(controller_root=controller_root)
    except (ValueError, KeyError, RuntimeError, TypeError) as exc:
        if isinstance(exc, NexusCliActionError):
            raise
        raise NexusCliActionError(str(exc), exit_code=1) from exc


def run_self_hosted_workspace_plan(
    controller_root: str | Path | None = None,
    expected_controller_revision: str | None = None,
    state_dir: str | Path | None = None,
    service: SelfHostedTaskService | None = None,
) -> dict[str, Any]:
    svc = get_self_hosted_service(state_dir=state_dir, service=service)
    try:
        return svc.workspace_convergence_plan(
            controller_root=controller_root,
            expected_controller_revision=expected_controller_revision,
        )
    except (ValueError, KeyError, RuntimeError, TypeError) as exc:
        if isinstance(exc, NexusCliActionError):
            raise
        raise NexusCliActionError(str(exc), exit_code=1) from exc


def run_self_hosted_workspace_slot_status(
    campaign_id: str = "default",
    slot_index: int = 0,
    controller_root: str | Path | None = None,
    state_dir: str | Path | None = None,
    service: SelfHostedTaskService | None = None,
) -> dict[str, Any]:
    svc = get_self_hosted_service(state_dir=state_dir, service=service)
    try:
        return svc.workspace_slot_status(
            campaign_id=campaign_id,
            slot_index=slot_index,
            controller_root=controller_root,
        )
    except (ValueError, KeyError, RuntimeError, TypeError) as exc:
        if isinstance(exc, NexusCliActionError):
            raise
        raise NexusCliActionError(str(exc), exit_code=1) from exc


def run_self_hosted_workspace_slot_prepare(
    request: dict[str, Any],
    campaign_id: str = "default",
    slot_index: int = 0,
    state_dir: str | Path | None = None,
    service: SelfHostedTaskService | None = None,
) -> dict[str, Any]:
    svc = get_self_hosted_service(state_dir=state_dir, service=service)
    try:
        return svc.workspace_slot_prepare(
            request,
            campaign_id=campaign_id,
            slot_index=slot_index,
        )
    except (ValueError, KeyError, RuntimeError, TypeError) as exc:
        if isinstance(exc, NexusCliActionError):
            raise
        raise NexusCliActionError(str(exc), exit_code=1) from exc


def run_self_hosted_workspace_converge(
    expected_controller_revision: str,
    expected_plan_hash: str,
    apply: bool = False,
    controller_root: str | Path | None = None,
    state_dir: str | Path | None = None,
    service: SelfHostedTaskService | None = None,
) -> dict[str, Any]:
    if not expected_controller_revision or not expected_controller_revision.strip():
        raise NexusCliActionError("expected_controller_revision is required", exit_code=1)
    if not expected_plan_hash or not expected_plan_hash.strip():
        raise NexusCliActionError("expected_plan_hash is required", exit_code=1)
    svc = get_self_hosted_service(state_dir=state_dir, service=service)
    try:
        return svc.apply_workspace_convergence(
            controller_root=controller_root,
            expected_controller_revision=expected_controller_revision,
            expected_plan_hash=expected_plan_hash,
            apply=apply,
        )
    except (ValueError, KeyError, RuntimeError, TypeError) as exc:
        if isinstance(exc, NexusCliActionError):
            raise
        raise NexusCliActionError(str(exc), exit_code=1) from exc


def run_self_hosted_cleanup(
    task_id: str,
    apply: bool = False,
    state_dir: str | Path | None = None,
    service: SelfHostedTaskService | None = None,
) -> dict[str, Any]:
    if not task_id or not str(task_id).strip():
        raise NexusCliActionError("task_id is required", exit_code=1)
    svc = get_self_hosted_service(state_dir=state_dir, service=service)
    try:
        return svc.cleanup_tasks(task_id=task_id, dry_run=not apply)
    except (ValueError, KeyError, RuntimeError, TypeError) as exc:
        if isinstance(exc, NexusCliActionError):
            raise
        raise NexusCliActionError(str(exc), exit_code=1) from exc


def run_self_hosted_approve(
    task_id: str,
    candidate_commit_sha: str,
    candidate_tree_sha: str,
    candidate_state_hash: str,
    verified_receipt_hash: str,
    state_dir: str | Path | None = None,
    service: SelfHostedTaskService | None = None,
) -> dict[str, Any]:
    if not task_id or not str(task_id).strip():
        raise NexusCliActionError("task_id is required", exit_code=1)
    svc = get_self_hosted_service(state_dir=state_dir, service=service)
    try:
        return svc.approve_promotion(
            task_id,
            candidate_commit_sha=candidate_commit_sha,
            candidate_tree_sha=candidate_tree_sha,
            candidate_state_hash=candidate_state_hash,
            verified_receipt_hash=verified_receipt_hash,
        )
    except (ValueError, KeyError, RuntimeError, TypeError) as exc:
        if isinstance(exc, NexusCliActionError):
            raise
        raise NexusCliActionError(str(exc), exit_code=1) from exc


def run_self_hosted_integrate(
    task_id: str,
    integration_branch: str = "nexus/integration",
    state_dir: str | Path | None = None,
    service: SelfHostedTaskService | None = None,
) -> dict[str, Any]:
    if not task_id or not str(task_id).strip():
        raise NexusCliActionError("task_id is required", exit_code=1)
    svc = get_self_hosted_service(state_dir=state_dir, service=service)
    try:
        return svc.integrate_approved(
            task_id,
            integration_branch=integration_branch,
        )
    except (ValueError, KeyError, RuntimeError, TypeError) as exc:
        if isinstance(exc, NexusCliActionError):
            raise
        raise NexusCliActionError(str(exc), exit_code=1) from exc


def run_self_hosted_dispose(
    task_id: str,
    disposition: str,
    superseded_by: str | None = None,
    state_dir: str | Path | None = None,
    service: SelfHostedTaskService | None = None,
) -> dict[str, Any]:
    if not task_id or not str(task_id).strip():
        raise NexusCliActionError("task_id is required", exit_code=1)
    svc = get_self_hosted_service(state_dir=state_dir, service=service)
    try:
        return svc.dispose_candidate(
            task_id,
            disposition=disposition,
            superseded_by=superseded_by,
        )
    except (ValueError, KeyError, RuntimeError, TypeError) as exc:
        if isinstance(exc, NexusCliActionError):
            raise
        raise NexusCliActionError(str(exc), exit_code=1) from exc


def run_self_hosted_close_without_candidate(
    task_id: str,
    superseded_by: str,
    state_dir: str | Path | None = None,
    service: SelfHostedTaskService | None = None,
) -> dict[str, Any]:
    if not task_id or not str(task_id).strip():
        raise NexusCliActionError("task_id is required", exit_code=1)
    svc = get_self_hosted_service(state_dir=state_dir, service=service)
    try:
        return svc.close_task_without_candidate(
            task_id,
            superseded_by=superseded_by,
        )
    except (ValueError, KeyError, RuntimeError, TypeError) as exc:
        if isinstance(exc, NexusCliActionError):
            raise
        raise NexusCliActionError(str(exc), exit_code=1) from exc


def run_self_hosted_cancel(
    task_id: str,
    state_dir: str | Path | None = None,
    service: SelfHostedTaskService | None = None,
) -> dict[str, Any]:
    if not task_id or not str(task_id).strip():
        raise NexusCliActionError("task_id is required", exit_code=1)
    svc = get_self_hosted_service(state_dir=state_dir, service=service)
    try:
        return svc.cancel_task(task_id)
    except (ValueError, KeyError, RuntimeError, TypeError) as exc:
        if isinstance(exc, NexusCliActionError):
            raise
        raise NexusCliActionError(str(exc), exit_code=1) from exc


def run_self_hosted_recover_verified_uncommitted(
    task_id: str,
    state_dir: str | Path | None = None,
    service: SelfHostedTaskService | None = None,
) -> dict[str, Any]:
    if not task_id or not str(task_id).strip():
        raise NexusCliActionError("task_id is required", exit_code=1)
    svc = get_self_hosted_service(state_dir=state_dir, service=service)
    try:
        return svc.recover_verified_uncommitted_candidate(task_id)
    except (ValueError, KeyError, RuntimeError, TypeError) as exc:
        raise NexusCliActionError(str(exc), exit_code=1) from exc


def run_self_hosted_verify(
    task_id: str,
    state_dir: str | Path | None = None,
    service: SelfHostedTaskService | None = None,
) -> dict[str, Any]:
    if not task_id or not str(task_id).strip():
        raise NexusCliActionError("task_id is required", exit_code=1)
    svc = get_self_hosted_service(state_dir=state_dir, service=service)
    try:
        return svc.verify_task(task_id)
    except (ValueError, KeyError, RuntimeError, TypeError) as exc:
        raise NexusCliActionError(str(exc), exit_code=1) from exc
