from __future__ import annotations

import json
from dataclasses import dataclass

from click.testing import CliRunner

import scripts.engine.nexus_cli as cli_mod
from scripts.engine.commands.exception_translation import NexusCliActionError
from scripts.engine.commands.multi_agent_actions import (
    TaskAuditView,
    TaskIntegrationView,
    TaskStartView,
    TaskStatusView,
    TaskSubmissionView,
    TaskVerificationView,
    close_multi_agent_task,
    create_multi_agent_task,
    get_multi_agent_metrics,
    get_multi_agent_task_audit,
    get_multi_agent_task_status,
    integrate_multi_agent_tasks,
    render_multi_agent_metrics,
    render_multi_agent_task_integration,
    render_multi_agent_task_audit,
    render_multi_agent_task_start,
    render_multi_agent_task_status,
    render_multi_agent_task_submission,
    render_multi_agent_task_verification,
    start_multi_agent_task,
    submit_multi_agent_task,
    verify_multi_agent_task,
)


class FakeOrchestrator:
    logger = object()

    def __init__(self, state_store=None):
        self.state_store = state_store or FakeStateStore({})


class FakeAggregator:
    def __init__(self, logger):
        self.logger = logger

    def compute_metrics(self):
        return {
            "total_tasks": 4,
            "success_rate": 0.75,
            "conflict_rate": 0.25,
            "gate_failure_rate": 0.5,
            "avg_lead_time_sec": 12.5,
        }


@dataclass(frozen=True)
class FakeEvidence:
    exit_code: int
    command: str


class FakeTask:
    def __init__(self, task_id: str, status: str, owner: str, evidence_list=None):
        self.task_id = task_id
        self.current_status = status
        self.owner = owner
        self.evidence_list = evidence_list or []

    def model_dump_json(self, *, indent: int):
        return json.dumps(
            {"task_id": self.task_id, "current_status": self.current_status, "owner": self.owner},
            indent=indent,
        )


class FakeEvidenceCollector:
    def __init__(self, evidence_path):
        self.evidence_path = evidence_path
        self.calls = []

    def generate_hallucination_evidence(self, task, message: str):
        self.calls.append((task.task_id, message))
        return self.evidence_path


class FakeStateStore:
    def __init__(self, tasks):
        self._tasks = tasks

    def load_task(self, task_id: str):
        return self._tasks.get(task_id)

    def list_tasks(self):
        return self._tasks


def test_create_multi_agent_task_parses_files_and_uses_default_contract_without_click():
    class CreateOrchestrator(FakeOrchestrator):
        def __init__(self):
            super().__init__()
            self.create_calls = []

        def create_task(self, **kwargs):
            self.create_calls.append(kwargs)

    orchestrator = CreateOrchestrator()

    lines = create_multi_agent_task(
        "T-create",
        owner="alice",
        allowed_files_csv="a.py, b.py",
        orchestrator_factory=lambda: orchestrator,
    )

    assert orchestrator.create_calls == [
        {
            "task_id": "T-create",
            "owner": "alice",
            "allowed_files": ["a.py", "b.py"],
            "done_criteria": ["Gate pass"],
            "evidence_requirements": ["pytest", "nexus acceptance-check"],
        }
    ]
    assert lines == ["✅ Task T-create created for alice."]


def test_start_multi_agent_task_returns_worktree_view_without_click():
    class StartedTask:
        working_dir = "/tmp/worktree"
        branch_name = "task-branch"

    class StartOrchestrator(FakeOrchestrator):
        def __init__(self):
            super().__init__()
            self.started = []

        def start_task(self, task_id: str):
            self.started.append(task_id)
            return StartedTask()

    orchestrator = StartOrchestrator()

    view = start_multi_agent_task("T-start", orchestrator_factory=lambda: orchestrator)

    assert orchestrator.started == ["T-start"]
    assert view == TaskStartView(
        task_id="T-start",
        working_dir="/tmp/worktree",
        branch_name="task-branch",
        text_lines=[
            "✅ Task T-start started.",
            "📍 Working directory: /tmp/worktree",
            "🌿 Branch: task-branch",
        ],
    )
    assert render_multi_agent_task_start(view) == view.text_lines


