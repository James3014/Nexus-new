from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from click.testing import CliRunner

import scripts.engine.nexus_cli as cli_mod
from scripts.engine.commands.exception_translation import NexusCliActionError
from scripts.engine.commands.learn_actions import (
    LearnAskResult,
    LearnConvergeResult,
    LearnIngestResult,
    LearnGateResult,
    LearnPhaseReportResult,
    LearnReportResult,
    LearnSourceLifecycleResult,
    get_learn_phase_policy,
    get_learn_scheduler_status,
    render_learn_ask_response,
    render_learn_converge_complete,
    render_learn_ingest_complete,
    render_learn_gate_complete,
    render_learn_phase_kpi_complete,
    render_learn_phase_policy,
    render_learn_phase_slo_complete,
    render_learn_report_complete,
    render_learn_refresh_complete,
    render_learn_refresh_plan_complete,
    render_learn_register_source_complete,
    render_learn_scheduler_status,
    render_learn_precision_benchmark_complete,
    run_learn_ask,
    run_learn_converge,
    run_learn_ingest,
    run_learn_gate,
    run_learn_phase_kpi,
    run_learn_phase_slo,
    run_learn_report,
    run_learn_precision_benchmark,
    run_learn_refresh,
    run_learn_refresh_plan,
    run_learn_register_source,
    verify_learn_phase_report_completion,
    enforce_learn_ingest_semantic_contract,
    enforce_learn_report_semantic_contract,
    verify_learn_source_lifecycle_completion,
    write_learn_precision_benchmark_output,
)


class FakeLearnService:
    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root

    def read_phase_slo_summary(self) -> dict:
        return {"overall_pass_rate": 0.8}


@dataclass(frozen=True)
class FakeStrictness:
    value: str


@dataclass(frozen=True)
class FakeActions:
    allow_research: bool
    force_baseline: bool
    require_writeback: bool
    audit_strictness: FakeStrictness
    reasoning: str


def test_get_learn_phase_policy_builds_payload_without_click(tmp_path: Path):
    calls = []

    def service_factory(root: Path) -> FakeLearnService:
        calls.append(root)
        return FakeLearnService(root)

    def derive_actions(slo_summary: dict, task_type: str, risk: str) -> FakeActions:
        assert slo_summary == {"overall_pass_rate": 0.8}
        assert task_type == "feature"
        assert risk == "high"
        return FakeActions(True, False, True, FakeStrictness("strict"), "ready")

    payload = get_learn_phase_policy(
        tmp_path,
        task_type="feature",
        risk="high",
        service_factory=service_factory,
        derive_actions=derive_actions,
    )

    assert calls == [tmp_path]
    assert payload == {
        "task_type": "feature",
        "risk": "high",
        "slo_readiness": 0.8,
        "policy": {
            "allow_research": True,
            "force_baseline": False,
            "require_writeback": True,
            "audit_strictness": "strict",
            "reasoning": "ready",
        },
    }


def test_render_learn_phase_policy_preserves_cli_output_schema():
    lines = render_learn_phase_policy(
        {
            "slo_readiness": 0.8,
            "policy": {
                "allow_research": True,
                "force_baseline": False,
                "reasoning": "ready",
            },
        }
    )

    assert lines == [
        "SLO Readiness: 80.0%",
        "Allow Research: True",
        "Force Baseline: False",
        "Reasoning: ready",
    ]


def test_get_learn_scheduler_status_reads_utf8_and_last_three_alerts(tmp_path: Path):
    report = tmp_path / ".nexus/reports/learn/scheduler_last_run.json"
    report.parent.mkdir(parents=True)
    report.write_text(
        json.dumps({"timestamp": "2026-05-22T12:00:00Z", "exit_code": 2, "slo_readiness": 0.7}),
        encoding="utf-8",
    )
    alerts = tmp_path / ".nexus/reports/alerts"
    alerts.mkdir(parents=True)
    for name in ["a.json", "b.json", "c.json", "d.json"]:
        (alerts / name).write_text("{}", encoding="utf-8")

    payload = get_learn_scheduler_status(tmp_path)

    assert payload == {
        "last_run": "2026-05-22T12:00:00Z",
        "last_exit_code": 2,
        "slo_readiness": 0.7,
        "alert_count": 4,
        "alert_paths": ["b.json", "c.json", "d.json"],
    }


def test_get_learn_scheduler_status_returns_none_without_history(tmp_path: Path):
    assert get_learn_scheduler_status(tmp_path) is None


def test_render_learn_scheduler_status_preserves_cli_output_schema():
    lines = render_learn_scheduler_status(
        {"last_run": "2026-05-22T12:00:00Z", "last_exit_code": 2, "alert_count": 4}
    )

    assert lines == [
        "Last Run: 2026-05-22T12:00:00Z",
        "Status: DEGRADED",
        "Alerts Found: 4",
    ]


def test_learn_phase_policy_cli_uses_action_result(monkeypatch, tmp_path: Path):
    def fake_get_learn_phase_policy(root: Path, *, task_type: str, risk: str):
        assert root == tmp_path
        assert task_type == "feature"
        assert risk == "high"
        return {
            "task_type": task_type,
            "risk": risk,
            "slo_readiness": 0.8,
            "policy": {"allow_research": True, "force_baseline": False, "reasoning": "ready"},
        }

    monkeypatch.setattr(cli_mod, "repo_root", tmp_path)
    monkeypatch.setattr(cli_mod, "get_learn_phase_policy", fake_get_learn_phase_policy)

    result = CliRunner().invoke(
        cli_mod.nexus,
        ["nexus", "learn:phase-policy", "--task-type", "feature", "--risk", "high"],
    )

    assert result.exit_code == 0
    assert "SLO Readiness: 80.0%" in result.output
    assert "Allow Research: True" in result.output


