from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from scripts.ops import nexus_pre_flash_gate


def test_repair_factory_skipped_route_blocks_ranking_layers():
    checks = nexus_pre_flash_gate.validate_repair_factory_skipped_routes(Path(".").resolve())

    assert checks
    assert all(item["passed"] for item in checks)
    for item in checks:
        details = item["details"]
        assert details["readiness"]["status"] == "SKIPPED"
        assert "autoreason" not in details["selected_stack"]
        assert "autoreason" not in details["selected_plan"]
        assert "judge_panel" not in details["selected_plan"]


def test_runtime_receipt_reconcile_prunes_skipped_and_restores_success():
    checks = nexus_pre_flash_gate.validate_runtime_receipt_reconcile()

    assert checks == [
        {
            "name": "runtime_receipt_reconcile",
            "passed": True,
            "details": {
                "pruned": ["hyper"],
                "restored": ["autoreason", "hyper"],
            },
        }
    ]


def test_quick_payload_skips_flash_style_repair_subset():
    payload = nexus_pre_flash_gate.build_payload(Path(".").resolve(), run_repair=False, output_dir="unused")

    assert payload["passed"] is True
    assert {item["name"] for item in payload["checks"]} == {
        "repair_factory_skipped_route",
        "runtime_receipt_reconcile",
    }


def test_repair_subset_command_uses_flash_style_nexus_only_path():
    cmd = nexus_pre_flash_gate.repair_subset_command(".nexus/reports/pref")

    assert cmd[:4] == ["uv", "run", "python", "scripts/bench/capability_ab_runner.py"]
    assert "--nexus-only" in cmd
    assert cmd[cmd.index("--with-llm-mode") + 1] == "all"
    assert cmd[cmd.index("--task-id-filter") + 1] == "nexus-value-repair-001,nexus-value-repair-002"
    assert cmd[cmd.index("--output-dir") + 1] == ".nexus/reports/pref"


def test_run_repair_subset_reports_failure(monkeypatch, tmp_path: Path):
    def fake_run(*_args, **_kwargs):
        return SimpleNamespace(returncode=2, stdout="out", stderr="err")

    monkeypatch.setattr(nexus_pre_flash_gate.subprocess, "run", fake_run)

    out = nexus_pre_flash_gate.run_repair_subset(tmp_path, ".nexus/reports/pref")

    assert out["name"] == "flash_style_repair_subset"
    assert out["passed"] is False
    assert out["returncode"] == 2
    assert out["stdout_tail"] == "out"
    assert out["stderr_tail"] == "err"