def test_integrate_multi_agent_tasks_parses_ids_and_uses_integration_manager_without_click():
    class IntegrateOrchestrator(FakeOrchestrator):
        evidence_collector = object()

    class FakeIntegrationManager:
        def __init__(self):
            self.calls = []

        def batch_integrate(self, task_ids, target_branch):
            self.calls.append((task_ids, target_branch))
            return ["T-ok"], ["T-bad"]

    manager = FakeIntegrationManager()

    view = integrate_multi_agent_tasks(
        "T-ok, T-bad",
        target_branch="release",
        orchestrator_factory=IntegrateOrchestrator,
        integration_manager_factory=lambda state_store, evidence_collector: manager,
    )

    assert manager.calls == [(["T-ok", "T-bad"], "release")]
    assert view == TaskIntegrationView(
        task_ids=["T-ok", "T-bad"],
        target_branch="release",
        success=["T-ok"],
        failed=["T-bad"],
        text_lines=[
            "🚢 Integrating tasks: ['T-ok', 'T-bad'] into release...",
            "✅ Successfully integrated: ['T-ok']",
            "❌ Failed to integrate: ['T-bad']",
        ],
    )
    assert render_multi_agent_task_integration(view) == view.text_lines


def test_submit_multi_agent_task_blocks_when_verification_fails_without_side_effects(tmp_path):
    class SubmitOrchestrator(FakeOrchestrator):
        evidence_collector = FakeEvidenceCollector(tmp_path / "evidence.json")

        def verify_task(self, task_id: str):
            return False

    governance_events = []

    view = submit_multi_agent_task(
        "T-submit",
        repo_root=tmp_path,
        orchestrator_factory=SubmitOrchestrator,
        governance_event_appender=lambda _repo_root, payload: governance_events.append(payload),
        commit_sha_provider=lambda: "abc123",
    )

    assert view == TaskSubmissionView(
        task_id="T-submit",
        submitted=False,
        delivery_payload=None,
        text_lines=["🚀 Submitting task T-submit...", "❌ Gate failure. Submission blocked."],
    )
    assert governance_events == []
    assert render_multi_agent_task_submission(view) == view.text_lines


def test_submit_multi_agent_task_builds_delivery_payload_and_governance_event(tmp_path):
    evidence_path = tmp_path / "evidence.json"
    evidence_path.write_text(
        json.dumps({"claim_state": "VERIFIED", "confidence_level": "HIGH"}),
        encoding="utf-8",
    )
    task = FakeTask("T-submit", "DONE", "alice")

    class SubmitOrchestrator(FakeOrchestrator):
        evidence_collector = FakeEvidenceCollector(evidence_path)

        def __init__(self):
            super().__init__(FakeStateStore({"T-submit": task}))

        def verify_task(self, task_id: str):
            return True

    governance_events = []

    view = submit_multi_agent_task(
        "T-submit",
        repo_root=tmp_path,
        orchestrator_factory=SubmitOrchestrator,
        receipt_loader=lambda receipt_path: {
            "delivery_gate_passed": True,
            "acceptance_result": {"gate_passed": True},
        },
        governance_event_appender=lambda repo_root, payload: governance_events.append((repo_root, payload)),
        commit_sha_provider=lambda: "abc123",
    )

    assert view.submitted is True
    assert view.delivery_payload == {
        "commit_sha": "abc123",
        "nas_fitness": 1.0,
        "nexus_participation_ratio": 1.0,
        "swarm_pids": "none",
        "gate_summary": {
            "delivery_gate": "PASS",
            "acceptance_check": "PASS",
            "hallucination_index": "VERIFIED",
            "contract_check": "UNRUN",
            "ci_gate": "UNRUN",
            "proof_present": True,
        },
        "receipt_path": str(tmp_path / ".nexus" / "reports" / "delivery_gate.json"),
    }
    assert governance_events == [
        (
            str(tmp_path),
            {
                "task_id": "T-submit",
                "pass": True,
                "phantom_blocked": False,
                "proof_present": True,
            },
        )
    ]
    assert view.text_lines[0] == "🚀 Submitting task T-submit..."
    assert view.text_lines[1] == "✅ Task submitted successfully."
    assert json.loads(view.text_lines[2]) == view.delivery_payload


