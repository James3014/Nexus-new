import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_delivery_gate_claim_verifier_requires_report_test_evidence():
    """H1: Static source contract check preserved."""
    script = (ROOT / "scripts/ops/nexus_delivery_gate.sh").read_text(encoding="utf-8")
    assert 'AGENT_REPORT_PATH=".nexus/reports/agent_report.json"' in script
    assert '--report-file "$AGENT_REPORT_PATH"' in script
    assert '--report-newer-than "$EVIDENCE_PATH"' in script
    assert "--require-test-evidence" in script
    assert "--require-nexus-command-evidence" in script
    assert "--require-worktree-delta" in script


def _build_delivery_fixture(tmp_path: Path) -> str:
    """Construct a self-contained, isolated test repository fixture for nexus_delivery_gate.sh."""
    subprocess.run(["git", "init", "-b", "main"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.name", "NexusTester"], cwd=tmp_path, check=True, capture_output=True
    )
    subprocess.run(
        ["git", "config", "user.email", "tester@nexus.local"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )

    readme = tmp_path / "README.md"
    readme.write_text("# Nexus Test Repo\n", encoding="utf-8")

    scripts_ops = tmp_path / "scripts" / "ops"
    scripts_ops.mkdir(parents=True, exist_ok=True)

    shutil.copy2(
        ROOT / "scripts" / "ops" / "nexus_delivery_gate.sh", scripts_ops / "nexus_delivery_gate.sh"
    )
    (scripts_ops / "nexus_delivery_gate.sh").chmod(0o755)
    shutil.copy2(
        ROOT / "scripts" / "ops" / "verify_report_claims.py",
        scripts_ops / "verify_report_claims.py",
    )
    (scripts_ops / "verify_report_claims.py").chmod(0o755)

    stub_script = "#!/usr/bin/env python3\nimport sys\nsys.exit(0)\n"
    for name in [
        "verify_governance_seal.py",
        "verify_lineage_chain.py",
        "evidence_verifier.py",
        "diagnose_regression.py",
    ]:
        p = scripts_ops / name
        p.write_text(stub_script, encoding="utf-8")
        p.chmod(0o755)

    test_dir = tmp_path / "tests" / "nexus" / "orchestrator"
    test_dir.mkdir(parents=True, exist_ok=True)
    (test_dir / "test_dummy.py").write_text("def test_ok(): pass\n", encoding="utf-8")

    reports_dir = tmp_path / ".nexus" / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    (reports_dir / "hallucination_evidence.json").write_text(
        json.dumps({"status": "PASS"}), encoding="utf-8"
    )

    baseline_dir = reports_dir / "baseline"
    baseline_dir.mkdir(parents=True, exist_ok=True)
    (baseline_dir / "baseline_manifest.json").write_text(
        json.dumps({"version": "fixture-v1", "generated_by_sha": "fixture-setup"}),
        encoding="utf-8",
    )

    config_dir = tmp_path / ".nexus" / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "delivery_gate_allow_dirty.json").write_text(
        json.dumps({"ignore_dirty_paths": []}), encoding="utf-8"
    )

    # Ensure step 5 orchestrator test passes deterministically by providing python with pytest.
    # Keep this shim tracked so it cannot accidentally become the worktree-delta failure source.
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    uv_stub = bin_dir / "uv"
    uv_stub.write_text(
        f'#!/bin/sh\nif [ "$1" = "run" ]; then\n  shift\nfi\nif [ "$1" = "python3" ] || [ "$1" = "python" ]; then\n  shift\nfi\nexec "{sys.executable}" "$@"\n',
        encoding="utf-8",
    )
    uv_stub.chmod(0o755)

    # Track all fixture support files, then create an empty HEAD commit. This leaves
    # the worktree clean and makes the commit-integrity expectation deterministic.
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "fixture setup"], cwd=tmp_path, check=True, capture_output=True
    )
    subprocess.run(
        ["git", "commit", "--allow-empty", "-m", "fixture head"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )

    return (
        subprocess
        .check_output(["git", "rev-parse", "--short", "HEAD"], cwd=tmp_path)
        .decode()
        .strip()
    )


def _valid_agent_report(head_sha: str) -> dict:
    return {
        "head_sha": head_sha,
        "files_changed_in_this_commit": [],
        "base_branch": "main",
        "branch_delta_vs_base": [],
        "tests_run": [
            {"command": "pytest -q", "exit_code": 0},
            {"command": "scripts/engine/nexus_cli.py nexus run", "exit_code": 0},
        ],
        "worktree_changed_files": [],
    }


def _run_delivery_gate(tmp_path: Path) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["PYTHONPATH"] = f"{ROOT}:{env.get('PYTHONPATH', '')}"
    env["UV_PYTHON"] = sys.executable
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PATH"] = f"{tmp_path / 'bin'}:{env.get('PATH', '')}"

    shell_bin = shutil.which("zsh") or shutil.which("bash") or "/bin/sh"
    return subprocess.run(
        [shell_bin, "scripts/ops/nexus_delivery_gate.sh"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
    )


def test_delivery_gate_physical_valid_report_passes_step_7(tmp_path):
    """Control: a valid report must clear Step 7 so negative cases cannot pass on fixture noise."""
    head_sha = _build_delivery_fixture(tmp_path)
    report_path = tmp_path / ".nexus" / "reports" / "agent_report.json"
    report_path.write_text(json.dumps(_valid_agent_report(head_sha)), encoding="utf-8")

    res = _run_delivery_gate(tmp_path)
    output = res.stderr + res.stdout
    assert res.returncode == 16
    assert "== Step 8: Acceptance (Quality Gate) ==" in output
    assert "Report integrity check failed" not in output


def test_delivery_gate_physical_test_evidence_decision_bearing(tmp_path):
    """H2-H5: A nonzero test witness alone must make real Step 7 fail with exit 17."""
    head_sha = _build_delivery_fixture(tmp_path)

    agent_report = _valid_agent_report(head_sha)
    agent_report["tests_run"][0]["exit_code"] = 1
    report_path = tmp_path / ".nexus" / "reports" / "agent_report.json"
    report_path.write_text(json.dumps(agent_report), encoding="utf-8")

    res = _run_delivery_gate(tmp_path)
    output = res.stderr + res.stdout
    assert res.returncode == 17
    assert '"error": "tests_with_nonzero_exit"' in output
    assert "Report integrity check failed" in output


def test_delivery_gate_physical_nexus_command_evidence_decision_bearing(tmp_path):
    """H6: Valid test evidence without a Nexus CLI command must fail real Step 7."""
    head_sha = _build_delivery_fixture(tmp_path)

    agent_report = _valid_agent_report(head_sha)
    agent_report["tests_run"] = [{"command": "pytest -q", "exit_code": 0}]
    report_path = tmp_path / ".nexus" / "reports" / "agent_report.json"
    report_path.write_text(json.dumps(agent_report), encoding="utf-8")

    res = _run_delivery_gate(tmp_path)
    output = res.stderr + res.stdout
    assert res.returncode == 17
    assert '"error": "missing_nexus_command_evidence"' in output
    assert "Report integrity check failed" in output


def test_delivery_gate_physical_worktree_delta_decision_bearing(tmp_path):
    """H7: One undeclared worktree path alone must fail real Step 7."""
    head_sha = _build_delivery_fixture(tmp_path)

    extra_file = tmp_path / "untracked.txt"
    extra_file.write_text("dirty\n", encoding="utf-8")

    agent_report = _valid_agent_report(head_sha)
    report_path = tmp_path / ".nexus" / "reports" / "agent_report.json"
    report_path.write_text(json.dumps(agent_report), encoding="utf-8")

    res = _run_delivery_gate(tmp_path)
    output = res.stderr + res.stdout
    assert res.returncode == 17
    assert '"error": "worktree_delta_mismatch"' in output
    assert "Report integrity check failed" in output


def test_delivery_gate_physical_freshness_decision_bearing(tmp_path):
    """H8: A stale report alone must fail real Step 7."""
    head_sha = _build_delivery_fixture(tmp_path)

    agent_report = _valid_agent_report(head_sha)
    report_path = tmp_path / ".nexus" / "reports" / "agent_report.json"
    report_path.write_text(json.dumps(agent_report), encoding="utf-8")

    evidence_path = tmp_path / ".nexus" / "reports" / "hallucination_evidence.json"
    old_time = time.time() - 3600
    os.utime(report_path, (old_time, old_time))
    os.utime(evidence_path, (time.time(), time.time()))

    res = _run_delivery_gate(tmp_path)
    output = res.stderr + res.stdout
    assert res.returncode == 17
    assert '"error": "report_older_than_reference"' in output
    assert "Report integrity check failed" in output
