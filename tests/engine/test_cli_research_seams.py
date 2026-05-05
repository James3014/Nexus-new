import json
from pathlib import Path

from click.testing import CliRunner

import scripts.engine.nexus_cli as cli_mod


def test_research_auto_flow_cli_uses_service_seam(monkeypatch, tmp_path):
    captured = {}

    def _fake_run_auto_flow(**kwargs):
        captured.update(kwargs)
        return (
            {
                "chosen_flow": "hyper_sprint",
                "result": {"status": "SUCCESS", "elapsed_sec": 0.2},
                "io": {"output_written": False, "output_path": None},
            },
            tmp_path / ".nexus" / "reports" / "research" / "auto-flow-report.json",
        )

    monkeypatch.setattr(cli_mod, "repo_root", tmp_path)
    monkeypatch.setattr("nexus.app.research_flow_service.run_auto_flow", _fake_run_auto_flow)

    runner = CliRunner()
    res = runner.invoke(
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
            "--force-flow",
            "hyper_sprint",
        ],
    )

    assert res.exit_code == 0, res.output
    assert captured["repo_root"] == tmp_path
    assert captured["task_desc"] == "fix race"
    assert captured["target_file"] == "demo.py"
    assert captured["test_file"] == "tests/test_demo.py"
    assert captured["force_flow"] == "hyper_sprint"