def test_learn_scheduler_status_cli_json_and_empty_history(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(cli_mod, "repo_root", tmp_path)
    monkeypatch.setattr(cli_mod, "get_learn_scheduler_status", lambda root: None)

    empty = CliRunner().invoke(cli_mod.nexus, ["nexus", "learn:scheduler-status"])
    assert empty.exit_code == 0
    assert "No scheduler run history found." in empty.output

    monkeypatch.setattr(
        cli_mod,
        "get_learn_scheduler_status",
        lambda root: {"last_run": "t", "last_exit_code": 0, "slo_readiness": 1.0, "alert_count": 0, "alert_paths": []},
    )

    result = CliRunner().invoke(cli_mod.nexus, ["nexus", "learn:scheduler-status", "--output-json"])
    assert result.exit_code == 0
    assert json.loads(result.output)["last_exit_code"] == 0


def test_learn_action_cli_translates_action_errors(monkeypatch, tmp_path: Path):
    def fake_get_learn_phase_policy(root: Path, *, task_type: str, risk: str):
        raise NexusCliActionError("learn policy unavailable", exit_code=6)

    monkeypatch.setattr(cli_mod, "repo_root", tmp_path)
    monkeypatch.setattr(cli_mod, "get_learn_phase_policy", fake_get_learn_phase_policy)

    result = CliRunner().invoke(cli_mod.nexus, ["nexus", "learn:phase-policy"])

    assert result.exit_code == 6
    assert "Error: learn policy unavailable" in result.output


class FakeSourceLifecycleService:
    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root
        self.calls = []

    def register_source(self, **kwargs) -> dict:
        self.calls.append(("register_source", kwargs))
        return {"status": "SUCCESS", "source_id": "src-1"}

    def refresh_sources(self, **kwargs) -> dict:
        self.calls.append(("refresh_sources", kwargs))
        return {"status": "SUCCESS", "refreshed_count": 2, "skipped_count": 1}

    def build_refresh_plan(self, **kwargs) -> dict:
        self.calls.append(("build_refresh_plan", kwargs))
        return {"status": "SUCCESS", "due_count": 3, "sources_total": 5}

    def build_report(self, **kwargs) -> dict:
        self.calls.append(("build_report", kwargs))
        return {
            "sources_count": 2,
            "claims_count": 4,
            "coverage": 0.75,
            "converged": True,
            "citation_valid_ratio": 1.0,
            "unresolved_questions": [{"question": "q?", "reason": "missing"}],
        }

    def ingest(self, **kwargs) -> dict:
        self.calls.append(("ingest", kwargs))
        return {
            "claims_count": 3,
            "verified_claims_count": 2,
            "source_ref": "src-ref",
            "channel_counts": {"tactical_data": 2, "governance_principles": 1},
        }

    def build_phase_slo_report(self, **kwargs) -> dict:
        self.calls.append(("build_phase_slo_report", kwargs))
        return {"status": "SUCCESS", "phase_slo_pass": True, "global": {"required_done_ratio": 1.0}}

    def build_phase_kpi_report(self, **kwargs) -> dict:
        self.calls.append(("build_phase_kpi_report", kwargs))
        return {
            "status": "SUCCESS",
            "total_records": 2,
            "global": {"success_ratio": 0.5, "required_done_ratio": 0.75},
        }


def test_run_learn_source_lifecycle_actions_write_report_and_finalize(tmp_path: Path):
    services = []
    verified = []

    def service_factory(root: Path) -> FakeSourceLifecycleService:
        service = FakeSourceLifecycleService(root)
        services.append(service)
        return service

    registered = run_learn_register_source(
        tmp_path,
        topic="nexus",
        source="docs://one",
        source_file=None,
        refresh_after_days=14,
        priority="medium",
        report_file=".nexus/reports/learn/register.json",
        service_factory=service_factory,
    )

    assert registered.command_name == "learn:register-source"
    assert registered.report_path == tmp_path / ".nexus/reports/learn/register.json"
    assert registered.payload["status"] == "SUCCESS"
    assert registered.payload["runtime_status"] == "SUCCESS"
    assert registered.payload["source_id"] == "src-1"
    assert registered.payload["semantic_status"] == "VERIFIED"
    assert registered.payload["command_name"] == "learn:register-source"
    assert registered.payload["task_name"] == "register source topic=nexus"
    assert registered.payload["execution_path"] == "cli->learn_mode_service"
    assert json.loads(registered.report_path.read_text(encoding="utf-8")) == {
        "status": "SUCCESS",
        "source_id": "src-1",
    }

    refreshed = run_learn_refresh(
        tmp_path,
        topic="nexus",
        due_only=True,
        pass_threshold=0.7,
        question_count=8,
        report_file=".nexus/reports/learn/refresh.json",
        service_factory=service_factory,
    )
    planned = run_learn_refresh_plan(
        tmp_path,
        topic="nexus",
        due_within_days=2,
        report_file=".nexus/reports/learn/refresh_plan.json",
        service_factory=service_factory,
    )

    assert [service.calls[0] for service in services] == [
        (
            "register_source",
            {
                "topic": "nexus",
                "source": "docs://one",
                "source_file": None,
                "refresh_after_days": 14,
                "priority": "medium",
            },
        ),
        (
            "refresh_sources",
            {"topic": "nexus", "due_only": True, "pass_threshold": 0.7, "question_count": 8},
        ),
        ("build_refresh_plan", {"topic": "nexus", "due_within_days": 2}),
    ]
    assert render_learn_register_source_complete(registered, topic="nexus", source="docs://one") == [
        "✅ Learn source registered: topic=nexus source=docs://one",
        f"Report: {registered.report_path}",
    ]
    assert render_learn_refresh_complete(refreshed) == [
        "✅ Learn refresh complete: refreshed=2 skipped=1",
        f"Report: {refreshed.report_path}",
    ]
    assert render_learn_refresh_plan_complete(planned) == [
        "✅ Learn refresh plan generated: due=3 total=5",
        f"Report: {planned.report_path}",
    ]

    verify_learn_source_lifecycle_completion(
        registered,
        completion_verifier=lambda payload, *, context: verified.append((payload, context)),
    )
    assert verified == [(registered.payload, "learn:register-source")]


def test_learn_source_lifecycle_cli_uses_action_results(monkeypatch, tmp_path: Path):
    verified = []

    def fake_register(repo_root: Path, **kwargs):
        assert repo_root == tmp_path
        assert kwargs["topic"] == "nexus"
        return LearnSourceLifecycleResult(
            "learn:register-source",
            {"status": "SUCCESS", "semantic_status": "UNVERIFIED"},
            tmp_path / "register.json",
        )

    def fake_refresh(repo_root: Path, **kwargs):
        assert repo_root == tmp_path
        assert kwargs["due_only"] is True
        return LearnSourceLifecycleResult(
            "learn:refresh",
            {"status": "SUCCESS", "refreshed_count": 2, "skipped_count": 1, "semantic_status": "UNVERIFIED"},
            tmp_path / "refresh.json",
        )

    def fake_plan(repo_root: Path, **kwargs):
        assert repo_root == tmp_path
        assert kwargs["due_within_days"] == 3
        return LearnSourceLifecycleResult(
            "learn:refresh-plan",
            {"status": "SUCCESS", "due_count": 1, "sources_total": 4, "semantic_status": "UNVERIFIED"},
            tmp_path / "refresh_plan.json",
        )

    monkeypatch.setattr(cli_mod, "repo_root", tmp_path)
    monkeypatch.setattr(cli_mod, "run_learn_register_source", fake_register)
    monkeypatch.setattr(cli_mod, "run_learn_refresh", fake_refresh)
    monkeypatch.setattr(cli_mod, "run_learn_refresh_plan", fake_plan)
    monkeypatch.setattr(
        cli_mod,
        "verify_learn_source_lifecycle_completion",
        lambda result: verified.append(result.command_name),
    )

    runner = CliRunner()
    registered = runner.invoke(
        cli_mod.nexus,
        ["nexus", "learn:register-source", "--topic", "nexus", "--source", "docs://one"],
    )
    refreshed = runner.invoke(cli_mod.nexus, ["nexus", "learn:refresh", "--topic", "nexus"])
    planned = runner.invoke(
        cli_mod.nexus,
        ["nexus", "learn:refresh-plan", "--topic", "nexus", "--due-within-days", "3", "--output-json"],
    )

    assert registered.exit_code == 0
    assert "Learn source registered" in registered.output
    assert refreshed.exit_code == 0
    assert "refreshed=2 skipped=1" in refreshed.output
    assert planned.exit_code == 0
    assert json.loads(planned.output)["sources_total"] == 4
    assert verified == ["learn:register-source", "learn:refresh", "learn:refresh-plan"]


def test_run_learn_phase_reports_write_report_finalize_and_verify(tmp_path: Path):
    services = []
    verified = []

    def service_factory(root: Path) -> FakeSourceLifecycleService:
        service = FakeSourceLifecycleService(root)
        services.append(service)
        return service

    slo = run_learn_phase_slo(
        tmp_path,
        window=100,
        report_file=".nexus/reports/learn/phase_slo_summary.json",
        service_factory=service_factory,
    )
    kpi = run_learn_phase_kpi(
        tmp_path,
        window=200,
        report_file=".nexus/reports/learn/phase_kpi_report.json",
        service_factory=service_factory,
    )

    assert [service.calls[0] for service in services] == [
        ("build_phase_slo_report", {"window": 100}),
        ("build_phase_kpi_report", {"window": 200}),
    ]
    assert slo.command_name == "learn:phase-slo"
    assert slo.payload["runtime_status"] == "SUCCESS"
    assert slo.payload["semantic_status"] == "VERIFIED"
    assert slo.payload["phase_slo_pass"] is True
    assert json.loads(slo.report_path.read_text(encoding="utf-8")) == {
        "status": "SUCCESS",
        "phase_slo_pass": True,
        "global": {"required_done_ratio": 1.0},
    }
    assert kpi.command_name == "learn:phase-kpi"
    assert kpi.payload["runtime_status"] == "SUCCESS"
    assert kpi.payload["total_records"] == 2
    assert render_learn_phase_slo_complete(slo) == [
        "✅ Learn phase SLO summary generated",
        "phase_slo_pass=True required_done_ratio=1.0",
        f"Report: {slo.report_path}",
    ]
    assert render_learn_phase_kpi_complete(kpi) == [
        "✅ Learn phase KPI report generated",
        "total_records=2 success_ratio=0.5 required_done_ratio=0.75",
        f"Report: {kpi.report_path}",
    ]

    verify_learn_phase_report_completion(
        kpi,
        completion_verifier=lambda payload, *, context: verified.append((payload, context)),
    )
    assert verified == [(kpi.payload, "learn:phase-kpi")]


def test_learn_phase_report_cli_uses_action_results(monkeypatch, tmp_path: Path):
    verified = []

    def fake_slo(repo_root: Path, **kwargs):
        assert repo_root == tmp_path
        assert kwargs["window"] == 100
        return LearnPhaseReportResult(
            "learn:phase-slo",
            {"status": "SUCCESS", "phase_slo_pass": True, "global": {"required_done_ratio": 1.0}},
            tmp_path / "slo.json",
        )

    def fake_kpi(repo_root: Path, **kwargs):
        assert repo_root == tmp_path
        assert kwargs["window"] == 200
        return LearnPhaseReportResult(
            "learn:phase-kpi",
            {"status": "SUCCESS", "total_records": 2, "global": {"success_ratio": 0.5, "required_done_ratio": 0.75}},
            tmp_path / "kpi.json",
        )

    monkeypatch.setattr(cli_mod, "repo_root", tmp_path)
    monkeypatch.setattr(cli_mod, "run_learn_phase_slo", fake_slo)
    monkeypatch.setattr(cli_mod, "run_learn_phase_kpi", fake_kpi)
    monkeypatch.setattr(
        cli_mod,
        "verify_learn_phase_report_completion",
        lambda result: verified.append(result.command_name),
    )

    runner = CliRunner()
    slo = runner.invoke(cli_mod.nexus, ["nexus", "learn:phase-slo", "--window", "100"])
    kpi = runner.invoke(cli_mod.nexus, ["nexus", "learn:phase-kpi", "--window", "200", "--output-json"])

    assert slo.exit_code == 0
    assert "Learn phase SLO summary generated" in slo.output
    assert kpi.exit_code == 0
    assert json.loads(kpi.output)["total_records"] == 2
    assert verified == ["learn:phase-slo", "learn:phase-kpi"]


def test_run_learn_report_writes_markdown_report_and_semantic_contract(tmp_path: Path):
    services = []
    markdown_calls = []
    semantic_calls = []

    def service_factory(root: Path) -> FakeSourceLifecycleService:
        service = FakeSourceLifecycleService(root)
        services.append(service)
        return service

    def markdown_writer(base_root: Path, path: Path, task: str, data: dict, evidence: str, debt: str) -> Path:
        out = (base_root / path).resolve()
        markdown_calls.append((task, evidence, debt, data))
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text("markdown", encoding="utf-8")
        return out

    def semantic_evaluator(*, root: Path, payload: dict, command_name: str, markdown_report_written: bool) -> dict:
        semantic_calls.append((root, payload, command_name, markdown_report_written))
        return {"semantic_status": "VERIFIED", "semantic_failures": []}

    result = run_learn_report(
        tmp_path,
        topic="nexus",
        question_count=5,
        pass_threshold=0.6,
        report_file=".nexus/reports/learn/report.json",
        markdown_report_file=".nexus/reports/learn/report.md",
        service_factory=service_factory,
        markdown_writer=markdown_writer,
        semantic_evaluator=semantic_evaluator,
    )

    assert services[0].calls == [("build_report", {"topic": "nexus", "question_count": 5, "pass_threshold": 0.6})]
    assert markdown_calls[0][0] == "learn:report topic=nexus"
    assert "claims_count=4" in markdown_calls[0][1]
    assert markdown_calls[0][2] == "q? - missing"
    assert semantic_calls[0][2:] == ("learn:report", True)
    assert result == LearnReportResult(
        topic="nexus",
        payload={
            "sources_count": 2,
            "claims_count": 4,
            "coverage": 0.75,
            "converged": True,
            "citation_valid_ratio": 1.0,
            "unresolved_questions": [{"question": "q?", "reason": "missing"}],
            "semantic_status": "VERIFIED",
            "semantic_failures": [],
        },
        report_path=tmp_path / ".nexus/reports/learn/report.json",
        markdown_path=tmp_path / ".nexus/reports/learn/report.md",
    )
    assert json.loads(result.report_path.read_text(encoding="utf-8")) == result.payload
    assert render_learn_report_complete(result) == [
        "✅ Learn report generated",
        "sources=2 claims=4 coverage=0.75 converged=True",
        f"Report: {result.report_path}",
        f"Markdown: {result.markdown_path}",
    ]


def test_learn_report_semantic_contract_enforcer_raises_action_error():
    result = LearnReportResult(
        topic="nexus",
        payload={"semantic_status": "UNVERIFIED", "semantic_failures": ["missing_identity"]},
        report_path=Path("report.json"),
        markdown_path=Path("report.md"),
    )

    try:
        enforce_learn_report_semantic_contract(result)
    except NexusCliActionError as exc:
        assert str(exc) == "Learn report semantic contract failed: missing_identity"
    else:
        raise AssertionError("expected NexusCliActionError")


def test_learn_report_cli_uses_action_result(monkeypatch, tmp_path: Path):
    enforced = []

    def fake_run_learn_report(repo_root: Path, **kwargs):
        assert repo_root == tmp_path
        assert kwargs["topic"] == "nexus"
        return LearnReportResult(
            topic="nexus",
            payload={
                "sources_count": 2,
                "claims_count": 4,
                "coverage": 0.75,
                "converged": True,
                "semantic_status": "VERIFIED",
                "semantic_failures": [],
            },
            report_path=tmp_path / "report.json",
            markdown_path=tmp_path / "report.md",
        )

    monkeypatch.setattr(cli_mod, "repo_root", tmp_path)
    monkeypatch.setattr(cli_mod, "run_learn_report", fake_run_learn_report)
    monkeypatch.setattr(cli_mod, "enforce_learn_report_semantic_contract", lambda result: enforced.append(result.topic))

    text = CliRunner().invoke(cli_mod.nexus, ["nexus", "learn:report", "--topic", "nexus"])
    assert text.exit_code == 0
    assert "Learn report generated" in text.output
    assert enforced == ["nexus"]

    output_json = CliRunner().invoke(cli_mod.nexus, ["nexus", "learn:report", "--topic", "nexus", "--output-json"])
    assert output_json.exit_code == 0
    assert json.loads(output_json.output)["claims_count"] == 4
    assert enforced == ["nexus", "nexus"]


def test_run_learn_ingest_writes_evidence_markdown_report_and_semantic_contract(tmp_path: Path):
    services = []
    evidence_calls = []
    gate_calls = []
    markdown_calls = []

    def service_factory(root: Path) -> FakeSourceLifecycleService:
        service = FakeSourceLifecycleService(root)
        services.append(service)
        return service

    def evidence_writer(path: Path | None, final_response: str, evidence_bundle: dict):
        evidence_calls.append((path, final_response, evidence_bundle))
        assert path is not None
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("evidence", encoding="utf-8")
        return path

    def markdown_writer(base_root: Path, path: Path, task: str, data: dict, evidence: str, debt: str) -> Path:
        out = (base_root / path).resolve()
        markdown_calls.append((task, evidence, debt, data))
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text("markdown", encoding="utf-8")
        return out

    result = run_learn_ingest(
        tmp_path,
        source="docs://one",
        source_file=None,
        topic="nexus",
        report_file=".nexus/reports/learn/ingest.json",
        markdown_report_file=".nexus/reports/learn/ingest.md",
        evidence_file=".nexus/reports/learn/evidence_ingest.json",
        service_factory=service_factory,
        evidence_writer=evidence_writer,
        hallucination_gate=lambda final_response, evidence_bundle: gate_calls.append((final_response, evidence_bundle)),
        markdown_writer=markdown_writer,
        semantic_evaluator=lambda **kwargs: {"semantic_status": "VERIFIED", "semantic_failures": []},
    )

    assert services[0].calls == [("ingest", {"source": "docs://one", "source_file": None, "topic": "nexus"})]
    assert evidence_calls[0][1] == "Learn ingest finished for source: docs://one."
    assert evidence_calls[0][2]["test_artifacts"] == ["claims_count=3"]
    assert gate_calls == [(evidence_calls[0][1], evidence_calls[0][2])]
    assert markdown_calls[0][0] == "learn:ingest source=docs://one"
    assert markdown_calls[0][2] == "None"
    assert result == LearnIngestResult(
        source="docs://one",
        payload={
            "claims_count": 3,
            "verified_claims_count": 2,
            "source_ref": "src-ref",
            "channel_counts": {"tactical_data": 2, "governance_principles": 1},
            "semantic_status": "VERIFIED",
            "semantic_failures": [],
        },
        report_path=tmp_path / ".nexus/reports/learn/ingest.json",
        markdown_path=tmp_path / ".nexus/reports/learn/ingest.md",
        evidence_path=tmp_path / ".nexus/reports/learn/evidence_ingest.json",
    )
    assert json.loads(result.report_path.read_text(encoding="utf-8")) == result.payload
    assert render_learn_ingest_complete(result) == [
        "✅ Learn ingest complete: docs://one",
        "Claims: 3, Verified: 2",
        f"Report: {result.report_path}",
        f"Markdown: {result.markdown_path}",
        f"Evidence: {result.evidence_path}",
    ]


def test_learn_ingest_cli_uses_action_result(monkeypatch, tmp_path: Path):
    enforced = []

    def fake_run_learn_ingest(repo_root: Path, **kwargs):
        assert repo_root == tmp_path
        assert kwargs["source"] == "docs://one"
        return LearnIngestResult(
            source="docs://one",
            payload={
                "claims_count": 3,
                "verified_claims_count": 2,
                "semantic_status": "VERIFIED",
                "semantic_failures": [],
            },
            report_path=tmp_path / "ingest.json",
            markdown_path=tmp_path / "ingest.md",
            evidence_path=tmp_path / "evidence.json",
        )

    monkeypatch.setattr(cli_mod, "repo_root", tmp_path)
    monkeypatch.setattr(cli_mod, "run_learn_ingest", fake_run_learn_ingest)
    monkeypatch.setattr(cli_mod, "enforce_learn_ingest_semantic_contract", lambda result: enforced.append(result.source))

    text = CliRunner().invoke(
        cli_mod.nexus,
        ["nexus", "learn:ingest", "--source", "docs://one", "--topic", "nexus"],
    )
    assert text.exit_code == 0
    assert "Learn ingest complete" in text.output
    assert enforced == ["docs://one"]

    output_json = CliRunner().invoke(
        cli_mod.nexus,
        ["nexus", "learn:ingest", "--source", "docs://one", "--topic", "nexus", "--output-json"],
    )
    assert output_json.exit_code == 0
    assert json.loads(output_json.output)["claims_count"] == 3
    assert enforced == ["docs://one", "docs://one"]


def test_learn_ingest_semantic_contract_enforcer_raises_action_error():
    result = LearnIngestResult(
        source="docs://one",
        payload={"semantic_status": "UNVERIFIED", "semantic_failures": ["missing_dual_channel_fields"]},
        report_path=Path("ingest.json"),
        markdown_path=Path("ingest.md"),
        evidence_path=Path("evidence.json"),
    )

    try:
        enforce_learn_ingest_semantic_contract(result)
    except NexusCliActionError as exc:
        assert str(exc) == "Learn ingest semantic contract failed: missing_dual_channel_fields"
    else:
        raise AssertionError("expected NexusCliActionError")


def test_run_learn_gate_writes_evidence_report_and_runs_required_commands(tmp_path: Path):
    commands = []
    evidence_calls = []
    gate_calls = []

    class FakeGateService:
        def __init__(self, repo_root: Path) -> None:
            self.repo_root = repo_root

        def build_report(self, **kwargs) -> dict:
            assert kwargs == {"topic": "nexus"}
            return {
                "claims_count": 8,
                "coverage": 0.9,
                "self_question_pass_rate": 0.8,
                "citation_valid_ratio": 0.99,
            }

    def evidence_writer(path: Path | None, final_response: str, evidence_bundle: dict):
        evidence_calls.append((path, final_response, evidence_bundle))
        assert path is not None
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("evidence", encoding="utf-8")
        return path

    result = run_learn_gate(
        tmp_path,
        topic="nexus",
        pass_threshold=0.6,
        citation_valid_min=0.95,
        claims_min=5,
        report_file=".nexus/reports/learn/gate.json",
        evidence_file=".nexus/reports/learn/evidence_gate.json",
        contract_file=".nexus/config/task_contract.example.json",
        skip_contract=False,
        skip_ci=False,
        service_factory=lambda root: FakeGateService(root),
        evidence_writer=evidence_writer,
        hallucination_gate=lambda final_response, evidence_bundle: gate_calls.append((final_response, evidence_bundle)),
        command_runner=lambda command: commands.append(command),
        python_executable="/python",
    )

    assert result == LearnGateResult(
        payload={
            "claims_count": 8,
            "coverage": 0.9,
            "self_question_pass_rate": 0.8,
            "citation_valid_ratio": 0.99,
        },
        report_path=tmp_path / ".nexus/reports/learn/gate.json",
        evidence_path=tmp_path / ".nexus/reports/learn/evidence_gate.json",
    )
    assert evidence_calls[0][1] == "Validated learn gate. topic=nexus, coverage=0.9, self_question_pass_rate=0.8."
    assert gate_calls == [(evidence_calls[0][1], evidence_calls[0][2])]
    assert len(commands) == 4
    assert commands[0][-2:] == ["--evidence", str(result.evidence_path)]
    assert commands[1][-3:] == ["--json", "--evidence", str(result.evidence_path)]
    assert commands[2][-2:] == ["--contract-file", ".nexus/config/task_contract.example.json"]
    assert commands[3][-2:] == ["--learn-topic", "nexus"]
    assert render_learn_gate_complete(result) == [
        "✅ Learn gate PASSED",
        f"Report: {result.report_path}",
        f"Evidence: {result.evidence_path}",
    ]


def test_run_learn_gate_blocks_before_subprocess_when_thresholds_fail(tmp_path: Path):
    class FakeGateService:
        def __init__(self, repo_root: Path) -> None:
            self.repo_root = repo_root

        def build_report(self, **kwargs) -> dict:
            return {"claims_count": 1, "self_question_pass_rate": 0.2, "citation_valid_ratio": 0.5}

    commands = []

    try:
        run_learn_gate(
            tmp_path,
            topic="nexus",
            pass_threshold=0.6,
            citation_valid_min=0.95,
            claims_min=5,
            report_file=".nexus/reports/learn/gate.json",
            evidence_file=".nexus/reports/learn/evidence_gate.json",
            contract_file=".nexus/config/task_contract.example.json",
            skip_contract=False,
            skip_ci=False,
            service_factory=lambda root: FakeGateService(root),
            hallucination_gate=lambda final_response, evidence_bundle: None,
            command_runner=lambda command: commands.append(command),
            python_executable="/python",
        )
    except NexusCliActionError as exc:
        assert str(exc) == (
            "Learn gate blocked: self_question_pass_rate_below_threshold, "
            "citation_valid_ratio_below_threshold, claims_count_below_threshold"
        )
    else:
        raise AssertionError("expected NexusCliActionError")
    assert commands == []


def test_learn_gate_cli_uses_action_result(monkeypatch, tmp_path: Path):
    def fake_run_learn_gate(repo_root: Path, **kwargs):
        assert repo_root == tmp_path
        assert kwargs["topic"] == "nexus"
        return LearnGateResult(
            payload={"claims_count": 8},
            report_path=tmp_path / "gate.json",
            evidence_path=tmp_path / "evidence.json",
        )

    monkeypatch.setattr(cli_mod, "repo_root", tmp_path)
    monkeypatch.setattr(cli_mod, "run_learn_gate", fake_run_learn_gate)

    result = CliRunner().invoke(cli_mod.nexus, ["nexus", "learn:gate", "--topic", "nexus"])

    assert result.exit_code == 0
    assert "Learn gate PASSED" in result.output


class FakeAskService:
    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root
        self.calls = []
        self.ask_kwargs = []

    def ask(self, *, topic: str, question: str, **kwargs) -> dict:
        self.calls.append((topic, question))
        self.ask_kwargs.append(kwargs)
        if question == "unknown?":
            return {"status": "UNKNOWN", "citations": [], "filtered_out_count": 2}
        return {"status": "ANSWER", "citations": ["c1"], "filtered_out_count": 0}


def test_run_learn_ask_writes_evidence_and_preserves_answer_render(tmp_path: Path):
    services = []
    evidence_calls = []
    gate_calls = []

    def service_factory(root: Path) -> FakeAskService:
        service = FakeAskService(root)
        services.append(service)
        return service

    def evidence_writer(path: Path | None, final_response: str, evidence_bundle: dict):
        evidence_calls.append((path, final_response, evidence_bundle))
        assert path is not None
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"final_response": final_response, "evidence_bundle": evidence_bundle}), encoding="utf-8")
        return path

    result = run_learn_ask(
        tmp_path,
        topic="nexus",
        question="answer?",
        top_k=3,
        min_evidence=2,
        min_token_coverage=0.5,
        max_staleness_days=30,
        allow_cross_pack=True,
        evidence_file=".nexus/reports/learn/evidence_ask.json",
        service_factory=service_factory,
        evidence_writer=evidence_writer,
        hallucination_gate=lambda final_response, evidence_bundle: gate_calls.append((final_response, evidence_bundle)),
    )

    assert services[0].repo_root == tmp_path
    assert services[0].calls == [("nexus", "answer?")]
    assert services[0].ask_kwargs == [
        {
            "top_k": 3,
            "min_evidence": 2,
            "min_token_coverage": 0.5,
            "max_staleness_days": 30,
            "allow_cross_pack": True,
        }
    ]
    assert result == LearnAskResult(
        topic="nexus",
        question="answer?",
        payload={"status": "ANSWER", "citations": ["c1"], "filtered_out_count": 0},
        evidence_path=tmp_path / ".nexus/reports/learn/evidence_ask.json",
    )
    assert evidence_calls[0][1] == "UNKNOWN"
    assert evidence_calls[0][2]["test_artifacts"] == ["claims_used=0"]
    assert evidence_calls[0][2]["command_artifacts"] == ["topic=nexus", "question=answer?"]
    assert gate_calls == [(evidence_calls[0][1], evidence_calls[0][2])]
    assert render_learn_ask_response(result) == ["UNKNOWN"]


