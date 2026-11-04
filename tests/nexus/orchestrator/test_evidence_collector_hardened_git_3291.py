import json
import subprocess
from pathlib import Path
from unittest.mock import patch

from nexus.orchestrator.evidence_collector import EvidenceCollector
from nexus.orchestrator.task_contract import Evidence, Task

MOD = "nexus.orchestrator.evidence_collector"


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.com", *args],
        cwd=repo,
        check=True,
        capture_output=True,
    )


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "work"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    (repo / "a.txt").write_text("one\n")
    _git(repo, "add", "a.txt")
    _git(repo, "commit", "-q", "-m", "init")
    (repo / "a.txt").write_text("two\n")
    return repo


def _bundle(tmp_path: Path, repo: Path) -> dict:
    task = Task(
        task_id="T-3291",
        owner="A1",
        allowed_files=["a.txt"],
        done_criteria=[],
        evidence_requirements=["pytest"],
        working_dir=str(repo),
    )
    task.add_evidence(Evidence(command="pytest", exit_code=0, output_summary="ok"))
    out = tmp_path / "ev" / "evidence.json"
    collector = EvidenceCollector(reports_dir=str(tmp_path / "reports"), evidence_file=str(out))
    return json.loads(Path(collector.generate_hallucination_evidence(task, "Done")).read_text())


def test_normal_repo_diff_is_captured(tmp_path):
    data = _bundle(tmp_path, _repo(tmp_path))
    assert data["proof_type"] == "git_diff"
    assert "+two" in data["proof_value"]
    assert data["claim_state"] == "VERIFIED"


def test_repo_config_naming_a_program_gives_no_proof_and_runs_nothing(tmp_path):
    repo = _repo(tmp_path)
    marker = tmp_path / "marker"
    helper = tmp_path / "helper.sh"
    helper.write_text(f"#!/bin/sh\ntouch {marker}\ncat\n")
    helper.chmod(0o755)
    _git(repo, "config", "diff.evil.textconv", str(helper))
    _git(repo, "config", "diff.external", str(helper))
    (repo / ".gitattributes").write_text("*.txt diff=evil\n")
    data = _bundle(tmp_path, repo)
    assert not marker.exists()
    assert data["proof_type"] == "none"
    assert data["claim_state"] != "VERIFIED"


def test_git_timeout_gives_no_proof(tmp_path):
    repo = _repo(tmp_path)

    def boom(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd="git", timeout=1)

    with patch(f"{MOD}.run_hardened_git", side_effect=boom):
        data = _bundle(tmp_path, repo)
    assert data["proof_type"] == "none"
    assert data["claim_state"] != "VERIFIED"
