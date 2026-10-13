import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _run(script: str, cwd: Path, *args: str) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(filter(None, [str(REPO_ROOT), env.get("PYTHONPATH", "")]))
    return subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "ops" / script), *args],
        capture_output=True,
        text=True,
        cwd=str(cwd),
        env=env,
    )


def _baseline_check(cwd: Path) -> dict:
    res = _run("verify_report_claims.py", cwd, "--json", "--project-root", str(cwd))
    report = json.loads(res.stdout)
    return next(c for c in report["checks"] if c["name"] == "baseline_manifest")


def test_stage_a(tmp_path):
    # Hermetic: the baseline manifest lives in a throwaway project root, never in the real .nexus/.
    baseline_file = tmp_path / ".nexus" / "reports" / "baseline" / "baseline_manifest.json"
    baseline_file.parent.mkdir(parents=True)
    valid = json.dumps({"version": "1.0.0", "generated_by_sha": "test-sha", "metrics": {}})

    # 1. Invalid schema (missing fields)
    baseline_file.write_text(json.dumps({"old_field": "test"}))
    res = _run("diagnose_regression.py", tmp_path, ".nexus/reports/acceptance_check.json")
    assert res.returncode != 0
    assert "missing required fields" in (res.stdout + res.stderr).lower()
    check = _baseline_check(tmp_path)
    assert check["passed"] is False
    assert check["detail"]["error"] == "missing_schema_fields"

    # 2. Missing file
    baseline_file.unlink()
    res = _run("diagnose_regression.py", tmp_path, ".nexus/reports/acceptance_check.json")
    assert res.returncode != 0
    assert "missing baseline manifest" in res.stdout.lower()
    check = _baseline_check(tmp_path)
    assert check["passed"] is False
    assert check["detail"]["exists"] is False

    # 3. Success path
    baseline_file.write_text(valid)
    assert _baseline_check(tmp_path)["passed"] is True
