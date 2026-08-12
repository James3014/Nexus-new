from __future__ import annotations

import json
import sys
from pathlib import Path

from nexus.services.audit_service import AuditService


def test_audit_service_forwards_exact_root_and_window_without_mutating_argv(tmp_path, monkeypatch):
    from scripts.ops import nexus_acceptance_check

    calls: list[dict[str, object]] = []
    original_argv = list(sys.argv)

    def _fake_run_acceptance(**kwargs):
        calls.append(kwargs)
        return 7

    monkeypatch.setattr(nexus_acceptance_check, "run_acceptance", _fake_run_acceptance)

    result = AuditService(tmp_path).run_acceptance(window=17)

    assert result == 7
    assert calls == [{"project_root": tmp_path, "window": 17}]
    assert sys.argv == original_argv


def test_acceptance_cli_delegates_once_to_programmatic_callable(monkeypatch, tmp_path):
    from scripts.ops import nexus_acceptance_check

    calls: list[dict[str, object]] = []

    def _fake_run_acceptance(**kwargs):
        calls.append(kwargs)
        return 3

    monkeypatch.setattr(nexus_acceptance_check, "run_acceptance", _fake_run_acceptance)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "nexus_acceptance_check.py",
            "--project-root",
            str(tmp_path),
            "--window",
            "23",
        ],
    )

    result = nexus_acceptance_check.main.__wrapped__()

    assert result == 3
    assert len(calls) == 1
    assert calls == [
        {
            "project_root": Path(tmp_path),
            "output_dir": ".nexus/reports",
            "window": 23,
            "repair_success_min": 80.0,
            "phantom_fp_max": 3.0,
            "regression_pass_min": 95.0,
            "retry_spike_factor": 2.0,
            "retry_abs_max": 1.0,
            "pr_min": 30.0,
            "nrh_min": 20.0,
            "learning_gate_mode": "soft_signal",
            "include_sources": ("pipeline.crystallize,pipeline.repair,pipeline.repair_audit"),
            "exclude_sources": "calibration.sim",
            "exclude_tasks": "",
            "cold_start_min_samples": 10,
            "required_claim_paths": "",
            "report_file": ".nexus/reports/agent_report.json",
            "require_test_evidence": True,
            "report_newer_than": None,
        }
    ]


def test_programmatic_acceptance_preserves_pass_and_fail_exit_semantics(tmp_path, monkeypatch):
    from scripts.ops import nexus_acceptance_check

    passing = nexus_acceptance_check.CriterionResult("criterion", True, {})

    monkeypatch.setattr(
        nexus_acceptance_check,
        "_evaluate_repair_success",
        lambda *_args, **_kwargs: passing,
    )
    monkeypatch.setattr(
        nexus_acceptance_check,
        "_evaluate_phantom_false_positive",
        lambda *_args, **_kwargs: passing,
    )
    monkeypatch.setattr(
        nexus_acceptance_check,
        "_evaluate_regression_and_side_effects",
        lambda *_args, **_kwargs: (passing, {}),
    )
    monkeypatch.setattr(
        nexus_acceptance_check,
        "_evaluate_learning_promotion",
        lambda *_args, **_kwargs: passing,
    )
    monkeypatch.setattr(
        nexus_acceptance_check,
        "_evaluate_ucc_truth_efficiency",
        lambda *_args, **_kwargs: passing,
    )
    monkeypatch.setattr(
        nexus_acceptance_check,
        "_summarize_wiki_harness",
        lambda *_args, **_kwargs: {
            key: 0 for key in nexus_acceptance_check.REQUIRED_WIKI_HARNESS_KEYS
        },
    )
    monkeypatch.setattr(
        nexus_acceptance_check,
        "_evaluate_wiki_harness_contract",
        lambda *_args, **_kwargs: passing,
    )
    monkeypatch.setattr(
        nexus_acceptance_check,
        "_evaluate_lesson_writeback",
        lambda *_args, **_kwargs: passing,
    )
    monkeypatch.setattr(
        nexus_acceptance_check,
        "_evaluate_report_claim_integrity",
        lambda *_args, **_kwargs: passing,
    )

    assert (
        nexus_acceptance_check.run_acceptance(
            project_root=tmp_path,
            require_test_evidence=False,
        )
        == 0
    )
    report_path = tmp_path / ".nexus" / "reports" / "acceptance_check.json"
    assert json.loads(report_path.read_text(encoding="utf-8"))["status"] == "PASS"

    failing = nexus_acceptance_check.CriterionResult("criterion", False, {"status": "FAIL"})
    monkeypatch.setattr(
        nexus_acceptance_check,
        "_evaluate_repair_success",
        lambda *_args, **_kwargs: failing,
    )

    assert (
        nexus_acceptance_check.run_acceptance(
            project_root=tmp_path,
            require_test_evidence=False,
        )
        == 1
    )
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["gate_passed"] is False
    assert report["status"] == "UNVERIFIED_COLD_START"


def test_cli_facade_forwards_acceptance_exactly_once(tmp_path):
    from nexus.services.cli_commands_service import CliCommandsService

    calls: list[int] = []

    class _FakeAudit:
        def run_acceptance(self, window):
            calls.append(window)
            return 11

    facade = object.__new__(CliCommandsService)
    facade._audit = _FakeAudit()

    assert facade.acceptance_check(window=29) == 11
    assert calls == [29]


def test_audit_service_dispatch_uses_physical_acceptance_owner():
    import inspect

    source = inspect.getsource(AuditService.run_acceptance)

    assert "scripts.ops.nexus_acceptance_check" in source
    assert "nexus.core.ops" not in source


def test_orphan_release_facades_are_not_exposed():
    from nexus.services.cli_commands_service import CliCommandsService

    assert not hasattr(AuditService, "run_release")
    assert not hasattr(CliCommandsService, "release")