def test_submit_multi_agent_task_raises_when_receipt_gate_fails_after_governance_event(tmp_path):
    evidence_path = tmp_path / "evidence.json"
    evidence_path.write_text(
        json.dumps({"claim_state": "VERIFIED", "confidence_level": "HIGH"}),
        encoding="utf-8",
    )
    task = FakeTask("T-submit", "DONE", "alice")

    class SubmitOrchestrator(FakeOrchestrator):
        evidence_collector = FakeEvidenceCollector(evidence_path)

        def __init__(self):
            super().__init__(FakeStateStore({"T-submit": task}))

        def verify_task(self, task_id: str):
            return True

    governance_events = []

    try:
        submit_multi_agent_task(
            "T-submit",
            repo_root=tmp_path,
            orchestrator_factory=SubmitOrchestrator,
            receipt_loader=lambda receipt_path: {
                "delivery_gate_passed": False,
                "acceptance_result": {"gate_passed": True},
            },
            governance_event_appender=lambda repo_root, payload: governance_events.append((repo_root, payload)),
            commit_sha_provider=lambda: "abc123",
        )
    except NexusCliActionError as exc:
        assert "Submission blocked" in str(exc)
    else:
        raise AssertionError("failed delivery receipt must block submission")

    assert governance_events == [
        (
            str(tmp_path),
            {
                "task_id": "T-submit",
                "pass": False,
                "phantom_blocked": True,
                "proof_present": True,
            },
        )
    ]


def test_multi_agent_submit_cli_uses_action_result(monkeypatch):
    monkeypatch.setattr(
        cli_mod,
        "submit_multi_agent_task",
        lambda task_id, *, repo_root: TaskSubmissionView(
            task_id=task_id,
            submitted=True,
            delivery_payload={"commit_sha": "abc123"},
            text_lines=["submitted from action", '{"commit_sha": "abc123"}'],
        ),
    )

    result = CliRunner().invoke(cli_mod.nexus, ["nexus", "multi-agent", "submit", "--task-id", "T-submit"])

    assert result.exit_code == 0
    assert "submitted from action" in result.output
    assert json.loads(result.output.splitlines()[-1]) == {"commit_sha": "abc123"}


def test_multi_agent_create_task_cli_uses_action_result(monkeypatch):
    calls = []

    def fake_create_multi_agent_task(task_id, *, owner, allowed_files_csv):
        calls.append((task_id, owner, allowed_files_csv))
        return ["created from action"]

    monkeypatch.setattr(cli_mod, "create_multi_agent_task", fake_create_multi_agent_task)

    result = CliRunner().invoke(
        cli_mod.nexus,
        [
            "nexus",
            "multi-agent",
            "create-task",
            "--task-id",
            "T-create",
            "--owner",
            "alice",
            "--allowed-files",
            "a.py,b.py",
        ],
    )

    assert result.exit_code == 0
    assert calls == [("T-create", "alice", "a.py,b.py")]
    assert "created from action" in result.output


def test_multi_agent_start_cli_uses_action_result(monkeypatch):
    monkeypatch.setattr(
        cli_mod,
        "start_multi_agent_task",
        lambda task_id: TaskStartView(
            task_id=task_id,
            working_dir="/tmp/worktree",
            branch_name="task-branch",
            text_lines=["started from action"],
        ),
    )

    result = CliRunner().invoke(cli_mod.nexus, ["nexus", "multi-agent", "start", "--task-id", "T-start"])

    assert result.exit_code == 0
    assert "started from action" in result.output