def test_render_learn_ask_response_handles_unknown_conflict_and_answer():
    assert render_learn_ask_response(
        LearnAskResult("nexus", "q", {"status": "UNKNOWN"}, None)
    ) == ["UNKNOWN"]
    assert render_learn_ask_response(
        LearnAskResult("nexus", "q", {"status": "CONFLICT"}, None)
    ) == ["CONFLICT"]
    assert render_learn_ask_response(
        LearnAskResult("nexus", "q", {"status": "ANSWER", "answer": "42"}, None)
    ) == ["42"]


def test_learn_ask_cli_uses_action_result(monkeypatch, tmp_path: Path):
    def fake_run_learn_ask(repo_root: Path, **kwargs):
        assert repo_root == tmp_path
        assert kwargs["topic"] == "nexus"
        assert kwargs["question"] == "answer?"
        return LearnAskResult(
            topic="nexus",
            question="answer?",
            payload={"status": "ANSWER", "answer": "answer text"},
            evidence_path=tmp_path / "evidence.json",
        )

    monkeypatch.setattr(cli_mod, "repo_root", tmp_path)
    monkeypatch.setattr(cli_mod, "run_learn_ask", fake_run_learn_ask)

    text = CliRunner().invoke(
        cli_mod.nexus,
        ["nexus", "ask", "--topic", "nexus", "--question", "answer?"],
    )
    assert text.exit_code == 0
    assert text.output.strip() == "answer text"

    json_result = CliRunner().invoke(
        cli_mod.nexus,
        ["nexus", "ask", "--topic", "nexus", "--question", "answer?", "--output-json"],
    )
    assert json_result.exit_code == 0
    assert json.loads(json_result.output) == {"status": "ANSWER", "answer": "answer text"}


