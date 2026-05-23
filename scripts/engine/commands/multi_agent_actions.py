from __future__ import annotations

import json
import subprocess
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from nexus.delivery.submission import (
    assess_submission,
    build_submission_payload,
    governance_payload,
    load_delivery_receipt,
)
from scripts.engine.commands.exception_translation import NexusCliActionError


class OrchestratorLike(Protocol):
    logger: Any
    state_store: Any
    evidence_collector: Any


class MetricsAggregatorLike(Protocol):
    def compute_metrics(self) -> Mapping[str, Any]:
        ...


class IntegrationManagerLike(Protocol):
    def batch_integrate(self, task_ids: list[str], target_branch: str) -> tuple[list[str], list[str]]:
        ...


OrchestratorFactory = Callable[[], OrchestratorLike]
MetricsAggregatorFactory = Callable[[Any], MetricsAggregatorLike]
IntegrationManagerFactory = Callable[[Any, Any], IntegrationManagerLike]
ReceiptLoader = Callable[[Path], dict[str, Any]]
GovernanceEventAppender = Callable[[str, dict[str, Any]], None]
CommitShaProvider = Callable[[], str]


@dataclass(frozen=True)
class TaskStatusView:
    text_lines: list[str]
    json_text: str | None = None


@dataclass(frozen=True)
class TaskAuditView:
    text_lines: list[str]


@dataclass(frozen=True)
class TaskStartView:
    task_id: str
    working_dir: str
    branch_name: str
    text_lines: list[str]


@dataclass(frozen=True)
class TaskVerificationView:
    task_id: str
    passed: bool
    text_lines: list[str]


@dataclass(frozen=True)
class TaskIntegrationView:
    task_ids: list[str]
    target_branch: str
    success: list[str]
    failed: list[str]
    text_lines: list[str]


@dataclass(frozen=True)
class TaskSubmissionView:
    task_id: str
    submitted: bool
    delivery_payload: dict[str, Any] | None
    text_lines: list[str]


def _default_orchestrator_factory() -> OrchestratorLike:
    from nexus.orchestrator.orchestrator import NexusOrchestrator

    return NexusOrchestrator()


def _default_metrics_aggregator_factory(logger: Any) -> MetricsAggregatorLike:
    from nexus.orchestrator.metrics import MetricsAggregator

    return MetricsAggregator(logger)


def _default_integration_manager_factory(state_store: Any, evidence_collector: Any) -> IntegrationManagerLike:
    from nexus.orchestrator.integration_manager import IntegrationManager

    return IntegrationManager(state_store, evidence_collector)


def _default_governance_event_appender(repo_root: str, payload: dict[str, Any]) -> None:
    from nexus.orchestrator.governance_bridge import append_governance_event

    append_governance_event(repo_root, payload)


def _default_commit_sha_provider() -> str:
    return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"]).decode().strip()


def _parse_csv(value: str) -> list[str]:
    return [part.strip() for part in value.split(",") if part.strip()]


def create_multi_agent_task(
    task_id: str,
    *,
    owner: str,
    allowed_files_csv: str,
    orchestrator_factory: OrchestratorFactory | None = None,
) -> list[str]:
    orchestrator = (orchestrator_factory or _default_orchestrator_factory)()
    orchestrator.create_task(
        task_id=task_id,
        owner=owner,
        allowed_files=_parse_csv(allowed_files_csv),
        done_criteria=["Gate pass"],
        evidence_requirements=["pytest", "nexus acceptance-check"],
    )
    return [f"✅ Task {task_id} created for {owner}."]


def start_multi_agent_task(
    task_id: str,
    *,
    orchestrator_factory: OrchestratorFactory | None = None,
) -> TaskStartView:
    orchestrator = (orchestrator_factory or _default_orchestrator_factory)()
    task = orchestrator.start_task(task_id)
    working_dir = str(task.working_dir)
    branch_name = str(task.branch_name)
    return TaskStartView(
        task_id=task_id,
        working_dir=working_dir,
        branch_name=branch_name,
        text_lines=[
            f"✅ Task {task_id} started.",
            f"📍 Working directory: {working_dir}",
            f"🌿 Branch: {branch_name}",
        ],
    )


