import hashlib
import json
import os
import subprocess
from pathlib import Path

from scripts.ops import wiki_truth_claims_check as checker


def _git_repo_with_truth_register(tmp_path: Path) -> tuple[Path, Path]:
    repo = tmp_path / "repo"
    register = repo / "nexus_wiki_vault" / "06_Ops" / "Ops - Truth Claims Register.md"
    ledger = repo / ".nexus" / "reports" / "learn" / "learning_closure.jsonl"
    register.parent.mkdir(parents=True)
    ledger.parent.mkdir(parents=True)
    (repo / "scripts").mkdir()
    (repo / "sentinel.txt").write_text("sentinel\n", encoding="utf-8")
    ledger.write_text('{"existing": true}\n', encoding="utf-8")
    register.write_text(
        "| ID | Claim | Evidence | Command | Status | Date |\n"
        "|---|---|---|---|---|---|\n"
        "| `C-01` | file exists | `sentinel.txt` | `test -f sentinel.txt` | ✅ | 2026-07-15 |\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "add", "sentinel.txt", str(ledger.relative_to(repo))], check=True)
    subprocess.run(["git", "-C", str(repo), "-c", "user.name=Test", "-c", "user.email=test@example.com", "commit", "-qm", "fixture"], check=True)
    return repo, ledger


def test_truth_claims_audit_mode_blocks_learning_writeback(monkeypatch, tmp_path: Path):
    repo, ledger = _git_repo_with_truth_register(tmp_path)
    monkeypatch.setattr(checker, "REPO_ROOT", repo)
    monkeypatch.setattr(checker, "VAULT_ROOT", repo / "nexus_wiki_vault")
    monkeypatch.setattr(checker, "REPORT_PATH", repo / ".nexus" / "reports" / "truth.json")
    monkeypatch.setenv("NEXUS_AUDIT_READ_ONLY", "1")
    monkeypatch.setenv("NEXUS_LEARN_CLOSURE_WRITEBACK", "0")

    before = hashlib.sha256(ledger.read_bytes()).hexdigest()
    summary = checker.run_checks()
    after = hashlib.sha256(ledger.read_bytes()).hexdigest()

    from nexus.research.learn_mode import LearnModeService

    closure = LearnModeService(repo)._persist_learning_closure(
        action="ask",
        status="PARTIAL",
        reason="test",
        topic_or_source="test",
        evidence_paths=[],
        retrieval_hints=[],
        metrics={},
    )

    assert summary["status"] == "PASS"
    assert before == after
    assert closure["writeback_disabled"] is True
    assert not list((repo / ".nexus" / "memory").rglob("*") if (repo / ".nexus" / "memory").exists() else [])


def test_truth_claims_audit_mode_still_executes_real_claim_commands(monkeypatch, tmp_path: Path):
    repo, _ledger = _git_repo_with_truth_register(tmp_path)
    monkeypatch.setattr(checker, "REPO_ROOT", repo)
    monkeypatch.setattr(checker, "VAULT_ROOT", repo / "nexus_wiki_vault")
    monkeypatch.setattr(checker, "REPORT_PATH", repo / ".nexus" / "reports" / "truth.json")
    monkeypatch.setenv("NEXUS_AUDIT_READ_ONLY", "1")

    summary = checker.run_checks()
    report = json.loads((repo / ".nexus" / "reports" / "truth.json").read_text())

    assert summary["total_claims"] == 1
    assert report["details"][0]["status"] == "MATCH"
    assert report["details"][0]["stdout"] == ""


def test_truth_claims_environment_failure_still_blocks_gate(monkeypatch, tmp_path: Path):
    repo, _ledger = _git_repo_with_truth_register(tmp_path)
    register = repo / "nexus_wiki_vault" / "06_Ops" / "Ops - Truth Claims Register.md"
    register.write_text(register.read_text(encoding="utf-8").replace("test -f sentinel.txt", "test -f definitely_missing.txt"), encoding="utf-8")
    monkeypatch.setattr(checker, "REPO_ROOT", repo)
    monkeypatch.setattr(checker, "VAULT_ROOT", repo / "nexus_wiki_vault")
    monkeypatch.setattr(checker, "REPORT_PATH", repo / ".nexus" / "reports" / "truth.json")

    summary = checker.run_checks()

    assert summary["status"] == "FAIL"
    assert summary["mismatch_count"] == 1


def test_non_audit_mode_preserves_existing_writeback_behavior(monkeypatch):
    from nexus.research.learn_mode import LearnModeService

    monkeypatch.delenv("NEXUS_AUDIT_READ_ONLY", raising=False)
    monkeypatch.setenv("NEXUS_LEARN_CLOSURE_WRITEBACK", "0")

    closure = LearnModeService(Path.cwd())._persist_learning_closure(
        action="ask",
        status="PARTIAL",
        reason="test",
        topic_or_source="test",
        evidence_paths=[],
        retrieval_hints=[],
        metrics={},
    )

    assert os.environ.get("NEXUS_AUDIT_READ_ONLY") is None
    assert closure["writeback_disabled"] is True
