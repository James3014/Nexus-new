import json

from scripts.ops import ultra_gate


def _valid_report(diff_path="/tmp/nexus-ultra/changes.diff", git_status_path="/tmp/nexus-ultra/git_status.txt"):
    return {
        "schema_version": "ultra-review.v1",
        "run_id": "ultra-review-test",
        "status": "DRY_RUN_PASS",
        "gate_passed": True,
        "mode": "dry-run",
        "project_root": "/tmp/project",
        "sandbox_path": "/tmp/nexus-ultra",
        "artifacts": {
            "diff": str(diff_path),
            "git_status": str(git_status_path),
        },
        "diff": {
            "changed_files": [],
            "has_worktree_delta": False,
        },
        "fleet": [
            {"lane": "security_sentry", "status": "DRY_RUN_READY"},
            {"lane": "logic_breaker", "status": "DRY_RUN_READY"},
            {"lane": "ghost_regression", "status": "SKIPPED"},
        ],
        "findings": [],
        "verification": {
            "verified_findings": 0,
            "unverified_observations": 0,
            "reproduction_required": True,
            "negative_test_execution": "not_applicable_dry_run",
        },
        "created_at": "2026-04-24T00:00:00+00:00",
        "report_path": "/tmp/report.json",
    }


def test_evaluate_report_passes_valid_dry_run_report():
    passed, failures = ultra_gate.evaluate_report(_valid_report())

    assert passed is True
    assert failures == []


def test_evaluate_report_blocks_high_verified_finding():
    payload = _valid_report()
    payload["findings"] = [
        {
            "id": "finding-1",
            "state": "VERIFIED_FINDING",
            "severity": "high",
        }
    ]

    passed, failures = ultra_gate.evaluate_report(payload)

    assert passed is False
    assert failures == ["blocking_verified_finding:finding-1"]


def test_evaluate_report_blocks_failed_ghost_regression():
    payload = _valid_report()
    payload["ghost_regression"] = {
        "passed": False,
        "executed_tests": ["tests/engine/test_sample.py"],
        "failed_tests": ["tests/engine/test_sample.py"],
    }

    passed, failures = ultra_gate.evaluate_report(payload)

    assert passed is False
    assert failures == ["ghost_regression_failed"]


def test_evaluate_report_fails_closed_for_schema_gaps():
    payload = _valid_report()
    del payload["sandbox_path"]
    payload["schema_version"] = "old"
    payload["verification"]["reproduction_required"] = False

    passed, failures = ultra_gate.evaluate_report(payload)

    assert passed is False
    assert "missing_field:sandbox_path" in failures
    assert "schema_version_mismatch" in failures
    assert "missing_sandbox_path" in failures
    assert "reproduction_not_required" in failures


def test_evaluate_report_fails_closed_for_missing_lane():
    payload = _valid_report()
    payload["fleet"] = [{"lane": "security_sentry", "status": "DRY_RUN_READY"}]

    passed, failures = ultra_gate.evaluate_report(payload)

    assert passed is False
    assert "missing_lane:logic_breaker" in failures
    assert "missing_lane:ghost_regression" in failures


def test_evaluate_report_checks_artifact_files_when_requested(tmp_path):
    diff_path = tmp_path / "changes.diff"
    git_status_path = tmp_path / "git_status.txt"
    diff_path.write_text("", encoding="utf-8")
    git_status_path.write_text("", encoding="utf-8")
    payload = _valid_report(diff_path=diff_path, git_status_path=git_status_path)

    passed, failures = ultra_gate.evaluate_report(payload, check_artifacts=True)

    assert passed is True
    assert failures == []

    diff_path.unlink()
    passed, failures = ultra_gate.evaluate_report(payload, check_artifacts=True)

    assert passed is False
    assert failures == ["missing_artifact_file:diff"]


def test_main_fails_closed_for_missing_report(tmp_path, capsys):
    missing = tmp_path / "missing.json"

    exit_code = ultra_gate.main(["--report", str(missing), "--json"])

    assert exit_code == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["passed"] is False
    assert payload["failures"]
