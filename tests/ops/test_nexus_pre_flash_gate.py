from __future__ import annotations

from pathlib import Path
import subprocess
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
    assert {
        "repair_factory_skipped_route",
        "runtime_receipt_reconcile",
        "hallucination_guard_drift",
        "brain_hub_audit",
        "event_contract_audit",
        "openseeker_autodata_smoke",
    }.issubset({item["name"] for item in payload["checks"]})


def test_quick_payload_includes_brain_hub_alignment_gate():
    payload = nexus_pre_flash_gate.build_payload(Path(".").resolve(), run_repair=False, output_dir="unused")

    names = {item["name"] for item in payload["checks"]}
    assert {
        "repair_factory_skipped_route",
        "runtime_receipt_reconcile",
        "hallucination_guard_drift",
        "brain_hub_audit",
        "event_contract_audit",
        "openseeker_autodata_smoke",
    }.issubset(names)


def test_quick_payload_fails_when_event_contract_audit_fails(monkeypatch):
    monkeypatch.setattr(
        nexus_pre_flash_gate,
        "validate_event_contracts",
        lambda _repo_root: [
            {
                "name": "event_contract_audit",
                "passed": False,
                "reason": "unknown_event_types_present",
                "details": {"unknown_event_types": ["legacy_blob"]},
            }
        ],
    )

    payload = nexus_pre_flash_gate.build_payload(Path(".").resolve(), run_repair=False, output_dir="unused")

    assert payload["passed"] is False
    assert any(item["name"] == "event_contract_audit" and not item["passed"] for item in payload["checks"])


def test_event_contract_gate_can_fail_on_raw_strict_mode(monkeypatch, tmp_path: Path):
    from nexus.events.transport import NexusEventBus

    monkeypatch.setenv("NEXUS_EVENT_RAW_STRICT", "1")
    NexusEventBus.configure(tmp_path)
    NexusEventBus.publish("phase_start", {"task_id": "task-1", "phase": "P"})

    checks = nexus_pre_flash_gate.validate_event_contracts(tmp_path)

    assert checks[0]["passed"] is False
    assert checks[0]["reason"] == "raw_event_types_present"
    assert checks[0]["details"]["strict_raw_mode"] is True


def test_quick_payload_fails_when_brain_hub_audit_fails(monkeypatch):
    class FailedHubAudit:
        passed = False
        documents = []
        failures = [{"reason": "brain_hub_drift"}]
        runtime_checklist = {"s_stage_runtime_contract": {"canonical_stage_flow": False}}

    monkeypatch.setattr(nexus_pre_flash_gate, "scan_brain_hub", lambda *_args, **_kwargs: FailedHubAudit())

    payload = nexus_pre_flash_gate.build_payload(Path(".").resolve(), run_repair=False, output_dir="unused")

    assert payload["passed"] is False
    assert any(item["name"] == "brain_hub_audit" and not item["passed"] for item in payload["checks"])


def test_quick_payload_includes_openseeker_autodata_smoke(tmp_path: Path):
    check = nexus_pre_flash_gate.validate_openseeker_autodata_smoke(tmp_path)[0]

    assert check["passed"] is True
    assert check["details"]["action_catalog_count"] >= 1
    assert check["details"]["autodata_manifest"]["training_eligible_count"] == 1


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
    assert out["classification"] == "failure"
    assert out["failure_category"] == "runner_failed"
    assert out["progress_observed"] is False
    assert out["stdout_tail"] == "out"
    assert out["stderr_tail"] == "err"


def test_run_repair_subset_reports_stderr_progress(monkeypatch, tmp_path: Path):
    stderr = (
        '{"event":"task_start","task_id":"a","elapsed_sec":0.1}\n'
        '{"event":"task_end","task_id":"a","elapsed_sec":1.2,"status":"SUCCESS"}\n'
    )

    def fake_run(*_args, **_kwargs):
        return SimpleNamespace(returncode=0, stdout="", stderr=stderr)

    monkeypatch.setattr(nexus_pre_flash_gate.subprocess, "run", fake_run)

    out = nexus_pre_flash_gate.run_repair_subset(tmp_path, ".nexus/reports/pref", timeout_sec=5)

    assert out["passed"] is True
    assert out["classification"] == "success"
    assert out["stdout_empty"] is True
    assert out["failure_category"] == ""
    assert out["progress_observed"] is True
    assert out["progress_event_count"] == 2
    assert out["progress_summary"]["task_start_count"] == 1
    assert out["progress_summary"]["task_end_count"] == 1
    assert out["progress_summary"]["active_task_ids"] == []
    assert out["last_progress_event"]["event"] == "task_end"


