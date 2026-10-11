"""`nexus run` VERIFIED must be bound to a delivery-gate receipt for this run and HEAD."""

import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

from click.testing import CliRunner

import scripts.engine.nexus_cli as cli_mod
from nexus.delivery.receipt import write_delivery_receipt
from nexus.engine.completion_contract import (
    build_completion_envelope,
    evaluate_delivery_closeout,
)

TASK = "closeout-task"


class _RuntimeResult(SimpleNamespace):
    def __bool__(self):
        return bool(self.ok)


def _runtime_result():
    return _RuntimeResult(
        ok=True,
        receipt={
            "task_id": TASK,
            "workspace_revision": "test-revision",
            "receipt_complete": True,
            "local": {"status": "NOT_REQUESTED", "gate_passed": False},
            "online": {
                "status": "SUCCEEDED",
                "gate_passed": True,
                "response": {"provider": "fixture"},
            },
            "claim_boundary": {"public_claim_allowed": False},
        },
        receipt_path="/tmp/canonical-runtime.json",
        root_receipt={"root_receipt_hash": "sha256:" + "a" * 64},
        root_receipt_valid=True,
        root_receipt_blockers=(),
        execution_decision_authority="CapabilityPlanner",
        production_ingress_count=1,
        production_runtime_entry_count=1,
    )


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", *args],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


def _init_repo(repo: Path) -> str:
    _git(repo, "init", "-q")
    (repo / "a.txt").write_text("a", encoding="utf-8")
    _git(repo, "add", "a.txt")
    _git(repo, "commit", "-q", "-m", "init")
    return _git(repo, "rev-parse", "HEAD")


def _write_receipt(repo: Path, *, run_id: str | None, head_sha: str, gate_ok: bool = True) -> Path:
    """Produce a receipt with the real writer from real gate input files."""
    inputs = repo / "gate_inputs"
    inputs.mkdir(exist_ok=True)
    evidence = inputs / "evidence.json"
    baseline = inputs / "baseline.json"
    acceptance = inputs / "acceptance.json"
    evidence.write_text(
        json.dumps({"evidence_bundle": {"test_artifacts": ["verified"]}}), encoding="utf-8"
    )
    baseline.write_text(json.dumps({"version": "1"}), encoding="utf-8")
    acceptance.write_text(
        json.dumps({
            "status": "PASS" if gate_ok else "FAIL",
            "gate_passed": gate_ok,
            "criteria": [
                {"name": "report_claim_integrity", "passed": True, "detail": {"passed": True}},
            ],
        }),
        encoding="utf-8",
    )
    return write_delivery_receipt(
        receipt_path=repo / ".nexus" / "reports" / "delivery_gate.json",
        evidence_path=evidence,
        baseline_path=baseline,
        acceptance_report=acceptance,
        acceptance_policy="dev",
        acceptance_exit_code=0 if gate_ok else 1,
        acceptance_status="PASS" if gate_ok else "FAIL",
        acceptance_gate=gate_ok,
        acceptance_primary="none",
        run_id=run_id,
        head_sha=head_sha,
    )


def _run_cli(monkeypatch, repo: Path):
    monkeypatch.setattr(cli_mod, "REPO_ROOT", repo)
    monkeypatch.setattr(
        cli_mod, "execute_canonical_product_task", lambda *_a, **_k: _runtime_result()
    )
    report_path = repo / "reports" / "run_report.json"
    res = CliRunner().invoke(
        cli_mod.nexus, ["nexus", "run", TASK, "--report-file", str(report_path)]
    )
    report = json.loads(report_path.read_text(encoding="utf-8"))
    return res, report


def test_run_without_receipt_is_unverified(monkeypatch, tmp_path):
    _init_repo(tmp_path)
    res, report = _run_cli(monkeypatch, tmp_path)
    assert res.exit_code != 0
    assert report["status"] == "SUCCESS"
    assert report["semantic_status"] == "UNVERIFIED"
    assert "delivery_gate_not_run" in report["semantic_failures"]


def test_run_with_matching_receipt_is_verified(monkeypatch, tmp_path):
    head = _init_repo(tmp_path)
    _write_receipt(tmp_path, run_id=TASK, head_sha=head)
    res, report = _run_cli(monkeypatch, tmp_path)
    assert res.exit_code == 0, res.output
    assert report["semantic_status"] == "VERIFIED"
    assert report["semantic_failures"] == []


def test_run_with_stale_sha_receipt_is_unverified(monkeypatch, tmp_path):
    head = _init_repo(tmp_path)
    _write_receipt(tmp_path, run_id=TASK, head_sha=head)
    (tmp_path / "b.txt").write_text("b", encoding="utf-8")
    _git(tmp_path, "add", "b.txt")
    _git(tmp_path, "commit", "-q", "-m", "advance")
    res, report = _run_cli(monkeypatch, tmp_path)
    assert res.exit_code != 0
    assert report["semantic_status"] == "UNVERIFIED"
    assert "delivery_receipt_stale" in report["semantic_failures"]


def test_receipt_for_other_run_is_unverified(tmp_path):
    head = _init_repo(tmp_path)
    receipt = _write_receipt(tmp_path, run_id="some-other-run", head_sha=head)
    assert evaluate_delivery_closeout(receipt_path=receipt, run_id=TASK, head_sha=head) == [
        "delivery_receipt_run_mismatch"
    ]


def test_receipt_without_run_id_is_unverified(tmp_path, monkeypatch):
    monkeypatch.delenv("NEXUS_RUN_ID", raising=False)
    head = _init_repo(tmp_path)
    receipt = _write_receipt(tmp_path, run_id=None, head_sha=head)
    assert evaluate_delivery_closeout(receipt_path=receipt, run_id=TASK, head_sha=head) == [
        "delivery_receipt_run_mismatch"
    ]


def test_failed_gate_receipt_is_unverified(tmp_path):
    head = _init_repo(tmp_path)
    receipt = _write_receipt(tmp_path, run_id=TASK, head_sha=head, gate_ok=False)
    assert evaluate_delivery_closeout(receipt_path=receipt, run_id=TASK, head_sha=head) == [
        "delivery_gate_failed"
    ]


def test_envelope_default_unchanged_for_other_commands():
    payload = build_completion_envelope(
        command_name="swarm", task_name="t", runtime_ok=True, execution_path="x"
    )
    assert payload["semantic_status"] == "VERIFIED"
