from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

import scripts.engine.nexus_cli as cli_mod
from scripts.engine.commands.research_actions import (
    ResearchAutoFlowResult,
    ResearchAutoFlowRouteResult,
    ResearchHumanReportResult,
    ResearchRouteResult,
    ResearchRunResult,
    ResearchSessionActionResult,
    render_research_auto_flow_result,
    render_research_auto_flow_route_explanation,
    render_research_run_result,
    render_research_route_explanation,
    render_research_route_summary,
    render_research_session_action,
    render_research_human_report,
    run_research_auto_flow,
    run_research_auto_flow_route_explanation,
    run_research_finalize_preview,
    run_research_human_report,
    run_research_log_from_last,
    run_research_onboarding,
    run_research_packet,
    run_research_recommend_next,
    run_research_route,
    run_research_run,
    run_research_writeback_lessons,
)


def _route_payload() -> dict:
    return {
        "should_research": True,
        "mode": "external",
        "reason": "low_confidence",
        "recommended_flow": "hyper_sprint",
        "recommended_reason": "risky_task",
        "findings_hits": 1,
        "adjusted_root_cause_confidence": 0.5,
        "historical_hints": ["hint"],
        "require_codex_audit": True,
        "explain_payload": {"why": "because"},
    }


class FakePlanner:
    def __init__(self) -> None:
        self.calls = []

    def plan(self, **kwargs) -> dict:
        self.calls.append(kwargs)
        return {"planned": True}


class FakeResearchSessionService:
    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root
        self.calls = []

    def onboarding(self, **kwargs) -> dict:
        self.calls.append(("onboarding", kwargs))
        return {"session_id": kwargs["session_id"], "ledger_path": "ledger.jsonl"}

    def recommend_next(self, **kwargs) -> dict:
        self.calls.append(("recommend_next", kwargs))
        return {
            "nextStep": {
                "nextAction": {
                    "stage": "claim_scout",
                    "recommended_flow": "research",
                    "reason": "needs evidence",
                }
            },
            "route": kwargs["route"],
        }

    def packet(self, **kwargs) -> dict:
        self.calls.append(("packet", kwargs))
        return {"schema": "nexus_research_packet_v1", "packet_id": "pkt-1"}

    def log_from_last(self, **kwargs) -> dict:
        self.calls.append(("log_from_last", kwargs))
        if kwargs["status"] == "keep":
            return {"logged": True, "entry": {"packet_id": "pkt-1"}}
        return {"logged": False, "reason": "no_packet"}

    def finalize_preview(self, **kwargs) -> dict:
        self.calls.append(("finalize_preview", kwargs))
        return {"ready": True, "entry_count": 2, "keep_count": 1}

    def writeback_pending_lessons(self, **kwargs) -> dict:
        self.calls.append(("writeback_pending_lessons", kwargs))
        return {"written_count": 1}

    def human_report(self, **kwargs) -> str:
        self.calls.append(("human_report", kwargs))
        return "Research Session demo"


def _service_factory(services: list[FakeResearchSessionService]):
    def factory(root: Path) -> FakeResearchSessionService:
        service = FakeResearchSessionService(root)
        services.append(service)
        return service

    return factory


def test_run_research_route_builds_route_without_click(tmp_path: Path):
    calls = []

    def route_builder(**kwargs) -> dict:
        calls.append(kwargs)
        return _route_payload()

    result = run_research_route(
        tmp_path,
        task_desc="fix ws",
        task_type="bug",
        candidate_count=2,
        root_cause_confidence=0.7,
        findings_query="websocket",
        task_id="task-1",
        route_builder=route_builder,
    )

    assert calls == [
        {
            "repo_root": tmp_path,
            "task_desc": "fix ws",
            "task_type": "bug",
            "candidate_count": 2,
            "root_cause_confidence": 0.7,
            "findings_query": "websocket",
            "task_id": "task-1",
        }
    ]
    assert result == ResearchRouteResult(payload=_route_payload(), route_report_path=None)
    assert render_research_route_summary(result) == [
        "Should Research: True",
        "Mode: external",
        "Reason: low_confidence",
        "Recommended Flow: hyper_sprint (risky_task)",
        "Findings Hits: 1",
        "Adjusted RC Confidence: 0.5",
        "Historical Hints: ['hint']",
        "ADVISOR: Low confidence detected. Codex Audit recommended.",
    ]
    assert render_research_route_explanation(result) == [
        "--- ROUTE EXPLANATION ---",
        json.dumps({"why": "because"}, indent=2),
    ]