def test_run_repair_subset_classifies_timeout_no_progress(monkeypatch, tmp_path: Path):
    def fake_run(*_args, **_kwargs):
        raise subprocess.TimeoutExpired(cmd=["runner"], timeout=1, output="", stderr="")

    monkeypatch.setattr(nexus_pre_flash_gate.subprocess, "run", fake_run)

    out = nexus_pre_flash_gate.run_repair_subset(tmp_path, ".nexus/reports/pref", timeout_sec=1)

    assert out["passed"] is False
    assert out["timed_out"] is True
    assert out["classification"] == "hang"
    assert out["failure_category"] == "timeout_no_progress"
    assert out["progress_observed"] is False
    assert out["progress_event_count"] == 0


def test_run_repair_subset_classifies_timeout_after_task_start(monkeypatch, tmp_path: Path):
    def fake_run(*_args, **_kwargs):
        raise subprocess.TimeoutExpired(
            cmd=["runner"],
            timeout=1,
            output="",
            stderr='{"event":"task_start","task_id":"a","elapsed_sec":0.1}\n',
        )

    monkeypatch.setattr(nexus_pre_flash_gate.subprocess, "run", fake_run)

    out = nexus_pre_flash_gate.run_repair_subset(tmp_path, ".nexus/reports/pref", timeout_sec=1)

    assert out["passed"] is False
    assert out["timed_out"] is True
    assert out["classification"] == "timeout"
    assert out["failure_category"] == "timeout_after_task_start"
    assert out["progress_observed"] is True
    assert out["last_progress_event"]["task_id"] == "a"


def test_run_repair_subset_classifies_nonzero_after_progress(monkeypatch, tmp_path: Path):
    def fake_run(*_args, **_kwargs):
        return SimpleNamespace(
            returncode=9,
            stdout="",
            stderr='{"event":"task_start","task_id":"a","elapsed_sec":0.1}\n',
        )

    monkeypatch.setattr(nexus_pre_flash_gate.subprocess, "run", fake_run)

    out = nexus_pre_flash_gate.run_repair_subset(tmp_path, ".nexus/reports/pref", timeout_sec=5)

    assert out["passed"] is False
    assert out["classification"] == "progress"
    assert out["failure_category"] == "runner_failed_after_progress"
    assert out["progress_event_count"] == 1


def test_run_repair_subset_classifies_total_timeout_event(monkeypatch, tmp_path: Path):
    def fake_run(*_args, **_kwargs):
        return SimpleNamespace(
            returncode=0,
            stdout="",
            stderr='{"event":"total_timeout","task_id":"a","elapsed_sec":1.0,"status":"INTERRUPTED"}\n',
        )

    monkeypatch.setattr(nexus_pre_flash_gate.subprocess, "run", fake_run)

    out = nexus_pre_flash_gate.run_repair_subset(tmp_path, ".nexus/reports/pref", timeout_sec=5)

    assert out["passed"] is False
    assert out["classification"] == "timeout"
    assert out["failure_category"] == "timeout_after_progress"
    assert out["progress_summary"]["total_timeout_count"] == 1


def test_run_repair_subset_ignores_non_json_stderr_and_counts_bad_json(monkeypatch, tmp_path: Path):
    def fake_run(*_args, **_kwargs):
        return SimpleNamespace(
            returncode=2,
            stdout="",
            stderr='noise line\n{"event":"task_start","task_id":"a"}\n{bad-json}\n',
        )

    monkeypatch.setattr(nexus_pre_flash_gate.subprocess, "run", fake_run)

    out = nexus_pre_flash_gate.run_repair_subset(tmp_path, ".nexus/reports/pref", timeout_sec=5)

    assert out["classification"] == "progress"
    assert out["progress_observed"] is True
    assert out["progress_event_count"] == 1
    assert out["progress_parse_errors"] == 1