class FakeConvergeService:
    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root
        self.calls = []

    def converge(self, **kwargs) -> dict:
        self.calls.append(kwargs)
        return {
            "status": "SUCCESS",
            "converged": True,
            "self_question_pass_rate": 0.75,
            "coverage": 0.8,
            "claims_matched": 3,
        }


def test_run_learn_converge_writes_report_and_evidence_without_click(tmp_path: Path):
    services = []
    evidence_calls = []
    gate_calls = []

    def service_factory(root: Path) -> FakeConvergeService:
        service = FakeConvergeService(root)
        services.append(service)
        return service

    def evidence_writer(path: Path | None, final_response: str, evidence_bundle: dict):
        evidence_calls.append((path, final_response, evidence_bundle))
        assert path is not None
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"final_response": final_response, "evidence_bundle": evidence_bundle}), encoding="utf-8")
        return path

    result = run_learn_converge(
        tmp_path,
        topic="nexus",
        max_rounds=2,
        pass_threshold=0.5,
        question_count=3,
        auto_research=False,
        max_sources_per_round=1,
        swarm_mode=True,
        swarm_max_parallel=2,
        per_source_timeout_sec=10,
        report_file=".nexus/reports/learn/converge_report.json",
        evidence_file=".nexus/reports/learn/evidence_converge.json",
        service_factory=service_factory,
        evidence_writer=evidence_writer,
        hallucination_gate=lambda final_response, evidence_bundle: gate_calls.append((final_response, evidence_bundle)),
    )

    assert services[0].repo_root == tmp_path
    assert services[0].calls == [
        {
            "topic": "nexus",
            "max_rounds": 2,
            "pass_threshold": 0.5,
            "question_count": 3,
            "auto_research": False,
            "max_sources_per_round": 1,
            "swarm_mode": True,
            "swarm_max_parallel": 2,
            "per_source_timeout_sec": 10,
        }
    ]
    assert result.payload["status"] == "SUCCESS"
    assert result.report_path == tmp_path / ".nexus/reports/learn/converge_report.json"
    assert result.evidence_path == tmp_path / ".nexus/reports/learn/evidence_converge.json"
    assert json.loads(result.report_path.read_text(encoding="utf-8"))["converged"] is True
    assert evidence_calls[0][1] == "Converge status for topic nexus: converged=True, pass_rate=0.75."
    assert evidence_calls[0][2]["benchmark_metrics"] == {"success_rate": 0.75, "success_threshold": 0.5}
    assert gate_calls == [(evidence_calls[0][1], evidence_calls[0][2])]
    assert render_learn_converge_complete(result) == [
        "✅ Learn converge complete: topic=nexus",
        "Converged=True | pass_rate=0.75 | coverage=0.8",
        f"Report: {result.report_path}",
        f"Evidence: {result.evidence_path}",
    ]


