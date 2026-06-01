import json

from nexus.services.local_heal.manifest_report import summarize_manifest_results


def test_summarize_manifest_results_groups_failure_reasons(tmp_path):
    result_path = tmp_path / "results.jsonl"
    rows = [
        {
            "instance_id": "astropy__astropy-12907",
            "manifest_task_id": "astropy-swe-verified-0",
            "solve_eligible": False,
            "failure_reason": "ASTROPY_VERSION_PARITY_MISSING",
            "receipt_path": "/reports/a/receipt.json",
        },
        {
            "instance_id": "astropy__astropy-13033",
            "manifest_task_id": "astropy-swe-verified-1",
            "solve_eligible": False,
            "failure_reason": "ASTROPY_DEPENDENCY_MISSING",
            "receipt_path": "/reports/a2/receipt.json",
        },
        {
            "instance_id": "local_fix_deepswe_task4_singleton_race.py",
            "manifest_task_id": "deepswe-task4",
            "solve_eligible": False,
            "failure_reason": "REPRO_NOT_REPRODUCED",
            "receipt_path": "/reports/b/receipt.json",
        },
        {
            "instance_id": "synthetic-success",
            "manifest_task_id": "synthetic-success",
            "solve_eligible": True,
            "failure_reason": "",
            "receipt_path": "/reports/c/receipt.json",
        },
    ]
    result_path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")

    summary = summarize_manifest_results(result_path)

    assert summary["total"] == 4
    assert summary["solved"] == 1
    assert summary["completion_gate"] == "NOT_MET"
    assert summary["by_bucket"] == {
        "env_blocked": 2,
        "no_repro": 1,
        "solved": 1,
    }
    assert summary["by_failure_reason"]["ASTROPY_VERSION_PARITY_MISSING"] == 1
    assert summary["by_failure_reason"]["ASTROPY_DEPENDENCY_MISSING"] == 1
    assert summary["receipts"][0] == "/reports/a/receipt.json"


def test_summarize_manifest_results_groups_preflight_rows(tmp_path):
    result_path = tmp_path / "preflight.jsonl"
    rows = [
        {
            "manifest_task_id": "astropy-swe-verified-0",
            "preflight_ready": False,
            "failure_reason": "ASTROPY_VERSION_PARITY_MISSING",
        },
        {
            "manifest_task_id": "deepswe-task4",
            "preflight_ready": True,
            "failure_reason": "",
        },
    ]
    result_path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")

    summary = summarize_manifest_results(result_path)

    assert summary["by_bucket"] == {
        "env_blocked": 1,
        "preflight_ready": 1,
    }
    assert summary["by_failure_reason"]["PREFLIGHT_READY"] == 1
    assert summary["preflight_ready"] == 1
    assert summary["preflight_gate"] == "NOT_MET"
