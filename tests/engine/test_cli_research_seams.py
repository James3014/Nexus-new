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