def test_learn_converge_cli_uses_action_result(monkeypatch, tmp_path: Path):
    result_payload = {"status": "SUCCESS", "converged": True}

    def fake_run_learn_converge(repo_root: Path, **kwargs):
        assert repo_root == tmp_path
        assert kwargs["topic"] == "nexus"
        assert kwargs["max_rounds"] == 2
        return LearnConvergeResult(
            topic="nexus",
            payload=result_payload,
            report_path=tmp_path / "report.json",
            evidence_path=tmp_path / "evidence.json",
        )

    monkeypatch.setattr(cli_mod, "repo_root", tmp_path)
    monkeypatch.setattr(cli_mod, "run_learn_converge", fake_run_learn_converge)

    rendered = CliRunner().invoke(
        cli_mod.nexus,
        [
            "nexus",
            "learn:converge",
            "--topic",
            "nexus",
            "--max-rounds",
            "2",
            "--output-json",
        ],
    )

    assert rendered.exit_code == 0
    assert json.loads(rendered.output) == result_payload


def test_run_learn_precision_benchmark_builds_summary_without_click(tmp_path: Path):
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "cases": [
                    {"q": "answer?", "expected": "ANSWER"},
                    {"q": "unknown?", "expected_status": "ANSWERED"},
                    {"q": "unknown?", "expected": "UNKNOWN"},
                ]
            }
        ),
        encoding="utf-8",
    )
    services = []

    def service_factory(root: Path) -> FakeAskService:
        service = FakeAskService(root)
        services.append(service)
        return service

    summary = run_learn_precision_benchmark(
        tmp_path,
        manifest_file=manifest,
        topic="nexus",
        service_factory=service_factory,
    )

    assert services[0].repo_root == tmp_path
    assert services[0].calls == [
        ("nexus", "answer?"),
        ("nexus", "unknown?"),
        ("nexus", "unknown?"),
    ]
    assert summary["total"] == 3
    assert summary["correct"] == 2
    assert summary["precision"] == 1.0
    assert summary["unknown_correct_rate"] == 1.0
    assert summary["baseline"]["total_questions"] == 3
    assert summary["results"][1]["expected"] == "ANSWER"
    assert summary["results"][1]["actual"] == "UNKNOWN"


