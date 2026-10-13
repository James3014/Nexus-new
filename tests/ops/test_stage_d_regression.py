import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _script(name: str, cwd: Path, *args: str, check: bool = False) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "ops" / name), *args],
        capture_output=True,
        text=True,
        cwd=str(cwd),
        env=dict(os.environ),
        check=check,
    )


def test_stage_d(tmp_path):
    # Hermetic: all baseline/lineage/report state lives under tmp_path (scripts use cwd-relative .nexus/).
    reports = tmp_path / ".nexus" / "reports"
    baseline_file = reports / "baseline" / "baseline_manifest.json"
    lineage_path = reports / "lineage_chain.jsonl"
    acc_report_path = reports / "acceptance_check.json"
    baseline_file.parent.mkdir(parents=True)

    baseline_file.write_text(
        json.dumps({
            "version": "1.0.0",
            "generated_by_sha": "test",
            "metrics": {"success_rate_threshold": 0.8},
        })
    )

    # 1. Regression case: rate 0.5 < 0.8
    acc_report_path.write_text(
        json.dumps({"status": "PASS", "metrics": {"auto_repair_success_rate": 50.0}})
    )
    _script(
        "append_lineage.py",
        tmp_path,
        "delivery_gate_receipt",
        json.dumps({"acceptance_report_path": str(acc_report_path), "head": "fail-sha"}),
        check=True,
    )
    res = _script("diagnose_regression.py", tmp_path)
    assert res.returncode == 2
    assert "regression detected" in res.stdout.lower()

    # 2. Success case: rate 0.9 >= 0.8 (fresh lineage)
    lineage_path.unlink()
    acc_report_path.write_text(
        json.dumps({"status": "PASS", "metrics": {"auto_repair_success_rate": 90.0}})
    )
    _script(
        "append_lineage.py",
        tmp_path,
        "delivery_gate_receipt",
        json.dumps({"acceptance_report_path": str(acc_report_path), "head": "pass-sha"}),
        check=True,
    )
    res = _script("diagnose_regression.py", tmp_path)
    assert res.returncode == 0
    assert "no regression detected" in res.stdout.lower()