def test_run_research_route_writes_route_decision_report_with_injected_seams(tmp_path: Path):
    planner = FakePlanner()
    written_reports = []

    def report_writer(path: Path, decision: dict) -> Path:
        written_reports.append((path, decision))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(decision), encoding="utf-8")
        return path

    result = run_research_route(
        tmp_path,
        task_desc="fix ws",
        task_type="bug",
        candidate_count=2,
        root_cause_confidence=0.7,
        findings_query=None,
        task_id=None,
        route_decision_report=".nexus/reports/routes/route.json",
        route_builder=lambda **kwargs: _route_payload(),
        planner_factory=lambda: planner,
        learning_policy_loader=lambda root: {"budget": "ok"},
        decision_builder=lambda **kwargs: {"decision": kwargs},
        report_writer=report_writer,
        timestamp_provider=lambda: 123,
    )

    assert planner.calls == [
        {
            "task_desc": "fix ws",
            "task_type": "bug",
            "route": _route_payload(),
            "budget": {"budget": "ok"},
        }
    ]
    assert written_reports[0][0] == tmp_path / ".nexus/reports/routes/route.json"
    assert written_reports[0][1]["decision"]["task_id"] == "research-route-123"
    assert result.route_report_path == tmp_path / ".nexus/reports/routes/route.json"
    assert result.payload["route_decision_report"] == str(result.route_report_path)
    assert render_research_route_explanation(result)[-1] == f"Route Decision Report: {result.route_report_path}"


def test_research_route_cli_uses_action_result(monkeypatch, tmp_path: Path):
    def fake_run_research_route(repo_root: Path, **kwargs):
        assert repo_root == tmp_path
        assert kwargs["task_desc"] == "fix ws"
        return ResearchRouteResult(payload=_route_payload(), route_report_path=None)

    monkeypatch.setattr(cli_mod, "repo_root", tmp_path)
    monkeypatch.setattr(cli_mod, "run_research_route", fake_run_research_route)

    result = CliRunner().invoke(
        cli_mod.nexus,
        ["nexus", "research:route", "--task-desc", "fix ws", "--output-json"],
    )

    assert result.exit_code == 0
    assert json.loads(result.output)["recommended_flow"] == "hyper_sprint"

    explain = CliRunner().invoke(
        cli_mod.nexus,
        ["nexus", "research:route", "--task-desc", "fix ws", "--explain-route"],
    )
    assert explain.exit_code == 0
    assert "--- ROUTE EXPLANATION ---" in explain.output


