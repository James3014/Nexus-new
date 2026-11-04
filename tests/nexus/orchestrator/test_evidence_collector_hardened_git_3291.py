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


def _bundle_for(tmp_path: Path, repo: Path, base_branch: str) -> dict:
    task = Task(
        task_id="T-3291",
        owner="A1",
        allowed_files=["a.txt"],
        done_criteria=[],
        evidence_requirements=["pytest"],
        working_dir=str(repo),
        base_branch=base_branch,
    )
    task.add_evidence(Evidence(command="pytest", exit_code=0, output_summary="ok"))
    out = tmp_path / "ev" / "evidence.json"
    collector = EvidenceCollector(reports_dir=str(tmp_path / "reports"), evidence_file=str(out))
    return json.loads(Path(collector.generate_hallucination_evidence(task, "Done")).read_text())


def test_a_work_tree_whose_git_pointer_leaves_it_gives_no_proof(tmp_path):
    """A .git file naming a git dir outside the work tree (not a registered linked worktree)
    is not trusted, so no diff is taken there."""
    elsewhere = _repo(tmp_path)
    work = tmp_path / "pointer"
    work.mkdir()
    (work / "a.txt").write_text("two\n")
    (work / ".git").write_text(f"gitdir: {elsewhere / '.git'}\n")
    data = _bundle(tmp_path, work)
    assert data["proof_type"] == "none"
    assert data["claim_state"] != "VERIFIED"


def test_a_base_revision_shaped_like_an_option_gives_no_proof(tmp_path):
    repo = _repo(tmp_path)
    data = _bundle_for(tmp_path, repo, "--output=" + str(tmp_path / "written"))
    assert not (tmp_path / "written").exists()
    assert data["proof_type"] == "none"


def test_diff_stays_on_the_probed_git_dir_when_the_pointer_is_rewritten(tmp_path):
    """The diff stays pinned to the git dir that was probed: a .git pointer rewritten
    between the probe and the diff is refused, never followed to another repository."""
    main = tmp_path / "main"
    main.mkdir()
    _git(main, "init", "-q", "-b", "main")
    (main / "a.txt").write_text("one\n")
    _git(main, "add", "a.txt")
    _git(main, "commit", "-q", "-m", "init")
    work = tmp_path / "linked"
    _git(main, "worktree", "add", "-q", "-b", "wt", str(work))
    (work / "a.txt").write_text("two\n")
    other = tmp_path / "other"
    other.mkdir()
    _git(other, "init", "-q", "-b", "main")
    (other / "a.txt").write_text("other\n")
    _git(other, "add", "a.txt")
    _git(other, "commit", "-q", "-m", "init")

    from nexus.core.hardened_git import repository_config_can_start_a_program as real_probe

    def probe_then_rewrite(*args, **kwargs):
        result = real_probe(*args, **kwargs)
        (work / ".git").write_text(f"gitdir: {other / '.git'}\n")
        return result

    with patch(f"{MOD}.repository_config_can_start_a_program", side_effect=probe_then_rewrite):
        data = _bundle(tmp_path, work)
    assert data["proof_type"] == "none"
    assert "other" not in json.dumps(data)


def test_option_shaped_base_branch_writes_no_file_and_gives_no_proof_3361(tmp_path):
    repo = _repo(tmp_path)
    target = tmp_path / "written-by-git"
    task = Task(
        task_id="T-3361",
        owner="A1",
        allowed_files=["a.txt"],
        done_criteria=[],
        evidence_requirements=["pytest"],
        working_dir=str(repo),
    )
    task.base_branch = f"--output={target}"
    task.add_evidence(Evidence(command="pytest", exit_code=0, output_summary="ok"))
    out = tmp_path / "ev" / "evidence.json"
    collector = EvidenceCollector(reports_dir=str(tmp_path / "reports"), evidence_file=str(out))
    data = json.loads(Path(collector.generate_hallucination_evidence(task, "Done")).read_text())
    assert not target.exists()
    assert data["proof_type"] == "none"
    assert data["claim_state"] != "VERIFIED"