def test_research_auto_flow_emits_completion_contract(monkeypatch, tmp_path):
    report_path = tmp_path / ".nexus" / "reports" / "research" / "auto-flow-report.json"

    def _fake_run_auto_flow(**kwargs):
        return (
            {
                "chosen_flow": "baseline",
                "result": {"status": "SUCCESS", "elapsed_sec": 0.1},
                "io": {"output_written": False, "output_path": None},
            },
            report_path,
        )

    monkeypatch.setattr(cli_mod, "repo_root", tmp_path)
    monkeypatch.setattr("nexus.app.research_flow_service.run_auto_flow", _fake_run_auto_flow)

    runner = CliRunner()
    res = runner.invoke(
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

    assert res.exit_code == 0, res.output
    payload = json.loads(res.output)
    assert payload["semantic_status"] == "VERIFIED"
    assert payload["runtime_classification"] == "verified_pass"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["semantic_status"] == "VERIFIED"
    assert report["execution_path"] == "cli->research_flow_service"


def test_research_auto_flow_gate_blocks_unverified_claim_before_execution(monkeypatch, tmp_path):
    called = False

    def _fake_run_auto_flow(**kwargs):
        nonlocal called
        called = True
        return ({}, tmp_path / "unused.json")

    monkeypatch.setattr(cli_mod, "repo_root", tmp_path)
    monkeypatch.setattr("nexus.app.research_flow_service.run_auto_flow", _fake_run_auto_flow)

    runner = CliRunner()
    res = runner.invoke(
        cli_mod.nexus,
        [
            "nexus",
            "research:auto-flow",
            "--task-desc",
            "Verify SDK API parameter before editing call site",
            "--target-file",
            "demo.py",
            "--test-file",
            "tests/test_demo.py",
            "--research-session-id",
            "claim-gate",
            "--research-gate",
            "--output-json",
        ],
    )

    assert res.exit_code == 1, res.output
    assert called is False
    payload = json.loads(res.output)
    assert payload["semantic_status"] == "BLOCKED"
    assert payload["blocker_type"] == "research_preflight"
    assert payload["next_action"] == "verify_contract_before_editing"
    assert payload["research_preflight"]["route"]["research_context"]["role"] == "claim_scout"


def test_research_auto_flow_session_logs_success_packet(monkeypatch, tmp_path):
    report_path = tmp_path / ".nexus" / "reports" / "research" / "auto-flow-report.json"

    def _fake_run_auto_flow(**kwargs):
        return (
            {
                "chosen_flow": "baseline",
                "result": {"status": "SUCCESS", "elapsed_sec": 0.1},
                "io": {"output_written": False, "output_path": None},
            },
            report_path,
        )

    monkeypatch.setattr(cli_mod, "repo_root", tmp_path)
    monkeypatch.setattr("nexus.app.research_flow_service.run_auto_flow", _fake_run_auto_flow)

    runner = CliRunner()
    res = runner.invoke(
        cli_mod.nexus,
        [
            "nexus",
            "research:auto-flow",
            "--task-desc",
            "fix race condition",
            "--target-file",
            "demo.py",
            "--test-file",
            "tests/test_demo.py",
            "--research-session-id",
            "auto-log",
            "--output-json",
        ],
    )

    assert res.exit_code == 0, res.output
    payload = json.loads(res.output)
    assert payload["research_session"]["logged"] is True
    assert payload["research_session"]["status"] == "keep"
    ledger = tmp_path / ".nexus" / "research_sessions" / "auto-log.jsonl"
    assert ledger.exists()
    assert '"status": "keep"' in ledger.read_text(encoding="utf-8")


def test_research_session_loop_cli_drives_route_packet_and_ledger(monkeypatch, tmp_path):
    monkeypatch.setattr(cli_mod, "repo_root", tmp_path)

    runner = CliRunner()
    onboard = runner.invoke(
        cli_mod.nexus,
        [
            "nexus",
            "research:onboarding",
            "--session-id",
            "demo",
            "--goal",
            "make research improve code routing",
            "--scope",
            "nexus/app",
            "--output-json",
        ],
    )
    assert onboard.exit_code == 0, onboard.output
    manifest = json.loads(onboard.output)
    assert manifest["session_id"] == "demo"

    recommend = runner.invoke(
        cli_mod.nexus,
        [
            "nexus",
            "research:recommend-next",
            "--session-id",
            "demo",
            "--task-desc",
            "Verify the SDK API parameter before editing the route",
            "--output-json",
        ],
    )
    assert recommend.exit_code == 0, recommend.output
    recommendation = json.loads(recommend.output)
    assert recommendation["route"]["research_context"]["role"] == "claim_scout"
    assert "research" in recommendation["nextStep"]["nextAction"]["recommended_capabilities"]

    packet = runner.invoke(
        cli_mod.nexus,
        ["nexus", "research:packet", "--session-id", "demo", "--output-json"],
    )
    assert packet.exit_code == 0, packet.output
    assert json.loads(packet.output)["schema"] == "nexus_research_packet_v1"

    logged = runner.invoke(
        cli_mod.nexus,
        [
            "nexus",
            "research:log-from-last",
            "--session-id",
            "demo",
            "--status",
            "keep",
            "--description",
            "route contract kept",
            "--output-json",
        ],
    )
    assert logged.exit_code == 0, logged.output
    assert json.loads(logged.output)["logged"] is True

    preview = runner.invoke(
        cli_mod.nexus,
        ["nexus", "research:finalize-preview", "--session-id", "demo", "--output-json"],
    )
    assert preview.exit_code == 0, preview.output
    assert json.loads(preview.output)["ready"] is True

    report = runner.invoke(cli_mod.nexus, ["nexus", "research:human-report", "--session-id", "demo"])
    assert report.exit_code == 0, report.output
    assert "Research Session demo" in report.output


def test_research_session_loop_marks_failure_lessons_pending(monkeypatch, tmp_path):
    monkeypatch.setattr(cli_mod, "repo_root", tmp_path)
    runner = CliRunner()

    assert runner.invoke(
        cli_mod.nexus,
        [
            "nexus",
            "research:onboarding",
            "--session-id",
            "lesson-demo",
            "--goal",
            "capture failed research lesson",
        ],
    ).exit_code == 0
    assert runner.invoke(
        cli_mod.nexus,
        ["nexus", "research:packet", "--session-id", "lesson-demo"],
    ).exit_code == 0
    logged = runner.invoke(
        cli_mod.nexus,
        [
            "nexus",
            "research:log-from-last",
            "--session-id",
            "lesson-demo",
            "--status",
            "checks_failed",
            "--description",
            "gate failed after route claim",
            "--output-json",
        ],
    )
    assert logged.exit_code == 0, logged.output
    entry = json.loads(logged.output)["entry"]
    assert entry["asi"]["status"] == "checks_failed"
    assert entry["lesson_writeback"]["required"] is True
    assert entry["lesson_writeback"]["status"] == "pending"

    preview = runner.invoke(
        cli_mod.nexus,
        ["nexus", "research:finalize-preview", "--session-id", "lesson-demo", "--output-json"],
    )
    assert preview.exit_code == 0, preview.output
    payload = json.loads(preview.output)
    assert payload["status_counts"]["checks_failed"] == 1
    assert payload["lesson_writeback_pending_count"] == 1
    assert "lesson_writeback_pending" in payload["warnings"]

    writeback = runner.invoke(
        cli_mod.nexus,
        ["nexus", "research:writeback-lessons", "--session-id", "lesson-demo", "--output-json"],
    )
    assert writeback.exit_code == 0, writeback.output
    writeback_payload = json.loads(writeback.output)
    assert writeback_payload["written_count"] == 1
    assert Path(writeback_payload["written"][0]["memory_path"]).exists()

    preview_after = runner.invoke(
        cli_mod.nexus,
        ["nexus", "research:finalize-preview", "--session-id", "lesson-demo", "--output-json"],
    )
    assert preview_after.exit_code == 0, preview_after.output
    after_payload = json.loads(preview_after.output)
    assert after_payload["lesson_writeback_pending_count"] == 0
    assert "lesson_writeback_pending" not in after_payload["warnings"]


def test_research_run_gate_blocks_unverified_claim_before_candidates(monkeypatch, tmp_path):
    monkeypatch.setattr(cli_mod, "repo_root", tmp_path)
    runner = CliRunner()

    res = runner.invoke(
        cli_mod.nexus,
        [
            "nexus",
            "research:run",
            "--hypothesis",
            "Verify SDK API parameter before editing route",
            "--scope",
            "nexus/research",
            "--research-session-id",
            "run-gate",
            "--research-gate",
        ],
    )

    assert res.exit_code == 1, res.output
    payload = json.loads(res.output)
    assert payload["semantic_status"] == "BLOCKED"
    assert payload["blocker_type"] == "research_preflight"
    assert payload["next_action"] == "verify_contract_before_editing"
    assert payload["research_preflight"]["route"]["research_context"]["role"] == "claim_scout"


def test_research_benchmark_cli_uses_service_seam(monkeypatch, tmp_path):
    captured = {}

    class _FakeService:
        def __init__(self, repo_root):
            captured["repo_root"] = repo_root

        def run_benchmark(
            self,
            mode,
            manifest_file,
            report_file,
            budget_limit,
            timeout_sec,
            max_wall_time_sec,
            ab_trials,
            ab_llm_mode,
            llm_baseline,
        ):
            captured["args"] = {
                "mode": mode,
                "manifest_file": manifest_file,
                "report_file": report_file,
                "budget_limit": budget_limit,
                "timeout_sec": timeout_sec,
                "max_wall_time_sec": max_wall_time_sec,
                "ab_trials": ab_trials,
                "ab_llm_mode": ab_llm_mode,
                "llm_baseline": llm_baseline,
            }

    manifest = tmp_path / "manifest.json"
    manifest.write_text('{"cases":[]}', encoding="utf-8")

    monkeypatch.setattr(cli_mod, "repo_root", tmp_path)
    monkeypatch.setattr("nexus.app.research_benchmark_service.ResearchBenchmarkService", _FakeService)

    runner = CliRunner()
    res = runner.invoke(
        cli_mod.nexus,
        [
            "nexus",
            "research:benchmark",
            "--manifest-file",
            str(manifest),
            "--mode",
            "ab",
            "--ab-trials",
            "2",
        ],
    )

    assert res.exit_code == 0, res.output
    assert captured["repo_root"] == tmp_path
    assert captured["args"]["mode"] == "ab"
    assert captured["args"]["manifest_file"] == str(manifest)
    assert captured["args"]["ab_trials"] == 2


def test_research_run_does_not_route_through_legacy_run_seam():
    source = Path("/Users/jameschen/Workspace/nexus/scripts/engine/nexus_cli.py").read_text(encoding="utf-8")
    start = source.index('@nexus_group.command(name="research:run")')
    end = source.index('@nexus_group.command(name="research:benchmark")')
    block = source[start:end]
    assert "execute_tactical_node" not in block
    assert "execute_single_task_via_service" not in block
