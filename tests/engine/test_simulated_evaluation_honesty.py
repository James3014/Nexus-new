"""Simulated evaluations must say so, and never ship baked-in credentials (#1733 batch 3)."""

import asyncio
import importlib.util
import json
from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from nexus.app.research_benchmark_service import (
    ARCHIVED_REASON as ResearchArchivedReason,
)
from nexus.app.research_benchmark_service import (
    ArchivedResearchBenchmarkError,
    ResearchBenchmarkService,
)
from nexus.services.benchmark_service import (
    ARCHIVED_REASON,
    ArchivedBenchmarkError,
    BenchmarkService,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
UI_VALIDATOR = REPO_ROOT / "scripts" / "ui-validator.py"


def _load_ui_validator():
    spec = importlib.util.spec_from_file_location("ui_validator_under_test", UI_VALIDATOR)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


LOGIN_DOM = "\n".join([
    '[1] <input> placeholder: "Enter Operator ID"',
    '[2] <input> placeholder: "Passcode"',
    '[3] <button> text: "Authenticate"',
])


def test_ui_validator_source_has_no_baked_in_credentials():
    source = UI_VALIDATOR.read_text(encoding="utf-8")
    assert "nexus_admin" not in source
    assert "singularity" not in source


def test_ui_validator_stops_at_login_without_configured_credentials(monkeypatch):
    module = _load_ui_validator()
    monkeypatch.delenv(module.USER_ENV_VAR, raising=False)
    monkeypatch.delenv(module.PASSWORD_ENV_VAR, raising=False)
    action = json.loads(asyncio.run(module.agent_get_action("login", LOGIN_DOM)))
    assert action == {"action": "finish", "value": module.FINISH_NO_CREDENTIALS}
    assert action["value"] != module.FINISH_SUCCESS


def test_ui_validator_types_operator_supplied_credentials(monkeypatch):
    module = _load_ui_validator()
    monkeypatch.setenv(module.USER_ENV_VAR, "op-user")
    monkeypatch.setenv(module.PASSWORD_ENV_VAR, "op-pass")
    first = json.loads(asyncio.run(module.agent_get_action("login", LOGIN_DOM)))
    assert first == {"action": "type", "target_id": "1", "value": "op-user"}
    second = json.loads(asyncio.run(module.agent_get_action("login", LOGIN_DOM + "\nop-user")))
    assert second == {"action": "type", "target_id": "2", "value": "op-pass"}


def test_benchmark_service_tags_simulation_and_makes_no_quality_claims(tmp_path):
    # Historical node id: the simulated benchmark was archived 2026-10-12 and now fails closed.
    service = BenchmarkService(project_root=str(tmp_path))
    out_csv = tmp_path / "bench.csv"
    with pytest.raises(ArchivedBenchmarkError) as excinfo:
        service.run(
            dataset="missing",
            repeat=1,
            dual_core_physical=True,
            ablation=False,
            tasks_count=3,
            output_csv=str(out_csv),
        )
    assert excinfo.value.reason == "archived_fake_benchmark_2026-10-12"
    assert not out_csv.exists()
    assert not (tmp_path / "dual_core_benchmark.md").exists()
    assert not (tmp_path / ".nexus").exists()


def test_benchmark_service_report_handles_zero_tasks(tmp_path):
    # Historical node id: zero tasks also fails closed and writes nothing.
    service = BenchmarkService(project_root=str(tmp_path))
    with pytest.raises(ArchivedBenchmarkError):
        service.run(
            dataset="missing", repeat=1, dual_core_physical=False, ablation=False, tasks_count=0
        )
    assert not (tmp_path / "dual_core_benchmark.md").exists()


def test_benchmark_service_module_has_no_random_source():
    import nexus.services.benchmark_service as module

    source = Path(module.__file__).read_text(encoding="utf-8")
    assert "import random" not in source


def test_archived_reason_matches_capability_registry_whitelist():
    from nexus.services.capability_registry import ARCHIVED_FAKE_BENCHMARK, SKIP_REASONS

    assert ARCHIVED_REASON == ARCHIVED_FAKE_BENCHMARK == ResearchArchivedReason
    assert ARCHIVED_REASON in SKIP_REASONS


def test_research_benchmark_reports_are_tagged_simulated(tmp_path):
    # Historical node id: both research benchmark modes were archived 2026-10-12 and fail
    # closed instead of writing a "simulated" report.
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"cases": [{"id": "c1"}]}), encoding="utf-8")
    service = ResearchBenchmarkService(tmp_path)

    for mode in ("gladiator", "ab"):
        report = tmp_path / f"{mode}.json"
        with pytest.raises(ArchivedResearchBenchmarkError) as excinfo:
            service.run_benchmark(mode, str(manifest), str(report), 1.0, 5, 0, 1, False, False)
        assert excinfo.value.reason == "archived_fake_benchmark_2026-10-12"
        assert not report.exists()


def _run_meta_opt(tmp_path, child_report):
    from scripts.engine.nexus_cli import nexus

    presets = tmp_path / "presets.json"
    presets.write_text(
        json.dumps([{"name": "p1", "timeout_sec": 1, "ab_trials": 1}]), encoding="utf-8"
    )
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"cases": []}), encoding="utf-8")
    report = tmp_path / "meta.json"

    async def fake_run_async(*args, **_kwargs):
        cmd = args[1] if len(args) > 2 else args[0]
        log_path = args[2] if len(args) > 2 else args[1]
        run_report = Path(cmd[cmd.index("--report-file") + 1])
        run_report.parent.mkdir(parents=True, exist_ok=True)
        run_report.write_text(json.dumps(child_report), encoding="utf-8")
        log_path.write_text("", encoding="utf-8")
        return 0, 0, 0

    with patch("scripts.engine.nexus_cli.AsyncProcessExecutor.run_async", new=fake_run_async):
        result = CliRunner().invoke(
            nexus,
            [
                "nexus",
                "research:meta-opt",
                "--manifest-file",
                str(manifest),
                "--presets-file",
                str(presets),
                "--report-file",
                str(report),
            ],
        )
    assert result.exit_code == 0, result.output
    return json.loads(report.read_text(encoding="utf-8"))


MEASURED_AGGREGATES = {"success_rate": 1.0, "regression_rate": 0.0, "infra_blocked_rate": 0.0}


def test_meta_opt_never_selects_a_simulated_child_report(tmp_path):
    result = _run_meta_opt(tmp_path, {"simulated": True, "aggregates": MEASURED_AGGREGATES})
    assert result["status"] == "no_eligible_preset"
    assert result["rankings"][0]["status"] == "simulated_report"


def test_meta_opt_still_selects_a_measured_child_report(tmp_path):
    result = _run_meta_opt(tmp_path, {"aggregates": MEASURED_AGGREGATES})
    assert result["status"] == "ok"
    assert result["selected_preset"]["preset_name"] == "p1"