def render_multi_agent_task_start(view: TaskStartView) -> list[str]:
    return view.text_lines


def get_multi_agent_metrics(
    *,
    orchestrator_factory: OrchestratorFactory | None = None,
    aggregator_factory: MetricsAggregatorFactory | None = None,
) -> dict[str, Any]:
    orchestrator = (orchestrator_factory or _default_orchestrator_factory)()
    aggregator = (aggregator_factory or _default_metrics_aggregator_factory)(orchestrator.logger)
    return dict(aggregator.compute_metrics())


def render_multi_agent_metrics(metrics: Mapping[str, Any]) -> list[str]:
    return [
        "📊 Nexus Multi-Agent Metrics",
        f"Total Tasks: {metrics.get('total_tasks', 0)}",
        f"Success Rate: {float(metrics.get('success_rate', 0) or 0):.1%}",
        f"Conflict Rate: {float(metrics.get('conflict_rate', 0) or 0):.1%}",
        f"Gate Failure Rate: {float(metrics.get('gate_failure_rate', 0) or 0):.1%}",
        f"Avg Lead Time: {metrics.get('avg_lead_time_sec', 0)}s",
    ]


def get_multi_agent_task_status(
    task_id: str | None,
    *,
    orchestrator_factory: OrchestratorFactory | None = None,
) -> TaskStatusView:
    orchestrator = (orchestrator_factory or _default_orchestrator_factory)()
    if task_id:
        task = orchestrator.state_store.load_task(task_id)
        if not task:
            return TaskStatusView(text_lines=[f"Task {task_id} not found."])
        return TaskStatusView(
            text_lines=[f"Task: {task.task_id} | Status: {task.current_status} | Owner: {task.owner}"],
            json_text=task.model_dump_json(indent=2),
        )

    tasks = orchestrator.state_store.list_tasks()
    return TaskStatusView(
        text_lines=[
            f"{task.task_id}: {task.current_status} ({task.owner})"
            for task in tasks.values()
        ]
    )


def render_multi_agent_task_status(view: TaskStatusView, *, output_json: bool) -> list[str]:
    if output_json and view.json_text is not None:
        return [view.json_text]
    return view.text_lines


def get_multi_agent_task_audit(
    task_id: str,
    *,
    orchestrator_factory: OrchestratorFactory | None = None,
) -> TaskAuditView:
    orchestrator = (orchestrator_factory or _default_orchestrator_factory)()
    task = orchestrator.state_store.load_task(task_id)
    if not task:
        return TaskAuditView(text_lines=[f"Task {task_id} not found."])

    lines = [
        f"🔍 Auditing Task {task_id} (Owner: {task.owner})",
        f"Status: {task.current_status}",
        f"Evidence Count: {len(task.evidence_list)}",
    ]
    for index, evidence in enumerate(task.evidence_list):
        status = "✅ PASS" if evidence.exit_code == 0 else "❌ FAIL"
        lines.append(f"  [{index}] {status} | Command: {evidence.command}")
    return TaskAuditView(text_lines=lines)


def render_multi_agent_task_audit(view: TaskAuditView) -> list[str]:
    return view.text_lines


def verify_multi_agent_task(
    task_id: str,
    *,
    orchestrator_factory: OrchestratorFactory | None = None,
) -> TaskVerificationView:
    orchestrator = (orchestrator_factory or _default_orchestrator_factory)()
    passed = bool(orchestrator.verify_task(task_id))
    status_line = (
        f"✅ Task {task_id} passed all gates."
        if passed
        else f"❌ Task {task_id} failed gates."
    )
    return TaskVerificationView(
        task_id=task_id,
        passed=passed,
        text_lines=[f"🔍 Verifying task {task_id}...", status_line],
    )


def render_multi_agent_task_verification(view: TaskVerificationView) -> list[str]:
    return view.text_lines


