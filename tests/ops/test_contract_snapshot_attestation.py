import json
import subprocess
import sys
from pathlib import Path

from scripts.ops import closeout_guard

REPO_ROOT = Path(__file__).resolve().parents[2]
CLI = REPO_ROOT / "scripts" / "engine" / "nexus_cli.py"


def _snapshot(tmp_path: Path, *args: str) -> dict:
    out = tmp_path / "snapshot.json"
    res = subprocess.run(
        [sys.executable, str(CLI), "nexus", "contract-snapshot", "--output", str(out), *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert res.returncode == 0, res.stderr
    return json.loads(out.read_text(encoding="utf-8"))


def _git(repo: Path, *args: str) -> str:
    res = subprocess.run(
        ["git", "-c", "user.email=t@example.com", "-c", "user.name=t", *args],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    )
    return res.stdout


def _check(snapshot: dict, tmp_path: Path) -> dict:
    # Pad changed_files so only the attestation/result checks decide the outcome.
    snapshot = {**snapshot, "changed_files": snapshot.get("changed_files") or ["x.py"]}
    path = tmp_path / "contract.json"
    path.write_text(json.dumps(snapshot), encoding="utf-8")
    return closeout_guard.validate_contract(path, require_head_match=False)


def test_default_snapshot_does_not_claim_tests_passed(tmp_path):
    snap = _snapshot(tmp_path)
    assert snap["required_tests_passed"] is None
    assert snap["linter_exit_code"] is None
    assert snap["ci_gate_exit_code"] is None
    assert {v["source"] for v in snap["attestation"].values()} == {"not_run"}


def test_contract_check_rejects_default_snapshot(tmp_path):
    snap = _snapshot(tmp_path)
    result = _check(snap, tmp_path)
    assert result["ok"] is False
    assert result["checks"]["attestation_ok"] is False
    assert any("NOT_RUN" in reason for reason in result["attestation_failures"])
    proc = subprocess.run(
        [
            sys.executable,
            str(CLI),
            "nexus",
            "contract-check",
            "--contract-file",
            str(tmp_path / "snapshot.json"),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert proc.returncode != 0


def test_caller_supplied_values_without_evidence_are_rejected(tmp_path):
    snap = _snapshot(
        tmp_path, "--tests-passed", "--linter-exit-code", "0", "--ci-gate-exit-code", "0"
    )
    assert {v["source"] for v in snap["attestation"].values()} == {"caller_supplied"}
    result = _check(snap, tmp_path)
    assert result["ok"] is False
    assert any("self-asserted" in reason for reason in result["attestation_failures"])


def test_measured_values_with_evidence_pass(tmp_path):
    evidence = tmp_path / "delivery_gate_receipt.json"
    evidence.write_text('{"delivery_gate_passed": true}', encoding="utf-8")
    snap = _snapshot(
        tmp_path,
        "--tests-passed",
        "--linter-exit-code",
        "0",
        "--ci-gate-exit-code",
        "0",
        "--evidence-ref",
        str(evidence),
    )
    assert {v["source"] for v in snap["attestation"].values()} == {"measured"}
    result = _check(snap, tmp_path)
    assert result["ok"] is True, result

    evidence.write_text('{"delivery_gate_passed": false}', encoding="utf-8")
    tampered = _check(snap, tmp_path)
    assert tampered["ok"] is False
    assert any("sha256" in reason for reason in tampered["attestation_failures"])


def test_clean_tree_reports_no_changed_files(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    (repo / "a.py").write_text("a = 1\n", encoding="utf-8")
    _git(repo, "add", "a.py")
    _git(repo, "commit", "-q", "-m", "base")
    # A later commit already on the base must not leak into changed_files
    # (root cause of the old bug: `git show --name-only HEAD` lists the last commit's files).
    (repo / "b.py").write_text("b = 1\n", encoding="utf-8")
    _git(repo, "add", "b.py")
    _git(repo, "commit", "-q", "-m", "merged upstream")
    _git(repo, "update-ref", "refs/remotes/origin/main", "HEAD")
    _git(repo, "checkout", "-q", "--detach", "origin/main")

    files, base = closeout_guard.compute_changed_files(repo, "origin/main")
    assert files == []
    assert base is not None

    (repo / "c.py").write_text("c = 1\n", encoding="utf-8")
    (repo / "a.py").write_text("a = 2\n", encoding="utf-8")
    files, _ = closeout_guard.compute_changed_files(repo, "origin/main")
    assert files == ["a.py", "c.py"]


def test_unresolvable_base_is_unknown_not_empty(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "topic")
    (repo / "a.py").write_text("a = 1\n", encoding="utf-8")
    _git(repo, "add", "a.py")
    _git(repo, "commit", "-q", "-m", "base")
    files, base = closeout_guard.compute_changed_files(repo, "origin/main")
    assert files is None
    assert base is None