def test_run_research_session_actions_call_service_and_render(tmp_path: Path):
    services: list[FakeResearchSessionService] = []
    factory = _service_factory(services)

    onboarding = run_research_onboarding(
        tmp_path,
        session_id="demo",
        goal="goal",
        benchmark="bench",
        metric="score",
        scope=("nexus/app",),
        service_factory=factory,
    )
    route = _route_payload()
    recommend = run_research_recommend_next(
        tmp_path,
        session_id="demo",
        task_desc="verify API",
        task_type="bug",
        candidate_count=1,
        root_cause_confidence=0.9,
        findings_query=None,
        route_builder=lambda **kwargs: route,
        service_factory=factory,
    )
    packet = run_research_packet(
        tmp_path,
        session_id="demo",
        report_file="report.json",
        route_file="route.json",
        json_reader=lambda root, path: {"path": path},
        service_factory=factory,
    )
    logged = run_research_log_from_last(
        tmp_path,
        session_id="demo",
        status="keep",
        description="kept",
        asi_file="asi.json",
        json_reader=lambda root, path: {"asi": path},
        service_factory=factory,
    )
    preview = run_research_finalize_preview(tmp_path, session_id="demo", service_factory=factory)
    writeback = run_research_writeback_lessons(tmp_path, session_id="demo", service_factory=factory)

    assert onboarding == ResearchSessionActionResult("research:onboarding", {"session_id": "demo", "ledger_path": "ledger.jsonl"})
    assert services[0].calls == [
        ("onboarding", {"session_id": "demo", "goal": "goal", "benchmark": "bench", "metric": "score", "scope": ["nexus/app"]})
    ]
    assert services[1].calls[0] == ("recommend_next", {"session_id": "demo", "route": route})
    assert services[2].calls[0] == (
        "packet",
        {"session_id": "demo", "report": {"path": "report.json"}, "route": {"path": "route.json"}},
    )
    assert services[3].calls[0] == (
        "log_from_last",
        {"session_id": "demo", "status": "keep", "description": "kept", "asi": {"asi": "asi.json"}},
    )
    assert render_research_session_action(onboarding) == ["Research session: demo", "Ledger: ledger.jsonl"]
    assert render_research_session_action(recommend) == ["Next: claim_scout", "Flow: research", "Reason: needs evidence"]
    assert render_research_session_action(packet) == ["Research packet: pkt-1"]
    assert render_research_session_action(logged) == ["Logged: pkt-1"]
    assert render_research_session_action(preview) == ["Ready: True", "Entries: 2", "Keeps: 1"]
    assert render_research_session_action(writeback) == ["Lessons written: 1"]


def test_run_research_human_report_writes_optional_output(tmp_path: Path):
    services: list[FakeResearchSessionService] = []

    result = run_research_human_report(
        tmp_path,
        session_id="demo",
        output="reports/human.md",
        service_factory=_service_factory(services),
    )

    assert result == ResearchHumanReportResult(
        report="Research Session demo",
        output_path=tmp_path / "reports/human.md",
    )
    assert result.output_path.read_text(encoding="utf-8") == "Research Session demo"
    assert render_research_human_report(result) == [f"Human report: {result.output_path}"]

    inline = run_research_human_report(
        tmp_path,
        session_id="demo",
        output=None,
        service_factory=_service_factory([]),
    )
    assert render_research_human_report(inline) == ["Research Session demo"]


def test_research_session_cli_uses_action_results(monkeypatch, tmp_path: Path):
    def fake_onboarding(repo_root: Path, **kwargs):
        assert repo_root == tmp_path
        return ResearchSessionActionResult("research:onboarding", {"session_id": "demo", "ledger_path": "ledger.jsonl"})

    def fake_packet(repo_root: Path, **kwargs):
        assert repo_root == tmp_path
        return ResearchSessionActionResult("research:packet", {"packet_id": "pkt-1"})

    def fake_human(repo_root: Path, **kwargs):
        assert repo_root == tmp_path
        return ResearchHumanReportResult("Research Session demo", None)

    monkeypatch.setattr(cli_mod, "repo_root", tmp_path)
    monkeypatch.setattr(cli_mod, "run_research_onboarding", fake_onboarding)
    monkeypatch.setattr(cli_mod, "run_research_packet", fake_packet)
    monkeypatch.setattr(cli_mod, "run_research_human_report", fake_human)

    runner = CliRunner()
    onboard = runner.invoke(
        cli_mod.nexus,
        ["nexus", "research:onboarding", "--session-id", "demo", "--goal", "goal"],
    )
    packet = runner.invoke(cli_mod.nexus, ["nexus", "research:packet", "--session-id", "demo", "--output-json"])
    human = runner.invoke(cli_mod.nexus, ["nexus", "research:human-report", "--session-id", "demo"])

    assert onboard.exit_code == 0
    assert "Research session: demo" in onboard.output
    assert packet.exit_code == 0
    assert json.loads(packet.output)["packet_id"] == "pkt-1"
    assert human.exit_code == 0
    assert human.output.strip() == "Research Session demo"


