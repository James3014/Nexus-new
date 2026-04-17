from __future__ import annotations

import json
import subprocess
from pathlib import Path

from scripts.ops.verify_report_claims import verify_claims


def _init_git_repo(path: Path) -> None:
    subprocess.run(["git", "init"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=path, check=True, capture_output=True)
    (path / "README.md").write_text("seed\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=path, check=True, capture_output=True)


def _write_acceptance(path: Path, status: str, gate_passed: bool) -> None:
    report = path / ".nexus" / "reports" / "acceptance_check.json"
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps({"status": status, "gate_passed": gate_passed}), encoding="utf-8")


def test_verify_claims_pass_with_required_paths_and_acceptance(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    _write_acceptance(tmp_path, status="PASS", gate_passed=True)
    req = tmp_path / "docs" / "proof.md"
    req.parent.mkdir(parents=True, exist_ok=True)
    req.write_text("ok\n", encoding="utf-8")

    report = verify_claims(
        tmp_path,
        required_paths=["docs/proof.md"],
        require_clean=False,
        require_acceptance_pass=True,
    )
    assert report["passed"] is True


def test_verify_claims_fail_when_required_path_missing(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    _write_acceptance(tmp_path, status="PASS", gate_passed=True)

    report = verify_claims(
        tmp_path,
        required_paths=["docs/missing.md"],
        require_clean=False,
        require_acceptance_pass=False,
    )
    assert report["passed"] is False
    missing_check = next(c for c in report["checks"] if c["name"] == "required_paths")
    assert missing_check["passed"] is False


def test_verify_claims_fail_when_acceptance_not_pass(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    _write_acceptance(tmp_path, status="FAIL", gate_passed=False)

    report = verify_claims(
        tmp_path,
        required_paths=[],
        require_clean=False,
        require_acceptance_pass=True,
    )
    assert report["passed"] is False
    acceptance_check = next(c for c in report["checks"] if c["name"] == "acceptance_report")
    assert acceptance_check["passed"] is False
