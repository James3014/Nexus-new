import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest
from click.testing import CliRunner

import scripts.engine.nexus_cli as cli_module
from nexus.delivery.status_report import build_status_report

REPO_ROOT = Path(__file__).resolve().parents[2]


def _vcs(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=root, check=True, capture_output=True, text=True
    ).stdout.strip()


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    _vcs(tmp_path, "init", "-q")
    _vcs(
        tmp_path,
        "-c",
        "user.email=t@example.com",
        "-c",
        "user.name=t",
        "commit",
        "-q",
        "--allow-empty",
        "-m",
        "init",
    )
    return tmp_path


def _write_receipt(root: Path, head_sha: str, passed: bool = True) -> None:
    reports = root / ".nexus" / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at_utc": "2026-01-01T00:00:00+00:00",
        "head_sha": head_sha,
        "delivery_gate_passed": passed,
    }
    (reports / "delivery_gate.json").write_text(json.dumps(payload), encoding="utf-8")


def _invoke(root: Path, monkeypatch, args: list[str]):
    monkeypatch.setattr(cli_module, "repo_root", root)
    return CliRunner().invoke(cli_module.nexus, args)


def test_status_without_evidence_is_unverified_and_has_no_hardcoded_pass(repo, monkeypatch) -> None:
    for args in (["nexus", "status", "--json"], ["status", "--json"]):
        result = _invoke(repo, monkeypatch, args)
        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert payload["schema"] == "nexus.status_report.v1"
        assert payload["overall"] == "UNVERIFIED"
        assert payload["health_claimed"] is False
        assert payload["delivery_receipt"]["state"] == "NOT_MEASURED"
        assert payload["acceptance_check"]["state"] == "NOT_MEASURED"
        assert payload["governance_seal"]["state"] == "NOT_MEASURED"
        assert set(payload["not_measured"].values()) == {"NOT_MEASURED"}
        for forbidden in ("PASS", "OPERATIONAL", "READY", "0.005", "0.85", "v23.7"):
            assert forbidden not in result.output

    human = _invoke(repo, monkeypatch, ["nexus", "status"])
    assert human.exit_code == 0, human.output
    assert "NOT_MEASURED" in human.output and "UNVERIFIED" in human.output
    assert "PASS" not in human.output and "Audit Complete" not in human.output


def test_status_reports_real_delivery_receipt_for_current_head(repo, monkeypatch) -> None:
    head = _vcs(repo, "rev-parse", "HEAD")
    _write_receipt(repo, head)
    payload = json.loads(_invoke(repo, monkeypatch, ["nexus", "status", "--json"]).output)
    assert payload["head_sha"] == head
    assert payload["delivery_receipt"]["state"] == "MATCHES_HEAD"
    assert payload["delivery_receipt"]["head_sha"] == head
    assert payload["delivery_receipt"]["generated_at_utc"] == "2026-01-01T00:00:00+00:00"
    assert payload["overall"] == "EVIDENCE_PRESENT"
    assert payload["health_claimed"] is False
    assert set(payload["not_measured"].values()) == {"NOT_MEASURED"}


def test_status_reports_stale_receipt_for_other_head(repo, monkeypatch) -> None:
    _write_receipt(repo, "f" * 40)
    payload = build_status_report(repo)
    assert payload["delivery_receipt"]["state"] == "STALE"
    assert payload["overall"] == "UNVERIFIED"
    result = _invoke(repo, monkeypatch, ["nexus", "status"])
    assert result.exit_code == 0
    assert "STALE" in result.output


def test_status_reports_governance_seal_match_and_drift(repo) -> None:
    tracked = repo / "a.txt"
    tracked.write_text("one", encoding="utf-8")
    config = repo / ".nexus" / "config"
    config.mkdir(parents=True)
    seal = {"files": {"a.txt": hashlib.sha256(b"one").hexdigest()}}
    (config / "governance_seal.json").write_text(json.dumps(seal), encoding="utf-8")
    assert build_status_report(repo)["governance_seal"]["state"] == "MATCH"
    tracked.write_text("two", encoding="utf-8")
    assert build_status_report(repo)["governance_seal"]["state"] == "DRIFT"


def test_enterprise_audit_report_is_flagged_simulated_and_not_run(tmp_path: Path) -> None:
    subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "ops" / "enterprise_audit_v22.py")],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    report = json.loads(
        (tmp_path / ".nexus" / "reports" / "enterprise_audit.json").read_text(encoding="utf-8")
    )
    assert report["status"] == "SIMULATED"
    assert report["semantic_status"] == "UNVERIFIED"
    assert report["simulated"] is True
    assert report["nexus_participation_ratio"] is None
    assert set(report["gate_summary"].values()) == {"NOT_RUN"}
    assert report["results"]
    assert all(
        item["status"] == "SIMULATED" and item["simulated"] is True for item in report["results"]
    )
    assert "PASS" not in json.dumps(report)