def test_multi_agent_integrate_cli_uses_action_result(monkeypatch):
    calls = []

    def fake_integrate_multi_agent_tasks(task_ids, *, target_branch):
        calls.append((task_ids, target_branch))
        return TaskIntegrationView(
            task_ids=["T-ok"],
            target_branch=target_branch,
            success=["T-ok"],
            failed=[],
            text_lines=["integrated from action"],
        )

    monkeypatch.setattr(cli_mod, "integrate_multi_agent_tasks", fake_integrate_multi_agent_tasks)

    result = CliRunner().invoke(
        cli_mod.nexus,
        ["nexus", "multi-agent", "integrate", "--task-ids", "T-ok", "--target-branch", "release"],
    )

    assert result.exit_code == 0
    assert calls == [("T-ok", "release")]
    assert "integrated from action" in result.output


def test_get_multi_agent_metrics_wires_orchestrator_logger_to_aggregator():
    calls = []

    def aggregator_factory(logger):
        calls.append(logger)
        return FakeAggregator(logger)

    metrics = get_multi_agent_metrics(
        orchestrator_factory=FakeOrchestrator,
        aggregator_factory=aggregator_factory,
    )

    assert calls == [FakeOrchestrator.logger]
    assert metrics == {
        "total_tasks": 4,
        "success_rate": 0.75,
        "conflict_rate": 0.25,
        "gate_failure_rate": 0.5,
        "avg_lead_time_sec": 12.5,
    }


def test_render_multi_agent_metrics_preserves_cli_output_schema():
    lines = render_multi_agent_metrics(
        {
            "total_tasks": 4,
            "success_rate": 0.75,
            "conflict_rate": 0.25,
            "gate_failure_rate": 0.5,
            "avg_lead_time_sec": 12.5,
        }
    )

    assert lines == [
        "📊 Nexus Multi-Agent Metrics",
        "Total Tasks: 4",
        "Success Rate: 75.0%",
        "Conflict Rate: 25.0%",
        "Gate Failure Rate: 50.0%",
        "Avg Lead Time: 12.5s",
    ]


def test_multi_agent_metrics_cli_uses_action_result(monkeypatch):
    monkeypatch.setattr(
        cli_mod,
        "get_multi_agent_metrics",
        lambda: {
            "total_tasks": 4,
            "success_rate": 0.75,
            "conflict_rate": 0.25,
            "gate_failure_rate": 0.5,
            "avg_lead_time_sec": 12.5,
        },
    )

    result = CliRunner().invoke(cli_mod.nexus, ["nexus", "multi-agent", "metrics"])

    assert result.exit_code == 0
    assert "Total Tasks: 4" in result.output
    assert "Success Rate: 75.0%" in result.output
    assert "Avg Lead Time: 12.5s" in result.output


def test_multi_agent_metrics_cli_json_uses_action_result(monkeypatch):
    monkeypatch.setattr(
        cli_mod,
        "get_multi_agent_metrics",
        lambda: {"total_tasks": 4, "success_rate": 0.75},
    )

    result = CliRunner().invoke(cli_mod.nexus, ["nexus", "multi-agent", "metrics", "--json"])

    assert result.exit_code == 0
    assert json.loads(result.output) == {"total_tasks": 4, "success_rate": 0.75}


def test_multi_agent_metrics_cli_translates_action_errors(monkeypatch):
    def fake_get_multi_agent_metrics():
        raise NexusCliActionError("multi-agent metrics unavailable", exit_code=6)

    monkeypatch.setattr(cli_mod, "get_multi_agent_metrics", fake_get_multi_agent_metrics)

    result = CliRunner().invoke(cli_mod.nexus, ["nexus", "multi-agent", "metrics"])

    assert result.exit_code == 6
    assert "Error: multi-agent metrics unavailable" in result.output


