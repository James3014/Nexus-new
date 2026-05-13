from __future__ import annotations

from pathlib import Path
import subprocess
from types import SimpleNamespace

from scripts.ops import nexus_pre_flash_gate
from nexus.engine.local_reflex import ReflexAssessment


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
        "codex_nexus_smoke_plan",
        "brain_hub_coverage_gate",
        "openseeker_autodata_smoke",
        "benchmark_autodata_manifest_gate",
        "pipeline_composition_gate",
        "route_cost_policy_audit",
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
        "codex_nexus_smoke_plan",
        "brain_hub_coverage_gate",
        "openseeker_autodata_smoke",
        "benchmark_autodata_manifest_gate",
        "pipeline_composition_gate",
        "route_cost_policy_audit",
    }.issubset(names)


def test_quick_payload_fails_when_event_contract_audit_fails(monkeypatch):
    monkeypatch.setattr(
        nexus_pre_flash_gate,
        "validate_event_contracts",
        lambda _repo_root, **_kwargs: [
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


def test_event_contract_gate_warns_on_raw_default_mode(tmp_path: Path):
    from nexus.events.transport import NexusEventBus

    NexusEventBus.configure(tmp_path)
    NexusEventBus.publish("phase_start", {"task_id": "task-1", "phase": "P"})

    checks = nexus_pre_flash_gate.validate_event_contracts(tmp_path)

    assert checks[0]["passed"] is True
    assert checks[0]["details"]["raw_policy"] == "warn"
    assert checks[0]["details"]["warning_reasons"] == ["raw_event_types_present"]


def test_event_contract_gate_accepts_explicit_strict_raw_argument(tmp_path: Path):
    from nexus.events.transport import NexusEventBus

    NexusEventBus.configure(tmp_path)
    NexusEventBus.publish("phase_start", {"task_id": "task-1", "phase": "P"})

    checks = nexus_pre_flash_gate.validate_event_contracts(tmp_path, strict_raw=True)

    assert checks[0]["passed"] is False
    assert checks[0]["reason"] == "raw_event_types_present"
    assert checks[0]["details"]["strict_raw_mode"] is True


def test_quick_payload_includes_codex_nexus_smoke_plan():
    checks = nexus_pre_flash_gate.validate_codex_nexus_smoke_plan()

    assert checks[0]["name"] == "codex_nexus_smoke_plan"
    assert checks[0]["passed"] is True
    assert checks[0]["details"]["same_model"] is True
    assert checks[0]["details"]["preflight_only"] is True


def test_quick_payload_includes_brain_hub_coverage_gate():
    checks = nexus_pre_flash_gate.validate_brain_hub_coverage_gate(Path(".").resolve())

    assert checks[0]["name"] == "brain_hub_coverage_gate"
    assert checks[0]["passed"] is True
    assert checks[0]["details"]["status_counts"]["implemented"] >= 1


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
    assert check["details"]["autodata_manifest"]["written"] is False
    assert not (tmp_path / ".nexus" / "reports" / "pre_flash_autodata_manifest.json").exists()


def test_benchmark_autodata_manifest_gate_accepts_real_flash_and_pro_manifests():
    check = nexus_pre_flash_gate.validate_benchmark_autodata_manifest_gate(Path(".").resolve())[0]

    assert check["passed"] is True
    assert check["name"] == "benchmark_autodata_manifest_gate"
    assert len(check["details"]["manifests"]) == 2
    assert all(item["training_eligible_count"] >= 3 for item in check["details"]["manifests"])
    assert all(item["hard_negative_count"] >= 3 for item in check["details"]["manifests"])


def test_benchmark_autodata_manifest_gate_fails_without_manifest(tmp_path: Path):
    check = nexus_pre_flash_gate.validate_benchmark_autodata_manifest_gate(tmp_path)[0]

    assert check["passed"] is False
    assert check["reason"] == "benchmark_autodata_manifest_gate_failed"
    assert {item["reason"] for item in check["details"]["failures"]} == {"autodata_manifest_missing"}


def test_benchmark_autodata_manifest_gate_fails_without_hard_negatives(tmp_path: Path):
    manifest = tmp_path / ".nexus" / "reports" / "autodata" / "flash_8x1_autodata_manifest.json"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(
        """{
  "schema_version": "nexus_autodata_forge_manifest.v1",
  "rows": [
    {"task_id": "a", "label": {"label": "GOLD"}, "eligible_for_training": true, "hard_negative": false, "evidence_refs": ["EV-1"], "low_step_filter": {"filtered": false}},
    {"task_id": "b", "label": {"label": "GOLD"}, "eligible_for_training": true, "hard_negative": false, "evidence_refs": ["EV-2"], "low_step_filter": {"filtered": false}},
    {"task_id": "c", "label": {"label": "GOLD"}, "eligible_for_training": true, "hard_negative": false, "evidence_refs": ["EV-3"], "low_step_filter": {"filtered": false}}
  ]
}""",
        encoding="utf-8",
    )

    check = nexus_pre_flash_gate.validate_benchmark_autodata_manifest_gate(
        tmp_path,
        manifest_paths=(manifest,),
    )[0]

    assert check["passed"] is False
    assert check["details"]["failures"][0]["reason"] == "insufficient_hard_negative_rows"


def test_quick_payload_includes_pipeline_composition_gate():
    check = nexus_pre_flash_gate.validate_pipeline_composition_gate(Path(".").resolve())[0]

    assert check["passed"] is True
    assert check["name"] == "pipeline_composition_gate"
    assert check["details"]["phase_ownership_status"] == "executor_owned_with_legacy_mixins_retained"
    assert check["details"]["runtime_missing_phases"] == []
    assert check["details"]["fallback_debt_phases"] == []


def test_quick_payload_includes_route_cost_policy_audit():
    check = nexus_pre_flash_gate.validate_route_cost_policy_audit(Path(".").resolve())[0]

    assert check["passed"] is True
    assert check["name"] == "route_cost_policy_audit"
    assert check["details"]["task_id_runtime_policy_count"] == 0


def test_quick_payload_includes_mutation_assurance_gate():
    check = nexus_pre_flash_gate.validate_mutation_assurance_gate()[0]

    assert check["passed"] is True
    assert check["name"] == "mutation_assurance_gate"
    assert check["details"]["gate"]["required"] is True
    assert check["details"]["gate"]["killed_count"] == 1


def test_quick_payload_includes_capability_wiring_and_scheduled_heavy_audit_gates():
    payload = nexus_pre_flash_gate.build_payload(Path(".").resolve(), run_repair=False, output_dir=".nexus/reports/test")
    checks = {item["name"]: item for item in payload["checks"]}

    wiring = checks["capability_wiring_audit"]
    scheduled = checks["ralph_scheduled_heavy_audit"]
    assert wiring["passed"] is True
    assert wiring["details"]["pending_executor_without_spec"] == []
    assert scheduled["passed"] is True
    assert scheduled["details"]["foreground_policy"] == "summary_receipt_only"
    assert scheduled["details"]["all_non_blocking"] is True
    assert {item["capability"] for item in scheduled["details"]["tasks"]} == {
        "mutation_assurance",
        "autodata_forge",
        "nightshift",
    }


def test_quick_payload_includes_harness_engineering_gate():
    payload = nexus_pre_flash_gate.build_payload(Path(".").resolve(), run_repair=False, output_dir=".nexus/reports/test")
    checks = {item["name"]: item for item in payload["checks"]}

    harness = checks["harness_engineering_gate"]
    assert harness["passed"] is True
    assert harness["details"]["preflight"]["bdd_acceptance_required"] is True
    assert harness["details"]["semantic_failure_sensor"]["retry_policy"]["allow_blind_retry"] is False
    assert harness["details"]["bdd_acceptance"]["business_verified"] is True


def test_quick_payload_fails_when_mutation_assurance_gate_fails(monkeypatch):
    monkeypatch.setattr(
        nexus_pre_flash_gate,
        "validate_mutation_assurance_gate",
        lambda: [
            {
                "name": "mutation_assurance_gate",
                "passed": False,
                "reason": "mutation_assurance_failed",
                "details": {"gate": {"failures": ["survived_mutants_present"]}},
            }
        ],
    )

    payload = nexus_pre_flash_gate.build_payload(Path(".").resolve(), run_repair=False, output_dir="unused")

    assert payload["passed"] is False
    assert any(item["name"] == "mutation_assurance_gate" and not item["passed"] for item in payload["checks"])


def test_route_cost_policy_audit_ignores_legacy_task_controls(tmp_path: Path):
    policy = tmp_path / ".nexus" / "policy" / "promoted_route_cost_policy.json"
    policy.parent.mkdir(parents=True, exist_ok=True)
    policy.write_text(
        """{
  "schema_version": "nexus_promoted_route_cost_policy.v1",
  "source": ".nexus/reports/cost",
  "candidate_cap_overrides": {"task-a": 1},
  "lite_route_tasks": ["task-b"],
  "hold_tasks": ["task-c"]
}""",
        encoding="utf-8",
    )

    check = nexus_pre_flash_gate.validate_route_cost_policy_audit(tmp_path)[0]

    assert check["passed"] is True
    assert check["details"]["legacy_task_controls_ignored_count"] == 3
    assert check["details"]["task_id_runtime_policy_count"] == 0


def test_local_reflex_shadow_requires_destructive_probe_high_risk(monkeypatch):
    def fake_assess(*, task_desc: str, provider: str | None = None, **_kwargs):
        if provider == "bonsai":
            return ReflexAssessment(
                "nexus_local_reflex.v1",
                "heuristic_fallback",
                False,
                "low",
                "high",
                False,
                False,
                False,
                0.82,
                0,
                ("bonsai_unavailable",),
            )
        if "rm -rf" in task_desc:
            return ReflexAssessment(
                "nexus_local_reflex.v1",
                "ollama",
                True,
                "low",
                "high",
                False,
                False,
                False,
                0.7,
                10,
                ("bad_local_false_negative",),
            )
        if "Refactor core" in task_desc:
            return ReflexAssessment(
                "nexus_local_reflex.v1",
                "ollama",
                True,
                "high",
                "low",
                False,
                True,
                True,
                0.82,
                10,
                (),
            )
        return ReflexAssessment(
            "nexus_local_reflex.v1",
            "ollama",
            True,
            "low",
            "high",
            False,
            False,
            False,
            0.82,
            10,
            (),
        )

    monkeypatch.setattr(nexus_pre_flash_gate, "assess_local_reflex", fake_assess)

    check = nexus_pre_flash_gate.validate_local_reflex_shadow()[0]

    assert check["passed"] is False
    assert check["reason"] == "local_reflex_contract_mismatch"
    assert check["details"]["destructive"]["risk_level"] == "low"


def test_pipeline_composition_gate_fails_when_inventory_fails(monkeypatch):
    monkeypatch.setattr(
        nexus_pre_flash_gate,
        "build_inventory",
        lambda _repo_root: {
            "passed": False,
            "composition_status": "partial",
            "phase_ownership_status": "incomplete",
            "runtime_missing_phases": ["C"],
            "fallback_debt_phases": ["C"],
            "fallback_debt_count": 1,
            "failures": [{"reason": "runtime_owned_phase_missing", "phase": "C"}],
        },
    )

    check = nexus_pre_flash_gate.validate_pipeline_composition_gate(Path(".").resolve())[0]

    assert check["passed"] is False
    assert check["reason"] == "pipeline_composition_inventory_failed"
    assert check["details"]["runtime_missing_phases"] == ["C"]


def test_pipeline_composition_gate_fails_when_fallback_debt_remains(monkeypatch):
    monkeypatch.setattr(
        nexus_pre_flash_gate,
        "build_inventory",
        lambda _repo_root: {
            "passed": True,
            "composition_status": "partial",
            "phase_ownership_status": "executor_owned_with_legacy_mixins_retained",
            "runtime_missing_phases": [],
            "fallback_debt_phases": ["C"],
            "fallback_debt_count": 1,
            "failures": [],
        },
    )

    check = nexus_pre_flash_gate.validate_pipeline_composition_gate(Path(".").resolve())[0]

    assert check["passed"] is False
    assert check["reason"] == "pipeline_composition_fallback_debt_present"
    assert check["details"]["fallback_debt_phases"] == ["C"]


def test_openseeker_autodata_smoke_writes_manifest_only_when_explicit(tmp_path: Path):
    check = nexus_pre_flash_gate.validate_openseeker_autodata_smoke(tmp_path, write_manifest=True)[0]
    manifest = tmp_path / ".nexus" / "reports" / "pre_flash_autodata_manifest.json"

    assert check["passed"] is True
    assert check["details"]["autodata_manifest"]["written"] is True
    assert manifest.exists()


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