def test_run_research_auto_flow_writes_completion_report_with_injected_runner(tmp_path: Path):
    calls = []
    report_path = tmp_path / ".nexus/reports/research/auto-flow-report.json"

    def fake_auto_flow_runner(**kwargs):
        calls.append(kwargs)
        return (
            {
                "chosen_flow": "baseline",
                "result": {"status": "SUCCESS", "elapsed_sec": 0.1},
                "io": {"output_written": False, "output_path": None},
            },
            report_path,
        )

    result = run_research_auto_flow(
        tmp_path,
        task_desc="fix race",
        target_file="demo.py",
        test_file="tests/test_demo.py",
        task_type="bug",
        success_criteria="all_target_tests_pass",
        candidate_count=1,
        root_cause_confidence=1.0,
        findings_query=None,
        llm_mode=False,
        llm_baseline=False,
        llm_baseline_required=False,
        timeout_sec=60,
        stage1_timeout_sec=20,
        max_time_ratio_guard=1.5,
        baseline_fast_sec=9.0,
        history_window=5,
        history_fail_threshold=2,
        dynamic_timeout_multiplier=2.5,
        min_dynamic_stage1_timeout=12,
        force_flow="baseline",
        report_file=".nexus/reports/research/auto-flow-report.json",
        output_file=None,
        task_id="task-1",
        research_session_id="",
        research_gate=False,
        auto_flow_runner=fake_auto_flow_runner,
    )

    assert calls[0]["repo_root"] == tmp_path
    assert calls[0]["task_desc"] == "fix race"
    assert calls[0]["force_flow"] == "baseline"
    assert result == ResearchAutoFlowResult(
        payload=json.loads(report_path.read_text(encoding="utf-8")),
        report_path=report_path,
        exit_code=0,
        blocked=False,
        completion_handoff_path=None,
        completion_error=None,
    )
    assert result.payload["semantic_status"] == "VERIFIED"
    assert result.payload["execution_path"] == "cli->research_flow_service"
    assert render_research_auto_flow_result(result) == [
        "Chosen Flow: baseline",
        "Status: SUCCESS",
        "Elapsed: 0.1 sec",
        f"Report: {report_path}",
        "Output Written: False",
        "Output Path: N/A",
        "Semantic Status: VERIFIED",
    ]


def test_run_research_auto_flow_blocks_preflight_before_runner(tmp_path: Path):
    called = False

    def fake_auto_flow_runner(**kwargs):
        nonlocal called
        called = True
        return ({}, tmp_path / "unused.json")

    result = run_research_auto_flow(
        tmp_path,
        task_desc="verify sdk contract",
        target_file="demo.py",
        test_file="tests/test_demo.py",
        task_type="bug",
        success_criteria="all_target_tests_pass",
        candidate_count=1,
        root_cause_confidence=1.0,
        findings_query=None,
        llm_mode=False,
        llm_baseline=False,
        llm_baseline_required=False,
        timeout_sec=60,
        stage1_timeout_sec=20,
        max_time_ratio_guard=1.5,
        baseline_fast_sec=9.0,
        history_window=5,
        history_fail_threshold=2,
        dynamic_timeout_multiplier=2.5,
        min_dynamic_stage1_timeout=12,
        force_flow=None,
        report_file=".nexus/reports/research/auto-flow-report.json",
        output_file=None,
        task_id=None,
        research_session_id="claim-gate",
        research_gate=True,
        auto_flow_runner=fake_auto_flow_runner,
        research_preflight=lambda **kwargs: {
            "blocked": True,
            "block_reasons": ["claim_uncertainty_requires_research"],
            "next_action": "verify_contract_before_editing",
        },
    )

    assert called is False
    assert result.exit_code == 1
    assert result.blocked is True
    assert result.payload["semantic_status"] == "BLOCKED"
    assert result.report_path == tmp_path / ".nexus/reports/research/auto-flow-report.json"


