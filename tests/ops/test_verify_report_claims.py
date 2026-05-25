from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from scripts.ops.verify_report_claims import _parse_porcelain_paths, verify_claims


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


def test_verify_claims_require_clean_can_ignore_generated_reports(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    _write_acceptance(tmp_path, status="PASS", gate_passed=True)
    report_md = tmp_path / ".nexus" / "reports" / "acceptance_check.md"
    report_md.write_text("generated\n", encoding="utf-8")

    subprocess.run(["git", "add", ".nexus/reports/acceptance_check.json"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "acceptance"], cwd=tmp_path, check=True, capture_output=True)

    report_md.write_text("regenerated\n", encoding="utf-8")

    report = verify_claims(
        tmp_path,
        require_clean=True,
        ignore_dirty_paths=[".nexus/reports/acceptance_check.md"],
        require_acceptance_pass=True,
    )
    assert report["passed"] is True
    working_tree = next(c for c in report["checks"] if c["name"] == "working_tree")
    assert working_tree["detail"]["effective_dirty_entries"] == 0


def test_parse_porcelain_paths_preserves_dot_prefixed_paths() -> None:
    raw = " M .nexus/reports/acceptance_check.json\nM  scripts/ops/nexus_delivery_gate.sh\n"
    assert _parse_porcelain_paths(raw) == [
        ".nexus/reports/acceptance_check.json",
        "scripts/ops/nexus_delivery_gate.sh",
    ]


def test_verify_claims_loads_ignore_dirty_paths_from_config(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    _write_acceptance(tmp_path, status="PASS", gate_passed=True)
    report_md = tmp_path / ".nexus" / "reports" / "acceptance_check.md"
    report_md.write_text("generated\n", encoding="utf-8")
    cfg = tmp_path / ".nexus" / "config" / "delivery_gate_allow_dirty.json"
    cfg.parent.mkdir(parents=True, exist_ok=True)
    cfg.write_text(json.dumps({"ignore_dirty_paths": [".nexus/reports/acceptance_check.md"]}), encoding="utf-8")

    subprocess.run(
        ["git", "add", ".nexus/reports/acceptance_check.json", ".nexus/config/delivery_gate_allow_dirty.json"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    subprocess.run(["git", "commit", "-m", "acceptance"], cwd=tmp_path, check=True, capture_output=True)

    report_md.write_text("regenerated\n", encoding="utf-8")
    report = verify_claims(
        tmp_path,
        require_clean=True,
        ignore_dirty_config=".nexus/config/delivery_gate_allow_dirty.json",
        require_acceptance_pass=True,
    )
    assert report["passed"] is True


def test_verify_claims_report_integrity_fails_when_tests_evidence_missing(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    head = subprocess.check_output(
        ["git", "rev-parse", "--short", "HEAD"], cwd=tmp_path, text=True
    ).strip()
    changed = [
        line.strip()
        for line in subprocess.check_output(
            ["git", "show", "--name-only", "--pretty=format:", "HEAD"], cwd=tmp_path, text=True
        ).splitlines()
        if line.strip()
    ]
    branch = subprocess.check_output(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=tmp_path, text=True
    ).strip()
    report_file = tmp_path / ".nexus" / "reports" / "agent_report.json"
    report_file.parent.mkdir(parents=True, exist_ok=True)
    report_file.write_text(
        json.dumps(
            {
                "head_sha": head,
                "files_changed_in_this_commit": changed,
                "base_branch": branch,
                "branch_delta_vs_base": [],
            }
        ),
        encoding="utf-8",
    )

    report = verify_claims(
        tmp_path,
        report_file_rel=".nexus/reports/agent_report.json",
        require_test_evidence=True,
    )
    integrity = next(c for c in report["checks"] if c["name"] == "report_integrity_lock")
    assert integrity["passed"] is False
    assert integrity["detail"]["test_evidence"]["error"] == "missing_tests_run"


def test_verify_claims_report_integrity_passes_with_valid_tests_evidence(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    head = subprocess.check_output(
        ["git", "rev-parse", "--short", "HEAD"], cwd=tmp_path, text=True
    ).strip()
    changed = [
        line.strip()
        for line in subprocess.check_output(
            ["git", "show", "--name-only", "--pretty=format:", "HEAD"], cwd=tmp_path, text=True
        ).splitlines()
        if line.strip()
    ]
    branch = subprocess.check_output(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=tmp_path, text=True
    ).strip()
    report_file = tmp_path / ".nexus" / "reports" / "agent_report.json"
    report_file.parent.mkdir(parents=True, exist_ok=True)
    report_file.write_text(
        json.dumps(
            {
                "head_sha": head,
                "files_changed_in_this_commit": changed,
                "base_branch": branch,
                "branch_delta_vs_base": [],
                "tests_run": [
                    {"command": "uv run pytest -q tests/test_cli_learn_mode.py", "exit_code": 0}
                ],
            }
        ),
        encoding="utf-8",
    )

    report = verify_claims(
        tmp_path,
        report_file_rel=".nexus/reports/agent_report.json",
        require_test_evidence=True,
    )
    assert report["passed"] is True


def test_verify_claims_report_integrity_fails_when_report_older_than_evidence(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    head = subprocess.check_output(
        ["git", "rev-parse", "--short", "HEAD"], cwd=tmp_path, text=True
    ).strip()
    changed = [
        line.strip()
        for line in subprocess.check_output(
            ["git", "show", "--name-only", "--pretty=format:", "HEAD"], cwd=tmp_path, text=True
        ).splitlines()
        if line.strip()
    ]
    branch = subprocess.check_output(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=tmp_path, text=True
    ).strip()
    report_file = tmp_path / ".nexus" / "reports" / "agent_report.json"
    report_file.parent.mkdir(parents=True, exist_ok=True)
    report_file.write_text(
        json.dumps(
            {
                "head_sha": head,
                "files_changed_in_this_commit": changed,
                "base_branch": branch,
                "branch_delta_vs_base": [],
                "tests_run": [{"command": "uv run pytest -q tests/test_cli_learn_mode.py", "exit_code": 0}],
            }
        ),
        encoding="utf-8",
    )
    evidence_file = tmp_path / ".nexus" / "reports" / "hallucination_evidence.json"
    evidence_file.parent.mkdir(parents=True, exist_ok=True)
    evidence_file.write_text('{"final_response":"x","evidence_bundle":{}}', encoding="utf-8")
    os.utime(report_file, (1000, 1000))
    os.utime(evidence_file, (2000, 2000))

    report = verify_claims(
        tmp_path,
        report_file_rel=".nexus/reports/agent_report.json",
        require_test_evidence=True,
        report_newer_than=".nexus/reports/hallucination_evidence.json",
    )
    integrity = next(c for c in report["checks"] if c["name"] == "report_integrity_lock")
    assert integrity["passed"] is False
    assert integrity["detail"]["freshness"]["error"] == "report_older_than_reference"


def test_verify_claims_report_integrity_fails_without_nexus_command_evidence(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    head = subprocess.check_output(
        ["git", "rev-parse", "--short", "HEAD"], cwd=tmp_path, text=True
    ).strip()
    changed = [
        line.strip()
        for line in subprocess.check_output(
            ["git", "show", "--name-only", "--pretty=format:", "HEAD"], cwd=tmp_path, text=True
        ).splitlines()
        if line.strip()
    ]
    branch = subprocess.check_output(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=tmp_path, text=True
    ).strip()
    report_file = tmp_path / ".nexus" / "reports" / "agent_report.json"
    report_file.parent.mkdir(parents=True, exist_ok=True)
    report_file.write_text(
        json.dumps(
            {
                "head_sha": head,
                "files_changed_in_this_commit": changed,
                "base_branch": branch,
                "branch_delta_vs_base": [],
                "worktree_changed_files": [],
                "tests_run": [{"command": "uv run pytest -q tests/test_cli_learn_mode.py", "exit_code": 0}],
            }
        ),
        encoding="utf-8",
    )

    report = verify_claims(
        tmp_path,
        report_file_rel=".nexus/reports/agent_report.json",
        require_test_evidence=True,
        require_nexus_command_evidence=True,
        require_worktree_delta=True,
    )
    integrity = next(c for c in report["checks"] if c["name"] == "report_integrity_lock")
    assert integrity["passed"] is False
    assert integrity["detail"]["nexus_command_evidence"]["error"] == "missing_nexus_command_evidence"


def test_verify_claims_report_integrity_passes_with_nexus_and_worktree_evidence(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    head = subprocess.check_output(
        ["git", "rev-parse", "--short", "HEAD"], cwd=tmp_path, text=True
    ).strip()
    changed = [
        line.strip()
        for line in subprocess.check_output(
            ["git", "show", "--name-only", "--pretty=format:", "HEAD"], cwd=tmp_path, text=True
        ).splitlines()
        if line.strip()
    ]
    branch = subprocess.check_output(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=tmp_path, text=True
    ).strip()
    # Create one untracked file to assert worktree delta parity (including untracked).
    untracked = tmp_path / "scratch.txt"
    untracked.write_text("x\n", encoding="utf-8")

    report_file = tmp_path / ".nexus" / "reports" / "agent_report.json"
    report_file.parent.mkdir(parents=True, exist_ok=True)
    base_payload = {
        "head_sha": head,
        "files_changed_in_this_commit": changed,
        "base_branch": branch,
        "branch_delta_vs_base": [],
        "worktree_changed_files": [],
        "tests_run": [
            {"command": "uv run scripts/engine/nexus_cli.py nexus research:run --dry-run", "exit_code": 0},
            {"command": "uv run pytest -q tests/test_cli_learn_mode.py", "exit_code": 0},
        ],
    }
    report_file.write_text(json.dumps(base_payload), encoding="utf-8")
    # Capture current worktree after report exists and persist exact value.
    raw_status = subprocess.check_output(["git", "status", "--porcelain"], cwd=tmp_path, text=True)
    base_payload["worktree_changed_files"] = sorted(_parse_porcelain_paths(raw_status))
    report_file.write_text(
        json.dumps(
            base_payload
        ),
        encoding="utf-8",
    )

    report = verify_claims(
        tmp_path,
        report_file_rel=".nexus/reports/agent_report.json",
        require_test_evidence=True,
        require_nexus_command_evidence=True,
        require_worktree_delta=True,
    )
    assert report["passed"] is True


def test_verify_claims_git_timeout_handling(tmp_path: Path) -> None:
    from unittest.mock import patch
    _init_git_repo(tmp_path)
    _write_acceptance(tmp_path, status="PASS", gate_passed=True)

    # 模擬 git rev-parse HEAD 時發生 TimeoutExpired 超時
    with patch("subprocess.check_output", side_effect=subprocess.TimeoutExpired(cmd=["git", "rev-parse", "HEAD"], timeout=15.0)):
        report = verify_claims(
            tmp_path,
            required_paths=[],
            require_clean=True, # 需要執行 git status
            require_acceptance_pass=True,
        )
        # 由於超時，git 執行失敗，安全閘門應當返回 Fail (passed=False) 而非卡死
        assert report["passed"] is False