def test_get_multi_agent_task_status_reads_one_task_without_click():
    task = FakeTask("T-1", "OPEN", "alice")
    view = get_multi_agent_task_status(
        "T-1",
        orchestrator_factory=lambda: FakeOrchestrator(FakeStateStore({"T-1": task})),
    )

    assert view.text_lines == ["Task: T-1 | Status: OPEN | Owner: alice"]
    assert json.loads(view.json_text or "{}") == {
        "task_id": "T-1",
        "current_status": "OPEN",
        "owner": "alice",
    }


def test_get_multi_agent_task_status_lists_tasks_without_click():
    view = get_multi_agent_task_status(
        None,
        orchestrator_factory=lambda: FakeOrchestrator(
            FakeStateStore(
                {
                    "T-1": FakeTask("T-1", "OPEN", "alice"),
                    "T-2": FakeTask("T-2", "DONE", "bob"),
                }
            )
        ),
    )

    assert view == TaskStatusView(
        text_lines=["T-1: OPEN (alice)", "T-2: DONE (bob)"],
    )


def test_render_multi_agent_task_status_preserves_json_mode():
    view = TaskStatusView(text_lines=["Task: T-1"], json_text='{"task_id": "T-1"}')

    assert render_multi_agent_task_status(view, output_json=False) == ["Task: T-1"]
    assert render_multi_agent_task_status(view, output_json=True) == ['{"task_id": "T-1"}']


def test_get_multi_agent_task_status_reports_missing_task():
    view = get_multi_agent_task_status(
        "missing",
        orchestrator_factory=lambda: FakeOrchestrator(FakeStateStore({})),
    )

    assert view == TaskStatusView(text_lines=["Task missing not found."])


def test_get_multi_agent_task_audit_renders_evidence_chain_without_click():
    task = FakeTask(
        "T-1",
        "DONE",
        "alice",
        evidence_list=[
            FakeEvidence(exit_code=0, command="uv run pytest tests/a.py"),
            FakeEvidence(exit_code=1, command="uv run pytest tests/b.py"),
        ],
    )

    view = get_multi_agent_task_audit(
        "T-1",
        orchestrator_factory=lambda: FakeOrchestrator(FakeStateStore({"T-1": task})),
    )

    assert render_multi_agent_task_audit(view) == [
        "🔍 Auditing Task T-1 (Owner: alice)",
        "Status: DONE",
        "Evidence Count: 2",
        "  [0] ✅ PASS | Command: uv run pytest tests/a.py",
        "  [1] ❌ FAIL | Command: uv run pytest tests/b.py",
    ]


def test_get_multi_agent_task_audit_reports_missing_task():
    view = get_multi_agent_task_audit(
        "missing",
        orchestrator_factory=lambda: FakeOrchestrator(FakeStateStore({})),
    )

    assert view == TaskAuditView(text_lines=["Task missing not found."])


def test_verify_multi_agent_task_runs_gate_without_click():
    class VerifyOrchestrator(FakeOrchestrator):
        def __init__(self):
            super().__init__()
            self.seen_task_ids = []

        def verify_task(self, task_id: str):
            self.seen_task_ids.append(task_id)
            return True

    orchestrator = VerifyOrchestrator()

    view = verify_multi_agent_task("T-verify", orchestrator_factory=lambda: orchestrator)

    assert orchestrator.seen_task_ids == ["T-verify"]
    assert view == TaskVerificationView(
        task_id="T-verify",
        passed=True,
        text_lines=["🔍 Verifying task T-verify...", "✅ Task T-verify passed all gates."],
    )
    assert render_multi_agent_task_verification(view) == view.text_lines


