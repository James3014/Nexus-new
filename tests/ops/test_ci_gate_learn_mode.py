import json
from pathlib import Path

from scripts.ops.ci_gate import run_learn_check


def _write_phase_slo(path: Path, passed: bool = True, required_done_ratio: float = 1.0):
    phase_payload = {
        "phase_slo_pass": passed,
        "global": {"required_done_ratio": required_done_ratio},
        "phases": {
            "P": {"required_done_ratio": 1.0, "success_ratio": 1.0},
            "X": {"required_done_ratio": 1.0, "success_ratio": 1.0},
            "D": {"required_done_ratio": 1.0, "success_ratio": 1.0},
            "R": {"required_done_ratio": 1.0, "success_ratio": 1.0},
            "A": {"required_done_ratio": 1.0, "success_ratio": 1.0},
            "C": {"required_done_ratio": 1.0, "success_ratio": 1.0},
        },
    }
    path.write_text(json.dumps(phase_payload), encoding="utf-8")


def test_run_learn_check_smoke_pass(monkeypatch, tmp_path):
    monkeypatch.setattr("scripts.ops.ci_gate.ROOT", tmp_path)
    report = tmp_path / ".nexus" / "reports" / "learn" / "learn-ci-smoke.json"
    phase_slo = tmp_path / ".nexus" / "reports" / "learn" / "phase_slo_summary.json"
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(
        json.dumps(
            {
                "claims_count": 3,
                "coverage": 0.75,
                "citation_valid_ratio": 1.0,
                "self_question_pass_rate": 0.8,
                "stale_claims_count": 0,
                "conflict_candidate_count": 0,
                "converged": True,
            }
        ),
        encoding="utf-8",
    )
    _write_phase_slo(phase_slo, passed=True, required_done_ratio=1.0)

    class _Res:
        returncode = 0

    monkeypatch.setattr("scripts.ops.ci_gate.subprocess.run", lambda *args, **kwargs: _Res())
    assert run_learn_check(mode="smoke", dry_run=True, topic="nexus") is True


def test_run_learn_check_blocks_when_claims_zero(monkeypatch, tmp_path):
    monkeypatch.setattr("scripts.ops.ci_gate.ROOT", tmp_path)
    report = tmp_path / ".nexus" / "reports" / "learn" / "learn-ci-smoke.json"
    phase_slo = tmp_path / ".nexus" / "reports" / "learn" / "phase_slo_summary.json"
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(
        json.dumps(
            {
                "claims_count": 0,
                "coverage": 0.0,
                "citation_valid_ratio": 0.0,
                "self_question_pass_rate": 0.0,
                "stale_claims_count": 0,
                "conflict_candidate_count": 0,
                "converged": False,
            }
        ),
        encoding="utf-8",
    )
    _write_phase_slo(phase_slo, passed=True, required_done_ratio=1.0)

    class _Res:
        returncode = 0

    monkeypatch.setattr("scripts.ops.ci_gate.subprocess.run", lambda *args, **kwargs: _Res())
    assert run_learn_check(mode="smoke", dry_run=False, topic="nexus") is False


def test_run_learn_check_blocks_when_citation_ratio_low(monkeypatch, tmp_path):
    monkeypatch.setattr("scripts.ops.ci_gate.ROOT", tmp_path)
    report = tmp_path / ".nexus" / "reports" / "learn" / "learn-ci-smoke.json"
    phase_slo = tmp_path / ".nexus" / "reports" / "learn" / "phase_slo_summary.json"
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(
        json.dumps(
            {
                "claims_count": 5,
                "coverage": 0.8,
                "citation_valid_ratio": 0.5,
                "self_question_pass_rate": 0.9,
                "stale_claims_count": 0,
                "conflict_candidate_count": 0,
                "converged": True,
            }
        ),
        encoding="utf-8",
    )
    _write_phase_slo(phase_slo, passed=True, required_done_ratio=1.0)

    class _Res:
        returncode = 0

    monkeypatch.setattr("scripts.ops.ci_gate.subprocess.run", lambda *args, **kwargs: _Res())
    assert run_learn_check(mode="smoke", dry_run=False, topic="nexus") is False


def test_run_learn_check_blocks_when_conflict_candidates_high(monkeypatch, tmp_path):
    monkeypatch.setattr("scripts.ops.ci_gate.ROOT", tmp_path)
    report = tmp_path / ".nexus" / "reports" / "learn" / "learn-ci-smoke.json"
    phase_slo = tmp_path / ".nexus" / "reports" / "learn" / "phase_slo_summary.json"
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(
        json.dumps(
            {
                "claims_count": 8,
                "coverage": 0.9,
                "citation_valid_ratio": 1.0,
                "self_question_pass_rate": 0.9,
                "stale_claims_count": 0,
                "conflict_candidate_count": 5,
                "converged": True,
            }
        ),
        encoding="utf-8",
    )
    _write_phase_slo(phase_slo, passed=True, required_done_ratio=1.0)

    class _Res:
        returncode = 0

    monkeypatch.setattr("scripts.ops.ci_gate.subprocess.run", lambda *args, **kwargs: _Res())
    assert run_learn_check(mode="smoke", dry_run=False, topic="nexus") is False


def test_run_learn_check_blocks_when_phase_slo_fails(monkeypatch, tmp_path):
    monkeypatch.setattr("scripts.ops.ci_gate.ROOT", tmp_path)
    report = tmp_path / ".nexus" / "reports" / "learn" / "learn-ci-smoke.json"
    phase_slo = tmp_path / ".nexus" / "reports" / "learn" / "phase_slo_summary.json"
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(
        json.dumps(
            {
                "claims_count": 6,
                "coverage": 0.9,
                "citation_valid_ratio": 1.0,
                "self_question_pass_rate": 0.8,
                "stale_claims_count": 0,
                "conflict_candidate_count": 0,
                "converged": True,
            }
        ),
        encoding="utf-8",
    )
    _write_phase_slo(phase_slo, passed=False, required_done_ratio=0.9)

    class _Res:
        returncode = 0

    monkeypatch.setattr("scripts.ops.ci_gate.subprocess.run", lambda *args, **kwargs: _Res())
    assert run_learn_check(mode="smoke", dry_run=False, topic="nexus") is False