def close_multi_agent_task(
    task_id: str,
    *,
    no_cleanup: bool,
    orchestrator_factory: OrchestratorFactory | None = None,
) -> list[str]:
    orchestrator = (orchestrator_factory or _default_orchestrator_factory)()
    orchestrator.close_task(task_id, cleanup=not no_cleanup)
    return [f"✅ Task {task_id} closed."]


def integrate_multi_agent_tasks(
    task_ids_csv: str,
    *,
    target_branch: str,
    orchestrator_factory: OrchestratorFactory | None = None,
    integration_manager_factory: IntegrationManagerFactory | None = None,
) -> TaskIntegrationView:
    orchestrator = (orchestrator_factory or _default_orchestrator_factory)()
    manager = (integration_manager_factory or _default_integration_manager_factory)(
        orchestrator.state_store,
        orchestrator.evidence_collector,
    )
    task_ids = _parse_csv(task_ids_csv)
    success, failed = manager.batch_integrate(task_ids, target_branch)
    text_lines = [f"🚢 Integrating tasks: {task_ids} into {target_branch}..."]
    if success:
        text_lines.append(f"✅ Successfully integrated: {success}")
    if failed:
        text_lines.append(f"❌ Failed to integrate: {failed}")
    return TaskIntegrationView(
        task_ids=task_ids,
        target_branch=target_branch,
        success=list(success),
        failed=list(failed),
        text_lines=text_lines,
    )


def render_multi_agent_task_integration(view: TaskIntegrationView) -> list[str]:
    return view.text_lines


def submit_multi_agent_task(
    task_id: str,
    *,
    repo_root: Path,
    orchestrator_factory: OrchestratorFactory | None = None,
    receipt_loader: ReceiptLoader | None = None,
    governance_event_appender: GovernanceEventAppender | None = None,
    commit_sha_provider: CommitShaProvider | None = None,
) -> TaskSubmissionView:
    orchestrator = (orchestrator_factory or _default_orchestrator_factory)()
    text_lines = [f"🚀 Submitting task {task_id}..."]
    if not bool(orchestrator.verify_task(task_id)):
        text_lines.append("❌ Gate failure. Submission blocked.")
        return TaskSubmissionView(
            task_id=task_id,
            submitted=False,
            delivery_payload=None,
            text_lines=text_lines,
        )

    task = orchestrator.state_store.load_task(task_id)
    if task is None:
        raise NexusCliActionError(f"Task {task_id} not found.", exit_code=1)

    evidence_path = orchestrator.evidence_collector.generate_hallucination_evidence(
        task,
        f"Task {task_id} processed by {task.owner}.",
    )
    derived_bundle = json.loads(Path(evidence_path).read_text(encoding="utf-8"))

    root = Path(repo_root)
    receipt_path = root / ".nexus" / "reports" / "delivery_gate.json"
    receipt_payload = (receipt_loader or load_delivery_receipt)(receipt_path)
    assessment = assess_submission(
        receipt_payload=receipt_payload,
        derived_bundle=derived_bundle,
        receipt_path=receipt_path,
    )

    (governance_event_appender or _default_governance_event_appender)(
        str(root),
        governance_payload(task_id, assessment),
    )

    if not assessment.delivery_gate_passed or not assessment.acceptance_gate_passed:
        raise NexusCliActionError(
            "Submission blocked: delivery receipt does not prove both delivery-gate and acceptance-check passed.",
            exit_code=1,
        )

    delivery = build_submission_payload(
        commit_sha=(commit_sha_provider or _default_commit_sha_provider)(),
        assessment=assessment,
    )
    text_lines.append("✅ Task submitted successfully.")
    text_lines.append(json.dumps(delivery, indent=2))
    return TaskSubmissionView(
        task_id=task_id,
        submitted=True,
        delivery_payload=delivery,
        text_lines=text_lines,
    )


def render_multi_agent_task_submission(view: TaskSubmissionView) -> list[str]:
    return view.text_lines