def test_write_and_render_learn_precision_benchmark_output(tmp_path: Path):
    summary = {"precision": 0.5, "unknown_correct_rate": 0.25, "status": "SUCCESS"}
    output = tmp_path / "out.json"

    assert write_learn_precision_benchmark_output(summary, output) == output
    assert json.loads(output.read_text(encoding="utf-8")) == summary
    assert render_learn_precision_benchmark_complete(summary) == (
        "✅ Benchmark complete. Precision: 50.00%, Unknown Correct: 25.00%"
    )


def test_learn_benchmark_cli_uses_action_result(monkeypatch, tmp_path: Path):
    manifest = tmp_path / "manifest.json"
    manifest.write_text("{}", encoding="utf-8")
    output = tmp_path / "out.json"

    def fake_run(repo_root: Path, *, manifest_file: str, topic: str):
        assert repo_root == tmp_path
        assert manifest_file == str(manifest)
        assert topic == "nexus"
        return {"precision": 0.5, "unknown_correct_rate": 0.25, "status": "SUCCESS"}

    monkeypatch.setattr(cli_mod, "repo_root", tmp_path)
    monkeypatch.setattr(cli_mod, "run_learn_precision_benchmark", fake_run)

    result = CliRunner().invoke(
        cli_mod.nexus,
        ["nexus", "learn:benchmark", "--manifest-file", str(manifest), "--topic", "nexus", "--output", str(output)],
    )

    assert result.exit_code == 0
    assert "Running Learn Precision Benchmark on topic: nexus" in result.output
    assert "Precision: 50.00%" in result.output
    assert json.loads(output.read_text(encoding="utf-8"))["status"] == "SUCCESS"


def test_learn_benchmark_cli_json_does_not_write_output(monkeypatch, tmp_path: Path):
    manifest = tmp_path / "manifest.json"
    manifest.write_text("{}", encoding="utf-8")
    output = tmp_path / "out.json"

    monkeypatch.setattr(cli_mod, "repo_root", tmp_path)
    monkeypatch.setattr(
        cli_mod,
        "run_learn_precision_benchmark",
        lambda repo_root, *, manifest_file, topic: {"precision": 0.5, "unknown_correct_rate": 0.25},
    )

    result = CliRunner().invoke(
        cli_mod.nexus,
        [
            "nexus",
            "learn:benchmark",
            "--manifest-file",
            str(manifest),
            "--topic",
            "nexus",
            "--output",
            str(output),
            "--output-json",
        ],
    )

    assert result.exit_code == 0
    assert json.loads(result.output) == {"precision": 0.5, "unknown_correct_rate": 0.25}
    assert not output.exists()