def test_verify_multi_agent_task_preserves_failed_gate_output():
    class VerifyOrchestrator(FakeOrchestrator):
        def verify_task(self, task_id: str):
            return False

    view = verify_multi_agent_task("T-fail", orchestrator_factory=VerifyOrchestrator)

    assert view == TaskVerificationView(
        task_id="T-fail",
        passed=False,
        text_lines=["🔍 Verifying task T-fail...", "❌ Task T-fail failed gates."],
    )


def test_close_multi_agent_task_releases_task_with_cleanup_flag_without_click():
    class CloseOrchestrator(FakeOrchestrator):
        def __init__(self):
            super().__init__()
            self.close_calls = []

        def close_task(self, task_id: str, *, cleanup: bool):
            self.close_calls.append((task_id, cleanup))

    orchestrator = CloseOrchestrator()

    lines = close_multi_agent_task("T-close", no_cleanup=True, orchestrator_factory=lambda: orchestrator)

    assert orchestrator.close_calls == [("T-close", False)]
    assert lines == ["✅ Task T-close closed."]


def test_multi_agent_verify_cli_uses_action_result(monkeypatch):
    monkeypatch.setattr(
        cli_mod,
        "verify_multi_agent_task",
        lambda task_id: TaskVerificationView(
            task_id=task_id,
            passed=True,
            text_lines=["verify started", "verify passed"],
        ),
    )

    result = CliRunner().invoke(cli_mod.nexus, ["nexus", "multi-agent", "verify", "--task-id", "T-verify"])

    assert result.exit_code == 0
    assert "verify started" in result.output
    assert "verify passed" in result.output


def test_multi_agent_close_cli_uses_action_result(monkeypatch):
    calls = []

    def fake_close_multi_agent_task(task_id, *, no_cleanup):
        calls.append((task_id, no_cleanup))
        return ["closed from action"]

    monkeypatch.setattr(cli_mod, "close_multi_agent_task", fake_close_multi_agent_task)

    result = CliRunner().invoke(
        cli_mod.nexus,
        ["nexus", "multi-agent", "close", "--task-id", "T-close", "--no-cleanup"],
    )

    assert result.exit_code == 0
    assert calls == [("T-close", True)]
    assert "closed from action" in result.output


def test_multi_agent_status_cli_uses_action_result(monkeypatch):
    monkeypatch.setattr(
        cli_mod,
        "get_multi_agent_task_status",
        lambda task_id: TaskStatusView(
            text_lines=["Task: T-1 | Status: OPEN | Owner: alice"],
            json_text='{"task_id": "T-1"}',
        ),
    )

    result = CliRunner().invoke(cli_mod.nexus, ["nexus", "multi-agent", "status", "--task-id", "T-1"])

    assert result.exit_code == 0
    assert "Task: T-1 | Status: OPEN | Owner: alice" in result.output

    json_result = CliRunner().invoke(
        cli_mod.nexus,
        ["nexus", "multi-agent", "status", "--task-id", "T-1", "--json"],
    )
    assert json_result.exit_code == 0
    assert json.loads(json_result.output) == {"task_id": "T-1"}


def test_multi_agent_audit_cli_uses_action_result(monkeypatch):
    monkeypatch.setattr(
        cli_mod,
        "get_multi_agent_task_audit",
        lambda task_id: TaskAuditView(text_lines=["Audit T-1"]),
    )

    result = CliRunner().invoke(cli_mod.nexus, ["nexus", "multi-agent", "audit", "--task-id", "T-1"])

    assert result.exit_code == 0
    assert "Audit T-1" in result.output


def test_multi_agent_status_cli_translates_action_errors(monkeypatch):
    def fake_get_multi_agent_task_status(task_id):
        raise NexusCliActionError("multi-agent status unavailable", exit_code=6)

    monkeypatch.setattr(cli_mod, "get_multi_agent_task_status", fake_get_multi_agent_task_status)

    result = CliRunner().invoke(cli_mod.nexus, ["nexus", "multi-agent", "status"])

    assert result.exit_code == 6
    assert "Error: multi-agent status unavailable" in result.output