def test_run_research_auto_flow_route_explanation_uses_action_seam(tmp_path: Path):
    route = _route_payload()
    result = run_research_auto_flow_route_explanation(
        tmp_path,
        task_desc="fix race",
        task_type="bug",
        candidate_count=1,
        root_cause_confidence=0.8,
        findings_query=None,
        target_file="demo.py",
        route_builder=lambda **kwargs: route,
    )

    assert result == ResearchAutoFlowRouteResult(payload=route)
    assert render_research_auto_flow_route_explanation(result) == [
        "--- ROUTE EXPLANATION ---",
        json.dumps(route["explain_payload"], indent=2),
    ]


def test_research_auto_flow_cli_uses_action_result(monkeypatch, tmp_path: Path):
    def fake_run_auto_flow(repo_root: Path, **kwargs):
        assert repo_root == tmp_path
        assert kwargs["task_desc"] == "fix race"
        return ResearchAutoFlowResult(
            payload={
                "chosen_flow": "baseline",
                "result": {"status": "SUCCESS", "elapsed_sec": 0.1},
                "io": {"output_written": False, "output_path": None},
                "semantic_status": "VERIFIED",
            },
            report_path=tmp_path / "report.json",
            exit_code=0,
        )

    monkeypatch.setattr(cli_mod, "repo_root", tmp_path)
    monkeypatch.setattr(cli_mod, "run_research_auto_flow", fake_run_auto_flow)

    result = CliRunner().invoke(
        cli_mod.nexus,
        [
            "nexus",
            "research:auto-flow",
            "--task-desc",
            "fix race",
            "--target-file",
            "demo.py",
            "--test-file",
            "tests/test_demo.py",
            "--output-json",
        ],
    )

    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["chosen_flow"] == "baseline"


def test_run_research_run_fails_governance_without_candidate_execution(tmp_path: Path):
    result = run_research_run(
        tmp_path,
        run_id="run-1",
        candidate_id="candidate-main",
        candidate_count=0,
        hypothesis="invalid candidate count",
        scope=(),
        candidate_src_root=Path("."),
        budget_limit=100.0,
        min_score_threshold=0.5,
        estimated_cost_per_round=1.0,
        dry_run=True,
        report_file=Path(".nexus/reports/research/report.json"),
        max_parallel=1,
        max_retries=0,
        continuation_attempts=0,
        timeout_sec=60,
        retain_last_n=20,
        disk_watermark_gb=0.0,
        research_session_id="",
        research_gate=False,
        task_type="bug",
        root_cause_confidence=1.0,
        findings_query=None,
        disk_usage=lambda root: (0, 0, 10 * 1024**3),
    )

    assert isinstance(result, ResearchRunResult)
    assert result.exit_code == 1
    assert result.output_payload["status"] == "failed"
    assert result.output_payload["semantic_status"] == "BLOCKED"
    assert result.report_payload["rejected_reasons"] == ["invalid_candidate_count"]
    assert result.report_path == tmp_path / ".nexus/reports/research/report.json"
    assert json.loads(result.report_path.read_text(encoding="utf-8"))["semantic_status"] == "BLOCKED"


def test_research_run_cli_uses_action_result(monkeypatch, tmp_path: Path):
    def fake_run_research_run(repo_root: Path, **kwargs):
        assert repo_root == tmp_path
        assert kwargs["hypothesis"] == "try safe run"
        return ResearchRunResult(
            output_payload={
                "status": "success",
                "winner": "candidate-main",
                "report_file": str(tmp_path / "report.json"),
                "semantic_status": "VERIFIED",
                "retryable": False,
                "blocker_type": "none",
                "next_action": "none",
                "next_action_file": None,
            },
            report_payload={"semantic_status": "VERIFIED"},
            report_path=tmp_path / "report.json",
            exit_code=0,
        )

    monkeypatch.setattr(cli_mod, "repo_root", tmp_path)
    monkeypatch.setattr(cli_mod, "run_research_run", fake_run_research_run)

    result = CliRunner().invoke(
        cli_mod.nexus,
        ["nexus", "research:run", "--hypothesis", "try safe run"],
    )

    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["semantic_status"] == "VERIFIED"
